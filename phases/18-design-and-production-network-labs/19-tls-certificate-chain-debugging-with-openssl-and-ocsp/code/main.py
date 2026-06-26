#!/usr/bin/env python3
"""TLS Certificate Chain Debugger (Production Lab 19).

Simulates the 'Compliance Vault' TLS debugging scenario from the lesson:
  leaf -> Let's Encrypt R3 (expired) -> ISRG Root X1

Implements:
  - RFC 8446 §4.4.2 chain-building rule validation
  - Expiry / not-yet-valid detection
  - Hostname mismatch detection (SAN wildcard-aware)
  - Weak signature algorithm and weak key detection
  - OCSP status simulation (good / revoked / unknown)
  - JSON report generation
  - NGINX / HAProxy OCSP stapling config generation
  - Prometheus blackbox monitoring YAML
  - Renewal runbook shell script

Stdlib only (ssl, socket, hashlib, datetime, json, dataclasses, os).

Run: python3 code/main.py
"""
from __future__ import annotations

import datetime
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

# ── Lesson "current date" (from prose: exercise 4 uses 2026-06-25) ──────────
TODAY = datetime.date(2026, 6, 25)

# ── Security thresholds ──────────────────────────────────────────────────────
MIN_RSA_BITS = 2048
MIN_EC_BITS = 256
WEAK_SIG_ALGS = frozenset({"md5WithRSAEncryption", "sha1WithRSAEncryption"})
EXPIRY_WARN_DAYS = 30


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class CertInfo:
    """One certificate in the TLS chain (leaf | intermediate | root)."""

    role: str                # leaf | intermediate | root
    subject: str
    issuer: str
    not_before: str          # ISO-8601 date string
    not_after: str           # ISO-8601 date string
    serial: str              # hex
    sig_alg: str             # e.g. sha256WithRSAEncryption
    key_type: str            # RSA | EC
    key_bits: int
    san: list[str]           # Subject Alternative Names (leaf only)
    is_ca: bool
    path_len: int            # -1 = unlimited
    key_usage: list[str]
    ext_key_usage: list[str]
    ocsp_url: str            # AIA OCSP URI
    ca_issuer_url: str       # AIA caIssuers URI
    crl_dp: list[str]        # CRL distribution points
    fingerprint_sha256: str


@dataclass
class ChainIssue:
    """One detected problem in the certificate chain."""

    severity: str   # ERROR | WARN | INFO
    code: str       # CERT_EXPIRED | HOSTNAME_MISMATCH | CHAIN_BROKEN | …
    cert: str       # subject of the offending certificate
    detail: str


@dataclass
class ChainResult:
    """Outcome of RFC 8446 §4.4.2 chain-building rule validation."""

    valid: bool
    issues: list[ChainIssue]


@dataclass
class OCSPResult:
    """Simulated OCSP response (RFC 6960) for one certificate."""

    cert_subject: str
    status: str                    # good | revoked | unknown
    produced_at: str
    this_update: str
    next_update: str
    revocation_time: Optional[str] = None
    revocation_reason: Optional[str] = None


@dataclass
class TLSReport:
    """Full TLS chain debug report (mirrors openssl s_client output)."""

    host: str
    port: int
    scan_time: str
    tls_version: str
    cipher_suite: str
    chain: list[CertInfo]
    chain_result: ChainResult
    ocsp: list[OCSPResult]
    summary_issues: list[str]
    recommendations: list[str]


# ── Helper ───────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


def _days_until(date_str: str) -> int:
    return (_parse_date(date_str) - TODAY).days


# ── Chain-building rule validator (RFC 8446 §4.4.2) ─────────────────────────

def validate_chain(chain: list[CertInfo], hostname: str) -> ChainResult:
    """Apply RFC 8446 §4.4.2 chain-building rules and return all issues."""
    issues: list[ChainIssue] = []

    for i, cert in enumerate(chain):
        nb = _parse_date(cert.not_before)
        na = _parse_date(cert.not_after)

        # Rule: validity window
        if TODAY > na:
            days_ago = (TODAY - na).days
            issues.append(ChainIssue(
                severity="ERROR",
                code="CERT_EXPIRED",
                cert=cert.subject,
                detail=f"expired {days_ago} day(s) ago (notAfter={cert.not_after})",
            ))
        elif TODAY < nb:
            issues.append(ChainIssue(
                severity="ERROR",
                code="CERT_NOT_YET_VALID",
                cert=cert.subject,
                detail=f"not yet valid until {cert.not_before}",
            ))
        else:
            days_left = (na - TODAY).days
            if days_left <= EXPIRY_WARN_DAYS:
                issues.append(ChainIssue(
                    severity="WARN",
                    code="CERT_EXPIRY_SOON",
                    cert=cert.subject,
                    detail=f"expires in {days_left} day(s) (notAfter={cert.not_after})",
                ))

        # Rule: weak signature algorithm
        if cert.sig_alg in WEAK_SIG_ALGS:
            issues.append(ChainIssue(
                severity="ERROR",
                code="WEAK_SIGNATURE",
                cert=cert.subject,
                detail=f"signature algorithm '{cert.sig_alg}' is cryptographically deprecated",
            ))

        # Rule: weak public key
        if cert.key_type == "RSA" and cert.key_bits < MIN_RSA_BITS:
            issues.append(ChainIssue(
                severity="ERROR",
                code="WEAK_KEY",
                cert=cert.subject,
                detail=f"RSA {cert.key_bits}-bit key is below minimum {MIN_RSA_BITS} bits",
            ))
        elif cert.key_type == "EC" and cert.key_bits < MIN_EC_BITS:
            issues.append(ChainIssue(
                severity="ERROR",
                code="WEAK_KEY",
                cert=cert.subject,
                detail=f"EC {cert.key_bits}-bit key is below minimum {MIN_EC_BITS} bits",
            ))

        # Rule: intermediate must have CA:TRUE in Basic Constraints
        if cert.role == "intermediate" and not cert.is_ca:
            issues.append(ChainIssue(
                severity="ERROR",
                code="NOT_CA",
                cert=cert.subject,
                detail="intermediate is missing Basic Constraints: CA:TRUE",
            ))

        # Rule: issuer/subject linkage (RFC 8446 §4.4.2 rule 2)
        if i < len(chain) - 1:
            next_cert = chain[i + 1]
            if cert.issuer != next_cert.subject:
                issues.append(ChainIssue(
                    severity="ERROR",
                    code="CHAIN_BROKEN",
                    cert=cert.subject,
                    detail=(
                        f"issuer='{cert.issuer}' does not match "
                        f"next cert subject='{next_cert.subject}'"
                    ),
                ))

        # Rule: leaf must cover the target hostname (SAN check)
        if cert.role == "leaf":
            if not _san_matches(hostname, cert.san):
                issues.append(ChainIssue(
                    severity="ERROR",
                    code="HOSTNAME_MISMATCH",
                    cert=cert.subject,
                    detail=f"hostname '{hostname}' not found in SAN: {cert.san}",
                ))

        # Rule: root must be self-signed
        if cert.role == "root" and cert.subject != cert.issuer:
            issues.append(ChainIssue(
                severity="ERROR",
                code="ROOT_NOT_SELF_SIGNED",
                cert=cert.subject,
                detail="root certificate subject != issuer (not self-signed)",
            ))

    # Rule: chain must terminate at a root
    if chain and chain[-1].role != "root":
        issues.append(ChainIssue(
            severity="ERROR",
            code="CHAIN_INCOMPLETE",
            cert=chain[-1].subject,
            detail="chain does not end in a root certificate — missing trust anchor",
        ))

    errors = [iss for iss in issues if iss.severity == "ERROR"]
    return ChainResult(valid=len(errors) == 0, issues=issues)


def _san_matches(hostname: str, san: list[str]) -> bool:
    """Match hostname against SAN list; honours wildcard (*.example.com)."""
    for name in san:
        if name.startswith("*."):
            suffix = name[2:]
            parts = hostname.split(".")
            if len(parts) >= 2 and ".".join(parts[1:]) == suffix:
                return True
        elif name == hostname:
            return True
    return False


# ── OCSP simulation (RFC 6960) ───────────────────────────────────────────────

def simulate_ocsp(
    cert: CertInfo,
    *,
    force_revoked: bool = False,
    force_unknown: bool = False,
) -> OCSPResult:
    """Simulate an OCSP response from the CA's responder at cert.ocsp_url.

    Real OCSP: the client builds a request (DER-encoded CertID), sends it to
    the responder, receives a BasicOCSPResponse signed by the CA, and checks:
      certStatus = good | revoked | unknown
    This simulation derives status from the caller flags (force_revoked /
    force_unknown) to exercise all three RFC 6960 status values.
    """
    if force_revoked:
        status = "revoked"
        revocation_time: Optional[str] = cert.not_after  # simulated revocation
        revocation_reason: Optional[str] = "keyCompromise"
    elif force_unknown:
        status = "unknown"
        revocation_time = None
        revocation_reason = None
    else:
        status = "good"
        revocation_time = None
        revocation_reason = None

    return OCSPResult(
        cert_subject=cert.subject,
        status=status,
        produced_at=TODAY.isoformat(),
        this_update=TODAY.isoformat(),
        next_update=(TODAY + datetime.timedelta(days=7)).isoformat(),
        revocation_time=revocation_time,
        revocation_reason=revocation_reason,
    )


# ── Certificate chain scenarios ──────────────────────────────────────────────

def _isrg_root_x1() -> CertInfo:
    return CertInfo(
        role="root",
        subject="CN=ISRG Root X1, O=Internet Security Research Group, C=US",
        issuer="CN=ISRG Root X1, O=Internet Security Research Group, C=US",
        not_before="2015-06-04",
        not_after="2035-06-04",
        serial="8210CFB0D240E3591C142132696741F9",
        sig_alg="sha256WithRSAEncryption",
        key_type="RSA",
        key_bits=4096,
        san=[],
        is_ca=True,
        path_len=-1,
        key_usage=["Certificate Sign", "CRL Sign"],
        ext_key_usage=[],
        ocsp_url="",
        ca_issuer_url="",
        crl_dp=[],
        fingerprint_sha256=(
            "96:BC:EC:06:26:49:76:F3:74:60:77:9A:CF:28:C5:A7:"
            "CF:E8:A3:C0:AA:E1:1A:8F:FC:EE:05:C0:BD:DF:08:C6"
        ),
    )


def build_broken_chain() -> tuple[str, int, list[CertInfo]]:
    """Broken chain: expired R3 intermediate and expired leaf (lesson scenario).

    As of TODAY (2026-06-25) Let's Encrypt R3 expired 2025-09-15, and the
    leaf's 90-day cert expired 2026-04-15. The chain is structurally correct
    (issuer/subject linkage holds) but two certificates have passed their
    notAfter date.
    """
    hostname = "compliance-vault.example.com"
    port = 443

    root = _isrg_root_x1()

    intermediate = CertInfo(
        role="intermediate",
        subject="CN=R3, O=Let's Encrypt, C=US",
        issuer="CN=ISRG Root X1, O=Internet Security Research Group, C=US",
        not_before="2020-09-04",
        not_after="2025-09-15",   # EXPIRED as of TODAY=2026-06-25 (284 days ago)
        serial="00912B084ACF0C18A753F6D62E25A75F5A",
        sig_alg="sha256WithRSAEncryption",
        key_type="RSA",
        key_bits=2048,
        san=[],
        is_ca=True,
        path_len=0,
        key_usage=["Digital Signature", "Certificate Sign", "CRL Sign"],
        ext_key_usage=["TLS Web Server Authentication", "TLS Web Client Authentication"],
        ocsp_url="http://x1.c.lencr.org",
        ca_issuer_url="http://x1.i.lencr.org/",
        crl_dp=["http://x1.c.lencr.org/clrl.crl"],
        fingerprint_sha256=(
            "67:AD:D1:16:6B:02:0A:E6:1B:0F:7A:18:C3:19:0C:E7:"
            "AE:13:B5:28:88:22:48:79:43:E7:27:23:14:36:97:91"
        ),
    )

    leaf = CertInfo(
        role="leaf",
        subject="CN=compliance-vault.example.com",
        issuer="CN=R3, O=Let's Encrypt, C=US",
        not_before="2026-01-15",
        not_after="2026-04-15",   # EXPIRED 71 days ago (90-day LE cert)
        serial="03F2B4B9E3D5C1A827F6E4A210BC97D5",
        sig_alg="sha256WithRSAEncryption",
        key_type="RSA",
        key_bits=2048,
        san=["compliance-vault.example.com", "www.compliance-vault.example.com"],
        is_ca=False,
        path_len=-1,
        key_usage=["Digital Signature", "Key Encipherment"],
        ext_key_usage=["TLS Web Server Authentication", "TLS Web Client Authentication"],
        ocsp_url="http://r3.o.lencr.org",
        ca_issuer_url="http://r3.i.lencr.org/",
        crl_dp=[],
        fingerprint_sha256=(
            "2A:BC:7D:F5:8E:1C:9A:43:2E:65:B8:F0:C4:D2:74:A5:"
            "B6:E3:12:87:9F:5A:31:4D:77:C8:E6:A0:3B:25:9E:81"
        ),
    )

    return hostname, port, [leaf, intermediate, root]


def build_fixed_chain() -> tuple[str, int, list[CertInfo]]:
    """Fixed chain: renewed leaf signed by current R10 intermediate."""
    hostname = "compliance-vault.example.com"
    port = 443

    root = _isrg_root_x1()

    intermediate = CertInfo(
        role="intermediate",
        subject="CN=R10, O=Let's Encrypt, C=US",
        issuer="CN=ISRG Root X1, O=Internet Security Research Group, C=US",
        not_before="2024-03-13",
        not_after="2027-03-12",   # valid; 260 days remaining
        serial="00A71E2D5D9A0C3B87F4D2E6C51A9B8F0D",
        sig_alg="sha256WithRSAEncryption",
        key_type="RSA",
        key_bits=2048,
        san=[],
        is_ca=True,
        path_len=0,
        key_usage=["Digital Signature", "Certificate Sign", "CRL Sign"],
        ext_key_usage=["TLS Web Server Authentication", "TLS Web Client Authentication"],
        ocsp_url="http://x1.c.lencr.org",
        ca_issuer_url="http://x1.i.lencr.org/",
        crl_dp=["http://x1.c.lencr.org/clrl.crl"],
        fingerprint_sha256=(
            "4A:BC:7D:F5:8E:1C:9A:43:2E:65:B8:F0:C4:D2:74:A5:"
            "B6:E3:12:87:9F:5A:31:4D:77:C8:E6:A0:3B:25:9E:82"
        ),
    )

    leaf = CertInfo(
        role="leaf",
        subject="CN=compliance-vault.example.com",
        issuer="CN=R10, O=Let's Encrypt, C=US",
        not_before="2026-06-01",
        not_after="2026-08-30",   # valid; 66 days remaining
        serial="04F3B5C0E4D6D2B938F7F5B321CD08E6",
        sig_alg="sha256WithRSAEncryption",
        key_type="RSA",
        key_bits=2048,
        san=["compliance-vault.example.com", "www.compliance-vault.example.com"],
        is_ca=False,
        path_len=-1,
        key_usage=["Digital Signature", "Key Encipherment"],
        ext_key_usage=["TLS Web Server Authentication", "TLS Web Client Authentication"],
        ocsp_url="http://r10.o.lencr.org",
        ca_issuer_url="http://r10.i.lencr.org/",
        crl_dp=[],
        fingerprint_sha256=(
            "3B:CD:8E:F6:9F:2D:0A:54:3F:76:C9:E1:D3:85:B7:C6:"
            "A4:23:98:0F:6B:42:5E:88:D9:F7:B1:4C:36:A0:9F:92"
        ),
    )

    return hostname, port, [leaf, intermediate, root]


# ── Report builder ───────────────────────────────────────────────────────────

def build_report(
    hostname: str,
    port: int,
    chain: list[CertInfo],
    tls_version: str = "TLSv1.3",
    cipher_suite: str = "TLS_AES_256_GCM_SHA384",
    ocsp_results: Optional[list[OCSPResult]] = None,
) -> TLSReport:
    chain_result = validate_chain(chain, hostname)

    if ocsp_results is None:
        # Default: all certs report 'good' OCSP
        ocsp_results = [simulate_ocsp(c) for c in chain]

    summary_issues = [
        f"[{iss.severity}] {iss.code}: {iss.detail}"
        for iss in chain_result.issues
    ]

    recs: list[str] = []
    leaf = next((c for c in chain if c.role == "leaf"), None)
    if leaf:
        days_left = _days_until(leaf.not_after)
        if days_left < 0:
            recs.append(
                f"URGENT: leaf certificate expired {-days_left}d ago — "
                "run: certbot renew --cert-name compliance-vault.example.com"
            )
        elif days_left <= EXPIRY_WARN_DAYS:
            recs.append(
                f"Leaf certificate expires in {days_left}d — "
                "schedule renewal immediately"
            )

    for cert in chain:
        if cert.role == "intermediate" and _days_until(cert.not_after) < 0:
            recs.append(
                f"Replace expired intermediate '{cert.subject}' — "
                "update ssl_certificate_chain / fullchain.pem with current CA bundle"
            )

    if any(iss.code == "CHAIN_BROKEN" for iss in chain_result.issues):
        recs.append(
            "Fix chain order: leaf first, then intermediates, then root "
            "(NGINX: ssl_certificate = fullchain.pem)"
        )

    if not chain_result.issues:
        recs.append(
            "Enable OCSP stapling: "
            "NGINX: ssl_stapling on; ssl_stapling_verify on; resolver 8.8.8.8; "
            "HAProxy: ssl ocsp-update on; Apache: SSLUseStapling On"
        )
        recs.append(
            "Set up 30-day expiry alerting via Prometheus blackbox_exporter "
            "(see outputs/monitoring.yml)"
        )

    return TLSReport(
        host=hostname,
        port=port,
        scan_time=TODAY.isoformat(),
        tls_version=tls_version,
        cipher_suite=cipher_suite,
        chain=chain,
        chain_result=chain_result,
        ocsp=ocsp_results,
        summary_issues=summary_issues,
        recommendations=recs,
    )


# ── Pretty printer ───────────────────────────────────────────────────────────

SEP = "─" * 72


def print_report(report: TLSReport, title: str = "") -> None:
    if title:
        print(f"\n{'═' * 72}")
        print(f"  {title}")
        print(f"{'═' * 72}")

    print(f"\n{SEP}")
    print(f"Host        : {report.host}:{report.port}")
    print(f"Scan time   : {report.scan_time}  (lesson TODAY)")
    print(f"TLS version : {report.tls_version}")
    print(f"Cipher suite: {report.cipher_suite}")

    print(f"\n{SEP}")
    print("Certificate chain (openssl s_client -showcerts output):")
    for idx, cert in enumerate(report.chain):
        days_left = _days_until(cert.not_after)
        validity_tag = "OK" if days_left > 0 else f"EXPIRED {-days_left}d ago"
        print(f"\n  [{idx}] {cert.role.upper():14s}  {cert.subject}")
        print(f"       Issuer      : {cert.issuer}")
        print(f"       Validity    : {cert.not_before} → {cert.not_after}  [{validity_tag}]")
        print(f"       Key         : {cert.key_type} {cert.key_bits}-bit  "
              f"sigAlg={cert.sig_alg}")
        if cert.san:
            print(f"       SAN         : {', '.join(cert.san)}")
        print(f"       CA          : {cert.is_ca}  pathLen={cert.path_len}")
        print(f"       Key Usage   : {', '.join(cert.key_usage)}")
        if cert.ext_key_usage:
            print(f"       EKU         : {', '.join(cert.ext_key_usage)}")
        print(f"       OCSP URL    : {cert.ocsp_url or '(none)'}")
        if cert.ca_issuer_url:
            print(f"       CA Issuer   : {cert.ca_issuer_url}")
        if cert.crl_dp:
            print(f"       CRL DP      : {', '.join(cert.crl_dp)}")
        print(f"       SHA-256     : {cert.fingerprint_sha256}")

    print(f"\n{SEP}")
    chain_ok = "PASS" if report.chain_result.valid else "FAIL"
    print(f"Chain validation (RFC 8446 §4.4.2): {chain_ok}")
    if report.chain_result.issues:
        for iss in report.chain_result.issues:
            icon = "✗" if iss.severity == "ERROR" else "⚠"
            print(f"  {icon} [{iss.severity:5s}] {iss.code}")
            print(f"           cert  : {iss.cert}")
            print(f"           detail: {iss.detail}")
    else:
        print("  ✓ No issues detected")

    print(f"\n{SEP}")
    print("OCSP responses (RFC 6960):")
    for ocsp in report.ocsp:
        icon = {"good": "✓", "revoked": "✗", "unknown": "?"}.get(ocsp.status, "?")
        subj_short = ocsp.cert_subject.split(",")[0]
        print(f"  {icon} {ocsp.status.upper():8s}  {subj_short}")
        print(f"           produced={ocsp.produced_at}  "
              f"nextUpdate={ocsp.next_update}")
        if ocsp.revocation_time:
            print(f"           REVOKED at {ocsp.revocation_time}  "
                  f"reason={ocsp.revocation_reason}")

    if report.recommendations:
        print(f"\n{SEP}")
        print("Recommendations:")
        for rec in report.recommendations:
            print(f"  → {rec}")

    print(f"\n{SEP}")


# ── Output file generators ───────────────────────────────────────────────────

def _nginx_stapling_conf(hostname: str) -> str:
    return f"""\
# NGINX OCSP stapling — add to your server {{ }} block
# Verify with: openssl s_client -connect {hostname}:443 -status

server {{
    listen 443 ssl http2;
    server_name {hostname};

    ssl_certificate     /etc/letsencrypt/live/{hostname}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{hostname}/privkey.pem;

    # Chain for staple verification (intermediates only, not the leaf)
    ssl_trusted_certificate /etc/letsencrypt/live/{hostname}/chain.pem;

    # OCSP stapling — server fetches + caches the signed OCSP response
    ssl_stapling        on;
    ssl_stapling_verify on;

    # Resolver used to contact the OCSP responder
    resolver            8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout    5s;

    # TLS hardening
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
}}
"""


def _monitoring_yml() -> str:
    return """\
# Prometheus blackbox_exporter — TLS expiry monitoring
# Place in /etc/prometheus/blackbox.yml

modules:
  tls_expiry:
    prober: tcp
    timeout: 10s
    tcp:
      tls: true
      tls_config:
        insecure_skip_verify: false

# --- prometheus.yml scrape config ---
# - job_name: tls_expiry
#   scrape_interval: 1h
#   metrics_path: /probe
#   params:
#     module: [tls_expiry]
#   static_configs:
#     - targets:
#         - compliance-vault.example.com:443
#   relabel_configs:
#     - source_labels: [__address__]
#       target_label: __param_target
#     - target_label: __address__
#       replacement: blackbox-exporter:9115

# --- Alert rules (alert_rules.yml) ---
# groups:
#   - name: tls
#     rules:
#       - alert: TLSCertExpiresIn30Days
#         expr: probe_ssl_earliest_cert_expiry - time() < 30 * 86400
#         for: 1h
#         labels:
#           severity: warning
#         annotations:
#           summary: "TLS cert expiring < 30d: {{ $labels.instance }}"
#
#       - alert: TLSCertExpiresIn7Days
#         expr: probe_ssl_earliest_cert_expiry - time() < 7 * 86400
#         for: 1h
#         labels:
#           severity: critical
#         annotations:
#           summary: "URGENT: TLS cert expiring < 7d: {{ $labels.instance }}"
"""


def _renewal_sh(hostname: str) -> str:
    return f"""\
#!/bin/bash
# TLS certificate renewal runbook for Compliance Vault
# Cron: 0 3 * * * /opt/scripts/renewal.sh >> /var/log/certbot-renewal.log 2>&1
set -euo pipefail

HOSTNAME="{hostname}"
WEBROOT="/var/www/html"

echo "=== $(date -u) : Starting TLS renewal for $HOSTNAME ==="

# 1. Renew via Let's Encrypt (certbot)
certbot renew \\
    --cert-name "$HOSTNAME" \\
    --webroot --webroot-path "$WEBROOT" \\
    --post-hook "systemctl reload nginx"

# 2. Verify the new leaf certificate
openssl x509 \\
    -in /etc/letsencrypt/live/$HOSTNAME/cert.pem \\
    -noout -subject -issuer -dates

# 3. Verify chain-of-trust
openssl verify \\
    -CAfile /etc/letsencrypt/live/$HOSTNAME/chain.pem \\
    /etc/letsencrypt/live/$HOSTNAME/cert.pem

# 4. Query OCSP status
openssl ocsp \\
    -issuer /etc/letsencrypt/live/$HOSTNAME/chain.pem \\
    -cert   /etc/letsencrypt/live/$HOSTNAME/cert.pem \\
    -url    "$(openssl x509 -in /etc/letsencrypt/live/$HOSTNAME/cert.pem \\
               -noout -ocsp_uri)" \\
    -resp_text 2>&1 | grep -E "(Cert Status|This Update|Next Update)"

# 5. Confirm stapled response is visible (requires NGINX reload above)
echo "Verifying OCSP staple..."
openssl s_client \\
    -connect $HOSTNAME:443 \\
    -servername $HOSTNAME \\
    -status \\
    </dev/null 2>&1 | grep -E "(OCSP response|Cert Status)"

echo "=== Renewal complete for $HOSTNAME ==="

# --- Revocation runbook (key compromise) ---
# 1. revoke:   certbot revoke --cert-path /etc/letsencrypt/live/$HOSTNAME/cert.pem
# 2. new key:  certbot certonly --key-type ecdsa --elliptic-curve secp384r1 ...
# 3. deploy:   systemctl reload nginx
# 4. verify:   openssl s_client -connect $HOSTNAME:443 -status
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs("outputs", exist_ok=True)

    # ── Scenario 1: Broken chain (lesson scenario) ───────────────────────────
    host_b, port_b, chain_b = build_broken_chain()
    report_broken = build_report(host_b, port_b, chain_b)
    print_report(
        report_broken,
        "SCENARIO 1 — Broken chain  (leaf[expired] → R3[expired] → ISRG Root X1)",
    )

    # ── Scenario 2: Fixed chain ──────────────────────────────────────────────
    host_f, port_f, chain_f = build_fixed_chain()
    # Leaf cert's OCSP is 'good'; demonstrate 'revoked' for an additional check
    leaf_good = simulate_ocsp(chain_f[0])
    inter_good = simulate_ocsp(chain_f[1])
    root_na = simulate_ocsp(chain_f[2])   # root has no OCSP; 'good' trivially
    report_fixed = build_report(
        host_f, port_f, chain_f,
        ocsp_results=[leaf_good, inter_good, root_na],
    )
    print_report(
        report_fixed,
        "SCENARIO 2 — Fixed chain   (leaf[valid] → R10[valid] → ISRG Root X1)",
    )

    # ── RFC 8446 §4.4.2 chain-building rules (annotated) ────────────────────
    print(f"\n{'═' * 72}")
    print("  RFC 8446 §4.4.2 Chain-Building Rule Demonstration")
    print(f"{'═' * 72}\n")
    chain = chain_f
    print("Rule 1 — Chain order: leaf first, intermediates, then root")
    for i, cert in enumerate(chain):
        print(f"  [{i}] {cert.role:14s}  {cert.subject}")

    print("\nRule 2 — Issuer/subject linkage (each cert signed by the next):")
    for i in range(len(chain) - 1):
        c, n = chain[i], chain[i + 1]
        ok = c.issuer == n.subject
        sym = "✓" if ok else "✗"
        print(f"  {sym}  [{i}].issuer == [{i+1}].subject  →  {ok}")
        print(f"       '{c.issuer}'")
        print(f"    == '{n.subject}'")

    print("\nRule 3 — Root is self-signed (subject == issuer):")
    root = chain[-1]
    self_signed = root.subject == root.issuer
    print(f"  {'✓' if self_signed else '✗'}  {self_signed}  '{root.subject}'")

    print("\nRule 4 — Intermediate has CA:TRUE and pathLen=0 (max 1 more CA):")
    inter = chain[1]
    print(f"  is_ca={inter.is_ca}  path_len={inter.path_len}  "
          f"({'✓ OK' if inter.is_ca and inter.path_len == 0 else '✗ FAIL'})")

    # ── All three OCSP status values ─────────────────────────────────────────
    print(f"\n{SEP}")
    print("OCSP status values (RFC 6960) — all three states:")
    leaf_cert = chain_f[0]
    ocsp_good = simulate_ocsp(leaf_cert)
    ocsp_revoked = simulate_ocsp(leaf_cert, force_revoked=True)
    ocsp_unknown = simulate_ocsp(leaf_cert, force_unknown=True)
    for result in (ocsp_good, ocsp_revoked, ocsp_unknown):
        icon = {"good": "✓", "revoked": "✗", "unknown": "?"}.get(result.status, "?")
        print(f"  {icon}  status={result.status:8s}  "
              f"nextUpdate={result.next_update}  "
              f"revocationTime={result.revocation_time or 'n/a'}")

    # ── Hostname / SAN matching ──────────────────────────────────────────────
    print(f"\n{SEP}")
    print("SAN hostname matching (wildcard-aware):")
    san = ["compliance-vault.example.com", "www.compliance-vault.example.com"]
    test_hostnames = [
        "compliance-vault.example.com",
        "www.compliance-vault.example.com",
        "api.compliance-vault.example.com",   # NOT in SAN
        "evil.example.com",                    # NOT in SAN
    ]
    for h in test_hostnames:
        match = _san_matches(h, san)
        print(f"  {'✓' if match else '✗'}  {h:45s}  match={match}")

    # ── Weak-algorithm detection table ───────────────────────────────────────
    print(f"\n{SEP}")
    print("Weak-algorithm detector:")
    demo = [
        ("cert_a", "sha256WithRSAEncryption", "RSA", 4096),
        ("cert_b", "sha256WithRSAEncryption", "RSA", 2048),
        ("cert_c", "sha1WithRSAEncryption",   "RSA", 2048),   # weak sig
        ("cert_d", "md5WithRSAEncryption",    "RSA", 2048),   # weak sig
        ("cert_e", "sha256WithRSAEncryption", "RSA", 1024),   # weak key
        ("cert_f", "ecdsa-with-SHA256",       "EC",  256),
        ("cert_g", "ecdsa-with-SHA256",       "EC",  128),    # weak key
    ]
    print(f"  {'Name':8s}  {'Sig algorithm':35s}  {'Key':10s}  Result")
    print(f"  {'-'*8}  {'-'*35}  {'-'*10}  ------")
    for name, sig, kt, kb in demo:
        weak_sig = sig in WEAK_SIG_ALGS
        weak_key = (kt == "RSA" and kb < MIN_RSA_BITS) or \
                   (kt == "EC" and kb < MIN_EC_BITS)
        flags = []
        if weak_sig:
            flags.append("WEAK_SIGNATURE")
        if weak_key:
            flags.append("WEAK_KEY")
        result = ", ".join(flags) if flags else "OK"
        print(f"  {name:8s}  {sig:35s}  {kt} {kb:4d}   {result}")

    # ── Exercise 4: days-until-expiry calculation ────────────────────────────
    print(f"\n{SEP}")
    target_date = datetime.date(2027, 1, 1)
    days_remaining = (target_date - TODAY).days
    renewal_deadline = target_date - datetime.timedelta(days=EXPIRY_WARN_DAYS)
    print(f"Exercise 4 — Days until notAfter=2027-01-01 from TODAY={TODAY}:")
    print(f"  Days remaining    : {days_remaining}")
    print(f"  Renewal deadline  : {renewal_deadline} "
          f"({EXPIRY_WARN_DAYS} days before expiry)")
    print(f"  Alert would fire  : at or before {renewal_deadline}")

    # ── must-staple vs soft-fail ─────────────────────────────────────────────
    print(f"\n{SEP}")
    print("Exercise 5 — must-staple (RFC 7633) vs soft-fail:")
    print("  WITH  must-staple extension : OCSP responder down → TLS handshake FAILS")
    print("                                (client receives TLS alert: certificate_required)")
    print("  WITHOUT must-staple         : OCSP responder down → soft-fail")
    print("                                (handshake SUCCEEDS; revocation unchecked)")
    print("  must-staple prevents silent fallback to unvalidated revocation status")

    # ── Exercise 6: cross-signed chain ──────────────────────────────────────
    print(f"\n{SEP}")
    print("Exercise 6 — Cross-signed intermediate (old root → new root):")
    print("  Client trust store: ISRG Root X1 only (new root)")
    print("  Server sends     : leaf → R3 (cross-signed by DST Root CA X3 AND ISRG)")
    print("  Path building    : client walks leaf → R3 → ISRG Root X1  ✓")
    print("  If server sends OLD intermediate (cross-signed by expired DST Root CA X3):")
    print("    client finds DST Root CA X3 in its trust store IF present")
    print("    → DST Root CA X3 expired 2021-09-30 → chain FAILS for modern clients")
    print("  Fix: serve the R3 cert signed by ISRG Root X1 (not the DST cross-sign)")

    # ── Write outputs ────────────────────────────────────────────────────────
    hostname = "compliance-vault.example.com"

    report_json = {
        "generated": TODAY.isoformat(),
        "broken_chain": asdict(report_broken),
        "fixed_chain": asdict(report_fixed),
        "chain_building_rules_rfc": "RFC 8446 §4.4.2",
        "ocsp_rfc": "RFC 6960",
        "must_staple_rfc": "RFC 7633",
    }
    with open("outputs/tls_report.json", "w") as fh:
        json.dump(report_json, fh, indent=2, default=str)
    print(f"\n{SEP}")
    print(f"Wrote outputs/tls_report.json")

    with open("outputs/nginx_stapling.conf", "w") as fh:
        fh.write(_nginx_stapling_conf(hostname))
    print("Wrote outputs/nginx_stapling.conf")

    with open("outputs/monitoring.yml", "w") as fh:
        fh.write(_monitoring_yml())
    print("Wrote outputs/monitoring.yml")

    with open("outputs/renewal.sh", "w") as fh:
        fh.write(_renewal_sh(hostname))
    print("Wrote outputs/renewal.sh")

    # ── Final summary ────────────────────────────────────────────────────────
    print(f"\n{'═' * 72}")
    print("Summary")
    print(f"{'═' * 72}")
    print(f"  Broken chain valid  : {report_broken.chain_result.valid}")
    print(f"  Fixed chain valid   : {report_fixed.chain_result.valid}")
    broken_errors = sum(
        1 for i in report_broken.chain_result.issues if i.severity == "ERROR"
    )
    fixed_errors = sum(
        1 for i in report_fixed.chain_result.issues if i.severity == "ERROR"
    )
    print(f"  Broken chain errors : {broken_errors}")
    print(f"  Fixed chain errors  : {fixed_errors}")
    print(f"  Root cert valid for : "
          f"{_days_until(_isrg_root_x1().not_after)} more days "
          f"(expires {_isrg_root_x1().not_after})")
    print()


if __name__ == "__main__":
    main()
