"""IPsec AH (RFC 4302) packet builder and verifier.

We model a SecurityAssociation, build an AH-protected IPv4 packet in
either transport or tunnel mode, and verify the ICV on the receiver
side. The ICV is computed over the IP pseudo-header (with mutable fields
zeroed) plus the AH header (excluding the ICV field itself) plus the
payload. HMAC-SHA-256 truncated to 128 bits is the default algorithm.
"""

from __future__ import annotations

import hmac
import hashlib
import struct
from dataclasses import dataclass


# Algorithm registry: name -> (hash constructor, icv_length in bytes).
ALGORITHMS = {
    "hmac-sha256-128": (hashlib.sha256, 16),
    "hmac-sha256":     (hashlib.sha256, 32),
    "hmac-sha512":     (hashlib.sha512, 64),
    "hmac-md5-96":     (hashlib.md5, 12),
}

NEXT_HEADER_IPV4 = 4   # IP-in-IP tunnel mode inner
NEXT_HEADER_TCP = 6
NEXT_HEADER_UDP = 17
NEXT_HEADER_ICMP = 1


@dataclass
class SecurityAssociation:
    spi: int
    src: str
    dst: str
    algorithm: str
    key: bytes
    seq: int = 1
    replay_window: int = 32


def _icv_length(algorithm: str) -> int:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unsupported algorithm: {algorithm}")
    return ALGORITHMS[algorithm][1]


def _ip_pseudo_for_icv(ip_header: bytes) -> bytes:
    """RFC 4302 §3.3.2.1: zero mutable fields (Total Length, Flags/Frag,
    Header Checksum) and pass the rest through unchanged."""
    if len(ip_header) < 20 or ip_header[0] >> 4 != 4:
        raise ValueError("expected IPv4 header")
    buf = bytearray(ip_header)
    buf[2:4] = b"\x00\x00"        # Total Length
    buf[6:8] = b"\x00\x00"        # Flags + Fragment Offset
    buf[10:12] = b"\x00\x00"      # Header Checksum
    return bytes(buf)


def _hmac(algorithm: str, key: bytes, msg: bytes) -> bytes:
    constructor, length = ALGORITHMS[algorithm]
    return hmac.new(key, msg, constructor).digest()[:length]


def build_ah_packet(
    sa: SecurityAssociation,
    inner_packet: bytes,
    next_header: int,
    mode: str = "transport",
    inner_ip_header: bytes = b"",
) -> bytes:
    """Build an AH-protected packet.

    Transport mode: inner_packet is the transport segment; ah sits
    between outer IP and inner_packet. The outer IP header is supplied
    as inner_ip_header when mode='transport'; in tunnel mode, the
    inner packet already includes its own IP header.
    """
    icv_len = _icv_length(sa.algorithm)
    payload_len_field = (4 + icv_len) // 4 - 2  # in 32-bit words minus 2
    ah_header = struct.pack(
        ">BBHII",
        next_header,
        payload_len_field & 0xFF,
        0,
        sa.spi & 0xFFFFFFFF,
        sa.seq & 0xFFFFFFFF,
    )
    # ICV computation: pseudo-header || AH without ICV || payload
    pseudo_src = _ip_pseudo_for_icv(inner_ip_header)
    region = pseudo_src + ah_header + inner_packet
    icv = _hmac(sa.algorithm, sa.key, region)
    return ah_header + icv + inner_packet


def verify_ah_packet(
    sa: SecurityAssociation,
    packet: bytes,
    outer_ip_header: bytes = b"",
    window: set[int] | None = None,
) -> tuple[bool, str]:
    """Verify an AH packet and update anti-replay state.

    Returns (ok, reason). Mutable fields in `outer_ip_header` are zeroed
    for ICV computation, matching the sender's pseudo-header.
    """
    icv_len = _icv_length(sa.algorithm)
    if len(packet) < 12 + icv_len:
        return False, "packet shorter than AH header + ICV"
    next_header, payload_len_field, _reserved, spi, seq = struct.unpack(
        ">BBHII", packet[:12]
    )
    if spi != sa.spi:
        return False, f"spi mismatch ({spi:#x} != {sa.spi:#x})"
    if seq < sa.seq - sa.replay_window:
        return False, f"sequence number {seq} outside replay window"
    if window is not None and seq in window:
        return False, f"sequence number {seq} already received"
    pseudo_src = _ip_pseudo_for_icv(outer_ip_header)
    region = pseudo_src + packet[:12] + packet[12 + icv_len:]
    expected_icv = _hmac(sa.algorithm, sa.key, region)
    received_icv = packet[12:12 + icv_len]
    if not hmac.compare_digest(expected_icv, received_icv):
        return False, "ICV mismatch"
    return True, "ok"


def main() -> None:
    """Run a build-verify-tamper cycle."""
    sa = SecurityAssociation(
        spi=0xC0FFEE, src="10.0.0.1", dst="10.0.0.2",
        algorithm="hmac-sha256-128", key=b"k" * 32, seq=1,
    )
    inner_ip_header = bytes.fromhex(
        "45000020000040004006" + "0000" + "0a000001" + "0a000002"
    )
    payload = b"GET / HTTP/1.1\r\n\r\n"
    pkt = build_ah_packet(sa, payload, next_header=NEXT_HEADER_TCP,
                          mode="transport", inner_ip_header=inner_ip_header)
    ok, reason = verify_ah_packet(sa, pkt, outer_ip_header=inner_ip_header)
    print(f"verify ok: {ok}  reason: {reason}")
    # Tamper with the payload.
    tampered = bytearray(pkt)
    tampered[-1] ^= 0xFF
    ok2, reason2 = verify_ah_packet(sa, bytes(tampered),
                                     outer_ip_header=inner_ip_header)
    print(f"verify tampered ok: {ok2}  reason: {reason2}")
    # Anti-replay: replay with seq=1 again.
    seen: set[int] = set()
    ok3, reason3 = verify_ah_packet(sa, pkt, outer_ip_header=inner_ip_header,
                                     window=seen)
    seen.add(1)
    ok4, reason4 = verify_ah_packet(sa, pkt, outer_ip_header=inner_ip_header,
                                     window=seen)
    print(f"first ok={ok3} reason={reason3}; replay ok={ok4} reason={reason4}")


if __name__ == "__main__":
    main()