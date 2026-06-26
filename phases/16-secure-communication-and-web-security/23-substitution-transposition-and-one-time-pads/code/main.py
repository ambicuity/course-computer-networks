"""Classical ciphers: substitution, transposition, one-time pads.

Implements Caesar, monoalphabetic, Vigenere, columnar transposition, and the
one-time pad in pure stdlib, plus three classical attacks:

  * frequency analysis on monoalphabetic ciphertext
  * Kasiski + Friedman (Index of Coincidence) on Vigenere ciphertext
  * key-reuse attack on the OTP (XOR of two ciphertexts)

All ciphers round-trip via `decrypt(encrypt(m, k), k) == m` for sane inputs.
"""

from __future__ import annotations

import math
import secrets
import string
from collections import Counter

ENGLISH_FREQ_ORDER = "ETAOINSRHLDCUMWFGYPBVKJXQZ"
IC_ENGLISH = 0.066
IC_RANDOM = 1 / 26


def caesar_encrypt(text: str, k: int) -> str:
    out = []
    for ch in text.lower():
        if ch.isalpha():
            out.append(chr((ord(ch) - ord("a") + k) % 26 + ord("a")))
        else:
            out.append(ch)
    return "".join(out)


def caesar_decrypt(text: str, k: int) -> str:
    return caesar_encrypt(text, -k % 26)


def caesar_brute(text: str) -> list[tuple[int, str, float]]:
    candidates = []
    for k in range(26):
        plain = caesar_decrypt(text, k)
        score = english_score(plain)
        candidates.append((k, plain, score))
    candidates.sort(key=lambda x: -x[2])
    return candidates


def monoalphabetic_encrypt(text: str, key_perm: str) -> str:
    alphabet = string.ascii_lowercase
    table = str.maketrans(alphabet, key_perm.lower())
    return text.lower().translate(table)


def monoalphabetic_decrypt(text: str, key_perm: str) -> str:
    alphabet = string.ascii_lowercase
    table = str.maketrans(key_perm.lower(), alphabet)
    return text.lower().translate(table)


def english_score(text: str) -> float:
    counts = Counter(c for c in text.lower() if c.isalpha())
    total = sum(counts.values())
    if total == 0:
        return 0.0
    score = 0.0
    for ch, expected in zip(ENGLISH_FREQ_ORDER, (12.7, 9.1, 8.2, 7.5, 7.0, 6.7, 6.3, 6.1, 5.0, 4.3, 4.0, 2.8, 2.8, 2.4, 2.4, 2.2, 2.0, 1.9, 1.5, 1.0, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1)):
        observed = counts.get(ch.lower(), 0) / total * 100
        score -= (observed - expected) ** 2
    return score


def frequency_break(ciphertext: str) -> str:
    counts = Counter(c for c in ciphertext.lower() if c.isalpha())
    observed_order = "".join(c for c, _ in counts.most_common())
    observed_padded = observed_order + "".join(c for c in string.ascii_lowercase if c not in observed_order)
    table = str.maketrans(observed_padded, ENGLISH_FREQ_ORDER.lower())
    return ciphertext.lower().translate(table)


def vigenere_encrypt(text: str, key: str) -> str:
    out = []
    key = key.lower()
    j = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[j % len(key)]) - ord("a")
            base = ord("a") if ch.islower() else ord("A")
            out.append(chr((ord(ch) - base + shift) % 26 + base))
            j += 1
        else:
            out.append(ch)
    return "".join(out)


def vigenere_decrypt(text: str, key: str) -> str:
    out = []
    key = key.lower()
    j = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[j % len(key)]) - ord("a")
            base = ord("a") if ch.islower() else ord("A")
            out.append(chr((ord(ch) - base - shift) % 26 + base))
            j += 1
        else:
            out.append(ch)
    return "".join(out)


def index_of_coincidence(text: str) -> float:
    letters = [c for c in text.lower() if c.isalpha()]
    n = len(letters)
    if n < 2:
        return 0.0
    counts = Counter(letters)
    pairs = sum(c * (c - 1) for c in counts.values())
    return pairs / (n * (n - 1))


def kasiski_key_length(ciphertext: str, min_len: int = 3) -> int:
    letters = "".join(c for c in ciphertext.lower() if c.isalpha())
    seen: dict[str, list[int]] = {}
    for i in range(len(letters) - min_len + 1):
        gram = letters[i:i + min_len]
        seen.setdefault(gram, []).append(i)
    distances = []
    for positions in seen.values():
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                distances.append(positions[i + 1] - positions[i])
    if not distances:
        return 1
    common = Counter(distances).most_common(5)
    best = common[0][0]
    for k in range(2, 16):
        if best % k == 0:
            return k
    return best


def friedman_key_length(ciphertext: str, max_len: int = 12) -> int:
    letters = "".join(c for c in ciphertext.lower() if c.isalpha())
    best_k = 1
    best_diff = float("inf")
    for k in range(1, max_len + 1):
        diffs = []
        for i in range(k):
            column = letters[i::k]
            if len(column) > 1:
                diffs.append(abs(index_of_coincidence(column) - IC_ENGLISH))
        if diffs:
            avg = sum(diffs) / len(diffs)
            if avg < best_diff:
                best_diff = avg
                best_k = k
    return best_k


def vigenere_break(ciphertext: str, key_length: int | None = None) -> tuple[str, str]:
    if key_length is None:
        key_length = friedman_key_length(ciphertext)
    letters = "".join(c for c in ciphertext.lower() if c.isalpha())
    key_chars = []
    for i in range(key_length):
        column = letters[i::key_length]
        best_k = 0
        best_score = -math.inf
        for shift in range(26):
            shifted = "".join(chr((ord(c) - ord("a") - shift) % 26 + ord("a")) for c in column)
            score = english_score(shifted)
            if score > best_score:
                best_score = score
                best_k = shift
        key_chars.append(chr(best_k + ord("a")))
    recovered_key = "".join(key_chars)
    return recovered_key, vigenere_decrypt(ciphertext, recovered_key)


def columnar_transposition_encrypt(text: str, key: str) -> str:
    key = key.lower()
    order = sorted(range(len(key)), key=lambda i: (key[i], i))
    cols = len(key)
    rows = math.ceil(len(text) / cols)
    padded = text.ljust(rows * cols, " ")
    grid = [padded[r * cols:(r + 1) * cols] for r in range(rows)]
    out = []
    for col in order:
        for row in grid:
            out.append(row[col])
    return "".join(out).rstrip()


def columnar_transposition_decrypt(text: str, key: str) -> str:
    key = key.lower()
    order = sorted(range(len(key)), key=lambda i: (key[i], i))
    cols = len(key)
    rows = math.ceil(len(text) / cols)
    grid = [[""] * cols for _ in range(rows)]
    idx = 0
    for col in order:
        for r in range(rows):
            if idx < len(text):
                grid[r][col] = text[idx]
                idx += 1
    return "".join("".join(row) for row in grid).rstrip()


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def otp_encrypt(message: bytes, key: bytes) -> bytes:
    if len(key) < len(message):
        raise ValueError("OTP key must be at least as long as the message")
    return xor_bytes(message, key)


def otp_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    return xor_bytes(ciphertext, key)


def key_reuse_attack(c1: bytes, c2: bytes, known_plaintext: bytes) -> bytes:
    if len(known_plaintext) > len(c1):
        return b""
    leaked = xor_bytes(c1[:len(known_plaintext)], c2[:len(known_plaintext)])
    return xor_bytes(leaked, known_plaintext)


def main() -> None:
    print("=" * 68)
    print("CLASSICAL CIPHERS  --  substitution, transposition, OTP")
    print("=" * 68)

    print("\n[1] Caesar: attack at dawn -> shift 3")
    print(f"  plaintext  : attack at dawn")
    print(f"  ciphertext : {caesar_encrypt('attack at dawn', 3)}")
    print(f"  decrypted  : {caesar_decrypt(caesar_encrypt('attack at dawn', 3), 3)}")

    print("\n[2] Monoalphabetic frequency break")
    plain = "the quick brown fox jumps over the lazy dog and then runs away into the dark forest near the river"
    key = "QWERTYUIOPASDFGHJKLZXCVBNM"
    cipher = monoalphabetic_encrypt(plain, key)
    recovered = frequency_break(cipher)
    print(f"  ciphertext[:40]: {cipher[:40]}")
    print(f"  recovered[:40]  : {recovered[:40]}")

    print("\n[3] Vigenere + Kasiski/Friedman attack")
    vplain = "tobeornottobethatisthequestionwhethertisnoblerinthemind" * 3
    vkey = "hamlet"
    vcipher = vigenere_encrypt(vplain, vkey)
    kasiski = kasiski_key_length(vcipher)
    friedman = friedman_key_length(vcipher)
    print(f"  plaintext (first 40): {vplain[:40]}")
    print(f"  key                 : {vkey} (length {len(vkey)})")
    print(f"  Kasiski guess       : {kasiski}")
    print(f"  Friedman guess      : {friedman}")
    recovered_key, recovered_text = vigenere_break(vcipher, key_length=len(vkey))
    print(f"  recovered key       : {recovered_key}")
    print(f"  recovered[:40]      : {recovered_text[:40]}")

    print("\n[4] Columnar transposition with key 'MEGABUCK'")
    plain = "pleasetransferonemilliondollarstomyswissbankaccountsixtwotwo"
    cipher = columnar_transposition_encrypt(plain, "MEGABUCK")
    back = columnar_transposition_decrypt(cipher, "MEGABUCK")
    print(f"  plaintext  : {plain}")
    print(f"  ciphertext : {cipher}")
    print(f"  round-trip : {back}")

    print("\n[5] One-time pad is Shannon-secure; key reuse is catastrophic")
    msg_a = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    msg_b = b"GET / HTTP/1.1\r\nHost: evil.com\r\n\r\n"
    key = secrets.token_bytes(max(len(msg_a), len(msg_b)))
    c_a = otp_encrypt(msg_a, key[:len(msg_a)])
    c_b = otp_encrypt(msg_b, key[:len(msg_b)])
    print(f"  c_a[:24] : {c_a[:24].hex()}")
    print(f"  c_b[:24] : {c_b[:24].hex()}")
    known_prefix = b"GET / HTTP/1.1\r\nHost: "
    leaked = key_reuse_attack(c_a, c_b, known_prefix)
    print(f"  recovered second Host via XOR+known-plain: {leaked.decode('latin1')}")


if __name__ == "__main__":
    main()
