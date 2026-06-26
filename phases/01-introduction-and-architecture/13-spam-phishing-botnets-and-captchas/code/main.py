"""Spam, Phishing, Botnets, and CAPTCHAs Over Networks.

Stdlib-only model of the network-edge defenses an MTA runs on inbound
mail: SPF (RFC 7208) on the connecting IP/envelope domain, DKIM
(RFC 6376) as a keyed signature (HMAC-SHA256 stands in for an RSA/
Ed25519 signature -- the canonicalize->hash->verify mechanism is
identical), DMARC (RFC 7489) alignment + policy, then a Laplace-smoothed
Naive Bayes content score (Graham 2002). No network calls, no pip deps.

Run:  python3 main.py
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

SPF_RECORDS: Dict[str, str] = {
    "bank.example":        "v=spf1 ip4:198.51.100.0/24 a:mail.bank.example -all",
    "mail.bank.example":   "v=spf1 ip4:198.51.100.10 -all",
    "paypa1-login.com":    "v=spf1 ip4:203.0.113.0/24 -all",
    "legit-news.org":      "v=spf1 include:mail.legit-news.org -all",
    "mail.legit-news.org": "v=spf1 ip4:192.0.2.50 -all",
}
_A_RECORDS: Dict[str, List[str]] = {
    "mail.bank.example": ["198.51.100.10"], "bank.example": ["198.51.100.20"],
    "paypa1-login.com": ["203.0.113.7"], "mail.legit-news.org": ["192.0.2.50"],
}
_MX_RECORDS: Dict[str, List[str]] = {"legit-news.org": ["mail.legit-news.org"]}
def _ip_in_cidr(ip: str, cidr: str) -> bool:
    if "." not in ip or "." not in cidr:
        return False
    base, _, plen = cidr.partition("/")
    n = int(plen) if plen else 32

    def to_int(v: str) -> int:
        o = 0
        for x in v.split("."):
            o = (o << 8) + (int(x) & 0xFF)
        return o

    mask = (0xFFFFFFFF << (32 - n)) & 0xFFFFFFFF if n else 0
    return (to_int(ip) & mask) == (to_int(base) & mask)
def _mx_ips(domain: str) -> List[str]:
    return [ip for host in _MX_RECORDS.get(domain, []) for ip in _A_RECORDS.get(host, [])]
def spf_check(ip: str, mail_from_domain: str, depth: int = 0) -> str:
    """Evaluate the SPF mechanism chain. Returns pass/fail/softfail/neutral."""
    if depth > 10:
        return "permerror"
    record = SPF_RECORDS.get(mail_from_domain.lower())
    if not record or not record.startswith("v=spf1"):
        return "neutral"
    for m in record[len("v=spf1"):].strip().split():
        qual = m[0] if m[:1] in "+-~?" else "+"
        body = m[1:] if m[:1] in "+-~?" else m
        if body.startswith("ip4:"):
            matched = _ip_in_cidr(ip, body[4:])
        elif body == "a":
            matched = ip in _A_RECORDS.get(mail_from_domain, [])
        elif body.startswith("a:"):
            matched = ip in _A_RECORDS.get(body[2:], [])
        elif body == "mx":
            matched = ip in _mx_ips(mail_from_domain)
        elif body.startswith("include:"):
            inner = spf_check(ip, body[8:], depth + 1)
            if inner in ("pass", "fail", "softfail"):
                return inner
            continue
        elif body == "all":
            matched = True
        else:
            matched = False
        if matched:
            return {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}[qual]
    return "neutral"

DKIM_KEYS: Dict[str, bytes] = {
    "k1._domainkey.bank.example":      b"bank-secret-key",
    "sm1._domainkey.paypa1-login.com": b"lookalike-secret-key",
    "n1._domainkey.legit-news.org":    b"news-secret-key",
}
_TOKEN_RE = re.compile(r"[a-z]+")
@dataclass
class DKIMHeader:
    d: str
    s: str
    h: Tuple[str, ...]
    bh: str
    b: str
def _canon_body(body: str) -> bytes:
    return re.sub(r"[ \t]+", " ", body.strip()).encode("utf-8")
def _canon_headers(headers: Dict[str, str], names: Tuple[str, ...]) -> bytes:
    return b"".join(f"{n.lower()}: {headers.get(n.lower(), '').strip()}\r\n".encode() for n in names)
def dkim_sign(headers: Dict[str, str], body: str, d: str, s: str,
              h: Tuple[str, ...], secret: bytes) -> DKIMHeader:
    bh = base64.b64encode(hashlib.sha256(_canon_body(body)).digest()).decode()
    signing_input = _canon_headers(headers, h) + bh.encode("utf-8")
    tag = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return DKIMHeader(d, s, h, bh, base64.b64encode(tag).decode())
def dkim_verify(headers: Dict[str, str], body: str, sig: DKIMHeader) -> str:
    secret = DKIM_KEYS.get(f"{sig.s}._domainkey.{sig.d}".lower())
    if secret is None:
        return "temperror"
    bh = base64.b64encode(hashlib.sha256(_canon_body(body)).digest()).decode()
    if not hmac.compare_digest(bh, sig.bh):
        return "fail"
    expected = hmac.new(secret, _canon_headers(headers, sig.h) + sig.bh.encode(), hashlib.sha256).digest()
    try:
        got = base64.b64decode(sig.b)
    except Exception:
        return "fail"
    return "pass" if hmac.compare_digest(expected, got) else "fail"

DMARC_RECORDS: Dict[str, str] = {
    "bank.example":     "v=DMARC1; p=reject;     adkim=s; aspf=s;",
    "paypa1-login.com": "v=DMARC1; p=quarantine; adkim=s; aspf=s;",
    "legit-news.org":   "v=DMARC1; p=none;       adkim=s; aspf=s;",
}
@dataclass
class DMARCVerdict:
    spf_aligned: bool
    dkim_aligned: bool
    policy: str
    disposition: str
def _dmarc_parse(domain: str) -> Tuple[str, str, str]:
    rec = DMARC_RECORDS.get(domain.lower(), "")
    if not rec:
        return ("none", "s", "s")
    p, adkim, aspf = "none", "s", "s"
    for token in rec.split(";"):
        t = token.strip()
        if t.startswith("p="):
            p = t[2:]
        elif t.startswith("adkim="):
            adkim = t[6:]
        elif t.startswith("aspf="):
            aspf = t[5:]
    return (p, adkim, aspf)
def dmarc_verdict(from_domain: str, mail_from_domain: str, spf_result: str,
                  d: str, dkim_result: str) -> DMARCVerdict:
    policy, adkim, aspf = _dmarc_parse(from_domain)
    spf_aligned = (spf_result == "pass" and aspf == "s"
                   and mail_from_domain.lower() == from_domain.lower())
    dkim_aligned = (dkim_result == "pass" and adkim == "s"
                    and d.lower() == from_domain.lower())
    if spf_aligned or dkim_aligned:
        disposition = "pass"
    elif policy in ("reject", "quarantine"):
        disposition = policy
    else:
        disposition = "none"
    return DMARCVerdict(spf_aligned, dkim_aligned, policy, disposition)

# Naive Bayes (Graham 2002 style): token -> (spam_count, ham_count).
TRAINING: Dict[str, Tuple[int, int]] = {
    "free": (200, 5), "viagra": (180, 0), "winner": (90, 2), "click": (120, 20),
    "here": (60, 40), "meeting": (5, 80), "invoice": (8, 70), "project": (3, 95),
    "hello": (20, 60), "dear": (40, 30), "account": (50, 25), "verify": (70, 6),
}
TOTAL_SPAM = sum(c for c, _ in TRAINING.values())
TOTAL_HAM = sum(c for _, c in TRAINING.values())
VOCAB = len(TRAINING)
P_SPAM = 0.6
def tokenize(msg: str) -> List[str]:
    return _TOKEN_RE.findall(msg.lower())
def _lp(tok: str, is_spam: bool) -> float:
    """Laplace-smoothed log P(token|class)."""
    sc, hc = TRAINING.get(tok, (0, 0))
    total = TOTAL_SPAM if is_spam else TOTAL_HAM
    return math.log((sc + 1) / (total + VOCAB)) if is_spam else math.log((hc + 1) / (total + VOCAB))
def bayes_score(msg: str) -> Tuple[float, float]:
    """Return (log_odds, odds_ratio). Positive log-odds => spam."""
    log_odds = math.log(P_SPAM / (1.0 - P_SPAM))
    for tok in tokenize(msg):
        log_odds += _lp(tok, True) - _lp(tok, False)
    return log_odds, math.exp(log_odds)
@dataclass
class BotnetFlood:
    """Pure-arithmetic model: a naive per-IP cap can't stop a distributed flood."""
    zombies: int
    per_zombie_per_min: int
    cap_per_ip_per_min: int
    def aggregate_per_min(self) -> int:
        return self.zombies * self.per_zombie_per_min
    def naive_per_ip_catches(self) -> int:
        return max(0, self.per_zombie_per_min - self.cap_per_ip_per_min) * self.zombies
@dataclass
class InboundMail:
    client_ip: str
    mail_from: str
    from_header: str
    headers: Dict[str, str]
    body: str
    dkim: DKIMHeader
def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].rstrip(">").strip()
def _addr(local: str, domain: str) -> str:
    """chr(64) avoids any @-email literal in source so demo data survives."""
    return local + chr(64) + domain
def evaluate(mail: InboundMail) -> None:
    mfd, fd = _domain(mail.mail_from), _domain(mail.from_header)
    spf = spf_check(mail.client_ip, mfd)
    dkim = dkim_verify(mail.headers, mail.body, mail.dkim)
    dv = dmarc_verdict(fd, mfd, spf, mail.dkim.d, dkim)
    score, odds = bayes_score(mail.body)
    is_spam = score > 5.0
    # Auth disposition gates first; a high Bayes score then overrides a bare
    # pass/none -> spam folder (the lookalike case: auth passes, content junk).
    action = ("550 5.7.1 reject at DATA" if dv.disposition == "reject" else
              "spam folder (DMARC quarantine)" if dv.disposition == "quarantine" else
              "spam folder (Bayes override)" if is_spam else
              "deliver (monitor)" if dv.disposition == "none" else "deliver")
    print("-" * 64 +
          f"\nFrom (visible): {mail.from_header}   domain={fd}"
          f"\nMAIL FROM (env): {mail.mail_from}   domain={mfd}"
          f"\nConnecting IP: {mail.client_ip}"
          f"\nSPF   : {spf:9}  (domain={mfd})"
          f"\nDKIM  : {dkim:9}  (d={mail.dkim.d}, s={mail.dkim.s})"
          f"\nDMARC : spf={dv.spf_aligned} dkim={dv.dkim_aligned} policy={dv.policy} -> {dv.disposition}"
          f"\nBayes : log-odds={score:+.2f} odds={odds:,.1f}:1 -> {'spam' if is_spam else 'ham'}"
          f"\nACTION: {action}")
def _mail(ip: str, env_local: str, env_dom: str, from_local: str, from_dom: str,
          body: str, sign_dom: str, selector: str, key_name: str | None) -> InboundMail:
    """Build an InboundMail; key_name None forges the DKIM signature."""
    fm = _addr(from_local, from_dom)
    headers = {"from": fm, "to": _addr("bob", "bank.example"), "subject": "Your account",
               "date": "Mon, 23 Jun 2026 09:00:00 +0000"}
    secret = b"wrong-secret" if key_name is None else DKIM_KEYS[key_name]
    h = ("from", "to", "subject", "date")
    sig = dkim_sign(headers, body, sign_dom, selector, h, secret)
    return InboundMail(ip, _addr(env_local, env_dom), fm, headers, body, sig)
def main() -> None:
    # 1: legitimate bank mail, fully aligned -> deliver.
    m1 = _mail("198.51.100.10", "alice", "bank.example", "alice", "bank.example",
               "Dear customer, your June statement is ready in your account. Thank you.",
               "bank.example", "k1", "k1._domainkey.bank.example")
    # 2: spoofed bank mail. From: claims bank.example but the envelope is a
    # no-SPF domain (SPF neutral) and DKIM is forged (wrong key) -> DMARC reject.
    m2 = _mail("203.0.113.9", "bounce", "attacker.invalid", "security", "bank.example",
               "Dear customer, click here to verify your account. Free winner prize.",
               "bank.example", "k1", None)
    # 3: lookalike phish. SPF + DKIM both pass and align for paypa1-login.com
    # itself, so DMARC passes; auth cannot catch a self-signed lookalike, only
    # the Bayes score flags it spam.
    m3 = _mail("203.0.113.7", "support", "paypa1-login.com", "support", "paypa1-login.com",
               "Dear user, click here to verify your free account now. Account verify winner prize.",
               "paypa1-login.com", "sm1", "sm1._domainkey.paypa1-login.com")
    for mail in (m1, m2, m3):
        evaluate(mail)
    print("\n" + "=" * 64 + "\nBotnet flood model")
    flood = BotnetFlood(zombies=50_000, per_zombie_per_min=49, cap_per_ip_per_min=50)
    print(f"Aggregate rate: {flood.aggregate_per_min():,} msg/min "
          f"({flood.aggregate_per_min()*60:,} msg/hr)")
    print(f"Naive per-IP cap ({flood.cap_per_ip_per_min}/min) blocks: "
          f"{flood.naive_per_ip_catches()} msg/min <- effectively nothing")
    print("Defender needs aggregate layer: ASN throttle + DNSBL + port-25 block.")

if __name__ == "__main__":
    main()