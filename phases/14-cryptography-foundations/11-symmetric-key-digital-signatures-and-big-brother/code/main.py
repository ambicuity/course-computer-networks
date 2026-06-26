#!/usr/bin/env python3
"""Symmetric-key digital signatures via a trusted Big Brother (BB) authority.

Implements the protocol from Tanenbaum & Wetherall Chapter 8, Sec. 8.4.1:
* Every user shares a unique symmetric key with Big Brother.
* Alice authenticates to BB by HMAC-ing the request (B, R_A, t, P) under K_A.
* BB re-signs under K_BB and forwards to Bob, who verifies timestamp and nonce.

No third-party dependencies, no network access. Run: ``python3 main.py``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
HMAC_KEY_BYTES = 32        # 256-bit HMAC key for K_A, K_B, K_BB
REPLAY_WINDOW_SECONDS = 5  # Bob accepts timestamps within ±5 s of his clock
NONCE_BYTES = 16           # 128-bit R_A


# ---------------------------------------------------------------------------
# Symmetric primitive (HMAC-SHA256, used as a stand-in for a keyed permutation)
# ---------------------------------------------------------------------------
def keyed_mac(key: bytes, message: bytes) -> bytes:
    """MAC under a shared key using HMAC-SHA256 (RFC 2104)."""
    return hmac.new(key, message, hashlib.sha256).digest()


def make_key() -> bytes:
    """Cryptographically strong random key (os.urandom)."""
    return os.urandom(HMAC_KEY_BYTES)


def make_nonce() -> bytes:
    return secrets.token_bytes(NONCE_BYTES)


# ---------------------------------------------------------------------------
# Big Brother — keeps K_A for every user, master K_BB, plus a request escrow
# ---------------------------------------------------------------------------
@dataclass
class BigBrother:
    user_keys: Dict[str, bytes] = field(default_factory=dict)
    master_key: bytes = b""
    escrow: list = field(default_factory=list)  # BB records (A, P, t) for every signed request

    def register(self, user: str) -> bytes:
        """Issue and store a fresh K_user shared with the named user."""
        key = make_key()
        self.user_keys[user] = key
        return key

    def receive_request(self, envelope: dict, now: float) -> dict | None:
        """BB decrypts Alice's request, builds the two-part bundle for Bob."""
        a = envelope["sender"]
        ct = envelope["ciphertext"]
        t = envelope["timestamp"]
        if abs(now - t) > REPLAY_WINDOW_SECONDS:
            return {"error": "stale_timestamp_at_BB"}
        a_key = self.user_keys.get(a)
        if a_key is None:
            return {"error": "unknown_user"}
        mac = keyed_mac(a_key, envelope["plaintext_blob"])
        if not hmac.compare_digest(mac, ct):
            return {"error": "mac_invalid_at_BB"}
        request = json.loads(envelope["plaintext_blob"].decode())
        b, r_a, _, p = request["b"], request["r_a"], request["t"], request["p"]
        b_key = self.user_keys.get(b)
        if b_key is None:
            return {"error": "unknown_recipient"}
        # Exhibit: K_BB(A, t, P)
        exhibit_payload = json.dumps({"a": a, "t": t, "p": p}, sort_keys=True).encode()
        exhibit = keyed_mac(self.master_key, exhibit_payload)
        # Forwarded request: K_B(B, R_A, t, P)
        forward_payload = json.dumps(
            {"b": b, "r_a": r_a, "t": t, "p": p}, sort_keys=True
        ).encode()
        forward = keyed_mac(b_key, forward_payload)
        self.escrow.append({"a": a, "b": b, "p": p, "t": t})
        return {
            "exhibit": exhibit,
            "exhibit_payload": exhibit_payload,
            "forward": forward,
            "forward_payload": forward_payload,
            "for_b": b,
        }


# ---------------------------------------------------------------------------
# Alice — submits signed requests
# ---------------------------------------------------------------------------
@dataclass
class Alice:
    name: str
    bb_key: bytes
    bb: BigBrother

    def submit(self, recipient: str, plaintext: str, now: float) -> dict:
        r_a = make_nonce()
        t = now
        payload = json.dumps(
            {"b": recipient, "r_a": r_a.hex(), "t": t, "p": plaintext},
            sort_keys=True,
        ).encode()
        mac = keyed_mac(self.bb_key, payload)
        return {"sender": self.name, "plaintext_blob": payload, "ciphertext": mac, "timestamp": t}


# ---------------------------------------------------------------------------
# Bob — receives and verifies; caches R_A per sender
# ---------------------------------------------------------------------------
@dataclass
class Bob:
    name: str
    bb_key: bytes
    nonce_cache: Dict[Tuple[str, str], float] = field(default_factory=dict)

    def receive(self, bundle: dict, now: float) -> dict:
        if "error" in bundle:
            return {"accepted": False, "reason": bundle["error"]}
        exhibit_payload = bundle["exhibit_payload"]
        forward_payload = bundle["forward_payload"]
        # Exhibit must verify under BB's master key
        if not hmac.compare_digest(
            keyed_mac(self.bb_key, exhibit_payload), bundle["exhibit"]
        ):
            return {"accepted": False, "reason": "exhibit_mac_invalid"}
        # Forwarded request must verify under Bob's K_B
        if not hmac.compare_digest(
            keyed_mac(self.bb_key, forward_payload), bundle["forward"]
        ):
            return {"accepted": False, "reason": "forward_mac_invalid"}
        exhibit = json.loads(exhibit_payload.decode())
        forward = json.loads(forward_payload.decode())
        t = exhibit["t"]
        if abs(now - t) > REPLAY_WINDOW_SECONDS:
            return {"accepted": False, "reason": "stale_timestamp_at_bob"}
        cache_key = (exhibit["a"], forward["r_a"])
        if cache_key in self.nonce_cache:
            return {"accepted": False, "reason": "replay_detected"}
        self.nonce_cache[cache_key] = now
        return {
            "accepted": True,
            "exhibit": bundle["exhibit"],
            "exhibit_payload": exhibit_payload,
            "from": exhibit["a"],
            "plaintext": exhibit["p"],
        }


# ---------------------------------------------------------------------------
# Courtroom — Bob produces Exhibit A, BB testifies
# ---------------------------------------------------------------------------
def try_dispute(bb: BigBrother, bob_evidence: dict) -> dict:
    """A judge asks BB to decrypt the exhibit and verify it matches a request."""
    payload = bob_evidence["exhibit_payload"]
    mac = bob_evidence["exhibit"]
    if not hmac.compare_digest(keyed_mac(bb.master_key, payload), mac):
        return {"verdict": "forgery", "reason": "exhibit_mac_mismatch"}
    decoded = json.loads(payload.decode())
    matching = [
        e for e in bb.escrow
        if e["a"] == decoded["a"] and e["p"] == decoded["p"] and abs(e["t"] - decoded["t"]) < 1e-3
    ]
    if not matching:
        return {"verdict": "forgery", "reason": "no_escrow_match"}
    return {"verdict": "authentic", "escrow_entry": matching[0]}


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("Symmetric-key digital signatures with Big Brother — demo")
    print("=" * 72)

    bb = BigBrother(master_key=make_key())
    alice = Alice("Alice", bb.register("Alice"), bb)
    bob = Bob("Bob", bb.user_keys["Bob"])

    # 1. Happy path
    print("\n[1] Happy-path signed order")
    now = time.time()
    env = alice.submit("Bob", "Wire $400000 to GoldDealer X", now)
    bundle = bb.receive_request(env, now)
    bob_evidence = bob.receive(bundle, now)
    assert bob_evidence["accepted"], bob_evidence
    verdict = try_dispute(bb, bob_evidence)
    print(f"    Bob accepted: plaintext={bob_evidence['plaintext']!r}")
    print(f"    Court verdict: {verdict['verdict']}")

    # 2. Instant replay (same R_A, within window) — caught
    print("\n[2] Instant replay attempt")
    env_replay = dict(env)
    bob2 = bob.receive(bundle, now)
    print(f"    Bob's second receipt: {bob2}")

    # 3. Delayed replay (timestamp out of window)
    print("\n[3] Delayed replay (timestamp 60 s old)")
    env_old = alice.submit("Bob", "Wire $1 to GoldDealer X", now - 60)
    bundle_old = bb.receive_request(env_old, now)
    print(f"    BB verdict on stale request: {bundle_old.get('error')}")

    # 4. Forgery (attacker fabricates an envelope without K_A)
    print("\n[4] Forgery attempt — wrong HMAC key")
    forged = {
        "sender": "Alice",
        "plaintext_blob": env["plaintext_blob"],
        "ciphertext": b"\x00" * 32,
        "timestamp": now,
    }
    forged_bundle = bb.receive_request(forged, now)
    print(f"    BB verdict on forged envelope: {forged_bundle.get('error')}")

    # 5. Escrow visibility
    print("\n[5] BB escrow — BB saw plaintext of every signed message")
    for entry in bb.escrow:
        print(f"    BB knows: {entry['a']} -> {entry['b']}: {entry['p']!r}")


if __name__ == "__main__":
    main()