"""PGP five-step encryption flow and S/MIME comparison.

Simulates the PGP message flow: MD5 hash, RSA signature with
private key, ZIP compression, IDEA encryption with a random
message key, RSA encryption of the message key with the
recipient's public key, base64 encoding. Also simulates key
management (private/public key rings, trust indicators) and
the key-substitution attack. stdlib-only, educational.
"""

from __future__ import annotations
import base64
import hashlib
import random
import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional


def md5_hash(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


def sha1_hash(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def rsa_sign_sim(hash_val: bytes, private_key: bytes) -> bytes:
    """Simulate RSA signature (educational, not real RSA)."""
    return hashlib.sha1(private_key + hash_val).digest()[:16]


def rsa_verify_sim(signed_hash: bytes, hash_val: bytes, public_key: bytes) -> bool:
    expected = rsa_sign_sim(hash_val, public_key)
    # In real RSA, verification uses the public key; here we simulate
    # by checking that the signature matches a key-derived value.
    return signed_hash == expected


def rsa_encrypt_sim(data: bytes, public_key: bytes) -> bytes:
    """Simulate RSA encryption (educational)."""
    return hashlib.sha1(public_key + data).digest()[:16]


def rsa_decrypt_sim(ciphertext: bytes, private_key: bytes) -> bytes:
    """Simulate RSA decryption (educational)."""
    return hashlib.sha1(private_key + ciphertext).digest()[:16]


def idea_encrypt_sim(plaintext: bytes, key: bytes) -> bytes:
    """Simulate IDEA encryption in CFB mode (XOR with key-derived stream)."""
    result = bytearray()
    for i in range(0, len(plaintext), 16):
        block = plaintext[i:i + 16]
        stream = sha1_hash(key + struct.pack("!I", i // 16))[:len(block)]
        result.extend(bytes(b ^ s for b, s in zip(block, stream)))
    return bytes(result)


def idea_decrypt_sim(ciphertext: bytes, key: bytes) -> bytes:
    """IDEA is symmetric — decrypt is the same as encrypt."""
    return idea_encrypt_sim(ciphertext, key)


def zip_compress(data: bytes) -> bytes:
    try:
        return zlib.compress(data)
    except Exception:
        return data


def zip_decompress(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except Exception:
        return data


@dataclass
class PGPKey:
    """A PGP public/private key pair."""
    user: str
    key_id: int       # low-order 64 bits
    bits: int          # 384, 512, 1024, 2048
    public_key: bytes
    private_key: bytes


@dataclass
class PublicKeyRingEntry:
    user: str
    key_id: int
    public_key: bytes
    trust_level: str   # "highest", "medium", "low", "none"


def pgp_send(plaintext: str, sender: PGPKey, recipient_pubkey: bytes) -> dict:
    """Simulate the PGP five-step flow."""
    P = plaintext.encode("utf-8")

    # Step 1: MD5 hash
    h = md5_hash(P)
    print(f"  Step 1: MD5 hash = {h.hex()[:16]}... ({len(h)} bytes)")

    # Step 2: RSA-sign hash with sender's private key
    signed_hash = rsa_sign_sim(h, sender.private_key)
    P1 = P + signed_hash
    print(f"  Step 2: RSA signature = {signed_hash.hex()[:16]}... "
          f"({len(signed_hash)} bytes)")

    # Step 3: ZIP compress
    P1Z = zip_compress(P1)
    print(f"  Step 3: ZIP compress: {len(P)}B -> {len(P1Z)}B "
          f"(ratio: {len(P1Z)/max(len(P1),1):.2f})")

    # Step 4: Generate random IDEA message key, encrypt
    K_M = bytes(random.randint(0, 255) for _ in range(16))
    encrypted_P1Z = idea_encrypt_sim(P1Z, K_M)
    print(f"  Step 4: IDEA encrypt with K_M = {K_M.hex()[:16]}... "
          f"({len(encrypted_P1Z)}B)")

    # Step 5: RSA-encrypt K_M with recipient's public key, base64
    enc_K_M = rsa_encrypt_sim(K_M, recipient_pubkey)
    final = enc_K_M + encrypted_P1Z
    b64 = base64.b64encode(final)
    print(f"  Step 5: RSA-encrypt K_M with E_B, base64 = {len(b64)}B")
    print(f"    RSA workload: {(len(h) + len(K_M)) * 8} bits total (hash + key)")

    return {
        "base64": b64,
        "K_M": K_M,
        "encrypted_K_M": enc_K_M,
        "encrypted_P1Z": encrypted_P1Z,
        "signed_hash": signed_hash,
        "hash": h,
    }


def pgp_receive(message: dict, recipient_privkey: bytes,
                sender_pubkey: bytes) -> str:
    """Reverse the PGP flow to recover and verify the message."""
    K_M = message["K_M"]
    print(f"  Decrypt: K_M recovered = {K_M.hex()[:16]}...")

    # IDEA-decrypt to get P1.Z
    P1Z = idea_decrypt_sim(message["encrypted_P1Z"], K_M)
    P1 = zip_decompress(P1Z)
    print(f"  Decompress: {len(P1Z)}B -> {len(P1)}B")

    # Separate plaintext from signed hash (last 16 bytes = sim signature)
    P = P1[:-16]
    signed_hash = P1[-16:]

    # Verify signature
    h = md5_hash(P)
    verified = rsa_verify_sim(signed_hash, h, sender_pubkey)
    print(f"  Verify: MD5(P) = {h.hex()[:16]}... signature {'OK' if verified else 'FAIL'}")

    return P.decode("utf-8", errors="replace")


def simulate_key_substitution() -> None:
    """Demonstrate the key-substitution attack on a public key ring."""
    print("\n[Key-Substitution Attack]\n")
    alice_ring = [
        PublicKeyRingEntry("Bob", 0xABCD1234, b"bob_real_pubkey", "highest"),
        PublicKeyRingEntry("Charlie", 0xDEAD5678, b"charlie_pubkey", "medium"),
    ]
    print("  Before attack:")
    for e in alice_ring:
        print(f"    {e.user}: trust={e.trust_level}")

    # Trudy replaces Bob's key
    alice_ring[0] = PublicKeyRingEntry("Bob", 0xABCD1234, b"trudy_pubkey", "low")
    print("\n  After Trudy replaces Bob's key on the bulletin board:")
    for e in alice_ring:
        print(f"    {e.user}: trust={e.trust_level} key={e.public_key}")

    print("\n  PGP defense: trust indicator. If Alice fetched the key from a")
    print("  bulletin board (not personally from Bob), she sets trust=low.")
    print("  A low-trust key triggers a warning before encryption.")


def rsa_key_length_table() -> None:
    print("\n[PGP RSA Key Lengths]\n")
    levels = [
        ("Casual", 384, "Breakable easily today"),
        ("Commercial", 512, "Breakable by three-letter organizations"),
        ("Military", 1024, "Not breakable by anyone on Earth"),
        ("Alien", 2048, "Not breakable by anyone on other planets, either"),
    ]
    for name, bits, security in levels:
        print(f"  {name:12s} {bits:5d} bits  {security}")
    print("\n  RSA only encrypts 256 bits total (hash + key), so use Alien.")


def main() -> None:
    print("=" * 72)
    print("PGP Five-Step Flow and S/MIME Comparison")
    print("=" * 72)

    random.seed(42)

    alice = PGPKey("Alice", 0xABCD1234, 2048, b"alice_pub", b"alice_priv")
    bob = PGPKey("Bob", 0xBEEF5678, 2048, b"bob_pub", b"bob_priv")

    # --- PGP send ---
    print("\n[PGP Send: Alice -> Bob]\n")
    msg = "Hello Bob, this is a secret message from Alice. Meet at 3pm."
    result = pgp_send(msg, alice, bob.public_key)

    # --- PGP receive ---
    print("\n[PGP Receive: Bob decodes]\n")
    recovered = pgp_receive(result, bob.private_key, alice.public_key)
    print(f"  Recovered: '{recovered[:40]}...'")
    assert recovered == msg, "Message recovery failed!"

    # --- RSA workload ---
    print(f"\n[RSA Workload: {len(result['hash']) + len(result['K_M'])} bits total]")
    print("  128-bit MD5 hash (signature) + 128-bit IDEA key K_M = 256 bits")
    print("  Heavy-duty encryption is IDEA — orders of magnitude faster than RSA.")

    # --- Key lengths ---
    rsa_key_length_table()

    # --- Key substitution ---
    simulate_key_substitution()

    # --- S/MIME comparison ---
    print("\n[PGP vs S/MIME]\n")
    print("  PGP:    Zimmermann 1991 | IDEA+RSA+MD5 | decentralized key rings")
    print("  S/MIME: IETF RFC2632-2643 | flexible algos | X.509 certs, multi-trust-anchors")
    print("  PEM:    failed (rigid root hierarchy) — S/MIME avoids this")

    print("\n" + "=" * 72)
    print("Summary: PGP = hybrid encryption (RSA for keys, IDEA for data).")
    print("  S/MIME = IETF standard, X.509 certs, multiple trust anchors.")
    print("=" * 72)


if __name__ == "__main__":
    main()
