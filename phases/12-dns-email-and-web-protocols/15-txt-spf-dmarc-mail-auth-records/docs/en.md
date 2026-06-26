# TXT, SPF, and DMARC Mail Authentication Records

> The Domain Name System carries more than name-to-address mappings: it carries the policy that lets a domain announce which mail servers are authorized to send for it, and what receivers should do when a message fails authentication. The **TXT** record (RFC 1035 §3.3.14) is the generic DNS string container; **SPF** (Sender Policy Framework, RFC 7208) is its specialized successor, now published only as a TXT record at the apex (`example.com`) with the literal prefix `v=spf1`. **DKIM** (RFC 6376) puts a public key in a TXT at `<selector>._domainkey.example.com`, used by receivers to verify the cryptographic signature in the message header. **DMARC** (RFC 7489) ties them together with a TXT at `_dmarc.example.com` reporting where failures should be sent and what policy (none, quarantine, reject) to apply. Together these four record types form the modern email authentication stack that complements FCrDNS and lets a domain owner say, in machine-readable form, "these are my outbound servers; these are my signing keys; this is what to do with forgeries".

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Phase 12 lessons on DNS records, reverse DNS, and zone-file authoring
**Time:** ~75 minutes

## Learning Objectives

- Read a TXT record and recognize the `v=spf1` (RFC 7208) and `v=DMARC1` (RFC 7489) version tags and their mechanism syntax.
- Author an SPF policy that authorizes the right set of senders (with `mx`, `a`, `ip4`, `include`, `~all`) and verify it with `dig TXT example.com`.
- Publish a DKIM TXT record at `<selector>._domainkey.example.com` and understand how a receiver fetches the public key to verify a signature.
- Build a DMARC TXT record at `_dmarc.example.com` with `p=`, `sp=`, `rua=`, `ruf=`, and `pct=` tags, and reason about the policy choice.
- Trace an inbound message through SPF, DKIM, DMARC, and FCrDNS and predict the receiver's verdict for each pass/fail combination.
- Avoid the common misconfigurations: multiple SPF records (only one is allowed), over-broad `+all`, missing DKIM selectors, and DMARC policies stricter than the worst pass can support.

## The Problem

Your outbound mail goes to spam at Gmail and Outlook. You have set up PTR records (FCrDNS) but the rejections continue. You check `dig TXT example.com` and see nothing useful — no SPF record at all. Major receivers fall back to "no policy means no policy" and either reject or down-score the message. You also discover that DKIM signing is off because the DKIM TXT record was never published. And you have never sent a DMARC record, so receivers do not even know how to report failures to you.

The trap is treating SPF, DKIM, and DMARC as separate concerns. They are layered: SPF says who can send for the domain in the SMTP `MAIL FROM`, DKIM signs and lets the receiver verify, DMARC aligns the two with the `From:` header and decides what to do. Each one fixes a different forgery; all three together are needed for trustworthy senders.

## The Concept

### TXT: the generic DNS string container

The TXT record (RFC 1035 §3.3.14) was originally a free-form ASCII note. It is now the universal carrier for machine-readable policy. The format is `name TTL CLASS TXT "<one or more <character-string>s>"`, where each `<character-string>` is a 1-byte length prefix followed by up to 255 bytes of UTF-8. A single TXT record can carry up to 65535 bytes total when split across multiple strings. Most policy records use a single string because parsers prefer it.

### SPF: who can send for this domain (RFC 7208)

SPF is published as a TXT record at the domain apex. The exact prefix `v=spf1` identifies the record. Mechanisms, evaluated left-to-right, declare authorized senders:

```
example.com.  IN  TXT  "v=spf1 ip4:192.0.2.0/24 ip4:198.51.100.5 include:_spf.google.com ~all"
```

| Mechanism | Meaning |
|---|---|
| `ip4:192.0.2.0/24` | Any IPv4 in this range |
| `ip6:2001:db8::/32` | Any IPv6 in this range |
| `a` | Any IP whose reverse-confirmed name has an A record at this domain |
| `mx` | Any IP that is an MX for this domain |
| `include:domain` | Look up the SPF record at the included domain and use its mechanisms |
| `exists:domain` | Match if the domain has any A record (often used for dynamic IP ranges) |
| `redirect=domain` | Replace this entire record's evaluation with the SPF at the named domain |
| `all` | Catch-all; prefixes: `+all` (allow), `-all` (fail), `~all` (softfail), `?all` (neutral) |

The evaluation rule: count matches, count DNS queries, and stop after 10 mechanisms that required DNS lookups (RFC 7208 §4.6.4). If `+all` is reached, the result is `pass`; if `-all` is reached, the result is `fail`. The receiver uses the result to compute an SPF verdict: `none` (no policy), `neutral`, `pass`, `fail`, `softfail`, `temperror`, `permerror`.

Only **one** SPF record is allowed per domain. If a query returns more than one `v=spf1` TXT, the result is `permerror` and the message is treated as failing. Many published SPF records accidentally include two `v=spf1` strings because a second provider added their own; the fix is to merge into a single record using `include:`.

### DKIM: cryptographic signing (RFC 6376)

DKIM signs selected message headers and body with a per-domain RSA or Ed25519 key. The signature travels in a header like:

```
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=selector1;
                h=from:to:subject:date;
                bh=...; b=...
```

Where:
- `d=` is the signing domain.
- `s=` is the selector — a label that lets the domain publish multiple keys.
- `bh=` is the body hash.
- `b=` is the signature.

The receiver fetches the public key from `<selector>._domainkey.<d>`, TXT-record form:

```
selector1._domainkey.example.com.  IN  TXT  "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8..."
```

The `p=` value is the base64-encoded public key. A missing or empty `p=` means revoke the key. Receivers rotate keys by publishing a new selector and signing new messages with it; old selectors are retired by removing the TXT record.

### DMARC: alignment and policy (RFC 7489)

DMARC ties SPF and DKIM together. The TXT record at `_dmarc.example.com` carries `v=DMARC1` and policy tags:

```
_dmarc.example.com.  IN  TXT  "v=DMARC1; p=reject; rua=mailto:dmarc-reports@example.com; ruf=mailto:forensics@example.com; pct=100"
```

| Tag | Meaning |
|---|---|
| `v=DMARC1` | Version tag, must be exactly this |
| `p=` | Policy for the apex domain: `none`, `quarantine`, `reject` |
| `sp=` | Policy for subdomains (optional, defaults to `p`) |
| `rua=` | URI(s) for aggregate reports (XML, sent daily) |
| `ruf=` | URI(s) for forensic reports (per-message) |
| `pct=` | Percentage of messages to filter (1-100, default 100) |
| `adkim=` | DKIM alignment mode: `s` (strict) or `r` (relaxed, default) |
| `aspf=` | SPF alignment mode: `s` (strict) or `r` (relaxed, default) |

DMARC alignment means: the domain in the `From:` header must match (relaxed: same organizational domain; strict: exact) the domain in the SPF `MAIL FROM` or the DKIM `d=`. Without alignment, a phisher could DKIM-sign with their own domain and pass DKIM while sending a `From:` of `ceo@example.com`.

### The four authentication verdicts

A receiver looks at each incoming message and computes:

| Check | Where | Verdict when fail |
|---|---|---|
| SPF | SMTP `MAIL FROM` (the envelope sender) | Softfail/Fail: usually flagged |
| DKIM | Cryptographic signature in header | Fail: usually flagged |
| DMARC | Aligned + (SPF pass OR DKIM pass) | Apply `p=` action |
| FCrDNS | Reverse then forward lookups | Many MTAs reject |

A message that passes SPF or DKIM, with alignment, and is otherwise clean, is fine. A message that fails DMARC with `p=reject` is dropped at SMTP or moved to the spam folder.

### The publish-and-test workflow

The textbook sequence is:

1. Publish `v=spf1` at the apex with `~all` (softfail). Allow up to a week of `none` first to gather reports.
2. Publish DKIM keys for every outbound selector. Sign outbound mail.
3. Publish `v=DMARC1; p=none; rua=...` to start receiving aggregate reports.
4. After a week of clean reports, move DMARC to `p=quarantine; pct=10`, then `pct=100`, then `p=reject` once you are confident.
5. Monitor the aggregate reports. Loosen the policy or fix any legitimate senders you missed.

## Build It

1. Run `code/main.py` to parse a sample SPF record, evaluate it against a candidate sending IP, and check DKIM/DMARC alignment.
2. Author an SPF record at `example.com` with `v=spf1 ip4:198.51.100.0/24 include:_spf.google.com -all`. Verify with `dig TXT example.com`.
3. Generate a DKIM keypair (e.g., `opendkim-genkey -s selector1 -d example.com`) and publish the public key at `selector1._domainkey.example.com`.
4. Author a DMARC TXT at `_dmarc.example.com` and verify with `dig TXT _dmarc.example.com`.
5. Send a test message to a mailbox that reports DMARC (e.g., a Gmail or Yahoo test account) and check the aggregate report.

```python
# Excerpt from code/main.py
def evaluate_spf(ip: str, record: str) -> str:
    """Toy SPF evaluator. Real implementation: see pyspf."""
    if record.startswith("v=spf1") and "ip4:192.0.2.0/24" in record and ip.startswith("192.0.2."):
        return "pass"
    return "fail"
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| SPF evaluator | `evaluate_spf(ip, record)` | `pyspf`, `python-spf` | RFC 7208 |
| DKIM key fetch | `dkim_key(selector, domain)` | `dkimpy`, `opendkim` | RFC 6376 |
| DMARC alignment | `aligned(from_domain, spf_domain, dkim_domain)` | `parsedmarc` | RFC 7489 §3 |
| Policy verdict | `dmarc_verdict(spf, dkim, alignment)` | `authres` | RFC 8601 |
| Report parsing | `parse_aggregate(xml)` | `parsedmarc` | RFC 7489 §7 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A complete TXT record bundle for an outbound domain (apex SPF, DKIM selectors, DMARC).
- A pre-flight check that verifies the four checks against a sample outbound IP and reports a verdict per check.
- A migration plan: `p=none` → `p=quarantine pct=10` → `p=quarantine pct=100` → `p=reject`, with monitoring checkpoints.

Start from [`outputs/prompt-txt-spf-dmarc-mail-auth-records.md`](../outputs/prompt-txt-spf-dmarc-mail-auth-records.md).

## Exercises

1. Publish an SPF record at `example.com` that authorizes exactly two CIDR blocks and uses `~all`. Verify with `dig TXT`.
2. Use `opendkim-genkey` to generate a DKIM keypair and publish the public key as a TXT. Sign a test message and verify with `dkimpy`.
3. Publish a DMARC record with `p=quarantine; rua=mailto:reports@example.com`. Wait 24 hours and inspect an aggregate report.
4. Read RFC 7208 §4.6.4 and confirm the 10-DNS-lookup limit. Simulate it with a chain of `include:` records and `dig` each step.
5. Compute the DMARC verdict for a message with `From: alice@example.com`, `MAIL FROM: bounces@example.org`, DKIM `d=example.com`, and DKIM result `pass`. Does it align?
6. Find a real-world policy at `_dmarc.gmail.com` and at `_dmarc.microsoft.com` and compare the `p=` and `rua=` tags.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TXT record | "a text record" | Generic DNS string container; carries SPF, DKIM, DMARC, site verification, and other policies |
| SPF | "the SPF record" | RFC 7208 TXT at the apex (`v=spf1`) listing authorized senders |
| DKIM | "the DKIM signature" | RFC 6376: per-message cryptographic signature, key published as TXT at `<selector>._domainkey` |
| DMARC | "the DMARC policy" | RFC 7489 TXT at `_dmarc` that aligns SPF/DKIM and decides the action |
| Alignment | "the From: matches" | DMARC requires the auth domain to align with the visible From: domain |
| `~all` | "softfail" | Catch-all in SPF; receiver treats as a soft failure, scores but does not reject |
| `-all` | "hardfail" | SPF: catch-all that hard-fails the check |
| `+all` | "allow all" | SPF: authorize the entire internet. Almost always wrong. |
| Aggregate report | "the DMARC XML" | Daily XML report of all senders seen for the domain |
| `rua` / `ruf` | "report URIs" | DMARC tags pointing at mailboxes that receive aggregate and forensic reports |

## Further Reading

- RFC 1035 §3.3.14 — TXT record format
- RFC 6376 — DomainKeys Identified Mail (DKIM)
- RFC 7208 — Sender Policy Framework (SPF)
- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- RFC 8601 — Authentication-Results header field (the receiver's per-message verdict)
- RFC 6377 — DKIM and SPF in operation
- DMARC specification XML schema: https://datatracker.ietf.org/doc/html/rfc7489#appendix-C
- `opendkim`, `pyspf`, `parsedmarc` — reference implementations
- `dig TXT` reference: querying SPF, DKIM, and DMARC records
