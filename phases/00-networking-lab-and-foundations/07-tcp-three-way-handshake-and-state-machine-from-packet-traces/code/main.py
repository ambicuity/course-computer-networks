"""TCP three-way handshake and connection state machine, parsed from packet traces.

Pure-stdlib model of RFC 793's connection establishment. It:

  * Parses a minimal TCP header (20-byte fixed part) out of a bytes blob,
    reading the real fields -- src/dst port, 32-bit seq/ack numbers, the
    16-bit flags word (with the SYN/ACK/FIN/RST bits at their real offsets),
    the 16-bit window, the 16-bit checksum, and the 16-bit urgent pointer.
  * Computes the Internet checksum (RFC 1071, one's-complement sum) over the
    header plus a pseudo-header, and validates it.
  * Drives an 11-state connection FSM through the three-way handshake,
    reproducing the ISN arithmetic (SEG.NEXT = ISN+1 after SYN) and the
    state transitions CLOSED -> SYN_SENT -> ESTABLISHED on the client and
    LISTEN -> SYN_RCVD -> ESTABLISHED on the server.
  * Tears the connection down with the four-wave FIN exchange and shows the
    TIME_WAIT 2*MSL hold so late retransmits do not reopen a port.

No network calls, no third-party packages. Run:  python3 main.py
"""

from __future__ import annotations

import random
import struct
from dataclasses import dataclass, field
from enum import IntFlag, auto

# --- TCP flags (RFC 793, Section 3.1, "Control Bits") ------------------------

FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10
URG = 0x20

FLAG_NAMES = {FIN: "FIN", SYN: "SYN", RST: "RST", PSH: "PSH", ACK: "ACK", URG: "URG"}


def flag_string(flags: int) -> str:
    return ",".join(name for bit, name in FLAG_NAMES.items() if flags & bit) or "."


# --- TCP header layout -------------------------------------------------------

TCP_HEADER_FMT = "!HHIIHHHH"  # sport,dport,seq,ack,off+flags,win,cksum,urg
TCP_HEADER_LEN = 20


@dataclass
class TCPHeader:
    src_port: int
    dst_port: int
    seq: int
    ack: int
    data_offset: int  # in 32-bit words; 5 means a 20-byte header
    flags: int
    window: int
    checksum: int
    urgent: int

    def is_valid_offsets(self) -> bool:
        return 5 <= self.data_offset <= 15

    def seg_len(self, payload_len: int) -> int:
        # SYN and FIN each consume one sequence number (RFC 793 3.3)
        n = payload_len
        if self.flags & SYN:
            n += 1
        if self.flags & FIN:
            n += 1
        return n


def parse_tcp_header(raw: bytes) -> TCPHeader:
    if len(raw) < TCP_HEADER_LEN:
        raise ValueError(f"need at least {TCP_HEADER_LEN} bytes, got {len(raw)}")
    sport, dport, seq, ack, off_flags, win, cksum, urg = struct.unpack(
        TCP_HEADER_FMT, raw[:TCP_HEADER_LEN]
    )
    data_offset = (off_flags >> 12) & 0xF
    flags = off_flags & 0x1FF
    return TCPHeader(sport, dport, seq, ack, data_offset, flags, win, cksum, urg)


# --- RFC 1071 Internet checksum ---------------------------------------------


def internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def tcp_checksum(header_bytes: bytes, payload: bytes, src_ip: bytes, dst_ip: bytes) -> int:
    # RFC 793 pseudo-header: src(4) dst(4) zero(1) proto(1) tcp_len(2)
    pseudo = src_ip + dst_ip + b"\x00\x06" + struct.pack("!H", len(header_bytes) + len(payload))
    return internet_checksum(pseudo + header_bytes + payload)


# --- Connection state machine (RFC 793, Section 3.2) ------------------------


class TCPState(IntFlag):
    CLOSED = auto()
    LISTEN = auto()
    SYN_SENT = auto()
    SYN_RCVD = auto()
    ESTABLISHED = auto()
    FIN_WAIT_1 = auto()
    FIN_WAIT_2 = auto()
    CLOSING = auto()
    TIME_WAIT = auto()
    CLOSE_WAIT = auto()
    LAST_ACK = auto()


STATE_NAMES = {
    TCPState.CLOSED: "CLOSED",
    TCPState.LISTEN: "LISTEN",
    TCPState.SYN_SENT: "SYN_SENT",
    TCPState.SYN_RCVD: "SYN_RCVD",
    TCPState.ESTABLISHED: "ESTABLISHED",
    TCPState.FIN_WAIT_1: "FIN_WAIT_1",
    TCPState.FIN_WAIT_2: "FIN_WAIT_2",
    TCPState.CLOSING: "CLOSING",
    TCPState.TIME_WAIT: "TIME_WAIT",
    TCPState.CLOSE_WAIT: "CLOSE_WAIT",
    TCPState.LAST_ACK: "LAST_ACK",
}


@dataclass
class TCB:
    """A Transmission Control Block -- per-connection state (RFC 793 3.4)."""
    name: str
    state: TCPState = TCPState.CLOSED
    snd_una: int = 0  # oldest unacknowledged seq
    snd_nxt: int = 0  # next seq to send
    rcv_nxt: int = 0  # next seq expected
    iss: int = 0      # initial send sequence
    irs: int = 0      # initial receive sequence
    log: list = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.log.append(f"[{self.name:>6} {STATE_NAMES[self.state]:<12}] {msg}")


def client_open(c: TCB, server_isn: int, client_isn: int) -> None:
    """Drive the active opener through the three-way handshake."""
    c.iss = client_isn
    c.snd_nxt = c.iss + 1
    c.state = TCPState.SYN_SENT
    c.note(f"send SYN seq={c.iss} (SEG.NEXT becomes {c.snd_nxt})")

    # receive SYN,ACK from server
    c.irs = server_isn
    c.rcv_nxt = c.irs + 1
    c.snd_una = c.iss + 1  # our SYN is now acked
    c.state = TCPState.ESTABLISHED
    c.note(f"recv SYN,ACK irs={c.irs}; send ACK seq={c.snd_nxt} ack={c.rcv_nxt}")
    c.note(f"ESTABLISHED  snd_nxt={c.snd_nxt} rcv_nxt={c.rcv_nxt}")


def server_open(s: TCB, client_isn: int, server_isn: int) -> None:
    """Drive the passive opener through the three-way handshake."""
    s.iss = server_isn
    s.state = TCPState.LISTEN
    s.note("LISTEN waiting for SYN")

    s.irs = client_isn
    s.rcv_nxt = s.irs + 1
    s.snd_nxt = s.iss + 1
    s.state = TCPState.SYN_RCVD
    s.note(f"recv SYN irs={s.irs}; send SYN,ACK seq={s.iss} ack={s.rcv_nxt}")

    s.snd_una = s.iss + 1  # our SYN acked by final ACK
    s.state = TCPState.ESTABLISHED
    s.note(f"recv ACK ack={s.snd_una}; ESTABLISHED snd_nxt={s.snd_nxt} rcv_nxt={s.rcv_nxt}")


def close_active(c: TCB, msl: float = 60.0) -> None:
    """Four-wave close from the active side, ending in TIME_WAIT for 2*MSL."""
    c.state = TCPState.FIN_WAIT_1
    c.note(f"send FIN seq={c.snd_nxt}; FIN consumes one seq -> {c.snd_nxt + 1}")
    c.snd_nxt += 1

    c.state = TCPState.FIN_WAIT_2
    c.note("recv ACK of our FIN; half-close, still receive")

    c.state = TCPState.TIME_WAIT
    c.note("recv server FIN; send final ACK; hold 2*MSL to catch retransmits")
    c.note(f"TIME_WAIT {2*msl:.0f}s then -> CLOSED (frees port)")
    c.state = TCPState.CLOSED


def close_passive(s: TCB) -> None:
    s.state = TCPState.CLOSE_WAIT
    s.note("recv client FIN; send ACK; CLOSE_WAIT (app should close())")

    s.state = TCPState.LAST_ACK
    s.note(f"app close(); send FIN seq={s.snd_nxt}; FIN consumes one seq")
    s.snd_nxt += 1

    s.state = TCPState.CLOSED
    s.note("recv ACK of our FIN; CLOSED")


def make_segment(src_port: int, dst_port: int, seq: int, ack: int,
                 flags: int, win: int, payload: bytes = b"",
                 src_ip: bytes = b"\xc0\xa8\x01\x05",
                 dst_ip: bytes = b"\xc0\xa8\x01\x0a") -> bytes:
    """Build a real 20-byte TCP header with a correct checksum."""
    data_offset = 5
    off_flags = (data_offset << 12) | flags
    hdr = struct.pack(TCP_HEADER_FMT, src_port, dst_port, seq, ack,
                      off_flags, win, 0, 0)
    cksum = tcp_checksum(hdr, payload, src_ip, dst_ip)
    hdr = struct.pack(TCP_HEADER_FMT, src_port, dst_port, seq, ack,
                      off_flags, win, cksum, 0)
    return hdr + payload


def main() -> None:
    rng = random.Random(0x793)
    client_isn = rng.randrange(1 << 32)
    server_isn = rng.randrange(1 << 32)

    print("=" * 72)
    print("THREE-WAY HANDSHAKE  (RFC 793, Section 3.4)")
    print(f"  client ISN = {client_isn:#010x}   server ISN = {server_isn:#010x}")
    print("=" * 72)

    client = TCB("client")
    server = TCB("server")
    client_open(client, server_isn, client_isn)
    server_open(server, client_isn, server_isn)
    for line in client.log:
        print(line)
    print("-" * 72)
    for line in server.log:
        print(line)

    print("\n" + "=" * 72)
    print("WIRE SEGMENTS  (built + re-parsed, checksum verified)")
    print("=" * 72)
    segs = [
        ("SYN      ", make_segment(51512, 80, client_isn, 0, SYN, 64240)),
        ("SYN,ACK  ", make_segment(80, 51512, server_isn, client_isn + 1, SYN | ACK, 64240)),
        ("ACK      ", make_segment(51512, 80, client_isn + 1, server_isn + 1, ACK, 64240)),
    ]
    for label, seg in segs:
        h = parse_tcp_header(seg)
        flags_ok = tcp_checksum(seg[:TCP_HEADER_LEN], b"", b"\xc0\xa8\x01\x05", b"\xc0\xa8\x01\x0a") == 0
        print(f"{label} sport={h.src_port} dport={h.dst_port} "
              f"seq={h.seq:#010x} ack={h.ack:#010x} flags=[{flag_string(h.flags)}] "
              f"win={h.window} cksum_ok={flags_ok}")

    print("\n" + "=" * 72)
    print("FOUR-WAVE CLOSE  (active client -> TIME_WAIT 2*MSL)")
    print("=" * 72)
    close_active(client)
    close_passive(server)
    for line in client.log[3:]:
        print(line)
    print("-" * 72)
    for line in server.log[3:]:
        print(line)

    print("\n" + "=" * 72)
    print("VALIDATION: bad checksum is detected")
    print("=" * 72)
    bad = bytearray(make_segment(51512, 80, client_isn, 0, SYN, 64240))
    bad[16] ^= 0xFF  # corrupt the checksum field
    h = parse_tcp_header(bytes(bad))
    recomputed = tcp_checksum(bytes(bad)[:TCP_HEADER_LEN], b"",
                              b"\xc0\xa8\x01\x05", b"\xc0\xa8\x01\x0a")
    print(f"corrupted cksum={h.checksum:#06x}  recomputed(incl.corr)={recomputed:#06x}  "
          f"valid={recomputed == 0}  -> receiver would SILENTLY DROP (RFC 793)")


if __name__ == "__main__":
    main()
