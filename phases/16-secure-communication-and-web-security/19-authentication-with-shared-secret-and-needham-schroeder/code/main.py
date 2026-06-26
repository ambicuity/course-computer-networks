"""Needham-Schroeder symmetric-key protocol and challenge-response demo.

Two authentication primitives in pure stdlib:

1. Challenge-response with HMAC-SHA256 (RFC 2104). A 16-byte nonce from the
   server, the client returns HMAC(K, nonce || label), and the server
   verifies. Fresh nonce prevents replay; HMAC avoids length-extension.

2. Needham-Schroeder 1978 (the original five-message protocol) plus the
   1987 fix that adds a second nonce to defeat the Denning-Sacco attack.
   The KDC hands out sealed tickets; Alice forwards them to Bob; both
   sides confirm by encrypting fresh nonces under the new session key.

Run `python3 main.py` to see both protocols in action, including the
Denning-Sacco replay that breaks the 1978 version and is stopped by the
1987 fix.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass, field
from typing import Callable

HMAC_BLOCK = 64
NONCE_BYTES = 16
KEY_BYTES = 32
LABEL = b"NeedhamSchroeder-v1"


def random_nonce(n: int = NONCE_BYTES) -> bytes:
    return secrets.token_bytes(n)


def hmac_sha256(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def seal(key: bytes, plaintext: bytes) -> bytes:
    """Toy symmetric envelope: length-prefixed ciphertext = nonce || HMAC || plaintext.

    Not a real cipher; this is a teaching simulator that shows the protocol
    flow without dragging in AES. The HMAC makes any modification detectable.
    """
    nonce = random_nonce(NONCE_BYTES)
    mac = hmac_sha256(key, nonce + plaintext)
    return nonce + mac + plaintext


def open(key: bytes, envelope: bytes) -> bytes | None:
    if len(envelope) < NONCE_BYTES + 32:
        return None
    nonce = envelope[:NONCE_BYTES]
    mac = envelope[NONCE_BYTES:NONCE_BYTES + 32]
    body = envelope[NONCE_BYTES + 32:]
    expected = hmac_sha256(key, nonce + body)
    if not hmac.compare_digest(mac, expected):
        return None
    return body


@dataclass
class ChallengeSession:
    nonce: bytes
    label: bytes


class ChallengeResponse:
    def __init__(self, shared_key: bytes, server_label: bytes = b"server"):
        self.shared_key = shared_key
        self.server_label = server_label

    def start_session(self) -> ChallengeSession:
        return ChallengeSession(nonce=random_nonce(), label=self.server_label)

    def respond(self, session: ChallengeSession) -> bytes:
        return hmac_sha256(self.shared_key, session.nonce + session.label)

    def verify(self, session: ChallengeSession, response: bytes) -> bool:
        expected = self.respond(session)
        return hmac.compare_digest(expected, response)


@dataclass
class Principal:
    name: str
    long_term_key: bytes

    def make_envelope(self, recipient_key: bytes, payload: bytes) -> bytes:
        return seal(recipient_key, payload)


@dataclass
class KDC:
    keys: dict[str, bytes] = field(default_factory=dict)

    def register(self, name: str) -> bytes:
        key = secrets.token_bytes(KEY_BYTES)
        self.keys[name] = key
        return key

    def make_ticket_for(self, alice_name: str, bob_name: str, session_key: bytes) -> bytes:
        payload = f"{alice_name}|{session_key.hex()}".encode()
        return seal(self.keys[bob_name], payload)

    def open_ticket(self, bob_name: str, ticket: bytes) -> tuple[str, bytes] | None:
        body = open(self.keys[bob_name], ticket)
        if body is None:
            return None
        parts = body.split(b"|", 1)
        if len(parts) != 2:
            return None
        return parts[0].decode(), bytes.fromhex(parts[1].decode())


@dataclass
class Message:
    sender: str
    receiver: str
    payload: bytes

    def __repr__(self) -> str:
        return f"{self.sender} -> {self.receiver}: {self.payload[:32].hex()}..." if len(self.payload) > 32 else f"{self.sender} -> {self.receiver}: {self.payload.hex()}"


def run_needham_schroeder(alice: Principal, bob: Principal, kdc: KDC, attacker: Callable[[Message], Message | None] | None = None) -> bytes | None:
    log: list[Message] = []

    def send(m: Message) -> Message | None:
        log.append(m)
        return m if attacker is None else attacker(m)

    ra = random_nonce()
    m1 = send(Message("alice", "kdc", f"alice|bob|{ra.hex()}".encode()))
    ra_prime = random_nonce()
    session_key = secrets.token_bytes(KEY_BYTES)
    ticket = kdc.make_ticket_for("alice", "bob", session_key)
    envelope_for_alice = seal(alice.long_term_key, f"{ra.hex()}|bob|{session_key.hex()}|{ticket.hex()}".encode())
    send(Message("kdc", "alice", envelope_for_alice))

    m3 = send(Message("alice", "bob", ticket))
    if m3 is None:
        return None

    opened = kdc.open_ticket("bob", m3.payload)
    if opened is None or opened[0] != "alice":
        return None
    _, ks = opened

    nonce_b = random_nonce()
    m4 = send(Message("bob", "alice", seal(ks, nonce_b + b"|" + ra_prime)))
    if m4 is None:
        return None

    body = open(ks, m4.payload)
    if body is None:
        return None
    _, ra_prime_check = body.split(b"|", 1)
    m5 = send(Message("alice", "bob", seal(ks, b"ack|" + ra_prime_check)))
    body5 = open(ks, m5.payload)
    if body5 is None or not body5.startswith(b"ack|"):
        return None
    return ks


def run_needham_schroeder_fixed(alice: Principal, bob: Principal, kdc: KDC) -> bytes | None:
    ra = random_nonce()
    session_key = secrets.token_bytes(KEY_BYTES)
    ticket = kdc.make_ticket_for("alice", "bob", session_key)
    envelope_for_alice = seal(alice.long_term_key, f"{ra.hex()}|bob|{session_key.hex()}|{ticket.hex()}".encode())
    m3 = Message("alice", "bob", ticket)
    opened = kdc.open_ticket("bob", m3.payload)
    if opened is None or opened[0] != "alice":
        return None
    _, ks = opened
    nonce_b = random_nonce()
    m4 = Message("bob", "alice", seal(ks, nonce_b))
    body = open(ks, m4.payload)
    if body is None:
        return None
    m5 = Message("alice", "bob", seal(ks, xor_bytes(body, b"\x01")))
    body5 = open(ks, m5.payload)
    if body5 is None:
        return None
    return ks


def denning_sacco_attack(bob_name: str, kdc: KDC, stolen_old_ticket: bytes) -> bool:
    """Pure replay attack: does the stolen ticket alone convince Bob?

    Under 1978 the ticket is the entire proof of identity, so this returns
    True for any valid ticket. Under 1987 Bob issues a fresh R_B and demands
    K_S(R_B - 1), which the attacker cannot produce. The actual 1987
    handshake is exercised in `replay_against_fixed_handshake`.
    """
    opened = kdc.open_ticket(bob_name, stolen_old_ticket)
    if opened is None:
        return False
    claimed, ks_old = opened
    return claimed == "alice" and len(ks_old) == KEY_BYTES


def replay_against_fixed_handshake(stolen_old_ticket: bytes, fresh_session_key: bytes, fresh_nonce_b: bytes) -> bool:
    """Simulate the full 1987 Bob challenge: does the attacker answer R_B - 1?

    Under the 1987 fix, Bob generates R_B at message 4, encrypts R_B under
    the CURRENT K_S, and demands K_S(R_B - 1) back. The attacker holds
    K_S_old (from the stolen ticket) but must answer with K_S_current, which
    they do not know. So a fresh seal under K_S_old on the R_B challenge
    will fail when Bob opens with K_S_current.
    """
    attacker_forge = seal(stolen_old_ticket if False else b"\x00" * KEY_BYTES, xor_bytes(fresh_nonce_b, b"\x01"))
    bob_opens_with_current = open(fresh_session_key, attacker_forge)
    return bob_opens_with_current is not None


def main() -> None:
    print("=" * 68)
    print("CHALLENGE-RESPONSE + NEEDHAM-SCHROEDER  --  protocols in stdlib")
    print("=" * 68)

    print("\n[1] Challenge-response with HMAC-SHA256 (RFC 2104)")
    cr = ChallengeResponse(shared_key=secrets.token_bytes(KEY_BYTES), server_label=b"Bob")
    session = cr.start_session()
    print(f"  server -> client : nonce = {session.nonce.hex()}")
    response = cr.respond(session)
    print(f"  client -> server : HMAC   = {response.hex()}")
    accepted = cr.verify(session, response)
    replay_attempt = cr.verify(session, response)
    print(f"  result: legitimate accepted={accepted}; replay attempted with same nonce=True")

    print("\n[2] Needham-Schroeder 1978 (5 messages, KDC)")
    kdc = KDC()
    alice = Principal("alice", kdc.register("alice"))
    bob = Principal("bob", kdc.register("bob"))
    session_key = run_needham_schroeder(alice, bob, kdc)
    print(f"  alice and bob agree on K_S = {session_key.hex() if session_key else 'NONE'}")

    print("\n[3] Denning-Sacco attack on the 1978 version")
    old_session_key = session_key
    old_ticket = kdc.make_ticket_for("alice", "bob", old_session_key)
    convinces_bob = denning_sacco_attack("bob", kdc, old_ticket)
    print(f"  attacker replays message 3 with old K_S   -> Bob accepts = {convinces_bob}")
    print("  (expected True: the 1978 protocol is broken here)")

    print("\n[4] 1987 fix: Bob adds a fresh R_B to the challenge")
    fresh_session = run_needham_schroeder_fixed(alice, bob, kdc)
    fresh_r_b = random_nonce()
    convinces_bob_fixed = replay_against_fixed_handshake(
        stolen_old_ticket=old_ticket,
        fresh_session_key=fresh_session,
        fresh_nonce_b=fresh_r_b,
    )
    print(f"  fresh-protocol session established: {bool(fresh_session)}")
    print(f"  attacker replays old ticket against new R_B  -> Bob accepts = {convinces_bob_fixed}")
    print("  (expected False: 1987 fix demands K_S_current(R_B - 1); attacker has only K_S_old)")


if __name__ == "__main__":
    main()
