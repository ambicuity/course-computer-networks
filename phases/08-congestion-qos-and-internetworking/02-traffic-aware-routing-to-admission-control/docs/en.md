# Traffic-aware Routing to Admission Control

> Two ways to keep a link from saturating: shift load, or deny new flows. **Traffic-aware routing** sets link weights as a function of measured queueing delay so least-weight paths drift away from hotspots — but naive load-sensitive weights oscillate as traffic chases the momentarily idle link, which is why the real Internet does traffic engineering outside the routing protocol. **Hot-potato routing** is the BGP cousin: dump the packet out of your AS at the closest exit rather than carrying it across your backbone, trading symmetry for cheaper transit. When rerouting is not enough, **admission control** refuses new virtual circuits whose token-bucket descriptor would push a link over capacity — the telephone network's "no dial tone" applied to packet flows. A **flowspec** (RFC 2210/2211: token bucket rate, bucket size, peak rate, min/max packet size) is the negotiable contract; **RSVP** (RFC 2205) is the signaling protocol that walks that flowspec hop-by-hop up a multicast tree so each router can reserve bandwidth or reject; **IntServ** ties it together. The failure mode is real: one unreserved router on the path breaks the guarantee, and over-optimistic admission leads to congestion collapse.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 · 01 (Approaches to Congestion Control), Phase 7 routing lessons
**Time:** ~90 minutes

## Learning Objectives

- Explain why load-sensitive link weights cause routing oscillation and how multipath routing plus slow weight shifts fix it.
- Distinguish traffic-aware routing (inside the routing protocol) from traffic engineering (outside it).
- Describe admission control as the virtual-circuit analogue of the telephone network refusing dial tone.
- Define a flow specification in terms of token bucket (R, B), peak rate, and min/max packet size.
- Implement a discrete-time token bucket and leaky bucket and show the burst-smoothing output.
- Trace an RSVP PATH/RESV exchange and map it to per-router resource reservation.
- Name the failure mode where one unreserved router invalidates an IntServ guarantee.

## The Problem

A link saturates. You have two choices: move traffic off the link, or stop admitting new flows onto it. Both sound simple and both are hard.

Moving traffic off a saturated link is the premise of traffic-aware routing: fold the measured queueing delay into the link metric so shortest-path computation naturally detours around hotspots. The trap, documented in the source's Figure 5-23, is that once everyone reroutes onto the idle link, that link becomes the hotspot, the original link looks idle, and the routing tables oscillate wildly. The Internet's operational answer is to leave the routing protocol alone (OSPF/IS-IS weights stay fixed) and do **traffic engineering** by slowly nudging inputs — a change window measured in minutes, not the SPF recompute time.

Stopping new flows is admission control. In the telephone network a switch that is out of capacity simply stops giving dial tone; in a packet network you must first characterize the flow — its rate and its burstiness — because two flows with the same average rate stress a router very differently. The descriptor is the **token bucket** (rate R, capacity B): it bounds the long-term average rate and the largest instantaneous burst a source may emit. Armed with that descriptor, each router along the path decides admit or reject. RSVP is the signaling protocol that carries the descriptor up the multicast tree so every router gets a chance to say no.

## The Concept

### Traffic-aware routing

Set the link weight to a function of fixed cost (bandwidth, propagation delay) plus a variable term (measured load or average queueing delay). Least-weight paths then drift toward lightly loaded links. Khanna and Zinky (1989) ran this in the early Internet. The peril is oscillation: traffic chases the idle link, makes it busy, the old link looks idle, traffic swings back. Two fixes help — **multipath routing** spreads traffic across several equal-cost paths so no single link gets all the reroute; and **slow weight shifts** (Gallagher 1977) move the load gradually enough that the system converges. The pragmatic Internet answer is to keep load out of the routing protocol and do traffic engineering by changing OSPF/IS-IS link metrics on a slow schedule, or by steering traffic with MPLS LSPs and BGP communities.

### Hot-potato routing

In interdomain routing, each AS chooses its own best exit point. **Hot-potato** (early-exit) routing says: hand the packet to the next AS as soon as you can, even if that means a longer path inside your own AS. The side effect is asymmetric routes — the path B→C exits at the top of AS3, while C→B exits at the bottom, because each router optimizes only for its own AS's cost. Hot-potato is why two traceroutes between the same pair of hosts often look nothing alike in reverse.

### Flow admission

Admission control refuses to set up a new virtual circuit if it would cause congestion. The hard part is predicting whether a new circuit will overload the network. Telephone calls are easy — 64 kbps each, so divide link capacity by 64 kbps. Packet flows are bursty, so you need a descriptor. The descriptor most networks use is the **token bucket**: rate R (bytes/sec) bounds the long-term average, capacity B (bytes) bounds the burst. With descriptors in hand the network can either reserve bandwidth on every hop (the IntServ approach) or statistically estimate how many circuits fit without congestion and accept some risk.

### Token bucket

A bucket fills with tokens at rate R and has capacity B. To send a packet of size P bytes you need P tokens; if the bucket has fewer than P tokens, the packet waits (shaping) or is dropped/marked (policing). Long-term throughput is capped at R, but a burst up to B bytes can pass at the link's peak rate M. The maximum burst duration is S = B / (M − R): while the burst drains the bucket, tokens keep arriving at rate R, so the effective credit is B + R·S and the output at peak rate M consumes M·S bytes; solving B + R·S = M·S gives the formula. The source's worked example: B = 9600 KB, M = 125 MB/s, R = 25 MB/s ⇒ S ≈ 94 ms. Two buckets in series — the first sets the average rate, the second with rate higher than R but capacity 0 caps the peak rate — is the standard way to smooth bursts without flattening them entirely.

### Leaky bucket

The dual formulation: a bucket with a hole drains at constant rate R. Incoming water (packets) enters the bucket; if the bucket is full (capacity B) the excess spills and is lost. The outflow is constant at R whenever the bucket is non-empty, and zero when empty. Leaky bucket produces strictly smooth output — it is the token bucket with capacity 0 in the limit. Turner (1986) proposed it for traffic policing at the network edge: if a source exceeds its agreed leaky-bucket rate, the excess is dropped at the provider's interface.

### RSVP signaling

RSVP (RFC 2205–2210) is the signaling half of IntServ. Senders multicast PATH messages down the spanning tree toward receivers; each PATH carries the sender's traffic descriptor (a TSpec, essentially a token bucket). Receivers who want a reservation send RESV messages back up the tree toward the sender. At each hop the router inspects the RESV, checks whether it has the resources, and either installs a reservation and forwards the RESV upstream or rejects it. Because reservations are receiver-initiated, RSVP scales to large multicast groups — each receiver asks for the QoS it actually wants, and the tree merges reservations where branches join. The cost is per-flow state in every router, which is why IntServ never won the backbone.

### Comparison: traffic-aware routing vs admission control

| Aspect | Traffic-aware routing | Admission control |
|---|---|---|
| What it changes | Link weights / routes | Which flows are accepted |
| Granularity | Per-link, per-prefix | Per-flow, per-virtual-circuit |
| Requires signaling | No | Yes (RSVP or equivalent) |
| Failure mode | Oscillation if weights move fast | Per-flow state does not scale |
| Real Internet use | Via TE, not in OSPF | Largely absent; DiffServ won |

### When admission control fails

A single unreserved router on the path breaks the guarantee. IntServ requires every router from source to receiver to honor the reservation; one best-effort hop and the delay bound is gone. Over-optimistic admission — admitting ten 10 Mbps circuits on a 100 Mbps link because "they rarely all blast at once" — works until they do, at which point you get congestion collapse and the very packet loss the scheme was supposed to prevent. RSVP's soft-state refresh (messages expire if not refreshed) means a router reboot silently drops reservations and the application does not learn until the QoS degrades.

## Build It

`code/main.py` is a stdlib-only simulator with three parts:

1. **Token bucket** — discrete-time implementation: a counter advances by R·Δt each tick, packets consume P bytes, traffic over the bucket is queued and released at rate R.
2. **Leaky bucket** — the dual: a queue drained at constant rate R, arrivals beyond capacity B are dropped.
3. **Traffic-aware routing** — a 7-node East/West topology (the source's Figure 5-23) with two cross-links CF and EI. We compute shortest paths with load-sensitive weights, push all East-West traffic onto one link, watch the SPF recompute and flip to the other link, and show the oscillation that multipath routing fixes.

Run it, read the output, then replace the sample traffic pattern with your own and confirm the oscillation behavior.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Confirm oscillation | SPF output per round, link utilisation table | You can predict which link SPF picks next round before running it |
| Verify token bucket smoothing | Bucket-level trace + output-rate trace over time | Burst is spread; long-term rate equals R; peak rate never exceeds M |
| Verify leaky bucket policing | Drop count vs offered load | Drops begin exactly when queue exceeds B; steady output at rate R |
| RSVP admission | Per-hop accept/reject log for a PATH/RESV walk | Rejected RESV identifies the bottleneck router and the missing resource |
| TE vs traffic-aware routing | Compare fixed-weight SPF against load-sensitive SPF over 10 rounds | Fixed-weight is stable but ignores congestion; load-sensitive oscillates unless multipath is on |

## Ship It

Produce one artifact under `outputs/`:

- A token-bucket parameter worksheet (given R, B, M, compute max burst S and verify with the simulator)
- An oscillation trace runbook: the exact round-by-round SPF picks for the Figure 5-23 topology under a given load
- An RSVP PATH/RESV sequence diagram for a 3-router path with one rejection
- A short script that turns a flow spec (rate, burst, peak, min/max pkt) into per-router bandwidth and buffer reservations

Start with [`outputs/prompt-traffic-aware-routing-to-admission-control.md`](../outputs/prompt-traffic-aware-routing-to-admission-control.md).

## Exercises

1. Run `code/main.py` and watch the East/West SPF oscillate. Turn on multipath routing and confirm the oscillation damps. Explain in one sentence why spreading traffic fixes it.
2. Set the token bucket to R = 25 MB/s, B = 9600 KB, M = 125 MB/s. Run the simulator and confirm the maximum burst duration is ≈ 94 ms. Derive the formula S = B/(M − R) yourself.
3. Feed a leaky bucket a burst larger than B. Confirm the drop count equals (burst − B) and that output is constant at R after the burst.
4. Add a second token bucket in series with rate 500 Mbps and capacity 0. Show that the peak rate into the network is now capped at 500 Mbps instead of 1000 Mbps.
5. Simulate an RSVP walk along a 4-router path where router 3 has no spare bandwidth. Confirm the RESV is rejected at router 3 and that routers 1 and 2 roll back their reservations.
6. Give one real-world reason IntServ/RSVP did not win the Internet backbone, and one context (MPLS-TE, 5G slicing) where per-flow reservation still shows up.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Traffic-aware routing | "routing around congestion" | Folding measured load into link weights; oscillates unless done slowly or with multipath |
| Hot-potato routing | "dump it early" | BGP early-exit: hand the packet to the next AS at the closest point, trading symmetry for cheaper transit |
| Admission control | "say no to new flows" | Refuse a virtual circuit whose descriptor would push a link over capacity; the packet-network analogue of no dial tone |
| Token bucket | "the burst limiter" | Counter fills at rate R up to capacity B; a packet needs P tokens; bounds average rate R and burst B |
| Leaky bucket | "the smoother" | Queue drained at constant rate R; arrivals over capacity B are dropped; output is constant-rate |
| Flow specification (flowspec) | "the contract" | Negotiable parameter set: token bucket rate, bucket size, peak rate, min/max packet size (RFC 2210/2211) |
| RSVP | "the reservation protocol" | Receiver-initiated signaling that walks a flowspec up the multicast tree so each router reserves or rejects (RFC 2205) |
| IntServ | "per-flow QoS" | Architecture tying flowspec + RSVP + per-hop reservation; guarantee breaks if any router on the path lacks a reservation |
| Traffic engineering | "TE" | Changing routing inputs outside the routing protocol to shift load slowly without oscillation |

## Further Reading

- RFC 2205 — RSVP Resource reSerVation Protocol
- RFC 2210/2211 — Integrated Services flow specification
- Tanenbaum & Wetherall, *Computer Networks* 5th ed., Ch. 5 §5.3.2–5.3.3, §5.4.2–5.4.5
- Khanna & Zinky (1989), the early Internet load-sensitive routing deployment
- Parekh & Gallagher (1993, 1994), token bucket + WFQ delay bounds