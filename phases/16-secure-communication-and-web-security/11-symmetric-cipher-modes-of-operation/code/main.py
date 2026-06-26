"""Symmetric block cipher modes of operation: ECB, CBC, CFB, CTR.

Educational stdlib-only implementation that exercises a toy 16-byte Feistel
block cipher, demonstrates why ECB is dangerous (cut-and-paste), shows CBC
defeating the cut-and-paste, and runs a two-time-pad demonstration on CTR.

Run: python3 code/main.py
"""

from __future__ import annotations

import os
import struct
from typing import Callable, List


# ---------------------------------------------------------------------------
# Toy 16-byte block cipher (two-round Feistel; NOT cryptographically secure).
# The cipher takes a 16-byte block and a 16-byte key and returns 16 bytes.
# ---------------------------------------------------------------------------

def _round_function(block: bytes, key: bytes) -> bytes:
    """Half-block Feistel round: XOR with a key-derived byte stream."""
    out = bytearray(len(block))
    for i, b in enumerate(block):
        k = key[i % len(key)]
        # Mix: multiply by an odd constant in GF(2^8), then XOR with key.
        mixed = ((b * 0x1B) ^ k ^ ((i * 17) & 0xFF)) & 0xFF
        out[i] = mixed
    return bytes(out)


def toy_cipher(block: bytes, key: bytes) -> bytes:
    """Two-round Feistel with a half-block round function."""
    if len(block) != 16 or len(key) != 16:
        raise ValueError("toy_cipher requires 16-byte block and key")
    L, R = block[:8], block[8:]
    for _ in range(2):
        L, R = R, bytes(a ^ b for a, b in zip(L, _round_function(R, key)))
    return L + R


def toy_cipher_inverse(block: bytes, key: bytes) -> bytes:
    """Inverse of toy_cipher (Feistel is invertible by reversing rounds)."""
    if len(block) != 16 or len(key) != 16:
        raise ValueError("toy_cipher_inverse requires 16-byte block and key")
    L, R = block[:8], block[8:]
    for _ in range(2):
        L, R = bytes(a ^ b for a, b in zip(R, _round_function(L, key))), L
    return L + R


# ---------------------------------------------------------------------------
# PKCS#7 padding helpers.
# ---------------------------------------------------------------------------

def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad = block_size - (len(data) % block_size)
    return data + bytes([pad]) * pad


def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("padded data length must be a positive multiple of block")
    pad = data[-1]
    if pad < 1 or pad > block_size or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-pad]


# ---------------------------------------------------------------------------
# XOR helper for stream-cipher modes.
# ---------------------------------------------------------------------------

def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _split_blocks(data: bytes, block_size: int = 16) -> List[bytes]:
    return [data[i:i + block_size] for i in range(0, len(data), block_size)]


# ---------------------------------------------------------------------------
# ECB mode: deterministic, pattern-preserving. The dangerous one.
# ---------------------------------------------------------------------------

def ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    pt = pkcs7_pad(plaintext)
    return b"".join(toy_cipher(p, key) for p in _split_blocks(pt))


def ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) % 16 != 0:
        raise ValueError("ciphertext length must be a multiple of 16")
    pt = b"".join(toy_cipher_inverse(c, key) for c in _split_blocks(ciphertext))
    return pkcs7_unpad(pt)


# ---------------------------------------------------------------------------
# CBC mode: chained XOR defeats cut-and-paste.
# ---------------------------------------------------------------------------

def cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    if len(iv) != 16:
        raise ValueError("IV must be 16 bytes")
    pt = pkcs7_pad(plaintext)
    out = bytearray()
    prev = iv
    for p in _split_blocks(pt):
        x = _xor(p, prev)
        c = toy_cipher(x, key)
        out.extend(c)
        prev = c
    return bytes(out)


def cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    if len(iv) != 16 or len(ciphertext) % 16 != 0:
        raise ValueError("bad IV or ciphertext length")
    out = bytearray()
    prev = iv
    for c in _split_blocks(ciphertext):
        x = toy_cipher_inverse(c, key)
        out.extend(_xor(x, prev))
        prev = c
    return pkcs7_unpad(bytes(out))


# ---------------------------------------------------------------------------
# CFB mode (8-bit feedback): self-synchronizing stream cipher.
# ---------------------------------------------------------------------------

def cfb_encrypt(plaintext: bytes, key: bytes, iv: bytes, segment: int = 8) -> bytes:
    if len(iv) != 16 or segment not in (8, 16, 32, 64, 128):
        raise ValueError("CFB: bad IV or segment size")
    shift = bytearray(iv)
    out = bytearray()
    i = 0
    while i < len(plaintext):
        ks = toy_cipher(bytes(shift), key)
        chunk = plaintext[i:i + segment]
        ct_chunk = bytes(ks[j] ^ chunk[j] for j in range(len(chunk)))
        out.extend(ct_chunk)
        shift = bytearray(shift[len(ct_chunk):]) + bytearray(ct_chunk)
        i += segment
    return bytes(out)


def cfb_decrypt(ciphertext: bytes, key: bytes, iv: bytes, segment: int = 8) -> bytes:
    if len(iv) != 16 or segment not in (8, 16, 32, 64, 128):
        raise ValueError("CFB: bad IV or segment size")
    shift = bytearray(iv)
    out = bytearray()
    i = 0
    while i < len(ciphertext):
        ks = toy_cipher(bytes(shift), key)
        chunk = ciphertext[i:i + segment]
        pt_chunk = bytes(ks[j] ^ chunk[j] for j in range(len(chunk)))
        out.extend(pt_chunk)
        shift = bytearray(shift[len(chunk):]) + bytearray(chunk)
        i += segment
    return bytes(out)


# ---------------------------------------------------------------------------
# CTR mode: counter keystream, parallelizable, foundation of AES-GCM.
# ---------------------------------------------------------------------------

def _ctr_block(nonce: bytes, counter: int) -> bytes:
    """Pack a 12-byte nonce and 4-byte counter into a 16-byte input block."""
    if len(nonce) != 12:
        raise ValueError("CTR nonce must be 12 bytes")
    return nonce + struct.pack(">I", counter)


def ctr_encrypt(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    for i, p in enumerate(_split_blocks(plaintext, 16)):
        ks = toy_cipher(_ctr_block(nonce, i), key)
        out.extend(_xor(p, ks))
    return bytes(out)


def ctr_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    return ctr_encrypt(ciphertext, key, nonce)  # CTR is symmetric.


# ---------------------------------------------------------------------------
# Demonstrations and attacks.
# ---------------------------------------------------------------------------

def cut_and_paste(ciphertext: bytes, src_block: int, dst_block: int) -> bytes:
    """Swap one ECB-encrypted block for another. Works because ECB preserves
    block identity and is malleable."""
    blocks = _split_blocks(ciphertext, 16)
    if not (0 <= src_block < len(blocks) and 0 <= dst_block < len(blocks)):
        raise ValueError("block index out of range")
    blocks[dst_block] = blocks[src_block]
    return b"".join(blocks)


def keystream_recover(ciphertext1: bytes, ciphertext2: bytes) -> bytes:
    """Given two ciphertexts encrypted with the same CTR keystream, the XOR of
    the two ciphertexts equals the XOR of the two plaintexts (two-time pad)."""
    n = min(len(ciphertext1), len(ciphertext2))
    return _xor(ciphertext1[:n], ciphertext2[:n])


# ---------------------------------------------------------------------------
# Demo / output driver.
# ---------------------------------------------------------------------------

def _bonus_record(name: str, position: str, bonus: int) -> bytes:
    name_f = name.ljust(16)[:16].encode()
    pos_f = position.ljust(8)[:8].encode()
    return name_f + pos_f + f"${bonus}".rjust(8).encode()


def main() -> None:
    os.makedirs("outputs", exist_ok=True)
    key = bytes(range(16))  # deterministic toy key.
    iv = bytes((i * 7) & 0xFF for i in range(16))

    # Tiny payroll file: 4 records, each exactly 32 bytes (2 blocks).
    file_plaintext = b"".join([
        _bonus_record("Adams, Leslie", "Clerk", 10),
        _bonus_record("Black, Robin", "Boss", 500000),
        _bonus_record("Collins, Kim", "Manager", 100000),
        _bonus_record("Davis, Bobbie", "Janitor", 5),
    ])
    assert len(file_plaintext) == 32 * 4

    # --- ECB: cut-and-paste attack ---------------------------------------------
    ecb_ct = ecb_encrypt(file_plaintext, key)
    swapped = cut_and_paste(ecb_ct, src_block=4, dst_block=0)
    # src block 4 is Kim's bonus ($100,000) — copy it into Leslie's first block.
    decrypted_swapped = ecb_decrypt(swapped, key)

    # --- CBC: same swap, but the file corrupts at the insertion point --------
    cbc_ct = cbc_encrypt(file_plaintext, key, iv)
    cbc_blocks = _split_blocks(cbc_ct, 16)
    cbc_blocks[0] = cbc_blocks[4]  # attempt the same cut-and-paste
    cbc_swapped = b"".join(cbc_blocks)
    cbc_decrypted = cbc_decrypt(cbc_swapped, key, iv)

    # --- CTR two-time-pad -----------------------------------------------------
    msg1 = b"Transfer $100 to account 1234."
    msg2 = b"Transfer $999 to account 5678."
    nonce = b"\x00" * 12
    ct1 = ctr_encrypt(msg1, key, nonce)
    ct2 = ctr_encrypt(msg2, key, nonce)
    recovered = keystream_recover(ct1, ct2)

    print("=== Symmetric Cipher Modes of Operation ===")
    print(f"ECB ciphertext blocks: {[b.hex() for b in _split_blocks(ecb_ct)]}")
    print(f"After cut-and-paste, decrypted record 0:")
    print(f"  {decrypted_swapped[:32]!r}")
    print()
    print(f"CBC ciphertext blocks: {[b.hex() for b in _split_blocks(cbc_ct)]}")
    print(f"After cut-and-paste, CBC plaintext (note garbage at block 0):")
    print(f"  {cbc_decrypted!r}")
    print()
    print(f"CTR two-time-pad recovered XOR ({len(recovered)} bytes):")
    print(f"  {recovered.hex()}")
    print(f"  (Should equal msg1 XOR msg2: {_xor(msg1, msg2).hex()})")
    # Sanity: assert the recovered XOR matches (msg1 XOR msg2) up to common length.
    expected = _xor(msg1, msg2)
    assert recovered == expected, "CTR two-time-pad recovery is wrong"

    with open("outputs/bonus_ecb.txt", "wb") as f:
        f.write(b"ECB encrypted payroll (cut-and-paste applied):\n")
        f.write(swapped)
    with open("outputs/bonus_cbc.txt", "wb") as f:
        f.write(b"CBC encrypted payroll (cut-and-paste attempted):\n")
        f.write(cbc_swapped)
    with open("outputs/keystream_reuse.txt", "wb") as f:
        f.write(b"msg1: " + msg1 + b"\n")
        f.write(b"msg2: " + msg2 + b"\n")
        f.write(b"recovered msg1 XOR msg2: " + recovered + b"\n")
    print("\nWrote outputs/bonus_ecb.txt, outputs/bonus_cbc.txt, outputs/keystream_reuse.txt")


if __name__ == "__main__":
    main()
