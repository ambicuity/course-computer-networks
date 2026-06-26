# DNS Resolution Path Tracing with dig +trace

> `dig +trace example.com` turns a recursive resolver into an iterative one: instead of handing the name to a caching resolver and trusting the answer, the tool starts at the DNS root (the 13 logical root servers, named `a`–`m.root-servers.net`, described in RFC 1035 §6 and the root hints), sends the full query name to a root server, reads the **referral** (an empty answer section with **NS** records in the AUTHORITY section and optional **glue A** records in ADDITIONAL), and walks the delegation chain — root → TLD (`com.`, `net.`) → authoritative — until a server sets the **AA (authoritative answer)** bit and returns the final record. Each DNS message carries a 12-byte header: a 16-bit **ID**, 16-bit **flags** (QR/Opcode/AA/TC/RD/RA/RCODE), and four 16-bit section counts (QD/AN/NS/AR). The classic failure modes a trace exposes are **lame delegations** (an NS points at a server that is not authoritative — the AA bit is absent where it should be), **missing glue** (an in-bailiwick NS name with no A record in ADDITIONAL, forcing an extra resolution round-trip), and **NXDOMAIN** vs **NODATA** (RCODE 3 with SOA in AUTHORITY versus RCODE 0 with an empty answer and a SOA proving the name exists but has no record of that type). This lab builds an RFC 1035 message parser and an iterative resolver that reproduces the exact `+trace` output, then uses `dig` and `tcpdump` to capture the same walk on the real Internet.

**Type:** Lab
**Languages:** Python, dig, tcpdump
**Prerequisites:** DNS record types (A/NS/SOA) and the hierarchical namespace; UDP port 53; basic `dig` usage
**Time:** ~80 minutes

## Learning Objectives

- Read a 12-byte DNS message header and decode the QR, AA, TC, RD, RA, and RCODE bits, plus the four section counts.
- Distinguish a **referral** (AA=0, NS records in AUTHORITY, glue in ADDITIONAL) from an **authoritative answer** (AA=1, record in ANSWER) and from **NXDOMAIN** (RCODE=3, SOA in AUTHORITY).
- Walk the root → TLD → authoritative delegation chain manually and explain why each hop sends the *full* query name rather than a suffix.
- Identify a lame delegation and missing glue from `dig +trace` output and from a captured packet, naming the exact fields that prove it.
- Explain why glue records exist only for **in-bailiwick** NS names (names inside the delegated zone) and why out-of-bailiwick NS names get no glue.
- Build an iterative resolver that follows NS delegations using a 12-byte header parser, matching `dig +trace` hop for hop.

## The Problem

A customer reports that `www.brandco.io` intermittently fails to resolve from some networks but works from others. Their caching resolver sometimes returns an A record and sometimes times out. The nameservers listed in their registrar are `ns1.brandco.io` and `ns2.brandco.io` — but `ns1.brandco.io` is itself a subdomain of `brandco.io`, the very zone it is supposed to serve. When you ask the `.io` TLD for `brandco.io`, it hands back NS records but, if the registrar never uploaded the glue, no A records for those NS names. The resolver is now in a loop: to find the address of `ns1.brandco.io` it must ask `ns1.brandco.io`, which it cannot reach without that address. Some resolvers cache the glue from a prior successful walk; others give up.

You cannot diagnose this from a single `dig www.brandco.io` — it returns the cached answer or a timeout with no clue *where* the chain broke. You need to replay the exact delegation walk the resolver performs, hop by hop, and inspect each server's response. That tool is `dig +trace`.

## The Concept

### The DNS message header (RFC 1035 §4.1.1)

Every DNS message over UDP/53 (or TCP/53 for messages exceeding 512 bytes, per RFC 1035 §4.2.2, extended by EDNS0 in RFC 6891) begins with a fixed 12-byte header:

| Offset | Field | Size | Meaning |
|---|---|---|---|
| 0 | ID | 16 bits | Transaction id; copied by the server into the response for matching |
| 2 | Flags | 16 bits | QR (1=resp), Opcode (4 bits), AA, TC, RD, RA, Z (3 bits), RCODE (4 bits) |
| 4 | QDCOUNT | 16 bits | Number of entries in the QUESTION section |
| 6 | ANCOUNT | 16 bits | Number of resource records in the ANSWER section |
| 8 | NSCOUNT | 16 bits | Number of resource records in the AUTHORITY section |
| 10 | ARCOUNT | 16 bits | Number of resource records in the ADDITIONAL section |

The single most diagnostic bit is **AA** (bit 10, mask `0x0400`). It is set *only* by a server that is authoritative for the zone containing the answer — never by a recursive resolver, never on a referral. Its presence or absence is what `dig +trace` prints as `aa` in the flags line, and it is the first thing an engineer checks at each hop. The **RCODE** field (low 4 bits) distinguishes `NOERROR` (0) from `NXDOMAIN` (3); both can come back with an empty ANSWER section, but NXDOMAIN means the name does not exist, while NOERROR-with-empty-answer (NODATA) means the name exists but has no record of the requested type. A SOA record in the AUTHORITY section accompanies both, signed by the zone that is asserting the non-existence.

### The four sections and where records live

A DNS response carries up to four sections, and *which section a record sits in* is as meaningful as the record itself:

| Section | Holds | What it tells you |
|---|---|---|
| QUESTION | The original query name/type/class, echoed | Confirms the server answered what you asked |
| ANSWER | RRs that directly answer the question | Present only on a final answer; empty on a referral |
| AUTHORITY | NS records for the zone that delegated, or a SOA | NS here = "I am not authoritative, ask these"; SOA here = NXDOMAIN/NODATA proof |
| ADDITIONAL | Glue A/AAAA records for the NS names above | Only present for in-bailiwick NS names the server can resolve |

A **referral** is the signature pattern: ANSWER empty, AUTHORITY full of NS records, ADDITIONAL full of glue. An **authoritative answer** is the opposite: ANSWER populated, AA bit set. `code/main.py` reproduces both shapes — the root and TLD hops build referrals (AA=0, NS in AUTHORITY), while the authoritative hop sets AA and puts the A record in ANSWER.

### Why iterative resolution sends the full name

A stub resolver sends `www.example.com` to a recursive resolver and waits. The recursive resolver, however, must *discover* the chain itself. It starts at a root server — from the **root hints** file shipped with every resolver (the current set is published as `https://www.internic.net/domain/named.root`, mirroring the `a`–`m.root-servers.net` anycast cluster). Critically, it sends the *entire* query name `www.example.com` to the root server, not just `com`. The root server does not know `www.example.com`, but it does know who delegates `com.`, so it returns a referral to the `.com` TLD servers. The resolver then sends the *same full name* to a TLD server, which refers it to `ns1.example.com`. Only at the authoritative server does the full name finally match a record and produce an answer.

This is why each hop is a query for the complete name — the delegation tree narrows *which server knows*, not *what is being asked*. `assets/dns-resolution-path-tracing-with-dig-trace.svg` shows the three-hop walk with the query and response at each step.

### Glue records and the in-bailiwick rule

A **glue record** is an A (or AAAA) record placed in the ADDITIONAL section to break a circular dependency. Consider `example.com` delegated to `ns1.example.com`. To contact `ns1.example.com` you need its address, but to get its address you must ask `ns1.example.com` — a loop. The `.com` TLD breaks the loop by including the A record for `ns1.example.com` in the ADDITIONAL section of its referral. This is only possible because `ns1.example.com` is **in-bailiwick** — it lives inside the zone being delegated (`example.com`). The TLD is allowed to serve that glue because the glue's parent zone is the TLD's child, and the registrar uploaded it.

If `example.com` were instead delegated to `ns1.provider.net`, no glue is needed: `ns1.provider.net` is **out-of-bailiwick**, and the resolver resolves it through a separate, independent walk of the `.net` tree. A common misconfiguration is registering in-bailiwick nameservers but forgetting to upload glue through the registrar — exactly the `brandco.io` failure. The TLD then returns NS records with an *empty* ADDITIONAL section, and the resolver stalls.

| NS name style | Bailiwick | Glue in referral? | Failure if missing |
|---|---|---|---|
| `ns1.example.com` (delegating `example.com`) | In-bailiwick | Yes, required | Resolver cannot reach NS — resolution stalls |
| `ns1.provider.net` (delegating `example.com`) | Out-of-bailiwick | No, resolved independently | Separate `.net` walk fails instead |

### Referral vs authoritative answer vs NXDOMAIN

The three outcomes a hop can produce, and the exact field evidence for each:

| Outcome | AA bit | RCODE | ANSWER | AUTHORITY | ADDITIONAL |
|---|---|---|---|---|---|
| Referral | 0 | 0 (NOERROR) | empty | NS records (child) | glue A/AAAA |
| Authoritative answer | 1 | 0 (NOERROR) | requested RR(s) | (often empty, may carry SOA) | (optional) |
| NXDOMAIN | 0 or 1 | 3 (NXDOMAIN) | empty | SOA of the asserting zone | (optional) |
| NODATA (name exists, no such type) | 1 | 0 (NOERROR) | empty | SOA of the zone | (optional) |

Note that NXDOMAIN and NODATA both have an empty ANSWER section; only the RCODE and the presence/absence of the SOA distinguish them. The SOA in AUTHORITY also carries the **negative TTL** (the minimum of the SOA's TTL and its MINIMUM field, per RFC 2308) that tells a caching resolver how long to remember the negative answer.

### Lame delegations: the missing AA bit

A **lame delegation** occurs when a parent zone points an NS record at a server that is *not* actually configured to be authoritative for that zone. The server still responds (it is reachable), but it is not authoritative, so it does not set the AA bit and typically returns a referral *back* toward the root or an empty answer. `dig +trace` shows this immediately: at the hop where you expect `aa` in the flags line, it is missing. `code/main.py` includes a `lame_delegation_demo()` that constructs exactly this case — a response with `qr` set but `aa` absent — and points out that the resolver, seeing no answer and no usable delegation, retraces from the root. In the field, lame delegations usually trace to a typo in the NS list, a server that lost its zone file, or a registrar pointing at the wrong provider.

### Worked example: `dig +trace www.example.com`

Running `dig +trace www.example.com A` produces a three-block trace (abridged):

```
;; Received 5 bytes from a.root-servers.net#53(198.41.0.4) in 4 ms
example.com.        172800  IN  NS  a.iana-servers.net.   ;; referral, no AA
;; Received 500 bytes from a.gtld-servers.net#53(192.5.6.30) in 60 ms
www.example.com.    300     IN  A   93.184.216.34         ;; final, aa flag set
;; Received 87 bytes from a.iana-servers.net#53(199.43.135.53) in 30 ms
```

The first block is the root's referral to the `.com` TLD (NS records, no AA). The second is the TLD's referral to `example.com`'s authoritative servers (NS plus glue). The third is the final answer with the AA bit. The numbers to check at each hop: the **AA bit** flips from 0 → 0 → 1, the **ANSWER count** goes 0 → 0 → 1, and the **ADDITIONAL count** is nonzero only where glue is needed. If any hop shows an unexpected `rcode=3`, the chain broke at that server, not the one before it.

## Build It

1. Read `code/main.py`. It implements an RFC 1035 header parser (`parse_header`, `flags_str`), an authoritative-server model (`AuthoritativeServer.answer`), and an iterative resolver (`resolve`) that follows NS delegations root → TLD → authoritative.
2. Run it: `python3 code/main.py`. Confirm the three-hop trace: root referral (`qr`, no `aa`, NS in AUTHORITY), TLD referral with glue, final answer with `aa` and the A record in ANSWER.
3. Inspect the lame-delegation demo block: a response with `qr` but no `aa` is the signature of a non-authoritative server answering for a zone it does not own.
4. Edit the `EXAMPLE_COM` zone to remove the `www.example.com.` A record and rerun — observe the authoritative hop returns NOERROR with an empty ANSWER (NODATA), not NXDOMAIN, because the zone origin still exists.
5. Add a `Zone` for `example.net.` and register it in `SERVERS`, then change the root's `delegations` to point `net.` at it; trace `www.example.net.` to confirm a second independent branch works.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a referral | ANSWER count = 0, NS records in AUTHORITY, AA bit = 0 | The resolver follows the NS to the next hop instead of stopping |
| Confirm a final answer | ANSWER count ≥ 1, AA bit = 1, requested RR present | The AA bit is set; the record's TTL is plausible (seconds–hours, not 0 or maxint) |
| Detect a lame delegation | Expected hop has AA = 0 and no useful ANSWER or referral | The NS points at a server that is not authoritative; trace retraces or stalls |
| Detect missing glue | In-bailiwick NS name with empty ADDITIONAL section | An extra resolution round-trip is forced, or resolution fails entirely |
| Distinguish NXDOMAIN from NODATA | RCODE 3 + SOA vs RCODE 0 + empty ANSWER + SOA | The negative TTL from the SOA MINIMUM governs caching of the non-existence |
| Capture the real walk | `tcpdump -ni any port 53 -X` alongside `dig +trace` | UDP/53 packets to root, then TLD, then authoritative, each carrying the 12-byte header |

## Ship It

Produce one artifact under `outputs/prompt-dns-resolution-path-tracing-with-dig.md`:

- An annotated `dig +trace` transcript for a real domain of your choice, with each hop's AA bit, section counts, and the NS/glue records called out, plus a `tcpdump -X` capture of one referral packet with the 12-byte header decoded byte by byte. Annotate the failure mode you triggered (or found) — lame delegation, missing glue, or NXDOMAIN — and the exact field evidence that proves it.

Start from the printed output of `code/main.py` as the template for the format, then run the real `dig +trace` and `tcpdump` commands and paste their output.

## Exercises

1. Run `dig +trace example.com +nodnssec` and `dig +trace example.com +dnssec` and compare the AUTHORITY/ADDITIONAL sections. Identify where DNSSEC records (RRSIG, DNSKEY, DS) appear and which hop introduces the DS record that chains `example.com` back to `.com` (RFC 4035).
2. A domain delegates to `ns1.own.tld` where `own.tld` is the zone itself, but the registrar has no glue on file. Trace the exact failure: which section is empty, what the resolver does next, and the error a stub sees. Then describe the fix at the registrar.
3. Capture `dig +trace` with `tcpdump -ni any 'port 53' -w trace.pcap` and open it in Wireshark. Identify the three UDP query/response pairs, confirm source port 53 on the server side, and decode the ID and flags fields of the root referral by hand from the hex.
4. Modify `code/main.py` so the TLD zone returns no glue for an in-bailiwick NS (set `glue={}`). Run the resolver and show it cannot progress past the TLD hop; explain why the resolver does not simply query the root again for the NS's address.
5. Construct a zone where the authoritative server returns RCODE 3 (NXDOMAIN) for `ghost.example.com` and RCODE 0 with empty ANSWER (NODATA) for `example.com` of type MX. Show, from the AUTHORITY SOA in both cases, how a caching resolver learns the negative TTL (RFC 2308) for each.
6. Use `dig +trace +all` to force a query over TCP instead of UDP (or trigger truncation by disabling EDNS0 with `+bufsize=512`). Explain when a DNS message must switch from UDP to TCP (the TC bit, RFC 1035 §4.2.2, and EDNS0 buffer negotiation in RFC 6891) and how `dig` surfaces the retry.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Referral | "the server punted" | A response with empty ANSWER, NS records in AUTHORITY, and AA=0, pointing the resolver to the next zone down the tree |
| Authoritative answer (AA) | "the real answer" | The AA bit (flags `0x0400`), set only by a server configured as authoritative for the zone containing the answer |
| Glue record | "extra A records" | A/AAAA records in the ADDITIONAL section that resolve in-bailiwick NS names, breaking the delegation circular dependency |
| In-bailiwick | "same zone" | An NS name that lives inside the zone being delegated; only these get glue, because the parent can authoritatively answer for them |
| Lame delegation | "broken NS" | An NS record pointing at a server that is not authoritative for the zone; the response lacks the AA bit and the chain stalls |
| Root hints | "the starting list" | The cached list of root server addresses (`named.root`) a resolver uses to bootstrap the first query before it has any cache |
| NXDOMAIN | "name not found" | RCODE 3: the queried name does not exist at all, asserted with a SOA in AUTHORITY carrying a negative TTL |
| NODATA | "empty answer" | RCODE 0 with an empty ANSWER: the name exists but has no record of the requested type, also signed by a SOA |
| Iterative resolution | "walking the tree" | The resolver follows referrals hop by hop itself, as `dig +trace` does, rather than delegating the walk to a recursive server |

## Further Reading

- **RFC 1035** — Domain Names: Implementation and Specification (header format §4.1.1, message construction, the four sections).
- **RFC 1034** — Domain Names: Concepts and Facilities (the iterative resolution algorithm and the delegation model).
- **RFC 2308** — Negative Caching of DNS Responses (NXDOMAIN/NODATA and the SOA negative TTL).
- **RFC 6891** — Extension Mechanisms for DNS (EDNS0): larger UDP buffers, the OPT pseudo-RR.
- **RFC 4034 / RFC 4035** — DNSSEC Resource Records and Protocol Modifications (RRSIG, DNSKEY, DS, the chain of trust a `+trace +dnssec` reveals).
- **IANA Root Zone Database** — the authoritative list of TLD delegations and their NS/glue.
- `named.root` / `https://www.internic.net/domain/named.root` — the current root hints file shipped with every recursive resolver.
- Albitz & Liu, *DNS and BIND*, 5th ed., O'Reilly — the canonical operational reference for zone files, delegation, and troubleshooting.
