# Shortest Path Routing Lab

> Shortest-path routing computes a least-cost tree from one source to every destination, then installs the next hop toward each destination into the forwarding table. **Dijkstra** (1959) runs a priority-queue greedy search in `O(E log V)` and requires **non-negative** edge weights — once a node is settled, its distance is final, so a negative link could undercut it. **Bellman-Ford** relaxes every edge `V-1` times in `O(VE)`, tolerates negative weights, and detects **negative cycles** with one extra pass. Every link-state protocol uses Dijkstra: **OSPF** (RFC 2328) floods Link-State Advertisements so every router holds an identical Link-State Database, then each runs SPF independently. **Distance-vector** protocols (RIP) are distributed Bellman-Ford; count-to-infinity is the failure mode its centralized negative-cycle check cannot catch. **Convergence** is the window between a topology change and all routers re-running their algorithm; transient **micro-loops** form when two adjacent routers disagree mid-update.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 7 lessons 05-06
**Time:** ~90 minutes

## Learning Objectives

- Implement Dijkstra's shortest-path algorithm with a binary heap and explain why non-negative weights are mandatory.
- Implement Bellman-Ford with `V-1` relaxation passes and negative-cycle detection, and state when it beats Dijkstra.
- Convert a shortest-path *tree* (predecessor pointers) into a *forwarding table* mapping destination → next hop, which is what a router actually installs.
- Compare the two algorithms on the same topology: trace relaxations, verify identical trees on non-negative weights, and run Bellman-Ford on a graph with a negative edge.
- Describe how OSPF turns bandwidth into a cost, floods link state, and re-runs SPF on failure (reconvergence).

## The Problem

A network operator at a regional ISP pages at 2 a.m.: customers in the east POP report 40% packet loss to the west POP. The link between two core routers just flapped. Within seconds OSPF reconverges and loss clears — but for about 800 ms, `traceroute` showed packets ping-ponging between two routers, TTL expiring, ICMP Time Exceeded flooding back.

Before the post-mortem the operator must answer three questions: (1) Once the link failed, what path *should* traffic take, and is it provisioned with enough capacity? (2) During the gap before full reconvergence, which router pair formed the micro-loop, and why? (3) If they re-cost one link, can they steer the backup path somewhere with more headroom?

Every one is a shortest-path question. You cannot answer them by staring at a CLI — you need to reproduce the SPF computation on the real topology with the real link costs and watch the forwarding tables change. You also need Bellman-Ford to reason about distance-vector protocols and to handle the one case Dijkstra cannot: negative weights, which appear in traffic-engineering metrics and policy-based routing — never in raw OSPF but everywhere in TE.

## The Concept

### Graph representation

A network is a weighted graph `G = (V, E)`. Routers are vertices; links are edges weighted by cost. Two encodings matter: **adjacency list** `{u: {v: w}}` — sparse graphs (real networks), `O(V + E)` space, what Dijkstra and Bellman-Ford both consume; **adjacency matrix** `M[u][v] = w` — dense graphs, `O(V²)` space, useful for Floyd-Warshall (all-pairs) but wasteful here. Routing links are **bidirectional and symmetric** by default, but OSPF lets each direction carry a different cost. `code/main.py` models adjacency lists and adds both directions in `Graph.add_link()`.

### Dijkstra — the greedy priority-queue algorithm

```
function dijkstra(graph, source):
    dist[v] = +inf for all v;  dist[source] = 0
    prev[v] = none for all v
    heap   = [(0, source)]
    settled = {}
    while heap:
        (d, u) = heap.pop_min()
        if u in settled: continue        # stale entry, skip
        settled.add(u)
        for (v, w) in neighbors(u):
            if v in settled: continue
            nd = d + w
            if nd < dist[v]:              # relaxation
                dist[v] = nd
                prev[v] = u
                heap.push((nd, v))
    return dist, prev
```

The "lazy deletion" trick — pushing a new `(nd, v)` instead of decreasing a key in place, then skipping settled pops — is what `heapq` forces in Python and what production implementations use. With a binary heap the complexity is `O((V + E) log V)`, commonly written `O(E log V)`. **Non-negative weights are mandatory**: Dijkstra's correctness rests on the invariant that once a node is settled, no cheaper path can appear. A negative edge could undercut a settled node, so OSPF costs are 16-bit unsigned, 1–65535.

### Bellman-Ford — relax everything, V-1 times

```
function bellman_ford(graph, source):
    dist[v] = +inf for all v;  dist[source] = 0
    prev[v] = none for all v
    for i in 1 .. |V|-1:                 # at most V-1 edges in a shortest path
        for (u, v, w) in all_edges:
            if dist[u] + w < dist[v]:     # relaxation
                dist[v] = dist[u] + w
                prev[v] = u
    # negative-cycle detection: one more pass
    for (u, v, w) in all_edges:
        if dist[u] + w < dist[v]:
            return "NEGATIVE CYCLE reachable from source"
    return dist, prev
```

Why `V-1` passes? A shortest path with `V` vertices has at most `V-1` edges; after `k` passes, every destination whose shortest path uses at most `k` edges is settled. Complexity is `O(VE)` — slower than Dijkstra on dense graphs, but it tolerates **negative weights** and reports negative cycles. **Distance-vector routing** (RIP, RFC 2453) is distributed Bellman-Ford: each router announces its `dist[]` vector to neighbors, neighbors relax, repeat. The notorious **count-to-infinity** failure is what happens when a link cost effectively becomes infinite and distributed Bellman-Ford lacks the global view to detect it — the centralized version's negative-cycle check has no distributed analogue.

### Comparison

| Aspect | Dijkstra | Bellman-Ford |
|---|---|---|
| Complexity | `O(E log V)` with heap | `O(VE)` |
| Negative weights | **Forbidden** | Allowed |
| Negative-cycle detection | No | Yes (extra pass) |
| Relaxation order | Greedy, settled-first | All edges, `V-1` passes |
| Used by | OSPF, IS-IS (link-state) | RIP, distance-vector variants |
| Best fit | Sparse non-negative (real networks) | Negative/TE metrics, distributed |

On a graph with only non-negative weights, both produce identical shortest-path trees — Dijkstra just gets there faster.

### Link-state routing: OSPF uses Dijkstra

OSPF does not route on hop count. Each interface gets a cost, and path cost is the sum of *outgoing* interface costs. By default:

```
cost = reference_bandwidth / interface_bandwidth   (integer, min 1)
reference_bandwidth default = 100 Mbps = 10^8 bps
```

| Link bandwidth | Default OSPF cost |
|---|---|
| 10 Mbps   | 10 |
| 100 Mbps  | 1  |
| 1 Gbps    | 1 (clamped) |
| 10 Gbps   | 1 (clamped) |

The clamping problem is real: with the default reference, every link at or above 100 Mbps costs 1, so a 100 Mbps link and a 100 Gbps link look identical to SPF. Operators raise the reference (Cisco `auto-cost reference-bandwidth 100000` makes it 100 Gbps) so modern links get distinct costs. `code/main.py` exposes `ospf_cost(bandwidth_mbps, reference_mbps)` so you can see and fix the clamp.

The full OSPF loop: (1) routers flood LSAs describing their interfaces and costs, (2) every router assembles the same LSDB, (3) each runs Dijkstra independently to build its own shortest-path tree and forwarding table. No router ever sees another's table — only the shared graph.

### From tree to table: extracting the next hop

A router does not store full paths. It stores, per destination, a single **next hop**. Dijkstra produces a shortest-path *tree* via `prev[]`; the router walks back from each destination toward the root and records the node *one hop away from the root* as the next hop.

```
function next_hop(prev, source, dest):
    if dest == source: return source
    node = dest
    while prev[node] != source:
        node = prev[node]
        if node is none: return UNREACHABLE
    return node
```

Worked example: for `D`, `prev[D] = B`, `prev[B] = A = source`, loop stops with `node = B`. The router installs `D → B` and never needs the rest of the path; downstream routers each made their own consistent SPF decision, so hop-by-hop forwarding follows the global tree.

### Failure handling and convergence

When an edge is removed, every router must (1) receive the new LSA via flooding, (2) install it in the LSDB, (3) re-run SPF. These steps are gated by timers — `lsa-arrival`, `spf-delay`, `spf-hold` (tens to hundreds of ms). Because routers do not run SPF at the same instant, two adjacent routers can briefly hold *contradictory* next hops:

```
Before failure A—B—C path to E:   A: E via B    B: E via C
Link B—C fails. B re-runs SPF first, reroutes E via A:
                                   A: E via B    B: E via A
A packet for E now loops A->B->A->B... until A re-runs SPF.
TTL (IPv4 8-bit field, RFC 791) decrements each hop until 0,
the router drops the packet and emits ICMP Time Exceeded (type 11).
```

`code/main.py`'s `detect_microloop()` compares pre- and post-failure forwarding tables and flags any destination where router X's next hop is Y while Y's next hop for the same destination is X — the signature of a two-router loop. Loop-Free Alternates (RFC 5286) and ordered FIB updates suppress these.

## Build It

1. Read `code/main.py` top to bottom. The topology is an adjacency dict `{node: {neighbor: cost}}`; `Graph.add_link()` adds symmetric edges.
2. Run it: `python3 main.py`. It prints Dijkstra's step-by-step relaxation from `A`, the forwarding table, then Bellman-Ford on the same graph (identical tree), then Bellman-Ford on a graph with a negative edge, then a reconvergence diff.
3. Trace one entry by hand. Pick destination `E`, follow `prev` back to the root, confirm the printed next hop matches your walk-back.
4. Change a link cost (make `B-C` expensive) and re-run. Watch which destinations change next hop.
5. Fail a link in `simulate_failure()` and read the micro-loop report. Identify the looping router pair and which destination triggered it.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify Dijkstra picks least-cost path | Printed cost column vs hand-summed interface costs | Every destination cost equals the minimum over all paths, not hop count |
| Compare Dijkstra vs Bellman-Ford | Same tree, different relaxation count on non-negative graph | Trees identical; Bellman-Ford shows more relaxations |
| Handle negative weights | Bellman-Ford on graph with negative edge | Correct tree where Dijkstra would have failed; negative cycle flagged if present |
| Spot the OSPF cost clamp | `ospf_cost()` table at 1 Gbps and 10 Gbps | Both show cost 1 with default reference; raising reference separates them |
| Detect a micro-loop | `detect_microloop()` output after failure | You name the exact router pair and destination, tied to TTL / ICMP type 11 |

## Ship It

This lesson produces an artifact under `outputs/`. Start with [`outputs/prompt-shortest-path-routing-lab.md`](../outputs/prompt-shortest-path-routing-lab.md). Good artifacts for this lab:

- A reusable `spf.py` you can point at any topology file to dump per-router forwarding tables using either algorithm.
- A one-page reconvergence runbook: failure → expected new next hops → micro-loop risk → mitigation (LFA / SPF timers).
- A cost-design worksheet that picks a reference bandwidth so your real link speeds get distinct OSPF costs.

## Exercises

1. The example topology has `A-B=1, A-C=4, B-C=1, B-D=2, C-E=0`. By hand, compute the shortest-path tree from `C` using Dijkstra. Which destinations does `C` reach via `B` rather than directly? Verify against `python3 main.py` after changing the source to `C`.
2. Run Bellman-Ford on the same graph. Count the relaxations vs Dijkstra. Confirm the final `dist[]` and `prev[]` are identical. Why is Bellman-Ford slower here despite producing the same tree?
3. Add an edge `D-E = -3` to the graph. Run Dijkstra — describe the wrong answer it produces and explain, using the "settled = final" invariant, why it fails. Run Bellman-Ford — confirm it gives the correct tree. Now add a negative cycle (e.g. `D-E = -3, E-D = -1`) and confirm Bellman-Ford reports it.
4. A 40 Gbps link and a 10 Gbps link both show OSPF cost 1 under the default reference bandwidth. Choose a reference bandwidth (in Mbps) that gives the 10 Gbps link cost 2 and the 40 Gbps link cost 1 (rounding down, min 1). Confirm with `ospf_cost()`.
5. Fail link `B-C` in `simulate_failure()`. Which router forms a micro-loop with which neighbor, and for which destination? Explain using the pre/post next-hop diff and the IPv4 TTL field.
6. The west-POP scenario from *The Problem*: re-cost one link in the topology so the backup path after a failure avoids a chosen router. Show the before/after forwarding table for the affected destination.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SPF | "the routing algorithm" | Specifically Dijkstra's shortest-path-first run per router over the shared LSDB |
| Relaxation | "updating the distance" | Replacing `dist[v]` when a cheaper path through `u` is found |
| LSA / LSDB | "the OSPF database" | Link-State Advertisements flooded so every router holds an identical Link-State Database before SPF |
| Next hop | "the route" | One neighbor per destination — the *first* edge of the shortest-path tree, not the whole path |
| OSPF cost | "the metric" | `reference_bw / interface_bw`, summed over outgoing interfaces; 16-bit, 1–65535 |
| Bellman-Ford | "the slow one" | `O(VE)` relaxation over all edges `V-1` times; handles negative weights and detects negative cycles |
| Negative cycle | "broken metric" | A cycle whose total weight is negative; Bellman-Ford flags it, Dijkstra silently mishandles it |
| Reconvergence | "the network healing" | Flood new LSA → update LSDB → re-run SPF, gated by timers, not instantaneous |
| Micro-loop | "a routing loop" | A *transient* 2+ router loop during reconvergence because tables disagree mid-update |

## Further Reading

- **RFC 2328** — OSPF Version 2 (the canonical link-state spec, including SPF and the Dijkstra section).
- **RFC 2453** — RIP Version 2 (the distance-vector / distributed Bellman-Ford protocol).
- **RFC 5286** — IP Fast Reroute: Loop-Free Alternates (micro-loop mitigation).
- **RFC 791** — Internet Protocol: the 8-bit Time To Live field whose expiry produces ICMP Time Exceeded.
- **RFC 792** — ICMP, including Time Exceeded (type 11) emitted when TTL hits 0.
- Dijkstra, E. W. (1959), *A Note on Two Problems in Connexion with Graphs* — the original algorithm.
- Bellman, R. (1958), *On a Routing Problem*; Ford, L. R. (1956), *Network Flow Theory* — the Bellman-Ford origins.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Ch. 5: Shortest Path, Distance Vector, and Link State Routing.
- Cormen et al., *Introduction to Algorithms*, Ch. 24: Single-Source Shortest Paths (Dijkstra and Bellman-Ford correctness proofs).