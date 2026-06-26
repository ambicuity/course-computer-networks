"""10-Gigabit Ethernet PHY selector and 64B/66B encoder.

Stdlib-only demo of Tanenbaum & Wetherall, *Computer Networks*, 5th ed.,
section 4.3.7 and IEEE 802.3ae / 802.3an / clause 49. No third-party
packages, no network calls. Run ``python3 main.py`` for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# 64B/66B sync header values. 01 = all-data block, 10 = control block.
# The receiver hunts for 01 or 10 (never 00 or 11) to recover block alignment.
SYNC_DATA, SYNC_CONTROL = 0b01, 0b10
LAN_BAUD = 10_312.5  # Mbaud: 10 Gbps * 66/64


class Medium(Enum):
    """Cable categories used by 10 GbE PHY variants."""

    MMF = "multimode fiber"
    SMF = "single-mode fiber"
    UTP = "twisted pair (Cat6a)"
    COPPER = "twinaxial copper (CX4)"
    WAN = "SONET/SDH handoff (WAN PHY)"


@dataclass(frozen=True)
class TenGPhy:
    """A 10 Gigabit Ethernet PHY variant, per IEEE 802.3ae / 802.3an."""

    name: str
    medium: Medium
    max_reach_m: int
    wavelength_nm: int | None
    coding: str
    notes: str


# Reach numbers are the spec headlines: SR uses OM4 MMF at 400 m,
# LR / ER are SMF at 10 / 40 km, 10GBASE-T is 100 m on Cat6a.
PHY_FAMILY: tuple[TenGPhy, ...] = (
    TenGPhy("10GBASE-SR", Medium.MMF, 400, 850, "64B/66B",
            "0.85 um VCSEL: 26 m OM1 / 300 m OM3 / 400 m OM4."),
    TenGPhy("10GBASE-LR", Medium.SMF, 10_000, 1310, "64B/66B",
            "1.3 um laser, 10 km OS1/OS2. Campus / metro uplink."),
    TenGPhy("10GBASE-ER", Medium.SMF, 40_000, 1550, "64B/66B",
            "1.5 um laser, 40 km SMF. Metro / WAN handoff."),
    TenGPhy("10GBASE-LX4", Medium.MMF, 300, 1310, "8B/10B (4 lanes)",
            "Legacy 4-wavelength WDM PHY; superseded by SR/LR."),
    TenGPhy("10GBASE-T", Medium.UTP, 100, None, "64B/66B + LDPC / PAM-16",
            "802.3an (2006). 4 pairs @ 800 Mbaud, 16 levels."),
    TenGPhy("10GBASE-CX4", Medium.COPPER, 15, None, "8B/10B (4 lanes)",
            "4 twinax pairs @ 3.125 Gbaud. Obsolete for new builds."),
    TenGPhy("10GBASE-W (WAN PHY)", Medium.WAN, 10_000, 1310, "64B/66B",
            "LAN PHY wrapped to OC-192/STM-64 framing."),
)


@dataclass(frozen=True)
class SixtyFourBitBlock:
    """One 64B/66B encoded block: 64 payload bits + 2-bit sync header."""

    sync: int
    payload_bits: int

    def to_bitstring(self) -> str:
        if self.sync not in (SYNC_DATA, SYNC_CONTROL):
            raise ValueError(f"bad sync {self.sync:02b}")
        if not 0 <= self.payload_bits < (1 << 64):
            raise ValueError("payload does not fit in 64 bits")
        return f"{self.sync:02b}{self.payload_bits:064b}"


def encode_64b66b(payload: bytes) -> tuple[SixtyFourBitBlock, ...]:
    """Pack a byte string into 64B/66B blocks with SYNC_DATA (01)."""
    if not payload:
        return ()
    pad = (-len(payload)) % 8
    padded = payload + b"\x00" * pad
    return tuple(
        SixtyFourBitBlock(SYNC_DATA, int.from_bytes(padded[i : i + 8], "big"))
        for i in range(0, len(padded), 8)
    )


@dataclass(frozen=True)
class OverheadReport:
    """Output of coding_overhead for a single line code."""

    scheme: str
    data_bits: int
    wire_bits: int
    overhead_percent: float
    symbol_rate_mega_for_10g: float


def coding_overhead(scheme: str) -> OverheadReport:
    """Overhead and required baud to carry 10 Gbps of user data."""
    table = {
        "8B/10B": (8, 10, "8 data bits -> 10 codewords; 25% tax."),
        "64B/66B": (64, 66, "64 payload bits + 2-bit sync; 3.125% tax."),
    }
    if scheme not in table:
        raise ValueError(f"unknown scheme: {scheme!r}")
    data, wire, _ = table[scheme]
    return OverheadReport(
        scheme=scheme,
        data_bits=data,
        wire_bits=wire,
        overhead_percent=(wire - data) / data * 100.0,
        symbol_rate_mega_for_10g=10_000.0 * wire / data,
    )


@dataclass(frozen=True)
class PhyRecommendation:
    """Output of select_phy: the chosen PHY plus a short rationale."""

    chosen: TenGPhy
    reason: str
    fallback: TenGPhy | None


def select_phy(distance_m: float, medium: Medium,
               jitter_tolerant: bool = True) -> PhyRecommendation:
    """Pick a 10 GbE PHY for a given distance and medium."""
    family = sorted((p for p in PHY_FAMILY if p.medium == medium),
                    key=lambda p: p.max_reach_m)
    if not family:
        return PhyRecommendation(
            next(p for p in PHY_FAMILY if p.name == "10GBASE-SR"),
            "unknown medium; defaulting to SR.", None,
        )
    if medium is Medium.WAN:
        return PhyRecommendation(
            next(p for p in PHY_FAMILY if p.name == "10GBASE-W (WAN PHY)"),
            "SONET/SDH handoff -> WAN PHY.", None,
        )
    if medium is Medium.UTP:
        lr = next(p for p in PHY_FAMILY if p.name == "10GBASE-LR")
        t = next(p for p in PHY_FAMILY if p.name == "10GBASE-T")
        if distance_m > 100:
            return PhyRecommendation(lr, f"{distance_m:.0f} m exceeds T's 100 m cap; use LR.", t)
        if not jitter_tolerant:
            return PhyRecommendation(lr, "DSP latency on T is intolerable; use LR.", t)
        return PhyRecommendation(t, "100 m on Cat6a; reuse copper plant.", lr)
    for phy in family:
        if distance_m <= phy.max_reach_m:
            return PhyRecommendation(phy,
                f"{distance_m:.0f} m fits within {phy.max_reach_m} m ({phy.name}).",
                family[0] if family[0] is not phy else None)
    return PhyRecommendation(next(p for p in PHY_FAMILY if p.name == "10GBASE-ER"),
        f"{distance_m:.0f} m exceeds every {medium.value} PHY; escalate to ER.", None)


def _print_phy_table() -> None:
    print("10 GbE PHY family (IEEE 802.3ae / 802.3an / clause 49)")
    print(f"{'PHY':<22}{'Medium':<22}{'Reach':>10}  {'Wavelength':<10}{'Coding'}")
    print("-" * 72)
    for p in PHY_FAMILY:
        wl = f"{p.wavelength_nm} nm" if p.wavelength_nm else "n/a"
        print(f"{p.name:<22}{p.medium.value:<22}{p.max_reach_m:>7} m  {wl:<10}{p.coding}")
    print()


def _demo_64b66b() -> None:
    sample = b"\xDE\xAD\xBE\xEF\xCA\xFE\xBA\xBE"
    blocks = encode_64b66b(sample)
    print(f"64B/66B encoding of {len(sample)}-byte sample")
    for i, b in enumerate(blocks):
        print(f"  block {i}: sync={b.sync:02b} wire={b.to_bitstring()}")
    wire_bytes = len(blocks) * 66 // 8
    overhead = (wire_bytes - len(sample)) / len(sample) * 100
    print(f"  -> {wire_bytes} wire bytes, {overhead:.3f}% overhead\n")


def _demo_overhead() -> None:
    print("Coding overhead at 10 Gbps user data")
    for scheme in ("8B/10B", "64B/66B"):
        r = coding_overhead(scheme)
        print(f"  {r.scheme:<10}overhead = {r.overhead_percent:5.3f}%   "
              f"baud = {r.symbol_rate_mega_for_10g:8.2f} Mbaud")
    print()


def _demo_select_phy() -> None:
    scenarios = [
        (50, Medium.UTP, True, "lab bench, 50 m Cat6a"),
        (250, Medium.MMF, True, "DC spine, OM3"),
        (15_000, Medium.SMF, True, "metro ring, 15 km SMF"),
        (50, Medium.UTP, False, "HFT, DSP latency is unacceptable"),
        (5_000, Medium.WAN, True, "carrier handoff to OC-192"),
    ]
    print("PHY selection for sample deployments")
    for dist, med, jitter, label in scenarios:
        rec = select_phy(dist, med, jitter_tolerant=jitter)
        print(f"  {label}\n    -> {rec.chosen.name}  ({rec.reason})")
    print()


def main() -> None:
    print("=" * 72)
    print("10-Gigabit Ethernet: PHY family, 64B/66B, PHY selection")
    print("=" * 72)
    _print_phy_table()
    _demo_64b66b()
    _demo_overhead()
    _demo_select_phy()


if __name__ == "__main__":
    main()
