# Routing for Mobile Hosts to Routing in Ad Hoc Networks

> Two related problems sit at the edge of the network layer. **Mobile-host routing** (Mobile IP, RFC 5944 for IPv4, RFC 6275 for IPv6) keeps a host reachable at its fixed *home address* while it roams: a **home agent** intercepts packets via gratuitous/proxy ARP, **tunnels** them with IP-in-IP encapsulation (RFC 2003, protocol number 4) to a **care-of address**, and the mobile host decapsulates. **Ad hoc routing** (AODV, RFC 3561) goes further — the routers themselves move, so routes are discovered *on demand* by flooding a **ROUTE REQUEST (RREQ)**, answered by a unicast **ROUTE REPLY (RREP)** along reverse-path state, and kept fresh with a 32-bit **destination sequence number** that defeats the count-to-infinity problem distance-vector protocols suffer. AODV scopes floods with an expanding-ring search on the IP **TTL** field and detects breakage with periodic **HELLO** messages. DSDV (Destination-Sequenced Distance Vector) adds the same sequence-number trick to proactive Bellman-Ford; DSR (RFC 4728) carries the full source route in the packet header; OLSR (RFC 3626) optimizes proactive link-state with Multi-Point Relay selectors. The classic failure modes are *triangle routing* (Mobile IP forcing traffic through the home agent) and *stale routes* (an ad hoc node leaving without warning). This lesson builds a runnable AODV route-discovery simulator and a Mobile IP tunnel tracer so you can read the actual state these protocols leave behind.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Distance-vector routing (Phase 7 lessons on Bellman-Ford and count-to-infinity), IP addressing and tunneling/encapsulation, flooding
**Time:** ~90 minutes

## Learning Objectives

- Trace a Mobile IP packet from sender through home agent, IP-in-IP tunnel, and care-of address, naming each header that is added or stripped.
- Run an AODV route discovery on a sample topology and read the reverse-route state, hop counts, and the path that survives.
- Explain how the 32-bit destination sequence number prevents the count-to-infinity problem that plagues plain distance vector.
- Compute the broadcast cost of expanding-ring search (TTL = 1, 2, 3, ...) versus a single network-wide flood.
- Distinguish AODV (hop-by-hop, table-driven) from DSR (source routing), DSDV (proactive sequenced), OLSR (MPR link-state), and GPSR (geographic), and pick which fits a given MANET.
- Identify the evidence — RREQ sequence numbers, HELLO timeouts, active-neighbor lists — that confirms route maintenance is working.

## The Problem

A field team deploys 12 laptops at a disaster site with no infrastructure — no access point, no DHCP, no upstream router. Laptop A needs to reach laptop I three hops away, but A has never heard of I and the wireless topology reshuffles every few seconds as people walk around. There is no administrator to configure static routes and no stable link to run OSPF over.

Meanwhile, back at headquarters, an engineer with a fixed laptop keeps its corporate IP `198.51.100.7` while travelling between three cities. Email sent to `198.51.100.7` must still arrive in San Diego even though the routing fabric of the Internet wants to deliver it to New York, where that prefix lives.

Both are the same core difficulty stated in the textbook: *to route a packet to a moving target, the network first has to find it.* Conventional routing assumes a host's address tells you where it is. Mobility breaks that assumption. The two standard answers — Mobile IP for moving hosts on a fixed core, AODV for a moving core — are the subject of this lesson.

## The Concept

### Mobile IP: home address, care-of address, and the home agent

Every mobile host has a permanent **home address** tied to its **home network**, the way `1-212-5551212` encodes country code 1 and area code 212. While the host is home, ordinary routing works. The interesting case is when it roams.

On the visited (foreign) network the host acquires a temporary **care-of address (CoA)** — typically via DHCP, or in older schemes from a **foreign agent (FA)**. It then sends a **registration request** to its **home agent (HA)** — a router on the home network — carrying the CoA. The home agent stores the binding `home address → care-of address` in a *binding cache*.

When a correspondent sends a packet to the home address, normal routing delivers it to the home network. The home agent **intercepts** it (using gratuitous/proxy ARP so it answers for the absent host), **encapsulates** it, and **tunnels** it to the CoA. This is the mechanism the textbook calls tunneling, and it is the heart of Mobile IP (RFC 5944 for IPv4, RFC 6275 for IPv6).

### IP-in-IP encapsulation, field by field

The home agent prepends an entire outer IPv4 header (RFC 2003). The original packet becomes the payload, untouched.

| Field | Outer header (added by home agent) | Inner header (original, unchanged) |
|---|---|---|
| Source IP | Home agent address | Correspondent address |
| Destination IP | Care-of address | Home address |
| Protocol | **4** (IP-in-IP) | 6 (TCP) / 17 (UDP) / etc. |
| TTL | Fresh, e.g. 64 | Carried as data, not decremented in tunnel |

At the CoA, the mobile host (or a foreign agent) strips the 20-byte outer header and recovers the inner packet exactly as the correspondent sent it. Reply traffic can go directly to the correspondent, which is why Mobile IP is asymmetric and gives rise to **triangle routing**: correspondent → home agent → mobile, but mobile → correspondent directly. Mobile IPv6 route optimization (RFC 6275) lets the mobile host send a binding update directly to the correspondent so subsequent packets skip the home agent — at the cost of a new trust problem (the correspondent must authenticate the binding update). See `assets/routing-for-mobile-hosts-to-routing-in-ad-hoc-networks.svg` for the full triangle.

### Why ad hoc networks are harder

In Mobile IP the *hosts* move but the *routers* are fixed and well-connected. An ad hoc network (a **MANET**, Mobile Ad hoc NETwork) removes even that anchor: every node is simultaneously host and router, every link is a radio link that appears and disappears, and there is no fixed infrastructure at all. A path that is valid now may be invalid one bit-time later, with no failure notification. Proactive protocols (OSPF, RIP) that flood periodic updates would burn bandwidth and battery recomputing a topology that never settles.

The dominant answers are **on-demand** protocols that build routes *only when needed*: AODV (RFC 3561) and DSR (RFC 4728). Proactive alternatives include DSDV and OLSR (RFC 3626).

### DSDV: proactive distance vector with sequence numbers

**DSDV** (Destination-Sequenced Distance Vector, Perkins & Bhagwat 1994) is the simplest bridge from classic Bellman-Ford to a mobile world. Each routing table entry carries a *(destination, next-hop, metric, sequence-number)* tuple. The destination owns its sequence number and increments it whenever its local topology changes; it stamps every update with that number. A node receiving two advertisements for the same destination always prefers the higher sequence number, and for equal sequence numbers the lower metric. Because stale routes always carry a *lower* sequence number, a node can never mistake an obsolete route for a fresh one — count-to-infinity is killed at the root. The cost is periodic full-table broadcasts, which is why DSDV is rarely used in large dense MANETs but is the conceptual ancestor of AODV's sequence-number discipline.

### AODV route discovery: RREQ flood and RREP reverse path

**AODV** (Ad hoc On-demand Distance Vector, RFC 3561) borrows DSDV's sequence numbers but builds routes *lazily*. Suppose node A wants to send to node I and has no table entry for I. A builds a **ROUTE REQUEST (RREQ)** and broadcasts it. Key RREQ fields:

| RREQ field | Purpose |
|---|---|
| Source address | Originator (A) |
| Destination address | Target (I) |
| Broadcast ID + Source seq # | Uniquely identifies this RREQ; used to drop duplicates during the flood |
| Destination sequence number | Last known freshness for I; a node may only answer with an equal-or-newer route |
| Hop count | Incremented at each forwarding node |

The RREQ floods outward (the textbook's Fig. 5-20): A reaches B and D; they rebroadcast to C, F, G; then to E, H, I. A node that has already seen this `(source, broadcast ID)` pair **discards the duplicate** — that is why D drops B's copy. As each node forwards, it records the neighbor it heard the request from, building **reverse-route state** pointing back toward A.

When the RREQ reaches I (or any node with a fresh-enough route to I), that node unicasts a **ROUTE REPLY (RREP)** back along the reverse path. Each intermediate node increments the RREP hop count and installs a *forward* route entry: "to reach I, send to the neighbor that gave me this reply." When the RREP reaches A, the route **A → D → G → I** exists end to end. `code/main.py` reproduces exactly this flood-and-reply on a sample graph and prints the surviving path with hop counts.

### Expanding-ring search: bounding the flood with TTL

A network-wide flood is expensive, especially for a nearby destination. AODV bounds it using the IP **Time to live** field. The sender first broadcasts the RREQ with **TTL = 1** (only direct neighbors). If no RREP returns within a timeout, it retries with **TTL = 2**, then 3, 4, 5 ... searching in widening rings.

Worked example on a uniform mesh where ring *k* contains roughly 6*k* nodes:

| TTL | Nodes reached this ring | Cumulative transmissions |
|---|---|---|
| 1 | 6 | 6 |
| 2 | 12 | 18 |
| 3 | 18 | 36 |

If I is 2 hops away, expanding-ring search costs ~18 broadcasts versus a full flood of the entire network — a large saving when destinations are usually close.

### Route maintenance: HELLO, active neighbors, and sequence numbers

Because a node can move or power off silently, AODV must detect breakage. Each node periodically broadcasts a **HELLO** message; neighbors are expected to answer. A missed HELLO (or a failed unicast) means that neighbor is gone.

For every destination, a node tracks the **active neighbors** that forwarded traffic for it in the last ΔT seconds. When neighbor G vanishes, the node finds every route that used G, marks those routes invalid, and notifies the upstream active neighbors — who recurse the purge. In the example, D drops its entries for G and I and tells A, which drops its entry for I. Senders then rediscover via a fresh RREQ.

The subtle part is correctness. Plain distance vector suffers **count-to-infinity**: after a break, nodes can keep advertising stale routes that loop. AODV fixes this with a **32-bit destination sequence number** that acts as a logical clock owned by the destination. The destination increments it on every fresh RREP. A sender requesting a route includes the last sequence number it used; the RREQ keeps propagating until a route with a *strictly higher* sequence number is found. Intermediate nodes prefer the route with the higher sequence number, or — for equal sequence numbers — the one with fewer hops. A stale route always has a lower sequence number, so it can never be mistaken for a fresh one. This is the single most important difference from classic Bellman-Ford.

### DSR: source routing, no tables

**DSR** (Dynamic Source Routing, RFC 4728) also discovers on demand but puts the entire hop list in the packet header. The RREQ accumulates the path it has taken; the RREP carries that path back to the source, which then stamps every data packet with the full route. No per-node routing tables are needed — each forwarder just reads the next hop from the header. The trade-off: header length grows with path length, and route caches can go stale. DSR shines in small networks where the overhead of header length is less than the overhead of table maintenance.

### OLSR: proactive link-state with Multi-Point Relays

**OLSR** (Optimized Link State Routing, RFC 3626) takes the opposite tack — it is proactive, flooding topology periodically like OSPF, but it cuts broadcast cost drastically by designating **Multi-Point Relays (MPRs)**. Each node picks a minimal subset of its neighbors as MPRs such that every two-hop neighbor is covered; only MPRs retransmit broadcasts. Link-state updates are diffused through the MPR set, giving each node a full topology map and shortest-path routes with no on-demand delay. The cost is steady control traffic and MPR reselection as nodes move.

### Comparison: AODV vs DSR vs DSDV vs OLSR vs GPSR

| Protocol | Strategy | State carried | Best when |
|---|---|---|---|
| **AODV** (RFC 3561) | On-demand distance vector, hop-by-hop tables | Per-node next-hop + seq # | General MANET, moderate size |
| **DSR** (RFC 4728) | On-demand source routing — full path in each packet header | Path list in the packet | Small networks; route caching helps |
| **DSDV** | Proactive sequenced distance vector | Full table + seq #, periodic broadcast | Small, low-mobility MANETs |
| **OLSR** (RFC 3626) | Proactive link-state, MPR-optimized flooding | Full topology map | Dense, low-mobility; routes needed instantly |
| **GPSR** | Geographic greedy forwarding | Node positions only, no routes | All nodes know GPS coordinates |

DSR puts the entire hop list in the packet header (no per-hop table lookup, but header grows with path length). GPSR computes no routes at all: knowing every node's coordinates, it simply forwards greedily toward the destination and perimeter-routes around dead ends.

## Build It

1. Read `code/main.py`. It models a MANET as an undirected graph of radio neighbors and implements AODV `route_discovery()` (BFS flood that records reverse routes) plus `expanding_ring_search()`.
2. Run it: `python3 code/main.py`. Confirm the discovered A→I path and the per-node reverse-route table match the textbook's A–D–G–I result.
3. Inspect the Mobile IP section: `mobile_ip_tunnel()` builds the inner and outer headers and prints the encapsulated packet the home agent sends to the care-of address.
4. Change the topology dictionary (remove the G–I edge) and rerun. Watch route discovery find an alternate path and the hop count change.
5. Drive `expanding_ring_search()` for a near vs far destination and compare the broadcast counts it reports.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a Mobile IP tunnel | Outer header with protocol = 4, dst = CoA; inner header dst = home address | The home address is preserved end to end; only the outer header changes per tunnel |
| Verify AODV found a route | RREP hop count, installed next-hop per node, surviving solid path | The path is loop-free and the destination sequence number is non-decreasing |
| Detect a stale route | Lower destination sequence number than current; missed HELLO | The node purges the route and triggers rediscovery instead of forwarding into a hole |
| Justify expanding-ring search | Broadcast count at TTL 1, 2, 3 vs full flood | Nearby destinations resolve in a small ring, not a network-wide storm |
| Pick AODV vs DSR vs OLSR | Mobility rate, node count, delay tolerance | Low delay → OLSR; small + sparse → DSR; general → AODV |

## Ship It

Produce one artifact under `outputs/`:

- An annotated AODV trace (RREQ flood + RREP path) for a topology you define, with the destination sequence numbers called out.
- A Mobile IP runbook: the registration → intercept → tunnel → decapsulate sequence with the exact headers at each step.
- A one-page comparison card: AODV vs DSR vs DSDV vs OLSR vs GPSR with the decision rule for each.

Start from the printed output of `code/main.py` and annotate it with the failure mode you tested.

## Exercises

1. In the textbook topology, node G is switched off after route A–D–G–I is established. Walk through route maintenance: which node detects the loss first, which entries get purged, and what RREQ does A send to recover?
2. A correspondent at `203.0.113.9` sends a 1400-byte TCP segment to a mobile host whose home address is `198.51.100.7`, currently at CoA `192.0.2.50`. Write out the outer and inner IP headers the home agent emits, including the protocol number and both address pairs.
3. Two RREQs for destination I arrive at node D: one with destination sequence number 12 and hop count 2, another with sequence number 12 and hop count 4. Which does D keep, and why? Now the second has sequence number 14 — does your answer change?
4. Compute the total transmissions for expanding-ring search to find a destination exactly 3 hops away in a mesh where ring *k* has 6*k* nodes, and compare with a single full flood reaching 60 nodes.
5. Your MANET is 6 nodes, all GPS-equipped, in open terrain. Argue for GPSR over AODV, then describe one terrain feature that would break GPSR's greedy forwarding and force a fallback.
6. Triangle routing sends every correspondent-to-mobile packet through the home agent. Describe the Mobile IPv6 route-optimization binding update (RFC 6275) that removes the triangle, and the new trust problem it introduces.
7. Contrast DSDV and OLSR: both are proactive, but one uses sequence-numbered distance vectors and the other uses MPR-optimized link state. When would each win?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Care-of address | "the mobile's new IP" | A temporary topologically-correct address on the visited network; the tunnel endpoint, never shown to correspondents |
| Home agent | "the thing that forwards" | A router on the home network that intercepts packets for the absent host and tunnels them to the current CoA |
| Foreign agent | "the remote helper" | A router on the visited network that terminates the tunnel and hands the inner packet to the mobile; optional in modern Mobile IP |
| Tunneling | "wrapping a packet" | IP-in-IP encapsulation (protocol 4): an outer header to the CoA carries the unchanged inner packet to the home address |
| Triangle routing | "an inefficiency" | Correspondent → home agent → mobile while mobile → correspondent goes direct; fixed by IPv6 route optimization |
| RREQ / RREP | "AODV messages" | Broadcast ROUTE REQUEST that floods to discover a route; unicast ROUTE REPLY that walks the reverse path installing forward routes |
| Destination sequence number | "a version number" | A 32-bit destination-owned logical clock; strictly higher = fresher, which is what kills count-to-infinity |
| Expanding-ring search | "TTL trick" | Repeated RREQs with TTL 1, 2, 3 ... so nearby destinations resolve without a full-network flood |
| Active neighbor | "a neighbor" | A neighbor that forwarded traffic for a destination within the last ΔT seconds; the set notified when a route breaks |
| MANET | "a wireless mesh" | Mobile Ad hoc NETwork — no infrastructure, every node is host and router, topology changes without warning |
| MPR | "OLSR relays" | Multi-Point Relay — a minimal neighbor subset chosen to cover all two-hop neighbors, only MPRs rebroadcast |

## Further Reading

- **RFC 3561** — Ad hoc On-Demand Distance Vector (AODV) Routing (Perkins, Belding-Royer, Das).
- **RFC 5944** — IP Mobility Support for IPv4, Revised (Mobile IPv4).
- **RFC 6275** — Mobility Support in IPv6, including route optimization that removes triangle routing.
- **RFC 2003** — IP Encapsulation within IP (the IP-in-IP, protocol-4 tunnel).
- **RFC 4728** — The Dynamic Source Routing Protocol (DSR) for MANETs.
- **RFC 3626** — Optimized Link State Routing (OLSR) with Multi-Point Relays.
- Perkins & Bhagwat, "Highly Dynamic Destination-Sequenced Distance-Vector Routing (DSDV)," SIGCOMM 1994.
- Karp & Kung, "GPSR: Greedy Perimeter Stateless Routing for Wireless Networks," MobiCom 2000.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, Sections 5.2.10–5.2.11.
- Perkins, *Ad Hoc Networking*, Addison-Wesley, 2001.