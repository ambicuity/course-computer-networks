#!/usr/bin/env python3
"""TCP connection establishment and release simulator.

Stdlib only. Demonstrates Sec 6.5.5-6.5.6:

1. Three-way handshake: SYN -> SYN-ACK -> ACK, with ISN exchange and
   the SYN consuming 1 byte of sequence space.
2. Four-way close: FIN -> ACK -> FIN -> ACK (half-close semantics).
3. Simultaneous close: both sides send FIN at the same time.
4. SYN flood defense via SYN cookies (cryptographic ISN, stateless server).

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

FLAG_SYN = 0x02
FLAG_ACK = 0x10
FLAG_FIN = 0x01
FLAG_RST = 0x04


@dataclass
class TCPSegment:
    seq: int
    ack: int
    flags: int
    payload: bytes = b""
    window: int = 65535

    def flag_str(self) -> str:
        parts = []
        if self.flags & FLAG_SYN: parts.append("SYN")
        if self.flags & FLAG_ACK: parts.append("ACK")
        if self.flags & FLAG_FIN: parts.append("FIN")
        if self.flags & FLAG_RST: parts.append("RST")
        return ",".join(parts) if parts else "-"

    def __str__(self) -> str:
        return (f"[{self.flag_str()}] seq={self.seq} ack={self.ack} "
                f"win={self.window} data={len(self.payload)}B")


@dataclass
class TCPEndpoint:
    name: str
    isn: int
    send_next: int = 0
    recv_next: int = 0
    state: str = "CLOSED"
    sent_fin_seq: int = -1

    def init_seq(self) -> None:
        self.send_next = self.isn

    def send(self, flags: int, payload: bytes = b"", window: int = 65535) -> TCPSegment:
        seg = TCPSegment(seq=self.send_next, ack=self.recv_next,
                         flags=flags, payload=payload, window=window)
        consumed = len(payload)
        if flags & FLAG_SYN:
            consumed += 1
        if flags & FLAG_FIN:
            consumed += 1
            self.sent_fin_seq = self.send_next
        self.send_next += consumed
        return seg

    def receive(self, seg: TCPSegment) -> bool:
        if seg.flags & FLAG_SYN:
            if seg.flags & FLAG_ACK:
                self.recv_next = seg.seq + 1
            else:
                self.recv_next = seg.seq + 1
        if len(seg.payload) > 0:
            if seg.seq == self.recv_next:
                self.recv_next += len(seg.payload)
                return True
            return False
        if seg.flags & FLAG_FIN:
            if seg.seq == self.recv_next:
                self.recv_next = seg.seq + 1
                return True
        if seg.flags & FLAG_ACK:
            return True
        return True


def syn_cookie(peer_ip: str, peer_port: int, mss: int, secret: str) -> int:
    """Generate a stateless SYN cookie (simplified version of RFC 4987)."""
    key = f"{peer_ip}:{peer_port}:{secret}".encode()
    h = hashlib.md5(key).digest()
    cookie = struct.unpack("!I", h[:4])[0]
    cookie = (cookie & 0x00FFFFFF) | ((mss_to_code(mss) & 0x0F) << 24)
    return cookie


def mss_to_code(mss: int) -> int:
    table = [1460, 1380, 1132, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100, 64, 32, 16]
    for i, v in enumerate(table):
        if mss >= v:
            return i
    return 15


def code_to_mss(code: int) -> int:
    table = [1460, 1380, 1132, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100, 64, 32, 16]
    return table[code & 0x0F]


# ---------------------------------------------------------------------------
# Handshake simulation
# ---------------------------------------------------------------------------

def simulate_handshake() -> list[str]:
    """Three-way handshake: client (active open) + server (passive open)."""
    log: list[str] = []
    client = TCPEndpoint("Client", isn=1000)
    server = TCPEndpoint("Server", isn=5000)

    client.init_seq()
    client.state = "SYN_SENT"
    syn = client.send(FLAG_SYN)
    log.append(f"1. Client -> Server: {syn}  (client: CLOSED -> SYN_SENT)")
    server.receive(syn)
    server.state = "SYN_RCVD"

    syn_ack = server.send(FLAG_SYN | FLAG_ACK)
    log.append(f"2. Server -> Client: {syn_ack}  (server: LISTEN -> SYN_RCVD)")
    client.receive(syn_ack)
    client.state = "ESTABLISHED"

    ack = client.send(FLAG_ACK)
    log.append(f"3. Client -> Server: {ack}  (client: SYN_SENT -> ESTABLISHED)")
    server.receive(ack)
    server.state = "ESTABLISHED"

    log.append(f"   Result: Client state={client.state}, Server state={server.state}")
    log.append(f"   Client: send_next={client.send_next} recv_next={client.recv_next}")
    log.append(f"   Server: send_next={server.send_next} recv_next={server.recv_next}")
    log.append(f"   SYN consumed 1 byte of seq space (ISN+1 was acked)")
    return log


def simulate_close() -> list[str]:
    """Four-way close: client initiates, server follows."""
    log: list[str] = []
    client = TCPEndpoint("Client", isn=1000, send_next=2000, recv_next=6001, state="ESTABLISHED")
    server = TCPEndpoint("Server", isn=5000, send_next=6001, recv_next=2000, state="ESTABLISHED")

    fin1 = client.send(FLAG_FIN | FLAG_ACK)
    client.state = "FIN_WAIT_1"
    log.append(f"1. Client -> Server: {fin1}  (client: ESTABLISHED -> FIN_WAIT_1)")

    server.receive(fin1)
    ack1 = server.send(FLAG_ACK)
    server.state = "CLOSE_WAIT"
    log.append(f"2. Server -> Client: {ack1}  (server: ESTABLISHED -> CLOSE_WAIT)")
    client.receive(ack1)
    client.state = "FIN_WAIT_2"
    log.append(f"   (client: FIN_WAIT_1 -> FIN_WAIT_2; one direction now closed)")

    fin2 = server.send(FLAG_FIN | FLAG_ACK)
    server.state = "LAST_ACK"
    log.append(f"3. Server -> Client: {fin2}  (server: CLOSE_WAIT -> LAST_ACK)")

    client.receive(fin2)
    ack2 = client.send(FLAG_ACK)
    client.state = "TIME_WAIT"
    log.append(f"4. Client -> Server: {ack2}  (client: FIN_WAIT_2 -> TIME_WAIT)")
    server.receive(ack2)
    server.state = "CLOSED"
    log.append(f"   (server: LAST_ACK -> CLOSED)")
    log.append(f"   Client waits 2*MSL in TIME_WAIT, then -> CLOSED")
    return log


def simulate_simultaneous_close() -> list[str]:
    """Both sides send FIN at the same time."""
    log: list[str] = []
    a = TCPEndpoint("HostA", isn=100, send_next=500, recv_next=600, state="ESTABLISHED")
    b = TCPEndpoint("HostB", isn=200, send_next=600, recv_next=500, state="ESTABLISHED")

    fin_a = a.send(FLAG_FIN | FLAG_ACK)
    a.state = "FIN_WAIT_1"
    fin_b = b.send(FLAG_FIN | FLAG_ACK)
    b.state = "FIN_WAIT_1"
    log.append(f"1. HostA -> HostB: {fin_a}  (HostA: -> FIN_WAIT_1)")
    log.append(f"1. HostB -> HostA: {fin_b}  (HostB: -> FIN_WAIT_1) [simultaneous!]")

    a.receive(fin_b)
    b.receive(fin_a)
    ack_a = a.send(FLAG_ACK)
    ack_b = b.send(FLAG_ACK)
    a.state = "CLOSING"
    b.state = "CLOSING"
    log.append(f"2. HostA -> HostB: {ack_a}  (HostA: FIN_WAIT_1 -> CLOSING)")
    log.append(f"2. HostB -> HostA: {ack_b}  (HostB: FIN_WAIT_1 -> CLOSING)")

    a.receive(ack_b)
    b.receive(ack_a)
    a.state = "TIME_WAIT"
    b.state = "TIME_WAIT"
    log.append(f"3. Both enter TIME_WAIT, then -> CLOSED after 2*MSL")
    return log


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("TCP Three-Way Handshake (Fig 6-37a)")
    print("=" * 70)
    for line in simulate_handshake():
        print(f"  {line}")

    print()
    print("=" * 70)
    print("TCP Four-Way Close (Normal Case)")
    print("=" * 70)
    for line in simulate_close():
        print(f"  {line}")

    print()
    print("=" * 70)
    print("Simultaneous Close (Fig 6-37b analog)")
    print("=" * 70)
    for line in simulate_simultaneous_close():
        print(f"  {line}")

    print()
    print("=" * 70)
    print("SYN Cookies: Stateless Defense Against SYN Flood")
    print("=" * 70)
    secret = "my-secret-key-2024"
    peer_ip = "10.0.0.99"
    peer_port = 12345
    mss = 1460

    cookie = syn_cookie(peer_ip, peer_port, mss, secret)
    print(f"  Server receives SYN from {peer_ip}:{peer_port}")
    print(f"  Server receives SYN from {peer_ip}:{peer_port}")
    print(f"  Instead of storing state, server sends SYN-ACK with ISN = {cookie:#010x}")
    print(f"  MSS encoded in top 4 bits: code={mss_to_code(mss)} -> MSS={code_to_mss(cookie >> 24)}")

    expected_ack = (cookie + 1) & 0xFFFFFFFF
    print(f"  If client completes handshake, it ACKs {expected_ack:#010x}")
    print(f"  Server regenerates cookie: {syn_cookie(peer_ip, peer_port, mss, secret):#010x}")
    print(f"  (cookie+1 == ack: {expected_ack == (syn_cookie(peer_ip, peer_port, mss, secret) + 1) & 0xFFFFFFFF})")
    print()
    print("  No per-connection state stored until handshake completes.")
    print("  SYN flood sends millions of SYNs but never completes the handshake,")
    print("  so server memory is never exhausted.")


if __name__ == "__main__":
    main()