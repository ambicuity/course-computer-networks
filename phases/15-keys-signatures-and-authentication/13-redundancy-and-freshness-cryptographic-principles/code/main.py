#!/usr/bin/env python3
"""Build a small authenticated frame that demonstrates redundancy + freshness.

Implements, with stdlib only:

  * OrderFrame packing with redundant zero prefix, nonce, timestamp, HMAC
  * Frame verification with redundancy, freshness, replay, and HMAC checks
  * Random-forgery simulation against the no-redundancy baseline
  * ReplayFilter that drops replays and stale messages

Run with `python3 main.py`.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Optional, Set


REDUNDANCY_LEN = 9  # bytes of zero prefix
NONCE_LEN = 8
TIMESTAMP_LEN = 8


@dataclass(frozen=True)
class FrameLayout:
    redundancy: int = REDUNDANCY_LEN
    nonce: int = NONCE_LEN
    timestamp: int = TIMESTAMP_LEN
    hmac_len: int = 32


LAYOUT = FrameLayout()


def make_frame(
    customer_id: bytes,
    quantity: int,
    product_id: int,
    key: bytes,
    redundancy: int = REDUNDANCY_LEN,
    nonce: Optional[bytes] = None,
    timestamp: Optional[float] = None,
) -> bytes:
    """Pack an order frame with redundancy + freshness + HMAC."""
    if len(customer_id) > 16:
        raise ValueError("customer_id must fit in 16 bytes")
    if not 0 <= quantity <= 0xFF:
        raise ValueError("quantity must fit in 1 byte")
    if not 0 <= product_id <= 0xFFFF:
        raise ValueError("product_id must fit in 2 bytes")

    if nonce is None:
        nonce = secrets.token_bytes(NONCE_LEN)
    if timestamp is None:
        timestamp = time.time()

    customer_padded = customer_id.ljust(16, b"\x00")[:16]
    payload = customer_padded + struct.pack("!BHH", quantity, product_id >> 8, product_id & 0xFF)
    nonce_field = nonce[:NONCE_LEN].ljust(NONCE_LEN, b"\x00")
    ts_field = struct.pack("!d", timestamp)
    zero_prefix = b"\x00" * redundancy

    mac_input = zero_prefix + ts_field + nonce_field + payload
    tag = hmac.new(key, mac_input, hashlib.sha256).digest()
    return mac_input + tag


def verify_frame(
    frame: bytes,
    key: bytes,
    max_age_seconds: float = 10.0,
    seen_nonces: Optional[Set[bytes]] = None,
    now: Optional[float] = None,
) -> bool:
    if len(frame) < REDUNDANCY_LEN + TIMESTAMP_LEN + NONCE_LEN + 16 + 32:
        return False
    if frame[:REDUNDANCY_LEN] != b"\x00" * REDUNDANCY_LEN:
        return False
    ts = struct.unpack("!d", frame[REDUNDANCY_LEN:REDUNDANCY_LEN + TIMESTAMP_LEN])[0]
    nonce = frame[REDUNDANCY_LEN + TIMESTAMP_LEN:REDUNDANCY_LEN + TIMESTAMP_LEN + NONCE_LEN]
    mac_input = frame[:-(LAYOUT.hmac_len)]
    tag = frame[-LAYOUT.hmac_len:]
    expected = hmac.new(key, mac_input, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        return False
    if now is None:
        now = time.time()
    if abs(now - ts) > max_age_seconds:
        return False
    if seen_nonces is not None:
        if nonce in seen_nonces:
            return False
        seen_nonces.add(nonce)
    return True


class ReplayFilter:
    """Tracks nonces within a freshness window."""

    def __init__(self, max_age_seconds: float = 10.0) -> None:
        self.max_age_seconds = max_age_seconds
        self._seen: Set[bytes] = set()

    def check(self, frame: bytes, key: bytes, now: Optional[float] = None) -> bool:
        return verify_frame(frame, key, self.max_age_seconds, self._seen, now)


def random_forge(rate: int, key: bytes) -> int:
    """Try random ciphertexts against a no-redundancy decoder; return successes."""
    successes = 0
    for _ in range(rate):
        junk = secrets.token_bytes(3)
        if hashlib.sha256(junk + key).digest()[:1] == b"\x00":
            successes += 1
    return successes


def attack_without_redundancy(trials: int = 1000) -> None:
    """No redundancy: every 3-byte ciphertext is accepted as a valid order.

    The chapter's Couch Potato scenario: 60,000 products, so any 3-byte
    payload yields a real product id and quantity. Roughly all random
    ciphertexts 'succeed'.
    """
    print(f"=== No redundancy: {trials} random ciphertexts accepted as orders ===")
    successes = trials
    print(f"  success rate: {successes}/{trials} (~100.0%)")
    print("  -> fired employee ships 837 swings, 540 sandboxes to nobody")


def attack_with_redundancy(trials: int = 1000, redundancy: int = REDUNDANCY_LEN) -> None:
    """With a `redundancy`-byte zero prefix, random guesses must hit 2^(8*redundancy)."""
    print(f"=== {redundancy}-byte zero prefix: random ciphertexts ===")
    successes = 0
    for _ in range(trials):
        junk = secrets.token_bytes(redundancy + 3)
        if all(b == 0 for b in junk[:redundancy]):
            successes += 1
    expected = trials / (256 ** redundancy)
    print(f"  success rate: {successes}/{trials}")
    print(f"  expected:     ~{expected:.3e}  (2^-{8*redundancy})")


def demo_attack_and_defense() -> None:
    key = b"shared-secret-32-bytes-long-enough"

    print("\n--- 1. No redundancy ---")
    attack_without_redundancy(trials=1000)

    print("\n--- 2. Add 9-byte zero prefix ---")
    attack_with_redundancy(trials=1000, redundancy=9)

    print("\n--- 3. Add timestamp + nonce (replay defense) ---")
    frame = make_frame(b"alice", 1, 0x1234, key)
    filt = ReplayFilter(max_age_seconds=10)
    print(f"  first verify:  {verify_frame(frame, key, seen_nonces=filt._seen)}")
    print(f"  replay verify: {verify_frame(frame, key, seen_nonces=filt._seen)}")

    print("\n--- 4. HMAC tampering defense ---")
    tampered = bytearray(frame)
    tampered[20] ^= 0x01
    print(f"  tampered verify: {verify_frame(bytes(tampered), key)}")

    print("\n--- 5. Stale timestamp defense ---")
    old = make_frame(b"alice", 1, 0x1234, key, timestamp=time.time() - 60)
    print(f"  60s-old verify: {verify_frame(old, key)}")


def main() -> None:
    demo_attack_and_defense()


if __name__ == "__main__":
    main()