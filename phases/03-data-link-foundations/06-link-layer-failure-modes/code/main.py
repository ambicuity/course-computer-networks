#!/usr/bin/env python3
"""Link-layer failure-mode classifier for IEEE 802.3 Ethernet frames.

Pure-stdlib. No network calls. Given the raw bytes of an Ethernet frame
(including the 4-byte FCS), this program does exactly what receiver
hardware does and what a network engineer reasons about:

  1. Recompute the CRC-32 FCS and compare it to the trailing 4 bytes.
  2. Classify the frame by on-wire length: runt (<64), good (64-1518/1522
     tagged), giant (>1518/1522), or jabber (giant AND FCS-bad).
  3. Parse the header fields (MACs, EtherType/length, VLAN tag).
  4. Detect MAC flapping from a stream of (mac, port, time) observations,
     the signature of an L2 loop / broadcast-storm condition.

Run:  python3 main.py
"""
from __future__ import annotations

import binascii
from dataclasses import dataclass
from typing import Optional

# --- Ethernet constants (IEEE 802.3 / 802.1Q) -----------------------------
MIN_FRAME_LEN = 64           # DST6 + SRC6 + TYPE2 + PAYLOAD46 + FCS4
MAX_FRAME_LEN_UNTAGGED = 1518
MAX_FRAME_LEN_TAGGED = 1522  # +4 for one 802.1Q tag
FCS_LEN = 4
VLAN_TPID = 0x8100           # 802.1Q tag protocol identifier
ETHERTYPE_MIN = 0x0600       # >= 1536 means "type", <= 1500 means "length"

ETHERTYPES = {
    0x0800: "IPv4",
    0x0806: "ARP",
    0x86DD: "IPv6",
    0x8100: "802.1Q VLAN",
    0x8847: "MPLS",
}


@dataclass(frozen=True)
class FrameVerdict:
    """Result of classifying one frame."""
    on_wire_len: int
    fcs_ok: bool
    computed_fcs: int
    trailer_fcs: int
    klass: str            # good | runt | giant | jabber
    dst_mac: str
    src_mac: str
    ethertype: int
    ethertype_name: str
    is_broadcast: bool
    is_tagged: bool
    vlan_id: Optional[int]


def mac_to_str(raw: bytes) -> str:
    """Format six bytes as a colon-separated MAC address."""
    return ":".join(f"{b:02x}" for b in raw)


def compute_fcs(frame_without_fcs: bytes) -> int:
    """Return the 32-bit Ethernet FCS (CRC-32, poly 0x04C11DB7).

    binascii.crc32 implements the exact reflected CRC-32 used by 802.3,
    so this matches what a NIC computes over DST..payload.
    """
    return binascii.crc32(frame_without_fcs) & 0xFFFFFFFF


def classify_length(on_wire_len: int, tagged: bool, fcs_ok: bool) -> str:
    """Bucket a frame by its on-wire length and FCS validity."""
    max_len = MAX_FRAME_LEN_TAGGED if tagged else MAX_FRAME_LEN_UNTAGGED
    if on_wire_len < MIN_FRAME_LEN:
        return "runt"
    if on_wire_len > max_len:
        # A giant that is ALSO corrupt is the jabber fingerprint:
        # a stuck transmitter floods oversized, CRC-bad garbage.
        return "jabber" if not fcs_ok else "giant"
    return "good"


def parse_frame(frame: bytes) -> FrameVerdict:
    """Parse and classify a complete Ethernet frame (header..FCS)."""
    if len(frame) < 14 + FCS_LEN:
        raise ValueError(
            f"frame too short to parse: {len(frame)} bytes "
            "(need >= 14 header + 4 FCS)"
        )

    on_wire_len = len(frame)
    body, trailer = frame[:-FCS_LEN], frame[-FCS_LEN:]
    trailer_fcs = int.from_bytes(trailer, "big")
    computed_fcs = compute_fcs(body)
    # For this teaching parser we treat a match on the recomputed CRC as
    # "FCS OK" -- the same comparison the receiver MAC performs.
    fcs_ok = computed_fcs == trailer_fcs

    dst = body[0:6]
    src = body[6:12]
    is_broadcast = dst == b"\xff\xff\xff\xff\xff\xff"

    # Detect an 802.1Q tag and resolve the real EtherType behind it.
    tpid = int.from_bytes(body[12:14], "big")
    is_tagged = tpid == VLAN_TPID
    if is_tagged:
        tci = int.from_bytes(body[14:16], "big")
        vlan_id = tci & 0x0FFF
        ethertype = int.from_bytes(body[16:18], "big")
    else:
        vlan_id = None
        ethertype = tpid

    klass = classify_length(on_wire_len, is_tagged, fcs_ok)

    name = ETHERTYPES.get(ethertype)
    if name is None:
        name = "type" if ethertype >= ETHERTYPE_MIN else "length"

    return FrameVerdict(
        on_wire_len=on_wire_len,
        fcs_ok=fcs_ok,
        computed_fcs=computed_fcs,
        trailer_fcs=trailer_fcs,
        klass=klass,
        dst_mac=mac_to_str(dst),
        src_mac=mac_to_str(src),
        ethertype=ethertype,
        ethertype_name=name,
        is_broadcast=is_broadcast,
        is_tagged=is_tagged,
        vlan_id=vlan_id,
    )


# --- Collision reasoning (CSMA/CD slot time) ------------------------------
SLOT_TIME_BYTES = 64  # 512 bit-times at 10/100 Mb/s


def is_late_collision(bytes_sent_before_collision: int, duplex: str) -> bool:
    """Return True if a collision at this offset/duplex is a real fault.

    A collision after the 512-bit (64-byte) slot time is a LATE collision
    and is never normal. ANY collision on full duplex is also a fault.
    """
    if duplex == "full":
        return True  # full duplex must never collide
    return bytes_sent_before_collision > SLOT_TIME_BYTES


# --- MAC flap / L2 loop detector ------------------------------------------
def detect_mac_flaps(
    observations: list[tuple[str, str, float]],
    window_s: float = 5.0,
    threshold: int = 2,
) -> list[str]:
    """Flag MACs that change port more than `threshold` times in `window_s`.

    This mirrors a switch's MAC-flap alarm: the same source MAC bouncing
    between ports is the signature of a forwarding loop / broadcast storm.
    `observations` is a list of (mac, port, time_seconds), time-ordered.
    """
    moves: dict[str, list[tuple[float, str]]] = {}
    for mac, port, t in observations:
        history = moves.setdefault(mac, [])
        if not history or history[-1][1] != port:
            history.append((t, port))

    flapping: list[str] = []
    for mac, history in moves.items():
        recent = [h for h in history if history[-1][0] - h[0] <= window_s]
        if len(recent) - 1 >= threshold:  # number of PORT CHANGES
            flapping.append(mac)
    return flapping


def build_frame(dst: bytes, src: bytes, ethertype: int,
                payload: bytes) -> bytes:
    """Build a valid frame WITH a correct FCS, padding payload to 46 bytes."""
    if len(payload) < 46:
        payload = payload + b"\x00" * (46 - len(payload))
    body = dst + src + ethertype.to_bytes(2, "big") + payload
    fcs = compute_fcs(body).to_bytes(4, "big")
    return body + fcs


def _print_verdict(label: str, v: FrameVerdict) -> None:
    fcs = "FCS OK " if v.fcs_ok else "FCS BAD"
    tag = f" vlan={v.vlan_id}" if v.is_tagged else ""
    print(
        f"  {label:<14} len={v.on_wire_len:<5} {v.klass.upper():<7} {fcs} "
        f"{v.src_mac} -> {v.dst_mac} [{v.ethertype_name}]{tag}"
    )


def main() -> None:
    print("=== 802.3 frame classification ===")
    dst = bytes.fromhex("ffffffffffff")          # broadcast
    src = bytes.fromhex("aabbcc001122")

    good = build_frame(dst, src, 0x0800, b"hello payload")
    _print_verdict("good", parse_frame(good))

    # Corrupt one payload byte: receiver-side CRC must now fail.
    corrupt = bytearray(good)
    corrupt[20] ^= 0xFF
    _print_verdict("corrupted", parse_frame(bytes(corrupt)))

    # Runt: chop the frame below 64 bytes on the wire.
    runt = good[:40]
    _print_verdict("runt", parse_frame(runt))

    # Giant: oversized payload, but with a VALID FCS -> giant, not jabber.
    giant = build_frame(dst, src, 0x0800, b"J" * 1600)
    _print_verdict("giant", parse_frame(giant))

    # Jabber: oversized AND corrupt -> stuck-transmitter signature.
    jab = bytearray(giant)
    jab[100] ^= 0xFF
    _print_verdict("jabber", parse_frame(bytes(jab)))

    print("\n=== CSMA/CD collision check (slot time = 64 bytes) ===")
    for sent, duplex in [(30, "half"), (200, "half"), (30, "full")]:
        bad = is_late_collision(sent, duplex)
        verdict = "FAULT (late/illegal)" if bad else "normal"
        print(f"  sent={sent:<4} duplex={duplex:<4} -> {verdict}")

    print("\n=== MAC flap / L2 loop detector ===")
    obs = [
        ("aabbcc001122", "Gi1/0/1", 0.0),
        ("aabbcc001122", "Gi1/0/2", 1.2),
        ("aabbcc001122", "Gi1/0/1", 2.5),
        ("aabbcc001122", "Gi1/0/2", 3.9),
        ("00de00ad00be", "Gi1/0/9", 0.0),  # stable host, never flaps
    ]
    flaps = detect_mac_flaps(obs, window_s=5.0, threshold=2)
    if flaps:
        for mac in flaps:
            print(f"  ALARM: {mac} flapping across ports -> suspect L2 loop")
    else:
        print("  no flaps detected")


if __name__ == "__main__":
    main()
