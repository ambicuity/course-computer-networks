# Link State Routing

> Link state routing replaced distance vector on the ARPANET in 1979 because distance vector converged too slowly (the count-to-infinity problem). Every router runs five steps: discover neighbors with HELLO packets, measure link cost (often inversely proportional to bandwidth — 1-Gbps Ethernet costs 1, 100-Mbps costs 10), build a Link State Packet (LSP) carrying its identity, a 32-bit sequence number, an Age field, and a list of (neighbor, cost) pairs, flood that LSP reliably to every other router, then run Dijkstra's shortest-path algorithm locally over the full topology. Flooding is controlled by tracking (source, sequence) pairs: new LSPs are forwarded on every line except the arrival line, duplicates are discarded, and lower-sequence LSPs are rejected as obsolete. The Age field (decremented once per second and during each flooding hop) cleans up stale state when a router crashes and restarts its sequence at 0. The two production link state protocols are IS-IS (ISO 10589, used by many ISPs) and OSPF (RFC 2328), both of which add a designated router to model broadcast LANs as a single artificial node.

**Type:** Build
**Languages:** Python (stdlib), routing traces
**Prerequisites:** Graph basics, Distance Vector Routing (Phase 07 · 07), IP addressing
**Time:** ~90 minutes

## Learning Objectives

- Name and order the five steps every link state router performs, and state what each one produces.
- Build a Link State Packet by hand from a labeled topology, including the source, sequence number, Age, and the (neighbor, cost) list.
- Apply the flooding rules — forward-if-new, discard duplicates, reject-if-obsolete — to a (source, sequence) seen-set and predict which lines an LSP leaves on.
- Run Dijkstra's algorithm over a reassembled topology and read off the next-hop routing table for one router.
- Explain three sequence-number failure modes (wraparound, crash-and-restart, 1-bit corruption) and how the 32-bit sequence plus Age field defeat each.
- Contrast IS-IS and OSPF and explain why a broadcast LAN is modeled as a pseudonode.

## The Problem

A regional ISP runs distance vector routing. An engineer pulls the fiber between two core routers at 02:14. Reachability to a downstream prefix does not fail cleanly — instead, ping times to it climb from 12 ms to 400 ms over the next ninety seconds, then the prefix goes fully unreachable, then it flaps back. Traceroute shows the path bouncing R3 → R7 → R3 → R7. This is count-to-infinity: routers are slowly counting their metric upward, one increment per update interval, believing each other's stale good news. Convergence takes minutes, and during those minutes packets loop until their TTL expires.

Link state routing removes this failure class. Instead of each router advertising its *distance* to every destination (and trusting neighbors' summaries), each router advertises only its *directly observed local links* and floods that fact to everyone. Every router independently assembles the same complete map and computes its own shortest paths. There is no second-hand distance to count up. When the fiber drops, the two affected routers flood a new LSP, and within one flooding sweep every router recomputes consistent loop-free paths.

## The Concept

Link state routing is five steps, run by every router. `code/main.py` implements all five; the topology diagram in `assets/link-state-routing.svg` shows the example network used below.

### Step 1 — Discover the neighbors (HELLO)

When a router boots, its first job is to learn who is on the other end of each link. It sends a **HELLO packet** on every point-to-point line; the router at the far end replies with its name. Names must be **globally unique** — when a distant router later hears that three routers all connect to "F", it must be certain they all mean the same F.

A broadcast link (a switch, ring, or classic Ethernet) connecting several routers is *not* modeled as a full mesh of point-to-point links — that bloats the topology with O(k²) edges and wastes flooding messages. Instead one router is elected the **designated router** and the LAN becomes a single artificial **pseudonode** N. Saying "you can go from A to C across the LAN" is represented as the two-hop path A–N–C. OSPF and IS-IS both do this.

### Step 2 — Set the link costs

Dijkstra needs a cost (distance metric) on every link. Costs are configured by the operator or derived automatically. The common rule is **cost inversely proportional to bandwidth**, so fatter pipes are preferred:

| Link type | Bandwidth | Typical cost |
|---|---|---|
| 10-Gbps Ethernet | 10 Gbps | 1 |
| 1-Gbps Ethernet | 1 Gbps | 1 |
| 100-Mbps Ethernet | 100 Mbps | 10 |
| T1 serial | 1.544 Mbps | ~64 |

For geographically spread networks, propagation **delay** can be folded in: send an **ECHO packet** the far side must bounce back immediately, measure round-trip time, divide by two. Shorter links then win.

### Step 3 — Build the Link State Packet

Once neighbors and costs are known, the router assembles an **LSP**. Its layout:

```
+-----------------+
| Source identity |   who built this LSP (e.g. "B")
+-----------------+
| Sequence number |   32-bit, incremented per new LSP
+-----------------+
| Age             |   countdown, decremented once/sec and per hop
+-----------------+
| (neighbor, cost) ... list of directly observed links
+-----------------+
```

For the network in the SVG (B–A cost 4, B–C cost 2, B–F cost 6, etc.), router B's LSP body is `{A:4, C:2, F:6}`. Every router builds one. **When** to build is the hard part: either periodically, or — better — on a significant event (a line or neighbor going up/down, or a cost change).

### Step 4 — Distribute the LSPs by flooding

This is the trickiest step. Every router must receive every LSP **quickly and reliably**; if routers compute on different topology versions, the result is transient loops and black holes. The mechanism is controlled flooding driven by a **(source, sequence) seen-set**:

| Incoming LSP vs. seen-set | Action |
|---|---|
| Sequence higher than any seen for this source | Accept, forward on all lines except arrival line |
| Sequence equal (duplicate) | Discard |
| Sequence lower than highest seen | Reject as obsolete |

LSPs are not forwarded instantly — they sit briefly in a **holding/buffer area** so a router can collapse a burst of updates and acknowledge correctly. The per-router buffer carries **send flags** and **ACK flags** per outgoing link. Worked example for router B (links to A, C, F):

| Source | Seq | Age | Send A C F | ACK A C F | Meaning |
|---|---|---|---|---|---|
| A | 21 | 60 | 0 1 1 | 1 0 0 | arrived from A → send to C,F; ACK to A |
| F | 21 | 60 | 1 1 0 | 0 0 1 | arrived from F → send to A,C; ACK to F |
| E | 21 | 59 | 0 1 0 | 1 0 1 | arrived twice (via A and via F) → send only to C; ACK both A and F |

All LSPs are **acknowledged** hop-by-hop to survive link errors.

### Step 5 — The sequence number and Age failure modes

A naive flood breaks in three ways; the 32-bit sequence plus the Age field fix all three:

1. **Wraparound.** A 16-bit counter wraps fast. With a **32-bit** sequence number at one LSP per second, wraparound takes ~137 years — ignore it.
2. **Crash and restart.** A crashed router forgets its sequence and restarts at 0; its fresh LSPs look like ancient duplicates and get rejected. The **Age** field rescues this: Age decrements once per second, and at Age 0 the stale LSP is purged, so the restarted router's low-sequence LSP is accepted again.
3. **1-bit corruption.** If sequence 4 is corrupted to 65,540, every real LSP up to 65,540 is wrongly rejected as obsolete. Again Age purges the bad high-sequence record after it times out (typically a new LSP arrives every ~10 s; six consecutive losses would be needed to false-timeout a live router).

Age is also decremented at **each hop during flooding**, guaranteeing no LSP circulates forever.

### Step 6 — Compute routes with Dijkstra

Once a router holds a full set of LSPs, it reassembles the entire graph — every link appears **twice**, once per direction, and the two directions may carry **different costs**, so the A→B path can differ from B→A. The router then runs **Dijkstra's shortest-path algorithm** locally. The output gives, for each destination, the **outgoing link (next hop)** to install in the forwarding table. `code/main.py` does exactly this and prints the resulting table.

Cost: for *n* routers each with *k* neighbors, input storage is ~*kn* and Dijkstra's run time grows faster than *kn* — heavier than distance vector, but it does not suffer slow convergence. **IS-IS** (ISO 10589, common in ISP cores) and **OSPF** (RFC 2328) are the two production link state protocols; IS-IS can carry multiple network-layer protocols (IP, IPX) at once, OSPF is IP-only.

## Build It

`code/main.py` implements the whole pipeline against the example topology in the SVG:

1. **Define the topology** as a weighted graph and have each router emit its LSP (`build_lsp`).
2. **Simulate flooding** from one origin LSP across the graph, maintaining a `(source, seq)` seen-set and printing the forward/discard/obsolete decision at each hop (`flood`).
3. **Reassemble** the global graph from the collected LSPs (`reassemble_topology`).
4. **Run Dijkstra** from a chosen source and print the cost and full path to every destination (`dijkstra`).
5. **Emit the routing table** mapping each destination to its next hop (`routing_table`).

Run it: `python3 code/main.py`. No dependencies, stdlib only.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Build an LSP from a topology | The (neighbor, cost) list for one router | List matches every directly attached link, each with the right cost |
| Trace a flood | Per-hop forward/discard/obsolete log | Each LSP leaves on all lines except its arrival line; duplicates dropped; lower seq rejected |
| Detect an obsolete LSP | Seen-set state before/after | A seq lower than the recorded highest is rejected, not installed |
| Compute next hops | Dijkstra path tree + routing table | Next hop is the first link on the shortest path, ties resolved deterministically |
| Recover from a router crash | Age countdown reaching 0 | Stale LSP purged at Age 0; restarted router's seq-0 LSP accepted |

## Ship It

Produce one artifact under `outputs/`:

- A **flooding runbook**: given a (source, seq) seen-set and an arriving LSP, the decision and the outgoing lines.
- A **Dijkstra trace sheet** for the SVG topology with the next-hop table for each router.
- A **failure-mode card** mapping wraparound / crash-restart / corruption to the 32-bit-seq and Age mitigation.

Start with [`outputs/prompt-link-state-routing.md`](../outputs/prompt-link-state-routing.md).

## Exercises

1. From the SVG topology, write router C's LSP body by hand, then confirm it against the `build_lsp("C")` output. Why does C's link to D appear in *both* C's LSP and D's LSP, possibly with different costs?
2. Router E's LSP (seq 21) reaches B twice — once via A, once via F. Fill in B's buffer row: which send flags and which ACK flags are set, and why is it sent on only one link?
3. A router crashes and reboots, restarting its sequence number at 0. Walk through why its first new LSP is initially rejected, then how the Age field eventually lets it back in. How long does this take if Age starts at 60?
4. A 1-bit error turns sequence 4 into 65,540 in a stored LSP. Which subsequent LSPs from that source get wrongly dropped, and what finally clears the bad record?
5. Change the B–C link cost in `code/main.py` from 2 to 20 and rerun. Which destinations in B's routing table change next hop, and which do not? Explain using the Dijkstra tree.
6. Three routers A, C, F share one broadcast LAN. Draw both the naive point-to-point model and the pseudonode model. How many graph edges does each use, and why does the designated router reduce flooding load?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Link State Packet (LSP) | "the router's update" | A packet carrying one router's identity, 32-bit sequence number, Age, and its (neighbor, cost) list — only *local* links, never second-hand distances |
| Flooding | "send it everywhere" | Forward each new LSP on all lines except its arrival line, gated by a (source, sequence) seen-set; discard duplicates, reject lower sequences |
| Sequence number | "a version tag" | A 32-bit monotonically increasing counter per source; ~137 years to wrap at 1 LSP/sec |
| Age | "a TTL" | A countdown decremented once per second *and* at each flooding hop; at 0 the LSP is purged, which is what survives crash-restart and corruption |
| Designated router | "the LAN boss" | The router elected to represent a broadcast LAN as a single pseudonode, avoiding O(k²) point-to-point edges |
| Pseudonode | "fake router" | An artificial graph node N standing in for a broadcast LAN; A–C across the LAN is modeled as A–N–C |
| Dijkstra's algorithm | "shortest path" | Run locally over the reassembled topology to produce next hops; distinct from the flooding that *delivers* the topology |
| Count-to-infinity | "the loop bug" | The distance-vector slow-convergence failure that link state routing structurally avoids |

## Further Reading

- RFC 2328 — *OSPF Version 2* (the IP link state protocol; LSA types, flooding, DR election)
- RFC 1195 — *Use of OSI IS-IS for Routing in TCP/IP and Dual Environments* (integrated IS-IS)
- ISO/IEC 10589 — *Intermediate System to Intermediate System (IS-IS) Intra-Domain Routing Protocol*
- RFC 5340 — *OSPF for IPv6 (OSPFv3)*
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §5.2.5 (Link State Routing) and §5.6.6 (OSPF)
- Dijkstra, E. W. (1959), *A Note on Two Problems in Connexion with Graphs*, Numerische Mathematik 1
