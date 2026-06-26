#!/usr/bin/env python3
"""Gigabit / 10-Gigabit Ethernet math toolkit (stdlib only).

This module makes the tradeoffs in the Gigabit -> 10-Gigabit Ethernet lesson
concrete and computable:

* half-duplex slot-time geometry and why CSMA/CD forces a tiny collision domain
  at 1 Gbps, plus the carrier-extension fix that restores a 200 m diameter;
* carrier-extension / frame-bursting line efficiency;
* 8B/10B vs 64B/66B line-code overhead;
* 802.3x PAUSE-frame quanta-to-time conversion;
* a media selector mapping (distance, medium) to a standard 1000BASE-*/10GBASE-*
  name.

No third-party dependencies, no network access. Run: ``python3 main.py``.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Physical and protocol constants
# ---------------------------------------------------------------------------
SPEED_OF_LIGHT = 3.0e8  # m/s in vacuum
NVP = 0.66  # nominal velocity of propagation factor for copper/fiber media
PROP_SPEED = SPEED_OF_LIGHT * NVP  # signal speed on the medium (m/s)

GIGABIT_BPS = 1_000_000_000
TEN_GIGABIT_BPS = 10_000_000_000

MIN_FRAME_BYTES = 64  # 802.3 minimum frame (incl. 14B header + 4B FCS)
MIN_PAYLOAD_BYTES = 46  # user data inside a 64-byte minimum frame
CARRIER_EXTENSION_SLOT_BYTES = 512  # half-duplex Gigabit slot time
PAUSE_QUANTUM_BITS = 512  # one PAUSE quantum = 512 bit-times
PAUSE_MAX_QUANTA = 0xFFFF  # 16-bit quanta field
PAUSE_ETHERTYPE = 0x8808
PAUSE_OPCODE = 0x0001
PAUSE_DEST_MAC = "01:80:C2:00:00:01"


# ---------------------------------------------------------------------------
# Slot time / collision domain
# ---------------------------------------------------------------------------
def slot_time_seconds(slot_bytes: int, link_bps: int) -> float:
    """Transmission time of one slot (in bytes) at a given link speed."""
    return (slot_bytes * 8) / link_bps


def max_collision_radius_m(slot_bytes: int, link_bps: int) -> float:
    """Worst-case one-way cable length CSMA/CD can support for this slot.

    The sender must still be transmitting when the collision signal returns,
    so the round trip (2 * length / prop_speed) must fit inside the slot time.
    """
    slot_s = slot_time_seconds(slot_bytes, link_bps)
    return (slot_s * PROP_SPEED) / 2.0


# ---------------------------------------------------------------------------
# Line efficiency: carrier extension and frame bursting
# ---------------------------------------------------------------------------
def carrier_extension_efficiency(payload_bytes: int = MIN_PAYLOAD_BYTES) -> float:
    """Fraction of the 512-byte slot that carries real payload."""
    return payload_bytes / CARRIER_EXTENSION_SLOT_BYTES


def frame_burst_efficiency(frame_bytes: int, num_frames: int) -> float:
    """Efficiency when ``num_frames`` real frames fill one burst.

    Bursting amortizes the slot acquisition across several frames; once the
    burst exceeds the 512-byte slot, padding overhead disappears.
    """
    burst_bytes = frame_bytes * num_frames
    billed_bytes = max(burst_bytes, CARRIER_EXTENSION_SLOT_BYTES)
    payload = (frame_bytes - (MIN_FRAME_BYTES - MIN_PAYLOAD_BYTES)) * num_frames
    return payload / billed_bytes


# ---------------------------------------------------------------------------
# Line coding overhead
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LineCode:
    name: str
    data_bits: int
    line_bits: int

    @property
    def overhead(self) -> float:
        return (self.line_bits - self.data_bits) / self.data_bits

    def symbol_rate_bps(self, payload_bps: int) -> float:
        """Raw on-wire bit/symbol rate needed to carry ``payload_bps``."""
        return payload_bps * self.line_bits / self.data_bits


CODE_8B10B = LineCode("8B/10B", 8, 10)
CODE_64B66B = LineCode("64B/66B", 64, 66)


# ---------------------------------------------------------------------------
# 802.3x PAUSE flow control
# ---------------------------------------------------------------------------
def pause_quantum_seconds(link_bps: int) -> float:
    """Wall-clock duration of one PAUSE quantum (512 bit-times)."""
    return PAUSE_QUANTUM_BITS / link_bps


def pause_time_seconds(quanta: int, link_bps: int) -> float:
    if not 0 <= quanta <= PAUSE_MAX_QUANTA:
        raise ValueError(f"quanta must be 0..{PAUSE_MAX_QUANTA}, got {quanta}")
    return quanta * pause_quantum_seconds(link_bps)


# ---------------------------------------------------------------------------
# Media selection
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Media:
    name: str
    medium: str
    max_meters: float
    line_code: str


MEDIA_TABLE: tuple[Media, ...] = (
    Media("1000BASE-CX", "shielded twisted pair", 25, "8B/10B"),
    Media("1000BASE-T", "Cat-5 UTP (4 pair)", 100, "PAM-5"),
    Media("1000BASE-SX", "multimode fiber 0.85um", 550, "8B/10B"),
    Media("1000BASE-LX", "single-mode fiber 1.3um", 5000, "8B/10B"),
    Media("10GBASE-CX4", "twinax (4 pair)", 15, "8B/10B"),
    Media("10GBASE-T", "Cat-6a UTP (4 pair)", 100, "PAM-16 + LDPC"),
    Media("10GBASE-SR", "multimode fiber 0.85um", 300, "64B/66B"),
    Media("10GBASE-LR", "single-mode fiber 1.3um", 10000, "64B/66B"),
    Media("10GBASE-ER", "single-mode fiber 1.5um", 40000, "64B/66B"),
)


def select_media(distance_m: float, want_fiber: bool, speed_bps: int) -> list[Media]:
    """Return standard media that reach ``distance_m`` at the given speed."""
    is_ten_gig = speed_bps >= TEN_GIGABIT_BPS
    out = []
    for m in MEDIA_TABLE:
        ten = m.name.startswith("10GBASE")
        if ten != is_ten_gig:
            continue
        is_fiber = "fiber" in m.medium
        if want_fiber != is_fiber:
            continue
        if m.max_meters >= distance_m:
            out.append(m)
    return sorted(out, key=lambda m: m.max_meters)


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 66)
    print("Gigabit -> 10-Gigabit Ethernet math toolkit")
    print("=" * 66)

    print("\n[1] Half-duplex slot time and collision domain at 1 Gbps")
    naive = max_collision_radius_m(MIN_FRAME_BYTES, GIGABIT_BPS)
    extended = max_collision_radius_m(CARRIER_EXTENSION_SLOT_BYTES, GIGABIT_BPS)
    print(f"  64-byte slot   -> one-way radius ~ {naive:6.1f} m  (too small for an office)")
    print(f"  512-byte slot  -> one-way radius ~ {extended:6.1f} m  (carrier extension fix)")
    print("  Full-duplex (switch): no CSMA/CD, distance bounded by signal strength only.")

    print("\n[2] Line efficiency")
    eff = carrier_extension_efficiency()
    print(f"  64B frame in 512B slot: {eff*100:4.1f}% efficient ({MIN_PAYLOAD_BYTES}B payload / 512B slot)")
    burst = frame_burst_efficiency(frame_bytes=512, num_frames=4)
    print(f"  Frame bursting 4x512B frames: {burst*100:4.1f}% efficient (bursting preferred)")

    print("\n[3] Line-code overhead (why 10 GbE switched codes)")
    for code in (CODE_8B10B, CODE_64B66B):
        raw = code.symbol_rate_bps(TEN_GIGABIT_BPS)
        print(f"  {code.name:8s}: {code.overhead*100:4.1f}% overhead -> "
              f"{raw/1e9:5.2f} Gbps on the wire for 10 Gbps payload")
    saved = (CODE_8B10B.symbol_rate_bps(TEN_GIGABIT_BPS)
             - CODE_64B66B.symbol_rate_bps(TEN_GIGABIT_BPS)) / 1e9
    print(f"  Switching 8B/10B -> 64B/66B saves ~{saved:.2f} Gbps of raw symbol rate.")

    print("\n[4] 802.3x PAUSE frame decode")
    print(f"  dest={PAUSE_DEST_MAC}  ethertype=0x{PAUSE_ETHERTYPE:04X}  opcode=0x{PAUSE_OPCODE:04X}")
    q1 = pause_quantum_seconds(GIGABIT_BPS)
    print(f"  1 quantum @ 1 Gbps  = {q1*1e9:6.1f} ns")
    for quanta in (0x4000, PAUSE_MAX_QUANTA):
        t_gig = pause_time_seconds(quanta, GIGABIT_BPS) * 1e3
        t_10g = pause_time_seconds(quanta, TEN_GIGABIT_BPS) * 1e3
        print(f"  quanta=0x{quanta:04X} -> {t_gig:7.3f} ms @ 1 Gbps, {t_10g:7.3f} ms @ 10 Gbps")

    print("\n[5] Media selection")
    for dist, fiber, spd, label in (
        (90, False, GIGABIT_BPS, "90 m copper @ 1 Gbps"),
        (600, True, TEN_GIGABIT_BPS, "600 m fiber @ 10 Gbps"),
        (8000, True, TEN_GIGABIT_BPS, "8 km fiber @ 10 Gbps"),
    ):
        picks = select_media(dist, fiber, spd)
        names = ", ".join(m.name for m in picks) or "none qualifies"
        print(f"  {label:24s} -> {names}")

    print("\nDone.")


if __name__ == "__main__":
    main()
