#!/usr/bin/env python3
"""Capstone 06: Secure Remote Access Plan + DNS/HTTP Diagnostic Tool.

Part 1: Secure remote access design (VPN, MFA, access control).
Part 2: DNS and HTTP diagnostic CLI tool (dig-like + curl-like simulator).

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass


def secure_remote_access_plan() -> None:
    print("=" * 65)
    print("Part 1: Secure Remote Access Plan")
    print("=" * 65)
    print(f"\n  VPN Design:")
    print(f"    Type:       SSL VPN (OpenVPN / Cisco AnyConnect)")
    print(f"    Transport:  DTLS 1.3 over UDP 443")
    print(f"    Auth:       MFA (SAML SSO + TOTP)")
    print(f"    Profile:    Split-tunnel (only corp traffic via VPN)")
    print(f"    MFA:        Okta SSO -> push notification + TOTP fallback")
    print(f"    Access:     RBAC by group (Engineering, Sales, Admin)")
    print(f"    Logging:    All VPN sessions logged to SIEM")
    print(f"    Timeout:    8-hour session, re-auth after 1 hour idle")
    print(f"    Endpoint:   Host check (antivirus, OS patch level, disk encryption)")

    print(f"\n  Access Control Matrix:")
    print(f"  {'Group':15s} {'VPN':5s} {'Prod SSH':8s} {'Prod DB':8s} {'Admin':5s}")
    print(f"  {'-'*15} {'-'*5} {'-'*8} {'-'*8} {'-'*5}")
    print(f"  {'Engineering':15s} {'YES':5s} {'YES':8s} {'read':8s} {'no':5s}")
    print(f"  {'Sales':15s} {'YES':5s} {'no':8s} {'no':8s} {'no':5s}")
    print(f"  {'NetAdmin':15s} {'YES':5s} {'YES':8s} {'YES':8s} {'YES':5s}")
    print(f"  {'Contractor':15s} {'lim':5s} {'lim':8s} {'no':8s} {'no':5s}")


@dataclass
class DNSAnswer:
    name: str
    rtype: str
    ttl: int
    value: str


@dataclass
class DNSResult:
    query: str
    rcode: str
    answers: list[DNSAnswer]


def dig_simulate(domain: str, rtype: str = "A") -> DNSResult:
    fake_db = {
        ("example.com", "A"): [DNSAnswer("example.com", "A", 3600, "93.184.216.34")],
        ("example.com", "AAAA"): [DNSAnswer("example.com", "AAAA", 3600, "2606:2800:220:1:248:1893:25c8:1946")],
        ("example.com", "MX"): [DNSAnswer("example.com", "MX", 3600, "10 mail.example.com")],
        ("example.com", "NS"): [DNSAnswer("example.com", "NS", 3600, "a.iana-servers.net")],
        ("mail.example.com", "A"): [DNSAnswer("mail.example.com", "A", 3600, "93.184.216.35")],
        ("nonexistent.com", "A"): [],
    }
    key = (domain.lower(), rtype.upper())
    answers = fake_db.get(key, [])
    rcode = "NOERROR" if answers else "NXDOMAIN"
    return DNSResult(domain, rcode, answers)


@dataclass
class HTTPResponse:
    status: int
    headers: dict
    body: str


def curl_simulate(url: str, method: str = "GET") -> HTTPResponse:
    if "example.com" in url:
        return HTTPResponse(200, {"Content-Type": "text/html", "Content-Length": "1256",
                                   "Server": "nginx/1.24", "Connection": "keep-alive"},
                            "<!DOCTYPE html><html><head><title>Example Domain</title>")
    return HTTPResponse(404, {"Content-Type": "text/html", "Content-Length": "153"},
                        "<html><body><h1>404 Not Found</h1></body></html>")


def dns_http_tool() -> None:
    print(f"\n{'='*65}")
    print(f"Part 2: DNS and HTTP Diagnostic Tool")
    print(f"{'='*65}")

    print(f"\n  --- DNS Queries (dig-like simulator) ---")
    queries = [("example.com", "A"), ("example.com", "AAAA"), ("example.com", "MX"),
               ("example.com", "NS"), ("nonexistent.com", "A")]
    for domain, rtype in queries:
        result = dig_simulate(domain, rtype)
        print(f"\n  $ dig {domain} {rtype}")
        print(f"  ;; ANSWER SECTION (rcode={result.rcode}):")
        if result.answers:
            for a in result.answers:
                print(f"  {a.name:25s} {a.ttl:5d} IN {a.rtype:5s} {a.value}")
        else:
            print(f"  (no answers - {result.rcode})")

    print(f"\n  --- HTTP Requests (curl-like simulator) ---")
    urls = ["http://example.com/", "http://nonexistent.com/"]
    for url in urls:
        resp = curl_simulate(url)
        print(f"\n  $ curl -v {url}")
        print(f"  < HTTP/1.1 {resp.status}")
        for k, v in resp.headers.items():
            print(f"  < {k}: {v}")
        print(f"  < ")
        print(f"  {resp.body[:60]}...")


def main() -> None:
    secure_remote_access_plan()
    dns_http_tool()


if __name__ == "__main__":
    main()
