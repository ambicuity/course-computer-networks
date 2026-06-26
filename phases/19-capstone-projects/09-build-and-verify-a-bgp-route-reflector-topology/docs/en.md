# Build and Verify a BGP Route Reflector Topology

> Design and simulate an iBGP route-reflector cluster, verify path selection against the AS-path rules, and demonstrate why full-mesh iBGP does not scale.

**Type:** Capstone
**Languages:** Python, FRRouting, shell
**Prerequisites:** Phase 9 BGP lessons; understanding of eBGP vs. iBGP, AS-path, route reflectors, and cluster IDs
**Time:** ~150 minutes

## Learning Objectives

- Build a BGP topology simulator with route reflectors (RR), RR clients, and non-clients
- Implement the three route-reflector advertisement rules: RR-to-client, RR-to-non-client, client-to-RR
- Verify AS-path propagation: eBGP-learned routes are re-advertised to iBGP peers; iBGP-learned routes are not re-advertised to other iBGP peers without a route reflector
- Simulate a 10-router full-mesh iBGP topology and count the required sessions (n*(n-1)/2)
- Compare full-mesh vs. route-reflector topology by session count and convergence time
- Demonstrate path-selection: local-pref, AS-path length, MED, origin, and router ID tie-breakers

## The Problem

In an Autonomous System (AS) running iBGP, every router must peer with every other router to learn all routes. This full-mesh requirement creates O(n^2) BGP sessions. A 10-router AS needs 45 sessions. A 100-router AS needs 4,950 sessions. This does not scale.

The route reflector (RFC 4456) solves this: a designated RR router re-advertises iBGP-learned routes to its clients, breaking the full-mesh requirement. But the route-reflector rules are subtle: an RR reflects routes from clients to other clients and to non-clients, reflects routes from non-clients to clients, but does NOT reflect routes from non-clients to other non-clients. Get this wrong and you create route black holes or hidden paths.

This capstone asks you to build a BGP topology simulator in Python that models route reflectors, verifies the advertisement rules, and compares the session count and convergence behavior of full-mesh vs. route-reflector designs. The simulator must implement BGP path selection with the full attribute comparison chain: local-pref, AS-path length, origin code, MED, eBGP-over-iBGP, router ID, and tie-break by neighbor address.

## The Approach

The simulation follows six stages:

**Stage 1: Topology Initialization** — Build a graph of 10 BGP routers in AS64512 plus 2 eBGP peers (AS64513, AS64514). Assign loopback addresses 10.0.0.1 through 10.0.0.12. Designate R1 (10.0.0.1) and R2 (10.0.0.2) as route reflectors, both sharing cluster-id 1.1.1.1. R3 through R7 (10.0.0.3–10.0.0.7) are RR clients of R1. R8 through R10 (10.0.0.8–10.0.0.10) are non-clients that peer directly with both RRs but not with each other or with R1/R2's clients. The two eBGP peers connect to R1 and R2 respectively: AS64513 peers with R1 at 192.168.1.0/30, AS64514 peers with R2 at 192.168.2.0/30.

**Stage 2: Session Establishment** — Initialize BGP sessions and count them. Full-mesh iBGP for 10 internal routers requires n*(n-1)/2 = 45 sessions. The route-reflector design requires 14 iBGP sessions: R1 holds 5 client sessions (R3–R7) and R2 holds 5 client sessions (the same R3–R7, since both RRs serve the same client set), plus 1 RR-to-RR session between R1 and R2, plus 3 non-client sessions (R8, R9, R10 peer with both R1 and R2, adding 6 sessions total). Add the 2 eBGP sessions for a grand total of 16 sessions versus 45 for full mesh. Print the count comparison as part of stage output.

**Stage 3: Route Injection** — Inject 5 routes from each eBGP peer. AS64513 originates 192.0.2.0/24, 192.0.2.128/25, 203.0.113.0/24, 198.51.100.0/24, and 198.51.100.128/25 with local-pref 100, MED 50, and origin IGP. AS64514 originates the same five prefixes with local-pref 90, MED 10, and origin IGP. Propagate these routes through iBGP using the advertisement rules. Track which router first receives each route and in which round.

**Stage 4: Advertisement Rule Verification** — For each route, trace which routers receive it and verify the three RR rules in code. Rule 1: when R1 receives a route from a client (R3–R7), it reflects to all other clients and to all non-clients (R8–R10). Rule 2: when R1 receives a route from a non-client (R8–R10), it reflects only to its clients (R3–R7), not to the other non-clients. Rule 3: R1 does not reflect a route received from a non-client back to other non-clients — a route learned from R8 is never sent to R9 or R10 via reflection. Encode each rule as an assertion in `verify_advertisement_rules()` and raise a descriptive error if any rule is violated.

**Stage 5: Path Selection** — For routes reachable via both eBGP peers (all five overlapping prefixes), run the full path selection chain at each router and verify it selects the correct best path. Selection order: (1) highest local-pref wins — AS64513 routes win on local-pref 100 vs. 90; (2) shortest AS-path length; (3) lowest origin code (IGP=0, EGP=1, Incomplete=2); (4) lowest MED when routes come from the same AS — AS64514's MED 10 beats AS64513's MED 50, but only within the same AS; (5) prefer eBGP over iBGP; (6) lowest router-ID as tie-breaker. Implement `select_best_path(routes: list[BgpRoute]) -> BgpRoute` and assert the winner at each router matches the expected result.

**Stage 6: Convergence Measurement** — Withdraw 192.0.2.0/24 from AS64513. Measure how many BGP UPDATE messages propagate through the topology before all routers remove or replace the route. Compare with what a full-mesh topology would require for the same withdrawal. In the route-reflector design, R1 sends a single WITHDRAW to R3–R7 and to R8–R10; in full-mesh every router notifies every peer individually. Record the UPDATE count ratio and the number of simulation rounds to convergence.

## Build It

1. Define four dataclasses: `Router(id: str, asn: int, loopback: str, is_rr: bool, cluster_id: str)`, `BgpPeer(local: Router, remote: Router, session_type: str)` where session_type is one of `"ebgp"`, `"ibgp-client"`, `"ibgp-non-client"`, `"ibgp-rr"`, `BgpRoute(prefix: str, next_hop: str, local_pref: int, as_path: list[int], origin: str, med: int, learned_from: str)`, and `PathAttributes` as a frozen dataclass wrapping the mutable fields for comparison.

2. Construct the topology in `build_topology() -> tuple[list[Router], list[BgpPeer]]`. Create routers R1–R10 in AS64512 with loopbacks 10.0.0.1–10.0.0.10, plus two eBGP peers: `AS64513` at 10.0.0.11 and `AS64514` at 10.0.0.12. Mark R1 and R2 as route reflectors with `cluster_id="1.1.1.1"`. Wire R3–R7 as clients of both R1 and R2. Wire R8–R10 as non-clients peering with R1 and R2. Add eBGP sessions from R1 to AS64513 and from R2 to AS64514.

3. Implement `count_sessions(peers: list[BgpPeer]) -> dict[str, int]` that returns counts broken down by session type, plus a `full_mesh_count(n: int) -> int` that returns `n * (n - 1) // 2`. Print the comparison table at startup.

4. Implement `inject_routes(topology) -> dict[str, list[BgpRoute]]` that returns a per-router RIB seeded with the five prefixes from each eBGP peer with the attributes specified in Stage 3.

5. Implement `reflect_routes(router: Router, route: BgpRoute, peers: list[BgpPeer], source_type: str) -> list[tuple[Router, BgpRoute]]` applying the three advertisement rules. Add `ORIGINATOR_ID` set to the route's originating router-id, and append `router.cluster_id` to `CLUSTER_LIST` on each reflection to enable loop detection.

6. Implement `select_best_path(routes: list[BgpRoute]) -> BgpRoute` using the seven-step chain: local-pref descending, as-path length ascending, origin code ascending (igp=0, egp=1, incomplete=2), med ascending (compare only within same neighbor AS), ebgp before ibgp, router-id ascending, neighbor-address ascending.

7. Implement `simulate_convergence(topology, ribs) -> dict[str, int]` that iterates rounds of route propagation until no new routes are installed. Return a dict of `{router_id: rounds_to_converge}`. Then run a second simulation with full-mesh wiring and compare both round counts and total UPDATE message counts.

8. Wire everything together in `code/main.py`: build topology, print session comparison, inject routes, run convergence, verify advertisement rules, run path selection verification, withdraw one prefix, measure re-convergence, and write results to `outputs/`.

## Use It

Run `python code/main.py` and confirm the following table matches your output. Each row is one advertisement rule or verification check.

| Check | Source router | Source type | Expected recipients | Must NOT receive |
|---|---|---|---|---|
| Client-to-client reflection | R3 (client of R1) | ibgp-client | R4, R5, R6, R7, R8, R9, R10, R2 | none — R1 reflects to all |
| Client-to-non-client reflection | R5 (client of R1) | ibgp-client | R8, R9, R10 via R1 | other non-clients bypassing RR |
| Non-client-to-client reflection | R9 (non-client) | ibgp-non-client | R3, R4, R5, R6, R7 via R1 | R8, R10 (non-client to non-client blocked) |
| Non-client-to-non-client suppression | R8 (non-client) | ibgp-non-client | R3–R7 only | R9, R10 must not receive via R1 |
| Path selection: local-pref wins | 192.0.2.0/24 | both peers | AS64513 path selected (lp=100) | AS64514 path (lp=90) |
| Session count | full-mesh vs. RR | topology | full-mesh=45, RR=16 | — |

## Ship It

Produce the following files under `outputs/`:

- `outputs/topology.txt` — ASCII diagram of all 12 nodes (R1–R10 plus two eBGP peers), labeled with ASN, loopback IP, role (RR / client / non-client / eBGP peer), and cluster-id. Draw iBGP sessions as solid lines and eBGP sessions as dashed lines.

- `outputs/session-count.txt` — Two-column table: topology type (full-mesh vs. route-reflector) and session count, plus a column showing the reduction factor. Include the formula used for each.

- `outputs/advertisement-rules.txt` — For each of the three RR advertisement rules, list the rule, the routers involved in the test, the expected outcome, and PASS or FAIL. Any FAIL line must include which router incorrectly received or was incorrectly denied the route.

- `outputs/path-selection-trace.txt` — For prefix 192.0.2.0/24, trace the full path-selection chain at R5 showing the two candidate routes (one from each eBGP peer via the RR), the attribute compared at each step, and which candidate is eliminated at each step until one winner remains.

- `outputs/convergence-comparison.txt` — Table showing rounds to convergence and total UPDATE message count for both full-mesh and route-reflector topologies, for both initial propagation and the withdrawal scenario.

## Exercises

1. Add a second route reflector cluster: make R6 and R7 into a second RR pair with cluster-id 2.2.2.2, and move R8–R10 to be clients of this cluster. Draw the new topology. What happens to the session count? What happens to the non-client-to-non-client suppression rule — does it still apply between the two clusters?

2. Simulate RR failure: shut down R1 (remove all its sessions) and re-run convergence. Verify that R2 alone can still reach all five prefixes at all routers. Measure whether convergence rounds increase. Explain why the cluster-id prevents R2 from creating a routing loop when it is the sole remaining RR.

3. Force a cluster loop: create a misconfiguration where R3 (a client) is also configured as an RR reflecting back to R1. Run the simulation and show that the CLUSTER_LIST loop-detection mechanism catches the loop and drops the route before it cycles. Print the CLUSTER_LIST value at the point of detection.

4. Implement route filtering at the RR: add a policy on R1 that suppresses 203.0.113.0/24 before reflecting it to clients. Verify that R3–R7 never receive this prefix, but R8–R10 and R2 still do (because they peer directly with AS64513 or with R1 as non-clients). Document the filtering hook in your `reflect_routes` function.

5. Add BGP communities: tag routes from AS64513 with community 64512:100 meaning "high-preference internal" and routes from AS64514 with 64512:200 meaning "backup path". Implement a community-based policy at R1 that sets local-pref=150 for 64512:100 and local-pref=80 for 64512:200 before reflecting. Verify path selection now changes at all clients.

6. Implement AS-path prepending: configure AS64514 to prepend its ASN twice on 198.51.100.0/24 before advertising it to R2. Verify that even though AS64514 wins on MED (10 vs. 50), it loses on AS-path length (3 vs. 1) and the AS64513 path is selected for that prefix. Show the full path-selection trace.

7. Model confederations as an alternative to route reflectors: split AS64512 into two confederation sub-ASes (64512.1 containing R1–R5, 64512.2 containing R6–R10). The confederation border routers exchange eBGP-like sessions across sub-AS boundaries but the external AS-path still shows AS64512. Count the sessions required and compare with the route-reflector count. Discuss the operational trade-offs.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Route reflector (RR) | A BGP relay | An iBGP router that re-advertises iBGP-learned routes to its clients, breaking the full-mesh requirement |
| RR client | A dependent peer | A router that peers only with the RR and relies on it for route propagation, not requiring a full mesh |
| Non-client | A peer outside the cluster | An iBGP router that peers directly with the RR but is not a member of its cluster; non-client-to-non-client routes are never reflected |
| Cluster ID | A group identifier | A value identifying an RR cluster; all RRs in the same cluster share the cluster ID and use it to detect reflection loops |
| CLUSTER_LIST | A loop-prevention attribute | A path attribute appended by each RR on reflection; if a router sees its own cluster-id in CLUSTER_LIST, it drops the route |
| ORIGINATOR_ID | The route's birthplace | Set by the first RR to reflect a route; records the router-id of the originating router to prevent it from re-accepting its own route |
| Full-mesh iBGP | Too many sessions | Every iBGP router peers with every other, requiring n*(n-1)/2 sessions — 45 for 10 routers, 4950 for 100 |
| iBGP | Internal BGP | BGP sessions between routers in the same AS; iBGP-learned routes are never re-advertised to other iBGP peers without an RR |
| eBGP | External BGP | BGP sessions between routers in different ASes; eBGP-learned routes are re-advertised to all iBGP and eBGP peers |
| Local-pref | How much this AS wants the route | A BGP attribute set within the AS; higher value wins and is the first tie-breaker in path selection |
| MED | How much the neighbor wants traffic | Multi-Exit Discriminator; lower value preferred; only compared between routes from the same neighboring AS |
| AS-path | The route's ancestry | The sequence of AS numbers the route has traversed; shorter path wins in step 2 of path selection and loop prevention rejects routes containing the local AS |

## Further Reading

- RFC 4456 — BGP Route Reflection: An Alternative to Full Mesh iBGP (the primary specification for route reflectors, cluster-ids, ORIGINATOR_ID, and CLUSTER_LIST)
- RFC 4271 — A Border Gateway Protocol 4 (BGP-4) (the base BGP specification defining UPDATE messages, path attributes, and the path-selection algorithm)
- RFC 5065 — Autonomous System Confederations for BGP (the confederation alternative to route reflectors; useful context for Exercise 7)
- "BGP Design and Implementation" by Randy Zhang and Micah Bartell (Chapter 5 covers route reflectors in operational deployments with real configuration examples)
- FRRouting documentation: BGP route-reflector configuration (covers `neighbor X route-reflector-client`, `bgp cluster-id`, and `bgp always-compare-med` knobs used when simulating with real routing daemons)
