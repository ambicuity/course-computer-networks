#!/usr/bin/env python3
"""UDP datagram parser, checksum calculator, and wireless-throttling demo.

Stdlib only. Demonstrates four concepts from Sec 6.3.3 and 6.4.1:

1. Parsing the 8-byte UDP header (src/dst port, length, checksum).
2. Computing the IPv4 pseudo-header checksum (RFC 768) over the
   datagram plus the source/destination IP, protocol, and length.
3. Selecting an ephemeral source port in the IANA-reserved range
   49152-65535 (RFC 6335).
4. Estimating the throughput penalty from misclassifying wireless
   transmission errors as congestion, using the Padhye formula.

Run:  python3 main.py
"""
from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# UDP header layout (Sec 6.4.1, RFC 768)
# ---------------------------------------------------------------------------

UDP_HEADER_FMT = "!HHHH"          # src port, dst port, length, checksum
UDP_HEADER_LEN = 8
UDP_MAX_PACKET = 65_535           # full UDP datagram (header + payload)
UDP_MAX_PAYLOAD_IPV4 = 65_507     # 65535 - 8 (header) - 20 (typical IPv4)
PROTOCOL_UDP = 17
EPHEMERAL_PORT_MIN = 49_152
EPHEMERAL_PORT_MAX = 65_535


@dataclass(frozen=True)
class PseudoHeader:
    """IPv4 pseudo-header from RFC 768, used in the UDP checksum."""

    src_ip: str
    dst_ip: str
    protocol: int
    udp_length: int


@dataclass(frozen=True)
class UDPDatagram:
    """Parsed UDP datagram."""

    src_port: int
    dst_port: int
    length: int
    checksum: int
    payload: bytes


# ---------------------------------------------------------------------------
# Checksum implementation (Sec 6.4.1)
# ---------------------------------------------------------------------------

def _parse_ipv4(ip: str) -> bytes:
    return bytes(int(o) for o in ip.split("."))


def build_pseudo_header(src_ip: str, dst_ip: str,
                        protocol: int, udp_length: int) -> bytes:
    """Return the 12-byte IPv4 pseudo-header in network order."""
    return (
        _parse_ipv4(src_ip)
        + _parse_ipv4(dst_ip)
        + struct.pack("!BBH", 0, protocol, udp_length)
    )


def ones_complement_sum(words: list[int]) -> int:
    """Sum a list of 16-bit ints with end-around carry, return 16-bit sum."""
    total = 0
    for w in words:
        total += w
        # End-around carry: fold the high 16 bits back into the low 16.
        total = (total & 0xFFFF) + (total >> 16)
    return total & 0xFFFF


def udp_checksum(src_ip: str, dst_ip: str, udp_header: bytes,
                 payload: bytes) -> int:
    """Compute UDP checksum over header + payload + IPv4 pseudo-header."""
    if len(udp_header) != UDP_HEADER_LEN:
        raise ValueError("UDP header must be exactly 8 bytes")
    udp_length = len(udp_header) + len(payload)
    pseudo = build_pseudo_header(src_ip, dst_ip, PROTOCOL_UDP, udp_length)
    raw = pseudo + udp_header + payload
    # Pad odd-length data with zero byte.
    if len(raw) % 2:
        raw += b"\x00"
    words = list(struct.unpack(f"!{len(raw) // 2}H", raw))
    # Replace checksum field (last 16 bits of the UDP header at offset 12+6) with 0.
    # The header portion occupies bytes pseudo (12) .. pseudo+8; checksum is the 4th word.
    # In our words list, the checksum word is at index len(pseudo)/2 + 3 = 6 + 3 = 9.
    words[6 + 3] = 0
    return (~ones_complement_sum(words)) & 0xFFFF


# ---------------------------------------------------------------------------
# UDP datagram encode / parse
# ---------------------------------------------------------------------------

def encode_udp(src_port: int, dst_port: int, payload: bytes,
               src_ip: str, dst_ip: str,
               compute_checksum: bool = True) -> bytes:
    """Build a UDP datagram (header + payload) with optional checksum."""
    length = UDP_HEADER_LEN + len(payload)
    if length > UDP_MAX_PACKET:
        raise ValueError(f"UDP datagram too long: {length}")
    checksum = 0
    if compute_checksum:
        hdr = struct.pack(UDP_HEADER_FMT, src_port, dst_port, length, 0)
        checksum = udp_checksum(src_ip, dst_ip, hdr, payload)
    return struct.pack(UDP_HEADER_FMT, src_port, dst_port, length, checksum) + payload


def parse_udp(raw: bytes) -> UDPDatagram:
    """Parse a UDP datagram and return a typed UDPDatagram."""
    if len(raw) < UDP_HEADER_LEN:
        raise ValueError(f"UDP datagram too short: {len(raw)} bytes")
    src_port, dst_port, length, checksum = struct.unpack(
        UDP_HEADER_FMT, raw[:UDP_HEADER_LEN]
    )
    if length < UDP_HEADER_LEN:
        raise ValueError(f"UDP length {length} < 8 (header size)")
    if length > UDP_MAX_PACKET:
        raise ValueError(f"UDP length {length} > 65535")
    if length > len(raw):
        raise ValueError(f"UDP length {length} > received {len(raw)}")
    payload = raw[UDP_HEADER_LEN:length]
    return UDPDatagram(src_port, dst_port, length, checksum, payload)


def verify_udp_checksum(raw: bytes, src_ip: str, dst_ip: str) -> bool:
    """Verify a received UDP datagram's checksum in constant time."""
    return udp_checksum(src_ip, dst_ip, raw[:UDP_HEADER_LEN],
                        raw[UDP_HEADER_LEN:]) == 0


# ---------------------------------------------------------------------------
# Ephemeral port allocator (RFC 6335)
# ---------------------------------------------------------------------------

class EphemeralPortPool:
    """In-memory allocator that mimics the kernel's ephemeral port range."""

    def __init__(self, low: int = EPHEMERAL_PORT_MIN,
                 high: int = EPHEMERAL_PORT_MAX) -> None:
        if low > high:
            raise ValueError("empty port range")
        self._in_use: set[int] = set()
        self._low = low
        self._high = high

    def allocate(self) -> int:
        if len(self._in_use) >= (self._high - self._low + 1):
            raise RuntimeError("ephemeral port pool exhausted")
        while True:
            candidate = random.randint(self._low, self._high)
            if candidate not in self._in_use:
                self._in_use.add(candidate)
                return candidate

    def release(self, port: int) -> None:
        self._in_use.discard(port)

    def available(self) -> int:
        return (self._high - self._low + 1) - len(self._in_use)


# ---------------------------------------------------------------------------
# Wireless throttling model (Sec 6.3.3)
# ---------------------------------------------------------------------------

def padhye_tcp_rate(mss: int, rtt: float, loss_rate: float) -> float:
    """Padhye throughput formula: B <= (MSS/RTT) * 1/sqrt(2p/3)."""
    if loss_rate <= 0:
        return float("inf")
    return (mss / rtt) * (1.0 / math.sqrt(2.0 * loss_rate / 3.0))


def timescale_separation_ratio(link_rtx_ms: float, tcp_timer_ms: float) -> float:
    """How many link-layer retransmissions can the TCP timer absorb."""
    return tcp_timer_ms / link_rtx_ms


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def _demo_parse_and_checksum() -> None:
    print("=" * 72)
    print("UDP Header Parse + Checksum Verification")
    print("=" * 72)
    payload = b"hello"
    src_ip, dst_ip = "10.0.0.5", "8.8.8.8"
    src_port, dst_port = 53127, 53  # ephemeral client -> DNS
    raw = encode_udp(src_port, dst_port, payload, src_ip, dst_ip)
    parsed = parse_udp(raw)
    print(f"  Hex datagram     : {raw.hex()}")
    print(f"  Source port      : {parsed.src_port}")
    print(f"  Dest port        : {parsed.dst_port}  (53 = DNS)")
    print(f"  Length           : {parsed.length}  (header + payload)")
    print(f"  Checksum         : 0x{parsed.checksum:04x}")
    print(f"  Payload          : {parsed.payload!r}")
    ok = verify_udp_checksum(raw, src_ip, dst_ip)
    print(f"  Receiver verify  : {'PASS' if ok else 'FAIL'}")
    # Flip one bit and re-verify.
    tampered = bytearray(raw)
    tampered[-1] ^= 0x01
    ok2 = verify_udp_checksum(bytes(tampered), src_ip, dst_ip)
    print(f"  Tampered verify  : {'PASS' if ok2 else 'FAIL (expected)'}")


def _demo_pseudo_header() -> None:
    print()
    print("=" * 72)
    print("IPv4 Pseudo-Header (RFC 768, Fig 6-28)")
    print("=" * 72)
    pseudo = build_pseudo_header("10.0.0.5", "8.8.8.8", PROTOCOL_UDP, 13)
    print("  12 bytes laid out as:")
    print(f"    source IP      : {pseudo[0:4].hex()}  (10.0.0.5)")
    print(f"    destination IP : {pseudo[4:8].hex()}  (8.8.8.8)")
    print(f"    zero/protocol  : {pseudo[8:10].hex()}  (proto 17)")
    print(f"    UDP length     : {pseudo[10:12].hex()}  (= 13)")
    print("  These 6 words are mixed into the UDP checksum before folding.")


def _demo_ephemeral_ports() -> None:
    print()
    print("=" * 72)
    print("Ephemeral Port Allocation (RFC 6335, 49152-65535)")
    print("=" * 72)
    pool = EphemeralPortPool()
    picks = [pool.allocate() for _ in range(5)]
    for p in picks:
        ok = EPHEMERAL_PORT_MIN <= p <= EPHEMERAL_PORT_MAX
        print(f"  allocated port {p}  (in ephemeral range: {ok})")
    print(f"  duplicates in picks: {len(picks) - len(set(picks))}")
    print(f"  pool size remaining: {pool.available()} ports free")


def _demo_wireless_loss_budget() -> None:
    print()
    print("=" * 72)
    print("Wireless Loss vs TCP-Friendly Throughput (Padhye formula)")
    print("=" * 72)
    print(f"  {'Loss rate p':>11}  {'Loss %':>8}  {'Padhye rate (Mbps)':>20}  % of clean")
    mss, rtt = 1460, 0.080
    clean = padhye_tcp_rate(mss, rtt, 1e-7)
    for p in [1e-7, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1]:
        rate = padhye_tcp_rate(mss, rtt, p)
        ratio = (rate / clean) * 100 if clean else 0
        marker = ""
        if p >= 0.01:
            marker = "  <-- common on marginal Wi-Fi"
        print(f"  {p:11.0e}  {p * 100:7.3f}%  {rate * 8 / 1e6:18.2f}  {ratio:6.2f}%{marker}")

    print()
    print("  Timescale separation (Sec 6.3.3):")
    print(f"    802.11 ACK RTT ~1 ms, TCP RTO initial 200 ms -> "
          f"ratio = {timescale_separation_ratio(1, 200):.0f}x")
    print("    The link layer can retry ~200 times before the TCP timer fires.")


def main() -> None:
    _demo_parse_and_checksum()
    _demo_pseudo_header()
    _demo_ephemeral_ports()
    _demo_wireless_loss_budget()


if __name__ == "__main__":
    main()
