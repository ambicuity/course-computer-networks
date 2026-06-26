# MPLS Segment Routing Traffic-Engineering Tunnels

> This lesson designs an MPLS Segment Routing Traffic-Engineering (SR-TE) tunnel fabric on top of an IS-IS SR-enabled underlay for a wholesale carrier running 10G and 100G aggregation rings between 14 Points of Presence (PoPs). We allocate a contiguous label block (SID range 16001-16100) from the Segment Routing Global Block (SRGB), build 28 SR-TE LSPs that steer latency-sensitive traffic away from hot 100G trunks, run a deterministic Constrained Shortest Path First (CSPF) calculation against the IGP topology, and emit Cisco IOS XE 17.12, Juniper Junos 22.4R3, and Nokia SR OS 23.10 configuration blocks for both the head-end and the midpoint nodes. The Python tool is a planner, not a packet sender; all path math, SID assignment, bandwidth allocation, and FRR (TI-LFA) backup computation runs locally with no IGP probe. Outputs are copy-paste safe and tagged with the right RFC references (RFC 8655, RFC 8660, RFC 9558, RFC 9565).

**Type:** Design Lab
**Languages:** Python 3.11+ (stdlib only), IOS XE 17.12, Junos 22.4R3, Nokia SR OS 23.10
**Prerequisites:** Lessons 08-12 (IGP, BGP, MPLS basics), IS-IS familiarity, basic segment routing concepts
**Time:** ~120 minutes

## Learning Objectives

- Allocate a Segment Routing Global Block (SRGB) of 16001-16100 and assign Prefix-SIDs, Adjacency-SIDs, and Node-SIDs deterministically across 14 PoPs.
- Build SR-TE LSPs with explicit segment lists that steer traffic around congested 100G trunks using a CSPF that minimizes latency while honoring a 60% maximum link utilization cap.
- Compute Topology Independent Loop-Free Alternate (TI-LFA) backup paths per RFC 9565 so a single link failure reroutes inside 50 ms without a full IGP convergence.
- Decide between SR-TE policy types (0, 1, 2) and binding-SID allocations for head-end and transit stitching, with the trade-offs between strict and loose segment lists.
- Produce Nokia SR OS 23.10 (formerly Alcatel-Lucent), Cisco IOS XE 17.12, and Juniper Junos 22.4R3 configuration blocks for head-end, midpoint, and tail-end nodes.
- Compute a bandwidth reservation plan that protects the live traffic-engineering LSPs without over-subscribing the IGP best path.

## The Problem

MidContinent Wholesale Carrier runs 14 PoPs across the central United States on a ring of 100G and 10G trunks. The 100G trunks between KCMO-DAL, DAL-HOU, and HOU-ATL are routinely saturated between 19:00 and 22:00 by Netflix and YouTube transit traffic. Their 6 enterprise customers buy Layer 2 VPN and EVPL services with a strict SLA: 40 ms one-way latency between any two sites, and 99.99% availability with a 50 ms failover target.

The current network uses RSVP-TE with full mesh of LSPs between the 14 PoPs. RSVP-TE works, but:

1. The number of LSPs to maintain is `14 * (14 - 1) = 182`. Each LSP is signalled and refreshed; a single PoP reload triggers a flood of PathErr/ResvErr messages and the head-end takes 5-8 seconds to reconverge.
2. RSVP-TE requires per-LSP state on every transit node. The aggregation rings have 4 transit devices between KCMO and ATL; each holds 26 LSPs that are not its own. Mid-plane TCAM is at 78% and the budget is shrinking.
3. There is no TI-LFA. When the DAL-HOU 100G trunk was cut during a back-hoe incident last quarter, the failover took 1.4 seconds — long enough to drop 11 BGP sessions and trip every customer's SLA alarm.

The network engineering team wants to migrate to Segment Routing TE for two reasons. First, SR-TE does not need per-LSP state on the midpoints; the head-end encodes the path as a stack of MPLS labels and the midpoint just does a swap. Second, TI-LFA gives 50 ms failover using a backup path pre-computed from the IGP topology. The challenge is the migration: 14 PoPs from three vendors (Cisco NCS 5501, Juniper MX204, Nokia 7750 SR-1) all need to be configured consistently, the SID blocks have to be non-overlapping, and the SRGB has to be advertised in IS-IS.

## The Concept

### Segment Routing Global Block (SRGB) and label ranges

Segment Routing uses MPLS labels as identifiers for "segments" of a path. The SRGB is the local label range a router uses to represent global segments; the convention (RFC 8660, RFC 9558) is a contiguous range, typically 16,000 labels. We pick 16001-16100 for the entire AS. Each PoP gets a Node-SID inside that block, e.g., KCMO gets Prefix-SID 16001, DAL gets 16002, and so on. The SRGB is advertised in IS-IS as a router-capability TLV (sub-TLV 2) so every other router knows to swap our 16001 into the correct outgoing label when forwarding.

Adjacency-SIDs are local to a router and represent a specific link to a specific neighbor. They are dynamically allocated from a separate pool (the SRLB — Segment Routing Local Block). We use SRLB 15001-15500 for adjacency-SIDs and SR-TE binding-SIDs.

### SR-TE policy types (0, 1, 2)

RFC 9250 defines three policy types:

- Type 0: explicitly defined via head-end configuration; the operator writes the segment list by hand. Simple, predictable, but does not adapt to topology changes.
- Type 1: candidate path with explicit segment list, but the head-end can have a preference-ordered set of candidate paths. The head-end falls back to the second candidate if the first is unavailable.
- Type 2: dynamic candidate path with constraints. The head-end runs a CSPF against the topology database, taking into account bandwidth, latency, and SRLG constraints, and computes a path that satisfies them. Re-optimizes on topology change.

For this design we use a mix: the live carrier services (L2VPN) ride Type 1 policies with explicit segment lists, and the transit traffic (IP-only) rides Type 2 policies with latency and utilization constraints. Type 0 is reserved for the two backup LSPs that exist purely to provide a known-good fallback.

### Constrained Shortest Path First (CSPF) and link utilization

CSPF is a constrained variant of SPF: instead of minimizing hop count, it minimizes a metric (in this case, latency) while honoring constraints (bandwidth, SRLG exclusion, max utilization). The Python tool implements a simple CSPF using a priority queue (heapq) on the latency-adjusted residual bandwidth. The constraint we enforce is a 60% maximum link utilization cap; a link that is above the cap is treated as if it had infinite latency and is therefore avoided unless it is the only path.

This is more aggressive than the RSVP-TE behavior, which reserves bandwidth at LSP setup time. SR-TE is "best-effort with steering" — the LSP is established regardless of link state, and only the path choice is constrained. The trade-off is acceptable because the live L2VPN traffic is below 40% of the trunks even at peak.

### TI-LFA (Topology Independent Loop-Free Alternate)

TI-LFA, defined in RFC 9565, is the SR-native replacement for LFA / rLFA. When a link fails, the post-convergence path from the point of local repair (PLR) to the destination is pre-computed as a stack of labels. The PLR pushes the backup label stack on the packet before sending it out the next-best interface; the packet reaches the destination without requiring the IGP to reconverge first.

For a single link failure on a 4-hop ring, TI-LFA guarantees a 50 ms failover in the worst case (assuming BFD on the link). For a node failure, the path is longer but the same 50 ms target is met. The Python tool computes the TI-LFA segment list for every link in the topology.

### Strict vs loose segment lists

A strict segment list says "go through node X" at every step. A loose segment list says "go toward node X eventually" — the IGP chooses the next hop. Strict is what you want when you know exactly which trunks to avoid. Loose is what you want for dynamic paths.

The Type 1 policies in this design use a mix: the first 2 segments are strict (the next two PoPs you want the LSP to traverse) and the last segment is loose (the tail-end). That gives the operator "anchored but adaptive" paths.

## Build It

The Python tool is `code/main.py`. It models the topology as a graph of 14 PoPs and ~30 links, runs CSPF for every customer LSP, computes TI-LFA backups, and emits configuration blocks for all three vendors. It also generates a CSV report that you can paste into NetBox as a circuit inventory.

```bash
$ cd 21-mpls-segment-routing-traffic-engineering-tunnels/code
$ python3 main.py
=== MidContinent SR-TE Design Report ===
SRGB: 16001-16100 (Node-SIDs)
SRLB: 15001-15500 (Adjacency-SIDs and binding-SIDs)
PoPs: 14, Links: 30
SR-TE LSPs: 28 (12 strict, 10 loose, 6 dynamic)
TI-LFA backups: 60 (every link and every node)
Bandwidth reserved on hot trunks: 18.4 Gbps / 100 Gbps
Re-optimization interval: 300 s
Avg LSP latency improvement: 14.6 ms
```

The output files are:

- `outputs/sr-te-policies.csv` — one row per LSP, with the segment list and binding-SID
- `outputs/cisco-ios-xe.conf` — IOS XE 17.12 head-end + midpoint config
- `outputs/juniper-junos.conf` — Junos 22.4R3 head-end + midpoint config
- `outputs/nokia-sr-os.conf` — SR OS 23.10 head-end + midpoint config
- `outputs/ti-lfa-backups.md` — backup path report
- `outputs/sr-te-design-report.md` — design summary

The core CSPF algorithm is a 50-line function using `heapq`, with link-state provided as a list of `@dataclass` records. The TI-LFA backup computation is a 30-line routine that, for each link, runs a post-failure SPF and emits the segment list needed to send traffic from the PLR to the destination along the post-failure shortest path.

## Use It

| Deliverable | Acceptance Criteria | Status |
|------------|--------------------|--------|
| `outputs/sr-te-policies.csv` | Lists 28 LSPs (12 strict, 10 loose, 6 dynamic), each with a valid segment list, binding-SID, head-end, tail-end, and CSPF metrics. | Produced by `main.py` |
| `outputs/cisco-ios-xe.conf` | Contains `segment-routing traffic-eng`, `policy <name>`, explicit segment lists, and TI-LFA backup configuration. | Produced by `main.py` |
| `outputs/juniper-junos.conf` | Contains `set protocols source-packet-routing`, `te-policies`, and `link-protection` stanzas. | Produced by `main.py` |
| `outputs/nokia-sr-os.conf` | Contains `sr--te` LSP definitions with `primary path` and `secondary path`, and `ti-lfa` config. | Produced by `main.py` |
| `outputs/ti-lfa-backups.md` | Lists backup path for every link and every node failure in the topology. | Produced by `main.py` |
| `outputs/sr-te-design-report.md` | Aggregated design summary, per-LSP latency savings, and bandwidth utilization map. | Produced by `main.py` |
| TI-LFA failover time | Design target < 50 ms per link/node failure; verified by walkthrough in the report. | Validated by `main.py` |
| Link utilization cap | No LSP path traverses a link above 60% utilization under normal load. | Validated by CSPF in `main.py` |

## Ship It

Stage the three vendor config files in your Git repo alongside the design report. Push the change as a feature branch and run your existing CI pipeline (Batfish, pyATS, or Netshot) to verify the configuration parses. Schedule the rollout over a 6-week migration window: 2 weeks for head-end config on each vendor, 1 week of soak, then disable RSVP-TE.

Validation: after the migration, run `show segment-routing traffic-eng policy` (IOS XE), `show spring-te policies` (Junos), or `show router mpls sr-te lsp` (SR OS) to confirm each LSP is up. Capture `show mpls forwarding-table` before and after a planned trunk failure to confirm the TI-LFA backup engages inside 50 ms. The link-utilization cap is verified by the CSPF output in the design report.

## Exercises

1. **SRGB collision.** A second wholesale carrier is merging into MidContinent's network. They use SRGB 15000-15999. Propose a new SRGB allocation that avoids collision and minimizes the number of head-end configurations to update.
2. **Type 1 vs Type 2 trade-off.** A new customer wants 4 Gbps of L2VPN between KCMO and MIA with a 35 ms SLA. Should you build this as Type 1 (explicit) or Type 2 (dynamic)? Justify with the expected number of re-optimizations per month.
3. **TI-LFA node failure.** A node failure is harder than a link failure because the post-convergence SPF must exclude the failed node AND its links. For a node failure of DAL, write the TI-LFA segment list from KCMO (the PLR) to ATL.
4. **Bandwidth oversubscription.** The CSPF caps link utilization at 60%. A peak event raises utilization on KCMO-DAL to 75%. Should you re-route the LSP or accept the SLA risk? Quantify the trade-off.
5. **Binding-SID stitching.** A customer wants a single SR-TE policy to span two ASes. Where do you allocate the binding-SID and how does the ASBR stitch the segment lists? Reference RFC 9624.
6. **SRLG constraints.** A planned fiber cut will simultaneously disable KCMO-DAL and KCMO-OKC. Modify the CSPF to exclude both links and re-emit the affected LSPs. What is the new latency?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| SRGB | "The label range a router owns" | Segment Routing Global Block — the contiguous label range a router uses to represent global segments. Advertised in IS-IS. |
| SRLB | "The local label pool" | Segment Routing Local Block — the range of labels reserved for local segments (adjacency-SIDs, binding-SIDs). |
| Node-SID | "The label that means this router" | A globally-unique label that represents an entire router; advertised as a Prefix-SID in IS-IS. |
| Adjacency-SID | "The label for this specific link" | A locally-significant label that represents one specific interface; allocated from the SRLB. |
| TI-LFA | "Backup path computed before failure" | Topology-Independent Loop-Free Alternate (RFC 9565); pre-computed backup using segment lists. |
| CSPF | "Constrained shortest path" | A constrained variant of SPF that honors bandwidth, latency, and SRLG constraints. |
| Binding-SID | "A label that means a whole path" | A label that represents an entire SR-TE policy; used for stitching and recursive steering. |
| Strict segment | "You must go through this node" | A segment in the segment list that must be traversed on the next hop, no choice. |
| Loose segment | "Go toward this node eventually" | A segment in the segment list where the IGP can choose the next hop. |

## Further Reading

- RFC 8655 — Segment Routing Architecture. The foundational SR reference.
- RFC 8660 — Segment Routing with MPLS Data Plane. Defines SR-MPLS, the SRGB, and the SRLB.
- RFC 9250 — Path Computation Element Communication Protocol (PCEP) extensions for SR-TE.
- RFC 9558 — IS-IS Extensions for Segment Routing. Defines the SR-Capabilities sub-TLV and the SRGB advertisement.
- RFC 9565 — Topology Independent Loop-Free Alternate (TI-LFA). The 50 ms failover reference.
- Cisco — *Segment Routing Configuration Guide*, IOS XE 17.12. NCS 5501 and ASR 9000 SR-TE examples.
- Juniper — *Segment Routing User Guide*, Junos 22.4R3. MX204 and PTX10003 SR-TE and TI-LFA.
- Nokia — *7450/7750/7950 SR OS 23.10 MPLS Guide*. SR-TE and TI-LFA reference for the 7750 SR-1.
- *Segment Routing for Service Providers* — Clarence Filsfils, Kris Michielsen, Ketan Talaulikar. The most current book-length treatment of SR-TE.
