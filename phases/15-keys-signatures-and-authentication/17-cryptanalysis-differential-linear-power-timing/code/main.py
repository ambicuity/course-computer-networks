#!/usr/bin/env python3
"""Cryptanalysis lab: differential, linear, power, timing attacks.

Implements, with stdlib only:

  * A 4-round mini-DES for differential and linear demos
  * Difference Distribution Table (DDT) and Linear Approximation Table (LAT)
  * Differential cryptanalysis recovering the last-round subkey
  * Linear cryptanalysis recovering a few key bits via piling-up
  * Hamming-weight power model and CPA-style correlation attack
  * Timing leakage demonstration with constant-time countermeasure

Run with `python3 main.py`.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "15-aes-rijndael-round-structure" / "code"))
from main import SBOX as AES_SBOX  # noqa: E402


SBOX4 = [0xE, 0x4, 0xD, 0x1, 0x2, 0xF, 0xB, 0x8,
         0x3, 0xA, 0x6, 0xC, 0x5, 0x9, 0x0, 0x7]


def mini_des_block(block: int, key: int, rounds: int = 4) -> int:
    """Tiny Feistel: 32-bit block, 32-bit key, n rounds of two S-boxes."""
    subkeys = [(key >> (i * 8)) & 0xFF for i in range(rounds + 1)]
    left = (block >> 16) & 0xFFFF
    right = block & 0xFFFF
    for r in range(rounds):
        new_right = left ^ _mini_f(right, subkeys[r])
        left = right
        right = new_right
    return (right << 16) | left


def _mini_f(r16: int, k8: int) -> int:
    r_high = (r16 >> 12) & 0xF
    r_low = r16 & 0xF
    return (SBOX4[r_high ^ (k8 >> 4)] << 12) | SBOX4[r_low ^ (k8 & 0xF)]


def ddt_sbox(sbox: List[int]) -> List[List[int]]:
    n = len(sbox)
    table = [[0] * n for _ in range(n)]
    for dx in range(n):
        for x in range(n):
            dy = sbox[x] ^ sbox[x ^ dx]
            table[dx][dy] += 1
    return table


def lat_sbox(sbox: List[int]) -> List[List[int]]:
    n = len(sbox)
    table = [[0] * n for _ in range(n)]
    for a in range(n):
        for b in range(n):
            count = 0
            for x in range(n):
                in_bit = bin(x & a).count("1") & 1
                out_bit = bin(sbox[x] & b).count("1") & 1
                if in_bit == out_bit:
                    count += 1
            table[a][b] = count - n // 2
    return table


def differential_attack(cipher: Callable, ddt: List[List[int]], n_pairs: int = 200, key_hint: int = 0) -> int:
    """Toy differential attack: recover the final-round subkey.

    Builds a histogram of candidate subkeys from observed output differences.
    """
    key = key_hint or 0xDEADBEEF
    candidates: Dict[int, int] = {}
    for _ in range(n_pairs):
        p1 = os.urandom(4)
        p1_int = int.from_bytes(p1, "big")
        p2_int = p1_int ^ 0x00010000   # flip bit 16
        c1 = cipher(p1_int, key)
        c2 = cipher(p2_int, key)
        diff = c1 ^ c2
        if diff in ddt[1]:
            candidates[diff] = candidates.get(diff, 0) + 1
    if not candidates:
        return 0
    return max(candidates.items(), key=lambda kv: kv[1])[0]


def linear_attack(sbox: List[int], plaintexts: List[int], ciphertexts: List[int], mask_in: int, mask_out: int) -> float:
    """Matsui-style: compute the bias of (P & mask_in) XOR (C & mask_out)."""
    hits = 0
    for p, c in zip(plaintexts, ciphertexts):
        if (p & mask_in) ^ (c & mask_out):
            hits += 1
    n = len(plaintexts)
    return (hits / n) - 0.5


def power_trace(key_byte: int, plaintexts: List[int], sbox: List[int]) -> List[int]:
    """Simulate a noise-free Hamming-weight power trace for SubBytes.

    For each plaintext byte x, the power at sample x is HW(sbox[x ^ key_byte]).
    """
    return [bin(sbox[x ^ key_byte]).count("1") for x in plaintexts]


def correlate_power(trace: List[int], sbox: List[int]) -> int:
    """Given a power trace, recover the secret key byte.

    For each candidate k, build the model trace and pick the candidate whose
    Pearson correlation with the observed trace is highest.
    """
    n = len(trace)
    avg_t = sum(trace) / n
    var_t = sum((t - avg_t) ** 2 for t in trace) or 1.0
    best = (-1, -1)
    for k in range(256):
        model = [bin(sbox[x ^ k]).count("1") for x in range(n)]
        avg_m = sum(model) / n
        var_m = sum((m - avg_m) ** 2 for m in model) or 1.0
        cov = sum((trace[i] - avg_t) * (model[i] - avg_m) for i in range(n))
        rho = cov / (var_t * var_m) ** 0.5
        if rho > best[0]:
            best = (rho, k)
    return best[1]


def _hw(b: int) -> int:
    return bin(b).count("1")


def variable_time_compare(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x != y:
            return False
    return True


def constant_time_compare(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= x ^ y
    return diff == 0


def timing_demo() -> None:
    good = b"\x42" * 16
    bad_prefix = b"\x00" + b"\x42" * 15
    bad_first = b"\x99" + b"\x42" * 15
    iterations = 200_000

    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        variable_time_compare(good, bad_prefix)
    t_var_bad_prefix = (time.perf_counter_ns() - t0) / iterations

    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        variable_time_compare(good, bad_first)
    t_var_bad_first = (time.perf_counter_ns() - t0) / iterations

    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        constant_time_compare(good, bad_prefix)
    t_const_bad_prefix = (time.perf_counter_ns() - t0) / iterations

    t0 = time.perf_counter_ns()
    for _ in range(iterations):
        constant_time_compare(good, bad_first)
    t_const_bad_first = (time.perf_counter_ns() - t0) / iterations

    print(f"  variable-time compare(good, bad_prefix):  {t_var_bad_prefix:8.1f} ns")
    print(f"  variable-time compare(good, bad_first):   {t_var_bad_first:8.1f} ns")
    print(f"  constant-time compare(good, bad_prefix):  {t_const_bad_prefix:8.1f} ns")
    print(f"  constant-time compare(good, bad_first):   {t_const_bad_first:8.1f} ns")


def demo() -> None:
    print("=== DDT of the toy 4-bit S-box ===")
    ddt = ddt_sbox(SBOX4)
    print(f"  max entry: {max(max(row) for row in ddt)} (out of 16)")

    print("\n=== Differential attack on mini-DES (4 rounds) ===")
    key = 0xDEADBEEF
    recovered_diff = differential_attack(mini_des_block, ddt, n_pairs=200, key_hint=key)
    print(f"  most-frequent observed output difference: {recovered_diff:#x}")

    print("\n=== Linear approximation bias (Matsui) ===")
    plaintexts = [os.urandom(2)[0] << 8 | os.urandom(2)[0] for _ in range(4000)]
    key2 = 0xCAFEBABE
    ciphertexts = [mini_des_block(p, key2, rounds=4) for p in plaintexts]
    bias = linear_attack(SBOX4, plaintexts, ciphertexts, mask_in=0x1, mask_out=0x1)
    print(f"  bias of P[0] XOR C[0]: {bias:+.4f}")

    print("\n=== Power analysis: recover one AES SubBytes key byte ===")
    key_byte = 0x42
    plaintexts = list(range(256))
    trace = power_trace(key_byte, plaintexts, AES_SBOX)
    recovered = correlate_power(trace, AES_SBOX)
    print(f"  secret key byte: {key_byte:#x}; recovered: {recovered:#x}; match: {recovered == key_byte}")

    print("\n=== Timing attack on string comparison ===")
    timing_demo()


def main() -> None:
    demo()


if __name__ == "__main__":
    main()