#!/usr/bin/env python3
"""Offline simulator for the Berkeley socket API and the five-primitive
hypothetical transport service from Tanenbaum Ch. 6 (sections 6.1.2-6.1.4).

The simulator models the state machine of a TCP server and client as they walk
through SOCKET -> BIND -> LISTEN -> ACCEPT -> CONNECT -> SEND/RECEIVE -> CLOSE,
and prints the segment that each primitive would put on the wire (SYN, SYN+ACK,
ACK, DATA, FIN, RST). It also walks the five-primitive hypothetical model
(LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT) and the Web-server asymmetric
close (RST) versus the symmetric FIN handshake.

No network calls, no third-party packages -- pure stdlib. Run with
``python3 main.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SYN_SENT = "SYN_SENT"
    SYN_RECEIVED = "SYN_RECEIVED"
    ESTABLISHED = "ESTABLISHED"
    CLOSE_WAIT = "CLOSE_WAIT"
    LAST_ACK = "LAST_ACK"
    TIME_WAIT = "TIME_WAIT"
    CLOSED = "CLOSED"
    RST_PATH = "RST_PATH"


class Prim(str, Enum):
    SOCKET = "SOCKET"
    BIND = "BIND"
    LISTEN = "LISTEN"
    ACCEPT = "ACCEPT"
    CONNECT = "CONNECT"
    SEND = "SEND"
    RECEIVE = "RECEIVE"
    CLOSE = "CLOSE"
    SHUTDOWN_WR = "SHUTDOWN(SHUT_WR)"


@dataclass
class Segment:
    kind: str
    src: str
    dst: str
    flags: list[str] = field(default_factory=list)
    payload: str = ""

    def render(self) -> str:
        flag_str = "+".join(self.flags) if self.flags else ""
        head = f"[{self.kind:<10} {self.src:>10} -> {self.dst:<10}"
        if flag_str:
            head += f"  flags={flag_str}"
        if self.payload:
            head += f"  payload=\"{self.payload}\""
        return head + "]"


@dataclass
class Endpoint:
    role: str
    state: State = State.IDLE
    fd: int = -1
    addr: tuple[str, int] = ("0.0.0.0", 0)
    backlog: int = 0
    accepted_children: list[int] = field(default_factory=list)

    def transition(self, target: State) -> None:
        print(f"  {self.role:<8} state: {self.state.value:<14} -> {target.value}")
        self.state = target


def simulate_berkeley_lifecycle(server_port: int = 12345) -> None:
    print("=" * 72)
    print("BERKELEY SOCKET LIFECYCLE  (SOCKET, BIND, LISTEN, ACCEPT, CONNECT, ...)")
    print("=" * 72)
    print(f"  Server-side arguments: socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)")
    print(f"  Local address family: IPv4 (RFC 791), 32-bit NSAP")
    print(f"  Transport protocol: TCP (RFC 793), reliable byte stream")
    print()

    server = Endpoint(role="server")
    client = Endpoint(role="client")

    print("Step 1 -- SOCKET(AF_INET, SOCK_STREAM, IPPROTO_TCP)")
    server.fd = 3
    client.fd = 4
    print(f"  server FD={server.fd} allocated (kernel resource: TCB, buffers)")
    print(f"  client FD={client.fd} allocated")
    print()

    print("Step 2 -- server BIND(0.0.0.0, htons(12345))")
    server.addr = ("0.0.0.0", server_port)
    if server_port < 1024:
        print(f"  !! port {server_port} is PRIVILEGED -- needs CAP_NET_BIND_SERVICE")
    else:
        print(f"  sockaddr_in: family=AF_INET, port=htons({server_port})")
        print(f"  client BIND skipped -- kernel will pick an ephemeral port")

    print("Step 2a -- server setsockopt(SO_REUSEADDR, 1)")
    print("  without this, a crashed-and-restarted server hits EADDRINUSE")
    print("  because the previous instance is in TIME_WAIT for 2*MSL = 60 s")
    print()

    print("Step 3 -- server LISTEN(backlog=10)")
    server.backlog = 10
    server.transition(State.LISTENING)
    print(f"  kernel will now queue up to {server.backlog} incomplete SYNs")
    print(f"  the somaxconn cap on Linux is 4096 by default")
    print()

    print("Step 4 -- client CONNECT(server, 12345)")
    client.transition(State.SYN_SENT)
    print("  segment sent: SYN, seq=ISN_c")
    print("  connect() returns when the third segment (final ACK) is sent")
    print()

    print("Step 4 -- kernel on the server side completes the three-way handshake")
    server.transition(State.SYN_RECEIVED)
    print("  segment sent: SYN+ACK, seq=ISN_s, ack=ISN_c+1")
    server.transition(State.ESTABLISHED)
    print("  segment sent: ACK, ack=ISN_s+1")
    client.transition(State.ESTABLISHED)
    print()

    print("Step 5 -- server ACCEPT() returns a brand-new FD for the client")
    child_fd = 5
    server.accepted_children.append(child_fd)
    print(f"  ACCEPT returned FD={child_fd} (the per-connection socket)")
    print(f"  the LISTENING FD={server.fd} is preserved for the next accept()")
    print(f"  the server's standard pattern: while True: client, _ = accept()")
    print()

    print("Step 6 -- data exchange: SEND('GET /etc/hosts\\0') and RECEIVE")
    seg_down = Segment("DATA", "client", "server", flags=["PSH", "ACK"],
                       payload="GET /etc/hosts\\0")
    seg_up = Segment("DATA", "server", "client", flags=["PSH", "ACK"],
                     payload="127.0.0.1 localhost ...")
    print(f"  {seg_down.render()}")
    print(f"  {seg_up.render()}")
    print()

    print("Step 7 -- server writes a response and immediately RSTs (asymmetric close)")
    server.transition(State.RST_PATH)
    print("  segment sent: RST, seq=ISN_s+1+N")
    print("  Web-server rationale: the request was the only client data,")
    print("  the response is already on the wire, so no data is lost.")
    print("  Tradeoff: skip the FIN handshake and avoid TIME_WAIT bloat.")
    print()

    print("Step 8 -- client CLOSE()")
    client.transition(State.CLOSED)
    print("  if the client had been graceful it would have sent FIN instead,")
    print("  the server would ACK the FIN, and both sides would TIME_WAIT 2*MSL.")


def simulate_five_primitive_model() -> None:
    print()
    print("=" * 72)
    print("FIVE-PRIMITIVE HYPOTHETICAL TRANSPORT SERVICE  (Tanenbaum Fig. 6-2)")
    print("=" * 72)
    table = [
        ("LISTEN", "(none)", "Block until some process tries to connect"),
        ("CONNECT", "CONNECTION REQ", "Actively attempt to establish a connection"),
        ("SEND", "DATA", "Send information"),
        ("RECEIVE", "(none)", "Block until a DATA packet arrives"),
        ("DISCONNECT", "DISCONNECTION REQ", "Request a release of the connection"),
    ]
    for prim, seg, meaning in table:
        print(f"  {prim:<12}  segment={seg:<22}  {meaning}")
    print()
    print("  Symmetric release: each side issues DISCONNECT independently;")
    print("  the connection is fully released only when both have done so.")
    print("  This is exactly the FIN handshake that TCP implements (RFC 793).")


def simulate_keepalive_failure() -> None:
    print()
    print("=" * 72)
    print("HALF-OPEN CONNECTION AND THE KEEPALIVE RULE  (Tanenbaum 6.2.3)")
    print("=" * 72)
    print("  Failure mode: client crashes after the third ACK; server still holds")
    print("  the TCB and thinks the connection is ESTABLISHED.")
    print()
    print("  Recovery: each side runs a 'quiet' timer that is stopped and")
    print("  restarted on every segment. If it expires, the side sends a")
    print("  dummy segment (zero-window probe) to test liveness.")
    print()
    print("  Linux defaults: tcp_keepalive_time=7200 s, tcp_keepalive_probes=9,")
    print("                  tcp_keepalive_intvl=75 s")
    print()
    print("  After K seconds of silence the segment is sent: <keepalive probe>")
    print("  If N probes go unacknowledged, the connection is auto-closed.")


def main() -> None:
    simulate_berkeley_lifecycle(server_port=12345)
    simulate_five_primitive_model()
    simulate_keepalive_failure()
    print()
    print("=" * 72)
    print("Lesson complete. See docs/en.md for the full socket-API walk-through,")
    print("the two-army problem, and RFC references.")
    print("=" * 72)


if __name__ == "__main__":
    main()
