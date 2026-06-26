# Traffic Shaping

> Data-network traffic is bursty: a host idles, then fires a 16,000 KB burst at line rate. Routers cannot size buffers for the worst burst, so unshaped traffic overflows queues and packets die. **Traffic shaping** smooths the offered load so it fits a contract the network can honor. The two canonical regulators are the **leaky bucket** (constant outflow rate R, capacity B; packets queue or spill when full) and the **token bucket** (tokens fill at rate R up to capacity B; a packet needs tokens before it leaves, so short bursts pass but long bursts are smoothed). Add a second token bucket in series to cap peak rate without flattening the average. On the router side, **Weighted Fair Queueing (WFQ)** schedules the smoothed flows so each gets a weighted share of the outgoing link, and **DSCP marking** (RFC 2597 Assured Forwarding) tags packets into priority/drop classes the scheduler can act on. **Shaping** delays excess packets into a queue; **policing** drops or demotes them — same token-bucket math, opposite operator intent.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01-04 (congestion control, admission control, load shedding)
**Time:** ~90 minutes

## Learning Objectives

- Describe why bursty traffic is harder for routers than constant-rate traffic, and name the buffer-overflow failure mode it produces.
- Implement a leaky bucket and a token bucket in Python and explain the difference in burst behavior.
- Derive the maximum burst length formula `S = B / (M - R)` and verify it against a simulated trace.
- Explain WFQ finish-time computation `F_i = max(A_i, F_{i-1}) + L_i / W` and why deficit round robin approximates it in O(1).
- Distinguish traffic shaping (queue and delay) from traffic policing (drop or mark), and say when each is applied at the host vs. the edge router.
- Read DSCP markings on a captured packet and map them to an Assured Forwarding class.

## The Problem

A host on a 1000 Mbps link produces an average of 200 Mbps, but in bursts: it sends 16,000 KB at full line rate in 125 ms, then goes quiet, then sends again. The downstream router has a 9600 KB buffer and a long-haul tolerance of 200 Mbps. The burst is bigger than the buffer and faster than the long-haul rate, so the router drops packets at the peak of every burst. The symptom the user sees is intermittent throughput collapse and retransmissions; the symptom the operator sees is tail-drop counters climbing in bursts.

The fix is not a bigger buffer — that just moves the queue and adds delay. The fix is to make the traffic match what the network can carry before it enters the router. That is traffic shaping: agree on a rate `R` and a burst tolerance `B`, then regulate the flow so it never exceeds `(R, B)`. The router can then police the same `(R, B)` contract and know immediately when a flow is lying.

## The Concept

### Leaky bucket — constant outflow

Picture a bucket with a hole in the bottom. Water pours in at whatever rate the host produces; it drips out at a fixed rate `R`. The bucket holds `B` bytes; once full, incoming water spills and is lost. The outflow is **always** `R` when there is anything in the bucket and zero when empty. This completely smooths the flow: bursts become a steady stream at rate `R`, and the capacity `B` only determines how much burst the bucket absorbs before packets start spilling. A leaky bucket with `B = 0` is a strict rate limiter — every packet waits its turn.

### Token bucket — burst capability

Flip the bucket around. Tokens drip in at rate `R` and accumulate up to capacity `B`. To send a packet of `L` bytes, you must remove `L` tokens; if the bucket has fewer than `L` tokens, the packet waits. The bucket fills while the host is idle, so a host that pauses can build up `B` tokens and then fire a burst at the full output rate `M` until the bucket empties. The long-term average is still `R`, but short bursts up to size `B + R*S` are allowed through unaltered.

### Maximum burst length

While a burst is being sent at rate `M`, tokens keep arriving at rate `R`, so the bucket drains slower than `M`. Solving `B + R*S = M*S` gives the maximum burst time:

```
S = B / (M - R)
```

With `B = 9600 KB`, `M = 125 MB/s`, `R = 25 MB/s`, the burst lasts about 94 ms before the host must cut back to `R`. This is the number that tells you whether a flow fits a router's buffer: a burst longer than `S` will overflow a `B`-sized buffer.

### Leaky vs. token — when to pick which

| Property | Leaky bucket | Token bucket |
|---|---|---|
| Outflow during a burst | Fixed at `R` | Up to `M` until bucket empties |
| Burst tolerance | None (strict smoothing) | Up to `B` bytes of accumulated credit |
| Good for | Policing a strict rate at an edge | Shaping bursty interactive traffic |
| Queuing behavior | Always a queue behind the hole | Queue only when tokens run out |

Token buckets dominate real shapers because most applications (video, web, RPC) are bursty by nature and a strict rate limiter would add needless latency to every burst. Leaky buckets show up where the downstream resource is truly rigid — a CBR virtual circuit, or a policer that must enforce an exact rate.

### Two token buckets in series — peak limiting

A single token bucket caps the long-term rate but still lets bursts leave at the full host rate `M`. To cap the peak without raising the average, put a second token bucket after the first with a higher rate (say 500 Mbps) and capacity 0. The first bucket characterizes the average; the second clips the peak. This is the standard pattern for shaping video into a DiffServ edge.

### Weighted Fair Queueing (WFQ)

Shaping fixes the input; scheduling shares the output. WFQ gives each flow a weight `W` and computes a virtual finish time for every packet:

```
F_i = max(A_i, F_{i-1}) + L_i / W
```

Packets are sent in finish-time order. A flow with weight 2 finishes its packets twice as fast as a weight-1 flow, so it gets twice the bandwidth on a congested link. Exact WFQ needs an O(log N) sorted insert per packet; **deficit round robin** approximates it with O(1) per packet and is what most routers actually run. A two-queue WFQ with the high-priority queue at very high weight is equivalent to strict priority with a starvation floor for the low queue.

### Shaping vs. policing

Same token-bucket math, different action on overflow:

- **Shaping** (host-side): the bucket is simulated; packets that would exceed `(R, B)` are queued and delayed until tokens are available. No packets are lost at the shaper; latency is the cost.
- **Policing** (router-side): the bucket is simulated; packets that exceed `(R, B)` are **dropped** or **marked down** (DSCP demotion). The policer protects the network from a host that lies about its contract.

A well-designed edge does both: the host shapes to its contract, and the router polices the same contract so a misbehaving host cannot steal bandwidth from conforming flows.

### Configuration parameters

A traffic contract is parameterized by `(R, B)` for a single bucket, or `(R1, B1, R2, B2)` for a dual-bucket peak-limited shaper. On Cisco IOS this maps to `rate`, `burst`, and `peak-rate`; on Linux `tc-tbf` takes `rate`, `burst`, and `latency` (the queue limit before drops). The DSCP field (6 bits in the IP header) carries the class: EF ( Expedited Forwarding, DSCP 46) for low-latency, AF classes (RFC 2597) for the four-priority × three-drop grid. The shaper and the scheduler must agree on these markings or the contract is unenforceable.

## Build It

`code/main.py` implements both buckets as stdlib Python classes and runs a burst through each, plus a WFQ scheduler over three weighted flows. Run it and read the trace: you will see the leaky bucket emit at a constant rate while the token bucket emits the initial burst at line rate and then cuts back.

1. Read the source slice in [`chapters/chapter-05-the-network-layer.md`](../../../../chapters/chapter-05-the-network-layer.md) around the leaky/token bucket figures (Fig. 5-28, 5-29) and the WFQ finish-time formula.
2. Run `python3 code/main.py` and confirm the token-bucket burst length matches `S = B / (M - R)`.
3. Modify `BURST_BYTES` or `TOKEN_RATE` and predict the new burst length before you re-run.
4. Capture a shaped flow with `tcpdump` or Wireshark and compare the inter-packet spacing to the simulator output.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm shaping is active | `tc -s qdisc show` counters, router shaping stats | Sent rate tracks `R`; queue depth rises during bursts then drains |
| Confirm policing is active | Edge router drop/mark counters by DSCP class | Non-conforming packets dropped or demoted, conforming packets untouched |
| Diagnose a bursty flow | Before/after trace, token-bucket level plot | The shaped trace's peak is capped; the unshaped trace overflows the buffer |
| Tune WFQ weights | Per-flow throughput under load | Flow bandwidth ratio matches weight ratio within one packet time |

## Ship It

Produce one artifact under `outputs/`:

- A token-bucket parameter worksheet: given a host rate `M`, a router buffer `B`, and a long-haul rate `R`, compute `S` and pick `(R, B)` that fits.
- A `tc` or IOS shaping config for a voice + data edge, with the DSCP mappings.
- A Wireshark display-filter cheat sheet for DSCP classes and a script that plots token-bucket level from a captured trace.

Start from [`outputs/prompt-traffic-shaping.md`](../outputs/prompt-traffic-shaping.md) if present.

## Exercises

1. A host on a 6 Mbps link is regulated by a token bucket with `R = 6 Mbps` and `B = 0`. What is the maximum burst length, and why?
2. You have `M = 1000 Mbps`, `R = 200 Mbps`, `B = 9600 KB`. Compute `S` by hand, then confirm with `code/main.py`.
3. Add a second token bucket with `R2 = 500 Mbps`, `B2 = 0` to the simulator. How does the shaped trace's peak change?
4. Three flows with weights 1, 2, 3 share a 90 Mbps link. What bandwidth does each get under WFQ when all three are backlogged?
5. A policer drops packets that exceed `(R, B)`. A shaper queues them. Give one operational scenario where shaping is worse than policing, and one where policing is worse than shaping.
6. Capture a 30-second trace of a video call. Estimate `(R, B)` from the trace by inspecting the largest burst that fits the average rate.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Leaky bucket | "the smooth one" | Constant outflow rate R; absorbs bursts up to B then spills |
| Token bucket | "the bursty one" | Tokens fill at R up to B; a packet needs L tokens; bursts up to B pass |
| Burst length S | "how long the burst lasts" | `S = B / (M - R)` — the time until a full bucket drains at peak rate M |
| WFQ | "fair queuing with weights" | Finish-time scheduling `F_i = max(A_i, F_{i-1}) + L_i / W`; weight sets bandwidth share |
| Deficit round robin | "fast WFQ" | O(1) per-packet approximation of WFQ used in real routers |
| Shaping | "delay the extra" | Queue non-conforming packets so the flow conforms; no loss, added latency |
| Policing | "drop the extra" | Drop or DSCP-demote non-conforming packets; protects the network from liars |
| DSCP | "the QoS bits" | 6-bit IP header field marking per-hop behavior; EF for low-latency, AF for classed drop |
| Assured Forwarding | "the 4×3 grid" | RFC 2597: four priority classes × three drop precedences = 12 service classes |

## Further Reading

- [`chapters/chapter-05-the-network-layer.md`](../../../../chapters/chapter-05-the-network-layer.md) — Sec. 5.4.2 (Leaky and Token Buckets), 5.4.3 (Packet Scheduling / WFQ), 5.4.4 (DiffServ).
- RFC 2697 — *A Single Rate Three Color Marker* (policer spec).
- RFC 2698 — *A Two Rate Three Color Marker* (dual-token-bucket peak-rate policer).
- RFC 2597 — *Assured Forwarding PHB Group* (the four-priority × three-drop grid).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, Sec. 5.4.
- Linux `tc-tbf(8)` and `tc-hfsc(8)` man pages for shaping configuration.