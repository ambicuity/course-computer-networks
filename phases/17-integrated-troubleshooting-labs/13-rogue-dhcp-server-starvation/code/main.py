#!/usr/bin/env python3
"""Rogue DHCP Server and DHCP Starvation (Lab 13).

Simulates a broadcast segment with a legitimate DHCP server, a rogue
server that hands out a malicious gateway, and a starvation attacker
that floods DISCOVERs with forged chaddr values.  A DHCP Snooping +
port-security layer can be toggled to show the remediation.

Run:  python3 code/main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


LEGIT_SERVER_MAC = "00:11:22:33:44:01"
LEGIT_SERVER_IP = "10.0.0.2"
LEGIT_GW = "10.0.0.1"
LEGIT_DNS = "10.0.0.53"
POOL_START = 10
POOL_END = 99
SUBNET = "10.0.0."

ROGUE_SERVER_MAC = "de:ad:be:ef:00:99"
ROGUE_SERVER_IP = "10.0.0.254"
ROGUE_GW = "10.0.0.254"
ROGUE_DNS = "10.0.0.254"


@dataclass
class DhcpOffer:
    server_mac: str
    server_ip: str
    yiaddr: str
    gw: str
    dns: str


@dataclass
class Lease:
    ip: str
    chaddr: str
    arped: bool = False


@dataclass
class DhcpServer:
    server_mac: str
    server_ip: str
    gw: str
    dns: str
    pool: set[str]
    leases: dict[str, Lease] = field(default_factory=dict)
    offers_made: int = 0

    def offer(self, chaddr: str) -> DhcpOffer | None:
        free = sorted(self.pool - set(l.ip for l in self.leases.values()))
        if not free:
            return None
        ip = free[0]
        self.offers_made += 1
        return DhcpOffer(self.server_mac, self.server_ip, ip, self.gw, self.dns)

    def ack(self, chaddr: str, ip: str) -> bool:
        used_ips = {l.ip for l in self.leases.values()}
        if ip in used_ips:
            return False
        self.leases[chaddr] = Lease(ip, chaddr)
        return True


@dataclass
class SnoopingSwitch:
    trusted_server_macs: set[str]
    blocked_offers: int = 0

    def filter_offer(self, offer: DhcpOffer) -> DhcpOffer | None:
        if offer.server_mac in self.trusted_server_macs:
            return offer
        self.blocked_offers += 1
        return None


def simulate_clients(
    legit: DhcpServer,
    rogue: DhcpServer,
    snooping: SnoopingSwitch | None,
    n_clients: int,
) -> None:
    print("=" * 64)
    print("Rogue DHCP + Starvation Simulator")
    print("=" * 64)
    print(f"  Clients             : {n_clients}")
    print(f"  Snooping            : {'ON' if snooping else 'OFF'}")
    print()
    rogue_accepted = 0
    legit_accepted = 0
    no_offer = 0
    for i in range(n_clients):
        chaddr = f"02:00:{i:04x}"
        legit_offer = legit.offer(chaddr)
        rogue_offer = rogue.offer(chaddr)
        if snooping is not None:
            rogue_offer = snooping.filter_offer(rogue_offer) if rogue_offer else None
        # Rogue server typically replies faster (lighter load) so when
        # both offers are present the client often picks the rogue one.
        chosen = None
        if rogue_offer and legit_offer:
            chosen = rogue_offer if (i % 3 != 0) else legit_offer
        else:
            chosen = legit_offer or rogue_offer
        if chosen is None:
            no_offer += 1
            continue
        if chosen.server_mac == rogue.server_mac:
            if rogue.ack(chaddr, chosen.yiaddr):
                rogue_accepted += 1
        else:
            if legit.ack(chaddr, chosen.yiaddr):
                legit_accepted += 1
    print(f"  Legit leases   : {legit_accepted}")
    print(f"  Rogue leases   : {rogue_accepted}")
    print(f"  No offer (pool exhausted) : {no_offer}")
    if snooping:
        print(f"  Rogue offers blocked by snooping: {snooping.blocked_offers}")
    print(f"  Legit pool utilisation: "
          f"{len(legit.leases)}/{len(legit.pool)}")
    if rogue_accepted:
        print("  DIAGNOSIS: ROGUE DHCP SERVER ACTIVE")
        print(f"    {rogue_accepted} clients installed gateway {ROGUE_GW}")
        print("    Remediation: enable DHCP Snooping; trust only uplink port.")
    if no_offer:
        print("  DIAGNOSIS: POOL EXHAUSTION (starvation)")
        print("    Remediation: port-security max-mac; rate-limit DISCOVERs.")
    if rogue_accepted == 0 and no_offer == 0:
        print("  DIAGNOSIS: healthy.")
    print()


def starvation_attack(legit: DhcpServer, n_forge: int) -> None:
    print("=" * 64)
    print(f"DHCP Starvation Attack ({n_forge} forged DISCOVERs)")
    print("=" * 64)
    accepted = 0
    for i in range(n_forge):
        chaddr = f"06:00:00:{i:06x}"
        offer = legit.offer(chaddr)
        if offer is None:
            break
        if legit.ack(chaddr, offer.yiaddr):
            accepted += 1
    leased = len(legit.leases)
    forged_no_arp = sum(1 for l in legit.leases.values() if not l.arped)
    print(f"  Forged DISCOVERs     : {n_forge}")
    print(f"  Leases accepted      : {accepted}")
    print(f"  Pool size            : {len(legit.pool)}")
    print(f"  Leases with no ARP   : {forged_no_arp}")
    print(f"  Pool available       : {len(legit.pool) - leased}")
    if leased >= len(legit.pool):
        print("  DIAGNOSIS: POOL EXHAUSTED by forged chaddr.")
        print("  Detection: lease table full of MACs that never ARP'd.")
        print("  Remediation: port-security max 2 MAC per access port;")
        print("               DHCP Snooping rate-limit on untrusted ports.")
    print()


def main() -> None:
    random.seed(13)
    pool = {f"{SUBNET}{i}" for i in range(POOL_START, POOL_END + 1)}
    legit = DhcpServer(LEGIT_SERVER_MAC, LEGIT_SERVER_IP, LEGIT_GW, LEGIT_DNS, pool)
    rogue_pool = {f"{SUBNET}{i}" for i in range(150, 160)}
    rogue = DhcpServer(ROGUE_SERVER_MAC, ROGUE_SERVER_IP, ROGUE_GW, ROGUE_DNS, rogue_pool)

    # Scenario 1: no snooping -> rogue wins some clients
    simulate_clients(legit, rogue, snooping=None, n_clients=20)

    # Scenario 2: snooping ON -> rogue blocked
    legit2 = DhcpServer(LEGIT_SERVER_MAC, LEGIT_SERVER_IP, LEGIT_GW, LEGIT_DNS, pool)
    rogue2 = DhcpServer(ROGUE_SERVER_MAC, ROGUE_SERVER_IP, ROGUE_GW, ROGUE_DNS, rogue_pool)
    snooping = SnoopingSwitch(trusted_server_macs={LEGIT_SERVER_MAC})
    simulate_clients(legit2, rogue2, snooping=snooping, n_clients=20)

    # Scenario 3: starvation attack drains the pool
    legit3 = DhcpServer(LEGIT_SERVER_MAC, LEGIT_SERVER_IP, LEGIT_GW, LEGIT_DNS, pool)
    starvation_attack(legit3, n_forge=150)


if __name__ == "__main__":
    main()
