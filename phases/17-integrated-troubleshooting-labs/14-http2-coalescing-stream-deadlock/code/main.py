#!/usr/bin/env python3
"""HTTP/2 Coalescing and Stream Deadlock (Integrated Troubleshooting Lab 14).

Frame-level HTTP/2 simulator demonstrating connection coalescing across three
origins and the flow-control deadlock that arises when the connection window
drains while coalesced streams are waiting for credit.

Reproduces the 8-step Build-It scenario from the lesson prose:

  setup          — configure three origins sharing one IP and TLS cert (SAN)
  settings       — exchange SETTINGS frame (max-concurrent=100, window=65535)
  open-streams   — open streams 1, 3, 5 for a.example, b.example, c.example
  send-data      — drain the connection window fully on stream 1
  status         — report per-stream state and DEADLOCK flag
  window-update  — send WINDOW_UPDATE(stream=0, increment=65535)
  confirm        — re-check status: streams 3 and 5 unblocked
  middlebox      — simulate SETTINGS rewrite to MAX_CONCURRENT_STREAMS=1

Run:  python3 main.py [--mode <mode>]
"""
from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


# ---------------------------------------------------------------------------
# HTTP/2 frame type constants  (RFC 9113 §11.2)
# ---------------------------------------------------------------------------
class FrameType(IntEnum):
    DATA = 0x0
    HEADERS = 0x1
    RST_STREAM = 0x3
    SETTINGS = 0x4
    GOAWAY = 0x7
    WINDOW_UPDATE = 0x8


# HTTP/2 SETTINGS parameter identifiers
SETTINGS_MAX_CONCURRENT_STREAMS = 0x3
SETTINGS_INITIAL_WINDOW_SIZE = 0x4

# Default values per RFC 9113 §6.9.2
DEFAULT_INITIAL_WINDOW_SIZE = 65535
CONNECTION_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"


# ---------------------------------------------------------------------------
# Frame serialization
# ---------------------------------------------------------------------------
def build_frame_header(payload_len: int, ftype: FrameType,
                       flags: int, stream_id: int) -> bytes:
    """Pack a 9-byte HTTP/2 frame header.

    Format: 3-byte length | 1-byte type | 1-byte flags | 4-byte stream_id
    The stream_id high bit is reserved (must be 0).
    """
    # length is 24-bit big-endian
    length_bytes = struct.pack(">I", payload_len)[1:]          # drop top byte
    id_bytes = struct.pack(">I", stream_id & 0x7FFFFFFF)
    return length_bytes + struct.pack("BB", int(ftype), flags) + id_bytes


def build_settings_frame(params: dict[int, int], ack: bool = False) -> bytes:
    """Build a SETTINGS frame.

    Each parameter is encoded as 6 bytes: 2-byte id + 4-byte value.
    flags=0x1 when ack=True (empty payload, stream_id=0).
    """
    if ack:
        return build_frame_header(0, FrameType.SETTINGS, 0x1, 0)
    payload = b"".join(struct.pack(">HI", k, v) for k, v in params.items())
    return build_frame_header(len(payload), FrameType.SETTINGS, 0x0, 0) + payload


def build_headers_frame(stream_id: int, authority: str) -> bytes:
    """Build a minimal HEADERS frame (END_HEADERS flag set, flags=0x4).

    Real HPACK compression is omitted; we store the authority as a literal
    byte string so the frame is parseable and demonstrable.  In production
    these bytes would be HPACK-encoded.
    """
    # Literal pseudo-header block: :authority = authority
    # HPACK literal, never-indexed (0x10), name length, name, value len, value
    name = b":authority"
    val = authority.encode()
    payload = (struct.pack("B", 0x10) +
               struct.pack("B", len(name)) + name +
               struct.pack("B", len(val)) + val)
    return build_frame_header(len(payload), FrameType.HEADERS, 0x4, stream_id) + payload


def build_data_frame(stream_id: int, length: int) -> bytes:
    """Build a DATA frame with synthetic payload of ``length`` zero bytes."""
    payload = bytes(length)
    return build_frame_header(length, FrameType.DATA, 0x0, stream_id) + payload


def build_window_update_frame(stream_id: int, increment: int) -> bytes:
    """Build a WINDOW_UPDATE frame.

    stream_id=0 → connection-level; non-zero → stream-level.
    increment is a 31-bit value; the high bit is reserved.
    """
    payload = struct.pack(">I", increment & 0x7FFFFFFF)
    return build_frame_header(4, FrameType.WINDOW_UPDATE, 0x0, stream_id) + payload


def build_rst_stream_frame(stream_id: int, error_code: int) -> bytes:
    """Build a RST_STREAM frame carrying a 32-bit error code."""
    payload = struct.pack(">I", error_code)
    return build_frame_header(4, FrameType.RST_STREAM, 0x0, stream_id) + payload


def build_goaway_frame(last_stream_id: int, error_code: int) -> bytes:
    """Build a GOAWAY frame."""
    payload = struct.pack(">II", last_stream_id & 0x7FFFFFFF, error_code)
    return build_frame_header(8, FrameType.GOAWAY, 0x0, 0) + payload


def frame_hex(raw: bytes) -> str:
    """Format raw bytes as annotated hex blocks (9-byte header | payload)."""
    header = raw[:9].hex(" ")
    payload = raw[9:].hex(" ")
    if payload:
        return f"{header} | {payload}"
    return header


# ---------------------------------------------------------------------------
# Connection coalescing decision (RFC 9113 §9.1)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Origin:
    hostname: str
    ip: str
    san_list: tuple[str, ...]  # Subject Alternative Names from TLS cert


def coalescing_decision(existing: Origin, new_hostname: str,
                        new_ip: str) -> tuple[bool, str]:
    """Return (can_coalesce, reason) per RFC 9113 §9.1.

    All three conditions must hold:
      1. Same IP (byte-for-byte comparison, no re-resolution)
      2. Existing TLS certificate covers new hostname (SAN match)
      3. ALPN h2 negotiated (assumed true for existing h2 connection)
    """
    if new_ip != existing.ip:
        return False, f"IP mismatch: {new_ip!r} != {existing.ip!r}"
    if new_hostname not in existing.san_list:
        return False, f"{new_hostname!r} not in SAN {existing.san_list}"
    return True, "same IP + valid SAN + ALPN h2 → COALESCE"


# ---------------------------------------------------------------------------
# Stream and connection state
# ---------------------------------------------------------------------------
class StreamState(str):
    IDLE = "IDLE"
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    REFUSED = "REFUSED_STREAM"
    CLOSED = "CLOSED"


@dataclass
class Http2Stream:
    stream_id: int
    authority: str
    state: str = StreamState.IDLE
    stream_window: int = DEFAULT_INITIAL_WINDOW_SIZE
    bytes_sent: int = 0

    def status_line(self, conn_window: int) -> str:
        if self.state == StreamState.OPEN and conn_window == 0:
            blocked = f"BLOCKED(conn_window=0)"
            return (f"  stream {self.stream_id} ({self.authority}): {blocked}  "
                    f"stream_window={self.stream_window}")
        return (f"  stream {self.stream_id} ({self.authority}): {self.state}  "
                f"stream_window={self.stream_window}  bytes_sent={self.bytes_sent}")


@dataclass
class Http2Connection:
    ip: str
    san: tuple[str, ...]
    conn_window: int = DEFAULT_INITIAL_WINDOW_SIZE
    max_concurrent_streams: int = 100
    initial_window_size: int = DEFAULT_INITIAL_WINDOW_SIZE
    streams: dict[int, Http2Stream] = field(default_factory=dict)

    # ---------- helpers ----------
    def active_streams(self) -> list[Http2Stream]:
        return [s for s in self.streams.values()
                if s.state in (StreamState.OPEN, StreamState.BLOCKED)]

    def is_deadlocked(self) -> bool:
        """True when conn_window==0 and multiple streams are open."""
        if self.conn_window > 0:
            return False
        blocked = [s for s in self.active_streams() if s.stream_id != 1]
        # Deadlock: stream 1 stalls the connection and at least one other waits
        return len(blocked) >= 1 and len(self.active_streams()) > 1

    def open_stream(self, stream_id: int, authority: str) -> tuple[bool, str]:
        """Attempt to open a new stream; honour MAX_CONCURRENT_STREAMS."""
        active = len(self.active_streams())
        if active >= self.max_concurrent_streams:
            s = Http2Stream(stream_id, authority, StreamState.REFUSED,
                            self.initial_window_size)
            self.streams[stream_id] = s
            return False, StreamState.REFUSED
        s = Http2Stream(stream_id, authority, StreamState.OPEN,
                        self.initial_window_size)
        self.streams[stream_id] = s
        return True, StreamState.OPEN

    def send_data(self, stream_id: int, byte_count: int) -> tuple[int, int]:
        """Consume flow-control credit for DATA on stream_id.

        Returns (bytes_actually_sent, remainder_blocked).
        A sender must respect min(conn_window, stream_window).
        """
        s = self.streams[stream_id]
        allowed = min(self.conn_window, s.stream_window, byte_count)
        s.bytes_sent += allowed
        s.stream_window -= allowed
        self.conn_window -= allowed
        remainder = byte_count - allowed
        if remainder > 0:
            s.state = StreamState.BLOCKED if s.state != StreamState.OPEN else StreamState.OPEN
        return allowed, remainder

    def apply_window_update(self, stream_id: int, increment: int) -> None:
        """Apply a WINDOW_UPDATE (stream_id=0 → connection-level)."""
        if stream_id == 0:
            self.conn_window += increment
        else:
            self.streams[stream_id].stream_window += increment
        # If conn_window > 0, blocked open streams can proceed
        if self.conn_window > 0:
            for s in self.streams.values():
                if s.state == StreamState.BLOCKED:
                    s.state = StreamState.OPEN


# ---------------------------------------------------------------------------
# Step renderers (matching the 8-step Build-It procedure)
# ---------------------------------------------------------------------------
SEP = "=" * 72


def print_header(step: int, title: str) -> None:
    print()
    print(SEP)
    print(f"  Step {step}: {title}")
    print(SEP)


def step_setup(origins: list[str], ip: str) -> tuple[Http2Connection, Origin]:
    """Step 1 — DNS + TLS handshake; establish coalescing eligibility."""
    print_header(1, "Setup — DNS resolution and TLS handshake")
    san = tuple(origins)
    origin = Origin(hostname=origins[0], ip=ip, san_list=san)
    conn = Http2Connection(ip=ip, san=san)
    print(f"  Target IP  : {ip}")
    print(f"  SAN list   : {', '.join(san)}")
    print(f"  ALPN       : h2 (negotiated during TLS 1.3 handshake)")
    print(f"  conn_window: {conn.conn_window}")
    print()
    # Verify coalescing decisions for each additional origin
    for host in origins[1:]:
        ok, reason = coalescing_decision(origin, host, ip)
        marker = "COALESCE" if ok else "NEW-CONN"
        print(f"  {host}: [{marker}] {reason}")
    return conn, origin


def step_settings(conn: Http2Connection,
                  max_concurrent: int, initial_window: int) -> None:
    """Step 2 — Exchange SETTINGS frames."""
    print_header(2, "Exchange SETTINGS")
    conn.max_concurrent_streams = max_concurrent
    conn.initial_window_size = initial_window

    server_frame = build_settings_frame({
        SETTINGS_MAX_CONCURRENT_STREAMS: max_concurrent,
        SETTINGS_INITIAL_WINDOW_SIZE: initial_window,
    })
    client_ack = build_settings_frame({}, ack=True)

    print(f"  Server SETTINGS frame ({len(server_frame)} bytes):")
    print(f"    hex: {frame_hex(server_frame)}")
    print(f"    MAX_CONCURRENT_STREAMS = {max_concurrent} (0x{max_concurrent:x})")
    print(f"    INITIAL_WINDOW_SIZE    = {initial_window} (0x{initial_window:x})")
    print()
    print(f"  Client ACK ({len(client_ack)} bytes):")
    print(f"    hex: {frame_hex(client_ack)}")
    print(f"    flags = 0x1 (ACK)")


def step_open_streams(conn: Http2Connection,
                      stream_ids: list[int], authorities: list[str]) -> None:
    """Step 3 — Open one stream per coalesced origin."""
    print_header(3, "Open Streams — one HEADERS frame per origin")
    for sid, auth in zip(stream_ids, authorities):
        ok, state = conn.open_stream(sid, auth)
        frame = build_headers_frame(sid, auth)
        print(f"  stream {sid} ({auth}):  {state}")
        print(f"    HEADERS frame hex: {frame_hex(frame[:9])} ...")
        print(f"    stream_window = {conn.streams[sid].stream_window}")


def step_send_data(conn: Http2Connection, stream_id: int, byte_count: int) -> None:
    """Step 4 — Server sends DATA on stream 1, draining the connection window."""
    print_header(4, f"Drain Connection Window — DATA on stream {stream_id}")
    sent, blocked = conn.send_data(stream_id, byte_count)
    s = conn.streams[stream_id]

    # Build and show the first DATA frame (chunk limited to 16384 per RFC)
    chunk = min(byte_count, 16384)
    frame = build_data_frame(stream_id, chunk)
    print(f"  Sending {byte_count} bytes on stream {stream_id} ({s.authority})")
    print(f"  (showing first DATA frame of {chunk} bytes)")
    print(f"    hex: {frame_hex(frame[:9])} ... [{chunk} bytes payload]")
    print()
    print(f"  bytes actually sent : {sent}")
    print(f"  bytes blocked       : {blocked}")
    print(f"  conn_window after   : {conn.conn_window}")
    print(f"  stream_window after : {s.stream_window}")

    if conn.conn_window == 0:
        print()
        print("  >> Connection window exhausted.")
        print("  >> Streams 3 and 5 have credit in their stream windows")
        print("  >> but cannot send DATA — min(conn_window=0, stream_window) = 0.")


def step_status(conn: Http2Connection) -> None:
    """Step 5 (or 7) — Print per-stream state and deadlock indicator."""
    print_header(5 if conn.conn_window == 0 else 7, "Status")
    print(f"  conn_window    : {conn.conn_window}")
    print(f"  max_concurrent : {conn.max_concurrent_streams}")
    for s in sorted(conn.streams.values(), key=lambda x: x.stream_id):
        # Compute effective display state
        if s.state == StreamState.OPEN and conn.conn_window == 0 and s.bytes_sent < DEFAULT_INITIAL_WINDOW_SIZE:
            display = "BLOCKED(conn_window=0)"
        else:
            display = s.state
        print(f"    stream {s.stream_id} ({s.authority}): {display}  "
              f"stream_window={s.stream_window}  bytes_sent={s.bytes_sent}")
    deadlock = conn.is_deadlocked()
    print(f"  DEADLOCK       : {deadlock}")
    if deadlock:
        print("  >> chrome://net-export would log HTTP2_SESSION_SEND_DATA_BLOCKED")
        print("  >> and HTTP2_STREAM_FLOW_CONTROL_BLOCKED for streams 3 and 5.")


def step_window_update(conn: Http2Connection, stream_id: int,
                       increment: int) -> None:
    """Step 6 — Issue WINDOW_UPDATE(stream=0) to clear the stall."""
    print_header(6, f"WINDOW_UPDATE  stream={stream_id}  increment={increment}")
    frame = build_window_update_frame(stream_id, increment)
    print(f"  Frame ({len(frame)} bytes):")
    print(f"    hex: {frame_hex(frame)}")
    origin_label = "connection-level" if stream_id == 0 else f"stream {stream_id}"
    print(f"  Target         : {origin_label}")
    print(f"  conn_window before: {conn.conn_window}")
    conn.apply_window_update(stream_id, increment)
    print(f"  conn_window after : {conn.conn_window}")


def step_confirm_unblocked(conn: Http2Connection) -> None:
    """Step 7 — Confirm deadlock cleared after WINDOW_UPDATE."""
    # Reuse status display with a different step header
    print()
    print(SEP)
    print("  Step 7: Confirm Stall Cleared")
    print(SEP)
    print(f"  conn_window    : {conn.conn_window}")
    for s in sorted(conn.streams.values(), key=lambda x: x.stream_id):
        print(f"    stream {s.stream_id} ({s.authority}): {s.state}  "
              f"stream_window={s.stream_window}  bytes_sent={s.bytes_sent}")
    deadlock = conn.is_deadlocked()
    print(f"  DEADLOCK       : {deadlock}")
    if not deadlock:
        print("  >> Streams 3 and 5 are now UNBLOCKED.")
        print("  >> Server can send font (stream 3) and beacon (stream 5).")


def step_middlebox(conn: Http2Connection, max_concurrent: int) -> None:
    """Step 8 — Simulate middlebox rewrite of MAX_CONCURRENT_STREAMS."""
    print_header(8, f"Middlebox SETTINGS Rewrite → MAX_CONCURRENT_STREAMS={max_concurrent}")
    conn2 = Http2Connection(
        ip=conn.ip,
        san=conn.san,
        max_concurrent_streams=max_concurrent,
        initial_window_size=DEFAULT_INITIAL_WINDOW_SIZE,
    )
    # Build and show the middlebox-rewritten SETTINGS frame
    rewritten_frame = build_settings_frame({
        SETTINGS_MAX_CONCURRENT_STREAMS: max_concurrent,
    })
    print(f"  Middlebox-rewritten SETTINGS ({len(rewritten_frame)} bytes):")
    print(f"    hex: {frame_hex(rewritten_frame)}")
    print(f"    MAX_CONCURRENT_STREAMS = {max_concurrent} "
          f"(origin configured 100)")
    print()

    # Try opening stream 1 (a.example) then stream 3 (b.example)
    ok1, state1 = conn2.open_stream(1, "a.example")
    ok3, state3 = conn2.open_stream(3, "b.example")

    # RST_STREAM with error code REFUSED_STREAM (0x7)
    rst = build_rst_stream_frame(3, 0x7)
    print(f"  stream 1 (a.example): {state1}")
    print(f"  stream 3 (b.example): {state3}")
    if state3 == StreamState.REFUSED:
        print(f"    RST_STREAM frame hex: {frame_hex(rst)}")
        print(f"    error_code = 0x7 (REFUSED_STREAM)")
        print()
        print("  >> With MAX_CONCURRENT_STREAMS=1, every coalesced origin")
        print("  >> after the first queues or is refused immediately.")
        print("  >> Minimum value allowing 3 origins without queuing: 3")
    else:
        # Restore
        conn2.max_concurrent_streams = 100
        print(f"  Restored MAX_CONCURRENT_STREAMS=100; streams can proceed.")


# ---------------------------------------------------------------------------
# Topology diagram (ASCII art from lesson prose)
# ---------------------------------------------------------------------------
def print_diagram() -> None:
    print()
    print(SEP)
    print("  Coalescing topology and deadlock sequence")
    print(SEP)
    diagram = """\
  Browser ──TLS(h2, SAN=a,b,c)──► Server:443
    stream 1 (a.example)  consumes full conn_window (65535 B)  ─► STALLS
    stream 3 (b.example)  stream_window=65535 but conn_window=0 ─► BLOCKED
    stream 5 (c.example)  stream_window=65535 but conn_window=0 ─► BLOCKED
                   │
                   │  Client never issues WINDOW_UPDATE
                   │  (render-blocked on stream 1 HTML)
                   ▼
              DEADLOCK  (streams 3+5 cannot deliver font / beacon)
                   │
                   │  WINDOW_UPDATE(stream=0, increment=65535)
                   ▼
              UNBLOCKED (conn_window=65535; all streams can send)
"""
    print(diagram)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
MODES = [
    "setup", "settings", "open-streams", "send-data",
    "status", "window-update", "confirm", "middlebox", "all",
]

ORIGINS = ["a.example", "b.example", "c.example"]
SERVER_IP = "203.0.113.42"
STREAM_IDS = [1, 3, 5]
MAX_CONCURRENT = 100
INITIAL_WINDOW = DEFAULT_INITIAL_WINDOW_SIZE  # 65535


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="HTTP/2 coalescing and stream deadlock simulator."
    )
    ap.add_argument(
        "--mode", default="all", choices=MODES,
        help="Which step to run (default: all)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    print()
    print("HTTP/2 Coalescing and Stream Deadlock — Lab 14")
    print_diagram()

    # All steps share a single connection object so state persists across them.
    conn: Http2Connection | None = None
    origin: Origin | None = None

    def ensure_conn() -> Http2Connection:
        nonlocal conn, origin
        if conn is None:
            conn, origin = step_setup(ORIGINS, SERVER_IP)
            step_settings(conn, MAX_CONCURRENT, INITIAL_WINDOW)
            step_open_streams(conn, STREAM_IDS, ORIGINS)
        return conn

    mode = args.mode

    if mode in ("setup", "all"):
        conn, origin = step_setup(ORIGINS, SERVER_IP)

    if mode in ("settings", "all"):
        c = ensure_conn()
        if mode == "settings":
            step_settings(c, MAX_CONCURRENT, INITIAL_WINDOW)
        else:
            step_settings(c, MAX_CONCURRENT, INITIAL_WINDOW)

    if mode in ("open-streams", "all"):
        c = ensure_conn()
        if mode == "open-streams":
            step_open_streams(c, STREAM_IDS, ORIGINS)
        else:
            step_open_streams(c, STREAM_IDS, ORIGINS)

    if mode in ("send-data", "all"):
        c = ensure_conn()
        step_send_data(c, stream_id=1, byte_count=INITIAL_WINDOW)

    if mode in ("status", "all"):
        c = ensure_conn()
        if "send-data" not in (mode,):  # ensure window is drained for standalone
            if mode == "status":
                c = ensure_conn()
                if c.conn_window == INITIAL_WINDOW:
                    step_send_data(c, stream_id=1, byte_count=INITIAL_WINDOW)
        step_status(c)

    if mode in ("window-update", "all"):
        c = ensure_conn()
        step_window_update(c, stream_id=0, increment=INITIAL_WINDOW)

    if mode in ("confirm", "all"):
        c = ensure_conn()
        step_confirm_unblocked(c)

    if mode in ("middlebox", "all"):
        c = ensure_conn()
        step_middlebox(c, max_concurrent=1)

    print()
    print(SEP)
    print("  Summary")
    print(SEP)
    print()
    print("  Key frame types used:")
    print("    HEADERS     (0x1) — opens a stream, carries :authority pseudo-header")
    print("    DATA        (0x0) — carries body bytes; decrements both windows")
    print("    SETTINGS    (0x4) — exchanges MAX_CONCURRENT_STREAMS, INITIAL_WINDOW")
    print("    WINDOW_UPDATE(0x8)— restores flow-control credit; stream_id=0 = conn")
    print("    RST_STREAM  (0x3) — refuses stream 3 when max_concurrent=1")
    print()
    print("  Coalescing conditions (RFC 9113 §9.1):")
    print("    1. New origin resolves to same IP as existing connection")
    print("    2. TLS certificate SAN covers the new hostname")
    print("    3. ALPN negotiated 'h2' on the existing connection")
    print()
    print("  Flow-control arithmetic:")
    print("    bytes_allowed = min(conn_window, stream_window)")
    print(f"    At window=0: streams 3,5 blocked despite stream_window={INITIAL_WINDOW}")
    print()
    print("  Mitigations:")
    print("    - Tune INITIAL_WINDOW_SIZE / WINDOW_UPDATE cadence on the server")
    print("    - Raise OS TCP buffers (net.core.rmem_default)")
    print("    - Split origins to distinct IPs (break coalescing precondition #1)")
    print("    - Issue separate TLS cert (break coalescing precondition #2)")
    print("    - Chrome: --disable-features=Http2Coalescing")
    print()


if __name__ == "__main__":
    main()
