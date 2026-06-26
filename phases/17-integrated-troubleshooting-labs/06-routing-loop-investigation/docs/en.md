# Routing Loop Investigation

> A network engineer sees `traceroute` return the same three router IPs in a cycle, with TTL exceeded messages incrementing but never reaching the destination. Meanwhile, `ping` times out, SSH sessions freeze, and the routing protocol's logs are full of "neighbor adjacency change" notifications. This is a **routing loop** — a forwarding loop in the data plane where packets bounce between two or more routers, incrementing their TTL each hop, until the TTL expires and the packet is dropped. This lesson walks the diagnostic chain for routing loops: how to identify one from `traceroute` output, how to map it to a specific topology mistake using `show ip ospf database` and `show ip bgp`, how to disambiguate it from a forwarding-plane loop (Layer 2) and from a transient convergence event, and the operational discipline of using TTL-based mitigation, route dampening, and BFD. The synthetic trace generator in `code/main.py` models the control-plane adjacency messages, the data-plane TTL cascade, and the BGP UPDATE loop that produces an oscillating routing table.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 04 IP forwarding, Phase 05 OSPF, Phase 05 BGP, Phase 13 ICMP TTL exceeded, Lesson 01 of this phase
**Time:** ~110 minutes

## Learning Objectives

- Identify a routing loop from `traceroute` output: a sequence of repeated router addresses with TTLs incrementing linearly, never reaching the destination.
- Distinguish a routing loop (Layer 3) from a Layer-2 forwarding loop (which produces MAC address flapping and broadcast storms) and from a transient convergence event (where the loop self-resolves in seconds).
- Read the OSPF LSDB and BGP table to find the topology mistake that produces the loop: a missing route, a misconfigured route map, a redistributed static route, an aggregate that's too specific, a missing null0/discard route.
- Apply a four-command diagnostic chain (`traceroute`, `ip route get`, `show ip ospf database`, `show ip bgp`) to identify the loop and the offending router.
- Explain why ICMP TTL Exceeded messages are themselves subject to loops (the "TTL exceeded storm" problem) and how to mitigate with rate-limited TTL responses.
- Construct a synthetic routing-protocol simulator (no live devices required) that models a misconfigured network and demonstrates the oscillating routing table and TTL cascade.

## The Problem

A medium-sized enterprise runs a hub-and-spoke OSPF network with two core routers (CORE-A, CORE-B) and a BGP edge to two ISPs. Last night, a network engineer deployed a new prefix-list on the edge router connecting to ISP-1, intending to filter inbound bogons. The change should have been routine. By morning, the help desk is flooded with complaints: half the company cannot reach `8.8.8.8`, `github.com`, or the company's SaaS providers. `ping 8.8.8.8` times out. `traceroute 8.8.8.8` shows hops 4–11 cycling through the same three internal routers: `10.0.0.1`, `10.0.0.2`, `10.0.0.3`, with the same TTL values repeating in a pattern like `1 2 3 1 2 3 1 2 3 ...`. SSH sessions to internal hosts are sluggish — connection succeeds but every command takes 5 seconds to type. The OSPF logs on the core routers show "neighbor 10.0.0.2, Interface GigabitEthernet0/0/1 changed state to DOWN" followed 30 seconds later by "neighbor 10.0.0.2, Interface GigabitEthernet0/0/1 changed state to UP," repeating every 30 seconds.

What happened: the new prefix-list accidentally permitted a more-specific prefix (192.0.2.0/24) for an internal subnet to be advertised to ISP-1. ISP-1 accepted it and advertised it to ISP-2. ISP-2's route to the internal subnet was via the company's own BGP edge, and BGP's loop prevention rejected the advertisement on ISP-2's side. But on the company's edge, the redistributed static route for 192.0.2.0/24 (intended for a point-to-point link to a partner) was now being preferred over the OSPF route to the internal subnet, because BGP's AD (Administrative Distance) of 20 beat OSPF's AD of 110. The edge router advertised the new "best" route to its BGP neighbor, ISP-1, which advertised it to ISP-2, which advertised it back to the company. The company's edge accepted the advertisement (because it had a different AS path) and updated its routing table. The new route pointed back into the company's internal network via CORE-A. CORE-A saw the new route, preferred it (because it was more specific), and forwarded packets to CORE-B, which forwarded them back to the edge, which forwarded them back to CORE-A. The routing table oscillated every 30 seconds as the BGP hold timer expired and the routes were re-advertised.

The result: a routing loop that ping-pongs packets between three routers until their TTL expires. From the user's perspective, the destination is unreachable; from the network's perspective, the routing table is "working correctly" by its own internal logic but the topology is broken.

The first responder's job is to identify the loop, find the offending router, and identify the specific route that's oscillating. The diagnostic chain in this lesson exists to do this in 5–10 minutes.

## The Concept

### What a Routing Loop Is (and Is Not)

A **routing loop** is a data-plane condition where a packet's TTL decrements at each hop but the path of routers is cyclic, so the packet never reaches its destination. After the TTL expires (TTL=0), the router drops the packet and sends an ICMP Type 11 Code 0 "Time Exceeded" message back to the source. The source's `traceroute` shows the cycle: same router addresses in a repeating pattern.

A routing loop is **not** the same as:

- **A Layer-2 forwarding loop**: A misconfigured switch network where a broadcast or unknown-unicast frame circulates indefinitely between switches. The symptom is `MAC address flapping` in the switch logs (the same MAC seen on two ports, alternating) and a CPU spike on the switches. There is no TTL cascade because Layer 2 frames don't have TTLs.
- **A transient convergence event**: A brief period (sub-second to a few seconds) after a topology change where routers are still updating their FIBs and may temporarily forward packets suboptimally. Traceroute during this window may show odd paths, but the loop self-resolves when the routing protocol reconverges.
- **A black hole**: A router has a route to a destination and forwards the packet, but the next hop silently drops it. Traceroute shows the path getting to a certain hop and then `* * *` (no response) for subsequent hops. There is no cycle.

The signature that uniquely identifies a routing loop is **a cycle in the traceroute output**: the same router addresses appear in a repeating pattern, with TTLs incrementing normally. The pattern `1 2 3 1 2 3 1 2 3` is a 3-router loop; `1 2 1 2 1 2` is a 2-router loop; `1 2 3 4 1 2 3 4 1 2 3 4` is a 4-router loop.

### Why Routing Loops Happen

The most common causes, in approximate order of frequency in production networks:

1. **Inconsistent routing tables during convergence**: After a topology change, different routers in the network may have inconsistent views of the topology for a brief period. A packet can be forwarded by router A using one path, then by router B using a different path that points back to router A. This is a transient loop; it self-resolves in seconds.

2. **Misconfigured static routes or redistribution**: A static route that points to an interface that is down, or that conflicts with a dynamic route, can cause a router to forward packets to a neighbor that has a different view of the topology. The `ip route 0.0.0.0 0.0.0.0 <wrong-gw>` mistake is the canonical example.

3. **BGP route oscillation**: When a route is advertised, accepted, and re-advertised in a cycle (BGP doesn't have built-in loop prevention for IBGP, and eBGP only prevents the loop within an AS path), the routing table can oscillate. The fix is the BGP "full mesh" or "route reflector" rule for IBGP.

4. **Aggregated routes that are too specific**: A `summary-address` or `aggregate-address` that covers a smaller range than the underlying specific routes can create a "less-specific" route that points back into the network. The fix is to always advertise a black-hole (null0) route alongside the aggregate.

5. **OSPF area mismatches or LSA type confusion**: A Type-3 LSA (summary) that is generated for a range the ABR doesn't actually own, or a Type-5 LSA (external) that points to an external network via a wrong forwarding address, can produce a loop.

6. **Misconfigured route maps or prefix lists**: A route map that matches the wrong community, or a prefix list that inadvertently matches an internal prefix, can cause routes to be advertised that should not be.

### The Four-Command Diagnostic Chain

| # | Command | Healthy output | Problem output | Points to |
|---|---------|----------------|----------------|-----------|
| 1 | `traceroute -n <dst>` | Strictly increasing router addresses, terminating at dst | Cycle: same addresses repeat, no termination | Routing loop confirmed |
| 2 | `ip route get <dst>` | `via <next-hop> dev <iface>` | `via <next-hop> dev <iface>` that points to a router in the loop | Which router is the source |
| 3 | `show ip ospf database` (Cisco) / `vtysh -c 'show ip ospf database'` (FRR) | Consistent LSDB across routers | One router has a different LSA for the affected prefix | OSPF-level cause |
| 4 | `show ip bgp` (Cisco) / `vtysh -c 'show ip bgp'` (FRR) | Consistent BGP table, AS paths are stable | Route is flapping; AS path oscillates | BGP-level cause |

The order matters: `traceroute` is the most decisive single command for *identifying* the loop. `ip route get` is the most decisive for *finding the source router*. The OSPF and BGP commands are most decisive for *identifying the topology mistake* that produced the loop.

### Reading `traceroute` Output

A `traceroute` to `8.8.8.8` from a workstation inside the enterprise:

```text
$ traceroute -n 8.8.8.8
 1  10.0.0.1  0.412 ms  0.398 ms  0.401 ms    # CORE-A
 2  10.0.0.2  1.213 ms  1.198 ms  1.205 ms    # CORE-B
 3  10.0.0.3  2.401 ms  2.398 ms  2.405 ms    # EDGE-1
 4  10.0.0.1  3.602 ms  3.598 ms  3.601 ms    # CORE-A   <- cycle start
 5  10.0.0.2  4.811 ms  4.798 ms  4.805 ms    # CORE-B
 6  10.0.0.3  5.999 ms  5.998 ms  6.005 ms    # EDGE-1
 7  10.0.0.1  7.198 ms  7.198 ms  7.201 ms    # CORE-A
 8  10.0.0.2  8.411 ms  8.398 ms  8.405 ms    # CORE-B
 9  10.0.0.3  9.602 ms  9.598 ms  9.605 ms    # EDGE-1
10  10.0.0.1 10.811 ms 10.798 ms 10.805 ms    # CORE-A
...
30  * * *                                     # TTL exceeded; ICMP lost
```

The cycle is unambiguous: hops 1, 4, 7, 10 are all `10.0.0.1` (CORE-A); hops 2, 5, 8 are `10.0.0.2` (CORE-B); hops 3, 6, 9 are `10.0.0.3` (EDGE-1). The TTLs are incrementing (each cycle is 3 hops), so the packet is making progress through the loop; eventually the TTL reaches 0 and the packet is dropped. The `* * *` at hop 30 indicates that the ICMP TTL Exceeded message from a router in the loop was itself lost (perhaps because the loop's ICMP rate-limit kicked in, or because the message's TTL was insufficient to escape the loop).

The `ms` columns tell you how long each hop took: ~1 ms per hop is typical for a healthy enterprise. In the example above, the times are increasing by ~1.2 ms per hop because each router is processing the packet and adding its forwarding delay. If the times are not increasing (e.g., 0.4 ms at hop 1 and 0.4 ms at hop 7), the router is forwarding the packet immediately without lookup, which is suspicious.

### `ip route get`: The Local Router's View

The next command is to ask the local router (or the workstation's kernel) where it would send a packet to the destination:

```text
$ ip route get 8.8.8.8
8.8.8.8 via 10.0.0.3 dev eth0 src 10.0.0.5 uid 1000
   cache
```

This says: the kernel would send the packet to `10.0.0.3` (EDGE-1) via `eth0`, with source `10.0.0.5`. The `cache` keyword means the route is in the kernel's route cache (or, in newer kernels, the FIB). If the kernel's choice is `10.0.0.3` and the traceroute shows `10.0.0.3` as hop 3, then the local router is sending the packet into the loop. The next step is to SSH to `10.0.0.3` and run `ip route get 8.8.8.8` from its perspective. If `10.0.0.3` says "via `10.0.0.1`," then `10.0.0.3` is forwarding to `10.0.0.1`, and we have a 2-router sub-loop between `10.0.0.1` and `10.0.0.3`.

This is the recursive walk: at each router in the loop, run `ip route get <dst>` and follow the chain. The chain ends when you reach a router whose `ip route get` returns the destination directly (the loop is broken at that router), or when you return to a router you've already visited (you've found the cycle).

### Reading the OSPF LSDB and BGP Table

The next step is to identify the topology mistake. For OSPF, the relevant command is `show ip ospf database` (Cisco) or `vtysh -c 'show ip ospf database router self-originate'` (FRR). The output shows every LSA in the LSDB. Look for:

- A Type-5 LSA (external route) with a forwarding address that points to an internal IP
- A Type-3 LSA (summary) for a prefix that the ABR doesn't actually own
- An LSA with a metric that doesn't make sense (e.g., a Type-1 LSA with metric 65535 for a directly connected prefix)

For BGP, the relevant command is `show ip bgp <prefix>`. The output shows the AS path, the next hop, the local preference, the MED, the community, and the origin. Look for:

- An AS path that contains your own AS (a loop the protocol should have caught)
- An AS path that oscillates between two states (BGP route flap)
- A next hop that points to an internal IP
- A local preference that's higher than the default (which would override the IGP metric)

### ICMP TTL Exceeded Storms

When a packet's TTL expires, the router sends an ICMP Type 11 Code 0 "Time Exceeded" message back to the source. If the source is in a routing loop too (e.g., the source is in the same enterprise as the destination and is itself affected by the loop), the ICMP message itself can be looped. The result is an **ICMP TTL Exceeded storm**: the router spends all its CPU generating ICMP messages for every expired packet, the ICMP messages go into the loop, the ICMP messages expire, and the router generates more ICMP messages for those.

Modern routers mitigate this with rate-limited TTL responses: the router will only send N ICMP TTL Exceeded messages per second per source, where N is typically 1–10. Beyond that, the ICMP messages are dropped silently. This prevents the storm but also means that `traceroute` may show `* * *` for some hops in the loop.

### The TTL Field and the Forwarding Decision

The TTL field in the IPv4 header (and the Hop Limit field in IPv6) is decremented by 1 at every router. When the TTL reaches 0, the router drops the packet and sends an ICMP Type 11 Code 0 message back to the source. The TTL field has two purposes:

1. **Prevent infinite forwarding loops**: If a routing loop exists, the TTL eventually expires and the packet is dropped.
2. **Limit the scope of a packet's lifetime**: The TTL is set by the source (typically 64 on Linux, 128 on Windows, 255 on some routers) and bounds the number of hops a packet can traverse.

The default TTL of 64 on Linux means a packet can traverse at most 64 routers before being dropped. This is more than enough for the entire Internet (the longest path on the Internet is typically < 30 hops), but it is not unlimited. A 3-router loop will burn through 64 hops in 21 cycles; at 1 ms per cycle (typical for a tight loop), the packet is dropped in 21 ms.

The TTL is also a security feature: an attacker who can craft packets with very short TTLs can probe the network without being seen (the ICMP TTL Exceeded messages would not reach the source because they would expire before they got out). Tools like `traceroute` exploit this: by setting the TTL to 1 first, then 2, then 3, ..., the source can map the path hop by hop.

### Mitigation: BFD, Route Dampening, and TTL-Based Defenses

Three operational mitigations for routing loops:

1. **BFD (Bidirectional Forwarding Detection)**: A sub-second liveness protocol that detects when a neighbor has become unreachable, allowing the routing protocol to withdraw the route quickly. BFD is enabled on the interface level and runs at 50 ms × 3 = 150 ms detection time by default. With BFD, a routing loop self-resolves in 150 ms instead of the OSPF default 40 s.

2. **Route dampening**: A BGP feature that suppresses a route that has flapped recently. A route that has been withdrawn and re-advertised more than N times in T minutes is suppressed for a "half-life" period. This prevents the routing table from oscillating.

3. **TTL-based defenses**: Some operators configure edge routers to drop packets with very low TTLs (e.g., TTL < 5) to prevent TTL-based probing. This is a security measure, not a loop mitigation; it does not help with the routing loop itself, but it does reduce the impact of TTL-based attacks.

## Build It

The `code/main.py` in this lesson is a synthetic routing-protocol simulator. It models a small network of routers, runs a simplified distance-vector/SPF computation, and demonstrates the routing table oscillation that produces a loop. It also models the `traceroute` output, the `ip route get` chain, and the BGP UPDATE sequence.

1. **Read** `code/main.py`. Notice the `Router` dataclass (frozen=True for the immutable config), the `Network` class that owns the routers and links, the `find_loop` function that walks `ip route get` recursively, and the `simulate_ospf_bgp` function that emits the control-plane events.
2. **Run** `python3 code/main.py --mode misconfigured_aggregate` (or `--mode ibgp_full_mesh_missing`, `--mode static_route_oscillation`, `--mode healthy`). You will see the routing table on each router, the `traceroute` output, the `ip route get` chain, and the BGP UPDATE sequence.
3. **Compare** the four modes side by side: `python3 code/main.py --mode all`. The output will show the diagnostic chain producing a different verdict for each case.
4. **Modify** the `Network` class to add a fifth mode where the routing loop is a transient convergence event (lasts 2 s, then resolves). Walk through the diagnostic chain and identify which step is *not* decisive for a transient loop.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| `ping` times out | `traceroute -n <dst>` | Cycle: same addresses repeat | Routing loop |
| `traceroute` cycles | `ip route get <dst>` | Next hop is a router in the cycle | Local router is sending into the loop |
| `traceroute` cycles, identified source | `show ip ospf database` (on source) | LSA with wrong forwarding address | OSPF config error |
| `traceroute` cycles, identified source | `show ip bgp` (on source) | AS path oscillates | BGP route flap |
| Loops only for some destinations | `traceroute` to each | One loops, others don't | Specific prefix is misconfigured |
| OSPF neighbor flapping | `show log \| i OSPF` | "Neighbor ... changed state to DOWN/UP" | Adjacency issue (Layer 1/2 or timer mismatch) |
| BGP route dampening active | `show ip bgp <prefix>` | `dampened` flag set | Route has flapped too many times |
| BFD active | `show bfd neighbors` | BFD neighbor UP | BFD is detecting failures quickly |
| ICMP TTL storm on a router | `show ip icmp statistics` | `ICMP Time Exceeded` rate-limited | TTL loop storm |
| Slow BGP convergence | `show ip bgp summary` | `Uptime` resets frequently | BGP session unstable |

## Ship It

The `outputs/prompt-routing-loop-investigation.md` file is your deliverable. Author a one-page runbook for "destination is unreachable" that contains:

1. The four-command diagnostic chain with one-line decision rules.
2. A reference table of "what the loop looks like" vs. "what a black hole looks like" vs. "what a transient convergence event looks like" — with one distinguishing feature for each.
3. A list of three common false-positive pitfalls: (a) `traceroute` may show `* * *` for some hops in the loop because of ICMP rate-limiting — does not mean the loop has resolved, (b) a loop that involves only one router's interface (e.g., the router is sending packets back out the same interface they came in on) may not be visible in `traceroute` if the router is suppressing ICMP for that interface, (c) a route flap dampening event may *hide* a loop temporarily — the loop is still there, the route is just suppressed.
4. An "intervention menu" with the specific commands to fix each root cause: fix the prefix-list, fix the redistribution, fix the BGP full mesh, add a null0 route for the aggregate.

## Exercises

1. **Loop detection**: A `traceroute` shows hops `1 2 3 1 2 3 1 2 3` for 30 hops and then `* * *`. Is this a routing loop, a black hole, or a transient convergence event? Justify.
2. **`ip route get` chain**: The local router's `ip route get 8.8.8.8` says `via 10.0.0.3`. On 10.0.0.3, the same command says `via 10.0.0.1`. On 10.0.0.1, it says `via 10.0.0.3`. What is the loop?
3. **OSPF LSA reading**: An OSPF Type-5 LSA has a forwarding address of `192.168.1.1` (an internal IP) and a metric of 20. What does this mean? Is it suspicious?
4. **BGP AS path**: A BGP route has an AS path of `65001 65002 65001` and the local AS is 65001. What does this mean? Should the router have accepted it?
5. **ICMP rate limit**: A `traceroute` shows `* * *` for hops 4–7 in a loop, but the same hops appear in subsequent traceroutes. Is the loop gone?
6. **Compare with lesson 01**: Lesson 01's chain reports layer-by-layer evidence for a *complete* failure. This lesson's chain focuses on a *specific layer* (Layer 3) for a *specific failure mode* (loop). How does the diagnostic chain narrow as the symptom becomes more specific?

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| Routing loop | A path that goes in circles | A data-plane condition where packets cycle through the same routers until TTL expires |
| Forwarding loop | A synonym | Often used interchangeably with routing loop; sometimes reserved for Layer-2 loops |
| TTL | Time to live | The IPv4 field (and IPv6 Hop Limit) that decrements at each hop and bounds packet lifetime |
| Traceroute | A tool | A diagnostic tool that uses TTL manipulation to map the path to a destination |
| ICMP Type 11 | A number | ICMP Time Exceeded — the message a router sends back when a packet's TTL reaches 0 |
| LSA | A term from OSPF | Link-State Advertisement — the unit of routing information in OSPF |
| LSDB | A term from OSPF | Link-State Database — the collection of all LSAs known to a router |
| BGP UPDATE | A message | The BGP message used to advertise and withdraw routes |
| AS path | A list | The sequence of AS numbers a BGP route has traversed, used for loop prevention |
| Route flap | A flap | A route that is repeatedly withdrawn and re-advertised, often due to an underlying topology issue |

## Further Reading

- **RFC 2328** — *OSPF Version 2*. The OSPF specification, including the LSA types and the SPF algorithm.
- **RFC 4271** — *A Border Gateway Protocol 4 (BGP-4)*. The BGP specification, including the UPDATE message format and the AS path loop prevention.
- **RFC 5082** — *The Generalized TTL Security Mechanism (GTSM)*. A technique to use TTL to validate that BGP peers are directly connected.
- **RFC 5880–5884** — *Bidirectional Forwarding Detection (BFD)*. The sub-second liveness protocol used to detect routing failures quickly.
- **Cisco's OSPF Design Guide** — the canonical guide to designing OSPF networks, including loop-avoidance best practices.
- **Cisco's BGP Best Path Selection Algorithm** — the algorithm BGP uses to choose between multiple routes for the same prefix.
- **phases/04-network-layer-and-ip** — IP forwarding, TTL, and the ICMP Time Exceeded message.
- **phases/05-medium-access-protocols** — OSPF and BGP fundamentals.
- **phases/17-integrated-troubleshooting-labs/01-physical-to-application-outage-trace** — the parent lesson whose bottom-up methodology this lesson specializes for Layer 3 loops.
- **phases/17-integrated-troubleshooting-labs/25-vrf-namespace-blackhole-asymmetric-routing** — the VRF-level routing black hole, a related failure class.
