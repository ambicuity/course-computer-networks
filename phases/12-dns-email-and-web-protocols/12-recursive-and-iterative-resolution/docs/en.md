# Recursive vs Iterative Query Resolution

> Two query modes coexist in DNS because no single name server can answer every question on its own. A **recursive** query tells the server: "do the work for me and bring back the final answer (or an error)"; an **iterative** query tells the server: "give me the best referral you have, and I will ask the next server myself". The relationship between client and local resolver (the ISP or company caching server) is recursive — the resolver promises to return either the answer or NXDOMAIN. The relationship between the resolver and the root, TLD, and authoritative servers is iterative — each server returns the NS records for the next-lower zone and the resolver keeps walking down. Caching makes this practical: a recursive resolver holds responses for the duration of their TTL (RFC 1035 §3.2.1; RFC 2308 for negative caching), so a popular name is answered locally without ever touching the global hierarchy. The 13 root servers (a.root-servers.net through m.root-servers.net) and the gTLD servers behind them will refuse recursion, return a delegation-only referral, and let the resolver do the next hop itself.

**Type:** Lab
**Languages:** Python, dig, shell
**Prerequisites:** Phase 12 lessons 11 and prior on DNS records, name servers, and UDP transport
**Time:** ~90 minutes

## Learning Objectives

- Distinguish recursive from iterative queries by watching the wire with `dig +trace` and `dig +norecurse`.
- Trace a name resolution through root → TLD → authoritative → answer, naming every RR type that crosses the wire (NS, A, AAAA glue).
- Explain why the local resolver performs recursion for its clients while the root and TLD servers return referrals only.
- Reason about TTL-driven caching: which records get cached, for how long, and why a record with TTL=0 must never be cached.
- Read the iterative `+trace` output as a sequence of A/NS/A glue records that build a delegation chain.
- Compare the cost of a cold recursive resolution (multiple round trips, UDP/TCP) versus a cached answer (one round trip, or none at all).

## The Problem

You type `http://www.cs.uwa.edu.au/`. Your laptop's stub resolver asks the local DNS server (the recursive one). That server has no cached answer; it does not know where `cs.uwa.edu.au` lives. Some mechanism must walk the namespace from the root down to the authoritative server for `uwa.edu.au` and return the A record. The naive design — one server that knows everything — would never scale. The actual design splits the work: the root knows the TLDs, each TLD knows its second-level domains, each zone knows its own hosts. The trick is making them cooperate via a tiny set of message types and a clear division of who asks whom.

The trap is conflating the two modes. `dig @8.8.8.8 example.com A` looks recursive from your perspective but underneath the resolver is doing an iterative walk: it talks iteratively to the root, to the `.com` servers, and finally to the authoritative server for `example.com`. `dig +trace` shows the entire walk; `dig +norecurse` (when sent to a recursive resolver) lets you simulate the iterative mode and see the resolver tell you "I would have done recursion, but you asked me not to — here is the referral".

## The Concept

### The two modes, in one sentence

- **Recursive**: the server promises an answer (or an error). Used between stub resolvers and their local caching resolver.
- **Iterative**: the server promises the best referral it has. Used between the local resolver and every other server on the path to the answer.

The RD flag in the DNS header (RFC 1035 §4.1.1) says "Recursion Desired": set by the client when it wants recursion. The RA flag (Recursion Available) says the server supports recursion. A root server returns RA=0 because it does not perform recursion on behalf of random clients — it is too busy.

### A canonical 10-step trace

The textbook trace from RFC / Tanenbaum shows a flits.cs.vu.nl client resolving `robot.cs.washington.edu`:

| Step | Client → Server | Query / Referral | Mode |
|---|---|---|---|
| 1 | flits → local | Q: robot.cs.washington.edu A | recursive ask |
| 2 | local → a.root-servers.net | Q: robot.cs.washington.edu A | iterative ask (RD=0) |
| 3 | a.root → local | Refers to edu NS: a.edu-servers.net (with A glue) | referral |
| 4 | local → a.edu-servers.net | Q: robot.cs.washington.edu A | iterative ask |
| 5 | a.edu → local | Refers to washington.edu NS: ns1.washington.edu | referral |
| 6 | local → ns1.washington.edu | Q: robot.cs.washington.edu A | iterative ask |
| 7 | ns1 → local | Refers to cs.washington.edu NS: star.cs.washington.edu | referral |
| 8 | local → star.cs.washington.edu | Q: robot.cs.washington.edu A | iterative ask |
| 9 | star → local | A: 128.208.3.82 (authoritative) | answer |
| 10 | local → flits | A: 128.208.3.82 (recursive answer) | recursion done |

Each `→` is one or more UDP/53 messages. The local resolver caches every record it sees along the way: the edu NS, the washington.edu NS, and the final A. The next query for `galah.cs.washington.edu` skips straight to step 8 because the NS for `cs.washington.edu` is now cached. The next query for `www.cs.uwa.edu.au` still hits the root (different TLD) but skips the `.edu` and `washington.edu` lookups by going straight to whatever authoritative NS the root returned.

### The messages at each hop

At every step the resolver sends the *same* QNAME and QTYPE but gets back different things:

| Step's response | What the server returns | Why |
|---|---|---|
| root (`.`) | NS records for `.edu` (and the A glue for `a.edu-servers.net`) | root is authoritative for `.` only |
| `.edu` TLD | NS records for `washington.edu` | TLD is authoritative for `.edu` only |
| `washington.edu` zone | NS records for `cs.washington.edu` (a sub-zone) | zone is authoritative for itself, may delegate sub-zones |
| `cs.washington.edu` zone | A record (or NXDOMAIN) for `robot` | zone is authoritative for itself, no further delegation |

Glue records (RFC 1034 §3.6) are the A/AAAA records for the NS hostnames returned in a referral. Without glue the resolver would face a chicken-and-egg problem: "to ask the NS for `cs.washington.edu`, I must resolve its name, but to resolve its name I have to ask the NS for `cs.washington.edu`". Glue breaks the loop. Modern zones keep glue in the **additional** section of the referral response specifically for this reason.

### Caching, TTLs, and negative caching

Each record carries its own TTL (RFC 1035 §3.2.1). The local resolver caches the answer for at most that long. RFC 2308 added **negative caching**: an NXDOMAIN or NODATA response is cached too, with a TTL derived from the SOA's `MINIMUM` field, so repeated misses for non-existent names do not hammer the authoritative servers. The textbook TTL numbers:

- A record for a stable host: 86400 (one day).
- A record for a CDN or load-balanced pool: 30 to 300 seconds.
- An NS record for a TLD: typically 172800 (two days) — TLD delegations are extremely stable.
- Negative answers: bounded by the SOA `MINIMUM` field (often 300 to 3600 seconds).

A TTL of 0 means "do not cache this answer". This is sometimes used for very dynamic records (load-balancer pool membership) at the cost of one upstream query per resolution.

### Glue records and the chicken-and-egg problem

The additional-section glue in a referral is one of the more subtle parts of the protocol. When the root returns NS records for `.edu`, it also returns the A record for `a.edu-servers.net` (and often the AAAA) in the additional section. Without that, the resolver would have to ask the root again — or someone else — for the address of the very server it was just told to contact. In well-managed zones (`.com`, `.net`, `.org`) the TLD operators pre-publish glue for every second-level domain's NS hostnames so the bootstrapping is fast. Badly-managed zones (some country-code TLDs) historically had glue missing or stale, leading to slow first lookups until the cache warmed.

### Why roots and TLDs refuse recursion

A root server sees a query rate that is genuinely enormous — single-digit-millisecond response times under billions of queries per day from across the planet. Performing recursion on top of that workload would multiply the work per query by an order of magnitude. The operational rule (RFC 1035 §6) is: root and TLD servers are delegation-only — they return NS records for the next zone and nothing else. If you send RD=1 to a root, you get back the same NS referral you would have received without it, with RA=0 in the header so you know recursion is unavailable. Local resolvers are the only servers that say yes to recursion; this concentrates the recursive work at the network edges where it can be cached.

## Build It

1. Run `code/main.py` to print a model of the recursive walk, the cached intermediate state, and the resulting RTT count.
2. Reproduce the canonical 10-step walk with `dig +trace www.cs.washington.edu`. Each `;;Got answer:` block is one step; the `;;SERVER:` line tells you which server answered.
3. Force the iterative mode with `dig +norecurse @8.8.8.8 example.com NS`. You will receive a referral to the `.com` NS set, not the answer.
4. Verify caching: run `dig +nocache example.com A`, then `dig example.com A` immediately — the second should return in roughly half the time and show a smaller `;;Query time`.
5. Test the no-recursion flag with `dig +norecurse @a.root-servers.net example.com`: the root ignores RD and returns NS records for `.com`.
6. Use `dig +trace +nodnssec ...` if your resolver adds EDNS(0) OPT records you do not want to see — it trims the per-step output to the essentials.

```python
# Excerpt from code/main.py
def walk_recursive(name: str, zones: list[str]) -> list[str]:
    """Return the servers contacted in order for a cold recursive resolution."""
    hops = ["local-resolver"]
    for zone in zones:
        hops.append(f"{zone}-NS")
    return hops
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Recursive walk | `walk_recursive(name, zones)` | `dig +trace` | RFC 1034 §3.1 |
| Iterative referral | `refer(name, level)` | `dig +norecurse` | RFC 1035 §4.1.1 (RD flag) |
| TTL-driven cache | `Cache(ttl_map)` | BIND, Unbound, Knot | RFC 1035 §3.2.1 |
| Negative caching | `Cache.put_nxdomain(soa_min)` | BIND `max-ncache-ttl` | RFC 2308 |
| Glue-record traversal | `glue_for(ns)` | Unbound's `infra-cache` | RFC 1034 §3.6 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `dig +trace` annotated log with each server named (root, TLD, zone, authoritative) and each section's purpose (question, referral, glue, answer) labelled in the margin.
- A TTL-aware cache simulator that predicts how long a name remains "warm" after each lookup.
- A decision rule for "send RD=1 vs RD=0" given the role of the queried server.

Start from [`outputs/prompt-recursive-and-iterative-resolution.md`](../outputs/prompt-recursive-and-iterative-resolution.md).

## Exercises

1. Run `dig +trace www.cnn.com A` and identify each server in the chain. How many distinct NS names appear, and how many distinct IP addresses?
2. Use `dig +nocache www.example.com A` then `dig www.example.com A` and record the `;;Query time` difference. What is the minimum TTL on the answer section that bounds how long the cache helps?
3. Send `dig +norecurse @a.root-servers.net www.example.com A`. Why does the root return NS records for `.com` instead of the A record?
4. Capture a single `+trace` walk in `tcpdump -w trace.pcap udp port 53`. In Wireshark, count the distinct transaction IDs across the trace — one per server visited.
5. Force a negative cache: query a name guaranteed not to exist (`nx.example-123456789.invalid`) and check that subsequent queries within the SOA `MINIMUM` window do not reach the authoritative server.
6. Predict the difference in round trips for a cold recursive resolution versus a warm cached one. Verify with `dig +stats` and the `;;Query time` field.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Recursive query | "the server does all the work" | Server promises an answer (or NXDOMAIN); used between stub and local resolver |
| Iterative query | "the server gives a referral" | Server returns the best NS it knows; used between resolvers and authoritative servers |
| RD flag | "Recursion Desired" | Header bit set by clients that want recursion |
| RA flag | "Recursion Available" | Header bit set by recursive resolvers; root and TLD servers return RA=0 |
| Referral | "NS records pointing deeper" | An NS RRset in the authority section pointing to the next-lower zone |
| Glue record | "the A record for the NS host" | A/AAAA in the additional section of a referral so the resolver does not loop |
| TTL | "how long to cache" | 32-bit seconds field on every RR; 0 = do not cache |
| Negative caching | "cache the misses too" | RFC 2308: cache NXDOMAIN/NODATA for the SOA MINIMUM duration |
| Cold vs warm | "first lookup vs subsequent" | Cold cache = full walk; warm cache = answer from local RAM/disk |

## Further Reading

- RFC 1034 — Domain Names — Concepts and Facilities (resolver model, recursive vs iterative)
- RFC 1035 — Domain Names — Implementation and Specification (header flags RD/RA, TTL field)
- RFC 2308 — Negative Caching of DNS Queries (NXDOMAIN, SOA MINIMUM)
- RFC 1034 §3.6 — Glue records and the chicken-and-egg problem
- RFC 7816 — DNS Query Name Minimisation to Improve Privacy
- IANA Root Servers — https://www.iana.org/domains/root/servers
- `dig` reference — `+trace`, `+norecurse`, `+nocache`, `+nodnssec`, `+stats`
