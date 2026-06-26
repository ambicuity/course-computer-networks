#!/usr/bin/env python3
"""RPC stub simulator and RTP packet codec with jitter-buffer demo.

Stdlib only. Demonstrates four concepts from Sec 6.4.2 and 6.4.3:

1. The five-step RPC flow: client call -> marshal -> send -> receive -> unmarshal
2. Call-by-copy-restore semantics for pointer parameters (RFC 1831, Birrell-Nelson 1984)
3. RTP header layout per RFC 3550: V/P/X/CC/M/PT + sequence + timestamp + SSRC
4. A playout buffer that absorbs jitter by delaying playback by a fixed interval P

Run:  python3 main.py
"""
from __future__ import annotations

import random
import struct
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: Five-step RPC simulator (Sec 6.4.2, Birrell and Nelson 1984)
# ---------------------------------------------------------------------------

PROCEDURE_ADD = 0x01
PROCEDURE_GET_QUOTE = 0x02
PROCEDURE_INCR = 0x03


@dataclass
class RPCServer:
    """A toy server that holds procedures and a request counter."""

    procedures: dict[int, callable] = field(default_factory=dict)
    call_count: int = 0

    def register(self, proc_id: int, fn: callable) -> None:
        self.procedures[proc_id] = fn


def marshal_request(proc_id: int, args: bytes) -> bytes:
    """Pack a request: 1-byte proc_id, 4-byte length, args."""
    if proc_id > 0xFF:
        raise ValueError("proc_id out of range")
    return struct.pack("!BI", proc_id, len(args)) + args


def unmarshal_request(raw: bytes) -> tuple[int, bytes]:
    proc_id, arg_len = struct.unpack("!BI", raw[:5])
    return proc_id, raw[5:5 + arg_len]


def marshal_reply(value: bytes) -> bytes:
    return struct.pack("!I", len(value)) + value


def unmarshal_reply(raw: bytes) -> bytes:
    (length,) = struct.unpack("!I", raw[:4])
    return raw[4:4 + length]


def client_stub(server: RPCServer, proc_id: int, args: bytes) -> bytes:
    """Five-step RPC: client marshals, transmits, server unmarshals, runs, replies."""
    # Step 2: client stub marshals the arguments.
    wire = marshal_request(proc_id, args)
    # Step 3: network (simulated by direct handoff).
    received = wire
    # Step 4: server stub receives, unmarshals.
    server_proc_id, server_args = unmarshal_request(received)
    server.call_count += 1
    # Step 5: server stub calls the actual server procedure.
    if server_proc_id not in server.procedures:
        raise RuntimeError(f"unknown procedure 0x{server_proc_id:02x}")
    result = server.procedures[server_proc_id](server_args)
    reply = marshal_reply(result)
    return reply


def _demo_rpc() -> None:
    print("=" * 72)
    print("RPC Five-Step Flow (Sec 6.4.2)")
    print("=" * 72)
    srv = RPCServer()
    srv.register(PROCEDURE_ADD, lambda a: struct.pack("!i", int.from_bytes(a[:4], "big") + int.from_bytes(a[4:8], "big")))
    srv.register(PROCEDURE_INCR, lambda a: struct.pack("!i", int.from_bytes(a[:4], "big") + 1))

    def add(a: int, b: int) -> int:
        args = struct.pack("!ii", a, b)
        reply = client_stub(srv, PROCEDURE_ADD, args)
        return int.from_bytes(unmarshal_reply(reply), "big")

    def incr(p: list[int]) -> int:
        # Call-by-copy-restore: send value, server modifies, returns value.
        args = struct.pack("!i", p[0])
        reply = client_stub(srv, PROCEDURE_INCR, args)
        p[0] = int.from_bytes(unmarshal_reply(reply), "big")
        return p[0]

    print(f"  add(7, 35) = {add(7, 35)}        (5 wire bytes + 8 args)")
    counter = [41]
    incr(counter)
    print(f"  incr via copy-restore -> counter = {counter[0]}    (was 41)")
    print(f"  server call count = {srv.call_count}")


# ---------------------------------------------------------------------------
# Part 2: RTP packet codec (RFC 3550)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RTPPacket:
    """RFC 3550 RTP header plus payload."""

    version: int = 2
    padding: bool = False
    extension: bool = False
    cc: int = 0
    marker: bool = False
    payload_type: int = 0
    seq: int = 0
    timestamp: int = 0
    ssrc: int = 0
    csrc: tuple[int, ...] = ()
    payload: bytes = b""


def encode_rtp(pkt: RTPPacket) -> bytes:
    """Serialize an RTPPacket into wire bytes."""
    if not 0 <= pkt.cc <= 15:
        raise ValueError(f"CC must be 0-15, got {pkt.cc}")
    if len(pkt.csrc) != pkt.cc:
        raise ValueError(f"CC={pkt.cc} but {len(pkt.csrc)} CSRC values given")
    byte0 = (pkt.version << 6) | (int(pkt.padding) << 5) | (int(pkt.extension) << 4) | pkt.cc
    byte1 = (int(pkt.marker) << 7) | (pkt.payload_type & 0x7F)
    header = struct.pack("!BBHII", byte0, byte1, pkt.seq, pkt.timestamp, pkt.ssrc)
    for c in pkt.csrc:
        header += struct.pack("!I", c & 0xFFFFFFFF)
    return header + pkt.payload


def decode_rtp(raw: bytes) -> RTPPacket:
    """Parse wire bytes into an RTPPacket."""
    if len(raw) < 12:
        raise ValueError("RTP header must be at least 12 bytes")
    b0, b1, seq, timestamp, ssrc = struct.unpack("!BBHII", raw[:12])
    version = (b0 >> 6) & 0x03
    padding = bool((b0 >> 5) & 1)
    extension = bool((b0 >> 4) & 1)
    cc = b0 & 0x0F
    marker = bool((b1 >> 7) & 1)
    payload_type = b1 & 0x7F
    csrc = struct.unpack(f"!{cc}I", raw[12:12 + 4 * cc]) if cc else ()
    payload = raw[12 + 4 * cc:]
    return RTPPacket(version, padding, extension, cc, marker, payload_type,
                     seq, timestamp, ssrc, csrc, payload)


def _demo_rtp() -> None:
    print()
    print("=" * 72)
    print("RTP Packet Encode/Decode (RFC 3550, 12-byte minimum header)")
    print("=" * 72)
    pkt = RTPPacket(
        version=2, padding=False, extension=False, cc=1,
        marker=True, payload_type=111,  # Opus dynamic PT
        seq=1000, timestamp=48000, ssrc=0x12345678,
        csrc=(0xDEADBEEF,),
        payload=b"\x00\x01\x02\x03",
    )
    raw = encode_rtp(pkt)
    print(f"  Hex (header + payload): {raw.hex()}")
    print(f"  Header bytes (12+4 CSRC=16): {raw[:16].hex()}")
    print(f"  Header length = {12 + 4 * pkt.cc} bytes; payload = {len(pkt.payload)} bytes")
    decoded = decode_rtp(raw)
    print(f"  Decoded: V={decoded.version} P={int(decoded.padding)} X={int(decoded.extension)}")
    print(f"           CC={decoded.cc} M={int(decoded.marker)} PT={decoded.payload_type}")
    print(f"           seq={decoded.seq} timestamp={decoded.timestamp} SSRC=0x{decoded.ssrc:08x}")
    print(f"           CSRC={tuple(f'0x{c:08x}' for c in decoded.csrc)}")
    print(f"           payload={decoded.payload.hex()}")


# ---------------------------------------------------------------------------
# Part 3: Playout buffer + jitter simulation (Sec 6.4.3)
# ---------------------------------------------------------------------------

@dataclass
class PlayoutBuffer:
    """Buffer of received packets with a delayed-playback scheduler."""

    playout_delay: int              # in packet-times
    buffer: list[tuple[int, bytes]] = field(default_factory=list)

    def receive(self, seq: int, payload: bytes, current_time: int) -> None:
        self.buffer.append((current_time, payload))

    def playout(self, target_time: int) -> list[tuple[int, bytes]]:
        """Return all packets whose arrival time was on or before target - P."""
        deadline = target_time - self.playout_delay
        ready = [p for (t, p) in self.buffer if t <= deadline]
        self.buffer = [p for p in self.buffer if p not in ready]
        return ready


def simulate_jitter(n_packets: int = 20, interval: int = 20,
                    jitter_ms: int = 5, playout_p: int = 60) -> tuple[int, int]:
    """Send n_packets at uniform interval with jitter; return (played, late)."""
    rng = random.Random(42)
    received: list[tuple[int, int]] = []
    for i in range(n_packets):
        send_t = i * interval
        arrival_t = send_t + rng.randint(-jitter_ms, jitter_ms)
        received.append((send_t, max(arrival_t, send_t)))
    played = 0
    late = 0
    playout_t = -1
    buf = PlayoutBuffer(playout_delay=playout_p // interval)
    arrivals_by_t: dict[int, list[bytes]] = {}
    for send_t, arrival_t in received:
        arrivals_by_t.setdefault(arrival_t, []).append(
            f"seq={send_t // interval:03d}".encode())
    cur_t = 0
    while cur_t < (n_packets + 2) * interval:
        if cur_t in arrivals_by_t:
            for p in arrivals_by_t[cur_t]:
                buf.receive(send_t=cur_t, payload=p, current_time=cur_t)
        slot = cur_t - playout_p
        if slot >= 0 and slot in arrivals_by_t:
            ready = buf.playout(cur_t)
            for _ in ready:
                played += 1
        cur_t += interval
    deadline = (n_packets + 1) * interval - playout_p
    for send_t, arrival_t in received:
        if arrival_t > send_t + playout_p:
            late += 1
    return played, late


def _demo_playout() -> None:
    print()
    print("=" * 72)
    print("Playout Buffer (Sec 6.4.3)")
    print("=" * 72)
    for P in [40, 60, 100]:
        played, late = simulate_jitter(n_packets=20, interval=20,
                                       jitter_ms=5, playout_p=P)
        print(f"  P = {P} ms -> played {played} packets, {late} arrived too late")


# ---------------------------------------------------------------------------
# Part 4: RTCP 5%-of-media budget
# ---------------------------------------------------------------------------

def rtcp_budget(media_bps: float, n_participants: int,
                rtcp_pkt_bytes: int = 100) -> float:
    """Per-participant RTCP report interval (seconds) under 5% rule."""
    rtcp_share = 0.05 * media_bps
    per_sec = rtcp_share / 8.0
    per_participant_bps = per_sec * rtcp_pkt_bytes / n_participants
    if per_participant_bps <= 0:
        return float("inf")
    return 8.0 * rtcp_pkt_bytes / per_participant_bps


def _demo_rtcp() -> None:
    print()
    print("=" * 72)
    print("RTCP 5%-of-Media Bandwidth Budget (RFC 3550 Sec 6.2)")
    print("=" * 72)
    print(f"  {'Media kbps':>10}  {'N':>4}  {'RTCP kbps budget':>17}  {'Report interval (s)':>19}")
    for media_kbps, n in [(64, 2), (64, 10), (2000, 100), (2000, 1000)]:
        media_bps = media_kbps * 1000
        rtcp_share_kbps = 0.05 * media_kbps
        interval = rtcp_budget(media_bps, n)
        print(f"  {media_kbps:10d}  {n:4d}  {rtcp_share_kbps:15.2f}   {interval:17.2f}")


def main() -> None:
    _demo_rpc()
    _demo_rtp()
    _demo_playout()
    _demo_rtcp()


if __name__ == "__main__":
    main()
