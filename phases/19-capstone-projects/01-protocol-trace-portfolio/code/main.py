#!/usr/bin/env python3
"""Capstone 01: Protocol Trace Portfolio.

Multi-layer packet annotator: builds a synthetic multi-layer trace (DNS
lookup, TCP handshake, HTTP request/response, four-way close, RTO-based
retransmit), annotates each packet across Ethernet/IP/TCP-UDP/HTTP-DNS,
and produces a per-trace timing analysis.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Eth:
    dst: str
    src: str
    etype: int = 0x0800


@dataclass
class IP:
    proto: int
    src: str
    dst: str
    length: int
    ident: int
    ttl: int = 64


@dataclass
class TCP:
    sp: int
    dp: int
    seq: int
    ack: int
    flags: dict
    win: int = 65535


@dataclass
class UDP:
    sp: int
    dp: int
    length: int


@dataclass
class HTTP:
    method: Optional[str]
    url: Optional[str]
    status: Optional[int]
    headers: dict
    body: str = ""


@dataclass
class DNS:
    name: str
    rtype: str
    rcode: str
    answers: list


@dataclass
class Packet:
    t: float
    eth: Eth
    ip: IP
    tr: Union[TCP, UDP]
    app: Optional[Union[HTTP, DNS]] = None
    note: str = ""


PROTO = {1: "ICMP", 6: "TCP", 17: "UDP"}
SYN, SYNACK, ACK_F, PSH, FIN = ({"syn": True, "ack": False},
                                 {"syn": True, "ack": True},
                                 {"ack": True},
                                 {"ack": True, "psh": True},
                                 {"fin": True, "ack": True})
E1, E2, E3 = "AA:BB:CC:DD:EE:01", "11:22:33:44:55:66", "11:22:33:44:55:99"
C, S, R = "10.0.0.5", "93.184.216.34", "8.8.8.8"


def annotate(p: Packet) -> str:
    L = [f"  Packet @ {p.t:.3f}s",
         f"  Ethernet: {p.eth.src} -> {p.eth.dst} (IPv4)",
         f"  IPv4: {p.ip.src} -> {p.ip.dst} TTL={p.ip.ttl} proto="
         f"{PROTO.get(p.ip.proto, p.ip.proto)} len={p.ip.length} id=0x{p.ip.ident:04X}"]
    if isinstance(p.tr, TCP):
        fs = "".join(k[0].upper() for k, v in p.tr.flags.items() if v)
        L.append(f"  TCP: {p.tr.sp} -> {p.tr.dp} seq={p.tr.seq} ack={p.tr.ack} "
                 f"[{fs}] win={p.tr.win}")
        if isinstance(p.app, HTTP):
            L.append(_http(p.app))
        elif isinstance(p.app, DNS):
            L.append(f"  DNS: {p.app.name} {p.app.rtype} rcode={p.app.rcode}")
            for a in p.app.answers:
                L.append(f"    -> {a}")
    else:
        L.append(f"  UDP: {p.tr.sp} -> {p.tr.dp} len={p.tr.length}")
    if p.note:
        L.append(f"  NOTE: {p.note}")
    return "\n".join(L)


def _http(a: HTTP) -> str:
    if a.method:
        h = "\n".join(f"    {k}: {v}" for k, v in a.headers.items())
        b = f"\n    Body: {a.body[:50]}..." if a.body else ""
        return f"  HTTP: {a.method} {a.url}\n{h}{b}"
    s = f"  HTTP: {a.status} {a.headers.get('Reason', '')}\n"
    s += "\n".join(f"    {k}: {v}" for k, v in a.headers.items() if k != "Reason")
    return s


def P(t, src_mac, dst_mac, proto, src, dst, length, ident, tr, app=None, note=""):
    """Compact packet builder: header + transport in one call."""
    return Packet(t, Eth(dst_mac, src_mac), IP(proto, src, dst, length, ident), tr, app, note)


def build_dns_trace() -> list[Packet]:
    return [
        P(0.000, E1, E3, 17, C, R, 76, 0xA001, UDP(50001, 53, 44),
          DNS("example.com", "A", "NOERROR", []), "DNS query: example.com A?"),
        P(0.005, E3, E1, 17, R, C, 92, 0xB001, UDP(53, 50001, 60),
          DNS("example.com", "A", "NOERROR", ["93.184.216.34"]),
          "DNS response: example.com A 93.184.216.34 (5 ms RTT)"),
    ]


def build_sample_trace() -> list[Packet]:
    get = HTTP("GET", "/index.html", None,
               {"Host": "example.com", "User-Agent": "Mozilla/5.0"})
    ok = HTTP(None, None, 200,
              {"Content-Type": "text/html", "Content-Length": "1280", "Reason": "OK"},
              "<!DOCTYPE html><html><head><title>Example</title>")
    return [
        # Three-way handshake
        P(0.000, E1, E2, 6, C, S, 60, 0x1234, TCP(50000, 80, 0, 0, SYN),
          None, "SYN: initial connection request, seq=0"),
        P(0.015, E2, E1, 6, S, C, 60, 0x5678, TCP(80, 50000, 0, 1, SYNACK),
          None, "SYN-ACK: server accepts, seq=0, ack=1"),
        P(0.016, E1, E2, 6, C, S, 52, 0x1235, TCP(50000, 80, 1, 1, ACK_F),
          None, "ACK: 3-way handshake complete"),
        # HTTP request-response
        P(0.020, E1, E2, 6, C, S, 420, 0x1236, TCP(50000, 80, 1, 1, PSH),
          get, "HTTP GET request"),
        P(0.080, E2, E1, 6, S, C, 1440, 0x5679, TCP(80, 50000, 1, 370, PSH),
          ok, "HTTP 200 OK response with 1280-byte HTML body"),
        P(0.085, E1, E2, 6, C, S, 52, 0x1237, TCP(50000, 80, 370, 1281, ACK_F),
          None, "ACK: client acks 1280 bytes of response data"),
        # Four-way close
        P(0.100, E1, E2, 6, C, S, 52, 0x1238, TCP(50000, 80, 370, 1281, FIN),
          None, "FIN: client initiates close"),
        P(0.115, E2, E1, 6, S, C, 52, 0x5680, TCP(80, 50000, 1281, 371, FIN),
          None, "FIN-ACK: server agrees to close"),
        P(0.116, E1, E2, 6, C, S, 52, 0x1239, TCP(50000, 80, 371, 1282, ACK_F),
          None, "ACK: final ACK, connection goes to TIME_WAIT"),
    ]


def build_retransmission_trace() -> list[Packet]:
    s = {"syn": True}
    return [
        P(0.000, E1, E2, 6, C, S, 60, 0x1234, TCP(50000, 80, 0, 0, s),
          None, "SYN: original (lost)"),
        P(1.000, E1, E2, 6, C, S, 60, 0x1234, TCP(50000, 80, 0, 0, s),
          None, "SYN: retransmit after 1.0s RTO (same seq=0)"),
        P(1.020, E2, E1, 6, S, C, 60, 0x5678, TCP(80, 50000, 0, 1, {"syn": True, "ack": True}),
          None, "SYN-ACK: server responds to retransmit"),
    ]


def analyze(packets):
    syn = sum(1 for p in packets if isinstance(p.tr, TCP) and p.tr.flags.get("syn"))
    fin = sum(1 for p in packets if isinstance(p.tr, TCP) and p.tr.flags.get("fin"))
    req = sum(1 for p in packets if isinstance(p.app, HTTP) and p.app.method)
    res = sum(1 for p in packets if isinstance(p.app, HTTP) and p.app.status)
    hs = (packets[1].t - packets[0].t) * 1000 if len(packets) > 1 else 0
    rtt = (packets[4].t - packets[3].t) * 1000 if len(packets) > 4 else 0
    total = (packets[-1].t - packets[0].t) * 1000 if packets else 0
    return dict(total=len(packets), handshake_ms=hs, rtt_ms=rtt, total_ms=total,
                syn=syn, fin=fin, req=req, res=res)


def main():
    print("=" * 65)
    print("Capstone 01: Protocol Trace Portfolio")
    print("=" * 65)
    print("\n  [1/3] DNS lookup trace (precedes the TCP exchange):\n")
    for p in build_dns_trace():
        print(annotate(p)); print()
    trace = build_sample_trace()
    print(f"\n  [2/3] Annotated HTTP transaction trace ({len(trace)} packets):\n")
    for p in trace:
        print(annotate(p)); print()
    s = analyze(trace)
    print("  Trace Analysis Summary:")
    print(f"    Total packets:          {s['total']}")
    print(f"    TCP handshake time:     {s['handshake_ms']:.1f} ms")
    print(f"    HTTP request-response:  {s['rtt_ms']:.1f} ms RTT")
    print(f"    Total session time:     {s['total_ms']:.1f} ms")
    print(f"    SYN/FIN:                {s['syn']}/{s['fin']}")
    print(f"    HTTP req/res:           {s['req']}/{s['res']}")
    print(f"\n  [3/3] Failure-mode trace: SYN retransmit after 1.0s RTO\n")
    for p in build_retransmission_trace():
        print(annotate(p)); print()
    print(f"\n  Demonstrates: SYN -> SYN-ACK -> ACK, GET -> 200 OK,")
    print(f"  FIN -> FIN-ACK -> ACK, and RTO-based SYN retransmit.")


if __name__ == "__main__":
    main()
