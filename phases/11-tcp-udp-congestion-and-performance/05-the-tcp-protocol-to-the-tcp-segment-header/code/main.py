#!/usr/bin/env python3
"""TCP segment header parser with all flags and common options.

Stdlib only. Demonstrates the TCP header from Sec 6.5.4:

1. Full 20-byte header parse: ports, seq, ack, data offset, flags
   (CWR, ECE, URG, ACK, PSH, RST, SYN, FIN), window, checksum, urgent ptr.
2. TCP options: MSS (Maximum Segment Size), SACK-Permitted, SACK blocks,
   Timestamps (TSval/TSecch), Window Scale, and NOP padding.
3. Round-trip encode/decode verification.

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


FLAG_CWR = 0x80
FLAG_ECE = 0x40
FLAG_URG = 0x20
FLAG_ACK = 0x10
FLAG_PSH = 0x08
FLAG_RST = 0x04
FLAG_SYN = 0x02
FLAG_FIN = 0x01

FLAG_NAMES = [
    (FLAG_FIN, "FIN"), (FLAG_SYN, "SYN"), (FLAG_RST, "RST"), (FLAG_PSH, "PSH"),
    (FLAG_ACK, "ACK"), (FLAG_URG, "URG"), (FLAG_ECE, "ECE"), (FLAG_CWR, "CWR"),
]


@dataclass
class TCPOption:
    kind: int
    name: str
    data: bytes

    def encode(self) -> bytes:
        if self.kind in (0, 1):
            return bytes([self.kind])
        return bytes([self.kind, 2 + len(self.data)]) + self.data


@dataclass
class TCPHeader:
    src_port: int = 0
    dst_port: int = 0
    seq: int = 0
    ack: int = 0
    data_offset: int = 5
    flags: int = 0
    window: int = 65535
    checksum: int = 0
    urgent_pointer: int = 0
    options: list[TCPOption] = field(default_factory=list)

    def flag_string(self) -> str:
        parts = [name for bit, name in FLAG_NAMES if self.flags & bit]
        return ",".join(parts) if parts else "NONE"

    def encode(self) -> bytes:
        opts = b"".join(o.encode() for o in self.options)
        pad = (4 - (len(opts) % 4)) % 4
        opts += b"\x00" * pad
        self.data_offset = 5 + len(opts) // 4
        offset_reserved = (self.data_offset << 12) | (self.flags & 0x01FF)
        header = struct.pack(
            "!HHIIHHHH",
            self.src_port, self.dst_port,
            self.seq, self.ack,
            offset_reserved, self.window,
            self.checksum, self.urgent_pointer,
        )
        return header + opts

    @classmethod
    def decode(cls, raw: bytes) -> "TCPHeader":
        if len(raw) < 20:
            raise ValueError("too short for TCP header")
        (sp, dp, seq, ack, off_flags, win, cksum, urg) = struct.unpack("!HHIIHHHH", raw[:20])
        data_offset = (off_flags >> 12) & 0x0F
        flags = off_flags & 0x01FF
        header_bytes = data_offset * 4
        opt_raw = raw[20:header_bytes]
        options = _parse_options(opt_raw)
        return cls(
            src_port=sp, dst_port=dp, seq=seq, ack=ack,
            data_offset=data_offset, flags=flags, window=win,
            checksum=cksum, urgent_pointer=urg, options=options,
        )


def _parse_options(raw: bytes) -> list[TCPOption]:
    options: list[TCPOption] = []
    i = 0
    while i < len(raw):
        kind = raw[i]
        if kind == 0:
            break
        if kind == 1:
            options.append(TCPOption(1, "NOP", b""))
            i += 1
            continue
        if i + 1 >= len(raw):
            break
        length = raw[i + 1]
        data = raw[i + 2:i + length] if length > 2 else b""
        name = _OPTION_NAMES.get(kind, f"Unknown({kind})")
        options.append(TCPOption(kind, name, data))
        i += length if length > 0 else 1
    return options


_OPTION_NAMES = {
    0: "END", 1: "NOP", 2: "MSS", 3: "WScale", 4: "SACK-Perm",
    5: "SACK", 8: "Timestamps",
}


def build_mss_option(mss: int) -> TCPOption:
    return TCPOption(2, "MSS", struct.pack("!H", mss))


def build_window_scale_option(shift: int) -> TCPOption:
    return TCPOption(3, "WScale", bytes([shift]))


def build_sack_permitted_option() -> TCPOption:
    return TCPOption(4, "SACK-Perm", b"")


def build_sack_option(blocks: list[tuple[int, int]]) -> TCPOption:
    data = b""
    for left, right in blocks:
        data += struct.pack("!II", left, right)
    return TCPOption(5, "SACK", data)


def build_timestamp_option(tsval: int, tsecch: int) -> TCPOption:
    return TCPOption(8, "Timestamps", struct.pack("!II", tsval, tsecch))


def parse_sack_blocks(data: bytes) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    for i in range(0, len(data), 8):
        left, right = struct.unpack("!II", data[i:i + 8])
        blocks.append((left, right))
    return blocks


def parse_timestamp(data: bytes) -> tuple[int, int]:
    tsval, tsecch = struct.unpack("!II", data[:8])
    return tsval, tsecch


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("TCP Header Field-by-Field (Fig 6-36)")
    print("=" * 70)
    hdr = TCPHeader(
        src_port=54321, dst_port=443, seq=1000, ack=5001,
        flags=FLAG_ACK | FLAG_PSH, window=32768, checksum=0xABCD,
    )
    raw = hdr.encode()
    print(f"  src_port      = {hdr.src_port}")
    print(f"  dst_port      = {hdr.dst_port}")
    print(f"  seq           = {hdr.seq}")
    print(f"  ack           = {hdr.ack}")
    print(f"  data_offset   = {hdr.data_offset} ({hdr.data_offset * 4} bytes)")
    print(f"  flags         = 0x{hdr.flags:02X} ({hdr.flag_string()})")
    print(f"  window        = {hdr.window}")
    print(f"  checksum      = 0x{hdr.checksum:04X}")
    print(f"  urgent_ptr    = {hdr.urgent_pointer}")
    print(f"  raw ({len(raw)} bytes)  = {raw.hex()}")

    parsed = TCPHeader.decode(raw)
    print(f"\n  Round-trip verification:")
    print(f"    ports:  {parsed.src_port == hdr.src_port and parsed.dst_port == hdr.dst_port}")
    print(f"    seq/ack: {parsed.seq == hdr.seq and parsed.ack == hdr.ack}")
    print(f"    flags:  {parsed.flags == hdr.flags} ({parsed.flag_string()})")
    print(f"    window: {parsed.window == hdr.window}")

    print()
    print("=" * 70)
    print("TCP Flags (8 one-bit flags)")
    print("=" * 70)
    test_flags = [
        (FLAG_SYN, "SYN", "Connection request"),
        (FLAG_SYN | FLAG_ACK, "SYN,ACK", "Connection accepted"),
        (FLAG_ACK, "ACK", "Acknowledgement number valid"),
        (FLAG_PSH | FLAG_ACK, "PSH,ACK", "Push data immediately"),
        (FLAG_FIN | FLAG_ACK, "FIN,ACK", "No more data to send"),
        (FLAG_RST, "RST", "Reset connection abruptly"),
        (FLAG_URG | FLAG_ACK, "URG,ACK", "Urgent pointer in use"),
        (FLAG_ECE | FLAG_ACK, "ECE,ACK", "ECN-Echo: slow down"),
        (FLAG_CWR | FLAG_ACK, "CWR,ACK", "Congestion Window Reduced"),
    ]
    for flags, label, desc in test_flags:
        h = TCPHeader(flags=flags)
        print(f"  0x{flags:02X}  {label:>12}  {desc}")

    print()
    print("=" * 70)
    print("TCP Options (Type-Length-Value encoding)")
    print("=" * 70)
    hdr_opts = TCPHeader(
        src_port=50000, dst_port=80, seq=0, ack=0,
        flags=FLAG_SYN, window=64240,
        options=[
            build_mss_option(1460),
            build_sack_permitted_option(),
            build_window_scale_option(7),
            build_timestamp_option(1000000, 0),
            TCPOption(1, "NOP", b""),
            TCPOption(1, "NOP", b""),
        ],
    )
    raw_opts = hdr_opts.encode()
    parsed_opts = TCPHeader.decode(raw_opts)
    print(f"  SYN segment with {len(parsed_opts.options)} options:")
    print(f"  data_offset={parsed_opts.data_offset} ({parsed_opts.data_offset * 4} header bytes)")
    for opt in parsed_opts.options:
        if opt.kind == 2:
            mss = struct.unpack("!H", opt.data)[0]
            print(f"    MSS        kind={opt.kind} len={2 + len(opt.data)}  mss={mss}")
        elif opt.kind == 3:
            shift = opt.data[0]
            print(f"    WScale     kind={opt.kind} len={2 + len(opt.data)}  shift={shift}"
                  f"  (max window = 64240 * 2^{shift} = {64240 * (2 ** shift)})")
        elif opt.kind == 4:
            print(f"    SACK-Perm  kind={opt.kind} len=2  (selective ACK permitted)")
        elif opt.kind == 5:
            blocks = parse_sack_blocks(opt.data)
            print(f"    SACK       kind={opt.kind} len={2 + len(opt.data)}  blocks={blocks}")
        elif opt.kind == 8:
            tsval, tsecch = parse_timestamp(opt.data)
            print(f"    Timestamps kind={opt.kind} len=10  TSval={tsval} TSecch={tsecch}")
        elif opt.kind == 1:
            print(f"    NOP        kind={opt.kind}  (padding)")
        else:
            print(f"    {opt.name:<10} kind={opt.kind} data={opt.data.hex()}")

    print()
    print("=" * 70)
    print("SACK Option: Selective Acknowledgement (Fig 6-48)")
    print("=" * 70)
    print("  Receiver got packets 1, 3-4, 6 but lost 2 and 5:")
    print("  cumulative ACK = 1 (next expected byte after packet 1)")
    sack_hdr = TCPHeader(
        ack=1000, flags=FLAG_ACK,
        options=[build_sack_option([(3000, 5000), (6000, 7000)])],
    )
    raw_sack = sack_hdr.encode()
    parsed_sack = TCPHeader.decode(raw_sack)
    for opt in parsed_sack.options:
        if opt.kind == 5:
            blocks = parse_sack_blocks(opt.data)
            print(f"  SACK blocks: {blocks}")
            print(f"    Block 1: bytes {blocks[0][0]}-{blocks[0][1]} (packets 3-4 received)")
            print(f"    Block 2: bytes {blocks[1][0]}-{blocks[1][1]} (packet 6 received)")
            print("  Sender should retransmit packets 2 and 5.")


if __name__ == "__main__":
    main()