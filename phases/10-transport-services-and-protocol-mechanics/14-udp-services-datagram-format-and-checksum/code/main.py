"""UDP service, datagram format, and checksum.

Three stdlib-only parts:

1. udp_checksum() - compute the IPv4 pseudo-header UDP checksum per RFC 768
   + RFC 1071 (ones-complement sum with end-around carry).

2. parse_udp() - slice a raw UDP payload into its four header fields plus
   data, and run the self-consistency check.

3. build_udp() - assemble a valid datagram (or one with checksum=0, or
   one deliberately corrupted for testing).

Run: python3 main.py
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


# --- Constants ----------------------------------------------------------------
UDP_HEADER_LEN = 8
PROTO_UDP = 17
MAX_UDP_LENGTH = 65535


# --- Part 1: checksum ---------------------------------------------------------
def _ones_complement_sum(words: list[int]) -> int:
    """Fold a list of 16-bit words with end-around carry; return 16-bit sum."""
    acc = 0
    for w in words:
        acc += w
        acc = (acc & 0xFFFF) + (acc >> 16)
    return acc & 0xFFFF


def udp_checksum(src_ip: str, dst_ip: str, udp_header_no_cksum: bytes,
                 payload: bytes) -> tuple[int, int]:
    """Compute UDP checksum per RFC 768 / 1071 with IPv4 pseudo-header.

    Returns (checksum, self_check_sum). The self_check_sum is what a
    receiver computes over the full datagram (with checksum field filled
    in); a correct datagram yields 0xFFFF, an incorrect one does not.
    """
    s = bytes(int(o) for o in src_ip.split("."))
    d = bytes(int(o) for o in dst_ip.split("."))
    if len(s) != 4 or len(d) != 4:
        raise ValueError("only IPv4 supported in this lab")

    udp_len = UDP_HEADER_LEN + len(payload)
    pseudo = s + d + struct.pack("!BBH", 0, PROTO_UDP, udp_len)
    body = udp_header_no_cksum + payload
    if len(body) % 2 == 1:
        body += b"\x00"  # RFC 1071 pad to even length
    words = list(struct.unpack(f"!{len(body) // 2}H", body))
    cksum = _ones_complement_sum(
        list(struct.unpack("!8H", pseudo)) + words
    )
    cksum = (~cksum) & 0xFFFF
    if cksum == 0:
        cksum = 0xFFFF  # RFC 768: transmitted checksum is never 0
    return cksum, cksum  # self-check computed in parser, not here


# --- Part 2: parser -----------------------------------------------------------
@dataclass
class ParsedDatagram:
    src_port: int
    dst_port: int
    length: int
    checksum: int
    payload: bytes
    raw: bytes
    self_check_sum: int
    self_check_ok: bool
    checksum_zero: bool

    @property
    def truncated(self) -> bool:
        return self.length > len(self.raw)


def parse_udp(raw: bytes) -> ParsedDatagram:
    """Parse a UDP datagram (no IP header) and run the self-consistency check."""
    if len(raw) < UDP_HEADER_LEN:
        raise ValueError(f"UDP datagram too short: {len(raw)} bytes")
    src, dst, length, cksum = struct.unpack("!HHHH", raw[:UDP_HEADER_LEN])
    payload = raw[UDP_HEADER_LEN:length] if length >= UDP_HEADER_LEN else b""
    # Self-consistency: sum of all 16-bit words == 0xFFFF when valid.
    body = raw[:length]
    if len(body) % 2 == 1:
        body += b"\x00"
    words = list(struct.unpack(f"!{len(body) // 2}H", body))
    s = _ones_complement_sum(words)
    zero = cksum == 0
    return ParsedDatagram(
        src_port=src,
        dst_port=dst,
        length=length,
        checksum=cksum,
        payload=payload,
        raw=raw,
        self_check_sum=s,
        self_check_ok=(s == 0xFFFF) and not zero,
        checksum_zero=zero,
    )


# --- Part 3: builder ----------------------------------------------------------
def build_udp(src_port: int, dst_port: int, payload: bytes,
              src_ip: str = "10.0.0.1", dst_ip: str = "10.0.0.2",
              want_checksum: bool = True,
              corrupt_byte: int | None = None) -> bytes:
    """Build a UDP datagram. Set want_checksum=False for a zero-checksum
    datagram (valid in IPv4). Set corrupt_byte=N to flip a bit in byte N of
    the payload for testing the self-consistency check."""
    if corrupt_byte is not None and 0 <= corrupt_byte < len(payload):
        payload = bytearray(payload)
        payload[corrupt_byte] ^= 0xFF
        payload = bytes(payload)
    header_no_cksum = struct.pack("!HHHH", src_port, dst_port,
                                  UDP_HEADER_LEN + len(payload), 0)
    if want_checksum:
        cksum, _ = udp_checksum(src_ip, dst_ip, header_no_cksum, payload)
    else:
        cksum = 0
    header = struct.pack("!HHHH", src_port, dst_port,
                         UDP_HEADER_LEN + len(payload), cksum)
    return header + payload


# --- Demo ---------------------------------------------------------------------
def demo_checksum_walk() -> None:
    print("=" * 70)
    print("CHECKSUM STEP-BY-STEP (RFC 1071 folding)")
    print("=" * 70)
    payload = b"hello"
    src_ip, dst_ip = "10.0.0.1", "10.0.0.2"
    hdr = struct.pack("!HHHH", 53000, 53, UDP_HEADER_LEN + len(payload), 0)
    s = bytes(int(o) for o in src_ip.split("."))
    d = bytes(int(o) for o in dst_ip.split("."))
    pseudo = s + d + struct.pack("!BBH", 0, PROTO_UDP, UDP_HEADER_LEN + len(payload))
    body = hdr + payload
    print(f"  src_ip={src_ip} dst_ip={dst_ip} payload={payload!r}")
    print(f"  pseudo-header words: " + " ".join(f"{w:04x}" for w in struct.unpack("!8H", pseudo)))
    print(f"  body words:          " + " ".join(f"{w:04x}" for w in struct.unpack(f"!{len(body) // 2}H", body)))


def demo_build_parse() -> None:
    print("\n" + "=" * 70)
    print("BUILD, PARSE, VALIDATE")
    print("=" * 70)
    cases = [
        ("valid",      build_udp(53000, 53, b"hello ethernet",  want_checksum=True,  corrupt_byte=None)),
        ("zero-cksum", build_udp(53000, 53, b"hello ethernet",  want_checksum=False, corrupt_byte=None)),
        ("corrupted",  build_udp(53000, 53, b"hello ethernet",  want_checksum=True,  corrupt_byte=0)),
    ]
    print(f"  {'case':<14s} {'src':>5s} {'dst':>5s} {'len':>5s} {'cksum':>6s} {'self_ok':>8s} {'zero':>6s}")
    for name, raw in cases:
        p = parse_udp(raw)
        print(f"  {name:<14s} {p.src_port:>5d} {p.dst_port:>5d} "
              f"{p.length:>5d} 0x{p.checksum:04x} {str(p.self_check_ok):>8s} {str(p.checksum_zero):>6s}")


def demo_lengths() -> None:
    print("\n" + "=" * 70)
    print("EDGE CASES")
    print("=" * 70)
    print(f"  UDP header size       : {UDP_HEADER_LEN} bytes")
    print(f"  Min datagram length   : {UDP_HEADER_LEN} (no payload)")
    print(f"  Max datagram length   : {MAX_UDP_LENGTH} bytes")
    print(f"  IPv4 MTU (Ethernet)   : 1500 bytes -> 1472 B UDP payload max w/o fragment")
    # Build a max-length datagram and check it parses cleanly.
    payload = b"x" * (MAX_UDP_LENGTH - UDP_HEADER_LEN)
    raw = build_udp(1, 2, payload)
    p = parse_udp(raw)
    print(f"  Max-size parse        : length={p.length}, payload={len(p.payload)} B, self_ok={p.self_check_ok}")


def main() -> None:
    demo_checksum_walk()
    demo_build_parse()
    demo_lengths()
    print("\nDone. Edit `corrupt_byte` in demo_build_parse() to test the receiver.")


if __name__ == "__main__":
    main()
