#!/usr/bin/env python3
"""TLS Handshake Lab + Firewall Policy Review Lab (textbook Sec 8.9, 8.6).

Stdlib only. Demonstrates:

1. TLS 1.2 and TLS 1.3 handshake state machine — ClientHello, ServerHello,
   certificate exchange, key exchange, ChangeCipherSpec, Finished. Shows
   the 2-RTT (1.2) vs 1-RTT (1.3) difference and PSK resumption.
2. Firewall policy simulator — packet filter with rule matching (src/dst IP,
   port, protocol, direction), first-match semantics, stateful inspection
   with connection tracking, and a policy reviewer that flags overly
   permissive rules.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TLSState(Enum):
    CLOSED = auto()
    CLIENT_HELLO_SENT = auto()
    SERVER_HELLO_SENT = auto()
    CERT_SENT = auto()
    KEY_EXCHANGED = auto()
    CCS_SENT = auto()
    FINISHED = auto()
    ESTABLISHED = auto()


@dataclass
class ClientHello:
    version: str
    cipher_suites: list[str]
    extensions: list[str]
    supported_versions: list[str]


@dataclass
class ServerHello:
    version: str
    cipher_suite: str
    session_id: str
    extensions: list[str]


@dataclass
class Certificate:
    subject: str
    issuer: str
    public_key: str
    valid: bool


@dataclass
class TLSHandshake:
    state: TLSState = TLSState.CLOSED
    client_hello: Optional[ClientHello] = None
    server_hello: Optional[ServerHello] = None
    cert: Optional[Certificate] = None
    rtt_count: int = 0
    messages: list[str] = field(default_factory=list)
    shared_secret: Optional[str] = None

    def log(self, msg: str) -> None:
        self.messages.append(msg)

    def tls12_handshake(self) -> None:
        self.log("=== TLS 1.2 Handshake (2-RTT) ===")
        self.log("RTT 1:")
        self.state = TLSState.CLIENT_HELLO_SENT
        self.client_hello = ClientHello(
            version="TLS 1.2",
            cipher_suites=["TLS_RSA_WITH_AES_128_CBC_SHA", "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"],
            extensions=["server_name", "signature_algorithms"],
            supported_versions=["TLS 1.2"],
        )
        self.rtt_count += 1
        self.log(f"  C->S: ClientHello (version={self.client_hello.version}, "
                 f"{len(self.client_hello.cipher_suites)} cipher suites)")

        self.server_hello = ServerHello(
            version="TLS 1.2",
            cipher_suite="TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            session_id="abc123",
            extensions=["renegotiation_info"],
        )
        self.state = TLSState.SERVER_HELLO_SENT
        self.log(f"  S->C: ServerHello (cipher={self.server_hello.cipher_suite})")

        self.cert = Certificate(subject="example.com", issuer="Let's Encrypt", public_key="RSA-2048", valid=True)
        self.state = TLSState.CERT_SENT
        self.log(f"  S->C: Certificate (subject={self.cert.subject}, issuer={self.cert.issuer}, valid={self.cert.valid})")
        self.log(f"  S->C: ServerKeyExchange (ECDHE params)")
        self.log(f"  S->C: ServerHelloDone")

        self.log("RTT 2:")
        self.rtt_count += 1
        self.log(f"  C->S: ClientKeyExchange (ECDHE public key)")
        self.state = TLSState.KEY_EXCHANGED
        self.shared_secret = "derived_from_ECDHE"
        self.log(f"  C->S: ChangeCipherSpec")
        self.state = TLSState.CCS_SENT
        self.log(f"  C->S: Finished (encrypted, MAC verified)")
        self.log(f"  S->C: ChangeCipherSpec")
        self.log(f"  S->C: Finished (encrypted, MAC verified)")
        self.state = TLSState.ESTABLISHED
        self.log(f"  State: ESTABLISHED (total RTTs: {self.rtt_count})")

    def tls13_handshake(self) -> None:
        self.log("=== TLS 1.3 Handshake (1-RTT) ===")
        self.log("RTT 1:")
        self.state = TLSState.CLIENT_HELLO_SENT
        self.client_hello = ClientHello(
            version="TLS 1.3",
            cipher_suites=["TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256"],
            extensions=["key_share (ECDHE)", "supported_versions", "psk_key_exchange_modes"],
            supported_versions=["TLS 1.3", "TLS 1.2"],
        )
        self.rtt_count += 1
        self.log(f"  C->S: ClientHello (version={self.client_hello.version}, "
                 f"key_share included in first message)")

        self.server_hello = ServerHello(
            version="TLS 1.3",
            cipher_suite="TLS_AES_256_GCM_SHA384",
            session_id="",
            extensions=["key_share (ECDHE)"],
        )
        self.state = TLSState.SERVER_HELLO_SENT
        self.log(f"  S->C: ServerHello (cipher={self.server_hello.cipher_suite}, key_share included)")
        self.state = TLSState.KEY_EXCHANGED
        self.shared_secret = "derived_from_ECDHE_1rtt"
        self.log(f"  S->C: {EncryptedExtensions()}")
        self.cert = Certificate(subject="example.com", issuer="Let's Encrypt", public_key="ECDSA-P256", valid=True)
        self.state = TLSState.CERT_SENT
        self.log(f"  S->C: Certificate (encrypted, subject={self.cert.subject})")
        self.log(f"  S->C: CertificateVerify (signature over handshake)")
        self.log(f"  S->C: Finished (encrypted)")
        self.log(f"  C->S: Finished (encrypted)")
        self.state = TLSState.FINISHED
        self.state = TLSState.ESTABLISHED
        self.log(f"  State: ESTABLISHED (total RTTs: {self.rtt_count})")

    def tls13_psk_resumption(self) -> None:
        self.log("=== TLS 1.3 PSK Resumption (0-RTT) ===")
        self.rtt_count = 0
        self.log(f"  C->S: ClientHello + early_data (PSK ticket from prior session)")
        self.log(f"  S->C: ServerHello + application data (0-RTT accepted)")
        self.state = TLSState.ESTABLISHED
        self.log(f"  State: ESTABLISHED (total RTTs: {self.rtt_count} - early data sent immediately)")
        self.log(f"  Warning: 0-RTT data is not forward-secret and vulnerable to replay.")


class EncryptedExtensions:
    def __str__(self) -> str:
        return "EncryptedExtensions (server_name, ALPN=h2)"


class Action(Enum):
    ACCEPT = auto()
    DENY = auto()
    REJECT = auto()


class Direction(Enum):
    INBOUND = auto()
    OUTBOUND = auto()


@dataclass
class FirewallRule:
    id: int
    direction: Direction
    src_ip: Optional[str]
    dst_ip: Optional[str]
    port: Optional[int]
    protocol: Optional[str]
    action: Action
    description: str


@dataclass
class Packet:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    direction: Direction


@dataclass
class Connection:
    key: str
    state: str = "NEW"
    packets: int = 0


class Firewall:
    def __init__(self) -> None:
        self.rules: list[FirewallRule] = []
        self.connections: dict[str, Connection] = {}
        self.default_action = Action.DENY

    def add_rule(self, rule: FirewallRule) -> None:
        self.rules.append(rule)

    def _matches(self, rule: FirewallRule, pkt: Packet) -> bool:
        if rule.direction != pkt.direction:
            return False
        if rule.src_ip and rule.src_ip != pkt.src_ip:
            return False
        if rule.dst_ip and rule.dst_ip != pkt.dst_ip:
            return False
        if rule.port and rule.port != pkt.dst_port:
            return False
        if rule.protocol and rule.protocol != pkt.protocol:
            return False
        return True

    def filter_packet(self, pkt: Packet) -> Action:
        for rule in self.rules:
            if self._matches(rule, pkt):
                return rule.action
        return self.default_action

    def stateful_filter(self, pkt: Packet) -> tuple[Action, str]:
        conn_key = f"{pkt.src_ip}:{pkt.src_port}->{pkt.dst_ip}:{pkt.dst_port}"
        if pkt.protocol == "TCP" and pkt.dst_port == 80:
            if conn_key not in self.connections:
                self.connections[conn_key] = Connection(key=conn_key, state="ESTABLISHED")
                return Action.ACCEPT, f"NEW connection {conn_key} -> ESTABLISHED"
            else:
                self.connections[conn_key].packets += 1
                return Action.ACCEPT, f"ESTABLISHED {conn_key} (pkt #{self.connections[conn_key].packets})"
        action = self.filter_packet(pkt)
        reason = f"rule matched, action={action.name}"
        return action, reason


def review_policy(fw: Firewall) -> list[str]:
    findings: list[str] = []
    for rule in fw.rules:
        if rule.src_ip is None and rule.dst_ip is None and rule.port is None and rule.protocol is None:
            if rule.action == Action.ACCEPT:
                findings.append(f"  CRITICAL: Rule {rule.id} is a catch-all ALLOW - "
                                f"overrides default deny for {rule.direction.name}")
        if rule.action == Action.ACCEPT and rule.port == 22 and rule.src_ip is None:
            findings.append(f"  HIGH: Rule {rule.id} allows SSH from ANY source")
        if rule.action == Action.ACCEPT and rule.port == 3389 and rule.src_ip is None:
            findings.append(f"  HIGH: Rule {rule.id} allows RDP from ANY source")
        if rule.action == Action.ACCEPT and rule.port is None and rule.protocol is None:
            findings.append(f"  MEDIUM: Rule {rule.id} allows all ports/protocols from "
                            f"src={rule.src_ip} to dst={rule.dst_ip}")
    if fw.default_action == Action.ACCEPT:
        findings.append("  CRITICAL: Default action is ACCEPT - firewall is effectively open")
    if not findings:
        findings.append("  PASS: No critical policy issues found")
    return findings


def main() -> None:
    print("=" * 65)
    print("TLS Handshake Lab")
    print("=" * 65)

    print("\n--- TLS 1.2 Handshake (2-RTT, RSA or ECDHE key exchange) ---")
    hs12 = TLSHandshake()
    hs12.tls12_handshake()
    for msg in hs12.messages:
        print(f"  {msg}")

    print("\n--- TLS 1.3 Handshake (1-RTT, ECDHE only) ---")
    hs13 = TLSHandshake()
    hs13.tls13_handshake()
    for msg in hs13.messages:
        print(f"  {msg}")

    print("\n--- TLS 1.3 PSK Resumption (0-RTT) ---")
    hs13_psk = TLSHandshake()
    hs13_psk.tls13_psk_resumption()
    for msg in hs13_psk.messages:
        print(f"  {msg}")

    print(f"\n  TLS Version Comparison:")
    print(f"  {'Version':10s} {'RTTs':>5s} {'Key Exchange':20s} {'Forward Secrecy':15s} {'0-RTT'}")
    print(f"  {'-'*10} {'-'*5} {'-'*20} {'-'*15} {'-'*6}")
    print(f"  {'TLS 1.2':10s} {'2':>5s} {'RSA or ECDHE':20s} {'Only with ECDHE':15s} {'No'}")
    print(f"  {'TLS 1.3':10s} {'1':>5s} {'ECDHE only':20s} {'Yes (always)':15s} {'Yes (PSK)'}")

    print()
    print("=" * 65)
    print("Firewall Policy Review Lab")
    print("=" * 65)

    fw = Firewall()
    fw.add_rule(FirewallRule(1, Direction.INBOUND, None, None, 80, "TCP", Action.ACCEPT,
                             "Allow HTTP from anywhere"))
    fw.add_rule(FirewallRule(2, Direction.INBOUND, None, None, 443, "TCP", Action.ACCEPT,
                             "Allow HTTPS from anywhere"))
    fw.add_rule(FirewallRule(3, Direction.INBOUND, "10.0.0.5", None, 22, "TCP", Action.ACCEPT,
                             "Allow SSH from admin only"))
    fw.add_rule(FirewallRule(4, Direction.INBOUND, None, None, None, None, Action.DENY,
                             "Default deny all other inbound"))
    fw.add_rule(FirewallRule(5, Direction.OUTBOUND, None, None, None, None, Action.ACCEPT,
                             "Allow all outbound"))

    print(f"\n  Firewall rules ({len(fw.rules)} total, default={fw.default_action.name}):")
    for r in fw.rules:
        src = r.src_ip or "ANY"
        dst = r.dst_ip or "ANY"
        port = r.port or "ANY"
        proto = r.protocol or "ANY"
        print(f"    #{r.id} {r.direction.name:8s} {src:12s} {dst:12s} port={str(port):5s} "
              f"proto={proto:5s} -> {r.action.name:6s}  ({r.description})")

    print(f"\n  Packet filtering tests:")
    test_packets = [
        Packet("1.2.3.4", "10.0.0.1", 50000, 80, "TCP", Direction.INBOUND),
        Packet("1.2.3.4", "10.0.0.1", 50001, 443, "TCP", Direction.INBOUND),
        Packet("1.2.3.4", "10.0.0.1", 50002, 22, "TCP", Direction.INBOUND),
        Packet("10.0.0.5", "10.0.0.1", 50003, 22, "TCP", Direction.INBOUND),
        Packet("1.2.3.4", "10.0.0.1", 50004, 3389, "TCP", Direction.INBOUND),
        Packet("10.0.0.1", "8.8.8.8", 40000, 53, "UDP", Direction.OUTBOUND),
    ]
    for pkt in test_packets:
        action = fw.filter_packet(pkt)
        print(f"    {pkt.direction.name:8s} {pkt.src_ip:12s}:{pkt.src_port:5d} -> "
              f"{pkt.dst_ip:12s}:{pkt.dst_port:5d} {pkt.protocol:4s} -> {action.name}")

    print(f"\n  Stateful inspection (HTTP connection tracking):")
    http1 = Packet("1.2.3.4", "10.0.0.1", 50000, 80, "TCP", Direction.INBOUND)
    http2 = Packet("1.2.3.4", "10.0.0.1", 50000, 80, "TCP", Direction.INBOUND)
    http3 = Packet("1.2.3.4", "10.0.0.1", 50000, 80, "TCP", Direction.INBOUND)
    for i, pkt in enumerate([http1, http2, http3], 1):
        action, reason = fw.stateful_filter(pkt)
        print(f"    Packet {i}: {action.name:6s} - {reason}")

    print(f"\n  Policy review findings:")
    fw_bad = Firewall()
    fw_bad.add_rule(FirewallRule(1, Direction.INBOUND, None, None, None, None, Action.ACCEPT,
                                 "Allow everything inbound (DANGEROUS)"))
    fw_bad.add_rule(FirewallRule(2, Direction.INBOUND, None, None, 22, "TCP", Action.ACCEPT,
                                 "Allow SSH from anywhere"))
    fw_bad.add_rule(FirewallRule(3, Direction.INBOUND, None, None, 3389, "TCP", Action.ACCEPT,
                                 "Allow RDP from anywhere"))
    findings = review_policy(fw_bad)
    for f in findings:
        print(f"    {f}")

    print(f"\n  Good policy review:")
    findings_good = review_policy(fw)
    for f in findings_good:
        print(f"    {f}")


if __name__ == "__main__":
    main()
