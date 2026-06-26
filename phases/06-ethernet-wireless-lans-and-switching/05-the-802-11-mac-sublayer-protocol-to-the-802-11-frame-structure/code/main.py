#!/usr/bin/env python3
"""802.11 MAC sublayer: data-frame builder/parser + DCF backoff model.

Stdlib-only, no network access. Demonstrates three things from the lesson:

1. build_data_frame() / parse_data_frame() — pack and decode the exact
   802.11 data-frame layout (Frame Control, Duration, three addresses,
   Sequence Control, payload, CRC-32 FCS) and verify integrity.
2. address_roles() — decode how the To DS / From DS bit pair remaps
   Address 1/2/3 into receiver/transmitter/DA/SA/BSSID.
3. simulate_backoff() — model Distributed Coordination Function (DCF)
   binary exponential backoff with the contention window doubling
   CWmin=15 -> ... -> CWmax=1023.

Run:  python3 main.py
"""

from __future__ import annotations

import binascii
import random
import struct
from dataclasses import dataclass

# --- DCF / PHY constants (OFDM PHY values from the lesson) ---------------
CW_MIN = 15
CW_MAX = 1023
RETRY_LIMIT = 7

# Frame Control Type values
TYPE_MGMT = 0b00
TYPE_CONTROL = 0b01
TYPE_DATA = 0b10


@dataclass
class FrameControl:
    """The 16-bit Frame Control word, split into its 11 subfields."""

    protocol_version: int = 0b00
    type_: int = TYPE_DATA
    subtype: int = 0b0000
    to_ds: int = 0
    from_ds: int = 0
    more_fragments: int = 0
    retry: int = 0
    power_mgmt: int = 0
    more_data: int = 0
    protected: int = 0
    order: int = 0

    def pack(self) -> int:
        """Assemble the subfields into one 16-bit little-endian-on-air word."""
        value = 0
        value |= (self.protocol_version & 0b11) << 0
        value |= (self.type_ & 0b11) << 2
        value |= (self.subtype & 0b1111) << 4
        value |= (self.to_ds & 1) << 8
        value |= (self.from_ds & 1) << 9
        value |= (self.more_fragments & 1) << 10
        value |= (self.retry & 1) << 11
        value |= (self.power_mgmt & 1) << 12
        value |= (self.more_data & 1) << 13
        value |= (self.protected & 1) << 14
        value |= (self.order & 1) << 15
        return value

    @classmethod
    def unpack(cls, value: int) -> "FrameControl":
        return cls(
            protocol_version=(value >> 0) & 0b11,
            type_=(value >> 2) & 0b11,
            subtype=(value >> 4) & 0b1111,
            to_ds=(value >> 8) & 1,
            from_ds=(value >> 9) & 1,
            more_fragments=(value >> 10) & 1,
            retry=(value >> 11) & 1,
            power_mgmt=(value >> 12) & 1,
            more_data=(value >> 13) & 1,
            protected=(value >> 14) & 1,
            order=(value >> 15) & 1,
        )


def mac_to_bytes(mac: str) -> bytes:
    """'aa:bb:cc:dd:ee:ff' -> 6 raw bytes."""
    return bytes(int(octet, 16) for octet in mac.split(":"))


def bytes_to_mac(raw: bytes) -> str:
    return ":".join(f"{byte:02x}" for byte in raw)


def seq_control(sequence_number: int, fragment_number: int) -> int:
    """16-bit Sequence Control = 12-bit seq num (high) + 4-bit frag (low)."""
    return ((sequence_number & 0xFFF) << 4) | (fragment_number & 0xF)


def build_data_frame(
    fc: FrameControl,
    duration_us: int,
    addr1: str,
    addr2: str,
    addr3: str,
    sequence_number: int,
    fragment_number: int,
    payload: bytes,
) -> bytes:
    """Build a 3-address 802.11 data frame with a real CRC-32 FCS."""
    if len(payload) > 2312:
        raise ValueError("802.11 data payload is limited to 2312 bytes")
    header = struct.pack("<H", fc.pack())
    header += struct.pack("<H", duration_us)
    header += mac_to_bytes(addr1)
    header += mac_to_bytes(addr2)
    header += mac_to_bytes(addr3)
    header += struct.pack("<H", seq_control(sequence_number, fragment_number))
    body = header + payload
    fcs = binascii.crc32(body) & 0xFFFFFFFF
    return body + struct.pack("<I", fcs)


def parse_data_frame(frame: bytes) -> dict:
    """Decode a 3-address data frame and verify the trailing FCS."""
    if len(frame) < 24 + 4:
        raise ValueError("frame too short for a 3-address data frame")
    body, fcs_bytes = frame[:-4], frame[-4:]
    (fc_raw,) = struct.unpack("<H", body[0:2])
    (duration,) = struct.unpack("<H", body[2:4])
    addr1 = bytes_to_mac(body[4:10])
    addr2 = bytes_to_mac(body[10:16])
    addr3 = bytes_to_mac(body[16:22])
    (seq_raw,) = struct.unpack("<H", body[22:24])
    payload = body[24:]
    fc = FrameControl.unpack(fc_raw)
    (claimed_fcs,) = struct.unpack("<I", fcs_bytes)
    computed_fcs = binascii.crc32(body) & 0xFFFFFFFF
    return {
        "frame_control": fc,
        "duration_us": duration,
        "address1": addr1,
        "address2": addr2,
        "address3": addr3,
        "sequence_number": seq_raw >> 4,
        "fragment_number": seq_raw & 0xF,
        "payload": payload,
        "fcs_ok": claimed_fcs == computed_fcs,
    }


def address_roles(to_ds: int, from_ds: int) -> tuple[str, str, str]:
    """Map the To DS / From DS pair to Address 1/2/3 roles."""
    table = {
        (0, 0): ("DA (dest)", "SA (source)", "BSSID"),       # IBSS / ad-hoc
        (0, 1): ("DA (dest)", "BSSID", "SA (source)"),       # AP -> client
        (1, 0): ("BSSID", "SA (source)", "DA (dest)"),       # client -> AP
        (1, 1): ("RA (receiver)", "TA (transmitter)", "DA"),  # WDS bridge
    }
    return table[(to_ds, from_ds)]


def simulate_backoff(
    loss_probability: float, seed: int = 42
) -> list[tuple[int, int, int, bool]]:
    """Model DCF binary exponential backoff until success or retry limit.

    Returns a list of (attempt, contention_window, slots_drawn, delivered).
    """
    rng = random.Random(seed)
    cw = CW_MIN
    history: list[tuple[int, int, int, bool]] = []
    for attempt in range(1, RETRY_LIMIT + 1):
        slots = rng.randint(0, cw)
        delivered = rng.random() >= loss_probability
        history.append((attempt, cw, slots, delivered))
        if delivered:
            break
        cw = min((cw + 1) * 2 - 1, CW_MAX)  # 15 -> 31 -> 63 -> ... -> 1023
    return history


def fragment_success(p_bit_error: float, frame_bits: int) -> float:
    """Probability an n-bit frame is received with zero bit errors."""
    return (1.0 - p_bit_error) ** frame_bits


def main() -> None:
    print("=" * 64)
    print("802.11 DATA FRAME: build, dump, parse, verify")
    print("=" * 64)
    fc = FrameControl(type_=TYPE_DATA, subtype=0b0000, to_ds=0, from_ds=1, retry=0)
    frame = build_data_frame(
        fc=fc,
        duration_us=213,  # microseconds reserved for this frame + its ACK
        addr1="00:11:22:33:44:55",  # receiver (laptop)
        addr2="66:77:88:99:aa:bb",  # transmitter (AP / BSSID)
        addr3="cc:dd:ee:00:11:22",  # distant source endpoint
        sequence_number=1037,
        fragment_number=0,
        payload=b"\xaa\xaa\x03\x00\x00\x00\x08\x00HELLO-802.11",  # LLC/SNAP + data
    )
    print(f"on-air bytes ({len(frame)}): {frame.hex()}")

    decoded = parse_data_frame(frame)
    dfc = decoded["frame_control"]
    print("\nDecoded Frame Control:")
    print(f"  version={dfc.protocol_version:02b}  type={dfc.type_:02b}  "
          f"subtype={dfc.subtype:04b}")
    print(f"  ToDS={dfc.to_ds} FromDS={dfc.from_ds} retry={dfc.retry} "
          f"protected={dfc.protected} order={dfc.order}")
    print(f"Duration : {decoded['duration_us']} us (seeds neighbor NAV)")
    print(f"Address1 : {decoded['address1']}  (receiver)")
    print(f"Address2 : {decoded['address2']}  (transmitter / BSSID)")
    print(f"Address3 : {decoded['address3']}  (distant source)")
    print(f"Sequence : seq={decoded['sequence_number']} "
          f"frag={decoded['fragment_number']}")
    print(f"FCS check: {'PASS' if decoded['fcs_ok'] else 'FAIL'}")

    print("\n" + "=" * 64)
    print("To DS / From DS -> address roles")
    print("=" * 64)
    for to_ds, from_ds, label in [
        (0, 0, "ad-hoc / IBSS"),
        (0, 1, "AP -> client (downlink)"),
        (1, 0, "client -> AP (uplink)"),
        (1, 1, "WDS bridge (4 addr)"),
    ]:
        a1, a2, a3 = address_roles(to_ds, from_ds)
        print(f"  ToDS={to_ds} FromDS={from_ds} {label:24s} "
              f"A1={a1:12s} A2={a2:14s} A3={a3}")

    print("\n" + "=" * 64)
    print("DCF binary exponential backoff (loss_probability=0.6)")
    print("=" * 64)
    print("attempt  CW     slots_drawn  result")
    for attempt, cw, slots, delivered in simulate_backoff(0.6, seed=1):
        result = "DELIVERED" if delivered else "no ACK -> double CW"
        print(f"  {attempt:>5}  {cw:>5}  {slots:>11}  {result}")

    print("\n" + "=" * 64)
    print("Fragmentation: P(frame survives) at bit error rate p=1e-4")
    print("=" * 64)
    for bits, label in [(12144, "full Ethernet-size frame"), (4048, "1/3-size fragment")]:
        prob = fragment_success(1e-4, bits)
        print(f"  {label:26s} {bits:>6} bits -> {prob*100:5.1f}% delivered intact")


if __name__ == "__main__":
    main()
