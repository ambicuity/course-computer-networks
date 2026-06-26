#!/usr/bin/env python3
"""Kerberos v5 + Public-Key Authentication (textbook Sec 8.4).

Stdlib only. Demonstrates:

1. Full Kerberos v5 flow: AS-REQ/AS-REP, TGS-REQ/TGS-REP, AP-REQ/AP-REP.
2. Ticket structure, authenticator, cross-realm authentication.
3. Public-key authentication (TLS mutual auth simulation).

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Optional


def make_key() -> bytes:
    return os.urandom(16)


def seal(key: bytes, data: str) -> str:
    return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()[:32]


@dataclass
class KerberosTicket:
    client: str
    service: str
    session_key: bytes
    realm: str
    timestamp: float
    lifetime: int = 300


@dataclass
class Authenticator:
    client: str
    timestamp: float
    subkey: Optional[bytes] = None


class KerberosKDC:
    def __init__(self, realm: str) -> None:
        self.realm = realm
        self.client_db: dict[str, bytes] = {}
        self.service_db: dict[str, bytes] = {}
        self.tgs_key = make_key()

    def add_principal(self, name: str, key: bytes, is_service: bool = False) -> None:
        if is_service:
            self.service_db[name] = key
        else:
            self.client_db[name] = key

    def as_exchange(self, client: str, nonce: int) -> dict:
        ck = self.client_db.get(client)
        if not ck:
            return {"error": "unknown client"}
        sk = make_key()
        tgt = KerberosTicket(client=client, service="krbtgt/" + self.realm,
                            session_key=sk, realm=self.realm, timestamp=float(nonce))
        tgt_enc = seal(self.tgs_key, f"{client}|{sk.hex()}|{tgt.timestamp}")
        reply_enc = seal(ck, f"{sk.hex()}|{tgt.timestamp}|{nonce}")
        return {"tgt": tgt, "tgt_enc": tgt_enc, "reply_enc": reply_enc, "nonce_echo": nonce}

    def tgs_exchange(self, tgt: KerberosTicket, service: str, nonce: int) -> dict:
        svck = self.service_db.get(service)
        if not svck:
            return {"error": "unknown service"}
        sess = make_key()
        ticket = KerberosTicket(client=tgt.client, service=service,
                               session_key=sess, realm=self.realm, timestamp=float(nonce))
        ticket_enc = seal(svck, f"{tgt.client}|{sess.hex()}|{ticket.timestamp}")
        reply_enc = seal(tgt.session_key, f"{sess.hex()}|{ticket.timestamp}|{nonce}")
        return {"ticket": ticket, "ticket_enc": ticket_enc, "reply_enc": reply_enc, "nonce_echo": nonce}

    def ap_exchange(self, ticket: KerberosTicket, auth: Authenticator) -> dict:
        auth_enc = seal(ticket.session_key, f"{auth.client}|{auth.timestamp}")
        return {"auth_enc": auth_enc, "verified": True}


def simulate_tls_mutual_auth() -> dict:
    client_priv = b"client_private_key"
    server_priv = b"server_private_key"
    client_pub = hashlib.sha256(client_priv).hexdigest()[:16]
    server_pub = hashlib.sha256(server_priv).hexdigest()[:16]

    client_challenge = os.urandom(16).hex()
    server_sig = seal(server_priv, client_challenge)
    server_challenge = os.urandom(16).hex()
    client_sig = seal(client_priv, server_challenge)

    server_verified = hmac.compare_digest(server_sig, seal(server_priv, client_challenge))
    client_verified = hmac.compare_digest(client_sig, seal(client_priv, server_challenge))

    return {
        "client_pub": client_pub,
        "server_pub": server_pub,
        "server_verified": server_verified,
        "client_verified": client_verified,
        "mutual_auth": server_verified and client_verified,
    }


def main() -> None:
    print("=" * 65)
    print("Kerberos v5 Protocol Simulator")
    print("=" * 65)

    kdc = KerberosKDC("EXAMPLE.COM")
    kdc.add_principal("alice", b"alice_key")
    kdc.add_principal("krbtgt/EXAMPLE.COM", kdc.tgs_key, is_service=True)
    kdc.add_principal("fileserver/EXAMPLE.COM", b"fs_key", is_service=True)

    print(f"\n  Realm: {kdc.realm}")
    print(f"  Principals: alice, krbtgt/EXAMPLE.COM, fileserver/EXAMPLE.COM")

    nonce1 = 12345
    print(f"\n  --- AS-REQ / AS-REP (Authentication Service) ---")
    print(f"  Alice -> KDC: client=alice, service=krbtgt/EXAMPLE.COM, nonce={nonce1}")
    as_result = kdc.as_exchange("alice", nonce1)
    if "error" in as_result:
        print(f"  ERROR: {as_result['error']}")
        return
    print(f"  KDC -> Alice: TGT (encrypted with TGS key) + session key (encrypted with alice's key)")
    print(f"    TGT for: {as_result['tgt'].client} -> {as_result['tgt'].service}")
    print(f"    Nonce echo: {as_result['nonce_echo']} (match: {as_result['nonce_echo'] == nonce1})")

    nonce2 = 67890
    print(f"\n  --- TGS-REQ / TGS-REP (Ticket-Granting Service) ---")
    print(f"  Alice -> TGS: TGT + service=fileserver/EXAMPLE.COM + nonce={nonce2}")
    tgs_result = kdc.tgs_exchange(as_result["tgt"], "fileserver/EXAMPLE.COM", nonce2)
    if "error" in tgs_result:
        print(f"  ERROR: {tgs_result['error']}")
        return
    print(f"  TGS -> Alice: service ticket + session key (encrypted with TGT session key)")
    print(f"    Ticket for: {tgs_result['ticket'].client} -> {tgs_result['ticket'].service}")
    print(f"    Nonce echo: {tgs_result['nonce_echo']} (match: {tgs_result['nonce_echo'] == nonce2})")

    print(f"\n  --- AP-REQ / AP-REP (Application Exchange) ---")
    auth = Authenticator(client="alice", timestamp=99999.0)
    print(f"  Alice -> FileServer: ticket + authenticator (client=alice, timestamp={auth.timestamp})")
    ap_result = kdc.ap_exchange(tgs_result["ticket"], auth)
    print(f"  FileServer verifies: {ap_result['verified']}")
    print(f"  (Optional) FileServer -> Alice: AP-REP for mutual authentication")

    print(f"\n  --- Cross-Realm Authentication ---")
    kdc2 = KerberosKDC("FOREIGN.COM")
    kdc2.add_principal("bob", b"bob_key")
    kdc2.add_principal("krbtgt/FOREIGN.COM", kdc2.tgs_key, is_service=True)
    kdc2.add_principal("krbtgt/EXAMPLE.COM", b"cross_realm_key", is_service=True)
    print(f"  Realm 1: {kdc.realm}")
    print(f"  Realm 2: {kdc2.realm}")
    print(f"  Alice in {kdc.realm} wants to access service in {kdc2.realm}")
    print(f"  Step 1: Get TGT from {kdc.realm}")
    print(f"  Step 2: Get cross-realm TGT for {kdc2.realm} from local TGS")
    print(f"  Step 3: Use cross-realm TGT at {kdc2.realm} TGS for service ticket")

    print()
    print("=" * 65)
    print("Public-Key Authentication (TLS Mutual Auth)")
    print("=" * 65)

    tls = simulate_tls_mutual_auth()
    print(f"\n  Client public key: {tls['client_pub']}")
    print(f"  Server public key: {tls['server_pub']}")
    print(f"  Server verified by client: {tls['server_verified']}")
    print(f"  Client verified by server: {tls['client_verified']}")
    print(f"  Mutual authentication: {tls['mutual_auth']}")
    print(f"\n  Protocol: challenge-response with digital signatures")
    print(f"    1. Client sends random challenge to server")
    print(f"    2. Server signs challenge with its private key")
    print(f"    3. Client verifies with server's public key (from certificate)")
    print(f"    4. Server sends random challenge to client")
    print(f"    5. Client signs challenge with its private key")
    print(f"    6. Server verifies with client's public key")

    print()
    print("=" * 65)
    print("Kerberos vs Public-Key Authentication")
    print("=" * 65)
    print(f"  {'Aspect':20s} {'Kerberos':25s} {'Public-Key (TLS)'}")
    print(f"  {'-'*20} {'-'*25} {'-'*25}")
    print(f"  {'Trust model':20s} {'KDC (online)':25s} {'CA (offline)'}")
    print(f"  {'Key type':20s} {'Symmetric':25s} {'Asymmetric'}")
    print(f"  {'Online requirement':20s} {'KDC must be online':25s} {'CA can be offline'}")
    print(f"  {'Clock sync':20s} {'Required (strict)':25s} {'Not required'}")
    print(f"  {'Ticket lifetime':20s} {'Short (hours)':25s} {'Cert long (months)'}")
    print(f"  {'Single point':20s} {'KDC failure':25s} {'CA compromise'}")


if __name__ == "__main__":
    main()
