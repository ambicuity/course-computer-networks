#!/usr/bin/env python3
"""Berkeley socket API simulator (Tanenbaum 6.1.3).

Implements the socket primitives from Fig 6-5 using in-process queues:
    SOCKET  - create a new communication endpoint
    BIND    - associate a local address (host, port) with a socket
    LISTEN  - announce willingness to accept connections (non-blocking)
    ACCEPT  - block until an incoming connection arrives
    CONNECT - actively establish a connection to a remote address
    SEND    - send data over the connection
    RECV    - receive data from the connection
    CLOSE   - release the connection (symmetric)

Each socket has a state machine: UNCONNECTED -> BOUND -> LISTENING ->
ESTABLISHED (after accept/connect) -> CLOSED.

The simulator uses a global kernel to route connection requests and data
between sockets via in-process byte queues, mimicking TCP's reliable
byte-stream service.

Run:  python3 main.py
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SocketState(Enum):
    UNCONNECTED = "UNCONNECTED"
    BOUND = "BOUND"
    LISTENING = "LISTENING"
    CONNECTING = "CONNECTING"
    ESTABLISHED = "ESTABLISHED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class SocketError(Exception):
    pass


@dataclass
class Socket:
    fd: int
    state: SocketState = SocketState.UNCONNECTED
    local_addr: Optional[tuple[str, int]] = None
    remote_addr: Optional[tuple[str, int]] = None
    backlog: deque = field(default_factory=deque)
    send_buf: bytearray = field(default_factory=bytearray)
    recv_buf: bytearray = field(default_factory=bytearray)
    peer: Optional["Socket"] = None
    listen_fd: Optional[int] = None

    def fileno(self) -> int:
        return self.fd


class SocketKernel:
    def __init__(self) -> None:
        self._next_fd: int = 3
        self._sockets: dict[int, Socket] = {}
        self._bound: dict[tuple[str, int], int] = {}

    def socket(self) -> Socket:
        fd = self._next_fd
        self._next_fd += 1
        s = Socket(fd=fd)
        self._sockets[fd] = s
        return s

    def bind(self, s: Socket, addr: tuple[str, int]) -> None:
        if s.state not in (SocketState.UNCONNECTED, SocketState.BOUND):
            raise SocketError(f"bind: invalid state {s.state.name}")
        if addr in self._bound:
            raise SocketError(f"bind: address {addr} already in use")
        s.local_addr = addr
        s.state = SocketState.BOUND
        self._bound[addr] = s.fd

    def listen(self, s: Socket, queue_size: int = 5) -> None:
        if s.state != SocketState.BOUND:
            raise SocketError(f"listen: socket not bound")
        s.state = SocketState.LISTENING
        s.backlog = deque(maxlen=queue_size)

    def accept(self, s: Socket) -> Socket:
        if s.state != SocketState.LISTENING:
            raise SocketError(f"accept: socket not listening")
        while not s.backlog:
            pass
        conn_sock = s.backlog.popleft()
        conn_sock.state = SocketState.ESTABLISHED
        conn_sock.listen_fd = s.fd
        return conn_sock

    def connect(self, s: Socket, addr: tuple[str, int]) -> None:
        if s.state not in (SocketState.UNCONNECTED, SocketState.BOUND):
            raise SocketError(f"connect: invalid state {s.state.name}")
        if addr not in self._bound:
            raise SocketError(f"connect: connection refused (no server at {addr})")
        listen_fd = self._bound[addr]
        listen_sock = self._sockets[listen_fd]
        if listen_sock.state != SocketState.LISTENING:
            raise SocketError(f"connect: server not listening")
        if len(listen_sock.backlog) >= listen_sock.backlog.maxlen:
            raise SocketError(f"connect: backlog full")
        s.state = SocketState.CONNECTING
        s.remote_addr = addr
        conn = self.socket()
        conn.state = SocketState.ESTABLISHED
        conn.local_addr = listen_sock.local_addr
        conn.remote_addr = s.local_addr or addr
        conn.peer = s
        s.peer = conn
        listen_sock.backlog.append(conn)
        s.state = SocketState.ESTABLISHED

    def send(self, s: Socket, data: bytes) -> int:
        if s.state != SocketState.ESTABLISHED:
            raise SocketError(f"send: socket not established (state={s.state.name})")
        if s.peer is None:
            raise SocketError("send: no peer")
        s.peer.recv_buf.extend(data)
        return len(data)

    def recv(self, s: Socket, nbytes: int) -> bytes:
        if s.state not in (SocketState.ESTABLISHED, SocketState.CLOSING):
            raise SocketError(f"recv: socket not established (state={s.state.name})")
        while not s.recv_buf and s.state == SocketState.ESTABLISHED:
            pass
        data = bytes(s.recv_buf[:nbytes])
        del s.recv_buf[:nbytes]
        if len(data) < nbytes and s.state == SocketState.CLOSING:
            s.state = SocketState.CLOSED
        return data

    def close(self, s: Socket) -> None:
        if s.state == SocketState.CLOSED:
            return
        if s.peer and s.peer.state == SocketState.ESTABLISHED:
            s.peer.state = SocketState.CLOSING
        s.state = SocketState.CLOSED
        if s.local_addr and self._bound.get(s.local_addr) == s.fd:
            if s.state == SocketState.LISTENING:
                del self._bound[s.local_addr]

    def getsockname(self, s: Socket) -> tuple[str, int]:
        return s.local_addr or ("", 0)

    def getpeername(self, s: Socket) -> tuple[str, int]:
        if s.remote_addr is None:
            raise SocketError("not connected")
        return s.remote_addr


def run_tcp_server_client() -> None:
    print("=" * 72)
    print("TCP Server/Client lifecycle via Berkeley sockets")
    print("=" * 72)
    kernel = SocketKernel()

    SERVER_ADDR = ("0.0.0.0", 12345)

    print("\n--- Server side ---")
    srv_sock = kernel.socket()
    print(f"  SOCKET() -> fd={srv_sock.fileno()}, state={srv_sock.state.name}")
    kernel.bind(srv_sock, SERVER_ADDR)
    print(f"  BIND({SERVER_ADDR}) -> state={srv_sock.state.name}")
    kernel.listen(srv_sock, queue_size=10)
    print(f"  LISTEN(10) -> state={srv_sock.state.name}")

    print("\n--- Client side ---")
    cli_sock = kernel.socket()
    print(f"  SOCKET() -> fd={cli_sock.fileno()}, state={cli_sock.state.name}")
    kernel.connect(cli_sock, SERVER_ADDR)
    print(f"  CONNECT({SERVER_ADDR}) -> state={cli_sock.state.name}")
    print(f"  getpeername = {kernel.getpeername(cli_sock)}")

    print("\n--- Server accepts ---")
    conn_sock = kernel.accept(srv_sock)
    print(f"  ACCEPT() -> fd={conn_sock.fileno()}, state={conn_sock.state.name}")
    print(f"  getpeername = {kernel.getpeername(conn_sock)}")

    print("\n--- Data exchange: client sends, server receives ---")
    msg1 = b"Hello from client!"
    n = kernel.send(cli_sock, msg1)
    print(f"  SEND(fd={cli_sock.fileno()}) -> {n} bytes sent")
    data = kernel.recv(conn_sock, 4096)
    print(f"  RECV(fd={conn_sock.fileno()}) -> {len(data)} bytes: {data!r}")
    assert data == msg1

    print("\n--- Data exchange: server sends, client receives ---")
    msg2 = b"Hello from server!"
    n = kernel.send(conn_sock, msg2)
    print(f"  SEND(fd={conn_sock.fileno()}) -> {n} bytes sent")
    data = kernel.recv(cli_sock, 4096)
    print(f"  RECV(fd={cli_sock.fileno()}) -> {len(data)} bytes: {data!r}")
    assert data == msg2

    print("\n--- Partial reads (byte stream semantics) ---")
    kernel.send(conn_sock, b"AAAABBBBCCCC")
    part1 = kernel.recv(cli_sock, 4)
    part2 = kernel.recv(cli_sock, 4)
    part3 = kernel.recv(cli_sock, 4)
    print(f"  RECV(4) -> {part1!r}, RECV(4) -> {part2!r}, RECV(4) -> {part3!r}")
    assert part1 == b"AAAA" and part2 == b"BBBB" and part3 == b"CCCC"

    print("\n--- Close (symmetric release) ---")
    kernel.close(conn_sock)
    print(f"  CLOSE(conn) -> conn state={conn_sock.state.name}, "
          f"client state={cli_sock.state.name}")
    data = kernel.recv(cli_sock, 4096)
    print(f"  RECV(client) after close -> {data!r} (empty = EOF)")
    kernel.close(cli_sock)
    print(f"  CLOSE(client) -> state={cli_sock.state.name}")
    kernel.close(srv_sock)
    print(f"  CLOSE(server) -> state={srv_sock.state.name}")


def run_connection_refused() -> None:
    print("\n" + "=" * 72)
    print("Failure mode: connect to a port with no listener -> refused")
    print("=" * 72)
    kernel = SocketKernel()
    cli = kernel.socket()
    try:
        kernel.connect(cli, ("0.0.0.0", 9999))
    except SocketError as e:
        print(f"  connect() raised: {e}")
    print(f"  client state = {cli.state.name} (stayed UNCONNECTED)")


def run_backlog_full() -> None:
    print("\n" + "=" * 72)
    print("Failure mode: backlog queue full -> connection refused")
    print("=" * 72)
    kernel = SocketKernel()
    srv = kernel.socket()
    kernel.bind(srv, ("0.0.0.0", 8080))
    kernel.listen(srv, queue_size=2)
    clients = []
    for i in range(2):
        c = kernel.socket()
        kernel.connect(c, ("0.0.0.0", 8080))
        clients.append(c)
        print(f"  client {i+1} connected, backlog size={len(srv.backlog)}")
    c3 = kernel.socket()
    try:
        kernel.connect(c3, ("0.0.0.0", 8080))
    except SocketError as e:
        print(f"  client 3 rejected: {e}")
    print(f"  backlog max = {srv.backlog.maxlen}, current = {len(srv.backlog)}")


def main() -> None:
    print("Berkeley Socket API Simulator (Tanenbaum 6.1.3)")
    print()
    print("Primitives: SOCKET  BIND  LISTEN  ACCEPT  CONNECT  SEND  RECV  CLOSE")
    print("States:     UNCONNECTED -> BOUND -> LISTENING -> ESTABLISHED -> CLOSED")
    print("Service:     reliable byte stream (like TCP)")
    print()

    run_tcp_server_client()
    run_connection_refused()
    run_backlog_full()

    print("\n" + "=" * 72)
    print("Key insight: The socket API hides the transport protocol entirely.")
    print("SOCKET/BIND/LISTEN/ACCEPT/CONNECT/SEND/RECV/CLOSE map to the TCP")
    print("state machine, but the application programmer sees only file-like")
    print("read/write on a reliable byte stream.")
    print("=" * 72)


if __name__ == "__main__":
    main()