#!/usr/bin/env python3
"""Parse and build 802.16 (WiMAX) MAC headers and Bluetooth baseband headers.

This module is a self-contained, stdlib-only teaching tool for the lesson
"The 802.16 Frame Structure to Bluetooth Applications". It covers:

  * The 802.16 6-byte generic MAC header (HT/EC/Type/CI/EK/Length/CID/HCS)
    and the 8-bit Header CRC using polynomial x^8 + x^2 + x + 1 (0x07).
  * The 802.16 bandwidth-request header (HT=1, 16-bit "bytes needed").
  * The Bluetooth 18-bit logical baseband header (Addr/Type/Flow/ARQN/SEQN/HEC)
    and the 54-bit triple-repeated, majority-voted on-air form.

Nothing here touches the network or any third-party package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# --- 802.16 Header CRC: 8-bit CRC, polynomial x^8 + x^2 + x + 1 = 0x07 -------

HCS_POLY = 0x07  # x^8 + x^2 + x + 1, top x^8 implicit


def crc8_atm(data: bytes, poly: int = HCS_POLY) -> int:
    """Compute the 8-bit Header CRC used by 802.16 over the given bytes."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


# --- 802.16 generic MAC header ----------------------------------------------


@dataclass
class WimaxGenericHeader:
    """802.16 generic MAC header (Tanenbaum Fig. 4-33a). HT bit is 0."""

    ec: int           # 1 bit: payload encrypted
    type_field: int   # 6 bits: packing/fragmentation subtype
    ci: int           # 1 bit: full-frame CRC present
    ek: int           # 2 bits: encryption key index
    length: int       # 11 bits: total frame length incl. header
    connection_id: int  # 16 bits
    hcs: int = 0      # 8 bits: header CRC (filled by pack())

    def pack(self) -> bytes:
        """Serialize to 6 bytes with a freshly computed Header CRC."""
        b0 = (0 << 7) | ((self.ec & 1) << 6) | (self.type_field & 0x3F)
        b1 = ((self.ci & 1) << 7) | ((self.ek & 0x3) << 5) | ((self.length >> 8) & 0x07)
        b2 = self.length & 0xFF
        b3 = (self.connection_id >> 8) & 0xFF
        b4 = self.connection_id & 0xFF
        header5 = bytes([b0, b1, b2, b3, b4])
        self.hcs = crc8_atm(header5)
        return header5 + bytes([self.hcs])


@dataclass
class WimaxBandwidthRequest:
    """802.16 bandwidth-request header (Fig. 4-33b). HT bit is 1, no payload."""

    type_field: int    # 6 bits
    bytes_needed: int  # 16 bits: requested uplink bytes
    connection_id: int  # 16 bits
    hcs: int = 0

    def pack(self) -> bytes:
        b0 = (1 << 7) | (0 << 6) | (self.type_field & 0x3F)
        b1 = (self.bytes_needed >> 8) & 0xFF
        b2 = self.bytes_needed & 0xFF
        b3 = (self.connection_id >> 8) & 0xFF
        b4 = self.connection_id & 0xFF
        header5 = bytes([b0, b1, b2, b3, b4])
        self.hcs = crc8_atm(header5)
        return header5 + bytes([self.hcs])


def parse_wimax_header(raw: bytes) -> Tuple[str, object, bool]:
    """Parse 6 header bytes. Returns (kind, dataclass, hcs_ok)."""
    if len(raw) != 6:
        raise ValueError(f"802.16 header must be 6 bytes, got {len(raw)}")
    ht = (raw[0] >> 7) & 1
    hcs_ok = crc8_atm(raw[:5]) == raw[5]

    if ht == 0:
        ec = (raw[0] >> 6) & 1
        type_field = raw[0] & 0x3F
        ci = (raw[1] >> 7) & 1
        ek = (raw[1] >> 5) & 0x3
        length = ((raw[1] & 0x07) << 8) | raw[2]
        cid = (raw[3] << 8) | raw[4]
        return "generic", WimaxGenericHeader(ec, type_field, ci, ek, length, cid, raw[5]), hcs_ok

    type_field = raw[0] & 0x3F
    bytes_needed = (raw[1] << 8) | raw[2]
    cid = (raw[3] << 8) | raw[4]
    return "bandwidth-request", WimaxBandwidthRequest(type_field, bytes_needed, cid, raw[5]), hcs_ok


# --- Bluetooth baseband header (18 logical bits, sent 3x) --------------------

BT_TYPES = {0: "NULL", 1: "POLL", 2: "FHS", 3: "DM1", 4: "SCO", 5: "ACL"}


@dataclass
class BluetoothHeader:
    """Bluetooth 18-bit logical baseband header (Tanenbaum Fig. 4-36)."""

    address: int   # 3 bits: which of 8 active devices
    type_code: int  # 4 bits: ACL/SCO/poll/null + FEC + slot count
    flow: int      # 1 bit: buffer-full flow control
    arqn: int      # 1 bit: piggyback ACK
    seqn: int      # 1 bit: stop-and-wait sequence
    hec: int       # 8 bits: header checksum

    def type_name(self) -> str:
        return BT_TYPES.get(self.type_code, f"type-{self.type_code}")

    def is_voice(self) -> bool:
        """SCO frames carry real-time voice and are never retransmitted."""
        return self.type_name() == "SCO"

    def to_18_bits(self) -> List[int]:
        bits: List[int] = []
        for value, width in (
            (self.address, 3), (self.type_code, 4), (self.flow, 1),
            (self.arqn, 1), (self.seqn, 1), (self.hec, 8),
        ):
            for i in range(width - 1, -1, -1):
                bits.append((value >> i) & 1)
        return bits


def encode_bluetooth_onair(header: BluetoothHeader) -> List[int]:
    """Triple-repeat each of the 18 logical bits -> 54 on-air bits."""
    return [bit for bit in header.to_18_bits() for _ in range(3)]


def majority_vote_decode(onair_54: List[int]) -> List[int]:
    """Recover 18 logical bits from 54 on-air bits by per-bit majority vote."""
    if len(onair_54) != 54:
        raise ValueError("expected 54 on-air bits")
    recovered: List[int] = []
    for i in range(0, 54, 3):
        triple = onair_54[i:i + 3]
        recovered.append(1 if sum(triple) >= 2 else 0)
    return recovered


def sco_throughput_bps(payload_bits: int, slots_per_sec: int = 800) -> int:
    """Throughput of a basic-rate SCO link for a given payload variant."""
    return payload_bits * slots_per_sec


# --- Demonstration -----------------------------------------------------------


def _show_wimax_generic() -> None:
    print("=== 802.16 generic MAC header ===")
    hdr = WimaxGenericHeader(ec=1, type_field=0x03, ci=1, ek=2, length=120,
                             connection_id=0x00A3)
    raw = hdr.pack()
    print(f"  built bytes : {raw.hex(' ')}")
    kind, parsed, ok = parse_wimax_header(raw)
    print(f"  kind        : {kind}")
    print(f"  EC={parsed.ec} Type=0x{parsed.type_field:02X} CI={parsed.ci} "
          f"EK={parsed.ek} Length={parsed.length} CID=0x{parsed.connection_id:04X}")
    print(f"  Header CRC  : 0x{parsed.hcs:02X}  (valid={ok})")
    note = "present" if parsed.ci else "ABSENT (legal: no-retransmit connection)"
    print(f"  payload CRC : {note}")


def _show_wimax_bwreq() -> None:
    print("\n=== 802.16 bandwidth-request header ===")
    req = WimaxBandwidthRequest(type_field=0x00, bytes_needed=1500,
                                connection_id=0x00A3)
    raw = req.pack()
    print(f"  built bytes : {raw.hex(' ')}")
    kind, parsed, ok = parse_wimax_header(raw)
    print(f"  kind        : {kind}")
    print(f"  bytes needed: {parsed.bytes_needed}  CID=0x{parsed.connection_id:04X}")
    print(f"  Header CRC  : 0x{parsed.hcs:02X}  (valid={ok})")


def _show_wimax_corruption() -> None:
    print("\n=== 802.16 corrupted header detection ===")
    good = WimaxGenericHeader(0, 0, 0, 0, 60, 0x0010).pack()
    bad = bytearray(good)
    bad[3] ^= 0x01  # flip a Connection-ID bit
    _, _, ok = parse_wimax_header(bytes(bad))
    print(f"  flipped one CID bit -> Header CRC valid={ok} (frame discarded)")


def _show_bluetooth() -> None:
    print("\n=== Bluetooth baseband header (18 bits, sent 3x) ===")
    hdr = BluetoothHeader(address=4, type_code=4, flow=0, arqn=1, seqn=1, hec=0x6F)
    print(f"  Addr={hdr.address} Type={hdr.type_name()} Flow={hdr.flow} "
          f"ARQN={hdr.arqn} SEQN={hdr.seqn} HEC=0x{hdr.hec:02X}")
    print(f"  voice link (never retransmitted): {hdr.is_voice()}")
    onair = encode_bluetooth_onair(hdr)
    onair[1] ^= 1  # corrupt exactly one of the three copies of the first bit
    recovered = majority_vote_decode(onair)
    print(f"  on-air bits : {len(onair)}  recovered logical bits match: "
          f"{recovered == hdr.to_18_bits()}")


def _show_throughput() -> None:
    print("\n=== Basic-rate SCO throughput ===")
    for variant in (80, 160, 240):
        print(f"  {variant}-bit payload -> {sco_throughput_bps(variant):,} bps")
    print("  (80-bit variant repeats data 3x; 64 kbps = one PCM voice channel)")


def main() -> None:
    _show_wimax_generic()
    _show_wimax_bwreq()
    _show_wimax_corruption()
    _show_bluetooth()
    _show_throughput()


if __name__ == "__main__":
    main()
