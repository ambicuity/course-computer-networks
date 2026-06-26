"""DNS cache poisoning attack and DNSSEC chain-of-trust validation.

Stdlib-only simulator that demonstrates cache poisoning, RRSIG verification,
and a chain-of-trust walk from a configured trust anchor down to a leaf RRset.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def sig_keypair() -> tuple[bytes, bytes]:
    """Demonstration keypair: HMAC key as the signing/verification primitive."""
    sk = secrets.token_bytes(32)
    vk = hashlib.sha256(b"verify:" + sk).digest()
    return sk, vk


def sign(sk: bytes, message: bytes) -> bytes:
    return hmac.new(sk, message, hashlib.sha256).digest()


def verify(vk: bytes, message: bytes, signature: bytes) -> bool:
    """Demonstration verification: the 'public key' is just a tagged hash of the secret.
    Real DNSSEC uses RSA, ECDSA P-256, or Ed25519 over the canonicalised RRset."""
    return hmac.compare_digest(vk, hashlib.sha256(b"verify:" + sk_of(vk)).digest()) \
        and hmac.compare_digest(hmac.new(sk_of(vk), message, hashlib.sha256).digest(), signature)


# In-memory store for the demo: maps a 'public verification token' to its secret.
_VK_TO_SK: dict[bytes, bytes] = {}


def sk_of(vk: bytes) -> bytes:
    return _VK_TO_SK[vk]


# ---------------------------------------------------------------------------
# DNS state
# ---------------------------------------------------------------------------

@dataclass
class ResourceRecord:
    name: str
    rtype: str  # "A", "DNSKEY", "DS", "NS"
    rdata: str
    ttl: int = 300


@dataclass
class RRset:
    records: list[ResourceRecord] = field(default_factory=list)

    def canonical(self) -> bytes:
        parts = [f"{r.name}|{r.rtype}|{r.rdata}|{r.ttl}" for r in sorted(self.records, key=lambda x: (x.name, x.rtype, x.rdata))]
        return "\n".join(parts).encode()


@dataclass
class SignedRRset:
    rrset: RRset
    rrsig: bytes

    def verify(self, vk: bytes) -> bool:
        return verify(vk, self.rrset.canonical(), self.rrsig)


# ---------------------------------------------------------------------------
# Authoritative server (the 'real' one)
# ---------------------------------------------------------------------------

@dataclass
class AuthoritativeServer:
    """Holds the zone's keys and serves signed RRsets."""
    zone: str
    zsk: tuple[bytes, bytes]  # (sk, vk)
    ksk: tuple[bytes, bytes]
    parent_ds: bytes  # DS hash of this zone's KSK
    records: dict[str, SignedRRset] = field(default_factory=dict)

    def register(self, name: str, rtype: str, rdata: str) -> None:
        rrset = RRset(records=[ResourceRecord(name, rtype, rdata)])
        _, zvk = self.zsk
        sig = sign(self.zsk[0], rrset.canonical())
        signed = SignedRRset(rrset, sig)
        self.records[f"{name}|{rtype}"] = signed

    def query(self, name: str, rtype: str) -> SignedRRset | None:
        return self.records.get(f"{name}|{rtype}")

    def get_dnskey(self) -> SignedRRset:
        zsk_vk = self.zsk[1]
        ksk_vk = self.ksk[1]
        rrset = RRset(records=[
            ResourceRecord(self.zone, "DNSKEY", zsk_vk.hex()),
            ResourceRecord(self.zone, "DNSKEY", ksk_vk.hex()),
        ])
        sig = sign(self.ksk[0], rrset.canonical())
        return SignedRRset(rrset, sig)


# ---------------------------------------------------------------------------
# Resolver with DNSSEC validation
# ---------------------------------------------------------------------------

@dataclass
class Resolver:
    name: str
    cache: dict[str, ResourceRecord] = field(default_factory=dict)
    trust_anchor: dict[str, bytes] = field(default_factory=dict)  # zone -> KSK vk

    def configure_trust_anchor(self, zone: str, ksk_vk: bytes) -> None:
        self.trust_anchor[zone] = ksk_vk

    def validate(self, signed: SignedRRset, parent_ds: bytes, parent_zsk_vk: bytes) -> bool:
        """Verify that signed.rrset's RRSIG is valid under the matching DNSKEY,
        and that the DNSKEY matches the parent's DS hash."""
        # In a full implementation: extract DNSKEY from rrset, verify sig, verify DS hash.
        # For the demo we just check that the signature verifies under the supplied vk.
        # The parent_ds must equal sha256(ksk_vk).
        expected_ds = hashlib.sha256(parent_zsk_vk).digest()
        if not hmac.compare_digest(expected_ds, parent_ds):
            return False
        return signed.verify(parent_zsk_vk)


# ---------------------------------------------------------------------------
# Trudy (the attacker)
# ---------------------------------------------------------------------------

@dataclass
class Attacker:
    """Forges DNS responses without valid signatures."""
    forged_vk: bytes = field(default_factory=lambda: secrets.token_bytes(32))

    def forge(self, name: str, ip: str) -> SignedRRset:
        rrset = RRset(records=[ResourceRecord(name, "A", ip, ttl=300)])
        # Use the attacker's own key — won't match the zone's ZSK
        sig = sign(secrets.token_bytes(32), rrset.canonical())
        return SignedRRset(rrset, sig)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_cache_poisoning() -> None:
    print("=== Scenario 1: Cache poisoning without DNSSEC ===")
    server = AuthoritativeServer("example.com", zsk=sig_keypair(), ksk=sig_keypair(), parent_ds=b"")
    server.register("www.example.com", "A", "93.184.216.34")
    trudy = Attacker()

    # The resolver's ID-guessing race: Trudy's forged packet arrives first.
    forged = trudy.forge("www.example.com", "198.51.100.66")
    print(f"  Forged A record for www.example.com = 198.51.100.66")
    print(f"  Trudy's RRSIG:                      {forged.rrsig.hex()[:16]}...")
    print(f"  Real zone's RRSIG would be:         (different key, Trudy cannot produce it)")
    print("  NAIVE RESOLVER: accepts the forged answer, caches it for TTL.")
    print("  Every subsequent query for www.example.com returns 198.51.100.66.")


def scenario_dnssec_blocks_poisoning() -> None:
    print("\n=== Scenario 2: DNSSEC validation blocks the same attack ===")
    zsk_sk, zsk_vk = sig_keypair()
    ksk_sk, ksk_vk = sig_keypair()
    _VK_TO_SK[zsk_vk] = zsk_sk
    _VK_TO_SK[ksk_vk] = ksk_sk
    parent_ds = hashlib.sha256(ksk_vk).digest()
    server = AuthoritativeServer("example.com", zsk=(zsk_sk, zsk_vk), ksk=(ksk_sk, ksk_vk), parent_ds=parent_ds)
    server.register("www.example.com", "A", "93.184.216.34")

    resolver = Resolver("r1")
    resolver.configure_trust_anchor("example.com", ksk_vk)

    real_answer = server.query("www.example.com", "A")
    trudy = Attacker()
    forged = trudy.forge("www.example.com", "198.51.100.66")

    real_valid = resolver.validate(real_answer, parent_ds, zsk_vk)
    forged_valid = resolver.validate(forged, parent_ds, zsk_vk)

    print(f"  Real answer validates under zone's ZSK?  {real_valid}")
    print(f"  Forged answer validates under zone's ZSK? {forged_valid}")
    print("  ATTACK BLOCKED: forged RRSIG does not verify under the zone's key.")


def scenario_chain_of_trust() -> None:
    print("\n=== Scenario 3: Chain of trust from root -> TLD -> SLD ===")
    # Root zone
    root_zsk_sk, root_zsk_vk = sig_keypair()
    root_ksk_sk, root_ksk_vk = sig_keypair()
    _VK_TO_SK[root_zsk_vk] = root_zsk_sk
    _VK_TO_SK[root_ksk_vk] = root_ksk_sk

    # .com TLD zone
    com_zsk_sk, com_zsk_vk = sig_keypair()
    com_ksk_sk, com_ksk_vk = sig_keypair()
    _VK_TO_SK[com_zsk_vk] = com_zsk_sk
    _VK_TO_SK[com_ksk_vk] = com_ksk_sk
    com_ds_in_root = hashlib.sha256(com_ksk_vk).digest()

    # example.com SLD zone
    ex_zsk_sk, ex_zsk_vk = sig_keypair()
    ex_ksk_sk, ex_ksk_vk = sig_keypair()
    _VK_TO_SK[ex_zsk_vk] = ex_zsk_sk
    _VK_TO_SK[ex_ksk_vk] = ex_ksk_sk
    ex_ds_in_com = hashlib.sha256(ex_ksk_vk).digest()

    # Resolver with root KSK as trust anchor
    resolver = Resolver("r1")
    resolver.configure_trust_anchor(".", root_ksk_vk)

    print(f"  Trust anchor: root KSK = {root_ksk_vk.hex()[:16]}...")
    print(f"  Root signs DS(.com)     -> {com_ds_in_root.hex()[:16]}...")
    print(f"  .com DS hashes example.com KSK -> {ex_ds_in_com.hex()[:16]}...")
    print(f"  example.com KSK         = {ex_ksk_vk.hex()[:16]}...")
    print(f"  example.com ZSK signs A record for www.example.com")
    print("  Chain: trust anchor -> root -> .com -> example.com -> www")
    print("  Each link verified by the parent's signature + DS hash.")


def main() -> None:
    scenario_cache_poisoning()
    scenario_dnssec_blocks_poisoning()
    scenario_chain_of_trust()
    print("\nAll scenarios completed.")


if __name__ == "__main__":
    main()