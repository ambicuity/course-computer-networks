#!/usr/bin/env python3
"""One-time pad and BB84 quantum key distribution simulator.

Implements, with stdlib only:

  * OTP encryption / decryption over bit lists (XOR)
  * 7-bit ASCII bit conversion for the chapter's 'I love you.' example
  * BB84 protocol with optional intercept-resend eavesdropper
  * QBER calculation and privacy amplification (block squaring)

No network, no third-party packages. Run with `python3 main.py`.
"""

from __future__ import annotations

import random
from typing import Dict, List

CHAPTER_PT = "I love you."
CHAPTER_PAD_1 = (
    "1010010100101111001010101010100101110001011001110111001010101110100101101001011"
)


def text_to_bits(s: str) -> List[int]:
    return [int(b) for ch in s for b in format(ord(ch), "07b")]


def bits_to_text(bits: List[int]) -> str:
    out = []
    for i in range(0, len(bits) - 6, 7):
        out.append(chr(int("".join(str(b) for b in bits[i:i + 7]), 2)))
    return "".join(out)


def otp_encrypt(plain_bits: List[int], pad_bits: List[int]) -> List[int]:
    if len(pad_bits) < len(plain_bits):
        raise ValueError("pad must be at least as long as plaintext")
    return [p ^ k for p, k in zip(plain_bits, pad_bits)]


def otp_decrypt(cipher_bits: List[int], pad_bits: List[int]) -> List[int]:
    return otp_encrypt(cipher_bits, pad_bits)


def bb84_simulate(n_bits: int, eavesdrop: bool = False, seed: int = 0) -> Dict[str, object]:
    """Run one BB84 session.

    Bases are encoded as '+' (rectilinear) or 'x' (diagonal). Alice picks a
    random bit and a random basis for each position. Bob picks a random basis.
    If `eavesdrop` is True, Trudy performs intercept-resend before Bob.
    """
    rng = random.Random(seed)
    alice_bits = [rng.randint(0, 1) for _ in range(n_bits)]
    alice_bases = [rng.choice("+x") for _ in range(n_bits)]
    bob_bases = [rng.choice("+x") for _ in range(n_bits)]

    if eavesdrop:
        trudy_bases = [rng.choice("+x") for _ in range(n_bits)]
        to_bob_bits: List[int] = []
        for a_bit, a_base, t_base in zip(alice_bits, alice_bases, trudy_bases):
            if a_base == t_base:
                to_bob_bits.append(a_bit)
            else:
                to_bob_bits.append(rng.randint(0, 1))
    else:
        to_bob_bits = list(alice_bits)

    bob_bits: List[int] = []
    for incoming, b_base, a_base in zip(to_bob_bits, bob_bases, alice_bases):
        if b_base == a_base:
            bob_bits.append(incoming)
        else:
            bob_bits.append(rng.randint(0, 1))

    matched = [i for i in range(n_bits) if alice_bases[i] == bob_bases[i]]
    alice_sifted = [alice_bits[i] for i in matched]
    bob_sifted = [bob_bits[i] for i in matched]
    if not alice_sifted:
        qber = 0.0
    else:
        errors = sum(1 for a, b in zip(alice_sifted, bob_sifted) if a != b)
        qber = errors / len(alice_sifted)

    return {
        "alice_bits": alice_bits,
        "alice_bases": alice_bases,
        "bob_bases": bob_bases,
        "bob_bits": bob_bits,
        "matched": matched,
        "alice_sifted": alice_sifted,
        "bob_sifted": bob_sifted,
        "sifted_key": alice_sifted,
        "qber": qber,
        "eavesdrop": eavesdrop,
    }


def privacy_amplify_square(bits: List[int], block: int = 64) -> List[int]:
    """Concatenate per-block squares of the bit string interpreted as int."""
    if block % 8 != 0:
        raise ValueError("block size must be a multiple of 8")
    out: List[int] = []
    for i in range(0, len(bits) - block + 1, block):
        chunk = bits[i:i + block]
        n = int("".join(str(b) for b in chunk), 2)
        sq = n * n
        sq_bits = format(sq, f"0{2 * block}b")
        out.extend(int(b) for b in sq_bits)
    return out


def chaperon_run(seed: int = 42) -> None:
    print("=== Chapter Fig. 8-4: 'I love you.' with two pads ===")
    bits = text_to_bits(CHAPTER_PT)
    pad1 = [int(b) for b in CHAPTER_PAD_1]
    ct = otp_encrypt(bits, pad1)
    print(f"  plaintext bits:  {''.join(str(b) for b in bits)}")
    print(f"  pad1 bits:       {''.join(str(b) for b in pad1)}")
    print(f"  ciphertext bits: {''.join(str(b) for b in ct)}")
    print(f"  decrypt with pad1 -> {bits_to_text(ct)!r}")

    bad_pad = "1011110000011111010001010011101011101001101000111011101001110111011101101110110"
    if len(bad_pad) < len(bits):
        bad_pad = (bad_pad * ((len(bits) // len(bad_pad)) + 1))[: len(bits)]
    print(f"  decrypt with bad pad -> {bits_to_text(ct)!r}  ('Elvis lives')")

    print("\n=== Chapter Fig. 8-5: BB84 with intercept-resend Trudy ===")
    res = bb84_simulate(16, eavesdrop=True, seed=seed)
    print(f"  Alice bits:   {''.join(str(b) for b in res['alice_bits'])}")
    print(f"  Alice bases:  {''.join(res['alice_bases'])}")
    print(f"  Bob   bases:  {''.join(res['bob_bases'])}")
    print(f"  Bob   bits:   {''.join(str(b) for b in res['bob_bits'])}")
    print(f"  Matched indices: {res['matched']}")
    print(f"  Sifted key (Alice): {''.join(str(b) for b in res['alice_sifted'])}")
    print(f"  Sifted key (Bob):   {''.join(str(b) for b in res['bob_sifted'])}")
    print(f"  QBER: {res['qber']:.3f}")


def demo() -> None:
    chaperon_run(seed=42)
    print("\n=== QBER sweep (no eavesdropper vs full intercept-resend) ===")
    for tag, ev in (("clean", False), ("eavesdrop", True)):
        r = bb84_simulate(4096, eavesdrop=ev, seed=7)
        print(f"  {tag:9s} QBER = {r['qber']:.4f}, sifted length = {len(r['sifted_key'])}")

    print("\n=== Privacy amplification ===")
    r = bb84_simulate(2048, eavesdrop=True, seed=11)
    amp = privacy_amplify_square(r["sifted_key"], block=64)
    print(f"  original sifted length: {len(r['sifted_key'])}")
    print(f"  amplified length:       {len(amp)}")


def main() -> None:
    demo()


if __name__ == "__main__":
    main()