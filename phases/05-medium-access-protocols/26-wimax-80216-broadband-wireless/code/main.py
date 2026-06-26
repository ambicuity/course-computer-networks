"""
WiMAX / IEEE 802.16 — DL-MAP/UL-MAP frame builder + service-class scheduler.

A stdlib-only Python toolkit that demonstrates the 802.16 connection-oriented MAC
and the per-frame MAP-driven scheduling. Five pieces are wired together:

  1. Generic MAC header encoder/decoder (6-byte header, 8-bit HCS, optional CRC).
  2. Bandwidth-request (BW-REQ) header encoder/decoder (4-byte header, no payload).
  3. Connection-ID allocator (16-bit CIDs, basic/primary/transport, with release).
  4. Service-flow scheduler for UGS, rtPS, nrtPS, BE — turns bytes-into-time-slots
     against a 5 ms TDD frame with 256 OFDM symbols and a 50/50 DL/UL split.
  5. DL-MAP and UL-MAP information-element builder + ASCII rendering of the frame.

Run:  python3 code/main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# 802.16 PHY parameters (fixed WiMAX, 5 ms TDD, 256 FFT, 50/50 split).
# ---------------------------------------------------------------------------
FRAME_MS = 5
SYMBOL_US = 91.4 + (91.4 / 4.0)        # useful + 1/4 cyclic prefix
DL_SYMBOLS = 64                         # half of 256 OFDM symbols
UL_SYMBOLS = 64                         # the other half
PREAMBLE_SYMBOLS = 1
FCH_SYMBOLS = 1
MAP_SYMBOLS = 2
TTG_SYMBOLS = 1
RTG_SYMBOLS = 1

# 7-profile burst ladder: (modulation, coding rate, bits per OFDM symbol at slot=1)
BURST_PROFILES = [
    ("BPSK_1/2", 0.5, 64),
    ("QPSK_1/2", 1.0, 128),
    ("QPSK_3/4", 1.5, 192),
    ("16QAM_1/2", 2.0, 256),
    ("16QAM_3/4", 3.0, 384),
    ("64QAM_2/3", 4.0, 512),
    ("64QAM_3/4", 4.5, 576),
]

# MAC frame-type values (subset of the 6-bit Type field, most common kinds).
class MacType(IntEnum):
    GENERIC = 0
    BROADCAST = 1
    INITIAL_RANGING = 2
    BW_REQUEST = 3
    PACKING = 4
    FRAGMENT = 5
    MANAGEMENT = 6


# ---------------------------------------------------------------------------
# Service classes.
# ---------------------------------------------------------------------------
class ServiceClass(IntEnum):
    UGS = 1
    RTPS = 2
    NRTPS = 3
    BE = 4


# ---------------------------------------------------------------------------
# 8-bit HCS: polynomial x^8 + x^2 + x + 1 (the same one used in 802.16 headers).
# ---------------------------------------------------------------------------
def hcs8(data: bytes) -> int:
    crc = 0x00
    poly = 0x07  # x^8 + x^2 + x + 1, reflected
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


# ---------------------------------------------------------------------------
# Generic MAC header (6 bytes).
#   EC  : 1 bit   — payload encrypted
#   Type: 6 bits  — frame type
#   CI  : 1 bit   — final CRC present
#   EK  : 2 bits  — encryption key index
#   Len : 11 bits — total length including header
#   CID : 16 bits — Connection Identifier
#   HCS : 8 bits  — header check sequence
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MacHeader:
    ec: int
    type: int
    ci: int
    ek: int
    length: int
    cid: int

    def encode(self) -> bytes:
        if not (0 <= self.ec <= 1):
            raise ValueError("EC must be 0 or 1")
        if not (0 <= self.type <= 0x3F):
            raise ValueError("Type must fit in 6 bits")
        if not (0 <= self.ci <= 1):
            raise ValueError("CI must be 0 or 1")
        if not (0 <= self.ek <= 3):
            raise ValueError("EK must fit in 2 bits")
        if not (1 <= self.length <= 0x7FF):
            raise ValueError("Length must fit in 11 bits")
        if not (0 <= self.cid <= 0xFFFF):
            raise ValueError("CID must fit in 16 bits")
        # Layout:  EC|Type(6)|CI|EK(2)|Length(11) | CID(16) | HCS(8)
        word1 = (self.ec << 15) | (self.type << 9) | (self.ci << 8) | (self.ek << 6) | (self.length & 0x07FF)
        word2 = self.cid & 0xFFFF
        body = word1.to_bytes(2, "big") + word2.to_bytes(2, "big")
        return body + bytes([hcs8(body)])

    @staticmethod
    def decode(buf: bytes) -> "MacHeader":
        if len(buf) < 6:
            raise ValueError("header too short")
        word1 = int.from_bytes(buf[0:2], "big")
        word2 = int.from_bytes(buf[2:4], "big")
        got_hcs = buf[4]
        body = buf[0:4]
        if hcs8(body) != got_hcs:
            raise ValueError("HCS mismatch — header corrupted")
        return MacHeader(
            ec=(word1 >> 15) & 0x01,
            type=(word1 >> 9) & 0x3F,
            ci=(word1 >> 8) & 0x01,
            ek=(word1 >> 6) & 0x03,
            length=word1 & 0x07FF,
            cid=word2 & 0xFFFF,
        )


# ---------------------------------------------------------------------------
# Bandwidth-request header (4 bytes): the "1 0 Type Bytes CID HCS" layout.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BandwidthRequest:
    type: int
    bytes_needed: int
    cid: int

    def encode(self) -> bytes:
        if not (0 <= self.type <= 0x3F):
            raise ValueError("Type must fit in 6 bits")
        if not (1 <= self.bytes_needed <= 0xFFFF):
            raise ValueError("bytes_needed must fit in 16 bits")
        if not (0 <= self.cid <= 0xFFFF):
            raise ValueError("CID must fit in 16 bits")
        # Layout: 1|0|Type(6)|BytesNeeded(16)|CID(16)|HCS(8)
        word1 = 0x8000 | ((self.type & 0x3F) << 9) | (self.bytes_needed >> 7) & 0x01FF
        # Simpler: build as 3 x 16-bit words.
        w0 = 0x8000 | ((self.type & 0x3F) << 9) | ((self.bytes_needed >> 8) & 0x01)
        w1 = (self.bytes_needed & 0xFF) << 8 | ((self.cid >> 8) & 0xFF)
        w2_cid_low = self.cid & 0xFF
        body = w0.to_bytes(2, "big") + w1.to_bytes(2, "big")
        return body + bytes([hcs8(body)]) + bytes([w2_cid_low & 0xFF])

    @staticmethod
    def decode(buf: bytes) -> "BandwidthRequest":
        if len(buf) < 4:
            raise ValueError("BW-REQ too short")
        if not (buf[0] & 0x80):
            raise ValueError("not a BW-REQ frame (bit 0 must be 1)")
        type_ = (buf[0] >> 2) & 0x3F
        bytes_needed = ((buf[0] & 0x03) << 14) | (buf[1] << 6) | (buf[2] >> 2)
        cid = ((buf[2] & 0x03) << 14) | (buf[3] << 6) | (buf[4] >> 2)
        # Use the simple reading of the last 16 bits as CID; the BW-REQ HCS
        # is computed over the first 4 bytes.
        body = buf[0:4]
        if hcs8(body) != buf[4]:
            raise ValueError("BW-REQ HCS mismatch")
        return BandwidthRequest(type=type_, bytes_needed=bytes_needed, cid=cid)


# ---------------------------------------------------------------------------
# Connection-ID allocator.
# ---------------------------------------------------------------------------
class ConnectionIdAllocator:
    """Allocates 16-bit CIDs. The first two slots are reserved for the basic
    and primary management CIDs (per 802.16). The remaining 0x0002..0xFFFF
    are handed out to transport/service-flow CIDs."""

    def __init__(self) -> None:
        self._next = 0x0002
        self._in_use: set[int] = set()

    def allocate(self) -> int:
        cid = self._next
        if cid in self._in_use:
            raise RuntimeError("CID space exhausted")
        self._in_use.add(cid)
        self._next += 1
        if self._next > 0xFFFF:
            self._next = 0x0002
        return cid

    def release(self, cid: int) -> None:
        self._in_use.discard(cid)


# ---------------------------------------------------------------------------
# Service flow.
# ---------------------------------------------------------------------------
@dataclass
class ServiceFlow:
    cid: int
    service_class: ServiceClass
    queue_bytes: int = 0
    granted_bytes_this_frame: int = 0
    # UGS parameters
    ugs_grant_bytes: int = 0    # bytes per frame for UGS
    # rtPS / nrtPS polling cadence
    poll_interval_frames: int = 4
    last_polled_frame: int = -1


# ---------------------------------------------------------------------------
# DL-MAP / UL-MAP Information Element (IE).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MapIE:
    cid: int
    symbol_start: int
    symbol_count: int
    burst_profile: int   # index into BURST_PROFILES
    modulation: str

    def render(self) -> str:
        return (
            f"  CID=0x{self.cid:04X}  symbols[{self.symbol_start:>3}..{self.symbol_start + self.symbol_count - 1:>3}]  "
            f"({self.symbol_count:>2} sym)  profile={self.burst_profile}  {self.modulation}"
        )


# ---------------------------------------------------------------------------
# OFDM subcarrier map (toy view — we just need a name for the layout).
# ---------------------------------------------------------------------------
@dataclass
class OfdmSubcarrierMap:
    n_fft: int = 256
    n_pilot: int = 8
    n_guard: int = 28

    @property
    def n_data(self) -> int:
        return self.n_fft - self.n_pilot - self.n_guard

    def layout(self) -> str:
        return (
            f"FFT={self.n_fft}  data={self.n_data}  pilot={self.n_pilot}  "
            f"guard={self.n_guard}  subcarrier_spacing=10.94 kHz"
        )


# ---------------------------------------------------------------------------
# Adaptive modulation fallback.
# ---------------------------------------------------------------------------
def pick_burst_profile(snr_db: float) -> int:
    """Map a measured SNR (dB) to a burst-profile index in [0..6]."""
    if snr_db < 8:
        return 0
    if snr_db < 12:
        return 1
    if snr_db < 16:
        return 2
    if snr_db < 20:
        return 3
    if snr_db < 24:
        return 4
    if snr_db < 28:
        return 5
    return 6


# ---------------------------------------------------------------------------
# TDD frame + scheduler.
# ---------------------------------------------------------------------------
@dataclass
class TddFrame:
    frame_number: int
    dl_ies: list[MapIE] = field(default_factory=list)
    ul_ies: list[MapIE] = field(default_factory=list)

    def render(self) -> str:
        used_dl = sum(ie.symbol_count for ie in self.dl_ies)
        used_ul = sum(ie.symbol_count for ie in self.ul_ies)
        avail_dl = DL_SYMBOLS - PREAMBLE_SYMBOLS - FCH_SYMBOLS - MAP_SYMBOLS
        avail_ul = UL_SYMBOLS - TTG_SYMBOLS - RTG_SYMBOLS
        lines = [
            f"=== Frame #{self.frame_number}  ({FRAME_MS} ms TDD) ===",
            f"  Preamble {PREAMBLE_SYMBOLS} sym | FCH {FCH_SYMBOLS} sym | "
            f"DL-MAP+UL-MAP {MAP_SYMBOLS} sym | DL bursts {used_dl}/{avail_dl} sym | "
            f"TTG {TTG_SYMBOLS} | UL bursts {used_ul}/{avail_ul} sym | RTG {RTG_SYMBOLS}",
            "  DL-MAP IEs:",
        ]
        for ie in self.dl_ies:
            lines.append(ie.render())
        lines.append("  UL-MAP IEs:")
        for ie in self.ul_ies:
            lines.append(ie.render())
        return "\n".join(lines)


def schedule_frame(
    flows: list[ServiceFlow],
    snr_db: dict[int, float],
    frame_number: int,
) -> TddFrame:
    """Run the deadline-aware scheduler for one frame.

    Priority: UGS first (pre-reserved grant), then rtPS (polled this frame),
    then nrtPS (polled occasionally), then BE (contention). Bytes are converted
    to OFDM symbols using the per-SS burst profile.
    """
    frame = TddFrame(frame_number=frame_number)
    avail_dl = DL_SYMBOLS - PREAMBLE_SYMBOLS - FCH_SYMBOLS - MAP_SYMBOLS
    avail_ul = UL_SYMBOLS - TTG_SYMBOLS - RTG_SYMBOLS
    dl_cursor = PREAMBLE_SYMBOLS + FCH_SYMBOLS + MAP_SYMBOLS
    ul_cursor = 0  # UL bursts begin at the start of the UL subframe

    def bytes_to_symbols(nbytes: int, profile: int) -> int:
        bits_per_sym = BURST_PROFILES[profile][2]
        bits = nbytes * 8
        # Add 1 symbol of overhead as a guard for the leading reference.
        return max(1, -(-bits // bits_per_sym) + 1)  # ceiling division

    # Pass 1: UGS gets a pre-reserved grant every frame.
    for flow in flows:
        if flow.service_class != ServiceClass.UGS:
            continue
        if flow.ugs_grant_bytes <= 0:
            continue
        profile = pick_burst_profile(snr_db.get(flow.cid, 24.0))
        syms = bytes_to_symbols(flow.ugs_grant_bytes, profile)
        syms = min(syms, avail_ul - ul_cursor)
        if syms <= 0:
            continue
        frame.ul_ies.append(MapIE(
            cid=flow.cid, symbol_start=ul_cursor, symbol_count=syms,
            burst_profile=profile, modulation=BURST_PROFILES[profile][0],
        ))
        ul_cursor += syms
        flow.granted_bytes_this_frame = flow.ugs_grant_bytes

    # Pass 2: rtPS — polled this frame.
    for flow in flows:
        if flow.service_class != ServiceClass.RTPS:
            continue
        if (frame_number - flow.last_polled_frame) < flow.poll_interval_frames:
            continue
        if flow.queue_bytes <= 0:
            continue
        flow.last_polled_frame = frame_number
        profile = pick_burst_profile(snr_db.get(flow.cid, 20.0))
        syms = bytes_to_symbols(flow.queue_bytes, profile)
        syms = min(syms, avail_ul - ul_cursor)
        if syms <= 0:
            continue
        frame.ul_ies.append(MapIE(
            cid=flow.cid, symbol_start=ul_cursor, symbol_count=syms,
            burst_profile=profile, modulation=BURST_PROFILES[profile][0],
        ))
        ul_cursor += syms
        flow.granted_bytes_this_frame = flow.queue_bytes
        flow.queue_bytes = 0

    # Pass 3: nrtPS — best-effort polling; if any UL room remains, give it a slot.
    for flow in flows:
        if flow.service_class != ServiceClass.NRTPS:
            continue
        if flow.queue_bytes <= 0:
            continue
        profile = pick_burst_profile(snr_db.get(flow.cid, 16.0))
        syms = bytes_to_symbols(flow.queue_bytes, profile)
        syms = min(syms, avail_ul - ul_cursor)
        if syms <= 0:
            continue
        frame.ul_ies.append(MapIE(
            cid=flow.cid, symbol_start=ul_cursor, symbol_count=syms,
            burst_profile=profile, modulation=BURST_PROFILES[profile][0],
        ))
        ul_cursor += syms
        flow.granted_bytes_this_frame = flow.queue_bytes
        flow.queue_bytes = 0

    # Pass 4: BE — contention-based, no scheduled IE. We emit a "BW-REQ window"
    # IE in the UL-MAP to mark the contention region.
    if ul_cursor < avail_ul:
        frame.ul_ies.append(MapIE(
            cid=0x0000, symbol_start=ul_cursor,
            symbol_count=avail_ul - ul_cursor,
            burst_profile=0, modulation="BW-REQ-contention",
        ))

    # DL subframe: simple round-robin of each SS's pending DL data.
    for flow in flows:
        if flow.queue_bytes <= 0:
            continue
        profile = pick_burst_profile(snr_db.get(flow.cid, 22.0))
        syms = bytes_to_symbols(flow.queue_bytes, profile)
        syms = min(syms, avail_dl - (dl_cursor - PREAMBLE_SYMBOLS - FCH_SYMBOLS - MAP_SYMBOLS))
        if syms <= 0:
            continue
        frame.dl_ies.append(MapIE(
            cid=flow.cid, symbol_start=dl_cursor, symbol_count=syms,
            burst_profile=profile, modulation=BURST_PROFILES[profile][0],
        ))
        dl_cursor += syms
        flow.queue_bytes = 0
    return frame


# ---------------------------------------------------------------------------
# Demonstration driver.
# ---------------------------------------------------------------------------
def main() -> None:
    print("--- 802.16 MAC header encode / decode ---")
    hdr = MacHeader(ec=1, type=int(MacType.GENERIC), ci=0, ek=2, length=42, cid=0x0A0F)
    wire = hdr.encode()
    print(f"  Encoded  : {wire.hex(' ')}  (len={len(wire)})")
    decoded = MacHeader.decode(wire)
    print(f"  Decoded  : EC={decoded.ec} Type={decoded.type} CI={decoded.ci} "
          f"EK={decoded.ek} Len={decoded.length} CID=0x{decoded.cid:04X}")

    print("\n--- BW-REQ encode / decode ---")
    bw = BandwidthRequest(type=int(MacType.BW_REQUEST), bytes_needed=800, cid=0x1234)
    bw_wire = bw.encode()
    print(f"  Encoded  : {bw_wire.hex(' ')}  (len={len(bw_wire)})")
    bw_dec = BandwidthRequest.decode(bw_wire)
    print(f"  Decoded  : Type={bw_dec.type} BytesNeeded={bw_dec.bytes_needed} "
          f"CID=0x{bw_dec.cid:04X}")

    print("\n--- Connection-ID allocator ---")
    alloc = ConnectionIdAllocator()
    cids = [alloc.allocate() for _ in range(4)]
    print(f"  Allocated: {[f'0x{c:04X}' for c in cids]}")

    print("\n--- OFDM subcarrier map ---")
    ofdm = OfdmSubcarrierMap()
    print(f"  {ofdm.layout()}")

    print("\n--- Burst profile selection (adaptive modulation fallback) ---")
    for snr in (5.0, 10.0, 15.0, 20.0, 26.0, 30.0):
        p = pick_burst_profile(snr)
        print(f"  SNR={snr:>5.1f} dB -> profile {p} ({BURST_PROFILES[p][0]})")

    print("\n--- Building a 5 ms TDD frame for two SSes ---")
    # SS-A: voice (UGS, 200 bytes / frame at 64 kbps over 8 ms frames -> 100 B/frame)
    # SS-B: video (rtPS, queued bytes depend on scene complexity)
    ss_a = ServiceFlow(
        cid=cids[0], service_class=ServiceClass.UGS, queue_bytes=0,
        ugs_grant_bytes=200, poll_interval_frames=1,
    )
    ss_b = ServiceFlow(
        cid=cids[1], service_class=ServiceClass.RTPS, queue_bytes=900,
        poll_interval_frames=1,
    )
    flows = [ss_a, ss_b]
    snr_per_cid = {cids[0]: 12.0, cids[1]: 22.0}  # SS-A far, SS-B near

    for frame_no in range(3):
        ss_b.queue_bytes = 900 if frame_no in (0, 2) else 300  # VBR-ish
        frame = schedule_frame(flows, snr_per_cid, frame_no)
        print(frame)
        print()


if __name__ == "__main__":
    main()
