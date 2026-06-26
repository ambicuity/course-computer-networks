"""802.11 fragmentation bursts, beacons, and power-save simulation.

This module is a stdlib-only Python toolkit that mirrors the lesson
"802.11 fragmentation bursts, ACKs, and power-save via beacon TIMs".

It demonstrates:
  * splitting an MSDU into MPDU fragments of bounded size
  * assigning Sequence Control (12-bit Sequence Number + 4-bit Fragment
    Number) and More Fragments flag
  * computing the Duration/NAV value for each fragment so the burst
    keeps the channel through the next SIFS-ACK-SIFS exchange
  * building a 802.11 beacon frame with a TIM element whose partial
    virtual bitmap is keyed by Association ID (AID)
  * simulating the legacy PS-Poll handshake
  * simulating the 802.11e U-APSD (WMM Power Save) trigger/delivery
    exchange

No external libraries, no network calls. Run with ``python3 main.py``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Tuple

# --- 802.11 timing constants (OFDM 2.4 GHz reference values) -----------
SIFS_US: int = 10          # Short InterFrame Spacing
DIFS_US: int = 34          # DCF InterFrame Spacing
SLOT_US: int = 9           # Slot time
PREAMBLE_PLUS_PLCP_US: int = 20  # OFDM preamble + SIGNAL field
ACK_US: int = 24           # 14-byte ACK + 20 us preamble at 24 Mbps ~= 24 us
DATA_RATE_MBPS: int = 54   # OFDM data rate
ACK_RATE_MBPS: int = 24    # OFDM ACK rate
BEACON_INTERVAL_TU: int = 100  # 100 TU * 1024 us = 102.4 ms (typical)
TU_US: int = 1024

# --- Frame Control bit flags (only the ones the lesson uses) ----------
FC_TYPE_DATA: int = 0x08
FC_TYPE_CTRL: int = 0x04
FC_TYPE_MGMT: int = 0x00
FC_SUBTYPE_BEACON: int = 0x80
FC_SUBTYPE_ACK: int = 0xD0
FC_SUBTYPE_PSPOLL: int = 0xA4
FC_SUBTYPE_QOS_DATA: int = 0x28
FC_SUBTYPE_QOS_NULL: int = 0xC4
FC_TO_DS: int = 0x01
FC_FROM_DS: int = 0x02
FC_MORE_FRAG: int = 0x04
FC_RETRY: int = 0x08
FC_PWR_MGMT: int = 0x10
FC_MORE_DATA: int = 0x20
FC_PROTECTED: int = 0x40
FC_ORDER: int = 0x80


# --- Fragmenter --------------------------------------------------------

@dataclass(frozen=True)
class Fragment:
    """A single MPDU fragment of an MSDU burst.

    ``seq_num`` is the 12-bit Sequence Number shared by all fragments of
    the same MSDU. ``frag_num`` is the 4-bit Fragment Number, which
    increments 0, 1, 2... for each fragment of the burst.
    """

    seq_num: int
    frag_num: int
    more_frags: bool
    body: bytes
    duration_us: int
    retry: bool = False

    def header(self) -> bytes:
        """Pack the 2-byte Sequence Control field for this fragment."""
        # 4 bits Fragment Number (low), 12 bits Sequence Number (high)
        seq_ctrl = ((self.seq_num & 0x0FFF) << 4) | (self.frag_num & 0x000F)
        return struct.pack("<H", seq_ctrl)


def airtime_us(body_len: int, mbps: int) -> int:
    """Return the on-air time of a frame with ``body_len`` bytes at ``mbps``."""
    return PREAMBLE_PLUS_PLCP_US + (body_len * 8 * 1_000_000) // (mbps * 1_000_000)


def duration_value_for_fragment(
    frag_num: int, total_frags: int, data_bytes: int
) -> int:
    """Compute the Duration/NAV value a fragment must advertise.

    For the last fragment the Duration is 0; for every earlier fragment
    it must cover SIFS + ACK + SIFS + next-fragment airtime.
    """
    if frag_num == total_frags - 1:
        return 0
    next_frag = data_bytes  # assume uniform fragment size
    return SIFS_US + ACK_US + SIFS_US + airtime_us(next_frag, DATA_RATE_MBPS)


def fragment_msdu(
    payload: bytes,
    threshold: int,
    seq_num: int,
    *,
    retry: bool = False,
) -> List[Fragment]:
    """Split ``payload`` into MPDU fragments of at most ``threshold`` bytes."""
    if threshold < 256 or threshold > 2346:
        raise ValueError("threshold must be in [256, 2346]")

    bodies: List[bytes] = []
    for off in range(0, len(payload), threshold):
        bodies.append(payload[off:off + threshold])
    total = len(bodies)

    frags: List[Fragment] = []
    for idx, body in enumerate(bodies):
        more_frags = idx < total - 1
        dur = duration_value_for_fragment(idx, total, len(body))
        frags.append(
            Fragment(
                seq_num=seq_num,
                frag_num=idx,
                more_frags=more_frags,
                body=body,
                duration_us=dur,
                retry=retry,
            )
        )
    return frags


def print_burst_timeline(fragments: List[Fragment]) -> None:
    """Pretty-print the SIFS-separated DATA-ACK burst pattern."""
    print("Fragment burst (DATA - SIFS - ACK - SIFS - DATA - SIFS - ACK ...):")
    for i, f in enumerate(fragments):
        tag = "DATA" + str(f.frag_num + 1)
        tail = ""
        if i < len(fragments) - 1:
            tail = "  SIFS(10us)  ->  ACK  ->  SIFS(10us)  ->  "
        print(f"  {tag:8s} seq=0x{f.seq_num:03X} frag={f.frag_num} "
              f"more_frags={int(f.more_frags)} dur={f.duration_us}us "
              f"body={len(f.body)}B retry={int(f.retry)}")
        if tail:
            print(tail, end="")
    print("  <burst ends, channel released>\n")


# --- Beacon and TIM builder --------------------------------------------

@dataclass
class TimElement:
    """The Traffic Indication Map information element (Element ID = 5)."""

    dtim_count: int
    dtim_period: int
    bitmap_offset: int
    partial_virtual_bitmap: bytes  # packed LSB-first, 2007 bits max

    def to_bytes(self) -> bytes:
        bmp_ctl = (self.bitmap_offset & 0x1FF) << 0  # low 7 bits unused/0
        payload = bytes([self.dtim_count, self.dtim_period, bmp_ctl]) + self.partial_virtual_bitmap
        return bytes([0x05, len(payload)]) + payload


def build_partial_virtual_bitmap(aids: List[int]) -> Tuple[bytes, int]:
    """Pack ``aids`` (1..2007) into a 2007-bit partial virtual bitmap.

    The bitmap is LSB-first. Bit 0 of byte 0 is the AID-0 indicator
    (broadcast/multicast buffered traffic); bit n of byte n//8 is the
    indicator for AID n.

    Returns (bitmap_bytes, smallest_offset_aligned_to_byte).
    """
    if any(a < 0 or a > 2007 for a in aids):
        raise ValueError("AIDs must be in 1..2007")
    bmp = bytearray(252)  # 2008 bits -> 251 bytes; round up to 252
    for aid in aids:
        bmp[aid // 8] |= 1 << (aid % 8)
    # find smallest byte offset covering all set bits
    if aids:
        min_aid = min(aids)
        offset = min_aid // 8
    else:
        offset = 0
    return bytes(bmp[offset:]), offset


def build_beacon(
    *,
    timestamp: int,
    beacon_interval_tu: int,
    ssid: str,
    dtim_count: int,
    dtim_period: int,
    aids_with_buffered_traffic: List[int],
    bssid: bytes = b"\x00\x11\x22\x33\x44\x55",
) -> bytes:
    """Build a 802.11 beacon frame as a byte string.

    The MAC header is 24 bytes (Frame Control 2, Duration 2, three
    Address fields 6 each, Sequence Control 2). The body is the fixed
    fields (timestamp 8, interval 2, capability 2) followed by
    Information Elements (SSID, Supported Rates, TIM).
    """
    # --- MAC header ---
    fc = FC_TYPE_MGMT | FC_SUBTYPE_BEACON
    duration = 0
    addr1 = b"\xff\xff\xff\xff\xff\xff"  # broadcast DA
    addr2 = bssid  # SA
    addr3 = bssid  # BSSID
    seq_ctrl = 0
    mac_hdr = struct.pack("<HH", fc, duration) + addr1 + addr2 + addr3 + struct.pack("<H", seq_ctrl)
    assert len(mac_hdr) == 24

    # --- Beacon body: fixed fields ---
    capability = 0x0421  # ESS, short preamble, QoS
    body = struct.pack("<Q", timestamp)  # 8-byte timestamp
    body += struct.pack("<H", beacon_interval_tu)
    body += struct.pack("<H", capability)

    # --- SSID IE ---
    ssid_bytes = ssid.encode("utf-8")
    body += bytes([0x00, len(ssid_bytes)]) + ssid_bytes

    # --- Supported Rates IE (1, 2, 5.5, 11, 6, 9, 12, 18 Mbps) ---
    rates = bytes([0x82, 0x84, 0x8B, 0x96, 0x0C, 0x12, 0x18, 0x24])
    body += bytes([0x01, len(rates)]) + rates

    # --- TIM IE ---
    bmp, offset = build_partial_virtual_bitmap(aids_with_buffered_traffic)
    tim = TimElement(
        dtim_count=dtim_count,
        dtim_period=dtim_period,
        bitmap_offset=offset,
        partial_virtual_bitmap=bmp,
    )
    body += tim.to_bytes()

    return mac_hdr + body


def decode_tim(beacon: bytes) -> Tuple[int, int, List[int]]:
    """Walk a beacon's body and return (DTIM Count, DTIM Period, [AIDs])."""
    # skip 24-byte MAC header, skip 8-byte timestamp, 2-byte interval, 2-byte capability
    off = 24 + 8 + 2 + 2
    while off < len(beacon):
        eid, elen = beacon[off], beacon[off + 1]
        off += 2
        payload = beacon[off:off + elen]
        off += elen
        if eid == 0x05 and elen >= 3:  # TIM
            dtim_count, dtim_period, bmp_ctl = payload[0], payload[1], payload[2]
            bmp_offset = bmp_ctl & 0x1FF
            bmp_bytes = payload[3:]
            aids: List[int] = []
            for byte_off, b in enumerate(bmp_bytes):
                base = (bmp_offset + byte_off) * 8
                for bit in range(8):
                    if b & (1 << bit):
                        aids.append(base + bit)
            return dtim_count, dtim_period, aids
    raise ValueError("TIM element not found")


# --- PS-Poll and U-APSD simulators -------------------------------------

@dataclass
class BufferedFrame:
    """One downlink frame the AP is holding for a power-save station."""

    aid: int
    payload: bytes
    more_data: bool = False


@dataclass
class PowerSaveStation:
    """A station that uses the legacy PS-Poll power-save mechanism."""

    aid: int
    queue: List[BufferedFrame] = field(default_factory=list)
    dozing: bool = True

    def wake_for_beacon(self, beacon: bytes) -> bool:
        """Read the TIM and decide whether to send a PS-Poll."""
        _, _, aids = decode_tim(beacon)
        if self.aid in aids:
            self.dozing = False
            return True
        return False

    def poll(self) -> BufferedFrame | None:
        """Simulate the AP sending the head of the queue after SIFS."""
        if not self.queue:
            return None
        return self.queue.pop(0)


def simulate_ps_poll(station: PowerSaveStation, beacon: bytes) -> int:
    """Walk the legacy PS-Poll handshake until the station can doze."""
    print(f"  Station AID={station.aid} dozing={station.dozing}")
    polls_sent = 0
    while station.wake_for_beacon(beacon):
        polls_sent += 1
        print(f"    <- BEACON: AID={station.aid} bit set; waking")
        print(f"    -> PS-POLL (subtype 0xA4, AID={station.aid})")
        frame = station.poll()
        if frame is None:
            print("    <- NULL DATA (queue empty)")
            break
        print(f"    <- DATA ({len(frame.payload)}B) more_data={int(frame.more_data)}")
        print(f"    -> ACK")
        if not frame.more_data:
            break
    station.dozing = True
    print(f"  Station AID={station.aid} returns to doze after {polls_sent} poll(s)\n")
    return polls_sent


def simulate_uapsd(
    station: PowerSaveStation,
    downstream_frames: List[BufferedFrame],
) -> int:
    """Walk the 802.11e U-APSD trigger/delivery exchange."""
    print(f"  Station AID={station.aid} dozing, U-APSD enabled")
    print(f"    -> TRIGGER (QoS Data, subtype 0x28, EOSP=0)")
    delivered = 0
    for f in downstream_frames:
        print(f"    <- DATA ({len(f.payload)}B) more_data={int(f.more_data)}")
        delivered += 1
    print(f"    -> QoS NULL (subtype 0xC4, EOSP=1)  <-- end of service period")
    station.dozing = True
    print(f"  Station AID={station.aid} returns to doze, {delivered} frame(s) delivered\n")
    return delivered


# --- Demo main ---------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("802.11 fragmentation bursts, ACKs, and power-save via beacon TIMs")
    print("=" * 72 + "\n")

    # 1. Fragment a 1500-byte MSDU into 3 MPDUs at 500-byte threshold
    msdu = bytes((i * 37) & 0xFF for i in range(1500))  # deterministic payload
    fragments = fragment_msdu(msdu, threshold=500, seq_num=0x4A2)
    print(f"[1] Fragmenting a {len(msdu)}-byte MSDU into {len(fragments)} MPDUs "
          f"(seq_num=0x{fragments[0].seq_num:03X}, threshold=500)\n")
    print_burst_timeline(fragments)

    # 2. Build a beacon for 8 stations, AIDs 2/5/7 have buffered traffic
    aids = [2, 5, 7]
    beacon = build_beacon(
        timestamp=0x000123456789ABCD,
        beacon_interval_tu=BEACON_INTERVAL_TU,
        ssid="ECC-Demo",
        dtim_count=2,
        dtim_period=3,
        aids_with_buffered_traffic=aids,
    )
    print(f"[2] Beacon ({len(beacon)} bytes) hex:")
    hex_lines = [beacon[i:i + 32] for i in range(0, len(beacon), 32)]
    for line in hex_lines:
        print("    " + " ".join(f"{b:02X}" for b in line))
    print()

    dtim_count, dtim_period, decoded_aids = decode_tim(beacon)
    print(f"    Decoded TIM: dtim_count={dtim_count} dtim_period={dtim_period} "
          f"aids_with_buffered={decoded_aids}\n")

    # 3. Legacy PS-Poll handshake for station AID 5
    print("[3] Legacy PS-Poll handshake (one frame per poll):\n")
    station = PowerSaveStation(aid=5, queue=[
        BufferedFrame(aid=5, payload=b"\xDE\xAD\xBE\xEF", more_data=True),
        BufferedFrame(aid=5, payload=b"\xCA\xFE\xBA\xBE", more_data=False),
    ])
    simulate_ps_poll(station, beacon)

    # 4. U-APSD (WMM Power Save) for station AID 5
    print("[4] U-APSD trigger/delivery exchange (one trigger, burst of frames):\n")
    downstream = [
        BufferedFrame(aid=5, payload=b"\xA0\x01", more_data=True),
        BufferedFrame(aid=5, payload=b"\xA0\x02", more_data=False),
    ]
    simulate_uapsd(station, downstream)


if __name__ == "__main__":
    main()
