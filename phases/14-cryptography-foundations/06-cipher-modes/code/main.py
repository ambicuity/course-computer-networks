"""Cipher Modes — stdlib-only demonstration of ECB, CBC, CTR, OFB and the
attacks that motivate authenticated modes.

Uses a toy 16-bit block cipher built from a *full* 256-entry permutation S-box
so every mode's chaining, IV, and error-propagation behavior is observable in
printed output without any cryptography library. The lessons map 1:1 to real
AES: ECB leaks identical blocks, CBC garbles-on-swap, CTR allows random access
and is fatal on (key,IV) reuse, OFB is a keystream generator, GCM is CTR + tag.

Run:  python3 main.py    Exit: 0. No pip deps.
"""
from __future__ import annotations

from dataclasses import dataclass

BLOCK_BITS = 16
BLOCK_MASK = (1 << BLOCK_BITS) - 1

# A full 256-entry permutation (AES S-box) so toy_encrypt is a bijection on
# each byte and therefore on the 16-bit block.
SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
INV_SBOX = [0] * 256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i


def _rotl(x: int, r: int, bits: int = BLOCK_BITS) -> int:
    return ((x << r) | (x >> (bits - r))) & BLOCK_MASK


def toy_encrypt(key: int, block: int) -> int:
    """Deterministic 16-bit permutation keyed by `key` (NOT secure; for demos)."""
    x = (block ^ key) & BLOCK_MASK
    lo = x & 0xFF
    hi = (x >> 8) & 0xFF
    lo = SBOX[lo]
    hi = SBOX[(hi + 13) & 0xFF]
    x = ((hi << 8) | lo) & BLOCK_MASK
    x = _rotl(x, 3)
    x = (x * 0x9E37 + key) & BLOCK_MASK
    return x


def toy_decrypt(key: int, block: int) -> int:
    x = block
    inv = pow(0x9E37, -1, 1 << BLOCK_BITS)
    x = (x - key) & BLOCK_MASK
    x = (x * inv) & BLOCK_MASK
    x = ((x >> 3) | (x << 13)) & BLOCK_MASK  # rotate right 3
    hi = (x >> 8) & 0xFF
    lo = x & 0xFF
    hi = INV_SBOX[(hi - 13) & 0xFF]
    lo = INV_SBOX[lo]
    x = ((hi << 8) | lo) & BLOCK_MASK
    x = (x ^ key) & BLOCK_MASK
    return x


def xor(a: int, b: int) -> int:
    return (a ^ b) & BLOCK_MASK


def ecb_encrypt(key: int, blocks: list[int]) -> list[int]:
    return [toy_encrypt(key, b) for b in blocks]


def ecb_decrypt(key: int, blocks: list[int]) -> list[int]:
    return [toy_decrypt(key, b) for b in blocks]


def cbc_encrypt(key: int, iv: int, blocks: list[int]) -> list[int]:
    out: list[int] = []
    prev = iv
    for b in blocks:
        c = toy_encrypt(key, xor(b, prev))
        out.append(c)
        prev = c
    return out


def cbc_decrypt(key: int, iv: int, blocks: list[int]) -> list[int]:
    out: list[int] = []
    prev = iv
    for c in blocks:
        out.append(xor(toy_decrypt(key, c), prev))
        prev = c
    return out


def ctr_stream(key: int, iv: int, n: int) -> list[int]:
    return [toy_encrypt(key, (iv + i) & BLOCK_MASK) for i in range(n)]


def ctr_encrypt(key: int, iv: int, blocks: list[int]) -> list[int]:
    ks = ctr_stream(key, iv, len(blocks))
    return [xor(b, k) for b, k in zip(blocks, ks)]


def ofb_keystream(key: int, iv: int, n: int) -> list[int]:
    out: list[int] = []
    state = iv
    for _ in range(n):
        state = toy_encrypt(key, state)
        out.append(state)
    return out


def ofb_encrypt(key: int, iv: int, blocks: list[int]) -> list[int]:
    ks = ofb_keystream(key, iv, len(blocks))
    return [xor(b, k) for b, k in zip(blocks, ks)]


def hex4(n: int) -> str:
    return f"{n & BLOCK_MASK:04x}"


def show(title: str, blocks: list[int]) -> None:
    print(f"  {title:30s}: {' '.join(hex4(b) for b in blocks)}")


@dataclass
class Demo:
    name: str
    run: callable


def demo_ecb_identical_blocks() -> None:
    print("\n[1] ECB leaks identical plaintext blocks")
    key = 0x1234
    pt = [0xAABB, 0xAABB, 0x1234, 0xAABB]
    ct = ecb_encrypt(key, pt)
    show("plaintext", pt)
    show("ECB ciphertext", ct)
    identical_ct = all(ct[i] == ct[0] for i in (1, 3))
    print(f"  blocks 1 and 3 share CT {hex4(ct[0])}: identical-PT->identical-CT = {identical_ct}")


def demo_ecb_block_reorder() -> None:
    print("\n[2] ECB block-reorder attack (Leslie swaps Kim's bonus)")
    key = 0x4321
    pt = [0x4C65, 0x0BEE, 0x4B69, 0x0100]  # block 3 = Leslie's bonus 0x0100
    ct = ecb_encrypt(key, pt)
    tampered = ct[:3] + [ct[1]]            # copy Kim's block over Leslie's
    recovered = ecb_decrypt(key, tampered)
    show("original plaintext", pt)
    show("attacker's ciphertext", tampered)
    show("bank decrypts to", recovered)
    print(f"  Leslie's bonus is now {hex4(recovered[3])} = Kim's 0x0BEE -> attack succeeds without the key")


def demo_cbc_swap_garbles() -> None:
    print("\n[3] CBC: swapping a ciphertext block garbles that block AND the next")
    key = 0xBEEF
    iv = 0x55AA
    pt = [0x1111, 0x2222, 0x3333, 0x4444]
    ct = cbc_encrypt(key, iv, pt)
    swapped = ct[:1] + [ct[2], ct[1]] + ct[3:]
    recovered = cbc_decrypt(key, iv, swapped)
    show("ciphertext (correct)", ct)
    show("ciphertext (swapped 1<->2)", swapped)
    show("decrypted from swapped", recovered)
    garbled = (recovered[1] != pt[1]) and (recovered[2] != pt[2])
    print(f"  block 1 and 2 garbage -> tamper detected, not silent: {garbled}")


def demo_ctr_random_access() -> None:
    print("\n[4] CTR: random-access decryption of a single block")
    key = 0xCAFE
    iv = 0x0007
    pt = [0xDEAD, 0xBEEF, 0xF00D, 0x1234]
    ct = ctr_encrypt(key, iv, pt)
    ks2 = toy_encrypt(key, (iv + 2) & BLOCK_MASK)
    block2 = xor(ct[2], ks2)
    show("ciphertext", ct)
    show("block 2 decrypted alone", [block2])
    print(f"  matches original block 2: {block2 == pt[2]}  (CTR needs no predecessor blocks)")


def demo_ctr_iv_reuse() -> None:
    print("\n[5] CTR (key,IV) reuse -> two-time-pad leak")
    key = 0x1010
    iv = 0x0001
    msg_a = [0x4849, 0x4A4B]
    msg_b = [0x5354, 0x5556]
    ca = ctr_encrypt(key, iv, msg_a)
    cb = ctr_encrypt(key, iv, msg_b)
    diff = [xor(x, y) for x, y in zip(ca, cb)]
    show("ciphertext A", ca)
    show("ciphertext B", cb)
    show("A xor B (= PT_A xor PT_B)", diff)
    print("  keystream cancelled -> attacker learns relation of the two plaintexts")


def demo_ofb_error_propagation() -> None:
    print("\n[6] OFB: 1-bit ciphertext error -> 1-bit plaintext error (no garble)")
    key = 0x0F0F
    iv = 0x7070
    pt = [0xAAAA, 0xBBBB, 0xCCCC]
    ct = ofb_encrypt(key, iv, pt)
    flipped = ct[:1] + [ct[1] ^ 0x0001] + ct[2:]
    ks = ofb_keystream(key, iv, len(pt))
    recovered = [xor(c, k) for c, k in zip(flipped, ks)]
    show("ciphertext (1 bit flipped)", flipped)
    show("decrypted", recovered)
    only_one = (recovered[0] == pt[0]) and (recovered[1] == xor(pt[1], 0x0001)) and (recovered[2] == pt[2])
    print(f"  only block 1 differs by the flipped bit; later blocks unaffected: {only_one}")


def demo_gcm_is_ctr_plus_tag() -> None:
    print("\n[7] GCM = CTR encryption + an authentication tag (conceptual)")
    key = 0x9999
    iv = 0x0404
    pt = [0x0A0B, 0x0C0D, 0x0E0F]
    ct = ctr_encrypt(key, iv, pt)
    tag = 0
    for c in ct:
        tag = ((tag << 1) ^ (c * 0x100)) & BLOCK_MASK
    show("plaintext", pt)
    show("GCM ciphertext (= CTR)", ct)
    print(f"  authentication tag     : {hex4(tag)}")
    tampered = ct[:1] + [ct[1] ^ 0x0001] + ct[2:]
    new_tag = 0
    for c in tampered:
        new_tag = ((new_tag << 1) ^ (c * 0x100)) & BLOCK_MASK
    print(f"  tag after 1-bit tamper  : {hex4(new_tag)}  -> {'REJECTED' if new_tag != tag else 'accepted'}")


DEMOS = [
    Demo("ECB identical-block leak", demo_ecb_identical_blocks),
    Demo("ECB block-reorder attack", demo_ecb_block_reorder),
    Demo("CBC swap garbles two blocks", demo_cbc_swap_garbles),
    Demo("CTR random-access decrypt", demo_ctr_random_access),
    Demo("CTR (key,IV) reuse two-time-pad", demo_ctr_iv_reuse),
    Demo("OFB 1-bit error propagation", demo_ofb_error_propagation),
    Demo("GCM = CTR + tag", demo_gcm_is_ctr_plus_tag),
]


def main() -> None:
    print("=" * 64)
    print("CIPHER MODES  --  ECB / CBC / CTR / OFB / GCM (toy 16-bit blocks)")
    print("=" * 64)
    print(f"block size: {BLOCK_BITS} bits  |  one key per scenario  |  no pip deps")
    for d in DEMOS:
        d.run()
    print("\nRule: never use ECB for multi-block data; prefer an authenticated")
    print("mode (GCM, or CBC+HMAC) so tampering is detected, not silent.")
    print("Exit 0.")


if __name__ == "__main__":
    main()
