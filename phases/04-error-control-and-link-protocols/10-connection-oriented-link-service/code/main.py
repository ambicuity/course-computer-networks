#!/usr/bin/env python3
"""Connection-oriented data link service — three-phase simulator.

Models a stop-and-wait connection-oriented link (HDLC/LAPB style) over an
unreliable channel. Demonstrates the three phases a connection-oriented
transfer goes through:

  1. Connection establishment  (SABM / UA)   -> init V(S), V(R), buffers
  2. Data transfer             (I-frames)    -> sequenced, ACKed, retransmitted
  3. Connection release        (DISC / UA)   -> free state

Run with plain `python3 main.py`. No third-party packages, no network.

The simulator injects a dropped ACK and a dropped data frame so you can watch
the sequence number, the retransmission timer (RTO), and the duplicate-discard
logic do their jobs -- the receiver delivers each frame exactly once, in order,
even when frames or ACKs vanish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Frame model
# ---------------------------------------------------------------------------

# Frame kinds, named after HDLC frame-type categories.
I_FRAME = "I"      # Information frame: carries data + piggyback N(R)
RR = "RR"          # Receiver Ready: positive ACK (supervisory)
SABM = "SABM"      # Set Asynchronous Balanced Mode: connection request (U)
UA = "UA"          # Unnumbered Acknowledgment: reply to SABM / DISC (U)
DISC = "DISC"      # Disconnect: connection release request (U)


@dataclass
class Frame:
    """A single link-layer frame on the wire.

    For I-frames, `seq` is N(S) (send sequence) and `ack` is N(R) (the next
    frame the sender expects -- a piggybacked ACK). For supervisory/numbered
    frames, `ack` carries N(R) and `seq` is None.
    """
    kind: str
    seq: Optional[int] = None
    ack: Optional[int] = None
    data: Optional[bytes] = None

    def label(self) -> str:
        parts = [self.kind]
        if self.seq is not None:
            parts.append(f"N(S)={self.seq}")
        if self.ack is not None:
            parts.append(f"N(R)={self.ack}")
        if self.data is not None:
            parts.append(f"payload={self.data!r}")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Unreliable channel: delivers in order but silently drops chosen wire indices.
# ---------------------------------------------------------------------------

@dataclass
class Channel:
    """Delivers frames in order but silently drops any whose wire-index is in
    `drop_on_wire`. Each transmission gets a fresh wire index so losses can be
    injected at precise points in the trace."""
    drop_on_wire: set = field(default_factory=set)
    _next_wire: int = 0
    log: List[str] = field(default_factory=list)

    def transmit(self, frame: Frame, direction: str) -> Optional[Frame]:
        wire = self._next_wire
        self._next_wire += 1
        if wire in self.drop_on_wire:
            self.log.append(f"  [wire #{wire}] DROPPED {direction} {frame.label()}")
            return None
        self.log.append(f"  [wire #{wire}] {direction} {frame.label()}")
        return frame


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@dataclass
class LinkEndpoint:
    name: str
    peer: Optional["LinkEndpoint"] = None
    channel: Optional[Channel] = None
    # Connection state -- the whole point of phase 1.
    connected: bool = False
    vs: int = 0          # V(S): send state variable
    vr: int = 0          # V(R): receive state variable
    delivered: List[bytes] = field(default_factory=list)  # handed to network layer
    rto_count: int = 0   # how many timeouts fired
    peer_ack_queue: List[Optional[Frame]] = field(default_factory=list)

    # ---- Phase 1: connection establishment --------------------------------
    def connect(self) -> bool:
        """Send SABM, wait for UA. On UA both sides init V(S)=V(R)=0."""
        print(f"[{self.name}] phase 1: ESTABLISH -> send SABM (P=1)")
        self.channel.transmit(Frame(SABM), f"{self.name}->{self.peer.name}")
        # Peer receives SABM, inits state, replies UA.
        self.peer._on_sabm()
        # UA assumed to arrive (timer omitted for the control exchange).
        self.vs, self.vr = 0, 0
        self.connected = True
        print(f"[{self.name}] ESTABLISHED: V(S)={self.vs} V(R)={self.vr} buffers allocated")
        return True

    def _on_sabm(self) -> None:
        if not self.connected:
            self.vs, self.vr = 0, 0
            self.connected = True
            print(f"[{self.name}] received SABM -> init V(S)=0 V(R)=0, reply UA (F=1)")
            self.channel.transmit(Frame(UA), f"{self.name}->{self.peer.name}")

    # ---- Phase 2: data transfer (stop-and-wait) ---------------------------
    def send(self, payload: bytes) -> None:
        """Send one I-frame, wait for ACK; retransmit on RTO until ACKed."""
        seq = self.vs
        attempt = 0
        while True:
            attempt += 1
            frame = Frame(I_FRAME, seq=seq, ack=self.vr, data=payload)
            print(f"[{self.name}] phase 2: send {frame.label()} (attempt {attempt})")
            delivered = self.channel.transmit(frame, f"{self.name}->{self.peer.name}")
            if delivered is not None:
                self.peer._on_iframe(delivered)
            # Wait for an ACK. If the peer's RR is dropped, the timer fires.
            acked = self._await_ack(seq)
            if acked:
                self.vs ^= 1  # 1-bit sequence number advances 0->1->0
                return
            # RTO fired: retransmit the same sequence number.
            self.rto_count += 1
            print(f"[{self.name}] RTO fired -> retransmit seq={seq}")

    def _await_ack(self, expected_seq: int) -> bool:
        """Pull the next ACK the peer queued. If none (dropped), RTO."""
        ack = self.peer_ack_queue.pop(0) if self.peer_ack_queue else None
        if ack is None:
            return False  # timer fires
        print(f"[{self.name}] received {ack.label()}")
        return ack.ack == (expected_seq ^ 1)  # ACK N(R) = next expected

    def _on_iframe(self, frame: Frame) -> None:
        # Duplicate detection by sequence number -- the heart of exactly-once.
        if frame.seq == self.vr:
            print(f"[{self.name}] accept seq={frame.seq}, deliver to network layer, V(R)->{self.vr ^ 1}")
            self.delivered.append(frame.data)
            self.vr ^= 1
        else:
            print(f"[{self.name}] DUPLICATE seq={frame.seq} (expected {self.vr}) -> discard, re-ACK")
        # Piggyback-less: send a supervisory RR with N(R)=new V(R).
        ack = Frame(RR, ack=self.vr)
        self.peer.peer_ack_queue.append(
            self.channel.transmit(ack, f"{self.name}->{self.peer.name}")
        )

    # ---- Phase 3: connection release --------------------------------------
    def release(self) -> None:
        print(f"[{self.name}] phase 3: RELEASE -> send DISC (P=1)")
        self.channel.transmit(Frame(DISC), f"{self.name}->{self.peer.name}")
        self.peer._on_disc()
        self.connected = False
        print(f"[{self.name}] RELEASED: V(S)={self.vs} V(R)={self.vr} buffers freed")

    def _on_disc(self) -> None:
        print(f"[{self.name}] received DISC -> free buffers, reply UA (F=1)")
        self.channel.transmit(Frame(UA), f"{self.name}->{self.peer.name}")
        self.connected = False


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("Connection-oriented data link service -- three phases")
    print("Stop-and-wait, 1-bit sequence number, HDLC-style frame types.")
    print("=" * 72)

    channel = Channel()
    a = LinkEndpoint(name="A", channel=channel)
    b = LinkEndpoint(name="B", channel=channel)
    a.peer, b.peer = b, a

    # ---- Phase 1 -----------------------------------------------------------
    print("\n--- PHASE 1: CONNECTION ESTABLISHMENT ---")
    a.connect()

    # ---- Phase 2 -----------------------------------------------------------
    print("\n--- PHASE 2: DATA TRANSFER ---")
    payloads = [b"TELEMETRY-0", b"TELEMETRY-1", b"TELEMETRY-2", b"TELEMETRY-3"]

    # Wire indices are deterministic: 0=SABM, 1=UA, then each send attempt is
    #   I-frame (wire w), RR ack (wire w+1).
    # Drop wire 3  -> ACK for frame 0 vanishes (lost ACK -> RTO -> resend).
    # Drop wire 6  -> first send of I-frame seq=1 vanishes (lost frame -> RTO).
    channel.drop_on_wire = {3, 6}

    for p in payloads:
        a.send(p)

    # ---- Phase 3 -----------------------------------------------------------
    print("\n--- PHASE 3: CONNECTION RELEASE ---")
    a.release()

    # ---- Verdict -----------------------------------------------------------
    print("\n" + "=" * 72)
    print("RESULTS")
    print("=" * 72)
    print(f"A sent payloads : {[p for p in payloads]}")
    print(f"B delivered     : {b.delivered}")
    print(f"A RTO firings   : {a.rto_count}")
    print(f"Exactly once?   : {b.delivered == payloads}")
    print(f"In order?       : {b.delivered == list(payloads)}")
    print(f"Connection open?: {a.connected or b.connected}  (expect False)")
    print("\nChannel trace:")
    for line in channel.log:
        print(line)


if __name__ == "__main__":
    main()
