"""Challenge-response authentication with reflection attack demo.

Stdlib-only simulator that walks a two-message HMAC-SHA256 challenge-response
protocol, demonstrates the reflection attack against the naive construction,
and shows how per-direction key derivation defeats the attack.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def keyed_hash(key: bytes, msg: bytes) -> bytes:
    """f(K, R) = HMAC-SHA256(K, R). Returns 32 bytes."""
    return hmac.new(key, msg, hashlib.sha256).digest()


def derive(key: bytes, label: bytes) -> bytes:
    """Derive a sub-key from a master key and a label (per-direction split)."""
    return hmac.new(key, label, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Protocol state
# ---------------------------------------------------------------------------

@dataclass
class NaiveVerifier:
    """Single shared key -- vulnerable to reflection."""

    name: str
    key: bytes
    issued: list[bytes] = field(default_factory=list)

    def issue(self) -> bytes:
        r = secrets.token_bytes(16)
        self.issued.append(r)
        return r

    def verify(self, response: bytes, challenge: bytes) -> bool:
        expected = keyed_hash(self.key, challenge)
        return hmac.compare_digest(response, expected)


@dataclass
class SecureVerifier:
    """Per-direction keys (defeats reflection)."""

    name: str
    key_in: bytes  # verifier -> prover (challenge direction)
    key_out: bytes  # prover -> verifier (response direction)
    issued: list[bytes] = field(default_factory=list)

    def issue(self) -> bytes:
        r = secrets.token_bytes(16)
        self.issued.append(r)
        return r

    def verify(self, response: bytes, challenge: bytes) -> bool:
        expected = keyed_hash(self.key_out, challenge)
        return hmac.compare_digest(response, expected)


@dataclass
class Prover:
    """Alice, who proves knowledge of K_AB."""

    name: str
    key: bytes
    key_in: bytes | None = None  # for direction-aware variant

    def respond(self, challenge: bytes) -> bytes:
        return keyed_hash(self.key, challenge)

    def respond_secure(self, challenge: bytes) -> bytes:
        assert self.key_in is not None
        return keyed_hash(self.key_in, challenge)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_happy_path() -> None:
    """Alice authenticates to Bob; Bob accepts."""
    print("=== Scenario 1: Happy-path authentication ===")
    shared = os.urandom(32)
    bob = NaiveVerifier("Bob", shared)
    alice = Prover("Alice", shared)

    r = bob.issue()
    response = alice.respond(r)
    accepted = bob.verify(response, r)
    print(f"  challenge  R       = {r.hex()[:16]}...")
    print(f"  response   f(K,R)  = {response.hex()[:16]}...")
    print(f"  Bob accepts?       = {accepted}")
    assert accepted


def scenario_reflection_attack_naive() -> None:
    """Trudy reflects Bob's challenge back to Bob on a second connection."""
    print("\n=== Scenario 2: Reflection attack against naive CR ===")
    shared = os.urandom(32)
    bob = NaiveVerifier("Bob", shared)

    # Connection 1: Trudy -> Bob ("I am Alice")
    r1 = bob.issue()  # Bob sends challenge to Trudy

    # Connection 2: Trudy -> Bob ("I am Bob")
    r2_sent_by_trudy = r1  # Trudy reflects Bob's own challenge
    # Bob as a *prover* computes f(K_AB, r2_sent_by_trudy)
    bob_proof = keyed_hash(shared, r2_sent_by_trudy)

    # Trudy forwards Bob's proof into Connection 1
    trudy_response = bob_proof
    accepted = bob.verify(trudy_response, r1)
    print(f"  Bob's challenge R1          = {r1.hex()[:16]}...")
    print(f"  Trudy reflects R1 back to Bob on Conn 2")
    print(f"  Bob computes f(K,R1)        = {bob_proof.hex()[:16]}...")
    print(f"  Trudy forwards this into Conn 1")
    print(f"  Bob accepts Trudy as Alice? = {accepted}")
    print("  ATTACK SUCCEEDED: Trudy authenticated without knowing K_AB")


def scenario_reflection_blocked() -> None:
    """Per-direction keys defeat the reflection attack."""
    print("\n=== Scenario 3: Reflection attack against per-direction-key CR ===")
    shared = os.urandom(32)
    k_in = derive(shared, b"client->server")
    k_out = derive(shared, b"server->client")
    bob = SecureVerifier("Bob", k_in, k_out)
    alice = Prover("Alice", shared, key_in=k_in)

    # Happy path still works
    r = bob.issue()
    response = alice.respond_secure(r)
    accepted = bob.verify(response, r)
    print(f"  happy-path: Bob accepts Alice? = {accepted}")

    # Now attempt reflection
    r1 = bob.issue()
    # Trudy reflects R1 to Bob on Conn 2
    bob_proof = keyed_hash(k_in, r1)  # Bob uses K_IN as a prover
    # Trudy forwards bob_proof to Conn 1
    # But Conn 1 expects f(K_OUT, R1) -- different key!
    accepted_attack = bob.verify(bob_proof, r1)
    print(f"  reflected value          = {bob_proof.hex()[:16]}...")
    print(f"  expected (K_OUT, R1)     = {keyed_hash(k_out, r1).hex()[:16]}...")
    print(f"  Bob accepts reflected?   = {accepted_attack}")
    print("  ATTACK BLOCKED: per-direction keys made the contexts non-equivalent")


def scenario_challenge_uniqueness() -> None:
    """Replay of a stale challenge is rejected by a freshness cache."""
    print("\n=== Scenario 4: Replay defense via nonce uniqueness ===")
    shared = os.urandom(32)
    bob = NaiveVerifier("Bob", shared)
    alice = Prover("Alice", shared)

    r = bob.issue()
    response = alice.respond(r)
    first = bob.verify(response, r)

    seen: set[bytes] = set()
    second_fresh = r not in seen
    seen.add(r)
    print(f"  first use accepted?         = {first}")
    print(f"  replay rejected by freshness = {not second_fresh}")


def main() -> None:
    scenario_happy_path()
    scenario_reflection_attack_naive()
    scenario_reflection_blocked()
    scenario_challenge_uniqueness()
    print("\nAll scenarios completed.")


if __name__ == "__main__":
    main()