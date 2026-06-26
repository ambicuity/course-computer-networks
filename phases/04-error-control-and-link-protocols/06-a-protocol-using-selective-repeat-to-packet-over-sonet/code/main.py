#!/usr/bin/env python3
"""Selective Repeat (Protocol 6) windowing + Packet over SONET (PPP) framing.

Two halves of one lesson, stdlib only, no network calls:

  1. Selective Repeat:
       - validate the window-size rule  window <= (MAX_SEQ+1)/2 = 2^(n-1)
       - simulate a receiver that buffers out-of-order frames in arrived[]
         and delivers to the network layer strictly in order.

  2. Packet over SONET (RFC 2615):
       - build a PPP unnumbered-mode frame (Flag/Address/Control/Protocol/
         Payload/CRC-32/Flag) with byte stuffing,
       - destuff to prove the round trip,
       - run the x^43+1 self-synchronous scrambler and measure how it raises
         the bit-transition density of an all-zeros payload.

Run:  python3 main.py
"""

from __future__ import annotations

from typing import Iterable

# --- PPP / HDLC constants (RFC 1662, RFC 2615) -----------------------------
FLAG = 0x7E            # frame delimiter 01111110
ESC = 0x7D             # byte-stuffing escape
ESC_XOR = 0x20         # byte that the escaped value is XORed with
ADDRESS = 0xFF         # "all stations"
CONTROL = 0x03         # unnumbered frame
PROTO_IPV4 = 0x0021    # PPP Protocol field for IPv4
PROTO_IPV6 = 0x0057    # PPP Protocol field for IPv6

CRC32_POLY = 0x04C11DB7  # same generator as IEEE 802.3; PoS uses the 4-byte FCS


# --- Selective Repeat: window-size rule ------------------------------------
def max_legal_window(seq_bits: int) -> int:
    """Largest legal SR window for an n-bit sequence number: 2^(n-1)."""
    max_seq = (1 << seq_bits) - 1
    return (max_seq + 1) // 2


def window_is_legal(seq_bits: int, window: int) -> bool:
    """A Selective Repeat window is legal only if it is <= half the space."""
    return 0 < window <= max_legal_window(seq_bits)


def between(a: int, b: int, c: int) -> bool:
    """Cyclic window test from Protocol 6: true when b is in [a, c)."""
    return ((a <= b) and (b < c)) or ((c < a) and (a <= b)) or ((b < c) and (c < a))


# --- Selective Repeat: receiver simulation ---------------------------------
class SelectiveRepeatReceiver:
    """Models the frame_arrival path of Tanenbaum's Protocol 6 receiver."""

    def __init__(self, seq_bits: int) -> None:
        self.max_seq = (1 << seq_bits) - 1
        self.nr_bufs = max_legal_window(seq_bits)
        self.frame_expected = 0           # lower edge of receiver window
        self.too_far = self.nr_bufs       # upper edge + 1
        self.arrived = [False] * self.nr_bufs
        self.buffer: dict[int, str] = {}
        self.delivered: list[str] = []    # what the network layer saw, in order

    def _inc(self, x: int) -> int:
        return (x + 1) % (self.max_seq + 1)

    def receive(self, seq: int, info: str) -> str:
        """Accept one data frame; return a short note about what happened."""
        slot = seq % self.nr_bufs
        if not between(self.frame_expected, seq, self.too_far):
            return f"seq {seq}: REJECTED (outside window [{self.frame_expected},{self.too_far}))"
        if self.arrived[slot]:
            return f"seq {seq}: DUPLICATE (already buffered)"
        self.arrived[slot] = True
        self.buffer[seq] = info
        note = f"seq {seq}: buffered"
        released = []
        while self.arrived[self.frame_expected % self.nr_bufs]:
            fe = self.frame_expected
            self.delivered.append(self.buffer.pop(fe))
            released.append(fe)
            self.arrived[fe % self.nr_bufs] = False
            self.frame_expected = self._inc(self.frame_expected)
            self.too_far = self._inc(self.too_far)
        if released:
            note += f" -> delivered {released}, window now [{self.frame_expected},{self.too_far})"
        return note


# --- PPP byte stuffing (RFC 1662) ------------------------------------------
def byte_stuff(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        if b == FLAG or b == ESC:
            out.append(ESC)
            out.append(b ^ ESC_XOR)
        else:
            out.append(b)
    return bytes(out)


def byte_destuff(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == ESC:
            i += 1
            out.append(data[i] ^ ESC_XOR)
        else:
            out.append(data[i])
        i += 1
    return bytes(out)


# --- CRC-32 (IEEE 802.3 / PPP 4-byte FCS) ----------------------------------
def crc32(data: bytes) -> int:
    """Bit-reflected CRC-32, the standard FCS used by PoS per RFC 2615."""
    crc = 0xFFFFFFFF
    reflected_poly = 0xEDB88320  # reflected form of CRC32_POLY 0x04C11DB7
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ reflected_poly if (crc & 1) else (crc >> 1)
    return crc ^ 0xFFFFFFFF


def build_ppp_frame(payload: bytes, protocol: int = PROTO_IPV4) -> bytes:
    """Assemble a PPP-over-SONET unnumbered frame around an IP payload."""
    header = bytes([ADDRESS, CONTROL]) + protocol.to_bytes(2, "big")
    body = header + payload
    fcs = crc32(body).to_bytes(4, "big")
    inner = byte_stuff(body + fcs)
    return bytes([FLAG]) + inner + bytes([FLAG])


# --- SONET payload scrambler (x^43 + 1, self-synchronous) ------------------
def scramble(data: bytes, seed: int = 0) -> bytes:
    """x^43+1 self-synchronous scrambler: out_bit = in_bit XOR register[43]."""
    register = seed & ((1 << 43) - 1)
    out = bytearray()
    for byte in data:
        scrambled = 0
        for bit_pos in range(7, -1, -1):
            in_bit = (byte >> bit_pos) & 1
            fb = (register >> 42) & 1            # tap at position 43
            out_bit = in_bit ^ fb
            register = ((register << 1) | out_bit) & ((1 << 43) - 1)
            scrambled = (scrambled << 1) | out_bit
        out.append(scrambled)
    return bytes(out)


def transition_density(data: bytes) -> float:
    """Fraction of adjacent bit pairs that differ (0->1 or 1->0)."""
    bits: list[int] = []
    for byte in data:
        for bit_pos in range(7, -1, -1):
            bits.append((byte >> bit_pos) & 1)
    if len(bits) < 2:
        return 0.0
    transitions = sum(1 for i in range(1, len(bits)) if bits[i] != bits[i - 1])
    return transitions / (len(bits) - 1)


def hexdump(data: Iterable[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


def main() -> None:
    print("=" * 64)
    print("1. SELECTIVE REPEAT: window-size rule  window <= 2^(n-1)")
    print("=" * 64)
    for seq_bits in (2, 3, 4):
        legal = max_legal_window(seq_bits)
        max_seq = (1 << seq_bits) - 1
        print(f"  {seq_bits}-bit seq (MAX_SEQ={max_seq}): max legal window = {legal}")
    bad = (3, 7)
    print(f"  Illegal example: {bad[0]}-bit seq with window {bad[1]} -> "
          f"legal? {window_is_legal(*bad)}  (a stale frame 0 would be accepted as new)")

    print("\n" + "=" * 64)
    print("2. SELECTIVE REPEAT receiver: out-of-order arrivals, one loss")
    print("=" * 64)
    rx = SelectiveRepeatReceiver(seq_bits=3)   # NR_BUFS = 4, window [0,4)
    # Frames 0,2,3 arrive (frame 1 is lost), then 1 is retransmitted.
    for seq, info in [(0, "P0"), (2, "P2"), (3, "P3"), (1, "P1")]:
        print("  " + rx.receive(seq, info))
    print(f"  network layer received, in order: {rx.delivered}")

    print("\n" + "=" * 64)
    print("3. PACKET OVER SONET: build a PPP frame (RFC 2615)")
    print("=" * 64)
    # A toy IP payload that deliberately contains a 0x7E and a 0x7D.
    ip_payload = bytes([0x45, 0x00, 0x7E, 0x11, 0x7D, 0x28])
    print(f"  raw IP payload : {hexdump(ip_payload)}")
    stuffed = byte_stuff(ip_payload)
    print(f"  byte-stuffed   : {hexdump(stuffed)}  (7E->7D 5E, 7D->7D 5D)")
    assert byte_destuff(stuffed) == ip_payload, "destuff round trip failed"
    print("  destuff round-trip: OK")

    frame = build_ppp_frame(ip_payload, PROTO_IPV4)
    print(f"  full PPP frame : {hexdump(frame)}")
    print("    Flag=7E  Address=FF  Control=03  Protocol=0021(IPv4)  ...CRC32... Flag=7E")
    body = bytes([ADDRESS, CONTROL]) + PROTO_IPV4.to_bytes(2, "big") + ip_payload
    print(f"    CRC-32 over header+payload = 0x{crc32(body):08X}")

    print("\n" + "=" * 64)
    print("4. SONET SCRAMBLING: why all-zeros must not reach the fiber raw")
    print("=" * 64)
    zeros = bytes(16)   # 128 bits of zero -> zero clock transitions
    scrambled = scramble(zeros, seed=0x5A5A5A5A5A5)
    print(f"  raw zeros transition density       : {transition_density(zeros):.3f}")
    print(f"  scrambled zeros transition density : {transition_density(scrambled):.3f}")
    print("  Without scrambling, a long run of 0s starves SONET clock recovery.")


if __name__ == "__main__":
    main()
