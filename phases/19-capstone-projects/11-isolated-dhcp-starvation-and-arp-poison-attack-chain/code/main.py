#!/usr/bin/env python3
"""Capstone 11: Isolated DHCP Starvation and ARP Poison Attack Chain.

Simulates the two-phase L2 attack chain (DHCP starvation -> ARP poisoning),
runs detection logic, and applies three mitigations (DHCP snooping, DAI,
port security).

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Optional

random.seed(42)

GATEWAY_IP, GATEWAY_MAC = "10.0.0.1", "00:00:00:00:00:01"
DHCP_SERVER_IP = "10.0.0.2"
POOL_START, POOL_END, ATTACKER_MAC = 10, 254, "AA:AA:AA:AA:AA:AA"


class Msg(Enum):
    DISCOVER = "DISCOVER"; OFFER = "OFFER"; REQUEST = "REQUEST"; ACK = "ACK"; NAK = "NAK"


@dataclass
class Lease:
    ip: str; mac: str; t: float; legit: bool = True


@dataclass
class ArpEntry:
    ip: str; mac: str; gratuitous: bool = False; poisoned: bool = False


@dataclass
class SwitchPort:
    pid: str; device: str; trusted: bool = False; mac_limit: int = 1
    learned: set[str] = field(default_factory=set)
    dhcp_rate_limit: int = 10; blocked: bool = False


@dataclass
class DhcpMsg:
    msg: Msg; smac: str; offered: str = ""; forged: bool = False


@dataclass
class Ev:
    phase: str; etype: str; desc: str; sev: str = "INFO"


@dataclass
class Server:
    pool: dict[str, Optional[Lease]] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        for i in range(POOL_START, POOL_END + 1):
            self.pool[f"10.0.0.{i}"] = None

    @property
    def size(self): return len(self.pool)
    @property
    def used(self): return sum(1 for v in self.pool.values() if v is not None)
    @property
    def free(self): return sum(1 for v in self.pool.values() if v is None)
    @property
    def util(self): return self.used / self.size * 100 if self.size else 0.0

    def alloc(self, mac, t, legit=True):
        for ip, lease in self.pool.items():
            if lease is None:
                self.pool[ip] = Lease(ip, mac, t, legit)
                self.bindings[ip] = mac
                return ip
        return None


def fmac(): return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))


def simulate_normal_dora(srv, mac, t, msgs):
    msgs.append(DhcpMsg(Msg.DISCOVER, mac))
    ip = srv.alloc(mac, t, legit=True)
    if not ip:
        msgs.append(DhcpMsg(Msg.NAK, mac)); return None
    msgs.append(DhcpMsg(Msg.OFFER, mac, offered=ip))
    msgs.append(DhcpMsg(Msg.REQUEST, mac, offered=ip))
    msgs.append(DhcpMsg(Msg.ACK, mac, offered=ip))
    return ip


def simulate_starvation(srv, t, msgs, events):
    forged = 0
    for i in range(300):
        m = fmac()
        msgs.append(DhcpMsg(Msg.DISCOVER, m, forged=True))
        if srv.free > 0:
            ip = srv.alloc(m, t, legit=False)
            msgs.append(DhcpMsg(Msg.OFFER, m, offered=ip, forged=True))
            msgs.append(DhcpMsg(Msg.ACK, m, offered=ip, forged=True))
            forged += 1
        else:
            msgs.append(DhcpMsg(Msg.NAK, m, forged=True))
        if i == 0:
            events.append(Ev("Starvation", "Attack Start", "DHCP starvation begins", "CRITICAL"))
        if srv.util >= 90 and i > 0:
            events.append(Ev("Starvation", "Pool Near Exhaustion",
                             f"Pool at {srv.util:.0f}%", "CRITICAL"))
            break
        if srv.free == 0:
            events.append(Ev("Starvation", "Pool Exhausted",
                             f"Pool empty after {forged} forged leases", "CRITICAL"))
            break
    return forged


def simulate_arp_poison(victims, caches, arp_log, events):
    events.append(Ev("ARP Poison", "Attack Start", "Gratuitous ARP flood begins", "CRITICAL"))
    for mac in victims:
        e = ArpEntry(GATEWAY_IP, ATTACKER_MAC, gratuitous=True, poisoned=True)
        caches[mac][GATEWAY_IP] = e; arp_log.append(e)
        events.append(Ev("ARP Poison", "Cache Poisoned",
                         f"Victim {mac} -> gateway = attacker", "CRITICAL"))
    return len(victims)


def detect_starvation(srv, msgs, events):
    if srv.util > 90:
        events.append(Ev("Detection", "High Pool Utilization",
                         f"DHCP pool at {srv.util:.0f}%", "CRITICAL"))
    forged = [m for m in msgs if m.forged and m.msg == Msg.DISCOVER]
    if len(forged) > 50:
        ouis = {m.smac[:8] for m in forged}
        events.append(Ev("Detection", "Forged MAC Pattern",
                         f"{len(forged)} Discovers, {len(ouis)} OUIs", "CRITICAL"))


def detect_arp_poison(arp_log, events):
    c = [a for a in arp_log if a.gratuitous and a.poisoned]
    if c:
        events.append(Ev("Detection", "ARP Cache Poisoning",
                         f"{len(c)} gratuitous ARPs vs binding table", "CRITICAL"))


def apply_dhcp_snooping(ports, events):
    s = {"blocked_offers": 0, "rate_limited": 0}
    for p in ports.values():
        if p.device == "attacker" and not p.trusted:
            p.blocked = True
            s["blocked_offers"] += 100; s["rate_limited"] += 300
            events.append(Ev("Mitigation", "DHCP Snooping",
                             f"Port {p.pid} untrusted, rate-limited to {p.dhcp_rate_limit}/s",
                             "WARNING"))
    return s


def apply_dai(arp_log, gw_mac, events):
    d = v = 0
    for a in arp_log:
        if a.gratuitous and a.mac != gw_mac: d += 1
        else: v += 1
    events.append(Ev("Mitigation", "Dynamic ARP Inspection",
                     f"DAI dropped {d} ARPs, validated {v}", "WARNING"))
    return {"dropped_arp": d, "validated_arp": v}


def apply_port_security(ports, events):
    b = violations = 0
    for p in ports.values():
        if p.device == "attacker" and not p.trusted:
            p.blocked = True
            p.learned.update({ATTACKER_MAC, fmac()})
            violations += 1
            if len(p.learned) > p.mac_limit:
                b += 1
                events.append(Ev("Mitigation", "Port Security",
                                 f"Port {p.pid} err-disabled (MAC limit {p.mac_limit})",
                                 "WARNING"))
    return {"blocked_ports": b, "mac_violations": violations}


@dataclass
class Server:
    pool: dict[str, Optional[Lease]] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        for i in range(POOL_START, POOL_END + 1):
            self.pool[f"10.0.0.{i}"] = None

    @property
    def size(self): return len(self.pool)
    @property
    def used(self): return sum(1 for v in self.pool.values() if v is not None)
    @property
    def free(self): return sum(1 for v in self.pool.values() if v is None)
    @property
    def util(self): return self.used / self.size * 100 if self.size else 0.0

    def alloc(self, mac, t, legit=True):
        for ip, lease in self.pool.items():
            if lease is None:
                self.pool[ip] = Lease(ip, mac, t, legit)
                self.bindings[ip] = mac
                return ip
        return None


def fmac(): return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))


def simulate_normal_dora(srv, mac, t, msgs):
    msgs.append(DhcpMsg(Msg.DISCOVER, mac))
    ip = srv.alloc(mac, t, legit=True)
    if not ip:
        msgs.append(DhcpMsg(Msg.NAK, mac)); return None
    msgs.append(DhcpMsg(Msg.OFFER, mac, offered=ip))
    msgs.append(DhcpMsg(Msg.REQUEST, mac, offered=ip))
    msgs.append(DhcpMsg(Msg.ACK, mac, offered=ip))
    return ip


def simulate_starvation(srv, t, msgs, events):
    forged = 0
    for i in range(300):
        m = fmac()
        msgs.append(DhcpMsg(Msg.DISCOVER, m, forged=True))
        if srv.free > 0:
            ip = srv.alloc(m, t, legit=False)
            msgs.append(DhcpMsg(Msg.OFFER, m, offered=ip, forged=True))
            msgs.append(DhcpMsg(Msg.ACK, m, offered=ip, forged=True))
            forged += 1
        else:
            msgs.append(DhcpMsg(Msg.NAK, m, forged=True))
        if i == 0:
            events.append(Ev("Starvation", "Attack Start", "DHCP starvation begins", "CRITICAL"))
        if srv.util >= 90 and i > 0:
            events.append(Ev("Starvation", "Pool Near Exhaustion",
                             f"Pool at {srv.util:.0f}%", "CRITICAL"))
            break
        if srv.free == 0:
            events.append(Ev("Starvation", "Pool Exhausted",
                             f"Pool empty after {forged} forged leases", "CRITICAL"))
            break
    return forged


def simulate_arp_poison(victims, caches, arp_log, events):
    events.append(Ev("ARP Poison", "Attack Start", "Gratuitous ARP flood begins", "CRITICAL"))
    for mac in victims:
        e = ArpEntry(GATEWAY_IP, ATTACKER_MAC, gratuitous=True, poisoned=True)
        caches[mac][GATEWAY_IP] = e; arp_log.append(e)
        events.append(Ev("ARP Poison", "Cache Poisoned",
                         f"Victim {mac} -> gateway = attacker", "CRITICAL"))
    return len(victims)


def detect_starvation(srv, msgs, events):
    if srv.util > 90:
        events.append(Ev("Detection", "High Pool Utilization",
                         f"DHCP pool at {srv.util:.0f}%", "CRITICAL"))
    forged = [m for m in msgs if m.forged and m.msg == Msg.DISCOVER]
    if len(forged) > 50:
        ouis = {m.smac[:8] for m in forged}
        events.append(Ev("Detection", "Forged MAC Pattern",
                         f"{len(forged)} Discovers, {len(ouis)} OUIs", "CRITICAL"))


def detect_arp_poison(arp_log, events):
    c = [a for a in arp_log if a.gratuitous and a.poisoned]
    if c:
        events.append(Ev("Detection", "ARP Cache Poisoning",
                         f"{len(c)} gratuitous ARPs vs binding table", "CRITICAL"))


def apply_dhcp_snooping(ports, events):
    s = {"blocked_offers": 0, "rate_limited": 0}
    for p in ports.values():
        if p.device == "attacker" and not p.trusted:
            p.blocked = True
            s["blocked_offers"] += 100; s["rate_limited"] += 300
            events.append(Ev("Mitigation", "DHCP Snooping",
                             f"Port {p.pid} untrusted, rate-limited to {p.dhcp_rate_limit}/s",
                             "WARNING"))
    return s


def apply_dai(arp_log, gw_mac, events):
    d = v = 0
    for a in arp_log:
        if a.gratuitous and a.mac != gw_mac: d += 1
        else: v += 1
    events.append(Ev("Mitigation", "Dynamic ARP Inspection",
                     f"DAI dropped {d} ARPs, validated {v}", "WARNING"))
    return {"dropped_arp": d, "validated_arp": v}


def apply_port_security(ports, events):
    b = violations = 0
    for p in ports.values():
        if p.device == "attacker" and not p.trusted:
            p.blocked = True
            p.learned.update({ATTACKER_MAC, fmac()})
            violations += 1
            if len(p.learned) > p.mac_limit:
                b += 1
                events.append(Ev("Mitigation", "Port Security",
                                 f"Port {p.pid} err-disabled (MAC limit {p.mac_limit})",
                                 "WARNING"))
    return {"blocked_ports": b, "mac_violations": violations}


def main():
    print("=" * 65)
    print("Capstone 11: DHCP Starvation and ARP Poison Attack Chain")
    print("=" * 65)

    srv = Server()
    msgs, events, arp_log = [], [], []
    t = 0.0
    print(f"\n  Network: 10.0.0.0/24  Gateway={GATEWAY_IP}  "
          f"DHCP pool={srv.size}  Attacker MAC={ATTACKER_MAC}")

    print("\n  --- Phase 1: Normal DHCP (10 legitimate clients) ---")
    legals = [f"00:00:00:00:{i:02X}:01" for i in range(1, 11)]
    for mac in legals:
        if simulate_normal_dora(srv, mac, t, msgs): t += 0.05
    print(f"    Pool: {srv.used}/{srv.size} allocated ({srv.util:.1f}%)")

    print("\n  --- Phase 2: DHCP Starvation Attack ---")
    forged = simulate_starvation(srv, t, msgs, events)
    print(f"    Forged leases: {forged}  Pool: {srv.used}/{srv.size} ({srv.util:.1f}%)")

    print("\n  --- Phase 3: Legitimate client 11 fails ---")
    if not simulate_normal_dora(srv, "00:00:00:00:0B:01", t, msgs):
        print("    Client 11: NAK (pool exhausted)")

    print("\n  --- Phase 4: ARP Poisoning ---")
    caches = {m: {GATEWAY_IP: ArpEntry(GATEWAY_IP, GATEWAY_MAC)} for m in legals}
    poisoned = simulate_arp_poison(legals, caches, arp_log, events)
    print(f"    Victims poisoned: {poisoned}")
    for mac in legals[:3]:
        e = caches[mac][GATEWAY_IP]
        print(f"    {mac}: {e.ip} -> {e.mac} [{'POISONED' if e.poisoned else 'OK'}]")

    print("\n  --- Phase 5: Detection ---")
    detect_starvation(srv, msgs, events)
    detect_arp_poison(arp_log, events)
    for e in events[-4:]:
        print(f"    [{e.sev}] {e.etype}: {e.desc}")

    print("\n  --- Phase 6: Mitigation (Snooping + DAI + Port Security) ---")
    ports = {
        "Fa0/1": SwitchPort("Fa0/1", "dhcp_server", trusted=True),
        "Fa0/2": SwitchPort("Fa0/2", "client_1"),
        "Fa0/3": SwitchPort("Fa0/3", "attacker"),
    }
    sn = apply_dhcp_snooping(ports, events)
    dai = apply_dai(arp_log, GATEWAY_MAC, events)
    ps = apply_port_security(ports, events)
    for e in events[-3:]:
        print(f"    [{e.sev}] {e.etype}: {e.desc}")
    print(f"    Snooping: {sn['blocked_offers']} offers blocked, "
          f"{sn['rate_limited']} Discovers rate-limited")
    print(f"    DAI: {dai['dropped_arp']} ARPs dropped, {dai['validated_arp']} validated")
    print(f"    Port Security: {ps['blocked_ports']} port(s) shut down")

    print("\n  --- Phase 7: Post-mitigation recovery ---")
    srv2 = Server()
    for mac in legals[:5]:
        if simulate_normal_dora(srv2, mac, 0.0, []):
            print(f"    {mac} got a lease (legitimate)")
    print(f"    Pool: {srv2.used}/{srv2.size} ({srv2.util:.1f}%)")

    print(f"\n  Summary: starvation {forged} leases, ARP {poisoned} victims; "
          f"detection caught pool exhaustion + MAC entropy + gratuitous ARP; "
          f"mitigations snooping+DAI+port security restored legitimate service.")


if __name__ == "__main__":
    main()