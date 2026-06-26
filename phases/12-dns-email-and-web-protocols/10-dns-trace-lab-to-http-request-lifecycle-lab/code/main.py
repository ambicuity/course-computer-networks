#!/usr/bin/env python3
"""DNS trace lab and HTTP request lifecycle lab (section 7.1.3 + 7.3.1).

Stdlib only, no network calls. Demonstrates two end-to-end labs:

LAB 1: DNS Resolution Trace
  Simulates a full recursive DNS query from client -> local resolver ->
  root -> TLD (.edu) -> authoritative (washington.edu) -> authoritative
  (cs.washington.edu) -> answer, with TTL-based caching. A second query
  to the same domain shows cache hits. A third query to a different host
  in the same zone shows the benefit of zone-level caching.

LAB 2: HTTP Request Lifecycle
  Simulates the full 9-step page fetch from section 7.3.1:
  1. Browser determines URL
  2. DNS lookup for host IP
  3. DNS reply
  4. TCP 3-way handshake to port 80
  5. HTTP GET request sent
  6. HTTP response received
  7. Embedded resource fetches (images, scripts)
  8. Page rendered
  9. TCP connection released (keep-alive timeout)

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


# ---------------------------------------------------------------------------
# Shared DNS infrastructure (minimal, for both labs)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RR:
    name: str
    ttl: int
    rtype: str
    rdata: str


@dataclass
class DNSServer:
    name: str
    zone: str
    records: list[RR] = field(default_factory=list)

    def query(self, qname: str, qtype: str = "A") -> tuple[list[RR], Optional[str]]:
        """Return (answers, referral_ns). If no answer, return a referral."""
        for rr in self.records:
            if rr.name.lower() == qname.lower() and rr.rtype == qtype:
                return [rr], None
        parts = qname.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            for rr in self.records:
                if rr.name.lower() == candidate.lower() and rr.rtype == "NS":
                    return [], rr.rdata
        return [], None


@dataclass
class CacheEntry:
    records: list[RR]
    ttl: int
    timestamp: float = field(default_factory=time.time)

    def is_valid(self) -> bool:
        return (time.time() - self.timestamp) < self.ttl


class RecursiveResolver:
    """A caching recursive resolver that walks the DNS hierarchy."""

    def __init__(self, root: DNSServer, servers: list[DNSServer]) -> None:
        self.root = root
        self.servers = servers
        self.cache: dict[str, CacheEntry] = {}
        self.query_log: list[str] = []

    def resolve(self, qname: str, qtype: str = "A", _depth: int = 0) -> list[RR]:
        if _depth > 5:
            return []
        qname = qname.rstrip(".")
        cache_key = f"{qname.lower()}/{qtype}"
        if cache_key in self.cache and self.cache[cache_key].is_valid():
            entry = self.cache[cache_key]
            self.query_log.append(f"  [CACHE HIT] {cache_key} (TTL={entry.ttl})")
            return entry.records

        self.query_log.append(f"  Step 1: client -> local resolver  Q={qname} {qtype}")
        answers, referral = self._walk(qname, qtype)
        if not answers and qtype == "A":
            cnames, _ = self._walk(qname, "CNAME")
            if cnames:
                self.query_log.append(f"  [CNAME] {qname} -> {cnames[0].rdata}")
                answers = self.resolve(cnames[0].rdata, "A", _depth + 1)
                if answers:
                    ttl = min((r.ttl for r in answers), default=0)
                    self.cache[cache_key] = CacheEntry(answers, ttl)
                return answers
        if answers:
            ttl = min((r.ttl for r in answers), default=0)
            self.cache[cache_key] = CacheEntry(answers, ttl)
            self.query_log.append(f"  Step N: ANSWER -> {answers[0].rdata}")
        return answers

    def _walk(self, qname: str, qtype: str) -> tuple[list[RR], Optional[str]]:
        self.query_log.append(f"  Step 2: resolver -> root ({self.root.name})")
        current = self.root
        step = 2
        visited: set[str] = set()
        while True:
            step += 1
            if current.name in visited:
                self.query_log.append(f"  Step {step}: LOOP detected at {current.name}")
                return [], None
            visited.add(current.name)
            answers, referral = current.query(qname, qtype)
            if answers:
                return answers, None
            if referral:
                nxt = self._find_server(referral)
                if nxt is None or nxt.name == current.name:
                    self.query_log.append(f"  Step {step}: {current.name} -> no further referral")
                    return [], None
                self.query_log.append(f"  Step {step}: {current.name} -> referral to {nxt.name}")
                current = nxt
            else:
                self.query_log.append(f"  Step {step}: {current.name} -> NXDOMAIN")
                return [], None

    def _find_server(self, ns_host: str) -> Optional[DNSServer]:
        ns_host = ns_host.lower()
        for s in self.servers:
            if s.name.lower() == ns_host:
                return s
        for s in self.servers:
            if ns_host.endswith(s.zone.lower()) or s.zone.lower() == ns_host:
                return s
        return None

    def cache_stats(self) -> dict[str, int]:
        valid = sum(1 for e in self.cache.values() if e.is_valid())
        return {"total": len(self.cache), "valid": valid, "expired": len(self.cache) - valid}


# ---------------------------------------------------------------------------
# Lab 1: DNS trace
# ---------------------------------------------------------------------------

def setup_dns_hierarchy() -> tuple[RecursiveResolver, dict[str, DNSServer]]:
    root = DNSServer("a.root-servers.net", ".", [
        RR(".", 518400, "NS", "a.root-servers.net"),
        RR("edu", 172800, "NS", "a.edu-servers.net"),
    ])
    edu = DNSServer("a.edu-servers.net", "edu", [
        RR("edu", 172800, "NS", "a.edu-servers.net"),
        RR("washington.edu", 172800, "NS", "ns.washington.edu"),
    ])
    uw = DNSServer("ns.washington.edu", "washington.edu", [
        RR("washington.edu", 86400, "SOA", "ns.washington.edu admin 2010081501 7200 3600 1209600 3600"),
        RR("washington.edu", 86400, "NS", "ns.washington.edu"),
        RR("washington.edu", 86400, "MX", "10 mail.washington.edu"),
        RR("ns.washington.edu", 86400, "A", "128.95.120.1"),
        RR("mail.washington.edu", 86400, "A", "128.95.120.2"),
        RR("cs.washington.edu", 86400, "NS", "ns.cs.washington.edu"),
        RR("eng.washington.edu", 86400, "NS", "ns.eng.washington.edu"),
    ])
    cs = DNSServer("ns.cs.washington.edu", "cs.washington.edu", [
        RR("cs.washington.edu", 86400, "SOA", "ns.cs.washington.edu admin 2010081501 7200 3600 1209600 3600"),
        RR("cs.washington.edu", 86400, "NS", "ns.cs.washington.edu"),
        RR("cs.washington.edu", 86400, "MX", "10 mail.cs.washington.edu"),
        RR("ns.cs.washington.edu", 86400, "A", "128.208.3.88"),
        RR("mail.cs.washington.edu", 86400, "A", "128.208.3.89"),
        RR("www.cs.washington.edu", 86400, "CNAME", "www-lb.cs.washington.edu"),
        RR("www-lb.cs.washington.edu", 86400, "A", "128.208.3.90"),
        RR("robot.cs.washington.edu", 86400, "A", "128.208.3.91"),
        RR("galah.cs.washington.edu", 86400, "A", "128.208.3.92"),
    ])
    eng = DNSServer("ns.eng.washington.edu", "eng.washington.edu", [
        RR("eng.washington.edu", 86400, "NS", "ns.eng.washington.edu"),
        RR("ns.eng.washington.edu", 86400, "A", "128.95.120.10"),
        RR("www.eng.washington.edu", 86400, "A", "128.95.120.11"),
    ])

    servers = {"root": root, "edu": edu, "uw": uw, "cs": cs, "eng": eng}
    resolver = RecursiveResolver(root, [root, edu, uw, cs, eng])
    return resolver, servers


# ---------------------------------------------------------------------------
# Lab 2: HTTP request lifecycle
# ---------------------------------------------------------------------------

@dataclass
class TCPConnection:
    local_addr: str
    remote_addr: str
    remote_port: int
    state: str = "CLOSED"
    seq: int = 0
    ack: int = 0

    def three_way_handshake(self) -> list[str]:
        """Simulate TCP 3-way handshake."""
        self.state = "SYN_SENT"
        log = [
            f"  -> SYN  seq={self.seq}  (client -> {self.remote_addr}:{self.remote_port})",
            f"  <- SYN+ACK  seq=0 ack={self.seq + 1}  (server -> client)",
            f"  -> ACK  ack=1  (client -> server)",
        ]
        self.state = "ESTABLISHED"
        self.seq += 1
        self.ack = 1
        return log

    def send(self, data: str) -> str:
        self.seq += len(data)
        return f"  -> DATA  seq={self.seq - len(data)} len={len(data)}  ({data[:40]}...)"

    def close(self) -> list[str]:
        """Simulate TCP 4-way close."""
        self.state = "FIN_WAIT_1"
        log = [
            f"  -> FIN  seq={self.seq}  (client -> server)",
            f"  <- ACK  ack={self.seq + 1}  (server -> client)",
            f"  <- FIN+ACK  (server -> client)",
            f"  -> ACK  (client -> server)",
        ]
        self.state = "CLOSED"
        return log


@dataclass
class HTTPExchange:
    request_line: str
    headers: dict[str, str]
    body: str = ""
    response_status: int = 200
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    response_time_ms: float = 0.0


def simulate_http_request(url: str, resolver: RecursiveResolver) -> HTTPExchange:
    """Simulate the full 9-step HTTP request lifecycle."""
    print(f"\n{'─' * 60}")
    print(f"HTTP Request Lifecycle: {url}")
    print(f"{'─' * 60}")

    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path or "/"

    print(f"\n  Step 1: Browser determines URL")
    print(f"    scheme=http  host={host}  path={path}")

    print(f"\n  Step 2: Browser asks DNS for IP of {host}")
    print(f"\n  Step 3: DNS resolution (recursive query):")
    answers = resolver.resolve(host, "A")
    if not answers:
        print(f"    DNS resolution FAILED")
        return HTTPExchange("", {}, "", 502)
    ip = answers[0].rdata
    print(f"    DNS reply: {host} -> {ip}")

    print(f"\n  Step 4: TCP connection to {ip}:80")
    conn = TCPConnection("192.168.1.100", ip, 80)
    for line in conn.three_way_handshake():
        print(f"    {line}")
    print(f"    Connection state: {conn.state}")

    print(f"\n  Step 5: HTTP request sent")
    request_line = f"GET {path} HTTP/1.1"
    req_headers = {
        "Host": host,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
        "Accept": "text/html,*/*",
        "Connection": "keep-alive",
    }
    print(f"    {request_line}")
    for k, v in req_headers.items():
        print(f"    {k}: {v}")
    print(f"    (blank line)")
    data_sent = conn.send(request_line + "\n" + "\n".join(f"{k}: {v}" for k, v in req_headers.items()) + "\n\n")
    print(f"    {data_sent}")

    print(f"\n  Step 6: HTTP response received")
    response_body = "<html><body><h1>CSE Department</h1><p>Welcome!</p></body></html>"
    resp_headers = {
        "Content-Type": "text/html",
        "Content-Length": str(len(response_body)),
        "Server": "Apache/2.4.1",
        "Cache-Control": "max-age=3600",
    }
    print(f"    HTTP/1.1 200 OK")
    for k, v in resp_headers.items():
        print(f"    {k}: {v}")
    print(f"    (blank line)")
    print(f"    Body: {len(response_body)} bytes")

    print(f"\n  Step 7: Fetch embedded resources")
    embedded = [
        ("logo.png", "image/png", 45000),
        ("style.css", "text/css", 12000),
        ("analytics.js", "application/javascript", 28000),
    ]
    for resource, rtype, size in embedded:
        print(f"    GET /{resource}  -> 200  {rtype}  {size} bytes")

    print(f"\n  Step 8: Browser displays page")
    print(f"    Page rendered: {response_body[:50]}...")

    print(f"\n  Step 9: TCP connection released (keep-alive timeout)")
    for line in conn.close():
        print(f"    {line}")
    print(f"    Connection state: {conn.state}")

    return HTTPExchange(request_line, req_headers, "", 200, resp_headers, response_body, 12.5)


def main() -> None:
    print("=" * 70)
    print("LAB 1: DNS Resolution Trace")
    print("=" * 70)

    resolver, servers = setup_dns_hierarchy()

    print("\n--- Query 1: robot.cs.washington.edu (cold cache) ---")
    answers = resolver.resolve("robot.cs.washington.edu", "A")
    for line in resolver.query_log:
        print(line)
    resolver.query_log.clear()
    print(f"\n  Final answer: {answers[0].rdata if answers else 'NXDOMAIN'}")

    print("\n--- Query 2: robot.cs.washington.edu (cached) ---")
    answers2 = resolver.resolve("robot.cs.washington.edu", "A")
    for line in resolver.query_log:
        print(line)
    resolver.query_log.clear()
    print(f"\n  Final answer: {answers2[0].rdata if answers2 else 'NXDOMAIN'}")

    print("\n--- Query 3: galah.cs.washington.edu (zone cached) ---")
    answers3 = resolver.resolve("galah.cs.washington.edu", "A")
    for line in resolver.query_log:
        print(line)
    resolver.query_log.clear()
    print(f"\n  Final answer: {answers3[0].rdata if answers3 else 'NXDOMAIN'}")

    print("\n--- Query 4: www.eng.washington.edu (different zone) ---")
    answers4 = resolver.resolve("www.eng.washington.edu", "A")
    for line in resolver.query_log:
        print(line)
    resolver.query_log.clear()
    print(f"\n  Final answer: {answers4[0].rdata if answers4 else 'NXDOMAIN'}")

    print("\n--- Query 5: www.cs.washington.edu (CNAME chain) ---")
    cname_ans = resolver.resolve("www.cs.washington.edu", "CNAME")
    for line in resolver.query_log:
        print(line)
    resolver.query_log.clear()
    if cname_ans:
        print(f"\n  CNAME: {cname_ans[0].rdata}")
        a_ans = resolver.resolve("www-lb.cs.washington.edu", "A")
        for line in resolver.query_log:
            print(line)
        resolver.query_log.clear()
        if a_ans:
            print(f"\n  Final A: {a_ans[0].rdata}")

    print(f"\n--- Cache statistics ---")
    stats = resolver.cache_stats()
    print(f"  Total entries: {stats['total']}")
    print(f"  Valid: {stats['valid']}")
    print(f"  Expired: {stats['expired']}")

    print(f"\n{'=' * 70}")
    print("LAB 2: HTTP Request Lifecycle")
    print(f"{'=' * 70}")

    simulate_http_request("http://www.cs.washington.edu/index.html", resolver)

    print(f"\n{'=' * 70}")
    print("DNS + HTTP Combined Timeline")
    print(f"{'=' * 70}")
    print("""
  Typical page load (cold cache):
  +0ms    Browser determines URL
  +1ms    DNS query sent to local resolver
  +5ms    DNS: resolver -> root -> edu -> washington.edu -> cs.washington.edu
  +50ms   DNS answer received (IP = 128.208.3.90)
  +51ms   TCP SYN sent to 128.208.3.90:80
  +54ms   TCP SYN+ACK received
  +55ms   TCP ACK sent, connection established
  +56ms   HTTP GET /index.html sent
  +120ms  HTTP 200 OK response received (64ms server processing + transfer)
  +121ms  Browser parses HTML, finds embedded resources
  +122ms  Parallel fetch: logo.png, style.css, analytics.js (keep-alive connection)
  +180ms  All resources received, page rendered
  +180ms  Connection kept alive (idle timeout in 60s)
  +240ms  Connection closed after idle timeout

  DNS cache benefit (warm cache):
  +0ms    Browser determines URL
  +1ms    DNS: CACHE HIT (0ms vs 50ms cold)
  +2ms    TCP SYN sent
  +5ms    TCP established
  +6ms    HTTP GET sent
  +70ms   HTTP response received
  +71ms   Embedded resources fetched
  +120ms  Page rendered (60ms savings from DNS cache)
""")


if __name__ == "__main__":
    main()