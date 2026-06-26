# OSPF Multi-Area Convergence and LSA Throttling

> OSPF is the IGP of choice for most enterprise and service-provider cores because it converges fast, supports hierarchical area design, and is implemented by every router vendor with stable, deterministic behavior. This lesson walks the OSPFv2 protocol as specified in RFC 2328 (OSPF Version 2) plus the throttling extensions in RFC 4136 and the demand-circuit extensions in RFC 1793, and turns the protocol into a runnable Python simulator that models multi-area link-state databases (LSDBs), LSA type propagation across Area Border Routers (ABRs), Dijkstra Shortest Path First (SPF) runs, and the LSA throttling / SPF throttling timers that determine how quickly a network reconverges after a link event. The deliverable is a deterministic report showing which routers run SPF after a simulated failure, how many Type 1 (Router) and Type 3 (Summary) LSAs are re-flooded, and what the worst-case convergence time would be on a 50-router area running on Cisco IOS-XE, Juniper Junos, Arista EOS, or FRR.

**Type:** Project
**Languages:** Python (stdlib only: dataclasses, heapq, itertools, json, statistics)
**Prerequisites:** Phase 7 (Network Layer Design and Routing — OSPF single-area), Phase 16 (Anycast and High Availability — IGP convergence theory)
**Time:** ~150 minutes

## Learning Objectives

- Model an OSPF multi-area topology with backbone Area 0, one or more non-backbone areas (Area 1, Area 2), ABRs, ASBRs, and internal routers, and identify which LSA types each role originates.
- Simulate LSDB construction for Router LSAs (Type 1), Network LSAs (Type 2), Summary LSAs (Type 3), Summary ASB LSAs (Type 4), and External LSAs (Type 5), and prove that Area 0 carries the summary LSA traffic for all inter-area prefixes.
- Compute the number of Dijkstra SPF runs triggered per router per topology event, and explain why an area's internal failure does not cause every router in the network to run full SPF — only routers in the affected area plus ABRs that re-originate summary LSAs.
- Size LSA throttling (`timers throttle lsa`) and SPF throttling (`timers throttle spf`) values against a target convergence budget — for example, 200 ms sub-second convergence on a 50-router area — using the RFC 4136 initial / maximum / hold formula.
- Compute the LSA refresh / MaxAge budget (RFC 2328 §12, 30 minute default refresh, 60 minute MaxAge) and explain why a misconfigured LSA lifetime causes premature aging and constant SPF runs.
- Output a convergence report as JSON that lists SPF runs per router, LSA counts per area, and the worst-case convergence time after a simulated link failure.

## The Problem

A mid-sized financial services company has a campus and two data centers connected by a dual-area OSPFv2 design: Area 0 (backbone) at the data centers, Area 1 (campus east), Area 2 (campus west), Area 10 (DMZ), and a stub Area 99 (branch WAN aggregation). The IGP runs on Cisco ASR 9000 aggregation routers at the core, Juniper MX204 routers at the edge, Arista 7800R3 switches in the data-center spines, and FRR on white-box servers running as route reflectors. Each area has between 8 and 50 routers, with MTU 9000 jumbo frames on the intra-area links and BFD at 50 ms intervals on every inter-router link.

The senior network engineer is measured on three KPIs:

1. Failure-to-converge — after any single link or single router failure, every router in the network must reach a stable FIB within 200 ms at the data-center core and 1 second at the campus edge.
2. SPF run budget — no router should run more than one full Dijkstra per 200 ms under normal flap conditions, because every SPF run consumes CPU and risks transient routing loops.
3. LSDB stability — the Area 0 LSDB must stay under 2,000 LSA entries, because Type 3 Summary LSAs from many areas can choke the shortest-path tree.

A recent incident: a flapping access ring at a branch triggered 4,000 SPF runs in 90 seconds on the data-center ABRs, exhausting CPU and causing 600 ms of packet loss on the trading floor. The root cause was missing LSA throttling and SPF throttling on the FRR route reflector cluster. This lesson builds the simulator that would have caught that misconfiguration in design review.

## The Concept

OSPF is a link-state protocol: every router floods its locally-attached links as LSAs (Link State Advertisements), every router in the area assembles the LSAs into a Link-State Database (LSDB), and every router runs Dijkstra's algorithm on the LSDB to compute a loop-free shortest-path tree. OSPF adds areas to bound the flooding and SPF scope, and adds throttling to bound the CPU consumed by repeated SPF runs. The lesson works through each of those pieces.

### OSPF LSA types and their flooding scope

The five core LSA types from RFC 2328 (plus Opaque LSAs from RFC 5250) determine what a router learns about the network:

| Type | Name | Originated by | Flooded into | Purpose |
|---|---|---|---|---|
| 1 | Router LSA | Every router | Intra-area only | Describes router's links and stub networks within an area |
| 2 | Network LSA | DR on multi-access segments | Intra-area only | Lists all routers attached to the segment |
| 3 | Summary LSA | ABR | Inter-area (into other areas) | Describes an inter-area prefix |
| 4 | Summary ASB LSA | ABR | Inter-area | Locates the ASBR outside the area |
| 5 | External LSA | ASBR | Flooded to all areas except stubs | Describes a redistributed route (BGP, static, connected) |
| 7 | NSSA External | ASBR in NSSA area | NSSA only, translated to Type 5 at ABR | Like Type 5 but for Not-So-Stubby Areas |
| 10/11 | Opaque | Any router | Area-wide (10) or link-local (11) | Used for MPLS TE, traffic engineering, segment routing |

The flooding scope is the load-bearing concept. A Type 1 Router LSA never leaves its area. A Type 3 Summary LSA is the only way an internal route in Area 1 becomes visible in Area 2 — the ABR takes the Type 1 from Area 1, runs SPF (or partial SPF), and originates a Type 3 into Area 0 which then propagates to Area 2. If you design Area 0 badly, every inter-area prefix becomes a Type 3 across every ABR — and a flapping link in Area 1 means every ABR re-originates Type 3, every router in Area 2 and Area 0 runs partial SPF, and CPU spikes.

### Area types and their LSDB contents

| Area Type | LSA Types Allowed | Default Route | External Routes |
|---|---|---|---|
| Backbone (0) | All | No | Yes |
| Standard | 1, 2, 3, 4, 5 | No | Yes |
| Stub | 1, 2, 3 | Injected by ABR | No |
| Totally Stubby | 1, 2 (3 = default only) | Injected by ABR | No |
| NSSA | 1, 2, 3, 4, 7 | No | Yes (as Type 7) |
| Totally NSSA | 1, 2 (3 = default only), 7 | Injected by ABR | Yes (as Type 7) |

For the simulator, we model standard and stub areas. The user supplies a list of areas, each with internal routers and an ABR pair, and the simulator generates the LSDB for each area and the Type 3 traffic between areas.

### Throttling timers (RFC 4136)

RFC 4136 "OSPF Refresh and Flooding Reduction in Stable Topologies" introduced the start-interval, hold-interval, max-interval throttling triplet that all four major vendors adopted. The formula is:

```
delay(t+1) = min(max-interval, delay(t) * 2)
delay(0)  = start-interval
```

When a topology event occurs:

1. The router schedules an LSA generation in `start-interval` (default 0 ms — generate immediately).
2. While events keep arriving, each new generation is held for `delay(t)`, which doubles each time until it reaches `max-interval`.
3. The router waits `hold-interval` (default 5 s) after the last received event before allowing the delay to decrease again.

Cisco's defaults are `start-interval 0 ms`, `hold-interval 5000 ms`, `max-interval 5000 ms` (i.e. flat). Juniper's defaults are `start-interval 50 ms`, `hold-interval 200 ms`, `max-interval 5000 ms`. Arista's defaults are similar to Cisco. FRR's defaults are `start-interval 50 ms`, `hold-interval 200 ms`, `max-interval 5000 ms`. The lesson's planner recommends explicit values for a 200 ms convergence target:

- start-interval 50 ms — first LSA goes out immediately on event
- hold-interval 200 ms — allow at least one more event in 200 ms before backing off
- max-interval 5000 ms — never wait more than 5 s for next LSA generation

For SPF throttling, the same triplet applies but to the Dijkstra run:

- start-interval 50 ms
- hold-interval 200 ms
- max-interval 5000 ms

The simulation verifies whether these settings achieve the convergence budget under a worst-case flap pattern.

### SPF run mechanics and partial SPF

OSPF does not always run a full Dijkstra on every LSA change. Two optimizations matter:

- Partial SPF (RFC 2328 §16.5) — when a Type 3 Summary LSA changes, only the inter-area tree is recomputed, not the intra-area tree. This is dramatically cheaper.
- Incremental SPF (iSPF, Cisco proprietary, also in FRR and Junos) — only the changed subtree is recomputed. Even cheaper.

The simulator counts full SPF runs vs partial SPF runs so the report shows where the CPU goes. A flapping link in Area 1 causes:

1. The router on the flapping link re-originates a Type 1 LSA every `start-interval` (50 ms initially).
2. Every router in Area 1 receives the Type 1, runs intra-area SPF (full Dijkstra) on the changed subtree.
3. The ABR re-originates a Type 3 Summary LSA into Area 0 every `start-interval`.
4. Every router in Area 0 and every other area receives the Type 3, runs partial SPF only.

So an Area 1 flap causes full SPF in Area 1 (bad) and partial SPF everywhere else (cheap). The lesson teaches you to keep the full-SPF scope small by bounding area size and to keep partial-SPF cost down by bounding the number of areas.

### LSA refresh, MaxAge, and premature aging

Every LSA has an LSA age field that starts at 0 and is incremented by each router that re-floods it. RFC 2328 §12 specifies:

- LSRefreshTime = 30 minutes — the originator re-originates the LSA every 30 minutes to keep age from drifting.
- MaxAge = 60 minutes — if the LSA reaches 60 minutes without a refresh, it is purged.
- MaxAgeDiff = 15 minutes — if the received LSA's age differs from the local clock by more than 15 minutes, the LSA is rejected as suspicious.

A misconfigured LSA lifetime (for example, an FRR box running `refreshtime 10` instead of `refreshtime 1800`) causes premature aging and constant SPF runs. The simulator checks for this by computing the total LSA count and the refresh storm rate.

### Convergence math and the 200 ms target

For a sub-200 ms convergence target:

1. Detection — BFD at 50 ms × 3 = 150 ms maximum to detect a silent failure (or physical detection in ~10 ms on most optical interfaces).
2. LSA generation — start-interval 50 ms = 50 ms first generation.
3. Flooding — typically 5-20 ms for a single LSA to traverse a fully-meshed area with sub-millisecond links.
4. SPF computation — typically 1-50 ms on a 50-router area on a modern CPU (Cisco IOS-XE on ASR 9000 reports < 5 ms for 1,000 LSAs).
5. RIB / FIB update — typically 50-200 ms for full table updates; sub-millisecond for incremental.

Total: 150 + 50 + 20 + 50 + 50 = ~320 ms worst case, achievable in practice with sub-millisecond inter-router links, 50 ms BFD, 50 ms start-interval, and incremental FIB updates. The simulator verifies whether the topology meets this budget.

## Build It

The deliverable is a single Python module at `code/main.py` that builds a multi-area OSPF topology from a Python spec, simulates LSA flooding and SPF runs for a sequence of topology events, and emits a convergence report as JSON plus a human-readable summary.

Run it: `python3 code/main.py`. The output includes:

- The LSDB per area — number of Type 1, Type 2, Type 3, Type 4, Type 5 LSAs in each area.
- The Type 3 fan-out — for each inter-area prefix, which ABRs originate a Type 3 and how many routers consume it.
- A simulated link-failure event — a configurable link goes down, the simulator computes how many routers run full SPF, how many run partial SPF, and the simulated wall-clock convergence time using the configured throttling timers.
- A simulated flapping event — the same link flaps N times in T seconds; the simulator computes the total SPF runs and the throttle curve.
- A convergence budget verdict — green / yellow / red against the 200 ms (data center) and 1 second (campus) targets.
- An LSA refresh budget — the expected per-hour LSA refresh traffic across the network.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| `report.json` — LSDB per area | Type 1, 2, 3, 4, 5 counts per area, total < 2,000 LSA in Area 0 | Generated |
| `report.json` — Type 3 fan-out | One Type 3 per inter-area prefix per ABR | Generated |
| Convergence simulation — single failure | Full SPF runs <= 50 per router per event, partial SPF runs counted | Generated |
| Convergence simulation — flap | Total SPF runs in 60 s <= 100 per router (FRR default would be 1,000+) | Generated |
| Throttling recommendation | start 50 ms, hold 200 ms, max 5,000 ms explicitly justified vs. target | Generated |
| Convergence budget verdict | Sub-200 ms data-center / sub-1 s campus verified or flagged | Generated |
| LSA refresh budget | Refresh storm rate < 100 LSA/s on Area 0 ABR | Generated |
| Vendor config snippet | Cisco IOS-XE `timers throttle lsa/spf` and FRR equivalent | Generated |

## Ship It

The artifact is `outputs/report.json` plus `outputs/convergence-summary.txt`. The JSON is the design-of-record for the throttling and area design, suitable for a change-control meeting or a vendor-support call. The summary is the executive one-pager showing the convergence verdict, the throttling recommendation, and the area sizing check.

To regenerate after a topology change: edit the `TOPOLOGY` and `EVENTS` lists at the top of `code/main.py` and re-run. The output is deterministic — same topology produces the same SPF count.

## Exercises

1. Three-area design — design a topology with Area 0 (data center, 4 ABRs, 20 internal routers), Area 1 (campus east, 30 routers), Area 2 (campus west, 30 routers). Run the simulator and verify that a link flap in Area 1 does not cause full SPF in Area 2.

2. Stub-area trade-off — convert Area 1 to a totally stubby area (Cisco) and re-run. Verify that the LSDB in Area 1 drops to Type 1, 2, and a default Type 3, and that the ABR's CPU drops.

3. Throttling tuning — change the `SPF_MAX_INTERVAL` from 5,000 ms to 1,000 ms and re-run the flap scenario. Predict and verify whether the convergence improves or whether the SPF storm gets worse.

4. NSSA with redistribution — add an Area 99 (NSSA) with an ASBR that redistributes 5,000 BGP routes. Verify that the Type 7 LSAs are translated to Type 5 at the ABR and that the Area 0 LSDB stays under 2,000 LSAs.

5. MaxAge sweep — set `LS_REFRESH_TIME` to 600 s (instead of 1,800 s) and verify that the LSA refresh storm rate triples. Then predict what happens at 60 s.

6. BGP-free core — replace OSPF in Area 0 with BGP-only (RFC 7938) and verify that Area 1 still has full reachability through the ASBR at the ABR. The simulator can be extended by adding a flag to skip SPF in Area 0 when BGP carries the prefixes.

## Key Terms

| Term | Definition |
|---|---|
| LSA | Link State Advertisement — the unit of OSPF topology distribution, typed 1-5 plus 7 (NSSA) and 10/11 (Opaque). |
| LSDB | Link-State Database — the collection of all LSAs a router has received for an area. |
| ABR | Area Border Router — router with interfaces in two or more OSPF areas, one of which is Area 0. |
| ASBR | Autonomous System Boundary Router — router that redistributes routes from another protocol (BGP, static) into OSPF. |
| SPF | Shortest Path First — Dijkstra's algorithm run on the LSDB to compute the shortest-path tree. |
| Stub Area | An OSPF area that blocks Type 5 External LSAs and substitutes a default route. |
| NSSA | Not-So-Stubby Area — like a stub area but allows redistribution as Type 7 LSAs that the ABR translates to Type 5. |
| BFD | Bidirectional Forwarding Detection — sub-second failure detection at Layer 3. |
| Throttling | Bounding the rate of LSA generation or SPF computation using start / hold / max intervals. |
| Flooding | The reliable distribution of LSAs across all routers in an area using LSA Acknowledgement packets. |

## Further Reading

- RFC 2328 — OSPF Version 2. J. Moy. April 1998. The foundational standard.
- RFC 4136 — OSPF Refresh and Flooding Reduction in Stable Topologies. P. Pillay-Esnault. July 2005. Defines the throttling timers.
- RFC 1793 — Extending OSPF to Support Demand Circuits. J. Moy. April 1995. The basis for suppressing periodic refresh on demand links.
- RFC 3101 — The OSPF Not-So-Stubby Area (NSSA) Option. P. Murphy. January 2003.
- RFC 5250 — The OSPF Opaque LSA Option. L. Berger. July 2008. Defines LSA types 10, 11, 12.
- Cisco IOS-XE OSPF Configuration Guide — `timers throttle lsa` and `timers throttle spf` command reference.
- Juniper Junos OSPF User Guide — `set protocols ospf overload` and throttle knobs.
- Arista EOS OSPF Configuration Guide — `router ospf` and throttle defaults.
- FRR OSPF documentation — `ospfd.conf` and `timers throttle spf` syntax.
- Cisco Press, "OSPF: Anatomy of an Internet Routing Protocol" — John T. Moy (author of RFC 2328), the canonical textbook.
