#!/usr/bin/env python3
"""Introduction to Cryptography - toy Caesar cipher and work-factor demo.

Demonstrates the encryption model C = E_K(P), the round-trip identity
D_K(E_K(P)) = P, Kerckhoffs's principle (algorithm public, key secret),
and the exponential relationship between key length and brute-force
work factor. No external dependencies; runs under plain python3.
"""

from __future__ import annotations

ALPHABET: str = "abcdefghijklmnopqrstuvwxyz"
CIPHERTEXT_ALPHABET: str = ALPHABET.upper()


def caesar_encrypt(plaintext: str, key: int) -> str:
    """Encrypt with a Caesar cipher shifted by key positions (algorithm public)."""
    out: list[str] = []
    for ch in plaintext:
        if ch.lower() in ALPHABET:
            idx: int = ALPHABET.index(ch.lower())
            new_idx: int = (idx + key) % len(ALPHABET)
            out.append(CIPHERTEXT_ALPHABET[new_idx])
        else:
            out.append(ch)
    return "".join(out)


def caesar_decrypt(ciphertext: str, key: int) -> str:
    """Decrypt by shifting backward by key positions; D_K(E_K(P)) = P."""
    out: list[str] = []
    for ch in ciphertext:
        if ch.upper() in CIPHERTEXT_ALPHABET:
            idx: int = CIPHERTEXT_ALPHABET.index(ch.upper())
            new_idx: int = (idx - key) % len(ALPHABET)
            out.append(ALPHABET[new_idx])
        else:
            out.append(ch)
    return "".join(out)


def work_factor(key_bits: int, keys_per_second: int = 10**9) -> float:
    """Return seconds for exhaustive search of a key space of 2^key_bits."""
    return float(2 ** key_bits) / float(keys_per_second)


def format_seconds(seconds: float) -> str:
    """Render seconds in a human-friendly unit."""
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    if seconds < 3600:
        return f"{seconds:.1f} s"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    if seconds < 31557600:
        return f"{seconds / 86400:.1f} days"
    years: float = seconds / 31557600.0
    if years < 1000:
        return f"{years:.1f} years"
    if years < 10**6:
        return f"{years:.0f} years"
    return f"{years:.3e} years"


def demo_roundtrip(messages: list[str], keys: list[int]) -> None:
    """Verify D_K(E_K(P)) == P for each message/key pair."""
    print("=== Round-trip identity D_K(E_K(P)) == P ===")
    for key in keys:
        print(f"\nKey (shift) = {key}")
        for msg in messages:
            ct: str = caesar_encrypt(msg, key)
            pt: str = caesar_decrypt(ct, key)
            ok: bool = pt == msg
            print(f"  {msg:20s} -> {ct:20s} -> {pt:20s}  {'OK' if ok else 'FAIL'}")


def demo_work_factor() -> None:
    """Print the key-length vs brute-force table."""
    print("\n=== Work factor: exhaustive key search at 10^9 keys/sec ===")
    print(f"{'bits':>6}  {'key space':>18}  {'time':>22}")
    for bits in (8, 16, 32, 40, 56, 64, 80, 128, 192, 256):
        seconds: float = work_factor(bits)
        space: int = 2 ** bits
        print(f"{bits:>6}  {space:>18,}  {format_seconds(seconds):>22}")


def demo_attack_models() -> None:
    """Show how known-plaintext collapses the Caesar key space to 26 trials."""
    print("\n=== Attack models on Caesar cipher ===")
    ciphertext: str = "DWWDFN"  # Caesar(3) of "attack"
    print(f"Ciphertext: {ciphertext}")
    print("Ciphertext-only: try all 26 shifts:")
    for k in range(len(ALPHABET)):
        guess: str = caesar_decrypt(ciphertext, k)
        marker: str = ""
        if guess == "attack":
            marker = "  <-- correct key"
        print(f"  k={k:>2}  -> {guess}{marker}")
    print("\nKnown-plaintext: given 'attack' maps to 'DWWDFN', key = 3 instantly.")
    print("Chosen-plaintext:  ask for E('a'); the returned letter IS the key.")


def main() -> None:
    print("Lesson: Introduction to Cryptography\n")
    messages: list[str] = ["attack at dawn", "hello world", "meet me at noon"]
    keys: list[int] = [3, 7, 13]
    demo_roundtrip(messages, keys)
    demo_work_factor()
    demo_attack_models()
    print("\nKerckhoffs's principle: the algorithm above is fully public.")
    print("Only the key (the shift amount) is secret. 26 keys is trivially small;")
    print("real security comes from 128+ bit keys, not from hiding the algorithm.")


if __name__ == "__main__":
    main()