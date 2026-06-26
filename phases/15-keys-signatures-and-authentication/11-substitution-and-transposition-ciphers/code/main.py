#!/usr/bin/env python3
"""Offline cipher workbench for classical substitution and transposition.

Implements, with stdlib only:

  * Caesar shift (monoalphabetic with k mod 26)
  * Full 26-letter monoalphabetic substitution (chapter example key)
  * Columnar transposition keyed by a word with unique letters
  * Letter frequency analysis
  * Crib-based plaintext recovery

No network, no third-party packages. Run with `python3 main.py`.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
CHAPTER_KEY = "QWERTYUIOPASDFGHJKLZXCVBNM"
CHAPTER_CT = (
    "CTBMNBYCTCBTJDSQXBNSGSTJCBTSWXCTQTZCQVUJ"
    "QJSGSTJQZZMNQJSVLNSXVSZJUJDSTSJQUUSJUBXJ"
    "DSKSUJSNTKBGAQJZBGYQTLCTZBNYBNQJSWA"
)


def _letters_only(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalpha())


def caesar_encrypt(text: str, k: int) -> str:
    """Shift every letter by k mod 26, preserving non-letters."""
    shift = k % 26
    out = []
    for ch in text:
        if ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            out.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            out.append(ch)
    return "".join(out)


def caesar_decrypt(text: str, k: int) -> str:
    return caesar_encrypt(text, -k)


def monoalphabetic_key(permutation: str) -> Dict[str, str]:
    """Map a->first, b->second, ..., using the 26-letter permutation string."""
    perm = _letters_only(permutation)
    if len(perm) != 26 or len(set(perm)) != 26:
        raise ValueError("permutation must contain each of 26 letters exactly once")
    return dict(zip(ALPHABET, perm))


def monoalphabetic_encrypt(text: str, key: Dict[str, str]) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in key:
            mapped = key[low]
            out.append(mapped.upper() if ch.isupper() else mapped)
        else:
            out.append(ch)
    return "".join(out)


def monoalphabetic_decrypt(text: str, key: Dict[str, str]) -> str:
    inverse = {v: k for k, v in key.items()}
    return monoalphabetic_encrypt(text, inverse)


def columnar_key_order(word: str) -> List[int]:
    """Return ranked column indices for a transposition key.

    Example: 'MEGABUCK' -> [7, 4, 5, 1, 2, 8, 3, 6] (the chapter example).
    """
    w = _letters_only(word)
    if not w:
        raise ValueError("empty key")
    if len(set(w)) != len(w):
        raise ValueError("key must have unique letters")
    order = sorted(range(len(w)), key=lambda i: (w[i], i))
    rank = [0] * len(w)
    for rank_value, original_index in enumerate(order):
        rank[original_index] = rank_value
    return rank


def columnar_encrypt(text: str, key: str) -> str:
    """Encrypt by writing row-major, reading column-major in key order.

    Pads plaintext with 'x' to a multiple of len(key).
    """
    w = _letters_only(key)
    ncols = len(w)
    plain = _letters_only(text)
    pad = (-len(plain)) % ncols
    plain += "x" * pad
    nrow = len(plain) // ncols
    rows = [plain[r * ncols:(r + 1) * ncols] for r in range(nrow)]
    rank = columnar_key_order(key)
    out: List[str] = []
    for column_index in sorted(range(ncols), key=lambda i: rank[i]):
        for row in rows:
            out.append(row[column_index])
    return "".join(out)


def columnar_decrypt(text: str, key: str) -> str:
    w = _letters_only(key)
    ncols = len(w)
    cipher = _letters_only(text)
    if len(cipher) % ncols != 0:
        raise ValueError("ciphertext length not divisible by key length")
    nrow = len(cipher) // ncols
    rank = columnar_key_order(key)
    column_order = sorted(range(ncols), key=lambda i: rank[i])
    col_lengths = {idx: nrow for idx in range(ncols)}
    columns: Dict[int, List[str]] = {}
    pos = 0
    for original_index in column_order:
        columns[original_index] = list(cipher[pos:pos + nrow])
        pos += nrow
    out: List[str] = []
    for r in range(nrow):
        for c in range(ncols):
            out.append(columns[c][r])
    return "".join(out)


def frequency_analysis(ciphertext: str) -> List[Tuple[str, int]]:
    letters = _letters_only(ciphertext)
    counts = Counter(letters)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def attack_with_crib(ciphertext: str, crib: str) -> List[int]:
    """Slide `crib` over ciphertext; return start positions where the
    repeated-letter pattern of the crib matches the ciphertext.

    The classic 'financial' attack on a monoalphabetic cipher.
    """
    cipher = _letters_only(ciphertext)
    c = _letters_only(crib)
    if not c or not cipher:
        return []
    hits: List[int] = []
    for start in range(len(cipher) - len(c) + 1):
        window = cipher[start:start + len(c)]
        seen: Dict[str, str] = {}
        ok = True
        for i, ch in enumerate(window):
            if ch in seen:
                if seen[ch] != c[i]:
                    ok = False
                    break
            else:
                if c[i] in seen.values():
                    ok = False
                    break
                seen[ch] = c[i]
        if ok:
            hits.append(start)
    return hits


def product_cipher(text: str, sub_key: Dict[str, str], trans_key: str) -> str:
    """Substitute then transpose: a two-round product cipher."""
    return columnar_encrypt(monoalphabetic_encrypt(text, sub_key), trans_key)


def product_decipher(text: str, sub_key: Dict[str, str], trans_key: str) -> str:
    return monoalphabetic_decrypt(columnar_decrypt(text, trans_key), sub_key)


def demo() -> None:
    print("=== Caesar round-trip ===")
    pt = "attack at dawn"
    ct = caesar_encrypt(pt, 3)
    print(f"  caesar('attack at dawn', 3) = {ct!r}")
    print(f"  decrypt -> {caesar_decrypt(ct, 3)!r}")

    print("\n=== Monoalphabetic substitution ===")
    sub_key = monoalphabetic_key(CHAPTER_KEY)
    print(f"  encrypt('attack') = {monoalphabetic_encrypt('attack', sub_key)!r}")
    print(f"  decrypt -> {monoalphabetic_decrypt('QZZQEA', sub_key)!r}")

    print("\n=== Columnar transposition (MEGABUCK) ===")
    print(f"  key order = {columnar_key_order('MEGABUCK')}")
    pt2 = "pleasetransferonemilliondollarsto"
    ct2 = columnar_encrypt(pt2, "MEGABUCK")
    print(f"  encrypt('pleasetransferonemilliondollarsto') = {ct2!r}")
    print(f"  decrypt -> {columnar_decrypt(ct2, 'MEGABUCK').rstrip('x')!r}")

    print("\n=== Frequency analysis on chapter ciphertext ===")
    for letter, count in frequency_analysis(CHAPTER_CT)[:8]:
        print(f"  {letter}: {count}")

    print("\n=== Crib attack with 'financial' ===")
    print(f"  hits = {attack_with_crib(CHAPTER_CT, 'financial')}")

    print("\n=== Product cipher (substitute + transpose) ===")
    p_pt = "sendmoremoneytomorrow"
    p_ct = product_cipher(p_pt, sub_key, "CIPHER")
    print(f"  encrypt = {p_ct!r}")
    print(f"  decrypt = {product_decipher(p_ct, sub_key, 'CIPHER')!r}")


def main() -> None:
    demo()


if __name__ == "__main__":
    main()