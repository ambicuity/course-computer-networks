"""The birthday attack: collision math and Yuval's swindle demo.

Demonstrates (Python stdlib only):
  1. The birthday paradox: P(collision) vs group size, with the 23-person result.
  2. A real birthday collision on a truncated 16-bit digest space.
  3. Yuval's tenure-letter swindle: good/bad letter variants with bracketed
     options, hashed to find a shared digest.
  4. Work-factor table for 64/128/160/256-bit digests.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from typing import Callable

# ---------------------------------------------------------------------------
# Birthday paradox math
# ---------------------------------------------------------------------------

def birthday_probability(n: int, k: int) -> float:
    """P(at least one collision) for n items into k buckets."""
    if n <= 1 or k <= 0:
        return 0.0
    prob_no = 1.0
    for i in range(n):
        prob_no *= (k - i) / k
        if prob_no <= 0:
            return 1.0
    return 1.0 - prob_no


def collision_threshold(k: int, target: float = 0.5) -> int:
    """Smallest n such that P(collision) >= target."""
    n = 1
    while birthday_probability(n, k) < target:
        n += 1
    return n


# ---------------------------------------------------------------------------
# Real birthday collision on a truncated digest
# ---------------------------------------------------------------------------

def truncated_hash(data: bytes, bits: int) -> int:
    """Return the lowest `bits` bits of SHA-256(data) as an integer."""
    full = hashlib.sha256(data).digest()
    val = int.from_bytes(full, "big")
    return val & ((1 << bits) - 1)


def find_birthday_collision(bits: int, max_attempts: int = 100_000) -> tuple[int, bytes, bytes] | None:
    """Find two distinct messages whose truncated hashes collide."""
    seen: dict[int, bytes] = {}
    for i in range(max_attempts):
        msg = f"msg-{i}-{random.random()}".encode()
        h = truncated_hash(msg, bits)
        if h in seen and seen[h] != msg:
            return i + 1, seen[h], msg
        seen[h] = msg
    return None


# ---------------------------------------------------------------------------
# Yuval's tenure-letter swindle (small-scale demo)
# ---------------------------------------------------------------------------

GOOD_TEMPLATE = (
    "Dear Dean, This {a} is to give my {b} opinion of Tom. "
    "He is an {c} researcher of great {d}. He is also a {e} {f}. "
    "I urge you to grant him {g}."
)
BAD_TEMPLATE = (
    "Dear Dean, This {a} is to give my {b} opinion of Tom. "
    "He is a {c} researcher of poor {d}. He is also a {e} {f}. "
    "I cannot recommend him for {g}."
)
OPTIONS = {
    "a": ["letter", "message"],
    "b": ["honest", "frank"],
    "c": ["outstanding", "poor"],
    "d": ["talent", "ability"],
    "e": ["respected", "marginal"],
    "f": ["teacher", "educator"],
    "g": ["tenure", "a post"],
}


def all_variants(template: str) -> list[str]:
    keys = list(OPTIONS.keys())
    for combo in itertools.product(*[OPTIONS[k] for k in keys]):
        yield template.format(**dict(zip(keys, combo)))


def yuval_swindle(bits: int = 24) -> None:
    """Find a good/bad letter pair with the same truncated digest."""
    good_digests: dict[int, str] = {}
    bad_digests: dict[int, str] = {}
    good_gen = all_variants(GOOD_TEMPLATE)
    bad_gen = all_variants(BAD_TEMPLATE)
    for g, b in zip(good_gen, bad_gen):
        dg = truncated_hash(g.encode(), bits)
        db = truncated_hash(b.encode(), bits)
        good_digests.setdefault(dg, g)
        bad_digests.setdefault(db, b)
        # Check cross-set collision
        if dg in bad_digests:
            print("  COLLISION FOUND (good hits bad set):")
            print(f"    Good: {good_digests[dg][:60]}...")
            print(f"    Bad:  {bad_digests[dg][:60]}...")
            print(f"    Shared digest ({bits}-bit): {dg:#x}")
            return
        if db in good_digests:
            print("  COLLISION FOUND (bad hits good set):")
            print(f"    Good: {good_digests[db][:60]}...")
            print(f"    Bad:  {bad_digests[db][:60]}...")
            print(f"    Shared digest ({bits}-bit): {db:#x}")
            return
    print("  No collision in available variants (increase option count).")


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def run_birthday_paradox() -> None:
    print("=" * 64)
    print("SCENE 1 - The birthday paradox")
    print("=" * 64)
    k = 365
    for n in (10, 15, 23, 30, 50, 70):
        print(f"  n={n:3d}: P(shared birthday) = {birthday_probability(n, k):.3f}")
    thresh = collision_threshold(k)
    print(f"  Threshold (P>0.5): n = {thresh} people\n")


def run_collision_demo(bits: int = 16) -> None:
    print("=" * 64)
    print(f"SCENE 2 - Birthday collision on {bits}-bit digest space")
    print("=" * 64)
    k = 1 << bits
    sqrt_k = int(math.isqrt(k))
    print(f"  k = 2^{bits} = {k}; sqrt(k) ~= {sqrt_k}")
    result = find_birthday_collision(bits, max_attempts=50_000)
    if result:
        attempts, m1, m2 = result
        print(f"  Collision after {attempts} messages (threshold ~{sqrt_k})")
        print(f"    msg1: {m1.decode()[:40]}")
        print(f"    msg2: {m2.decode()[:40]}")
        print(f"    Both hash to: {truncated_hash(m1, bits):#06x}\n")
    else:
        print("  No collision found within attempt budget.\n")


def run_yuval() -> None:
    print("=" * 64)
    print("SCENE 3 - Yuval's tenure-letter swindle (24-bit digest)")
    print("=" * 64)
    print(f"  Options per letter: {math.prod(len(v) for v in OPTIONS.values())} variants")
    print(f"  (Full attack uses 32 options -> 2^32 variants; demo uses fewer.)")
    yuval_swindle(bits=24)
    print()


def run_work_factors() -> None:
    print("=" * 64)
    print("SCENE 4 - Work-factor table (birthday bound)")
    print("=" * 64)
    print(f"  {'Digest':<22} {'m bits':<8} {'Brute 2^m':<14} {'Birthday 2^(m/2)':<18} {'Safe?'}")
    for name, m in [("MD5", 128), ("64-bit MAC", 64), ("SHA-1", 160), ("SHA-256", 256)]:
        brute = 2 ** m
        birthday = 2 ** (m // 2)
        safe = "YES" if m >= 256 else ("NO" if m <= 64 else "marginal")
        print(f"  {name:<22} {m:<8} 2^{m:<12} 2^{m//2:<16} {safe}")
    print()


def main() -> None:
    random.seed(42)
    run_birthday_paradox()
    run_collision_demo(bits=16)
    run_yuval()
    run_work_factors()
    print("All four scenes completed successfully.")


if __name__ == "__main__":
    main()