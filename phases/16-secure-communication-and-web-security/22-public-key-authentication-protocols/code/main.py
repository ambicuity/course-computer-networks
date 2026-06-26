"""Public-key mutual challenge-response, plus SSH and TLS 1.3 transcript formats.

Pure stdlib RSA + SHA-256 + HMAC. Builds on lesson 18's RSA primitives and
adds the protocol logic for two-nonce mutual auth and the two canonical
real-world transcripts: SSH publickey (RFC 4252 §7) and TLS 1.3
CertificateVerify (RFC 8446 §4.4.3).

Run `python3 main.py` to see both transcripts signed, verified, and tested
against a downgrade attacker.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "18-x509-certificates-and-pki", "code"))
from main import (  # type: ignore
    PublicKey,
    PrivateKey,
    generate_rsa_keypair as rsa_keypair,
    pkcs1_v15_sign,
    pkcs1_v15_verify,
)

NONCE_BYTES = 32
HKDF_INFO = b"mutual-auth-session-key-v1"


def generate_nonce(n: int = NONCE_BYTES) -> bytes:
    return secrets.token_bytes(n)


def transcript_bytes(ra: bytes, rb: bytes, alice_id: str, bob_id: str, algorithm: str) -> bytes:
    h = hashlib.sha256()
    h.update(ra)
    h.update(rb)
    h.update(algorithm.encode())
    h.update(alice_id.encode())
    h.update(bob_id.encode())
    return h.digest()


@dataclass
class MutualAuthResult:
    success: bool
    ra: bytes
    rb: bytes
    alice_signature: bytes
    bob_signature: bytes
    algorithm: str
    session_key_material: bytes
    error: str | None = None


def mutual_challenge_response(
    alice_priv: PrivateKey, alice_pub: PublicKey,
    bob_priv: PrivateKey, bob_pub: PublicKey,
    alice_id: str = "alice",
    bob_id: str = "bob",
    algorithm: str = "rsa-pkcs1-sha256",
) -> MutualAuthResult:
    ra = generate_nonce()
    rb = generate_nonce()
    t_alice = transcript_bytes(ra, rb, alice_id, bob_id, algorithm)
    sig_alice = pkcs1_v15_sign(t_alice, alice_priv)
    if not pkcs1_v15_verify(t_alice, sig_alice, alice_pub):
        return MutualAuthResult(False, ra, rb, sig_alice, b"", algorithm, b"", "alice signature verify failed")
    t_bob = transcript_bytes(ra, rb, alice_id, bob_id, algorithm)
    sig_bob = pkcs1_v15_sign(t_bob, bob_priv)
    if not pkcs1_v15_verify(t_bob, sig_bob, bob_pub):
        return MutualAuthResult(False, ra, rb, sig_alice, sig_bob, algorithm, b"", "bob signature verify failed")
    session_key = hmac.new(ra + rb, HKDF_INFO, hashlib.sha256).digest()
    return MutualAuthResult(True, ra, rb, sig_alice, sig_bob, algorithm, session_key)


def ssh_transcript(session_id: bytes, user: str, service: str, key_blob: bytes, nonce: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(b"ssh-publickey-transcript-v1")
    h.update(session_id)
    h.update(user.encode())
    h.update(service.encode())
    h.update(key_blob)
    h.update(nonce)
    return h.digest()


def ssh_publickey_sign(
    priv: PrivateKey,
    session_id: bytes,
    user: str,
    service: str,
    key_blob: bytes,
    nonce: bytes,
) -> bytes:
    t = ssh_transcript(session_id, user, service, key_blob, nonce)
    return pkcs1_v15_sign(t, priv)


def ssh_publickey_verify(
    sig: bytes,
    pub: PublicKey,
    session_id: bytes,
    user: str,
    service: str,
    key_blob: bytes,
    nonce: bytes,
) -> bool:
    t = ssh_transcript(session_id, user, service, key_blob, nonce)
    return pkcs1_v15_verify(t, sig, pub)


def tls13_certificate_verify_sign(
    priv: PrivateKey,
    transcript_hash: bytes,
    context: bytes = b"TLS 1.3, client CertificateVerify\x00",
) -> bytes:
    """RFC 8446 §4.4.3: signs 64 zero bytes || context || transcript_hash."""
    pad = b"\x00" * 64
    message = pad + context + transcript_hash
    return pkcs1_v15_sign(message, priv)


def tls13_certificate_verify_check(
    sig: bytes,
    pub: PublicKey,
    transcript_hash: bytes,
    context: bytes = b"TLS 1.3, client CertificateVerify\x00",
) -> bool:
    pad = b"\x00" * 64
    message = pad + context + transcript_hash
    return pkcs1_v15_verify(message, sig, pub)


def downgrade_attack(ra: bytes, rb: bytes, sig_alice: bytes, sig_bob: bytes) -> tuple[bytes, bytes, bytes, bytes, str]:
    """Attacker rewrites algorithm negotiation. Returns forged tuple with weaker algo."""
    return (ra, rb, sig_alice, sig_bob, "rsa-pkcs1-sha1")


def main() -> None:
    print("=" * 68)
    print("MUTUAL CHALLENGE-RESPONSE  --  two-nonce public-key auth")
    print("=" * 68)

    alice_priv, alice_pub = rsa_keypair(2048)
    bob_priv, bob_pub = rsa_keypair(2048)

    print("\n[1] Two-nonce mutual challenge-response")
    result = mutual_challenge_response(alice_priv, alice_pub, bob_priv, bob_pub)
    print(f"  R_A = {result.ra.hex()[:32]}...")
    print(f"  R_B = {result.rb.hex()[:32]}...")
    print(f"  algorithm in transcript = {result.algorithm}")
    print(f"  session key material = {result.session_key_material.hex()[:32]}...")
    print(f"  success = {result.success}")

    print("\n[2] SSH publickey transcript (RFC 4252 §7)")
    session_id = secrets.token_bytes(32)
    user = "alice"
    service = "ssh-connection"
    key_blob = b"|".join([str(alice_pub.n).encode(), str(alice_pub.e).encode()])
    nonce = secrets.token_bytes(32)
    sig = ssh_publickey_sign(alice_priv, session_id, user, service, key_blob, nonce)
    print(f"  session_id = {session_id.hex()[:24]}...")
    print(f"  nonce      = {nonce.hex()[:24]}...")
    print(f"  signature  = {sig.hex()[:24]}...")
    ok = ssh_publickey_verify(sig, alice_pub, session_id, user, service, key_blob, nonce)
    print(f"  server verify = {ok}")

    print("\n[3] TLS 1.3 CertificateVerify (RFC 8446 §4.4.3)")
    transcript_hash = hashlib.sha256(b"ClientHello ... ServerHello ... Finished").digest()
    sig_client = tls13_certificate_verify_sign(alice_priv, transcript_hash)
    print(f"  transcript hash = {transcript_hash.hex()[:24]}...")
    print(f"  client signature = {sig_client.hex()[:24]}...")
    ok_client = tls13_certificate_verify_check(sig_client, alice_pub, transcript_hash)
    print(f"  client signature verifies = {ok_client}")

    print("\n[4] Downgrade attack rejected by algorithm binding")
    forged_algo, weaker_algo = downgrade_attack(result.ra, result.rb, result.alice_signature, result.bob_signature), "rsa-pkcs1-sha1"
    t_under_weaker = transcript_bytes(result.ra, result.rb, "alice", "bob", "rsa-pkcs1-sha1")
    alice_sig_verifies_under_weaker = pkcs1_v15_verify(t_under_weaker, result.alice_signature, alice_pub)
    print(f"  alice signature verifies under forged weaker algo = {alice_sig_verifies_under_weaker}")
    print(f"  (expected False: signature was over 'rsa-pkcs1-sha256'; weaker algo invalidates it)")


if __name__ == "__main__":
    main()
