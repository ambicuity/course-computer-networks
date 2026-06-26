"""Packet-filter and stateful firewall (5-tuple state machine).

We model a tiny Packet, a stateless rule engine (first-match-wins), and a
stateful firewall that tracks TCP flows through SYN/SYN-ACK/ACK/FIN/RST.
Both engines share the same rule syntax; the difference is whether they
consult a flow table.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


TCP = "tcp"
UDP = "udp"
ICMP = "icmp"
ANY = "any"


# TCP flag bit masks (subset).
TH_FIN = 0x01
TH_SYN = 0x02
TH_RST = 0x04
TH_ACK = 0x10
SYN = "S"
SYNACK = "SA"
ACK = "A"
FIN = "F"
RST = "R"


@dataclass
class Packet:
    proto: str
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    flags: str = ""

    def reverse(self) -> "Packet":
        return Packet(
            proto=self.proto,
            src_ip=self.dst_ip,
            src_port=self.dst_port,
            dst_ip=self.src_ip,
            dst_port=self.src_port,
            flags=self.flags,
        )


@dataclass
class Rule:
    action: str  # "allow" or "deny"
    src: str
    dst: str
    proto: str
    port: int  # dst port; 0 means any

    def matches(self, pkt: Packet) -> bool:
        if self.proto != ANY and self.proto != pkt.proto:
            return False
        if self.src != ANY and not _ip_in(pkt.src_ip, self.src):
            return False
        if self.dst != ANY and not _ip_in(pkt.dst_ip, self.dst):
            return False
        if self.port != 0 and self.port != pkt.dst_port:
            return False
        return True


def _ip_in(ip: str, spec: str) -> bool:
    if spec == ANY:
        return True
    if "/" in spec:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(spec, strict=False)
    return ip == spec


@dataclass
class Flow:
    key: Tuple
    state: str
    last_seen: float


class StatelessFirewall:
    def __init__(self, rules: List[Rule]) -> None:
        self.rules = rules

    def accept(self, pkt: Packet) -> bool:
        for rule in self.rules:
            if rule.matches(pkt):
                return rule.action == "allow"
        return False


class StatefulFirewall:
    def __init__(self, rules: List[Rule], idle_timeout: float = 60.0) -> None:
        self.rules = rules
        self.idle_timeout = idle_timeout
        self.flows: Dict[Tuple, Flow] = {}

    def _match(self, pkt: Packet) -> bool:
        for rule in self.rules:
            if rule.matches(pkt):
                return rule.action == "allow"
        return False

    def _key(self, pkt: Packet) -> Tuple:
        return (pkt.proto, pkt.src_ip, pkt.src_port, pkt.dst_ip, pkt.dst_port)

    def _rev_key(self, pkt: Packet) -> Tuple:
        return (pkt.proto, pkt.dst_ip, pkt.dst_port, pkt.src_ip, pkt.dst_port)

    def accept(self, pkt: Packet, now: float | None = None) -> bool:
        now = now or time.time()
        if pkt.proto == TCP:
            return self._accept_tcp(pkt, now)
        if pkt.proto == UDP:
            return self._accept_udp(pkt, now)
        if pkt.proto == ICMP:
            return self._accept_icmp(pkt, now)
        return self._match(pkt)

    def _accept_tcp(self, pkt: Packet, now: float) -> bool:
        fwd_key = self._key(pkt)
        rev_key = self._rev_key(pkt)
        flags = pkt.flags
        # Lookup an existing reverse flow (server -> client packet).
        rev_flow = self.flows.get(rev_key)
        if rev_flow is not None:
            rev_flow.last_seen = now
            if "R" in flags:
                rev_flow.state = "CLOSED"
                del self.flows[rev_key]
                return True
            if "F" in flags and rev_flow.state == "ESTABLISHED":
                rev_flow.state = "CLOSE_WAIT"
            return True
        # Lookup the forward flow.
        fwd_flow = self.flows.get(fwd_key)
        if fwd_flow is not None:
            fwd_flow.last_seen = now
            if "R" in flags:
                fwd_flow.state = "CLOSED"
                del self.flows[fwd_key]
                return True
            if flags == SYN:
                return False  # SYN retransmission in our model = ok; allow
            if fwd_flow.state == "SYN_SENT" and flags == SYNACK:
                fwd_flow.state = "ESTABLISHED"
                return True
            if fwd_flow.state == "ESTABLISHED":
                if "F" in flags:
                    fwd_flow.state = "FIN_WAIT_1"
                return True
            return True
        # No flow known. Allow new outbound flows only via policy.
        if flags == SYN and self._match(pkt):
            self.flows[fwd_key] = Flow(fwd_key, "SYN_SENT", now)
            return True
        return False

    def _accept_udp(self, pkt: Packet, now: float) -> bool:
        for key in (self._key(pkt), self._rev_key(pkt)):
            flow = self.flows.get(key)
            if flow is not None:
                flow.last_seen = now
                return True
        if self._match(pkt):
            self.flows[self._key(pkt)] = Flow(self._key(pkt), "OPEN", now)
            return True
        return False

    def _accept_icmp(self, pkt: Packet, now: float) -> bool:
        return self._match(pkt)

    def expire(self, now: float | None = None) -> int:
        now = now or time.time()
        dead = [k for k, f in self.flows.items() if now - f.last_seen > self.idle_timeout]
        for k in dead:
            del self.flows[k]
        return len(dead)


def _build_default_rules() -> List[Rule]:
    return [
        Rule("allow", "10.0.0.0/24", "any", "tcp", 80),
        Rule("allow", "10.0.0.0/24", "any", "tcp", 443),
        Rule("allow", "10.0.0.0/24", "any", "udp", 53),
        Rule("allow", "any", "10.0.0.1", "icmp", 0),
        Rule("deny", "any", "any", ANY, 0),
    ]


def main() -> None:
    """Run a stateless and stateful demonstration side by side."""
    rules = _build_default_rules()
    sw = StatelessFirewall(rules)
    sf = StatefulFirewall(rules, idle_timeout=30.0)

    syn = Packet(TCP, "203.0.113.1", 55555, "10.0.0.5", 443, flags=SYN)
    print(f"stateless SYN outbound: {sw.accept(syn)}")
    print(f"stateful  SYN outbound: {sf.accept(syn)}")

    synack = Packet(TCP, "10.0.0.5", 443, "203.0.113.1", 55555, flags=SYNACK)
    print(f"stateful  SYN-ACK:      {sf.accept(synack)}")
    print(f"flows: {[(k, f.state) for k, f in sf.flows.items()]}")

    unsolicited = Packet(TCP, "198.51.100.7", 4444, "10.0.0.5", 22, flags=SYN)
    print(f"stateless unsolicited inbound SSH: {sw.accept(unsolicited)}")
    print(f"stateful  unsolicited inbound SSH: {sf.accept(unsolicited)}")

    # Tear down.
    fin = Packet(TCP, "203.0.113.1", 55555, "10.0.0.5", 443, flags=FIN)
    print(f"stateful FIN:            {sf.accept(fin)}")
    print(f"flows after FIN: {[(k, f.state) for k, f in sf.flows.items()]}")


if __name__ == "__main__":
    main()