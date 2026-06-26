#!/usr/bin/env python3
"""IPv4 subnet calculator and VLSM planner (stdlib only).

Everything here is integer math on the 32-bit IPv4 address (RFC 791).
A prefix length p defines a mask of p leading 1-bits; the network address
is (addr AND mask), the broadcast is (addr OR ~mask), and two hosts share a
subnet iff (a AND mask) == (b AND mask) -- the same test an IP stack uses to
decide local (ARP) delivery vs handing the packet to the default gateway.

No third-party packages, no network calls. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

IPV4_BITS = 32
FULL_MASK = (1 << IPV4_BITS) - 1  # 0xFFFFFFFF


# --------------------------------------------------------------------------
# Core conversions
# --------------------------------------------------------------------------
def ip_to_int(addr: str) -> int:
    """Pack dotted-decimal 'a.b.c.d' into a 32-bit unsigned integer."""
    parts = addr.split(".")
    if len(parts) != 4:
        raise ValueError(f"not four octets: {addr!r}")
    value = 0
    for octet in parts:
        n = int(octet)
        if not 0 <= n <= 255:
            raise ValueError(f"octet out of range 0-255: {octet!r}")
        value = (value << 8) | n
    return value


def int_to_ip(value: int) -> str:
    """Unpack a 32-bit integer back into dotted-decimal."""
    if not 0 <= value <= FULL_MASK:
        raise ValueError(f"value outside 32-bit range: {value}")
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def prefix_to_mask(prefix: int) -> int:
    """Return the 32-bit mask for a prefix length (0..32)."""
    if not 0 <= prefix <= IPV4_BITS:
        raise ValueError(f"prefix must be 0..32, got {prefix}")
    if prefix == 0:
        return 0
    return (FULL_MASK << (IPV4_BITS - prefix)) & FULL_MASK


def mask_to_wildcard(mask: int) -> int:
    """Wildcard mask = bitwise complement of the subnet mask (ACL/OSPF form)."""
    return (~mask) & FULL_MASK


def parse_cidr(cidr: str) -> tuple[int, int]:
    """Parse 'a.b.c.d/p' into (addr_int, prefix)."""
    if "/" not in cidr:
        raise ValueError(f"missing prefix in {cidr!r}")
    addr_str, prefix_str = cidr.split("/", 1)
    return ip_to_int(addr_str), int(prefix_str)


# --------------------------------------------------------------------------
# Subnet arithmetic
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Subnet:
    """An immutable view of one subnet derived from address + prefix."""

    addr: int
    prefix: int

    @property
    def mask(self) -> int:
        return prefix_to_mask(self.prefix)

    @property
    def network(self) -> int:
        return self.addr & self.mask

    @property
    def broadcast(self) -> int:
        return self.network | mask_to_wildcard(self.mask)

    @property
    def total_addresses(self) -> int:
        return 1 << (IPV4_BITS - self.prefix)

    @property
    def usable_hosts(self) -> int:
        if self.prefix == 31:  # RFC 3021 point-to-point: both usable
            return 2
        if self.prefix == 32:  # single-host route
            return 1
        return self.total_addresses - 2

    @property
    def first_host(self) -> int:
        return self.network if self.prefix >= 31 else self.network + 1

    @property
    def last_host(self) -> int:
        return self.broadcast if self.prefix >= 31 else self.broadcast - 1

    def __str__(self) -> str:
        return f"{int_to_ip(self.network)}/{self.prefix}"


def same_subnet(a: str, b: str, mask: int) -> bool:
    """Forwarding decision: do a and b share a subnet under this mask?"""
    return (ip_to_int(a) & mask) == (ip_to_int(b) & mask)


# --------------------------------------------------------------------------
# Address classification (RFC special ranges)
# --------------------------------------------------------------------------
_SPECIAL_RANGES: list[tuple[str, int, str]] = [
    ("0.0.0.0", 8, "this-network/unspecified (RFC 1122)"),
    ("10.0.0.0", 8, "private (RFC 1918)"),
    ("100.64.0.0", 10, "shared CGN space (RFC 6598)"),
    ("127.0.0.0", 8, "loopback (RFC 1122)"),
    ("169.254.0.0", 16, "link-local / APIPA (RFC 3927)"),
    ("172.16.0.0", 12, "private (RFC 1918)"),
    ("192.168.0.0", 16, "private (RFC 1918)"),
    ("224.0.0.0", 4, "multicast (RFC 5771)"),
    ("240.0.0.0", 4, "reserved (RFC 1112)"),
]


def classify(addr: str) -> str:
    """Return the RFC label for an address, or 'global unicast (routable)'."""
    value = ip_to_int(addr)
    for net, prefix, label in _SPECIAL_RANGES:
        mask = prefix_to_mask(prefix)
        if (value & mask) == (ip_to_int(net) & mask):
            return label
    return "global unicast (routable)"


# --------------------------------------------------------------------------
# VLSM planner (greedy, largest-requirement-first)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Allocation:
    name: str
    need: int
    subnet: Subnet


def prefix_for_hosts(need: int) -> int:
    """Smallest prefix whose usable-host count covers `need`."""
    if need <= 0:
        raise ValueError("need must be positive")
    for host_bits in range(2, IPV4_BITS + 1):
        if (1 << host_bits) - 2 >= need:
            return IPV4_BITS - host_bits
    raise ValueError(f"cannot fit {need} hosts in IPv4")


def vlsm_plan(block: str, requirements: Iterable[tuple[str, int]]) -> list[Allocation]:
    """Carve `block` (CIDR) into right-sized subnets, largest need first."""
    base, base_prefix = parse_cidr(block)
    base_net = base & prefix_to_mask(base_prefix)
    block_end = base_net | mask_to_wildcard(prefix_to_mask(base_prefix))

    cursor = base_net
    plan: list[Allocation] = []
    for name, need in sorted(requirements, key=lambda r: r[1], reverse=True):
        prefix = prefix_for_hosts(need)
        size = 1 << (IPV4_BITS - prefix)
        # Align cursor to this subnet's natural boundary.
        if cursor % size != 0:
            cursor += size - (cursor % size)
        if cursor + size - 1 > block_end:
            raise ValueError(f"out of space allocating {name} (/{prefix})")
        plan.append(Allocation(name, need, Subnet(cursor, prefix)))
        cursor += size
    return plan


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------
def describe(sn: Subnet) -> None:
    print(f"  {sn}  (mask {int_to_ip(sn.mask)}  wildcard {int_to_ip(mask_to_wildcard(sn.mask))})")
    print(f"    network   {int_to_ip(sn.network)}")
    print(f"    broadcast {int_to_ip(sn.broadcast)}")
    print(f"    hosts     {int_to_ip(sn.first_host)} - {int_to_ip(sn.last_host)} ({sn.usable_hosts} usable)")


def main() -> None:
    print("=== Subnet breakdown: 10.20.1.130/25 ===")
    addr, prefix = parse_cidr("10.20.1.130/25")
    describe(Subnet(addr, prefix))

    print("\n=== Point-to-point WAN link: 10.20.1.192/30 ===")
    addr, prefix = parse_cidr("10.20.1.192/30")
    describe(Subnet(addr, prefix))

    print("\n=== Same-subnet test (the .130 vs .200 bug) ===")
    for p, name in ((25, "/25 (correct)"), (26, "/26 (the bug)")):
        mask = prefix_to_mask(p)
        ok = same_subnet("10.20.1.130", "10.20.1.200", mask)
        verdict = "REACHABLE directly" if ok else "DIFFERENT subnets -> via gateway"
        print(f"  mask {name:14s}: {verdict}")

    print("\n=== VLSM plan for 10.20.0.0/22 ===")
    requirements = [("Engineering", 200), ("Sales", 100), ("Ops", 50), ("WAN-link", 2)]
    for alloc in vlsm_plan("10.20.0.0/22", requirements):
        sn = alloc.subnet
        rng = f"{int_to_ip(sn.first_host)}-{int_to_ip(sn.last_host)}"
        print(f"  {alloc.name:12s} need {alloc.need:>3} -> {str(sn):18s} {rng} ({sn.usable_hosts} usable)")

    print("\n=== Address classification ===")
    for ip in ("8.8.8.8", "10.20.1.130", "172.20.5.1", "192.168.0.10",
               "100.72.1.1", "169.254.18.4", "127.0.0.1"):
        print(f"  {ip:15s} -> {classify(ip)}")


if __name__ == "__main__":
    main()
