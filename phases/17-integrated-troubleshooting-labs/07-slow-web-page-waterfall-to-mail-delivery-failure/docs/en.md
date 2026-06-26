# Slow Web Page Waterfall to Mail Delivery Failure

> A user reports "the website is slow" — not a single page, but the whole site. The page-load waterfall shows dozens of requests with most of the time spent in "Waiting" (TTFB) rather than "Content Download." The HTML arrives in 50 ms but every image, CSS file, and JavaScript bundle takes 1.5 seconds of TTFB before the first byte. Meanwhile, the mail server reports that outbound mail is being rejected by major recipients with "550 5.7.1 ... does not designate ... as a permitted sender" — a clear DKIM/SPF/DMARC failure. The two symptoms look unrelated, but they share a common cause: the company's authoritative DNS server is broken in a way that produces correct answers for some query types (A, AAAA, MX) and incorrect answers for others (TXT, CNAME). This lesson walks the diagnostic chain from "web page is slow" through the waterfall analysis, then extends to the mail failure that emerges from the same root cause, and shows how a single misconfigured DNS delegation can produce both symptoms. The synthetic trace generator in `code/main.py` models a DNS zone with split records — healthy for A/AAAA/MX, broken for TXT/CNAME — and demonstrates the divergent diagnostic chains for the two application-layer failures.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 09 DNS zone types, Phase 10 HTTP caching, Phase 11 SMTP and DKIM/SPF/DMARC, Lesson 02 of this phase
**Time:** ~130 minutes

## Learning Objectives

- Diagnose "the whole website is slow" by reading a waterfall chart, identifying whether the slowness is in DNS, TCP, TLS, TTFB (server), or content download, and naming the specific layer responsible.
- Distinguish three "everything is slow" failure classes: (a) a slow authoritative DNS server causing all lookups to take 1.5 s, (b) a slow origin server causing all TTFBs to be 1.5 s, (c) a saturated CDN edge node causing all transfers to be slow.
- Apply a four-step diagnostic chain for web slowness (`dig +stats`, browser DevTools waterfall, `curl -w` timing, server-side `top`/`iostat`/application logs) and identify which step first produces decisive evidence.
- Diagnose mail delivery failures from the SMTP response code and the error text, mapping 550/553/554 to specific DKIM, SPF, DMARC, MX, or PTR problems.
- Explain why DKIM, SPF, and DMARC all depend on the DNS zone's TXT and CNAME records, and how a single DNS zone misconfiguration can break mail while leaving web browsing working.
- Construct a synthetic DNS-zone generator (no live DNS queries) that emits a zone with deliberately broken DKIM/SPF/DMARC records, and walk the diagnostic chain for both web and mail failures.

## The Problem

A regional e-commerce company gets two seemingly unrelated reports on the same Monday morning:

1. **Web performance team**: "The site has been slow all weekend. Page-load times have tripled. Waterfall shows 1.5 s TTFB on every request."
2. **Customer service**: "Customers say their order confirmation emails are being bounced. Specifically Gmail and Outlook are rejecting them."

The two teams are in different parts of the company, with different tools, different on-call rotations, and different mental models. They open separate incident tickets. The web team starts checking the CDN, the load balancer, the origin server, and the application. The mail team starts checking the SMTP relay, the DKIM signing, the SPF record, and the DMARC policy.

The actual cause: the company's authoritative DNS server was migrated to a new provider on Friday evening. The migration was tested for A and AAAA records (the records browsers query for hostnames), and those worked. The migration was *not* tested for TXT and CNAME records (the records used for DKIM signing, SPF authorization, DMARC policy, and CDN hostname aliases). The new DNS provider has a different default behavior for these record types: TXT records are returned with a 2-second TTL that triggers a 1.5-second wait at every recursive resolver, and CNAME records for the CDN hostname are not being followed (the recursive resolver returns the CNAME as a "no such name" error).

The web slowness comes from the CNAME issue: every page-load triggers a lookup for `cdn.example.com`, which has a CNAME to `example.cdn.net`. The CNAME lookup returns NXDOMAIN at the recursive resolver (because the new DNS provider is not returning the CNAME chain correctly), the browser falls back to a direct lookup of the apex `example.com`, which also fails, and the browser waits 1.5 seconds before timing out. The slowness is in the DNS layer, not the HTTP or TCP layer.

The mail failure comes from the TXT record issue: DKIM signing requires a TXT record at `default._domainkey.example.com` containing the public key. The TXT lookup is taking 1.5 seconds, and then the record is *empty* (the new DNS provider lost the DKIM key in the migration). The receiving mail server (Gmail) sees that the DKIM signature does not verify, consults the DMARC policy (also a TXT record at `_dmarc.example.com`, also lost in the migration), and rejects the mail with `550 5.7.1 ... does not designate ... as a permitted sender`.

The two failures share a common root cause: the DNS migration was incomplete. The first responder's job is to identify this shared root cause, fix the DNS zone, and verify both web and mail are restored.

## The Concept

### Reading a Waterfall Chart

A browser waterfall chart (in Chrome DevTools, Safari Web Inspector, Firefox Developer Tools, or `curl -w`) shows the timing of each request broken into phases. The phases are:

- **Queue**: The browser has too many connections to the same origin and is waiting for a slot. Modern browsers open 6 connections per origin (HTTP/1.1) or unlimited (HTTP/2, HTTP/3).
- **DNS Lookup**: The browser is resolving the hostname. Typically < 50 ms for a warm cache, 20–200 ms for a cold cache.
- **Initial Connection (TCP)**: The browser is doing the TCP three-way handshake. Typically < 100 ms for nearby servers, 50–300 ms for cross-continental.
- **SSL/TLS Negotiation**: The browser is doing the TLS handshake. Typically 50–200 ms, dominated by the cryptographic operations and the RTT to the server.
- **Request Sent**: The browser is sending the HTTP request. Typically < 1 ms for small requests.
- **Waiting (TTFB, Time To First Byte)**: The browser has sent the request and is waiting for the first byte of the response. This is the server's processing time.
- **Content Download**: The browser is downloading the response. This is `size / bandwidth`.

A healthy waterfall for a static asset on a nearby CDN looks like:

```text
GET /style.css
  Queue:        0 ms
  DNS:          8 ms
  TCP:         12 ms
  TLS:         18 ms
  Request:      0 ms
  Waiting:     35 ms
  Download:     2 ms
  Total:       75 ms
```

A slow page where every request has 1.5 s of "Waiting" (TTFB) looks like:

```text
GET /style.css
  Queue:        0 ms
  DNS:          8 ms
  TCP:         12 ms
  TLS:         18 ms
  Request:      0 ms
  Waiting:   1500 ms      <- server is slow
  Download:     2 ms
  Total:     1540 ms
```

A slow page where every request has 1.5 s of "DNS Lookup" looks like:

```text
GET /style.css
  Queue:        0 ms
  DNS:       1500 ms      <- DNS is slow
  TCP:         12 ms
  TLS:         18 ms
  Request:      0 ms
  Waiting:     35 ms
  Download:     2 ms
  Total:     1567 ms
```

The difference between the two is decisive: high "Waiting" = server issue, high "DNS Lookup" = DNS issue. The first responder should always look at the *phase* of the slowness, not just the total time.

### The `curl -w` Timing Variables

`curl` exposes the same waterfall timing as DevTools, in text form, with the `-w` flag:

| Variable | Meaning |
|----------|---------|
| `time_namelookup` | Time from start until name resolution completed |
| `time_connect` | Time from start until TCP connect completed |
| `time_appconnect` | Time from start until SSL handshake completed |
| `time_pretransfer` | Time from start until just before transfer started |
| `time_redirect` | Time spent on redirects |
| `time_starttransfer` | Time from start until first byte received (TTFB) |
| `time_total` | Total time of the transfer |

A useful one-liner:

```text
$ curl -w '\nDNS:%{time_namelookup} TCP:%{time_connect} TTFB:%{time_starttransfer} Total:%{time_total}\n' \
       -o /dev/null -s https://example.com/
DNS:1.523 TCP:0.012 TTFB:0.057 Total:0.061
```

This says: DNS took 1.5 seconds, TCP took 12 ms, the first byte came back in 57 ms (TTFB), total transfer took 61 ms. The DNS is the bottleneck, not the server.

### The Four-Step Diagnostic Chain for Web Slowness

| # | Command | Healthy output | Problem output | Points to |
|---|---------|----------------|----------------|-----------|
| 1 | `dig +stats <name>` | `Query time: 8 msec` | `Query time: 1500 msec` | Slow authoritative DNS |
| 2 | Browser DevTools waterfall | All phases under 200 ms | One phase dominates (DNS, TCP, TLS, TTFB, Download) | Specific layer |
| 3 | `curl -w` timing | All phases under 200 ms | High DNS, TCP, TTFB, or Download | Specific timing |
| 4 | Server-side `top`, `iostat`, application logs | Low load, normal response times | High CPU, slow DB, slow external API | Server-side cause |

The order matters: `dig +stats` is fast and tells you whether the issue is in DNS. The waterfall is comprehensive but requires a real browser. `curl -w` is the same as the waterfall in text form. Server-side investigation is the last resort because it requires access to the server.

### SMTP Error Code Catalog

SMTP uses 3-digit reply codes, with the first digit indicating the category:

| Code | Meaning |
|------|---------|
| 2xx | Success |
| 3xx | Intermediate success (the server is waiting for more input) |
| 4xx | Transient failure (try again later) |
| 5xx | Permanent failure (do not retry) |

The most important 5xx codes for mail delivery troubleshooting:

| Code | Meaning | Common cause |
|------|---------|--------------|
| 550 5.7.1 | "Relaying denied" or "does not designate ... as a permitted sender" | SPF, DKIM, or DMARC failure |
| 553 5.7.1 | "Sender address rejected" | MAIL FROM address is malformed or blocked |
| 554 5.7.1 | "Message rejected as spam" | Content-based filtering, PTR record missing, or DMARC policy=reject |
| 550 5.1.1 | "User unknown in local mailbox" | RCPT TO address does not exist |
| 554 5.6.1 | "Body rejected" | Content matched a spam rule |
| 452 4.2.2 | "Mailbox full" | Recipient's mailbox is over quota |

The 550 5.7.1 with "does not designate" is the canonical DKIM/SPF/DMARC failure. The text after the code is the key: it tells you which mechanism failed. Common patterns:

- "does not designate <ip> as a permitted sender" → SPF failure
- "signature domain ... is not aligned with ..." → DKIM alignment failure
- "DMARC policy ... rejects message" → DMARC policy=reject and the message failed both SPF and DKIM

### DKIM, SPF, and DMARC: How They Work

The three mechanisms are layered:

**SPF (Sender Policy Framework)**: A TXT record at `<domain>` (e.g., `example.com`) that lists the IP addresses and hostnames authorized to send mail for the domain. The receiving server checks the TXT record, looks up the sending IP, and rejects the mail if the IP is not in the SPF record. The DNS lookup is a single TXT query.

**DKIM (DomainKeys Identified Mail)**: A TXT record at `default._domainkey.<domain>` (e.g., `default._domainkey.example.com`) that contains the public key used to verify the signature. The sending server signs every outgoing message with the corresponding private key. The receiving server queries the TXT record, retrieves the public key, and verifies the signature. The DNS lookup is a TXT query at a non-apex hostname.

**DMARC (Domain-based Message Authentication, Reporting, and Conformance)**: A TXT record at `_dmarc.<domain>` (e.g., `_dmarc.example.com`) that contains the policy: how to handle mail that fails SPF or DKIM (none, quarantine, or reject), and where to send reports. The DNS lookup is a TXT query at a non-apex hostname.

All three are TXT records. All three depend on the DNS zone being correct. A single broken TXT query breaks all three.

### The Shared Root Cause: A Broken DNS Zone

The lesson's central insight: many "unrelated" application failures share a common cause in the DNS zone. The most common DNS-zone misconfigurations that produce application-level failures:

- **Missing or wrong CNAME for a CDN**: The CDN's hostname (e.g., `cdn.example.com`) is a CNAME to a third-party provider (e.g., `example.cdn.net`). If the CNAME is missing or points to the wrong target, every request to the CDN fails or is slow.
- **Missing or wrong TXT for SPF**: The SPF record is missing or has the wrong IP range. Mail from the company's actual sending server is rejected.
- **Missing or wrong TXT for DKIM**: The DKIM public key TXT record is missing or has been replaced. Mail signatures cannot be verified and are rejected.
- **Missing or wrong TXT for DMARC**: The DMARC policy TXT record is missing. Receiving servers fall back to "no policy," which is permissive, but some receivers treat "no policy" as a soft fail.
- **Missing or wrong MX**: The mail exchange records are missing or point to the wrong server. Mail cannot be delivered.
- **Missing or wrong PTR**: The reverse DNS (PTR) record for the sending server is missing or wrong. Many receivers reject mail from servers without valid PTR records.

A single DNS audit, run with `dig` against all the relevant record types, can catch all of these in one pass. The audit should produce:

```text
$ dig +short example.com A          # should return 1-4 IPs
$ dig +short example.com AAAA       # should return 1-4 IPv6 addresses
$ dig +short example.com MX         # should return 1-2 MX records
$ dig +short example.com TXT        # should include "v=spf1 ..."
$ dig +short default._domainkey.example.com TXT  # should include "v=DKIM1 ..."
$ dig +short _dmarc.example.com TXT              # should include "v=DMARC1 ..."
$ dig +short cdn.example.com CNAME               # should include the CDN target
$ dig -x <sending-ip>               # should return the sending server's hostname
```

If any of these are missing or wrong, the application failure it produces is the predictable consequence.

### The "TXT record is slow" Anti-Pattern

A subtle variant of the lesson's central insight: a TXT record can be *correct* but *slow* to resolve. Some DNS providers return TXT records with a very short TTL (1–2 seconds), forcing every recursive resolver to refresh the cache. If the authoritative server is slow or the path to it is slow, every recursive resolver waits 1.5 seconds for the TXT record to be returned. This is invisible in `dig` against the local resolver (which is often warmed), but visible in `dig` against a cold recursive resolver (such as a fresh cloud instance).

The fix: increase the TXT record TTL. A 5-minute or 1-hour TTL is fine for SPF, DKIM, and DMARC records because they change rarely. The TTL is a *cache lifetime* hint, not a *propagation time*; a long TTL is safe if the record is stable.

## Build It

The `code/main.py` in this lesson is a synthetic DNS-zone generator. It models a zone file with the A, AAAA, MX, TXT, CNAME, and PTR records, deliberately breaks the DKIM, SPF, DMARC, and CNAME records, and walks the four-step diagnostic chain for both web and mail failures.

1. **Read** `code/main.py`. Notice the `DnsZone` dataclass (frozen=True for the immutable records), the `FailureMode` enum, the `audit_zone` function that runs all the `dig` queries, and the `simulate_waterfall` and `simulate_smtp` functions that emit the application-layer symptoms.
2. **Run** `python3 code/main.py --mode dns_migration` (or `--mode cname_broken`, `--mode dkim_missing`, `--mode spf_wrong`, `--mode healthy`). You will see the zone file, the audit results, the web waterfall, and the SMTP session for each mode.
3. **Compare** the five modes side by side: `python3 code/main.py --mode all`. The output will show that the same DNS zone misconfiguration produces both web and mail symptoms.
4. **Modify** the `DnsZone` class to add a sixth mode where the DKIM record is present but rotated weekly and the new key has not yet been deployed to the sending MTA. Mail signatures verify against the old key (still in DNS) but the receiver has cached the old DKIM signature, leading to a temporary rejection. Walk through the diagnostic chain and identify which step is *not* decisive for this case.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| Whole site is slow | `dig +stats example.com` | `Query time: 1500 msec` | Slow authoritative DNS |
| Page-load waterfall has 1.5s in DNS | DevTools → Network → timing | `DNS Lookup: 1500 ms` | DNS latency, not server |
| Page-load waterfall has 1.5s in Waiting | DevTools → Network → timing | `Waiting (TTFB): 1500 ms` | Server is slow |
| Page-load waterfall has 1.5s in Download | DevTools → Network → timing | `Content Download: 1500 ms` | Bandwidth or large asset |
| Mail rejected, "does not designate" | `dig +short example.com TXT` | TXT record missing or wrong | SPF misconfiguration |
| Mail rejected, "signature doesn't verify" | `dig +short default._domainkey.example.com TXT` | DKIM TXT missing | DKIM key not published |
| Mail rejected, "DMARC policy" | `dig +short _dmarc.example.com TXT` | DMARC TXT missing | DMARC not published |
| Mail rejected, "user unknown" | `dig +short example.com MX` | MX record wrong | Mail exchange misconfigured |
| Mail rejected, "no PTR" | `dig -x <sending-ip>` | Returns NXDOMAIN | Reverse DNS missing |
| One bad record breaks everything | `dig +short example.com A` | Returns correct IP | Other records still wrong |

## Ship It

The `outputs/prompt-slow-web-page-waterfall-to-mail-delivery-failure.md` file is your deliverable. Author a one-page runbook for "web is slow and mail is bouncing" that contains:

1. The four-step diagnostic chain for web slowness with one-line decision rules.
2. The SMTP error code catalog with one-line "if you see X, the cause is Y" rules for the most common 5xx codes.
3. A reference list of the eight DNS record types that should be in every production zone (A, AAAA, MX, TXT-SPF, TXT-DKIM, TXT-DMARC, CNAME-CDN, PTR) and the `dig` command to audit each.
4. A list of three common false-positive pitfalls: (a) `dig` from a warm cache shows the answer instantly, hiding a slow authoritative server — always run `dig +stats` to see the query time, (b) a CDN can mask a slow origin but cannot mask a slow DNS, (c) a single broken DKIM record can break mail from a specific subdomain but not from the apex — make sure to audit all subdomains that send mail.

## Exercises

1. **Waterfall reading**: A page-load waterfall shows 30 requests, each with `DNS Lookup: 1500 ms` and other phases normal. What is the most likely cause? What single `dig` command would confirm?
2. **`curl -w` reading**: `time_namelookup=1.5, time_connect=0.01, time_starttransfer=0.05, time_total=0.06`. Which phase is the bottleneck?
3. **SMTP error mapping**: An outgoing mail is rejected with `550 5.7.1 ... does not designate 198.51.100.10 as a permitted sender`. Which mechanism failed? What `dig` command confirms?
4. **DKIM verification**: A mail is rejected with `550 5.7.1 ... signature verification failed`. The DKIM TXT record at `default._domainkey.example.com` is present and looks correct. What is the next thing to check?
5. **PTR record**: A mail server is rejected with `554 5.7.1 ... PTR record not found`. What command would diagnose? What is the fix?
6. **Shared root cause**: A company has web slowness (1.5s DNS) AND mail failures (DKIM/SPF/DMARC). What is the most likely shared root cause? How would you verify?
7. **Compare with lesson 02**: Lesson 02's "DNS works but HTTP fails" chain is for *application* failures from *single-record* DNS issues. This lesson's chain is for *layered* failures from *multi-record* DNS issues. How does the audit methodology differ?

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| Waterfall | A visualization | A chart of network request timing broken into phases (DNS, TCP, TLS, TTFB, Download) |
| TTFB | An acronym | Time To First Byte — the time from the request being sent to the first byte of the response |
| DKIM | An acronym | DomainKeys Identified Mail — a signature scheme that lets receivers verify mail authenticity |
| SPF | An acronym | Sender Policy Framework — a TXT record listing IPs authorized to send for a domain |
| DMARC | An acronym | Domain-based Message Authentication, Reporting, and Conformance — the policy for handling SPF/DKIM failures |
| MX | A record type | Mail Exchange — the DNS record that points to the mail server for a domain |
| PTR | A record type | Pointer — the reverse DNS record that maps an IP to a hostname |
| CNAME | A record type | Canonical Name — an alias that points one name to another |
| TXT | A record type | Text — a general-purpose record used for SPF, DKIM, DMARC, site verification, and many other purposes |
| 550 5.7.1 | An SMTP code | "Mail refused — does not designate ... as a permitted sender" — the canonical DKIM/SPF/DMARC failure |

## Further Reading

- **RFC 6376** — *DomainKeys Identified Mail (DKIM) Signatures*. The DKIM specification, including the DNS query mechanism.
- **RFC 7208** — *Sender Policy Framework (SPF) for Authorizing Use of Domains in Email, Version 1*. The SPF specification, including the DNS TXT record format.
- **RFC 7489** — *Domain-based Message Authentication, Reporting, and Conformance (DMARC)*. The DMARC specification, including the policy record format.
- **RFC 5321** — *Simple Mail Transfer Protocol*. The SMTP specification, including the reply codes.
- **RFC 1035** — *Domain Names — Implementation and Specification*. The DNS specification, including the record types and TTL semantics.
- **W3C Navigation Timing API** — the spec for the browser's `performance.timing` object that DevTools uses to render the waterfall.
- **curl `-w` format documentation** — `man curl` and the curl-format.txt file in the curl source distribution.
- **Google's Email Sender Guidelines** — https://support.google.com/mail/answer/81175. The receiver-side guidance for SPF, DKIM, and DMARC.
- **MXToolbox** — https://mxtoolbox.com/. A free online tool for DNS audits and mail deliverability testing.
- **phases/09-tcp-and-udp** — DNS fundamentals, including the resolver and TTL behavior.
- **phases/11-application-protocols** — SMTP, IMAP, POP3, and the mail delivery chain.
- **phases/17-integrated-troubleshooting-labs/02-dns-works-but-http-fails** — the parent lesson whose diagnostic chain this lesson extends for layered DNS failures.
- **phases/17-integrated-troubleshooting-labs/20-dnssec-ds-dnskey-chain-rollover-break** — the DNSSEC-related DNS failures, a related failure class.
