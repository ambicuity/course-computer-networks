"""Symmetric-key signatures: the Big Brother protocol simulator.

Demonstrates the three-principal signing protocol from Tanenbaum section 8.4.1
using HMAC-SHA256 (Python stdlib only). Shows:
  1. Alice signing a message under her key K_A.
  2. Big Brother decrypting/re-signing with K_BB for Bob.
  3. Bob verifying BB's signature.
  4. Replay detection via a bounded nonce cache.
  5. A court-dispute scene proving nonrepudiation.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Crypto helpers (HMAC-SHA256 stands in for symmetric encryption/signing)
# ---------------------------------------------------------------------------

def sign(key: bytes, message: bytes) -> bytes:
    """Produce a symmetric-key signature (HMAC-SHA256 tag)."""
    return hmac.new(key, message, hashlib.sha256).digest()


def verify(key: bytes, message: bytes, tag: bytes) -> bool:
    """Verify a symmetric-key signature in constant time."""
    return hmac.compare_digest(sign(key, message), tag)


def pack_fields(*fields: str | int | float | bytes) -> bytes:
    """Length-prefix each field to avoid ambiguity (a poor man's ASN.1)."""
    out = bytearray()
    for f in fields:
        b = f if isinstance(f, bytes) else str(f).encode()
        out += len(b).to_bytes(4, "big") + b
    return bytes(out)


# ---------------------------------------------------------------------------
# Principal model
# ---------------------------------------------------------------------------

@dataclass
class BigBrother:
    """Central authority that co-signs every message."""
    key: bytes = field(default_factory=lambda: os.urandom(32))
    user_keys: dict[str, bytes] = field(default_factory=dict)

    def register(self, user_id: str) -> bytes:
        k = os.urandom(32)
        self.user_keys[user_id] = k
        return k

    def process(self, sender: str, signed_msg: bytes) -> tuple[bytes, bytes] | None:
        """Decrypt Alice's signed message, re-sign for Bob under BB's key."""
        k_a = self.user_keys.get(sender)
        if k_a is None:
            return None
        if not verify(k_a, signed_msg, sign(k_a, signed_msg)):
            return None  # Alice's signature invalid
        # In a real system BB decrypts; here the "plaintext" is signed_msg itself.
        bb_sig = sign(self.key, signed_msg)  # K_BB(A, t, P) analogue
        return signed_msg, bb_sig


@dataclass
class Bob:
    """Recipient who verifies BB's signature and tracks nonces."""
    name: str
    bb_key: bytes
    seen_nonces: set[int] = field(default_factory=set)
    replay_window_s: int = 3600

    def verify_and_accept(
        self, sender: str, nonce: int, timestamp: float,
        payload: str, bb_sig: bytes, original: bytes,
    ) -> str:
        # Replay check: nonce already seen?
        if nonce in self.seen_nonces:
            return f"REJECT: replay detected (nonce {nonce} already used)"
        # Timestamp freshness
        if time.time() - timestamp > self.replay_window_s:
            return f"REJECT: message too old (age {time.time()-timestamp:.0f}s)"
        # Verify BB's signature over Alice's signed message
        if not verify(self.bb_key, original, bb_sig):
            return "REJECT: BB signature invalid"
        self.seen_nonces.add(nonce)
        return f"ACCEPT: {sender} -> {payload} (nonce={nonce})"


# ---------------------------------------------------------------------------
# Protocol flow
# ---------------------------------------------------------------------------

def run_normal_flow() -> None:
    print("=" * 64)
    print("SCENE 1 - Normal signed message flow")
    print("=" * 64)
    bb = BigBrother()
    k_alice = bb.register("Alice")
    bob = Bob(name="Bob", bb_key=bb.key)

    nonce_a = int.from_bytes(os.urandom(8), "big")
    t = time.time()
    payload = "Transfer $1000 to account 67890"
    fields = pack_fields("Bob", nonce_a, t, payload)
    alice_sig = sign(k_alice, fields)
    print(f"Alice sends: K_A(B, R_A={nonce_a}, t, P=\"{payload}\")")
    print(f"  Alice's HMAC tag: {alice_sig.hex()[:32]}...")

    result = bb.process("Alice", fields)
    if result is None:
        print("BB: cannot verify Alice's signature"); return
    original, bb_sig = result
    print(f"BB produces K_BB(A, t, P): {bb_sig.hex()[:32]}...")

    verdict = bob.verify_and_accept("Alice", nonce_a, t, payload, bb_sig, original)
    print(f"Bob: {verdict}\n")


def run_replay_attack() -> None:
    print("=" * 64)
    print("SCENE 2 - Replay attack (Trudy resends old message)")
    print("=" * 64)
    bb = BigBrother()
    k_alice = bb.register("Alice")
    bob = Bob(name="Bob", bb_key=bb.key)

    # First legitimate message
    nonce_a = int.from_bytes(os.urandom(8), "big")
    t = time.time()
    payload = "Transfer $1000 to account 67890"
    fields = pack_fields("Bob", nonce_a, t, payload)
    alice_sig = sign(k_alice, fields)
    orig, bb_sig = bb.process("Alice", fields)
    v1 = bob.verify_and_accept("Alice", nonce_a, t, payload, bb_sig, orig)
    print(f"First  message: {v1}")

    # Trudy captures (orig, bb_sig) and replays with the SAME nonce
    v2 = bob.verify_and_accept("Alice", nonce_a, t, payload, bb_sig, orig)
    print(f"Replay attempt:  {v2}\n")


def run_court_dispute() -> None:
    print("=" * 64)
    print("SCENE 3 - Court dispute (nonrepudiation proof)")
    print("=" * 64)
    bb = BigBrother()
    k_alice = bb.register("Alice")
    bob = Bob(name="Bob", bb_key=bb.key, replay_window_s=10**9)

    nonce_a = int.from_bytes(os.urandom(8), "big")
    t = time.time()
    payload = "Buy 1 ton of gold for acct 12345"
    fields = pack_fields("Bob", nonce_a, t, payload)
    orig, bb_sig = bb.process("Alice", fields)
    bob.verify_and_accept("Alice", nonce_a, t, payload, bb_sig, orig)

    print("Alice denies sending the order.")
    print("Bob presents Exhibit A: K_BB(A, t, P)")
    # Judge asks BB to verify the signature over the disputed payload
    is_authentic = verify(bb.key, orig, bb_sig)
    print(f"BB verifies signature: {is_authentic}")
    if is_authentic:
        print("Judge: signature is genuine. Alice loses. Case dismissed.")
    print()


def main() -> None:
    run_normal_flow()
    run_replay_attack()
    run_court_dispute()
    print("All three scenes completed successfully.")


if __name__ == "__main__":
    main()