#!/usr/bin/env python3
"""ADSL data path: PPPoA over AAL5 over ATM segmentation and reassembly.

This models the upper layers of the ADSL protocol stack from Tanenbaum
section 3.5.2 (Fig. 3-26):  IP -> PPP -> AAL5 -> ATM cells.

What it does, with no third-party dependencies:
  * Build a PPPoA payload (PPP Protocol field + IP payload), per RFC 2364 --
    PPP flag bytes and PPP FCS are deliberately omitted because AAL5/ATM
    already frame and check.
  * Wrap it in an AAL5 frame: pad to a multiple of 48 bytes, then append the
    8-byte trailer (1 B UU + 1 B CPI + 2 B Length + 4 B CRC-32). The CRC-32
    uses polynomial 0x04C11DB7 -- the same one PPP and Ethernet (IEEE 802) use.
  * Segment the AAL5 frame into 53-byte ATM cells (5-byte header carrying a
    VPI/VCI + 48-byte payload). The last cell of a frame is marked in the PTI.
  * Reassemble the cell stream, validate the AAL5 Length and CRC-32, and
    recover the original IP packet.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# ---- Protocol constants (sizes in bytes) -----------------------------------
ATM_CELL_SIZE = 53
ATM_HEADER_SIZE = 5
ATM_PAYLOAD_SIZE = 48          # the famous 32-vs-64 compromise
AAL5_TRAILER_SIZE = 8          # UU(1) + CPI(1) + Length(2) + CRC-32(4)
PPP_PROTO_IP = 0x0021          # PPP Protocol value for an IPv4 packet
PPP_PROTO_LCP = 0xC021         # PPP Protocol value for an LCP control packet
CRC32_POLY = 0x04C11DB7        # IEEE 802 / PPP / AAL5 CRC-32 polynomial


def aal5_crc32(data: bytes) -> int:
    """CRC-32 with polynomial 0x04C11DB7 (the AAL5 / Ethernet / PPP CRC).

    Standard reflected CRC-32: init 0xFFFFFFFF, reflect in/out, final XOR.
    """
    reflected_poly = 0xEDB88320  # bit-reflection of 0x04C11DB7
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ reflected_poly if (crc & 1) else (crc >> 1)
    return crc ^ 0xFFFFFFFF


def build_pppoa_payload(ip_packet: bytes, proto: int = PPP_PROTO_IP) -> bytes:
    """Wrap an IP packet as a PPPoA payload (RFC 2364).

    Only the 2-byte PPP Protocol field is prepended. No flag bytes, no FCS.
    """
    return proto.to_bytes(2, "big") + ip_packet


def aal5_encapsulate(payload: bytes) -> bytes:
    """Build a complete AAL5 frame: payload + PAD + 8-byte trailer.

    Total length is rounded up to a multiple of 48 bytes so the frame
    divides evenly into ATM cells.
    """
    real_len = len(payload)
    total_no_pad = real_len + AAL5_TRAILER_SIZE
    padded_total = ((total_no_pad + ATM_PAYLOAD_SIZE - 1)
                    // ATM_PAYLOAD_SIZE) * ATM_PAYLOAD_SIZE
    pad_len = padded_total - total_no_pad

    frame_wo_crc = (
        payload
        + b"\x00" * pad_len             # PAD
        + b"\x00"                       # UU  (CPCS User-to-User, unused here)
        + b"\x00"                       # CPI (Common Part Indicator)
        + real_len.to_bytes(2, "big")  # Length: real payload, excludes pad
    )
    crc = aal5_crc32(frame_wo_crc)
    return frame_wo_crc + crc.to_bytes(4, "big")


@dataclass(frozen=True)
class AtmCell:
    """One 53-byte ATM cell: VPI/VCI in the header, 48-byte payload."""
    vpi: int
    vci: int
    last: bool          # PTI bit = "last cell of AAL5 frame"
    payload: bytes      # always 48 bytes

    def to_bytes(self) -> bytes:
        # 5-byte header: GFC|VPI (1B), VPI|VCI (1B), VCI (1B),
        # VCI|PTI|CLP (1B), HEC (1B). Simplified bit packing for teaching.
        b0 = (self.vpi >> 4) & 0xFF
        b1 = ((self.vpi & 0x0F) << 4) | ((self.vci >> 12) & 0x0F)
        b2 = (self.vci >> 4) & 0xFF
        pti = 0b001 if self.last else 0b000
        b3 = ((self.vci & 0x0F) << 4) | (pti << 1)
        hec = (b0 ^ b1 ^ b2 ^ b3) & 0xFF   # stand-in for the real HEC
        return bytes([b0, b1, b2, b3, hec]) + self.payload


def segment_into_cells(frame: bytes, vpi: int, vci: int) -> List[AtmCell]:
    """Slice an AAL5 frame into 48-byte ATM cell payloads."""
    if len(frame) % ATM_PAYLOAD_SIZE != 0:
        raise ValueError("AAL5 frame is not a multiple of 48 bytes")
    chunks = [frame[i:i + ATM_PAYLOAD_SIZE]
              for i in range(0, len(frame), ATM_PAYLOAD_SIZE)]
    return [
        AtmCell(vpi, vci, last=(idx == len(chunks) - 1), payload=chunk)
        for idx, chunk in enumerate(chunks)
    ]


def reassemble(cells: List[AtmCell]) -> bytes:
    """Reassemble cells into the AAL5 frame, validate length + CRC, return payload.

    Raises ValueError on a CRC mismatch or an inconsistent Length field --
    the exact symptoms a real DSLAM/modem would log and drop on.
    """
    frame = b"".join(cell.payload for cell in cells)
    if len(frame) < AAL5_TRAILER_SIZE:
        raise ValueError("frame shorter than AAL5 trailer")

    trailer = frame[-AAL5_TRAILER_SIZE:]
    real_len = int.from_bytes(trailer[2:4], "big")
    rx_crc = int.from_bytes(trailer[4:8], "big")

    calc_crc = aal5_crc32(frame[:-4])
    if calc_crc != rx_crc:
        raise ValueError(
            f"AAL5 CRC mismatch: got 0x{rx_crc:08X}, computed 0x{calc_crc:08X}")
    if real_len > len(frame) - AAL5_TRAILER_SIZE:
        raise ValueError(f"AAL5 Length {real_len} exceeds frame payload")
    return frame[:real_len]


def strip_pppoa(payload: bytes) -> Tuple[int, bytes]:
    """Recover (PPP Protocol value, IP packet) from a PPPoA payload."""
    proto = int.from_bytes(payload[:2], "big")
    return proto, payload[2:]


def efficiency(ip_len: int, wire_bytes: int) -> float:
    return 100.0 * ip_len / wire_bytes


def main() -> None:
    # A sample 100-byte IP packet (contents are illustrative bytes).
    ip_packet = bytes(range(100))
    print("=" * 64)
    print("ADSL upper stack: IP -> PPPoA -> AAL5 -> ATM cells")
    print("=" * 64)
    print(f"IP packet length            : {len(ip_packet)} bytes")

    pppoa = build_pppoa_payload(ip_packet, PPP_PROTO_IP)
    print(f"PPPoA payload (proto+IP)    : {len(pppoa)} bytes "
          f"(PPP Protocol = 0x{PPP_PROTO_IP:04X} = IPv4)")

    frame = aal5_encapsulate(pppoa)
    trailer = frame[-AAL5_TRAILER_SIZE:]
    pad_len = len(frame) - len(pppoa) - AAL5_TRAILER_SIZE
    print(f"AAL5 frame length           : {len(frame)} bytes "
          f"(PAD = {pad_len}, multiple of 48 = {len(frame) % 48 == 0})")
    print(f"AAL5 trailer (hex)          : {trailer.hex()}")
    print(f"  Length field              : {int.from_bytes(trailer[2:4], 'big')}")
    print(f"  CRC-32                    : 0x{int.from_bytes(trailer[4:8], 'big'):08X}")

    cells = segment_into_cells(frame, vpi=8, vci=35)
    wire = len(cells) * ATM_CELL_SIZE
    print(f"\nATM cells                   : {len(cells)} x 53 = {wire} wire bytes")
    for i, cell in enumerate(cells):
        raw = cell.to_bytes()
        tag = "  <- last cell (PTI)" if cell.last else ""
        print(f"  cell {i} VPI/VCI={cell.vpi}/{cell.vci} "
              f"hdr={raw[:5].hex()}{tag}")
    print(f"Efficiency (IP / wire)      : {efficiency(len(ip_packet), wire):.1f}%")

    print("\n--- Reassembly at the DSLAM ---")
    payload = reassemble(cells)
    proto, recovered_ip = strip_pppoa(payload)
    print("AAL5 CRC + Length           : OK")
    print(f"PPP Protocol recovered      : 0x{proto:04X}")
    print(f"IP packet recovered intact  : {recovered_ip == ip_packet}")

    print("\n--- Failure mode: one corrupted byte in a cell ---")
    bad_payload = bytearray(cells[0].payload)
    bad_payload[10] ^= 0xFF
    corrupt = [AtmCell(cells[0].vpi, cells[0].vci, cells[0].last,
                       bytes(bad_payload))] + cells[1:]
    try:
        reassemble(corrupt)
        print("unexpected: corruption not detected")
    except ValueError as exc:
        print(f"Detected and dropped frame  : {exc}")


if __name__ == "__main__":
    main()
