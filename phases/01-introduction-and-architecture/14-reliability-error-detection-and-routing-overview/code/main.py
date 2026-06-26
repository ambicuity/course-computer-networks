"""
Reliability, Error Detection, and Routing as Layer Design Issues.

A stdlib-only model of the three recurring reliability mechanisms:

  1. Error detection   - CRC-32 (Ethernet FCS) and IPv4 one's-complement checksum
  2. Error correction  - Hamming(7,4) forward error correction
  3. Reliable transfer - sliding-window ARQ over a lossy link
  4. Routing           - Dijkstra shortest path, with reroute on failure

Run:  python3 main.py
No network calls, no third-party packages.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# 1. Error detection: CRC-32 (IEEE 802.3 Frame Check Sequence)
# ---------------------------------------------------------------------------

_CRC32_POLY = 0xEDB88320  # reflected form of 0x04C11DB7
_CRC32_TABLE: List[int] = []


def _build_crc32_table() -> None:
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ _CRC32_POLY if (c & 1) else (c >> 1)
        _CRC32_TABLE.append(c)


def crc32(data: bytes) -> int:
    """IEEE 802.3 CRC-32 remainder, as appended to an Ethernet frame as the FCS."""
    if not _CRC32_TABLE:
        _build_crc32_table()
    c = 0xFFFFFFFF
    for b in data:
        c = _CRC32_TABLE[(c ^ b) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


def internet_checksum(header: bytes) -> int:
    """RFC 1071 one's-complement 16-bit sum, returned inverted (the stored value)."""
    if len(header) % 2 == 1:
        header = header + b"\x00"
    total = 0
    for i in range(0, len(header), 2):
        word = (header[i] << 8) | header[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)  # fold carry
    return (~total) & 0xFFFF


def raw_sum(header: bytes) -> int:
    """Un-inverted one's-complement sum; a valid header (checksum included) == 0xFFFF."""
    if len(header) % 2 == 1:
        header = header + b"\x00"
    total = 0
    for i in range(0, len(header), 2):
        total += (header[i] << 8) | header[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return total


# ---------------------------------------------------------------------------
# 2. Error correction: Hamming(7,4)
# ---------------------------------------------------------------------------

# Positions 1,2,4 are parity; 3,5,6,7 carry data d1..d4.
_HAMMING_PARITY: Dict[int, List[int]] = {
    1: [3, 5, 7],
    2: [3, 6, 7],
    4: [5, 6, 7],
}
_PARITY_BIT: Dict[int, int] = {1: 0, 2: 1, 4: 2}


class Hamming74:
    """Encode 4 data bits into 7, correct any single-bit error."""

    @staticmethod
    def encode(nibble: int) -> List[int]:
        if not 0 <= nibble <= 0b1111:
            raise ValueError("nibble must be 4 bits")
        d = [(nibble >> (3 - i)) & 1 for i in range(4)]  # d1..d4
        code = [0] * 8  # index 0 unused so positions are 1..7
        code[3], code[5], code[6], code[7] = d
        for p, covered in _HAMMING_PARITY.items():
            code[p] = sum(code[i] for i in covered) % 2
        return code[1:]

    @staticmethod
    def syndrome(code: List[int]) -> int:
        c = [0] + list(code)
        s = 0
        for p in (1, 2, 4):
            recomputed = sum(c[i] for i in _HAMMING_PARITY[p]) % 2
            check = recomputed ^ c[p]  # parity holds iff recomputed == stored
            s |= check << _PARITY_BIT[p]  # parity-p contributes value p
        return s

    @staticmethod
    def correct(code: List[int]) -> Tuple[List[int], int]:
        s = Hamming74.syndrome(code)
        out = list(code)
        if s != 0:
            out[s - 1] ^= 1  # flip the offending bit (1-indexed)
        return out, s

    @staticmethod
    def decode(code: List[int]) -> int:
        c = list(code)
        return (c[2] << 3) | (c[4] << 2) | (c[5] << 1) | c[6]


# ---------------------------------------------------------------------------
# 3. Reliable transfer: sliding-window ARQ (Go-Back-N) over a lossy link
# ---------------------------------------------------------------------------

@dataclass
class SlidingWindow:
    """A Go-Back-N sender over a Bernoulli-loss channel."""
    window: int
    loss_prob: float
    total_frames: int
    base: int = 0
    next_seq: int = 0
    log: List[str] = field(default_factory=list)

    def _send(self, seq: int) -> bool:
        lost = random.random() < self.loss_prob
        self.log.append(f"  TX frame {seq:>2}  {'LOST' if lost else 'ok'}")
        return not lost

    def run(self) -> int:
        """Return total transmissions (including retransmissions)."""
        tx = 0
        while self.base < self.total_frames:
            while (self.next_seq < self.base + self.window
                   and self.next_seq < self.total_frames):
                delivered = self._send(self.next_seq)
                tx += 1
                if delivered:
                    self.log.append(f"  RX ACK {self.next_seq}")
                    self.base = self.next_seq + 1
                self.next_seq += 1
            if (self.base < self.total_frames
                    and self.next_seq >= self.base + self.window):
                self.log.append(f"  RTO -> rewind to base {self.base}")
                self.next_seq = self.base
        return tx


# ---------------------------------------------------------------------------
# 4. Routing: Dijkstra, with reroute on a failed node
# ---------------------------------------------------------------------------

Graph = Dict[str, Dict[str, int]]


def dijkstra(graph: Graph, src: str, dst: str,
             down: set[str] | None = None) -> Tuple[List[str], int]:
    """Shortest path src->dst avoiding any node in `down`. Returns (path, cost)."""
    down = down or set()
    dist = {n: float("inf") for n in graph if n not in down}
    prev: Dict[str, str | None] = {n: None for n in dist}
    dist[src] = 0
    pq: List[Tuple[int, str]] = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in graph[u].items():
            if v in down:
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dist[dst] == float("inf"):
        return [], -1
    path: List[str] = []
    cur: str | None = dst
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return list(reversed(path)), int(dist[dst])


EUROPE: Graph = {
    "London":    {"Paris": 8, "Frankfurt": 4},
    "Paris":     {"London": 8, "Frankfurt": 5, "Rome": 6},
    "Frankfurt": {"London": 4, "Paris": 5, "Rome": 4},
    "Rome":      {"Paris": 6, "Frankfurt": 4},
}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_detection() -> None:
    print("== Error detection ==")
    frame = bytes.fromhex("4500001c00004000401100000a0000010a000002")
    print(f"sample frame ({len(frame)} bytes): {frame.hex()}")
    print(f"  CRC-32 FCS  = 0x{crc32(frame):08X}")
    header = frame  # treat as 20-byte IPv4 header with checksum field = 0
    cs = internet_checksum(header)
    print(f"  IPv4 checksum (computed, field was 0) = 0x{cs:04X}")
    stamped = header[:10] + cs.to_bytes(2, "big") + header[12:]
    print(f"  stamped header: {stamped.hex()}")
    print(f"  receiver raw sum == 0xFFFF? {raw_sum(stamped) == 0xFFFF}")
    damaged = bytearray(stamped)
    damaged[2] ^= 0x01  # flip one bit in Total Length
    print(f"  damaged header:  {bytes(damaged).hex()}")
    print(f"  receiver raw sum == 0xFFFF? "
          f"{raw_sum(bytes(damaged)) == 0xFFFF}  (router drops it)")


def demo_fec() -> None:
    print("\n== Forward error correction: Hamming(7,4) ==")
    nibble = 0b1011
    code = Hamming74.encode(nibble)
    print(f"nibble {nibble:04b} -> codeword {code}")
    code[4] ^= 1  # flip position 5 (index 4)
    print(f"inject 1-bit error -> {code}")
    fixed, syndrome = Hamming74.correct(code)
    print(f"syndrome = {syndrome:03b} (points at position {syndrome})")
    print(f"corrected codeword = {fixed}, decoded nibble = "
          f"{Hamming74.decode(fixed):04b}")


def demo_arq() -> None:
    print("\n== Sliding-window ARQ (Go-Back-N) ==")
    # A seed chosen so frames 3,4,5 are all lost within the window: the
    # window fills, the base cannot advance past 3, and the sender rewinds.
    random.seed(1)
    sw = SlidingWindow(window=3, loss_prob=0.50, total_frames=8)
    tx = sw.run()
    for line in sw.log:
        print(line)
    print(f"delivered {sw.total_frames} frames with {tx} transmissions "
          f"(ideal {sw.total_frames}, overhead {tx - sw.total_frames})")


def demo_routing() -> None:
    print("\n== Routing: Dijkstra, reroute around failure ==")
    path, cost = dijkstra(EUROPE, "London", "Rome")
    print(f"normal:          London -> Rome = {path}  cost {cost}")
    path2, cost2 = dijkstra(EUROPE, "London", "Rome", down={"Frankfurt"})
    print(f"Frankfurt down:  London -> Rome = {path2}  cost {cost2}")
    print("  (the textbook's London->Paris->Rome reroute)")


def main() -> None:
    demo_detection()
    demo_fec()
    demo_arq()
    demo_routing()


if __name__ == "__main__":
    main()
