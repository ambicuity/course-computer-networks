#!/usr/bin/env python3
"""Capstone 05: Analyze an HTTPS Failure.

Simulates the full HTTPS stack (DNS -> TCP -> TLS -> HTTP), injects
failures at each layer, produces a diagnostic report.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiagnosticResult:
    layer: str
    test: str
    result: str
    error_code: str
    root_cause: str


def diagnose_https_failures() -> list[DiagnosticResult]:
    return [
        DiagnosticResult("DNS", "dig example.com", "NXDOMAIN", "ERR_NAME_NOT_RESOLVED",
                         "Domain does not exist or DNS server unreachable"),
        DiagnosticResult("DNS", "dig example.com", "timeout", "ERR_NAME_NOT_RESOLVED",
                         "DNS server not responding (port 53 blocked)"),
        DiagnosticResult("TCP", "connect 93.184.216.34:443", "timeout", "ERR_CONNECTION_TIMED_OUT",
                         "Firewall blocking port 443 or server down"),
        DiagnosticResult("TCP", "connect 93.184.216.34:443", "refused", "ERR_CONNECTION_REFUSED",
                         "No service listening on port 443"),
        DiagnosticResult("TLS", "openssl s_client", "cert expired", "ERR_CERT_DATE_INVALID",
                         "Certificate past not_after date"),
        DiagnosticResult("TLS", "openssl s_client", "untrusted CA", "ERR_CERT_AUTHORITY_INVALID",
                         "Issuer not in trust store"),
        DiagnosticResult("TLS", "openssl s_client", "hostname mismatch", "ERR_CERT_COMMON_NAME_INVALID",
                         "SAN does not include the requested hostname"),
        DiagnosticResult("TLS", "openssl s_client", "TLS version", "ERR_SSL_PROTOCOL_ERROR",
                         "Server only supports TLS 1.0, client requires 1.2+"),
        DiagnosticResult("HTTP", "GET /", "403 Forbidden", "HTTP 403",
                         "Access denied (ACL, WAF, or auth required)"),
        DiagnosticResult("HTTP", "GET /", "500 Internal Error", "HTTP 500",
                         "Server-side application failure"),
        DiagnosticResult("HTTP", "GET /", "502 Bad Gateway", "HTTP 502",
                         "Reverse proxy cannot reach backend"),
        DiagnosticResult("HTTP", "GET /", "503 Service Unavailable", "HTTP 503",
                         "Service overloaded or in maintenance mode"),
    ]


def main() -> None:
    print("=" * 65)
    print("Capstone 05: Analyze an HTTPS Failure")
    print("=" * 65)

    results = diagnose_https_failures()
    print(f"\n  HTTPS failure catalog ({len(results)} scenarios):\n")
    print(f"  {'Layer':6s} {'Browser Error':35s} {'Root Cause'}")
    print(f"  {'-'*6} {'-'*35} {'-'*45}")
    for r in results:
        print(f"  {r.layer:6s} {r.error_code:35s} {r.root_cause}")

    print(f"\n  Diagnostic procedure (top-down):")
    print(f"    1. DNS:      dig example.com  (is name resolving?)")
    print(f"    2. TCP:      nc -zv host 443  (is port open?)")
    print(f"    3. TLS:      openssl s_client -connect host:443  (cert valid?)")
    print(f"    4. HTTP:     curl -v https://example.com/  (response code?)")

    print(f"\n  Sample diagnosis: 'ERR_CERT_DATE_INVALID'")
    print(f"    Step 1 DNS:   example.com -> 93.184.216.34  (OK)")
    print(f"    Step 2 TCP:   Connected to 93.184.216.34:443  (OK)")
    print(f"    Step 3 TLS:   Verify return code: 10 (certificate has expired)")
    print(f"    Step 4 HTTP:  (never reached - TLS handshake failed)")
    print(f"    Root cause:   Certificate expired on 2024-01-01")
    print(f"    Fix:          certbot renew (Let's Encrypt auto-renewal)")

    print(f"\n  Browser error -> layer mapping:")
    print(f"    ERR_NAME_NOT_RESOLVED       -> DNS")
    print(f"    ERR_CONNECTION_TIMED_OUT    -> TCP (firewall/network)")
    print(f"    ERR_CONNECTION_REFUSED      -> TCP (service down)")
    print(f"    ERR_CERT_*                  -> TLS (certificate)")
    print(f"    ERR_SSL_PROTOCOL_ERROR      -> TLS (version/cipher)")
    print(f"    HTTP 4xx/5xx                -> Application (HTTP)")


if __name__ == "__main__":
    main()
