# Multicast Routing

> Multicast delivers one packet stream to a group of receivers without the N-copy cost of unicast or the scattershot waste of broadcast. Groups are named by Class D IPv4 addresses (224.0.0.0/4, high bits `1110`) that map to MAC `01:00:5E` frames using only 23 of the address's 28 group bits — a 32:1 collision overlap engineers must know about. Two tree-building strategies dominate: **source-based trees** built by Reverse Path Forwarding plus PRUNE pruning (DVMRP, RFC 1075; MOSPF, RFC 1584), which store up to *mn* trees per router, and **shared core-based trees** rooted at a rendezvous point (CBT, RFC 2189; PIM-SM, RFC 7761) that store one tree per group at the cost of suboptimal paths. RPF accepts a packet only if it arrived on the interface the router would use to reach the source; otherwise it is dropped to kill loops. PRUNE state is soft — it expires (default ~3 minutes in DVMRP) and the tree is re-flooded, so a forgotten prune silently turns a pruned link back into a flooded one. This lesson builds an RPF+prune simulator so you can watch a spanning tree shrink hop by hop.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Link-state and distance-vector routing (Phase 7 lessons 06–08), broadcast/spanning-tree routing, IPv4 addressing
**Time:** ~90 minutes

## Learning Objectives

- Compute a Class D group address's Ethernet MAC mapping and explain why 5 address bits are lost, producing 32-way frame aliasing.
- Trace Reverse Path Forwarding: decide accept-or-drop for a multicast packet given a router's unicast routing table toward the source.
- Run the flood-and-prune cycle for a source-based tree and count the links removed by PRUNE messages.
- Contrast source-based trees (DVMRP/MOSPF, *mn* trees) with shared core-based trees (CBT/PIM-SM, one tree per group) on storage, path length, and which to pick for dense vs. sparse groups.
- Identify three real failure modes: RPF check failure after a unicast route change, soft-state prune expiry re-flooding, and rendezvous-point loss in a shared tree.

## The Problem

A live-video team streams a 6 Mb/s sports feed to 1,200 viewers spread across a campus of 40,000 hosts. The naive build sends 1,200 unicast copies: the source NIC and first-hop link now carry 7.2 Gb/s of duplicated payload — the same bytes, 1,200 times. Someone "fixes" it by switching the app to broadcast. Now every one of the 40,000 hosts receives interrupts for a feed only 3% of them want, and the broadcast leaks past the intended audience to machines that were never supposed to see it.

Multicast is the middle path: send **one** copy per link, replicated by routers only where the delivery tree branches toward actual group members. The engineering problem is *which links belong to the tree*, and how routers agree on that without a central controller — because group membership changes continuously as viewers join and leave. Get the tree wrong and you either drop legitimate receivers or flood the whole campus anyway.

## The Concept

### Class D addressing and the 23-bit MAC mapping

IPv4 multicast uses **Class D**: the top four bits are `1110`, giving the range **224.0.0.0 – 239.255.255.255** (`224.0.0.0/4`). The low 28 bits identify the group. Some addresses are reserved: `224.0.0.0/24` is link-local control (e.g. `224.0.0.5` = OSPF all-routers, `224.0.0.2` = all-routers), and `239.0.0.0/8` is administratively scoped (private, RFC 2365).

When a router forwards a multicast IP packet onto Ethernet, it builds a frame with a destination MAC in the reserved IANA block **`01:00:5E:00:00:00`**. Only the **low 23 bits** of the group address are copied:

```
IPv4:  1110 xxxx . xxxxx101 . 10101011 . 11001101   (239.x.171.205)
                   ^^^^^----- top 5 of the 28 group bits are DISCARDED
MAC:   01:00:5E : 0_______ : 10101011 : 11001101
                  (bit 24 forced 0; 23 group bits carried)
```

Because 28 group bits are squeezed into 23 MAC bits, **2^5 = 32 different IP groups alias to the same MAC**. For example `224.1.1.1` and `225.1.1.1` and `239.129.1.1` all become `01:00:5E:01:01:01`. A NIC that filters in hardware on this MAC will pass frames for 31 groups the host never joined; the kernel must re-check the IP group and discard the strays. `code/main.py` includes `ipv4_to_multicast_mac()` so you can see this collapse on real addresses.

### Reverse Path Forwarding (RPF): the loop killer

A multicast packet has no single destination to route toward — it must fan out. To prevent it looping forever, routers use **Reverse Path Forwarding**. The rule is one line:

> Accept a multicast packet **only if** it arrived on the interface the router would use to send *unicast* traffic back toward the source. Otherwise, drop it.

That interface is the **RPF interface**; the check is the **RPF check**. The intuition: a packet on the shortest reverse path is almost certainly on a non-looping forward path, so accept and replicate it out all *other* interfaces. A duplicate arriving on any non-RPF interface is a loop artifact and is silently discarded.

| Event | RPF interface to source S | Packet arrived on | Decision |
|-------|---------------------------|-------------------|----------|
| Normal | eth0 (next hop toward S) | eth0 | Accept, forward out eth1, eth2 |
| Loop copy | eth0 | eth1 | **Drop** (off reverse path) |
| Route flap | eth0 → now eth2 | eth0 | **Drop** (stale path, was valid a second ago) |

The route-flap row is a real failure mode: when the unicast route to the source changes, the RPF interface changes with it, and in-flight multicast on the old interface is dropped until receivers re-establish. `code/main.py` implements `rpf_check()` directly against a unicast next-hop table.

### Flood-and-prune: building a source-based tree

RPF alone *floods* — every router replicates to all neighbors, reaching members and non-members alike. To trim the dead branches, distance-vector multicast (DVMRP, RFC 1075) layers **PRUNE** messages on top:

1. The source floods via RPF. The packet reaches a leaf router with **no** local group members and **no** downstream routers that want the group.
2. That router sends a **PRUNE** back up its RPF interface: "stop sending group G from source S this way."
3. When an upstream router has received PRUNEs on **all** interfaces it was forwarding out (and has no local members), it prunes itself, sending PRUNE further up. The tree shrinks recursively.

The result is the **multicast spanning tree** — only links that reach members survive. In the textbook 10-link broadcast tree, pruning for one group leaves 7 links; for a sparser group, 5 links.

Critically, **prune state is soft**. It carries a lifetime (DVMRP default ~3 minutes / 7200 s max in implementations). When it expires the source **re-floods**, and routers with new members can re-join by simply *not* re-pruning (or by sending a GRAFT, RFC 1075). The failure mode: a prune that expires under high churn causes periodic flood storms; a GRAFT that is lost leaves a new member dark until the next flood cycle. The SVG (`assets/multicast-routing.svg`) shows this flood → prune → shrink sequence.

### Source-based vs. shared core-based trees

There are two fundamentally different tree shapes:

| Property | Source-based (DVMRP, MOSPF) | Shared / core-based (CBT, PIM-SM) |
|----------|-----------------------------|-----------------------------------|
| Tree per | (source, group) pair | group only |
| Trees stored per router | up to *m·n* (m members, n groups) | 1 per group |
| Root | the sender | a chosen **core** / rendezvous point (RP) |
| Path length | optimal (shortest from source) | can detour via the core |
| Best for | **dense** groups, few sources | **sparse** groups, many sources |
| Build method | RPF flood + PRUNE | members send JOIN toward the core |
| RFC | 1075 / 1584 | 2189 / 7761 |

In a **core-based tree** (Ballardie 1993), all routers agree on one root. Each member sends a JOIN toward the core; the tree is the union of those paths. A sender ships its packet toward the core, and as soon as the packet touches *any* on-tree router it is forwarded both up toward the core and down all other branches — it need not reach the core first. The cost: a sender on one edge may reach a member on the opposite edge via the core in 3 hops instead of 1. The win: each router keeps **one** tree per group instead of *m*, and off-tree routers do **zero** work — why PIM-SM (RFC 7761) shared trees dominate sparse Internet multicast.

### Dense vs. sparse: choosing the algorithm

The deciding question is group density relative to the network:

- **Dense** (receivers in most of the network): start from broadcast and prune. The flood is cheap because nearly everyone wants it. Use DVMRP / MOSPF / PIM-DM.
- **Sparse** (receivers are a small island, e.g. 1,200 of 40,000): flooding the whole network repeatedly is catastrophic. Build a shared tree explicitly with JOINs. Use PIM-SM / CBT. Routers off the tree never touch the traffic.

Picking flood-and-prune for the 1,200-of-40,000 streaming scenario in *The Problem* would re-flood the entire campus every few minutes — exactly the broadcast waste multicast was meant to eliminate. The right answer there is a sparse-mode shared tree.

### The storage explosion

Source-based trees are optimal per-packet but expensive in state. For *n* groups averaging *m* members, each router may store **mn** pruned trees — and the tree for the *leftmost* sender to a group looks nothing like the tree for the *rightmost* sender, so the router forwards the *same* group in different directions depending on the source. Shared trees collapse this to *n* trees (one per group) at the cost of path optimality — the state-vs-optimality trade that drives the dense/sparse decision.

## Build It

The program in `code/main.py` is a self-contained multicast toolkit (stdlib only):

1. **`ipv4_to_multicast_mac(ip)`** — maps a Class D address to its `01:00:5E` Ethernet MAC and reports the 32-way aliasing set. Run it on `224.1.1.1` and `225.1.1.1` and confirm they collide.
2. **`rpf_check(router, source, arrival_iface, unicast_table)`** — returns accept/drop using the unicast next-hop table. Feed it the route-flap case and watch a valid-looking packet get dropped.
3. **`build_source_tree(graph, source, members)`** — runs RPF flood then recursive PRUNE, returning the surviving link set. Count the links before and after pruning.
4. **`build_core_tree(graph, core, members)`** — unions the shortest paths from each member to the core. Compare its link count and worst-case path length against the source tree.
5. **`main()`** drives all four on the textbook Fig. 5-16 topology and prints annotated traces.

Run it:

```
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Verify MAC mapping | `ipv4_to_multicast_mac()` output for two aliasing groups | Both produce identical `01:00:5E:..` and the tool names all 32 colliding IPs |
| Confirm RPF behavior | Accept/drop log per arrival interface | Packets on the reverse-path interface accept; all others drop, including stale-route case |
| Measure prune savings | Link count before vs. after PRUNE | Pruned tree has strictly fewer links and still reaches every member |
| Compare tree types | Source-tree vs. core-tree link counts & max path | Source tree shorter paths, more total state; core tree fewer trees, longer worst path |

## Ship It

Produce one artifact under `outputs/`:

- A **runbook** for "multicast receivers suddenly drop after a unicast route change" that walks RPF-interface verification (`show ip rpf <source>` equivalent).
- A **decision card**: dense → flood-and-prune (PIM-DM/DVMRP); sparse → shared tree (PIM-SM), with the storage math.
- The **annotated trace** from `code/main.py` showing flood → prune → final tree on Fig. 5-16.

Start with `outputs/prompt-multicast-routing.md`.

## Exercises

1. Map `232.10.20.30`, `224.138.20.30`, and `239.10.148.30` to Ethernet MACs. Which collide, and why? State the exact 5 discarded bits for each.
2. A router's RPF interface to source `10.0.0.1` is `eth2`. A multicast packet for that source arrives on `eth0` carrying valid payload. What happens and why? Now the operator changes the unicast metric so the next hop becomes `eth0` — re-run the check.
3. On the Fig. 5-16 topology in `code/main.py`, the 10-link broadcast tree prunes to 7 links for group 1 and 5 for group 2. Remove one member from group 2 and recompute — how many links survive now?
4. A sparse group has 50 members in a 100,000-router network with 200 active sources. Compute the per-router tree state for (a) source-based and (b) shared-tree designs. Which is viable and why?
5. A PIM-SM rendezvous point fails. Describe what receivers see, what state is lost, and how recovery happens. Contrast with a DVMRP source-tree where a non-RP router fails.
6. A DVMRP prune expires every 3 minutes under heavy join/leave churn. Sketch the traffic-vs-time graph on a non-member link and explain the periodic spikes. What soft-state tuning reduces them?

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Multicast | "Sending to many people" | One packet per link, replicated by routers only at tree branch points toward group members |
| Class D address | "A multicast IP" | `224.0.0.0/4`, top bits `1110`; 28-bit group id, only 23 bits survive into the Ethernet MAC |
| RPF | "The loop check" | Accept a packet only if it came in on the interface the router would use to reach the source unicast; else drop |
| PRUNE | "Stop sending" | Soft-state message up the RPF path removing a dead branch; expires and re-floods if not refreshed |
| GRAFT | "Re-join fast" | Explicit message to re-attach a pruned branch without waiting for the next flood cycle (RFC 1075) |
| Source-based tree | "Shortest-path tree" | Per-(source,group) tree; optimal paths but up to *mn* trees of router state (DVMRP, MOSPF) |
| Core-based tree | "Shared tree" | One tree per group rooted at a core/RP; less state, possibly longer paths (CBT, PIM-SM) |
| Dense / sparse mode | "Flood vs. join" | Dense = broadcast-then-prune; sparse = explicit JOIN toward a core. Choice driven by member fraction |

## Further Reading

- RFC 1075 — *Distance Vector Multicast Routing Protocol (DVMRP)* (Waitzman, Partridge, Deering, 1988): flood-and-prune, GRAFT.
- RFC 1584 — *Multicast Extensions to OSPF (MOSPF)* (Moy, 1994): link-state source trees.
- RFC 2189 — *Core Based Trees (CBT) Multicast Routing Architecture* (Ballardie, 1997).
- RFC 7761 — *Protocol Independent Multicast – Sparse Mode (PIM-SM)* (Fenner et al., 2016): the modern sparse-mode standard.
- RFC 1112 — *Host Extensions for IP Multicasting* (Deering, 1989): IGMP and the `01:00:5E` MAC mapping.
- RFC 2365 — *Administratively Scoped IP Multicast* (`239.0.0.0/8`).
- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., §5.2.8 (Multicast Routing) and §5.6 (IGMP / Internet multicast).
- Deering & Cheriton, "Multicast Routing in Datagram Internetworks and Extended LANs," *ACM TOCS*, 1990.
