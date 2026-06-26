#!/usr/bin/env python3
"""MTU Black Hole (Integrated Troubleshooting Lab 04).

Reproduces the wire format of the packets involved in PMTUD and walks a
four-command diagnostic chain against four scenarios:

  pmtud_ok            - PMTUD works: ICMP Type 3 Code 4 is returned
  pmtud_blackhole     - large packets disappear; ICMP is filtered
  mtu_mismatch        - tunnel MTU is left at 1500 but the path is 1400
  tunnel_overhead     - IPsec tunnel with full AES-GCM overhead

Run:  python3 main.py [--mode pmtud_ok|pmtud_blackhole|mtu_mismatch|tunnel_overhead|all]
"""
from __future__ import annotations

import argparse
import enum
import struct
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    PMTUD_OK = "pmtud_ok"
    PMTUD_BLACKHOLE = "pmtud_blackhole"
    MTU_MISMATCH = "mtu_mismatch"
    TUNNEL_OVERHEAD = "tunnel_overhead"


# ---------------------------------------------------------------------------
# Wire-format helpers
# ---------------------------------------------------------------------------
def ip_checksum(header: bytes) -> int:
    """Standard IPv4 header checksum (one's-complement sum)."""
    if len(header) % 2:
        header += b"\x00"
    total = 0
    for i in range(0, len(header), 2):
        total += (header[i] << 8) | header[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def build_ipv4_packet(payload_len: int, df: bool = True,
                     identification: int = 0x1234) -> bytes:
    """Build a minimal IPv4 header with the given DF bit and total length."""
    total_length = 20 + payload_len
    flags_fragment = (0x4000 if df else 0x0000) | 0x0000
    # Header (without checksum) for checksum computation
    header_no_cksum = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,                # version=4, ihl=5
        0x00,                # DSCP/ECN
        total_length,
        identification,
        flags_fragment,
        64,                  # TTL
        6,                   # protocol = TCP
        0,                   # checksum placeholder
        b"\x0a\x00\x00\x01",  # src 10.0.0.1
        b"\x0a\x00\x00\x02",  # dst 10.0.0.2
    )
    cksum = ip_checksum(header_no_cksum)
    return struct.pack(
        ">BBHHHBBH4s4s",
        0x45, 0x00, total_length, identification, flags_fragment,
        64, 6, cksum,
        b"\x0a\x00\x00\x01", b"\x0a\x00\x00\x02",
    )


def build_tcp_syn_with_mss(mss: int) -> bytes:
    """Build a minimal TCP SYN header with the MSS option (4 bytes)."""
    # TCP header (20 bytes) + MSS option (4 bytes: kind=2, len=4, value=mss)
    # SYN flag = 0x02
    tcp_header = struct.pack(
        ">HHIIBBHHH",
        49152,     # src port
        443,       # dst port
        0x00000001,  # seq
        0x00000000,  # ack
        0x60,      # data offset = 6 (24 bytes incl. options), reserved
        0x02,      # SYN
        0xFFFF,    # window
        0,         # checksum (would be computed over pseudo-header + segment)
        0,         # urgent pointer
    )
    mss_option = struct.pack(">BBH", 2, 4, mss)
    return tcp_header + mss_option


def build_icmp_type3_code4(next_hop_mtu: int, original_packet: bytes) -> bytes:
    """Build an ICMP Type 3 Code 4 'Fragmentation Needed' message.

    Wire format: type(1) + code(1) + checksum(2) + reserved(2) + next-hop-mtu(2)
                  + IP header (20) + 8 bytes of original packet
    """
    body = struct.pack(">BBHHH", 3, 4, 0, 0, next_hop_mtu)
    # Truncate original packet to 8 bytes of payload after the IP header
    original_header = original_packet[:20]
    original_payload = original_packet[20:28]
    msg = body + original_header + original_payload
    cksum = ip_checksum(msg)
    msg = struct.pack(">BBHHH", 3, 4, cksum, 0, next_hop_mtu)
    return msg + original_header + original_payload


# ---------------------------------------------------------------------------
# Synthetic path
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Hop:
    name: str
    mtu: int
    filters_icmp: bool = False


@dataclass
class MtuPath:
    hops: list[Hop] = field(default_factory=list)

    def min_mtu(self) -> int:
        return min(h.mtu for h in self.hops)

    def bottleneck(self) -> Hop:
        return min(self.hops, key=lambda h: h.mtu)

    def tracepath(self, start_mtu: int) -> tuple[int, Hop | None]:
        """Simulate `tracepath` walking the path from start_mtu down."""
        cur = start_mtu
        for h in self.hops:
            if h.mtu < cur:
                cur = h.mtu
                # In a real tracepath, if the hop's ICMP filter blocks the
                # response, the trace continues; if PMTUD works, the next-hop
                # MTU is reported. For simplicity, we assume the response is
                # seen at the bottleneck and we return the minimum MTU.
                return cur, h
        return cur, None

    def pmtud_works(self) -> bool:
        """PMTUD works iff the bottleneck hop does not filter ICMP Type 3 Code 4."""
        return not self.bottleneck().filters_icmp


# ---------------------------------------------------------------------------
# Diagnostic chain
# ---------------------------------------------------------------------------
@dataclass
class DiagResult:
    step: int
    name: str
    finding: str
    healthy: bool
    points_to: str
    decisive: bool


def cmd_ip_route_get(path: MtuPath, target: str) -> DiagResult:
    return DiagResult(1, f"ip route get {target}",
                       f"route present, kernel PMTUD cache empty (no probe yet)",
                       healthy=True, points_to="initial", decisive=False)


def cmd_tracepath(path: MtuPath, target: str, start_mtu: int = 1500) -> DiagResult:
    min_mtu, bottleneck = path.tracepath(start_mtu)
    if min_mtu >= 1500:
        return DiagResult(2, f"tracepath -m 1500 {target}",
                           f"pmtu 1500 (no bottleneck found)",
                           healthy=True, points_to="none", decisive=False)
    return DiagResult(2, f"tracepath -m 1500 {target}",
                       f"pmtu {min_mtu} at hop {bottleneck.name if bottleneck else '?'}",
                       healthy=False,
                       points_to=bottleneck.name if bottleneck else "unknown",
                       decisive=True)


def cmd_ip_link(iface: str, expected_mtu: int, actual_mtu: int) -> DiagResult:
    if actual_mtu == expected_mtu:
        return DiagResult(3, f"ip link show {iface}",
                           f"mtu {actual_mtu} (expected {expected_mtu})",
                           healthy=True, points_to="none", decisive=False)
    return DiagResult(3, f"ip link show {iface}",
                       f"mtu {actual_mtu} (expected {expected_mtu})",
                       healthy=False, points_to=iface, decisive=True)


def cmd_tcpdump_syn(iface: str, observed_mss: int, expected_mss: int) -> DiagResult:
    if observed_mss == expected_mss:
        return DiagResult(4, f"tcpdump -ni {iface} 'tcp[tcpflags] & tcp-syn != 0'",
                           f"SYN MSS={observed_mss} (expected)",
                           healthy=True, points_to="none", decisive=False)
    return DiagResult(4, f"tcpdump -ni {iface} 'tcp[tcpflags] & tcp-syn != 0'",
                       f"SYN MSS={observed_mss} (expected {expected_mss})",
                       healthy=False, points_to="MSS or tunnel config",
                       decisive=True)


def cmd_tcpdump_icmp(iface: str, saw_icmp: bool) -> DiagResult:
    if saw_icmp:
        return DiagResult(5, f"tcpdump -ni {iface} 'icmp'",
                           "ICMP Type 3 Code 4 seen from bottleneck",
                           healthy=True, points_to="none", decisive=False)
    return DiagResult(5, f"tcpdump -ni {iface} 'icmp'",
                       "no ICMP Type 3 Code 4 from bottleneck",
                       healthy=False, points_to="ICMP filter on path",
                       decisive=True)


def run_diag(mode: FailureMode) -> list[DiagResult]:
    if mode is FailureMode.PMTUD_OK:
        path = MtuPath(hops=[
            Hop("10.0.0.1", 1500),
            Hop("core-1", 1500),
            Hop("core-2", 1400),         # bottleneck
            Hop("server", 1500),
        ])
        return [
            cmd_ip_route_get(path, "10.0.0.2"),
            cmd_tracepath(path, "10.0.0.2"),
            cmd_ip_link("tun0", 1400, 1400),
            cmd_tcpdump_syn("tun0", 1360, 1360),
            cmd_tcpdump_icmp("tun0", saw_icmp=path.pmtud_works()),
        ]
    if mode is FailureMode.PMTUD_BLACKHOLE:
        path = MtuPath(hops=[
            Hop("10.0.0.1", 1500),
            Hop("core-1", 1500),
            Hop("core-2", 1400, filters_icmp=True),   # bottleneck + ICMP filter
            Hop("server", 1500),
        ])
        return [
            cmd_ip_route_get(path, "10.0.0.2"),
            cmd_tracepath(path, "10.0.0.2"),
            cmd_ip_link("tun0", 1400, 1400),
            cmd_tcpdump_syn("tun0", 1460, 1360),       # kernel still advertises 1460
            cmd_tcpdump_icmp("tun0", saw_icmp=path.pmtud_works()),
        ]
    if mode is FailureMode.MTU_MISMATCH:
        # Tunnel interface MTU is 1500 but the path is 1400; PMTUD works
        # but the SYN's MSS=1460 means segments are 1500 bytes and get dropped.
        path = MtuPath(hops=[
            Hop("10.0.0.1", 1500),
            Hop("core-1", 1500),
            Hop("core-2", 1400),
            Hop("server", 1500),
        ])
        return [
            cmd_ip_route_get(path, "10.0.0.2"),
            cmd_tracepath(path, "10.0.0.2"),
            cmd_ip_link("tun0", 1400, 1500),            # MISCONFIGURED
            cmd_tcpdump_syn("tun0", 1460, 1360),
            cmd_tcpdump_icmp("tun0", saw_icmp=path.pmtud_works()),
        ]
    # TUNNEL_OVERHEAD
    path = MtuPath(hops=[
        Hop("10.0.0.1", 1500),
        Hop("ipsec-gw", 1500),                        # outer link is 1500
        Hop("mpls-vpn", 1400),                        # inner link is 1400
        Hop("server", 1500),
    ])
    return [
        cmd_ip_route_get(path, "10.0.0.2"),
        cmd_tracepath(path, "10.0.0.2"),
        cmd_ip_link("ipsec0", 1380, 1500),              # tunnel MTU not set
        cmd_tcpdump_syn("ipsec0", 1460, 1360),
        cmd_tcpdump_icmp("ipsec0", saw_icmp=path.pmtud_works()),
    ]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render_packets(mode: FailureMode) -> None:
    """Print the wire format of a few key packets for reference."""
    pkt = build_ipv4_packet(payload_len=1480, df=True)
    syn = build_tcp_syn_with_mss(1460)
    icmp = build_icmp_type3_code4(next_hop_mtu=1400, original_packet=pkt)
    print("=" * 78)
    print(f"Wire-format reference (mode={mode.value})")
    print("=" * 78)
    print(f"  IPv4 packet (DF=1, total_length=1500):")
    print(f"    hex: {pkt[:20].hex()}")
    print(f"    fields: ver=4 ihl=5 total_len=1500 flags=DF id=0x1234 proto=TCP")
    print()
    print(f"  TCP SYN with MSS option (MSS=1460):")
    print(f"    hex: {syn[:24].hex()}")
    print(f"    fields: src=49152 dst=443 flags=SYN mss=1460")
    print()
    print(f"  ICMP Type 3 Code 4 (Next-Hop MTU=1400):")
    print(f"    hex: {icmp[:36].hex()}")
    print(f"    fields: type=3 code=4 next_hop_mtu=1400 orig_ip=10.0.0.1->10.0.0.2")
    print()


def render_diag(mode: FailureMode, results: list[DiagResult]) -> None:
    print(f"{'#':<3}  {'finding':<60}  decisive?  points_to")
    print("-" * 78)
    for r in results:
        first_line = r.finding[:58]
        marker = "YES" if r.decisive else "no"
        print(f"{r.step:<3}  {first_line:<60}  {marker:<9}  {r.points_to}")
    print()
    decisive = next((r for r in results if r.decisive), None)
    if decisive:
        print(f"  First decisive evidence: step {decisive.step} ({decisive.name})")
        print(f"  Points to:                {decisive.points_to}")
        print(f"  Verdict:                  {decisive.finding}")
    else:
        print("  No decisive evidence in chain; deeper inspection needed.")
    print()


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="all",
                    choices=[m.value for m in FailureMode] + ["all"])
    args = ap.parse_args(list(argv) if argv is not None else None)

    modes = (list(FailureMode) if args.mode == "all"
             else [FailureMode(args.mode)])
    for mode in modes:
        render_packets(mode)
        results = run_diag(mode)
        render_diag(mode, results)


if __name__ == "__main__":
    main()
