"""Network interconnection simulator: repeaters, bridges, routers, tunneling.

Models a packet crossing dissimilar networks (802.11, MPLS, Ethernet) to show
how each interconnection device processes headers at its OSI layer, then
demonstrates tunneling (IPv6 over IPv4) and the failure of protocol conversion.

Run: python3 code/main.py   (stdlib only, no network calls)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# --- Network link types and their properties ---------------------------------

LINK_MTU = {
    "802.11": 2304,   # 802.11 can carry larger frames than Ethernet
    "MPLS": 1500,     # MPLS adds a 4-byte label but MTU is typically 1500
    "Ethernet": 1500,
    "IPv4-Internet": 1500,
    "IPv6-Island": 2304,
}


@dataclass
class Packet:
    """A simplified network-layer packet."""

    protocol: str          # "IPv4" | "IPv6"
    src_addr: str
    dst_addr: str
    payload_size: int
    flow_label: int = 0     # IPv6 only
    ext_headers: List[str] = field(default_factory=list)
    ttl: int = 64

    def total_size(self) -> int:
        header = 40 if self.protocol == "IPv6" else 20
        ext = 8 * len(self.ext_headers)
        return header + ext + self.payload_size

    def describe(self) -> str:
        parts = [f"{self.protocol} {self.src_addr}->{self.dst_addr}",
                 f"payload={self.payload_size}B total={self.total_size()}B"]
        if self.protocol == "IPv6":
            parts.append(f"flow=0x{self.flow_label:05x}")
            if self.ext_headers:
                parts.append(f"ext={self.ext_headers}")
        parts.append(f"ttl={self.ttl}")
        return " ".join(parts)


@dataclass
class Fragment:
    offset: int
    size: int
    more: bool  # More-Fragments flag

    def __repr__(self) -> str:
        return (f"Fragment(offset={self.offset}, size={self.size}B, "
                f"MF={'1' if self.more else '0'})")


# --- Interconnection devices -------------------------------------------------

def repeater(bits_in: str) -> str:
    """Physical layer (OSI 1): regenerate and retransmit bits. No protocol awareness."""
    print("  [Repeater]    L1  regenerating bits, no header inspection")
    return bits_in


def bridge(frame_dest_mac: str, frame_payload: bytes) -> Tuple[str, bytes]:
    """Data link layer (OSI 2): forward whole frame by MAC address."""
    print(f"  [Bridge]      L2  forwarding frame by MAC dest={frame_dest_mac}")
    return frame_dest_mac, frame_payload


def router(pkt: Packet, in_link: str, out_link: str) -> Packet:
    """Network layer (OSI 3): strip frame, consult IP address, re-encapsulate."""
    pkt.ttl -= 1
    print(f"  [Router]      L3  stripped {in_link} frame, read IP dst={pkt.dst_addr}, "
          f"routing table -> next hop via {out_link} (ttl now {pkt.ttl})")
    return pkt


def mpls_push(pkt: Packet, label: int) -> Packet:
    """Encapsulate IP packet with an MPLS label stack entry."""
    print(f"  [MPLS]        L2.5 pushing label={label} (EXP=0, S=1, TTL={pkt.ttl})")
    return pkt


def mpls_pop(pkt: Packet) -> Packet:
    print("  [MPLS]        L2.5 popping label stack")
    return pkt


def fragment_packet(pkt: Packet, mtu: int) -> List[Fragment]:
    """Split a packet to fit a smaller MTU. Returns fragment descriptors."""
    header = 40 if pkt.protocol == "IPv6" else 20
    max_payload_per_frag = mtu - header
    frags: List[Fragment] = []
    remaining = pkt.payload_size
    offset = 0
    while remaining > 0:
        chunk = min(remaining, max_payload_per_frag)
        frags.append(Fragment(offset=offset, size=chunk, more=(remaining - chunk) > 0))
        offset += chunk
        remaining -= chunk
    return frags


# --- Journey 1: routed path 802.11 -> MPLS -> Ethernet ------------------------

def journey_routed(src_pkt_size: int = 2300) -> None:
    print("\n=== Journey 1: Routed path 802.11 -> MPLS -> Ethernet ===")
    print(f"Source packet size: {src_pkt_size} bytes\n")
    pkt = Packet(protocol="IPv6", src_addr="2001:db8::1", dst_addr="2001:db8::99",
                 payload_size=src_pkt_size, flow_label=0x12345,
                 ext_headers=["Hop-by-Hop"])
    print(f"Source creates: {pkt.describe()}\n")

    print("-- Boundary 1: 802.11 source -> first router --")
    print("  [802.11]      L2  frame encap, EtherType=0x86DD, dest=router1 MAC")
    pkt = router(pkt, in_link="802.11", out_link="MPLS")
    pkt = mpls_push(pkt, label=100)

    print("\n-- Boundary 2: MPLS -> second router --")
    pkt = mpls_pop(pkt)
    pkt = router(pkt, in_link="MPLS", out_link="Ethernet")

    print("\n-- Boundary 3: Ethernet destination (fragmentation) --")
    eth_mtu = LINK_MTU["Ethernet"]
    if pkt.total_size() > eth_mtu:
        frags = fragment_packet(pkt, eth_mtu)
        print(f"  [Frag]        L3  packet {pkt.total_size()}B > Ethernet MTU {eth_mtu}B "
              f"-> {len(frags)} fragments:")
        for f in frags:
            print(f"    {f}")
    else:
        print(f"  [Frag]        packet fits in Ethernet MTU ({pkt.total_size()} <= {eth_mtu})")

    print(f"\nDestination receives: {pkt.describe()}")
    print(f"  flow_label preserved: 0x{pkt.flow_label:05x}")
    print(f"  ext_headers preserved: {pkt.ext_headers}")
    print(f"  ttl decremented by 2 hops: {pkt.ttl}")


# --- Journey 2: tunneled path IPv6 over IPv4 ----------------------------------

def journey_tunneled() -> None:
    print("\n=== Journey 2: Tunneled path IPv6 over IPv4 (Paris -> London) ===\n")
    inner = Packet(protocol="IPv6", src_addr="2001:db8:dead::1",
                   dst_addr="2001:db8:beef::2", payload_size=1400,
                   flow_label=0xABCDE, ext_headers=["Hop-by-Hop"])
    print(f"Paris host creates inner packet: {inner.describe()}\n")

    print("-- Paris router: encapsulate IPv6 in IPv4 --")
    outer = Packet(protocol="IPv4", src_addr="192.0.2.1", dst_addr="198.51.100.1",
                   payload_size=inner.total_size(), ttl=64)
    print("  [Tunnel]      inner IPv6 -> outer IPv4 payload")
    print(f"  [Tunnel]      outer: {outer.describe()}")
    print("  [Tunnel]      outer IPv4 protocol field = 41 (IPv6 encapsulation, RFC 2473)\n")

    print("-- IPv4 Internet transit --")
    print("  [IPv4 routers] see only the outer IPv4 header, route by 198.51.100.1")
    outer.ttl -= 1
    print(f"  [IPv4]        outer ttl decremented to {outer.ttl}\n")

    print("-- London router: decapsulate --")
    print("  [Tunnel]      strip outer IPv4 header, recover inner IPv6 packet")
    print(f"  [Tunnel]      inner: {inner.describe()}\n")

    print(f"London host receives: {inner.describe()}")
    print(f"  flow_label preserved through tunnel: 0x{inner.flow_label:05x}")
    print(f"  ext_headers preserved: {inner.ext_headers}")
    print(f"  inner ttl (untouched by IPv4 routers): {inner.ttl}")
    print(f"  outer ttl (decremented by IPv4 transit): {outer.ttl}")
    print("  Only Paris and London routers understood both IPv4 and IPv6.")


# --- Journey 3: protocol conversion failure -----------------------------------

def attempt_conversion() -> None:
    print("\n=== Journey 3: Protocol conversion IPv6 -> IPv4 (and failure) ===\n")
    v6 = Packet(protocol="IPv6", src_addr="2001:db8:dead:beef::1234",
                dst_addr="2001:db8:cafe:feed::5678", payload_size=500,
                flow_label=0x1F2F3, ext_headers=["Hop-by-Hop", "Routing"])
    print(f"Original IPv6 packet: {v6.describe()}\n")

    losses = [
        ("source address", "128 bits (2001:db8:dead:beef::1234)",
         "32-bit IPv4 field cannot hold 128 bits"),
        ("destination address", "128 bits (2001:db8:cafe:feed::5678)",
         "32-bit IPv4 field cannot hold 128 bits"),
        ("flow label", "20 bits (0x1f2f3)", "no IPv4 equivalent field"),
        ("traffic class", "8 bits", "maps roughly to DSCP but not 1:1"),
        ("extension headers", "Hop-by-Hop, Routing", "no IPv4 equivalent; dropped entirely"),
        ("hop limit semantics", "per-hop processing", "maps to TTL but loses extension-header behavior"),
    ]
    print("Conversion attempt field-by-field:")
    for field_name, v6_val, reason in losses:
        print(f"  {field_name:22s} v6={v6_val}")
        print(f"  {'':22s} -> LOST: {reason}")
    print(f"\nResult: translation incomplete. {len(losses)} fields lost or degraded.")
    print("This is why IP survives as a lowest common denominator: it demands")
    print("little of underlying networks but offers only best-effort service.")


# --- Device comparison table -------------------------------------------------

def print_device_table() -> None:
    print("=== Interconnection device hierarchy ===\n")
    rows: List[Tuple[str, str, str, str]] = [
        ("Repeater/hub", "Physical (1)", "bits", "regenerate signal"),
        ("Bridge/switch", "Data link (2)", "MAC address", "forward whole frame"),
        ("Router", "Network (3)", "IP address", "strip frame, re-encapsulate"),
        ("Gateway", "Transport/App (4-7)", "port/app hdr", "translate upper layers"),
    ]
    print(f"{'Device':16s} {'OSI layer':16s} {'Inspects':14s} {'Does':24s}")
    print("-" * 72)
    for dev, layer, insp, does in rows:
        print(f"{dev:16s} {layer:16s} {insp:14s} {does:24s}")
    print()


def main() -> None:
    print_device_table()
    journey_routed(src_pkt_size=2300)
    journey_tunneled()
    attempt_conversion()
    print("\n=== Summary ===")
    print("Routers join dissimilar networks by reading IP and re-encapsulating.")
    print("Tunnels carry same-protocol packets through foreign networks as freight.")
    print("Protocol conversion fails when source fields have no target equivalent")
    print("(128-bit IPv6 address vs 32-bit IPv4 field).")
    print("IP won as the lowest common denominator: demands little, offers best-effort.")


if __name__ == "__main__":
    main()