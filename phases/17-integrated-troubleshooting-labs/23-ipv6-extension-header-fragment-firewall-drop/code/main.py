#!/usr/bin/env python3
"""IPv6 Extension Header Fragment firewall drop diagnostic.

Reference oracle for the integrated troubleshooting lab. Computes
the wire format of an IPv6 packet with a Fragment extension header
and prints the verdict for the four scenarios.

Scenarios:

  fragment_drop
    Firewall rule `-m exthdr --hdr frag -j DROP` is in place; the
    packet never reaches the server; the connection stalls.

  pmtud_ok
    ICMPv6 Type 2 Packet Too Big is honored; PMTUD lowers the
    path MTU; the sender does not need to fragment.

  atomic
    RFC 6946 atomic fragment (offset 0, M=0) is used; the
    firewall rule may or may not catch it.

  mss_clamp
    TCP MSS is clamped to path_MTU - 40 - 8; the kernel never
    needs to fragment.

Run:  python3 main.py --scenario fragment_drop
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Ipv6FragmentHeader:
    next_header: int
    reserved: int
    fragment_offset: int
    m_flag: int
    identification: int


# Canonical IPv6 extension header protocol numbers (RFC 8200).
IPV6_HBH = 0        # Hop-by-Hop Options
IPV6_DST_OPTS = 60  # Destination Options
IPV6_ROUTING = 43
IPV6_FRAGMENT = 44
IPV6_AH = 51        # Authentication Header (IPsec)
IPV6_ESP = 50       # Encapsulating Security Payload (IPsec)
IPV6_ICMPV6 = 58    # ICMPv6
IPV6_NO_NEXT = 59   # No Next Header
IPV6_TCP = 6
IPV6_UDP = 17

# IPv6 minimum MTU (RFC 8200 sec. 5).
IPV6_MIN_MTU = 1280
IPV6_HEADER_SIZE = 40
IPV6_FRAGMENT_HEADER_SIZE = 8


def render_fragment_header() -> str:
    return (
        "  IPv6 Fragment Header (RFC 8200 sec. 4.5, 8 bytes):\n"
        "    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n"
        "    |  Next Header  |   Reserved    |      Fragment Offset    |Res|M|\n"
        "    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n"
        "    |                         Identification                        |\n"
        "    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n"
        "    offset 0..1    2..3            4..5                  6         7\n"
    )


def compute_effective_mss(path_mtu: int = 1500, has_fragment: bool = True) -> int:
    """MSS = path_MTU - 40 (IPv6) - 8 (Fragment Header, if present)."""
    overhead = 40 + (8 if has_fragment else 0)
    return path_mtu - overhead


def is_atomic_fragment(offset: int, m_flag: int) -> bool:
    """RFC 6946: an atomic fragment has offset=0 and M=0."""
    return offset == 0 and m_flag == 0


def tcp_byte_offset_for_fragment() -> int:
    """Offset of the inner TCP Next Header after a Fragment extension header.

    IPv6 main header is 40 bytes (offset 0..39). Next Header field is at
    offset 6 (1 byte). After the main header, the Fragment Header is 8
    bytes, so its Next Header field is at offset 40. The inner TCP header
    starts at offset 48, and its Next Header (which would point to the
    payload) is at offset 48+6 = 54.
    """
    return IPV6_HEADER_SIZE + IPV6_FRAGMENT_HEADER_SIZE + 6


def fragment_identification_unique_check(id_a: int, id_b: int) -> bool:
    """Two fragment IDs from the same source must differ to avoid collisions."""
    return id_a != id_b


def self_test() -> bool:
    """Verify the IPv6 fragment calculations."""
    mss = compute_effective_mss(1500, has_fragment=False)
    assert mss == 1460, f"MSS without frag should be 1460, got {mss}"
    mss_frag = compute_effective_mss(1500, has_fragment=True)
    assert mss_frag == 1452, f"MSS with frag should be 1452, got {mss_frag}"
    assert is_atomic_fragment(0, 0), "offset=0, M=0 must be atomic"
    assert not is_atomic_fragment(0, 1), "offset=0, M=1 is not atomic"
    return True


def render(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"IPV6 FRAGMENT FIREWALL DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    if scenario == "fragment_drop":
        out.append("Path: client --(corporate IPv6)--> server (2001:db8::1)")
        out.append("Edge firewall rule:")
        out.append("  ip6tables -A FORWARD -m exthdr --hdr frag -j DROP")
        out.append("  (or nft add rule ip6 filter forward fraghdr exists counter drop)")
        out.append("")
        out.append("Symptom: client's first 1280-byte segment works; larger segments")
        out.append("are sent with a Fragment extension header; the firewall drops them.")
        out.append("")
        out.append(render_fragment_header())
        out.append("Verdict: every fragment is dropped; the server never receives the")
        out.append("reassembled packet; TCP retransmits and eventually times out.")
        out.append("Fix: remove the firewall rule, or use stateful fragment tracking,")
        out.append("or clamp the MSS so fragments are never needed.")
    elif scenario == "pmtud_ok":
        out.append("Path: client --(IPv6)--> server (2001:db8::1)")
        out.append("No fragment-drop rule; ICMPv6 Type 2 Packet Too Big is honored.")
        out.append("")
        out.append("PMTUD: kernel sends 1500-byte probe, router returns ICMPv6 Type 2")
        out.append("with MTU=1280, kernel lowers path_MTU to 1280, no fragmentation needed.")
        out.append("Verdict: clean PMTUD, no fragments, no firewall interaction.")
    elif scenario == "atomic":
        out.append("RFC 6946 atomic fragment: Fragment Header with offset=0, M=0.")
        out.append("Payload is not actually fragmented; the header is a placeholder.")
        out.append("Some firewalls that drop fragments allow atomic fragments through.")
        out.append("Test: tcpdump -i eth0 -n 'ip6[6] == 44 and ip6[46] == 0'")
    else:
        mss = compute_effective_mss(1500, has_fragment=False)
        mss_frag = compute_effective_mss(1500, has_fragment=True)
        out.append("MSS clamping on the IPv6 path:")
        out.append("  ip6tables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \\")
        out.append("      -j TCPMSS --clamp-mss-to-pmtu")
        out.append("")
        out.append(f"  Effective MSS without fragment header: {mss} bytes")
        out.append(f"  Effective MSS with fragment header:    {mss_frag} bytes")
        out.append("  Sender never sends a segment larger than path_MTU - 40 - 8.")
        out.append("  No fragments generated; firewall rule is a non-issue.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("fragment_drop", "pmtud_ok", "atomic", "mss_clamp"),
        default="fragment_drop",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit.")
    args = parser.parse_args()
    if args.self_test:
        ok = self_test()
        print("IPv6 fragment self-test: PASS" if ok else "IPv6 fragment self-test: FAIL")
        return
    print(render(args.scenario))


if __name__ == "__main__":
    main()
