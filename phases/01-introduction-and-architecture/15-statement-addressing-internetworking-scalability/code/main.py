"""Addressing, Internetworking, and Network Scalability.

A stdlib-only demonstration of three recurring design issues from
Tanenbaum's "Design Issues for the Layers" (Computer Networks 1.3.2):

  * Addressing      -> CIDR subnet arithmetic (hierarchy makes routing scale)
  * Internetworking -> IPv4 fragmentation and reassembly (disparate MTUs)
  * Scalability     -> a flat-vs-aggregated routing-table growth model

Run it:  python3 code/main.py
No third-party packages, no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Low-level IP integer helpers
# ---------------------------------------------------------------------------

IPV4_HEADER_LEN = 20  # bytes, the baseline header with no options
RFC791_MIN_MTU = 576  # every IPv4 host must be able to receive this


def ip_to_int(ip: str) -> int:
    """Convert dotted-decimal 'a.b.c.d' to a 32-bit integer."""
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"bad IPv4 literal: {ip!r}")
    octets = [int(p) for p in parts]
    if any(not 0 <= o <= 255 for o in octets):
        raise ValueError(f"octet out of range in {ip!r}")
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def int_to_ip(value: int) -> str:
    """Convert a 32-bit integer back to dotted-decimal."""
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("integer out of IPv4 range")
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def mask_from_prefix(prefix: int) -> int:
    """Return the 32-bit netmask for a /prefix length."""
    if not 0 <= prefix <= 32:
        raise ValueError(f"bad prefix length: {prefix}")
    return (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0


def network_of(ip: str, prefix: int) -> int:
    """Return the network address (host bits zeroed) as an int."""
    return ip_to_int(ip) & mask_from_prefix(prefix)


# ---------------------------------------------------------------------------
# CIDR subnetting  -- addressing / hierarchy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Subnet:
    network: str
    prefix: int
    broadcast: str
    first_host: str
    last_host: str
    usable_hosts: int


def cidr_subnets(parent_prefix: str, new_prefix: int) -> List[Subnet]:
    """Split a parent CIDR block into subnets of length new_prefix.

    Example: cidr_subnets('198.51.100.0/24', 26) -> four /26 subnets.
    """
    ip_str, _, pre_str = parent_prefix.partition("/")
    parent_prefix_len = int(pre_str)
    if new_prefix <= parent_prefix_len:
        raise ValueError("new_prefix must be longer than the parent prefix")
    if new_prefix > 32:
        raise ValueError("prefix cannot exceed /32")

    base = network_of(ip_str, parent_prefix_len)
    host_bits = 32 - new_prefix
    subnet_size = 1 << host_bits            # addresses per subnet (incl. net+bcast)
    count = 1 << (new_prefix - parent_prefix_len)
    usable = subnet_size - 2 if subnet_size >= 2 else subnet_size

    subnets: List[Subnet] = []
    for i in range(count):
        net = base + i * subnet_size
        bcast = net + subnet_size - 1
        first = net + 1 if usable else net
        last = bcast - 1 if usable else net
        subnets.append(
            Subnet(
                network=int_to_ip(net),
                prefix=new_prefix,
                broadcast=int_to_ip(bcast),
                first_host=int_to_ip(first),
                last_host=int_to_ip(last),
                usable_hosts=usable,
            )
        )
    return subnets


# ---------------------------------------------------------------------------
# IPv4 fragmentation and reassembly  -- internetworking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fragment:
    identification: int
    total_length: int
    frag_offset: int          # field value (in 8-byte units)
    more_fragments: bool
    payload: bytes


@dataclass(frozen=True)
class Datagram:
    identification: int
    src: str
    dst: str
    protocol: int
    payload: bytes            # L4 payload only (IP header not included)


def ipv4_fragment(dg: Datagram, mtu: int) -> List[Fragment]:
    """Split an IPv4 datagram's payload into fragments that fit `mtu`.

    Each fragment carries its own 20-byte IP header, so the maximum
    payload per fragment is mtu - 20, rounded DOWN to a multiple of 8
    (the fragment-offset field is in 8-byte units).
    """
    if mtu < RFC791_MIN_MTU:
        raise ValueError(f"MTU {mtu} below RFC 791 minimum {RFC791_MIN_MTU}")
    max_payload = mtu - IPV4_HEADER_LEN
    # The offset field counts in 8-byte units, so payload per fragment
    # must be a multiple of 8.
    chunk = (max_payload // 8) * 8
    if chunk <= 0:
        raise ValueError("MTU too small to carry any payload")

    fragments: List[Fragment] = []
    offset = 0
    payload = dg.payload
    while offset < len(payload):
        piece = payload[offset:offset + chunk]
        is_last = offset + len(piece) >= len(payload)
        fragments.append(
            Fragment(
                identification=dg.identification,
                total_length=IPV4_HEADER_LEN + len(piece),
                frag_offset=offset // 8,
                more_fragments=not is_last,
                payload=piece,
            )
        )
        offset += len(piece)
    return fragments


def reassemble(fragments: List[Fragment]) -> bytes:
    """Reassemble fragment payloads back into the original L4 payload.

    Mirrors RFC 815's hole-descriptor approach: sort by offset, reject
    overlaps, and assert the result is contiguous and complete.
    """
    if not fragments:
        return b""
    ordered = sorted(fragments, key=lambda f: f.frag_offset)
    seen_end = 0
    out = bytearray()
    for frag in ordered:
        start = frag.frag_offset * 8
        if start < seen_end:
            raise ValueError(
                f"overlapping fragment at offset {start} (already have {seen_end})"
            )
        if start > seen_end:
            raise ValueError(f"gap before offset {start}; datagram incomplete")
        out.extend(frag.payload)
        seen_end = start + len(frag.payload)
    if not any(not f.more_fragments for f in fragments):
        raise ValueError("no fragment cleared the MF flag; tail missing")
    return bytes(out)


# ---------------------------------------------------------------------------
# Routing-table growth model  -- scalability
# ---------------------------------------------------------------------------


def routing_table_growth(sites: int, customers_per_isp: int = 256) -> Tuple[int, int]:
    """Return (flat_routes, aggregated_routes) for `sites` customer sites.

    Flat model: every site advertises its own /24 -> one route per site.
    Aggregated model: one ISP advertises one prefix per `customers_per_isp`
    sites -> routes = ceil(sites / customers_per_isp).
    """
    if sites < 0 or customers_per_isp <= 0:
        raise ValueError("sites must be >= 0, customers_per_isp > 0")
    flat = sites
    aggregated = (sites + customers_per_isp - 1) // customers_per_isp
    return flat, aggregated


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def main() -> None:
    print("== Addressing: CIDR subnetting ==")
    parent = "198.51.100.0/24"
    print(f"Splitting {parent} into /26 subnets:\n")
    print(f"{'network':<22}{'broadcast':<18}{'first host':<18}"
          f"{'last host':<18}{'usable'}")
    for s in cidr_subnets(parent, 26):
        print(f"{s.network + '/' + str(s.prefix):<22}{s.broadcast:<18}"
              f"{s.first_host:<18}{s.last_host:<18}{s.usable_hosts}")

    print("\n== Internetworking: IPv4 fragmentation ==")
    payload = bytes(range(256)) * 15 + bytes(range(140))  # 3840 + 140 = 3980 bytes
    dg = Datagram(identification=0x1234, src="198.51.100.10",
                  dst="203.0.113.9", protocol=17, payload=payload)
    mtu = 1500
    frags = ipv4_fragment(dg, mtu)
    print(f"Datagram id=0x{dg.identification:04x}, payload={len(payload)} B, "
          f"MTU={mtu} -> {len(frags)} fragments\n")
    print(f"{'#':<3}{'total_len':<11}{'offset':<8}{'MF':<4}{'payload B'}")
    for i, f in enumerate(frags, 1):
        print(f"{i:<3}{f.total_length:<11}{f.frag_offset:<8}"
              f"{'1' if f.more_fragments else '0':<4}{len(f.payload)}")

    reassembled = reassemble(frags)
    print(f"\nReassembled payload: {len(reassembled)} B; "
          f"byte-identical to original: {reassembled == dg.payload}")

    print("\n== Scalability: routing-table growth ==")
    flat, agg = routing_table_growth(65536, customers_per_isp=256)
    print(f"65,536 customer sites:")
    print(f"  flat (/24 per site):        {flat:>7} routes")
    print(f"  aggregated (/16 per ISP):   {agg:>7} routes")
    print(f"  reduction factor:           {flat // agg}x")

    print("\n== Fragmenting the 576-byte minimum MTU ==")
    frags576 = ipv4_fragment(dg, RFC791_MIN_MTU)
    print(f"MTU=576 -> {len(frags576)} fragments; first payload "
          f"{len(frags576[0].payload)} B (offset must be /8 -> "
          f"payload multiple of 8: {len(frags576[0].payload) % 8 == 0})")
    assert reassemble(frags576) == dg.payload
    print("Reassembly at 576 MTU also byte-identical: True")


if __name__ == "__main__":
    main()
