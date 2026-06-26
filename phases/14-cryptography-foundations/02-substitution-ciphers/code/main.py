#!/usr/bin/env python3
"""Substitution Ciphers - Caesar, monoalphabetic, and frequency analysis.

Demonstrates the Caesar cipher, an arbitrary monoalphabetic substitution,
and a frequency-analysis attack that recovers the key from ciphertext
without brute force. No external dependencies; runs under plain python3.
"""

from __future__ import annotations

import collections

PLAIN: str = "abcdefghijklmnopqrstuvwxyz"
CIPHER: str = PLAIN.upper()

# English letter frequencies (approximate percentages), used for ranking.
ENGLISH_FREQ_ORDER: str = "etaoinshrdlcumwfgypbvkjxqz"


def caesar_encrypt(plaintext: str, key: int) -> str:
    """Caesar encrypt: shift each letter by key; preserve non-letters."""
    out: list[str] = []
    for ch in plaintext:
        if ch.lower() in PLAIN:
            idx: int = PLAIN.index(ch.lower())
            out.append(CIPHER[(idx + key) % 26])
        else:
            out.append(ch)
    return "".join(out)


def caesar_decrypt(ciphertext: str, key: int) -> str:
    """Caesar decrypt: shift back by key."""
    out: list[str] = []
    for ch in ciphertext:
        if ch.upper() in CIPHER:
            idx: int = CIPHER.index(ch.upper())
            out.append(PLAIN[(idx - key) % 26])
        else:
            out.append(ch)
    return "".join(out)


def mono_encrypt(plaintext: str, key_alphabet: str) -> str:
    """Monoalphabetic encrypt: key_alphabet is a 26-letter permutation."""
    table: dict[str, str] = dict(zip(PLAIN, key_alphabet.upper()))
    return "".join(table.get(ch.lower(), ch) for ch in plaintext)


def mono_decrypt(ciphertext: str, key_alphabet: str) -> str:
    """Monoalphabetic decrypt: reverse the permutation."""
    rev: dict[str, str] = dict(zip(key_alphabet.upper(), PLAIN))
    return "".join(rev.get(ch.upper(), ch) for ch in ciphertext)


def frequency_rank(ciphertext: str) -> list[tuple[str, int]]:
    """Return letters of ciphertext sorted by descending frequency."""
    counts: collections.Counter = collections.Counter(
        ch.upper() for ch in ciphertext if ch.isalpha()
    )
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def frequency_attack(ciphertext: str) -> dict[str, str]:
    """Map ciphertext letters to English-frequency-ordered plaintext guesses."""
    ranked: list[tuple[str, int]] = frequency_rank(ciphertext)
    mapping: dict[str, str] = {}
    for i, (cipher_ch, _) in enumerate(ranked):
        if i < len(ENGLISH_FREQ_ORDER):
            mapping[cipher_ch] = ENGLISH_FREQ_ORDER[i]
    return mapping


def apply_mapping(ciphertext: str, mapping: dict[str, str]) -> str:
    """Apply a partial frequency mapping to produce a guess at plaintext."""
    out: list[str] = []
    for ch in ciphertext:
        if ch.upper() in mapping:
            out.append(mapping[ch.upper()])
        else:
            out.append(ch)
    return "".join(out)


def probable_word_positions(ciphertext: str, word: str) -> list[int]:
    """Find ciphertext positions where 'word' could align by letter pattern.

    Two letters in 'word' match if they are equal; the ciphertext letters
    at the same relative offsets must follow the same equality pattern.
    """
    clean: str = "".join(ch.upper() for ch in ciphertext if ch.isalpha())
    w: str = word.lower()
    positions: list[int] = []
    for start in range(len(clean) - len(w) + 1):
        ok: bool = True
        for i in range(len(w)):
            for j in range(i + 1, len(w)):
                same_in_word: bool = w[i] == w[j]
                same_in_cipher: bool = clean[start + i] == clean[start + j]
                if same_in_word != same_in_cipher:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            positions.append(start)
    return positions


def main() -> None:
    print("Lesson: Substitution Ciphers\n")

    # Caesar demo
    msg: str = "attack at dawn"
    for k in (3, 7, 13):
        ct: str = caesar_encrypt(msg, k)
        pt: str = caesar_decrypt(ct, k)
        print(f"Caesar k={k:>2}: {msg} -> {ct} -> {pt}  {'OK' if pt == msg else 'FAIL'}")

    # Monoalphabetic demo
    key_alpha: str = "QWERTYUIOPASDFGHJKLZXCVBNM"
    ct_mono: str = mono_encrypt(msg, key_alpha)
    pt_mono: str = mono_decrypt(ct_mono, key_alpha)
    print(f"\nMono key={key_alpha}")
    print(f"  {msg} -> {ct_mono} -> {pt_mono}  {'OK' if pt_mono == msg else 'FAIL'}")

    # Frequency analysis on a longer sample
    sample_pt: str = (
        "the quick brown fox jumps over the lazy dog and the dog ran away "
        "the end is near and the beginning is also near and everything "
        "in between is just the middle of the story that never ends well"
    )
    ct_sample: str = mono_encrypt(sample_pt, key_alpha)
    print(f"\nSample ciphertext (first 80 chars): {ct_sample[:80]}...")
    ranked: list[tuple[str, int]] = frequency_rank(ct_sample)
    print("Ciphertext letter frequencies (top 10):")
    for ch, count in ranked[:10]:
        print(f"  {ch}: {count}")
    mapping: dict[str, str] = frequency_attack(ct_sample)
    guess: str = apply_mapping(ct_sample, mapping)
    print(f"\nFrequency-attack guess (first 80 chars): {guess[:80]}...")
    print(f"Original plaintext  (first 80 chars): {sample_pt[:80]}...")

    # Probable word attack
    word: str = "financial"
    positions: list[int] = probable_word_positions(ct_sample, word)
    print(f"\nProbable word '{word}' pattern matches at positions: {positions}")
    print("Note: real attack would then align n, a and deduce key letters.")


if __name__ == "__main__":
    main()