"""RTP and RTCP Packet Trace Lab.

A stdlib-only simulation of an RTP/RTCP media session. Generates RTP
packets with realistic headers, simulates network loss/jitter, builds
RTCP Sender Reports (SR) and Receiver Reports (RR), computes jitter
and round-trip time, and produces an annotated trace summary.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

CLOCK_RATE = 8000  # Hz for PCMU voice
SAMPLES_PER_PACKET = 160  # 20ms at 8kHz
NUM_PACKETS = 50
LOSS_RATE = 0.05
JITTER_MEAN_MS = 20
JITTER_STD_MS = 15
RTCP_INTERVAL = 10  # send RTCP every N packets


@dataclass
class RTPPacket:
    """Minimal RTP packet with 12-byte fixed header fields."""
    version: int = 2
    padding: bool = False
    extension: bool = False
    csrc_count: int = 0
    marker: bool = False
    payload_type: int = 0  # PCMU
    sequence_number: int = 0
    timestamp: int = 0
    ssrc: int = 0
    payload: bytes = field(default_factory=bytes)

    def encode_header(self) -> bytes:
        """Pack the 12-byte RTP fixed header."""
        byte0 = (self.version << 6) | (int(self.padding) << 5) | (int(self.extension) << 4) | self.csrc_count
        byte1 = (int(self.marker) << 7) | self.payload_type
        return struct.pack("!BBHII", byte0, byte1, self.sequence_number, self.timestamp, self.ssrc)

    def __str__(self) -> str:
        return (f"V={self.version} PT={self.payload_type} seq={self.sequence_number:5d} "
                f"ts={self.timestamp:8d} ssrc={self.ssrc:#010x} len={len(self.payload)}")


@dataclass
class RTCPReceiverReport:
    """RTCP Receiver Report (type 201) block."""
    ssrc: int
    fraction_lost: int  # 8-bit fixed point (0-255)
    cumulative_lost: int  # 24-bit
    highest_seq: int  # 16-bit + 16-bit cycle
    jitter: int  # 32-bit, in timestamp units
    lsr: int  # 32-bit, NTP timestamp middle bits
    dlsr: int  # 32-bit, delay in 1/65536 seconds


@dataclass
class RTCPSenderReport:
    """RTCP Sender Report (type 200)."""
    ssrc: int
    ntp_msw: int  # NTP timestamp most significant word
    ntp_lsw: int  # NTP timestamp least significant word
    rtp_timestamp: int
    packet_count: int
    octet_count: int


class RTPSender:
    """Generates RTP packets for a media session."""

    def __init__(self, ssrc: int = 0x12345678) -> None:
        self.ssrc = ssrc
        self.seq = 0
        self.timestamp = 0
        self.packets_sent = 0
        self.octets_sent = 0
        self.sr: Optional[RTCPSenderReport] = None

    def send(self, payload_size: int = 20) -> RTPPacket:
        """Create and return the next RTP packet."""
        pkt = RTPPacket(
            payload_type=0,
            sequence_number=self.seq,
            timestamp=self.timestamp,
            ssrc=self.ssrc,
            payload=bytes(payload_size),
        )
        self.seq = (self.seq + 1) & 0xFFFF
        self.timestamp += SAMPLES_PER_PACKET
        self.packets_sent += 1
        self.octets_sent += payload_size
        return pkt

    def send_sr(self) -> RTCPSenderReport:
        """Generate an RTCP Sender Report."""
        sr = RTCPSenderReport(
            ssrc=self.ssrc,
            ntp_msw=int(time.time()) & 0xFFFFFFFF,
            ntp_lsw=random.randint(0, 0xFFFFFFFF),
            rtp_timestamp=self.timestamp,
            packet_count=self.packets_sent,
            octet_count=self.octets_sent,
        )
        self.sr = sr
        return sr


class RTPReceiver:
    """Receives RTP packets and tracks statistics for RTCP reports."""

    def __init__(self, ssrc: int) -> None:
        self.ssrc = ssrc
        self.expected_seq: Optional[int] = None
        self.highest_seq: int = 0
        self.cumulative_lost: int = 0
        self.last_lost: int = 0
        self.last_expected: int = 0
        self.jitter: float = 0.0
        self.last_arrival_time: Optional[float] = None
        self.last_rtp_ts: Optional[int] = None
        self.received_count: int = 0
        self.last_sr_ntp: int = 0
        self.last_sr_recv_time: float = 0.0

    def receive(self, pkt: RTPPacket, arrival_time: float) -> None:
        """Process a received RTP packet and update statistics."""
        self.received_count += 1

        if self.expected_seq is None:
            self.expected_seq = pkt.sequence_number
            self.highest_seq = pkt.sequence_number
        else:
            self.expected_seq += 1
            if pkt.sequence_number > self.highest_seq:
                self.highest_seq = pkt.sequence_number

        # Jitter calculation (RFC 3550)
        if self.last_arrival_time is not None and self.last_rtp_ts is not None:
            arrival_diff = (arrival_time - self.last_arrival_time) * CLOCK_RATE
            ts_diff = pkt.timestamp - self.last_rtp_ts
            d = abs(arrival_diff - ts_diff)
            self.jitter = (self.jitter + (d - self.jitter) / 16.0)

        self.last_arrival_time = arrival_time
        self.last_rtp_ts = pkt.timestamp

    def note_loss(self, count: int) -> None:
        """Record lost packets (detected by gap in sequence numbers)."""
        self.cumulative_lost += count

    def build_rr(self, now: float) -> RTCPReceiverReport:
        """Build an RTCP Receiver Report."""
        total_expected = self.expected_seq if self.expected_seq else 0
        expected_interval = total_expected - self.last_expected
        lost_interval = self.cumulative_lost - self.last_lost
        if expected_interval > 0:
            fraction = min(255, int(256 * lost_interval / expected_interval))
        else:
            fraction = 0
        self.last_expected = total_expected
        self.last_lost = self.cumulative_lost

        # DLSR: delay since last SR received
        if self.last_sr_recv_time > 0:
            dlsr = int((now - self.last_sr_recv_time) * 65536)
        else:
            dlsr = 0

        return RTCPReceiverReport(
            ssrc=self.ssrc,
            fraction_lost=fraction,
            cumulative_lost=self.cumulative_lost,
            highest_seq=self.highest_seq,
            jitter=int(self.jitter),
            lsr=self.last_sr_ntp >> 16,
            dlsr=dlsr,
        )

    def receive_sr(self, sr: RTCPSenderReport, recv_time: float) -> None:
        """Record the arrival of a Sender Report for RTT calculation."""
        self.last_sr_ntp = (sr.ntp_msw << 16) | (sr.ntp_lsw >> 16)
        self.last_sr_recv_time = recv_time


def simulate_network(pkt: RTPPacket, base_time: float, index: int) -> Tuple[Optional[float], bool]:
    """Simulate network delay and loss. Returns (arrival_time_relative_s, was_lost)."""
    if random.random() < LOSS_RATE:
        return (None, True)
    delay = max(5, random.gauss(JITTER_MEAN_MS, JITTER_STD_MS))
    arrival_relative = index * 20.0 + delay  # ms relative to session start
    return (arrival_relative / 1000.0, False)


def main() -> None:
    print("RTP and RTCP Packet Trace Lab\n")
    print(f"Packets: {NUM_PACKETS}, clock: {CLOCK_RATE}Hz, loss: {LOSS_RATE*100:.0f}%")
    print(f"Jitter: mean={JITTER_MEAN_MS}ms, std={JITTER_STD_MS}ms\n")
    random.seed(123)

    sender = RTPSender(ssrc=0x12345678)
    receiver = RTPReceiver(ssrc=0x12345678)

    trace: List[str] = []
    rtt_estimates: List[float] = []
    rr_reports: List[RTCPReceiverReport] = []
    sr_reports: List[RTCPSenderReport] = []

    base_time = time.time()

    print("=== RTP Packet Trace ===")
    print(f"  {'idx':>3}  {'seq':>5}  {'ts':>8}  {'arrival':>10}  {'status':>8}  {'payload':>7}")
    print("  " + "-" * 55)

    for i in range(NUM_PACKETS):
        pkt = sender.send(payload_size=20)

        # Send SR periodically
        if i > 0 and i % RTCP_INTERVAL == 0:
            sr = sender.send_sr()
            sr_reports.append(sr)
            receiver.receive_sr(sr, time.time())
            trace.append(f"  [RTCP SR]  ssrc={sr.ssrc:#010x} pkts={sr.packet_count} octets={sr.octet_count}")

        arrival, lost = simulate_network(pkt, base_time, i)

        if lost:
            receiver.note_loss(1)
            status = "LOST"
            print(f"  {i:3d}  {pkt.sequence_number:5d}  {pkt.timestamp:8d}  {'---':>10}  {status:>8}  {len(pkt.payload):>7}")
            trace.append(f"  RTP seq={pkt.sequence_number} LOST")
        else:
            receiver.receive(pkt, arrival or 0.0)
            status = "OK"
            arrival_ms = (arrival or 0) * 1000
            print(f"  {i:3d}  {pkt.sequence_number:5d}  {pkt.timestamp:8d}  {arrival_ms:10.1f}  {status:>8}  {len(pkt.payload):>7}")
            trace.append(f"  RTP seq={pkt.sequence_number} ts={pkt.timestamp} arrival={arrival_ms:.1f}ms")

        # Send RR periodically
        if i > 0 and i % RTCP_INTERVAL == 0:
            now = time.time()
            rr = receiver.build_rr(now)
            rr_reports.append(rr)
            loss_pct = rr.fraction_lost / 256 * 100
            jitter_ms = rr.jitter / CLOCK_RATE * 1000
            print(f"  [RTCP RR]  frac_lost={loss_pct:.1f}% cum_lost={rr.cumulative_lost} "
                  f"jitter={jitter_ms:.1f}ms lsr={rr.lsr:#010x} dlsr={rr.dlsr}")
            trace.append(f"  [RTCP RR]  frac_lost={loss_pct:.1f}% cum_lost={rr.cumulative_lost} jitter={jitter_ms:.1f}ms")

    print()

    # Session summary
    print("=== Session Summary ===")
    total_lost = receiver.cumulative_lost
    total_expected = NUM_PACKETS
    loss_rate = total_lost / total_expected * 100
    avg_jitter_ms = receiver.jitter / CLOCK_RATE * 1000 if receiver.jitter > 0 else 0

    print(f"  Packets sent:        {sender.packets_sent}")
    print(f"  Packets received:    {receiver.received_count}")
    print(f"  Packets lost:        {total_lost} ({loss_rate:.1f}%)")
    print(f"  Final jitter:        {avg_jitter_ms:.1f} ms ({int(receiver.jitter)} ts units)")
    print(f"  Octets sent:         {sender.octets_sent}")
    print(f"  RTCP SRs sent:       {len(sr_reports)}")
    print(f"  RTCP RRs sent:       {len(rr_reports)}")
    print()

    # RTT estimation from last RR
    if rr_reports and sr_reports:
        last_rr = rr_reports[-1]
        if last_rr.lsr > 0 and last_rr.dlsr > 0:
            rtt = (time.time() - receiver.last_sr_recv_time) * 1000
            rtt_estimates.append(rtt)
            print(f"  Estimated RTT:       {rtt:.1f} ms (from LSR/DLSR exchange)")
    print()

    # Quality assessment
    print("=== Quality Assessment ===")
    if loss_rate < 2:
        quality = "Excellent (toll quality)"
    elif loss_rate < 5:
        quality = "Good"
    elif loss_rate < 10:
        quality = "Fair"
    else:
        quality = "Poor"
    print(f"  Loss-based quality:  {quality}")
    print(f"  Jitter impact:       {'Low' if avg_jitter_ms < 20 else 'Moderate' if avg_jitter_ms < 50 else 'High'}")
    print()

    # Annotated trace excerpt
    print("=== Annotated Trace (first 15 entries) ===")
    for entry in trace[:15]:
        print(entry)
    print("  ...")
    print()

    print("Done. RTP/RTCP trace analysis complete.")


if __name__ == "__main__":
    main()
