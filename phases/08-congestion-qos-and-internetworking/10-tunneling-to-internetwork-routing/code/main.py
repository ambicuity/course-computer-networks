#!/usr/bin/env python3
"""Tunneling to Internetwork Routing (Tanenbaum sections 5.5.3 and 5.5.4).

Stdlib only.  A tunnel encapsulation/decapsulation simulator with:

  1. IP-in-IP  (RFC 2003, proto 4,  +20 B outer header)
  2. GRE       (RFC 2784, proto 47, +24 B: 20 IP + 4 GRE delivery header)
  3. 6to4      (RFC 3056, proto 41, +20 B, exit address embedded in prefix)

Each encapsulate() adds the correct outer header bytes and reports the
header stack; decapsulate() strips them and recovers the inner packet
byte-for-byte.  An MTU tracker computes the effective inner MTU per
tunnel type, flags oversize packets, and shows the IPv6 drop vs. IPv4
fragment path so the PMTU black hole is visible.  A two-level routing
model (IGP inside an AS, BGP across ASes) performs longest-prefix match
and walks the AS path with a policy decision.

Run:  python3 code/main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Tunnel type definitions: overhead and protocol numbers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TunnelType:
    name: str
    protocol: int          # IP protocol number in the outer header
    overhead: int          # bytes added by encapsulation
    rfc: str

IP_IN_IP = TunnelType("IP-in-IP", 4, 20, "RFC 2003")
GRE      = TunnelType("GRE",     47, 24, "RFC 2784")   # 20 IP + 4 GRE hdr
SIXTO4   = TunnelType("6to4",    41, 20, "RFC 3056")

TUNNELS: dict[str, TunnelType] = {
    "ip-in-ip": IP_IN_IP,
    "gre":      GRE,
    "6to4":     SIXTO4,
}


# ---------------------------------------------------------------------------
# Packet model
# ---------------------------------------------------------------------------

@dataclass
class Packet:
    """A minimal network-layer packet: addresses + payload + a 'version' tag."""
    version: int               # 4 or 6
    src: str
    dst: str
    payload: bytes
    hop_limit: int = 64

    def total_bytes(self) -> int:
        """Wire size: fixed header + payload (40 for IPv6, 20 for IPv4)."""
        hdr = 40 if self.version == 6 else 20
        return hdr + len(self.payload)

    def describe(self) -> str:
        return (f"IPv{self.version} src={self.src} dst={self.dst} "
                f"hop={self.hop_limit} total={self.total_bytes()}B")


@dataclass
class TunneledPacket:
    """An inner packet carried inside an outer packet across a tunnel."""
    outer: Packet
    inner: Packet
    tunnel: TunnelType

    def wire_bytes(self) -> int:
        return self.outer.total_bytes() + self.inner.total_bytes()

    def describe(self) -> str:
        lines = [
            f"  OUTER {self.outer.describe()}",
            f"    proto={self.tunnel.protocol} ({self.tunnel.name}, "
            f"{self.tunnel.rfc})  overhead=+{self.tunnel.overhead}B",
            f"  INNER {self.inner.describe()}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tunnel endpoints (multiprotocol routers)
# ---------------------------------------------------------------------------

class TunnelEndpoint:
    """A multiprotocol router that can encapsulate or decapsulate packets."""

    def __init__(self, name: str, ipv4_addr: str, ipv6_prefix: str) -> None:
        self.name = name
        self.ipv4_addr = ipv4_addr
        self.ipv6_prefix = ipv6_prefix

    def encapsulate(self, inner: Packet, peer: "TunnelEndpoint",
                    tunnel: TunnelType) -> TunneledPacket:
        outer = Packet(version=4, src=self.ipv4_addr, dst=peer.ipv4_addr,
                       payload=inner.payload, hop_limit=64)
        print(f"  [{self.name}] ENCAPSULATE via {tunnel.name} "
              f"(proto {tunnel.protocol}, +{tunnel.overhead}B)")
        tp = TunneledPacket(outer=outer, inner=inner, tunnel=tunnel)
        print(tp.describe())
        return tp

    def decapsulate(self, tp: TunneledPacket) -> Packet:
        print(f"  [{self.name}] DECAPSULATE: strip outer IPv4 header "
              f"(proto {tp.tunnel.protocol})")
        print(f"       recovered inner: {tp.inner.describe()}")
        return tp.inner


# ---------------------------------------------------------------------------
# MTU tracker: effective inner MTU per tunnel type
# ---------------------------------------------------------------------------

def effective_mtu(path_mtu: int, tunnel: TunnelType) -> int:
    """Path MTU minus the tunnel's header overhead."""
    return path_mtu - tunnel.overhead


def mtu_report(path_mtu: int) -> None:
    print(f"  Path MTU = {path_mtu} bytes")
    print(f"  {'Tunnel':<12} {'Overhead':>8} {'Eff. inner MTU':>16}  {'Note'}")
    print(f"  {'-'*12} {'-'*8} {'-'*16}  {'-'*28}")
    for t in TUNNELS.values():
        eff = effective_mtu(path_mtu, t)
        note = "above IPv6 min 1280" if eff >= 1280 else "BELOW IPv6 min!"
        print(f"  {t.name:<12} {t.overhead:>8} {eff:>16}  {note}")
    print()


def check_packet_fits(inner: Packet, path_mtu: int,
                      tunnel: TunnelType) -> None:
    eff = effective_mtu(path_mtu, tunnel)
    wire = inner.total_bytes()
    print(f"  Inner packet wire size = {wire}B, "
          f"effective MTU = {eff}B ({tunnel.name})")
    if wire <= eff:
        print(f"  -> FITS: delivered without fragmentation")
    elif inner.version == 6:
        print(f"  -> DROP (IPv6 never fragments)")
        print(f"     ICMPv6 Packet Too Big sent; if filtered -> PMTU black hole")
    else:
        nfrag = (wire + eff - 1) // eff
        print(f"  -> FRAGMENT (IPv4, DF clear): {nfrag} fragments of <= {eff}B")


# ---------------------------------------------------------------------------
# 6to4 address derivation (RFC 3056): 2002:vvvv:wwww:: from IPv4
# ---------------------------------------------------------------------------

def sixto4_prefix(ipv4: str) -> str:
    """Embed an IPv4 address into the 2002::/16 prefix."""
    octets = [int(o) for o in ipv4.split(".")]
    return (f"2002:{octets[0]:02x}{octets[1]:02x}:"
            f"{octets[2]:02x}{octets[3]:02x}::")


# ---------------------------------------------------------------------------
# Two-level routing (section 5.5.4): IGP inside, BGP across ASes
# ---------------------------------------------------------------------------

@dataclass
class IGPRoute:
    prefix: str
    next_hop: str
    metric: int


@dataclass
class BGPRoute:
    prefix: str
    as_path: list[int]
    next_hop_as: int
    local_pref: int = 100
    policy: str = "transit"


class AutonomousSystem:
    def __init__(self, asn: int, name: str, igp: str) -> None:
        self.asn = asn
        self.name = name
        self.igp = igp
        self.igp_routes: list[IGPRoute] = []
        self.bgp_routes: list[BGPRoute] = []

    def add_igp(self, prefix: str, hop: str, metric: int) -> None:
        self.igp_routes.append(IGPRoute(prefix, hop, metric))

    def add_bgp(self, prefix: str, as_path: list[int],
                local_pref: int = 100, policy: str = "transit") -> None:
        self.bgp_routes.append(
            BGPRoute(prefix, as_path, as_path[-1], local_pref, policy))

    def igp_lookup(self, dst: str) -> Optional[IGPRoute]:
        """Longest-prefix match among interior routes."""
        best: Optional[IGPRoute] = None
        for r in self.igp_routes:
            if dst.startswith(r.prefix):
                if best is None or len(r.prefix) > len(best.prefix):
                    best = r
        return best

    def bgp_lookup(self, dst: str) -> Optional[BGPRoute]:
        """BGP decision: LOCAL_PREF desc, then AS_PATH length asc, then metric."""
        cands = [r for r in self.bgp_routes if dst.startswith(r.prefix)]
        if not cands:
            return None
        cands.sort(key=lambda r: (-r.local_pref, len(r.as_path)))
        return cands[0]


def routing_demo() -> None:
    as100 = AutonomousSystem(100, "EuroISP", "OSPF")
    as200 = AutonomousSystem(200, "TransitCo", "IS-IS")
    as300 = AutonomousSystem(300, "US-ISP", "OSPF")

    as100.add_igp("10.1.1", "r-eu-1", 10)
    as100.add_igp("10.1.2", "r-eu-2", 20)
    as100.add_bgp("10.2", [100, 200, 300], local_pref=100, policy="transit")
    as100.add_bgp("10.2", [100, 400, 300], local_pref=150, policy="peer")

    as200.add_igp("172.16.0", "r-t-1", 5)
    as200.add_bgp("10.2", [200, 300], local_pref=100, policy="customer")

    as300.add_igp("10.2.0", "r-us-1", 15)

    for dst in ("10.1.1.5", "10.2.0.9"):
        print(f"  Lookup destination {dst} from AS100:")
        igp = as100.igp_lookup(dst)
        if igp:
            print(f"    IGP: prefix={igp.prefix} via {igp.next_hop} "
                  f"metric={igp.metric}")
            continue
        bgp = as100.bgp_lookup(dst)
        if bgp:
            print(f"    BGP: prefix={bgp.prefix} AS_PATH={bgp.as_path} "
                  f"LOCAL_PREF={bgp.local_pref} policy={bgp.policy}")
            print(f"    -> BGP chose the LOCAL_PREF=150 peer path, "
                  f"NOT the shorter AS_PATH, showing policy > metric")
        else:
            print(f"    no route -> DROP")
        print()


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("TUNNELING (Tanenbaum 5.5.3) -- IPv6 over IPv4, Paris to London")
    print("=" * 72)
    print()
    paris = TunnelEndpoint("Paris-MR", "192.0.2.1", "2001:db8:1::")
    london = TunnelEndpoint("London-MR", "192.0.2.2", "2001:db8:2::")
    inner = Packet(version=6, src="2001:db8:1::5", dst="2001:db8:2::9",
                   payload=b"bank-transfer" * 8)
    print(f"  Host sends: {inner.describe()}")
    print()
    for key in ("ip-in-ip", "gre", "6to4"):
        t = TUNNELS[key]
        print(f"  --- {t.name} ({t.rfc}) ---")
        enc = paris.encapsulate(inner, london, t)
        print(f"  [IPv4 Internet] carries outer packet, sees only proto "
              f"{t.protocol}; inner payload is opaque")
        out = london.decapsulate(enc)
        print(f"  Delivered: {out.describe()}")
        print(f"  Inner byte-identical to original: "
              f"{out.payload == inner.payload}")
        print()

    print("=" * 72)
    print("MTU TRACKER -- header overhead and effective inner MTU")
    print("=" * 72)
    print()
    mtu_report(1500)
    mtu_report(1492)
    print("  Oversize check: 1452-byte IPv6 inner via IP-in-IP, path 1500:")
    big = Packet(version=6, src="2001:db8:1::5", dst="2001:db8:2::9",
                 payload=b"x" * 1412)   # 1412 + 40 hdr = 1452
    check_packet_fits(big, 1500, IP_IN_IP)
    print()
    print("  Oversize check: same 1452-byte IPv6 inner via GRE, path 1500:")
    check_packet_fits(big, 1500, GRE)
    print()

    print("=" * 72)
    print("6to4 ADDRESS DERIVATION (RFC 3056)")
    print("=" * 72)
    print()
    for ipv4 in ("192.0.2.2", "203.0.113.42"):
        print(f"  IPv4 {ipv4}  ->  6to4 prefix {sixto4_prefix(ipv4)}")
    print()

    print("=" * 72)
    print("INTERNETWORK ROUTING (Tanenbaum 5.5.4) -- two-level, AS-based")
    print("=" * 72)
    print()
    routing_demo()
    print()
    print("  Failure mode: if London-MR is unreachable, the inner IPv6")
    print("  packet is encapsulated but never decapsulated.  Hosts see an")
    print("  IPv6 timeout, NOT an IPv4 error -- the symptom is on the")
    print("  wrong layer.  Trace at BOTH layers to diagnose tunnels.")


if __name__ == "__main__":
    main()