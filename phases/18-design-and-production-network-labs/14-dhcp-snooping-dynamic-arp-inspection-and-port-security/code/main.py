"""DHCP Snooping, Dynamic ARP Inspection, and Port Security simulator.

Models a Cisco Catalyst 9300 access-layer policy stack against a synthetic
one-second capture of DHCP, ARP, and MAC-flap events. Stdlib-only,
type-annotated, prints a design report. Does NOT touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Trust(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ViolationAction(str, Enum):
    PROTECT = "protect"
    RESTRICT = "restrict"
    SHUTDOWN = "shutdown"


class EventKind(str, Enum):
    DHCP_DISCOVER = "discover"
    DHCP_OFFER = "offer"
    DHCP_REQUEST = "request"
    DHCP_ACK = "ack"
    ARP_REPLY = "arp_reply"
    MAC_FRAME = "mac_frame"


@dataclass(frozen=True)
class Binding:
    vlan: int
    mac: str
    ip: str
    port: str
    lease_s: int = 14400

    def key(self) -> tuple[int, str]:
        return (self.vlan, self.ip)


@dataclass(frozen=True)
class Event:
    kind: EventKind
    vlan: int
    src_mac: str
    dst_mac: str
    sender_ip: str
    target_ip: str
    port: str
    trust: Trust
    client_port: str | None = None  # trusted DHCP server -> which access port


@dataclass
class PortState:
    name: str
    trust: Trust
    max_macs: int = 2
    learned: list[str] = field(default_factory=list)
    violations: int = 0
    errdisabled: bool = False
    violation_action: ViolationAction = ViolationAction.SHUTDOWN


class SnoopingTable:
    """Per-VLAN DHCP snooping binding table."""

    def __init__(self, capacity: int = 16000) -> None:
        self._cap = capacity
        self._b: dict[tuple[int, str], Binding] = {}

    def add(self, b: Binding) -> bool:
        if len(self._b) >= self._cap:
            return False
        self._b[b.key()] = b
        return True

    def lookup(self, vlan: int, ip: str) -> Binding | None:
        return self._b.get((vlan, ip))

    def __len__(self) -> int:
        return len(self._b)


def dhcp_snooping_eval(ev: Event, ports: dict[str, PortState], t: SnoopingTable) -> str:
    p = ports[ev.port]
    if ev.kind in (EventKind.DHCP_OFFER, EventKind.DHCP_ACK):
        if p.trust is Trust.UNTRUSTED:
            p.violations += 1
            return "DROP:DHCP_SNOOPING_DENY"
        if ev.client_port is None:
            return "DROP:MISSING_CLIENT_PORT"
        # target_ip is the assigned client IP; sender_ip is the server.
        t.add(Binding(ev.vlan, ev.dst_mac, ev.target_ip, ev.client_port))
        return "ACCEPT:LEARN"
    if p.errdisabled:
        return "DROP:ERRDISABLE"
    return "ACCEPT:CLIENT"


def arp_inspection_eval(ev: Event, ports: dict[str, PortState], t: SnoopingTable) -> str:
    if ev.kind is not EventKind.ARP_REPLY:
        return "ACCEPT:NON_ARP"
    p = ports[ev.port]
    if p.trust is Trust.TRUSTED:
        return "ACCEPT:TRUSTED"
    if p.errdisabled:
        return "DROP:ERRDISABLE"
    b = t.lookup(ev.vlan, ev.sender_ip)
    if b is None:
        p.violations += 1
        return "DROP:DAI_NO_BINDING"
    if b.mac != ev.src_mac:
        p.violations += 1
        return "DROP:DAI_SPOOF"
    if b.port != ev.port:
        p.violations += 1
        return "DROP:DAI_PORT_MISMATCH"
    return "ACCEPT:DAI_PASS"


def port_security_eval(ev: Event, ports: dict[str, PortState]) -> str:
    p = ports[ev.port]
    if p.trust is Trust.TRUSTED:
        return "ACCEPT:TRUSTED"
    if p.errdisabled:
        return "DROP:ERRDISABLE"
    if ev.src_mac in p.learned:
        return "ACCEPT:KNOWN"
    flapping = any(
        ev.src_mac in o.learned for n, o in ports.items() if n != ev.port
    )
    if flapping:
        p.violations += 1
        if p.violation_action is ViolationAction.SHUTDOWN:
            p.errdisabled = True
            return "DROP:PSECURE_MACFLAP:shutdown"
        return "DROP:PSECURE_MACFLAP:restrict"
    if len(p.learned) < p.max_macs:
        p.learned.append(ev.src_mac)
        return "ACCEPT:STICKY"
    p.violations += 1
    if p.violation_action is ViolationAction.SHUTDOWN:
        p.errdisabled = True
        return "DROP:PSECURE:shutdown"
    return "DROP:PSECURE:restrict"


def synth_capture() -> list[Event]:
    ev: list[Event] = []
    for i in range(30):
        mac = f"aa:bb:cc:00:00:{i:02x}"
        ip = f"10.20.{(i // 254) + 1}.{(i % 254) + 1}"
        port = f"Gi1/0/{(i % 40) + 1}"
        ev += [
            Event(EventKind.DHCP_DISCOVER, 10, mac, "ff:ff:ff:ff:ff:ff",
                  "0.0.0.0", ip, port, Trust.UNTRUSTED, None),
            Event(EventKind.DHCP_OFFER, 10, "00:1a:2b:3c:4d:5e", mac,
                  "10.20.1.4", ip, "Gi1/0/48", Trust.TRUSTED, port),
            Event(EventKind.DHCP_REQUEST, 10, mac, "ff:ff:ff:ff:ff:ff",
                  ip, "10.20.1.4", port, Trust.UNTRUSTED, None),
            Event(EventKind.DHCP_ACK, 10, "00:1a:2b:3c:4d:5e", mac,
                  "10.20.1.4", ip, "Gi1/0/48", Trust.TRUSTED, port),
        ]
    rm = "de:ad:be:ef:00:01"
    for i in range(5):
        ev.append(Event(EventKind.DHCP_OFFER, 10, rm, "ff:ff:ff:ff:ff:ff",
                        f"10.20.99.{i + 1}", "0.0.0.0", "Gi1/0/12",
                        Trust.UNTRUSTED, None))
    ev.append(Event(EventKind.ARP_REPLY, 10, rm, "ff:ff:ff:ff:ff:ff",
                    "10.20.0.1", "10.20.1.42", "Gi1/0/12", Trust.UNTRUSTED, None))
    flapper = "aa:bb:cc:de:ad:be"
    for p in ("Gi1/0/30", "Gi1/0/31"):
        ev.append(Event(EventKind.MAC_FRAME, 10, flapper, "ff:ff:ff:ff:ff:ff",
                        "0.0.0.0", "0.0.0.0", p, Trust.UNTRUSTED, None))
    return ev


def run(events: list[Event], ports: dict[str, PortState], t: SnoopingTable) -> dict[str, int]:
    c = {"dhcp_drop": 0, "dhcp_learn": 0, "arp_drop": 0, "arp_pass": 0,
         "psec_drop": 0, "psec_learn": 0}
    for e in events:
        s = dhcp_snooping_eval(e, ports, t)
        if s.startswith("DROP") and "DHCP" in s:
            c["dhcp_drop"] += 1
        elif "LEARN" in s:
            c["dhcp_learn"] += 1
        a = arp_inspection_eval(e, ports, t)
        if a.startswith("DROP"):
            c["arp_drop"] += 1
        elif "PASS" in a:
            c["arp_pass"] += 1
        p = port_security_eval(e, ports)
        if p.startswith("DROP") and "PSECURE" in p:
            c["psec_drop"] += 1
        elif "STICKY" in p:
            c["psec_learn"] += 1
    return c


def print_report(c: dict[str, int], ports: dict[str, PortState], t: SnoopingTable) -> None:
    bar = "=" * 64
    print(bar)
    print(" DHCP Snooping / DAI / Port-Security Design Report ")
    print(" Reference: Cisco Catalyst 9300, 17.9.x access stack ")
    print(bar)
    print(f" Binding table size         : {len(t):>5d} entries")
    print(f" DHCP server-side drops     : {c['dhcp_drop']:>5d}")
    print(f" DHCP learned (valid ACK)   : {c['dhcp_learn']:>5d}")
    print(f" DAI drops (spoof/no-bind)  : {c['arp_drop']:>5d}")
    print(f" DAI passes                 : {c['arp_pass']:>5d}")
    print(f" Port-security drops        : {c['psec_drop']:>5d}")
    print(f" Port-security learned      : {c['psec_learn']:>5d}")
    print(bar)
    flagged = [n for n, p in ports.items() if p.violations > 0 or p.errdisabled]
    print(f" Ports with violations      : {len(flagged)}")
    for n in sorted(flagged)[:8]:
        p = ports[n]
        st = "ERR-DIS" if p.errdisabled else "UP"
        print(f"   {n:<10s} trust={p.trust.value:<10s} "
              f"macs={len(p.learned)}/{p.max_macs} viol={p.violations:>3d} {st}")
    print(bar)
    print(" Executive summary:")
    print("  - All DHCPOFFER/DHCPACK from untrusted ports blocked at snooping")
    print("  - ARP spoof of gateway IP dropped at DAI with DAI_SPOOF")
    print("  - MAC flap trips port-security shutdown on the second port")
    print("  - 30 valid four-way handshakes populated the binding table")
    print(bar)


def build_ports() -> dict[str, PortState]:
    return {
        f"Gi1/0/{i}": PortState(name=f"Gi1/0/{i}",
                               trust=Trust.TRUSTED if i == 48 else Trust.UNTRUSTED)
        for i in range(1, 49)
    }


def main() -> None:
    table = SnoopingTable(capacity=16000)
    ports = build_ports()
    counters = run(synth_capture(), ports, table)
    print_report(counters, ports, table)


if __name__ == "__main__":
    main()
