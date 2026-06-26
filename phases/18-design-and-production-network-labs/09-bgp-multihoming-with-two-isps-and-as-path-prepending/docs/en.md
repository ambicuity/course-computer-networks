# BGP Multihoming to Two ISPs with AS-Path Prepending and Inbound Traffic Shaping

> A production network that depends on a single upstream ISP inherits that ISP's outages, congestion, and routing-policy missteps. Multihoming to two ISPs — ideally across two separate physical facilities, two separate transit providers, and ideally two distinct autonomous-system paths — gives the network both **outbound redundancy** (you can reach the Internet when one link is down) and **inbound traffic engineering** (you can bias inbound flows toward the higher-capacity or lower-cost link). This lesson is the working playbook for the most common production multihoming scenario: a single physical site with two BGP sessions to two ISPs, a private AS number (or a borrowed one), and a prefix advertised to both upstreams. We cover the **AS-path prepending** knob that lets you tell one upstream "be the backup path," the **MED** knob that lets you tell the other upstream "prefer me on link A," the **BGP communities** that let the upstreams reshape your traffic globally, the **RPKI** state that prevents your prefix from being hijacked, the **route filtering** that prevents you from becoming a transit for a third party, and the **convergence** trade-offs that determine whether your failover is sub-second or minute-scale. The deliverable is a deterministic Python multihoming planner that takes a prefix, an AS number, two ISP profiles, and a target traffic split, and outputs a BGP policy skeleton, a verification matrix, and a cutover runbook.

**Type:** Project
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, itertools, enum), shell, FRRouting
**Prerequisites:** Phase 7 BGP fundamentals, Phase 18 lessons 08 (OSPF design) and 10 (RPKI) recommended
**Time:** ~150 minutes

## Learning Objectives

- Choose between the four canonical multihoming architectures (single-homed, multi-homed to one ISP, multi-homed to two ISPs over one link, multi-homed to two ISPs over two links) and articulate the cost/resilience trade-off of each.
- Design a **BGP policy** that advertises the customer prefix to both upstreams with different AS-path lengths to influence inbound traffic, and that accepts default routes or full routes from each upstream based on memory and CPU budget.
- Apply **AS-path prepending** with the right number of prepends (typically 2-4 on the backup link) and the right placement (own AS vs. neighbor AS) to bias inbound traffic without breaking routing loops.
- Use **BGP communities** to ask the upstream to do per-prefix traffic engineering (geographic preference, blackhole, DDoS scope) and to verify the upstream honors them with looking-glass queries.
- Implement a **route filter** (prefix-list, AS-path ACL, RPKI ROA, IRR `as-set`) that prevents the customer AS from becoming a transit for traffic between the two upstreams.
- Build a **convergence matrix** that quantifies failover time, BGP damping risk, and BFD-augmented sub-second detection, and design a **verification runbook** with looking-glass checks, looking-glass dig, and `show ip bgp` snapshots.

## The Problem

A regional managed-services company, "Cascade Cloud," runs its production control plane from a single 1,500 sq ft colocation cage in a carrier-neutral facility in the Pacific Northwest. They have outgrown their single-homed 10 Gbps link to "WestLink Telecom" (AS 64500) and have contracted a second 10 Gbps link to "NorthCoast Networks" (AS 64600). The links terminate on two different Cisco Nexus 9300s in the cage, on two different physical routers (CE-A and CE-B), each in its own VRF to keep IGP traffic from leaking into the transit BGP session. The customer AS is 65001 (private), and they advertise 198.51.100.0/24 (a documentation prefix, real customer example) and 203.0.113.0/24 to both upstreams.

The senior network engineer who owns this project must deliver five things: (1) a BGP policy that gives 70% of inbound traffic to WestLink (cheaper, more capacity) and 30% to NorthCoast; (2) a sub-second failover if either link drops; (3) a route filter that prevents Cascade from accidentally transiting traffic between the two upstreams; (4) an RPKI-signed ROA that prevents the prefix from being hijacked; (5) a runbook that the on-call can follow at 3 AM without phoning the senior engineer. The 30% / 70% split is a business decision, not a technical one — it reflects WestLink's cheaper per-Mbps transit cost, NorthCoast's value as a true geographic diverse path, and Cascade's tolerance for NorthCoast being the "hot spare."

A wrong choice in this design is invisible for weeks and then becomes a major incident. AS-path prepending with three prepends that all hit the same ISP, or MED values that the upstream strips before propagating, or a route filter that blocks /32 host routes but accepts /8 supernets, all look correct in staging and break in production. The lesson is to build the policy once, completely, and to test it with a real looking-glass and a real RPKI validator before any production traffic flows.

## The Concept

Multihoming is a **policy problem** dressed up as a routing problem. The two upstreams each see Cascade as one of tens of thousands of customers. They have their own routing policies, their own preferences, and their own ways of being told what Cascade wants. The BGP knobs that Cascade controls — the AS-path, the MED, the communities, the next-hop — are the levers it pulls to influence how the global routing table treats its prefix. The BGP knobs that Cascade does *not* control — the local preference of its upstreams, the upstream's own peer policy, the upstream's RPKI enforcement — are constraints it must design around.

### The four multihoming architectures

The classic taxonomy is from **RFC 4116** ("Security Best Current Practices for Multihomed AS") and the **IETF GROW working group** drafts that preceded it. The four architectures, in order of increasing resilience and cost:

- **Single-homed, single-upstream**: one physical link, one BGP session, one ISP. Cheap and simple, but every outage — link, router, upstream, fiber cut — takes the network off the Internet. This is what Cascade had before this project.
- **Single-homed, dual-upstream, single physical link**: one physical link, two BGP sessions to two ISPs over a single cable. The two ISPs must agree to a "bilateral peering" at the same facility. A single fiber cut or a single router port failure takes both sessions down. Rare in production.
- **Dual-homed, dual-upstream, single physical site**: two physical links to two ISPs, terminated on the same router pair, in the same facility. Survives one ISP link failure, one router failure, and one ISP upstream outage. This is the most common production architecture and is the focus of this lesson.
- **Dual-homed, dual-upstream, dual physical site**: two physical links to two ISPs at two separate facilities (geographic diversity). Survives a facility power outage, a regional fiber cut, and a router-room flood. Expensive (two colocation cages, two fiber paths, two transit contracts) but the only choice for true tier-1 service levels.

Cascade is the third case: dual-homed, dual-upstream, single physical site. They pay for two BGP sessions, two routers, and two transit contracts, but they do not pay for a second cage or a second geographic fiber path. The architecture is good enough for a regional managed-services provider with 99.9% SLA targets and not good enough for a tier-1 carrier with 99.999% targets.

### AS-path prepending and the inbound traffic knob

When BGP selects a route to a prefix, the first tiebreaker is **local preference** (a value that never crosses an AS boundary), the second is **AS-path length** (fewer AS hops wins), and the third is **origin code** (IGP < EGP < incomplete). An AS can manipulate the *advertised* AS-path to influence what its neighbors — and through them, the global routing table — believe is the best path to its prefix.

The classic manipulation is **AS-path prepending**: instead of advertising `AS_PATH = 65001` to both upstreams, Cascade advertises `AS_PATH = 65001 65001 65001` to NorthCoast (the backup). The global table sees that the WestLink path is 1 AS hop and the NorthCoast path is 3 AS hops, so most other networks prefer WestLink, and inbound traffic is biased toward WestLink.

Prepending works because most networks — including both WestLink and NorthCoast and most of their peers and upstreams — run **hot-potato routing** that selects the shortest AS-path. It is *not* a hard policy: an AS that is closer (in AS-path terms) to NorthCoast than to WestLink will still prefer NorthCoast regardless of prepending. The 70% / 30% split is therefore an *aggregate* over all of Cascade's traffic sources, not a guarantee for any individual source.

The number of prepends to use is a tuning problem. Too few (one prepend) and the backup link never gets traffic. Too many (six prepends) and the upstream strips the advertisement as suspicious. The conservative default is 2-3 prepends on the backup link, validated by looking-glass queries at major transit-free networks (Cogent, Hurricane Electric, NTT, Lumen) and at a major content network (Cloudflare, Google, Meta). The lesson's `code/main.py` ships a prepending calculator that recommends 0, 1, 2, 3, 4, or 5 prepends based on the target split and the two ISPs' typical "prepend sensitivity" (a learned parameter, not a standard).

### MED, communities, and the upstream's policy

The other two knobs are **MED** (Multi-Exit Discriminator) and **BGP communities**. MED is sent to a single neighbor to tell it "prefer this path over the other one you have to me." It works only when both ends agree (Cascade and WestLink) and it is honored only when the neighbor's policy includes `bgp always-compare-med` (Cisco) or its equivalent. MED is per-neighbor and does not propagate beyond the neighbor. It is the right knob when the two links go to the *same* ISP; it is the wrong knob when the two links go to *different* ISPs.

**BGP communities** are 32-bit tags that propagate across AS boundaries. Upstreams document the community values they honor — for example, WestLink might say `64500:100` means "prepend this prefix once for inbound traffic engineering," and `64500:200` means "geographic preference: Seattle." Cascade sets the community on its advertisements, the upstream reads it and reshapes its routing policy, and the rest of the Internet sees the result. Communities are the most powerful knob and the most underused: a customer that learns the upstream's community vocabulary can ask the upstream to do sophisticated things (backup-only, DDoS-scoped, geographic, prefix-list-based filtering) without changing its own BGP configuration.

The lesson's planner encodes a community dictionary for two fictional but realistic ISPs, and emits a policy skeleton that uses the right communities to express Cascade's intent.

### Route filtering and the transit-prevention problem

When Cascade has two upstreams, both of which advertise `0.0.0.0/0` (or full routes) to Cascade, Cascade is in danger of becoming a **transit AS** — traffic from WestLink to NorthCoast (or vice versa) flowing through Cascade's network. This is bad for three reasons: (1) Cascade pays for traffic it does not want, (2) it is a violation of most transit contracts, and (3) it makes Cascade a vector for inter-ISP attacks.

The fix is a **route filter** that prevents Cascade from advertising any prefix it did not originate. The filter is built from a list of Cascade's own prefixes (the `198.51.100.0/24` and `203.0.113.0/24` in our example) and rejects everything else. On modern routers the filter is a **prefix-list** with a `permit` for each Cascade prefix and an implicit `deny` for everything else. The lesson's planner generates this prefix-list and emits a verification step that exercises it with negative tests (inject a `/8` and a `/32` and confirm they are rejected).

In addition to the prefix filter, a defense-in-depth approach uses **RPKI ROAs** (Route Origin Authorizations) and **IRR records** (Internet Routing Registry `route:` and `route6:` objects). ROAs are cryptographically signed by the RIR (ARIN, RIPE, APNIC, etc.) and authorize a specific AS to originate a specific prefix. If Cascade's ROA says `198.51.100.0/24 → AS 65001`, then any other AS advertising `198.51.100.0/24` is invalid by RPKI and will be rejected by RPKI-validating upstreams (a growing fraction of the Internet, including all major U.S. and EU transit providers). IRR records are an older mechanism that requires manual lookup and is being superseded by RPKI.

### BFD, BGP graceful restart, and convergence

Failover convergence has two components: **detection time** (how long until the router knows the link is down) and **BGP convergence time** (how long until the alternate path is selected and installed). On a typical fiber link, the physical layer may take 200-500 ms to declare the link down, then BGP's default hold-timer (180 s) waits for the hold-timer to expire before declaring the neighbor down. This is unacceptable for sub-second failover.

The fix is **BFD** (Bidirectional Forwarding Detection, RFC 5880 series). BFD is a lightweight hello/ack protocol that runs in the forwarding plane and can detect a link failure in 50 ms × 3 = 150 ms. When BFD is bound to a BGP session, the BGP hold-timer becomes irrelevant — BGP is told the session is down within 150 ms and immediately tears down the routes. The lesson's planner recommends BFD on both BGP sessions with a 50 ms interval and a 150 ms multiplier, giving sub-200 ms detection.

The second convergence component is the **BGP scanner** and the **best-path calculation**. After the session is down, BGP has to mark all routes from that neighbor as withdrawn, run best-path on the remaining routes, update the FIB, and propagate the withdrawal to other neighbors. On a modern router with hardware FIB update, this is typically 50-200 ms. The lesson's planner models both detection and best-path and reports a "convergence budget" that the on-call can use to set SLA targets.

**BGP graceful restart** (RFC 4724) is a complementary mechanism that preserves forwarding during a *control-plane* restart (router reload, software upgrade) but does not help with a *data-plane* failure. It is enabled by default on most modern routers and is documented in the lesson as a control-plane resilience measure.

### Inbound traffic shaping and the verification problem

Once the BGP policy is written, the verification problem is: does the upstream honor it? Most upstreams document their policy, but the actual propagation depends on the upstream's upstream, on geographic proximity, and on the upstream's local preference. The verification is done with **looking-glass** queries: a looking glass is a public BGP query tool that runs on a major network's router and shows what routes that router sees. The lesson's verification matrix includes looking-glass queries at eight major networks (Cogent, Hurricane Electric, NTT, Lumen, Telia, GTT, Cloudflare, Google) for both Cascade prefixes, and the planner emits a script that runs all eight queries and parses the results.

The planner also encodes a **prefix-hijack detection** step: it checks that no other AS appears as the origin of Cascade's prefixes in any of the looking-glass results, and it queries an RPKI validator (e.g., `routinator` or `rpki-client`) to confirm the ROAs are valid. A hijacked prefix can be detected within minutes if the monitoring is in place; the lesson's runbook includes the email template and the upstream NOC contact list for the hijack notification.

## Build It

The deliverable is `code/main.py`, a deterministic multihoming planner. Inputs are: customer AS, customer prefixes (list of CIDR), two ISP profiles (AS number, AS-path prepend sensitivity, MED honor flag, supported communities), target traffic split (e.g., 70% / 30%), and a list of looking-glass endpoints. Outputs are: a BGP policy skeleton (router-neutral), a prefix-list, a community policy, a BFD configuration, a convergence matrix, a looking-glass query script, and a verification report.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout. The printout includes:

- A **BGP policy skeleton** with one neighbor statement per upstream, with the right remote-AS, the right description, the right route-map in/out, and the right eBGP multihop setting.
- A **prefix-list** with one `permit` per Cascade prefix and an implicit `deny` for everything else.
- A **community policy** with the right community string for each upstream's documented knob (geographic preference, prepend, DDoS scope, blackhole).
- A **BFD profile** with 50 ms interval and 150 ms multiplier.
- A **convergence matrix** showing detection time, BGP best-path time, and total convergence budget for each link.
- A **looking-glass script** with eight `show ip bgp <prefix>` queries at major transit networks.
- A **verification report** with pass/fail criteria for each test.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| BGP policy skeleton | One `neighbor` statement per upstream with remote-AS, description, route-map, eBGP multihop; JSON form parseable | Pass |
| AS-path prepend plan | 0, 1, 2, 3, 4, or 5 prepends recommended; placement (own AS vs. neighbor AS) justified | Pass |
| Prefix-list | One `permit` per Cascade prefix; `deny` implicit; verified against negative tests | Pass |
| Community policy | At least three community knobs documented (geographic, prepend, DDoS) per ISP; community dictionary in the report | Pass |
| BFD profile | 50 ms × 3 multiplier; sub-200 ms detection; bound to both BGP sessions | Pass |
| Convergence matrix | Detection time + best-path time + FIB install time per link; total budget per upstream | Pass |
| Looking-glass script | Eight queries to eight networks; output parseable; parses origin AS from each result | Pass |
| Hijack detection | RPKI ROA validation per prefix; looking-glass origin comparison | Pass |
| Runbook | Cutover checklist, on-call contacts, escalation paths | Pass |

## Ship It

The artifact is `outputs/multihoming_plan.json` plus the printout. The JSON includes the BGP policy, the prefix-list, the community dictionary, the BFD profile, and the convergence matrix. The printout is the human-readable plan that goes to the change-advisory board. The plan is consumed by the FRRouting configuration template generator and by the operational runbook in the lesson's `outputs/runbook.md`.

The output directory should contain:
- `multihoming_plan.json` — the full plan in machine-readable form
- `bgp_policy.conf` — the vendor-neutral BGP configuration skeleton
- `looking_glass_queries.sh` — the eight looking-glass queries as a shell script
- `runbook.md` — the cutover and on-call runbook

## Exercises

1. **Pick a target split and justify it.** Given WestLink at $0.50/Mbps and NorthCoast at $1.20/Mbps, Cascade wants 80% of inbound traffic on WestLink. How many AS-path prepends should be applied to the NorthCoast advertisement? Justify with the typical AS-path-length sensitivity of major transit networks (assume each prepend reduces inbound traffic by ~25-30%).

2. **Design a prefix filter that survives a typo.** Cascade accidentally types `198.51.100.0/8` into the prefix-list (a typo for `/24`). What happens? Design a defense-in-depth filter (prefix-list + RPKI ROA + max-prefix length on neighbor) that catches this.

3. **Build a looking-glass parser.** Take the output of `show ip bgp 198.51.100.0/24` from a looking glass (the format is well-documented and stable) and parse out the origin AS, the AS-path, the next-hop, and the MED. What does the parser do if the route is missing? If the AS-path is empty? If the format changes (e.g., JSON output vs. text)?

4. **Compute convergence time.** Given a 200 ms physical-layer failure detection, 50 ms × 3 BFD, 100 ms BGP best-path, and 50 ms FIB install, what is the total convergence time? At what point does a long-lived TCP session (e.g., SSH, database replication) notice the failure? What application-level mitigation (DPD in IPsec, TCP keepalive, application-level reconnect) is needed?

5. **RPKI state and the hijack scenario.** Cascade's /24 prefix is signed with a ROA. An attacker advertises the same /24 from a different AS with a longer AS-path. Which upstreams reject the attacker's advertisement? Which accept it? What is the residual risk and how is it detected?

6. **Cost-vs-resilience curve.** A second physical site would raise Cascade's multihoming cost from $X/month to $3X/month but would survive a facility power outage. Build a quantitative cost-vs-resilience argument and decide whether the second site is worth it. The decision is a business decision, not a technical one, but the engineer must present the technical and financial facts to the executive sponsor.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| AS-path prepending | "We add our AS multiple times to bias inbound traffic" | Repeating the local AS in the AS-path attribute of a BGP advertisement to make the path look longer to neighbors |
| MED (Multi-Exit Discriminator) | "We tell the upstream to prefer this link" | A non-transitive BGP attribute that influences the upstream's best-path within its own AS |
| BGP community | "A tag the upstream reads to do something" | A 32-bit value carried in a BGP update that an upstream's policy can match on |
| RPKI ROA | "A signed authorization to originate a prefix" | A cryptographically signed object (RFC 6482) that authorizes a specific AS to originate a specific prefix |
| IRR (Internet Routing Registry) | "A public database of routing policy" | A distributed set of databases (RADB, RIPE, ARIN) that publish route and AS-set objects |
| BFD (Bidirectional Forwarding Detection) | "A fast-fail hello protocol" | A lightweight RFC 5880 protocol that detects forwarding-plane failures in milliseconds |
| BGP graceful restart | "BGP survives a router restart" | A RFC 4724 mechanism that preserves forwarding during a control-plane restart |
| Looking glass | "A public view of someone else's router" | A web or CLI interface on a public network that exposes the BGP table for query and debugging |
| Local preference | "The most important tiebreaker" | A BGP path attribute, propagated only within an AS, that overrides AS-path length in best-path selection |
| Transit AS | "A network that carries traffic for others" | An AS that carries traffic between two other ASes; multihomed customers must filter to avoid becoming one |

## Further Reading

- **RFC 4116** — *Security Best Current Practices for Multihomed AS* — the IETF's authoritative document on multihoming security
- **RFC 4271** — *A Border Gateway Protocol 4 (BGP-4)* — the BGP specification
- **RFC 4724** — *Graceful Restart Mechanism for BGP* — graceful restart
- **RFC 5880-5884** — *Bidirectional Forwarding Detection (BFD)* — BFD specification
- **RFC 6480-6487** — *Resource Public Key Infrastructure (RPKI)* — RPKI architecture and ROA format
- **RFC 6810, 6811** — *RPKI to Router Protocol* — how routers fetch RPKI data
- **RFC 8210** — *The RPKI to Router Protocol* — the production protocol
- **Cisco IOS-XE BGP configuration guide** — vendor implementation
- **Juniper Junos BGP User Guide** — vendor implementation
- **FRRouting BGP documentation** — open-source implementation
- **NANOG Multihoming tutorials** — operator-focused best current practice
- **MANRS (Mutually Agreed Norms for Routing Security)** — industry routing-security baseline
- **Hurricane Electric BGP toolkit** — public looking glass and routing tools
