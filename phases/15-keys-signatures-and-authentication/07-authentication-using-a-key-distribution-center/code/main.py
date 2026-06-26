#!/usr/bin/env python3
"""Authentication Using a Key Distribution Center (KDC) - Sec 8.4.

Stdlib only. Demonstrates the Needham-Schroeder protocol:

1. AS (Authentication Service) exchange: client gets a TGT (Ticket-Granting Ticket).
2. TGS (Ticket-Granting Service) exchange: client trades TGT for a service ticket.
3. Session key distribution: KDC generates and distributes session keys.
4. Replay attack prevention using nonces.

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field


def make_nonce() -> int:
    return int.from_bytes(os.urandom(4), "big")


def encrypt(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()[:32]


@dataclass
class TGT:
    client: str
    tgs_key: bytes
    client_tgs_key: bytes
    timestamp: float
    lifetime: float = 3600


@dataclass
class ServiceTicket:
    client: str
    service: str
    session_key: bytes
    timestamp: float
    lifetime: float = 300


class KDC:
    def __init__(self) -> None:
        self.client_keys: dict[str, bytes] = {}
        self.service_keys: dict[str, bytes] = {}
        self.tgs_key = os.urandom(16)

    def register_client(self, client: str, key: bytes) -> None:
        self.client_keys[client] = key

    def register_service(self, service: str, key: bytes) -> None:
        self.service_keys[service] = key

    def issue_tgt(self, client: str, nonce: int) -> dict:
        if client not in self.client_keys:
            return {"error": "unknown client"}
        client_key = self.client_keys[client]
        client_tgs_key = os.urandom(16)
        tgt = TGT(
            client=client,
            tgs_key=self.tgs_key,
            client_tgs_key=client_tgs_key,
            timestamp=float(make_nonce()),
        )
        tgt_blob = encrypt(self.tgs_key, f"{client}|{client_tgs_key.hex()}|{tgt.timestamp}")
        client_blob = encrypt(client_key, f"{client_tgs_key.hex()}|{tgt.timestamp}|{nonce}")
        return {
            "tgt": tgt,
            "tgt_blob": tgt_blob,
            "client_blob": client_blob,
            "nonce_echo": nonce,
        }

    def issue_service_ticket(self, tgt: TGT, service: str, nonce: int) -> dict:
        if service not in self.service_keys:
            return {"error": "unknown service"}
        service_key = self.service_keys[service]
        session_key = os.urandom(16)
        ticket = ServiceTicket(
            client=tgt.client,
            service=service,
            session_key=session_key,
            timestamp=float(make_nonce()),
        )
        ticket_blob = encrypt(service_key, f"{tgt.client}|{session_key.hex()}|{ticket.timestamp}")
        client_blob = encrypt(tgt.client_tgs_key, f"{session_key.hex()}|{ticket.timestamp}|{nonce}")
        return {
            "ticket": ticket,
            "ticket_blob": ticket_blob,
            "client_blob": client_blob,
            "nonce_echo": nonce,
        }


def needham_schroeder(kdc: KDC, client: str, service: str) -> dict:
    nonce1 = make_nonce()
    as_result = kdc.issue_tgt(client, nonce1)
    if "error" in as_result:
        return {"error": f"AS: {as_result['error']}"}

    nonce2 = make_nonce()
    tgs_result = kdc.issue_service_ticket(as_result["tgt"], service, nonce2)
    if "error" in tgs_result:
        return {"error": f"TGS: {tgs_result['error']}"}

    auth = encrypt(tgs_result["ticket"].session_key, f"{client}|{make_nonce()}")
    return {
        "step1_as": "Client -> KDC: client, TGS, nonce1",
        "step2_as": f"KDC -> Client: TGT (encrypted for TGS) + session key (encrypted for client), nonce1={nonce1}",
        "step3_tgs": "Client -> TGS: TGT + service + nonce2",
        "step4_tgs": f"TGS -> Client: service ticket + session key, nonce2={nonce2}",
        "step5_auth": f"Client -> Service: ticket + authenticator",
        "nonce1": nonce1,
        "nonce2": nonce2,
        "nonce1_ok": as_result["nonce_echo"] == nonce1,
        "nonce2_ok": tgs_result["nonce_echo"] == nonce2,
        "session_key": tgs_result["ticket"].session_key.hex()[:16],
    }


def main() -> None:
    print("=" * 65)
    print("Key Distribution Center (KDC) - Needham-Schroeder Protocol")
    print("=" * 65)

    kdc = KDC()
    kdc.register_client("Alice", b"alice_password_hash")
    kdc.register_service("FileServer", b"fileserver_key")

    print(f"\n  Registered clients: Alice")
    print(f"  Registered services: FileServer")
    print(f"  KDC TGS key: {kdc.tgs_key.hex()[:16]}...")

    print(f"\n  --- Needham-Schroeder Protocol ---")
    result = needham_schroeder(kdc, "Alice", "FileServer")

    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print(f"\n  Step 1 (AS-REQ): {result['step1_as']}")
    print(f"  Step 2 (AS-REP): {result['step2_as']}")
    print(f"    Nonce1 match: {result['nonce1_ok']}")
    print(f"\n  Step 3 (TGS-REQ): {result['step3_tgs']}")
    print(f"  Step 4 (TGS-REP): {result['step4_tgs']}")
    print(f"    Nonce2 match: {result['nonce2_ok']}")
    print(f"\n  Step 5 (AP-REQ): {result['step5_auth']}")
    print(f"  Session key: {result['session_key']}...")

    print(f"\n  Nonce verification:")
    print(f"    Nonce1 echoed by KDC: {result['nonce1_ok']} (prevents replay of AS-REP)")
    print(f"    Nonce2 echoed by TGS: {result['nonce2_ok']} (prevents replay of TGS-REP)")

    print()
    print("=" * 65)
    print("Replay Attack Prevention")
    print("=" * 65)

    print(f"\n  Scenario: Mallory captures Alice's service ticket and replays it.")
    print(f"  Defense: The authenticator contains a fresh timestamp.")
    print(f"  The service rejects authenticators older than the clock skew window.")

    print()
    print("=" * 65)
    print("KDC Protocol Flow Summary")
    print("=" * 65)
    print(f"  {'Step':6s} {'Message':15s} {'From':8s} {'To':8s} {'Purpose'}")
    print(f"  {'-'*6} {'-'*15} {'-'*8} {'-'*8} {'-'*35}")
    print(f"  {'1':6s} {'AS-REQ':15s} {'Client':8s} {'KDC':8s} {'Request TGT (client, TGS, nonce)'}")
    print(f"  {'2':6s} {'AS-REP':15s} {'KDC':8s} {'Client':8s} {'TGT + client/TGS session key'}")
    print(f"  {'3':6s} {'TGS-REQ':15s} {'Client':8s} {'TGS':8s} {'TGT + service + nonce'}")
    print(f"  {'4':6s} {'TGS-REP':15s} {'TGS':8s} {'Client':8s} {'Service ticket + session key'}")
    print(f"  {'5':6s} {'AP-REQ':15s} {'Client':8s} {'Service':8s} {'Ticket + authenticator'}")
    print(f"  {'6':6s} {'AP-REP':15s} {'Service':8s} {'Client':8s} {'Mutual auth (optional)'}")


if __name__ == "__main__":
    main()
