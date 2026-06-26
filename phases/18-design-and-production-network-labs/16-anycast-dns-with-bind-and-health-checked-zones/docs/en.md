# Anycast DNS Deployment with Health-Checked Authoritative Zones

> Every recursive resolver on the Internet queries authoritative DNS to find the IP address of a domain. A slow or unreachable authoritative DNS is a slow or unreachable Internet for every user behind that resolver. **Anycast DNS** — the same IP advertised from multiple physical locations using BGP — is the only architecture that delivers the millisecond-latency and the resilience that modern DNS requires. A well-designed anycast deployment has 6-12 globally distributed sites, each with a BIND9 (or Unbound, Knot, NSD) authoritative server, each announcing the same /24 (or /32 for IPv6) from the local router via BGP, and each serving the same zone from a hidden primary that pushes via AXFR/IXFR. When a query arrives, the BGP routing table directs it to the *nearest* site (in BGP terms), the local BIND9 answers from cache or from disk in microseconds, and the response is sent back through the same router. If one site fails — power, network, BIND9 crash — the BGP route is withdrawn, the global table converges in seconds, and all subsequent queries are routed to the next-nearest site. This lesson is the working playbook for anycast DNS: the site selection (PoP count, geographic distribution, transit diversity), the addressing plan (the anycast IP, the site IPs, the loopback IPs), the BIND9 configuration (views, masters, slaves, RPZ for response policy), the health-check and route-withdrawal automation (RFC 8213 health-check, RTBH-style route withdrawal, Prometheus blackbox exporter), the migration from unicast to anycast (parallel run, cutover, validation), and the operational runbook (cache poisoning, DDoS, AXFR failures). The deliverable is a Python anycast DNS planner that takes a list of PoPs, a zone list, and a query-rate target, and outputs the BIND9 configuration, the BGP configuration for the anycast prefix, the health-check script, and the cutover runbook.

**Type:** Build
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, enum), shell, BIND9, dig
**Prerequisites:** Phase 7 BGP, Phase 12 DNS, Phase 18 lesson 09 (multihoming)
**Time:** ~130 minutes

## Learning Objectives

- Explain the **anycast routing primitive**: the same prefix advertised from multiple sites, the BGP best-path directing queries to the nearest site, the failure model being "site is withdrawn from BGP, queries re-route to the next-nearest site."
- Design the **site selection** (6-12 PoPs, geographic distribution across continents, transit diversity, IPv4 + IPv6 dual-stack) and compute the median and tail latency for a global user population.
- Configure **BIND9** as the authoritative server (masters, slaves, AXFR/IXFR, TSIG-signed transfers, RPZ for response policy, minimal-responses for cache-friendly answers, ECS for EDNS client subnet) and verify the configuration with `named-checkconf` and `dig`.
- Implement a **health-check and route-withdrawal** loop (RFC 8213 health-check, Prometheus blackbox exporter, custom script that withdraws the BGP route when BIND9 fails) and integrate it with the router's API (BIRD, FRR, Cisco, Juniper).
- Plan the **migration from unicast to anycast** with a parallel run (the unicast IPs are still served, the anycast IPs are added), a cutover (the unicast IPs are withdrawn), and a validation (dig from multiple vantage points, RTT measurement, query rate per site).
- Build a **runbook** for the operational failures: BIND9 crash, disk full, AXFR failure, DDoS, cache poisoning, route leak, and the corresponding mitigation.

## The Problem

A content delivery network, "FastPath Networks," operates authoritative DNS for 4,500 customer domains, serving 80 billion queries per day from 8 unicast sites (a primary in Frankfurt and 7 secondary locations around the world). The pain is threefold: (1) the unicast architecture means a query from Sydney to the Frankfurt primary has 280 ms of latency, even though there is a Sydney secondary; (2) the unicast architecture has no automatic failover — when a secondary fails, the resolver continues to query the dead IP until its TTL expires; (3) DDoS attacks on the unicast IPs can saturate a single site because the IP is tied to the location.

The senior engineer must deliver an anycast DNS service: 12 PoPs (Frankfurt, London, Amsterdam, Paris, New York, Los Angeles, Sao Paulo, Singapore, Hong Kong, Tokyo, Sydney, Mumbai), each with a BIND9 authoritative server, each advertising the anycast /24 (192.0.2.0/24) via BGP from a local router, each serving the same zones via AXFR from the hidden primary. The cutover is risk-free because the unicast IPs are kept for one quarter as a fallback.

The lesson's planner builds the BIND9 configuration, the BGP configuration, the health-check script, and the cutover runbook.

## The Concept

Anycast DNS is **geographic routing** dressed up as a network primitive. The anycast prefix is a single IP (or a /24 for IPv4) that is advertised from multiple physical locations. When a recursive resolver in Sydney queries 192.0.2.53, the BGP routing table directs the query to the Sydney site (because the Sydney site is the nearest, in BGP terms) and the local BIND9 answers. The query from a resolver in Frankfurt goes to the Frankfurt site. The query from a resolver in Sao Paulo goes to... well, that's where the design gets interesting.

### Site selection and the latency distribution

The 12 PoPs are chosen for geographic distribution: 4 in Europe (Frankfurt, London, Amsterdam, Paris), 3 in North America (New York, Los Angeles, Toronto), 2 in Asia (Singapore, Tokyo), 2 in South America (Sao Paulo, Bogota), 1 in Oceania (Sydney), and 1 in South Asia (Mumbai). For a global user population, the median RTT to the nearest PoP is 15-30 ms, the 95th percentile is 60-90 ms, and the 99th percentile is 120-200 ms. The lesson's planner computes the latency distribution for a given PoP list and a given user-population distribution (e.g., 30% in Europe, 25% in North America, 25% in Asia, 10% in South America, 5% in Africa, 5% in Oceania).

The transit diversity is the second design decision. Each PoP should have at least two transit providers (or one transit and one IX) and should be in a different BGP AS than the other PoPs in the same region (so that a transit-provider failure does not take down multiple PoPs). The lesson's planner maintains a PoP-to-transit table and flags any PoP that is single-homed or that shares a transit AS with another PoP in the same region.

### The BIND9 configuration and the zone replication

Each PoP runs BIND9 in **authoritative-only** mode (no recursion, no caching of external queries). The hidden primary runs in **master** mode, and each PoP runs in **slave** mode, receiving zone updates via AXFR (full zone transfer) or IXFR (incremental zone transfer). The AXFR/IXFR is signed with **TSIG** (RFC 8945) to prevent zone-transfer hijacking.

The BIND9 configuration is a 200-400 line file that defines the options (listen-on, allow-query, allow-transfer, recursion no, minimal-responses yes, ECS yes), the key (the TSIG key for AXFR), the masters (the hidden primary IP), and the zones (one stanza per zone, with the master, the allow-transfer, and the file path).

The lesson's planner generates a BIND9 configuration from a zone list and a PoP list, with one configuration file per PoP (because each PoP has a different anycast IP and a different set of local interfaces).

### The health-check and route-withdrawal loop

The anycast deployment's resilience comes from the **health-check and route-withdrawal loop**. If a BIND9 instance fails, the local router must withdraw the anycast /24 from BGP, so the global table converges and the queries are routed to the next-nearest site. The loop is:

1. **Health check** (Prometheus blackbox exporter or a custom script) sends a DNS query (e.g., `dig @192.0.2.53 version.bind TXT CH`) to the local BIND9 every 5 seconds.
2. If the query fails (timeout, SERVFAIL, refused), the health check marks the BIND9 as unhealthy.
3. The health check sends a BGP update to the local router, withdrawing the anycast /24.
4. The router propagates the withdrawal via iBGP to the other routers, which propagate it via eBGP to the transit providers.
5. The global BGP table converges in 30-90 seconds, and the queries are routed to the next-nearest site.

The lesson's planner generates the health-check script and the BGP-withdrawal command (BIRD `disable`, FRR `neighbor ... route-map ... withdraw`, Cisco `clear ip bgp ... soft`, Juniper `delete protocols bgp ... neighbor ...`).

### The migration from unicast to anycast

The migration has three phases: **parallel run**, **cutover**, and **validation**.

The **parallel run** is the longest phase (typically 4-8 weeks). The unicast IPs are still served (the existing master and slaves), and the anycast IPs are added. The recursive resolvers are not yet pointed at the anycast IPs, so the anycast sites receive only a small amount of test traffic (from internal monitors and from the resolver's prefetch). The parallel run is the burn-in period for the anycast infrastructure.

The **cutover** is the change of the NS records at the parent zone. The parent zone's NS records are changed from the unicast IPs to the anycast IPs, and the recursive resolvers begin to query the anycast IPs. The cutover is done one zone at a time (starting with low-traffic zones, ending with high-traffic zones) and is reversible (the NS records are changed back to the unicast IPs).

The **validation** is the proof that the cutover was successful. The lesson's planner generates a validation script that uses the **RIPE Atlas** network to query the anycast IP from 500+ vantage points and measures the response time, the response IP (which site answered), and the response consistency (does the response match the expected zone data?). The validation runs every 15 minutes for the first 24 hours, then every hour for the first week, then daily.

## Build It

The deliverable is `code/main.py`, a deterministic anycast DNS planner. Inputs are: a list of PoPs (name, region, IPv4, IPv6, transit ASes), a list of zones, a user-population distribution, and a query-rate target. Outputs are: the PoP selection, the latency distribution, the BIND9 configuration per PoP, the BGP configuration per PoP, the health-check script, the cutover runbook, and the validation script.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| PoP selection | One PoP per major region; transit diversity; no shared AS in same region | Pass |
| Latency distribution | Median, 95th, 99th percentile per region; per-population | Pass |
| BIND9 config per PoP | `named-checkconf` clean; listen-on, allow-query, allow-transfer set | Pass |
| BGP config per PoP | Anycast /24 advertised; community for withdrawal; MED for traffic shaping | Pass |
| Health-check script | DNS query every 5s; BGP withdrawal on failure; tested with killed BIND9 | Pass |
| Cutover runbook | Per-zone cutover; NS record change; rollback procedure | Pass |
| Validation script | RIPE Atlas queries; per-site response rate; consistency check | Pass |

## Ship It

The artifact is `outputs/anycast_plan.json` plus the printout. The output directory should also contain `named.conf.poP-XX` (the BIND9 configuration per PoP), `bgp.conf.poP-XX` (the BGP configuration per PoP), `health_check.sh` (the health-check script), and `cutover_runbook.md` (the cutover runbook).

## Exercises

1. **Compute the latency distribution for 12 PoPs and a 30/25/25/10/5/5% population split.** What is the median RTT? The 95th percentile?

2. **Design the TSIG key rotation policy.** TSIG keys have a typical lifetime of 1-3 years. What is the rotation procedure? What is the rollback if the rotation fails?

3. **Compute the BGP withdrawal convergence time.** The PoP's local router withdraws the anycast /24. The transit provider propagates the withdrawal to its peers. The global table converges. What is the total convergence time? At what point do queries stop arriving at the failed PoP?

4. **Build a cache-poisoning detector.** A cache-poisoning attack sends forged DNS responses to a resolver. What are the signals? How is the attack detected? What is the mitigation?

5. **Design the DDoS response.** A 50 Gbps attack is hitting the anycast IP. How is the attack distributed across the PoPs? How is the attack mitigated at the per-PoP level? What is the role of RTBH?

6. **Migration validation.** A zone is cut over from unicast to anycast. The validation runs from 500 RIPE Atlas probes. What is the expected response? What is the failure mode? What is the rollback?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Anycast | "The same IP from multiple sites" | A prefix advertised from multiple physical locations; BGP directs queries to the nearest |
| Hidden primary | "The master that slaves pull from" | The authoritative master that is not advertised in the NS records, used to push zones to the slaves |
| AXFR / IXFR | "Full / incremental zone transfer" | RFC 5936 / RFC 1995 zone-transfer mechanisms; AXFR is full, IXFR is incremental |
| TSIG | "Signed zone transfer" | RFC 8945 transaction signature that authenticates the AXFR/IXFR sender and verifies the payload |
| RPZ | "Response Policy Zone" | A BIND9 mechanism (RFC 9209) that allows the operator to override DNS responses (for blocking, redirecting, etc.) |
| EDNS Client Subnet | "ECS for cache affinity" | RFC 7871 extension that carries the client's subnet in the query, allowing the authoritative to give a cache-friendly answer |
| RIPE Atlas | "A global measurement network" | A network of probes (currently 12,000+ globally) that can be used to query DNS and measure latency |
| Health check | "Is the BIND alive?" | A script that periodically queries the local BIND9 and withdraws the BGP route if the BIND is unhealthy |
| Route withdrawal | "Take the prefix out of BGP" | The BGP update that tells the upstream to remove the prefix from the routing table |

## Further Reading

- **RFC 1034, 1035** — *Domain Names - Concepts and Facilities / Implementation* — the original DNS specification
- **RFC 1995, 1996** — *Incremental Zone Transfer / DNSSEC-related changes* — IXFR
- **RFC 2845** — *Secret Key Transaction Authentication for DNS (TSIG)* — TSIG
- **RFC 5936** — *DNS Zone Transfer Protocol (AXFR)* — AXFR
- **RFC 7871** — *Client Subnet in DNS Queries* — EDNS Client Subnet
- **RFC 8213** — *Security of Messages Relating to DNS Health-Checking* — health-check security
- **RFC 8945** — *Secret Key Transaction Authentication for DNS (TSIG)* — TSIG (obsoletes 2845)
- **RFC 9209** — *DNS Response Policy Zone (RPZ)* — RPZ
- **BIND 9.18 Administrator Reference Manual** — BIND9 documentation
- **NLnet Labs Unbound documentation** — Unbound authoritative server
- **CZ.NIC Knot DNS documentation** — Knot authoritative server
- **RIPE Atlas** — global measurement network
- **DNS-OARC** — DNS Operations, Analysis, and Research Center
- **AFNOG / NANOG anycast tutorials** — operator best current practice
