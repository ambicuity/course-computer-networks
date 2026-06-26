#!/usr/bin/env python3
"""TCP segment header packer, decoder, and checksum calculator.

Builds and inspects 20-byte TCP headers (RFC 793), names every flag
bit, walks TCP option TLVs, and computes the 16-bit Internet
checksum (RFC 1071) over pseudo-header + TCP header + payload.
Pure stdlib -- runs anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

TCP_HEADER_BYTES = 20
FLAG_NAMES = ("FIN", "SYN", "RST", "PSH", "ACK", "URG", "ECE", "CWR")

TCP_OPT_EOL = 0
TCP_OPT_NOP = 1
TCP_OPT_MSS = 2
TCP_OPT_WSCALE = 3
TCP_OPT_SACK_PERMITTED = 4


@dataclass(frozen=True)
class TcpHeader:
    """The fixed 20-byte TCP header, no options."""

    src_port: int
    dst_port: int
    seq: int
    ack: int
    data_offset_words: int
    flags: int
    window: int
    urgent: int

    def pack(self) -> bytes:
        for name, value, hi in (
            ("src_port", self.src_port, 0xFFFF), ("dst_port", self.dst_port, 0xFFFF),
            ("seq", self.seq, 0xFFFFFFFF), ("ack", self.ack, 0xFFFFFFFF),
            ("flags", self.flags, 0xFF), ("window", self.window, 0xFFFF),
            ("urgent", self.urgent, 0xFFFF),
        ):
            if not 0 <= value <= hi:
                raise ValueError(f"{name} out of range")
        if not 5 <= self.data_offset_words <= 15:
            raise ValueError("data_offset must be 5..15")
        o = (self.data_offset_words << 4) & 0xF0
        s, d, q, w, u = self.src_port, self.dst_port, self.seq, self.window, self.urgent
        a = self.ack
        return bytes([
            s>>8, s&0xFF, d>>8, d&0xFF,
            q>>24, q>>16, q>>8, q&0xFF,
            a>>24, a>>16, a>>8, a&0xFF,
            o, self.flags & 0xFF, w>>8, w&0xFF, 0, 0, u>>8, u&0xFF,
        ])


def decode_flags(flag_byte: int) -> list[str]:
    return [name for i, name in enumerate(FLAG_NAMES) if (flag_byte >> i) & 1]


def flag_byte_from_names(*names: str) -> int:
    value = 0
    for name in names:
        if name not in FLAG_NAMES:
            raise ValueError(f"unknown flag {name!r}")
        value |= 1 << FLAG_NAMES.index(name)
    return value


def decode_header(raw: bytes) -> dict[str, int | list[str]]:
    if len(raw) < TCP_HEADER_BYTES:
        raise ValueError("header shorter than 20 bytes")
    offset_byte = raw[12]
    flags_byte = raw[13]
    data_offset = (offset_byte >> 4) & 0x0F
    return {
        "src_port": (raw[0] << 8) | raw[1],
        "dst_port": (raw[2] << 8) | raw[3],
        "seq": int.from_bytes(raw[4:8], "big"),
        "ack": int.from_bytes(raw[8:12], "big"),
        "data_offset_words": data_offset,
        "header_bytes": data_offset * 4,
        "reserved_low_nibble": offset_byte & 0x0F,
        "flags": flags_byte,
        "flag_names": decode_flags(flags_byte),
        "window": (raw[14] << 8) | raw[15],
        "checksum": (raw[16] << 8) | raw[17],
        "urgent": (raw[18] << 8) | raw[19],
    }


def consumed_sequence(flag_names: list[str]) -> int:
    return 1 if ("SYN" in flag_names or "FIN" in flag_names) else 0


def ones_complement_add(a: int, b: int) -> int:
    s = a + b
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return s & 0xFFFF


def internet_checksum(pseudo_header: bytes, header: bytes, payload: bytes) -> int:
    def sum_words(buf: bytes) -> int:
        if len(buf) % 2:
            buf = buf + b"\x00"
        total = 0
        for i in range(0, len(buf), 2):
            total = ones_complement_add(total, (buf[i] << 8) | buf[i + 1])
        return total
    total = sum_words(pseudo_header)
    total = ones_complement_add(total, sum_words(header))
    total = ones_complement_add(total, sum_words(payload))
    return (~total) & 0xFFFF


def make_pseudo_header(src_ip: str, dst_ip: str, tcp_length: int) -> bytes:
    q = lambda a: bytes(int(o) for o in a.split("."))
    return q(src_ip) + q(dst_ip) + bytes([0, 6]) + tcp_length.to_bytes(2, "big")


def encode_options(*options: tuple[int, bytes]) -> bytes:
    out = bytearray()
    for kind, value in options:
        if kind in (TCP_OPT_EOL, TCP_OPT_NOP):
            out.append(kind)
        else:
            out.append(kind)
            out.append(len(value) + 2)
            out.extend(value)
    while len(out) % 4:
        out.append(TCP_OPT_NOP)
    return bytes(out)


def decode_options(raw: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    i = 0
    while i < len(raw):
        kind = raw[i]
        if kind == TCP_OPT_EOL:
            out.append(("EOL", b"")); break
        if kind == TCP_OPT_NOP:
            out.append(("NOP", b"")); i += 1; continue
        length = raw[i + 1]
        out.append((f"OPT-{kind}", raw[i + 2 : i + length])); i += length
    return out


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)

def main() -> None:
    print("=" * 70)
    print("TCP SEGMENT HEADER  --  flags, data offset, options, checksum")
    print("=" * 70)

    print("\n[1] Flag byte -> named flags (LSB = FIN):")
    for fb, label in (
        (0x02, "SYN"),
        (0x12, "SYN + ACK"),
        (0x10, "pure ACK"),
        (0x18, "ACK + PSH (data)"),
        (0x14, "ACK + FIN (close)"),
        (0x04, "RST (abort)"),
        (0xC0, "CWR + ECE (ECN)"),
    ):
        flags = decode_flags(fb)
        print(f"   0x{fb:02x} -> {','.join(flags):<28} {label}")

    print("\n[2] Pack and decode a SYN:")
    syn = TcpHeader(45000, 80, 1000, 0, 5, flag_byte_from_names("SYN"), 65535, 0)
    syn_raw = syn.pack()
    print(f"   packed  : {hexdump(syn_raw)}")
    decoded = decode_header(syn_raw)
    print(f"   decoded : seq={decoded['seq']}, flags={decoded['flag_names']}, "
          f"data_offset={decoded['data_offset_words']}w, hdr={decoded['header_bytes']}B")
    print(f"   SYN consumes seq space: {consumed_sequence(decoded['flag_names'])} byte")

    print("\n[3] Pack and decode a SYN-ACK:")
    synack = TcpHeader(80, 45000, 5000, 1001, 5, flag_byte_from_names("SYN", "ACK"), 65535, 0)
    synack_raw = synack.pack()
    decoded = decode_header(synack_raw)
    print(f"   packed  : {hexdump(synack_raw)}")
    print(f"   decoded : seq={decoded['seq']}, ack={decoded['ack']}, flags={decoded['flag_names']}")

    print("\n[4] Internet checksum over a SYN packet:")
    pseudo = make_pseudo_header("10.0.0.1", "10.0.0.2", len(syn_raw))
    cksum = internet_checksum(pseudo, syn_raw, b"")
    print(f"   pseudo-header : {hexdump(pseudo)}")
    print(f"   tcp header    : {hexdump(syn_raw)}")
    print(f"   computed cksum: 0x{cksum:04x}")

    print("\n[5] A SYN carrying MSS=1460, Window Scale=7, SACK permitted:")
    opts = encode_options(
        (TCP_OPT_MSS, (1460).to_bytes(2, "big")),
        (TCP_OPT_NOP, b""), (TCP_OPT_WSCALE, bytes([7])),
        (TCP_OPT_SACK_PERMITTED, b""),
    )
    print(f"   options raw : {hexdump(opts)} ({len(opts)} bytes)")
    for name, value in decode_options(opts):
        print(f"     {name:<10} -> {value.hex()}")
    words = 5 + len(opts) // 4
    print(f"   data offset : {words} words -> {words * 4} header bytes")

    print("\n[6] Decode a real-world-style hex dump:")
    raw_hex = (bytes.fromhex("b400005000000001000000002502ffff0000000000") + b"\x00" * 20)[:20]
    decoded = decode_header(raw_hex)
    print(f"   raw       : {hexdump(raw_hex)}")
    print(f"   src_port  : {decoded['src_port']}    dst_port  : {decoded['dst_port']}")
    print(f"   seq       : {decoded['seq']}    ack       : {decoded['ack']}")
    print(f"   data_off  : {decoded['data_offset_words']}w ({decoded['header_bytes']}B)")
    print(f"   flags     : {decoded['flag_names']}    window    : {decoded['window']}")

    print("\nDone. Decode your own captures with decode_header().")


if __name__ == "__main__":
    main()