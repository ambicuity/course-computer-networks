#!/usr/bin/env python3
"""TCP service model, byte stream, and segmentation simulator.

This module models the parts of TCP that sit above the wire so you can
see them without capturing packets:

  * The 5-tuple that identifies one TCP connection, and how the same
    local socket can host many simultaneous connections.
  * How an application write of N bytes is chopped into segments of at
    most MSS bytes, each labeled with its sequence number.
  * Why TCP is a byte stream: four 512-byte writes may arrive as one
    2048-byte read, four 512-byte reads, or anything in between.
  * The fixed 20-byte TCP header layout and the per-segment byte
    accounting that adds 54 bytes (Ethernet + IP + TCP) around the data.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


IPV4_HEADER_BYTES = 20
TCP_HEADER_BYTES = 20
ETHERNET_HEADER_BYTES = 14
DEFAULT_MSS = 1460
MAX_SEQ_NUMBER = 1 << 32


@dataclass(frozen=True)
class FiveTuple:
    """The five values that uniquely identify one TCP connection."""

    protocol: str
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int

    def label(self) -> str:
        return (
            f"{self.protocol} {self.src_ip}:{self.src_port} "
            f"<-> {self.dst_ip}:{self.dst_port}"
        )


@dataclass(frozen=True)
class Segment:
    """One segment on the wire: sequence number + payload length."""

    seq: int
    payload: bytes

    @property
    def length(self) -> int:
        return len(self.payload)

    @property
    def next_seq(self) -> int:
        return (self.seq + self.length) % MAX_SEQ_NUMBER


def segment_write(data: bytes, mss: int, isn: int) -> list[Segment]:
    """Chop `data` into MSS-sized TCP segments starting at `isn+1`."""
    if mss <= 0:
        raise ValueError("MSS must be positive")
    out: list[Segment] = []
    seq = (isn + 1) % MAX_SEQ_NUMBER
    for start in range(0, len(data), mss):
        chunk = data[start : start + mss]
        out.append(Segment(seq=seq, payload=chunk))
        seq = (seq + len(chunk)) % MAX_SEQ_NUMBER
    return out


def coalesce(writes: list[bytes], mss: int) -> list[Segment]:
    """Concatenate a sequence of writes then segment the combined buffer."""
    merged = b"".join(writes)
    return segment_write(merged, mss, isn=0)


def reassembly_options(stream: bytes, mss: int) -> list[list[int]]:
    """Enumerate how a byte stream may be delivered to the receiver."""
    if len(stream) == 0:
        return [[]]

    def partitions(offset: int) -> list[list[int]]:
        if offset == len(stream):
            return [[]]
        result: list[list[int]] = []
        upper = min(offset + mss, len(stream))
        for end in range(offset + 1, upper + 1):
            for tail in partitions(end):
                result.append([end - offset, *tail])
        return result

    return partitions(0)


def mtu_math(mtu: int) -> dict[str, int]:
    """Decompose a link MTU into IP, TCP, and data bytes."""
    if mtu < IPV4_HEADER_BYTES + TCP_HEADER_BYTES:
        raise ValueError("MTU too small for IP + TCP headers")
    mss = mtu - IPV4_HEADER_BYTES - TCP_HEADER_BYTES
    return {
        "link_mtu": mtu,
        "ethernet_header": ETHERNET_HEADER_BYTES,
        "ipv4_header": IPV4_HEADER_BYTES,
        "tcp_header": TCP_HEADER_BYTES,
        "mss": mss,
        "overhead_bytes": ETHERNET_HEADER_BYTES + IPV4_HEADER_BYTES + TCP_HEADER_BYTES,
        "efficiency_pct": round(mss * 100 / mtu, 2),
    }


def header_layout() -> list[tuple[str, int, str]]:
    """Return the fixed 20-byte TCP header layout (RFC 793)."""
    return [
        ("Source Port", 2, "16-bit port of the sender"),
        ("Destination Port", 2, "16-bit port of the receiver"),
        ("Sequence Number", 4, "32-bit offset of the first data byte"),
        ("Acknowledgement Number", 4, "32-bit next-in-order byte expected"),
        ("Data Offset + Reserved + Flags", 2, "4-bit header length + 12 bits flags"),
        ("Window Size", 2, "16-bit receive window advertisement"),
        ("Checksum", 2, "16-bit ones'-complement over header + data + pseudoheader"),
        ("Urgent Pointer", 2, "16-bit offset of urgent data end (deprecated)"),
    ]


def five_tuple_demo() -> list[FiveTuple]:
    """Two concurrent connections that share the server's listening socket."""
    return [
        FiveTuple("TCP", "10.0.0.2", 49152, "10.0.1.10", 80),
        FiveTuple("TCP", "10.0.0.3", 62011, "10.0.1.10", 80),
        FiveTuple("TCP", "10.0.0.4", 51000, "10.0.1.10", 22),
    ]


def show_segments(segments: list[Segment]) -> None:
    for seg in segments:
        print(
            f"  SEQ={seg.seq:<11}  len={seg.length:<5}  "
            f"next_seq={seg.next_seq}"
        )


def main() -> None:
    print("=" * 70)
    print("TCP SERVICE MODEL  --  byte stream, segments, and the 5-tuple")
    print("=" * 70)

    print("\n[1] The fixed 20-byte TCP header (RFC 793):")
    layout = header_layout()
    width_used = sum(w for _, w, _ in layout)
    assert width_used == TCP_HEADER_BYTES == 20
    for name, width, desc in layout:
        print(f"  {name:<32} {width:>2} byte(s)  --  {desc}")

    print("\n[2] MTU decomposition (Ethernet, MTU=1500):")
    for key, value in mtu_math(1500).items():
        print(f"  {key:<20} = {value}")

    print("\n[3] The 5-tuple: three connections, one listening socket :80")
    for tup in five_tuple_demo():
        print(f"  {tup.label()}")

    print("\n[4] Segmenting one 2,048-byte write (MSS=1,460):")
    payload = (bytes(range(256)) * 8)[:2048]
    segments = segment_write(payload, DEFAULT_MSS, isn=0)
    show_segments(segments)

    print("\n[5] Boundary loss: four 512-byte writes vs one 2,048-byte write")
    four = [b"A" * 512, b"B" * 512, b"C" * 512, b"D" * 512]
    seg_four = coalesce(four, DEFAULT_MSS)
    seg_one = coalesce([b"".join(four)], DEFAULT_MSS)
    print(f"  four writes -> {len(seg_four)} segment(s), "
          f"sizes={[s.length for s in seg_four]}")
    print(f"  one merged  -> {len(seg_one)} segment(s), "
          f"sizes={[s.length for s in seg_one]}")
    print("  identical on the wire: TCP does not preserve write() boundaries")

    print("\n[6] Reassembly options for a 1,024-byte stream delivered over MSS=600:")
    sample = b"x" * 1024
    options = reassembly_options(sample, mss=600)
    print(f"  {len(options)} valid partitions, e.g.:")
    for sizes in options[:6]:
        print(f"    recv() chunk sizes = {sizes}")
    print(f"  ... ({len(options) - 6} more)")

    print("\n[7] Byte accounting for one full 1,460-byte segment on Ethernet:")
    m = mtu_math(1500)
    print(
        f"  Ethernet {m['ethernet_header']} + IPv4 {m['ipv4_header']} + "
        f"TCP {m['tcp_header']} + data {m['mss']} = "
        f"{m['ethernet_header'] + m['ipv4_header'] + m['tcp_header'] + m['mss']} bytes"
    )
    print(
        f"  overhead = {m['overhead_bytes']} bytes "
        f"({100 - m['efficiency_pct']:.2f}% of the frame)"
    )

    print("\nPlan verified. Run `tcpdump -i <iface> -nn -tttt` to see the same numbers live.")


if __name__ == "__main__":
    main()