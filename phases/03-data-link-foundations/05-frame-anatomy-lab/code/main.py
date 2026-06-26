"""Frame Anatomy Lab — an IEEE 802.3 / Ethernet II frame parser and CRC-32 verifier.

Stdlib only, no network calls. Given a raw hex stream (e.g. Wireshark's
"Copy -> ...as a Hex Stream"), this module slices the frame into its fields
(dest MAC, src MAC, EtherType/Length, payload, FCS), decodes the offset-12
field with the 1536 (0x0600) EtherType/Length rule, recomputes the CRC-32 FCS
using the IEEE 802.3 polynomial 0x04C11DB7 (reflected 0xEDB88320) and compares
it to the stored trailer, and classifies the frame size (runt/normal/jumbo).
The hand-rolled bit-by-bit CRC is cross-checked against zlib.crc32.

Run:  python3 main.py
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

# IEEE 802.3 frame geometry (offsets from the destination MAC; preamble/SFD
# are stripped by the NIC and never appear in a capture).
MAC_LEN = 6
ETHERTYPE_OFFSET = 12
ETHERTYPE_LEN = 2
FCS_LEN = 4
HEADER_PLUS_FCS = 2 * MAC_LEN + ETHERTYPE_LEN + FCS_LEN  # 18 bytes
MIN_FRAME = 64        # minimum legal frame on the wire
STD_MAX_FRAME = 1518  # 1500 MTU + 18
VLAN_MAX_FRAME = 1522 # with one 802.1Q tag
JUMBO_MAX_FRAME = 9018

# The 1536 (0x0600) threshold separates an 802.3 Length from an Ethernet II EtherType.
ETHERTYPE_THRESHOLD = 0x0600
MAX_802_3_LENGTH = 0x05DC  # 1500

KNOWN_ETHERTYPES = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x86DD: "IPv6",
    0x8100: "802.1Q VLAN-tagged",
    0x8847: "MPLS unicast",
    0x88CC: "LLDP",
}


@dataclass(frozen=True)
class Frame:
    """A decoded Ethernet frame."""

    dest_mac: str
    src_mac: str
    ethertype_raw: int
    payload: bytes
    stored_fcs: int
    frame_len: int


def format_mac(raw: bytes) -> str:
    """Render 6 raw bytes as a colon-separated MAC address."""
    return ":".join(f"{b:02x}" for b in raw)


def is_broadcast(mac: str) -> bool:
    return mac.lower() == "ff:ff:ff:ff:ff:ff"


def is_multicast(first_octet: int) -> bool:
    """The least-significant bit of the first octet marks a group address."""
    return bool(first_octet & 0x01)


def crc32_bitwise(data: bytes) -> int:
    """Compute the IEEE 802.3 CRC-32 the long way, bit by bit.

    Init register to all-ones, process each byte LSB-first against the
    reflected polynomial 0xEDB88320, then invert. This is the same CRC-32 as
    zlib/PNG/gzip, which lets us cross-check the result.
    """
    reflected_poly = 0xEDB88320
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ reflected_poly
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF


def decode_ethertype(value: int) -> str:
    """Apply the 1536 rule and name the protocol when it is an EtherType."""
    if value <= MAX_802_3_LENGTH:
        return f"802.3 Length = {value} bytes (LLC/SNAP payload)"
    if value >= ETHERTYPE_THRESHOLD:
        name = KNOWN_ETHERTYPES.get(value, "unknown EtherType")
        return f"EtherType 0x{value:04x} -> {name}"
    return f"0x{value:04x} (reserved gap between Length and EtherType)"


def classify_size(frame_len: int) -> str:
    """Bucket a frame by its on-the-wire length."""
    if frame_len < MIN_FRAME:
        return f"RUNT ({frame_len} B < {MIN_FRAME}) -> late collision / duplex mismatch"
    if frame_len <= STD_MAX_FRAME:
        return f"NORMAL ({frame_len} B)"
    if frame_len <= VLAN_MAX_FRAME:
        return f"BABY-GIANT ({frame_len} B) -> likely an 802.1Q VLAN tag"
    if frame_len <= JUMBO_MAX_FRAME:
        return f"JUMBO ({frame_len} B) -> needs end-to-end MTU agreement"
    return f"GIANT ({frame_len} B) -> dropped if it exceeds the port max"


def parse_frame(hex_stream: str) -> Frame:
    """Slice a raw hex stream into Ethernet fields. Preamble/SFD must be absent."""
    raw = bytes.fromhex(hex_stream.replace(" ", "").replace(":", ""))
    if len(raw) < HEADER_PLUS_FCS:
        raise ValueError(
            f"frame too short: {len(raw)} bytes, need at least {HEADER_PLUS_FCS}"
        )
    dest = raw[0:MAC_LEN]
    src = raw[MAC_LEN : 2 * MAC_LEN]
    etype = int.from_bytes(
        raw[ETHERTYPE_OFFSET : ETHERTYPE_OFFSET + ETHERTYPE_LEN], "big"
    )
    payload = raw[ETHERTYPE_OFFSET + ETHERTYPE_LEN : -FCS_LEN]
    stored_fcs = int.from_bytes(raw[-FCS_LEN:], "little")  # FCS is little-endian on the wire
    return Frame(
        dest_mac=format_mac(dest),
        src_mac=format_mac(src),
        ethertype_raw=etype,
        payload=payload,
        stored_fcs=stored_fcs,
        frame_len=len(raw),
    )


def verify_fcs(hex_stream: str) -> tuple[int, int, bool]:
    """Recompute the CRC-32 over dest-MAC..payload and compare to the stored FCS."""
    raw = bytes.fromhex(hex_stream.replace(" ", "").replace(":", ""))
    covered = raw[:-FCS_LEN]
    computed = crc32_bitwise(covered)
    assert computed == zlib.crc32(covered), "bitwise CRC disagrees with zlib"
    stored = int.from_bytes(raw[-FCS_LEN:], "little")
    return computed, stored, computed == stored


def build_frame(dest: str, src: str, ethertype: int, payload: bytes) -> str:
    """Construct a valid frame (with a correct FCS) and return it as a hex stream."""
    body = bytes.fromhex(dest.replace(":", "")) + bytes.fromhex(src.replace(":", ""))
    body += ethertype.to_bytes(2, "big") + payload
    if len(body) < MIN_FRAME - FCS_LEN:
        body += b"\x00" * (MIN_FRAME - FCS_LEN - len(body))  # pad to 46-byte payload floor
    fcs = crc32_bitwise(body).to_bytes(4, "little")
    return (body + fcs).hex()


def report(label: str, hex_stream: str) -> None:
    """Print a full field-by-field decode of one frame."""
    print(f"=== {label} ===")
    frame = parse_frame(hex_stream)
    first_octet = int(frame.dest_mac.split(":")[0], 16)
    if is_broadcast(frame.dest_mac):
        kind = "[broadcast]"
    elif is_multicast(first_octet):
        kind = "[multicast]"
    else:
        kind = "[unicast]"
    print(f"  Destination MAC : {frame.dest_mac}  {kind}")
    print(f"  Source MAC      : {frame.src_mac}")
    print(f"  Type/Length     : {decode_ethertype(frame.ethertype_raw)}")
    preview = frame.payload[:8].hex()
    ellipsis = "..." if len(frame.payload) > 8 else ""
    print(f"  Payload         : {len(frame.payload)} bytes ({preview}{ellipsis})")
    print(f"  Size class      : {classify_size(frame.frame_len)}")
    computed, stored, ok = verify_fcs(hex_stream)
    verdict = "OK" if ok else "BAD -> increments switch CRC counter"
    print(f"  FCS stored      : 0x{stored:08x}")
    print(f"  FCS computed    : 0x{computed:08x}  [{verdict}]")
    print()


# Embedded sample frames (preamble/SFD already stripped, as in a capture).
# ARP request, broadcast destination, EtherType 0x0806, FCS recomputed to be valid.
ARP_FRAME = build_frame(
    dest="ff:ff:ff:ff:ff:ff",
    src="00:11:22:33:44:55",
    ethertype=0x0806,
    payload=bytes.fromhex(
        "0001080006040001"      # hw=Ethernet, proto=IPv4, hlen=6, plen=4, op=request
        "001122334455c0a80101"  # sender MAC + sender IP 192.168.1.1
        "000000000000c0a80142"  # target MAC unknown + target IP 192.168.1.66
    ),
)

# IPv4 frame, unicast, EtherType 0x0800, valid FCS.
IPV4_FRAME = build_frame(
    dest="00:0c:29:ab:cd:ef",
    src="00:50:56:c0:00:08",
    ethertype=0x0800,
    payload=bytes.fromhex("4500001c0001000040067c") + b"hello-ipv4",
)


def corrupt_one_bit(hex_stream: str, byte_index: int = 20) -> str:
    """Flip one payload bit, leaving the stored FCS unchanged (simulates a CRC error)."""
    raw = bytearray(bytes.fromhex(hex_stream))
    raw[byte_index] ^= 0x01  # FCS now mismatches the data
    return raw.hex()


CORRUPT_FRAME = corrupt_one_bit(IPV4_FRAME)


def main() -> None:
    print("Frame Anatomy Lab — IEEE 802.3 frame parser + CRC-32 verifier\n")
    report("ARP request (broadcast)", ARP_FRAME)
    report("IPv4 unicast (healthy)", IPV4_FRAME)
    report("IPv4 unicast (1 bit flipped, FCS not updated)", CORRUPT_FRAME)

    print("Spot-check: CRC-32 of payload 'DE AD BE EF'")
    sample = bytes.fromhex("DEADBEEF")
    print(f"  crc32_bitwise = 0x{crc32_bitwise(sample):08x}")
    print(f"  zlib.crc32    = 0x{zlib.crc32(sample):08x}")


if __name__ == "__main__":
    main()
