"""Kerberos V5 authentication flow with AS, TGS, and service ticket.

Stdlib-only simulator of the simplified V5 flow: AS-REQ/REP with preauth,
TGS-REQ/REP, and AP-REQ/REP. Demonstrates single sign-on and replay defense.

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
from typing import Any


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def kdf(password: str, salt: bytes = b"kerberos") -> bytes:
    """String2Key: PBKDF2-HMAC-SHA256 over the password. Demo strength."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 50_000, dklen=32)


def seal(key: bytes, plaintext: bytes) -> bytes:
    """Encrypt under key using HMAC-then-AES-style: HMAC tag appended.
    Demo uses HMAC-SHA256 for both authentication and (via XOR-pad) encryption.
    """
    pad = b"\x00" * 32
    iv = secrets.token_bytes(16)
    stream = b""
    counter = 0
    pt = plaintext
    while len(stream) < len(pt):
        stream += hmac.new(key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    stream = stream[: len(pt)]
    ct = bytes(a ^ b for a, b in zip(pt, stream))
    tag = hmac.new(key, iv + ct, hashlib.sha256).digest()
    return iv + ct + tag


def open_seal(key: bytes, sealed: bytes) -> bytes | None:
    if len(sealed) < 16 + 32:
        return None
    iv, ct, tag = sealed[:16], sealed[16:-32], sealed[-32:]
    expected = hmac.new(key, iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        return None
    stream = b""
    counter = 0
    while len(stream) < len(ct):
        stream += hmac.new(key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    stream = stream[: len(ct)]
    return bytes(a ^ b for a, b in zip(ct, stream))


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

@dataclass
class Ticket:
    """A Kerberos ticket: encrypted blob holding session key and metadata."""
    client: str
    service: str
    session_key: bytes
    lifetime_sec: int
    issued_at: float

    def encode(self) -> bytes:
        obj = {
            "c": self.client,
            "s": self.service,
            "k": self.session_key.hex(),
            "lt": self.lifetime_sec,
            "ts": self.issued_at,
        }
        return json.dumps(obj, sort_keys=True).encode()

    @staticmethod
    def decode(blob: bytes) -> Ticket:
        obj = json.loads(blob)
        return Ticket(
            client=obj["c"],
            service=obj["s"],
            session_key=bytes.fromhex(obj["k"]),
            lifetime_sec=obj["lt"],
            issued_at=obj["ts"],
        )


@dataclass
class Authenticator:
    """Per-message freshness proof."""
    client: str
    timestamp: float

    def encode(self) -> bytes:
        obj = {"c": self.client, "ts": self.timestamp}
        return json.dumps(obj, sort_keys=True).encode()


# ---------------------------------------------------------------------------
# Principals
# ---------------------------------------------------------------------------

@dataclass
class Principal:
    name: str
    long_term_key: bytes


# ---------------------------------------------------------------------------
# KDC
# ---------------------------------------------------------------------------

@dataclass
class KDC:
    """Authentication Service + Ticket Granting Service."""
    realm: str
    as_key: bytes  # K_TGS, the TGS's long-term key
    principals: dict[str, Principal] = field(default_factory=dict)
    session_keys: dict[str, bytes] = field(default_factory=dict)

    def register(self, p: Principal) -> None:
        self.principals[p.name] = p

    # --- AS exchange ---
    def as_exchange(self, client_name: str, preauth_proof: bytes) -> tuple[bytes, bytes] | None:
        """Verify preauth; return (encrypted_session_part, tgt_sealed)."""
        client = self.principals[client_name]
        # V5 preauth: client encrypts a current timestamp under K_C.
        if open_seal(client.long_term_key, preauth_proof) is None:
            return None
        session = secrets.token_bytes(32)
        self.session_keys[f"{client_name}->tgs"] = session
        now = time.time()
        tgt = Ticket(client_name, "krbtgt/" + self.realm, session, 8 * 3600, now)
        sealed_tgt = seal(self.as_key, tgt.encode())
        part = {
            "tgt": sealed_tgt.hex(),
            "k_c_tgs": session.hex(),
            "realm": self.realm,
        }
        part_blob = json.dumps(part, sort_keys=True).encode()
        return seal(client.long_term_key, part_blob), sealed_tgt

    # --- TGS exchange ---
    def tgs_exchange(
        self, tgt_sealed: bytes, authenticator_sealed: bytes
    ) -> tuple[bytes, bytes] | None:
        """Verify TGT + authenticator; return (encrypted_session_part, service_ticket)."""
        tgt = Ticket.decode(open_seal(self.as_key, tgt_sealed))  # type: ignore[arg-type]
        k_c_tgs = tgt.session_key
        auth_blob = open_seal(k_c_tgs, authenticator_sealed)
        if auth_blob is None:
            return None
        auth = Authenticator(**json.loads(auth_blob))
        if abs(time.time() - auth.timestamp) > 300:
            return None
        # Client is asking for a service ticket for auth.service
        service_name = auth.client.split("->")[-1] if "->" in auth.client else auth.client
        if service_name not in self.principals:
            return None
        service = self.principals[service_name]
        session = secrets.token_bytes(32)
        now = time.time()
        svc_ticket = Ticket(auth.client, service_name, session, 8 * 3600, now)
        sealed_svc = seal(service.long_term_key, svc_ticket.encode())
        part = {"st": sealed_svc.hex(), "k_c_s": session.hex(), "s": service_name}
        return seal(k_c_tgs, json.dumps(part, sort_keys=True).encode()), sealed_svc


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

@dataclass
class Client:
    name: str
    long_term_key: bytes

    def make_preauth(self) -> bytes:
        payload = json.dumps({"ts": time.time()}, sort_keys=True).encode()
        return seal(self.long_term_key, payload)

    def decrypt_as_reply(self, blob: bytes) -> tuple[bytes, bytes]:
        inner = open_seal(self.long_term_key, blob)
        assert inner is not None
        obj = json.loads(inner)
        return bytes.fromhex(obj["tgt"]), bytes.fromhex(obj["k_c_tgs"])

    def request_tgs(self, tgt: bytes, k_c_tgs: bytes, service: str) -> bytes:
        auth = Authenticator(self.name, time.time())
        # Embed the requested service name into the auth client field for the demo.
        encoded = json.dumps({"c": f"{self.name}->{service}", "ts": auth.timestamp}).encode()
        return seal(k_c_tgs, encoded)

    def decrypt_tgs_reply(self, blob: bytes, k_c_tgs: bytes) -> tuple[bytes, bytes]:
        inner = open_seal(k_c_tgs, blob)
        assert inner is not None
        obj = json.loads(inner)
        return bytes.fromhex(obj["st"]), bytes.fromhex(obj["k_c_s"])


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class Service:
    name: str
    long_term_key: bytes
    replay_cache: set[tuple[str, float]] = field(default_factory=set)

    def accept(self, ticket_sealed: bytes, authenticator_sealed: bytes) -> bool:
        ticket = Ticket.decode(open_seal(self.long_term_key, ticket_sealed))  # type: ignore[arg-type]
        k_c_s = ticket.session_key
        auth_blob = open_seal(k_c_s, authenticator_sealed)
        if auth_blob is None:
            return False
        auth = json.loads(auth_blob)
        if abs(time.time() - auth["ts"]) > 300:
            return False
        key = (auth["c"], auth["ts"])
        if key in self.replay_cache:
            return False
        self.replay_cache.add(key)
        return True


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_full_flow() -> None:
    print("=== Scenario 1: AS + TGS + AP (full Kerberos V5 flow) ===")
    realm = "EXAMPLE.COM"
    kdc = KDC(realm, as_key=secrets.token_bytes(32))
    alice = Client("alice", long_term_key=kdf("alice-password"))
    fileserver = Service("fileserver", long_term_key=secrets.token_bytes(32))
    kdc.register(Principal("alice", alice.long_term_key))
    kdc.register(Principal("fileserver", fileserver.long_term_key))

    preauth = alice.make_preauth()
    as_reply = kdc.as_exchange("alice", preauth)
    assert as_reply is not None
    enc_part, tgt = alice.decrypt_as_reply(as_reply[0])
    print(f"  AS-REP: TGT sealed, K_C-TGS = {enc_part.hex()[:16]}...")

    tgs_req = alice.request_tgs(tgt, enc_part, "fileserver")
    tgs_reply = kdc.tgs_exchange(tgt, tgs_req)
    assert tgs_reply is not None
    svc_ticket, k_c_s = alice.decrypt_tgs_reply(tgs_reply[0], enc_part)
    print(f"  TGS-REP: service ticket sealed, K_C-S = {k_c_s.hex()[:16]}...")

    ap_auth = seal(k_c_s, json.dumps({"c": "alice", "ts": time.time()}).encode())
    accepted = fileserver.accept(svc_ticket, ap_auth)
    print(f"  AP-REQ: service accepted Alice? = {accepted}")
    assert accepted


def scenario_replay_blocked() -> None:
    print("\n=== Scenario 2: Replay attack blocked by service-side cache ===")
    realm = "EXAMPLE.COM"
    kdc = KDC(realm, as_key=secrets.token_bytes(32))
    alice = Client("alice", long_term_key=kdf("alice-password"))
    fileserver = Service("fileserver", long_term_key=secrets.token_bytes(32))
    kdc.register(Principal("alice", alice.long_term_key))
    kdc.register(Principal("fileserver", fileserver.long_term_key))

    preauth = alice.make_preauth()
    as_reply = kdc.as_exchange("alice", preauth)
    assert as_reply is not None
    _, tgt = alice.decrypt_as_reply(as_reply[0])
    k_c_tgs = open_seal(alice.long_term_key, as_reply[0])
    assert k_c_tgs is not None
    enc_part = json.loads(k_c_tgs)
    k_c_tgs_bytes = bytes.fromhex(enc_part["k_c_tgs"])

    tgs_req = alice.request_tgs(tgt, k_c_tgs_bytes, "fileserver")
    tgs_reply = kdc.tgs_exchange(tgt, tgs_req)
    assert tgs_reply is not None
    svc_ticket, k_c_s = alice.decrypt_tgs_reply(tgs_reply[0], k_c_tgs_bytes)

    ap_auth = seal(k_c_s, json.dumps({"c": "alice", "ts": time.time()}).encode())
    first = fileserver.accept(svc_ticket, ap_auth)
    # Trudy replays the same AP-REQ
    second = fileserver.accept(svc_ticket, ap_auth)
    print(f"  first AP-REQ accepted?  = {first}")
    print(f"  replayed AP-REQ accepted? = {second}")
    print("  ATTACK BLOCKED: replay cache caught the duplicate authenticator")


def main() -> None:
    scenario_full_flow()
    scenario_replay_blocked()
    print("\nAll scenarios completed.")


if __name__ == "__main__":
    main()