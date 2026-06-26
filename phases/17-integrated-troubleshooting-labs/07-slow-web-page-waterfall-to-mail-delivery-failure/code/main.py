#!/usr/bin/env python3
"""Slow Web Page Waterfall + Mail Delivery Failure (Integrated Lab 07).

Models a DNS zone with deliberately broken DKIM, SPF, DMARC, and CNAME
records. Walks the four-step diagnostic chain for five scenarios:

  dns_migration   - authoritative DNS is slow (1.5 s) for TXT queries
  cname_broken    - CNAME for the CDN hostname is missing
  dkim_missing    - DKIM TXT record is missing
  spf_wrong       - SPF TXT record lists wrong IP range
  healthy         - all records correct

Run:  python3 main.py [--mode <mode>|all]
"""
from __future__ import annotations

import argparse
import enum
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    DNS_MIGRATION = "dns_migration"
    CNAME_BROKEN = "cname_broken"
    DKIM_MISSING = "dkim_missing"
    SPF_WRONG = "spf_wrong"
    HEALTHY = "healthy"


# ---------------------------------------------------------------------------
# DNS zone records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ZoneRecord:
    name: str
    rtype: str
    value: str
    ttl: int = 300


@dataclass
class DnsZone:
    domain: str = "example.com"
    records: list[ZoneRecord] = field(default_factory=list)
    authoritative_query_ms: float = 20.0

    def get(self, name: str, rtype: str) -> list[str]:
        return [r.value for r in self.records
                if r.name == name and r.rtype == rtype]

    def has(self, name: str, rtype: str) -> bool:
        return bool(self.get(name, rtype))


# ---------------------------------------------------------------------------
# Build zones
# ---------------------------------------------------------------------------
def build_zone(mode: FailureMode) -> DnsZone:
    z = DnsZone()
    z.records = [
        # A/AAAA/MX are always present and correct
        ZoneRecord("example.com", "A", "93.184.216.34"),
        ZoneRecord("example.com", "AAAA", "2606:2800:220:1:248:1893:25c8:1946"),
        ZoneRecord("example.com", "MX", "10 mail.example.com"),
    ]
    if mode is FailureMode.HEALTHY:
        z.records.extend([
            ZoneRecord("example.com", "TXT", '"v=spf1 ip4:93.184.216.0/24 -all"'),
            ZoneRecord("default._domainkey.example.com", "TXT",
                       '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCg..."'),
            ZoneRecord("_dmarc.example.com", "TXT",
                       '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'),
            ZoneRecord("cdn.example.com", "CNAME", "example.cdn.net"),
        ])
    elif mode is FailureMode.DNS_MIGRATION:
        # TXT records are returned but the authoritative server is slow
        z.records.extend([
            ZoneRecord("example.com", "TXT", '"v=spf1 ip4:93.184.216.0/24 -all"'),
            ZoneRecord("default._domainkey.example.com", "TXT",
                       '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCg..."'),
            ZoneRecord("_dmarc.example.com", "TXT",
                       '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'),
            ZoneRecord("cdn.example.com", "CNAME", "example.cdn.net"),
        ])
        z.authoritative_query_ms = 1500.0
    elif mode is FailureMode.CNAME_BROKEN:
        z.records.extend([
            ZoneRecord("example.com", "TXT", '"v=spf1 ip4:93.184.216.0/24 -all"'),
            ZoneRecord("default._domainkey.example.com", "TXT",
                       '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCg..."'),
            ZoneRecord("_dmarc.example.com", "TXT",
                       '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'),
            # CNAME missing!
        ])
    elif mode is FailureMode.DKIM_MISSING:
        z.records.extend([
            ZoneRecord("example.com", "TXT", '"v=spf1 ip4:93.184.216.0/24 -all"'),
            # DKIM TXT missing
            ZoneRecord("_dmarc.example.com", "TXT",
                       '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'),
            ZoneRecord("cdn.example.com", "CNAME", "example.cdn.net"),
        ])
    else:  # SPF_WRONG
        z.records.extend([
            ZoneRecord("example.com", "TXT", '"v=spf1 ip4:198.51.100.0/24 -all"'),
            ZoneRecord("default._domainkey.example.com", "TXT",
                       '"v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCg..."'),
            ZoneRecord("_dmarc.example.com", "TXT",
                       '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"'),
            ZoneRecord("cdn.example.com", "CNAME", "example.cdn.net"),
        ])
    return z


# ---------------------------------------------------------------------------
# Web and mail simulation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WaterfallEntry:
    label: str
    dns_ms: float
    tcp_ms: float
    tls_ms: float
    waiting_ms: float
    download_ms: float

    def total_ms(self) -> float:
        return self.dns_ms + self.tcp_ms + self.tls_ms + self.waiting_ms + self.download_ms


def simulate_waterfall(z: DnsZone) -> list[WaterfallEntry]:
    """Simulate the waterfall for a typical page with one CDN asset."""
    cname_present = z.has("cdn.example.com", "CNAME")
    cname_target = z.get("cdn.example.com", "CNAME")
    # The cdn.example.com lookup goes through the authoritative server.
    # If CNAME is missing, the browser falls back to a direct lookup of
    # apex; the time is still the authoritative_query_ms.
    cdn_dns_ms = z.authoritative_query_ms if not cname_present or not cname_target \
                 else z.authoritative_query_ms
    apex_dns_ms = z.authoritative_query_ms
    return [
        WaterfallEntry("GET / (HTML)", apex_dns_ms, 12, 18, 35, 2),
        WaterfallEntry("GET /style.css", cdn_dns_ms, 12, 18, 35, 2),
        WaterfallEntry("GET /app.js",   cdn_dns_ms, 12, 18, 35, 2),
        WaterfallEntry("GET /logo.png", cdn_dns_ms, 12, 18, 35, 2),
    ]


@dataclass(frozen=True)
class SmtpReply:
    code: int
    text: str


def simulate_smtp(z: DnsZone, sending_ip: str = "93.184.216.99") -> list[SmtpReply]:
    """Simulate an SMTP session and the receiver's checks."""
    replies: list[SmtpReply] = []
    replies.append(SmtpReply(220, "mx.google.com ESMTP ready"))
    replies.append(SmtpReply(250, "mx.google.com Hello sender.example.com"))
    replies.append(SmtpReply(250, "Sender OK"))
    # SPF check
    spf = z.get("example.com", "TXT")
    if not spf or sending_ip not in spf[0]:
        replies.append(SmtpReply(550, "5.7.1 ... does not designate "
                                     f"{sending_ip} as a permitted sender"))
        return replies
    # DKIM check
    if not z.has("default._domainkey.example.com", "TXT"):
        replies.append(SmtpReply(550, "5.7.1 ... DKIM signature verification failed"))
        return replies
    # DMARC check
    if not z.has("_dmarc.example.com", "TXT"):
        replies.append(SmtpReply(550, "5.7.1 ... DMARC policy not found"))
        return replies
    replies.append(SmtpReply(250, "Recipient OK"))
    replies.append(SmtpReply(354, "End data with <CR><LF>.<CR><LF>"))
    replies.append(SmtpReply(250, "Message accepted"))
    return replies


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


def cmd_dig_stats(z: DnsZone) -> DiagResult:
    if z.authoritative_query_ms > 200:
        return DiagResult(1, "dig +stats example.com",
                           f"Query time: {z.authoritative_query_ms:.0f} msec",
                           "DNS slow", True)
    return DiagResult(1, "dig +stats example.com",
                       f"Query time: {z.authoritative_query_ms:.0f} msec (OK)",
                       "DNS OK", False)


def cmd_waterfall(waterfall: list[WaterfallEntry]) -> DiagResult:
    cdn = [w for w in waterfall if "cdn" in w.label or "/style" in w.label or "/app" in w.label or "/logo" in w.label]
    if not cdn:
        cdn = waterfall[1:]
    avg_dns = sum(w.dns_ms for w in cdn) / len(cdn) if cdn else 0
    if avg_dns > 500:
        return DiagResult(2, "DevTools Network waterfall",
                           f"avg DNS Lookup = {avg_dns:.0f} ms on {len(cdn)} requests",
                           "DNS slow", True)
    return DiagResult(2, "DevTools Network waterfall",
                       f"avg DNS Lookup = {avg_dns:.0f} ms (OK)",
                       "DNS OK", False)


def cmd_curl_w(waterfall: list[WaterfallEntry]) -> DiagResult:
    w = waterfall[0]
    if w.dns_ms > 500:
        return DiagResult(3, "curl -w (text waterfall)",
                           f"time_namelookup={w.dns_ms:.0f}, "
                           f"time_starttransfer={w.waiting_ms:.0f}, "
                           f"time_total={w.total_ms():.0f}",
                           "DNS dominant", True)
    return DiagResult(3, "curl -w",
                       f"time_namelookup={w.dns_ms:.0f}, "
                       f"time_starttransfer={w.waiting_ms:.0f}, "
                       f"time_total={w.total_ms():.0f}",
                       "OK", False)


def cmd_smtp(z: DnsZone) -> DiagResult:
    replies = simulate_smtp(z)
    final = next((r for r in replies if r.code >= 500), replies[-1])
    if final.code == 550:
        return DiagResult(4, "SMTP session (mx.google.com)",
                           f"{final.code} {final.text}",
                           "DKIM/SPF/DMARC", True)
    return DiagResult(4, "SMTP session",
                       f"{final.code} {final.text}",
                       "Mail accepted", False)


def run_diag(z: DnsZone) -> list[DiagResult]:
    w = simulate_waterfall(z)
    return [cmd_dig_stats(z), cmd_waterfall(w), cmd_curl_w(w), cmd_smtp(z)]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render(mode: FailureMode, z: DnsZone, results: list[DiagResult]) -> None:
    print("=" * 78)
    print(f"DNS-Wide Diagnostic  [mode={mode.value}]")
    print("=" * 78)
    print("  Zone records:")
    for r in z.records:
        print(f"    {r.name:<40} {r.rtype:<6} {r.value}  (TTL={r.ttl})")
    print(f"  authoritative_query_ms: {z.authoritative_query_ms:.0f}")
    print()
    print("  Page-load waterfall (typical request):")
    for w in simulate_waterfall(z):
        print(f"    {w.label:<22} DNS={w.dns_ms:>5.0f}ms TCP={w.tcp_ms:>3.0f}ms "
              f"TLS={w.tls_ms:>3.0f}ms Wait={w.waiting_ms:>4.0f}ms "
              f"DL={w.download_ms:>3.0f}ms Total={w.total_ms():>5.0f}ms")
    print()
    print("  SMTP session (mx.google.com):")
    for r in simulate_smtp(z):
        print(f"    {r.code:>3} {r.text}")
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
        z = build_zone(mode)
        results = run_diag(z)
        render(mode, z, results)
        print()


if __name__ == "__main__":
    main()
