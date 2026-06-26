# MX Records and MTA Relaying with DNS

> When an MTA has a message destined for `bob@ee.uwa.edu.au`, it cannot connect to the bare domain — it must discover which hosts are willing to accept mail for that domain. The **MX (Mail Exchange) record** (RFC 1035 §3.3.9, augmented by RFC 7505) is the DNS resource record that lists those hosts, each with a 16-bit **preference** value. Lower preference means higher priority: an MTA tries the lowest-numbered MX first, falls back to higher-numbered ones if it is unreachable, and only uses the implicit `A`/`AAAA` fallback (RFC 5321 §5.1) if the domain has no MX records at all. Each MX target also needs an A or AAAA record — usually carried as **glue** in the additional section of the MX response — so the resolver does not have to look it up recursively. The combination of MX priority, glue, and the implicit A-record fallback is the contract between DNS and SMTP: DNS tells the MTA "try these hosts in this order"; the MTA tries them, opens a TCP connection to port 25, and runs SMTP.

**Type:** Learn
**Languages:** Python, shell
**Prerequisites:** Phase 12 lessons on DNS records and zones
**Time:** ~75 minutes

## Learning Objectives

- Read an MX record set and rank its targets by preference.
- Resolve the MX targets to IPs using A/AAAA glue and explain why glue matters for mail delivery latency.
- Trace the MTA's behavior when an MX target is unreachable (retry, fall back to next MX, fall back to implicit A).
- Distinguish MX preference from MX load balancing and understand how the MTA picks one target per message.
- Author a primary MX with a backup MX at a higher preference, and verify it with `dig MX example.com`.
- Recognize the security implications: an MX redirector is an open relay risk; SPF/DKIM/DMARC also matter for inbound mail.

## The Problem

You want to receive mail for `example.com`. You register the domain, point the NS records at your DNS provider, but mail still bounces with `Host or domain name not found`. You check `dig example.com MX` and see nothing. The MTAs around the world are trying to look up `example.com` in DNS and finding no MX — they have no idea which host to deliver to. You publish an MX record pointing at `mail.example.com` with priority 10. Mail starts arriving.

The trap is treating MX records as decoration. They are the routing layer for mail. Without them, mail does not flow. With the wrong preference, mail flows to the wrong host. With the wrong glue, every MX lookup pays an extra round trip to resolve the A record. With no backup MX, a single server outage loses mail.

## The Concept

### The MX record format (RFC 1035 §3.3.9)

```
example.com.  IN  MX  10 mail1.example.com.
example.com.  IN  MX  20 mail2.example.com.
example.com.  IN  MX  30 mail3.example.com.
```

The fields are:

| Field | Meaning |
|---|---|
| Name | The domain the mail is for (left side of the `@`) |
| TTL | Standard cache lifetime |
| Class | `IN` (Internet) |
| Type | `MX` |
| Preference | 16-bit unsigned integer (0..65535); lower = higher priority |
| Target | The hostname that accepts mail (must have an A or AAAA record) |

RFC 974 originally specified MX semantics; RFC 5321 §5.1 codifies the implicit-A-record fallback used when no MX exists. RFC 7505 (Null MX) later added the explicit `MX 0 .` form to signal "this domain receives no mail" without forcing the MTA to try the implicit A record.

### Preference ordering and selection

A receiving MTA sorts all MX records for the destination domain by preference (ascending) and tries them in order. It will pick the lowest-preference host that is reachable, but the exact algorithm is implementation-specific:

- **Postfix / Sendmail / Exim**: try the lowest-preference MX; if unreachable, try the next; if all unreachable, queue and retry later.
- **Some load-balancers**: round-robin among the lowest-preference MX set.

Multiple MX records with the *same* preference are a common pattern for active-active load distribution. RFC 5321 §5.1.3 says they are equivalent in priority and the sender may pick any.

### The implicit A-record fallback

If a domain has no MX records at all (or `MX 0 .`), RFC 5321 §5.1 says the MTA should treat the domain's own A or AAAA record as an implicit MX with the same preference. So `dig example.com A` returning `192.0.2.10` is enough — the MTA will try `192.0.2.10` on port 25. This is convenient for tiny deployments (a single server that is also its own mail server) but loses all the redundancy and priority logic that MX provides.

### Glue and the resolution round trip

When the resolver returns an MX set, it should also return the A records for the MX hostnames in the **additional** section (RFC 1034 §3.6). Without glue, the resolver has to issue a second query to resolve `mail.example.com` to an IP, and that second query may itself need to walk the namespace. With glue, the entire chain — `example.com MX mail.example.com A 192.0.2.10` — arrives in one UDP packet. Every major TLD operator and zone operator publishes glue for exactly this reason.

### A worked MX query

```
$ dig MX example.com

;; ANSWER SECTION:
example.com.   3600  IN  MX  10  mail1.example.com.
example.com.   3600  IN  MX  20  mail2.example.com.

;; ADDITIONAL SECTION:
mail1.example.com.  3600  IN  A  192.0.2.10
mail2.example.com.  3600  IN  A  192.0.2.20

;; Query time: 32 msec
;; SERVER: 127.0.0.1#53(...)
```

The additional section is critical. With one UDP datagram the MTA knows both `mail1.example.com` and `mail1.example.com`'s IP, and the same for `mail2`.

### The implicit null MX (RFC 7505)

`MX 0 .` means "this domain does not accept mail". The trailing dot is the root of DNS; it is syntactically valid but cannot resolve to any A record, so the MTA gives up immediately. Useful for parked domains, brand-protection domains, and any domain you want to explicitly mark as non-mail-receiving.

### Backup MX patterns

A common deployment has:

```
example.com.  IN  MX  10 mail1.us.example.com.
example.com.  IN  MX  20 mail2.eu.example.com.
example.com.  IN  MX  30 backup.example.net.
```

When `mail1` is up, all mail goes there. When `mail1` is unreachable, the MTA falls back to `mail2`. When both are down, mail queues at `backup.example.net` (run by a third party) until a primary comes back. The backup MX must accept and queue mail for the primary domain even though it is not authoritative; that is the classic **secondary MX** or **backup MX** role.

### The security model around MX

Modern MX targets must:

- Run SMTP with `STARTTLS` (RFC 3207) for transport confidentiality.
- Publish valid reverse DNS (PTR) records for their IPs (RFC 5321 §5.1 SHOULD).
- Have valid forward-confirmed reverse DNS (FCrDNS).
- Apply SPF, DKIM, and DMARC checks on inbound mail.
- Optionally publish **MTA-STS** (RFC 8461) and **TLSRPT** (RFC 8460) for TLS policy enforcement and reporting.

A backup MX that stores mail without scanning for spam or malware becomes a security hole: spammers use it as a free relay. Modern backup MX services either scan mail on receipt or require the primary to pull it via authenticated SMTP.

## Build It

1. Run `code/main.py` to load a sample zone, rank MX records by preference, and resolve targets to IPs (with glue).
2. Author a zone file with primary and backup MX records, validate with `named-checkzone`.
3. Query your zone with `dig MX example.com` and confirm the preference order matches your intent.
4. Add `MX 0 .` (null MX) to a parked domain and observe how receiving MTAs handle it.
5. Use `tcping` or `nc -vz mail.example.com 25` to test SMTP reachability of each MX target.
6. Trace an actual SMTP delivery with `tcpdump -w mx.pcap tcp port 25` while sending a test message.

```python
# Excerpt from code/main.py
def rank_mx(records: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return sorted(records, key=lambda r: r[0])
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| MX ranker | `rank_mx(records)` | postfix `transport` table | RFC 5321 §5.1 |
| Glue-aware resolver | `resolve_mx(name, records, glue)` | `dnspython` | RFC 1034 §3.6 |
| Implicit-A fallback | `mx_or_a(name, mx, a)` | postfix `mydestination` | RFC 5321 §5.1 |
| Null MX | `null_mx(records)` | postfix `relay_domains` | RFC 7505 |
| SMTP reachability test | `probe_port_25(host)` | `tcping`, `nc` | RFC 5321 |
| Backup MX test | `simulate_fallback(mx_set)` | (manual) | RFC 974 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `db.example.com` template with a primary MX (preference 10) and a backup MX (preference 30), plus the matching A glue.
- An operational runbook for handling mail during an MX-target outage: which fallback to use, what to tell users, when to expect queue backlog.
- A test harness that simulates the MTA's selection logic against a configurable MX set.

Start from [`outputs/prompt-mx-records-and-mta-relaying.md`](../outputs/prompt-mx-records-and-mta-relaying.md).

## Exercises

1. Run `dig MX gmail.com` and rank the returned records by preference. Note the count of distinct MX hosts.
2. Add an `MX 0 .` (null MX) record to a domain and verify with a second `dig` that it appears with preference 0 and target `.`.
3. Run `dig MX example.com +trace` and identify the TLD server that returned the MX delegation.
4. Capture the MX query in `tcpdump -w mx.pcap udp port 53` and identify whether the answer included the additional-section glue.
5. Simulate a primary-MX outage: in a test environment, block traffic to `mail1.example.com:25` and confirm mail queues for the backup MX.
6. Author a zone with one primary MX (preference 10) and one backup MX (preference 30) and verify the order with `dig MX example.com`.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| MX record | "the mail record" | RFC 1035 §3.3.9: DNS RR listing mail-accepting hosts with priority |
| Preference | "the priority number" | 16-bit field on MX; lower = higher priority; same number = load-balancing pool |
| Glue | "the A record for the MX host" | A/AAAA in the additional section of an MX response |
| Implicit A fallback | "no MX means use the A record" | RFC 5321 §5.1: when a domain has no MX, treat the A as an implicit MX |
| Null MX | "MX 0 dot" | RFC 7505: explicit "this domain does not accept mail" |
| Backup MX | "the secondary mail server" | Higher-preference MX that queues mail when the primary is down |
| MX target | "the mail server hostname" | The right-hand side of an MX record; must have A/AAAA glue |
| Fallback chain | "tries in order" | MTA tries lowest-preference MX, then next, then implicit A |
| Round-robin | "load balancing" | Multiple MX records with the same preference; MTA picks one |
| FCrDNS for MX | "reverse DNS for the mail server" | The MX target's IP must have a PTR record resolving back to its name |

## Further Reading

- RFC 974 — MX Records (original specification)
- RFC 1035 §3.3.9 — MX record format
- RFC 5321 §5.1 — Domain specification and implicit-A-record fallback
- RFC 7505 — A Null MX (MX 0 .) Record for Domains That Do Not Accept Mail
- RFC 8461 — SMTP MTA Strict Transport Security (MTA-STS)
- RFC 8460 — SMTP TLS Reporting (TLSRPT)
- RFC 6376 — DKIM (for inbound verification)
- RFC 7208 — SPF (for inbound verification)
- RFC 7489 — DMARC (for inbound policy)
- `dig MX` reference — querying and tracing MX records
- `named-checkzone` reference — validating a zone file with MX records
