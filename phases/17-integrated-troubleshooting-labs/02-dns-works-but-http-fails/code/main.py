#!/usr/bin/env python3
"""DNS Works but HTTP Fails (Integrated Troubleshooting Lab 02).

Walks the seven-command diagnostic chain against four synthetic failure
modes and identifies the first decisive evidence for each:

  refused       - service down, kernel returns RST
  timeout       - firewall/NAT/routing drops SYN silently
  slow_backend  - TCP and TLS succeed, backend does not respond
  stale_cache   - DNS cache returns a stale IP, path is broken

Run:  python3 main.py [--mode refused|timeout|slow_backend|stale_cache|all]
"""
from __future__ import annotations

import argparse
import enum
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Synthetic environment (deterministic; no live network calls)
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    REFUSED = "refused"
    TIMEOUT = "timeout"
    SLOW_BACKEND = "slow_backend"
    STALE_CACHE = "stale_cache"


@dataclass(frozen=True)
class Command:
    name: str
    invocation: str
    purpose: str


@dataclass
class Network:
    """Models a tiny slice of network behavior for synthetic tests."""

    name: str = "api.example.com"
    fresh_ip: str = "203.0.113.42"
    stale_ip: str = "203.0.113.99"     # the "old" IP from the cache
    port: int = 443
    service_listening: bool = True
    firewall_drops_syn: bool = False
    backend_response_ms: float = 50.0
    path_to_fresh_ip_healthy: bool = True
    path_to_stale_ip_healthy: bool = False   # the "old" path is broken
    local_cache: dict[str, str] = field(default_factory=dict)
    cache_inserted_at: float = 0.0
    now: float = 1810.0                  # 30 min 10 s after cache insert
    cache_ttl_s: int = 3600

    def resolve(self, name: str, *, bypass_cache: bool = False) -> str | None:
        if not bypass_cache and name in self.local_cache:
            return self.local_cache[name]
        # Authoritative answer
        return self.fresh_ip

    def tcp_connect(self, ip: str, port: int, *, timeout_s: float = 5.0) -> str:
        # In a real system this would actually attempt the connect; here we
        # model the four possible outcomes deterministically.
        if self.firewall_drops_syn:
            return "timeout"
        if ip == self.stale_ip and not self.path_to_stale_ip_healthy:
            return "timeout"
        if ip == self.fresh_ip and not self.path_to_fresh_ip_healthy:
            return "timeout"
        if not self.service_listening:
            return "refused"
        return "open"

    def first_byte_ms(self, ip: str) -> float:
        if self.tcp_connect(ip, self.port) != "open":
            return -1.0
        return self.backend_response_ms


# ---------------------------------------------------------------------------
# The seven-command diagnostic chain
# ---------------------------------------------------------------------------
SEVEN_COMMANDS: list[Command] = [
    Command("dig",
            "dig +short api.example.com",
            "Authoritative name resolution at the configured resolver"),
    Command("getent",
            "getent ahosts api.example.com",
            "What the local resolver returns (no upstream cache bypass)"),
    Command("ping",
            "ping -c 3 -W 2 203.0.113.42",
            "ICMP reachability to the IP"),
    Command("traceroute",
            "traceroute -T -p 443 203.0.113.42",
            "L3 path and the first non-responsive hop"),
    Command("nc",
            "nc -vz -w 5 203.0.113.42 443",
            "TCP handshake to the destination port (refused/open/timeout)"),
    Command("curl",
            "curl -v --max-time 10 https://api.example.com/health",
            "Full stack: DNS + TCP + TLS + HTTP request and response"),
    Command("ss",
            "ss -ti dst 203.0.113.42",
            "Kernel TCP retrans, RTO, cwnd for sockets to the destination"),
]


# ---------------------------------------------------------------------------
# Diagnostic runner
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    command: str
    output: str
    decisive: bool
    layer: str | None
    verdict: str


def run_chain(net: Network, mode: FailureMode) -> list[Finding]:
    findings: list[Finding] = []
    # 1) dig - look at local cache vs. authoritative
    if mode is FailureMode.STALE_CACHE:
        # Simulate that the local cache was inserted at T=0 and is still valid.
        net.local_cache[net.name] = net.stale_ip
        elapsed = net.now - net.cache_inserted_at
        dig_output = f"{net.stale_ip}  (cached, TTL remaining {net.cache_ttl_s - elapsed:.0f}s)"
        findings.append(Finding(
            "dig", dig_output, False, "L7-cache",
            "DNS cache returns the OLD IP; TTL not yet expired"))
    else:
        dig_output = f"{net.fresh_ip}"
        findings.append(Finding(
            "dig", dig_output, False, "L7-DNS",
            "DNS resolves to the fresh IP"))

    # 2) getent - same as dig in this simulation
    findings.append(Finding(
        "getent", dig_output, False, "L7-DNS",
        "Same as dig; local resolver is the source of the answer"))

    # 3) ping
    ip_in_use = net.stale_ip if mode is FailureMode.STALE_CACHE else net.fresh_ip
    if mode is FailureMode.STALE_CACHE:
        ping_output = "3 packets transmitted, 0 received, 100% packet loss"
        findings.append(Finding(
            "ping", ping_output, True, "L3",
            "ICMP to the OLD IP fails; path to OLD IP is broken"))
    elif mode is FailureMode.TIMEOUT and net.firewall_drops_syn:
        # A firewall that drops TCP SYN may or may not drop ICMP; in this
        # simulation it drops both for clarity.
        ping_output = "3 packets transmitted, 0 received, 100% packet loss"
        findings.append(Finding(
            "ping", ping_output, False, "L3",
            "ICMP dropped; could be firewall or path - keep going"))
    elif mode is FailureMode.REFUSED:
        ping_output = "3 packets transmitted, 3 received, 0% packet loss"
        findings.append(Finding(
            "ping", ping_output, False, "L3",
            "ICMP path is open; keep going"))
    else:  # slow_backend
        ping_output = "3 packets transmitted, 3 received, 0% packet loss"
        findings.append(Finding(
            "ping", ping_output, False, "L3",
            "ICMP path is open; keep going"))

    # 4) traceroute (only interesting for timeout modes)
    if mode is FailureMode.STIMEOUT_FROM_HERE if False else mode in (FailureMode.TIMEOUT, FailureMode.STALE_CACHE):
        findings.append(Finding(
            "traceroute",
            "8  10.20.30.40  12.345 ms  9  * * *  10  * * *",
            True, "L3",
            "First non-responsive hop at hop 9 (likely firewall)"))
    else:
        findings.append(Finding(
            "traceroute",
            "8  203.0.113.42  12.345 ms  (destination reached)",
            False, "L3",
            "L3 path is healthy; the issue is not routing"))

    # 5) nc -vz
    nc_result = net.tcp_connect(ip_in_use, net.port)
    if nc_result == "refused":
        findings.append(Finding(
            "nc -vz", "Connection refused", True, "L4",
            "Service is NOT listening on port 443; SYN was answered with RST"))
    elif nc_result == "timeout":
        findings.append(Finding(
            "nc -vz", "Operation timed out (5 s)", True, "L4",
            "SYN was silently dropped - firewall, NAT, or routing black hole"))
    else:
        findings.append(Finding(
            "nc -vz", "succeeded", False, "L4",
            "TCP handshake to port 443 succeeded; keep going"))

    # 6) curl -v
    if mode is FailureMode.REFUSED:
        findings.append(Finding(
            "curl -v",
            "* connect to 203.0.113.42 port 443 failed: Connection refused",
            True, "L4", "Same as nc; service is down"))
    elif mode in (FailureMode.TIMEOUT, FailureMode.STALE_CACHE):
        findings.append(Finding(
            "curl -v",
            "* connect to 203.0.113.42 port 443 failed: Connection timed out",
            True, "L4", "Same as nc; SYN was dropped"))
    elif mode is FailureMode.SLOW_BACKEND:
        findings.append(Finding(
            "curl -v",
            ("* Connected to api.example.com (203.0.113.42) port 443\n"
             "* TLSv1.3 handshake complete\n"
             "> GET /health HTTP/1.1\n"
             "* Operation timed out after 10001 ms with 0 bytes received"),
            True, "L4-L7", "TCP+TLS succeeded; backend is not responding"))

    # 7) ss -ti
    if mode is FailureMode.SLOW_BACKEND:
        findings.append(Finding(
            "ss -ti",
            "ESTAB  retrans:5/7  timer:(on,1234ms)  rtt:50/40",
            True, "L4", "TCP retrans climbing - kernel sees no ACKs from peer"))
    else:
        # For other modes, ss shows an empty result for this destination.
        findings.append(Finding(
            "ss -ti", "(no established sockets to 203.0.113.42:443)",
            False, "L4", "No live TCP socket to inspect"))

    return findings


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render(mode: FailureMode, net: Network, findings: list[Finding]) -> None:
    print("=" * 78)
    print(f"DNS Works but HTTP Fails  [mode={mode.value}]")
    print("=" * 78)
    print(f"  Resolved name: {net.name}")
    print(f"  Fresh IP:      {net.fresh_ip}  (path healthy = {net.path_to_fresh_ip_healthy})")
    print(f"  Stale IP:      {net.stale_ip}  (path healthy = {net.path_to_stale_ip_healthy})")
    print()
    print(f"{'#':<3}{'command':<14}  {'output':<48}  decisive?  layer")
    print("-" * 78)
    for i, f in enumerate(findings, start=1):
        first_line = f.output.splitlines()[0][:46]
        marker = "YES" if f.decisive else "no"
        print(f"{i:<3}{f.command:<14}  {first_line:<48}  {marker:<9}  {f.layer or '-'}")
    print()
    decisive = next((f for f in findings if f.decisive), None)
    if decisive:
        print(f"  First decisive evidence: {decisive.command}")
        print(f"  Layer:                    {decisive.layer}")
        print(f"  Verdict:                  {decisive.verdict}")
    else:
        print("  No decisive evidence found in chain (unexpected).")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="all",
                    choices=[m.value for m in FailureMode] + ["all"])
    args = ap.parse_args(list(argv) if argv is not None else None)

    modes = (list(FailureMode) if args.mode == "all"
             else [FailureMode(args.mode)])

    for mode in modes:
        net = Network()
        if mode is FailureMode.REFUSED:
            net.service_listening = False
        elif mode is FailureMode.TIMEOUT:
            net.firewall_drops_syn = True
        elif mode is FailureMode.SLOW_BACKEND:
            net.backend_response_ms = 12_500.0
        elif mode is FailureMode.STALE_CACHE:
            net.local_cache[net.name] = net.stale_ip
        findings = run_chain(net, mode)
        render(mode, net, findings)
        print()


if __name__ == "__main__":
    main()
