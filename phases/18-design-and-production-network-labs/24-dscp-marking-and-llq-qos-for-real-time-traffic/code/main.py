#!/usr/bin/env python3
"""DSCP / PHB (Per-Hop Behavior) calculator.

Given a class name, returns the 6-bit DSCP value, the IP ToS byte (RFC 791
+ RFC 2474 combined), the queue index, the bandwidth ceiling, and the
queueing discipline -- the mapping a carrier switches on every packet.

The 6-bit DSCP rides in the high 6 bits of the IP ToS byte. The low 2
bits are the CU (Currently Unused) field, repurposed for ECN per RFC
3168. ECN is independent of DSCP, so we ignore it here and present the
pure DSCP value with CU=00.

This is the canonical DiffServ codepoint table used in production:
  BE  (RFC 2474)        - Best Effort
  AF11..AF43 (RFC 2597) - Assured Forwarding, 4 classes x 3 drop precedences
  EF   (RFC 3246)       - Expedited Forwarding (voice / VoIP)
  CS6, CS7 (RFC 2474)   - Control / routing protocols
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CU_MASK = 0x03
DSCP_SHIFT = 2

PHB_TABLE: dict[str, tuple[int, int, int, int, str]] = {
    "BE":   (0,  3, 100, 0, "tail drop"),
    "AF11": (10, 2, 100, 1, "precedence 1 drop"),
    "AF12": (12, 2, 100, 2, "precedence 2 drop"),
    "AF13": (14, 2, 100, 3, "precedence 3 drop"),
    "AF21": (18, 2, 100, 1, "precedence 1 drop"),
    "AF22": (20, 2, 100, 2, "precedence 2 drop"),
    "AF23": (22, 2, 100, 3, "precedence 3 drop"),
    "AF31": (26, 2, 100, 1, "precedence 1 drop"),
    "AF32": (28, 2, 100, 2, "precedence 2 drop"),
    "AF33": (30, 2, 100, 3, "precedence 3 drop"),
    "AF41": (34, 2, 100, 1, "precedence 1 drop"),
    "AF42": (36, 2, 100, 2, "precedence 2 drop"),
    "AF43": (38, 2, 100, 3, "precedence 3 drop"),
    "EF":   (46, 0, 33, 0, "police 33mbit / priority"),
    "CS6":  (48, 1, 100, 0, "priority (routing)"),
    "CS7":  (56, 0, 100, 0, "priority (keepalive)"),
}


@dataclass(frozen=True)
class PHB:
    name: str
    dscp: int
    tos: int
    queue: int
    ceil_pct: int
    precedence: int
    discipline: str

    @property
    def binary(self) -> str:
        return format(self.dscp, "06b")

    @property
    def tos_hex(self) -> str:
        return f"0x{self.tos:02x}"


def dscp_to_tos(dscp: int, ecn: int = 0) -> int:
    if not 0 <= dscp <= 63:
        raise ValueError(f"DSCP out of range: {dscp}")
    if not 0 <= ecn <= 3:
        raise ValueError(f"ECN out of range: {ecn}")
    return (dscp << DSCP_SHIFT) | ecn


def tos_to_dscp(tos: int) -> tuple[int, int]:
    return (tos >> DSCP_SHIFT) & 0x3F, tos & CU_MASK


def lookup(name: str) -> PHB:
    if name not in PHB_TABLE:
        raise KeyError(f"unknown class {name!r}")
    dscp, queue, ceil, prec, disc = PHB_TABLE[name]
    return PHB(
        name=name,
        dscp=dscp,
        tos=dscp_to_tos(dscp, 0),
        queue=queue,
        ceil_pct=ceil,
        precedence=prec,
        discipline=disc,
    )


def render_tc_filter(p: PHB) -> str:
    return (
        f"tc filter add dev <iface> parent 1:0 protocol ip u32 "
        f"match ip tos {p.tos_hex} 0xfc flowid 1:{p.queue + 1}"
    )


def render_iptables_mark(name: str) -> str:
    p = lookup(name)
    return (
        f"iptables -t mangle -A POSTROUTING "
        f"-m dscp --dscp {p.dscp} -j ACCEPT     # match\n"
        f"iptables -t mangle -A POSTROUTING "
        f"-p udp --dport 5004 -j DSCP --set-dscp {p.dscp}    # set {name}"
    )


def main() -> None:
    print("=" * 64)
    print("DSCP / PHB CALCULATOR -- 11 canonical DiffServ classes")
    print("=" * 64)
    print(f"{'class':<7} {'dscp':<4} {'tos':<6} {'binary':<8} {'queue':<5} "
          f"{'ceil%':<5} {'prec':<4} {'discipline':<28}")
    print("-" * 64)
    for name in ("BE", "AF11", "AF12", "AF13", "AF21", "AF31",
                 "AF41", "AF42", "EF", "CS6", "CS7"):
        p = lookup(name)
        print(
            f"{p.name:<7} 0x{p.dscp:02x}  {p.tos_hex:<6} {p.binary:<8} "
            f"{p.queue:<5} {p.ceil_pct:<5} {p.precedence:<4} {p.discipline:<28}"
        )
    print()
    print("=" * 64)
    print("EXAMPLE TC FILTERS -- paste into router config")
    print("=" * 64)
    for cls in ("EF", "AF41", "BE"):
        p = lookup(cls)
        print(f"  [{cls}]  {render_tc_filter(p)}")
    print()
    print("=" * 64)
    print("EXAMPLE IPTABLES MARK -- on the sender (phone)")
    print("=" * 64)
    print(render_iptables_mark("EF"))
    print()
    print("=" * 64)
    print("REVERSIBILITY TEST -- round-trip a tos byte")
    print("=" * 64)
    for cls in ("EF", "AF41", "CS6"):
        p = lookup(cls)
        dscp_back, ecn_back = tos_to_dscp(p.tos)
        print(f"  {cls:<5} tos={p.tos_hex} -> dscp={dscp_back} ecn={ecn_back} "
              f"(matches: {dscp_back == p.dscp and ecn_back == 0})")


if __name__ == "__main__":
    main()