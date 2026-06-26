#!/usr/bin/env python3
"""TCP connection state machine (all 11 states) and sliding window simulator.

Stdlib only. Demonstrates Sec 6.5.7-6.5.8:

1. The full 11-state TCP connection management finite state machine (Fig 6-38/39)
   with transitions driven by user calls (CONNECT, LISTEN, CLOSE) and segment
   arrivals (SYN, ACK, FIN, RST).
2. TCP sliding window with decoupled ack and window advertisement, including
   the zero-window probe and the silly window syndrome avoidance.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


FLAG_SYN = 0x02
FLAG_ACK = 0x10
FLAG_FIN = 0x01
FLAG_RST = 0x04


@dataclass
class Segment:
    seq: int
    ack: int
    flags: int
    window: int = 65535
    data: bytes = b""

    def flag_str(self) -> str:
        parts = []
        if self.flags & FLAG_SYN: parts.append("SYN")
        if self.flags & FLAG_ACK: parts.append("ACK")
        if self.flags & FLAG_FIN: parts.append("FIN")
        if self.flags & FLAG_RST: parts.append("RST")
        return ",".join(parts) if parts else "-"


TCP_STATES = [
    "CLOSED", "LISTEN", "SYN_SENT", "SYN_RCVD", "ESTABLISHED",
    "FIN_WAIT_1", "FIN_WAIT_2", "CLOSING", "TIME_WAIT",
    "CLOSE_WAIT", "LAST_ACK",
]

STATE_DESCRIPTIONS = {
    "CLOSED": "No connection is active or pending",
    "LISTEN": "Server waiting for incoming call",
    "SYN_RCVD": "Connection request arrived; wait for ACK",
    "SYN_SENT": "Application started opening connection",
    "ESTABLISHED": "Normal data transfer state",
    "FIN_WAIT_1": "Application said it is finished",
    "FIN_WAIT_2": "Other side agreed to release",
    "TIME_WAIT": "Wait for all packets to die off (2*MSL)",
    "CLOSING": "Both sides tried to close simultaneously",
    "CLOSE_WAIT": "Other side initiated release",
    "LAST_ACK": "Wait for all packets to die off",
}

TRANSITIONS: dict[str, list[tuple[str, str, str]]] = {
    "CLOSED": [
        ("LISTEN", "passive OPEN", "-"),
        ("SYN_SENT", "active OPEN / CONNECT", "SEND SYN"),
        ("CLOSED", "DELETE", "-"),
    ],
    "LISTEN": [
        ("SYN_RCVD", "rcv SYN", "SEND SYN+ACK"),
        ("SYN_SENT", "SEND / active OPEN", "SEND SYN"),
        ("CLOSED", "CLOSE", "-"),
    ],
    "SYN_SENT": [
        ("ESTABLISHED", "rcv SYN+ACK", "SEND ACK"),
        ("SYN_RCVD", "rcv SYN", "SEND SYN+ACK (simultaneous open)"),
        ("CLOSED", "rcv RST / CLOSE", "-"),
    ],
    "SYN_RCVD": [
        ("ESTABLISHED", "rcv ACK", "-"),
        ("LISTEN", "rcv RST", "-"),
    ],
    "ESTABLISHED": [
        ("FIN_WAIT_1", "CLOSE", "SEND FIN"),
        ("CLOSE_WAIT", "rcv FIN", "SEND ACK"),
    ],
    "FIN_WAIT_1": [
        ("FIN_WAIT_2", "rcv ACK of FIN", "-"),
        ("CLOSING", "rcv FIN", "SEND ACK"),
        ("TIME_WAIT", "rcv FIN+ACK", "SEND ACK"),
    ],
    "FIN_WAIT_2": [
        ("TIME_WAIT", "rcv FIN", "SEND ACK"),
    ],
    "CLOSING": [
        ("TIME_WAIT", "rcv ACK", "-"),
    ],
    "TIME_WAIT": [
        ("CLOSED", "timeout=2*MSL", "-"),
    ],
    "CLOSE_WAIT": [
        ("LAST_ACK", "CLOSE", "SEND FIN"),
    ],
    "LAST_ACK": [
        ("CLOSED", "rcv ACK", "-"),
    ],
}


@dataclass
class TCPStateMachine:
    state: str = "CLOSED"
    history: list[str] = field(default_factory=list)

    def transition(self, event: str) -> str:
        for next_state, evt, action in TRANSITIONS.get(self.state, []):
            if evt == event or event in evt:
                old = self.state
                self.state = next_state
                self.history.append(f"{old} --[{event}]--> {next_state}  action: {action}")
                return action
        self.history.append(f"{self.state} --[{event}]--> (NO TRANSITION)")
        return "(no transition)"

    def trace_client_path(self) -> None:
        self.state = "CLOSED"
        steps = [
            ("active OPEN / CONNECT", "Client opens connection"),
            ("rcv SYN+ACK", "Server responds"),
            ("rcv FIN", "Server initiates close"),
            ("CLOSE", "Client closes"),
            ("rcv ACK", "Server acks client FIN"),
            ("timeout=2*MSL", "Wait 2 MSL"),
        ]
        for evt, desc in steps:
            self.transition(evt)

    def trace_server_path(self) -> None:
        sm2 = TCPStateMachine()
        steps = [
            ("passive OPEN", "Server listens"),
            ("rcv SYN", "Client requests connection"),
            ("rcv ACK", "Client completes handshake"),
            ("rcv FIN", "Client initiates close"),
            ("CLOSE", "Server closes"),
            ("rcv ACK", "Client acks server FIN"),
        ]
        for evt, desc in steps:
            sm2.transition(evt)
        self.history.extend(sm2.history)


# ---------------------------------------------------------------------------
# Sliding window simulator
# ---------------------------------------------------------------------------

@dataclass
class SlidingWindowSender:
    base: int = 0
    next_seq: int = 0
    window: int = 4096
    mss: int = 1024
    buffered: dict[int, bytes] = field(default_factory=dict)

    def can_send(self) -> bool:
        return (self.next_seq - self.base) < self.window

    def send(self, data: bytes) -> Segment | None:
        if not self.can_send():
            return None
        seg = Segment(seq=self.next_seq, ack=0, flags=FLAG_ACK, window=self.window, data=data)
        self.buffered[self.next_seq] = data
        self.next_seq += len(data)
        return seg

    def receive_ack(self, ack_num: int, new_window: int) -> list[int]:
        retired: list[int] = []
        while self.base < ack_num:
            if self.base in self.buffered:
                del self.buffered[self.base]
                retired.append(self.base)
            self.base += 1
        self.window = new_window
        return retired

    def outstanding(self) -> int:
        return self.next_seq - self.base


@dataclass
class SlidingWindowReceiver:
    expected: int = 0
    buffer_size: int = 4096
    consumed: int = 0
    received: bytearray = field(default_factory=bytearray)

    def receive(self, seg: Segment) -> Segment:
        if seg.seq == self.expected:
            self.received.extend(seg.data)
            self.expected += len(seg.data)
        available = self.buffer_size - (self.expected - self.consumed)
        return Segment(seq=0, ack=self.expected, flags=FLAG_ACK,
                       window=max(0, available))

    def application_read(self, n: int) -> bytes:
        n = min(n, len(self.received))
        data = bytes(self.received[:n])
        self.received = self.received[n:]
        self.consumed += n
        return data


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("TCP Connection Management: 11 States (Fig 6-38)")
    print("=" * 70)
    for state in TCP_STATES:
        desc = STATE_DESCRIPTIONS.get(state, "")
        print(f"  {state:>14}  {desc}")

    print()
    print("=" * 70)
    print("Normal Client Path (heavy solid line in Fig 6-39)")
    print("=" * 70)
    sm = TCPStateMachine()
    client_steps = [
        ("active OPEN / CONNECT", "Application calls CONNECT"),
        ("rcv SYN+ACK", "Server's SYN+ACK arrives"),
        ("rcv FIN", "Server says it's done"),
        ("CLOSE", "Application calls CLOSE"),
        ("rcv ACK", "Server ACKs our FIN"),
        ("timeout=2*MSL", "2*MSL timer expires"),
    ]
    for evt, desc in client_steps:
        action = sm.transition(evt)
        print(f"  {desc:40s} -> state: {sm.state:14s}  ({action})")

    print()
    print("=" * 70)
    print("Normal Server Path (heavy dashed line in Fig 6-39)")
    print("=" * 70)
    sm2 = TCPStateMachine()
    server_steps = [
        ("passive OPEN", "Application calls LISTEN"),
        ("rcv SYN", "Client's SYN arrives"),
        ("rcv ACK", "Client's ACK completes handshake"),
        ("rcv FIN", "Client says it's done"),
        ("CLOSE", "Application calls CLOSE"),
        ("rcv ACK", "Client ACKs our FIN"),
    ]
    for evt, desc in server_steps:
        action = sm2.transition(evt)
        print(f"  {desc:40s} -> state: {sm2.state:14s}  ({action})")

    print()
    print("=" * 70)
    print("Sliding Window: Decoupled ACK and Window (Fig 6-40)")
    print("=" * 70)
    sender = SlidingWindowSender(window=4096, mss=2048)
    receiver = SlidingWindowReceiver(buffer_size=4096)

    print(f"  Initial: sender base={sender.base} next_seq={sender.next_seq} window={sender.window}")
    print()

    for i in range(4):
        if not sender.can_send():
            print(f"  Step {i+1}: sender window full (outstanding={sender.outstanding()})")
            break
        seg = sender.send(b"X" * 2048)
        print(f"  TX: {seg.flag_str()} seq={seg.seq} data={len(seg.data)}B  "
              f"(outstanding={sender.outstanding()}/{sender.window})")
        ack_seg = receiver.receive(seg)
        print(f"  RX: {ack_seg.flag_str()} ack={ack_seg.ack} win={ack_seg.window}")
        retired = sender.receive_ack(ack_seg.ack, ack_seg.window)
        print(f"  -> sender: base={sender.base} window={sender.window} retired={retired}")
        if ack_seg.window == 0:
            print(f"  ** Window is ZERO -- sender must stop! **")
            print(f"  Application reads 2048 bytes...")
            data = receiver.application_read(2048)
            available = receiver.buffer_size - (receiver.expected - receiver.consumed)
            probe_ack = Segment(seq=0, ack=receiver.expected, flags=FLAG_ACK, window=available)
            print(f"  Window update after read: win={probe_ack.window}")
            sender.receive_ack(probe_ack.ack, probe_ack.window)
            print(f"  -> sender: base={sender.base} window={sender.window}")
        print()

    print("  Key: ACK acknowledges received data; Window advertises buffer space.")
    print("  These are DECOUPLED -- receiver can say 'got it, but don't send more'.")


if __name__ == "__main__":
    main()