# Distance Vector Routing

> Distance vector routing is the distributed Bellman-Ford algorithm: every router keeps a vector of `(destination, best-metric, next-hop)` entries and, once every update interval, advertises that vector to its directly connected neighbors. A receiving router computes `cost-to-neighbor + neighbor's-advertised-cost` for each destination and keeps the minimum — the old table is never used in the recomputation. It was the original ARPANET algorithm (used until 1979) and survives in the Internet as RIP (RFC 1058 for RIPv1, RFC 2453 for RIPv2), which sends full-table UDP updates to port 520 every 30 s, treats 16 hops as infinity, and times out a route after 180 s. Its fatal weakness is the count-to-infinity problem: good news (a shorter path) propagates one hop per exchange, but bad news (a dead link) crawls upward one metric unit at a time, forming transient loops until the metric reaches "infinity." Mitigations — split horizon, poisoned reverse, triggered updates, and a small infinity (16) — reduce but never eliminate the problem, because a router cannot tell whether it is itself on the path a neighbor is advertising back to it.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Phase 07 lessons on the network layer, IP addressing, and the shortest-path problem (Dijkstra); basic graph terminology (nodes, edges, weights)
**Time:** ~90 minutes

## Learning Objectives

- Run one Bellman-Ford relaxation step by hand: given a router's neighbor costs and the delay vectors received from each neighbor, compute the new `(destination, metric, next-hop)` table and explain why the old table is discarded.
- Reproduce the count-to-infinity scenario on a five-node linear topology and state, exchange by exchange, why bad news rises one metric unit per round.
- Distinguish split horizon, poisoned reverse, and triggered updates, and identify which one each line of a routing trace demonstrates.
- Map RIP's concrete parameters (UDP/520, 30 s update timer, 180 s invalid timer, 120 s flush timer, metric ceiling 16) onto the generic algorithm.
- Explain why distance vector converges quickly for "link came up" but slowly for "link went down," and quantify convergence as a function of the longest path length N.

## The Problem

A campus has three RIP routers in a line: `core — dist — access`. The `access` router advertises the `10.20.0.0/24` subnet. At 09:14 the link between `core` and `dist` flaps. For the next ~90 seconds, monitoring shows packets toward `10.20.0.0/24` looping between `core` and `dist`, TTL expiring, and ICMP "time exceeded" floods. By the time you SSH in, the loop has cleared on its own and `show ip route` looks normal. Your manager asks: "Was that a bug, a misconfiguration, or expected behavior?"

The honest answer is *expected behavior* — you watched the count-to-infinity problem play out in real time. To defend that answer you need to read the RIP timers, the metric values in successive updates, and know whether split horizon was enabled. This lesson builds the simulator that reproduces the trace so you recognize the signature instead of guessing.

## The Concept

Source: `chapters/chapter-05-the-network-layer.md`, the Distance Vector Routing section (Figures 5-9 and 5-10).

### The data structure: a distance vector

Each router maintains one routing-table entry per known destination. The entry has exactly two operationally meaningful fields plus the key:

| Field | Meaning | RIP encoding |
|---|---|---|
| Destination | Which router/subnet this entry is about (table key) | 4-byte IPv4 address (+ subnet mask in RIPv2) |
| Metric | Best known distance to that destination | 4-byte integer, valid range 1–15, **16 = infinity** |
| Next hop | The outgoing line/neighbor that achieves that metric | derived from which neighbor's update won; RIPv2 carries it explicitly |

The whole table — the "vector" — is what gets advertised. A router does **not** advertise topology (who connects to whom); it advertises only its own best distances. This is the defining contrast with link-state routing, where each router floods the full adjacency of its own links and every node independently runs Dijkstra on a complete map.

### One relaxation step (the Bellman-Ford core)

A router knows the cost to each *directly connected* neighbor (1 hop for hop-count, or a measured delay). Once per update interval it receives, from each neighbor X, X's own vector of estimated costs to every destination. For destination `i`:

```
candidate_via_X(i) = cost_to_neighbor(X) + advertised_cost_X(i)
new_metric(i)      = min over all neighbors X of candidate_via_X(i)
next_hop(i)        = the neighbor X that achieved that minimum
```

The old routing table is **not** an input to this computation — only the freshly received neighbor vectors and the locally known neighbor costs are. That is why a single stale or lying neighbor can corrupt an entry.

**Worked example (Figure 5-9).** Router J has neighbors A, I, H, K with measured delays of 8, 10, 12, and 6 msec. To reach destination G, J adds its neighbor delay to each neighbor's advertised delay to G:

| Via neighbor | cost_to_neighbor | neighbor's cost to G | candidate to G |
|---|---|---|---|
| A | 8 | 18 | 26 |
| I | 10 | 31 | 41 |
| H | 12 | 6 | **18** |
| K | 6 | 31 | 37 |

The minimum is 18 via H, so J installs `G → metric 18, next-hop H`. J repeats this for every destination to rebuild its entire table in one pass. `code/main.py` implements exactly this loop and reproduces J's full new table; the SVG `assets/distance-vector-routing.svg` shows the four candidate computations converging on the winner.

### Convergence: good news fast, bad news slow

"Settling to the correct best paths everywhere" is called **convergence**. Distance vector reacts *rapidly to good news and leisurely to bad news*.

- **Good news (a router/link comes up).** Consider a five-node line `A–B–C–D–E` where A was down. When A revives, B learns it is 1 hop away on the first exchange, C learns it is 2 hops on the second, and so on. The truth spreads exactly one hop per exchange; in a network whose longest path is N hops, everyone knows within N exchanges.

- **Bad news (the count-to-infinity problem).** Now A goes down while B, C, D, E had distances 1, 2, 3, 4. On the first exchange B hears nothing from A, but C still advertises "I can reach A in 2" — C's path actually runs back through B, but B cannot know that. So B sets its distance to A to 3 (via C). On the next exchange C sees its neighbors claim 3 and bumps to 4, and so the metric climbs *one unit per exchange* toward infinity, with packets looping the whole time. The rule "no router ever has a value more than one higher than the minimum of its neighbors" is exactly why bad news is slow.

This is why "infinity" must be a small finite number. RIP picks **16**: the metric counts up 3, 4, 5 … 16, the loop self-terminates, and the route is declared unreachable — at the cost that no legitimate RIP path may exceed 15 hops.

### Mitigations and why they are incomplete

| Technique | Mechanism | What it fixes | What it misses |
|---|---|---|---|
| Small infinity (16) | Cap the count so the loop ends | Bounds count-to-infinity duration | Limits network diameter to 15 hops |
| Split horizon | Do not advertise a route back over the interface you learned it on | Two-node A↔B loops | Loops involving 3+ routers |
| Poisoned reverse | Advertise such routes back with metric = infinity (RFC 1058) | Forces neighbor to drop the false path fast | Bigger updates; still fails on larger loops |
| Triggered updates | Send an update immediately on a metric change instead of waiting for the 30 s timer | Speeds bad-news propagation | Update storms; loops can still form before triggers arrive |

The root cause survives all of them: when X tells Y "I have a path to Z," Y cannot know whether Y itself is on that path. Link-state routing avoids this because every node holds the full topology — which is why ARPANET abandoned distance vector in 1979.

### RIP: the concrete protocol

RIP is distance vector over UDP. The numbers worth memorizing:

| Parameter | Value | Why it matters |
|---|---|---|
| Transport / port | UDP, port 520 | Updates are unreliable broadcasts/multicasts, not a session |
| Update timer | 30 s | Full table advertised to neighbors every 30 s |
| Invalid (timeout) timer | 180 s (6 missed updates) | Route marked unreachable (metric 16) if no refresh |
| Flush (garbage) timer | 240 s / 120 s after invalid | Entry removed from table |
| Metric | Hop count, 1–15, 16 = ∞ | Caps diameter, bounds count-to-infinity |
| RIPv1 → RIPv2 | RFC 1058 → RFC 2453 | v2 adds subnet masks, next-hop field, and 224.0.0.9 multicast + MD5 auth |

The looping packets from "The Problem" are the count-to-infinity climb; they stop because the metric hits 16 within a handful of exchanges — the bounded-infinity design at work.

## Build It

1. Read the worked example above and confirm by hand that J reaches G in 18 msec via H.
2. Open `code/main.py`. The `relax_step()` function is the Bellman-Ford core; `DistanceVector` holds one router's table.
3. Run `python3 main.py`. The first block reproduces router J's full new table from the Figure 5-9 neighbor vectors — check that G shows metric 18, next-hop H.
4. The second block runs the five-node count-to-infinity simulation and prints the metric for destination A at each router after every exchange. Watch the numbers climb 3, 4, 5, 6 … toward infinity (capped at 16).
5. Re-run with `split_horizon=True` (flip the flag in `main()`) and compare: the two-node bounce is gone, but a 3-node loop still counts up — demonstrating the limit in the mitigations table.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm one relaxation step | `code/main.py` J-table output vs. the hand table | G = 18 via H, and every other destination matches Figure 5-9 |
| Recognize count-to-infinity | Per-exchange metric trace for a downed destination | Metrics rise exactly +1 per exchange; loop clears when metric reaches 16 |
| Tell good news from bad | Compare "link up" vs. "link down" exchange counts | Up converges in ≤ N exchanges; down crawls to infinity |
| Verify split horizon | Trace with the flag on vs. off | Two-node bounce disappears; multi-node loop persists |
| Map RIP timers to a flap | `show ip route` timestamps + update intervals | A 30–90 s loop window is consistent with 30 s updates and metric-16 cutoff |

## Ship It

Produce one reusable artifact under `outputs/`:

- A count-to-infinity runbook: the metric-climb signature, the RIP timers that bound it, and the `show ip rip` / capture filters (`udp.port == 520`) that confirm it.
- Or the annotated trace from `code/main.py` saved as a teaching example showing both convergence directions.

Start from `outputs/prompt-distance-vector-routing.md`.

## Exercises

1. In Figure 5-9, compute J's new metric and next-hop for destination **D** (not G) using neighbor delays A=8, I=10, H=12, K=6 and the four received vectors. Show all four candidates and the winner.
2. Five-node line `A–B–C–D–E`, A reachable at 1,2,3,4; A dies. Hand-trace the metric at B,C,D,E to A through 6 exchanges with **no** mitigation, then with **split horizon**. At which exchange does each reach infinity (16)?
3. Explain precisely why poisoned reverse fixes the A↔B two-node loop but not a B→C→D→B three-node loop. What false belief survives at each node?
4. A RIP network has a legitimate 17-hop diameter path. Describe the symptom users see and the single RIP parameter responsible. What protocol change fixes it without abandoning distance vector entirely?
5. You capture RIP updates and see a destination's metric advertised as 16. List two distinct events that produce a metric-16 advertisement and the timer evidence that distinguishes them.
6. For a 50-router network with 8-bit metrics, how many bytes does one full RIP vector advertise, and why does sending it every 30 s scale worse than a link-state protocol that floods only on change?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Distance vector | "Routers gossip their tables" | Distributed Bellman-Ford: advertise your best metrics, take the min of `neighbor-cost + advertised-cost`, discarding your old table each round |
| Bellman-Ford | "The shortest-path math" | The relaxation `d(i) = min_X (c(X) + d_X(i))` run distributedly with no global topology view |
| Convergence | "When routing settles" | All routers hold the correct best path; fast for link-up (≤ N exchanges), slow for link-down |
| Count-to-infinity | "A routing loop" | Bad news rising one metric unit per exchange because a router can't tell it's on the path a neighbor advertises back |
| Infinity | "Unreachable" | A small finite cap (16 in RIP) chosen so the count terminates; also caps network diameter |
| Split horizon | "Don't echo routes back" | Suppress advertising a route on the interface you learned it from; stops 2-node loops only |
| Poisoned reverse | "Advertise it as dead" | Send the learned-back route with metric = infinity instead of suppressing it (RFC 1058) |
| Triggered update | "Send it now" | Advertise immediately on a metric change rather than waiting for the periodic timer |

## Further Reading

- RFC 1058 — *Routing Information Protocol* (RIPv1; split horizon, poisoned reverse, the 30/180/120 s timers, metric 16).
- RFC 2453 — *RIP Version 2* (subnet masks, next-hop field, 224.0.0.9 multicast, MD5 authentication).
- RFC 1723 / RFC 4822 — RIPv2 extensions and cryptographic authentication.
- R. E. Bellman, *Dynamic Programming* (1957); Ford & Fulkerson, *Flows in Networks* (1962) — the algorithmic origins.
- Tanenbaum & Wetherall, *Computer Networks*, Chapter 5 (the Network Layer): Distance Vector Routing and the Count-to-Infinity Problem (Figures 5-9 and 5-10).
- Wireshark display filter `udp.port == 520` (RIP) for capturing live distance-vector updates.
