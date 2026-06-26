# The Optimality Principle

> The optimality principle (Bellman, 1957) states that if router J lies on the optimal path from router I to router K, then the optimal path from J to K is a *suffix* of that same path. The proof is a one-line contradiction: if a shorter J→K route existed, you could splice it onto the I→J prefix and beat the route you called optimal. The direct consequence is that the set of all optimal routes from every source to a single destination forms a **sink tree** rooted at that destination — a loop-free spanning structure (a DAG when ties are allowed) that guarantees delivery in a finite, bounded number of hops. Real distributed protocols approximate sink trees: distance-vector protocols like **RIP (RFC 2453)** build them hop-by-hop with the Bellman-Ford recurrence, and link-state protocols like **OSPF (RFC 2328)** compute them directly with Dijkstra's SPF. The principle is not an algorithm you run — it is the *benchmark* every routing algorithm is measured against, and the reason routing tables can store one next-hop per destination instead of a full path.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Graph basics (nodes/edges/weights), IP forwarding model, Phase 7 lessons 01–04
**Time:** ~90 minutes

## Learning Objectives

- State the optimality principle precisely and reconstruct its one-line proof-by-contradiction using a route prefix `r1` and suffix `r2`.
- Explain why optimal routes to a single destination form a **sink tree** and why that tree is guaranteed loop-free and finite-hop.
- Compute a sink tree for a given destination from a weighted topology and read it as a per-router next-hop table.
- Distinguish a unique sink tree from the DAG that appears when equal-cost paths exist (ECMP), and connect this to OSPF/IS-IS load splitting.
- Identify the three real-world conditions — stale topology, link flap, and path interference — under which deployed routers temporarily violate the principle and form micro-loops.

## The Problem

You are on call for a backbone network. A customer reports that traffic from site **A** to site **K** is taking a path through **G** and **H**, but the monitoring dashboard shows that the A→G leg and the G→K leg, *measured independently*, each look optimal. A junior engineer wants to "fix" the A→K route by hand-pinning a different next hop at A, leaving the G→K route untouched.

Should you let them? The optimality principle tells you the answer without touching a single router. If G genuinely sits on the optimal A→K path, then the optimal G→K path **must** be the tail of the optimal A→K path — they cannot disagree. If your two independent measurements show them disagreeing, you do not have a routing-policy problem; you have **inconsistent topology databases**: A and G are computing shortest paths over different views of the network (a stale LSA, a flapping link, an unsynchronized metric). Hand-pinning one hop will create a forwarding loop the moment the databases reconverge. The principle reframes a vague "the path looks wrong" ticket into a precise, testable claim about which routers' link-state databases are out of sync.

## The Concept

### The principle, stated precisely

Let the optimal (least-cost) path from router **I** to router **K** be written as a sequence of routers. Suppose router **J** appears on that path. Split the path into two pieces: the prefix `r1` from I to J, and the suffix `r2` from J to K. The optimality principle says:

> `r2` is itself an optimal path from J to K.

**Proof.** Suppose not. Then some path `r2'` from J to K is strictly cheaper than `r2`. But then `r1 · r2'` (the prefix followed by the cheaper suffix) is a path from I to K that is strictly cheaper than `r1 · r2`. That contradicts the assumption that `r1 · r2` was the optimal I→K path. Therefore no cheaper `r2'` exists, and `r2` is optimal. ∎

This is *optimal substructure* — the exact property that makes dynamic programming (Bellman-Ford) and greedy shortest-path search (Dijkstra) correct. `code/main.py` includes `verify_optimality_principle()`, which takes a computed shortest-path tree and checks, for every router J on every source's optimal path, that the stored suffix cost equals the independently computed J→K optimal cost.

### Sink trees: the structural consequence

Fix a single destination, say router **B**. For *every* source router, draw only its optimal path to B. Because each router has exactly one optimal next hop toward B (assuming unique costs), these paths overlap and merge as they approach B, and the union of all of them is a **tree rooted at B**. This is the **sink tree** for B (Tanenbaum's Fig. 5-6b). Three properties fall out immediately:

| Property | Why it holds | Operational meaning |
|---|---|---|
| Loop-free | A tree has no cycles by definition | Packets never circle back to a router they already visited |
| Bounded hop count | A path in a tree visits each node at most once | Delivery in ≤ (N−1) hops for N routers; TTL/Hop-Limit is a backstop, not the primary loop guard |
| One next-hop per router | Each tree node has exactly one parent | A forwarding table needs only `dest → next_hop`, not the full path |

The last row is *why* IP forwarding works the way it does. A router does not carry a packet's whole route; it stores one next hop per destination prefix and trusts that every downstream router's sink tree agrees with its own.

### Sink tree vs. DAG: the equal-cost case

A sink tree is **not unique**. If two paths to the destination have identical cost, both are optimal, and the router may keep both next hops. Allowing every equal-cost path turns the structure from a tree into a **DAG (Directed Acyclic Graph)** rooted at the destination — still loop-free, but now a router can have multiple parents. This is exactly **ECMP (Equal-Cost Multi-Path)**: OSPF and IS-IS install several next hops of equal metric and hash flows across them (typically a 5-tuple hash so a single TCP flow stays on one path and avoids reordering). The diagram in `assets/the-optimality-principle.svg` shows the same topology rendered first as a unique sink tree and then as a DAG once an equal-cost tie is admitted.

### Worked example: a sink tree by hand

Take this weighted topology (undirected, weights are link costs):

```
A —2— B —7— C
|     |     |
6     3     2
|     |     |
G —1— E —2— F —3— D
```

Compute the sink tree rooted at **D** (every router's cheapest path *to* D):

| Source | Optimal path to D | Cost | Next hop toward D |
|---|---|---|---|
| F | F→D | 3 | D |
| C | C→F→D wait — C→D? | C→F→D = 2+3 = 5 | F |
| E | E→F→D | 2+3 = 5 | F |
| B | B→E→F→D | 3+2+3 = 8 | E |
| G | G→E→F→D | 1+2+3 = 6 | E |
| A | A→B→E→F→D | 2+3+2+3 = 10 | B |

Read the right-hand column top to bottom and you have built D's sink tree: every router stores exactly one next hop, and following next hops from any source walks the tree to the root. `code/main.py` reproduces this table for any destination and prints the tree.

### How real protocols approximate it

The principle is topology- and traffic-independent, but real networks are neither static nor globally known. Two protocol families discover sink trees by different means:

- **Distance-vector — RIP (RFC 2453), Bellman-Ford.** A router knows only the cost to its neighbors and the distance vectors they advertise, applying `D(x) = min over neighbors n of [ cost(x,n) + D_n(dest) ]`. Convergence builds the sink tree from the leaves inward. The failure mode is **count-to-infinity**: after a link fails, routers bounce stale distances back and forth, incrementing one hop per round until they hit RIP's `infinity = 16`. Split horizon and poison reverse mitigate it.
- **Link-state — OSPF (RFC 2328), IS-IS, Dijkstra.** Every router floods its adjacencies (LSAs), assembles an identical link-state database, then runs Dijkstra's SPF locally to compute the sink tree rooted at *itself*. Because all routers run SPF on the *same* database, their trees are mutually consistent — that is the principle holding across the whole network.

### When deployed routers break the principle

The principle is a theorem about a *single consistent* weighted graph. Production networks violate its preconditions in three ways:

1. **Stale topology / convergence windows.** During the seconds between a link failure and full reconvergence, different routers hold different databases. Two routers' "optimal" paths can disagree, producing a transient **micro-loop**. TTL (IPv4, RFC 791) / Hop Limit (IPv6, RFC 8200) caps the damage by dropping packets after a bounded number of hops.
2. **Link flap and metric churn.** If a link's cost oscillates (e.g., dynamic delay-based metrics, the original ARPANET problem), the sink tree never settles and routers continuously recompute, wasting CPU and reordering flows.
3. **Path interference.** The principle assumes paths do not interact — "a traffic jam on one path will not cause another to divert." With congestion-aware metrics this assumption fails: rerouting traffic onto path X raises X's cost, which can push the optimal tree to flip back, oscillating. This is why most production IGPs use *static* administrative costs, not live load.

## Build It

1. Read `code/main.py`. It builds a weighted, undirected graph from an edge list, then exposes `sink_tree(graph, dest)` which runs Dijkstra to return, for every source, its cost and next hop toward `dest`.
2. Run `python3 main.py`. It prints the sink tree for a chosen destination, then runs `verify_optimality_principle()` to confirm that every router on every optimal path has a suffix whose cost matches the independently computed optimal cost.
3. Inspect `equal_cost_dag()`: add an edge that creates an equal-cost tie and watch one router gain a second next hop — the tree becomes a DAG (ECMP).
4. Break the principle deliberately: corrupt one router's view by raising a single edge weight *only in that router's copy of the graph*, recompute, and observe the next-hop disagreement that would form a micro-loop.
5. Map the printed next-hop column to a forwarding table: `dest_prefix → next_hop`. That column *is* the routing table entry for this destination.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Build a sink tree | `sink_tree(g, 'D')` output: per-source cost + next hop | Following next hops from any source reaches the root with no repeats |
| Verify the principle | `verify_optimality_principle()` returns no violations | Every suffix cost on every optimal path equals the standalone optimal cost |
| Detect an inconsistency | Two routers compute different next hops for the same destination | You can point to the diverging edge weight / stale LSA, not "the path looks wrong" |
| Confirm ECMP | A destination shows ≥2 equal-cost next hops | The structure is a DAG; flow-hashing keeps each 5-tuple on one path |
| Bound a loop | Path length in hops vs. TTL/Hop-Limit | A micro-loop is dropped after ≤ Hop-Limit hops, never infinitely |

## Ship It

Produce one artifact under `outputs/`:

- A **sink-tree calculator** that ingests an edge list and emits per-destination next-hop tables (extend `code/main.py`).
- A **micro-loop runbook**: how to detect next-hop disagreement, which counters/LSAs to pull (OSPF `show ip ospf database`, age fields), and the safe remediation (wait for reconvergence, never hand-pin one hop).
- A **diagram** contrasting the unique sink tree with the equal-cost DAG for one topology.

Start from [`outputs/prompt-the-optimality-principle.md`](../outputs/prompt-the-optimality-principle.md).

## Exercises

1. In the worked-example topology, compute the sink tree rooted at **A** by hand, then check it against `sink_tree(g, 'A')`. Which router has the longest optimal path to A, and what is its cost?
2. Add the edge `C—G` with cost 4 to the topology. Does any router’s optimal path to **D** change? Show the before/after next-hop column and explain using the optimality principle why only some rows can change.
3. Introduce a tie: set `A—G` to cost 5 so that A→G→E→F→D and A→B→E→F→D have equal cost. List A's next hops in the resulting DAG and explain how a 5-tuple flow hash keeps a single TCP connection on one branch.
4. Simulate count-to-infinity: in a 3-router line A—B—C, remove the C link and apply the Bellman-Ford update by hand for RIP with `infinity = 16`. How many rounds until both A and B reach 16? Show how split horizon shortens this.
5. Corrupt one router's database: raise `E—F` to cost 50 in *G's* copy only. Recompute G's next hop toward D and B's next hop toward D. Identify the micro-loop and state which protocol mechanism (TTL vs. reconvergence) stops the packet from circulating forever.
6. The optimality principle assumes non-interfering paths. Design a 4-node topology and a congestion-aware metric where shifting traffic to the optimal path makes a *different* path become optimal, causing oscillation. Explain why production IGPs avoid load-based metrics.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Optimality principle | "Shortest paths are shortest" | If J is on the optimal I→K path, the J→K suffix is itself optimal — optimal substructure, proven by contradiction |
| Sink tree | "The routing tree" | Union of all sources' optimal paths to one destination; loop-free, bounded-hop, one parent per node |
| DAG (here) | "A tree with loops" | A loop-free structure with multiple parents that appears when equal-cost paths are all kept (ECMP) |
| Optimal substructure | "A dynamic-programming buzzword" | The exact property the optimality principle expresses; what makes Bellman-Ford and Dijkstra correct |
| Next hop | "The path" | The single neighbor a router forwards to for a destination — all a router stores, thanks to the sink tree |
| Micro-loop | "A routing loop" | A *transient* loop during reconvergence when routers hold inconsistent databases; bounded by TTL/Hop-Limit |
| ECMP | "Load balancing" | Installing all equal-cost next hops and hashing flows across them; the DAG case of the principle |
| Count-to-infinity | "RIP is slow" | Distance-vector failure where stale metrics climb to `infinity = 16` one hop per round after a link loss |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 5, Section 5.2.1 (the optimality principle and sink trees) and 5.2.2 (Dijkstra's shortest-path algorithm).
- Bellman, R. (1957), *Dynamic Programming* — the origin of the principle of optimality.
- Dijkstra, E. W. (1959), "A Note on Two Problems in Connexion with Graphs," *Numerische Mathematik* 1, 269–271.
- RFC 2328 — *OSPF Version 2* (link-state, source-rooted SPF, areas, LSA flooding).
- RFC 2453 — *RIP Version 2* (distance-vector, Bellman-Ford, `infinity = 16`, split horizon).
- RFC 791 — *Internet Protocol* (the TTL field that bounds loops); RFC 8200 — *IPv6* (the Hop Limit field).
- ISO/IEC 10589 — *IS-IS* intra-domain routing (link-state, ECMP).
