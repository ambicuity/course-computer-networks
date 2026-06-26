# TFRC UDP Media Rate Control

> Implement TCP-Friendly Rate Control (TFRC) for UDP media streaming: achieve fair coexistence with TCP flows, adapt to network congestion without the overhead of TCP's retransmission, and benchmark the fairness.

**Type:** Capstone
**Languages:** Python, shell
**Prerequisites:** Phase 11 TCP congestion control lessons; understanding of RTT, loss rate, and the TCP throughput equation
**Time:** ~140 minutes

## Learning Objectives

- Implement the TFRC throughput equation (RFC 5348): X = s / (R * sqrt(2*p/3) + t_RTO * sqrt(3*p/8) * (1 + 32*p^3))
- Build a UDP media sender that adjusts its sending rate based on estimated loss rate and RTT
- Implement the receiver report mechanism: the receiver sends feedback with the observed loss rate and RTT
- Simulate coexistence with competing TCP flows and verify fairness using the Jain fairness index
- Demonstrate that TFRC achieves smoother rate adaptation than TCP (less oscillation) while remaining fair
- Benchmark TFRC vs. TCP vs. unregulated UDP under varying loss conditions

## The Problem

Real-time media (video calls, live streaming) cannot use TCP. TCP's retransmission adds latency that breaks real-time communication, and TCP's congestion control oscillates aggressively (halving cwnd on loss). But unregulated UDP has no congestion control at all: it floods the network, starves TCP flows, and causes congestion collapse.

TFRC (TCP-Friendly Rate Control, RFC 5348) is the solution: a congestion control scheme for UDP that achieves TCP-fair throughput without TCP's aggressive oscillation. The sender measures the loss rate and RTT, plugs them into the TCP throughput equation, and sends at the resulting rate. This produces a smooth sending rate that is fair to competing TCP flows.

The challenge is implementing the equation correctly, measuring loss rate at the receiver, feeding it back to the sender, and adapting the sending rate smoothly. TFRC's key property is that its long-term throughput matches TCP's, but its short-term rate changes are much smoother, making it suitable for media.

This capstone asks you to implement a TFRC-controlled UDP media sender and receiver in Python, simulate it alongside competing TCP flows, and verify fairness using the Jain fairness index. You must show that TFRC is fair to TCP (throughput within 10% of TCP's) while being smoother (rate changes are gradual, not halving on loss).

## The Approach

The implementation follows six stages:

**Stage 1: Throughput Equation Implementation.** Implement the core TFRC equation X = s / (R * sqrt(2*p/3) + t_RTO * (3 * sqrt(3*p/8)) * p * (1 + 32*p^2)), where s is packet size (1000 bytes), R is the measured RTT in seconds, p is the measured loss probability, and t_RTO is set to 4*R per RFC 5348. Handle edge cases carefully: when p = 0 the equation produces infinity, so clamp to the link capacity; when p = 1 the equation produces a very small positive rate, which is the correct floor behavior.

**Stage 2: Loss Estimation at Receiver.** The receiver tracks sequence numbers for every arriving packet and computes the loss fraction using a sliding window of 8 loss intervals per RFC 5348 section 5. Each loss interval is the number of packets received between consecutive loss events; the loss event rate p is derived as the weighted inverse of the average interval length, with recent intervals weighted more heavily. This weighted average dampens short-term fluctuations that would cause the sender to overreact to transient bursts.

**Stage 3: RTT Measurement.** The sender embeds a 64-bit timestamp in every outgoing data packet header. The receiver echoes the most recent sender timestamp back in each feedback report along with the receiver's own arrival time. When the sender receives the feedback, it computes the sample RTT as (now - echoed_timestamp) and feeds it into an EWMA with alpha = 0.1: smoothed_RTT = 0.9 * smoothed_RTT + 0.1 * sample_RTT. The EWMA filters out per-packet jitter and gives a stable R for the throughput equation.

**Stage 4: Sender Rate Adaptation.** Every 1 second the sender receives a feedback report containing the current loss event rate p and the smoothed RTT. It computes the target rate X using the throughput equation, then clamps to min(X, 2 * X_recv) where X_recv is the throughput the receiver estimates it is actually receiving, guarding against the sender overshooting when the feedback is stale. The sending rate changes smoothly: decreases are applied immediately but capped at halving once per RTT, and increases are applied only after at least one RTT of stable feedback, mimicking TCP's conservative increase behavior.

**Stage 5: Competing TCP Simulation.** Add a single competing TCP Reno flow sharing the same 10 Mbps bottleneck link alongside the TFRC flow. Run both flows for 120 seconds under a fixed random loss rate, record per-second throughput for each, then compute the Jain fairness index J = (sum(xi))^2 / (n * sum(xi^2)) over the final 60 seconds of steady state. A J value above 0.9 indicates the two flows share the link fairly; a value below 0.7 indicates TFRC is either starving or being starved by TCP.

**Stage 6: Benchmark.** Sweep the link loss rate from 0% to 20% in 1% steps. At each loss level, run three scenarios for 60 seconds each: TFRC only, TCP Reno only, and unregulated UDP only. Record the average sending rate, the variance of the sending rate (smoothness metric), and the Jain fairness index when both TFRC and TCP share the link simultaneously. Plot the three throughput curves and the rate-variance curves on the same axes to visualize how TFRC degrades gracefully while UDP stays flat and TCP oscillates.

## Build It

1. **Set up the simulation environment.** Use a discrete-event simulation with a 10 Mbps bottleneck link, 50 ms baseline RTT, 1000-byte packet size, and a token-bucket queue with 100-packet buffer. Initialize a random loss process with configurable per-packet drop probability p_loss. Represent time in milliseconds internally for precision; convert to seconds only at the equation boundary.

2. **Implement the TFRC throughput equation.** Write a pure function `tfrc_rate(s, R, p) -> float` that returns bytes/second. Set t_RTO = max(4 * R, 1.0) per RFC 5348 section 4. Guard against p <= 0 by returning a configurable maximum rate (link capacity), and against division-by-zero by returning a minimum floor of 8 * s bytes/second (eight minimum-size packets per second). Unit test this function against the RFC 5348 appendix A example values before integrating it.

3. **Implement the FeedbackReport dataclass.** Define fields: `loss_event_rate: float`, `receiver_rtt: float`, `x_recv: float` (receiver-estimated throughput in bytes/s), `timestamp: float` (sender timestamp echoed back), and `report_time: float` (when the receiver generated this report). The sender uses all five fields to update its state atomically on each feedback arrival.

4. **Implement TFRCReceiver.** On each received packet: record the sequence number and arrival time, update the 8-interval sliding window, recompute p using the RFC 5348 weighted average, estimate x_recv as bytes_received / measurement_window (8 seconds), and echo the sender timestamp. Send a FeedbackReport to the sender once per RTT. If no packet arrives for 2 * RTT, send a report with the last known loss rate to keep the sender from stalling.

5. **Implement TFRCSender.** Maintain state: `rate` (current bytes/s), `smoothed_rtt`, `last_report_time`. On each feedback report: update smoothed_rtt via EWMA, call `tfrc_rate` to get X_target, set new rate = min(X_target, 2 * x_recv). Apply a rate-decrease immediately if X_target < rate; apply a rate-increase only if the feedback is at least one smoothed_rtt newer than the last increase event. Schedule the next packet send at `now + packet_size / rate`.

6. **Implement TCPRenoFlow for comparison.** Model TCP Reno with an integer cwnd (packets), ssthresh, and per-ACK cwnd update. On loss (triple duplicate or timeout): ssthresh = cwnd / 2, cwnd = ssthresh. On ACK in congestion avoidance: cwnd += 1/cwnd. Convert cwnd to a throughput estimate as cwnd * packet_size / smoothed_rtt. This does not need to be a full TCP stack; a rate-equivalent model is sufficient for fairness comparison.

7. **Implement the Jain fairness calculator.** Write `jain_index(rates: list[float]) -> float` using the formula J = (sum(xi))^2 / (n * sum(xi^2)). Compute it over per-second throughput samples from the final 60 seconds of each run (discard the first 60 seconds as warm-up). Also compute the coefficient of variation (CoV = std / mean) of the per-second rate for each flow as the smoothness metric.

8. **Implement the benchmark sweep.** For loss rates [0.0, 0.01, 0.02, ..., 0.20], run the simulation and record: TFRC average rate, TCP average rate, unregulated UDP rate (= link capacity), TFRC CoV, TCP CoV, and Jain index for TFRC+TCP coexistence. Write results to `outputs/` as tab-separated text files. Print a summary table to stdout on completion.

## Use It

| Task | Measurement | What Good Looks Like |
|---|---|---|
| Verify equation correctness | Call `tfrc_rate(1000, 0.05, 0.01)` and compare to RFC 5348 appendix A | Within 1% of the RFC reference value (approximately 150 KB/s at p=0.01, RTT=50ms) |
| Verify loss response | Increase p from 0.01 to 0.10 mid-run; observe sender rate | Rate drops within 2 RTTs; new steady-state rate is within 5% of equation prediction |
| Verify fairness | Run one TFRC flow + one TCP Reno flow on a 10 Mbps link for 120s | Jain fairness index J > 0.9 over the steady-state window |
| Verify rate smoothness vs TCP | Compare CoV of TFRC sending rate to CoV of TCP cwnd-derived rate | TFRC CoV < 0.25; TCP CoV > 0.50 |
| Verify over-estimation guard | Set x_recv to a low value (50 KB/s) while equation says 500 KB/s | Sender rate clamps to min(500, 2*50) = 100 KB/s, not 500 KB/s |
| Verify under-estimation floor | Set p = 0 (no loss) | Sender rate reaches link capacity, not infinity; no divide-by-zero error |
| Verify loss sweep | Run benchmark from 0% to 20% loss | TFRC rate degrades smoothly and monotonically; TCP rate oscillates at each loss level |

## Ship It

- `outputs/tfrc-equation-verification.txt` — Table of (s, R, p) inputs vs. computed X vs. RFC 5348 appendix A reference values. Every row must show < 1% deviation from the RFC reference.
- `outputs/jain-fairness-results.txt` — Jain fairness index for three scenarios: TFRC+TCP, TCP+TCP, unregulated UDP+TCP. Include per-flow throughput samples used for the calculation.
- `outputs/throughput-vs-loss.txt` — Tab-separated table with columns: loss_rate, tfrc_rate_kbps, tcp_rate_kbps, udp_rate_kbps, tfrc_cov, tcp_cov. One row per 1% loss step from 0% to 20%.
- `outputs/rate-trajectory.txt` — Per-second sending rate for TFRC, TCP Reno, and unregulated UDP over a 120-second run at 5% loss. Shows the smoothness difference visually when plotted.
- `outputs/tfrc-implementation-runbook.md` — A runbook for embedding TFRC in a production media application: how to instrument the sender for RTT measurement, how to implement the receiver feedback channel, and what to monitor in production (smoothed RTT drift, feedback report loss, rate floor triggers).

## Exercises

1. **TFRC with DCCP transport.** Re-implement the TFRC sender and receiver over DCCP (Datagram Congestion Control Protocol) sockets using the Linux kernel's DCCP/CCID-3 support. Compare the kernel-managed rate to your userspace implementation under identical loss conditions. What does the kernel implementation do differently at the boundary cases?

2. **Bursty loss behavior.** Replace the uniform random loss model with a Gilbert-Elliott two-state Markov loss model (good state: 0.1% loss; bad state: 20% loss; transition probability: 0.05). Measure how TFRC's 8-interval sliding window responds to burst entry and burst exit. Does the weighted average react faster to burst entry or burst exit, and why?

3. **Receiver-driven TFRC.** Implement a variant where the receiver computes X using its own copy of the throughput equation and sends a rate limit directly, rather than sending raw (p, RTT) and letting the sender compute. Compare stability: does the sender overshoot less when rate decisions are centralized at the receiver?

4. **LEDBAT comparison.** Implement Low Extra Delay Background Transport (LEDBAT, RFC 6817) alongside TFRC on the same bottleneck link. LEDBAT uses one-way delay as its congestion signal instead of loss. Under what conditions does LEDBAT yield more throughput to TFRC, and under what conditions does it compete aggressively?

5. **Application-layer FEC alongside TFRC.** Add a Reed-Solomon forward error correction layer that sends k redundancy packets for every n data packets. At 5% loss, tune k/n so the application sees < 0.1% effective loss while TFRC still responds to the underlying network loss. What is the throughput overhead of FEC at 10% and 15% network loss?

6. **SCReAM for WebRTC.** Study the SCReAM (Self-Clocked Rate Adaptation for Multimedia) algorithm (RFC 8298), which is TFRC's modern WebRTC-oriented successor. Implement a minimal SCReAM sender using OWD (one-way delay) as the primary signal. Compare its rate trajectory against TFRC under the same 0–20% loss sweep.

7. **BBR comparison.** Run a BBR-controlled flow alongside your TFRC flow on the shared 10 Mbps bottleneck. BBR is model-based like TFRC but uses bandwidth-delay product estimation rather than the loss-equation. Measure the Jain fairness index between BBR and TFRC at 0%, 5%, and 10% loss. Under high loss, which flow dominates, and why does BBR's loss-insensitivity matter?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TFRC | A UDP congestion control | TCP-Friendly Rate Control (RFC 5348): an equation-based rate control for UDP that targets the same long-term throughput as TCP while producing far smoother short-term rate changes |
| TCP-friendly | Fair to TCP | A flow is TCP-friendly if its long-term throughput does not exceed the throughput a TCP Reno flow would achieve under the same (RTT, loss) conditions |
| Loss event | A packet drop | In TFRC, a loss event is one or more consecutive lost packets counted as a single event; grouping bursts prevents the equation from overreacting to correlated loss |
| Loss interval | Gap between events | The number of packets received between two consecutive loss events; TFRC averages the last 8 intervals with a recency-weighted formula to compute the loss event rate p |
| Loss fraction | p in the equation | The per-packet loss probability estimated at the receiver, derived from the inverse of the weighted-average loss interval length |
| Jain fairness index | Fairness score | J = (sum(xi))^2 / (n * sum(xi^2)); ranges from 1/n (maximally unfair) to 1.0 (perfectly fair); a value above 0.9 for TFRC+TCP indicates the two flows share the link equitably |
| t_RTO | Retransmit timeout | In the TFRC equation, t_RTO = max(4 * R, 1.0) seconds; it represents the TCP retransmission timeout contribution to the throughput equation's second term |
| EWMA | Smoothed average | Exponentially Weighted Moving Average; used to smooth per-sample RTT into a stable smoothed_RTT = 0.9 * smoothed_RTT + 0.1 * sample_RTT, filtering packet-level jitter |
| Feedback report | Receiver-to-sender control | A UDP datagram sent by the TFRC receiver once per RTT containing (loss_event_rate, receiver_rtt, x_recv, echoed_sender_timestamp); the sender's only view of network conditions |
| X_recv | Receiver throughput estimate | The rate at which the receiver is actually receiving data, estimated as bytes_received / 8s; used as an upper bound to prevent the sender from overshooting when feedback is delayed |
| Loss event rate | p in plain English | The frequency of loss events per packet transmitted; p = 1 / average_loss_interval; the key input to the TFRC throughput equation |
| Smooth rate adaptation | TFRC's key property | Unlike TCP which halves cwnd on every loss, TFRC decreases rate by at most 50% per RTT and increases only after one RTT of stable feedback, producing a gradual rate curve suitable for media encoding |

## Further Reading

- **RFC 5348** — Floyd, Handley, Padhye, Widmer. *TCP-Friendly Rate Control (TFRC): Protocol Specification.* IETF, 2008. The normative specification including the throughput equation, loss interval computation, and the worked example in appendix A that you should use to verify your implementation.
- **RFC 4342** — Floyd, Kohler, Padhye. *Profile for Datagram Congestion Control Protocol (DCCP) Congestion Control ID 3: TCP-Friendly Rate Control (TFRC).* IETF, 2006. Defines CCID-3, the DCCP congestion control profile that uses TFRC as its rate control algorithm; useful context for exercise 1.
- **Floyd, Handley, Padhye, Widmer** — *Equation-Based Congestion Control for Unicast Applications.* ACM SIGCOMM 2000. The original paper proposing TFRC; explains the design rationale for the equation, the 8-interval sliding window, and the smoothness-fairness trade-off that distinguishes TFRC from TCP.
- **Jain, Chiu, Hawe** — *A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems.* DEC Technical Report TR-301, 1984. The original paper defining the Jain fairness index used throughout this capstone; includes the derivation, intuition, and examples with competing flows.
- **RFC 8298** — Johansson, Sarker. *Self-Clocked Rate Adaptation for Multimedia (SCReAM).* IETF, 2017. The modern successor to TFRC designed for WebRTC; uses OWD as the congestion signal rather than loss, making it more responsive to shallow-buffer bottlenecks; relevant background for exercise 6.
