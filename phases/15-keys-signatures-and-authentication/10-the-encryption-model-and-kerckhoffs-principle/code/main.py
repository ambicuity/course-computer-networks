"""The encryption model, key-space work factor, and Kerckhoffs's principle.

Five stdlib-only tools that make the principle tangible:

1. work_factor(k_bits, trials_per_sec) -> float years to brute-force a k-bit key.
2. caesar_encrypt / caesar_decrypt -> 25-shift circular cipher.
3. vigenere_encrypt / vigenere_decrypt -> repeating-key polyalphabetic cipher.
4. xor_stream(plaintext, key) -> the core OTP / stream-cipher primitive.
5. frequency_attack(ciphertext) -> ciphertext-only attack on monoalphabetic cipher
   using the English letter frequency distribution.

No third-party packages, no network access. Run: python3 main.py
"""

from __future__ import annotations

# English letter frequencies (e_t_a_o_i_n_s_h_r_d_l_c_u_m_w_f_g_y_p_b_v_k_j_x_q_z).
# From Peter Norvig's compilation of the Corpus of Contemporary American English.
ENGLISH_FREQ: dict[str, float] = {
    "a": 0.0817, "b": 0.0150, "c": 0.0278, "d": 0.0425, "e": 0.1270,
    "f": 0.0223, "g": 0.0202, "h": 0.0609, "i": 0.0697, "j": 0.0015,
    "k": 0.0077, "l": 0.0403, "m": 0.0241, "n": 0.0675, "o": 0.0751,
    "p": 0.0193, "q": 0.0010, "r": 0.0599, "s": 0.0633, "t": 0.0906,
    "u": 0.0276, "v": 0.0098, "w": 0.0236, "x": 0.0015, "y": 0.0197,
    "z": 0.0007,
}

SECONDS_PER_YEAR = 365.25 * 24 * 3600


def work_factor(k_bits: int, trials_per_sec: float = 1e9) -> float:
    """Return the expected years of brute-force search for a k-bit key.

    Average position of the key in a uniform search over `2^k` candidates
    is `2^k / 2`; divide by trials/sec and by seconds/year.
    """
    if k_bits < 0 or trials_per_sec <= 0:
        raise ValueError("k_bits >= 0 and trials_per_sec > 0")
    trials = (2 ** k_bits) / 2.0
    return trials / trials_per_sec / SECONDS_PER_YEAR


def caesar_encrypt(plaintext: str, shift: int) -> str:
    """Circular shift of letters A-Z (case-preserving); non-letters unchanged."""
    s = shift % 26
    out: list[str] = []
    for ch in plaintext:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - ord("a") + s) % 26 + ord("a")))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - ord("A") + s) % 26 + ord("A")))
        else:
            out.append(ch)
    return "".join(out)


def caesar_decrypt(ciphertext: str, shift: int) -> str:
    """Inverse Caesar: shift by -shift."""
    return caesar_encrypt(ciphertext, -shift)


def vigenere_encrypt(plaintext: str, key: str) -> str:
    """Vigenere: shift each letter by the corresponding key letter's value."""
    key_letters = [k for k in key.lower() if k.isalpha()]
    if not key_letters:
        raise ValueError("Vigenere key must contain at least one letter")
    shifts = [ord(k) - ord("a") for k in key_letters]
    out: list[str] = []
    j = 0
    for ch in plaintext:
        if ch.isalpha():
            base = ord("a") if ch.islower() else ord("A")
            out.append(chr((ord(ch) - base + shifts[j % len(shifts)]) % 26 + base))
            j += 1
        else:
            out.append(ch)
    return "".join(out)


def vigenere_decrypt(ciphertext: str, key: str) -> str:
    key_letters = [k for k in key.lower() if k.isalpha()]
    shifts = [ord(k) - ord("a") for k in key_letters]
    out: list[str] = []
    j = 0
    for ch in ciphertext:
        if ch.isalpha():
            base = ord("a") if ch.islower() else ord("A")
            out.append(chr((ord(ch) - base - shifts[j % len(shifts)]) % 26 + base))
            j += 1
        else:
            out.append(ch)
    return "".join(out)


def xor_stream(plaintext: bytes, key: bytes) -> bytes:
    """Repeating-key XOR. Used by OTP, PGP, and CTR mode block ciphers."""
    if not key:
        raise ValueError("key must be non-empty")
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(plaintext))


def frequency_attack(ciphertext: str) -> str:
    """Recover the most likely Caesar shift by matching letter frequencies.

    The chapter's classic ciphertext-only attack: count the frequency of each
    letter in the ciphertext, shift the alphabet so the most common letter
    maps to E (the most common English letter), and decrypt.
    """
    counts: dict[str, int] = {c: 0 for c in "abcdefghijklmnopqrstuvwxyz"}
    total = 0
    for ch in ciphertext.lower():
        if ch.isalpha():
            counts[ch] += 1
            total += 1
    if total == 0:
        return ciphertext
    most_common = max(counts, key=counts.get)  # type: ignore[arg-type]
    shift = (ord(most_common) - ord("e")) % 26
    return caesar_decrypt(ciphertext, shift)


def print_work_factor_table() -> None:
    print("=" * 70)
    print("KEY-LENGTH WORK FACTOR (expected years of brute-force search)")
    print("=" * 70)
    print(f"{'k bits':>7} | {'2^k':>22} | {'@ 10^6 k/s':>12} | {'@ 10^9 k/s':>12} | {'@ 10^12 k/s':>13}")
    print("-" * 70)
    for k in (32, 40, 56, 64, 80, 96, 112, 128, 192, 256):
        line = f"{k:>7} | {2 ** k:>22d} |"
        for rate in (1e6, 1e9, 1e12):
            years = work_factor(k, rate)
            if years < 1e-6:
                label = f"{years * 1e6:.3f} us"
            elif years < 1e-3:
                label = f"{years * 1e3:.3f} ms"
            elif years < 1:
                label = f"{years:.3f} s"
            elif years < 3600:
                label = f"{years / 60:.1f} min"
            elif years < 86400:
                label = f"{years / 3600:.1f} hr"
            elif years < 31.5e6:
                label = f"{years / 86400:.0f} days"
            elif years < 31.5e9:
                label = f"{years / 31.5e6:.1f} yr"
            else:
                label = f"{years:.2e} yr"
            line += f" {label:>12} |"
        print(line)


def demo_caesar() -> None:
    print("\n" + "=" * 70)
    print("CAESAR: 25 effective keys; one of them is the identity")
    print("=" * 70)
    msg = "attack at dawn"
    c = caesar_encrypt(msg, 3)
    print(f"plaintext  = {msg!r}")
    print(f"shift 3    = {c!r}")
    for shift in (0, 1, 13, 25):
        print(f"  shift {shift:>2} -> {caesar_encrypt(msg, shift)!r}")
    print(f"  brute force (decrypt with shift 3) = {caesar_decrypt(c, 3)!r}")


def demo_vigenere() -> None:
    print("\n" + "=" * 70)
    print("VIGENERE: key = 'LEMON' (5 bytes => 26^5 = 11.9M candidates)")
    print("=" * 70)
    msg = "the quick brown fox jumps over the lazy dog"
    key = "LEMON"
    c = vigenere_encrypt(msg, key)
    p = vigenere_decrypt(c, key)
    print(f"plaintext  = {msg!r}")
    print(f"key        = {key!r}")
    print(f"ciphertext = {c!r}")
    print(f"recovered  = {p!r}")
    print(f"match      = {p == msg}")


def demo_xor_stream() -> None:
    print("\n" + "=" * 70)
    print("XOR STREAM: 200-byte message with 4-byte key (effective key space = 2^32)")
    print("=" * 70)
    pt = b"the quick brown fox jumps over the lazy dog. " * 5
    pt = pt[:200]
    key = b"\xde\xad\xbe\xef"
    ct = xor_stream(pt, key)
    rt = xor_stream(ct, key)
    print(f"plaintext  ({len(pt)} B) = {pt[:40]!r}...")
    print(f"key        ({len(key)} B) = {key.hex()}")
    print(f"ciphertext ({len(ct)} B) = {ct[:40].hex()}...")
    print(f"recovered           = {rt[:40]!r}...")
    print(f"match               = {rt == pt}")


def demo_frequency_attack() -> None:
    print("\n" + "=" * 70)
    print("FREQUENCY ATTACK: ciphertext-only attack on a monoalphabetic cipher")
    print("=" * 70)
    msg = (
        "the quick brown fox jumps over the lazy dog. the rain in spain stays "
        "mainly in the plain. pack my box with five dozen liquor jugs. "
        "how vexingly quick daft zebras jump. " * 3
    )
    c = caesar_encrypt(msg, 7)
    p = frequency_attack(c)
    print(f"shift used in encryption: 7")
    print(f"first 80 chars of ciphertext: {c[:80]!r}")
    print(f"first 80 chars of recovered:  {p[:80]!r}")
    if p == msg:
        print("attack succeeded: recovered plaintext exactly")
    else:
        # Caesar is cyclic; the attack may find any rotation of the answer.
        for s in range(26):
            if caesar_encrypt(p, s) == msg:
                print(f"recovered plaintext at shift {s} (cyclic offset)")
                break


def main() -> None:
    print_work_factor_table()
    demo_caesar()
    demo_vigenere()
    demo_xor_stream()
    demo_frequency_attack()
    print("\n" + "=" * 70)
    print("KERCKHOFFS CHECKLIST (a cipher must satisfy ALL)")
    print("=" * 70)
    checklist = [
        "1. The algorithm is fully public and documented",
        "2. The only secret is the key",
        "3. The key space is large enough (>= 128 bits for symmetric)",
        "4. The algorithm has survived >= 5 years of public review",
        "5. Known-plaintext and chosen-plaintext attacks are infeasible",
    ]
    for line in checklist:
        print(line)


if __name__ == "__main__":
    main()
