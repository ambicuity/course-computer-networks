"""Service primitives and the Berkeley socket client-server protocol.

A dependency-free simulator of the textbook's six-primitive connection-oriented
service (Fig. 1-18) running over an *acknowledged datagram* channel that may
drop packets. The goal is to make the blocking semantics of LISTEN/CONNECT/
ACCEPT/RECEIVE/SEND/DISCONNECT visible as printed state, including the
exponential-backoff retransmissions that a real kernel (TCP, RFC 9293 with the
timer rules of RFC 6298) performs when a packet is lost.

Run:  python3 code/main.py
No network calls, no third-party packages.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Primitives and the wire record that carries each of the six packets.
# ---------------------------------------------------------------------------

class Primitive(enum.Enum):
    """The six connection-oriented service primitives from the textbook (1.3.4)."""
    LISTEN = "LISTEN"
    CONNECT = "CONNECT"
    ACCEPT = "ACCEPT"
    RECEIVE = "RECEIVE"
    SEND = "SEND"
    DISCONNECT = "DISCONNECT"


@dataclass
class Packet:
    """An acknowledged datagram exchanged by the two simulated processes."""
    step: int            # 1..6 in the textbook's Fig. 1-18 exchange
    primitive: Primitive # which primitive emitted it
    payload: str = ""    # data carried (for SEND/RECEIVE steps)
    seq: int = 0         # logical sequence number for retransmit/de-dup
    is_ack: bool = False # acknowledgement half of an acknowledged datagram

    def describe(self) -> str:
        tag = "ACK" if self.is_ack else "PKT"
        return f"[{tag} step={self.step} {self.primitive.value} seq={self.seq}" + (
            f" payload={self.payload!r}]" if self.payload else "]")


# ---------------------------------------------------------------------------
# Channel: deterministic, injectable loss so traces are reproducible.
# ---------------------------------------------------------------------------

@dataclass
class LossyChannel:
    """Delivers packets to a receiver callback; drops one packet exactly once
    at ``drop_at`` (step number), then never again. Models one lost datagram
    on an otherwise reliable link."""
    drop_at: Optional[int] = None
    delivered: list[Packet] = field(default_factory=list)
    dropped: list[Packet] = field(default_factory=list)
    receiver: Optional[Callable[[Packet], None]] = None

    def send(self, pkt: Packet) -> None:
        if self.drop_at is not None and pkt.step == self.drop_at and not pkt.is_ack:
            # A data/control packet is lost; its ack never gets a chance to form.
            self.dropped.append(pkt)
            print(f"    channel: DROPPED {pkt.describe()}")
            self.drop_at = None  # only one drop, ever
            return
        self.delivered.append(pkt)
        if self.receiver is not None:
            self.receiver(pkt)


# ---------------------------------------------------------------------------
# Retransmission timer (RFC 6298 style exponential backoff, simplified).
# ---------------------------------------------------------------------------

@dataclass
class KarnTimer:
    """Simplified Karn/6298 timer: fixed base RTO, exponential backoff per
    retransmit. Real TCP also smooths RTT samples (SRTT, RTTVAR) and refuses
    to sample retransmitted segments; the backoff here is the part that is
    visible in the printed trace."""
    base_rto_ms: int = 1000
    max_rto_ms: int = 32000
    _current: int = field(init=False)

    def __post_init__(self) -> None:
        self._current = self.base_rto_ms

    def rto(self) -> int:
        return self._current

    def backoff(self) -> None:
        self._current = min(self._current * 2, self.max_rto_ms)

    def reset(self) -> None:
        self._current = self.base_rto_ms


# ---------------------------------------------------------------------------
# Connection-oriented client and server: each method is one service primitive.
# The `blocked` flag stands in for the kernel suspending the process.
# ---------------------------------------------------------------------------

class ConnectionOrientedClient:
    def __init__(self, channel: LossyChannel) -> None:
        self.channel = channel
        self.blocked: bool = False
        self.connected: bool = False
        self.answer: Optional[str] = None
        self.closed: bool = False
        self.timer = KarnTimer(base_rto_ms=1000)
        self.retransmits: int = 0
        self.next_seq: int = 0

    # CONNECT --------------------------------------------------------------
    def connect(self) -> None:
        print("CLIENT: CONNECT -> sending connect request (step 1)")
        self.blocked = True
        self._send_with_retransmit(step=1, primitive=Primitive.CONNECT, payload="REQ-CONN")

    def _send_with_retransmit(self, step: int, primitive: Primitive,
                              payload: str = "") -> None:
        seq = self.next_seq
        self.next_seq += 1
        attempt = 0
        while self.blocked:
            pkt = Packet(step=step, primitive=primitive, payload=payload, seq=seq)
            print(f"CLIENT: SEND {pkt.describe()} (RTO={self.timer.rto()}ms)")
            self.channel.send(pkt)
            attempt += 1
            # The reactor wired into the channel sets self.blocked=False on
            # receipt of the matching acknowledgement; otherwise we retransmit.
            if self.blocked:
                self.retransmits += 1
                self.timer.backoff()
                print(f"CLIENT:   no ack within RTO -> retransmit #{attempt}")

    def on_accept(self, pkt: Packet) -> None:
        print(f"CLIENT: RECEIVE {pkt.describe()} -> CONNECT returns, established")
        self.blocked = False
        self.connected = True
        self.timer.reset()

    def send_request(self, data: str) -> None:
        print("CLIENT: SEND -> request for data (step 3)")
        self.blocked = True
        self._send_with_retransmit(step=3, primitive=Primitive.SEND, payload=data)

    def on_reply(self, pkt: Packet) -> None:
        print(f"CLIENT: RECEIVE {pkt.describe()} -> got answer {pkt.payload!r}")
        self.answer = pkt.payload
        self.blocked = False
        self.timer.reset()

    def disconnect(self) -> None:
        print("CLIENT: DISCONNECT -> (step 5)")
        self.blocked = True
        self._send_with_retransmit(step=5, primitive=Primitive.DISCONNECT)

    def on_disconnect_ack(self, pkt: Packet) -> None:
        print(f"CLIENT: RECEIVE {pkt.describe()} -> connection closed, released")
        self.blocked = False
        self.closed = True
        self.timer.reset()


class ConnectionOrientedServer:
    def __init__(self, channel: LossyChannel) -> None:
        self.channel = channel
        self.blocked: bool = False
        self.listening: bool = False
        self.connected: bool = False
        self.request: Optional[str] = None

    # LISTEN ---------------------------------------------------------------
    def listen(self) -> None:
        print("SERVER: LISTEN -> blocked waiting for a connection")
        self.blocked = True
        self.listening = True

    def on_connect(self, pkt: Packet) -> None:
        # ACCEPT implicitly: unblock LISTEN, send accept reply (step 2).
        print(f"SERVER: ACCEPT <- {pkt.describe()} -> sending accept response (step 2)")
        self.blocked = False
        self.connected = True
        ack = Packet(step=2, primitive=Primitive.ACCEPT,
                     payload="ACCEPT", seq=pkt.seq, is_ack=True)
        self.channel.send(ack)
        # Immediately RECEIVE so we are ready before the ack gets back.
        self.receive()

    # RECEIVE -------------------------------------------------------------
    def receive(self) -> None:
        print("SERVER: RECEIVE -> blocked waiting for a request")
        self.blocked = True

    def on_request(self, pkt: Packet) -> None:
        print(f"SERVER: <- {pkt.describe()} -> handling request {pkt.payload!r}")
        self.request = pkt.payload
        self.blocked = False
        # SEND the reply (step 4).
        reply = Packet(step=4, primitive=Primitive.SEND,
                       payload=f"reply-for({pkt.payload})",
                       seq=pkt.seq, is_ack=True)
        print(f"SERVER: SEND -> reply (step 4) {reply.describe()}")
        self.channel.send(reply)

    def on_disconnect(self, pkt: Packet) -> None:
        print(f"SERVER: <- {pkt.describe()} -> DISCONNECT (step 6)")
        self.connected = False
        ack = Packet(step=6, primitive=Primitive.DISCONNECT,
                     seq=pkt.seq, is_ack=True)
        self.channel.send(ack)


# ---------------------------------------------------------------------------
# Orchestrator: replays the six-packet exchange, dispatching to reactors.
# ---------------------------------------------------------------------------

def run_exchange(drop_at: Optional[int] = None) -> None:
    channel = LossyChannel(drop_at=drop_at)
    server = ConnectionOrientedServer(channel)
    client = ConnectionOrientedClient(channel)

    def server_reactor(pkt: Packet) -> None:
        if pkt.step == 1 and pkt.primitive is Primitive.CONNECT:
            server.on_connect(pkt)
        elif pkt.step == 3 and pkt.primitive is Primitive.SEND and not pkt.is_ack:
            server.on_request(pkt)
        elif pkt.step == 5 and pkt.primitive is Primitive.DISCONNECT and not pkt.is_ack:
            server.on_disconnect(pkt)

    def client_reactor(pkt: Packet) -> None:
        if pkt.step == 2 and pkt.primitive is Primitive.ACCEPT:
            client.on_accept(pkt)
        elif pkt.step == 4 and pkt.primitive is Primitive.SEND and pkt.is_ack:
            client.on_reply(pkt)
        elif pkt.step == 6 and pkt.primitive is Primitive.DISCONNECT and pkt.is_ack:
            client.on_disconnect_ack(pkt)

    def both(pkt: Packet) -> None:
        server_reactor(pkt)
        if pkt.is_ack:
            client_reactor(pkt)

    channel.receiver = both

    server.listen()
    client.connect()
    client.send_request("GET temperature")
    client.disconnect()

    print(f"RESULT: closed={client.closed} retransmits={client.retransmits} "
          f"answer={client.answer!r}")


# ---------------------------------------------------------------------------
# Connectionless contrast: two-packet exchange, no bearer state.
# ---------------------------------------------------------------------------

@dataclass
class ConnectionlessClient:
    """Bare request-reply (the textbook's "in a perfect world" case). Has no
    sequence state, so it cannot distinguish a slow reply from a lost one and
    will retry even though the server may already have committed the work."""
    drop_first: int = 0
    delivered: bool = False
    retries: int = 0

    def request_reply(self, payload: str,
                      server_fn: Callable[[str], str]) -> str:
        attempt = 0
        while not self.delivered:
            attempt += 1
            print(f"CLIENT(connless): SEND request#{attempt} {payload!r}")
            # Deterministic loss for reproducibility: drop the first
            # `drop_first` attempts (request OR its reply lost, the client
            # cannot tell which).
            if attempt <= self.drop_first:
                print("    channel: DROPPED request (or its reply)")
                self.retries += 1
                continue
            reply = server_fn(payload)
            self.delivered = True
            print(f"CLIENT(connless): RECEIVE reply {reply!r}")
            return reply
        return ""


def run_connectionless(drop_first: int = 0) -> None:
    print("\n--- Connectionless (two-packet) exchange over lossy channel ---")
    committed: set[int] = set()
    counters: dict[str, int] = {}

    def server(payload: str) -> str:
        n = counters.get(payload, 0) + 1
        counters[payload] = n
        committed.add(n)
        print(f"SERVER(connless): processing {payload!r} commit#{n}")
        return f"ack({payload})#{n}"

    client = ConnectionlessClient(drop_first=drop_first)
    reply = client.request_reply("login(user=alice)", server)
    print(f"RESULT: reply={reply!r} retries={client.retries} "
          f"server_committed_times={sorted(committed)}")
    print("Note: without bearer state the client cannot tell a lost reply from "
          "a slow server, so an idempotent-unaware operation was done "
          f"{len(committed)} time(s).")


# ---------------------------------------------------------------------------
# Main: drive the scenarios that the lesson references.
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("SCENARIO 1: six-primitive exchange on a clean channel")
    print("=" * 72)
    run_exchange(drop_at=None)

    print("\n" + "=" * 72)
    print("SCENARIO 2: six-primitive exchange, CONNECT (step 1) dropped once")
    print("=" * 72)
    run_exchange(drop_at=1)

    print("\n" + "=" * 72)
    print("SCENARIO 3: six-primitive exchange, data request (step 3) dropped once")
    print("=" * 72)
    run_exchange(drop_at=3)

    print("\n" + "=" * 72)
    print("SCENARIO 4: connectionless two-packet exchange, first 2 attempts lost")
    print("=" * 72)
    run_connectionless(drop_first=2)


if __name__ == "__main__":
    main()