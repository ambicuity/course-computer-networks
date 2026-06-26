# Design an Anycast DNS High-Availability Infrastructure

> A four-node anycast DNS deployment shares the VIP 192.0.2.53 across AS64501, AS64502, AS64503, and AS64504 in US-East, US-West, EU-West, and AP-South. Each node runs a local DNS health check every 5 seconds; three consecutive failures trigger a BGP route withdrawal that propagates in roughly 0.5 seconds, giving a worst-case failover of about 15.5 seconds end-to-end. ECMP across the four origins lets anycast clients pick the lowest-latency path, and the resulting per-region improvement over a unicast server pinned to US-East ranges from zero for US-East clients to 92% for AP-South clients dropping from 200 ms to 15 ms. The capstone models the topology, the route propagation, the three-strike detection, the BGP withdrawal timeline, and the latency win against a single-server unicast baseline.

**Type:** Capstone
**Languages:** Python, BIND/Unbound, dig, shell
**Prerequisites:** Phase 9 BGP and anycast lessons; Phase 12 DNS lessons; understanding of BGP AS-path selection and ECMP
**Time:** ~180 minutes

## Learning Objectives

- Design a four-node anycast DNS topology with one shared VIP and one ASN per region.
- Simulate BGP route propagation from each node and apply the shortest-AS-path selection rule.
- Implement the three-strike health check that drives a BGP route withdrawal, and explain why three is the typical production threshold.
- Measure end-to-end failover time: 3 strikes x 5 second probe interval plus 0.5 second BGP convergence, totaling roughly 15.5 seconds.
- Distribute client load using ECMP and compute the per-region query latency win against a unicast server pinned to a single site.
- Reason about split-brain, route dampening, and RPKI origin validation as defenses against the common failure modes of anycast.

## The Problem

DNS is the front door of every other service. When the front door falls, nothing behind it can be found. A traditional unicast DNS deployment concentrates the failure domain on a single server or a single VIP behind a load balancer, and resilience depends on the client resolver's patience: most resolvers try each upstream server for 5 seconds before giving up, so a two-server fallback costs 5 to 10 seconds of user-visible latency per failover, and a single-server deployment has no fallback at all.

Anycast is the standard remedy. The same IP address is announced from multiple geographically distributed sites using BGP, and the routing system steers every client to the topologically nearest origin. When one site goes dark, its BGP route is withdrawn, the network reconverges, and the surviving sites absorb the load with no client-side reconfiguration. The hard parts are in the timing budget: detection latency, BGP convergence latency, and the ECMP arithmetic that distributes load when several paths are equally good.

This capstone asks you to build a working simulator of that system. You will place four nodes in four regions, give them the VIP 192.0.2.53, wire up a 5-second health check, model the three-strike rule, watch a BGP withdrawal propagate in 0.5 seconds, and compare the anycast failover and per-region latency against a unicast baseline.

## The Concept

Anycast DNS looks like one network concept on a slide and behaves like four interlocking systems at runtime. The build has to keep them separate in your head so the code stays clear and the runbook stays honest.

### Anycast vs. unicast DNS in one table

Unicast assigns a single IP to a single origin. The address is reachable through one path; if the path breaks or the origin dies, the address becomes unreachable. Anycast assigns the same IP to multiple origins. The network sees four different paths, all terminating on different machines, all advertising the same prefix. Failover is automatic because BGP does it for you: withdraw the dead origin, the rest of the table shifts, traffic flows elsewhere.

| Property | Unicast | Anycast |
|---|---|---|
| Origins per VIP | 1 | N (here N=4) |
| Routing substrate | Static or single-path | BGP with multi-origin advertisement |
| Failover driver | Client resolver timeout (5 s+) | BGP withdrawal (0.5 s) plus health detection |
| Latency shape | One number for everyone | Per-client-region minimum across the N origins |
| Failure domain | Single origin | One origin of N (N-1 redundancy) |
| Configuration surface | Resolver list on every client | One VIP, transparent to clients |

### VIP advertisement and BGP path selection

Each node advertises the same /32 VIP from its own ASN: 192.0.2.53/32 announced by AS64501 from US-East, AS64502 from US-West, AS64503 from EU-West, and AS64504 from AP-South. A client in US-East (AS65001) receives four paths to the VIP. The BGP best-path algorithm picks the route with the shortest AS_PATH. Because the client is directly connected to all four DNS-node ASNs, every path is one AS hop, so the algorithm falls through to the next tie-breaker: lowest origin ASN, which is AS64501. In production that is overridden by IGP cost to the egress, but the simulator uses the ASN tie-break because it is deterministic and free of routing-protocol detail.

The wire format is a standard BGP UPDATE with MP_REACH_NLRI for IPv4 unicast, NEXT_HOP set to the loopback of the advertising router, and AS_PATH containing only the origin ASN. A withdrawal is a BGP UPDATE with the withdrawn routes field populated and no reachable NLRI.

### ECMP and load distribution

Equal-Cost Multi-Path applies when more than one path has the same AS_PATH length. In a healthy anycast setup every path from a client region to the VIP has length one, so all four are equal cost. Modern routers hash the five-tuple (src IP, dst IP, protocol, src port, dst port) over the available paths, which yields a stable, deterministic distribution per flow. The simulator approximates that with a lowest-latency tie-break: among equal-cost paths it picks the origin whose distance to the client is smallest.

With 5000 US-East hosts, 3000 US-West hosts, 4000 EU-West hosts, and 2000 AP-South hosts, the anycast layer routes 36% to DNS-US-EAST, 21% to DNS-US-WEST, 29% to DNS-EU-WEST, and 14% to DNS-AP-SOUTH. If one node dies, the surviving three absorb the full 14,000 hosts and the ECMP hash reshuffles automatically.

### Health-check-driven BGP withdrawal

A node that is reachable on the network but broken in software must still stop advertising the VIP, otherwise the network will keep sending queries to a black hole. The standard fix is a local health probe: a cron-like loop that resolves a known record (for example, `healthcheck.example.com A 127.0.0.1`) against the local Unbound instance every 5 seconds. The probe is "local" so a network partition does not produce a false negative.

The probe result feeds a strike counter. After three consecutive failures (15 seconds of dead service) the node instructs its BGP daemon (BIRD, FRR, or ExaBGP) to withdraw the VIP advertisement. The three-strike threshold tolerates a single transient failure (a brief CPU spike, a recursive resolver hiccup) without flapping the route, while still detecting real failures inside the 15-second SLA most operators target.

### Failover timing model: probe plus propagation

The end-to-end failover budget has three parts: the 5-second probe period, the three-strike threshold (worst-case detection 15 seconds, best case 10 seconds if the node fails right after a successful probe), and the 0.5-second BGP convergence for a single-route withdrawal in a clean topology. The total is roughly 15.5 seconds end-to-end, dominated by detection.

```
t=0.0s  node crash
t=5.0s  probe 1 fails, strikes=1
t=10.0s probe 2 fails, strikes=2
t=15.0s probe 3 fails, strikes=3, BGP UPDATE withdraw sent
t=15.5s route withdrawal converges, all clients rerouted
```

### Geographic latency matrix

The latency win of anycast comes from the difference between the distance from the client to its nearest node and the distance to the unicast server. The simulator's latency matrix is a 4x4 grid of round-trip-time estimates in milliseconds, calibrated to real public latency numbers between the four regions:

| Client / Node | US-East | US-West | EU-West | AP-South |
|---|---|---|---|---|
| US-East   | 8   | 45  | 85  | 200 |
| US-West   | 45  | 8   | 140 | 150 |
| EU-West   | 85  | 140 | 12  | 180 |
| AP-South  | 200 | 150 | 180 | 15  |

The anycast picker reads the row for the client region and picks the column with the smallest entry. The unicast comparison pins every client to the US-East column. The improvement is `(unicast - anycast) / unicast * 100`: zero for US-East clients, 82% for US-West, 86% for EU-West, 92% for AP-South.

### RPKI route origin validation

A misconfigured or malicious AS can advertise the same /32 from a completely different location and hijack the VIP. Resource Public Key Infrastructure (RPKI) lets the legitimate owner of 192.0.2.0/24 sign a Route Origin Authorization (ROA) saying "AS64501 through AS64504 are the only ASNs authorized to originate 192.0.2.53/32." Every BGP router in the path can validate the advertisement against the ROA using the RPKI to router protocol (RFC 6810). Invalid origins are rejected and the route is not installed. Production anycast operators (the DNS root servers, large CDNs, public resolvers) all run RPKI-validating routers for exactly this reason.

### Split-brain and network partition risks

The three-strike rule is local to the node. If the DNS service is broken but the BGP session stays up, the probe detects the failure and the route is withdrawn. But if the network between the node and the rest of the Internet partitions, the node may keep advertising because the local probe still answers. Conversely, if the BGP session to its upstream goes down, the node will withdraw the route even if DNS is healthy. Both cases produce a "split-brain" where some clients keep sending to the dead node for as long as their routers hold the stale route. Mitigations include BFD for sub-second BGP session failure detection, route dampening to suppress flapping, and anycast health checks that probe from multiple external vantage points.

### Worked failover timeline

A single node failure produces this timeline in the simulator:

```
0.0s   DNS-US-EAST process crashes, local socket stops responding
5.0s   probe 1 from US-East node to its own Unbound: timeout, strikes=1
10.0s  probe 2 fails, strikes=2
15.0s  probe 3 fails, strikes=3, FRR sends BGP UPDATE withdraw
15.5s  withdrawal propagates through transit, all routers update
15.5s  US-East clients pick DNS-US-WEST (45 ms, next-best AS_PATH)
15.5s  EU-West, AP-South clients stay on their regional nodes
15.5s  load on US-West node rises from 3000 to 8000 clients
```

The 15.5 second number is the worst case for the simulator's parameters. Production deployments that want sub-5-second failover drop the probe interval to 1 second, keep the three-strike threshold (so detection is at most 3 seconds), and rely on the same 0.5 second BGP convergence.

## Build It

`code/main.py` is a stdlib-only Python simulator. Run it with `python3 code/main.py` and read the printed output. The implementation has six pieces:

1. **Topology** - `build_topology()` returns four `Node` records (one per region, each with an ASN and a 4-entry latency dict) and four `Client` records (one per client region, each with a host count, an ASN, and a list of connected ASNs).
2. **BGP route propagation** - `propagate_routes()` walks every (client, advertising node) pair, builds an AS_PATH, marks the route active only if the node is still advertising, and sorts by AS_PATH length with origin ASN as a deterministic tie-break.
3. **Path selection** - `select_node()` takes the shortest-AS_PATH route and, if multiple routes tie, picks the one with the lowest latency to the client. That emulates the ECMP lowest-latency tie-break performed by most ISP routers.
4. **Health check loop** - `simulate_failover()` marks the victim node failed, runs 5-second probe rounds, accumulates strikes, and emits a `BGP-WITHDRAW` event the moment the third strike fires. The simulation then advances 0.5 seconds for BGP convergence and emits the `CONVERGED` and `REROUTED` events.
5. **Load distribution** - `ecmp_distribution()` runs the path selector for every client region and tallies the host count per chosen node.
6. **Comparison** - `compare_with_unicast()` rebuilds a fresh healthy topology, runs the anycast path selector on it, and pairs the result with the latency that each client region would see if every query went to the US-East node. That is the unicast baseline.

The output shows the four-node topology, the BGP route table per client region, the query routing and per-region latency, the load distribution, the failover timeline, the post-failover rerouting, and the per-region anycast-versus-unicast comparison.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Verify the four-node topology | `DNS Nodes (4)` table | Four rows: DNS-US-EAST AS64501, DNS-US-WEST AS64502, DNS-EU-WEST AS64503, DNS-AP-SOUTH AS64504, all initially HEALTHY and advertising |
| Verify the VIP is 192.0.2.53 | `Anycast VIP:` line | Single line reading `Anycast VIP: 192.0.2.53` |
| Verify per-region routing | `Query routing` table | US-East -> DNS-US-EAST (8 ms), US-West -> DNS-US-WEST (8 ms), EU-West -> DNS-EU-WEST (12 ms), AP-South -> DNS-AP-SOUTH (15 ms) |
| Verify the three-strike rule | `Failover Simulation` block | Sequence `t=0.0s NODE-DOWN`, `t=15.0s BGP-WITHDRAW after 3 strikes`, `t=15.5s CONVERGED` |
| Verify the BGP convergence budget | `Total anycast failover time` line | Approximately 15.5 s, with the breakdown `(HC: 15s, BGP converge: 0.5s)` |
| Verify the unicast win | `Anycast vs. Unicast Comparison` block | AP-South around 92%, EU-West around 86%, US-West around 82%, US-East around 0% |
| Verify N-1 redundancy | `Redundancy` row in the metric table | Anycast column reads `N-1`, Unicast column reads `None` |
| Verify ECMP tie-break | `Load distribution` block | Each node receives a share proportional to the host population of its region |

## Ship It

Outputs land in `outputs/`:

- `anycast-topology.txt` - The four-node topology with regions, ASNs, status, advertising flag, and per-node latency to each client region.
- `bgp-route-table.txt` - The BGP route table for every client region: every (origin node, AS_PATH, active flag) tuple, sorted by AS_PATH length.
- `failover-timeline.txt` - A chronological log of the failover event with timestamps in seconds, the event kind (NODE-DOWN, BGP-WITHDRAW, CONVERGED, REROUTED), and a one-line description.
- `latency-comparison.txt` - A per-region side-by-side: anycast latency in ms, unicast latency in ms, and percent improvement, plus the full 4x4 latency matrix.
- `anycast-design-runbook.md` - A runbook that walks a new operator through deploying a four-node anycast with BIRD or FRR, configuring the VIP advertisement on each node, setting up the 5-second health check, and the steps to verify failover in a staging environment.

## Exercises

1. **Fifth node** - Add a fifth DNS node in SA-East (South America, AS64505) with a 4-entry latency row, then re-run the simulator. Does the average anycast latency across all four client regions drop, and by how much? What is the failure-domain trade-off of adding a fifth node?
2. **BGP route dampening** - Implement RFC 2439 route dampening in the simulator: when a node flaps (withdraws and re-advertises inside 30 seconds), suppress its advertisements for an exponentially decaying penalty window. How does dampening interact with the three-strike health check when a node is failing intermittently?
3. **Query load under failure** - Add a 10,000 queries/second arrival rate to each client region, and after the failover compute the new per-node query rate. Does any surviving node cross its capacity threshold, and what is the load-shift multiplier?
4. **RPKI origin validation** - Add an RPKI check to `propagate_routes()`: if a node's ASN is not in the authorized-origin set for 192.0.2.53, the route is marked invalid and excluded. Then add a rogue AS advertising the same VIP and verify the simulator refuses to install the route.
5. **Network partition** - Simulate a partition that splits the four nodes into {US-East, US-West} and {EU-West, AP-South}, where no BGP UPDATE can cross the partition. How does the client behavior differ for clients in the partition that contains the failed node versus clients on the other side? What is the split-brain risk and how would BFD on the BGP sessions mitigate it?
6. **Health check from external vantage points** - Replace the local probe with a check that queries the local node from two external probe boxes (one in a different region than the node). How does this change the failure-detection time, and what new false-positive mode does it introduce?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Anycast | A clever routing trick | Multiple origins advertise the same prefix; BGP best-path picks the nearest origin per client |
| VIP | A virtual IP | The single IP (here 192.0.2.53) that clients use; the network decides which origin answers |
| BGP route withdrawal | Removing an advertisement | A BGP UPDATE that drops the prefix; causes traffic to shift to the next-best path |
| AS_PATH | The list of autonomous systems | The sequence of ASNs a route has traversed; shorter is better under the BGP best-path algorithm |
| ECMP | Load balancing | Equal-Cost Multi-Path: when multiple paths tie on cost, traffic is hashed across them per flow |
| Health check | A ping | A local or external probe that decides whether a node is healthy enough to keep advertising the VIP |
| Three-strike rule | A counter | After three consecutive probe failures, the node withdraws the route; tolerates one transient blip |
| BGP convergence | When the network catches up | The time from a route change to all routers in the path holding the new table |
| RPKI | Crypto for routing | A signed authorization that lists which ASNs may originate a prefix; routers reject invalid origins |
| Split-brain | Two brains, one body | A failure mode where some clients keep sending to a node the rest of the network has given up on |
| Route dampening | A flapping penalty | RFC 2439: routes that flap are suppressed for an exponentially decaying window |
| BFD | Sub-second keepalive | Bidirectional Forwarding Detection: detects BGP session failure in milliseconds, not seconds |

## Further Reading

- RFC 4786 - Operation of Anycast Services (the foundational anycast architecture document)
- RFC 7098 - Use of Anycast in DNS (the DNS-specific application, written for the root-server operators)
- RFC 6810 / RFC 6811 - The Resource Public Key Infrastructure to Router protocol and origin validation
- RFC 2439 - BGP Route Flap Damping (the dampening algorithm referenced in the exercises)
- RFC 5880 / RFC 5881 - Bidirectional Forwarding Detection (BFD), the sub-second BGP session failure detector
- RFC 4271 - A Border Gateway Protocol 4 (BGP-4) (the BGP specification that drives anycast convergence)
- "BGP Design and Implementation" by Randy Zhang and Micah Bartell (Cisco Press, the operator's handbook for anycast-grade BGP)
- "DNS and BIND" by Cricket Liu and Paul Albitz (the canonical reference for the DNS side of the design)
- BIRD Internet Routing Daemon documentation (https://bird.network.cz/) - the open-source BGP daemon used by most anycast operators
- FRRouting documentation (https://frrouting.org/) - the Linux Foundation fork of Quagga, also widely used
- RIPE Atlas probes (https://atlas.ripe.net/) - the public measurement network used to validate anycast convergence in production
