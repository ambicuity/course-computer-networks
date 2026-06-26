#!/usr/bin/env python3
"""Transposition Ciphers to One-Time Pads.

Demonstrates columnar transposition (key MEGABUCK), the frequency tell
that distinguishes transposition from substitution, digram-based key-length
recovery, and the one-time pad XOR encryption/decryption with a worked
keystream-reuse attack. No external dependencies; runs under plain python3.
"""

from __future__ import annotations

import collections


def column_order(key: str) -> list[int]:
    """Return the column read-out order: column under the letter nearest A is 0."""
    indexed: list[tuple[str, int]] = [(ch, i) for i, ch in enumerate(key.upper())]
    indexed.sort()
    order: list[int] = [0] * len(key)
    for rank, (_, original_pos) in enumerate(indexed):
        order[original_pos] = rank
    return order


def transposition_encrypt(plaintext: str, key: str) -> str:
    """Columnar transposition: write rows, read columns in key order."""
    k: int = len(key)
    rows: int = (len(plaintext) + k - 1) // k
    padded: str = plaintext.ljust(rows * k)
    grid: list[list[str]] = [list(padded[i * k:(i + 1) * k]) for i in range(rows)]
    order: list[int] = column_order(key)
    out: list[str] = []
    for target_rank in range(k):
        col: int = order.index(target_rank)
        for r in range(rows):
            out.append(grid[r][col])
    return "".join(out)


def transposition_decrypt(ciphertext: str, key: str) -> str:
    """Reverse: fill columns in key order, read rows."""
    k: int = len(key)
    rows: int = len(ciphertext) // k
    order: list[int] = column_order(key)
    grid: list[list[str]] = [[""] * k for _ in range(rows)]
    idx: int = 0
    for target_rank in range(k):
        col: int = order.index(target_rank)
        for r in range(rows):
            grid[r][col] = ciphertext[idx]
            idx += 1
    return "".join(grid[r][c] for r in range(rows) for c in range(k)).rstrip()


def letter_frequencies(text: str) -> collections.Counter:
    """Count alpha letter frequencies (case-insensitive)."""
    return collections.Counter(ch.upper() for ch in text if ch.isalpha())


def digram_set_for_word(word: str, key_len: int) -> list[str]:
    """Digrams produced by 'word' when wrapped in a columnar cipher of key_len."""
    return [word[i] + word[i + key_len] for i in range(len(word) - key_len)]


def otp_encrypt(plaintext: str, pad: bytes) -> bytes:
    """One-time pad encrypt: XOR 7-bit ASCII bytes with pad bytes."""
    pt_bytes: bytes = plaintext.encode("ascii")
    return bytes(p ^ k for p, k in zip(pt_bytes, pad))


def otp_decrypt(ciphertext: bytes, pad: bytes) -> str:
    """One-time pad decrypt: XOR ciphertext bytes with pad bytes (latin-1 safe)."""
    return bytes(c ^ k for c, k in zip(ciphertext, pad)).decode("latin-1")


def main() -> None:
    print("Lesson: Transposition Ciphers to One-Time Pads\n")

    # Columnar transposition
    key: str = "MEGABUCK"
    msg: str = "pleasetransferonemilliondollarstomyswissbankaccountsixtwotwo"
    ct: str = transposition_encrypt(msg, key)
    pt: str = transposition_decrypt(ct, key)
    print(f"Key: {key}  column order: {column_order(key)}")
    print(f"Plaintext:  {msg}")
    print(f"Ciphertext: {ct}")
    print(f"Decrypted:  {pt}")
    print(f"Round-trip: {'OK' if pt == msg else 'FAIL'}\n")

    # Frequency tell
    print("Letter frequency comparison (plaintext vs ciphertext):")
    pf: collections.Counter = letter_frequencies(msg)
    cf: collections.Counter = letter_frequencies(ct)
    total_p: int = sum(pf.values())
    total_c: int = sum(cf.values())
    for ch in "ETAOINSHR":
        pp: float = pf.get(ch, 0) / total_p * 100 if total_p else 0.0
        cp: float = cf.get(ch, 0) / total_c * 100 if total_c else 0.0
        print(f"  {ch}: plaintext {pp:4.1f}%  ciphertext {cp:4.1f}%")
    print("Frequencies match -> transposition (not substitution).\n")

    # Digram patterns for key length discovery
    word: str = "milliondollars"
    print(f"Probable word '{word}' digram sets by key length:")
    for kl in (6, 7, 8, 9):
        digrams: list[str] = digram_set_for_word(word, kl)
        print(f"  k={kl}: {', '.join(digrams)}")

    # One-time pad
    print("\n=== One-Time Pad ===")
    pad1: bytes = bytes([0x52, 0x4B, 0x72, 0x55, 0x52, 0x63, 0x0B, 0x5A,
                         0x57, 0x66, 0x2B])
    msg1: str = "I love you."
    ct1: bytes = otp_encrypt(msg1, pad1)
    pt1: str = otp_decrypt(ct1, pad1)
    print(f"Message: {msg1}")
    print(f"Pad1:    {pad1.hex()}")
    print(f"Cipher:  {ct1.hex()}")
    print(f"Decrypt: {pt1}  {'OK' if pt1 == msg1 else 'FAIL'}")

    # Different pad -> different plausible plaintext
    pad2: bytes = bytes([0x5E, 0x07, 0x68, 0x53, 0x57, 0x26, 0x47,
                         0x4A, 0x4E, 0x76, 0x76])
    pt2: str = otp_decrypt(ct1, pad2)
    print(f"Pad2:    {pad2.hex()}")
    print(f"Decrypt with pad2: {repr(pt2)}")
    print("Any 11-char plaintext is possible -> ciphertext carries zero info.\n")

    # Keystream reuse attack
    print("=== OTP Reuse Attack ===")
    msg_a: str = "attack dawn"
    msg_b: str = "defend noon"
    pad: bytes = bytes([0x4A, 0x7C, 0x39, 0x61, 0x42, 0x5D, 0x6B, 0x12, 0x34, 0x56, 0x78])
    ct_a: bytes = otp_encrypt(msg_a, pad)
    ct_b: bytes = otp_encrypt(msg_b, pad)
    xor_ct: bytes = bytes(a ^ b for a, b in zip(ct_a, ct_b))
    xor_pt: bytes = bytes(a ^ b for a, b in zip(msg_a.encode(), msg_b.encode()))
    print(f"  C_A XOR C_B = {xor_ct.hex()}")
    print(f"  P_A XOR P_B = {xor_pt.hex()}")
    print(f"  Match: {'YES - key eliminated' if xor_ct == xor_pt else 'NO'}")
    print("With P_A known, P_B = (C_A XOR C_B) XOR P_A -> recovered.")


if __name__ == "__main__":
    main()