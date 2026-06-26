"""Classic Ethernet (IEEE 802.3 / DIX) frame parser + CSMA/CD backoff simulator.

Two stdlib-only tools that mirror the lesson:

1. parse_frame() dissects a classic Ethernet frame (preamble optional) into its
   fields, classifies the destination via the I/G bit, resolves the Type-vs-Length
   field using the 0x600 (1536) threshold, looks up known OUIs / EtherTypes, and
   verifies the IEEE 802.3 CRC-32 (generator polynomial 0x04C11DB7).

2. simulate_csma_cd() runs slotted contention with binary exponential backoff
   (window [0, 2^min(k,10)-1] slots, frozen at 1023, give up after 16 collisions)
   and reports collisions, total slots, and channel efficiency approaching 1/e.

No third-party packages, no network access. Run: python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# --- Constants straight from the standard -------------------------------------
SLOT_TIME_BITS = 512          # 512 bit-times
BIT_TIME_NS_10MBPS = 100      # 100 ns per bit at 10 Mbps
SLOT_TIME_US = SLOT_TIME_BITS * BIT_TIME_NS_10MBPS / 1000.0  # 51.2 us
MIN_FRAME_BYTES = 64          # Dest..CRC inclusive
MAX_PAYLOAD = 1500
TYPE_LENGTH_THRESHOLD = 0x600  # 1536: <= is Length, > is Type
MAX_COLLISIONS = 16
BACKOFF_FREEZE = 10           # window stops growing after 10th collision
JAM_BITS = 48

# IEEE 802.3 CRC-32 generator polynomial (reflected form used below: 0xEDB88320).
CRC32_POLY_NORMAL = 0x04C11DB7

KNOWN_OUIS = {
    "00:1B:44": "SanDisk",
    "00:00:0C": "Cisco",
    "00:50:56": "VMware",
    "08:00:27": "PCS/VirtualBox",
    "01:00:5E": "IPv4 multicast (RFC 1112)",
    "33:33:00": "IPv6 multicast",
}

KNOWN_ETHERTYPES = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x86DD: "IPv6",
    0x8100: "802.1Q VLAN tag",
    0x8035: "RARP",
}


def crc32_ieee(data: bytes) -> int:
    """Compute the IEEE 802.3 CRC-32 over `data` (reflected, init 0xFFFFFFFF)."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320  # reflected 0x04C11DB7
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF


def fmt_mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def classify_dest(dest: bytes) -> str:
    """Decode the Individual/Group bit and broadcast/multicast/unicast class."""
    if dest == b"\xff" * 6:
        return "broadcast (all stations)"
    # First *transmitted* bit is the low-order bit of the first byte (LSB-first).
    ig_bit = dest[0] & 0x01
    if ig_bit:
        return "multicast (group address, I/G=1)"
    return "unicast (individual, I/G=0)"


def interpret_type_length(value: int) -> str:
    """Apply the 1997 IEEE reconciliation rule at 0x600 (1536)."""
    if value <= TYPE_LENGTH_THRESHOLD:
        return f"Length = {value} bytes (IEEE 802.3 interpretation)"
    name = KNOWN_ETHERTYPES.get(value, "unknown EtherType")
    return f"Type = 0x{value:04X} ({name}) (DIX interpretation)"


@dataclass
class ParsedFrame:
    dest: bytes
    src: bytes
    type_length: int
    payload: bytes
    pad: bytes
    crc_in_frame: int
    crc_computed: int
    framed_len: int  # Dest..CRC

    @property
    def crc_ok(self) -> bool:
        return self.crc_in_frame == self.crc_computed

    @property
    def is_runt(self) -> bool:
        return self.framed_len < MIN_FRAME_BYTES


def parse_frame(hex_str: str, has_preamble: bool = False) -> ParsedFrame:
    """Parse a classic Ethernet frame from a hex string.

    Layout (no preamble): Dest(6) Src(6) Type/Len(2) Payload+Pad(N) CRC(4).
    If has_preamble is True, the leading 8 bytes (7x AA + AB SFD) are stripped.
    """
    raw = bytes.fromhex(hex_str.replace(" ", "").replace(":", ""))
    if has_preamble:
        raw = raw[8:]
    if len(raw) < 6 + 6 + 2 + 4:
        raise ValueError(f"frame too short: {len(raw)} bytes (need >= 18)")

    dest = raw[0:6]
    src = raw[6:12]
    type_length = int.from_bytes(raw[12:14], "big")
    body = raw[14:-4]
    crc_in_frame = int.from_bytes(raw[-4:], "big")

    # If the field is a Length, the trailing bytes beyond it are pad.
    if type_length <= TYPE_LENGTH_THRESHOLD and type_length <= len(body):
        payload, pad = body[:type_length], body[type_length:]
    else:
        payload, pad = body, b""

    crc_computed = crc32_ieee(raw[:-4])
    return ParsedFrame(
        dest=dest,
        src=src,
        type_length=type_length,
        payload=payload,
        pad=pad,
        crc_in_frame=crc_in_frame,
        crc_computed=crc_computed,
        framed_len=len(raw),
    )


def build_frame(dest: bytes, src: bytes, ethertype: int, payload: bytes) -> str:
    """Build a valid classic Ethernet frame (hex) with padding + CRC-32."""
    body = payload
    header = dest + src + ethertype.to_bytes(2, "big")
    # Pad so Dest..CRC reaches the 64-byte minimum (CRC is 4 bytes).
    min_body = MIN_FRAME_BYTES - len(header) - 4
    if len(body) < min_body:
        body = body + b"\x00" * (min_body - len(body))
    frame_wo_crc = header + body
    crc = crc32_ieee(frame_wo_crc)
    return (frame_wo_crc + crc.to_bytes(4, "big")).hex()


def backoff_window(collision_count: int) -> int:
    """Number of slots in the randomization window after `collision_count` collisions."""
    exponent = min(collision_count, BACKOFF_FREEZE)
    return 2 ** exponent  # window is [0, 2^k - 1], i.e. this many values


@dataclass
class SimResult:
    stations: int
    succeeded: int
    abandoned: int
    total_slots: int
    total_collisions: int

    @property
    def efficiency(self) -> float:
        # Useful slots / total slots; useful = one per successful frame.
        return self.succeeded / self.total_slots if self.total_slots else 0.0


def simulate_csma_cd(n_stations: int, seed: int = 7) -> SimResult:
    """Slotted CSMA/CD with binary exponential backoff.

    Each station has one frame. In each slot, every contending station with a
    zero backoff timer transmits. Exactly one transmitter => success. Two or more
    => collision: each colliding station increments its collision count and draws
    a new random backoff in [0, 2^min(k,10)-1]. After 16 collisions it is abandoned.
    """
    rng = random.Random(seed)
    timers = [0] * n_stations          # slots to wait before next attempt
    collisions = [0] * n_stations
    pending = set(range(n_stations))
    abandoned = 0
    succeeded = 0
    total_slots = 0
    total_collisions = 0

    while pending:
        total_slots += 1
        ready = [s for s in pending if timers[s] == 0]
        if len(ready) == 1:
            succeeded += 1
            pending.discard(ready[0])
        elif len(ready) >= 2:
            total_collisions += 1
            for s in ready:
                collisions[s] += 1
                if collisions[s] >= MAX_COLLISIONS:
                    pending.discard(s)
                    abandoned += 1
                else:
                    timers[s] = rng.randint(0, backoff_window(collisions[s]) - 1)
        # Decrement all waiting timers for the next slot.
        for s in pending:
            if timers[s] > 0:
                timers[s] -= 1

    return SimResult(
        stations=n_stations,
        succeeded=succeeded,
        abandoned=abandoned,
        total_slots=total_slots,
        total_collisions=total_collisions,
    )


def main() -> None:
    print("=" * 68)
    print("CLASSIC ETHERNET FRAME PARSER")
    print("=" * 68)
    print(f"Slot time: {SLOT_TIME_BITS} bit-times = {SLOT_TIME_US:.1f} us")
    print(f"Minimum frame (Dest..CRC): {MIN_FRAME_BYTES} bytes\n")

    # Build a real IPv4-over-Ethernet frame, then parse it back.
    dest = bytes.fromhex("ffffffffffff")          # broadcast
    src = bytes.fromhex("0800270a1b2c")           # VirtualBox OUI 08:00:27
    frame_hex = build_frame(dest, src, 0x0800, b"hello ethernet")
    fp = parse_frame(frame_hex)

    print(f"Destination : {fmt_mac(fp.dest)}  -> {classify_dest(fp.dest)}")
    oui = fmt_mac(fp.src)[:8].upper()
    print(f"Source      : {fmt_mac(fp.src)}  -> OUI {oui} "
          f"({KNOWN_OUIS.get(oui, 'unknown vendor')})")
    print(f"Type/Length : 0x{fp.type_length:04X}  -> {interpret_type_length(fp.type_length)}")
    print(f"Payload     : {fp.payload!r}")
    print(f"Pad bytes   : {len(fp.pad)} (frame padded to {fp.framed_len} bytes)")
    print(f"CRC-32      : in-frame=0x{fp.crc_in_frame:08X} "
          f"computed=0x{fp.crc_computed:08X}  -> {'OK' if fp.crc_ok else 'FAIL'}")
    print(f"Runt?       : {fp.is_runt}\n")

    # Show the Type-vs-Length rule on a boundary value.
    print("Type-vs-Length rule (threshold 0x600 = 1536):")
    for v in (0x002E, 0x0600, 0x0800, 0x86DD):
        print(f"  0x{v:04X} -> {interpret_type_length(v)}")

    print("\n" + "=" * 68)
    print("BINARY EXPONENTIAL BACKOFF WINDOWS")
    print("=" * 68)
    for k in (1, 2, 3, 4, 10, 11):
        w = backoff_window(k)
        print(f"  after collision {k:2d}: draw from [0, {w - 1}] ({w} slots)")
    print(f"  after collision {MAX_COLLISIONS}: give up, report to higher layers")

    print("\n" + "=" * 68)
    print("CSMA/CD CONTENTION SIMULATION")
    print("=" * 68)
    print(f"{'stations':>9} | {'success':>7} | {'collisions':>10} | "
          f"{'slots':>6} | {'efficiency':>10}")
    print("-" * 68)
    for n in (2, 5, 10, 25, 50):
        r = simulate_csma_cd(n)
        print(f"{r.stations:>9} | {r.succeeded:>7} | {r.total_collisions:>10} | "
              f"{r.total_slots:>6} | {r.efficiency:>9.2%}")
    print("\nNote: efficiency drifts toward the ~1/e ceiling as load climbs,")
    print("because contention slots (2tau each) eat into the channel.")


if __name__ == "__main__":
    main()
