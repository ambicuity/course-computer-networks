"""Real-Time Transport: RTP (RFC 3550) and RTCP.

Four stdlib-only parts:

1. build_rtp() - assemble a 12-byte RTP header plus optional CSRCs and
   payload; return a byte string.

2. parse_rtp() - decode a byte string into named fields; validates V=2 and
   counts CSRCs.

3. build_sr() / parse_sr() - build and decode a Sender Report, including
   NTP/RTP timestamps and zero or more 24-byte reception report blocks.

4. compute_jitter() - the canonical RFC 3550 interarrival jitter formula,
   in media-clock units.

Run: python3 main.py
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Optional


# --- RTP header (RFC 3550 sec 5.1) -------------------------------------------
RTP_VERSION = 2
PT_PCMU = 0
PT_PCMA = 8
PT_GSM = 3
PT_DYNAMIC_MIN = 96
PT_DYNAMIC_MAX = 127


@dataclass
class RTPPacket:
    version: int
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int
    seq: int
    timestamp: int
    ssrc: int
    csrcs: list[int]
    payload: bytes


def build_rtp(payload_type: int, seq: int, timestamp: int, ssrc: int,
              payload: bytes, marker: bool = False,
              csrcs: Optional[list[int]] = None) -> bytes:
    """Build an RTP packet: 12-byte fixed header + CSRCs + payload."""
    if csrcs is None:
        csrcs = []
    if len(csrcs) > 15:
        raise ValueError("CSRC count max 15")
    byte0 = (RTP_VERSION << 6) | (0 << 5) | (0 << 4) | (len(csrcs) & 0x0F)
    byte1 = ((1 if marker else 0) << 7) | (payload_type & 0x7F)
    header = struct.pack("!BBHII", byte0, byte1, seq & 0xFFFF,
                         timestamp & 0xFFFFFFFF, ssrc & 0xFFFFFFFF)
    csrc_block = b"".join(struct.pack("!I", c & 0xFFFFFFFF) for c in csrcs)
    return header + csrc_block + payload


def parse_rtp(data: bytes) -> RTPPacket:
    """Parse an RTP packet and return named fields."""
    if len(data) < 12:
        raise ValueError(f"RTP too short: {len(data)} bytes")
    byte0, byte1, seq, ts, ssrc = struct.unpack("!BBHII", data[:12])
    ver = (byte0 >> 6) & 0x03
    pad = bool((byte0 >> 5) & 0x01)
    ext = bool((byte0 >> 4) & 0x01)
    cc = byte0 & 0x0F
    marker = bool((byte1 >> 7) & 0x01)
    pt = byte1 & 0x7F
    if ver != RTP_VERSION:
        raise ValueError(f"RTP version {ver} != 2")
    pos = 12
    csrcs: list[int] = []
    for _ in range(cc):
        csrcs.append(struct.unpack_from("!I", data, pos)[0])
        pos += 4
    payload = data[pos:]
    return RTPPacket(ver, pad, ext, cc, marker, pt, seq, ts, ssrc, csrcs, payload)


# --- RTCP Sender Report (RFC 3550 sec 6.4.1) ---------------------------------
PT_SR = 200
PT_RR = 201
PT_SDES = 202
PT_BYE = 203
PT_APP = 204


@dataclass
class ReceptionBlock:
    ssrc: int
    fraction_lost: int
    cumulative_lost: int
    extended_highest_seq: int
    jitter: int
    last_sr: int
    delay_since_last_sr: int


def build_sr(ssrc: int, ntp_ts: int, rtp_ts: int, packet_count: int,
             octet_count: int, blocks: list[ReceptionBlock]) -> bytes:
    rc = len(blocks)
    if rc > 31:
        raise ValueError("max 31 report blocks per SR")
    word0 = (RTP_VERSION << 30) | (0 << 29) | (rc & 0x1F)
    word1 = (PT_SR << 16) | 0  # length filled below
    ntp_hi = (ntp_ts >> 32) & 0xFFFFFFFF
    ntp_lo = ntp_ts & 0xFFFFFFFF
    head = struct.pack("!IIHI", word0, ssrc & 0xFFFFFFFF, ntp_hi, ntp_lo)
    head += struct.pack("!III", rtp_ts & 0xFFFFFFFF, packet_count & 0xFFFFFFFF,
                        octet_count & 0xFFFFFFFF)
    body = b""
    for b in blocks:
        body += struct.pack("!I", b.ssrc & 0xFFFFFFFF)
        fl_cl = ((b.fraction_lost & 0xFF) << 24) | (b.cumulative_lost & 0xFFFFFF)
        body += struct.pack("!I", fl_cl & 0xFFFFFFFF)
        body += struct.pack("!I", b.extended_highest_seq & 0xFFFFFFFF)
        body += struct.pack("!I", b.jitter & 0xFFFFFFFF)
        body += struct.pack("!I", b.last_sr & 0xFFFFFFFF)
        body += struct.pack("!I", b.delay_since_last_sr & 0xFFFFFFFF)
    payload = head + body
    length = (len(payload) // 4) - 1  # in 32-bit words minus 1
    word1 = (PT_SR << 16) | (length & 0xFFFF)
    return struct.pack("!II", word0, ssrc & 0xFFFFFFFF) + payload[8:]


def parse_sr(data: bytes) -> tuple[int, int, int, int, int, list[ReceptionBlock]]:
    if len(data) < 28:
        raise ValueError("SR too short")
    word0, ssrc, ntp_hi, ntp_lo, rtp_ts, pkt_cnt, oct_cnt = struct.unpack_from(
        "!IIIIIII", data, 0)
    rc = word0 & 0x1F
    pos = 28
    blocks: list[ReceptionBlock] = []
    for _ in range(rc):
        if pos + 24 > len(data):
            break
        s, fl_cl, ehs, jit, lsr, dlsr = struct.unpack_from("!IIIIII", data, pos)
        fl = (fl_cl >> 24) & 0xFF
        cl = fl_cl & 0xFFFFFF
        blocks.append(ReceptionBlock(s, fl, cl, ehs, jit, lsr, dlsr))
        pos += 24
    return ssrc, (ntp_hi << 32) | ntp_lo, rtp_ts, pkt_cnt, oct_cnt, blocks


# --- Jitter (RFC 3550 sec 6.4.1) ---------------------------------------------
def compute_jitter(samples: list[tuple[int, int, int]]) -> int:
    """Jitter from (rtp_seq, rtp_ts, arrival_us) tuples. Returns media-clock units.

    The formula: J(i) = J(i-1) + (|D(i-1,i)| - J(i-1)) / 16
    where D = (arrival_i - arrival_{i-1}) - (rtp_ts_i - rtp_ts_{i-1}).
    """
    j = 0
    prev_arrival: Optional[int] = None
    prev_rtp_ts: Optional[int] = None
    for _seq, rtp_ts, arrival in samples:
        if prev_arrival is not None and prev_rtp_ts is not None:
            d = (arrival - prev_arrival) - (rtp_ts - prev_rtp_ts)
            if d < 0:
                d = -d
            j = j + (d - j) // 16
        prev_arrival = arrival
        prev_rtp_ts = rtp_ts
    return j


# --- Demo ---------------------------------------------------------------------
def demo_rtp() -> None:
    print("=" * 70)
    print("RTP PACKET BUILD + PARSE (RFC 3550 sec 5.1)")
    print("=" * 70)
    pkt = build_rtp(payload_type=PT_PCMU, seq=1, timestamp=0,
                    ssrc=0xDEADBEEF, payload=b"\x00" * 160, marker=True)
    print(f"  audio PCMU G.711 packet: {len(pkt)} bytes (12 hdr + 160 payload)")
    print(f"  hex: {pkt[:12].hex()}")
    dec = parse_rtp(pkt)
    print(f"  parsed: V={dec.version} P={dec.padding} X={dec.extension} "
          f"CC={dec.csrc_count} M={dec.marker} PT={dec.payload_type} "
          f"seq={dec.seq} ts={dec.timestamp} ssrc=0x{dec.ssrc:08x}")

    # Video packet with 2 CSRCs
    pkt2 = build_rtp(payload_type=96, seq=42, timestamp=90000,
                     ssrc=0xCAFEF00D, payload=b"\x00" * 500, marker=False,
                     csrcs=[0x11111111, 0x22222222])
    dec2 = parse_rtp(pkt2)
    print(f"\n  video PT=96 dynamic: {len(pkt2)} bytes, {dec2.csrc_count} CSRCs")
    print(f"  parsed: M={dec2.marker} PT={dec2.payload_type} seq={dec2.seq} "
          f"ts={dec2.timestamp} CSRCs={[hex(c) for c in dec2.csrcs]}")


def demo_sdes_cname() -> None:
    print("\n" + "=" * 70)
    print("SDES CNAME — THE PERSISTENT PARTICIPANT IDENTIFIER")
    print("=" * 70)
    ssrc = 0xDEADBEEF
    # Minimal SDES packet: 1 chunk for SSRC with CNAME.
    cname = b"user@host.example"
    sdes_text = struct.pack("!BB", 1, len(cname)) + cname  # type=1 (CNAME)
    # Pad to 4-byte boundary
    sdes_text += b"\x00" * ((4 - (len(sdes_text) % 4)) % 4)
    chunk = struct.pack("!I", ssrc) + sdes_text
    chunk_len = len(chunk)
    # SC = 1 source; 8-bit length in 32-bit words including the header.
    hdr = struct.pack("!BBH", (RTP_VERSION << 6) | 1, PT_SDES,
                      (8 + chunk_len) // 4 - 1)  # length in 32-bit words minus 1
    sdes = hdr + chunk
    print(f"  SDES packet for SSRC=0x{ssrc:08x}, CNAME='{cname.decode()}'")
    print(f"  total length: {len(sdes)} bytes (header 4 + chunk 4+N)")
    print(f"  hex: {sdes.hex()}")


def demo_sr() -> None:
    print("\n" + "=" * 70)
    print("RTCP SENDER REPORT (RFC 3550 sec 6.4.1)")
    print("=" * 70)
    ntp_ts = int(time.time() + 2208988800) << 32  # approx NTP seconds since 1900
    ntp_ts |= 0x12345678
    block = ReceptionBlock(ssrc=0xCAFEF00D, fraction_lost=2,
                           cumulative_lost=20, extended_highest_seq=0x00010042,
                           jitter=320, last_sr=0xE000_0000,
                           delay_since_last_sr=0x0001_0000)
    sr = build_sr(ssrc=0xDEADBEEF, ntp_ts=ntp_ts, rtp_ts=90000,
                  packet_count=100, octet_count=16000, blocks=[block])
    print(f"  SR total: {len(sr)} bytes (28 hdr + 24 block)")
    ssrc, ntp, rtp_ts, pkts, octs, blocks = parse_sr(sr)
    print(f"  parsed: SSRC=0x{ssrc:08x} NTP=0x{ntp:016x} RTP_ts={rtp_ts} "
          f"pkts={pkts} octets={octs}")
    for b in blocks:
        print(f"  report block: SSRC=0x{b.ssrc:08x} frac_lost={b.fraction_lost} "
              f"cum_lost={b.cumulative_lost} jitter={b.jitter}")


def demo_jitter() -> None:
    print("\n" + "=" * 70)
    print("RFC 3550 JITTER (per sec 6.4.1)")
    print("=" * 70)
    # 8 kHz audio, 20 ms packets: rtp_ts delta = 160, arrival delta = 20 ms = 20000 us.
    samples = [
        (1,      0,        1_000_000),
        (2,      160,      1_020_000),
        (3,      320,      1_045_000),   # +5 ms jitter
        (4,      480,      1_060_000),   # back to 20 ms
        (5,      640,      1_080_000),
    ]
    j = compute_jitter(samples)
    print(f"  5-packet sequence with one +5ms glitch")
    print(f"  final jitter (media-clock units, 8 kHz clock) = {j}")
    print(f"  convert to seconds: ~{j / 8000 * 1000:.3f} ms")


def main() -> None:
    demo_rtp()
    demo_sdes_cname()
    demo_sr()
    demo_jitter()
    print("\nDone. Edit `samples` in demo_jitter() to feed a real capture.")


if __name__ == "__main__":
    main()
