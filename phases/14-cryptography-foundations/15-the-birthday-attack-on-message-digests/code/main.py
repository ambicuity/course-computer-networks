"""Birthday-attack probability calculator and toy collision finder.

All routines are stdlib-only. The exact probability is computed via the
complement of the product prod_{i=0}^{k-1} (1 - i/N), and a toy brute-force
finder demonstrates the bound empirically against a 16-bit digest.
"""

from __future__ import annotations

import math
import random
import sys
from typing import Callable, Tuple


def collision_probability(n_bits: int, k: int) -> float:
    """Exact probability of at least one collision after k draws from a
    2^n_bits uniform bucket space."""
    if k < 0:
        raise ValueError("k must be non-negative")
    if k < 2:
        return 0.0
    n = 1 << n_bits
    if k > n:
        return 1.0
    log_no_collide = 0.0
    for i in range(k):
        log_no_collide += math.log1p(-i / n)
    return 1.0 - math.exp(log_no_collide)


def birthday_bound(n_bits: int, p: float = 0.5) -> int:
    """Smallest k such that collision_probability(n_bits, k) >= p."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    n = 1 << n_bits
    # Start from the closed-form estimate and refine.
    k = max(2, int(math.ceil(math.sqrt(2.0 * n * math.log(1.0 / (1.0 - p))))))
    # Increase k until we cross the threshold.
    while collision_probability(n_bits, k) < p and k <= n:
        k += 1
    # Try to decrease.
    while k > 2 and collision_probability(n_bits, k - 1) >= p:
        k -= 1
    return k


def expected_collisions(n_bits: int, k: int) -> float:
    """Expected number of unordered colliding pairs: E[X] = k(k-1)/(2N)."""
    if k < 2:
        return 0.0
    n = 1 << n_bits
    return k * (k - 1) / (2.0 * n)


def toy_digest_16(message: bytes) -> int:
    """A deliberately weak 16-bit digest for the toy attack.

    Returns (b[0] << 8 | b[1]) xor (b[2] << 8 | b[3]). Not cryptographic;
    pedagogical only.
    """
    if len(message) < 4:
        message = message + b"\x00" * (4 - len(message))
    h = ((message[0] << 8) | message[1]) ^ ((message[2] << 8) | message[3])
    return h & 0xFFFF


def find_collision(
    digest_fn: Callable[[bytes], int],
    n_bits: int = 16,
    max_tries: int = 100_000,
) -> Tuple[bytes, bytes]:
    """Brute-force collision finder.

    Draws random inputs, computes the digest, and returns the first two
    distinct inputs that collide. Raises RuntimeError if none found within
    `max_tries`.
    """
    seen: dict[int, bytes] = {}
    for _ in range(max_tries):
        m = random.randbytes(8)
        d = digest_fn(m) & ((1 << n_bits) - 1)
        if d in seen and seen[d] != m:
            return seen[d], m
        seen[d] = m
    raise RuntimeError(f"no collision found within {max_tries} tries")


def report(n_bits: int) -> None:
    """Pretty-print a report for a given digest size."""
    bound50 = birthday_bound(n_bits, 0.5)
    bound90 = birthday_bound(n_bits, 0.9)
    print(
        f"digest={n_bits:>4}-bit  bound@50%={bound50}  "
        f"bound@90%={bound90}  E[X]@2^(n/2)="
        f"{expected_collisions(n_bits, 1 << (n_bits // 2)):.3f}"
    )


def main() -> None:
    """Run the CLI: usage is `python3 main.py [n_bits] [k]`."""
    if len(sys.argv) >= 3:
        n_bits = int(sys.argv[1])
        k = int(sys.argv[2])
        print(
            f"P(collision) for {n_bits}-bit after {k} draws: "
            f"{collision_probability(n_bits, k):.6f}"
        )
        return
    # Default: report on SHA-1, SHA-256, MD5, plus a toy 16-bit run.
    for bits in (128, 160, 256, 512):
        report(bits)
    f, s = find_collision(toy_digest_16, n_bits=16)
    print(
        f"toy 16-bit collision found: {f.hex()} -> {toy_digest_16(f):#06x}, "
        f"{s.hex()} -> {toy_digest_16(s):#06x}"
    )


if __name__ == "__main__":
    main()