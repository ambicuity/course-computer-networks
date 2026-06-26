# Approaches to Congestion Control

> Congestion is what happens when offered load exceeds a network's carrying capacity. Two families of response. **Open-loop (precautionary)** acts before onset: provisioning bandwidth (months), traffic-aware routing (hours), admission control that refuses new VCs. **Closed-loop (reactive)** acts after onset: routers maintain an EWMA of instantaneous queue length `d = α·d_old + (1−α)·s`, and when `d` crosses a threshold they feed a signal back to senders — **explicitly** via ECN bits in the IP header (RFC 3168) or choke packets, or **implicitly** via drops and rising delay. **RED (Random Early Detection)** drops probabilistically as the average queue crosses `min_thresh` → `max_thresh`, so TCP sources back off before tail-drop collapse. **AIMD** (+1 segment/RTT on success, ÷2 on loss) is the sender-side closed loop that gives TCP its sawtooth window and converges to fair share (Chiu & Jain 1989). Standards: RFC 2309 (principles), RFC 3168 (ECN), Floyd & Jacobson 1993 (RED). Separating this from **flow control**: flow control is point-to-point (one fast sender vs one slow receiver); congestion control is global (the network itself is the bottleneck).

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 7 routing lessons (queueing at routers), the data-link sliding-window lab (window mechanics), basic probability and EWMA intuition.
**Time:** ~90 min

## Learning Objectives

- Distinguish open-loop from closed-loop congestion control and place provisioning, traffic-aware routing, admission control, traffic throttling, and load shedding on the correct side of that line.
- Derive the EWMA `d = α·d_old + (1−α)·s` and explain why packet-loss counts are lagging while queueing delay is leading.
- Tell ECN (in-band explicit feedback via two IP-header bits echoed by the receiver) apart from choke packets (out-of-band explicit) and from implicit feedback (delay, drops).
- Implement a router queue with RED dropping and an AIMD sender, and reproduce the throughput-collapse curve from Fig. 5-21 of the source.
- Explain why Nagle's "infinite buffer" result says more memory makes congestion *worse*, and why AIMD converges to fair share under a shared bottleneck.
- Read a trace (or simulator output) and name the exact counter, threshold, or header bit that proves congestion onset.

## The Problem

A research lab runs a 1 Gbps uplink shared by twelve hosts. At 09:00 Monday, eight of them start pulling a large model checkpoint from the same mirror. The border router's output queue was empty at 08:59; by 09:00:02 it holds 400 packets; by 09:00:04 it holds 2,000 and the first tail-drops appear. TCP senders notice the drops, halve their windows, and goodput crashes from 940 Mbps to 180 Mbps — then climbs back, then crashes again. Users see a 20× latency spike on SSH and file tickets. The link isn't broken. The routers aren't broken. The network is **congested**: offered load exceeded capacity, the queue built up, packets were delayed past their retransmission timers, duplicates were injected, and the network spent capacity carrying packets that were already dead. This is congestion collapse. The job of congestion control is to detect onset before collapse and push back on senders — open-loop or closed-loop — so the goodput curve stays near the "desirable response" line instead of falling off the cliff (Fig. 5-21).

## The Concept

### Open-loop: prevent congestion before it happens

Open-loop (precautionary) approaches assume you can match supply to demand, or refuse demand that won't fit. They run on slow timescales and don't react to instantaneous load.

- **Provisioning.** Upgrade the 1 Gbps uplink to 10 Gbps. Months of lead time, driven by long-term traffic trends. The source calls this "the most basic way to avoid congestion."
- **Traffic-aware routing.** Shift shortest-path weights so traffic moves off the loaded link. Hour-timescale. Peril: without multipath routing and slow weight changes, traffic *oscillates* between the two East–West links (Fig. 5-23). The modern Internet mostly does *traffic engineering* outside the routing protocol.
- **Admission control.** Refuse a new virtual circuit if it would push the network into congestion. The telephone network does this — when a switch is overloaded it stops giving dial tones. Packet networks need a traffic descriptor (leaky/token bucket, §5.4) because "up to 10 Mbps" circuits are bursty.

Open-loop is necessary but not sufficient: no amount of provisioning handles an eight-host Monday-morning burst.

### Closed-loop: react once congestion is imminent

Closed-loop (reactive) approaches assume congestion is inevitable and build a feedback loop: **monitor → detect → signal → throttle**. Three problems to solve.

1. **When is congestion approaching?** Packet-loss counts come *too late*. Link utilization averages hide burstiness. The winning signal is **queueing delay**: sample the instantaneous queue length `s` periodically, maintain an EWMA `d = α·d_old + (1−α)·s`, and when `d` crosses a threshold the router declares onset. α controls how fast the router forgets history — too small and you react to a single burst, too large and you miss a trend.
2. **How to tell the sender?** Three families, ordered by how explicit they are (below).
3. **On what timescale?** Too fast → oscillation; too slow → collapse. A 20 µsec idle-pulse "GO" and a 30-minute "STOP" are both broken.

### Explicit feedback: ECN and choke packets

**Choke packets** are the most direct: the router picks a congested packet, sends a choke back to the source, tags the original so it doesn't generate more chokes downstream, and forwards it. The source cuts traffic to that destination by ~50%. The early-internet `SOURCE-QUENCH` (Postel 1981) was a choke packet; it never caught on because generation semantics were underspecified.

**ECN (Explicit Congestion Notification, RFC 3168)** is the modern design: instead of *adding* packets to an already-loaded network, the router sets two bits in the IP header (`ECT` and `CE`) on a packet it was forwarding anyway. The destination echoes `CE` back to the sender in its next ACK (above IP — typically in TCP). ECN avoids the "send more messages when congested" paradox and is the standard in-band explicit signal on the internet today.

**Hop-by-hop backpressure** handles the long-pipe problem: if San Francisco sends 155 Mbps to New York and New York runs out of buffers, a choke takes ~40 ms to return — during which 6.2 Mbits keep pouring in. Hop-by-hop makes the choke take effect at *every* router it passes through (F slows to D, then E, then the source), buying buffer at each hop to absorb the in-flight pipe.

### Implicit feedback: delay and loss

If the network won't (or can't) tell you, the sender infers congestion from its own observations:

- **Rising RTT.** A packet's measured round-trip time grows as queues build. TCP Vegas uses the RTT gradient to detect onset before any drop.
- **Packet loss.** The crudest signal. A drop almost always means a queue overflowed, so the sender treats loss as "congested" by default. TCP Reno's fast retransmit and timeout both halve the window on this signal. Loss is lagging — you only see it after the queue is full — which is exactly why RED exists.

### RED: Random Early Detection

Tail-drop has two pathologies: (1) it signals only after the queue is *full*, too late; (2) when the queue overflows, *many* flows drop simultaneously, all halve their windows together, and goodput synchronously crashes ("global synchronization"). **RED** (Floyd & Jacobson 1993) fixes both by maintaining the EWMA queue length `d` and:

- `d < min_thresh`: drop nothing.
- `min_thresh ≤ d < max_thresh`: drop each arriving packet with probability `p` rising from 0 to a configured `max_p`.
- `d ≥ max_thresh`: drop every arriving packet (tail-drop territory).

The randomness decorrelates drops across flows, so sources back off at different times and the queue stays in the linear region of the goodput curve instead of oscillating around the cliff. RED is the bridge between closed-loop detection and AIMD senders: the probabilistic drop *is* the implicit feedback that tells TCP to halve.

### AIMD: the sender-side closed loop

**Additive Increase, Multiplicative Decrease** is the sender policy that closed-loop feedback drives. On every successful ACK: window += 1 segment per RTT (linear probe for spare capacity). On a loss or ECN mark: window ÷ 2 (aggressive backoff). The sawtooth on a TCP flow's cwnd-over-time plot *is* AIMD. Why ÷2 and not ÷10? Chiu & Jain 1989 proved AIMD converges to fair share under a shared bottleneck where MIAD, MIMD, and AIAD do not. The halving is what makes eight competing Monday-morning flows eventually share the 1 Gbps uplink roughly evenly.

### Comparison

| Approach | Timescale | Signal direction | Example | Failure mode |
|----------|-----------|-------------------|---------|---------------|
| Provisioning | months | n/a | bigger uplink | can't react to bursts |
| Traffic-aware routing | hours | reroute | load-weighted OSPF | oscillation East↔West |
| Admission control | per-VC setup | refuse | telephone dial tone | needs VC + traffic descriptor |
| Choke packets | ~RTT | router→source explicit | SOURCE-QUENCH | underspecified; adds load |
| ECN | ~RTT via receiver | in-band 2 bits, RFC 3168 | modern internet | needs ECN-capable endpoints |
| Hop-by-hop backpressure | per-hop | choke per hop | long fat pipes | buffer cost at each hop |
| RED | per-packet | probabilistic drop | Floyd-Jacobson 1993 | tuning min/max_thresh hard |
| AIMD | per-RTT | sender self-throttle | TCP Reno | synchrony if drops correlate |
| Load shedding | per-packet | drop on overflow | tail-drop, RED max | waste if policy bad |

## Build It

`code/main.py` is a 185-line stdlib-only simulator: single router, finite queue, N AIMD senders, compares **tail-drop** vs **RED** over a 60-second virtual clock.

1. Tail-drop: queue hits the buffer cap, drops a burst, all N senders halve together, goodput collapses, recovers, collapses again — the classic goodput cliff.
2. RED: queue hovers between `min_thresh` and `max_thresh`, drops are spread across senders, aggregate goodput stays near capacity instead of oscillating off the cliff.
3. The simulator prints the AIMD window evolution so you can see the sawtooth and RED threshold crossings directly.

```bash
python3 code/main.py
```

Expected exit code 0. Output: side-by-side summary table (tail-drop vs RED) plus AIMD window trace for sender 0.

## Use It

| Task | Evidence | What good looks like |
|------|----------|----------------------|
| Detect onset | EWMA `d` crosses `min_thresh` before any drop | You can predict a drop 10–50 ms before it happens |
| Prove ECN worked | `CE` bit set in IP header, echoed in TCP ACK, cwnd halved | Receiver saw the mark, sender reacted — no drop occurred |
| Diagnose collapse | goodput falls while offered load rises; retransmits climb | Congestion collapse, not a link fault — fix the sender, not the cable |
| Tune RED | drop probability rises smoothly 0→max_p across [min,max] | No global synchronization; queue stays in linear region |
| Size a buffer | queue rarely hits `max_thresh` | Buffer absorbs bursts but doesn't invite collapse |

## Ship It

Produce one artifact under `outputs/`:

- A RED configuration runbook for a border router: pick `min_thresh`, `max_thresh`, `max_p`, `α` for a 1 Gbps uplink serving ~12 hosts, with reasoning.
- Or: a trace annotation labeling EWMA, threshold crossing, first RED drop, and the corresponding AIMD window halving.
- Or: a one-page runbook distinguishing congestion collapse (goodput falls, RTT rises, drops rise) from link-layer errors (CRCs rise, drops bursty at one interface, RTT stable).

Start from [`outputs/prompt-approaches-to-congestion-control.md`](../outputs/prompt-approaches-to-congestion-control.md).

## Exercises

1. In `code/main.py`, set `N_SENDERS = 1`. Does the goodput cliff disappear? What does this tell you about whether collapse is per-flow or network-wide?
2. Change `ALPHA = 0.1` to `0.9` in the EWMA. Quantify the lag between true onset and `d` crossing `min_thresh` in virtual ms.
3. Raise `BUFFER_PKTS` from 200 to 10,000. Does goodput improve (Nagle's "infinite memory" question)? Reproduce or refute Nagle 1987.
4. Add an ECN path: instead of dropping when `min_thresh ≤ d < max_thresh`, mark the packet and let the sender halve on the mark (no drop). Compare goodput and drop count to RED.
5. 40 ms RTT, 155 Mbps pipe, New York runs out of buffers. Compute megabits in flight when the choke arrives in San Francisco. Justify hop-by-hop backpressure from the number.
6. Find a TCP trace and locate the first loss. Measure the RTT gradient in the 200 ms before it — would a Vegas-style implicit signal have caught it earlier than the drop?

## Key Terms

| Term | What it actually means |
|------|------------------------|
| Congestion | Offered load > capacity somewhere; queues grow, goodput falls |
| Congestion collapse | Goodput plummets as load rises past capacity; dead packets waste capacity |
| Open-loop | Match supply to demand or refuse demand; no feedback loop |
| Closed-loop | Monitor → detect → signal → throttle, on RTT timescales |
| EWMA `d` | `d = α·d_old + (1−α)·s`; low-pass filter on instantaneous queue length |
| ECN | Two IP bits, RFC 3168; router marks, receiver echoes, sender halves |
| Choke packet | Router sends a control packet back to source; adds load, underspecified |
| RED | Probabilistic drop between min/max_thresh; decorrelates TCP back-off |
| AIMD | +1/RTT on success, ÷2 on loss; converges to fair share |
| Hop-by-hop backpressure | Choke takes effect at each router traversed; absorbs the in-flight pipe |
| Goodput | Rate of *useful* delivered packets; excludes retransmits and dead packets |

## Further Reading

- RFC 2309 — *Recommendations on Queue Management and Congestion Avoidance* (Braden et al., 1998). Principles for RED and AQM.
- RFC 3168 — *The Addition of Explicit Congestion Notification (ECN) to IP* (Ramakrishnan, Floyd, Black, 2001). The ECN spec.
- Floyd, S. & Jacobson, V. — *Random Early Detection Gateways for Congestion Avoidance* (IEEE/ACM ToN, 1993). Original RED paper.
- Chiu, D. & Jain, R. — *Analysis of the Increase/Decrease Algorithms for Congestion Avoidance* (1989). Proves AIMD converges to fair share.
- Nagle, J. — *On Packet Switches with Infinite Storage* (RFC 970, 1987). "Infinite memory makes congestion worse."
- Tanenbaum & Wetherall — *Computer Networks*, 5th ed., Ch. 5 §5.3. Source chapter; §5.3.1 approaches, §5.3.4 throttling, §5.3.5 load shedding.