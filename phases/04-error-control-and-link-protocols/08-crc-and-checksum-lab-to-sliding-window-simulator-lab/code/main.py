#!/usr/bin/env python3
"""CRC/Checksum + Sliding-Window capstone (stdlib only, offline).

This program ties data-link error *detection* to error *recovery*:

  1. CRC-32 (IEEE 802.3, poly 0x04C11DB7) implemented bit-by-bit and
     cross-checked against ``binascii.crc32``.
  2. The RFC 1071 16-bit one's-complement Internet checksum, including the
     end-around carry, with a demonstration of its blind spot (16-bit word
     reordering passes the checksum but fails CRC-32).
  3. A lossy channel + Go-Back-N and Selective Repeat simulators that show
     the single-loss retransmission behaviour, the SR sequence-number
     aliasing bug when W > 2^(m-1), and the window-vs-utilization knee.

Run:  python3 main.py
No pip packages, no sockets, no network calls.
"""
from __future__ import annotations

import binascii
import random
from dataclasses import dataclass
from typing import List

# --------------------------------------------------------------------------
# Part 1: CRC-32 (IEEE 802.3) by bitwise LFSR
# --------------------------------------------------------------------------

CRC32_POLY_REFLECTED = 0xEDB88320  # reflected form of 0x04C11DB7
CRC32_INIT = 0xFFFFFFFF
CRC32_XOROUT = 0xFFFFFFFF


def crc32_bitwise(data: bytes) -> int:
    """Compute IEEE 802.3 CRC-32 one bit at a time (reflected, LSB-first)."""
    crc = CRC32_INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ CRC32_POLY_REFLECTED
            else:
                crc >>= 1
    return crc ^ CRC32_XOROUT


def crc32_verify(data: bytes, expected: int) -> bool:
    """Return True if the recomputed CRC matches the carried value."""
    return crc32_bitwise(data) == expected


def crc4_remainder(data_bits: str, generator: str = "10011") -> str:
    """Teaching CRC over GF(2): modulo-2 long division, returns remainder.

    ``generator`` defaults to x^4 + x + 1 (0b10011), width 4.
    """
    r = len(generator) - 1
    bits = list(data_bits + "0" * r)
    gen = list(generator)
    for i in range(len(data_bits)):
        if bits[i] == "1":
            for j in range(len(gen)):
                bits[i + j] = "1" if bits[i + j] != gen[j] else "0"
    return "".join(bits[-r:])


# --------------------------------------------------------------------------
# Part 2: RFC 1071 16-bit one's-complement Internet checksum
# --------------------------------------------------------------------------


def internet_checksum(data: bytes) -> int:
    """RFC 1071 checksum: sum 16-bit big-endian words, fold carries, complement."""
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:  # end-around carry
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def verify_checksum(data: bytes, checksum: int) -> bool:
    """Receiver check: summing data + checksum word must yield 0xFFFF."""
    if len(data) % 2:
        data = data + b"\x00"
    total = checksum
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return total == 0xFFFF


def swap_first_two_words(data: bytes) -> bytes:
    """Reorder the first two 16-bit words (checksum-invariant, CRC-sensitive)."""
    if len(data) < 4:
        return data
    return data[2:4] + data[0:2] + data[4:]


# --------------------------------------------------------------------------
# Part 3: lossy channel + sliding-window simulators
# --------------------------------------------------------------------------


@dataclass
class Channel:
    """Drops frames at a fixed probability with a seeded RNG (reproducible)."""

    loss_prob: float
    rng: random.Random

    def deliver(self, seq: int) -> bool:
        """Return True if a frame survives the channel."""
        return self.rng.random() >= self.loss_prob


@dataclass
class SimResult:
    protocol: str
    delivered: int
    transmissions: int
    timeouts: int

    @property
    def goodput(self) -> float:
        return self.delivered / self.transmissions if self.transmissions else 0.0


def go_back_n(n_frames: int, window: int, m_bits: int, channel: Channel,
              verbose: bool = False) -> SimResult:
    """Go-Back-N: cumulative ACK, single timer, full-window retransmit on loss."""
    seq_space = 1 << m_bits
    assert window <= seq_space - 1, "GBN requires W <= 2^m - 1"
    base = 0
    transmissions = 0
    timeouts = 0
    log: List[str] = []
    while base < n_frames:
        sent_ok_upto = base - 1
        for i in range(base, min(base + window, n_frames)):
            transmissions += 1
            if channel.deliver(i % seq_space):
                if i == sent_ok_upto + 1:
                    sent_ok_upto = i
                log.append(f"send {i} (seq {i % seq_space}) -> OK")
            else:
                log.append(f"send {i} (seq {i % seq_space}) -> DROPPED")
        # cumulative ACK advances base to the last in-order delivered frame + 1
        if sent_ok_upto >= base:
            base = sent_ok_upto + 1
        else:
            timeouts += 1
            log.append(f"TIMEOUT at base {base}: go back N, resend window")
    if verbose:
        for line in log:
            print("   " + line)
    return SimResult("Go-Back-N", n_frames, transmissions, timeouts)


def selective_repeat(n_frames: int, window: int, m_bits: int, channel: Channel,
                     allow_aliasing: bool = False,
                     verbose: bool = False) -> SimResult:
    """Selective Repeat: per-frame ACK/buffer, resend only the lost frame.

    With ``allow_aliasing`` the W <= 2^(m-1) guard is bypassed to reproduce
    the classic sequence-number ambiguity bug.
    """
    seq_space = 1 << m_bits
    if not allow_aliasing:
        assert window <= seq_space // 2, "SR requires W <= 2^(m-1)"
    transmissions = 0
    timeouts = 0
    acked = [False] * n_frames
    log: List[str] = []
    base = 0
    while base < n_frames:
        progressed = False
        for i in range(base, min(base + window, n_frames)):
            if acked[i]:
                continue
            transmissions += 1
            if channel.deliver(i % seq_space):
                acked[i] = True
                progressed = True
                log.append(f"send {i} (seq {i % seq_space}) -> ACK")
            else:
                log.append(f"send {i} (seq {i % seq_space}) -> DROPPED, retry")
        while base < n_frames and acked[base]:
            base += 1
        if not progressed and base < n_frames:
            timeouts += 1
    if verbose:
        for line in log:
            print("   " + line)
    return SimResult("Selective Repeat", n_frames, transmissions, timeouts)


def utilization(window: int, frame_time_s: float, rtt_s: float) -> float:
    """Sliding-window sender efficiency: U = min(1, W*Tf / (Tf + RTT))."""
    return min(1.0, window * frame_time_s / (frame_time_s + rtt_s))


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------


def demo_crc() -> None:
    print("=" * 64)
    print("Part 1: CRC-32 (IEEE 802.3, poly 0x04C11DB7)")
    print("=" * 64)
    for sample in (b"", b"123456789", b"The quick brown fox"):
        mine = crc32_bitwise(sample)
        ref = binascii.crc32(sample) & 0xFFFFFFFF
        ok = "OK" if mine == ref else "MISMATCH"
        print(f"  {sample!r:24} crc=0x{mine:08X}  vs binascii 0x{ref:08X} [{ok}]")
    frame = b"NET-FRAME-PAYLOAD"
    fcs = crc32_bitwise(frame)
    print(f"\n  clean frame verifies : {crc32_verify(frame, fcs)}")
    corrupt = bytearray(frame)
    corrupt[3] ^= 0x01  # flip one bit
    print(f"  1-bit flip verifies  : {crc32_verify(bytes(corrupt), fcs)}  (expect False)")
    rem = crc4_remainder("1101")
    print(f"\n  CRC-4 teaching division: 1101 / 10011 -> remainder {rem} "
          f"(frame on wire = 1101 {rem})")


def demo_checksum() -> None:
    print("\n" + "=" * 64)
    print("Part 2: RFC 1071 Internet checksum and its blind spot")
    print("=" * 64)
    packet = bytes([0x45, 0x00, 0x00, 0x3C, 0x1C, 0x46, 0x40, 0x00,
                    0x40, 0x06, 0x00, 0x00, 0xAC, 0x10, 0x0A, 0x63])
    cks = internet_checksum(packet)
    print(f"  packet checksum      : 0x{cks:04X}")
    print(f"  clean packet verifies: {verify_checksum(packet, cks)}")

    swapped = swap_first_two_words(packet)
    print("\n  -- swap first two 16-bit words --")
    print(f"  checksum still passes: {verify_checksum(swapped, cks)}  <- BLIND SPOT")
    crc_clean = crc32_bitwise(packet)
    print(f"  CRC-32 catches swap  : {not crc32_verify(swapped, crc_clean)}  "
          "(CRC is position-sensitive)")


def demo_sliding_window() -> None:
    print("\n" + "=" * 64)
    print("Part 3: Go-Back-N vs Selective Repeat over a lossy channel")
    print("=" * 64)
    gbn = go_back_n(n_frames=12, window=4, m_bits=3,
                    channel=Channel(loss_prob=0.20, rng=random.Random(42)))
    sr = selective_repeat(n_frames=12, window=4, m_bits=3,
                          channel=Channel(loss_prob=0.20, rng=random.Random(42)))
    for r in (gbn, sr):
        print(f"  {r.protocol:18} delivered={r.delivered:2d} "
              f"transmissions={r.transmissions:2d} timeouts={r.timeouts} "
              f"goodput={r.goodput:.2f}")

    print("\n  -- Selective Repeat aliasing (m=2 -> seq 0..3, W=3 > 2^(m-1)=2) --")
    try:
        selective_repeat(6, window=3, m_bits=2, channel=Channel(0.0, random.Random(1)))
    except AssertionError as exc:
        print(f"  guard correctly blocks unsafe window: {exc}")
    aliased = selective_repeat(6, window=3, m_bits=2,
                               channel=Channel(0.0, random.Random(1)),
                               allow_aliasing=True)
    print(f"  guard disabled -> frames 0 and 4 both map to seq {0 % 4} "
          f"(delivered={aliased.delivered}); a real receiver mistakes the "
          "resent seq 0 for new data.")


def demo_throughput() -> None:
    print("\n" + "=" * 64)
    print("Part 4: window size vs utilization (1 Gbps, 1500 B, RTT 10 ms)")
    print("=" * 64)
    frame_time = 12000 / 1e9      # 1500 bytes at 1 Gbps -> 12 us
    rtt = 10e-3                   # 10 ms round trip
    bdp = (frame_time + rtt) / frame_time
    print(f"  frame time = {frame_time * 1e6:.0f} us, RTT = {rtt * 1e3:.0f} ms, "
          f"BDP window ~= {bdp:.0f} frames\n")
    print("  W      utilization")
    for w in (1, 8, 64, 256, 835, 1024):
        u = utilization(w, frame_time, rtt)
        bar = "#" * int(u * 30)
        print(f"  {w:5d}  {u:6.3f}  {bar}")
    print("\n  A window of 8 saturates <1% of the link -> the 'crawls' symptom.")


def main() -> None:
    demo_crc()
    demo_checksum()
    demo_sliding_window()
    demo_throughput()
    print("\nDone. Detect with CRC/checksum, recover with the sliding window.")


if __name__ == "__main__":
    main()
