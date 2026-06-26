"""Diffie-Hellman key exchange and the man-in-the-middle attack.

A complete DH implementation in pure stdlib Python:

1. `modexp(base, exp, mod)` -- square-and-multiply, returns base^exp mod mod.
2. `RFC3526_GROUP5` -- the IETF 1536-bit MODP group, hard-coded hex literal.
3. `DiffieHellman` -- a DH party: pick a private exponent, expose a public
   value, compute the shared secret with a peer's public value.
4. `MITMTrudy` -- an active attacker who runs two parallel DH exchanges and
   learns the keys on both sides.
5. `signed_dh` -- a SIGMA-style binding of the DH exponentials to an RSA
   signature so MITM is detected.

Run `python3 main.py` to see the clean exchange, the MITM break, and the
authenticated exchange side by side.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

RFC3526_GROUP5_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF"
)
RFC3526_GROUP5 = (int(RFC3526_GROUP5_HEX, 16), 2)

RFC3526_GROUP14_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE65381"
    "FFFFFFFFFFFFFFFF"
)


def modexp(base: int, exp: int, mod: int) -> int:
    """Square-and-multiply modular exponentiation. Returns base^exp mod mod."""
    if mod == 1:
        return 0
    result = 1
    base = base % mod
    while exp > 0:
        if exp & 1:
            result = (result * base) % mod
        exp >>= 1
        base = (base * base) % mod
    return result


def fermat_prime_check(p: int, k: int = 16) -> bool:
    if p < 2:
        return False
    for small in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if p == small:
            return True
        if p % small == 0:
            return False
    d = p - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(k):
        a = secrets.randbelow(p - 3) + 2
        x = pow(a, d, p)
        if x == 1 or x == p - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, p)
            if x == p - 1:
                break
        else:
            return False
    return True


def random_private_exponent(p: int) -> int:
    return secrets.randbelow(p - 2) + 2


@dataclass
class DiffieHellman:
    p: int
    g: int
    private_exponent: int = 0
    public_value: int = 0

    def generate(self) -> int:
        self.private_exponent = random_private_exponent(self.p)
        self.public_value = modexp(self.g, self.private_exponent, self.p)
        return self.public_value

    def shared_secret(self, peer_public: int) -> int:
        if not (2 <= peer_public < self.p):
            raise ValueError("peer public value out of range; possible MITM")
        return modexp(peer_public, self.private_exponent, self.p)


class MITMTrudy:
    """Single-z MITM: Trudy picks ONE exponent z and uses it with both Alice and Bob.

    Under the textbook MITM, Trudy maintains two simultaneous DH exchanges:
    she sends g^z to Alice (pretending to be Bob) and g^z to Bob (pretending to
    be Alice). Alice ends up with g^(x*z) and Bob with g^(y*z); Trudy holds
    both because she can compute g^(x*z) = A^z and g^(y*z) = B^z.
    """

    def __init__(self, p: int, g: int) -> None:
        self.p = p
        self.g = g
        self.private_exponent = random_private_exponent(p)
        self.public_value = modexp(g, self.private_exponent, p)

    def to_bob_from_alice(self, alice_public: int) -> int:
        return self.public_value

    def to_alice_from_bob(self, bob_public: int) -> int:
        return self.public_value

    def shared_with_alice(self, alice_public: int) -> int:
        return modexp(alice_public, self.private_exponent, self.p)

    def shared_with_bob(self, bob_public: int) -> int:
        return modexp(bob_public, self.private_exponent, self.p)


def run_mitm(alice: DiffieHellman, bob: DiffieHellman, trudy: MITMTrudy) -> dict:
    if alice.public_value == 0:
        alice.generate()
    if bob.public_value == 0:
        bob.generate()
    forged_for_bob = trudy.to_bob_from_alice(alice.public_value)
    forged_for_alice = trudy.to_alice_from_bob(bob.public_value)
    secret_alice = alice.shared_secret(forged_for_alice)
    secret_bob = bob.shared_secret(forged_for_bob)
    secret_trudy_to_alice = trudy.shared_with_alice(alice.public_value)
    secret_trudy_to_bob = trudy.shared_with_bob(bob.public_value)
    return {
        "alice_thinks": secret_alice,
        "bob_thinks": secret_bob,
        "trudy_with_alice": secret_trudy_to_alice,
        "trudy_with_bob": secret_trudy_to_bob,
        "alice_matches_trudy_to_alice": secret_alice == secret_trudy_to_alice,
        "bob_matches_trudy_to_bob": secret_bob == secret_trudy_to_bob,
    }


def dh_transcript_hash(p: int, g: int, public_alice: int, public_bob: int, shared: int) -> bytes:
    h = hashlib.sha256()
    h.update(p.to_bytes((p.bit_length() + 7) // 8, "big"))
    h.update(g.to_bytes((g.bit_length() + 7) // 8, "big"))
    h.update(public_alice.to_bytes((public_alice.bit_length() + 7) // 8, "big"))
    h.update(public_bob.to_bytes((public_bob.bit_length() + 7) // 8, "big"))
    h.update(shared.to_bytes((shared.bit_length() + 7) // 8, "big"))
    return h.digest()


def signed_dh_sign(signer_priv_sign_key: bytes, p: int, g: int, peer_pub: int, own_pub: int, shared: int) -> bytes:
    h = dh_transcript_hash(p, g, own_pub, peer_pub, shared)
    return hmac.new(signer_priv_sign_key, h, hashlib.sha256).digest()


def signed_dh_verify(signer_pub_key: bytes, p: int, g: int, peer_pub: int, own_pub: int, shared: int, signature: bytes) -> bool:
    h = dh_transcript_hash(p, g, own_pub, peer_pub, shared)
    expected = hmac.new(signer_pub_key, h, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


def small_demo_exchange(p: int, g: int, x: int = 8, y: int = 10) -> tuple[int, int, int]:
    alice = DiffieHellman(p, g)
    bob = DiffieHellman(p, g)
    alice.private_exponent = x
    alice.public_value = modexp(g, x, p)
    bob.private_exponent = y
    bob.public_value = modexp(g, y, p)
    s_alice = alice.shared_secret(bob.public_value)
    s_bob = bob.shared_secret(alice.public_value)
    return s_alice, s_bob, int(s_alice == s_bob)


def main() -> None:
    print("=" * 68)
    print("DIFFIE-HELLMAN  --  key exchange, MITM, and signed DH")
    print("=" * 68)

    print("\n[1] Small-textbook DH (p=47, g=3, x=8, y=10)")
    s_a, s_b, ok = small_demo_exchange(47, 3)
    print(f"  Alice computes S = {s_a}")
    print(f"  Bob   computes S = {s_b}")
    print(f"  Match: {ok}")

    print("\n[2] RFC 3526 Group 5 (1536-bit) -- clean DH")
    p, g = RFC3526_GROUP5
    alice = DiffieHellman(p, g)
    bob = DiffieHellman(p, g)
    alice.generate()
    bob.generate()
    s_alice = alice.shared_secret(bob.public_value)
    s_bob = bob.shared_secret(alice.public_value)
    print(f"  Alice public (g^x mod p):  {alice.public_value.bit_length()} bits")
    print(f"  Bob   public (g^y mod p):  {bob.public_value.bit_length()} bits")
    s_bytes = (s_alice.bit_length() + 7) // 8
    print(f"  Shared secret fingerprint: {hashlib.sha256(s_alice.to_bytes(s_bytes, 'big')).hexdigest()[:24]}...")
    print(f"  Shared secrets match: {s_alice == s_bob}")

    print("\n[3] MITM attack by Trudy")
    trudy = MITMTrudy(p, g)
    result = run_mitm(alice, bob, trudy)
    print(f"  Alice believes shared secret = {result['alice_thinks'].bit_length()} bits")
    print(f"  Bob   believes shared secret = {result['bob_thinks'].bit_length()} bits")
    print(f"  Trudy holds Alice key        = {result['trudy_with_alice'].bit_length()} bits")
    print(f"  Trudy holds Bob   key        = {result['trudy_with_bob'].bit_length()} bits")
    print(f"  Alice matches Trudy_to_Alice: {result['alice_matches_trudy_to_alice']}")
    print(f"  Bob   matches Trudy_to_Bob  : {result['bob_matches_trudy_to_bob']}")
    print(f"  Alice thinks same as Bob    : {result['alice_thinks'] == result['bob_thinks']}  (False = MITM success)")
    mitm_worked = result['alice_matches_trudy_to_alice'] and result['bob_matches_trudy_to_bob'] and result['alice_thinks'] != result['bob_thinks']
    print(f"  MITM succeeded (both keys compromised): {mitm_worked}")

    print("\n[4] Signed DH (HMAC over transcript) defeats MITM")
    alice_sig_key = secrets.token_bytes(32)
    bob_sig_key = secrets.token_bytes(32)
    alice_sig = signed_dh_sign(alice_sig_key, p, g, bob.public_value, alice.public_value, s_alice)
    bob_verifies = signed_dh_verify(alice_sig_key, p, g, bob.public_value, alice.public_value, s_alice, alice_sig)
    print(f"  Alice signature over (p,g,A,B,S): {alice_sig.hex()[:32]}...")
    print(f"  Bob verifies Alice signature   : {bob_verifies}")
    trudy_signature = signed_dh_sign(b"unknown" * 16, p, g, bob.public_value, alice.public_value, s_alice)
    bob_accepts_trudy = signed_dh_verify(alice_sig_key, p, g, bob.public_value, alice.public_value, s_alice, trudy_signature)
    print(f"  Bob accepts forged signature    : {bob_accepts_trudy}  (expected False)")


if __name__ == "__main__":
    main()
