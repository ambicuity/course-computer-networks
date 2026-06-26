"""IPv4 address toolkit: CIDR parsing, subnet arithmetic, classification, VLSM.

Stdlib-only. Run: python3 main.py
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


PRIVATE_RANGES = [
    (0x0A000000, 0x0AFFFFFF),  # 10.0.0.0/8
    (0xAC100000, 0xAC1FFFFF),  # 172.16.0.0/12
    (0xC0A80000, 0xC0A8FFFF),  # 192.168.0.0/16
]

LOOPBACK_LO, LOOPBACK_HI = 0x7F000000, 0x7FFFFFFF
LINKLOCAL_LO, LINKLOCAL_HI = 0xA9FE0000, 0xA9FEFFFF
THIS_HOST = 0x00000000
LIMITED_BCAST = 0xFFFFFFFF


def ip_to_int(ip: str) -> int:
    """Dotted-decimal 'a.b.c.d' -> 32-bit integer."""
    parts = ip.strip().split(".")
    if len(parts) != 4:
        raise ValueError(f"bad IPv4: {ip!r}")
    octets = [int(p) for p in parts]
    for o in octets:
        if not 0 <= o <= 255:
            raise ValueError(f"octet out of range in {ip!r}")
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def int_to_ip(value: int) -> str:
    """32-bit integer -> dotted decimal."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"out of 32-bit range: {value}")
    return f"{(value >> 24) & 0xFF}.{(value >> 16) & 0xFF}.{(value >> 8) & 0xFF}.{value & 0xFF}"


def mask_from_prefix(prefix: int) -> int:
    if not 0 <= prefix <= 32:
        raise ValueError(f"bad prefix: {prefix}")
    if prefix == 0:
        return 0
    return (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF


def int_to_binary(value: int) -> str:
    return ".".join(f"{(value >> (24 - 8 * i)) & 0xFF:08b}" for i in range(4))


@dataclass
class Network:
    network: int
    prefix: int
    mask: int
    broadcast: int
    usable_lo: int
    usable_hi: int
    total: int
    usable: int

    def network_str(self) -> str:
        return int_to_ip(self.network)

    def broadcast_str(self) -> str:
        return int_to_ip(self.broadcast)

    def mask_str(self) -> str:
        return int_to_ip(self.mask)


def parse_cidr(cidr: str) -> Network:
    """Parse 'a.b.c.d/n' into a Network with all derived fields."""
    if "/" not in cidr:
        raise ValueError(f"missing prefix in {cidr!r}")
    ip_part, _, pre_part = cidr.partition("/")
    ip_int = ip_to_int(ip_part)
    prefix = int(pre_part)
    mask = mask_from_prefix(prefix)
    network = ip_int & mask
    broadcast = network | (~mask & 0xFFFFFFFF)
    total = 1 << (32 - prefix)
    usable = total if prefix >= 31 else total - 2
    return Network(
        network=network, prefix=prefix, mask=mask, broadcast=broadcast,
        usable_lo=network + 1, usable_hi=broadcast - 1,
        total=total, usable=usable,
    )


def in_subnet(ip: str, cidr: str) -> bool:
    """True if `ip` falls within the CIDR block."""
    ip_int = ip_to_int(ip)
    net = parse_cidr(cidr)
    return (ip_int & net.mask) == net.network


@dataclass
class Classification:
    ip: str
    ip_class: str
    is_private: bool
    special: str


def classify(ip: str) -> Classification:
    """Classify an IPv4 address by class, private range, and special-use."""
    val = ip_to_int(ip)
    first = val >> 24
    special = ""
    if val == THIS_HOST:
        special = "'this host' (boot)"
    elif val == LIMITED_BCAST:
        special = "limited broadcast"
    elif LOOPBACK_LO <= val <= LOOPBACK_HI:
        special = "loopback (127/8)"
    elif LINKLOCAL_LO <= val <= LINKLOCAL_HI:
        special = "link-local/APIPA (169.254/16)"

    is_private = any(lo <= val <= hi for lo, hi in PRIVATE_RANGES)

    if first <= 127:
        ip_class = "A"
    elif first <= 191:
        ip_class = "B"
    elif first <= 223:
        ip_class = "C"
    elif first <= 239:
        ip_class = "D (multicast)"
    else:
        ip_class = "E (reserved)"
    if special:
        ip_class = "special"

    return Classification(ip=ip, ip_class=ip_class, is_private=is_private, special=special)


@dataclass
class SubnetInfo:
    name: str
    needed: int
    prefix: int
    network: int
    broadcast: int
    mask: int

    def usable_range(self) -> str:
        return f"{int_to_ip(self.network + 1)} - {int_to_ip(self.broadcast - 1)}"


@dataclass
class VlsmResult:
    base_cidr: str
    subnets: List[SubnetInfo] = field(default_factory=list)
    remainder_start: int = 0
    remainder_end: int = 0
    success: bool = True
    error: str = ""


def prefix_for_hosts(needed: int) -> int:
    """Smallest prefix length that fits `needed` usable hosts."""
    for p in range(32, -1, -1):
        total = 1 << (32 - p)
        usable = total if p >= 31 else total - 2
        if usable >= needed:
            return p
    return 32


def divide(base_cidr: str, needs: List[int]) -> VlsmResult:
    """VLSM: split base_cidr into subnets for each host count (largest first)."""
    base = parse_cidr(base_cidr)
    result = VlsmResult(base_cidr=base_cidr)
    indexed = sorted(enumerate(needs), key=lambda kv: kv[1], reverse=True)
    cursor = base.network
    for idx, n in indexed:
        prefix = prefix_for_hosts(n)
        size = 1 << (32 - prefix)
        aligned = (cursor + size - 1) & ~(size - 1)
        bcast = aligned + size - 1
        if bcast > base.broadcast:
            result.success = False
            result.error = f"subnet {idx} needs /{prefix} but only {base.broadcast - cursor + 1} remain"
            return result
        result.subnets.append(SubnetInfo(
            name=f"subnet-{idx}", needed=n, prefix=prefix,
            network=aligned, broadcast=bcast, mask=mask_from_prefix(prefix),
        ))
        cursor = bcast + 1
    result.remainder_start = cursor
    result.remainder_end = base.broadcast
    return result


def banner(t: str) -> str:
    return f"\n{'=' * 68}\n{t}\n{'=' * 68}"


def show_net(n: Network) -> None:
    print(f"  CIDR={n.network_str()}/{n.prefix} mask={n.mask_str()}")
    print(f"  net={n.network_str()} bcast={n.broadcast_str()} usable={n.usable}")


def main() -> None:
    print(banner("CIDR PARSE: 192.168.1.0/24"))
    show_net(parse_cidr("192.168.1.0/24"))
    print(banner("CIDR PARSE: 10.0.0.0/30 (WAN)"))
    show_net(parse_cidr("10.0.0.0/30"))

    print(banner("MEMBERSHIP"))
    for ip, cidr in [("192.168.1.55", "192.168.1.0/24"),
                     ("192.168.1.200", "192.168.1.0/26"),
                     ("8.8.8.8", "10.0.0.0/8")]:
        print(f"  {ip:16} in {cidr:20} -> {in_subnet(ip, cidr)}")

    print(banner("CLASSIFICATION"))
    for ip in ["10.1.2.3", "172.16.0.1", "192.168.1.1", "128.208.2.151",
               "224.0.0.1", "127.0.0.1", "169.254.10.20", "0.0.0.0",
               "255.255.255.255"]:
        c = classify(ip)
        tags = [c.ip_class]
        if c.is_private:
            tags.append("private")
        if c.special:
            tags.append(c.special)
        print(f"  {ip:18} -> {', '.join(tags)}")

    print(banner("VLSM: 192.168.1.0/24 -> [60, 30, 14, 2]"))
    r = divide("192.168.1.0/24", [60, 30, 14, 2])
    if not r.success:
        print(f"  ERROR: {r.error}")
    else:
        for s in r.subnets:
            print(f"  {s.name} /{s.prefix} net={int_to_ip(s.network)} "
                  f"bcast={int_to_ip(s.broadcast)} mask={int_to_ip(s.mask)}")
        print(f"  remainder: {int_to_ip(r.remainder_start)}-{int_to_ip(r.remainder_end)}")

    print(banner("VLSM FAIL: 192.168.1.0/25 -> [60, 30, 14, 2]"))
    r2 = divide("192.168.1.0/25", [60, 30, 14, 2])
    if not r2.success:
        print(f"  expected failure: {r2.error}")


if __name__ == "__main__":
    main()
