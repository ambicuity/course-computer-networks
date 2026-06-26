#!/usr/bin/env python3
"""NAT Port Exhaustion and Hairpin Loopback (Lab 09).

Models a symmetric NAPT gateway hiding many inside clients behind one
public IPv4 address.  Each outbound flow consumes one public port from a
bounded ephemeral pool.  When the pool is exhausted new SYNs fail with
EADDRNOTAVAIL.

A hairpin generator additionally produces flows whose destination is an
inside server reached through the public address, demonstrating the
return-path tuple collision that occurs when the source is rewritten to
the public IP and the inside server cannot demultiplex.

Run:  python3 code/main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


PUBLIC_IP = "203.0.113.10"
PUBLIC_IP_2 = "203.0.113.11"
EPHEMERAL_LO_DEFAULT = 32768
EPHEMERAL_HI_DEFAULT = 60999
EPHEMERAL_HI_WIDE = 65535
INSIDE_SERVER = "198.51.100.55"  # published behind PUBLIC_IP:443
DEST_SERVICE = ("93.184.216.34", 443)


@dataclass
class Flow:
    fid: int
    inside_src_ip: str
    inside_src_port: int
    outside_dst: str
    outside_port: int
    public_ip: str = ""
    public_port: int = 0
    hairpin: bool = False
    state: str = "SYN_SENT"


@dataclass
class NatGateway:
    public_ips: list[str] = field(default_factory=lambda: [PUBLIC_IP])
    ephemeral_lo: int = EPHEMERAL_LO_DEFAULT
    ephemeral_hi: int = EPHEMERAL_HI_DEFAULT
    pool: set[tuple[str, int]] = field(default_factory=set)
    flows: list[Flow] = field(default_factory=list)
    insert_fail: int = 0
    time_wait_reservation: int = 120  # seconds

    @property
    def capacity(self) -> int:
        return (self.ephemeral_hi - self.ephemeral_lo + 1) * len(self.public_ips)

    def alloc_slot(self) -> tuple[str, int] | None:
        for ip in self.public_ips:
            for cand in range(self.ephemeral_lo, self.ephemeral_hi + 1):
                slot = (ip, cand)
                if slot not in self.pool:
                    self.pool.add(slot)
                    return slot
        return None

    def admit(self, flow: Flow) -> bool:
        slot = self.alloc_slot()
        if slot is None:
            self.insert_fail += 1
            flow.state = "DROP_NAT_FULL"
            return False
        flow.public_ip = slot[0]
        flow.public_port = slot[1]
        flow.state = "ESTABLISHED_HAIRPIN" if flow.hairpin else "ESTABLISHED"
        self.flows.append(flow)
        return True

    def utilisation(self) -> float:
        return len(self.pool) / self.capacity if self.capacity else 0.0


def generate_clients(n: int, hairpin_ratio: float) -> list[Flow]:
    flows: list[Flow] = []
    for i in range(n):
        src_ip = f"10.20.30.{i % 250 + 1}"
        src_port = 40000 + (i % 20000)
        if (i / n) < hairpin_ratio:
            dst, dst_port = PUBLIC_IP, 443
            hp = True
        else:
            dst, dst_port = DEST_SERVICE
            hp = False
        flows.append(Flow(i, src_ip, src_port, dst, dst_port, hairpin=hp))
    return flows


def detect_hairpin_collisions(gw: NatGateway) -> int:
    """Count inside-server return tuples that share a public-port key."""
    seen: dict[tuple[str, int, str, int], int] = {}
    for f in gw.flows:
        if not f.hairpin:
            continue
        key = (f.public_ip, f.public_port, INSIDE_SERVER, 443)
        seen[key] = seen.get(key, 0) + 1
    return sum(c - 1 for c in seen.values() if c > 1)


def sustained_rate(gw: NatGateway) -> float:
    """Max sustained flow rate given TIME-WAIT reservation cost."""
    if gw.time_wait_reservation <= 0:
        return 0.0
    return gw.capacity / gw.time_wait_reservation


def run(label: str, flows: list[Flow], gw: NatGateway | None = None) -> None:
    gw = gw or NatGateway()
    print("=" * 70)
    print(f"NAT Port Exhaustion Simulator  [{label}]")
    print("=" * 70)
    print(f"  Public IP(s): {gw.public_ips}")
    print(f"  Ephemeral pool: {gw.ephemeral_lo}-{gw.ephemeral_hi} "
          f"({gw.capacity} ports)")
    print(f"  TIME-WAIT reservation: {gw.time_wait_reservation}s")
    print(f"  Incoming flows: {len(flows)}")
    print(f"  Sustained rate ceiling: {sustained_rate(gw):.1f} flows/s\n")

    for f in flows:
        gw.admit(f)

    est = sum(1 for f in gw.flows if f.state == "ESTABLISHED")
    hair = sum(1 for f in gw.flows if f.hairpin)
    dropped = gw.insert_fail
    print("  Outcome:")
    print(f"    established        : {est}")
    print(f"    hairpin established: {hair}")
    print(f"    NAT insert failed  : {dropped}")
    print(f"    pool utilisation   : {gw.utilisation() * 100:.1f}%\n")

    if dropped > 0:
        print("  DIAGNOSIS: PORT EXHAUSTION")
        print(f"    {dropped} SYNs rejected locally before ever leaving the NAT.")
        print(f"    Client sees: 'connect: Cannot assign requested address'")
        print(f"    Remediation:")
        print(f"      1. Add a second public IP to double the 5-tuple space")
        print(f"      2. Widen net.ipv4.ip_local_port_range to 1024-65535")
        print(f"      3. Lower net.netfilter.nf_conntrack_tcp_timeout_time_wait")
        print(f"      4. Deploy an L7 proxy so idle flows close sooner")
    else:
        collisions = detect_hairpin_collisions(gw)
        if collisions:
            print("  DIAGNOSIS: HAIRPIN RETURN-PATH COLLISION")
            print(f"    {collisions} flows share an (public_ip, public_port) return key.")
            print(f"    Server cannot demultiplex the SYN-ACK; replies blackholed.")
            print(f"    Remediation: split-horizon DNS or disable hairpin NAT.")
        else:
            print("  DIAGNOSIS: healthy; pool under capacity.")
    print()


def main() -> None:
    random.seed(7)
    # Scenario 1: steady load well under capacity
    run("steady", generate_clients(5000, 0.0))
    # Scenario 2: burst to one external service saturates the pool
    run("burst-to-one-dest", generate_clients(32000, 0.0))
    # Scenario 3: hairpin-heavy load
    run("hairpin-heavy", generate_clients(20000, 0.5))
    # Scenario 4: add a second public IP and retry burst
    gw_two_ips = NatGateway(public_ips=[PUBLIC_IP, PUBLIC_IP_2])
    run("burst-with-second-ip", generate_clients(32000, 0.0), gw_two_ips)
    # Scenario 5: widen ephemeral range
    gw_wide = NatGateway(ephemeral_lo=1024, ephemeral_hi=EPHEMERAL_HI_WIDE)
    run("burst-with-wide-ephemeral", generate_clients(32000, 0.0), gw_wide)
    # Scenario 6: shorten TIME-WAIT reservation
    gw_short_tw = NatGateway(time_wait_reservation=30)
    run("burst-with-short-time-wait", generate_clients(32000, 0.0), gw_short_tw)


if __name__ == "__main__":
    main()
