"""Real-time Conferencing: VoIP, SIP, RTP sessions, jitter buffer, MOS.

A stdlib-only demonstration of the key mechanisms used in real-time IP
conferencing: the RTP session model (sequence numbers, timestamps, SSRC),
a simple jitter buffer that reorders packets and applies a fixed playout
delay, a packet-loss-concealment placeholder, MOS estimation from packet
loss, and a compact SIP call-flow state machine (INVITE -> 200 OK ->
ACK -> BYE -> 200 OK).

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# RTP session model
# ---------------------------------------------------------------------------

@dataclass
class RTPPacket:
    """A minimal RTP packet header plus opaque payload."""

    version: int
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes = field(default_factory=bytes)
    marker: bool = False

    def encode_header(self) -> bytes:
        """Pack the 12-byte RTP fixed header in network byte order."""
        byte0 = (self.version << 6) | self.payload_type
        byte1 = (int(self.marker) << 7) | self.payload_type
        return struct.pack(
            "!BBHII",
            byte0,
            byte1,
            self.sequence_number,
            self.timestamp,
            self.ssrc,
        )

    def __str__(self) -> str:
        return (
            f"RTP V{self.version} PT={self.payload_type} "
            f"seq={self.sequence_number} ts={self.timestamp} ssrc={self.ssrc:#010x}"
        )


class RTPSession:
    """A unidirectional RTP source that emits numbered packets."""

    def __init__(
        self,
        ssrc: int,
        payload_type: int,
        samples_per_packet: int = 160,
        clock_rate_hz: int = 8000,
    ) -> None:
        self.ssrc: int = ssrc
        self.payload_type: int = payload_type
        self.samples_per_packet: int = samples_per_packet
        self.clock_rate_hz: int = clock_rate_hz
        self.next_seq: int = 0
        self.next_ts: int = 0

    def emit(self, payload_size: int = 20, marker: bool = False) -> RTPPacket:
        """Produce the next RTP packet in the session."""
        pkt = RTPPacket(
            version=2,
            payload_type=self.payload_type,
            sequence_number=self.next_seq,
            timestamp=self.next_ts,
            ssrc=self.ssrc,
            payload=bytes(payload_size),
            marker=marker,
        )
        self.next_seq = (self.next_seq + 1) & 0xFFFF
        self.next_ts += self.samples_per_packet
        return pkt

    def wallclock_ms(self, timestamp: int) -> float:
        """Convert an RTP timestamp to a wall-clock offset in milliseconds."""
        return 1000.0 * timestamp / self.clock_rate_hz


def rtp_session_demo() -> None:
    """Print a short RTP packet sequence from two SSRCs."""
    print("=== RTP session model ===")
    audio = RTPSession(ssrc=0xAABBCCDD, payload_type=0, samples_per_packet=160)
    video = RTPSession(ssrc=0x11223344, payload_type=96, samples_per_packet=3000)
    for _ in range(5):
        print(f"  audio: {audio.emit()}")
    print(f"  video: {video.emit(payload_size=800, marker=True)}")
    print(f"  video: {video.emit(payload_size=800)}")
    print()


# ---------------------------------------------------------------------------
# Jitter buffer
# ---------------------------------------------------------------------------

@dataclass
class JitterBuffer:
    """Reorder packets by RTP sequence number and release them after a delay."""

    playout_delay_ms: float
    clock_rate_hz: int = 8000
    _packets: Dict[int, Tuple[float, RTPPacket]] = field(default_factory=dict)
    _base_time_ms: Optional[float] = None

    def receive(self, packet: RTPPacket, arrival_time_ms: float) -> None:
        """Insert an arriving packet, indexed by sequence number."""
        self._packets[packet.sequence_number] = (arrival_time_ms, packet)

    def playout(
        self,
        now_ms: float,
    ) -> List[Tuple[int, float, str, Optional[RTPPacket]]]:
        """Return packets whose playout time has passed, ordered by seq.

        Each returned entry is (sequence_number, playout_time_ms, status,
        packet_or_None).  Missing sequence numbers are reported as gaps so
        the caller can apply packet-loss concealment.
        """
        if self._base_time_ms is None:
            if not self._packets:
                return []
            first_arrival = min(t for t, _ in self._packets.values())
            self._base_time_ms = first_arrival + self.playout_delay_ms

        ready: List[Tuple[int, float, str, Optional[RTPPacket]]] = []
        if not self._packets:
            return ready

        min_seq = min(self._packets.keys())
        max_seq = max(self._packets.keys())
        for seq in range(min_seq, max_seq + 1):
            if seq not in self._packets:
                # Estimate playout time for a missing packet from its seq.
                playout = self._base_time_ms + 1000.0 * (
                    (seq - min_seq) * 160 / self.clock_rate_hz
                )
                if playout <= now_ms:
                    ready.append((seq, playout, "PLC", None))
                continue
            arrival, pkt = self._packets[seq]
            playout = self._base_time_ms + 1000.0 * (
                (seq - min_seq) * 160 / self.clock_rate_hz
            )
            if playout <= now_ms:
                status = "played" if arrival <= playout else "late (skipped)"
                ready.append((seq, playout, status, pkt))
                del self._packets[seq]
        return ready


def packet_loss_concealment() -> bytes:
    """Return a dummy comfort-noise frame used to fill a lost packet slot."""
    return bytes(20)


def jitter_buffer_demo() -> None:
    """Simulate out-of-order RTP arrival and show the jitter buffer smoothing it."""
    print("=== Jitter buffer (reorder + playout delay) ===")
    random.seed(5)
    session = RTPSession(ssrc=0xDEADBEEF, payload_type=0)
    jb = JitterBuffer(playout_delay_ms=80.0)

    # Generate 8 packets with variable network delay, delivered out of order.
    base_ms = 0.0
    sent: List[Tuple[float, RTPPacket]] = []
    for i in range(8):
        pkt = session.emit()
        delay_ms = random.gauss(40.0, 25.0)  # mean 40 ms, sd 25 ms
        if i == 3:
            delay_ms += 120.0  # one packet is heavily delayed
        sent.append((base_ms + delay_ms, pkt))
    # Drop packet 5 to demonstrate PLC reporting.
    sent = [s for s in sent if s[1].sequence_number != 5]
    # Shuffle to simulate network reordering.
    random.shuffle(sent)

    for arrival, pkt in sent:
        jb.receive(pkt, arrival)
        print(
            f"  recv seq={pkt.sequence_number:3d}  arrival={arrival:7.1f}ms"
        )

    # Advance time and drain the buffer.
    for t in (40.0, 90.0, 150.0, 250.0):
        out = jb.playout(t)
        if out:
            print(f"  playout at t={t:6.1f}ms:")
            for seq, playout, status, pkt in out:
                if pkt is None:
                    print(
                        f"    seq={seq:3d}  playout={playout:7.1f}ms  "
                        f"status={status} (PLC frame {len(packet_loss_concealment())} bytes)"
                    )
                else:
                    print(
                        f"    seq={seq:3d}  playout={playout:7.1f}ms  "
                        f"status={status}"
                    )
    print()


# ---------------------------------------------------------------------------
# MOS from packet loss
# ---------------------------------------------------------------------------

LOSS_TO_MOS: Dict[float, float] = {
    0.0: 4.41,
    1.0: 4.13,
    2.0: 3.88,
    3.0: 3.66,
    4.0: 3.47,
    5.0: 3.29,
    10.0: 2.51,
    15.0: 1.87,
    20.0: 1.35,
    30.0: 0.76,
    50.0: 0.33,
}


def mos_from_loss(packet_loss_percent: float) -> float:
    """Estimate a narrowband MOS score from a packet-loss percentage.

    Uses the E-model style approximation described in ITU-T G.107 / IETF
    literature for PCM-coded VoIP:

        MOS = 4.41 - 0.063 * loss - 0.023 * loss * loss

    The result is clamped to the valid MOS range [1.0, 4.5].
    """
    loss = max(0.0, packet_loss_percent)
    score = 4.41 - 0.063 * loss - 0.023 * loss * loss
    return max(1.0, min(4.5, score))


def mos_demo() -> None:
    """Print MOS values for several packet-loss rates."""
    print("=== MOS from packet loss ===")
    losses = [0.0, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0]
    print(f"  {'loss%':>8}  {'MOS':>6}  quality")
    for loss in losses:
        score = mos_from_loss(loss)
        quality = "toll" if score >= 4.0 else "good" if score >= 3.6 else "fair" if score >= 3.1 else "poor" if score >= 2.0 else "bad"
        print(f"  {loss:8.1f}  {score:6.2f}  {quality}")
    print()


# ---------------------------------------------------------------------------
# SIP call-flow state machine
# ---------------------------------------------------------------------------

SIP_TRANSITIONS: Dict[str, Dict[str, str]] = {
    "IDLE": {"INVITE": "CALLING"},
    "CALLING": {"100 Trying": "PROCEEDING", "180 Ringing": "RINGING", "200 OK": "ESTABLISHED"},
    "PROCEEDING": {"180 Ringing": "RINGING", "200 OK": "ESTABLISHED"},
    "RINGING": {"200 OK": "ESTABLISHED"},
    "ESTABLISHED": {"ACK": "CONFIRMED", "BYE": "TERMINATING"},
    "CONFIRMED": {"BYE": "TERMINATING"},
    "TERMINATING": {"200 OK": "IDLE"},
}


def sip_next_state(current: str, message: str) -> str:
    """Return the next SIP dialog state given the current state and a message."""
    return SIP_TRANSITIONS.get(current, {}).get(message, current)


def sip_call_flow_demo() -> None:
    """Show the classic SIP INVITE/200 OK/ACK/BYE flow as a state machine."""
    print("=== SIP call-flow state machine ===")
    state = "IDLE"
    messages = ["INVITE", "200 OK", "ACK", "BYE", "200 OK"]
    for msg in messages:
        next_state = sip_next_state(state, msg)
        print(f"  {msg:12s}  {state:12s} -> {next_state:12s}")
        state = next_state
    print(f"  final state: {state}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Real-time Conferencing over IP\n")
    rtp_session_demo()
    jitter_buffer_demo()
    mos_demo()
    sip_call_flow_demo()
    print("Done. All demonstrations completed.")


if __name__ == "__main__":
    main()
