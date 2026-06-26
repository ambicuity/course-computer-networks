# Anycast Routing

> Anycast delivers a packet to the *nearest* member of a group that shares one address, where "nearest" is defined by the routing metric, not by geography. It needs no new protocol: ordinary distance-vector (Bellman-Ford) and link-state (Dijkstra) routing already produce anycast routes because the routing protocol believes the many service instances are one node. In production, anycast is implemented by injecting the *same* prefix (e.g. `192.0.2.0/24` for IPv4 or `2001:db8::/48` for IPv6) into BGP from multiple sites; the BGP best-path algorithm picks the lowest cost — usually fewest AS-path hops — and each ingress router lands on its closest replica. The famous deployments are DNS root servers (all 13 letters A–M run on hundreds of anycast instances) and CDNs. The classic failure modes are *anycast flapping* (a TCP flow re-pathed mid-connection to a different replica, breaking session state), and *traffic black-holing* when a withdrawn route or a stale BGP advertisement keeps drawing packets to a dead site. Link-state routing adds one rule the textbook flags: the router-vs-host distinction must stop the SPF tree from routing *through* an anycast instance, which would be a meaningless "jump through hyperspace" between physically separate nodes.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Distance-vector routing (Bellman-Ford), link-state routing (Dijkstra/SPF), IP addressing and prefixes, basic BGP path selection
**Time:** ~90 minutes

## Learning Objectives

- Explain why anycast requires *no* new routing protocol and how distance-vector and link-state algorithms produce anycast routes from a shared address.
- Compute, by hand and in code, which anycast instance a given source reaches by running shortest-path over a topology where one address appears at multiple nodes.
- Distinguish unicast, broadcast, multicast, and anycast by their delivery semantics and the routing state each leaves behind.
- Identify the link-state "no transit through an anycast host" rule and explain the hyperspace-jump bug it prevents.
- Diagnose two real anycast failure modes — mid-flow re-pathing of stateful TCP and route-withdrawal black-holing — from routing-table evidence.
- Map the abstraction to its real Internet deployment: same prefix advertised via BGP from many points of presence (DNS roots, CDNs).

## The Problem

You operate a global DNS resolver service reachable at a single IP, `203.0.113.53`. A user in Frankfurt reports 180 ms query latency; a user in Singapore reports 4 ms. Both are hitting "the same server" as far as the address is concerned. You did not configure 200 separate IPs and a load balancer in front of them — there is no single front door to balance. Instead you advertised one `/24` prefix from twelve points of presence and let routing decide. Now a third user complains: their long-lived DNS-over-TCP/853 session resets every few minutes. Nothing in your application logs explains it.

These three symptoms — wildly different latency to one address, no central balancer, and intermittent TCP resets — are the signature of anycast. The address is real; the "node" behind it is a fiction maintained by the routing protocol. To debug this you have to stop thinking about *the* server and start thinking about *which instance* each source's shortest path lands on, and what happens when that shortest path changes underneath an open connection.

## The Concept

### Four delivery models, one address space

Anycast is the fourth member of a family. The difference is purely in *how many* recipients a single send reaches and *which* ones.

| Model | Recipients per send | Address semantics | Routing state |
|---|---|---|---|
| Unicast | Exactly one | Address names one interface | Normal shortest path to that node |
| Broadcast | All nodes in a domain | Reserved all-ones / subnet directed | Spanning tree or flood, no per-dest path |
| Multicast | All members of a group | Class D / `ff00::/8`, group address | Distribution tree (e.g. via IGMP/PIM) |
| **Anycast** | **The one nearest member** | **One address shared by many nodes** | **Shortest path — protocol thinks it's one node** |

The key insight, from Partridge et al. (1993): anycast reuses the *unicast* routing machinery. There is no group membership protocol, no tree, no replication. You give several physical nodes the same address and the shortest-path computation does the rest.

### Why no new protocol is needed

Suppose four service instances all advertise the address `1`. Distance-vector routing distributes distance vectors exactly as it always does. Each router runs Bellman-Ford: `D(v) = min over neighbors w of [ cost(v,w) + D(w) ]`. Because every instance claims address `1`, each router simply converges on the *cheapest* of the competing advertisements for `1`. The protocol never learns there are four instances; it believes all of them are the same node `1`. Every router therefore forwards toward whichever instance is closest by metric.

The SVG (`assets/anycast-routing.svg`) shows this directly: on the left, the real topology with four shaded replicas of address `1`; on the right, the *collapsed* topology the routing protocol imagines — a single node `1` that everyone reaches by shortest path. The dashed berry arrows trace each source's chosen instance.

Link-state routing produces the same result with one extra rule, discussed below.

### Worked example: who reaches which instance

Consider this weighted graph. Nodes `A`, `B`, `C`, `D` are clients; `S1`, `S2` are two instances of the anycast service, both advertising address `S`.

```text
A --1-- B --4-- C --1-- D
|               |
2               2
|               |
S1              S2
```

Run shortest path from each client to the *virtual* node `S` (the minimum over both instances):

| Source | Cost via S1 | Cost via S2 | Chosen instance | Total cost |
|---|---|---|---|---|
| A | 0+2 = 2 | 1+4+1+2 = 8 | **S1** | 2 |
| B | 1+2 = 3 | 4+1+2 = 7 | **S1** | 3 |
| C | 4+1+2 = 7 | 1+2 = 3 | **S2** | 3 |
| D | 1+4+1+2 = 8 | 0+2 = 2 | **S2** | 2 |

The "catchment" of `S1` is `{A, B}`; the catchment of `S2` is `{C, D}`. The boundary sits on the `B–C` link. `code/main.py` builds exactly this kind of graph, runs Dijkstra from every source to a *synthetic* sink fused from all instances, and prints the catchment map plus the per-source winning instance — reproducing this table programmatically.

### The link-state "no hyperspace jump" rule

The textbook flags one subtlety for link-state routing. If the SPF tree were allowed to route *through* an anycast instance to reach some other destination, the path would silently teleport: instance `S1` in Frankfurt and instance `S2` in Singapore are the same node `S` to the algorithm, so a "short path" that enters `S` near Frankfurt and exits near Singapore is physically impossible — a jump through hyperspace.

Link-state protocols already prevent this because they distinguish *routers* (which transit traffic) from *hosts* (which do not). An anycast service instance is advertised as a host/leaf, so SPF will deliver *to* it but never compute a path *through* it. In OSPF terms, the instance is a stub network, not a transit link. Forget this distinction and your SPF will compute impossible shortcuts.

### From the abstraction to the Internet: BGP anycast

On the real Internet you do not hand-edit distance vectors. You inject the same prefix into BGP from many sites. The BGP best-path algorithm — comparing `LOCAL_PREF`, then shortest `AS_PATH`, then `MED`, then eBGP-over-iBGP, then lowest IGP cost to next hop — selects one origin per ingress router, and that selection is the anycast decision.

| Layer in the model | Real-world realization |
|---|---|
| "Address `1` advertised by many nodes" | One `/24` (or `/48` IPv6) originated from N points of presence |
| "Routing protocol picks cheapest" | BGP best-path: AS-path length, MED, IGP metric |
| "Catchment of an instance" | The set of source ASes whose best path lands on that PoP |
| "Instance withdrawn" | BGP `WITHDRAW` for the prefix from one PoP |

DNS root servers are the canonical case: each letter A–M is a single IP served by hundreds of physical instances worldwide. Your stub resolver sends to `198.41.0.4` (the A root) and BGP delivers it to the nearest mirror. CDNs use the same trick to pull users to the closest cache.

### Failure mode 1: mid-flow re-pathing breaks TCP

Anycast assumes any instance is interchangeable, which is true for *stateless* request/response (a single DNS/UDP query). It is false for *stateful* sessions. If a BGP route change or IGP recomputation shifts a source's shortest path from `S1` to `S2` while a TCP connection is open, the next segment arrives at `S2`, which has no record of that connection's sequence numbers and replies `RST`. This is *anycast flapping*. Evidence: a `RST` from the server with a valid 4-tuple but no matching session, and a routing-table change (BGP `UPDATE` / SPF event) timestamped just before. Mitigations: keep anycast for stateless protocols, or pin stateful flows with a stable unicast address handed out after an initial anycast contact.

### Failure mode 2: black-holing on stale or withdrawn routes

If an instance dies but its prefix advertisement is not withdrawn — a wedged BGP session, a route still in a neighbor's RIB — traffic in that catchment keeps being drawn to a dead node and is silently dropped. The mirror image also bites: withdrawing a healthy instance during maintenance instantly shifts its entire catchment onto neighbors, which can overload them. Evidence: 100% loss from one region while others are fine, and a `show ip bgp <prefix>` still listing the dead PoP as best path.

## Build It

1. Read `code/main.py`. It models a weighted topology where one service address lives at several nodes.
2. The `anycast_catchments` function fuses all instances of the shared address into one synthetic sink, then runs Dijkstra from every client to that sink.
3. Run `python3 main.py`. Confirm the printed catchment table matches the worked example above (`S1: {A, B}`, `S2: {C, D}`).
4. Add a third instance `S3` on a new node and re-run. Watch the catchment boundaries move.
5. Trigger failure mode 1: call the provided `withdraw_instance(instances, "S1")` helper and re-run. Confirm A and B's catchment shifts to S2 and the total cost rises (A: 2→7, B: 3→6) — this is what happens to every open flow that was pinned to S1.
6. Compare the distance-vector result (Bellman-Ford, also implemented) against the link-state result. They agree, demonstrating the textbook claim that either algorithm produces anycast routes.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify anycast vs unicast | Same destination IP, different RTT and TTL from different sources; `dig +nsid` shows different instance IDs | You can state that the address is shared and routing chose the instance |
| Map a catchment | Dijkstra/BGP best-path output per source; `show ip bgp <prefix>` | Each source's winning instance matches the lowest-metric path |
| Diagnose TCP resets on anycast | Server `RST` with no matching session + a BGP/SPF event just prior | The route-change timestamp precedes the reset; flow was re-pathed |
| Diagnose regional black-hole | 100% loss from one region; stale best path still names a dead PoP | The withdrawn/wedged advertisement explains the drop |
| Justify the host/leaf rule | OSPF LSA showing the instance as a stub network | SPF delivers to but never transits the anycast node |

## Ship It

Produce one artifact under `outputs/`:

- A catchment map for a topology of your choice (source → winning instance, with costs).
- A one-page anycast failure-mode runbook covering re-pathing resets and black-holing.
- An annotated routing trace (distance-vector convergence or BGP best-path) showing instance selection.

Start with [`outputs/prompt-anycast-routing.md`](../outputs/prompt-anycast-routing.md) and the catchment table emitted by `code/main.py`.

## Exercises

1. In the worked example, change the `B–C` link cost from 4 to 1. Recompute every source's chosen instance by hand, then verify with `code/main.py`. Which sources switched, and why does lowering a single link cost move a catchment boundary?
2. Add a third instance `S3` two hops behind node `C` at total cost 5 from `C`. Does `S3` ever win a catchment? Explain using only the shortest-path argument — no new protocol allowed.
3. A long-lived DNS-over-TLS (TCP/853) session to an anycast resolver resets every few minutes. Write the exact sequence of evidence you would collect (server side and routing side) to prove the cause is re-pathing rather than an application bug.
4. Explain the "jump through hyperspace" problem to a colleague who thinks SPF should be allowed to route through any node. Give a concrete two-PoP example and state which OSPF mechanism prevents it.
5. You must take instance `S2` down for maintenance. Its catchment is 40% of traffic. Describe what BGP action you take, what happens to that catchment instantly, and one safeguard against overloading the neighbor that inherits it.
6. Contrast multicast and anycast: both involve a "group" address, yet one replicates to all members and the other reaches exactly one. Identify, for each, the routing state a core router must hold.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Anycast | "A load balancer in the network" | One address shared by many nodes; ordinary shortest-path routing delivers each source to its nearest instance — no balancer, no group protocol |
| Catchment | "The region a server covers" | The exact set of sources whose lowest-metric path lands on a given instance; its boundary sits on a link, computed by SPF/BGP |
| Anycast flapping | "The connection is unstable" | A stateful flow re-pathed mid-session to a different instance that has no session state, producing a TCP `RST` |
| Hyperspace jump | "A weird routing bug" | A link-state path that transits through an anycast node, teleporting between physically separate instances; blocked by the router/host (stub) distinction |
| Instance / PoP | "The server" | One physical replica advertising the shared anycast address; many exist behind one IP |
| BGP best-path | "How the route is chosen" | The deterministic tie-break (LOCAL_PREF → AS_PATH → MED → IGP) that makes the anycast instance decision on the real Internet |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, §5.2.9 "Anycast Routing"; §5.2.1–5.2.4 for distance-vector and link-state background.
- Partridge, Mendez & Milliken, **RFC 1546**, "Host Anycasting Service" (1993) — the original anycast proposal cited in the chapter.
- **RFC 4786** (BCP 126), "Operation of Anycast Services" — operational best practices for deploying anycast with BGP.
- **RFC 7094**, "Architectural Considerations of IP Anycast" — failure modes, statefulness, and the re-pathing problem.
- **RFC 4291**, "IP Version 6 Addressing Architecture" — IPv6 anycast addresses and the reserved Subnet-Router anycast address.
- **RFC 4271**, "A Border Gateway Protocol 4 (BGP-4)" — the best-path selection algorithm that realizes anycast on the Internet.
- **RFC 2328**, "OSPF Version 2" — stub networks and the router/host distinction behind the no-transit rule.
