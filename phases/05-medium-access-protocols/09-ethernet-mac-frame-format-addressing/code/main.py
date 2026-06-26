"""
Ethernet MAC Frame Parser and Builder (IEEE 802.3 / DIX Ethernet II)

Demonstrates:
  - Building and parsing Ethernet II / IEEE 802.3 frames from raw bytes
  - 48-bit MAC address encoding: unicast/multicast/broadcast, OUI extraction,
    I/G and U/L bit semantics
  - Type-vs-Length field disambiguation (threshold 0x0600 / 1536)
  - CRC-32 FCS calculation and verification using the standard 802.3 polynomial
  - Pad field insertion to enforce the 64-byte minimum frame size

No third-party dependencies — stdlib only.
Run:  python3 main.py
"""

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BROADCAST_MAC: bytes = b"\xff\xff\xff\xff\xff\xff"
MIN_PAYLOAD_BYTES: int = 46       # pad data to this if shorter (802.3 rule)
MAX_PAYLOAD_BYTES: int = 1500     # Ethernet MTU
MIN_FRAME_BYTES: int = 64         # dest+src+type/len+data+FCS minimum
MAX_FRAME_BYTES: int = 1518       # without 802.1Q VLAN tag

# Any value > 0x0600 means EtherType (DIX), ≤ 0x0600 means Length (802.3).
ETHERTYPE_THRESHOLD: int = 0x0600

ETHERTYPE_NAMES: dict[int, str] = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x0842: "Wake-on-LAN",
    0x86DD: "IPv6",
    0x8100: "802.1Q VLAN",
    0x88CC: "LLDP",
    0x9000: "Ethernet loopback",
}

# Partial OUI → vendor table (first 3 bytes of MAC address)
OUI_VENDOR: dict[bytes, str] = {
    bytes.fromhex("001a2b"): "Example Corp",
    bytes.fromhex("000c29"): "VMware",
    bytes.fromhex("525400"): "QEMU/KVM",
    bytes.fromhex("aabbcc"): "Demo NIC",
    bytes.fromhex("001122"): "Ciena",
}


# ---------------------------------------------------------------------------
# MAC address helpers
# ---------------------------------------------------------------------------

def mac_to_bytes(mac_str: str) -> bytes:
    """'aa:bb:cc:dd:ee:ff' or 'aa-bb-cc-dd-ee-ff' → 6 raw bytes."""
    clean = mac_str.replace("-", ":").replace(".", ":")
    parts = clean.split(":")
    if len(parts) != 6:
        raise ValueError(f"Invalid MAC: {mac_str!r}")
    return bytes(int(p, 16) for p in parts)


def bytes_to_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def mac_is_multicast(raw: bytes) -> bool:
    """I/G bit: LSB of the first transmitted (leftmost memory) byte."""
    return bool(raw[0] & 0x01)


def mac_is_broadcast(raw: bytes) -> bool:
    return raw == BROADCAST_MAC


def mac_is_locally_administered(raw: bytes) -> bool:
    """U/L bit: second LSB of the first byte."""
    return bool(raw[0] & 0x02)


def mac_oui(raw: bytes) -> tuple[bytes, str]:
    oui = raw[:3]
    return oui, OUI_VENDOR.get(oui, "Unknown vendor")


# ---------------------------------------------------------------------------
# Type/Length disambiguation
# ---------------------------------------------------------------------------

def interpret_type_length(value: int) -> tuple[str, str]:
    """
    IEEE 802.3-1997 unification rule:
      value ≤ 0x0600 → Length field (original 802.3)
      value  > 0x0600 → EtherType  (Ethernet II / DIX)
    Returns (kind, human_description).
    """
    if value <= ETHERTYPE_THRESHOLD:
        return "LENGTH", f"payload length = {value} B (IEEE 802.3)"
    name = ETHERTYPE_NAMES.get(value, "unknown protocol")
    return "ETHERTYPE", f"0x{value:04X} → {name}"


# ---------------------------------------------------------------------------
# FCS (CRC-32)
# ---------------------------------------------------------------------------

def compute_fcs(data: bytes) -> int:
    """
    Ethernet FCS uses CRC-32 with generator polynomial 0xEDB88320 (reflected).
    zlib.crc32 implements exactly this — the same polynomial as IEEE 802.3
    clause 3.2.9, PPP (RFC 1662), and ADSL.
    The 32-bit result is stored LSB-first (little-endian) in the frame.
    """
    return zlib.crc32(data) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Frame dataclass
# ---------------------------------------------------------------------------

@dataclass
class EthernetFrame:
    dst: bytes               # 6 bytes — destination MAC
    src: bytes               # 6 bytes — source MAC
    type_or_length: int      # 2 bytes — EtherType or payload byte count
    payload: bytes           # 0–1500 bytes (application / network layer data)
    _pad: bytes = field(default=b"", repr=False)
    _fcs: Optional[int] = field(default=None, repr=False)

    def build(self) -> bytes:
        """
        Serialise to wire bytes (destination address through FCS; no preamble).
        Inserts zero-padding if payload < 46 bytes to satisfy the 64-byte
        minimum enforced for CSMA/CD collision detection (2τ rule).
        """
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Payload {len(self.payload)} B exceeds 1500 B MTU")
        pad_len = max(0, MIN_PAYLOAD_BYTES - len(self.payload))
        self._pad = b"\x00" * pad_len
        header = self.dst + self.src + struct.pack("!H", self.type_or_length)
        body = header + self.payload + self._pad
        self._fcs = compute_fcs(body)
        return body + struct.pack("<I", self._fcs)  # FCS is LE on the wire

    @classmethod
    def parse(cls, raw: bytes) -> "EthernetFrame":
        """
        Parse raw wire bytes (dest…FCS) into an EthernetFrame.
        Raises ValueError on length violations or FCS mismatch.
        """
        if len(raw) < MIN_FRAME_BYTES:
            raise ValueError(f"Frame too short: {len(raw)} < {MIN_FRAME_BYTES} B")
        if len(raw) > MAX_FRAME_BYTES:
            raise ValueError(f"Frame too long: {len(raw)} > {MAX_FRAME_BYTES} B")

        dst = raw[0:6]
        src = raw[6:12]
        (type_or_length,) = struct.unpack("!H", raw[12:14])
        received_fcs = struct.unpack("<I", raw[-4:])[0]

        computed = compute_fcs(raw[:-4])
        if computed != received_fcs:
            raise ValueError(
                f"FCS mismatch: received 0x{received_fcs:08X}, "
                f"computed 0x{computed:08X} — frame corrupted"
            )

        kind, _ = interpret_type_length(type_or_length)
        if kind == "LENGTH":
            # 802.3: field value IS the true payload length (strip pad)
            payload_end = 14 + type_or_length
        else:
            # EtherType: entire region between header and FCS is payload
            payload_end = len(raw) - 4

        frame = cls(dst=dst, src=src, type_or_length=type_or_length,
                    payload=raw[14:payload_end])
        frame._fcs = received_fcs
        return frame

    def describe(self) -> None:
        kind, type_desc = interpret_type_length(self.type_or_length)
        _, dst_vendor = mac_oui(self.dst)
        _, src_vendor = mac_oui(self.src)
        dst_flags = ""
        if mac_is_broadcast(self.dst):
            dst_flags = " <BROADCAST>"
        elif mac_is_multicast(self.dst):
            dst_flags = " <MULTICAST>"
        src_flags = " <locally-admin>" if mac_is_locally_administered(self.src) else ""

        print(f"  Dst  : {bytes_to_mac(self.dst)}  [{dst_vendor}]{dst_flags}")
        print(f"  Src  : {bytes_to_mac(self.src)}  [{src_vendor}]{src_flags}")
        print(f"  Type/Len field : 0x{self.type_or_length:04X} ({self.type_or_length})")
        print(f"    ↳ {kind}: {type_desc}")
        print(f"  Payload: {len(self.payload)} B  |  Pad: {len(self._pad)} B"
              f"  |  FCS: 0x{self._fcs:08X}" if self._fcs is not None
              else f"  Payload: {len(self.payload)} B")


# ---------------------------------------------------------------------------
# main — realistic demonstrations
# ---------------------------------------------------------------------------

def main() -> None:
    SEP = "─" * 62

    print("=" * 62)
    print("  Ethernet MAC Frame — Parser & Builder (IEEE 802.3 / DIX)")
    print("=" * 62)

    # --- Demo 1: Ethernet II IPv4 broadcast, short payload → padding ---
    print(f"\n{SEP}")
    print("  Demo 1: Ethernet II — IPv4 broadcast (22-byte payload → pad to 46)")
    print(SEP)
    f1 = EthernetFrame(
        dst=mac_to_bytes("ff:ff:ff:ff:ff:ff"),
        src=mac_to_bytes("aa:bb:cc:00:11:22"),
        type_or_length=0x0800,
        payload=b"\x45\x00" + b"\xde\xad\xbe\xef" * 5,  # 22 bytes
    )
    wire1 = f1.build()
    print(f"  Wire ({len(wire1)} B): {wire1.hex()}")
    EthernetFrame.parse(wire1).describe()

    # --- Demo 2: Ethernet II ARP request (28-byte payload → also padded) ---
    print(f"\n{SEP}")
    print("  Demo 2: Ethernet II — ARP request (28-byte payload → pad to 46)")
    print(SEP)
    arp = (b"\x00\x01\x08\x00\x06\x04\x00\x01"
           + mac_to_bytes("aa:bb:cc:00:11:22")
           + b"\xc0\xa8\x01\x01"
           + b"\x00" * 6
           + b"\xc0\xa8\x01\x02")   # 28 bytes
    f2 = EthernetFrame(
        dst=mac_to_bytes("ff:ff:ff:ff:ff:ff"),
        src=mac_to_bytes("aa:bb:cc:00:11:22"),
        type_or_length=0x0806,
        payload=arp,
    )
    wire2 = f2.build()
    print(f"  Wire ({len(wire2)} B): {wire2.hex()}")
    EthernetFrame.parse(wire2).describe()

    # --- Demo 3: IEEE 802.3 Length-mode frame (value ≤ 0x0600) ---
    print(f"\n{SEP}")
    print("  Demo 3: IEEE 802.3 — Length field mode (value = payload length)")
    print(SEP)
    payload3 = b"Hello, 802.3 world! " * 3   # 60 bytes — no padding needed
    f3 = EthernetFrame(
        dst=mac_to_bytes("00:1a:2b:3c:4d:5e"),
        src=mac_to_bytes("52:54:00:ab:cd:ef"),
        type_or_length=len(payload3),   # 60 ≤ 1536 → Length semantics
        payload=payload3,
    )
    wire3 = f3.build()
    print(f"  Wire ({len(wire3)} B): {wire3.hex()[:80]}…")
    EthernetFrame.parse(wire3).describe()

    # --- Demo 4: FCS corruption detection ---
    print(f"\n{SEP}")
    print("  Demo 4: FCS corruption detection")
    print(SEP)
    f4 = EthernetFrame(
        dst=mac_to_bytes("00:1a:2b:3c:4d:5e"),
        src=mac_to_bytes("aa:bb:cc:00:11:22"),
        type_or_length=0x0800,
        payload=b"integrity check" + b"\x00" * 31,
    )
    wire4 = bytearray(f4.build())
    wire4[20] ^= 0xFF   # flip bits in the payload
    try:
        EthernetFrame.parse(bytes(wire4))
    except ValueError as exc:
        print(f"  Caught expected error: {exc}")

    # --- Demo 5: Type-vs-Length threshold table ---
    print(f"\n{SEP}")
    print("  Demo 5: Type-vs-Length disambiguation table (IEEE 802.3-1997)")
    print(SEP)
    print(f"  {'Value':<10} {'Kind':<12} {'Description'}")
    print(f"  {'─'*56}")
    rows = [
        (0x002E, "payload = 46 B minimum"),
        (0x05DC, "payload = 1500 B maximum"),
        (0x0600, "boundary — still treated as Length"),
        (0x0601, "one above boundary — EtherType"),
        (0x0800, "IPv4"),
        (0x0806, "ARP"),
        (0x86DD, "IPv6"),
        (0x8100, "802.1Q VLAN tag"),
    ]
    for val, note in rows:
        kind, _ = interpret_type_length(val)
        print(f"  0x{val:04X}     {kind:<12} {note}")

    print()


if __name__ == "__main__":
    main()
