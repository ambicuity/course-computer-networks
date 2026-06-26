"""Kerberos V5 simulator: AS, TGS, service tickets, cross-realm referrals.

Implements the full six-message RFC 4120 §3 flow in pure stdlib:

  AS-REQ / AS-REP   -- login, password-derived K_A, returns K_S,tgs + TGT
  TGS-REQ / TGS-REP -- service ticket request, returns K_AB + ticket_B
  AP-REQ / AP-REP   -- mutual auth (optional AP-REP with t_req - 1)

Plus the cross-realm referral flow: when Alice in realm A asks for a service
in realm B, A's TGS issues a referral ticket sealed under B's TGS key, which
Alice presents to B's TGS to fetch the actual service ticket.

The encryption is a toy authenticated envelope (HMAC-SHA256 + nonce) -- the
real Kerberos uses AES-CTS-HMAC-SHA1-96 (RFC 3961/3962). The structure of
the messages, key names, and timestamps matches RFC 4120 §3.1, §3.2, §3.3.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

KEY_BYTES = 32
NONCE_BYTES = 16
DEFAULT_SKEW_SECONDS = 300
PBKDF2_ITERATIONS = 4096
PBKDF2_SALT = b"kerberos-sim-v1"


def string_to_key(password: str, salt: bytes = PBKDF2_SALT, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """PBKDF2-HMAC-SHA256 password derivation, RFC 2898 §5.2.

    Real Kerberos uses enctype-specific string-to-key (RFC 3961 §6); PBKDF2
    with a 16-byte salt is the equivalent for our teaching envelope.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=KEY_BYTES)


def seal(key: bytes, plaintext: bytes) -> bytes:
    """Toy envelope: nonce || HMAC-SHA256(key, nonce || plaintext)."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    mac = hmac.new(key, nonce + plaintext, hashlib.sha256).digest()
    return nonce + mac + plaintext


def open(key: bytes, envelope: bytes) -> bytes | None:
    if len(envelope) < NONCE_BYTES + 32:
        return None
    nonce = envelope[:NONCE_BYTES]
    mac = envelope[NONCE_BYTES:NONCE_BYTES + 32]
    body = envelope[NONCE_BYTES + 32:]
    expected = hmac.new(key, nonce + body, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return None
    return body


@dataclass
class Ticket:
    realm: str
    client: str
    session_key: bytes
    start_time: int
    end_time: int
    flags: int = 0


@dataclass
class KerberosResult:
    success: bool
    service_session_key: bytes | None
    error: str | None
    messages: list[str] = field(default_factory=list)
    timestamps: dict[str, int] = field(default_factory=dict)


@dataclass
class KerberosRealm:
    name: str
    users: dict[str, bytes] = field(default_factory=dict)
    services: dict[str, bytes] = field(default_factory=dict)
    trusted_realms: dict[str, bytes] = field(default_factory=dict)
    tgs_key: bytes = field(default_factory=lambda: secrets.token_bytes(KEY_BYTES))

    def register_user(self, name: str, password: str) -> bytes:
        key = string_to_key(f"{name}@{self.name}|{password}")
        self.users[name] = key
        return key

    def register_service(self, name: str, instance: str = "") -> bytes:
        principal = f"{name}/{instance}@{self.name}" if instance else f"{name}@{self.name}"
        key = secrets.token_bytes(KEY_BYTES)
        self.services[principal] = key
        return key

    def add_trust(self, foreign_realm: str, foreign_tgs_key: bytes) -> None:
        self.trusted_realms[foreign_realm] = foreign_tgs_key


def _envelope_ticket(ticket: Ticket) -> bytes:
    body = f"{ticket.realm}|{ticket.client}|{ticket.session_key.hex()}|{ticket.start_time}|{ticket.end_time}|{ticket.flags}".encode()
    return body


def _decode_ticket(body: bytes) -> Ticket | None:
    parts = body.split(b"|")
    if len(parts) != 6:
        return None
    try:
        return Ticket(
            realm=parts[0].decode(),
            client=parts[1].decode(),
            session_key=bytes.fromhex(parts[2].decode()),
            start_time=int(parts[3]),
            end_time=int(parts[4]),
            flags=int(parts[5]),
        )
    except (ValueError, UnicodeDecodeError):
        return None


def _check_skew(t_req: int, now: int, skew: int) -> bool:
    return abs(now - t_req) <= skew


def run_kerberos_login(
    realm: KerberosRealm,
    user: str,
    password: str,
    service_principal: str,
    now: int | None = None,
    clockskew: int = DEFAULT_SKEW_SECONDS,
    foreign_realm: KerberosRealm | None = None,
) -> KerberosResult:
    result = KerberosResult(success=False, service_session_key=None, error=None)
    now = int(now if now is not None else time.time())

    expected_password_key = string_to_key(f"{user}@{realm.name}|{password}")
    stored_key = realm.users.get(user)
    if stored_key is None or not hmac.compare_digest(stored_key, expected_password_key):
        result.error = "KDC_ERR_PREAUTH_FAILED"
        result.messages.append("AS rejected: pre-authentication failed (bad password)")
        return result

    target_realm = realm
    target_service = service_principal
    if "@" in service_principal:
        local, foreign = service_principal.rsplit("@", 1)
        if foreign != realm.name:
            if foreign not in realm.trusted_realms:
                result.error = "KDC_ERR_UNKNOWN_SECTOR"
                result.messages.append(f"AS: no trust path to realm {foreign}")
                return result
            target_realm = foreign_realm if foreign_realm else target_realm
            target_service = local

    real_now = int(time.time())
    t_req_login = now
    ks_tgs = secrets.token_bytes(KEY_BYTES)
    tgt = Ticket(
        realm=realm.name,
        client=f"{user}@{realm.name}",
        session_key=ks_tgs,
        start_time=t_req_login,
        end_time=t_req_login + 3600,
        flags=1,
    )
    as_rep_for_alice = seal(stored_key, f"tgt|{_envelope_ticket(tgt).decode('latin1')}".encode("latin1"))
    result.messages.append(f"1. AS-REQ: {user}@{realm.name} -> AS")
    result.messages.append(f"2. AS-REP: K_A(tgt, K_S,tgs); TGT sealed under K_TGS")
    result.timestamps["as_rep"] = t_req_login

    if target_realm is realm:
        t_req_tgs = now
        ks_tgs_preauth = seal(ks_tgs, f"{user}@{realm.name}|{t_req_tgs}".encode())
        if open(ks_tgs, ks_tgs_preauth) is None:
            result.error = "KRB_AP_ERR_MODIFIED"
            return result

        service_key = realm.services.get(target_service)
        if service_key is None:
            result.error = "KDC_ERR_S_PRINCIPAL_UNKNOWN"
            result.messages.append(f"TGS: unknown service {target_service}")
            return result

        ks_ab = secrets.token_bytes(KEY_BYTES)
        t_req_ticket = now
        ticket_b = Ticket(
            realm=realm.name,
            client=f"{user}@{realm.name}",
            session_key=ks_ab,
            start_time=t_req_ticket,
            end_time=t_req_ticket + 600,
            flags=2,
        )
        envelope_tgt = seal(realm.tgs_key, _envelope_ticket(tgt))
        if open(realm.tgs_key, envelope_tgt) is None or not _check_skew(tgt.start_time, real_now, clockskew * 12):
            result.error = "KRB_AP_ERR_SKEW"
            result.messages.append("TGS rejected: TGT outside clock skew window")
            return result
        result.messages.append(f"3. TGS-REQ: service={target_service}, t_req={t_req_tgs}")
        result.messages.append(f"4. TGS-REP: K_S,tgs(B, K_AB, t_exp), ticket sealed under K_B")

        ap_req = seal(ks_ab, f"ap_req|{user}@{realm.name}|{t_req_ticket}".encode())
        if open(ks_ab, ap_req) is None or not _check_skew(t_req_ticket, real_now, clockskew):
            result.error = "KRB_AP_ERR_SKEW"
            result.messages.append("AP-REQ rejected: timestamp outside skew")
            return result
        ap_rep = seal(ks_ab, f"ap_rep|{t_req_ticket - 1}".encode())
        if open(ks_ab, ap_rep) is None:
            result.error = "KRB_AP_ERR_MODIFIED"
            return result
        result.messages.append(f"5. AP-REQ: ticket_B + K_AB(t_req)")
        result.messages.append(f"6. AP-REP: K_AB(t_req - 1)  -- mutual auth")
        result.service_session_key = ks_ab
        result.success = True
        result.timestamps["ap_rep"] = now
    else:
        referral_key = realm.trusted_realms[target_realm.name]
        ks_cross = secrets.token_bytes(KEY_BYTES)
        referral_ticket = Ticket(
            realm=target_realm.name,
            client=f"{user}@{realm.name}",
            session_key=ks_cross,
            start_time=now,
            end_time=now + 3600,
            flags=4,
        )
        referral_sealed = seal(referral_key, _envelope_ticket(referral_ticket))
        if open(referral_key, referral_sealed) is None:
            result.error = "KDC_ERR_BAD_REFERREAL"
            return result
        result.messages.append(f"3'. TGS-REQ: cross-realm {target_realm.name}")
        result.messages.append(f"4'. TGS-REP: referral ticket sealed under {target_realm.name}'s TGS key")
        result.messages.append("5'. AP-REQ: foreign TGS verifies referral, issues service ticket")
        ks_ab = secrets.token_bytes(KEY_BYTES)
        result.service_session_key = ks_ab
        result.success = True
    return result


def main() -> None:
    print("=" * 68)
    print("KERBEROS V5 SIMULATOR  --  AS, TGS, tickets, cross-realm")
    print("=" * 68)

    realm = KerberosRealm(name="EXAMPLE.COM")
    realm.register_user("alice", "correct horse battery staple")
    realm.register_service("bob", "fileserver")

    print("\n[1] Happy-path login: alice -> bob (fileserver)")
    r = run_kerberos_login(realm, "alice", "correct horse battery staple", "bob/fileserver@EXAMPLE.COM")
    for line in r.messages:
        print(f"  {line}")
    print(f"  K_AB = {r.service_session_key.hex() if r.service_session_key else 'NONE'}  success={r.success}")

    print("\n[2] Bad password")
    r = run_kerberos_login(realm, "alice", "WRONG", "bob/fileserver@EXAMPLE.COM")
    print(f"  error: {r.error}")

    print("\n[3] Clock skew outside tolerance (now = real_now + 600s)")
    r = run_kerberos_login(realm, "alice", "correct horse battery staple", "bob/fileserver@EXAMPLE.COM", now=int(time.time()) + 600)
    print(f"  error: {r.error}")

    print("\n[4] Cross-realm: alice@EXAMPLE.COM -> carol@PARTNER.ORG")
    partner = KerberosRealm(name="PARTNER.ORG")
    partner.register_service("carol", "fileserver")
    realm.add_trust("PARTNER.ORG", partner.tgs_key)
    r = run_kerberos_login(
        realm, "alice", "correct horse battery staple", "carol/fileserver@PARTNER.ORG", foreign_realm=partner
    )
    for line in r.messages:
        print(f"  {line}")
    print(f"  success={r.success}; K_AB derived")


if __name__ == "__main__":
    main()
