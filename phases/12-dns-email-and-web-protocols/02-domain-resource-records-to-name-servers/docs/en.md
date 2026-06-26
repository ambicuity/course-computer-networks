# Domain Resource Records and Name Servers

> DNS stores its data as **resource records (RRs)** — five-tuples of (Name, TTL, Class, Type, Value) defined in RFC 1035 and clarified by RFC 2181. The principal types are **A** (32-bit IPv4), **AAAA** (128-bit IPv6), **MX** (mail exchange with priority), **NS** (authoritative name server), **CNAME** (canonical-name alias), **PTR** (reverse-lookup pointer), **SRV** (service locator), **SPF** (sender policy), and **TXT** (free-form text). The Internet's namespace is partitioned into **non-overlapping zones**, each served by a **primary name server** (loaded from disk) plus one or more **secondary name servers** (zone transfers via AXFR/IXFR, RFC 5936). Recursion is delegated to resolvers, while each server returns the **best partial answer it has**, leaving the resolver to do iterative lookups. Caching is bounded by the TTL field; a typical stable A record is cached for 86400 seconds (one day). Thirteen logical root servers — `a.root-servers.net` through `m.root-servers.net` — are mirrored at hundreds of anycast sites worldwide so that the entire Internet can locate TLDs.

**Type:** Build
**Languages:** dig, nslookup, Python (RFC 1035 wire format)
**Prerequisites:** Phase 12 Lesson 01 (DNS name space)
**Time:** ~120 minutes

## Learning Objectives

- Decode the five fields of a DNS resource record (Name, TTL, Class, Type, Value) and explain why order is not significant in the zone file.
- Distinguish between the eight principal RR types (SOA, A, AAAA, MX, NS, CNAME, PTR, TXT) and produce a real zone file containing all of them.
- Calculate MX preference and explain how a mail transfer agent walks an MX list.
- Trace a name resolution from a stub resolver through a recursive resolver to the root, TLD, and authoritative servers.
- Articulate the role of TTL in cache coherence and the trade-off between low TTL (fast updates, more queries) and high TTL (eventual consistency, less load).

## The Problem

A resolver is asked to translate `robot.cs.washington.edu` into `128.208.3.88`. Somewhere — distributed across millions of machines — a small tuple holds the answer. If every query had to ask one central server, the server would melt. If every server had a complete copy, every update would have to propagate instantly to millions of replicas. DNS reconciles both extremes with a tiny, fixed-shape record and a clear delegation model. You need to understand the record format and the zone hierarchy that distributes authority for those records.

## The Concept

### The five-tuple that is the DNS database

Every record is five ASCII text fields (or the same fields packed into 32-bit-aligned binary on the wire per RFC 1035 Section 3.2.1):

```
Domain name  Time to live  Class  Type  Value
```

| Field | Meaning | Example |
|-------|---------|---------|
| Domain name | Primary search key; the node this record belongs to | `cs.vu.nl.` |
| TTL | How long (seconds) downstream resolvers may cache the record | `86400` |
| Class | Protocol family; `IN` for Internet, `CH` for Chaos, `HS` for Hesiod | `IN` |
| Type | What the Value field encodes (A, NS, MX, ...) | `MX` |
| Value | The data itself; its meaning depends on Type | `10 zephyr.cs.vu.nl.` |

The order of records in a zone file is **not significant**. A resolver looks up records by (Name, Type, Class); the database is essentially a small key-value store with TTLs and CNAME indirection.

### SOA — Start of Authority

The SOA record marks the apex of a zone and carries the parameters every secondary server needs to validate AXFR zone transfers. RFC 2308 defines the modern minimum format:

```text
$ORIGIN cs.vu.nl.
@  86400  IN  SOA  star.cs.vu.nl. hostmaster.cs.vu.nl. (
       2024010101  ; serial — increment on every change (yyyymmddnn)
       7200        ; refresh — seconds before secondary rechecks
       7200        ; retry  — wait after failed refresh
       2419200     ; expire — secondary stops answering after this
       86400 )     ; minimum — TTL for negative answers (NXDOMAIN)
```

The `hostmaster` address uses a dot instead of `@` because the SOA record predates the `@` shortcut. A secondary server with a serial number **lower** than its copy of the zone will retry the refresh; on **equal** numbers it does nothing. RFC 1982 serial-number arithmetic handles wrap-around at 2^32.

### A and AAAA — Address records

The most common query. An A record holds a 32-bit IPv4 address, AAAA ("quad-A") holds a 128-bit IPv6 address. A single host can have **multiple A records** for round-robin load distribution or because it has multiple network interfaces:

```text
flits.cs.vu.nl.   86400  IN  A     130.37.16.112
flits.cs.vu.nl.   86400  IN  A     192.31.231.165
flits.cs.vu.nl.   86400  IN  AAAA  2001:610:108:4015::112
```

When a resolver receives multiple A records, it returns **all of them** to the caller, and the application (typically a browser or operating system) decides how to use them — usually the first one for the first connection, with the rest as fallback.

### NS — Name server records

NS records publish the **authoritative servers** for a zone. They appear in two places:

1. In the **delegation records** returned by the parent zone (e.g., `.com` returns NS records pointing at `a.gtld-servers.net` for `example.com`).
2. Inside the zone itself, listing the servers that have authority for this zone.

```text
cs.vu.nl.        86400  IN  NS  star.cs.vu.nl.
cs.vu.nl.        86400  IN  NS  ns2.surfnet.nl.   ; external secondary
```

A zone must have at least one NS record. Best practice is **two NS records on independent networks** so that an outage of one site does not black-hole the zone.

### MX — Mail exchange

MX records tell the world where to deliver SMTP mail for a domain. The format is `preference host`:

```text
cs.vu.nl.   86400  IN  MX  10  zephyr.cs.vu.nl.   ; try first
cs.vu.nl.   86400  IN  MX  20  top.cs.vu.nl.      ; backup
cs.vu.nl.   86400  IN  MX  30  rowboat.cs.vu.nl.  ; tertiary
```

Lower preference numbers are tried first. If the highest-priority server is unreachable, the sender waits according to its retry schedule before trying the next. The MX target **must not be a CNAME** (RFC 974) — it must be the A or AAAA of a host willing to accept SMTP on port 25.

### CNAME and PTR — aliases and reverse lookups

A **CNAME** is a macro: any query for the alias name is rewritten to the canonical name. RFC 1034 Section 3.6.2 forbids CNAMEs at the zone apex and forbids other records at a CNAME name:

```text
www.cs.vu.nl.   86400  IN  CNAME  star.cs.vu.nl.
ftp.cs.vu.nl.   86400  IN  CNAME  zephyr.cs.vu.nl.
```

A **PTR** record is the inverse direction: IP address → name. It lives under the special reverse domains `in-addr.arpa.` (IPv4, RFC 1035) and `ip6.arpa.` (IPv6, RFC 3596):

```text
112.16.37.130.in-addr.arpa.   86400  IN  PTR  flits.cs.vu.nl.
```

### SRV, SPF, TXT — service discovery and policy

**SRV** (RFC 2782) generalizes the MX idea: locate a host that provides a specific service in a domain.

```text
_http._tcp.example.com.  86400  IN  SRV  10 5 80 www.example.com.
                                          priority weight port target
```

**TXT** records are free-form text. Originally for arbitrary human notes, they now carry machine-readable policy: SPF (RFC 7208), DKIM (RFC 6376), DMARC (RFC 7489), site-verification tokens, and DNS-based service-discovery hints (RFC 6763).

```text
cs.vu.nl.   86400  IN  TXT  "v=spf1 ip4:130.37.0.0/16 -all"
```

### Zones, primaries, and secondaries

A **zone** is a contiguous, non-overlapping slice of the DNS tree that has been delegated as a unit. The DNS administrator of the parent decides where the cuts go. For example, `cs.washington.edu` may be a separate zone from `eng.washington.edu` because the CS department runs its own name server while the English department does not.

Each zone has:

- **One primary (master) server** — loads the zone from a local disk file. Changes are made here.
- **Zero or more secondary (slave) servers** — pull copies of the zone via AXFR (RFC 5936) or IXFR (incremental zone transfer, RFC 1995). They answer queries but cannot be edited directly.

The serial number in the SOA record drives the synchronization. When a secondary's `refresh` timer expires, it queries the primary's SOA; if the primary's serial is higher, an AXFR begins. If the AXFR fails, the secondary retries after `retry` seconds, and after `expire` seconds it stops answering authoritatively.

### Recursive vs. iterative resolution

When a stub resolver asks a recursive resolver for `robot.cs.washington.edu`, the resolver does the legwork on the client's behalf — contacting one server after another until it has the answer. Each intermediate server does **not** recurse; it returns the **best partial answer it has** (a "referral") and lets the resolver continue:

```text
Client          Recursive resolver           Root            .edu            washington.edu           cs.washington.edu
  |                    |                       |                |                    |                       |
  |--query robot------>|                       |                |                    |                       |
  |                    |--query A------------->|                |                    |                       |
  |                    |<--referral to .edu----|                |                    |                       |
  |                    |--query A----------------------------->|                    |                       |
  |                    |<--referral to washington.edu----------|                    |                       |
  |                    |--query A---------------------------------------------->|                       |
  |                    |<--referral to cs.washington.edu------------------------|                       |
  |                    |--query A---------------------------------------------------------------------->|
  |                    |<--128.208.3.88 (A record)----------------------------------------------------|
  |<--128.208.3.88-----|                       |                |                    |                       |
```

This delegation pattern is what makes the system scale: the root servers answer millions of queries per second in aggregate, but each query is just "what are the NS for `edu`?" — a small response that takes microseconds to compute.

### Caching and TTL

Every record carries a TTL. When a recursive resolver receives a record, it stores it in cache until the TTL expires. Three classes of TTL behaviour:

| Record type | Typical TTL | Rationale |
|-------------|-------------|-----------|
| Root NS records | 518400 (6 days) | Extremely stable; anycast sites rarely move |
| TLD NS records | 86400 (1 day) | Stable but occasionally change |
| Host A records | 300 to 86400 | Operator choice; CDNs use 60 to 300 for fast failover |
| SOA parameters | refresh/7200 | Drives secondary behaviour, not client cache |

A low TTL lets an operator change the answer quickly — flip a load balancer, move a server — at the cost of more queries against the authoritative servers. A high TTL reduces load but makes changes take hours to propagate.

### The root servers

There are 13 logical root servers (`a` through `m`, `root-servers.net`). Each is operated by a different organisation under IANA coordination. Because 13 servers cannot serve the whole Internet, they are mirrored at hundreds of physical sites using **anycast** (RFC 4786): each site announces the same prefix, and BGP routes the query to the topologically nearest instance.

| Operator | Letters | Notable mirror count |
|----------|---------|----------------------|
| Verisign | a, j | many sites |
| USC ISI | b | several |
| Cogent | c | many |
| University of Maryland | d | many |
| NASA Ames | e | hundreds |
| ISC | f, l, k | many |
| US Army | g | a few |
| RIPE NCC | k, i, m | many in Europe |

## Build It

1. Run `python3 code/main.py` to decode a sample zone file and walk a real query.
2. Use `dig NS .` (note the trailing dot) to fetch the live list of root servers and observe the TTL on the response.
3. Query `dig AAAA www.example.com` and confirm the AAAA path works through the root.
4. Modify `sample_zone` in `main.py` to add an MX record for your own domain and check it parses.
5. Inspect `assets/dns-resource-records.svg` for the visual layout of an RR.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| Decode an RR | main.py | Each field printed, type-classified, value rendered |
| Find authoritative servers | `dig NS example.com +trace` | Three or four hops from `.` to leaf |
| Diagnose slow propagation | `dig A host.example.com @8.8.8.8` vs `@1.1.1.1` | Compare TTL and answer |
| Reverse lookup | `dig -x 8.8.8.8` | Returns `dns.google.` |
| Check mail policy | `dig TXT example.com` | Returns `v=spf1 ...` |

## Ship It

Build a zone-file validator and resolver simulator under `outputs/`. Start with [`outputs/prompt-domain-resource-records.md`](../outputs/prompt-domain-resource-records.md). Output a JSON dump of every RR parsed, plus a table of TTLs and record-type distribution.

## Exercises

1. Given zone file fragment `flits 86400 IN A 130.37.16.112`, list each of the five fields and their byte-lengths on the wire.
2. Why is the order of records in a zone file not significant, while the order of MX records **is** significant? Explain in terms of how a client uses each.
3. The SOA serial is `2024010101` and a secondary's last load was `2024010099`. Will it refresh? What if the primary's serial is `2024010100`?
4. You set `www.example.com` to `300` TTL. After 60 seconds, you change the A record. How many clients will see the old answer? What flag would you set on the previous response to ensure correctness?
5. Trace the resolution of `flits.cs.vu.nl`'s mail exchange from a host in another country. Which servers are contacted, and which MX priorities are tried in what order if the primary is down?
6. Why must an MX target not be a CNAME? What problem would arise if `cs.vu.nl`'s MX 10 host were a CNAME for a moving target?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| RR | "a row in the DNS database" | Five-tuple (Name, TTL, Class, Type, Value) |
| SOA | "zone metadata" | Record at zone apex with serial and timers |
| Zone | "a delegated slice of the tree" | Contiguous set of names managed as a unit |
| Primary | "where you edit the file" | Master server, loaded from disk |
| Secondary | "read-only copy" | Slave server, refreshed via AXFR/IXFR |
| AXFR | "full zone transfer" | Bulk TCP/53 transfer of every RR |
| IXFR | "delta zone transfer" | Incremental update by serial-number diff |
| TTL | "expiry timer" | Seconds a record may be cached |
| Recursive query | "do the work for me" | Server returns final answer or error |
| Iterative query | "best partial answer" | Server returns referral or answer |
| Anycast | "one address, many boxes" | Same prefix announced from multiple sites |
| Glue record | "extra A in the referral" | A record for an NS target, preventing loop |

## Further Reading

- RFC 1034 — Domain Names: Concepts and Facilities
- RFC 1035 — Domain Names: Implementation and Specification (Sections 3.2.1, 3.3, 4)
- RFC 2181 — Clarifications to the DNS Specification
- RFC 2308 — Negative Caching of DNS Queries
- RFC 2782 — SRV Records
- RFC 3596 — AAAA Records and IPv6 Reverse Mapping
- RFC 5936 — AXFR (Zone Transfer)
- RFC 7208 — SPF (Sender Policy Framework)
- Mockapetris, *Domain Names — Implementation and Specification*, 1987
- IANA Root Server List
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Sections 7.1.2 to 7.1.3
