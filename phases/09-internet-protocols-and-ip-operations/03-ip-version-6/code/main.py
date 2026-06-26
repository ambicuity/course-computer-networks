#!/usr/bin/env python3
"""IPv6 address parser and classifier (Tanenbaum section 5.6.3).

Stdlib only. Demonstrates:
  - Parsing and validating an IPv6 address (full form, :: compression,
    leading-zero omission, IPv4-mapped tail).
  - Compressing to RFC 5952 canonical form (longest zero run, one ::).
  - Classifying address type from the leading bits:
    unspecified, loopback, link-local, unique-local, global unicast,
    IPv4-mapped, multicast (with scope), solicited-node.
  - Extracting the prefix/network, first host, last host, and count.
  - Building EUI-64 interface IDs and link-local addresses from a MAC.

Run:  python3 code/main.py
"""
from __future__ import annotations

from dataclasses import dataclass

NEXT_HEADER_MAP: dict[int, str] = {
    0: "Hop-by-Hop Options",
    6: "TCP",
    17: "UDP",
    41: "IPv6 encapsulation",
    43: "Routing Header",
    44: "Fragment Header",
    50: "ESP",
    51: "Authentication Header",
    58: "ICMPv6",
    59: "No Next Header",
    60: "Destination Options",
    89: "OSPF",
    132: "SCTP",
}

MULTICAST_SCOPES: dict[int, str] = {
    0: "reserved",
    1: "interface-local",
    2: "link-local",
    3: "realm-local",
    4: "admin-local",
    5: "site-local",
    8: "organization-local",
    0xE: "global",
    0xF: "reserved",
}


# ---------------------------------------------------------------------
#  Address parse / compress
# ---------------------------------------------------------------------

def ipv6_to_int(addr: str) -> int:
    """Parse any valid IPv6 text form to a 128-bit integer."""
    addr = addr.strip().lower()
    if addr.startswith("[") and addr.endswith("]"):
        addr = addr[1:-1]

    if "." in addr and "::" in addr:
        head, tail = addr.rsplit(":", 1)
        octets = tail.split(".")
        if len(octets) != 4:
            raise ValueError(f"Invalid IPv4 tail in {addr!r}")
        tail_val = (int(octets[0]) << 24 | int(octets[1]) << 16 |
                    int(octets[2]) << 8 | int(octets[3]))
        groups = [g for g in head.split(":") if g] if head else []
        groups += [f"{tail_val >> 16 & 0xFFFF:04x}", f"{tail_val & 0xFFFF:04x}"]
        if "::" in head:
            head_part, _ = head.split("::", 1)
            head_count = len([g for g in head_part.split(":") if g])
            missing = 8 - len(groups)
            groups = ([g for g in head_part.split(":") if g]
                      + ["0"] * missing + groups[-2:])
        return int("".join(f"{int(g, 16):04x}" for g in groups), 16)

    if "::" in addr:
        if addr.count("::") > 1:
            raise ValueError(f"Multiple '::' in {addr!r}")
        head, tail = addr.split("::", 1)
        head_parts = [g for g in head.split(":") if g]
        tail_parts = [g for g in tail.split(":") if g]
        if "." in tail:
            tail_parts = tail_parts[:-1] + [
                f"{int(tail.split('.')[-4]) << 8 | int(tail.split('.')[-3]):04x}",
                f"{int(tail.split('.')[-2]) << 8 | int(tail.split('.')[-1]):04x}",
            ]
        missing = 8 - len(head_parts) - len(tail_parts)
        if missing < 0:
            raise ValueError(f"Too many groups in {addr!r}")
        groups = head_parts + ["0"] * missing + tail_parts
    else:
        groups = addr.split(":")

    if len(groups) != 8:
        raise ValueError(f"Expected 8 groups in {addr!r}, got {len(groups)}")
    return int("".join(f"{int(g, 16):04x}" for g in groups), 16)


def int_to_ipv6(value: int) -> str:
    """Render a 128-bit int as RFC 5952 canonical compressed text.

    Each group is written without leading zeros; the single longest run of
    all-zero groups (length >= 2) is replaced by '::' exactly once.
    """
    if value < 0 or value >= (1 << 128):
        raise ValueError("value out of 128-bit range")
    groups = [(value >> shift) & 0xFFFF for shift in range(112, -1, -16)]
    hex_groups = [f"{g:x}" for g in groups]  # no leading zeros

    best_start, best_len = -1, 0
    run_start, run_len = -1, 0
    for i, g in enumerate(hex_groups):
        if int(g, 16) == 0:
            if run_start == -1:
                run_start, run_len = i, 1
            else:
                run_len += 1
        else:
            if run_start != -1 and run_len > best_len:
                best_start, best_len = run_start, run_len
            run_start, run_len = -1, 0
    if run_start != -1 and run_len > best_len:
        best_start, best_len = run_start, run_len

    if best_len < 2:
        return ":".join(hex_groups)
    before = hex_groups[:best_start]
    after = hex_groups[best_start + best_len:]
    return ":".join(before) + "::" + ":".join(after)


def compress_ipv6(addr: str) -> str:
    """Canonical RFC 5952 compressed form of any IPv6 address."""
    return int_to_ipv6(ipv6_to_int(addr))


def expand_ipv6(addr: str) -> str:
    """Fully expanded 8-group form (lowercase, no ::)."""
    val = ipv6_to_int(addr)
    groups = [(val >> shift) & 0xFFFF for shift in range(112, -1, -16)]
    return ":".join(f"{g:04x}" for g in groups)


def validate_ipv6(addr: str) -> bool:
    """True if addr is a syntactically valid IPv6 address."""
    try:
        ipv6_to_int(addr)
        return True
    except (ValueError, IndexError):
        return False


# ---------------------------------------------------------------------
#  Classification
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class AddressInfo:
    address: str
    expanded: str
    type: str
    scope: str
    prefix: str

    def __str__(self) -> str:
        return (
            f"  address : {self.address}\n"
            f"  expanded: {self.expanded}\n"
            f"  type    : {self.type}\n"
            f"  scope   : {self.scope}\n"
            f"  prefix  : {self.prefix}"
        )


def classify_ipv6(addr: str) -> AddressInfo:
    val = ipv6_to_int(addr)
    expanded = int_to_ipv6(val)
    top8 = (val >> 120) & 0xFF
    top16 = (val >> 112) & 0xFFFF

    if val == 0:
        addr_type, scope, prefix = "unspecified", "n/a", "::/128"
    elif val == 1:
        addr_type, scope, prefix = "loopback", "host", "::1/128"
    elif (val >> 118) == 0x3FA:  # fe80::/10 → top 10 bits = 1111111010
        addr_type, scope, prefix = "link-local unicast", "link", "fe80::/10"
    elif (val >> 121) == 0x7E:  # fc00::/7 → top 7 bits = 1111110
        addr_type, scope, prefix = "unique local unicast", "site", "fc00::/7"
    elif (val >> 96) & 0xFFFF == 0xFFFF and (val >> 112) == 0:  # ::ffff:0:0/96
        addr_type, scope, prefix = "ipv4-mapped", "n/a", "::ffff:0:0/96"
    elif top8 == 0xFF:
        scope_val = (val >> 112) & 0xF
        addr_type = "multicast"
        scope = MULTICAST_SCOPES.get(scope_val, f"scope {scope_val}")
        prefix = f"ff{scope_val:x}::/16"
        if scope_val == 2 and (val >> 104) & 0xFFFFFF == 0x01FF:
            addr_type = "solicited-node multicast"
    elif (val >> 125) == 0x1:  # 2000::/3 → top 3 bits = 001
        addr_type, scope, prefix = "global unicast", "global", "2000::/3"
    else:
        addr_type, scope, prefix = "reserved / other", "n/a", "?"

    return AddressInfo(
        address=expanded, expanded=expand_ipv6(addr),
        type=addr_type, scope=scope, prefix=prefix,
    )


# ---------------------------------------------------------------------
#  Prefix / subnet extraction
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SubnetInfo:
    cidr: str
    network: str
    first_host: str
    last_host: str
    num_addresses: int


def ipv6_subnet(cidr: str) -> SubnetInfo:
    addr_str, sep, prefix_str = cidr.partition("/")
    if not sep:
        raise ValueError(f"Missing /prefix in {cidr!r}")
    prefix = int(prefix_str)
    if not 0 <= prefix <= 128:
        raise ValueError(f"prefix out of range: {prefix}")
    base = ipv6_to_int(addr_str)
    if prefix == 0:
        mask = 0
    else:
        mask = ((1 << 128) - 1) ^ ((1 << (128 - prefix)) - 1)
    network = base & mask
    host_bits = 128 - prefix
    last = network + ((1 << host_bits) - 1) if prefix < 128 else network
    first = network + 1 if prefix < 128 and prefix > 0 else network
    num = 1 << host_bits
    return SubnetInfo(
        cidr=f"{int_to_ipv6(network)}/{prefix}",
        network=int_to_ipv6(network),
        first_host=int_to_ipv6(first),
        last_host=int_to_ipv6(last),
        num_addresses=num,
    )


# ---------------------------------------------------------------------
#  EUI-64 / link-local
# ---------------------------------------------------------------------

def mac_to_eui64(mac: str) -> str:
    parts = [int(p, 16) for p in mac.replace("-", ":").split(":")]
    if len(parts) != 6:
        raise ValueError(f"Invalid MAC {mac!r}")
    parts[0] ^= 0x02  # flip the Universal/Local bit
    eui = parts[:3] + [0xFF, 0xFE] + parts[3:]
    return ":".join(f"{b:02x}" for b in eui)


def link_local_from_mac(mac: str) -> str:
    """Build the link-local fe80:: address from a 48-bit MAC."""
    iid_groups = mac_to_eui64(mac).split(":")
    b = [int(g, 16) for g in iid_groups]
    g4 = [f"{(b[i] << 8) | b[i+1]:04x}" for i in range(0, 8, 2)]
    return f"fe80::{g4[0]}:{g4[1]}:{g4[2]}:{g4[3]}"


# ---------------------------------------------------------------------
#  Header parser (base 40-byte fixed header)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class IPv6Header:
    version: int
    traffic_class: int
    flow_label: int
    payload_length: int
    next_header: int
    hop_limit: int
    src_addr: str
    dst_addr: str

    @property
    def next_header_name(self) -> str:
        return NEXT_HEADER_MAP.get(self.next_header, f"unknown({self.next_header})")


def parse_ipv6_header(raw: bytes) -> IPv6Header:
    if len(raw) < 40:
        raise ValueError(f"IPv6 header too short: {len(raw)} bytes")
    import struct
    (vtf, payload_len, nxt, hop, src, dst) = struct.unpack("!IHBB16s16s", raw[:40])
    version = (vtf >> 28) & 0xF
    if version != 6:
        raise ValueError(f"Version field is {version}, expected 6")
    return IPv6Header(
        version=version,
        traffic_class=(vtf >> 20) & 0xFF,
        flow_label=vtf & 0xFFFFF,
        payload_length=payload_len,
        next_header=nxt,
        hop_limit=hop,
        src_addr=int_to_ipv6(int.from_bytes(src, "big")),
        dst_addr=int_to_ipv6(int.from_bytes(dst, "big")),
    )


def build_sample_header() -> bytes:
    import struct
    vtf = (6 << 28) | (0x10 << 20) | 0x12345
    src_hex = f"{ipv6_to_int('2001:db8:85a3::8a2e:370:7334'):032x}"
    dst_hex = f"{ipv6_to_int('2001:db8:85a3::1'):032x}"
    return struct.pack(
        "!IHBB", vtf, 0x0400, 6, 64
    ) + bytes.fromhex(src_hex) + bytes.fromhex(dst_hex)


# ---------------------------------------------------------------------
#  Demo
# ---------------------------------------------------------------------

def main() -> None:
    print("=" * 68)
    print("IPv6 Address Parser & Classifier  --  Tanenbaum 5.6.3")
    print("=" * 68)

    print("\n[1] Parse + classify addresses")
    samples = [
        "::",
        "::1",
        "fe80:0000:0000:0000:0202:b3ff:fe1e:8329",
        "2001:0db8:0000:0000:0000:0000:0000:0001",
        "ff02:0000:0000:0000:0000:0000:0000:0001",
        "ff02::1:ff00:0",
        "fd12:3456:789a:1::1",
        "::ffff:192.0.2.1",
    ]
    for a in samples:
        info = classify_ipv6(a)
        print(info)
        print()

    print("[2] Compression (RFC 5952 canonical)")
    full = [
        "2001:0db8:0000:0000:0000:0000:0000:0001",
        "fe80:0000:0000:0000:0202:b3ff:fe1e:8329",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "::1",
        "2001:0db8:0:0:0:0:0:1",
    ]
    for a in full:
        print(f"  {a:<45} -> {compress_ipv6(a)}")

    print("\n[3] Validation")
    for a in ("2001:db8::1", "::1", "2001:db8:::1", "fe80::1", "xyz::1", "::ffff:1.2.3.4"):
        print(f"  {a:<25} valid={validate_ipv6(a)}")

    print("\n[4] EUI-64 interface ID + link-local from MAC")
    for mac in ("00:11:22:33:44:55", "aa:bb:cc:dd:ee:ff", "02:00:5e:10:00:00"):
        iid = mac_to_eui64(mac)
        ll = link_local_from_mac(mac)
        print(f"  MAC {mac}  ->  EUI-64 {iid}")
        print(f"    link-local: {ll}")

    print("\n[5] Subnet extraction")
    for cidr in ("2001:db8::/48", "2001:db8::/64", "2001:db8::/120", "::/0", "2001:db8::/127"):
        s = ipv6_subnet(cidr)
        print(f"  {cidr:<18} net={s.network:<25} first={s.first_host:<25} last={s.last_host}")
        print(f"    addresses: {s.num_addresses:,}")

    print("\n[6] IPv6 base header parse")
    raw = build_sample_header()
    h = parse_ipv6_header(raw)
    print(f"  raw ({len(raw)} bytes): {raw.hex()}")
    print(f"  Version           : {h.version}")
    print(f"  Traffic class     : 0x{h.traffic_class:02X}")
    print(f"  Flow label        : 0x{h.flow_label:05X}")
    print(f"  Payload length    : {h.payload_length}")
    print(f"  Next header       : {h.next_header} ({h.next_header_name})")
    print(f"  Hop limit         : {h.hop_limit}")
    print(f"  Source address    : {h.src_addr}")
    print(f"  Destination       : {h.dst_addr}")


if __name__ == "__main__":
    main()