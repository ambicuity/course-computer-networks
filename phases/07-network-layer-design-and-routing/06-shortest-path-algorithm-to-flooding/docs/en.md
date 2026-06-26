# Shortest Path Algorithm to Flooding

> Two routing techniques sit at opposite ends of the knowledge spectrum. **Dijkstra's algorithm (1959)** computes optimal paths when a router has the *complete* weighted graph: it labels every node `(distance, predecessor)`, keeps labels `tentative` or `permanent`, repeatedly promotes the smallest-tentative node, and relaxes its neighbors — `O(V²)` with an array, `O(E log V)` with a binary heap. **Flooding** is the opposite: a router with *zero* topology knowledge sends every incoming packet out every line except the one it arrived on. Naive flooding produces an *infinite* number of duplicates, so it is damped two ways: an IP-style **hop counter (TTL)** decremented each hop (RFC 791, 8-bit field, default 64) and **per-source sequence-number suppression** where each router keeps a `(source, highest-seq-k)` list and discards anything `seq ≤ k`. Flooding always finds the shortest-delay path because it explores every path in parallel, and it is the distribution mechanism inside link-state protocols (OSPF LSAs in RFC 2328, IS-IS LSPs). This lesson builds both: a Dijkstra solver that prints the `tentative→permanent` trace, and a flooding simulator that counts duplicates with and without suppression.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Graph basics, the optimality principle and sink trees (Phase 7 · 05), IP header fields (Phase 7 · 02)
**Time:** ~90 minutes

## Learning Objectives

- Trace Dijkstra's algorithm by hand on a weighted graph, maintaining the `(length, predecessor, label)` state for every node and naming the working node at each round.
- Explain why the shortest distances must be non-negative and what breaks if a link weight goes negative.
- Quantify the duplicate explosion in naive flooding and show how a hop counter bounds it but still allows exponential duplicates.
- Implement per-source sequence-number suppression using a single counter `k` that summarizes the whole "already seen" list below it.
- Identify where flooding is genuinely used in production routing (link-state LSA/LSP distribution, wireless broadcast, ARPANET robustness).
- Map both algorithms onto the SVG topology and the `code/main.py` traces and explain the evidence each produces.

## The Problem

You are handed a 12-router backbone and asked two questions in one incident review. First: "Why did traffic from A to D suddenly route the long way around after we re-weighted a link from 7 to 30?" Second: "When we flooded a topology update last night, the CPU on three routers spiked to 100% — why did one update generate thousands of packets?"

Both are basic routing primitives, answerable only if you reason mechanically. The first is a Dijkstra question: the metric change moved a node's permanent label, so the predecessor chain — and the installed next hop — flipped. The second is a flooding question: without duplicate suppression a single packet fans out across every link in parallel, exponential in the hop count. If you cannot trace the label promotions or count the duplicates, you cannot tell whether the behavior was correct, a misconfiguration, or a loop.

## The Concept

### The graph model and the metric

Build a graph where each **node is a router** and each **edge is a link**, labeled with a weight. The weight is whatever cost you choose: hop count (every edge = 1), kilometers, mean measured probe delay, inverse bandwidth, monetary cost, or a combination. Change the weighting function and "shortest" changes meaning. In Fig 5-7 (mirrored in `assets/shortest-path-algorithm-to-flooding.svg`) paths `ABC` and `ABE` are equal by hop count but differ by distance.

The critical constraint: **weights must be non-negative.** Dijkstra promotes the smallest-tentative node to permanent and *never revisits it*. A negative edge could later offer a cheaper path into an already-permanent node, silently producing a wrong answer. Real metrics (delay, inverse bandwidth) are naturally non-negative, which is why Dijkstra is sound for link-state routing; for negative weights you must use Bellman-Ford instead.

### Dijkstra's labeling algorithm

Every node carries three pieces of state:

| Field | Meaning |
|-------|---------|
| `length` | Best known distance from source along the current best path (starts at ∞) |
| `predecessor` | The node we probed *from* to achieve that length (reconstructs the path) |
| `label` | `tentative` (may still improve) or `permanent` (proven shortest, frozen) |

The loop, finding A→D on Fig 5-7:

1. Mark source A permanent, `length=0`. It is the working node.
2. **Relax** every neighbor of the working node: if `length[working] + weight < length[n]`, lower `length[n]` and set `predecessor[n] = working`.
3. Across the *whole* graph, find the tentatively-labeled node with the smallest `length`. Make it permanent — the new working node.
4. Repeat until the destination (or every node) is permanent.

The published trace, which `code/main.py` reproduces line-for-line:

| Step | Working node | B | C | E | F | G | H | D |
|------|-------------|------|------|------|------|------|------|------|
| (b) | A→perm | (2,A) | ∞ | ∞ | ∞ | (6,A) | ∞ | ∞ |
| (c) | B→perm | — | (9,B) | (4,B) | ∞ | (6,A) | ∞ | ∞ |
| (d) | E→perm | — | (9,B) | — | (6,E) | (5,E) | ∞ | ∞ |
| (e) | G→perm | — | (9,B) | — | (6,E) | — | (9,G) | ∞ |
| (f) | F→perm | — | (9,B) | — | — | — | (8,F) | ∞ |

Notice G's label improved from `(6,A)` to `(5,E)` in step (d): the path `A→E→G` (4+1) beats `A→G` (6). That relaxation is exactly the re-weighting symptom from "The Problem." The final shortest A→D path is read backward through the predecessor chain.

**Why promotion is safe:** when E is made permanent, any hypothetical shorter path `A…ZE` would route through some Z that is either already permanent (so E was already relaxed from Z) or still tentative with a label ≥ E's (so the path cannot be shorter). Either way no shorter path escapes. The array scan in Fig 5-8 is `O(V²)`; a binary heap makes it `O(E log V)`, which is what OSPF and IS-IS run.

### Flooding: routing with no topology at all

Dijkstra needs the whole graph. Flooding needs nothing but the router's own neighbor list. The rule is one line: **forward every incoming packet on every outgoing line except the one it arrived on.**

That is gloriously robust — if any path exists, flooding finds it — and catastrophically wasteful. On a connected mesh a single packet multiplies without bound; with no damping the duplicate count is *infinite* because packets loop forever.

### Damping mechanism 1: the hop counter (TTL)

Put a counter in the packet header, decrement it at every hop, and discard the packet when it reaches zero. This is exactly the **IPv4 TTL field** (RFC 791, 8 bits, offset byte 8; renamed Hop Limit in IPv6, RFC 8200). Ideally the source initializes it to the path length; if it does not know that, it uses the worst case — the network **diameter**.

The hop counter *bounds* the flood but does not make it efficient: a router still re-forwards packets it has seen before, so duplicates grow exponentially as the hop count rises. On a graph with average degree `d`, an unsuppressed flood with hop budget `h` emits on the order of `d^h` copies — the CPU-spike symptom from "The Problem."

### Damping mechanism 2: sequence-number suppression

The real fix is to stop re-forwarding. The **source router stamps each packet with a monotonically increasing sequence number.** Each router keeps, per source, a list of sequence numbers it has already flooded; an incoming packet already on the list is dropped.

To keep the list bounded, summarize it with a single counter **k**: "I have seen everything from this source through sequence number `k`." A packet with `seq ≤ k` is a duplicate and discarded; the list below `k` can be thrown away because `k` summarizes it. This is the exact mechanism inside link-state flooding — OSPF carries an LS sequence number in every LSA (RFC 2328 §12.1.6), IS-IS one in every LSP — so a topology update floods the area *once* and stops.

`code/main.py` simulates both regimes on the SVG topology and prints the duplicate counts side by side, so you watch suppression collapse the storm to one delivery per node.

### Where flooding actually earns its keep

| Use | Why flooding fits |
|-----|-------------------|
| Link-state LSA/LSP distribution | Every router must get every other's link state exactly once — sequence-number flooding does this |
| Wireless broadcast | A radio transmission is physically received by every station in range; that *is* flooding |
| Robustness / military nets | If routers are destroyed, flooding still finds any surviving path with zero setup |
| Routing benchmark | Flooding always picks the minimum-delay path (every path in parallel), so it is the yardstick |

### How the two relate

Flooding is not a competitor to Dijkstra — it is a *building block underneath it*. Link-state routing **floods** each router's link state to everyone, then each router runs **Dijkstra** locally on the assembled graph to compute its sink tree. You need both: flooding to distribute the map, Dijkstra to read it.

## Build It

1. Read `code/main.py`. The `Graph` class holds the weighted adjacency; `dijkstra(graph, source)` returns the `(length, predecessor, label)` state and the ordered promotion trace.
2. Run it. Confirm the trace matches the step (b)–(f) table above, including G's relabel from `(6,A)` to `(5,E)`.
3. Re-weight the `A–G` edge in `main()` from 6 down to 1 and re-run. Watch G go permanent earlier and the predecessor chain change.
4. Read `flood(...)`. Run it with `suppress=False` and `suppress=True` and compare the duplicate counters.
5. Lower the hop budget and watch the unsuppressed flood get bounded but stay wasteful; raise it and watch duplicates climb.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Trace Dijkstra | The per-step `(length, predecessor, label)` table | Every promotion is the smallest tentative node; relaxations lower labels monotonically |
| Justify a route flip | Two traces, before and after a metric change | The changed weight moves a permanent label and rewrites the predecessor chain |
| Diagnose a flood storm | Duplicate counts with suppression on vs off | Suppression yields exactly one forward per (router, source-seq); off yields `~d^h` |
| Validate suppression | The per-source counter `k` after the run | `k` equals the highest seq seen; everything `≤ k` was dropped |

## Ship It

Produce one artifact under `outputs/`:

- A routing-trace annotation that walks a Dijkstra run label by label.
- A flooding runbook covering the duplicate math and the two damping knobs (TTL, sequence number).
- The topology diagram annotated with your computed shortest paths.

Start with [`outputs/prompt-shortest-path-algorithm-to-flooding.md`](../outputs/prompt-shortest-path-algorithm-to-flooding.md).

## Exercises

1. Compute the full shortest-path tree from A to *every* node on Fig 5-7. Write each node's final `(length, predecessor)` and draw the sink tree.
2. Change the `A–G` weight from 6 to 30 and re-run Dijkstra. Which node's predecessor changes, and what is the new A→G path? Confirm against `code/main.py`.
3. Introduce a `-2` weight on one edge and give a concrete counterexample of the wrong path Dijkstra now produces. Which algorithm would you switch to?
4. A network has diameter 6 and average router degree 4. Estimate the packet copies an *unsuppressed* one-packet flood generates with a hop budget of 6, then state what suppression reduces it to.
5. An OSPF area floods one LSA with LS sequence number 0x80000005. A router already holds `k = 0x80000007` for that source. What does it do, and why is keeping only `k` sufficient?
6. Explain why link-state routing needs *both* flooding and Dijkstra, and which runs first.

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Tentative label | "Not done yet" | A node whose `length` may still be lowered; only the smallest tentative node is promoted each round |
| Permanent label | "Final answer" | A node proven to have its shortest distance; frozen and never relaxed again — the source of the non-negative-weight rule |
| Relaxation | "Updating the distance" | Replacing `length[n]` with `length[working] + weight` when smaller, and recording the new predecessor |
| Working node | "The current node" | The most recently promoted permanent node, whose neighbors get relaxed this round |
| Hop counter / TTL | "Time to live" | An 8-bit IPv4 field (RFC 791) decremented each hop; bounds a flood but does not stop duplicate re-forwarding |
| Sequence-number suppression | "Don't send it twice" | Per-source counter `k` summarizing seen sequence numbers; packets with `seq ≤ k` are dropped — the heart of LSA/LSP flooding |
| Diameter | "The network's size" | The longest shortest-path between any two nodes; the safe TTL init when path length is unknown |
| Sink tree | "The routing tree" | The union of shortest paths from all sources to one destination; what Dijkstra computes per router |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §5.2.2 (Shortest Path), §5.2.3 (Flooding).
- Dijkstra, E. W. (1959). "A Note on Two Problems in Connexion with Graphs." *Numerische Mathematik* 1, 269–271 — the original algorithm.
- RFC 791 — *Internet Protocol* — the IPv4 header and 8-bit TTL field.
- RFC 8200 — *Internet Protocol, Version 6* — the IPv6 Hop Limit field.
- RFC 2328 — *OSPF Version 2* — §12.1.6 (LS sequence number) and §13 (flooding procedure).
- RFC 1195 / ISO 10589 — *IS-IS* — LSP flooding and sequence numbers.
- Bellman (1957), Ford & Fulkerson (1962) — Bellman-Ford, for graphs with negative weights.
