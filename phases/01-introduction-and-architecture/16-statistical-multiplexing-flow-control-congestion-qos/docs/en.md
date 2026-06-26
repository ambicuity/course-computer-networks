# Statistical Multiplexing, Flow Control, Congestion, and QoS

> A network link is never-sized for the sum of its users' peak rates; it is sized for the *average* of their demand. **Statistical multiplexing** (textbook §1.3.2) lets N bursty on/off flows share one link of capacity C far below their combined peak N·C, because an ON burst from one flow rarely coincides with an ON burst from another — the gain is the law of large numbers applied to a queue. When the instantaneous offered load exceeds the link, excess packets queue in a FIFO buffer (delay), and when the buffer fills they drop (loss); the curve of loss versus offered load is the engineering signature of a mux. **Flow control** keeps a fast sender from swamping a slow receiver using feedback — a sliding window of W outstanding frames with sequence numbers mod 2^k, a receiver-advertised window (TCP's 16-bit `rwnd` field, RFC 793/9293), and the classic deadlock when W == 2^k makes "all acked" indistinguishable from "none acked." **Congestion** is different — it is the *network* being oversubscribed, not the receiver; TCP Reno handles it with AIMD (Additive Increase of +1 MSS per RTT, Multiplicative Decrease of /2 on loss, with `ssthresh` set to half cwnd), producing the familiar sawtooth. **Quality of Service (QoS)** reconciles a real-time video flow that needs bounded delay with a bulk transfer that wants throughput, using a scheduler such as Weighted Fair Queuing (WFQ, RFC draftsя) that ships each flow a guaranteed minimum share via virtual finish times `F = V + len/weight` and lets unused shares fall to leftover traffic. The failure modes are bufferbloat (over-large queues defeating mux gain), persistent congestion collapse (cwnd oscillation never converging), and window starvation under tiny rwnd. This lesson builds a runnable mux simulator, a sliding-window engine, an AIMD trace, and a WFQ scheduler.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Protocol layering and the service/primitive model (Phase 1 lessons on layers and §1.3.3 connectionless vs. connection-oriented), basic queueing intuition
**Time:** ~80 minutes

## Learning Objectives

- Compute the multiplexing gain when N bursty flows (each ON with probability p) share a link, and contrast a link sized for the average load versus one sized for the peak.
- Drive a sliding-window protocol with sequence numbers mod 2^k and a window W, identifying the cumulative-ACK window-sliding rule and the W == 2^k sequence-ambiguity deadlock.
- Trace an AIMD congestion window through slow start (exponential) then congestion avoidance (additive), describing how a loss event halves cwnd and sets ssthresh.
- Distinguish flow control (receiver-limited, feedback via rwnd) from congestion control (network-limited, inferred from loss/delay).
- Schedule flows under Weighted Fair Queuing and show that each flow realizes at least its weighted fair share while leftover bandwidth goes to flows that still have traffic.
- Read the evidence — queue occupancy, ACK gaps, cwnd sawtooth, virtual finish order — that each mechanism leaves behind in `code/main.py`.

## The Problem

A 10 Mbps uplink serves 40 home users browsing the web. No single user is ever at the link's full capacity for more than a fraction of a second, but occasionally two or three fetch a big image at once. If you provisioned the uplink at 40 × peak (40 × 1 Mbps = 40 Mbps) you would pay for bandwidth that is 95% idle; if you provisioned it at 0 Mbps nobody's page would load. Somewhere in between is a link that is cheap *and* responsive.

Separately, a server pumping 10 Gbps of disk reads toward a client whose NIC can absorb 1 Gbps will, within milliseconds, overrun the client's socket buffer and drop packets — not because the network is congested, but because the receiver is slow. And when that same server shares a bottleneck with a video stream, a purely FIFO scheduler will let the bulk transfer starve the video whose packets are time-sensitive and worthless if delivered late.

These are the four recurring "design issues for the layers" the textbook names in §1.3.2: how to share bandwidth dynamically (statistical multiplexing), how to keep a fast sender from swamping a slow receiver (flow control), how to react when the network itself is overloaded (congestion), and how to reconcile competing demands on delay versus throughput (quality of service). They recur at every layer — a link layer does them on one wire, the transport layer does them across an internet, and even an application can do them over a socket.

## The Concept

### Statistical multiplexing: sharing based on the statistics of demand

The textbook's definition is crisp: *"designs that share network bandwidth dynamically, according to the short-term needs of hosts, rather than by giving each host a fixed fraction of the bandwidth."* Contrast the two allocation philosophies:

| Mode | Allocation | Link size | What happens to idle share |
|---|---|---|---|
| **Circuit / peak reservation** | Each host gets a fixed fraction | sum of peaks = N · C_peak | Wasted — idle share is not re-usable |
| **Statistical multiplexing** | Bandwidth is a shared pool | sized for average load = N · p · C_peak | Reclaimed by whichever burst is currently ON |

For N independent on/off flows each ON with probability p, the number ON in a slot is Binomial(N, p) with mean Np and variance Np(1−p). The probability that demand exceeds the link capacity C (in packets/slot) is `P[Bin(N,p) > C]`, which falls rapidly once C is a few standard deviations above the mean. The **multiplexing gain** is the ratio peak : average you can size the link for: gain ≈ 1/p. With p = 0.1, ten flows need a link of ~1 packet/slot (the average) instead of 10 (the peak) — a 10× saving, paid for with a buffer that occasionally fills.

`code/main.py` runs exactly this: ten on/off flows over 10 000 slots on a 1-packet/slot link and reports that the link sized for the average carries the overwhelming majority of offered traffic (the rest queueing, not lost, as long as the buffer is finite-but-nonzero). See pane 1 of `assets/multiplexing-flow-control-congestion-qos.svg` for the bursts merging into the shared FIFO and link.

### The buffer trade-off: delay versus loss

Statistical multiplexing without a buffer is lossy; with an infinite buffer it is latency-explosive (bufferbloat). The buffer is the shock absorber that converts instantaneous excess into delay. The classic M/M/1 result gives mean delay `D = 1/(C − λ)` where λ is mean offered load and C is link capacity; as λ → C the delay blows up — the system is stable only when the *average* offered load stays below capacity. The bursts ride on top of that average and are absorbed by the buffer. The engineering rule of thumb (the "Bandwidth-Delay Product" rule) is to size the buffer to roughly the bandwidth-delay product of the link so that a full window of traffic can sit in the queue without emptying the link.

### Flow control: the sliding window and the receiver-advertised rwnd

Flow control is receiver-driven: the receiver tells the sender how much buffer it has left, and the sender never sends more outstanding bytes than that. A sliding window of W frames is the mechanism — at any instant the sender may have up to W unacknowledged frames in flight, identified by sequence numbers taken mod 2^k.

The window invariant is: at most W frames are outstanding (sent but not yet cumulatively ACKed). A cumulative ACK advances the base of the window; one more frame may be sent for each ACK. The TCP realization (RFC 793, clarified by RFC 9293) uses a 16-bit `Window` field (the receive window, `rwnd`) in every ACK segment, plus 32-bit sequence numbers in the Sequence Number and Acknowledgment Number fields. A 16-bit rwnd caps the receive window at 65535 bytes unless window scaling (RFC 7323) multiplies it by up to 2^14.

The subtle failure mode is the **sequence-number ambiguity** when W is too large relative to the sequence space. If W == 2^k, the sender can have all 2^k sequence numbers outstanding at once; when the cumulative ACK for the last one arrives, the receiver cannot tell whether "all previous frames acked" or "none acked" — the window cannot slide and the protocol deadlocks. The safe rule is W ≤ 2^k − 1 (for the stop-and-wait variant W=1, k=1, sequence {0,1}, which gives W = 2^k − 1 = 1). `code/main.py`'s `sliding_window_trace` runs W=4, modulus=8 and flips the deadlock flag for W ≥ 8.

| Sliding-window parameter | Symbol | Constraint |
|---|---|---|
| Sequence-number space | 2^k | k bits in the header |
| Window size | W | W ≤ 2^k − 1 to avoid ambiguity |
| Receive window | rwnd | advertised per ACK, ≤ receiver free buffer |
| Effective send window | min(W, rwnd) | the sender's actual cap |

### Congestion control: AIMD and the sawtooth

Flow control protects the receiver; congestion control protects the *network*. When too many senders push too much traffic through a bottleneck, queues grow, buffers overflow, packets drop, and retransmissions make things worse — the textbook's "congestion" and, in the limit, congestion collapse where useful throughput collapses to near zero.

TCP Reno's congestion window (`cwnd`, in MSS) follows AIMD:

1. **Slow start**: while `cwnd < ssthresh`, double `cwnd` every RTT (exponential growth) to find capacity quickly.
2. **Congestion avoidance**: once at `ssthresh`, grow `cwnd` by +1 MSS per RTT (additive increase), probing gently for spare bandwidth.
3. **Multiplicative decrease**: on a detected loss, set `ssthresh = cwnd/2` and `cwnd = ssthresh` (a halving), then re-enter congestion avoidance. A timeout (RTO) is harsher: `ssthresh = cwnd/2`, `cwnd = 1`, restart slow start.

The result is the textbook sawtooth: cwnd ramps linearly, collapses by half on loss, ramps again. The fairness property — two competing TCP flows sharing a bottleneck converge to roughly equal shares — follows from AIMD being symmetric in the increase and halving on decrease; flows with larger windows lose more in a decrease event, pulling them toward the smaller. RTT estimation uses SRTT/RTTVAR per RFC 6298 (SRTT = (1−α)·SRTT + α·RTT, with α = 1/8), and the RTO is SRTT + 4·RTTVAR. `code/main.py`'s `aimd_trace` prints the sawtooth as a text bar chart over 20 RTTs with a loss every 7.

### Detecting loss: ECN, dupACKs, and timeouts

Reno detects loss three ways: a **timeout** (the harshest signal — no ACK arrived within RTO), **three duplicate ACKs** (fast retransmit: the receiver re-ACKs the last in-order byte on every out-of-order arrival, so three identical ACKs imply one lost segment), and **ECN** (Explicit Congestion Notification, RFC 3168) where routers set the CE codepoint in the IP header (the two ECN bits in the TOS/DSCP field) on packets they would have dropped, and the receiver echoes it back in the TCP header's ECE flag so the sender halves cwnd without needing an actual drop. ECN is the方は the textbook point that "each computer reduces its demand when it experiences congestion" implemented without waste.

### Quality of Service: WFQ and the reconciliation of delay and throughput

The textbook frames QoS as reconciling *real-time* delivery (a video flow whose late packets are worthless) with *high-throughput* delivery (a bulk transfer that only cares about total bytes). A FIFO queue cannot do this — under load, a time-sensitive packet waits behind a queue of bulk packets. A scheduler can.

**Weighted Fair Queuing (WFQ)** assigns each flow a weight and serves the flow whose head packet has the smallest **virtual finish time** `F_i = V + L_i / w_i`, where V is the system virtual time and L_i is the packet length. A flow with weight 4 gets four times the service rate of a flow with weight 1; if the weight-1 flow is momentarily idle, its share falls to whichever flow is still busy. This guarantees each flow a minimum share (its weight over the sum of active weights) while letting leftover bandwidth be reclaimed — exactly the "competing demands" the textbook describes. The variant **Deficit Round Robin (DRR)** approximates WFQ with much simpler per-flow counters and is what most real routers implement at line rate.

The IntServ/RSVP model (RFC 2205, RFC 2210) reserves per-flow state along a path for a hard guaranteed rate; the DiffServ model (RFC 2474, RFC 2475) marks the 6-bit DSCP field in the IP header (EF for Expedited Forwarding, AFxy for Assured Forwarding) and lets each hop apply a per-class scheduler without per-flow state. `code/main.py`'s `weighted_fair_queuing` schedules video (weight 4), voice (weight 2), and bulk (weight 1) and shows video realizing ~57% of departures (its fair share), bulk taking leftover once the real-time flows exhaust their queues.

| QoS approach | Granularity | Where state lives | RFC |
|---|---|---|---|
| IntServ / RSVP | per flow | every router on the path | 2205, 2210 |
| DiffServ (DSCP) | per class (6-bit field) | each hop independently | 2474, 2475 |
| WFQ / DRR scheduler | per flow/class at one queue | the scheduling router | (proposed std) |
| ECN | per packet (2 bits) | routers + endpoints | 3168 |

### How the four mechanisms compose across layers

The textbook's point is that these are *layer-recurring* design issues, not transport-only concerns. A 100 Mbps Ethernet link statistically multiplexes its attached hosts; an Ethernet PAUSE frame (IEEE 802.3x) is link-layer flow control; switch input queueing and RED (Random Early Detection, RFC 2309) are link-layer-ish congestion response; and 802.1Q Traffic Classes with strict-priority and weighted scheduling are link-layer QoS. The same four knobs reappear at the transport layer (TCP cwnd, rwnd, ECN, DSCP) and even inside applications (a video codec adapts its rate to the window). Build a feel for one layer and you have a feel for all of them — which is why `code/main.py` models them generically rather than tying to a single protocol's wire format.

## Build It

1. Open `code/main.py`. Read the four sections in order: `statistical_multiplexing`, `sliding_window_trace`, `aimd_trace`, `weighted_fair_queuing`. Each is a self-contained function with no pip dependencies.
2. Run `python3 code/main.py`. Confirm four blocks of output: the mux gain summary and 10 000-slot run, the W=4 sliding-window trace with the deadlock flag, the 20-RTT AIMD sawtooth, and the WFQ departure order with realized shares.
3. Vary the mux: set `on_prob=0.4` and watch the 1-packet/slot link fall behind (carried fraction drops; `max_buffer` climbs). The link was sized for p=0.1; re-sizing for p=0.4 means C ≈ 4.
4. Trigger the deadlock: call `sliding_window_trace(window=8, modulus=8, rwnd_cap=8)` and confirm `ambiguity deadlock = True` — the window cannot distinguish a full from an empty ACK space.
5. Make the loss gentle: run `aimd_trace(start_cwnd=1, rtts=30, loss_every=15)` and observe that with rare loss the sawtooth ramp grows taller before each halving.
6. Add a flow to WFQ: extend the `flows` and `weights` dicts with a `sig` flow of weight 3 and confirm the realized shares re-weight accordingly.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Justify a link's bandwidth | peak vs. average offered load, multiplexing gain 1/p | Link sized for average with a finite buffer; idle share re-usable, not wasted |
| Verify flow control | sent seq, base advances on ACK, in_flight ≤ min(W, rwnd) | Window slides on cumulative ACK; W ≤ 2^k−1 avoids the ambiguity deadlock |
| Read congestion response | cwnd sawtooth, ssthresh reset on loss, +1/RTT growth | On loss cwnd halves (not to 1); on timeout cwnd=1 and restarts slow start |
| Confirm a QoS scheduler | per-flow virtual finish times, departure order, realized share | Each flow gets ≥ its fair share; leftover bandwidth goes to still-busy flows |
| Tell flow vs. congestion control | receiver rwnd cap vs. network loss/ECN signals | Flow control never sends "the network is full"; congestion control never cites the receiver's buffer |
| Spot bufferbloat | queue occupancy at average load, BDP-sized buffer rule | Delay stays bounded while loss stays rare; over-large buffer adds latency without cutting loss |

## Ship It

Produce one artifact under `outputs/prompt-statistical-multiplexing-flow-control-congestion-qos.md`:

- A sizing worksheet for the 40-user uplink scenario: peak load, average load, chosen link capacity, expected loss/queueing at p = 0.05, 0.1, 0.2, and the buffer you would provision (in packets and in ms of delay).
- Annotated sliding-window and AIMD traces from `code/main.py` with the deadlock case and one self-induced-loss case called out, the ACK-limited vs. congestion-limited boundary marked on each.
- A one-page QoS card: WFQ weights for video/voice/bulk, the realized shares from the scheduler, and a DiffServ DSCP marking plan (EF for voice, AF41 for video, BE for bulk) mapped to the same three classes.

Start from the printed output of `code/main.py` and annotate it with the failure mode each section demonstrates.

## Exercises

1. Ten on/off flows (p = 0.1) share a link. Compute (a) the peak offered load, (b) the average offered load, (c) the probability the link of capacity 2 packets/slot is exceeded in a slot using the Binomial(10, 0.1) tail. Sizing the link for the average (1/slot) gives what expected overload fraction?
2. A sliding-window protocol uses 3-bit sequence numbers (mod 8). What is the maximum window W that avoids the all-acked / none-acked ambiguity? Justify the W ≤ 2^k − 1 bound. What breaks if the receiver reorders segments (as real IP can) rather than delivering them in order?
3. Two TCP flows share a 10 Mbps bottleneck. Flow A has RTT 20 ms, flow B has RTT 80 ms. Under AIMD, which gets the larger share and why (the RTT bias of additive increase)? Describe how TCP Vegas (delay-based) or BBR (bandage-bandwidth-based, RFC draft) changes this fairness.
4. A scheduler must carry a 2 Mbps voice flow (loss-intolerant, 20 ms delay budget), a 5 Mbps video flow (loss-tolerant-soft, 200 ms budget), and a 15 Mbps bulk transfer over a 12 Mbps link. Assign WFQ weights and a DiffServ DSCP (EF, AF41, BE) to each. Which flow is over-subscribed and what policy (admission control, marking) saves it?
5. Trace an ECN-marked loss event: a router's queue exceeds a threshold, it sets the CE codepoint instead of dropping; the receiver echoes ECE; the sender halves cwnd and asserts CWR. Why is ECN preferable to a drop for a latency-sensitive flow, and what attack does RFC 3540 (the ECN nonce) defend against?
6. Routers A and B both run statistical multiplexing on their uplinks with identical average load, but A has a 4×BDP buffer and B has a 0.25×BDP buffer. Under a transient burst, contrast their loss and delay. Which is "bufferbloat" and which risks "congestion collapse"? How does CoDel (RFC 8289) reconcile the two?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Statistical multiplexing | "sharing a link" | Sharing bandwidth by the statistics of demand — size the link for the average, absorb bursts in a buffer, reclaim idle share |
| Multiplexing gain | "burst combining" | The peak : average ratio you can size a link for by aggregating independent bursty flows; ≈ 1/p for on/off flows |
| Sliding window | "outstanding bytes" | A cap W on unacknowledged frames; cumulative ACKs advance the base, letting new frames enter, until W or rwnd is hit |
| rwnd | "receiver's window" | The 16-bit TCP receive-window field, advertised per ACK, capping the sender at the receiver's free buffer (with RFC 7323 scaling) |
| Sequence-number ambiguity | "W too big" | When W = 2^k the cumulative ACK cannot distinguish "all acked" from "none acked"; the safe bound is W ≤ 2^k − 1 |
| Congestion | "the net is slow" | The network — not the receiver — being oversubscribed; recovered by reducing offered load, not by a bigger buffer |
| AIMD | "TCP's rule" | Additive Increase (+1 MSS/RTT), Multiplicative Decrease (/2 on loss); the property that makes competing TCP flows converge to fairness |
| ssthresh | "the slow-start cap" | The threshold at which TCP leaves slow start and switches to congestion avoidance; halved on loss, set to cwnd/2 |
| ECN | "early drop" | Explicit Congestion Notification (RFC 3168): routers mark CE in the IP header instead of dropping, echoed via TCP ECE/CWR |
| Quality of Service | "priority for video" | Mechanisms that reconcile bounded-delay real-time flows with high-throughput bulk flows via scheduling and/or marking |
| WFQ | "fair queueing" | Weighted Fair Queuing: serve the head packet with the smallest virtual finish time F = V + len/weight; guarantees each flow its weighted share |
| DSCP | "the QoS bits" | The 6-bit Differentiated Services Codepoint (RFC 2474) in the IP header — EF, AFxy, BE — that drives per-hop DiffServ scheduling |
| Bufferbloat | "too big a buffer" | An over-sized queue that converts bursts into persistent latency without reducing loss; the BDP-of-buffer rule bounds it |
| BDP | "bandwidth delay product" | Bandwidth × RTT — the amount of data that can fill the pipe; the rule for sizing congestion windows and buffers |

## Further Reading

- **RFC 793** / **RFC 9293** — TCP, including the sequence-number, acknowledgment, and 16-bit Window (rwnd) fields.
- **RFC 7323** — TCP Extensions for High Performance (window scaling, timestamps) lifting the 64 KB rwnd cap.
- **RFC 6298** — Computing TCP's Retransmission Timer (SRTT/RTTVAR and the RTO bound).
- **RFC 5681** — TCP Congestion Control, the normative AIMD definition (slow start, congestion avoidance, fast retransmit).
- **RFC 3168** — The Addition of ECN to IP; the CE/ECE/CWR codepoints.
- **RFC 3540** — Robust ECN signaling with nonces (the anti-cheating defense).
- **RFC 2309** — Recommendations on Queue Management and Congestion Avoidance (RED).
- **RFC 8289** — CoDel: Controlling Queue Delay (the data-queueing-delay antidote to bufferbloat).
- **RFC 2474** / **RFC 2475** — DiffServ: the DSCP field and per-hop behavior architecture.
- **RFC 2205** / **RFC 2210** — RSVP and the IntServ guaranteed-service model.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §1.3.2 Design Issues for the Layers (the source of this lesson's framework).
- Kurose & Ross, *Computer Networking*, 8th ed., Chapters 3 and 7, for TCP congestion control and WFQ scheduling depth.
