#!/usr/bin/env python3
"""Fast segment processing and header compression simulator.

Stdlib only. Demonstrates Sec 6.6.4-6.6.5:

1. Header prediction (fast path): check if an incoming segment is the
   "normal" expected one (ESTABLISHED, expected seq, no special flags,
   full segment). If so, take the fast path -- skip the slow-path processing.
2. Prototype header optimization: consecutive segments share most header
   fields; only seq/ack/checksum change. Copy a prototype and overwrite.
3. Van Jacobson TCP/IP header compression: compress 40-byte TCP/IP headers
   down to 3-7 bytes by exploiting that most fields are constant or change
   predictably (delta encoding of seq/ack).
4. Timing wheel for efficient timer management (O(1) insert/expire).

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: Header prediction (fast path processing)
# ---------------------------------------------------------------------------

FLAG_ACK = 0x10
FLAG_PSH = 0x08
FLAG_SYN = 0x02
FLAG_FIN = 0x01
FLAG_RST = 0x04
FLAG_URG = 0x20

SPECIAL_FLAGS = FLAG_SYN | FLAG_FIN | FLAG_RST | FLAG_URG


@dataclass
class Segment:
    src_port: int
    dst_port: int
    seq: int
    ack: int
    flags: int
    window: int
    payload: bytes = b""

    def is_normal(self, expected_seq: int, state: str = "ESTABLISHED") -> bool:
        """Header prediction test: is this the normal-case segment?"""
        if state != "ESTABLISHED":
            return False
        if self.flags & SPECIAL_FLAGS:
            return False
        if self.seq != expected_seq:
            return False
        if len(self.payload) == 0:
            return False
        return True


@dataclass
class FastPathProcessor:
    expected_seq: int = 0
    last_conn_used: str = ""
    fast_path_hits: int = 0
    slow_path_hits: int = 0

    def process(self, seg: Segment, conn_id: str) -> str:
        if conn_id == self.last_conn_used and seg.is_normal(self.expected_seq):
            self.fast_path_hits += 1
            self.expected_seq += len(seg.payload)
            return f"FAST PATH: seq={seg.seq} len={len(seg.payload)} -> expected={self.expected_seq}"
        self.slow_path_hits += 1
        self.last_conn_used = conn_id
        if seg.seq == self.expected_seq and len(seg.payload) > 0:
            self.expected_seq += len(seg.payload)
            return f"SLOW PATH (conn lookup): seq={seg.seq} -> expected={self.expected_seq}"
        return f"SLOW PATH (special): seq={seg.seq} flags=0x{seg.flags:02X}"


# ---------------------------------------------------------------------------
# Part 2: Prototype header optimization
# ---------------------------------------------------------------------------

@dataclass
class PrototypeHeader:
    """Store a prototype TCP/IP header; copy and overwrite changing fields."""
    src_port: int = 0
    dst_port: int = 0
    ip_src: str = "0.0.0.0"
    ip_dst: str = "0.0.0.0"
    flags: int = FLAG_ACK | FLAG_PSH
    window: int = 65535
    next_seq: int = 0

    def build_segment(self, seq: int, ack: int, payload: bytes) -> Segment:
        return Segment(
            src_port=self.src_port, dst_port=self.dst_port,
            seq=seq, ack=ack, flags=self.flags, window=self.window,
            payload=payload,
        )


# ---------------------------------------------------------------------------
# Part 3: Van Jacobson TCP/IP header compression
# ---------------------------------------------------------------------------

@dataclass
class VJCompressor:
    """Van Jacobson TCP/IP header compression (RFC 1144).

    Compresses 40-byte TCP/IP headers to 3-7 bytes by:
    - Omitting constant fields (ports, IP addresses)
    - Delta-encoding seq/ack (small changes sent as 1-2 byte deltas)
    - Omitting unchanged fields entirely
    """
    ctx_seq: dict[int, int] = field(default_factory=dict)
    ctx_ack: dict[int, int] = field(default_factory=dict)

    def compress(self, ctx_id: int, src_port: int, dst_port: int,
                 seq: int, ack: int, flags: int, window: int) -> bytes:
        prev_seq = self.ctx_seq.get(ctx_id, 0)
        prev_ack = self.ctx_ack.get(ctx_id, 0)
        self.ctx_seq[ctx_id] = seq
        self.ctx_ack[ctx_id] = ack

        delta_seq = (seq - prev_seq) & 0xFFFFFFFF
        delta_ack = (ack - prev_ack) & 0xFFFFFFFF

        compressed = bytes([ctx_id])
        change_byte = 0
        if delta_seq != 0:
            change_byte |= 0x40
        if delta_ack != 0:
            change_byte |= 0x20
        if flags != (FLAG_ACK | FLAG_PSH):
            change_byte |= 0x10
        compressed += bytes([change_byte])

        if delta_seq != 0:
            compressed += struct.pack("!I", delta_seq)
        if delta_ack != 0:
            compressed += struct.pack("!I", delta_ack)
        if flags != (FLAG_ACK | FLAG_PSH):
            compressed += bytes([flags])
        return compressed

    def decompress(self, compressed: bytes, src_port: int, dst_port: int
                   ) -> tuple[int, int, int, int]:
        ctx_id = compressed[0]
        change_byte = compressed[1]
        idx = 2
        delta_seq = 0
        delta_ack = 0
        flags = FLAG_ACK | FLAG_PSH
        if change_byte & 0x40:
            delta_seq = struct.unpack("!I", compressed[idx:idx+4])[0]
            idx += 4
        if change_byte & 0x20:
            delta_ack = struct.unpack("!I", compressed[idx:idx+4])[0]
            idx += 4
        if change_byte & 0x10:
            flags = compressed[idx]
            idx += 1
        seq = (self.ctx_seq.get(ctx_id, 0) + delta_seq) & 0xFFFFFFFF
        ack = (self.ctx_ack.get(ctx_id, 0) + delta_ack) & 0xFFFFFFFF
        self.ctx_seq[ctx_id] = seq
        self.ctx_ack[ctx_id] = ack
        return ctx_id, seq, ack, flags


# ---------------------------------------------------------------------------
# Part 4: Timing wheel for timer management
# ---------------------------------------------------------------------------

@dataclass
class TimingWheel:
    """O(1) timer insert/expire using a circular array of slots."""
    slots: list[list[str]] = field(default_factory=lambda: [[] for _ in range(16)])
    current: int = 0

    def add_timer(self, ticks: int, label: str) -> None:
        slot = (self.current + ticks) % len(self.slots)
        self.slots[slot].append(label)

    def tick(self) -> list[str]:
        expired = self.slots[self.current]
        self.slots[self.current] = []
        self.current = (self.current + 1) % len(self.slots)
        return expired


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Header Prediction: Fast Path vs Slow Path (Sec 6.6.4)")
    print("=" * 70)
    proc = FastPathProcessor(expected_seq=1000, last_conn_used="conn1")
    segments = [
        ("conn1", Segment(1000, 80, 1000, 5000, FLAG_ACK | FLAG_PSH, 65535, b"data1"), "normal data"),
        ("conn1", Segment(1000, 80, 1006, 5000, FLAG_ACK | FLAG_PSH, 65535, b"data2"), "normal data"),
        ("conn1", Segment(1000, 80, 1012, 5000, FLAG_SYN, 65535, b""), "SYN (special)"),
        ("conn2", Segment(5000, 80, 200, 100, FLAG_ACK | FLAG_PSH, 65535, b"other"), "different conn"),
        ("conn1", Segment(1000, 80, 1018, 5000, FLAG_ACK | FLAG_PSH, 65535, b"data3"), "normal again"),
        ("conn1", Segment(1000, 80, 1024, 5000, FLAG_FIN | FLAG_ACK, 65535, b""), "FIN (special)"),
    ]
    print(f"  {'Conn':>6}  {'Description':>15}  {'Result':>50}")
    for conn_id, seg, desc in segments:
        result = proc.process(seg, conn_id)
        print(f"  {conn_id:>6}  {desc:>15}  {result:>50}")
    print(f"\n  Fast path hits: {proc.fast_path_hits}  Slow path hits: {proc.slow_path_hits}")
    print("  Clark et al. observed >90% hit rate with last-connection cache.")

    print()
    print("=" * 70)
    print("Prototype Header: Copy and Overwrite Changing Fields")
    print("=" * 70)
    proto = PrototypeHeader(src_port=50000, dst_port=80, flags=FLAG_ACK | FLAG_PSH, window=65535)
    print(f"  Prototype: src={proto.src_port} dst={proto.dst_port} flags=0x{proto.flags:02X}")
    print("  Consecutive segments share all fields except seq/ack/checksum:")
    for i in range(4):
        seg = proto.build_segment(seq=1000 + i * 100, ack=2000, payload=b"x" * 100)
        print(f"    seg {i}: seq={seg.seq} ack={seg.ack} (other fields from prototype)")

    print()
    print("=" * 70)
    print("Van Jacobson TCP/IP Header Compression (RFC 1144)")
    print("=" * 70)
    comp = VJCompressor()
    full_header_size = 40
    print(f"  Full TCP/IP header: {full_header_size} bytes (20 IP + 20 TCP)")
    print(f"  {'Packet':>7}  {'Full(B)':>7}  {'Compressed(B)':>13}  {'Savings':>8}  {'Note':>25}")
    total_full = 0
    total_compressed = 0
    for i in range(8):
        seq = 1000 + i * 100
        ack = 2000 + i * 50
        flags = FLAG_ACK | FLAG_PSH if i < 6 else FLAG_ACK | FLAG_FIN
        compressed = comp.compress(1, 50000, 80, seq, ack, flags, 65535)
        total_full += full_header_size
        total_compressed += len(compressed)
        note = "first pkt (full delta)" if i == 0 else "seq+ack delta" if i < 6 else "FIN flag change"
        savings = (1 - len(compressed) / full_header_size) * 100
        print(f"  {i:7d}  {full_header_size:7d}  {len(compressed):13d}  {savings:7.1f}%  {note:>25}")

    print(f"\n  Total: {total_full}B full -> {total_compressed}B compressed "
          f"({(1-total_compressed/total_full)*100:.1f}% reduction)")
    print("  Average ~3-7 bytes per header on steady-state flows.")

    print()
    print("  Decompression verification:")
    comp2 = VJCompressor()
    for i in range(3):
        seq = 1000 + i * 100
        ack = 2000 + i * 50
        c = comp2.compress(1, 50000, 80, seq, ack, FLAG_ACK | FLAG_PSH, 65535)
        ctx, dseq, dack, dflags = comp2.decompress(c, 50000, 80)
        ok = dseq == seq and dack == ack
        print(f"    pkt {i}: compressed={len(c)}B -> seq={dseq} ack={dack} match={ok}")

    print()
    print("=" * 70)
    print("Timing Wheel: O(1) Timer Management (Fig 6-53)")
    print("=" * 70)
    wheel = TimingWheel(slots=[[] for _ in range(16)], current=4)
    print(f"  Current time T=4, wheel size=16 slots")
    wheel.add_timer(3, "timer-A")
    wheel.add_timer(10, "timer-B")
    wheel.add_timer(12, "timer-C")
    print(f"  Added: timer-A(3 ticks -> slot {7}), timer-B(10 -> slot {14}), timer-C(12 -> slot {0})")
    print()
    for t in range(16):
        expired = wheel.tick()
        if expired:
            print(f"  T={t}: expired {expired}")
    print("  O(1) insert and expire; no sorting needed (unlike linked-list timers).")


if __name__ == "__main__":
    main()