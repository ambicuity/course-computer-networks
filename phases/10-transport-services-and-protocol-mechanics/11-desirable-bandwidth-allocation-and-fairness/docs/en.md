# Desirable Bandwidth Allocation and Fairness

> Congestion control is not just a way to keep packets from being dropped. It is the mechanism that decides *who gets how much of the link* when many flows compete. A good allocation is **efficient** (it uses the link close to capacity without going over), **fair** (it does not starve any one flow), and **fast to converge** (it tracks changing demand as flows come and go). The three diagnostic tools in this lesson are *power* (Kleinrock 1979: `power = load / delay`, maximized at the onset of congestion), *max-min fairness* (no flow can be raised without lowering a smaller one, computable by water-filling), and *convergence time* (the time to redistribute bandwidth after a flow joins or leaves). The textbook example with four flows A, B, C, D through a six-router network (Fig. 6-20) produces the allocation 2/3, 1/3, 1/3, 1/3 — A wins the R2-R3 link because B, C, D are bottlenecked first on R4-R5. This lesson explains why each criterion matters, runs a max-min allocation on a sample topology, and traces how the bandwidth splits over time as flows arrive and leave.

**Type:** Learn
**Languages:** Python, simulation tables
**Prerequisites:** Goodput vs offered load curve (Phase 5), FIFO vs WFQ scheduling (Phase 5), basic graph topology
**Time:** ~75 minutes

## Learning Objectives

- Sketch the goodput vs offered load and delay vs offered load curves and identify the onset of congestion and the Kleinrock power maximum.
- Define max-min fairness precisely and apply water-filling on a small network to compute the per-flow allocation.
- Explain why per-connection fairness can be gamed (BitTorrent, multiple TCP sockets) and why per-host fairness is also problematic.
- Run a max-min allocator on a sample topology and verify that the textbook Fig. 6-20 case gives flows A, B, C, D the rates 2/3, 1/3, 1/3, 1/3.
- Plot a converging allocation as new flows join and old ones leave and identify the time-constant of the controller.
- Distinguish *efficiency*, *fairness*, and *convergence* as three orthogonal goals and recognize that real protocols (TCP CUBIC, DCTCP, BBR) trade them off differently.

## The Problem

An operator at a regional ISP sees a 10 Gbps backbone link at 92% utilization with sub-millisecond queuing delay most of the day, then 100% utilization with multi-millisecond delay and a long tail of TCP retransmissions during the evening peak. Downstream, two of the operator's largest customers complain: customer X, a video provider with a handful of long-lived 4K streams, has its throughput halved; customer Y, a search engine making many short flows, sees most of its queries complete in tens of milliseconds and a tail of stragglers. The operator must choose: do nothing and accept that the bulk TCP model is "fair enough," or deploy a queueing discipline that shifts bandwidth between the two traffic classes.

This is exactly the allocation question the textbook asks in §6.3.1. *Fair enough* sounds reassuring until you realize it is undefined. We need three tools: a measure of how close to capacity we are operating (efficiency), a measure of whether one flow is starving another (fairness), and a measure of how quickly the system returns to the right operating point after a disturbance (convergence). Without those three numbers, the operator is tuning by feel.

## The Concept

### Efficiency, power, and the onset of congestion

Plot goodput (useful packets delivered per second) against offered load. Initially the two are equal: every offered packet arrives. As load approaches the link capacity, goodput rises more slowly because bursts of traffic occasionally mound up at a router queue and overflow. If the transport protocol is poorly designed — for example, if it retransmits a packet that is merely delayed rather than lost — the network can enter **congestion collapse**, where senders furiously retransmit and very little useful work is done. This curve is Fig. 6-19(a) in the textbook and is the empirical reason every Internet congestion-control protocol adds backoff rather than just retransmitting harder.

The matching delay curve is Fig. 6-19(b). Delay is flat at the propagation round-trip for low load, then climbs steeply as load approaches capacity, again because queues are filling. The textbook's Kleinrock power metric, `power = load / delay`, is a scalar that captures both: it rises as load rises and delay stays low, peaks, and falls as delay grows. The peak is the **efficient operating point**, and it sits below the link capacity — typically around the *knee* of the goodput curve, before queues start to dominate delay.

This explains why an efficient allocation gives each flow "slightly less than 1/N" of the link when there are N flows: the slack absorbs burstiness without driving queues. A protocol that targets the power peak is one that holds the queue short, like DCTCP marking at low ECN thresholds, or like a paced sender that paces into the bottleneck rather than bursting.

### What does "fair" mean for a flow?

A first guess is that fairness means "give each of the N flows one Nth of the link." This sounds simple but is incomplete. The textbook raises three complications.

The first is whether the network *has* per-flow reservations. With strict QoS (IntServ, RSVP) it does; with plain FIFO best-effort it does not, and the congestion-control mechanism is the de-facto allocator. The second is the *path length* of each flow. If one flow crosses three congested links and another crosses one, the three-link flow consumes more resources, so allocating "1/N" to each is not obviously fair — but giving it less would let a single-link flow grab the surplus, again suboptimal. The third is the *level* of aggregation: per-connection fairness encourages opening more connections (BitTorrent famously does this, which is why some networks cap the number of TCP flows per host), while per-host fairness means a busy server fares no better than a phone.

In practice the textbook settles on per-connection fairness, with the caveat that the real goal is *no flow is starved*, not *every flow has the same rate*. That pragmatic stance is why TCP's multiplicative decrease punishes aggressive flows more than it punishes well-behaved ones.

### Max-min fairness and water-filling

A clean operational definition is **max-min fairness**: an allocation is max-min fair if the bandwidth given to one flow cannot be increased without decreasing the bandwidth of a flow whose allocation is no larger. Equivalently, you cannot raise a small flow's share without making a smaller flow worse off, and every other flow is at a bottleneck on at least one link on its path.

The textbook's worked example, Fig. 6-20, has four flows A, B, C, D through a network of six routers R1 through R6. Three flows (B, C, D) compete for the bottom-left link R4-R5, so each gets 1/3 of that link. Flow A competes with B on the R2-R3 link. B already has 1/3 (locked in by R4-R5), so A gets the remaining 2/3 of the R2-R3 link. The other links have spare capacity, but giving it to A would not help anyone, giving it to B would lower A, and giving it to C or D would lower a flow with a smaller share than B — both are forbidden by max-min. The allocation is therefore 2/3, 1/3, 1/3, 1/3.

Max-min allocations are computed with a water-filling procedure: start every flow at rate 0, increase them all uniformly, and freeze any flow that hits a bottleneck. Continue increasing the remaining flows until they too hit bottlenecks. The frozen flows cannot be raised without reducing one of the not-yet-frozen ones; the unfrozen ones share the remaining capacity equally. The `code/main.py` script does this on a small network, prints the bottlenecks, and verifies the Fig. 6-20 result.

### Per-flow vs per-host: why both are broken

A per-connection allocator is gameable: any application can open more connections to claim more share. BitTorrent clients open 50-200 TCP flows per swarm member; HTTP/1.1 browsers open 6 per origin. Each flow is a separate "fair" entity. The textbook notes that some networks (and some congestion controllers like BBR) implicitly cap the share a single host can obtain, but the per-connection rule is the de-facto Internet standard.

A per-host allocator is the other extreme. It treats a single server with 10,000 connections the same as a phone with 1, so the server is starved the moment it does real work. Worse, NATs and IPv6 prefix sharing make "host" ambiguous. The compromise in practice is per-(host, port) tuple or per-association — close to per-connection, with some anti-gaming through ECN and pacing.

### Convergence: tracking the moving optimum

The first three criteria describe a *static* optimum. Real networks are dynamic: users open browsers, peers join a swarm, servers boot, links flap. The fourth criterion is **convergence time**: how quickly does the allocator reach the new optimum after a disturbance?

The textbook's Fig. 6-21 shows an allocator tracking changes. Flow 1 starts alone, takes the full link. At t=1s flow 2 starts; the two share 50/50 within a fraction of a second. At t=4s flow 3 starts but only needs 20% of its share, so flows 1 and 2 each give up 10% to give flow 3 its 20%, leaving them at 40/40/20. At t=9s flow 2 leaves; flow 1 takes 80% and flow 3 stays at 20%. The total allocated is always close to 100%, and the response to each change is fast.

Convergence speed is a control-theory problem. AIMD (additive-increase multiplicative-decrease, the basis of TCP) has a known convergence rate that depends on the round-trip time and the loss probability; CUBIC replaces the linear AIMD ramp with a cubic curve that converges in approximately the bottleneck bandwidth-delay product regardless of RTT — which is why CUBIC dominates in the modern Internet. We will build an AIMD model in lesson 23 ("TCP Congestion Control Variants") and revisit convergence there.

## Build It

This lesson's `code/main.py` is a self-contained max-min fair allocator. It defines a sample topology, runs the water-filling algorithm, and prints the resulting allocation alongside the bottlenecks that froze each flow. Run it with `python3 code/main.py`.

The script uses an immutable dataclass to model each link's capacity, a small graph of nodes and links, and a priority queue of candidate bottleneck events. Water-filling increases every non-frozen flow at the same rate; whenever a flow's rate would exceed the residual capacity of one of its links, that flow freezes at the bottleneck rate. The process continues until every flow is frozen. The implementation has no third-party dependencies.

## Use It

| Function | Input | Output | When to use |
|----------|-------|--------|-------------|
| `Allocation` dataclass | flow id, rate, bottleneck link, frozen flag | one row per flow | reporting max-min result |
| `topology_from_edges(edges, caps)` | edge list, capacity list | dict of links keyed by `(u, v)` | building a graph for allocation |
| `max_min_fair(graph, flows)` | graph, list of (flow id, path) pairs | list of `Allocation` | computing the per-flow fair share |
| `verify_textbook_example()` | none | the Fig. 6-20 allocation printed | sanity-checking against the textbook |

The function `verify_textbook_example()` reproduces the textbook's four-flow, six-router example and prints the allocation 2/3, 1/3, 1/3, 1/3, identifying the bottleneck links R4-R5 for B, C, D and R2-R3 for A.

## Ship It

A runnable Python script that computes max-min fair allocation on a small network. Run `python3 code/main.py` and verify the output matches the textbook's worked example; modify the `textbook_edges` table to compute max-min allocation on your own topology.

| File | What it contains |
|------|------------------|
| `docs/en.md` | This lesson |
| `code/main.py` | Max-min fair allocator and textbook-example verification |
| `assets/desirable-bandwidth-allocation-and-fairness.svg` | Goodput/delay curves with power peak, plus the Fig. 6-20 topology with flow rates |

## Exercises

1. Run `python3 code/main.py` and confirm that the Fig. 6-20 example produces rates `(2/3, 1/3, 1/3, 1/3)` for flows A, B, C, D. Identify the bottleneck link for each flow in the printed output.
2. Add a new flow E to the textbook example with the path `R1 -> R2 -> R3 -> R6`. Recompute the max-min allocation. Hint: A is no longer the only flow on R2-R3, so its rate will change.
3. Implement Kleinrock's `power = load / delay` formula on the goodput and delay curves generated by the script. Identify the load at which power is maximum and comment on whether that load is below the link capacity.
4. Construct a topology where two flows share a 10 Mbps link and a third flow crosses a separate 1 Mbps link. What is the max-min allocation? What is the per-connection fair share if all three flows are equal? Why are they not the same?
5. A network has per-connection fairness. Host X opens 100 TCP connections; host Y opens 1. Approximately how much more bandwidth does X get, all else being equal? Discuss why this is a real problem on the modern Internet.
6. On a piece of paper, sketch the bandwidth allocation over time for a link with the following scenario: at t=0, flow 1 starts; at t=2, flow 2 starts and quickly takes 50%; at t=4, flow 2 leaves; at t=6, a long-lived flow 3 starts. Mark the time it takes for the allocator to reach each new steady state.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Congestion collapse | "The network is slow" | A pathological state where senders retransmit so aggressively that useful goodput collapses, even though the link is busy |
| Kleinrock power | `load / delay` | A scalar metric that peaks near the onset of congestion, used to pick the efficient operating point |
| Onset of congestion | "The knee of the curve" | The offered load at which the delay curve first starts to rise sharply; the target for efficient allocation |
| Max-min fairness | "No small flow can be raised without lowering a smaller one" | An allocation rule where each flow is bottlenecked on at least one path link, and raising any flow would lower a smaller one |
| Water-filling | "Ramp every flow up until something bottlenecks" | The algorithmic procedure for computing max-min fairness by uniform rate increase with freezing at bottlenecks |
| Per-connection fairness | "Each TCP socket gets a share" | The level of aggregation most Internet congestion controllers use, gameable by opening more sockets |
| Per-host fairness | "Each host gets a share" | An alternative that is fairer to mobile users but starves busy servers, and is hard to define under NAT |
| Convergence time | "How fast the allocator tracks change" | The control-theory measure of how quickly the system reaches a new optimum after a flow joins, leaves, or a link flaps |
| AIMD | Additive-increase multiplicative-decrease | The TCP-friendly rule: add 1 segment per RTT on success, halve on loss; the canonical convergence behavior |
| CUBIC | "A cubic growth function for cwnd" | A modern TCP variant whose window growth is a function of time since the last loss, giving faster convergence over high-bandwidth-delay product paths |

## Further Reading

- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., §6.3.1 ("Desirable Bandwidth Allocation") — the textbook chapter for this lesson.
- Kleinrock, L., "Power and Deterministic Rules of Thumb for Probabilistic Problems in Computer Communications," *ICC'79*. The original derivation of the power metric.
- Bertsekas, D. & Gallager, R., *Data Networks*, 2nd ed., §6.3 — max-min fairness and water-filling proofs.
- Chiu, D.-M. & Jain, R., "Analysis of the increase/decrease algorithms for congestion avoidance in computer networks," *Journal of Computer Networks and ISDN Systems*, 1989. The original convergence analysis of AIMD.
- Kelly, F. P., "Charging and Rate Control for Elastic Traffic," *European Transactions on Telecommunications*, 1997. The optimization-theoretic view of congestion control that justifies proportional fairness as a generalization of max-min.
- Floyd, S., "Connections with Multiple Congested Gateways in Packet-Switched Networks Part 1," 1991. The classic analysis of the fairness/efficiency tension the textbook highlights in Fig. 6-20.
- RFC 5681, "TCP Congestion Control" — the IETF specification of the AIMD rule.
- RFC 8312, "CUBIC for Fast Long-Distance Networks" — the modern Linux default congestion controller.
