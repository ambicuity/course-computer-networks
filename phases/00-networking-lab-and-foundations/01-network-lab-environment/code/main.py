#!/usr/bin/env python3
"""Offline subnet and reachability planner for the network lab.

This mirrors the arithmetic the Linux kernel performs on every packet:

  * Compute network, broadcast, and usable host range for an IPv4 CIDR
    (the same values `ip addr` derives from a prefix length).
  * Decide whether two hosts share a subnet via a bitwise AND with the mask
    -- the "same-subnet test" that determines direct ARP delivery vs.
    delivery through the default gateway.
  * Resolve a destination against a routing table using longest-prefix
    match, exactly as the kernel's FIB lookup does (RFC 791 routing model).

No network calls, no third-party packages -- pure stdlib so it runs anywhere
with `python3 main.py`. It plans the lab topology before you build it.
"""

from __future__ import annotations

from dataclasses import dataclass

IPV4_BITS = 32
OCTET_MAX = 255
FULL_MASK = 0xFFFFFFFF


def ip_to_int(addr: str) -> int:
    """Convert dotted-quad 'a.b.c.d' to a 32-bit integer."""
    octets = addr.split(".")
    if len(octets) != 4:
        raise ValueError(f"not a dotted quad: {addr!r}")
    value = 0
    for octet in octets:
        n = int(octet)
        if not 0 <= n <= OCTET_MAX:
            raise ValueError(f"octet out of range in {addr!r}: {n}")
        value = (value << 8) | n
    return value


def int_to_ip(value: int) -> str:
    """Convert a 32-bit integer back to dotted-quad notation."""
    return ".".join(str((value >> shift) & OCTET_MAX) for shift in (24, 16, 8, 0))


def prefix_to_mask(prefix: int) -> int:
    """Build a 32-bit netmask from a prefix length, e.g. 24 -> 255.255.255.0."""
    if not 0 <= prefix <= IPV4_BITS:
        raise ValueError(f"prefix must be 0..32, got {prefix}")
    if prefix == 0:
        return 0
    return (FULL_MASK << (IPV4_BITS - prefix)) & FULL_MASK


@dataclass(frozen=True)
class Subnet:
    """An IPv4 subnet described by a base address and prefix length."""

    address: str
    prefix: int

    @property
    def mask_int(self) -> int:
        return prefix_to_mask(self.prefix)

    @property
    def network_int(self) -> int:
        return ip_to_int(self.address) & self.mask_int

    @property
    def broadcast_int(self) -> int:
        return self.network_int | (~self.mask_int & FULL_MASK)

    @property
    def host_count(self) -> int:
        """Usable hosts. /31 and /32 have no usable-host range (RFC 3021)."""
        span = self.broadcast_int - self.network_int + 1
        return max(span - 2, 0)

    def contains(self, addr: str) -> bool:
        return (ip_to_int(addr) & self.mask_int) == self.network_int

    def describe(self) -> str:
        net = int_to_ip(self.network_int)
        bcast = int_to_ip(self.broadcast_int)
        if self.host_count == 0:
            host_range = "(no usable host range)"
        else:
            first = int_to_ip(self.network_int + 1)
            last = int_to_ip(self.broadcast_int - 1)
            host_range = f"{first} - {last}"
        return (
            f"  network   : {net}/{self.prefix}\n"
            f"  netmask   : {int_to_ip(self.mask_int)}\n"
            f"  broadcast : {bcast}\n"
            f"  hosts     : {self.host_count} usable  [{host_range}]"
        )


def same_subnet(ip_a: str, ip_b: str, prefix: int) -> bool:
    """True iff both addresses fall in the same /prefix network."""
    mask = prefix_to_mask(prefix)
    return (ip_to_int(ip_a) & mask) == (ip_to_int(ip_b) & mask)


@dataclass(frozen=True)
class Route:
    """A routing-table entry: a destination prefix and its next hop."""

    network: str
    prefix: int
    next_hop: str  # gateway IP, or "direct" for a connected route

    @property
    def mask_int(self) -> int:
        return prefix_to_mask(self.prefix)

    def matches(self, dest: str) -> bool:
        return (ip_to_int(dest) & self.mask_int) == (
            ip_to_int(self.network) & self.mask_int
        )


def longest_prefix_match(dest: str, table: list[Route]) -> Route | None:
    """Return the most-specific route covering `dest` (kernel FIB behaviour)."""
    best: Route | None = None
    for route in table:
        if route.matches(dest) and (best is None or route.prefix > best.prefix):
            best = route
    return best


def reachability_verdict(src: str, dst: str, prefix: int) -> str:
    """Explain how `src` reaches `dst`: direct ARP or via the gateway."""
    if same_subnet(src, dst, prefix):
        return f"{src} -> {dst}: SAME subnet -> deliver directly (ARP for {dst})"
    return (
        f"{src} -> {dst}: DIFFERENT subnet -> send to default gateway "
        f"(ARP for the gateway, not for {dst})"
    )


def main() -> None:
    print("=" * 62)
    print("NETWORK LAB PLANNER  --  subnets, reachability, routing")
    print("=" * 62)

    subnet_a = Subnet("10.0.0.0", 24)
    subnet_b = Subnet("10.0.1.0", 24)

    print("\nSubnet A (h1 side):")
    print(subnet_a.describe())
    print("\nSubnet B (h2 side):")
    print(subnet_b.describe())

    h1, h2 = "10.0.0.2", "10.0.1.2"
    gw_a = "10.0.0.1"

    print("\nReachability tests (/24):")
    print("  " + reachability_verdict(h1, gw_a, 24))   # local
    print("  " + reachability_verdict(h1, h2, 24))     # crosses router

    # h1's routing table: one connected route + a default via the gateway.
    h1_table = [
        Route("10.0.0.0", 24, "direct"),
        Route("0.0.0.0", 0, gw_a),
    ]
    print("\nLongest-prefix match from h1's routing table:")
    for dest in (gw_a, h2, "8.8.8.8"):
        chosen = longest_prefix_match(dest, h1_table)
        if chosen is None:
            print(f"  {dest:<12} -> NO ROUTE (host unreachable)")
        else:
            via = (
                "connected link"
                if chosen.next_hop == "direct"
                else f"via {chosen.next_hop}"
            )
            print(f"  {dest:<12} -> match {chosen.network}/{chosen.prefix:<2} {via}")

    print("\nPoint-to-point check (/30 links):")
    pair = ("10.0.0.2", "10.0.0.6")
    verdict = "SAME" if same_subnet(pair[0], pair[1], 30) else "DIFFERENT"
    print(f"  {pair[0]} and {pair[1]} on /30 -> {verdict} subnet")
    print(
        f"  a /30 yields {Subnet('10.0.0.0', 30).host_count} usable hosts "
        f"(classic point-to-point sizing)"
    )

    print("\nPlan verified. Build the lab with the ip-netns commands in docs/en.md.")


if __name__ == "__main__":
    main()
