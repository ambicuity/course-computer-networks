#!/usr/bin/env python3
"""Store-and-forward packet switching simulator.

This stdlib-only program walks a single IPv4 packet hop-by-hop across a
multi-router path, modelling the store-and-forward rule: each router must
receive the whole frame, verify its checksum, decrement the TTL, recompute
the IPv4 header checksum, do a destination lookup, and only then forward.

It demonstrates, with printed evidence: the four per-hop delay components
(transmission, propagation, processing, queuing) summing into end-to-end
latency; TTL decrement and the ICMP Time Exceeded drop when TTL hits 0;
the IPv4 header checksum (RFC 1071) changing each hop because TTL changed;
and integrity gating (a frame whose FCS / CRC-32 fails is dropped).

Run:  python3 main.py
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

PROPAGATION_SPEED_MPS = 2.0e8  # ~speed of light in fiber
PACKET_BYTES = 1500            # try 64 to see processing/propagation dominate
PROCESSING_DELAY_S = 20e-6     # per-hop lookup + checksum cost


def ones_complement_checksum(header: bytes) -> int:
    """Compute the 16-bit IPv4 header checksum (RFC 1071).

    Sum 16-bit words in ones'-complement, fold carries, then complement.
    The checksum field itself must be zero in the input.
    """
    if len(header) % 2 == 1:
        header = header + b"\x00"
    total = 0
    for i in range(0, len(header), 2):
        total += (header[i] << 8) | header[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_ipv4_header(src: str, dst: str, ttl: int, payload_len: int) -> bytes:
    """Build a 20-byte IPv4 header (RFC 791) with a valid checksum."""
    version_ihl = (4 << 4) | 5          # IPv4, IHL=5 (20 bytes)
    tos = 0
    total_length = 20 + payload_len
    identification = 0x1C46
    flags_frag = 0x4000                  # Don't Fragment
    protocol = 6                         # TCP
    src_b = bytes(int(o) for o in src.split("."))
    dst_b = bytes(int(o) for o in dst.split("."))
    header_no_csum = struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl, tos, total_length, identification,
        flags_frag, ttl, protocol, 0, src_b, dst_b,
    )
    csum = ones_complement_checksum(header_no_csum)
    return struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl, tos, total_length, identification,
        flags_frag, ttl, protocol, csum, src_b, dst_b,
    )


def read_ttl_and_checksum(header: bytes) -> tuple[int, int]:
    """Extract TTL (offset 8) and header checksum (offset 10)."""
    ttl = header[8]
    csum = (header[10] << 8) | header[11]
    return ttl, csum


@dataclass(frozen=True)
class Link:
    """One hop: the router that forwards onto an outgoing link."""
    router: str
    next_hop: str
    rate_bps: float
    distance_m: float


@dataclass(frozen=True)
class HopResult:
    router: str
    ttl_in: int
    ttl_out: int
    checksum: int
    transmission_s: float
    propagation_s: float
    processing_s: float
    queuing_s: float

    @property
    def total_s(self) -> float:
        return (self.transmission_s + self.propagation_s
                + self.processing_s + self.queuing_s)


def frame_passes_fcs(frame: bytes, claimed_fcs: int) -> bool:
    """Verify the Ethernet-style FCS (CRC-32) over the frame body."""
    return (zlib.crc32(frame) & 0xFFFFFFFF) == claimed_fcs


def forward_one_hop(header: bytes, link: Link, packet_bits: int,
                    queue_depth: int) -> tuple[bytes, HopResult] | None:
    """Apply store-and-forward processing at one router.

    Returns the rewritten header and a HopResult, or None if the packet is
    dropped (TTL exhausted -> ICMP Time Exceeded, Type 11).
    """
    ttl_in, _ = read_ttl_and_checksum(header)
    ttl_out = ttl_in - 1
    if ttl_out <= 0:
        return None  # drop; emit ICMP Time Exceeded

    # Rewrite TTL and recompute the header checksum (it changed).
    mutable = bytearray(header)
    mutable[8] = ttl_out
    mutable[10] = 0
    mutable[11] = 0
    new_csum = ones_complement_checksum(bytes(mutable))
    mutable[10] = (new_csum >> 8) & 0xFF
    mutable[11] = new_csum & 0xFF
    new_header = bytes(mutable)

    transmission = packet_bits / link.rate_bps
    propagation = link.distance_m / PROPAGATION_SPEED_MPS
    queuing = queue_depth * transmission  # packets already buffered ahead
    result = HopResult(
        router=link.router,
        ttl_in=ttl_in,
        ttl_out=ttl_out,
        checksum=new_csum,
        transmission_s=transmission,
        propagation_s=propagation,
        processing_s=PROCESSING_DELAY_S,
        queuing_s=queuing,
    )
    return new_header, result


def run_path(header: bytes, path: list[Link], packet_bits: int,
             queue_depths: list[int]) -> tuple[bytes, list[HopResult]]:
    """Walk the packet across every store-and-forward hop on the path."""
    results: list[HopResult] = []
    current = header
    for link, depth in zip(path, queue_depths):
        outcome = forward_one_hop(current, link, packet_bits, depth)
        if outcome is None:
            print(f"  [{link.router}] TTL exhausted -> DROP, "
                  f"ICMP Time Exceeded (Type 11, Code 0) to source")
            break
        current, res = outcome
        results.append(res)
    return current, results


def ms(seconds: float) -> str:
    return f"{seconds * 1000:8.3f} ms"


def main() -> None:
    packet_bits = PACKET_BYTES * 8
    header = build_ipv4_header("192.0.2.10", "203.0.113.45", ttl=64,
                               payload_len=PACKET_BYTES - 20)

    print("Store-and-Forward Packet Switching simulator")
    print("=" * 64)
    print(f"Packet: {PACKET_BYTES} bytes ({packet_bits} bits), "
          f"src 192.0.2.10 -> dst 203.0.113.45, initial TTL 64")
    _, csum0 = read_ttl_and_checksum(header)
    print(f"Initial header checksum: 0x{csum0:04X}\n")
    path = [
        Link("A", "C", rate_bps=10e6, distance_m=100_000),   # 10 Mbps, 100 km
        Link("C", "E", rate_bps=10e6, distance_m=80_000),
        Link("E", "F", rate_bps=100e6, distance_m=20_000),   # faster local link
        Link("F", "H2", rate_bps=1e9, distance_m=2_000),     # 1 Gbps LAN
    ]
    queue_depths = [0, 3, 0, 0]  # router C has 3 packets queued ahead

    print(f"{'Hop':<5}{'TTLin':>6}{'TTLout':>7}{'csum':>8}"
          f"{'tx':>11}{'prop':>11}{'proc':>11}{'queue':>11}{'hop':>11}")
    print("-" * 90)

    _, results = run_path(header, path, packet_bits, queue_depths)
    for r in results:
        print(f"{r.router:<5}{r.ttl_in:>6}{r.ttl_out:>7}"
              f"  0x{r.checksum:04X}"
              f"{ms(r.transmission_s):>11}{ms(r.propagation_s):>11}"
              f"{ms(r.processing_s):>11}{ms(r.queuing_s):>11}"
              f"{ms(r.total_s):>11}")

    end_to_end = sum(r.total_s for r in results)
    tx_total = sum(r.transmission_s for r in results)
    print("-" * 90)
    print(f"End-to-end delay: {ms(end_to_end)}  "
          f"(serialization paid {len(results)}x = {ms(tx_total)} of it)")

    # Integrity gating demonstration.
    print("\nIntegrity gate (FCS / CRC-32):")
    frame = header + b"payload-bytes-here"
    good_fcs = zlib.crc32(frame) & 0xFFFFFFFF
    corrupt = bytearray(frame)
    corrupt[-1] ^= 0xFF  # flip a payload bit in flight
    clean_ok = frame_passes_fcs(frame, good_fcs)
    corrupt_ok = frame_passes_fcs(bytes(corrupt), good_fcs)
    print(f"  clean frame   -> FCS {'PASS' if clean_ok else 'FAIL'} -> forwarded")
    print(f"  corrupt frame -> FCS {'PASS' if corrupt_ok else 'FAIL'} -> "
          f"DROPPED (no NAK; loss recovery is end-to-end)")

    # TTL exhaustion demonstration (traceroute-style probe).
    print("\nTTL exhaustion (traceroute probe, TTL=2):")
    probe = build_ipv4_header("192.0.2.10", "203.0.113.45", ttl=2,
                              payload_len=PACKET_BYTES - 20)
    run_path(probe, path, packet_bits, queue_depths)


if __name__ == "__main__":
    main()
