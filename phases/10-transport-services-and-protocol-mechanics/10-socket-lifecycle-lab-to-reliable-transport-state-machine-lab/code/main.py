"""Socket lifecycle lab + stop-and-wait reliable transport state machine.

Three stdlib-only parts:

1. socket_state_observer() - drives a real TCP socket through bind, listen,
   accept, connect, send, recv, shutdown, close and prints the observable
   state at each step.

2. stop_and_wait_send / stop_and_wait_recv - an alternating-bit protocol on
   UDP. The sender has a 2-state FSM (READY, WAIT_ACK); the receiver mirrors
   it (EXPECT_0, EXPECT_1). A LossyLink drops or corrupts packets so we can
   watch retransmits happen.

3. run_simulation() - N trials of sending a small message over the lossy
   link, reporting retransmits and duplicates.

Run: python3 main.py
"""

from __future__ import annotations

import socket
import struct
import threading
import time
import random
from dataclasses import dataclass, field
from typing import Optional


# --- Part 1: TCP socket lifecycle observer -----------------------------------
def socket_state_observer() -> None:
    print("=" * 70)
    print("PART 1: TCP SOCKET LIFECYCLE")
    print("=" * 70)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(8)
    local_addr = server_sock.getsockname()
    print(f"  [SERVER] bind+listen -> {local_addr}, state=LISTEN")

    def serve() -> None:
        conn, peer = server_sock.accept()
        print(f"  [SERVER] accept returned, peer={peer}, state=ESTABLISHED")
        conn.sendall(b"hello from server\n")
        conn.shutdown(socket.SHUT_WR)
        print("  [SERVER] shutdown(WR) sent FIN, state=CLOSE_WAIT (locally)")
        conn.close()
        print("  [SERVER] close() sent final FIN-ACK response; state=LAST_ACK->CLOSED")

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.05)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"  [CLIENT] socket() -> state=CLOSED")
    client.connect(local_addr)
    print(f"  [CLIENT] connect() -> state=ESTABLISHED, local={client.getsockname()}")
    data = b""
    while b"\n" not in data:
        chunk = client.recv(64)
        if not chunk:
            break
        data += chunk
    print(f"  [CLIENT] recv() -> {data!r}")
    client.shutdown(socket.SHUT_RDWR)
    print("  [CLIENT] shutdown(RDWR) -> FIN sent, state=FIN_WAIT_1")
    client.close()
    print("  [CLIENT] close() -> FIN-ACK sent; will move to TIME_WAIT then CLOSED")
    t.join(timeout=1.0)


# --- Part 2: stop-and-wait reliable transport on UDP -------------------------
HDR_FMT = "!BI"   # type (1B), sequence_bit (4B)
HDR_LEN = struct.calcsize(HDR_FMT)

DATA = 0x01
ACK = 0x02
SYN = 0x03  # not used; reserved


@dataclass
class LossyLink:
    drop_prob: float = 0.0
    rng: random.Random = field(default_factory=lambda: random.Random(0))
    delivered: int = 0
    dropped: int = 0

    def send(self, sock: socket.socket, addr: tuple[str, int], payload: bytes) -> None:
        if self.rng.random() < self.drop_prob:
            self.dropped += 1
            return
        self.delivered += 1
        sock.sendto(payload, addr)


@dataclass
class SWStats:
    sent: int = 0
    retransmits: int = 0
    acks_received: int = 0
    duplicates_dropped: int = 0
    delivered_to_app: int = 0


def sw_send(sock: socket.socket, link: LossyLink, peer: tuple[str, int],
            payload: bytes, stats: SWStats) -> None:
    """Sender: alternates between S0 (READY) and S1 (WAIT_ACK)."""
    seq = 0
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        pkt = struct.pack(HDR_FMT, DATA, seq) + payload
        stats.sent += 1
        link.send(sock, peer, pkt)
        sock.settimeout(0.1)
        try:
            data, _ = sock.recvfrom(512)
        except socket.timeout:
            stats.retransmits += 1
            continue
        if not data:
            continue
        kind, ack_bit = struct.unpack(HDR_FMT, data[:HDR_LEN])
        if kind == ACK and ack_bit == seq:
            stats.acks_received += 1
            return
        stats.retransmits += 1
    raise TimeoutError("stop-and-wait: no ACK received before deadline")


def sw_recv(sock: socket.socket, link: LossyLink, expected: int,
            stats: SWStats, timeout: float = 1.0) -> Optional[bytes]:
    """Receiver: alternates between EXPECT_0 and EXPECT_1 by `expected` bit."""
    sock.settimeout(timeout)
    while True:
        try:
            data, peer = sock.recvfrom(512)
        except socket.timeout:
            return None
        kind, seq = struct.unpack(HDR_FMT, data[:HDR_LEN])
        if kind != DATA:
            continue
        if seq == expected:
            stats.delivered_to_app += 1
            link.send(sock, peer, struct.pack(HDR_FMT, ACK, seq))
            return data[HDR_LEN:]
        # duplicate: re-ACK last accepted bit so the sender can advance
        stats.duplicates_dropped += 1
        link.send(sock, peer, struct.pack(HDR_FMT, ACK, 1 - expected))


# --- Part 3: simulation over a real loopback ---------------------------------
def run_simulation(drop_prob: float = 0.2, message: bytes = b"hello stop-and-wait") -> SWStats:
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    link = LossyLink(drop_prob=drop_prob)

    stats = SWStats()
    payload = message

    def receiver() -> None:
        exp = 0
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            out = sw_recv(rx, link, exp, stats, timeout=0.2)
            if out is not None:
                exp = 1 - exp
                if not out:
                    return
        rx.close()

    t = threading.Thread(target=receiver, daemon=True)
    t.start()
    try:
        sw_send(tx, link, rx.getsockname(), payload, stats)
    except TimeoutError:
        pass
    t.join(timeout=1.5)
    tx.close()
    return stats


def demo_stop_and_wait() -> None:
    print("\n" + "=" * 70)
    print("PART 3: STOP-AND-WAIT SIMULATION OVER LOSSY UDP")
    print("=" * 70)
    print(f"  {'drop':>5s} | {'sent':>5s} | {'retr':>5s} | {'acks':>5s} "
          f"| {'dup_drops':>9s} | {'delivered':>10s}")
    print("-" * 70)
    for p in (0.0, 0.1, 0.2, 0.4):
        s = run_simulation(drop_prob=p)
        print(f"  {p:>4.0%} | {s.sent:>5d} | {s.retransmits:>5d} "
              f"| {s.acks_received:>5d} | {s.duplicates_dropped:>9d} "
              f"| {s.delivered_to_app:>10d}")


def main() -> None:
    socket_state_observer()
    demo_stop_and_wait()
    print("\nDone. Set DROP_PROB env var or call run_simulation(p=...) to vary loss.")


if __name__ == "__main__":
    main()
