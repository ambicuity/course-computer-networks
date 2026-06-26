#!/usr/bin/env python3
"""Two Fundamental Cryptographic Principles - redundancy and freshness.

Simulates the Couch Potato active-intruder attack with and without
redundancy, and a replay attack with and without a timestamp freshness
check. Demonstrates that encryption alone is insufficient; the receiver
must verify validity (Principle 1) and freshness (Principle 2).
No external dependencies; runs under plain python3.
"""

from __future__ import annotations

import os
import time


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR two equal-length byte strings."""
    return bytes(x ^ y for x, y in zip(a, b))


def fake_encrypt(payload: bytes, key: bytes) -> bytes:
    """Toy stream-cipher-style encryption: XOR payload with key (educational only)."""
    return xor_bytes(payload, key)


def fake_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """Toy decryption: XOR ciphertext with key (symmetric)."""
    return xor_bytes(ciphertext, key)


def attack_no_redundancy(key: bytes, trials: int = 1000) -> float:
    """Active intruder sends random 3-byte ciphertext; almost all are valid orders."""
    successes: int = 0
    for _ in range(trials):
        fake_ct: bytes = os.urandom(3)
        decrypted: bytes = fake_decrypt(fake_ct, key)
        qty: int = decrypted[0]
        prod: int = int.from_bytes(decrypted[1:3], "big")
        # Without redundancy, almost every (qty, prod) is a "valid" order.
        if 0 < qty < 256 and 0 < prod < 60000:
            successes += 1
    return successes / trials


def attack_with_redundancy(key: bytes, trials: int = 1000) -> float:
    """9 leading zero bytes required; random ciphertext almost never passes."""
    successes: int = 0
    for _ in range(trials):
        fake_ct: bytes = os.urandom(12)
        decrypted: bytes = fake_decrypt(fake_ct, key)
        # Valid only if first 9 bytes are zero AND last 3 are a plausible order.
        if decrypted[:9] == b"\x00" * 9:
            qty: int = decrypted[9]
            prod: int = int.from_bytes(decrypted[10:12], "big")
            if 0 < qty < 256 and 0 < prod < 60000:
                successes += 1
    return successes / trials


def freshness_check(
    msg_time: float, current_time: float, window: float = 10.0
) -> bool:
    """Return True if message is within the freshness window."""
    age: float = current_time - msg_time
    return 0 <= age <= window


def demo_redundancy() -> None:
    print("=== Principle 1: Redundancy ===")
    key: bytes = os.urandom(12)  # toy key; real systems use AES, not XOR
    no_red: float = attack_no_redundancy(key[:3], 10000)
    with_red: float = attack_with_redundancy(key, 10000)
    print(f"  No redundancy:      attack success rate = {no_red * 100:.2f}%")
    print(f"  9-zero-byte prefix: attack success rate = {with_red * 100:.4f}%")
    print("  Redundancy lets the receiver reject attacker garbage.\n")


def demo_freshness() -> None:
    print("=== Principle 2: Freshness ===")
    window: float = 10.0
    base: float = time.time()
    messages: list[tuple[str, float, bytes]] = [
        ("order-A", base, b"\x01\x00\x0a"),
        ("order-B", base + 5, b"\x02\x00\x1e"),
        ("order-C", base + 12, b"\x03\x00\x28"),  # stale by 2s at t=10
    ]
    seen: set[str] = set()
    print(f"  Freshness window: {window:.0f} seconds")
    for name, ts, payload in messages:
        now: float = base + 10  # receiver processes at t = base + 10
        fresh: bool = freshness_check(ts, now, window)
        replayed: bool = name in seen
        seen.add(name)
        status: str = "ACCEPT" if (fresh and not replayed) else "REJECT"
        reason: str = ""
        if not fresh:
            reason = " (stale)"
        if replayed:
            reason = " (replay)"
        print(f"  {name} sent at t+{ts - base:.0f}s, processed at t+10s -> {status}{reason}")
    print("  Replay of order-A after processing:")
    fresh2: bool = freshness_check(messages[0][1], base + 25, window)
    print(f"  order-A replayed at t+25s -> {'ACCEPT' if fresh2 else 'REJECT (stale/replay)'}")
    print("  Freshness prevents replay attacks.\n")


def demo_protocol_table() -> None:
    print("=== Real protocols implement both principles ===")
    protocols: list[tuple[str, str, str]] = [
        ("TLS 1.3", "AEAD 16-byte tag", "Sequence number in nonce"),
        ("Kerberos", "Ticket encrypted with KDC key", "Timestamp (5-min skew)"),
        ("IPsec ESP", "ICV integrity check", "Seq num + anti-replay window"),
        ("SSH", "HMAC over payload", "Per-packet sequence number"),
    ]
    print(f"  {'Protocol':<12} {'Redundancy':<28} {'Freshness'}")
    for proto, red, fresh in protocols:
        print(f"  {proto:<12} {red:<28} {fresh}")


def main() -> None:
    print("Lesson: Two Fundamental Cryptographic Principles\n")
    demo_redundancy()
    demo_freshness()
    demo_protocol_table()
    print("\nPrinciple 1: Messages must contain verifiable redundancy.")
    print("Principle 2: Messages must be verifiable as fresh (no replays).")
    print("Encryption without these two is a locked door with no frame.")


if __name__ == "__main__":
    main()