#!/usr/bin/env python3
"""Message digests and one-way hash functions — stdlib-only demonstration.

Implements Tanenbaum & Wetherall Chapter 8, Sec. 8.4.3:
* Compute SHA-1, SHA-256, SHA-512, and MD5 digests of arbitrary input.
* Demonstrate the avalanche effect: a 1-bit input change flips ~n/2 output bits.
* Illustrate pre-image resistance: brute-force search over a small candidate space.
* Attempt SHA-256 collision search to show its infeasibility.
* Benchmark MD5, SHA-1, SHA-256, and SHA-512 throughput on a 10 MB buffer.
* Implement HMAC-SHA256 from scratch (RFC 2104) and verify against stdlib hmac.

No third-party dependencies. Run: ``python3 main.py``.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import time


# ---------------------------------------------------------------------------
# Core digest helper
# ---------------------------------------------------------------------------
def digest(text: str | bytes, algo: str = "sha256") -> str:
    """Return the hex-encoded digest of *text* using *algo*."""
    data = text.encode() if isinstance(text, str) else text
    return hashlib.new(algo, data).hexdigest()


# ---------------------------------------------------------------------------
# 1. Avalanche effect
# ---------------------------------------------------------------------------
def _hamming_distance_hex(h1: str, h2: str) -> int:
    """Count differing bits between two same-length hex digests."""
    b1 = int(h1, 16)
    b2 = int(h2, 16)
    return bin(b1 ^ b2).count("1")


def avalanche_demo() -> None:
    """Hash two strings differing by one character; count differing bits."""
    print("\n" + "=" * 72)
    print("DEMO 1: Avalanche Effect")
    print("  A 1-character change should flip ~n/2 bits of the n-bit digest.")
    print("=" * 72)

    pairs = [
        ("Hello, world!", "Hello, world?"),  # last char '!' -> '?'
        ("abc", "abd"),                       # last char 'c' -> 'd'
    ]

    for algo in ("md5", "sha1", "sha256", "sha512"):
        h_obj = hashlib.new(algo)
        bits = h_obj.digest_size * 8
        print(f"\n  [{algo.upper()}] {bits}-bit digest")
        for p1, p2 in pairs:
            d1 = digest(p1, algo)
            d2 = digest(p2, algo)
            ham = _hamming_distance_hex(d1, d2)
            pct = 100.0 * ham / bits
            print(f"    Input A : '{p1}'")
            print(f"             -> {d1[:32]}…")
            print(f"    Input B : '{p2}'")
            print(f"             -> {d2[:32]}…")
            print(f"    Hamming : {ham}/{bits} bits differ ({pct:.1f}%)  "
                  f"[ideal ~50%]")
            print()


# ---------------------------------------------------------------------------
# 2. Pre-image resistance illustration
# ---------------------------------------------------------------------------
def pre_image_resistance() -> None:
    """Brute-force a 3-letter pre-image for a short target message."""
    print("\n" + "=" * 72)
    print("DEMO 2: Pre-image Resistance")
    print("  The only way to reverse MD(P) is exhaustive search.")
    print("=" * 72)

    target_msg = "sun"
    target_hash = digest(target_msg, "sha256")
    print(f"\n  Target message  : '{target_msg}'")
    print(f"  SHA-256 digest  : {target_hash}")
    print(f"\n  Searching all 3-letter [a-z] strings for same digest…")

    found: str | None = None
    attempts = 0
    chars = "abcdefghijklmnopqrstuvwxyz"
    t0 = time.perf_counter()
    for a in chars:
        for b in chars:
            for c in chars:
                candidate = a + b + c
                attempts += 1
                if digest(candidate, "sha256") == target_hash:
                    found = candidate
                    break
            if found:
                break
        if found:
            break
    elapsed = time.perf_counter() - t0

    print(f"  Searched {attempts:,} candidates in {elapsed*1000:.1f} ms.")
    if found:
        print(f"  Pre-image found: '{found}'  "
              f"(succeeds only because target is in the 3-letter search space)")
    else:
        print("  No pre-image found  "
              "(expected when target message is not a 3-letter string)")

    print(f"\n  For real SHA-256: 2^256 ≈ 1.16×10^77 candidates.")
    print(f"  At 10^9 hashes/s that exhaustion takes ≈ 3.7×10^59 years.")


# ---------------------------------------------------------------------------
# 3. Collision resistance attempt with SHA-256
# ---------------------------------------------------------------------------
def collision_resistance_attempt() -> None:
    """Search 100 000 random 16-byte strings for a SHA-256 collision."""
    print("\n" + "=" * 72)
    print("DEMO 3: Collision Resistance Attempt (SHA-256)")
    print("  Birthday bound for 256-bit hash: ~2^128 samples needed.")
    print("=" * 72)

    n_tries = 100_000
    print(f"\n  Generating {n_tries:,} random 16-byte strings…")

    seen: dict[str, bytes] = {}
    collision_found = False
    t0 = time.perf_counter()
    for _ in range(n_tries):
        data = os.urandom(16)
        h = hashlib.sha256(data).hexdigest()
        if h in seen and seen[h] != data:
            collision_found = True
            print(f"  Collision found! (astronomically unlikely)")
            break
        seen[h] = data
    elapsed = time.perf_counter() - t0

    print(f"  Checked {n_tries:,} strings in {elapsed*1000:.1f} ms.")
    print(f"  Collision found: {collision_found}")
    prob = n_tries ** 2 / 2.0 / (2 ** 256)
    print(f"  Collision probability with {n_tries:,} samples ≈ {prob:.2e}  (negligible)")
    print(f"  Comparison: MD5 collision found in practice (Wang et al. 2004)")
    print(f"  SHA-1 collision found with ~2^63 ops (SHAttered 2017)")


# ---------------------------------------------------------------------------
# 4. Throughput benchmark: MD5, SHA-1, SHA-256, SHA-512
# ---------------------------------------------------------------------------
def md5_vs_sha256_perf() -> None:
    """Time each algorithm hashing a 10 MB random buffer."""
    print("\n" + "=" * 72)
    print("DEMO 4: Throughput Benchmark  (10 MB buffer, 3 trials each)")
    print("=" * 72)

    size_mb = 10
    data = os.urandom(size_mb * 1024 * 1024)

    algos = [
        ("md5",    "MD5"),
        ("sha1",   "SHA-1"),
        ("sha256", "SHA-256"),
        ("sha512", "SHA-512"),
        ("sha3_256", "SHA3-256"),
    ]

    print(f"\n  {'Algorithm':<12} {'MB/s':>8}  {'ms/iter':>9}  {'Digest (first 16 hex)'}")
    print(f"  {'-'*12} {'-'*8}  {'-'*9}  {'-'*32}")

    for algo, label in algos:
        times = []
        result = ""
        for _ in range(3):
            t0 = time.perf_counter()
            result = hashlib.new(algo, data).hexdigest()
            times.append(time.perf_counter() - t0)
        avg = sum(times) / len(times)
        mbps = size_mb / avg
        print(f"  {label:<12} {mbps:>8.1f}  {avg*1000:>9.1f}  {result[:32]}")


# ---------------------------------------------------------------------------
# 5. HMAC-SHA256 from scratch (RFC 2104) + stdlib cross-check
# ---------------------------------------------------------------------------
def hmac_sha256_manual(key: bytes, message: bytes) -> str:
    """HMAC-SHA256 per RFC 2104: H((K xor opad) || H((K xor ipad) || m))."""
    BLOCK_SIZE = 64  # SHA-256 processes 512-bit (64-byte) blocks

    # Step 1: normalise key to block size
    if len(key) > BLOCK_SIZE:
        key = hashlib.sha256(key).digest()
    key = key.ljust(BLOCK_SIZE, b"\x00")

    # Step 2: derive inner and outer padding
    ipad = bytes(b ^ 0x36 for b in key)  # inner pad (0x36 repeated)
    opad = bytes(b ^ 0x5C for b in key)  # outer pad (0x5C repeated)

    # Step 3: double hash
    inner = hashlib.sha256(ipad + message).digest()
    return hashlib.sha256(opad + inner).hexdigest()


def hmac_demo() -> None:
    """Demonstrate HMAC-SHA256, verify against stdlib, and show tamper detection."""
    print("\n" + "=" * 72)
    print("DEMO 5: HMAC-SHA256  (RFC 2104 — keyed hash for authentication)")
    print("  HMAC(K, m) = H((K xor opad) || H((K xor ipad) || m))")
    print("=" * 72)

    key = b"super-secret-key"
    message = b"The quick brown fox jumps over the lazy dog"

    manual = hmac_sha256_manual(key, message)
    stdlib = _hmac.new(key, message, hashlib.sha256).hexdigest()

    print(f"\n  Key        : {key.decode()}")
    print(f"  Message    : {message.decode()}")
    print(f"\n  HMAC (manual RFC 2104) : {manual}")
    print(f"  HMAC (stdlib hmac)     : {stdlib}")
    print(f"  Match                  : {manual == stdlib}")

    # Wrong key — should produce different MAC
    wrong_key = b"wrong-key-!!"
    mac_wrong = hmac_sha256_manual(wrong_key, message)
    print(f"\n  HMAC with wrong key    : {mac_wrong}")
    print(f"  Wrong key accepted     : {mac_wrong == manual}  (must be False)")

    # Alice sends (message, HMAC) to Bob over an untrusted network
    print("\n  [Scenario] Alice -> Bob: message + HMAC")
    alice_mac = hmac_sha256_manual(key, message)
    bob_mac = hmac_sha256_manual(key, message)
    print(f"    Alice MAC : {alice_mac[:32]}…")
    print(f"    Bob recomputed: {bob_mac[:32]}…")
    print(f"    Authentic : {_hmac.compare_digest(alice_mac, bob_mac)}")

    # Mallory tampers with the message
    tampered = b"The quick brown fox jumps over the lazy cat"
    mallory_mac = hmac_sha256_manual(key, tampered)
    print(f"\n  [Mallory tampers message] -> '{tampered.decode()}'")
    print(f"    Tampered MAC   : {mallory_mac[:32]}…")
    print(f"    Still valid    : {_hmac.compare_digest(alice_mac, mallory_mac)}  (must be False)")


# ---------------------------------------------------------------------------
# 6. Algorithm status summary
# ---------------------------------------------------------------------------
def algorithm_summary() -> None:
    """Print a one-line digest + status table for all major hash algorithms."""
    print("\n" + "=" * 72)
    print("DEMO 6: Algorithm Summary — When to Use Which Hash")
    print("=" * 72)

    sample = b"Tanenbaum & Wetherall, Computer Networks, Chapter 8 Sec 8.4.3"

    rows = [
        ("md5",     "MD5",      128, "Broken (Wang 2004)",          "Legacy checksums only"),
        ("sha1",    "SHA-1",    160, "Deprecated (SHAttered 2017)", "Legacy systems only"),
        ("sha256",  "SHA-256",  256, "NIST approved",               "TLS, code signing, HMAC"),
        ("sha384",  "SHA-384",  384, "NIST approved",               "High-security TLS"),
        ("sha512",  "SHA-512",  512, "NIST approved",               "Max security, 64-bit CPUs"),
        ("sha3_256","SHA3-256", 256, "NIST FIPS 202 (2015)",        "Post-quantum hedge"),
    ]

    print(f"\n  {'Algorithm':<12} {'Bits':>5}  {'Status':<28}  {'Recommended for'}")
    print(f"  {'-'*12} {'-'*5}  {'-'*28}  {'-'*30}")
    for algo, label, bits, status, use in rows:
        h = hashlib.new(algo, sample).hexdigest()
        print(f"  {label:<12} {bits:>5}  {status:<28}  {use}")

    print()
    print("  Full digest of sample string per algorithm:")
    for algo, label, bits, _, _ in rows:
        h = hashlib.new(algo, sample).hexdigest()
        print(f"    {label:<10}: {h}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("Message Digests & One-Way Hash Functions")
    print("Tanenbaum & Wetherall, Computer Networks, Chapter 8 Sec. 8.4.3")
    print("=" * 72)

    avalanche_demo()
    pre_image_resistance()
    collision_resistance_attempt()
    md5_vs_sha256_perf()
    hmac_demo()
    algorithm_summary()

    print("\n" + "=" * 72)
    print("All demonstrations complete.")
    print("=" * 72)


if __name__ == "__main__":
    main()
