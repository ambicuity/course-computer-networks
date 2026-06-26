#!/usr/bin/env python3
"""Internet file server via the socket API (Tanenbaum 6.1.4).

Implements the client-server file transfer from Fig 6-6 using an
in-process socket simulator. The server creates a socket, binds to a
port, listens, and loops accepting connections. For each connection it
reads the requested filename, opens the file, and sends it in chunks.
The client connects, sends the filename, and reads the file data chunk
by chunk until EOF.

This mirrors the C code in the textbook but in Python with a simulated
network layer, so it runs without a real OS socket. Demonstrates:

1. The server lifecycle: socket -> bind -> listen -> accept -> read -> send -> close
2. The client lifecycle: socket -> connect -> write -> read-loop -> exit
3. Chunked transfer (BUF_SIZE = 4096) and reassembly on the client side
4. Sequential request handling (one connection at a time, no threads)
5. The limitations noted in the text: no error recovery, no security

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
    recv_buf: bytearray = field(default_factory=bytearray)
    peer: Optional["Socket"] = None
    closed_by_peer: bool = False


class SocketKernel:
    SERVER_PORT = 12345
    BUF_SIZE = 64
    QUEUE_SIZE = 10

    def __init__(self) -> None:
        self._next_fd = 3
        self._sockets: dict[int, Socket] = {}
        self._bound: dict[tuple[str, int], int] = {}
        self._files: dict[str, bytes] = {}

    def socket(self) -> Socket:
        fd = self._next_fd
        self._next_fd += 1
        s = Socket(fd=fd)
        self._sockets[fd] = s
        return s

    def bind(self, s: Socket, addr: tuple[str, int]) -> None:
        s.local_addr = addr
        s.state = SocketState.BOUND
        self._bound[addr] = s.fd

    def listen(self, s: Socket, queue_size: int = QUEUE_SIZE) -> None:
        s.state = SocketState.LISTENING
        s.backlog = deque(maxlen=queue_size)

    def accept(self, s: Socket) -> Socket:
        while not s.backlog:
            pass
        conn = s.backlog.popleft()
        conn.state = SocketState.ESTABLISHED
        return conn

    def connect(self, s: Socket, addr: tuple[str, int]) -> None:
        listen_fd = self._bound[addr]
        listen_sock = self._sockets[listen_fd]
        s.state = SocketState.BOUND
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
        if s.peer is None:
            raise SocketError("no peer")
        s.peer.recv_buf.extend(data)
        return len(data)

    def recv(self, s: Socket, nbytes: int) -> bytes:
        data = bytes(s.recv_buf[:nbytes])
        del s.recv_buf[:nbytes]
        return data

    def recv_wait(self, s: Socket, nbytes: int) -> bytes:
        while not s.recv_buf and not s.closed_by_peer:
            pass
        data = bytes(s.recv_buf[:nbytes])
        del s.recv_buf[:nbytes]
        return data

    def close(self, s: Socket) -> None:
        if s.state == SocketState.CLOSED:
            return
        if s.peer:
            s.peer.closed_by_peer = True
        s.state = SocketState.CLOSED

    def register_file(self, name: str, content: bytes) -> None:
        self._files[name] = content

    def open_file(self, name: str) -> bytes:
        if name not in self._files:
            raise FileNotFoundError(name)
        return self._files[name]


def run_server(kernel: SocketKernel, server_files: dict[str, bytes]) -> int:
    pass


def run_client(kernel: SocketKernel, filename: str, srv: Socket) -> bytes:
    print(f"  [CLIENT] requesting file: {filename!r}")
    s = kernel.socket()
    kernel.connect(s, ("0.0.0.0", SocketKernel.SERVER_PORT))
    print(f"  [CLIENT] connected to server, fd={s.fd}")

    request = (filename + "\x00").encode("utf-8")
    kernel.send(s, request)
    print(f"  [CLIENT] sent filename ({len(request)} bytes)")

    conn = kernel.accept(srv)
    print(f"  [SERVER] accept() -> fd={conn.fd}")

    fname_received = kernel.recv(conn, 256).decode("utf-8").rstrip("\x00")
    print(f"  [SERVER] received filename: {fname_received!r}")

    try:
        content = kernel.open_file(fname_received)
    except FileNotFoundError:
        print(f"  [SERVER] file not found: {fname_received}")
        kernel.close(conn)
        kernel.close(s)
        return b""

    chunk_size = SocketKernel.BUF_SIZE
    offset = 0
    while offset < len(content):
        chunk = content[offset:offset + chunk_size]
        kernel.send(conn, chunk)
        offset += chunk_size
    print(f"  [SERVER] sent {len(content)} bytes in "
          f"{(len(content) + chunk_size - 1) // chunk_size} chunks")

    kernel.close(conn)

    received = bytearray()
    while s.recv_buf:
        data = kernel.recv(s, SocketKernel.BUF_SIZE)
        if not data:
            break
        received.extend(data)
    print(f"  [CLIENT] received {len(received)} bytes total")
    kernel.close(s)
    print(f"  [CLIENT] connection closed, exiting")
    return bytes(received)


def run_file_transfer() -> None:
    print("=" * 72)
    print("Internet File Server: chunked transfer over socket API")
    print("=" * 72)
    kernel = SocketKernel()

    file_data = {
        "small.txt": b"Hello, file server!",
        "lorem.txt": (b"Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                       b"Sed do eiusmod tempor incididunt ut labore et dolore "
                       b"magna aliqua. Ut enim ad minim veniam, quis nostrud "
                       b"exercitation ullamco laboris nisi ut aliquip ex ea "
                       b"commodo consequat."),
        "empty.txt": b"",
    }
    for name, content in file_data.items():
        kernel.register_file(name, content)

    print("\n--- Server starts, then clients connect sequentially ---\n")

    srv = kernel.socket()
    kernel.bind(srv, ("0.0.0.0", SocketKernel.SERVER_PORT))
    kernel.listen(srv, SocketKernel.QUEUE_SIZE)
    print(f"  [SERVER] socket/bind/listen on port {SocketKernel.SERVER_PORT}")

    for fname in ["small.txt", "lorem.txt", "missing.txt", "empty.txt"]:
        print(f"\n>>> Client request: {fname}")
        result = run_client(kernel, fname, srv)
        if fname in file_data:
            assert result == file_data[fname], f"Mismatch for {fname}"
            print(f"  [CHECK] file '{fname}' reassembled correctly "
                  f"({len(result)} bytes)")
        else:
            print(f"  [CHECK] file '{fname}' not found, got {len(result)} bytes")

    kernel.close(srv)
    print(f"\n  [SERVER] shutting down")


def run_chunked_reassembly() -> None:
    print("\n" + "=" * 72)
    print("Chunked transfer and reassembly detail")
    print("=" * 72)
    kernel = SocketKernel()
    large_file = bytes(range(256)) * 4
    kernel.register_file("binary.dat", large_file)

    srv = kernel.socket()
    kernel.bind(srv, ("0.0.0.0", 5000))
    kernel.listen(srv, 5)

    cli = kernel.socket()
    kernel.connect(cli, ("0.0.0.0", 5000))
    conn = kernel.accept(srv)

    kernel.send(cli, b"binary.dat\x00")
    filename = kernel.recv(conn, 256).decode().rstrip("\x00")
    print(f"  Server received filename: {filename!r}")

    content = kernel.open_file(filename)
    chunks_sent = 0
    offset = 0
    while offset < len(content):
        chunk = content[offset:offset + SocketKernel.BUF_SIZE]
        kernel.send(conn, chunk)
        chunks_sent += 1
        offset += SocketKernel.BUF_SIZE

    reassembled = bytearray()
    while cli.recv_buf:
        data = kernel.recv(cli, SocketKernel.BUF_SIZE)
        if not data:
            break
        reassembled.extend(data)

    print(f"  Original size:    {len(content)} bytes")
    print(f"  Chunks sent:      {chunks_sent} (BUF_SIZE={SocketKernel.BUF_SIZE})")
    print(f"  Reassembled size: {len(reassembled)} bytes")
    print(f"  Integrity check:  {'PASS' if bytes(reassembled) == content else 'FAIL'}")
    assert bytes(reassembled) == content


def main() -> None:
    print("Internet File Server via Sockets (Tanenbaum 6.1.4)")
    print()
    print("SERVER:  socket -> bind -> listen -> accept -> read(filename) ->")
    print("         open(file) -> read(file) -> write(socket) -> close")
    print("CLIENT:  socket -> connect -> write(filename) -> read(socket) -> exit")
    print(f"         BUF_SIZE = {SocketKernel.BUF_SIZE}, "
          f"QUEUE_SIZE = {SocketKernel.QUEUE_SIZE}")
    print()

    run_file_transfer()
    run_chunked_reassembly()

    print("\n" + "=" * 72)
    print("Limitations (as noted in the text):")
    print("  - Sequential handling (no threads) -> poor performance")
    print("  - No security, no authentication")
    print("  - Assumes filename fits in buffer and arrives atomically")
    print("  - Minimal error checking and reporting")
    print("  Nevertheless: it is a working Internet file server.")
    print("=" * 72)


if __name__ == "__main__":
    main()