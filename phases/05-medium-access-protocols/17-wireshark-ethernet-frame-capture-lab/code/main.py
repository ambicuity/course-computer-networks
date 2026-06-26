"""Wireshark-style Ethernet II frame parser (stdlib only).

This module dissects raw Ethernet II frames the way Wireshark/tshark would
on the link layer. It demonstrates the exact same fields a packet-capture
analyst reads first: preamble/SFD, destination MAC (with I/G and U/L bits),
source MAC (with OUI lookup), the EtherType/Length 0x600 rule, payload,
pad, and a CRC-32 trailer using the standard Ethernet generator
polynomial 0x04C11DB7. The printout at the bottom mirrors the Wireshark
dissection tree so you can verify your capture by hand.

Run with: python3 code/main.py
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Final

# Standard Ethernet CRC-32 generator polynomial (the same one used by
# classic Ethernet, PPP, ADSL, etc.). Reflected form 0xEDB88320 is what
# the on-the-wire hardware actually uses, but 0x04C11DB7 is the value the
# textbook states, and bit-reversed reflection is implemented below.
CRC32_POLY: Final[int] = 0x04C11DB7
CRC32_REFLECTED: Final[int] = 0xEDB88320

# OUI → vendor (a small but real subset of IEEE assignments).
OUI_TABLE: Final[dict[str, str]] = {
    "001B2B": "Cisco Systems",
    "A85C2C": "Apple, Inc.",
    "001A2B": "Hewlett-Packard",
    "F4F5D8": "Google, Inc.",
    "001CC4": "Intel Corporation",
    "001E52": "Apple, Inc. (older)",
    "D85D4C": "Dell Inc.",
    "B499BA": "Dell Inc. (Realtek)",
    "001100": "IBM",
    "0050F2": "Microsoft",
    "002272": "Cisco-Linksys",
    "ACDE48": "Private (locally administered)",
}

# Selected EtherTypes (16-bit). Values <= 0x0600 (1536) are 802.3 Length.
ETHERTYPE_TABLE: Final[dict[int, str]] = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x0842: "WoL (Wake-on-LAN)",
    0x22F3: "TRILL",
    0x6003: "DECnet Phase IV",
    0x8035: "RARP",
    0x809B: "AppleTalk",
    0x80F3: "AARP",
    0x8100: "IEEE 802.1Q VLAN-tagged frame",
    0x8137: "IPX",
    0x86DD: "IPv6",
    0x8808: "Ethernet flow control (PAUSE)",
    0x8847: "MPLS unicast",
    0x8848: "MPLS multicast",
    0x8863: "PPPoE Discovery",
    0x8864: "PPPoE Session",
    0x88CC: "LLDP (Link Layer Discovery Protocol)",
    0x88E1: "HomePlug AV",
    0x9000: "Ethernet Configuration Testing Protocol",
}

MAX_PAYLOAD: Final[int] = 1500
MIN_FRAME: Final[int] = 60  # 64 bytes from dest to FCS, minus the 4-byte FCS = 60


@dataclass(frozen=True)
class MacAddr:
    """48-bit MAC with first-transmitted-bit helpers."""

    octets: tuple[int, ...]  # 6 bytes, network order (byte 0 first on the wire)

    def __post_init__(self) -> None:
        if len(self.octets) != 6 or any(not 0 <= b <= 255 for b in self.octets):
            raise ValueError(f"not a valid MAC: {self.octets!r}")

    @property
    def canonical(self) -> str:
        return ":".join(f"{b:02x}" for b in self.octets)

    @property
    def first_transmitted_byte(self) -> int:
        """The byte sent first on the wire (lowest-numbered byte in the frame)."""
        return self.octets[0]

    @property
    def first_transmitted_bit(self) -> int:
        """Ethernet sends each byte LSB-first, so the very first bit on the wire
        is the LSB of byte 0. That bit is the I/G (Individual/Group) flag."""
        return self.first_transmitted_byte & 0x01

    @property
    def second_transmitted_bit(self) -> int:
        """Next bit on the wire: U/L (Universal/Local) bit. 0 = OUI-assigned,
        1 = locally administered (overrides the OUI)."""
        return (self.first_transmitted_byte >> 1) & 0x01

    @property
    def is_unicast(self) -> bool:
        return self.first_transmitted_bit == 0

    @property
    def is_multicast(self) -> bool:
        return self.first_transmitted_bit == 1 and self.octets != (0xFF,) * 6

    @property
    def is_broadcast(self) -> bool:
        return self.octets == (0xFF,) * 6

    @property
    def is_local(self) -> bool:
        return self.second_transmitted_bit == 1

    @property
    def oui(self) -> str:
        return "".join(f"{b:02X}" for b in self.octets[:3])

    @property
    def vendor(self) -> str:
        return OUI_TABLE.get(self.oui, "Unknown / not in local OUI table")


@dataclass(frozen=True)
class EtherTypeField:
    """The two-byte field after the source MAC. In Ethernet II it is a
    Type (EtherType) identifying the next protocol. In IEEE 802.3 it is a
    Length, in which case an LLC/SNAP header sits inside the payload."""

    raw: int

    def __post_init__(self) -> None:
        if not 0 <= self.raw <= 0xFFFF:
            raise ValueError(f"not a valid 16-bit field: {self.raw:#x}")

    @property
    def is_length(self) -> bool:
        # The 1997 IEEE reconciliation: <= 0x600 (1536) is Length, > 0x600 is Type.
        return self.raw <= 0x0600

    @property
    def interpretation(self) -> str:
        if self.is_length:
            return f"802.3 Length = {self.raw} bytes"
        return f"EtherType = 0x{self.raw:04X} ({ETHERTYPE_TABLE.get(self.raw, 'unknown')})"


def crc32_ethernet(data: bytes) -> int:
    """Compute the Ethernet CRC-32 (generator 0x04C11DB7, reflected)."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (CRC32_REFLECTED if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


@dataclass(frozen=True)
class EthernetFrame:
    """A dissected Ethernet II frame, Wireshark-style."""

    preamble: bytes
    sfd: int
    dst: MacAddr
    src: MacAddr
    type_length: EtherTypeField
    payload: bytes
    fcs: int

    @property
    def length_dest_to_fcs(self) -> int:
        """Bytes from destination through FCS, inclusive."""
        return 6 + 6 + 2 + len(self.payload) + 4

    @property
    def pad(self) -> int:
        """How many pad bytes the sender had to add to reach the 64-byte minimum
        from dest..FCS. A 0 here means the payload was at least 46 bytes."""
        return max(0, MIN_FRAME - (6 + 6 + 2 + len(self.payload) + 4))

    @property
    def fcs_valid(self) -> bool:
        recomputed = crc32_ethernet(
            bytes(self.dst.octets)
            + bytes(self.src.octets)
            + struct.pack("!H", self.type_length.raw)
            + self.payload
        )
        return recomputed == self.fcs

    def to_wireshark_text(self) -> str:
        dest_class = (
            "Broadcast" if self.dst.is_broadcast
            else "Multicast" if self.dst.is_multicast
            else "Unicast"
        )
        src_class = (
            "locally administered" if self.src.is_local
            else "globally unique (OUI-assigned)"
        )
        lines = [
            f"  Preamble: 7× 0xAA + SFD 0x{self.sfd:02X}",
            f"  Destination: {self.dst.canonical}   [{dest_class}]",
            f"    .... ..{self.dst.second_transmitted_bit} "
            f".... .... .... .... = U/L bit: {src_class}",
            f"    .... ...{self.dst.first_transmitted_bit} "
            f".... .... .... .... = I/G bit: "
            f"{'Group (multicast/broadcast)' if self.dst.first_transmitted_bit else 'Individual (unicast)'}",
            f"    OUI: {self.dst.vendor}",
            f"  Source:    {self.src.canonical}",
            f"    OUI: {self.src.vendor}",
            f"  {self.type_length.interpretation}",
            f"  Payload: {len(self.payload)} bytes",
            f"  Pad: {self.pad} bytes (to satisfy 64-byte minimum dest..FCS)",
            f"  FCS (CRC-32): 0x{self.fcs:08X}  "
            f"[{'VALID' if self.fcs_valid else 'MISMATCH'}]",
        ]
        return "\n".join(lines)


def _hex_to_bytes(s: str) -> bytes:
    cleaned = s.replace(" ", "").replace(":", "").replace("-", "").replace("\n", "")
    if len(cleaned) % 2:
        raise ValueError("hex string must have an even number of nibbles")
    return bytes.fromhex(cleaned)


def parse_frame(raw: str | bytes, include_preamble: bool = True) -> EthernetFrame:
    """Parse raw frame bytes (with or without preamble) into an EthernetFrame.

    The frame must include the 4-byte FCS trailer — the parser recomputes the
    CRC and reports whether it matches, exactly like Wireshark.
    """
    data = raw if isinstance(raw, bytes) else _hex_to_bytes(raw)
    offset = 0

    if include_preamble:
        if len(data) < 8:
            raise ValueError("frame too short to contain a preamble + SFD")
        preamble = data[:7]
        sfd = data[7]
        offset = 8
        if any(b != 0xAA for b in preamble):
            raise ValueError("preamble bytes other than 0xAA — not Ethernet II")
        if sfd != 0xAB:
            raise ValueError(f"unexpected SFD byte 0x{sfd:02X}, want 0xAB")
    else:
        preamble = bytes(7)
        sfd = 0xAB

    if len(data) < offset + 14 + 4:
        raise ValueError("frame too short to contain addresses, type/length, and FCS")

    dst = MacAddr(tuple(data[offset:offset + 6]))
    src = MacAddr(tuple(data[offset + 6:offset + 12]))
    type_length = EtherTypeField(struct.unpack("!H", data[offset + 12:offset + 14])[0])
    payload = bytes(data[offset + 14:-4])
    fcs = struct.unpack("!I", data[-4:])[0]
    return EthernetFrame(preamble, sfd, dst, src, type_length, payload, fcs)


def _mac(b: str) -> bytes:
    return bytes.fromhex(b.replace(":", ""))


def _format_table_row(label: str, value: str) -> str:
    return f"  {label:<14} {value}"


# ---------------------------------------------------------------------------
# Demonstration / self-test frames
# ---------------------------------------------------------------------------


def _build_frame(dst: str, src: str, ethertype: int, payload: bytes) -> EthernetFrame:
    """Build a frame with a *valid* CRC-32 trailer, then run parse_frame on it."""
    raw = (
        b"\xAA" * 7
        + b"\xAB"
        + _mac(dst)
        + _mac(src)
        + struct.pack("!H", ethertype)
        + payload
    )
    raw += struct.pack("!I", crc32_ethernet(raw[8:]))
    return parse_frame(raw)


def _vlan_frame(dst: str, src: str, vid: int, inner_type: int, payload: bytes) -> EthernetFrame:
    """Build an 802.1Q-tagged frame (TPID 0x8100 + TCI with VID, then the real Type)."""
    raw = (
        b"\xAA" * 7
        + b"\xAB"
        + _mac(dst)
        + _mac(src)
        + struct.pack("!HH", 0x8100, vid & 0x0FFF)
        + struct.pack("!H", inner_type)
        + payload
    )
    raw += struct.pack("!I", crc32_ethernet(raw[8:]))
    return parse_frame(raw)


# (name, dst, src, ethertype, payload) — six realistic frames a Wireshark user
# would expect to recognise. The VLAN entry uses _vlan_frame() instead.
_DEMOS: Final[list[tuple[str, str, str, str, int, bytes]]] = [
    (
        "1) Unicast IPv4  (Apple laptop -> Cisco router)",
        "00:1b:2b:b1:3f:90", "a8:5c:2c:22:c4:7e", "", 0x0800,
        b"\x45\x00\x00\x80\x00\x40\x40\x06" + b"\x00" * 100,
    ),
    (
        "2) Broadcast ARP request (who-has 10.0.0.1?)",
        "ff:ff:ff:ff:ff:ff", "a8:5c:2c:22:c4:7e", "", 0x0806,
        bytes.fromhex(
            "0001 0800 0604 0001 a85c2c22c47e 0a000007"
            " 0000 0000 0000 0a000001".replace(" ", "")
        ),
    ),
    (
        "3) Multicast IPv6 (solicited-node)",
        "33:33:00:00:00:01", "a8:5c:2c:22:c4:7e", "", 0x86DD,
        bytes.fromhex(
            "60000000 00202001 0db80000 00000000 00000000"
            " ff020000 00000000 00000001 8700".replace(" ", "")
        ),
    ),
    (
        "5) LLDP multicast 01:80:c2:00:00:0e",
        "01:80:c2:00:00:0e", "a8:5c:2c:22:c4:7e", "", 0x88CC,
        bytes.fromhex(
            "0207 04a85c 2c22c47e 0407 0300 1b2b b13f90 0602 0078".replace(" ", "")
        ),
    ),
    (
        "6) IEEE 802.3 length-style frame (Length = 0x002E = 46)",
        "00:1b:2b:b1:3f:90", "a8:5c:2c:22:c4:7e", "", 0x002E,
        b"\xaa\xaa\x03" + b"\x00" * 43,  # DSAP/SSAP/CTL + data
    ),
]


# ---------------------------------------------------------------------------
# CLI: print the dissection table
# ---------------------------------------------------------------------------


def _print_frame(name: str, frame: EthernetFrame) -> None:
    print("=" * 78)
    print(name)
    print("=" * 78)
    print(f"  Length (Dest..FCS): {frame.length_dest_to_fcs} bytes")
    print(frame.to_wireshark_text())
    print()


def main() -> None:
    print("Ethernet II frame dissection (Wireshark-style)")
    print(f"CRC-32 polynomial: 0x{CRC32_POLY:08X}  (reflected 0x{CRC32_REFLECTED:08X})")
    print("64-byte minimum (Dest..FCS), 1500-byte max payload, 0x600 Type/Length rule")
    print()

    for name, dst, src, _vlan_marker, ethertype, payload in _DEMOS:
        _print_frame(name, _build_frame(dst, src, ethertype, payload))

    # VLAN entry built with the tag-aware helper.
    _print_frame(
        "4) VLAN-tagged IPv4 (VID 20, 802.1Q)",
        _vlan_frame(
            "00:1b:2b:b1:3f:90", "a8:5c:2c:22:c4:7e",
            vid=20, inner_type=0x0800, payload=b"\x45" + b"\x00" * 60,
        ),
    )

    print("=" * 78)
    print("EtherType / Length field: the 0x600 (1536) reconciliation rule")
    print("=" * 78)
    for value, label in [
        (0x05DC, "1500 (still interpreted as Length in pre-1997 framing)"),
        (0x0600, "1536 boundary"),
        (0x0800, "0x0800 IPv4 — Type"),
        (0x0806, "0x0806 ARP — Type"),
        (0x86DD, "0x86DD IPv6 — Type"),
        (0x8100, "0x8100 IEEE 802.1Q VLAN — Type"),
        (0x88CC, "0x88CC LLDP — Type"),
    ]:
        ef = EtherTypeField(value)
        print(f"  0x{value:04X} ({value:>5})  →  {ef.interpretation}  [{label}]")


if __name__ == "__main__":
    main()
