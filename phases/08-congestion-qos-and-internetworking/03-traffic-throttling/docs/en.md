# Traffic Throttling

> Choke packets tell a sender to slow down; hop-by-hop backpressure nips congestion in the bud by throttling every hop the signal passes through; ECN marks bits in flight instead of inventing new packets; weighted fair queueing isolates flows so aggressive senders cannot starve the rest; AIMD adjusts sending rates additively up and multiplicatively down so competing flows converge on a fair share. Every one of these mechanisms must leave measurable evidence — a marked bit, a dropped packet, a queueing-delay spike, a sawtooth in the congestion window — that you can read in a trace, a counter, or a log.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01 (Approaches to Congestion Control) and 02 (Traffic-aware Routing to Admission Control)
**Time:** ~90 minutes

## Learning Objectives

- Explain why congestion feedback must be timely and why a 40 ms choke-packet round trip at OC-3 still dumps 6.2 Mb into a congested router before the source can react.
- Distinguish end-to-end choke packets from hop-by-hop backpressure and name the tradeoff: backpressure buys immediate relief at the cost of upstream buffers.
- Read the two ECN bits (`ECT`, `CE`) in an IPv4/IPv6 header and trace the echo path from destination back to sender.
- Describe weighted fair queueing finish times as `F_i = max(A_i, F_{i-1}) + L_i / W_i` and predict output order from a small input set.
- Connect aggressiveness, AIMD (additive increase, multiplicative decrease), and fairness: why multiplicative decrease plus additive increase drives a set of competing flows toward a fair, convergent operating point.
- Produce a reusable AIMD sawtooth diagram and a hop-by-hop backpressure trace annotation.

## The Problem

A network is a set of queues with finite buffers sitting in front of output links. When the offered load exceeds the service rate for long enough, the queues grow. If the queues grow without bound, three bad things happen: delay climbs past what applications tolerate, buffers fill and packets are dropped, and the network enters congestion collapse — where retransmissions push the offered load even higher while useful throughput falls.

Congestion cannot be fully avoided. The honest goal is to operate the network *just before the onset of congestion* and, when congestion is imminent, tell the senders to throttle back. Two questions dominate the design:

1. **When** is congestion approaching? Utilization averages are too crude — a 50% utilization is light for smooth traffic but heavy for bursty traffic. Packet-loss counts arrive too late; by the time packets are dropping, congestion has already set in. The most useful signal is the *queueing delay inside the router*, tracked as an EWMA: `d_new = α·d_old + (1−α)·s`. When `d` crosses a threshold, the router declares congestion imminent.

2. **How** does the feedback reach the senders? Congestion is felt in the network, but relief requires action at the sources. The feedback channel must be timely (latency between congestion and throttle must be short relative to the bandwidth-delay product), fair (only senders contributing to the queue should be throttled), and cheap (the signaling traffic must not itself worsen congestion).

The feedback problem is where the design space branches: choke packets, ECN marking, hop-by-hop backpressure, and per-hop scheduling (weighted fair queueing) each take a different stance on latency, buffer cost, and explicitness.

## The Concept

### Congestion detection: the EWMA queueing-delay signal

Each router continuously samples its instantaneous queue length `s` and maintains a smoothed estimate `d = α·d_old + (1−α)·s`. The constant α controls how fast the router forgets recent history. This is a low-pass filter: it strips out sub-burst noise while still responding to sustained backlogs. When `d` rises above a configured threshold, the router treats the link as congested and engages a feedback mechanism. This is the same EWMA the simulator in `code/main.py` uses to decide when to emit a choke signal.

### Choke packets: the direct feedback approach

The router picks a packet from the congested queue and sends a *choke packet* back to that packet's source, naming the destination in the original packet. The original packet is tagged (a header bit is flipped) so downstream routers do not generate duplicate chokes for it, and it is then forwarded normally. To avoid worsening the congestion it is signaling, the router rate-limits its choke-packet emissions.

When the source receives the choke, it must reduce traffic to the named destination — historically by 50%. Because the router picks packets at random, the senders with the most packets in the queue (the fastest, most aggressive senders) are the most likely to be choked. Multiple chokes for the same host+destination pair are expected; the host ignores further chokes for a fixed interval until its reduction takes effect, after which new chokes mean the network is still congested.

The early-Internet instance of this design was the ICMP **SOURCE QUENCH** message (Postel, 1981). It never caught on — the circumstances under which it was generated and the effect it should have were not specified precisely enough. Modern IP networks use ECN instead.

### Explicit Congestion Notification: marking bits instead of inventing packets

Rather than generate new packets during a congestion event, the router *marks* a packet it is already forwarding by setting a bit in the IP header. The destination observes the mark and echoes the congestion signal back to the sender in its next reply (in TCP, via the `ECE`/`CWR` flags). The sender throttles as it would for a choke packet.

ECN uses two bits in the IP header: **ECT** (ECN-Capable Transport) — set by the sender to declare "I can react to marks" — and **CE** (Congestion Experienced) — set by a router when its queueing delay crosses threshold. The path is:

```
sender -> [ECT=1, CE=0] -> router (congested) sets CE=1 -> destination
destination -> ECE flag in TCP ACK -> sender -> sender reduces cwnd, sets CWR
```

ECN's advantage over choke packets: no extra packets are injected into the network during a congestion event. Its disadvantage: the signal piggybacks on the destination's reply, so the feedback latency is one full RTT plus the forward path, longer than a directly backhauled choke packet.

### Hop-by-hop backpressure: throttling every hop, not just the source

At high speeds or over long distances, end-to-end feedback is too slow. A host in San Francisco sending to New York at OC-3 (155 Mbps) will pump roughly **6.2 Mb** into the pipe during the 40 ms it takes a choke packet to return — even if the source shuts down instantly, those bits still arrive and must be buffered.

Hop-by-hop backpressure solves this by making the choke packet take effect at *every hop it passes through*:

```
D congested -> choke sent back -> F reduces flow to D (uses more buffers at F, but D gets immediate relief)
                              -> E reduces flow to F (uses more buffers at E, but F gets relief)
                              -> A reduces flow to E (source throttles, buffers drain)
```

The net effect: quick relief at the point of congestion, at the price of consuming more buffers upstream. Congestion is nipped in the bud without losing packets. The tradeoff is buffer cost — each intermediate router absorbs the flow the downstream router can no longer take.

### Weighted fair queueing: isolating flows so aggressiveness cannot win

Without per-flow scheduling, an aggressive sender that floods the router will dominate the round-robin or FIFO queue and starve well-behaved flows. **Weighted Fair Queueing (WFQ)** gives each flow its own queue and a weight `W`. The router computes a virtual finish time for each packet:

```
F_i = max(A_i, F_{i-1}) + L_i / W_i
```

where `A_i` is the arrival time, `F_{i-1}` is the previous packet's finish time in the same queue, and `L_i` is the packet length. Packets are transmitted in order of finish time. A flow with weight 2 drains twice as fast as a flow with weight 1 — so the operator can give a video server more bandwidth than a file server without letting either starve the other. WFQ makes aggressiveness pointless: sending more packets does not improve your finish-time order, because your weight, not your rate, determines your share.

### Aggressiveness and the fairness problem

Even with WFQ at the router, end-host behavior matters. If one flow increases its window aggressively (e.g., doubles each RTT) while another increases conservatively (e.g., adds one segment per RTT), the aggressive flow will grab capacity during the probing phase and the conservative flow will be squeezed. The network needs a *rate-adjustment discipline* that makes aggressiveness counterproductive — so that all senders, left to their own incentives, converge on a fair share.

### AIMD: additive increase, multiplicative decrease

The discipline that makes aggressive probing self-defeating is **AIMD**. On each RTT without congestion, the sender increases its window additively — by a fixed amount (one segment for standard TCP). On a congestion signal (loss or ECN mark), the sender decreases its window *multiplicatively* — by half.

The mathematical intuition for fairness: consider two flows sharing a bottleneck of capacity `C`. If flow 1 has window `w1` and flow 2 has window `w2`, the fair point is `w1 = w2 = C/2`. Under AIMD, when both are below `C/2` both additively increase; when their sum exceeds `C`, at least one sees a congestion event and multiplicatively decreases. The *decrease* is proportional to the current window, so the larger flow shrinks more. Iterated, this drives `(w1, w2)` toward `(C/2, C/2)`. The decrease step is what gives AIMD its fairness property — additive increase alone would let the aggressive flow win; multiplicative decrease penalizes whoever was biggest.

The *convergence* property: AIMD is provably convergent to a fair share under synchronized loss, and approximately fair under realistic stochastic loss. The sawtooth — window ramps up linearly, drops by half, ramps up again — is the visible signature of AIMD in any congestion-window trace and is what `code/main.py` plots and what `assets/traffic-throttling.svg` illustrates.

## Build It

`code/main.py` simulates a four-hop path (A → E → F → D) and demonstrates both mechanisms:

1. **Hop-by-hop backpressure simulator.** Each router has a queue with a fixed buffer capacity and an EWMA queueing-delay estimator. The source sends at a fixed rate; when D's EWMA crosses threshold, a choke packet is generated. In `end-to-end` mode, the choke travels all the way back to A before any throttling happens — during which D's queue overflows and packets are dropped. In `hop-by-hop` mode, the choke takes effect at F first, then E, then A — D's queue stops growing immediately, at the cost of larger buffers on F and E, and no packets are dropped.

2. **AIMD sawtooth.** A single flow runs for N RTTs against a bottleneck capacity `C`. The window starts at 1, increases additively by `alpha` each non-congested RTT, and on a congestion event drops multiplicatively by `beta` (0.5). Congestion is modeled as the window exceeding `C`. The output is the per-RTT window series — the classic sawtooth — plus the long-run average throughput, which should hover near `C/2` (the 75% utilization point that AIMD targets).

Run it, then replace the sample observations with your own: change `C`, change `alpha` and `beta`, and watch the sawtooth shape change. The script exits 0 and prints a summary table.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Detect congestion onset | EWMA queueing-delay estimate crossing a threshold | The smoothed `d` value rises *before* packets are dropped, not after |
| Send a choke packet | A packet backhauled from the congested router to the source, naming the destination | The choke is rate-limited; duplicate chokes for the same pair are suppressed for a fixed interval |
| Read ECN in a trace | IP header `ECT` and `CE` bits set; TCP `ECE`/`CWR` flags in the ACK path | The CE bit appears on the forward path, the ECE echo appears on the reverse path, and the sender's cwnd drops on the next RTT |
| Diagnose end-to-end vs hop-by-hop | Buffer occupancies at each hop, drop counts at D | End-to-end drops packets at D while the choke is in flight; hop-by-hop spends upstream buffers but loses none |
| Verify AIMD behavior | Per-RTT congestion window series | A linear ramp up, a halving on congestion, repeat; long-run average near `C/2` |
| Verify WFQ fairness | Output order matches predicted finish times for the given weights | A weight-2 flow sends twice as many bytes per unit virtual time as a weight-1 flow; aggressiveness does not change the order |

## Ship It

Create one artifact under `outputs/`:

- A trace annotation checklist for ECN: which bits to look for, in which order, and what each combination means
- A one-page runbook: "Router queue is growing, no packets dropping yet — what do I check and in what order?"
- A hop-by-hop backpressure sequence diagram (you can extend `assets/traffic-throttling.svg`)
- An AIMD sawtooth plot from your own `code/main.py` run with `alpha` and `beta` tuned
- A study prompt that teaches ECN from a single Wireshark display filter

Start with [`outputs/prompt-traffic-throttling.md`](../outputs/prompt-traffic-throttling.md).

## Exercises

1. Run `code/main.py` in both `end-to-end` and `hop-by-hop` modes. Report the drop count and the peak buffer occupancy at each hop. Why does hop-by-hop use more upstream buffer but drop fewer packets?
2. A host in San Francisco sends to New York at OC-3 (155 Mbps). Compute the bandwidth-delay product that is "in flight" during the 40 ms choke round trip. What does this imply about the minimum buffer needed at the New York router to avoid drops under end-to-end feedback?
3. In the WFQ formula `F_i = max(A_i, F_{i-1}) + L_i / W_i`, give the finish times for three packets with arrival times 0, 5, 8 and lengths 8, 6, 9, with weight W=1. What changes if W=2?
4. Two flows share a 10 Mbps bottleneck. Flow A uses AIMD with additive increase 1 and multiplicative decrease 0.5. Flow B uses additive increase 2 and multiplicative decrease 0.5. Run the simulation for 50 RTTs and plot both windows. Which flow ends up with the larger long-run average? Why does this contradict the fairness claim, and what does it tell you about the assumption that all flows use the same AIMD parameters?
5. A router has ECN enabled. Describe the exact sequence of header bits and TCP flags from the moment the router sets CE to the moment the sender reduces its window. What goes wrong if the destination fails to echo ECE?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Choke packet | "tell the source to slow down" | A control packet backhauled from a congested router to the source, naming the destination; rate-limited to avoid worsening congestion |
| SOURCE QUENCH | "the old ICMP thing" | The early-Internet choke packet (Postel, 1981); deprecated because its generation rules and expected effect were unspecified |
| ECN | "the two bits in the IP header" | ECT + CE: ECT declares the transport can react; CE is set by a router on congestion; destination echoes via TCP ECE/CWR |
| Hop-by-hop backpressure | "throttle each hop" | The choke takes effect at every hop it traverses; buys immediate relief at the congested hop at the cost of upstream buffers |
| WFQ | "weighted round-robin" | Weighted Fair Queueing: finish time `F_i = max(A_i, F_{i-1}) + L_i / W_i`; packets sent in finish-time order; weight, not rate, determines share |
| Aggressiveness | "the loud flow" | A flow that increases its window faster than competitors; WFQ and AIMD both exist to make aggressiveness unprofitable |
| AIMD | "additive up, multiplicative down" | Additive increase probes for spare capacity; multiplicative decrease (typically halving) on congestion; provably converges to fair share |
| EWMA | "smoothed queue length" | `d_new = α·d_old + (1−α)·s`; the congestion-detection signal routers use before packets are dropped |
| Bandwidth-delay product | "the pipe" | Capacity × RTT; the volume of data in flight between source and destination; sets the minimum buffer to absorb feedback latency |
| Convergence | "settles to fair" | Repeated AIMD iterations drive competing windows toward equal shares; multiplicative decrease is what gives the convergence property |

## Further Reading

- RFC 3168 — *The Addition of Explicit Congestion Notification (ECN) to IP*, Ramakrishnan, Floyd, Black, 2001
- RFC 2309 — *Recommendations on Queue Management and Congestion Avoidance in the Internet*, Braden et al., 1998
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5 §5.3.4 (Traffic Throttling) and §5.4 (Quality of Service)
- Mishra, Karr, Sah, Poon — *Buffer-size and rate-allocation for hop-by-hop congestion control* (the hop-by-hop backpressure reference cited in the source)
- Demers, Keshav, Shenker — *Analysis and Simulation of a Fair Queueing Algorithm*, 1990 (the byte-by-byte WFQ basis)