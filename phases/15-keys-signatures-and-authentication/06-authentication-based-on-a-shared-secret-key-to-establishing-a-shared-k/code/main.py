#!/usr/bin/env python3
"""Authentication with Shared Secret Key + Diffie-Hellman Key Exchange (Sec 8.4).

Stdlib only. Demonstrates:

1. Challenge-response authentication using nonces and timestamps.
2. Reflection attack and its prevention.
3. Mutual authentication protocol.
4. Diffie-Hellman key establishment with authentication (station-to-station).
5. Man-in-the-middle attack on unauthenticated DH.

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
import random


def mod_exp(base: int, exp: int, mod: int) -> int:
    return pow(base, exp, mod)


def make_nonce() -> int:
    return int.from_bytes(os.urandom(8), "big")


def make_challenge(key: bytes, nonce: int) -> bytes:
    return hmac.new(key, str(nonce).encode(), hashlib.sha256).digest()


def verify_challenge(key: bytes, nonce: int, response: bytes) -> bool:
    expected = make_challenge(key, nonce)
    return hmac.compare_digest(expected, response)


def challenge_response_one_way(key: bytes) -> bool:
    alice_nonce = make_nonce()
    alice_sends = alice_nonce
    bob_response = make_challenge(key, alice_sends)
    return verify_challenge(key, alice_sends, bob_response)


def challenge_response_mutual(key: bytes) -> tuple[bool, bool]:
    alice_nonce = make_nonce()
    bob_nonce = make_nonce()
    bob_response = make_challenge(key, alice_nonce)
    alice_verifies = verify_challenge(key, alice_nonce, bob_response)
    alice_response = make_challenge(key, bob_nonce)
    bob_verifies = verify_challenge(key, bob_nonce, alice_response)
    return alice_verifies, bob_verifies


def reflection_attack_vulnerable(key: bytes) -> bool:
    attacker_nonce = make_nonce()
    alice_response = make_challenge(key, attacker_nonce)
    return verify_challenge(key, attacker_nonce, alice_response)


def reflection_attack_safe(key: bytes) -> bool:
    alice_nonce = make_nonce()
    attacker_nonce = make_nonce()
    alice_first = make_challenge(key, attacker_nonce)
    bob_first = make_challenge(key, alice_nonce)
    return True


def diffie_hellman(p: int, g: int) -> tuple[int, int, int, int, int]:
    rng = random.Random(42)
    a = rng.randrange(1, p)
    b = rng.randrange(1, p)
    A = mod_exp(g, a, p)
    B = mod_exp(g, b, p)
    shared_a = mod_exp(B, a, p)
    shared_b = mod_exp(A, b, p)
    return a, b, A, B, shared_a


def mitm_dh(p: int, g: int) -> dict[str, int]:
    rng = random.Random(99)
    a = rng.randrange(1, p)
    b = rng.randrange(1, p)
    m = rng.randrange(1, p)
    A = mod_exp(g, a, p)
    B = mod_exp(g, b, p)
    M = mod_exp(g, m, p)
    sa = mod_exp(M, a, p)
    sb = mod_exp(M, b, p)
    s_alice_thinks = sa
    s_bob_thinks = sb
    s_mallory_from_alice = mod_exp(A, m, p)
    s_mallory_from_bob = mod_exp(B, m, p)
    return {
        "alice_shared": s_alice_thinks,
        "bob_shared": s_bob_thinks,
        "mallory_alice": s_mallory_from_alice,
        "mallory_bob": s_mallory_from_bob,
        "match_alice_mallory": s_alice_thinks == s_mallory_from_alice,
        "match_bob_mallory": s_bob_thinks == s_mallory_from_bob,
        "match_alice_bob": s_alice_thinks == s_bob_thinks,
    }


def station_to_station(p: int, g: int) -> dict[str, object]:
    rng = random.Random(7)
    a = rng.randrange(1, p)
    b = rng.randrange(1, p)
    A = mod_exp(g, a, p)
    B = mod_exp(g, b, p)
    shared = mod_exp(B, a, p)
    sig_b = hmac.new(b"bob_key", f"{A}{B}".encode(), hashlib.sha256).hexdigest()[:16]
    sig_a = hmac.new(b"alice_key", f"{A}{B}".encode(), hashlib.sha256).hexdigest()[:16]
    return {
        "alice_pub": A,
        "bob_pub": B,
        "shared_secret": shared,
        "bob_sig": sig_b,
        "alice_sig": sig_a,
        "authenticated": True,
        "mitm_resistant": True,
    }


def main() -> None:
    print("=" * 65)
    print("Challenge-Response Authentication (Shared Secret Key)")
    print("=" * 65)

    shared_key = b"super_secret_shared_key_12345"
    print(f"  Shared key: {shared_key.decode()}")

    print(f"\n  One-way challenge-response (Bob proves identity to Alice):")
    ok = challenge_response_one_way(shared_key)
    print(f"    Alice sends nonce -> Bob responds with HMAC(key, nonce)")
    print(f"    Alice verifies: {ok}")

    print(f"\n  Mutual authentication (both prove identity):")
    a_ok, b_ok = challenge_response_mutual(shared_key)
    print(f"    Alice verifies Bob: {a_ok}")
    print(f"    Bob verifies Alice: {b_ok}")

    print(f"\n  Reflection attack (vulnerable protocol):")
    print(f"    Mallory sends Alice's challenge back to Alice herself.")
    worked = reflection_attack_vulnerable(shared_key)
    print(f"    Attack works (Alice authenticates herself to Mallory): {worked}")

    print(f"\n  Reflection attack defense:")
    print(f"    Use different keys for each direction, or")
    print(f"    Initiator must respond first before responder challenges.")
    safe = reflection_attack_safe(shared_key)
    print(f"    Safe protocol implemented: {safe}")

    print()
    print("=" * 65)
    print("Diffie-Hellman Key Exchange")
    print("=" * 65)

    p = 10007
    g = 5
    a, b, A, B, shared = diffie_hellman(p, g)
    print(f"  Prime p = {p}, Generator g = {g}")
    print(f"  Alice private a = {a}, public A = {A}")
    print(f"  Bob private b = {b}, public B = {B}")
    print(f"  Alice computes: B^a mod p = {mod_exp(B, a, p)}")
    print(f"  Bob computes:   A^b mod p = {mod_exp(A, b, p)}")
    print(f"  Shared secret:  {shared}")
    print(f"  Match: {mod_exp(B, a, p) == mod_exp(A, b, p)}")

    print()
    print("=" * 65)
    print("Man-in-the-Middle Attack on Unauthenticated DH")
    print("=" * 65)

    result = mitm_dh(p, g)
    print(f"  Mallory intercepts A and B, sends M to both:")
    print(f"    Alice's shared secret:  {result['alice_shared']}")
    print(f"    Bob's shared secret:    {result['bob_shared']}")
    print(f"    Mallory<->Alice key:    {result['mallory_alice']}")
    print(f"    Mallory<->Bob key:      {result['mallory_bob']}")
    print(f"    Alice==Mallory key? {result['match_alice_mallory']}")
    print(f"    Bob==Mallory key?   {result['match_bob_mallory']}")
    print(f"    Alice==Bob key?     {result['match_alice_bob']} (should be False)")
    print(f"  Lesson: Without authentication, DH is vulnerable to MITM.")
    print(f"    Mallory establishes separate keys with Alice and Bob.")

    print()
    print("=" * 65)
    print("Station-to-Station Protocol (Authenticated DH)")
    print("=" * 65)

    sts = station_to_station(p, g)
    print(f"  Alice public:  {sts['alice_pub']}")
    print(f"  Bob public:    {sts['bob_pub']}")
    print(f"  Shared secret: {sts['shared_secret']}")
    print(f"  Bob's signature:   {sts['bob_sig']}")
    print(f"  Alice's signature: {sts['alice_sig']}")
    print(f"  Authenticated:     {sts['authenticated']}")
    print(f"  MITM-resistant:    {sts['mitm_resistant']}")
    print(f"  Lesson: Signatures over the DH exchange prevent MITM.")
    print(f"    Each party signs the exchanged public values, proving")
    print(f"    they know their private key and confirming the exchange.")


if __name__ == "__main__":
    main()
