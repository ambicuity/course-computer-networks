"""802.11 data-frame encoder and decoder.

Stdlib-only reference: builds the Frame Control bit field, encodes the four
address modes implied by To DS / From DS, and parses a data frame back. The
FCS is the same 32-bit CRC used by classic Ethernet (0x04C11DB7, no
reflection, no final XOR). Every example below round-trips through the
encoder and parser.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Final

ADDR_LEN: Final = 6
FC_LEN: Final = 2
DUR_LEN: Final = 2
SEQ_LEN: Final = 2
FCS_LEN: Final = 4
MAX_BODY: Final = 2312
CRC32_POLY: Final = 0x04C11DB7

def _build_crc_table() -> tuple:
    table = []
    for i in range(256):
        crc = i << 24
        for _ in range(8):
            crc = ((crc << 1) ^ CRC32_POLY) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
        table.append(crc)
    return tuple(table)

_CRC_TABLE: Final = _build_crc_table()

def crc32(data: bytes) -> int:
    """Compute the 802.11 / Ethernet 32-bit CRC over `data`."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = ((crc << 8) ^ _CRC_TABLE[((crc >> 24) ^ byte) & 0xFF]) & 0xFFFFFFFF
    return crc

@dataclass(frozen=True)
class FrameControl:
    """The 16-bit Frame Control word broken into 11 sub-fields."""
    protocol_version: int = 0
    type: int = 2  # 0 mgmt, 1 ctrl, 2 data
    subtype: int = 0
    to_ds: int = 0
    from_ds: int = 0
    more_fragments: int = 0
    retry: int = 0
    power_management: int = 0
    more_data: int = 0
    protected: int = 0
    order: int = 0

    def to_word(self) -> int:
        return (self.protocol_version | (self.type << 2) | (self.subtype << 4)
                | (self.to_ds << 8) | (self.from_ds << 9) | (self.more_fragments << 10)
                | (self.retry << 11) | (self.power_management << 12)
                | (self.more_data << 13) | (self.protected << 14) | (self.order << 15))

    @classmethod
    def from_word(cls, word: int) -> "FrameControl":
        return cls(protocol_version=word & 0x3, type=(word >> 2) & 0x3,
                   subtype=(word >> 4) & 0xF, to_ds=(word >> 8) & 0x1,
                   from_ds=(word >> 9) & 0x1, more_fragments=(word >> 10) & 0x1,
                   retry=(word >> 11) & 0x1, power_management=(word >> 12) & 0x1,
                   more_data=(word >> 13) & 0x1, protected=(word >> 14) & 0x1,
                   order=(word >> 15) & 0x1)

TYPE_DATA, TYPE_CTRL, TYPE_MGMT = 2, 1, 0

@dataclass(frozen=True)
class MacAddress:
    octets: bytes
    def __post_init__(self) -> None:
        if len(self.octets) != ADDR_LEN:
            raise ValueError(f"802.11 address must be {ADDR_LEN} bytes")
    @classmethod
    def from_hex(cls, text: str) -> "MacAddress":
        return cls(bytes.fromhex(text.replace(":", "").replace("-", "").lower()))
    def to_hex(self) -> str:
        return ":".join(f"{b:02x}" for b in self.octets)
    def __str__(self) -> str:
        return self.to_hex()

@dataclass(frozen=True)
class SequenceControl:
    fragment: int = 0
    sequence: int = 0
    def to_word(self) -> int:
        return (self.sequence << 4) | self.fragment
    @classmethod
    def from_word(cls, word: int) -> "SequenceControl":
        return cls(fragment=word & 0xF, sequence=(word >> 4) & 0xFFF)

@dataclass(frozen=True)
class DataFrame:
    frame_control: FrameControl
    duration: int
    addr1: MacAddress
    addr2: MacAddress
    addr3: MacAddress
    addr4: MacAddress | None
    sequence: SequenceControl
    body: bytes = b""

    def to_bytes(self) -> bytes:
        if len(self.body) > MAX_BODY:
            raise ValueError(f"body too large: {len(self.body)}")
        if not 0 <= self.duration < 0x8000:
            raise ValueError("duration must be 15-bit NAV value")
        header = (self.frame_control.to_word().to_bytes(FC_LEN, "little")
                  + self.duration.to_bytes(DUR_LEN, "little")
                  + self.addr1.octets + self.addr2.octets + self.addr3.octets
                  + self.sequence.to_word().to_bytes(SEQ_LEN, "little"))
        if self.frame_control.to_ds and self.frame_control.from_ds:
            if self.addr4 is None:
                raise ValueError("WDS frame must carry Address 4")
            header += self.addr4.octets
        elif self.addr4 is not None:
            raise ValueError("Address 4 only legal for To=From=1")
        return header + self.body + crc32(header + self.body).to_bytes(FCS_LEN, "little")

def parse(wire: bytes) -> DataFrame:
    """Parse a data frame. Trailing 4 bytes are the FCS."""
    if len(wire) < FC_LEN + DUR_LEN + 3 * ADDR_LEN + SEQ_LEN + FCS_LEN:
        raise ValueError("frame too short")
    fc = FrameControl.from_word(int.from_bytes(wire[:FC_LEN], "little"))
    duration = int.from_bytes(wire[FC_LEN:FC_LEN + DUR_LEN], "little")
    cur = FC_LEN + DUR_LEN
    a1 = MacAddress(wire[cur:cur+ADDR_LEN]); cur += ADDR_LEN
    a2 = MacAddress(wire[cur:cur+ADDR_LEN]); cur += ADDR_LEN
    a3 = MacAddress(wire[cur:cur+ADDR_LEN]); cur += ADDR_LEN
    seq = SequenceControl.from_word(int.from_bytes(wire[cur:cur+SEQ_LEN], "little"))
    cur += SEQ_LEN
    a4 = MacAddress(wire[cur:cur+ADDR_LEN]); cur += ADDR_LEN if fc.to_ds and fc.from_ds else None
    body = wire[cur:len(wire) - FCS_LEN]
    fcs_got = int.from_bytes(wire[-FCS_LEN:], "little")
    fcs_calc = crc32(wire[:-FCS_LEN])
    if fcs_got != fcs_calc:
        raise ValueError(f"FCS mismatch: got 0x{fcs_got:08x}, want 0x{fcs_calc:08x}")
    return DataFrame(fc, duration, a1, a2, a3, a4 if fc.to_ds and fc.from_ds else None, seq, body)

def build_control(subtype: int, duration: int, ra: MacAddress, ta: MacAddress | None = None) -> bytes:
    fc = FrameControl(protocol_version=0, type=TYPE_CTRL, subtype=subtype)
    h = fc.to_word().to_bytes(FC_LEN, "little") + duration.to_bytes(DUR_LEN, "little") + ra.octets
    if ta is not None: h += ta.octets
    return h + crc32(h).to_bytes(FCS_LEN, "little")

def build_beacon(bssid: MacAddress, timestamp: int = 0) -> bytes:
    fc = FrameControl(protocol_version=0, type=TYPE_MGMT, subtype=8)
    h = fc.to_word().to_bytes(FC_LEN, "little") + (0).to_bytes(DUR_LEN, "little") + bssid.octets * 3
    body = timestamp.to_bytes(8, "little")
    return h + body + crc32(h + body).to_bytes(FCS_LEN, "little")

ADDRESS_MODES = (
    (0, 0, "IBSS direct", "DA", "SA", "BSSID", False),
    (1, 0, "From DS (AP->STA)", "DA (STA)", "BSSID (AP)", "SA", False),
    (0, 1, "To DS (STA->AP)", "BSSID (AP)", "SA (STA)", "DA", False),
    (1, 1, "WDS (bridge)", "RA", "TA", "DA", True),
)

def show_address_modes() -> None:
    print(f"  {'To':<4}{'From':<6}{'Mode':<22}{'Addr1':<14}{'Addr2':<14}{'Addr3':<10}{'Addr4?':<8}")
    for row in ADDRESS_MODES:
        print(f"  {row[0]:<4}{row[1]:<6}{row[2]:<22}{row[3]:<14}{row[4]:<14}{row[5]:<10}{row[6]}")

def main() -> None:
    print("=" * 72)
    print("802.11 Data-Frame Encoder/Decoder (Phase 5, Lesson 23)")
    print("=" * 72)
    ap = MacAddress.from_hex("00:11:22:33:44:55")
    sta = MacAddress.from_hex("aa:bb:cc:dd:ee:ff")
    src = MacAddress.from_hex("08:00:27:11:22:33")
    fc = FrameControl(type=TYPE_DATA, subtype=0, to_ds=1, from_ds=0)
    frame = DataFrame(fc, 44, sta, ap, src, None, SequenceControl(0, 137), b"hello-802.11")
    decoded = parse(frame.to_bytes())
    print(f"\n[1] From-DS AP->STA: FC=0x{decoded.frame_control.to_word():04x} body={decoded.body!r}")
    a = MacAddress.from_hex("de:ad:be:ef:00:01")
    b = MacAddress.from_hex("de:ad:be:ef:00:02")
    direct = DataFrame(FrameControl(TYPE_DATA, 0, 0, 0), 0, b, a, MacAddress(b"\x02"*6), None,
                       SequenceControl(0, 1), b"ad-hoc ping")
    dec2 = parse(direct.to_bytes())
    print(f"[2] IBSS direct: A->B body={dec2.body!r}")
    fc3 = FrameControl(TYPE_DATA, 0, 1, 1)
    wds = DataFrame(fc3, 100, ap, sta, src, a, SequenceControl(0, 7), b"four-addr bridge")
    dec3 = parse(wds.to_bytes())
    print(f"[3] WDS bridge: addr4={dec3.addr4} body={dec3.body!r}")
    print(f"[4] RTS = {build_control(11, 20, ap, sta).hex()}")
    print(f"    CTS = {build_control(12, 15, sta).hex()}")
    print(f"    ACK = {build_control(13, 0, sta).hex()}")
    print(f"[5] Beacon = {build_beacon(ap, 0x0123456789ABCDEF).hex()}")
    enc = frame.to_bytes()
    bad = bytearray(enc); bad[10] ^= 0x01
    try:
        parse(bytes(bad)); print("[6] ERROR: tampered accepted")
    except ValueError as exc:
        print(f"[6] Tamper rejected: {exc}")
    print("\nTo/From-DS address modes:")
    show_address_modes()

if __name__ == "__main__":
    main()
