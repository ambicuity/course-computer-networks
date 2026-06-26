#!/usr/bin/env python3
"""Dual-Stack SLAAC and DHCPv6 Misconfig (Lab 10).

Simulates the host-side state machine driven by Router Advertisement
flags (M, O, A) and a DHCPv6 server, then runs RFC 6724 source-
address selection to predict which source a host uses for a given
destination. Reference oracle for the dual-stack commissioning
checklist.

Scenarios:
  1) pure_slaac            RA on cafe::/64 with A=1, M=0, O=0
                           and no DHCPv6: all hosts SLAAC and
                           pick cafe:: for every destination.
  2) two_prefix_misconfig  RA on cafe::/64; rogue DHCPv6 server
                           leases face::/64; some hosts pick the
                           unrouted face:: for global destinations
                           due to prefixpolicy ordering.
  3) stateless_dhcpv6      RA with A=1, O=1, M=0; DHCPv6 gives
                           DNS only. Hosts SLAAC the address.

Run:  python3 code/main.py --scenario two_prefix_misconfig
"""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass, field

ROUTED_PREFIX = "2001:db8:cafe::/64"
UNROUTED_PREFIX = "2001:db8:face::/64"
ROUTED_DEST = "2001:db8:cafe::1"
GLOBAL_DEST = "2606:4700:4700::1111"  # Cloudflare DNS, global

# RFC 6724 default policy table (label, precedence). Lower = higher priority.
DEFAULT_POLICY: list[tuple[str, int]] = [
    ("::1/128", 0), ("::/0", 1), ("2001::/32", 4),
    ("::ffff:0:0/96", 10), ("fe80::/10", 12),
]


@dataclass(frozen=True)
class RaFlags:
    a_flag: bool = False  # autonomous (SLAAC)
    m_flag: bool = False  # managed (stateful DHCPv6)
    o_flag: bool = False  # other-config (stateless DHCPv6)
    def label(self) -> str:
        return f"A={int(self.a_flag)} M={int(self.m_flag)} O={int(self.o_flag)}"


@dataclass
class Dhcpv6Server:
    prefix: str
    stateful: bool = False
    dns: str = "2001:db8:cafe::53"


@dataclass
class Host:
    name: str
    slaac_addr: str | None = None
    dhcpv6_addr: str | None = None
    dns: str | None = None
    policy: list[tuple[str, int]] = field(default_factory=lambda: list(DEFAULT_POLICY))

    def candidates(self) -> list[str]:
        return [a for a in (self.slaac_addr, self.dhcpv6_addr) if a]

    def pick(self, dest: str) -> str | None:
        return rfc6724_select(self.candidates(), dest, self.policy)


def prefix_of(addr: str) -> str:
    """Return the /64 prefix body of an IPv6 address."""
    head = addr.rsplit(":", 1)[0] + "::/64"
    if head.startswith("2001:db8:cafe"):
        return ROUTED_PREFIX
    if head.startswith("2001:db8:face"):
        return UNROUTED_PREFIX
    return "unknown"


def rfc6724_select(candidates: list[str], dest: str,
                   policy: list[tuple[str, int]]) -> str | None:
    """Approximate RFC 6724 §5: prefer matching prefix (rule 7),
    then prefixpolicy label (rule 6)."""
    if not candidates:
        return None
    for a in candidates:  # rule 7
        if prefix_of(a) == prefix_of(dest):
            return a
    def label(addr: str) -> int:  # rule 6
        pre = prefix_of(addr)
        for p, prio in policy:
            if pre == p or pre.startswith(p.split("/")[0]):
                return prio
        return 100
    return min(candidates, key=label)


def rfc7217_iid(prefix: str, secret: str, counter: int) -> str:
    """Stable-privacy IID per RFC 7217."""
    h = hashlib.sha256(f"{prefix}|{secret}|{counter}".encode()).digest()
    iid_int = int.from_bytes(h[:8], "big") & 0x3FFFFFFFFFFFFFFF
    s = f"{iid_int:016x}"
    return f"{s[0:4]}:{s[4:8]}:{s[8:12]}:{s[12:16]}"


def build_addr(prefix: str, iid_hex: str) -> str:
    body = prefix.replace("::/64", "::")
    return f"{body}{iid_hex}"


def provision(hosts: list[Host], ra: RaFlags, dhcp: Dhcpv6Server | None) -> None:
    for i, h in enumerate(hosts):
        h.slaac_addr = h.dhcpv6_addr = h.dns = None
        # RFC 4861 §5.5.1: M=1 suppresses SLAAC on most stacks.
        if ra.a_flag and not (ra.m_flag and i % 2 == 0):
            iid = rfc7217_iid(ROUTED_PREFIX, f"secret-{h.name}", 0)
            h.slaac_addr = build_addr(ROUTED_PREFIX, iid)
        if dhcp and dhcp.stateful:
            h.dhcpv6_addr = build_addr(dhcp.prefix, f"0:0:0:dhcp{i + 1:04x}")
        h.dns = dhcp.dns if dhcp else ("fe80::1 (RDNSS)" if ra.o_flag else None)


def report(label: str, ra: RaFlags, dhcp: Dhcpv6Server | None,
           policies: list[list[tuple[str, int]] | None] | None = None) -> None:
    print("=" * 70)
    print(f"DUAL-STACK ORACLE  --  {label}")
    print("=" * 70)
    print(f"  RA flags: {ra.label()}")
    if dhcp:
        print(f"  DHCPv6:   prefix={dhcp.prefix} stateful={dhcp.stateful} dns={dhcp.dns}")
    else:
        print("  DHCPv6:   (none)")
    print()
    hosts = [Host(f"host-{i}") for i in range(6)]
    if policies:
        for h, p in zip(hosts, policies):
            if p is not None:
                h.policy = p
    provision(hosts, ra, dhcp)
    print(f"  {'host':<10} {'slaac':<26} {'dhcpv6':<26} dns")
    print("  " + "-" * 78)
    for h in hosts:
        print(f"  {h.name:<10} {h.slaac_addr or '-':<26} {h.dhcpv6_addr or '-':<26} {h.dns or '-'}")
    print()
    for dest, tag in ((ROUTED_DEST, "local"), (GLOBAL_DEST, "global")):
        ok = 0
        print(f"  RFC 6724 selection for {tag} dest {dest}:")
        for h in hosts:
            chosen = h.pick(dest)
            if not chosen:
                print(f"    {h.name:<10} -> no source (FAIL)")
            elif prefix_of(chosen) == ROUTED_PREFIX:
                ok += 1
                print(f"    {h.name:<10} -> {chosen}  [routed]")
            else:
                print(f"    {h.name:<10} -> {chosen}  [UNROUTED -- hop 2 fails]")
        print(f"  {ok}/{len(hosts)} hosts pick a routed source for {tag}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--scenario",
                        choices=("pure_slaac", "two_prefix_misconfig", "stateless_dhcpv6"),
                        default="two_prefix_misconfig")
    args = parser.parse_args()

    if args.scenario == "pure_slaac":
        report("SLAAC-only (correct)",
               RaFlags(a_flag=True, m_flag=False, o_flag=False), None)

    elif args.scenario == "stateless_dhcpv6":
        report("Stateless DHCPv6 (A=1, O=1, M=0)",
               RaFlags(a_flag=True, m_flag=False, o_flag=True),
               Dhcpv6Server(ROUTED_PREFIX, stateful=False))

    elif args.scenario == "two_prefix_misconfig":
        # RA on routed prefix; rogue DHCPv6 on unrouted prefix; some hosts
        # have a prefixpolicy that puts face:: before cafe:: for global.
        face_first: list[tuple[str, int]] = [
            ("2001:db8:face::/64", 5), ("2001:db8:cafe::/64", 6),
        ] + DEFAULT_POLICY
        policies: list[list[tuple[str, int]] | None] = [
            None, None, None, face_first, face_first, None,
        ]
        report("two_prefix_misconfig  (RA on cafe::/64, rogue DHCPv6 on face::/64)",
               RaFlags(a_flag=True, m_flag=False, o_flag=False),
               Dhcpv6Server(UNROUTED_PREFIX, stateful=True),
               policies=policies)
        print("  Root cause: DHCPv6 pool prefix != RA prefix; upstream router")
        print("              only routes cafe::/64.  Some hosts with a custom")
        print("              prefixpolicy prefer face:: for global destinations")
        print("              and silently fail at hop 2.")
        print("  Fix: align DHCPv6 pool to cafe::/64 and decommission rogue server,")
        print("       or set M=0 A=1 O=1 and use stateless DHCPv6 for DNS only.")


if __name__ == "__main__":
    main()
