# Implement a Routing Simulator

> A distance-vector and link-state routing simulator is the capstone synthesis of everything you have learned about intra-domain routing in Phases 7-9: shortest-path algorithms (Dijkstra, Bellman-Ford), distance-vector vs link-state trade-offs, count-to-infinity and split-horizon, OSPF LSA flooding, BGP path attributes, and the failure modes that make a real network converge badly. This capstone ships a stdlib-only Python simulator (`code/main.py`) that builds a 12-router topology, runs RIP-style distance-vector with poison reverse, runs OSPF-style link-state with Dijkstra, and exposes an interactive command loop so you can flip links up/down, watch routes recompute, and compare convergence time. The deliverable is a reproducible artifact that demonstrates your understanding of routing convergence, the limits of DV vs LS, and the operational levers (hello timers, SPF delay, hold-down) that real network operators use to keep a network stable.

**Type:** Capstone
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 7 lessons 01-12 (Dijkstra, Bellman-Ford, distance vector, link state, hierarchical routing), Phase 8 (congestion/QoS), Phase 9 (OSPF, BGP), Chapter 5
**Time:** ~180 minutes

## Learning Objectives

- Implement the distance-vector algorithm (Bellman-Ford) with split-horizon and poison-reverse and demonstrate the count-to-infinity problem.
- Implement the link-state algorithm (Dijkstra) with LSA flooding and an explicit LSDB.
- Build a 12-router topology in code with weighted edges, link up/down events, and per-router state.
- Compare convergence time, route flaps, and stability between DV and LS under identical failure scenarios.
- Read routing tables at each router and explain why a particular prefix takes a particular next-hop.
- Identify when each algorithm is appropriate (DV: small/flat networks; LS: large/hierarchical networks) and what real protocols map to each (RIP, EIGRP → DV; OSPF, IS-IS → LS; BGP → path-vector).
- Ship a runnable artifact with documented CLI commands so a teammate can replay your scenarios.

## The Problem

You are the network engineer at NetCove Inc., a mid-sized SaaS company with 12 offices worldwide. Yesterday a regional outage in the Frankfurt office was traced to a routing loop between routers FRA-1, FRA-2, and AMS-1 that lasted 47 seconds before the protocols converged. The post-mortem concluded that the on-call engineer could not answer the basic question "which path is the packet taking right now, and why?" The leadership wants a tool that the on-call rotation can use to reason about routing behavior before the next failure. You are asked to build a routing simulator that models the company's topology, runs both distance-vector and link-state, and lets a human operator flip links to study convergence in a controlled environment.

The deeper issue is that "convergence" is one of those words that looks simple in a textbook and is actually a multi-axis trade-off in practice. Distance-vector protocols are simple to implement and converge quickly on small networks but oscillate and produce count-to-infinity on larger ones unless you add poison-reverse and triggered updates. Link-state protocols converge consistently and predictably but require a synchronized LSDB and SPF delay tuning to avoid thrashing during flapping links. A real network engineer needs to *see* the trade-off, not just read about it. The simulator in this lesson makes the trade-off visible and reproducible.

## The Concept

Source: `chapters/chapter-05-the-network-layer.md`, sections 5.4.x (routing algorithms) and 5.6.x (OSPF). The companion diagram is `assets/implement-a-routing-simulator.svg`.

### The two families of intra-domain routing

Routing protocols split into two algorithm families:

| Family | Algorithm | Examples | Strengths | Weaknesses |
|--------|-----------|----------|-----------|------------|
| Distance-vector (DV) | Bellman-Ford | RIP v1/v2, IGRP, EIGRP (hybrid) | Simple, low memory, no global view | Slow convergence, count-to-infinity, routing loops |
| Link-state (LS) | Dijkstra over LSDB | OSPF, IS-IS | Fast, loop-free after convergence, scales with hierarchy | Higher memory, requires LSA flooding, more complex to implement |
| Path-vector (PV) | Policy-driven | BGP | Policy-rich, scales to internet | Slow convergence, requires policy config |

A good routing simulator must implement at least DV and LS so the operator can compare them head-to-head on the same topology.

### The count-to-infinity problem

A naive DV protocol with no safeguards converges slowly when a link fails. Consider three routers A-B-C in a line with link cost 1 in each direction. The link A-B fails at t=0. A and B do not know about the failure yet. A still advertises "B is 1 hop away" to C. C still advertises "A is 2 hops away" to B. B, having lost its direct path, takes C's word and decides A is now 3 hops away via C. A then takes B's word and decides B is 4 hops away via B. The metric climbs to infinity (or 16 in RIP's case) before the network stabilizes.

The two standard mitigations:

- **Split horizon**: do not advertise a route back to the neighbor from which you learned it. Stops the most common loop, but does not stop loops involving three or more routers.
- **Poison reverse**: advertise the route back to the neighbor with metric 16 (infinity) instead of refusing to advertise. Triggers immediate recomputation in the neighbor.

This simulator implements both so you can compare a "naive" DV (count-to-infinity visible) against a "hardened" DV (poison-reverse triggered, count-to-infinity contained).

### Dijkstra's algorithm and the link-state database

A link-state protocol requires every router to know the entire topology. Each router floods its own link-state advertisement (LSA) to every other router, every router builds an identical link-state database (LSDB), and each runs Dijkstra's shortest-path-first (SPF) algorithm over the LSDB to compute its forwarding table. OSPF's LSA is roughly (router-id, neighbor-id, cost, sequence, age); the LSDB is the union of all LSAs; Dijkstra runs in O(E + V log V) with a Fibonacci heap or O(V²) with a naive priority queue. The simulator implements Dijkstra with a simple O(V²) priority queue and exposes the resulting tree so you can see the path from any router to any prefix.

### Convergence time and route flaps

Convergence time has three components: detection time (how long until a router notices the failure), propagation time (how long until the news reaches everyone), and computation time (how long until SPF recomputes). On a small flat network DV and LS are comparable; on a real network LS is faster and more predictable because propagation is bounded by LSA flooding rather than DV's gossip-style update.

Route flaps occur when a link bounces up/down repeatedly. DV with poisoned reverse will flap wildly because every flap triggers a recompute. LS protocols damp this with SPF throttling (RFC 2328 §10): hold the SPF recomputation for `spf-delay` after the first LSA, then allow at most one recomputation per `spf-hold` interval. The simulator implements a configurable `spf-delay` so you can see its effect on flap stability.

### The CLI surface

The simulator exposes a small interactive command set so a human operator can drive scenarios:

```text
net> topology                      # print the 12-router graph
net> dv-step                       # advance the DV protocol one round
net> ls-step                       # flood one new LSA and recompute SPF
net> link down FRA-1 FRA-2         # cut a link
net> link up FRA-1 FRA-2           # restore a link
net> show dv FRA-1                 # print distance-vector table at FRA-1
net> show ls FRA-1                 # print SPF tree and forwarding table at FRA-1
net> show stats                    # print convergence counters
net> reset                         # reinitialize all protocol state
net> quit                          # exit
```

The shell is a tiny `cmd.Cmd` subclass; you can drive it from `code/main.py` with `python3 main.py` and type commands, or you can script a scenario with `python3 -c "from main import Net; n=Net(); n.link_down(...); print(n.show_dv('FRA-1'))"`.

## Build It

1. Read `code/main.py` and understand the data model: `Router` (id, neighbors, LSDB, DV table), `Link` (a, b, cost, up), `Net` (the simulator with a CLI and a scenario driver).
2. Run the default scenario: `python3 main.py` then type `topology` to see the 12-router graph, then `ls-step` twice to flood initial LSAs, then `show ls FRA-1` to see FRA-1's SPF tree.
3. Cut a link: `link down FRA-1 FRA-2`, then `ls-step` three times, then `show ls FRA-1` to see the new tree. Compare with the pre-failure tree.
4. Compare DV vs LS on a 3-router line topology: switch the topology in the source by editing the `DEFAULT_TOPOLOGY` constant to the line A-B-C, then `link down A B`, then `dv-step` repeatedly with `show dv A` to watch the metric climb to 16. Now switch to the hardened DV (`--hardened` flag) and watch poison-reverse trigger immediate recompute.
5. Run the flap scenario: cut and restore a link 10 times in a row with `spf-delay 0` vs `spf-delay 5` and observe how SPF throttling reduces the number of full recomputations.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Show that LS converges faster than DV on a 12-router topology | Run identical failure scenario against both, count rounds to stable | LS converges in 3-4 rounds; DV takes 8-12 with naive, 4-6 with poison-reverse |
| Demonstrate count-to-infinity | 3-router line, cut A-B, run naive DV, watch metric climb | Metric reaches 16 in 13 rounds |
| Verify poison-reverse works | Same 3-router line, hardened DV | Metric stabilizes at 16 immediately after the failure |
| Show LSA flooding | Step the LS protocol, log every LSA accepted | Every router's LSDB converges to the same set of LSAs |
| Demonstrate SPF throttling | Flap a link 10 times with different `spf-delay` | Larger `spf-delay` reduces SPF recomputation count |
| Build the routing table at a router | `show ls FRA-1` prints the forwarding table | Every destination appears exactly once with correct next-hop |

## Ship It

Produce one artifact under `outputs/`:

- A scenario-driven runbook titled *"NetCove routing post-mortem and convergence playbook"* that walks through: (1) the topology diagram, (2) the failure that caused the 47-second outage, (3) the protocol state at t=0, t=1s, t=5s, t=10s for both DV and LS, (4) the recommended configuration changes (`spf-delay`, `spf-hold`, `lsa-throttle`), and (5) the on-call runbook commands to re-run the scenario on demand.
- Or a 2-page "routing convergence trade-off" cheat sheet for new on-call engineers, with the DV vs LS comparison table and a flowchart of "which protocol to use when" based on the company's growth stage.

Start from [`outputs/prompt-implement-a-routing-simulator.md`](../outputs/prompt-implement-a-routing-simulator.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Run the default 12-router scenario and identify the two routers that act as the "backbone" (highest-degree nodes). Cut all three of their incident links simultaneously. How long does DV take to converge? How long does LS take?
2. Implement triggered updates in the DV protocol (recompute and advertise immediately on a metric change, not just on the periodic 30-second tick). Compare convergence time with the periodic-only baseline.
3. Modify the topology to a 3-router loop A-B-C-A. Show that split-horizon alone is not enough to stop the loop and that poison-reverse is required.
4. Add BGP-style path attributes to the LS protocol: each LSA carries an `as-path` and a `local-pref`. Implement best-path selection: highest `local-pref` wins; ties broken by shortest `as-path`; final tie broken by lowest `router-id`.
5. Add a `route dampening` feature: a flapping route is suppressed for exponentially increasing intervals. Show that this prevents sustained oscillation but introduces black-hole time during which the route is suppressed.
6. Build a "what-if" script that takes a CSV of link-up/down events and a protocol choice (DV, LS, hardened-DV) and outputs a CSV of convergence events. Use it to characterize the worst-case convergence time for your company topology.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Distance-vector (DV) | "routers tell each other what they know" | Each router shares its full routing table with neighbors; relies on Bellman-Ford update rule |
| Link-state (LS) | "every router knows the whole topology" | Each router floods its own links; every router builds a synchronized LSDB and runs Dijkstra |
| Bellman-Ford | "the DV update rule" | For each neighbor, distance = min(cost to neighbor + neighbor's distance); converges in V-1 rounds |
| Dijkstra | "the LS path algorithm" | Greedy shortest-path tree from a source; O(E + V log V) with a heap |
| Count-to-infinity | "the metric keeps climbing" | Failure in DV without poison-reverse: a lost route's metric grows by 1 per round until it hits the protocol's infinity (16 in RIP) |
| Split-horizon | "don't tell A what you learned from A" | DV mitigation: do not advertise a route back to the neighbor from which you learned it |
| Poison-reverse | "advertise infinity back" | DV mitigation: advertise a learned route back to its source with metric 16 to force recomputation |
| LSA | "the link-state advertisement" | A single router's locally-known links; flooded to all other routers in the area |
| LSDB | "the link-state database" | The union of all LSAs in an area; identical on every router in steady state |
| SPF delay | "wait before recomputing" | OSPF throttle: hold SPF recomputation for `spf-delay` after the first LSA change |
| Convergence | "everyone agrees on the topology" | The state where every router's forwarding table is consistent and stable under no further changes |
| Route flap | "the link keeps going up and down" | Repeated state changes on a link; causes excessive recomputation without damping |
| Path-vector | "carry the full path" | BGP's variant of DV where each advertisement carries the AS path; prevents loops without poison-reverse |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 5 §5.4.x — routing algorithms, distance vector, link state.
- RFC 1058 — *Routing Information Protocol* (RIP v1) — the original DV protocol.
- RFC 2328 — *OSPF Version 2* — the canonical link-state protocol; LSA types, flooding, SPF throttle (Section 10).
- RFC 2453 — *RIP Version 2* — adds subnet masks and authentication to RIP.
- Moy, J. T. (1998). *OSPF: Anatomy of an Internet Routing Protocol*, Addison-Wesley — the definitive OSPF reference.
- Huitema, C. (1995). *Routing in the Internet*, Prentice Hall — DV vs LS trade-offs, BGP, route flap damping.
- Perlman, R. (1999). *Interconnections: Bridges, Routers, Switches, and Internetworking Protocols*, 2nd ed., Addison-Wesley — the algorithmic foundations of routing.
- Steenstrup, M. (1995). *Routing in Communications Networks*, Prentice Hall — DV, LS, and path-vector in a single comparative volume.
