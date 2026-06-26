#!/usr/bin/env python3
"""Forward HTTP Proxy CONNECT tunnel and TLS interception diagnostic.

Reference oracle for the integrated troubleshooting lab. Given a
synthetic certificate chain (or one pasted from `openssl s_client`),
classifies the proxy mode and prints the verdict. Also runs an
end-to-end synthetic CONNECT exchange so the test is self-contained
and offline.

The chain format expected (one certificate block per entry):

    0 s:CN = api.partner.example
      i:CN = DigiCert Global G2
    1 s:CN = DigiCert Global G2
      i:CN = DigiCert Root CA

Modes:

  tunnel   -- the leaf issuer is a public CA recognised by the trust
              store; the proxy is forwarding TLS bytes unchanged.
  mitm     -- the leaf issuer is a corporate sub-CA; the proxy is
              terminating TLS, generating a new leaf, and re-encrypting.
  fail     -- the CONNECT exchange did not return HTTP/1.1 200; this
              is a tunnel-establishment problem, not a TLS one.

Run:  python3 main.py --mode tunnel
      python3 main.py --mode mitm
      python3 main.py --mode fail
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class CertEntry:
    """A single certificate in a chain: subject and issuer."""

    subject: str
    issuer: str


# Recognised public-CA strings (a small set for the lab).
PUBLIC_CA_MARKERS = (
    "DigiCert",
    "Let's Encrypt",
    "ISRG",
    "Sectigo",
    "Comodo",
    "GlobalSign",
    "IdenTrust",
    "GoDaddy",
    "Amazon",
    "Google Trust Services",
    "GTS",
    "Microsoft",
)

# Recognised corporate-CA strings (a small set for the lab).
CORP_CA_MARKERS = (
    "Corp Internal",
    "Enterprise Sub-CA",
    "Proxy Inspection CA",
    "Zscaler",
    "Palo Alto",
    "Netskope",
    "Blue Coat",
    "Symantec Managed PKI",
)


def classify_chain(chain: list[CertEntry]) -> tuple[str, str]:
    """Return (mode, reason) for a given certificate chain."""
    if not chain:
        return ("fail", "no certificate chain returned by the proxy")
    leaf = chain[0]
    if any(marker in leaf.issuer for marker in CORP_CA_MARKERS):
        return ("mitm", f"leaf issuer is corporate CA: {leaf.issuer}")
    if any(marker in leaf.issuer for marker in PUBLIC_CA_MARKERS):
        return ("tunnel", f"leaf issuer is public CA: {leaf.issuer}")
    return ("unknown", f"leaf issuer not recognised: {leaf.issuer}")


def connect_exchange(target_host: str, target_port: int) -> tuple[str, str]:
    """Render a synthetic CONNECT request and the proxy's response."""
    request = (
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n"
        f"User-Agent: openssl/3.0.13\r\n"
        f"\r\n"
    )
    return (request, "HTTP/1.1 200 Connection Established\r\nProxy-Agent: squid/5.7\r\n\r\n")


def tunnel_chain() -> list[CertEntry]:
    return [
        CertEntry(subject="CN = api.partner.example", issuer="CN = DigiCert Global G2"),
        CertEntry(subject="CN = DigiCert Global G2", issuer="CN = DigiCert Root CA"),
    ]


def mitm_chain() -> list[CertEntry]:
    return [
        CertEntry(subject="CN = api.partner.example", issuer="CN = Corp Internal Sub-CA, O = Corp"),
        CertEntry(subject="CN = Corp Internal Sub-CA, O = Corp", issuer="CN = Corp Internal Root, O = Corp"),
    ]


def render(request: str, response: str, chain: list[CertEntry], mode: str, reason: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"FORWARD PROXY DIAGNOSTIC  --  mode: {mode}")
    out.append("=" * 64)
    out.append("")
    out.append("--- CONNECT request sent to proxy ---")
    out.append(request.rstrip())
    out.append("")
    out.append("--- proxy response ---")
    out.append(response.rstrip())
    out.append("")
    out.append("--- certificate chain from openssl s_client ---")
    for i, c in enumerate(chain):
        out.append(f" {i} s:{c.subject}")
        out.append(f"   i:{c.issuer}")
    out.append("")
    out.append(f"Verdict: {mode.upper()}")
    out.append(f"Reason : {reason}")
    if mode == "mitm":
        out.append("Action : inspect the corporate CA's name constraints; the proxy")
        out.append("         is authorised to sign internal hostnames only.")
    elif mode == "tunnel":
        out.append("Action : no action; the proxy is in passthrough mode.")
    elif mode == "fail":
        out.append("Action : check the proxy's reply code; tunnel never came up.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--mode", choices=("tunnel", "mitm", "fail"), default="tunnel")
    parser.add_argument("--host", default="api.partner.example")
    parser.add_argument("--port", type=int, default=443)
    args = parser.parse_args()

    request, response = connect_exchange(args.host, args.port)
    if args.mode == "tunnel":
        chain = tunnel_chain()
    elif args.mode == "mitm":
        chain = mitm_chain()
    else:
        chain = []

    mode, reason = classify_chain(chain)
    if args.mode == "fail":
        mode, reason = ("fail", "proxy returned non-200 reply; tunnel did not establish")
        response = "HTTP/1.1 502 Bad Gateway\r\nProxy-Agent: squid/5.7\r\n\r\n"

    print(render(request, response, chain, mode, reason))


if __name__ == "__main__":
    main()
