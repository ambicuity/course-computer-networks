# DNS Zones, Primaries, and Secondary Replication

> A DNS zone is the unit of administrative delegation: one or more contiguous branches of the namespace whose records are served by a common set of authoritative name servers. Every zone has exactly one **primary** (master) that loads its data from a zone file on disk and signs it (if DNSSEC is in use), and one or more **secondaries** (slaves) that pull the zone via **AXFR** (full zone transfer, RFC 5936) or **IXFR** (incremental zone transfer, RFC 1995) over TCP/53. The primary notifies secondaries of changes with a NOTIFY message (RFC 1996) — a single SOA-typed query that says "my serial number changed, please come and AXFR/IXFR". Replication timing is governed by the SOA record's five timers: REFRESH, RETRY, EXPIRE, MINIMUM (the last doubles as the negative-cache TTL). Operators must keep zone serial numbers strictly increasing across edits because secondaries compare incoming serials against their own and treat any smaller value as stale or as an attack. A zone whose primary is unreachable for longer than EXPIRE (commonly 1-4 weeks) is dropped from the world — secondaries stop answering authoritatively for it until contact is restored.

**Type:** Learn
**Languages:** Python, shell
**Prerequisites:** Phase 12 lessons on DNS records and recursion, plus familiarity with `dig` and `named-checkzone`
**Time:** ~75 minutes

## Learning Objectives

- Distinguish a **zone** (administrative unit) from a **domain** (a node in the namespace) and explain why the boundaries often do not align.
- Read a zone file: `$ORIGIN`, `$TTL`, SOA record (with its five timers), NS records, and glue A/AAAA records.
- Trace an AXFR (RFC 5936) and IXFR (RFC 1995) zone transfer over TCP/53, noting how NOTIFY (RFC 1996) triggers them.
- Compute the timing of the SOA refresh cycle (REFRESH, RETRY, EXPIRE, MINIMUM) and predict when a secondary will expire its copy of the zone.
- Explain why zone serial numbers must be monotonically increasing, and what happens if an edit accidentally rolls a serial backwards.
- Configure a primary/secondary pair (BIND-style) and watch a NOTIFY → IXFR sequence with `dig` and `tcpdump`.

## The Problem

You run a small company and your boss says: "We need our own DNS, with a backup somewhere in case the datacenter floods." You have been using the registrar's free DNS service and you know nothing about zone files. The first question is the administrative one: which part of the namespace do *you* own? The second is the operational one: how does the secondary know when to pull an update? The third is the safety one: what happens if the secondary cannot reach the primary for a month — does the secondary keep answering until the primary comes back, or does it drop the zone?

The trap is conflating the primary with the only authoritative server. A zone can have many authoritative servers, all answering with the AA flag set, even though only one of them — the primary — has the canonical zone file. The secondaries are full peers in terms of answering queries, but they are followers in terms of getting updates. The protocol that keeps them in sync is the AXFR/IXFR/NOTIFY family; the rest of DNS just sees them as "another authoritative server for this zone".

## The Concept

### Zones vs domains

A **domain** is a node in the namespace tree. A **zone** is the part of the tree that one organization administers and one set of name servers serves. Most zones are simple — `example.com` is a zone that contains `example.com` and all its subdomains that the owner has not delegated away. But the textbook figure shows that `cs.washington.edu` is its own zone, separate from `washington.edu`, because the CS department wants to run its own name servers. The boundary between zones is wherever an operator chose to draw it; the cut is signalled by NS records at the parent zone that point to the child zone's authoritative servers.

```
example.com          (zone: example.com includes www, mail, ftp, ...)
   |
   +-- corp.example.com  (zone: a delegated sub-zone)
   |      |
   |      +-- its own NS records pointing to its own servers
   |
   +-- partner.example.com (still in zone example.com if not delegated)
```

### Inside a zone file

A zone file is plain text (RFC 1035 §5; BIND-style `$DIRECTIVE` extensions are de facto standard). Two directives set the file's frame:

- `$ORIGIN example.com.` — the default suffix for any relative name in the file.
- `$TTL 86400` — the default TTL when a record omits one.

The first non-comment record is always the SOA, which carries the five timing parameters that govern the secondary's refresh cycle:

```
@  IN  SOA  ns1.example.com. admin.example.com. (
        2026062501   ; serial (YYYYMMDDnn)
        3600         ; REFRESH  -- seconds until secondary checks for updates
        1800         ; RETRY    -- seconds between retries if REFRESH query fails
        1209600      ; EXPIRE   -- seconds after which the secondary drops the zone
        300 )        ; MINIMUM  -- negative-cache TTL (RFC 2308)
```

Then come the NS records (one per authoritative server), the MX records, and the A/AAAA/CNAME/TXT records. Glue records — A/AAAA records for NS hostnames that live inside the same zone — are mandatory to break the resolution loop.

### AXFR: full zone transfer (RFC 5936)

AXFR was specified in RFC 1035 and refined by RFC 5936. The protocol is:

1. The secondary opens a TCP/53 connection to the primary (RFC 5936 mandates TCP, not UDP, because the zone will not fit in one datagram).
2. The secondary sends a query `QTYPE=AXFR`, QCLASS=IN, RD=0 (it does not want recursion for an AXFR — it wants the zone).
3. The primary responds with the SOA, then every record in the zone in order, then a final SOA marking the end of the transfer.
4. The secondary replaces its copy of the zone with what it received.

AXFR is straightforward but inefficient for big zones: a zone with 100,000 records gets fully transferred even if just one changed. Operators limit AXFR with allow-transfer ACLs so unauthorized hosts cannot dump the entire zone.

### IXFR: incremental zone transfer (RFC 1995)

IXFR is what most modern secondaries use. After an AXFR establishes a baseline, the secondary tracks its own serial number. When it sees a new SOA serial (or gets a NOTIFY), it sends `QTYPE=IXFR` with the current serial, and the primary replies with just the SOA change and the diff: deleted records followed by added records, in zone-order. If the diff is larger than the full zone, the primary falls back to AXFR. The serial number discipline is critical: it must be strictly increasing across edits.

### NOTIFY: change push (RFC 1996)

NOTIFY is a tiny but important message. The primary, immediately after the zone file is updated and reloaded, sends a NOTIFY (a standard query with QTYPE=SOA, QCLASS=NOTIFY=1 by some implementations but really still IN) to every server listed in the zone's NS set. The recipient responds with its current SOA, the primary compares the serial numbers, and if the secondary's serial is lower, the secondary opens an IXFR (or AXFR) connection.

In practice NOTIFY is a "wake up and check" rather than "I am sending you the zone". It cuts the refresh delay from REFRESH (often 1 hour) down to a few seconds.

### The five SOA timers

The textbook numbers in the SOA are not arbitrary:

| Field | Typical | Meaning |
|---|---|---|
| Serial | `2026062501` | Zone version; strictly increasing; YYYYMMDDnn is the common format |
| REFRESH | 3600 s (1 h) | How often the secondary checks the primary's SOA for a new serial |
| RETRY | 1800 s (30 min) | How often to retry after a failed REFRESH check |
| EXPIRE | 1209600 s (14 d) | How long a secondary will keep answering authoritatively without a successful refresh |
| MINIMUM | 300 s (5 min) | Negative-cache TTL for NXDOMAIN/NODATA responses (RFC 2308) |

A second-ary whose primary is unreachable for longer than EXPIRE stops answering authoritatively for the zone — `dig @secondary example.com SOA` will return a SERVFAIL or refuse until the secondary can re-transfer. The exact behavior is implementation-defined; BIND drops the zone, Unbound marks it as "expired" and refuses queries.

### The chicken-and-egg of glue

A zone file for `example.com` that lists `ns1.example.com` as an NS must also include the A record for `ns1.example.com`. Without that glue, a resolver trying to reach the zone would have to ask `example.com` for the address of `ns1.example.com`, but to do that it must already know how to reach `example.com`. RFC 1034 §3.6 codifies the requirement that this be solved by publishing the A/AAAA inline.

### Why serial numbers must be monotonic

RFC 1982 serial number arithmetic (which wraps modulo 2^32) lets a serial wrap around back to a smaller value and still look "new" if the difference is small. The simple operational rule is: never decrease the serial number, even across rollback. If you change the serial from `2026062501` to `2026062502`, then revert the edit but write the zone file with serial `2026062501`, the secondaries will refuse the rollback or treat it as an outdated copy. The fix is to bump the serial to `2026062503` even when reverting content.

## Build It

1. Run `code/main.py` to load a small zone file and print the parsed SOA timers, the NS set, and a simulated IXFR diff.
2. Author a zone file at `zone/db.example.com` with the example structure from this lesson; check it with `named-checkzone example.com zone/db.example.com`.
3. Start a BIND instance (or use `python3 -m dnslib` if you have it) and `dig @primary example.com AXFR` to see the full transfer; then `dig @primary example.com IXFR=2026062501` to see the diff.
4. Watch NOTIFY: enable query logging on the secondary, edit the primary's zone file and `rndc reload`, then look for the NOTIFY message in the secondary's log.
5. Build the EXPIRE timing table for the four timers above using `code/main.py`'s `next_refresh_windows` function.

```python
# Excerpt from code/main.py
def refresh_schedule(serial: str, refresh: int, retry: int, expire: int) -> dict:
    return {
        "current_serial": serial,
        "next_refresh_in_s": refresh,
        "retry_interval_s": retry,
        "expire_after_s": expire,
    }
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Zone-file parser | `parse_zone(text)` | `named-checkzone`, `dns-zone-parser` | RFC 1035 §5 |
| AXFR framing | `axfr_stream(zone)` | BIND `allow-transfer` | RFC 5936 |
| IXFR diff | `ixfr_diff(old_zone, new_zone)` | BIND, NSD, Knot | RFC 1995 |
| NOTIFY | `send_notify(soa)` | `rndc notify` | RFC 1996 |
| Serial arithmetic | `compare_serials(a, b)` | `dns.soa` libraries | RFC 1982 |
| SOA timers | `refresh_schedule(...)` | `dig +nsid` | RFC 1035 §3.3.13 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `zone/db.example.com` template with the SOA, NS, MX, A, AAAA, TXT, and glue records needed for a delegation.
- An operational runbook covering: rotate serial after every edit, never roll back to a smaller serial, monitor `EXPIRE` with a calendar reminder, and restrict AXFR with allow-transfer.
- A small `code/main.py` extension that emits an IXFR diff (deleted-then-added record sets) given two versions of a zone.

Start from [`outputs/prompt-zones-primary-and-secondary-replication.md`](../outputs/prompt-zones-primary-and-secondary-replication.md).

## Exercises

1. Author a zone file for `example.com` with one NS, one MX, one A for `www`, and glue A for the NS host. Validate with `named-checkzone`.
2. Increment the serial number from `2026062501` to `2026062502`, reload the primary, and watch the secondary's log: it should see NOTIFY then IXFR.
3. Block the primary with `iptables` on TCP/53, wait until REFRESH + RETRY fires, and confirm the secondary retries on the schedule defined by the SOA.
4. Compute the maximum outage the secondary can survive before EXPIRE: with REFRESH=3600, RETRY=1800, EXPIRE=1209600, how many failed refresh cycles is that?
5. Force a serial-number rollback in the primary (write a smaller serial), reload, and observe the secondary's behaviour: does it accept the smaller serial, ignore it, or trigger an emergency AXFR?
6. Add a DS record for DNSSEC and watch the secondary pull the corresponding DNSKEY/RRSIG records via IXFR if your tooling supports it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Zone | "the part of DNS I manage" | Contiguous subtree served by one set of authoritative name servers |
| Primary (master) | "the main DNS server" | Loads the zone from a file (or dynamic update) and notifies secondaries |
| Secondary (slave) | "the backup DNS server" | Pulls the zone via AXFR/IXFR from the primary; answers authoritatively |
| AXFR | "zone transfer" | RFC 5936: full transfer of every record over TCP/53 |
| IXFR | "incremental transfer" | RFC 1995: serial-number-keyed diff of changes since the last transfer |
| NOTIFY | "push" | RFC 1996: a tiny SOA query telling secondaries "go check, my serial changed" |
| SOA | "the zone header record" | Carries the five timers + the serial number |
| REFRESH / RETRY / EXPIRE / MINIMUM | "those numbers in the SOA" | Refresh cycle, retry interval, hard expiry, and negative-cache TTL |
| Serial number | "the version" | Strictly increasing zone version; bumps on every edit |
| Glue | "the A record for the NS host" | A/AAAA published in the parent zone for an in-zone NS hostname |

## Further Reading

- RFC 1035 §5 — Zone file format (master file)
- RFC 1034 §3.6 — Glue records and the chicken-and-egg problem
- RFC 5936 — DNS Zone Transfer Protocol (AXFR)
- RFC 1995 — Incremental Zone Transfer (IXFR)
- RFC 1996 — DNS NOTIFY (a mechanism for master/slave coordination)
- RFC 1982 — Serial Number Arithmetic
- RFC 2308 — Negative Caching of DNS Queries (SOA MINIMUM)
- `named-checkzone(8)` — BIND zone-file validator
- `dig` reference: `AXFR`, `IXFR=<serial>`, `+nsid`, `+multiline`
