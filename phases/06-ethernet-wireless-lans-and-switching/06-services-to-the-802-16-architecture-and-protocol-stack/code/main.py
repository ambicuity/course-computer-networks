#!/usr/bin/env python3
"""IEEE 802.16 (WiMAX) MAC toolkit — stdlib only, no network calls.

Implements the pieces from Tanenbaum CN 5e sec. 4.5.2-4.5.5:

  * The 6-byte generic MAC header (Fig. 4-33a) with its fields:
    HT, EC, Type, CI, EK, Length, 16-bit Connection ID (CID), and the
    8-bit Header Check Sequence (HCS) computed with polynomial
    x^8 + x^2 + x + 1 (0x07).
  * The 6-byte bandwidth-request header (Fig. 4-33b), HT=1, no payload.
  * A round-trip parser that dispatches on the HT bit.
  * An uplink scheduler that walks the four QoS classes
    (UGS, rtPS, nrtPS, BE) and applies Ethernet-style binary exponential
    backoff to best-effort contention.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# CRC-8 generator polynomial used for the 802.16 Header Check Sequence:
# x^8 + x^2 + x + 1  ->  binary 1_0000_0111  ->  low byte 0x07.
HCS_POLY = 0x07
GENERIC_HEADER_LEN = 6  # bytes, both header variants are 6 bytes


class HeaderType(Enum):
    """The HT bit (most significant bit of byte 0)."""

    GENERIC = 0
    BANDWIDTH_REQUEST = 1


class ServiceClass(Enum):
    """802.16 uplink QoS classes (sec. 4.5.4)."""

    UGS = "Unsolicited Grant (constant bit rate)"
    RTPS = "Real-time polling (rt variable bit rate)"
    NRTPS = "Non-real-time polling (nrt variable bit rate)"
    BE = "Best effort"


def header_check_sequence(data: bytes) -> int:
    """Compute the 8-bit HCS over ``data`` using poly x^8+x^2+x+1.

    The HCS protects the first 5 header bytes; the 6th byte carries it.
    Standard bit-by-bit CRC-8, MSB-first, initial value 0.
    """
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ HCS_POLY) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_generic_header(
    cid: int,
    length: int,
    *,
    encrypted: bool = False,
    crc_present: bool = False,
    frame_type: int = 0,
    encryption_key: int = 0,
) -> bytes:
    """Build a 6-byte 802.16 generic MAC header (Fig. 4-33a).

    Bit layout (MSB first):
        byte0: HT(1)=0 | EC(1) | Type(6)
        byte1: rsv(1) | CI(1) | EK(2) | rsv(1) | Length high 3 bits
        byte2: Length low 8 bits
        byte3-4: Connection ID (16 bits)
        byte5: HCS
    """
    if not 0 <= cid <= 0xFFFF:
        raise ValueError("CID must fit in 16 bits")
    if not GENERIC_HEADER_LEN <= length <= 0x7FF:
        raise ValueError("Length is 11 bits and must include the 6-byte header")
    if not 0 <= frame_type <= 0x3F:
        raise ValueError("Type field is 6 bits")

    b0 = (0 << 7) | ((1 if encrypted else 0) << 6) | (frame_type & 0x3F)
    b1 = (
        ((1 if crc_present else 0) << 6)
        | ((encryption_key & 0x3) << 4)
        | ((length >> 8) & 0x07)
    )
    b2 = length & 0xFF
    b3 = (cid >> 8) & 0xFF
    b4 = cid & 0xFF
    first5 = bytes([b0, b1, b2, b3, b4])
    return first5 + bytes([header_check_sequence(first5)])


def build_bandwidth_request(cid: int, bytes_needed: int, req_type: int = 0) -> bytes:
    """Build a 6-byte bandwidth-request header (Fig. 4-33b), HT=1, no payload.

    Bit layout (MSB first):
        byte0: HT(1)=1 | EC(1)=0 | Type(6)
        byte1-2: Bytes needed (16 bits)
        byte3-4: Connection ID (16 bits)
        byte5: HCS
    """
    if not 0 <= cid <= 0xFFFF:
        raise ValueError("CID must fit in 16 bits")
    if not 0 <= bytes_needed <= 0xFFFF:
        raise ValueError("Bytes-needed is a 16-bit field")

    b0 = (1 << 7) | (0 << 6) | (req_type & 0x3F)
    b1 = (bytes_needed >> 8) & 0xFF
    b2 = bytes_needed & 0xFF
    b3 = (cid >> 8) & 0xFF
    b4 = cid & 0xFF
    first5 = bytes([b0, b1, b2, b3, b4])
    return first5 + bytes([header_check_sequence(first5)])


@dataclass
class ParsedHeader:
    """Decoded view of a 6-byte 802.16 MAC header."""

    header_type: HeaderType
    cid: int
    hcs_valid: bool
    # generic only:
    encrypted: Optional[bool] = None
    crc_present: Optional[bool] = None
    length: Optional[int] = None
    # bandwidth request only:
    bytes_needed: Optional[int] = None


def parse_header(raw: bytes) -> ParsedHeader:
    """Parse a 6-byte header, dispatching on the HT bit."""
    if len(raw) != GENERIC_HEADER_LEN:
        raise ValueError(f"802.16 header is {GENERIC_HEADER_LEN} bytes")

    hcs_valid = header_check_sequence(raw[:5]) == raw[5]
    ht = HeaderType((raw[0] >> 7) & 0x1)
    cid = (raw[3] << 8) | raw[4]

    if ht is HeaderType.GENERIC:
        encrypted = bool((raw[0] >> 6) & 0x1)
        crc_present = bool((raw[1] >> 6) & 0x1)
        length = ((raw[1] & 0x07) << 8) | raw[2]
        return ParsedHeader(ht, cid, hcs_valid, encrypted, crc_present, length)

    bytes_needed = (raw[1] << 8) | raw[2]
    return ParsedHeader(ht, cid, hcs_valid, bytes_needed=bytes_needed)


@dataclass
class Connection:
    cid: int
    service: ServiceClass
    pending_bytes: int


def schedule_uplink(connections: list[Connection]) -> list[str]:
    """Decide how each connection gets uplink bandwidth this frame.

    Mirrors sec. 4.5.4: UGS gets standing grants, rtPS/nrtPS get polled,
    BE contends with binary exponential backoff.
    """
    decisions: list[str] = []
    be_collisions = 0
    for conn in connections:
        if conn.service is ServiceClass.UGS:
            verb = "STANDING GRANT (no request needed)"
        elif conn.service is ServiceClass.RTPS:
            verb = "POLLED at fixed interval"
        elif conn.service is ServiceClass.NRTPS:
            verb = "POLLED at loose interval (may also use BE)"
        else:  # BE
            be_collisions += 1
            window = 2 ** be_collisions  # binary exponential backoff
            verb = f"CONTENDS (backoff window 0..{window - 1} slots)"
        decisions.append(
            f"CID 0x{conn.cid:04X}  {conn.service.name:<5}  "
            f"{conn.pending_bytes:>5}B  -> {verb}"
        )
    return decisions


def main() -> None:
    print("=== 802.16 generic MAC header ===")
    gen = build_generic_header(cid=0x1A2B, length=48, encrypted=True, crc_present=True)
    print("bytes:", gen.hex(" "))
    pg = parse_header(gen)
    print(f"  HT={pg.header_type.name} CID=0x{pg.cid:04X} length={pg.length} "
          f"encrypted={pg.encrypted} crc_present={pg.crc_present} "
          f"HCS_valid={pg.hcs_valid}")

    print("\n=== Bandwidth-request header (HT=1, no payload) ===")
    bw = build_bandwidth_request(cid=0x1A2B, bytes_needed=1500)
    print("bytes:", bw.hex(" "))
    pb = parse_header(bw)
    print(f"  HT={pb.header_type.name} CID=0x{pb.cid:04X} "
          f"bytes_needed={pb.bytes_needed} HCS_valid={pb.hcs_valid}")

    print("\n=== Header corruption detection (flip one CID bit) ===")
    corrupt = bytearray(gen)
    corrupt[3] ^= 0x80  # flip MSB of CID high byte
    pc = parse_header(bytes(corrupt))
    print(f"  flipped header HCS_valid={pc.hcs_valid}  "
          f"(receiver drops the frame)")

    print("\n=== Uplink scheduler over 4 QoS classes ===")
    conns = [
        Connection(0x0101, ServiceClass.UGS, 160),     # uncompressed voice
        Connection(0x0202, ServiceClass.RTPS, 900),    # compressed video
        Connection(0x0303, ServiceClass.NRTPS, 8000),  # file transfer
        Connection(0x0404, ServiceClass.BE, 1500),     # web
        Connection(0x0505, ServiceClass.BE, 1500),     # web (collides)
    ]
    for line in schedule_uplink(conns):
        print("  " + line)

    print("\nVoIP on UGS is immune to the upload; on BE it would be starved.")


if __name__ == "__main__":
    main()
