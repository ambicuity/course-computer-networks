"""MPLS label switching and Forwarding Equivalence Classes.

A small stdlib-only data plane: 32-bit shim encoder/decoder, LIB + LFIB
tables, FEC longest-prefix-match classification, and a linear four-router
LSP (LER1 -> LSR2 -> LSR3 -> LER4) walked with and without PHP.

Run with:  python3 code/main.py
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class MPLSShim:
    """RFC 3032 32-bit shim: 20-bit label | 3-bit TC | 1-bit S | 8-bit TTL."""

    label: int
    tc: int = 0
    s: int = 1
    ttl: int = 64

    def __post_init__(self) -> None:
        if not 0 <= self.label <= 0xFFFFF:
            raise ValueError(f"label out of 20-bit range: {self.label}")
        if not 0 <= self.tc <= 0x7 or self.s not in (0, 1) or not 0 <= self.ttl <= 0xFF:
            raise ValueError("tc/s/ttl out of range")

    def encode(self) -> bytes:
        return ((self.label << 12) | (self.tc << 9) | (self.s << 8) | self.ttl).to_bytes(4, "big")

    @staticmethod
    def decode(buf: bytes) -> "MPLSShim":
        if len(buf) != 4:
            raise ValueError(f"shim must be 4 bytes, got {len(buf)}")
        w = int.from_bytes(buf, "big")
        return MPLSShim((w >> 12) & 0xFFFFF, (w >> 9) & 0x7, (w >> 8) & 0x1, w & 0xFF)


@dataclass(frozen=True)
class IPPacket:
    src: str
    dst: str
    payload: bytes = b""


@dataclass
class LabeledPacket:
    """An IP packet with a stack of MPLS shim headers (top of stack first)."""

    ip: IPPacket
    stack: list[MPLSShim] = field(default_factory=list)

    def top(self) -> MPLSShim:
        return self.stack[0]


@dataclass(frozen=True)
class FEC:
    prefix: str
    prefix_len: int
    label: int

    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(f"{self.prefix}/{self.prefix_len}", strict=False)


class FECTable:
    """Longest-prefix-match table from destination IP to FEC."""

    def __init__(self) -> None:
        self._fecs: list[FEC] = []

    def add(self, fec: FEC) -> None:
        self._fecs.append(fec)

    def longest_match(self, dst_ip: str) -> Optional[FEC]:
        addr = ipaddress.IPv4Address(dst_ip)
        best, best_len = None, -1
        for fec in self._fecs:
            if addr in fec.network() and fec.prefix_len > best_len:
                best, best_len = fec, fec.prefix_len
        return best


@dataclass(frozen=True)
class LFIBEntry:
    """Data-plane row: (in_iface, in_label) -> (out_iface, out_label, next_hop)."""

    in_iface: str
    in_label: int
    out_iface: str
    out_label: int
    next_hop: str
    php: bool = False


class Router:
    """A Label Edge Router (push/pop) or a Label Switch Router (swap)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.lib: list[tuple[FEC, int]] = []  # control plane: (fec, local_label)
        self.lfib: dict[tuple[str, int], LFIBEntry] = {}  # data plane

    def install_lib(self, fec: FEC, local_label: int) -> None:
        self.lib.append((fec, local_label))

    def install_lfib(self, in_iface: str, in_label: int, out_iface: str,
                     out_label: int, next_hop: str, php: bool = False) -> None:
        self.lfib[(in_iface, in_label)] = LFIBEntry(
            in_iface, in_label, out_iface, out_label, next_hop, php)

    def push(self, ip: IPPacket, fec: FEC, in_iface: str, tc: int = 0) -> LabeledPacket:
        """Ingress LER action."""
        return LabeledPacket(ip, [MPLSShim(label=fec.label, tc=tc, s=1, ttl=64)])

    def swap(self, pkt: LabeledPacket, in_iface: str) -> LabeledPacket:
        """Interior LSR action: rewrite the top label using the LFIB."""
        top = pkt.top()
        e = self.lfib[(in_iface, top.label)]
        return LabeledPacket(pkt.ip, [MPLSShim(e.out_label, top.tc, top.s, top.ttl - 1), *pkt.stack[1:]])

    def pop(self, pkt: LabeledPacket) -> LabeledPacket | IPPacket:
        """Penultimate / egress action: pop the top label."""
        rest = pkt.stack[1:]
        return LabeledPacket(pkt.ip, rest) if rest else pkt.ip


def build_lsp() -> tuple[list[Router], FECTable, FEC]:
    """Linear 4-router LSP: LER1 -> LSR2 -> LSR3 -> LER4 with label 21->38->57."""
    fec_table = FECTable()
    demo = FEC("10.1.0.0", 16, 21)
    fec_table.add(demo)
    fec_table.add(FEC("10.1.5.0", 24, 22))  # a more-specific FEC, for the LPM demo

    r = [Router(n) for n in ("LER1", "LSR2", "LSR3", "LER4")]
    for x in r:
        x.install_lib(demo, x is r[0] and 21 or x is r[1] and 38 or x is r[2] and 57 or 3)
    r[0].install_lfib("if0", 21, "to_LSR2", 21, "LSR2")
    r[1].install_lfib("from_LER1", 21, "to_LSR3", 38, "LSR3")
    r[2].install_lfib("from_LSR2", 38, "to_LER4", 57, "LER4")
    r[3].install_lfib("from_LSR3", 57, "egress", 3, "egress_LAN")
    return r, fec_table, demo


def _fmt_stack(stack: list[MPLSShim]) -> str:
    return " | ".join(f"L{s.label} TC{s.tc} S{s.s} TTL{s.ttl}" for s in stack)


def walk_packet(pkt: LabeledPacket | IPPacket, routers: list[Router],
                ifaces: list[tuple[str, str]], desc: str) -> None:
    print(f"\n=== {desc} ===")
    for i, router in enumerate(routers):
        in_iface, _ = ifaces[i]
        if i == 0:
            assert isinstance(pkt, LabeledPacket)
            print(f"  {router.name:5} (ingress)  stack: [{_fmt_stack(pkt.stack)}]")
        elif i == len(routers) - 1:
            if isinstance(pkt, LabeledPacket):
                top = pkt.top()
                nh = router.lfib[(in_iface, top.label)].next_hop
                print(f"  {router.name:5} (egress)   in=L{top.label} -> pop, forward to {nh}")
                pkt = router.pop(pkt)
                tail = (f"stack: [{_fmt_stack(pkt.stack)}]" if isinstance(pkt, LabeledPacket)
                        else f"bare IP src={pkt.src} dst={pkt.dst}")
                print(f"  {router.name:5} (after pop) {tail}")
            else:
                print(f"  {router.name:5} (egress)   bare IP src={pkt.src} dst={pkt.dst} -> 1 IP lookup, forward")
        else:
            assert isinstance(pkt, LabeledPacket)
            top = pkt.top()
            e = router.lfib[(in_iface, top.label)]
            if e.php:
                print(f"  {router.name:5} (penult)   in=L{top.label} -> PHP-pop, forward IP to {e.next_hop}")
                pkt = router.pop(pkt)
            else:
                pkt = router.swap(pkt, in_iface)
                nt = pkt.top()
                print(f"  {router.name:5} (swap)     in=L{top.label} -> out=L{nt.label}, TTL={nt.ttl}, to {e.next_hop}")


def main() -> None:
    print("MPLS label switching and Forwarding Equivalence Classes")
    print("=" * 60)

    shim = MPLSShim(label=21, tc=5, s=1, ttl=64)
    parsed = MPLSShim.decode(shim.encode())
    print(f"\nShim round-trip: {shim} -> {shim.encode().hex()} -> {parsed}")
    assert parsed == shim

    fts = FECTable()
    fts.add(FEC("10.1.0.0", 16, 21))
    fts.add(FEC("10.1.5.0", 24, 22))
    m = fts.longest_match("10.1.5.42")
    print(f"\nFEC longest_match(10.1.5.42) = {m.prefix}/{m.prefix_len} label={m.label}")

    routers, _, demo = build_lsp()
    ip = IPPacket("10.9.0.1", "10.1.5.42", b"hello")
    ifaces = [("if0", "to_LSR2"), ("from_LER1", "to_LSR3"),
              ("from_LSR2", "to_LER4"), ("from_LSR3", "egress")]

    pushed = routers[0].push(ip, demo, "if0", tc=5)
    walk_packet(pushed, routers, ifaces, "Walk 1: push -> swap -> swap -> pop")

    r2, _, _ = build_lsp()
    r2[2].lfib.clear()
    r2[2].install_lfib("from_LSR2", 38, "to_LER4", 3, "LER4", php=True)
    walk_packet(r2[0].push(ip, demo, "if0", tc=5), r2, ifaces,
                "Walk 2: PHP at LSR3, LER4 does 1 IP lookup")


if __name__ == "__main__":
    main()
