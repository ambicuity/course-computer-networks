#!/usr/bin/env python3
"""Reverse DNS helper: address -> in-addr.arpa / ip6.arpa name and FCrDNS check.

Implements the byte-reversal (IPv4) and nibble-reversal (IPv6) conventions from
RFC 1035 and RFC 3596. Renders a tiny reverse zone file and demonstrates the
forward-confirmed reverse DNS loop that mail servers use as a sender signal
(RFC 5321 §5.1).

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


V4_IN_ADDR = "in-addr.arpa."
V6_IP6_ARPA = "ip6.arpa."


def ipv4_to_arpa(ip: str) -> str:
    octets = ip.split(".")
    if len(octets) != 4:
        raise ValueError(f"not an IPv4 address: {ip!r}")
    for o in octets:
        if not 0 <= int(o) <= 255:
            raise ValueError(f"octet out of range: {o!r}")
    return ".".join(reversed(octets)) + "." + V4_IN_ADDR


def ipv6_to_ip6_arpa(ip: str) -> str:
    if ":" not in ip:
        raise ValueError(f"not an IPv6 address: {ip!r}")
    head, _, tail = ip.partition("::")
    left_parts = head.split(":") if head else []
    right_parts = tail.split(":") if tail else []
    missing = 8 - (len(left_parts) + len(right_parts))
    if missing < 0:
        raise ValueError(f"too many groups: {ip!r}")
    full = left_parts + ["0"] * missing + right_parts
    full_hex = ["0" * (4 - len(g)) + g for g in full]
    nibbles = "".join(full_hex)
    if len(nibbles) != 32:
        raise ValueError(f"expanded nibbles wrong length: {ip!r}")
    return ".".join(reversed(nibbles)) + "." + V6_IP6_ARPA


@dataclass
class ReverseZone:
    origin: str
    soa: str
    ns: List[str]
    ptrs: List[Tuple[str, str]]

    def render(self) -> str:
        lines = [f"$ORIGIN {self.origin}", "$TTL 86400", self.soa]
        for ns in self.ns:
            lines.append(f"@  IN  NS  {ns}")
        for label, target in self.ptrs:
            lines.append(f"{label}  IN  PTR  {target}")
        return "\n".join(lines) + "\n"


def fcrdns_check(ip: str, ptr_name: str, forward_a: str) -> bool:
    """True if the PTR->A loop returns the original IP (RFC 5321 §5.1 spirit)."""
    return forward_a == ip and ptr_name != ""


def main() -> None:
    print("=" * 64)
    print("REVERSE DNS / in-addr.arpa / ip6.arpa  --  RFC 1035 / RFC 3596 / RFC 5321")
    print("=" * 64)

    for ip in ("192.0.2.10", "198.51.100.7", "203.0.113.42"):
        print(f"\n{ip:>15s}  ->  {ipv4_to_arpa(ip)}")

    for ip in ("2001:db8::1", "fe80::1", "2001:0db8:1234:5678::abcd"):
        print(f"\n{ip:>30s}  ->  {ipv6_to_ip6_arpa(ip)}")

    zone = ReverseZone(
        origin="0.113.0.203.in-addr.arpa.",
        soa="@  IN  SOA  ns1.example.com. admin.example.com. ( 2026062501 3600 1800 1209600 300 )",
        ns=["ns1.example.com.", "ns2.example.com."],
        ptrs=[
            ("5", "mail.example.com."),
            ("10", "ns1.example.com."),
            ("11", "ns2.example.com."),
        ],
    )
    print("\nReverse zone file (203.0.113.0/24):")
    print(zone.render())

    print("FCrDNS check (RFC 5321 §5.1):")
    cases = [
        ("203.0.113.5", "mail.example.com.", "203.0.113.5"),
        ("203.0.113.5", "mail.example.com.", "192.0.2.30"),
        ("203.0.113.5", "", ""),
    ]
    for ip, ptr, a in cases:
        ok = fcrdns_check(ip, ptr, a)
        print(f"  IP={ip:<14}  PTR={ptr:<24}  A={a:<14}  ->  FCrDNS ok? {ok}")


if __name__ == "__main__":
    main()
