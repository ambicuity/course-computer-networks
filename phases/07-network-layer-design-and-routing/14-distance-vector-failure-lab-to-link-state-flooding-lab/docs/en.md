# Distance Vector Failure Lab to Link State Flooding Lab

> Two families dominate interior gateway routing: **distance-vector** (Bellman-Ford, the family of RFC 2453 RIP and RFC 1058 RIP) and **link-state** (Dijkstra over a flooded topology, the family of RFC 2328 OSPFv2 and ISO 10589 IS-IS). This lab makes both *fail* and *recover* in front of you. You trigger the **count-to-infinity** problem on a three-router line — B and C raise their metric to A one hop per round until it hits RIP's magic value **16 = infinity**, a loop that can persist for tens of seconds at the default **30 s** update interval. You then apply **split horizon** and **poisoned reverse** to bound that loop, and add **hold-down timers** and **triggered updates** to accelerate bad-news propagation. Switching families, you build a link-state node that floods **Link State Advertisements** (LSAs), de-duplicates them by `(origin, sequence number)`, ages them via the **LSAge** field toward **MaxAge = 3600 s**, and runs **Dijkstra's shortest-path-first** (SPF) over the synchronized **link-state database** (LSDB). By the end you can state precisely *why* a link-state network reconverges in a handful of flooding hops where distance-vector counts toward 16 — and you ship a simulator that prints both behaviors side by side.

**Type:** Build
**Languages:** Python (stdlib only — Bellman-Ford, flooding, and Dijkstra hand-rolled)
**Prerequisites:** Phase 7 lessons on IPv4 forwarding, longest-prefix match, and the network-layer service model
**Time:** ~90 minutes

## Learning Objectives

- Trace a **count-to-infinity** loop step by step on a 3-router line topology and explain why each round only improves the metric by 1.
- Apply **split horizon** and **poisoned reverse** to a distance-vector update and predict exactly which routes are suppressed or poisoned to metric 16.
- Implement reliable **LSA flooding** with `(origin, sequence number)` de-duplication and justify why a node must *not* re-flood an LSA it already holds.
- Run **Dijkstra's SPF** over a link-state database and produce a forwarding table with next-hops, then show it matches the distance-vector answer in steady state.
- Quantify convergence: count update rounds for distance-vector versus flooding hops for link-state on the same topology.

## The Problem

A core link in a small ISP goes down at 14:02:11. The operations channel lights up: a customer prefix is unreachable, but `traceroute` shows packets bouncing between two routers — the same two hops repeating until the **8-bit TTL** field in the IPv4 header (RFC 791) hits zero. This is a **transient routing loop**: thirty seconds later it clears on its own. The on-call engineer must answer two questions an exam never asks but an outage always does. First: *why did a loop form at all, when every router was just running its protocol correctly?* Second: *would a different routing protocol have looped, or reconverged cleanly?*

The answer lives in the difference between **distance-vector** ("tell your neighbors what you know about everywhere") and **link-state** ("tell everyone what you know about your neighbors"). Distance-vector routers trust their neighbors' summaries without seeing the topology behind them, so bad news travels slowly and good-but-stale news can be believed. Link-state routers each hold an identical map and compute their own paths, so a single failure floods to everyone and each node recomputes independently. This lab reproduces both protocols in `code/main.py` so the loop is not a story — it is output you read line by line.

## The Concept

### Distance-vector: Bellman-Ford over a vector of (destination, cost)

Each node keeps a **distance vector**: for every known destination, the best cost it has found and the neighbor (next-hop) that offered it. On each round a node sends its vector to every neighbor. A receiver runs the Bellman-Ford update for each advertised destination `d` from neighbor `n`:

```
new_cost(d) = cost_to(n) + advertised_cost(n, d)
if new_cost(d) < table[d].cost:   adopt n as next-hop, store new_cost
```

There is no map. Node B believes "A is 1 away via A" purely because A *said so*. That trust is what breaks.

### The count-to-infinity failure (worked example)

Take the line `A — B — C`, all link costs 1. Steady state: C reaches A at cost 2 via B. Now the `A—B` link fails. B should mark A unreachable — but C is still advertising "I can reach A at cost 2." B has no map to know C's path to A *runs through B*, so it believes C and installs A at cost 3 via C. Next round B advertises that, C raises its estimate, B raises its estimate, and the cost climbs **one per round** toward infinity. The SVG (`assets/distance-vector-failure-lab-to-link-state-flooding-lab.svg`) renders this as a staircase.

| Round | B's cost to A | C's cost to A | Comment |
|------:|--------------:|--------------:|---------|
| 0 | 1 (via A) | 2 (via B) | steady state |
| 1 | 3 (via C) | 2 (via B) | B believes C's stale route |
| 2 | 3 (via C) | 4 (via B) | C believes B's new route |
| 3 | 5 (via C) | 4 (via B) | climbing |
| … | … | … | until cost reaches **16 = infinity** |

RIP caps this at metric **16** so the loop terminates instead of running forever — that is the entire reason RIP's maximum network diameter is **15 hops**. With the default **30 s** update timer, reaching 16 can take many quiet seconds, and during all of them packets loop. `code/main.py` runs this loop and prints each round.

### Split horizon and poisoned reverse

**Split horizon**: never advertise a route back to the neighbor you learned it from. C learned A *via B*, so C does not tell B "I can reach A" at all — B never gets the stale route, and the loop on the `A—B` failure cannot start.

**Poisoned reverse** is the stronger form: instead of silently omitting the route, C advertises it back to B with cost **16 (infinity)**. Explicit poison beats silence because it overrides any race where B briefly believed a leftover route. The trade-off is advertisement size — every route is echoed back poisoned, so vectors grow.

| Technique | What C tells B about A | Loop on A—B failure? |
|-----------|----------------------|----------------------|
| Naive | "cost 2" | Yes — count to infinity |
| Split horizon | (omitted) | Prevented on this 2-party loop |
| Poisoned reverse | "cost 16 (unreachable)" | Prevented, and faster to converge |

Neither fully solves loops involving **three or more** routers; that is why production networks lean on link-state or path-vector (BGP carries the full AS_PATH, RFC 4271, so a router rejects any route whose path already contains itself).

### Hold-down timers and triggered updates

Two more distance-vector band-aids. A **hold-down timer** keeps a recently-invalidated route in the table at infinity for a fixed interval (RIP default **180 s**) so a stale advertisement arriving during the window is ignored. A **triggered update** sends a partial vector the instant a route changes rather than waiting for the next **30 s** full update, so bad news starts propagating immediately. Both reduce the window in which count-to-infinity can run, but neither changes the fundamental trust model that causes it.

### Link-state fundamentals: flood the topology, compute locally

A link-state node does the opposite of distance-vector. It builds a **Link State Advertisement** describing only its own directly-attached links and their costs, then **floods** it to every neighbor. Each node collects all LSAs into a **Link State Database (LSDB)**. When every node holds the same LSDB, every node runs the same algorithm and gets a consistent, loop-free result. OSPF calls the unit an LSA; IS-IS calls it an LSP. A simplified OSPF Router-LSA field layout:

```
+-----------------+-----------------+
|     LS Age      |  Options | Type | LS Age counts up to MaxAge=3600
+-----------------+-----------------+
|        Link State ID (router)    |
+-----------------------------------+
|         Advertising Router        | origin
+-----------------------------------+
|        LS Sequence Number         | 0x80000001 .. 0x7FFFFFFF, monotonic
+-----------------+-----------------+
|   LS Checksum   |    Length       |
+-----------------+-----------------+
|  #Links | for each link: id,data,|
|         | type, metric (cost)     |
+-----------------------------------+
```

### LSA structure and the fields that matter

The fields that do the real work in this lab: **Advertising Router** identifies the origin so a node can tell two LSAs from different routers apart; **LS Sequence Number** is a monotonic per-origin counter so a node can tell two generations of the same origin's LSA apart; **LS Age** counts seconds from 0 toward **MaxAge = 3600**, and an LSA re-flooded at MaxAge tells everyone to purge it. The origin refreshes its own LSA every **LSRefreshTime (1800 s)** so good entries never age out. The **LS Checksum** catches corruption in transit — if it fails the LSA is dropped and re-requested.

### Sequence numbers and aging: the loop-breaker and the garbage collector

Flooding without a stop condition would loop forever. The rule, implemented in `code/main.py`'s `flood()`:

1. On receiving an LSA, look it up by `(advertising_router, sequence_number)`.
2. If the sequence is **newer** than what you hold, install it and re-flood out *every* interface **except the one it arrived on**.
3. If it is the **same or older**, drop it — do **not** re-flood. (An older copy triggers sending *your* newer copy back, so the laggard catches up.)

The sequence number is the loop-breaker. Without it, two neighbors would bounce the same LSA back and forth forever. With it, every node sees each LSA exactly once per generation, and flooding terminates in at most *diameter* hops. Aging is the garbage collector: if an origin crashes and stops refreshing, its LSA's age climbs to MaxAge and the network purges it, so a dead router's links leave the LSDB rather than lingering forever.

### Reliable flooding on the 4-node ring

`code/main.py` builds an `A—B—C—D` ring and floods one node's LSA. The hop count to reach all four nodes is the ring diameter — two hops, three at most. Every node de-duplicates by `(origin, sequence)`, so the same LSA is never re-flooded twice. Contrast: in distance-vector the *information* that A lost its link to B would have to propagate one hop per round; in link-state the *fact* (the LSA) reaches everyone in a single flooding wave.

### Dijkstra SPF over the database

Once the LSDB is synchronized, each node runs **Dijkstra's shortest-path-first** rooted at itself:

```
dist[self]=0; visited={}
while unvisited nodes remain:
    u = unvisited node with smallest dist
    mark u visited
    for each (u, v, cost) in LSDB:
        if dist[u] + cost < dist[v]:
            dist[v] = dist[u] + cost; first_hop[v] = first_hop[u] or v
```

The output is a forwarding table of `(destination → next-hop, cost)`. Because every node ran the *same* algorithm over the *same* database, the next-hops are mutually consistent — no two routers disagree, so **no micro-loops** form once flooding completes. On the `A—B—C—D` ring, a single link failure floods one new LSA to all nodes in 2–3 hops, and every node recomputes in microseconds. Compare that to distance-vector counting toward 16.

### Comparison: DV vs LS failure recovery

| Property | Distance-vector | Link-state |
|----------|-----------------|------------|
| What is advertised | Conclusions (cost to dest) | Facts (my links and costs) |
| Loop risk | High — trust + stale routes | Low — Dijkstra is loop-free on same LSDB |
| Convergence after failure | O(diameter) rounds, 30 s each | O(diameter) flooding hops + µs SPF |
| State per node | vector per neighbor (small) | whole topology LSDB (large) |
| Bandwidth | periodic full vectors | event-driven LSAs, smaller per event |
| Example protocol | RIP (RFC 2453), IGRP | OSPF (RFC 2328), IS-IS (ISO 10589) |

Distance-vector advertises **conclusions** without the **reasoning**. A neighbor cannot detect that adopting the route would create a cycle. Link-state advertises **facts** and lets every node derive conclusions from the full map, where Dijkstra structurally cannot produce a cycle. The cost is state: link-state floods O(links) data to every node and stores the whole topology; distance-vector stores only a vector per neighbor. That trade — convergence speed and loop-freedom versus memory and flooding overhead — is the central design choice of interior routing.

## Build It

`code/main.py` is one stdlib-only program with three demonstrations:

1. **`run_count_to_infinity()`** — builds the `A—B—C` line, fails the `A—B` link, and prints each Bellman-Ford round so you watch B and C climb toward metric 16.
2. **`run_split_horizon()`** — repeats the same failure with poisoned-reverse enabled and shows the loop never starts.
3. **`run_link_state()`** — builds a 4-node ring, floods every node's LSA, de-duplicates by `(origin, sequence)`, prints flooding hops, then runs Dijkstra at one node and prints the forwarding table.

Steps:

1. Run `python3 main.py` and read the count-to-infinity staircase first.
2. Find the `INFINITY = 16` constant and the Bellman-Ford update; confirm the cost rises by 1 each round.
3. In `flood()`, find the `(origin, sequence)` de-dup check — comment it out and watch flooding never terminate (then restore it).
4. Read the Dijkstra table and verify, by hand, that it matches the steady-state distance-vector answer for the same graph.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Trigger count-to-infinity | Per-round cost printout for B and C | Each round increases the metric by exactly 1 until it hits 16 |
| Apply poisoned reverse | Updated vectors with the reverse route at cost 16 | The loop never starts; convergence completes in one or two rounds |
| Flood LSAs reliably | Hop count and de-dup drops logged | Every node receives each LSA once; flooding stops after ~diameter hops |
| Compute SPF | Dijkstra forwarding table at one node | Next-hops are consistent and match the distance-vector steady state |
| Compare convergence | Rounds-to-converge for DV vs LS | LS reconverges in a few flooding hops; DV counts toward 16 |

## Ship It

Produce one artifact under `outputs/`:

- A side-by-side convergence report: distance-vector rounds vs link-state flooding hops on the same failure.
- A one-page runbook: "spotted a transient TTL-expiry loop — is this DV count-to-infinity, and would split horizon have stopped it?"
- The annotated Dijkstra forwarding table with a hand-checked SPF tree.

Start with [`outputs/prompt-distance-vector-failure-lab-to-link-state-flooding-lab.md`](../outputs/prompt-distance-vector-failure-lab-to-link-state-flooding-lab.md).

## Exercises

1. On the `A—B—C` line with RIP's `INFINITY=16`, exactly how many update rounds pass before B's cost to A reaches 16 after the `A—B` link fails? Modify `main.py` to count and print it.
2. Add a fourth node to make `A—B—C—D`, fail `A—B`, and show that split horizon alone does **not** stop the loop among B, C, and D. Explain why poisoned reverse also fails here and BGP's AS_PATH would not.
3. In `run_link_state()`, set two nodes to flood LSAs with the **same** sequence number but different link costs. Which wins, and what does this say about the importance of monotonic sequence numbers?
4. Implement LSA aging: give each LSA an `LSAge` field, increment it per round, and purge any LSA that reaches `MaxAge`. Show that an origin refreshing at `LSRefreshTime` keeps its LSA alive.
5. Break Dijkstra deliberately by feeding one node a stale LSDB (drop one LSA before SPF runs). Show that this node computes a next-hop that disagrees with its neighbor — a micro-loop — and explain how OSPF's flooding synchronization prevents it in practice.
6. Measure: print the total bytes flooded for link-state vs the total vector bytes exchanged for distance-vector to reach convergence on the 4-node ring. Which scales worse with node count?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Count-to-infinity | "routing loops" | Bellman-Ford metric climbing 1 per round because a node believes a neighbor's stale route back through itself |
| Split horizon | "don't echo routes" | Never advertise a route to the neighbor you learned it from |
| Poisoned reverse | "set it to infinity" | Echo the route back at metric 16 to explicitly override stale state |
| Hold-down timer | "wait before believing" | Keep a invalidated route at infinity for a fixed window so stale ads are ignored |
| Triggered update | "send on change" | Fire a partial vector immediately on a route change, not at the next 30 s tick |
| Infinity (RIP) | "unreachable" | The fixed metric **16**; caps loop duration and limits diameter to 15 hops |
| LSA / LSP | "link-state packet" | One node's advertisement of its own links and costs, flooded network-wide |
| Flooding | "broadcast it" | Reliable distribution that re-sends out all interfaces except the arrival one, de-duplicated by sequence |
| Sequence number | "a counter" | Monotonic per-origin field that lets nodes detect and drop duplicate or stale LSAs |
| LSDB | "the topology" | The synchronized database every node runs Dijkstra over |
| SPF | "Dijkstra" | Shortest-path-first computed locally, yielding loop-free consistent next-hops |
| MaxAge / LSRefreshTime | "timers" | 3600 s purge age and 1800 s refresh interval that keep the LSDB fresh |

## Further Reading

- RFC 1058 — RIP Version 1 (the original distance-vector protocol, metric 16, 30 s updates)
- RFC 2453 — RIP Version 2 (split horizon with poisoned reverse, 30 s/180 s/240 s timers)
- RFC 2328 — OSPF Version 2 (link-state, LSA types, reliable flooding, LSAge/MaxAge, SPF)
- ISO/IEC 10589 — IS-IS intra-domain routing (link-state, LSP, the other big interior protocol)
- RFC 4271 — BGP-4 (path-vector; AS_PATH loop prevention contrasts with distance-vector)
- RFC 791 — Internet Protocol (the 8-bit TTL field that contains, but does not prevent, routing loops)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Ch. 5 (distance-vector, count-to-infinity, link-state, Dijkstra)
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, Ch. 5 (intra-AS routing, OSPF, RIP)