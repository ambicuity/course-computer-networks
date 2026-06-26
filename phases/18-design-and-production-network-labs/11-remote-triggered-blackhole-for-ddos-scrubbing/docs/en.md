# Remote-Triggered Black Hole Filtering for DDoS Mitigation

> A volumetric DDoS attack at 600 Gbps has just saturated the upstream link at the Internet edge. The customer's authoritative DNS servers are unreachable, the API tier is dropping 70% of legitimate traffic, and the on-call engineer has been given three minutes to act. The only available lever is a **Remote-Triggered Black Hole (RTBH)** filter — a BGP-signaled discard that propagates a `/32` (or `/128` for IPv6) advertisement of the attacked target to every edge router in the upstream provider's network, causing all traffic destined for the target to be discarded at the provider edge. RTBH is the nuclear option of DDoS mitigation: it does not stop the attack, it stops the *delivery* of the attack, and it is the only tool that scales to the modern attack volume (1 Tbps+ is now common). This lesson covers the **destination-based RTBH** (RFC 5635), the **source-based RTBH** (used to block reflection sources), the **Flowspec** alternative (RFC 8956) for fine-grained per-flow filtering, the operational runbook for triggering and un-triggering, and the design of a DDoS scrubbing center that complements RTBH with traffic redirection. The deliverable is a Python RTBH controller that maintains a community-tagged BGP session to the upstream's RTBH receiver, accepts trigger requests from the NOC or the detection system, validates them against an allowlist, and emits BGP updates with the right community (e.g., `65000:666` for WestLink, `65000:999` for NorthCoast) to trigger the filter at the provider edge.

**Type:** Lab
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, datetime, hashlib, hmac), shell, BGP, tcpdump
**Prerequisites:** Phase 7 BGP, Phase 18 lessons 09 (multihoming) and 10 (RPKI) recommended
**Time:** ~120 minutes

## Learning Objectives

- Explain the **destination-based RTBH** model: the customer advertises the attacked `/32` with a blackhole community; the upstream matches the community in its route-map and re-advertises the `/32` to all its iBGP speakers, which install a discard route in the FIB.
- Distinguish destination-based RTBH (drops all traffic to the target) from **source-based RTBH** (drops all traffic from a source) and from **Flowspec** (RFC 8956, which filters on five-tuple at the provider edge).
- Configure an **RTBH receiver** BGP session between the customer and the upstream: the customer advertises a `/32` of the attacked target with the upstream's documented blackhole community; the upstream receives the update and triggers the discard.
- Implement a **trigger controller** that accepts trigger requests (HTTP API, e-mail, PagerDuty webhook), validates the requester against an allowlist, validates the target against a deny-list (so that critical infrastructure cannot be blackholed), logs the trigger to a tamper-evident audit log, and emits the BGP update via the router's API (NETCONF, gRPC, or `exabgp`).
- Design a **DDoS scrubbing center** as the alternative to RTBH for traffic that must be delivered, with a BGP-based traffic redirection (BGP `no-export` community, MED manipulation, or DNS-based redirection) and a scrubbing farm that uses behavioral analysis, rate limiting, and challenge-response to separate legitimate from attack traffic.
- Build an **operational runbook** that covers the trigger (under 60 seconds from detection to BGP update), the verification (confirming the discard is in effect at the provider edge), the un-trigger (removing the BGP update), the postmortem, and the legal notification (if the attack is a violation of local law).

## The Problem

A regional e-commerce company, "BlueSky Retail," has been hit with a 600 Gbps UDP amplification attack targeting their authoritative DNS (203.0.113.10). The attack is sustained at 580-620 Gbps for 45 minutes, with bursts to 750 Gbps. BlueSky's edge router has two 10 Gbps uplinks to WestLink and one 10 Gbps uplink to NorthCoast. The aggregate 30 Gbps of upstream bandwidth is 20x oversubscribed by the attack; every packet that reaches the edge is either attack or retransmit of a lost legitimate packet.

The on-call engineer at 2 AM has three tools:

1. **RTBH on the upstream's RTBH receiver**: BlueSky advertises 203.0.113.10/32 with the blackhole community `64600:666` to NorthCoast. NorthCoast receives the update, matches the community, and re-advertises the /32 to all 240 of its iBGP speakers with a next-hop pointing to a discard interface. The attack is dropped at the NorthCoast edge, before it ever enters the NorthCoast network. BlueSky's DNS is unreachable from the NorthCoast side, but the attack is also no longer consuming the BlueSky edge bandwidth.
2. **DDoS scrubbing via the upstream's redirection service**: BlueSky changes the authoritative DNS `A` record to point to a scrubbing-center IP. The next DNS query from the public gets the scrubbing-center IP, the attack and the legitimate traffic are redirected to the scrubbing center, the legitimate traffic is forwarded to BlueSky's origin, and the attack is dropped. This is the "scrubbing center" approach and is appropriate when the attacked service must remain reachable.
3. **Source-based RTBH**: If the attack sources are a small set of /24s (a reflection network), BlueSky can advertise those /24s with the source-blackhole community, and the upstream drops all traffic from those sources. This is a blunt instrument because it blocks legitimate traffic from those /24s too.

BlueSky's on-call triggers destination-based RTBH on NorthCoast first (the smaller uplink, the one that is fully saturated) and watches the attack volume on WestLink fall as the attack sources move away. Then they call the scrubbing center to set up a DNS-based redirection for the WestLink-bound traffic. The 600 Gbps attack is mitigated in 90 seconds, the DNS service is restored via the scrubbing center 8 minutes later, and BlueSky's revenue impact is contained to $40,000 in lost sales (versus $1.2M if the attack had been sustained for 4 hours).

The lesson is to build the controller and the runbook so that the on-call at 2 AM can trigger the filter in 60 seconds, with no tribal knowledge.

## The Concept

RTBH is a **policy primitive** dressed up as a routing primitive. The upstream has agreed, in advance, to honor a documented community value on received BGP routes and to install a discard route for any matching route. The customer, when under attack, advertises a /32 (or /128) for the attacked target with that community, and the upstream does the rest. The customer does not have to wait for a human at the upstream NOC; the trigger is automated and propagates in seconds.

### Destination-based RTBH and the community handshake

The **destination-based RTBH** model (specified in **RFC 5635** and the de-facto implementations that preceded it) is the simplest. The upstream configures a route-map on the iBGP ingress from the customer that matches the documented community (e.g., `64600:666`) and sets the next-hop to a special discard interface (on Cisco, a static `Null0` route in the BGP table; on Juniper, a `discard` next-hop; on FRR, a `blackhole` next-hop). The upstream then re-originates the /32 into its iBGP mesh, and every edge router in the upstream's network installs a discard route in the FIB.

The trigger is a BGP update from the customer: `203.0.113.10/32 → AS65020, community 64600:666, next-hop 192.0.2.1` (the customer's BGP peer IP). The upstream matches the community, installs the discard, and re-advertises the /32 with the discard next-hop to its iBGP peers. The whole propagation takes 2-5 seconds on a well-tuned provider network.

The customer must have a BGP session to the upstream's **RTBH receiver** — a dedicated BGP session, separate from the transit session, that filters all routes except the blackhole community. The session may use a different peer IP, a different VRF, and a different MD5 or TCP-AO authentication key. The customer must also have a `permit` for the blackhole community in its outbound route-map (so that the customer can send the trigger) and a `deny` for everything else (so that the customer cannot accidentally advertise other routes that would be dropped).

The community values are upstream-specific. The lesson's planner encodes a community dictionary for two fictional but realistic ISPs: WestLink uses `64500:666` for destination-blackhole and `64500:777` for source-blackhole, NorthCoast uses `64600:666` for destination and `64600:777` for source. The dictionary is operator-configurable and is stored in the RTBH controller's configuration file.

### Source-based RTBH and the reflection-source use case

**Source-based RTBH** is the inverse: the customer advertises a /24 (or /32) for the attack source with the source-blackhole community, and the upstream installs a discard route for traffic *from* that prefix. The use case is reflection DDoS: an attacker spoofs a small set of source prefixes (e.g., a misconfigured IoT botnet) and the reflection amplifiers (DNS, NTP, Memcached) send the responses to the spoofed prefixes. Source-based RTBH stops the reflection at the upstream edge.

The mechanism is the same as destination-based RTBH, but the discard route is on the source prefix instead of the destination. The customer must have a list of attack sources (from the DDoS detection system) and must advertise each source /24 with the source-blackhole community. The lesson's controller accepts a list of source prefixes (from a SIEM or a flow collector) and emits the corresponding BGP updates.

Source-based RTBH is operationally dangerous: blocking a /24 source means blocking all traffic from that /24, including legitimate users. It is appropriate only for confirmed attack sources (e.g., a known botnet's C2 prefixes) and only for the duration of the attack. The lesson's runbook requires a 5-minute expiry on every source-blackhole trigger and a manual review every 30 minutes.

### Flowspec and the per-flow alternative

**Flowspec** (RFC 8956, "Dissemination of Flow Specification Rules for IPv4", and RFC 8956's IPv6 extension) is the more granular alternative. A Flowspec NLRI carries a rule that matches on a five-tuple (source, destination, protocol, port, port) and an action (rate-limit, redirect, mark, discard). The upstream installs the rule in its forwarding plane and applies it to matching packets. The advantage is per-flow precision: the upstream can rate-limit a specific source to 100 Mbps without blocking all traffic from that source. The disadvantage is scale: a high-end router can hold 100K-1M Flowspec rules in TCAM, but the TCAM is expensive and the update rate is limited.

The lesson's planner models both RTBH and Flowspec and recommends RTBH for high-volume attacks (the 600 Gbps example) and Flowspec for low-volume, high-precision attacks (e.g., a 5 Gbps application-layer attack on a specific URL).

### Trigger controller and the audit log

The trigger controller is the software that accepts trigger requests and emits BGP updates. It runs on the customer's edge router or on a dedicated server with an `exabgp` (or `bgpd` from FRR) process. The controller has three components:

- **API endpoint**: HTTP POST to `/trigger` with the target IP, the action (destination-blackhole, source-blackhole, Flowspec), and the requester identity. The request is authenticated with a shared secret (HMAC over the body, the X-Auth header carries the HMAC).
- **Allowlist and deny-list**: the controller maintains a list of requesters who are allowed to trigger (the on-call, the NOC, the detection system) and a list of targets that cannot be triggered (e.g., the customer's authoritative DNS, the BGP peer IPs, the management network). A request to trigger a deny-listed target is rejected with a 403.
- **Audit log**: every trigger request (successful or rejected) is logged to a tamper-evident append-only log (e.g., a hash-chained sequence of records, where each record's hash includes the previous record's hash). The log is replicated to an off-host store every 5 minutes.

The lesson's controller implements all three in pure Python, with the HMAC validation, the allow/deny lists as JSON configuration, and the hash-chained audit log as a file. The controller is wired to a fake `exabgp` process via a Unix socket (the real wiring is a small change).

### DDoS scrubbing center and the redirection design

For traffic that must be delivered during an attack, RTBH is wrong (it drops the legitimate traffic too). The right tool is a **DDoS scrubbing center** — a service that receives the redirected traffic, separates attack from legitimate, and forwards the legitimate to the origin. The customer pays a per-month retainer plus a per-GB overage.

The redirection is typically done at the DNS layer: the customer changes the authoritative DNS `A` record for the attacked service to point to a scrubbing-center IP. The next DNS query from the public gets the scrubbing-center IP, the attack and the legitimate traffic are redirected to the scrubbing center, and the scrubbing center's behavioral analysis separates them. The legitimate traffic is forwarded to the customer's origin via a GRE tunnel or a direct interconnect; the attack is dropped.

The lesson's planner models the redirection design, including the DNS TTL (must be low, e.g., 60 seconds, so that the redirection takes effect quickly), the scrubbing-center capacity (typically 10x the customer's peak traffic), the BGP communities used to ask the upstream to redirect (some upstreams honor a `64600:555` community that says "redirect this prefix to the scrubbing center"), and the un-redirection (restoring the original DNS A record when the attack ends).

The trade-off: RTBH is free and immediate but drops legitimate traffic. Scrubbing is expensive (typically $5K-$50K/month) and slow (5-15 minutes to redirect) but preserves the service. The lesson's runbook has a decision matrix that recommends RTBH for non-customer-facing assets (e.g., the SMTP relay) and scrubbing for customer-facing assets (e.g., the web checkout).

### Operational runbook and the un-trigger

The un-trigger is as important as the trigger. A customer that forgets to un-trigger a blackhole after the attack ends loses the service permanently. The lesson's controller enforces an automatic expiry (default 4 hours for destination, 30 minutes for source) and emits a 60-second, 30-second, and 10-second warning before the auto-expiry. The on-call can also manually un-trigger by sending a BGP update that withdraws the /32.

The runbook includes the legal notification (in some jurisdictions, a sustained DDoS is a criminal offense and the customer must report to law enforcement), the upstream NOC notification (the upstream has a contractual right to know when its RTBH receiver is being used), the insurance notification (many cyber-insurance policies require notification within 24 hours of an attack), and the postmortem template.

## Build It

The deliverable is `code/main.py`, a deterministic RTBH controller. Inputs are: a list of upstream RTBH receivers (peer IP, community values for destination and source), a list of allow-listed requesters, a list of deny-listed targets, and a sequence of trigger events. Outputs are: BGP updates to send to each upstream, a hash-chained audit log, an allow/deny decision for each request, and a runbook template.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout. The printout includes:

- An **RTBH receiver table** with the peer IP, the community values, the BGP session state, and the last-update timestamp.
- A **trigger event log** with the requester, the target, the action, the decision (allow/deny), and the resulting BGP update.
- An **audit log** with the hash chain, verifiable by re-computing the chain from the first record.
- A **runbook template** with the trigger procedure, the un-trigger procedure, the legal notification template, and the postmortem template.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| RTBH receiver table | One entry per upstream; community values; BGP session state | Pass |
| Trigger event log | One record per request; requester, target, action, decision | Pass |
| HMAC validation | HMAC-SHA256 over the request body; request rejected if HMAC missing or wrong | Pass |
| Allowlist enforcement | Allowed requesters can trigger; denied requesters are rejected with 403 | Pass |
| Deny-list enforcement | Deny-listed targets cannot be triggered, even by allowed requesters | Pass |
| Audit log | Hash-chained; tamper-evident; verifiable | Pass |
| BGP update generation | One update per allow decision; community value correct; next-hop correct | Pass |
| Auto-expiry | Default 4h for destination, 30m for source; warning at 60s, 30s, 10s | Pass |
| Runbook template | Trigger, un-trigger, legal notification, postmortem | Pass |

## Ship It

The artifact is `outputs/rtbh_log.json` (the trigger log) and `outputs/rtbh_runbook.md` (the runbook). The controller is wired to the upstream's RTBH receiver via a real BGP session in production; in the lesson, the BGP update is printed to stdout and a fake `exabgp` process is included to demonstrate the wiring.

## Exercises

1. **Design the RTBH community for a new upstream.** The upstream "Pinnacle Transit" uses the community `64700:6666` for destination blackhole. Add Pinnacle to the controller's receiver table. What is the test plan to verify the community is honored?

2. **Compute the RTBH propagation time.** The customer advertises the /32 to NorthCoast. NorthCoast has 240 iBGP speakers. The iBGP convergence is 1 second. The customer-to-NorthCoast propagation is 50 ms. What is the total time from the trigger to the discard being in effect at the NorthCoast edge?

3. **Source-based RTBH and the collateral-damage problem.** BlueSky is under a 50 Gbps attack from AS 65999. The source-based RTBH on /24s in AS 65999 would block all 256 /24s. How many legitimate users are in AS 65999? What is the collateral damage? What is the alternative?

4. **Flowspec rule generation.** The attack is on TCP/443 to 203.0.113.10. Generate a Flowspec rule that rate-limits this flow to 1 Gbps. What is the NLRI encoding? What is the action encoding?

5. **Hash-chained audit log and tampering detection.** The auditor changes the timestamp on record 42. What is the effect on the hash chain? How is the tampering detected?

6. **DDoS scrubbing center capacity planning.** BlueSky's peak legitimate traffic is 5 Gbps. The scrubbing center must be able to absorb the attack (600 Gbps) and the legitimate (5 Gbps) at the same time. What is the scrubbing-center capacity requirement? What is the cost at typical scrubbing-center pricing ($0.005/Mbps/hour)?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| RTBH | "Remote-triggered black hole" | A BGP-signaled discard that propagates to the upstream's iBGP mesh and is installed at the upstream edge |
| Destination-based RTBH | "Drop all traffic to this /32" | An RTBH trigger on the attacked target's IP address |
| Source-based RTBH | "Drop all traffic from this /24" | An RTBH trigger on the attack source's prefix |
| Blackhole community | "The tag the upstream reads" | A BGP community value (e.g., 64600:666) that the upstream matches in its route-map to install a discard |
| Flowspec | "Per-flow filter at the provider edge" | RFC 8956 NLRI that carries a five-tuple match and an action (rate-limit, redirect, discard) |
| Scrubbing center | "A service that separates attack from legitimate" | A DDoS mitigation service that receives redirected traffic, drops the attack, and forwards the legitimate |
| DNS-based redirection | "Change the A record to point to the scrubber" | A redirection technique that changes the authoritative DNS answer to the scrubbing-center IP |
| Discard interface | "Null0" | A virtual interface on the router that drops all traffic routed to it |
| exabgp | "A BGP speaker in Python" | A process that speaks BGP from a user-space process, used to inject RTBH triggers from the controller |
| Hash-chained audit log | "A tamper-evident log" | A log where each record's hash includes the previous record's hash, making tampering detectable |

## Further Reading

- **RFC 5635** — *Remote Triggered Black Hole Filtering with Unicast Reverse Path Forwarding* — the canonical RTBH specification
- **RFC 8956** — *Dissemination of Flow Specification Rules for IPv4* — Flowspec
- **RFC 8956** (IPv6) — Flowspec for IPv6
- **draft-ietf-idr-flowspec-v2** — Flowspec v2 with extended match
- **Cisco RTBH configuration guide** — vendor implementation
- **Juniper RTBH configuration guide** — vendor implementation
- **FRRouting RTBH documentation** — open-source implementation
- **exabgp documentation** — the de-facto RTBH trigger tool
- **NANOG DDoS tutorial** — operator-focused DDoS mitigation best current practice
- **M3AAWG DDoS mitigation recommendations** — industry best practice
- **US-CERT DDoS guidance** — government DDoS response
- **DDoS scrubbing service comparison (Gartner, Forrester)** — vendor selection criteria
- **NIST SP 800-61** — incident-handling guide (general, applicable to DDoS)
