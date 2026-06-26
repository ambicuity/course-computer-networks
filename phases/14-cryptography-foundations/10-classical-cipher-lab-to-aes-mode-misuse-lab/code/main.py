#!/usr/bin/env python3
"""Classical Cipher Lab + AES Mode Misuse Lab (textbook Sec 8.2 & 8.3).

Stdlib only. Demonstrates:

1. Caesar cipher breaker via frequency analysis.
2. Vigenere cipher breaker via Kasiski examination + Friedman test.
3. AES mode misuse: ECB pattern preservation, CBC IV reuse, CTR nonce reuse.
   (AES modes modeled with XOR-based simulation since no external crypto.)

Run:  python3 main.py
"""
from __future__ import annotations

import string
from collections import Counter


def caesar_encrypt(text: str, shift: int) -> str:
    result = []
    for ch in text.upper():
        if ch in string.ascii_uppercase:
            result.append(chr((ord(ch) - ord('A') + shift) % 26 + ord('A')))
        else:
            result.append(ch)
    return ''.join(result)


def caesar_decrypt(text: str, shift: int) -> str:
    return caesar_encrypt(text, -shift)


def caesar_break(ciphertext: str) -> list[tuple[int, str, float]]:
    english_freq = {
        'E': 12.7, 'T': 9.1, 'A': 8.2, 'O': 7.5, 'I': 7.0, 'N': 6.7,
        'S': 6.3, 'H': 6.1, 'R': 6.0, 'D': 4.3, 'L': 4.0, 'C': 2.8,
        'U': 2.8, 'M': 2.4, 'W': 2.4, 'F': 2.2, 'G': 2.0, 'Y': 2.0,
        'P': 1.9, 'B': 1.5, 'V': 1.0, 'K': 0.8, 'J': 0.2, 'X': 0.2,
        'Q': 0.1, 'Z': 0.1,
    }
    results = []
    for shift in range(26):
        decrypted = caesar_decrypt(ciphertext, shift)
        letters = [c for c in decrypted if c in string.ascii_uppercase]
        if not letters:
            results.append((shift, decrypted, 0.0))
            continue
        freq = Counter(letters)
        total = len(letters)
        score = sum(english_freq.get(ch, 0) * (freq.get(ch, 0) / total) for ch in english_freq)
        results.append((shift, decrypted, score))
    results.sort(key=lambda x: -x[2])
    return results


def vigenere_encrypt(text: str, key: str) -> str:
    result = []
    ki = 0
    for ch in text.upper():
        if ch in string.ascii_uppercase:
            shift = ord(key.upper()[ki % len(key)]) - ord('A')
            result.append(chr((ord(ch) - ord('A') + shift) % 26 + ord('A')))
            ki += 1
        else:
            result.append(ch)
    return ''.join(result)


def vigenere_decrypt(text: str, key: str) -> str:
    result = []
    ki = 0
    for ch in text.upper():
        if ch in string.ascii_uppercase:
            shift = ord(key.upper()[ki % len(key)]) - ord('A')
            result.append(chr((ord(ch) - ord('A') - shift) % 26 + ord('A')))
            ki += 1
        else:
            result.append(ch)
    return ''.join(result)


def kasiski_examination(ciphertext: str, min_seq_len: int = 3) -> list[int]:
    positions: dict[str, list[int]] = {}
    clean = ''.join(c for c in ciphertext.upper() if c in string.ascii_uppercase)
    for i in range(len(clean) - min_seq_len + 1):
        seq = clean[i:i + min_seq_len]
        positions.setdefault(seq, []).append(i)

    distances = []
    for seq, pos_list in positions.items():
        if len(pos_list) > 1:
            for j in range(len(pos_list) - 1):
                distances.append(pos_list[j + 1] - pos_list[j])

    from math import gcd
    from functools import reduce
    if not distances:
        return [1]

    def gcd_list(nums: list[int]) -> int:
        return reduce(gcd, nums)

    factors: dict[int, int] = {}
    for d in distances:
        for f in range(2, d + 1):
            if d % f == 0:
                factors[f] = factors.get(f, 0) + 1

    sorted_factors = sorted(factors.items(), key=lambda x: -x[1])
    return [f for f, _ in sorted_factors[:5]]


def friedman_test(ciphertext: str) -> float:
    clean = ''.join(c for c in ciphertext.upper() if c in string.ascii_uppercase)
    n = len(clean)
    if n <= 1:
        return 1.0
    freq = Counter(clean)
    ic = sum(f * (f - 1) for f in freq.values()) / (n * (n - 1))
    kp = 0.0667
    kr = 0.0385
    if ic == kr:
        return 1.0
    estimated_key_len = (kp - kr) / (ic - kr)
    return max(1.0, estimated_key_len)


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def simulate_ecb_encrypt(blocks: list[bytes], key: bytes) -> list[bytes]:
    return [xor_bytes(blk, key) for blk in blocks]


def simulate_cbc_encrypt(blocks: list[bytes], key: bytes, iv: bytes) -> list[bytes]:
    result = []
    prev = iv
    for blk in blocks:
        xored = xor_bytes(blk, prev)
        enc = xor_bytes(xored, key)
        result.append(enc)
        prev = enc
    return result


def simulate_ctr_encrypt(blocks: list[bytes], key: bytes, nonce: bytes) -> list[bytes]:
    result = []
    for i, blk in enumerate(blocks):
        counter = nonce + i.to_bytes(4, 'big')
        keystream = xor_bytes(counter, key)
        result.append(xor_bytes(blk, keystream))
    return result


def main() -> None:
    print("=" * 65)
    print("Caesar Cipher Breaker (Frequency Analysis)")
    print("=" * 65)

    plaintext = "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG AND THE DOG BARKED LOUDLY"
    shift = 7
    ciphertext = caesar_encrypt(plaintext, shift)
    print(f"  Plaintext:  {plaintext}")
    print(f"  Shift:      {shift}")
    print(f"  Ciphertext: {ciphertext}")

    results = caesar_break(ciphertext)
    print(f"\n  Top 5 candidates by frequency score:")
    for rank, (s, text, score) in enumerate(results[:5], 1):
        marker = " <-- CORRECT" if s == shift else ""
        print(f"    {rank}. shift={s:2d} score={score:.3f}  {text}{marker}")

    print()
    print("=" * 65)
    print("Vigenere Cipher Breaker (Kasiski + Friedman)")
    print("=" * 65)

    vig_key = "CIPHER"
    vig_plain = "THEQUICKBROWNFOXJUMPSOVERTHELAZYDOGANDTHEDOGBARKEDLOUDLYATTHEMOON"
    vig_ct = vigenere_encrypt(vig_plain, vig_key)
    print(f"  Plaintext:  {vig_plain}")
    print(f"  Key:        {vig_key}")
    print(f"  Ciphertext: {vig_ct}")

    kasiski = kasiski_examination(vig_ct)
    friedman = friedman_test(vig_ct)
    print(f"\n  Kasiski examination (likely key lengths): {kasiski}")
    print(f"  Friedman test (estimated key length): {friedman:.1f}")
    print(f"  Actual key length: {len(vig_key)}")

    recovered = vigenere_decrypt(vig_ct, vig_key)
    print(f"  Decrypted with recovered key: {recovered}")
    print(f"  Match: {'YES' if recovered == vig_plain else 'NO'}")

    print()
    print("=" * 65)
    print("AES Mode Misuse Lab (XOR-based simulation)")
    print("=" * 65)

    key = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    iv = b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11"

    block_a = b"MESSAGE1"
    block_b = b"MESSAGE2"
    block_c = b"MESSAGE1"
    blocks = [block_a, block_b, block_c]

    print(f"  Plaintext blocks: {[b.hex() for b in blocks]}")
    print(f"  Note: block[0] == block[2] (identical plaintext)")

    print(f"\n  ECB Mode (no IV, no chaining):")
    ecb_ct = simulate_ecb_encrypt(blocks, key)
    print(f"    Ciphertext: {[c.hex() for c in ecb_ct]}")
    print(f"    block[0]==block[2]? {'YES - PATTERN LEAKED!' if ecb_ct[0]==ecb_ct[2] else 'no'}")
    print(f"    Lesson: ECB encrypts identical blocks identically.")
    print(f"    The famous 'ECB penguin' shows the plaintext pattern through ciphertext.")

    print(f"\n  CBC with fresh IV (correct usage):")
    cbc_ct = simulate_cbc_encrypt(blocks, key, iv)
    print(f"    Ciphertext: {[c.hex() for c in cbc_ct]}")
    print(f"    block[0]==block[2]? {'YES' if cbc_ct[0]==cbc_ct[2] else 'NO - chains break pattern'}")

    print(f"\n  CBC with IV reuse (misuse - same IV for two messages):")
    msg1 = [b"SECRET_A"]
    msg2 = [b"SECRET_B"]
    cbc1 = simulate_cbc_encrypt(msg1, key, iv)
    cbc2 = simulate_cbc_encrypt(msg2, key, iv)
    print(f"    Msg1 CT: {cbc1[0].hex()}")
    print(f"    Msg2 CT: {cbc2[0].hex()}")
    xored = xor_bytes(cbc1[0], cbc2[0])
    leaked = xor_bytes(xored, xor_bytes(msg1[0], msg2[0]))
    print(f"    IV reuse leaks: CT1 XOR CT2 = (P1 XOR IV) XOR (P2 XOR IV) = P1 XOR P2")
    print(f"    Recovered P1 XOR P2: {xored.hex()}")
    print(f"    If attacker knows P1, they recover P2 = P1 XOR (CT1 XOR CT2)")

    print(f"\n  CTR with nonce reuse (misuse - same nonce for two messages):")
    ctr1 = simulate_ctr_encrypt(msg1, key, nonce=b"\x00\x00\x00\x00")
    ctr2 = simulate_ctr_encrypt(msg2, key, nonce=b"\x00\x00\x00\x00")
    print(f"    Msg1 CT: {ctr1[0].hex()}")
    print(f"    Msg2 CT: {ctr2[0].hex()}")
    keystream_leak = xor_bytes(ctr1[0], ctr2[0])
    print(f"    CT1 XOR CT2 = P1 XOR P2 = {keystream_leak.hex()}")
    print(f"    Attacker who knows P1 recovers P2 directly.")
    print(f"    Lesson: CTR mode is a stream cipher. Nonce reuse = keystream reuse = catastrophic.")

    print()
    print("=" * 65)
    print("Mode Misuse Summary")
    print("=" * 65)
    print(f"  {'Mode':8s} {'Misuse':25s} {'Consequence'}")
    print(f"  {'-'*8} {'-'*25} {'-'*30}")
    print(f"  {'ECB':8s} {'Identical plaintext blocks':25s} {'Identical ciphertext (pattern leak)'}")
    print(f"  {'CBC':8s} {'IV reuse':25s} {'First-block plaintext XOR leak'}")
    print(f"  {'CTR':8s} {'Nonce reuse':25s} {'Full keystream reuse (XOR leak)'}")
    print(f"  {'GCM':8s} {'Nonce reuse':25s} {'Authentication forgery + plaintext'}")


if __name__ == "__main__":
    main()
