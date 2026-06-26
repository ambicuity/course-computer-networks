"""Firewall rule matcher and VPN tunnel simulator.

Evaluates packets against stateless and stateful rule sets,
demonstrates the DMZ architecture, and simulates a TCP SYN-flood
DoS attack that exhausts connection table slots.
stdlib-only, educational — no real network calls.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class ConnState(Enum):
    SYN_SENT = "SYN_SENT"
    SYN_ACK = "SYN_ACK"
    ESTABLISHED = "ESTABLISHED"
    CLOSED = "CLOSED"


@dataclass
class FirewallRule:
    """A single packet-filter rule."""
    name: str
    src_ip: str          # "*" = any
    dst_ip: str          # "*" = any
    dst_port: int        # 0 = any
    protocol: str        # "TCP", "UDP", "*"
    action: Action
    stateful: bool = False


@dataclass
class Connection:
    """A tracked TCP connection (for stateful firewall)."""
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    state: ConnState = ConnState.CLOSED


class StatelessFirewall:
    """Matches each packet independently against a rule list."""

    def __init__(self, rules: list[FirewallRule], default: Action = Action.DENY):
        self.rules = rules
        self.default = default

    def evaluate(self, src_ip: str, dst_ip: str, dst_port: int,
                 protocol: str = "TCP") -> tuple[Action, str]:
        for rule in self.rules:
            if rule.stateful:
                continue
            if (self._match(rule.src_ip, src_ip) and
                    self._match(rule.dst_ip, dst_ip) and
                    (rule.dst_port == 0 or rule.dst_port == dst_port) and
                    (rule.protocol == "*" or rule.protocol == protocol)):
                return rule.action, rule.name
        return self.default, "default-deny"

    @staticmethod
    def _match(pattern: str, value: str) -> bool:
        return pattern == "*" or pattern == value


class StatefulFirewall(StatelessFirewall):
    """Tracks TCP connections to allow return traffic only if initiated internally."""

    def __init__(self, rules: list[FirewallRule], internal_nets: set[str],
                 default: Action = Action.DENY):
        super().__init__(rules, default)
        self.connections: dict[tuple, Connection] = {}
        self.internal_nets = internal_nets

    def process_packet(self, src_ip: str, src_port: int, dst_ip: str,
                       dst_port: int, flags: str = "SYN") -> tuple[Action, str]:
        key = (src_ip, src_port, dst_ip, dst_port)
        internal_initiated = src_ip in self.internal_nets

        if flags == "SYN" and internal_initiated:
            conn = Connection(src_ip, src_port, dst_ip, dst_port,
                               ConnState.SYN_SENT)
            self.connections[key] = conn
            return Action.ALLOW, "stateful: internal SYN -> tracked"

        if flags == "SYN+ACK" and not internal_initiated:
            rev_key = (dst_ip, dst_port, src_ip, src_port)
            conn = self.connections.get(rev_key)
            if conn and conn.state == ConnState.SYN_SENT:
                conn.state = ConnState.ESTABLISHED
                return Action.ALLOW, "stateful: SYN+ACK for tracked conn"
            return Action.DENY, "stateful: SYN+ACK without matching SYN"

        if flags == "ACK" and not internal_initiated:
            rev_key = (dst_ip, dst_port, src_ip, src_port)
            if rev_key in self.connections:
                return Action.ALLOW, "stateful: return traffic for tracked conn"
            return Action.DENY, "stateful: no tracked conn for return"

        # Fall through to stateless rules
        return self.evaluate(src_ip, dst_ip, dst_port)


def build_demo_rules() -> list[FirewallRule]:
    return [
        FirewallRule("allow-dmz-web", "*", "10.0.0.100", 80, "TCP", Action.ALLOW),
        FirewallRule("allow-out-http", "192.168.1.0", "*", 80, "TCP", Action.ALLOW),
        FirewallRule("allow-out-https", "192.168.1.0", "*", 443, "TCP", Action.ALLOW),
        FirewallRule("block-finger", "*", "*", 79, "TCP", Action.DENY),
        FirewallRule("block-internal-80", "*", "192.168.1.0", 80, "TCP", Action.DENY),
    ]


class SynFloodSimulator:
    """Simulates a TCP SYN-flood DoS attack exhausting connection slots."""

    def __init__(self, table_size: int = 4096, timeout_s: int = 60):
        self.table_size = table_size
        self.timeout_s = timeout_s
        self.table: dict[int, float] = {}

    def syn(self, seq: int, t: float) -> bool:
        if len(self.table) >= self.table_size:
            return False  # table full, packet dropped
        self.table[seq] = t
        return True

    def expire(self, t: float) -> int:
        expired = [s for s, ts in self.table.items() if t - ts > self.timeout_s]
        for s in expired:
            del self.table[s]
        return len(expired)

    def available_slots(self) -> int:
        return self.table_size - len(self.table)


def main() -> None:
    print("=" * 72)
    print("Firewall Rule Matcher and VPN Tunnel Simulator")
    print("=" * 72)

    rules = build_demo_rules()
    fw = StatelessFirewall(rules)

    print("\n[Stateless Firewall — DMZ rules]\n")
    tests = [
        ("External", "1.2.3.4", "10.0.0.100", 80, "inbound web to DMZ"),
        ("External", "1.2.3.4", "192.168.1.5", 80, "inbound web to internal (blocked)"),
        ("External", "1.2.3.4", "10.0.0.50", 79, "Finger (blocked)"),
        ("Internal", "192.168.1.10", "8.8.8.8", 443, "outbound HTTPS"),
        ("Internal", "192.168.1.10", "8.8.8.8", 25, "outbound SMTP (default-deny)"),
    ]
    for label, src, dst, port, desc in tests:
        action, rule = fw.evaluate(src, dst, port)
        status = "PASS" if action == Action.ALLOW else "DROP"
        print(f"  [{status}] {desc}: {src}:{port} -> {dst} ({rule})")

    # --- Stateful firewall ---
    print("\n[Stateful Firewall — connection tracking]\n")
    sfw = StatefulFirewall(rules, internal_nets={"192.168.1.10"})
    a1 = sfw.process_packet("192.168.1.10", 5000, "8.8.8.8", 443, "SYN")
    print(f"  internal SYN -> {a1[0].value}: {a1[1]}")
    a2 = sfw.process_packet("8.8.8.8", 443, "192.168.1.10", 5000, "SYN+ACK")
    print(f"  external SYN+ACK -> {a2[0].value}: {a2[1]}")
    a3 = sfw.process_packet("8.8.8.8", 443, "192.168.1.10", 5000, "ACK")
    print(f"  external ACK (data) -> {a3[0].value}: {a3[1]}")
    a4 = sfw.process_packet("8.8.8.8", 443, "192.168.1.10", 22, "SYN")
    print(f"  unsolicited external SYN to port 22 -> {a4[0].value}: {a4[1]}")

    # --- SYN flood ---
    print("\n[SYN Flood DoS Simulation]\n")
    sim = SynFloodSimulator(table_size=100, timeout_s=60)
    flood_rate = 500  # SYNs/sec
    duration = 5      # seconds
    for t in range(duration):
        for i in range(flood_rate):
            sim.syn(t * flood_rate + i, float(t))
        avail = sim.available_slots()
        legit_ok = sim.syn(-1, float(t))  # one legit connection attempt
        print(f"  t={t}s: table={len(sim.table)}/{sim.table_size} "
              f"available={avail} legit={'OK' if legit_ok else 'BLOCKED'}")

    # --- VPN tunnel ---
    print("\n[VPN Tunnel — IPsec ESP tunnel mode]\n")
    offices = ["London", "Paris", "Tokyo"]
    print("  Offices:", ", ".join(offices))
    print("  Topology: full mesh of IPsec ESP tunnel-mode SAs")
    n_sas = len(offices) * (len(offices) - 1)
    print(f"  Bidirectional SAs needed: {n_sas} (2 per pair x {len(offices)}C2 pairs)")
    for i, a in enumerate(offices):
        for j, b in enumerate(offices):
            if i < j:
                spi = 0xC0FF0000 + i * 16 + j
                print(f"  SA 0x{spi:08X}: {a}-firewall <-> {b}-firewall (ESP tunnel)")

    print("\n  VPN is transparent to user software: only the firewall admin")
    print("  and the ISP admin (for MPLS) are aware of the tunnels.")
    print("=" * 72)


if __name__ == "__main__":
    main()
