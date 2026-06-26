#!/usr/bin/env python3
"""TCP Retransmission Storm + TLS Certificate Failure (Integrated Lab 05).

Emits a synthetic TCP+TLS trace for five failure modes and walks a
four-step diagnostic chain for each:

  retrans_storm        - micro-bursts of loss during TCP handshake
  missing_intermediate - server omits the intermediate CA from the chain
  cert_expired         - the leaf cert's notAfter has passed
  sni_mismatch         - cert is for a different hostname
  healthy              - all four steps pass

Run:  python3 main.py [--mode <mode>|all]
"""
from __future__ import annotations

import argparse
import enum
import random
import time
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    RETRANS_STORM = "retrans_storm"
    MISSING_INTERMEDIATE = "missing_intermediate"
    CERT_EXPIRED = "cert_expired"
    SNI_MISMATCH = "sni_mismatch"
    HEALTHY = "healthy"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TcpSegment:
    t_ms: float
    src: str
    dst: str
    flags: str      # SYN, SYN-ACK, ACK, DATA, FIN, RST
    seq: int
    retrans: bool = False


@dataclass(frozen=True)
class TlsMessage:
    t_ms: float
    direction: str  # client->server, server->client
    msg_type: str   # ClientHello, ServerHello, Certificate, Alert, Finished
    detail: str = ""


@dataclass
class Trace:
    tcp: list[TcpSegment] = field(default_factory=list)
    tls: list[TlsMessage] = field(default_factory=list)
    final_alert: str | None = None
    final_verification: str | None = None


# ---------------------------------------------------------------------------
# Handshake simulation
# ---------------------------------------------------------------------------
def rfc6298_backoff(attempt: int, rtt_ms: float = 50.0) -> float:
    """RTO cascade per RFC 6298, capped at 64 s."""
    return min(rtt_ms * (2 ** attempt), 64_000.0)


def run_handshake(mode: FailureMode, seed: int = 1) -> Trace:
    rng = random.Random(seed)
    t = Trace()
    base = 0.0
    rtt = 50.0

    # TCP handshake ----------------------------------------------------------
    t.tcp.append(TcpSegment(base, "client", "server", "SYN", 1000))
    # SYN-ACK from server
    syn_ack_time = base + rtt
    if mode is FailureMode.RETRANS_STORM:
        # First SYN-ACK dropped in a micro-burst; client retransmits
        if rng.random() < 0.6:
            t.tcp.append(TcpSegment(syn_ack_time, "server", "client",
                                     "SYN-ACK", 5000, lost=True))
            # Client retransmits SYN 1 s later (RFC 6298)
            for attempt in range(1, 4):
                delay = rfc6298_backoff(attempt) / 1000.0
                t.tcp.append(TcpSegment(base + delay, "client", "server",
                                         "SYN", 1000, retrans=True))
                if rng.random() > 0.5:
                    # Eventually succeeds
                    t.tcp.append(TcpSegment(base + delay + rtt / 1000.0,
                                             "server", "client", "SYN-ACK",
                                             5000))
                    t.tcp.append(TcpSegment(base + delay + 2 * rtt / 1000.0,
                                             "client", "server", "ACK", 1001))
                    break
        else:
            t.tcp.append(TcpSegment(syn_ack_time, "server", "client",
                                     "SYN-ACK", 5000))
            t.tcp.append(TcpSegment(syn_ack_time + rtt, "client", "server",
                                     "ACK", 1001))
    else:
        t.tcp.append(TcpSegment(syn_ack_time, "server", "client", "SYN-ACK", 5000))
        t.tcp.append(TcpSegment(syn_ack_time + rtt, "client", "server", "ACK", 1001))

    # TLS 1.2 handshake ------------------------------------------------------
    if any(s.lost for s in t.tcp):
        # TCP handshake was retried; subsequent TLS messages are delayed
        t_base = max(s.t_ms for s in t.tcp if s.flags == "ACK") + rtt
    else:
        t_base = syn_ack_time + 2 * rtt

    # ClientHello
    t.tls.append(TlsMessage(t_base, "client->server", "ClientHello",
                             f"SNI={'api.example.com' if mode is not FailureMode.SNI_MISMATCH else 'wrong.host.example'}"))
    # ServerHello + Certificate
    t.tls.append(TlsMessage(t_base + rtt, "server->client", "ServerHello",
                             "TLSv1.2 selected"))
    if mode is FailureMode.MISSING_INTERMEDIATE:
        t.tls.append(TlsMessage(t_base + rtt, "server->client", "Certificate",
                                 "chain=[leaf]  (intermediate MISSING)"))
        t.final_verification = "unable to verify the first certificate (num=20)"
    elif mode is FailureMode.CERT_EXPIRED:
        t.tls.append(TlsMessage(t_base + rtt, "server->client", "Certificate",
                                 "chain=[leaf, intermediate, root]  (leaf notAfter=past)"))
        t.final_verification = "certificate has expired (num=10)"
    elif mode is FailureMode.SNI_MISMATCH:
        t.tls.append(TlsMessage(t_base + rtt, "server->client", "Certificate",
                                 "chain=[leaf, intermediate, root]  (SAN=other.host)"))
        t.final_verification = "hostname mismatch (num=62)"
    else:
        t.tls.append(TlsMessage(t_base + rtt, "server->client", "Certificate",
                                 "chain=[leaf, intermediate, root]"))

    # ClientKeyExchange + Finished
    t.tls.append(TlsMessage(t_base + 2 * rtt, "client->server", "ClientKeyExchange",
                             "pre-master secret"))
    t.tls.append(TlsMessage(t_base + 2 * rtt, "client->server", "ChangeCipherSpec"))
    t.tls.append(TlsMessage(t_base + 2 * rtt, "client->server", "Finished",
                             "verify_data"))

    # Server's ChangeCipherSpec + Finished
    t.tls.append(TlsMessage(t_base + 3 * rtt, "server->client", "ChangeCipherSpec"))
    t.tls.append(TlsMessage(t_base + 3 * rtt, "server->client", "Finished",
                             "verify_data"))

    # If handshake is broken, the client sends an alert and closes
    if mode in (FailureMode.MISSING_INTERMEDIATE, FailureMode.CERT_EXPIRED,
                FailureMode.SNI_MISMATCH):
        if mode is FailureMode.MISSING_INTERMEDIATE:
            t.final_alert = "TLS Alert: certificate_unknown (fatal)"
        elif mode is FailureMode.CERT_EXPIRED:
            t.final_alert = "TLS Alert: certificate_expired (fatal)"
        else:
            t.final_alert = "TLS Alert: handshake_failure (fatal) - SNI mismatch"
        t.tls.append(TlsMessage(t_base + 2 * rtt, "client->server", "Alert",
                                 t.final_alert))
        t.tcp.append(TcpSegment(t_base + 2 * rtt + 5, "client", "server", "FIN", 1002))
    elif mode is FailureMode.RETRANS_STORM:
        # TCP finally completes but the user gave up after 15 s
        t.final_alert = "client gave up: Connection timed out (15 s)"
    else:
        # healthy: application data follows
        t.tcp.append(TcpSegment(t_base + 3 * rtt, "client", "server", "DATA", 1002))

    return t


# ---------------------------------------------------------------------------
# Four-step diagnostic chain
# ---------------------------------------------------------------------------
@dataclass
class DiagResult:
    step: int
    name: str
    finding: str
    layer: str
    decisive: bool


def cmd_ss_ti(trace: Trace) -> DiagResult:
    n_retrans = sum(1 for s in trace.tcp if s.retrans)
    if n_retrans > 0:
        return DiagResult(1, "ss -ti dst <ip>",
                           f"retrans:{n_retrans}, cwnd:2, timer:(on,...)",
                           "L4 TCP", True)
    return DiagResult(1, "ss -ti dst <ip>",
                       "retrans:0, cwnd:10, rtt:50/40",
                       "L4 OK; keep going", False)


def cmd_tcpdump(trace: Trace) -> DiagResult:
    syn_segs = [s for s in trace.tcp if s.flags == "SYN"]
    retrans_syn = [s for s in syn_segs if s.retrans]
    if len(retrans_syn) >= 1:
        return DiagResult(2, "tcpdump -tttt 'host <ip> and tcp'",
                           f"{len(syn_segs)} SYNs sent; {len(retrans_syn)} retransmits at 1/2/4 s",
                           "L4 TCP backoff", True)
    return DiagResult(2, "tcpdump -tttt 'host <ip> and tcp'",
                       "smooth TCP handshake, 1 SYN / 1 SYN-ACK / 1 ACK",
                       "L4 OK; keep going", False)


def cmd_openssl(trace: Trace) -> DiagResult:
    if trace.final_verification is None:
        return DiagResult(3, "openssl s_client -connect <ip>:443 -servername <name>",
                           "Verify return code: 0 (ok)",
                           "L6 OK; keep going", False)
    return DiagResult(3, "openssl s_client -connect <ip>:443 -servername <name>",
                       f"Verify return code: {trace.final_verification}",
                       "L6 TLS certificate", True)


def cmd_curl(trace: Trace) -> DiagResult:
    if trace.final_alert is None:
        return DiagResult(4, "curl -v --max-time 10 https://<name>",
                           "TLS handshake complete, HTTP 200",
                           "L7 OK", False)
    if "timed out" in trace.final_alert:
        return DiagResult(4, "curl -v --max-time 10 https://<name>",
                           "Connection timed out after 15 s (TCP-level)",
                           "L4 TCP", True)
    return DiagResult(4, "curl -v --max-time 10 https://<name>",
                       f"curl: {trace.final_alert}",
                       "L6 TLS", True)


def run_diag(trace: Trace) -> list[DiagResult]:
    return [cmd_ss_ti(trace), cmd_tcpdump(trace),
            cmd_openssl(trace), cmd_curl(trace)]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render(mode: FailureMode, trace: Trace, results: list[DiagResult]) -> None:
    print("=" * 78)
    print(f"TCP+TLS Diagnostic  [mode={mode.value}]")
    print("=" * 78)
    print(f"{'T (ms)':>8}  {'layer':<5}  {'direction':<16}  {'msg':<14}  detail")
    print("-" * 78)
    # Merge TCP and TLS into a single time-ordered trace
    events: list[tuple[float, str, str, str, str]] = []
    for s in trace.tcp:
        events.append((s.t_ms, "L4", f"{s.src[:3]}->{s.dst[:3]}", s.flags,
                       f"seq={s.seq}{' [lost]' if s.lost else ''}{' [retrans]' if s.retrans else ''}"))
    for m in trace.tls:
        events.append((m.t_ms, "L6", m.direction, m.msg_type, m.detail))
    events.sort(key=lambda e: (e[0], e[1]))
    for t_ms, layer, direction, msg, detail in events:
        print(f"{t_ms:>8.1f}  {layer:<5}  {direction:<16}  {msg:<14}  {detail}")
    print()
    print(f"{'#':<3}  {'finding':<60}  decisive?  layer")
    print("-" * 78)
    for r in results:
        first_line = r.finding[:58]
        marker = "YES" if r.decisive else "no"
        print(f"{r.step:<3}  {first_line:<60}  {marker:<9}  {r.layer}")
    print()
    decisive = next((r for r in results if r.decisive), None)
    if decisive:
        print(f"  First decisive evidence: step {decisive.step} ({decisive.name})")
        print(f"  Layer:                    {decisive.layer}")
        print(f"  Verdict:                  {decisive.finding}")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="all",
                    choices=[m.value for m in FailureMode] + ["all"])
    args = ap.parse_args(list(argv) if argv is not None else None)
    modes = (list(FailureMode) if args.mode == "all"
             else [FailureMode(args.mode)])
    for mode in modes:
        trace = run_handshake(mode)
        results = run_diag(trace)
        render(mode, trace, results)
        print()


if __name__ == "__main__":
    main()
