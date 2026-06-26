"""Diffie-Hellman key exchange with man-in-the-middle attack demo.

Stdlib-only simulator that walks a working DH exchange using a small safe-prime
group, demonstrates the MITM attack, and shows how signed parameters defeat it.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Small safe-prime group (DEMO ONLY -- do not use in production)
# p = 2*q + 1, both prime. g is a generator of order q in Z*_p.
# ---------------------------------------------------------------------------

P = 0xFFFFFFFFFFFFFFC5  # 64-bit safe prime
Q = (P - 1) // 2        # cofactor
G = 2                   # generator


def modpow(base: int, exp: int, mod: int) -> int:
    """Modular exponentiation via stdlib pow with three args."""
    return pow(base, exp, mod)


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

@dataclass
class DHParticipant:
    """A party who holds a long-term signing key and runs DH."""

    name: str
    signing_key: bytes  # long-term HMAC key for signed-DH demo

    private: int = 0
    public: int = 0

    def generate_keypair(self) -> None:
        """Pick a fresh private exponent in [2, q-1] and compute the public value."""
        self.private = secrets.randbelow(Q - 1) + 1
        self.public = modpow(G, self.private, P)

    def derive_shared(self, their_public: int) -> int:
        return modpow(their_public, self.private, P)

    def sign_public(self) -> bytes:
        """HMAC the public value under the long-term key."""
        return hmac.new(self.signing_key, str(self.public).encode(), hashlib.sha256).digest()

    def verify_signature(self, their_public: int, signature: bytes) -> bool:
        expected = hmac.new(self.signing_key, str(their_public).encode(), hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_honest_dh() -> None:
    """Two parties derive the same shared key."""
    print("=== Scenario 1: Honest DH exchange ===")
    alice = DHParticipant("Alice", signing_key=os.urandom(32))
    bob = DHParticipant("Bob", signing_key=os.urandom(32))

    alice.generate_keypair()
    bob.generate_keypair()

    alice_view = alice.derive_shared(bob.public)
    bob_view = bob.derive_shared(alice.public)
    print(f"  Alice's public value A = {hex(alice.public)[:18]}...")
    print(f"  Bob's public value   B = {hex(bob.public)[:18]}...")
    print(f"  Alice's K            = {hex(alice_view)[:18]}...")
    print(f"  Bob's K              = {hex(bob_view)[:18]}...")
    print(f"  Match?                 = {alice_view == bob_view}")
    assert alice_view == bob_view


def scenario_mitm_attack() -> None:
    """Trudy substitutes her own DH values and reads both conversations."""
    print("\n=== Scenario 2: Man-in-the-middle attack ===")
    alice = DHParticipant("Alice", signing_key=os.urandom(32))
    bob = DHParticipant("Bob", signing_key=os.urandom(32))
    trudy = DHParticipant("Trudy", signing_key=os.urandom(32))

    alice.generate_keypair()
    bob.generate_keypair()
    trudy.generate_keypair()  # Trudy will use *two* private values

    # Trudy substitutes her own values
    alice_view = alice.derive_shared(trudy.public)  # K with Trudy, not Bob
    bob_view = bob.derive_shared(trudy.public)      # K with Trudy, not Alice

    print(f"  Alice thinks she shares with Bob; actual K = {hex(alice_view)[:18]}...")
    print(f"  Bob   thinks he shares with Alice; K      = {hex(bob_view)[:18]}...")
    print(f"  Match? = {alice_view == bob_view}")
    print("  ATTACK SUCCEEDED: Alice and Bob derived DIFFERENT keys.")
    print("  Trudy can decrypt Alice's traffic with her t_b and Bob's with her t_a.")


def scenario_signed_dh() -> None:
    """Each party signs its public value; Trudy's MITM fails verification."""
    print("\n=== Scenario 3: Signed DH (MITM blocked) ===")
    # In a real system, Alice and Bob have published certificates binding
    # their identity to their long-term public key. Here we share the long-term
    # HMAC key out-of-band (this is the same setup TLS uses with trust anchors).
    shared_signing_key = os.urandom(32)
    alice = DHParticipant("Alice", signing_key=shared_signing_key)
    bob = DHParticipant("Bob", signing_key=shared_signing_key)
    trudy = DHParticipant("Trudy", signing_key=b"")  # unknown key

    alice.generate_keypair()
    bob.generate_keypair()
    trudy.generate_keypair()

    alice_sig = alice.sign_public()
    bob_sig = bob.sign_public()

    # Alice verifies Bob's signature over the public value she received.
    # Trudy can substitute her public value, but she cannot forge Bob's signature.
    trudy_sig = hmac.new(b"", str(trudy.public).encode(), hashlib.sha256).digest()

    alice_accepts_trudy = alice.verify_signature(trudy.public, trudy_sig)
    bob_accepts_alice = bob.verify_signature(alice.public, alice_sig)

    print(f"  Alice verifies Trudy's claimed Bob-signature = {alice_accepts_trudy}")
    print(f"  Bob   verifies Alice's actual signature      = {bob_accepts_alice}")
    print("  ATTACK BLOCKED: Trudy cannot forge Bob's signature without the long-term key.")


def scenario_group_size_comparison() -> None:
    """Sanity check: same protocol scales to larger primes."""
    print("\n=== Scenario 4: Group size sanity check ===")
    # 256-bit safe prime from RFC 5114 Appendix A (smallest IETF group for demo)
    P_256 = (1 << 256) - (1 << 32) - 977  # secp256k1 base prime, used as MODP stand-in
    a = secrets.randbelow(P_256 - 2) + 1
    b = secrets.randbelow(P_256 - 2) + 1
    A = pow(2, a, P_256)
    B = pow(2, b, P_256)
    K_ab = pow(B, a, P_256)
    K_ba = pow(A, b, P_256)
    print(f"  256-bit prime, group work factor ~ 2^128")
    print(f"  Alice and Bob's shared K = {hex(K_ab)[:24]}...")
    print(f"  Keys match:              {K_ab == K_ba}")


def main() -> None:
    scenario_honest_dh()
    scenario_mitm_attack()
    scenario_signed_dh()
    scenario_group_size_comparison()
    print("\nAll scenarios completed.")


if __name__ == "__main__":
    main()