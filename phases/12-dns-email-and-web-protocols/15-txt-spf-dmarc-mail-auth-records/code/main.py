#!/usr/bin/env python3
"""TXT / SPF / DKIM / DMARC evaluator (RFC 1035 §3.3.14, RFC 6376, RFC 7208, RFC 7489).

Parses the DNS-carried policy records used by the modern mail-authentication
stack and applies a minimal evaluator against a sample message. Real-world
SPF, DKIM, and DMARC evaluation has many edge cases -- use pyspf / dkimpy /
parsedmarc for production checks. This script focuses on the conceptual core
so the lesson can be exercised without network calls.

Run with `python3 main.py`.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SpfPolicy:
    raw: str
    mechanisms: List[tuple]

    @classmethod
    def parse(cls, txt: str) -> "SpfPolicy":
        if not txt.startswith("v=spf1"):
            raise ValueError(f"not an SPF record: {txt!r}")
        parts = txt.split()
        mechs: List[tuple] = []
        for token in parts[1:]:
            qualifier = "+"
            if token[0] in "+-~?":
                qualifier = token[0]
                token = token[1:]
            if ":" in token:
                mech, value = token.split(":", 1)
            else:
                mech, value = token, None
            mechs.append((qualifier, mech, value))
        return cls(raw=txt, mechanisms=mechs)


def evaluate_spf(policy: SpfPolicy, sending_ip: str) -> str:
    """Toy evaluator. Recognises ip4 / ip6 / mx / a / include / all."""
    if not policy.mechanisms:
        return "none"
    last_qualifier = "?"
    last_mech = "all"
    for qualifier, mech, value in policy.mechanisms:
        last_qualifier = qualifier
        last_mech = mech
        if mech == "ip4" and value is not None:
            try:
                if ipaddress.ip_address(sending_ip) in ipaddress.ip_network(value, strict=False):
                    return "pass"
            except ValueError:
                continue
        elif mech == "ip6" and value is not None:
            try:
                if ipaddress.ip_address(sending_ip) in ipaddress.ip_network(value, strict=False):
                    return "pass"
            except ValueError:
                continue
        elif mech == "all":
            break
    if last_mech != "all":
        return "neutral"
    return {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}.get(last_qualifier, "neutral")


def parse_dkim_txt(txt: str) -> Dict[str, str]:
    """Parse a DKIM TXT record into a tag dict (RFC 6376 §3.6.1)."""
    tags = {}
    if not txt.startswith("v=DKIM1"):
        raise ValueError(f"not a DKIM TXT: {txt!r}")
    for tag in txt.split(";"):
        tag = tag.strip()
        if not tag:
            continue
        if "=" in tag:
            k, _, v = tag.partition("=")
            tags[k.strip()] = v.strip()
    return tags


def parse_dmarc_txt(txt: str) -> Dict[str, str]:
    """Parse a DMARC TXT record (RFC 7489 §6.3)."""
    tags: Dict[str, str] = {}
    if not txt.startswith("v=DMARC1"):
        raise ValueError(f"not a DMARC TXT: {txt!r}")
    for tag in txt.split(";"):
        tag = tag.strip()
        if not tag:
            continue
        if "=" in tag:
            k, _, v = tag.partition("=")
            tags[k.strip()] = v.strip()
    return tags


@dataclass(frozen=True)
class Alignment:
    spf_aligned: bool
    dkim_aligned: bool

    def passes(self) -> bool:
        return self.spf_aligned or self.dkim_aligned


def relaxed_alignment(from_domain: str, auth_domain: str) -> bool:
    """Same organizational domain (last two labels)."""
    def org(d: str) -> str:
        parts = d.rstrip(".").split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else d
    return org(from_domain) == org(auth_domain)


def dmarc_action(policy: Dict[str, str], alignment: Alignment, spf_result: str, dkim_result: str) -> str:
    if not alignment.passes():
        return policy.get("p", "none")
    return "pass"


def main() -> None:
    print("=" * 64)
    print("TXT / SPF / DKIM / DMARC  --  RFC 1035 / 6376 / 7208 / 7489")
    print("=" * 64)

    spf_txt = "v=spf1 ip4:192.0.2.0/24 ip4:198.51.100.5 include:_spf.google.com ~all"
    policy = SpfPolicy.parse(spf_txt)
    print(f"\nSPF policy parsed: {policy.raw}")
    print(f"  mechanisms ({len(policy.mechanisms)}):")
    for q, m, v in policy.mechanisms:
        print(f"    {q} {m}{(':' + v) if v else ''}")

    for ip in ("192.0.2.10", "198.51.100.5", "203.0.113.42"):
        print(f"  evaluate(ip={ip:<14}) -> {evaluate_spf(policy, ip)}")

    dkim_txt = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
    print("\nDKIM TXT (selector1._domainkey.example.com):")
    print(f"  {dkim_txt}")
    dkim_tags = parse_dkim_txt(dkim_txt)
    print(f"  parsed tags: {dkim_tags}")

    dmarc_txt = "v=DMARC1; p=reject; rua=mailto:dmarc-reports@example.com; ruf=mailto:forensics@example.com; pct=100"
    print("\nDMARC TXT (_dmarc.example.com):")
    print(f"  {dmarc_txt}")
    dmarc_tags = parse_dmarc_txt(dmarc_txt)
    print(f"  parsed tags: {dmarc_tags}")

    print("\nAligned-pass simulation:")
    cases = [
        ("alice@example.com", "bounces@example.com", "example.com", "pass"),
        ("alice@example.com", "bounces@gmail.com", "example.com", "pass"),
        ("alice@example.com", "bounces@example.org", "example.com", "fail"),
    ]
    for from_d, mailfrom, dkim_d, dkim_result in cases:
        align = Alignment(
            spf_aligned=relaxed_alignment(from_d, mailfrom),
            dkim_aligned=relaxed_alignment(from_d, dkim_d),
        )
        action = dmarc_action(dmarc_tags, align, "pass", dkim_result)
        print(
            f"  From={from_d:<22}  MAIL FROM={mailfrom:<24}  "
            f"DKIM d={dkim_d:<14}  -> align={align}  dmarc action={action}"
        )


if __name__ == "__main__":
    main()
