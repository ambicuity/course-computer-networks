#!/usr/bin/env python3
"""Capstone 13: QUIC Connection Migration and Idle Timeout.

Simulate QUIC connection establishment, migration across a network change
(Wi-Fi -> cellular), path validation (PATH_CHALLENGE/RESPONSE), loss
recovery, and idle timeout. Compare to TCP behavior on the same change.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random

random.seed(42)
IDLE_TIMEOUT_DEFAULT = 30.0
LOSS_DETECTION_TIMEOUT = 0.2


class PacketType(Enum):
    INITIAL = "Initial"; HANDSHAKE = "Handshake"; ONE_RTT = "1-RTT"
    PATH_CHALLENGE = "PATH_CHALLENGE"; PATH_RESPONSE = "PATH_RESPONSE"


class ConnectionState(Enum):
    HANDSHAKING = "Handshaking"; ESTABLISHED = "Established"
    MIGRATING = "Migrating"; CLOSED_IDLE = "Closed (Idle Timeout)"


@dataclass
class CID:
    cid: bytes
    def __str__(self): return f"0x{self.cid.hex().upper()}"


@dataclass
class Path:
    src_ip: str; src_port: int; dst_ip: str; dst_port: int
    is_validated: bool = False; is_primary: bool = True
    @property
    def tup(self): return f"{self.src_ip}:{self.src_port}->{self.dst_ip}:{self.dst_port}"


@dataclass
class Packet:
    t: float; ptype: PacketType; dcid: CID; path: Path; pn: int = 0
    sid: int = -1; off: int = 0; plen: int = 0
    lost: bool = False; retx: bool = False; note: str = ""


@dataclass
class QuicConn:
    cc: CID; sc: CID
    state: ConnectionState = ConnectionState.HANDSHAKING
    cur: Path | None = None; old: Path | None = None
    inflight: list[Packet] = field(default_factory=list)
    last_act: float = 0.0; idle_to: float = IDLE_TIMEOUT_DEFAULT
    next_pn: int = 0


@dataclass
class TcpConn:
    src_ip: str; src_port: int; dst_ip: str; dst_port: int
    state: str = "ESTABLISHED"; alive: bool = True
    @property
    def tup(self): return f"{self.src_ip}:{self.src_port}->{self.dst_ip}:{self.dst_port}"


def mk_conn() -> QuicConn:
    return QuicConn(CID(b"\x1A\x2B\x3C\x4D\x5E\x6F\x70\x81"),
                    CID(b"\x82\x83\x84\x85\x86\x87\x88\x89"))


def handshake(c: QuicConn, cp: Path, sp: Path) -> list[Packet]:
    ps: list[Packet] = []
    t = 0.0
    ps.append(Packet(t, PacketType.INITIAL, c.sc, cp, 0, note="Client Initial: CID + ClientHello"))
    t += 0.030
    ps.append(Packet(t, PacketType.INITIAL, c.cc, sp, 0, note="Server Initial: CID + ServerHello"))
    ps.append(Packet(t, PacketType.HANDSHAKE, c.cc, sp, 1, note="Server Handshake: cert + Finished"))
    t += 0.030
    ps.append(Packet(t, PacketType.HANDSHAKE, c.sc, cp, 1, note="Client Handshake: Finished"))
    t += 0.001
    ps.append(Packet(t, PacketType.ONE_RTT, c.sc, cp, 2, sid=0, off=0, plen=100, note="Client 1-RTT data"))
    c.state = ConnectionState.ESTABLISHED; c.cur = cp; c.last_act = t
    return ps


def data_xfer(c: QuicConn, n: int = 5, t0: float = 0.1) -> list[Packet]:
    ps: list[Packet] = []; t = t0
    for i in range(n):
        p = Packet(t, PacketType.ONE_RTT, c.sc, c.cur, c.next_pn,
                   sid=0, off=i*100, plen=100, note=f"Data #{c.next_pn}")
        ps.append(p); c.inflight.append(p); c.next_pn += 1; c.last_act = t
        t += 0.020
    return ps


def migrate(c: QuicConn, np: Path, t0: float) -> tuple[list[Packet], list[Packet]]:
    """Migrate to new path with PATH_CHALLENGE/RESPONSE, retransmit lost packets."""
    mp: list[Packet] = []; lp: list[Packet] = []
    t = t0; c.old = c.cur; c.state = ConnectionState.MIGRATING
    pn = c.next_pn
    mp.append(Packet(t, PacketType.ONE_RTT, c.sc, np, pn,
        note=f"Client migrates to {np.tup}, same CID {c.cc}"))
    c.next_pn += 1; c.last_act = t; t += 0.030
    ch = b"\x12\x34\x56\x78\x9A\xBC\xDE\xF0"
    mp.append(Packet(t, PacketType.PATH_CHALLENGE, c.cc, np, pn+1,
        note=f"Server PATH_CHALLENGE data={ch.hex()}"))
    c.next_pn += 1; t += 0.030
    mp.append(Packet(t, PacketType.PATH_RESPONSE, c.sc, np, pn+2,
        note=f"Client PATH_RESPONSE echoes {ch.hex()}"))
    c.next_pn += 1; np.is_validated = True; t += 0.030
    c.cur = np; c.old.is_primary = False; np.is_primary = True
    c.state = ConnectionState.ESTABLISHED
    mp.append(Packet(t, PacketType.ONE_RTT, c.cc, np, pn+3,
        sid=0, off=500, plen=100, note="Server data on new path"))
    c.next_pn += 1; c.last_act = t; t += 0.030
    # Loss recovery: old-path packets are now lost
    tl = t + LOSS_DETECTION_TIMEOUT
    for pkt in c.inflight:
        if pkt.path == c.old:
            pkt.lost = True; lp.append(pkt)
            mp.append(Packet(tl, PacketType.ONE_RTT, c.sc, np, c.next_pn,
                sid=pkt.sid, off=pkt.off, plen=pkt.plen, retx=True,
                note=f"Retransmit of lost pkt #{pkt.pn}"))
            c.next_pn += 1
    c.inflight = [p for p in c.inflight if not p.lost]
    return mp, lp


def idle_timeout(c: QuicConn, t0: float) -> tuple[float, bool]:
    t = t0 + c.idle_to + 1
    if t - c.last_act >= c.idle_to:
        c.state = ConnectionState.CLOSED_IDLE; return t, True
    return t, False


def tcp_migrate(t: TcpConn, ip: str, port: int) -> bool:
    t.src_ip, t.src_port = ip, port; t.state, t.alive = "BROKEN", False
    return False


def main() -> None:
    print("=" * 65)
    print("Capstone 13: QUIC Connection Migration and Idle Timeout")
    print("=" * 65)
    c = mk_conn()
    cp = Path("192.168.1.5", 54321, "93.184.216.34", 443)
    sp = Path("93.184.216.34", 443, "192.168.1.5", 54321)
    np = Path("10.0.0.5", 54322, "93.184.216.34", 443)
    print(f"\n  CIDs: client={c.cc}, server={c.sc}")
    print(f"\n  --- Handshake ---")
    for p in handshake(c, cp, sp):
        print(f"    t={p.t:.3f} [{p.ptype.value:<15}] PN={p.pn} {p.note}")
    print(f"    State: {c.state.value}")
    print(f"\n  --- Data Transfer ---")
    data_xfer(c, 5, 0.1)
    print(f"    5 data packets sent, in-flight: {len(c.inflight)}")
    print(f"\n  --- Network Change (Wi-Fi -> Cellular) ---")
    print(f"    Old: {c.cur.tup}  ->  New: {np.tup}")
    print(f"\n  --- QUIC Migration ---")
    mp, lp = migrate(c, np, 0.3)
    for p in mp:
        print(f"    t={p.t:.3f} [{p.ptype.value:<15}] PN={p.pn} {p.note[:65]}")
    retx = [p for p in mp if p.retx]
    print(f"\n    {len(lp)} packets on old path lost, {len(retx)} retransmitted on new")
    print(f"    Connection survived: CID {c.cc} unchanged, new path validated")
    print(f"\n  --- Idle Timeout ---")
    tt, fired = idle_timeout(c, 0.5)
    if fired:
        print(f"    At t={tt:.0f}s, idle {tt-c.last_act:.0f}s >= {c.idle_to:.0f}s -> {c.state.value}")
        print(f"    No FIN, no RST - silent close")
    print(f"\n  --- TCP Comparison (same change) ---")
    tcp = TcpConn("192.168.1.5", 54321, "93.184.216.34", 443)
    print(f"    TCP before: {tcp.tup}")
    tcp_migrate(tcp, "10.0.0.5", 54322)
    print(f"    TCP after:  {tcp.tup}  state={tcp.state} alive={tcp.alive}")
    print(f"    Application must reconnect: +50-200ms handshake penalty")
    print(f"\n  Summary: QUIC connection {c.cc} migrated from {c.old.tup} to")
    print(f"    {c.cur.tup}. Server validated new path via PATH_CHALLENGE/RESPONSE,")
    print(f"    retransmitted {len(retx)} lost packets. Idle timeout fired after")
    print(f"    {c.idle_to:.0f}s of silence. TCP would have died on the same change.")


if __name__ == "__main__":
    main()
