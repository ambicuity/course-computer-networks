# Reconstruct TCP Congestion Control Behavior From a Packet Capture

> Given only a packet capture, reconstruct the sender's congestion window evolution, slow-start threshold, and congestion-control phase machine, then prove the model against a reference TCP Reno implementation that generated the same trace. The capstone integrates the TCP reliability machinery of Phase 11, the loss-recovery machinery of Phase 12, the path-characterization tools (Wireshark, tcpdump) of Phase 17, and the analytical statistics of Phase 18. The deliverable is a faithful reconstruction with a mean absolute error under two MSS and over ninety percent phase agreement against the reference model.

**Type:** Capstone
**Languages:** Python (stdlib only), Wireshark, packet traces
**Prerequisites:** Phase 11 TCP sequencing and state machine; Phase 12 retransmission and congestion control lessons; familiarity with RTT estimation; Phase 17 packet-capture tooling
**Time:** ~150 minutes

## Learning Objectives

- Reconstruct the congestion window (cwnd) trajectory from a TCP pcap using only the seq, ack, timestamp, and window fields visible on the wire.
- Classify each RTT interval into slow-start, congestion avoidance, fast recovery, or timeout phases from observable growth patterns and loss events.
- Detect duplicate ACKs and retransmissions, then map each event to the correct triggering cause (triplicate-ACK fast retransmit vs. RTO timeout).
- Estimate the slow-start threshold (ssthresh) after every loss event from the observed flight size divided by two.
- Compare the reconstructed cwnd against a reference TCP Reno model and quantify both numerical divergence and phase-agreement percentage.
- Explain the limits of black-box reconstruction: window scaling, delayed ACKs, ACK compression, and application-limited flight sizes.

## The Problem

TCP congestion control is invisible at the application layer. A user sees a slow download, a VoIP call exhibits jitter, or a bulk transfer collapses to a trickle, but the congestion window, slow-start threshold, retransmission timer, and phase state machine all live inside the sender's kernel and never appear on the wire. The only evidence available is in the packet capture: the sequence numbers the sender chose, the ACK numbers the receiver returned, the timestamps, the flags, and the advertised window.

When a network engineer receives a pcap that demonstrates a throughput problem, the conventional tools (Wireshark's TCP analysis graphs, tcptrace, tcpstat) only display aggregate statistics and flag retransmissions. They do not show the cwnd trajectory, do not classify the phase at each RTT, and do not tell the operator whether the sender is in slow-start, congestion avoidance, fast recovery, or timeout-driven backoff. The cwnd is internal state; the analyst must reverse it from packet timing and sequence arithmetic.

This capstone asks you to build that reverse-engineering pipeline. You receive a stream of TCP segments with timestamps, sequence numbers, acknowledgment numbers, flags, and payload lengths. From that stream you must: (1) group the packets into bidirectional flows by four-tuple; (2) estimate the round-trip time by pairing data segments with their first cumulative ACK; (3) track bytes-in-flight as `(highest_seq_sent - highest_ack_received)` sampled at each new ACK; (4) detect loss events by counting duplicate ACKs and ACK-progression gaps; (5) classify each RTT interval into the correct congestion-control phase; (6) compute the implied ssthresh after each loss event; (7) validate the reconstruction against a reference Reno model that produced the same trace.

The challenge is that cwnd is not directly observable. The best inference is the maximum bytes-in-flight observed during one RTT, bounded by the receiver's advertised window. Loss events manifest as duplicate ACKs (three of which trigger fast retransmit and fast recovery) or as gaps in the ACK stream beyond the retransmission timeout (which trigger the timeout-driven reset). The reconstruction must handle window scaling, delayed ACKs, the difference between congestion-limited and application-limited flight sizes, and the ambiguity between Reno, CUBIC, and BBR at the wire level.

## The Concept

The reconstruction rests on the marriage of three independent measurements (flight size, RTT, loss signal) into one trajectory. Each alone is noisy; together they pin down the sender's cwnd with high confidence.

### The bytes-in-flight inference

The fundamental observation: at any instant, the number of unacknowledged bytes the sender has transmitted equals the difference between the highest sequence number sent and the highest cumulative ACK received. The sender's kernel enforces `bytes_in_flight <= min(cwnd, rwnd)`. If the receiver advertised a 64 KB window and the sender pushed 32 KB through it without an ACK, then bytes-in-flight is 32 KB and that is the cwnd floor.

The reconstruction bins time into RTT-sized windows and, for each window, records the maximum bytes-in-flight observed. That maximum is the cwnd estimate for that RTT, capped at the receiver's advertised window. This works because during steady-state the sender always pushes the pipe to the limit: in slow-start it doubles the window each RTT, in congestion avoidance it adds one MSS per RTT, in fast recovery it inflates by one MSS per duplicate ACK, and in timeout it drops to one MSS. The flight-size maximum is the closest approximation to cwnd that the wire allows.

### The phase machine

TCP Reno's congestion-control state machine has four observable phases:

| Phase | Observable signature | cwnd trajectory |
|---|---|---|
| Slow start | cwnd doubles every RTT | 1, 2, 4, 8, 16, 32 MSS |
| Congestion avoidance | cwnd grows by 1 MSS per RTT | linear, +1 per RTT |
| Fast recovery | cwnd inflated by dup ACKs, then halved | spike then drop to ssthresh |
| Timeout | cwnd reset to 1 MSS | collapse to 1, then slow-start again |

Each phase is distinguishable in the reconstructed trajectory by its growth pattern alone, even without the loss-event annotation. Slow-start shows exponential growth (ratio ~2 between consecutive samples); congestion avoidance shows linear growth (delta ~1 MSS); fast recovery shows a sharp rise followed by a halving; timeout shows a vertical drop to 1 MSS. The phase machine in the SVG draws these four regimes as distinct curves layered on the same time axis, with loss events marked as red diamonds on the cwnd envelope.

### The loss signal

Two distinct loss signals appear on the wire, and confusing them is the most common mistake in reconstruction.

Triplicate-ACK (fast retransmit): When the receiver gets an out-of-order segment, it immediately sends a duplicate ACK echoing the last in-order sequence number. Three such duplicate ACKs in a row trigger the sender's fast retransmit; cwnd is halved, ssthresh is set to half the flight size, and fast recovery inflates cwnd by one MSS per additional duplicate ACK. The wire signature is three identical ACK numbers arriving back-to-back with no data in between.

Timeout: When the retransmission timer expires before any ACK arrives, the sender retransmits the oldest unacked segment and resets cwnd to 1 MSS. The wire signature is a long gap in ACK progression (greater than the smoothed RTT plus four times its variance) followed by a single retransmission of an old sequence number.

The distinction matters: fast retransmit halves cwnd; timeout collapses it to 1 MSS. Misclassifying a timeout as fast retransmit will inflate the reconstructed cwnd by an order of magnitude and lead to wrong diagnoses of network pathologies.

### The RTT reference clock

Every cwnd sample is bound to an RTT interval. The reconstruction needs a clock to bin time. The first RTT is estimated from the SYN/SYN-ACK handshake. Subsequent RTTs are estimated by pairing each new data segment with the first cumulative ACK that covers its sequence number. The smoothed RTT (SRTT) is computed with the standard `SRTT = 0.875 * SRTT + 0.125 * R` formula from RFC 6298. Each phase bin spans one SRTT. The choice of RTT estimator matters: using a fixed constant (e.g., always 30 ms) desynchronizes the bins from the actual data bursts and increases reconstruction error by 20-40 percent on traces with varying RTT.

### Window scaling and delayed ACKs

Two phenomena complicate the inference. First, RFC 7323 window scaling allows advertised windows larger than 64 KB; without the scaling factor, the inferred cwnd ceiling would be wrong. The reconstruction reads the window-scale option from the SYN/SYN-ACK and multiplies the advertised window by `2^scaling_factor`. Second, RFC 1122 delayed ACKs mean the receiver sends one ACK for every two segments; this halves the ACK rate and can fool a naive loss detector into firing on a single duplicate ACK. The reconstruction must count three duplicate ACKs (not two) to trigger fast retransmit, and must handle ACK compression (where many ACKs arrive close together) by looking at the ACK number stream rather than ACK arrival times.

### Synthetic trace as ground truth

The reference implementation in `code/main.py` generates a synthetic trace by running a deterministic Reno state machine. Every segment's timestamp, sequence number, and ACK number is the exact output of that machine. The trace contains twenty-five RTTs with two loss events: a triplicate-ACK at RTT nine and a timeout at RTT sixteen. The reconstructed cwnd is compared sample-by-sample against the reference, and the mean absolute error plus the phase-agreement percentage form the reconstruction quality metric. With a synthetic trace the ground truth is perfect, so the residual error is purely the binning resolution; on a real pcap the additional error comes from delayed ACKs, ACK aggregation, and sender-side pacing.

### Comparison to modern congestion control

Reno is the simplest case. CUBIC (RFC 8312) replaces the linear congestion avoidance with a cubic function of time since last loss, which produces a concave-then-convex cwnd curve. BBR (Google) probes bandwidth and RTT independently and holds a model-driven pacing rate rather than a window; on the wire BBR looks like a very stable flight size with periodic probing bursts. The reconstruction technique still applies, but the phase-classification rules change. The reference model can be swapped from Reno to CUBIC to BBR by changing only the cwnd-update function; everything downstream (flight-size sampling, loss detection, comparison) is unchanged.

## Build It

`code/main.py` is a stdlib-only Python pipeline with seven components. The reference Reno model is deterministic, so the reconstruction is exact up to the resolution of the RTT bin.

1. **Trace generator** - `build_synthetic_trace()` simulates a twenty-five-RTT session with one fast retransmit and one timeout, returning a list of `TcpSegment` records with timestamps, sequence numbers, ACK numbers, flags, and payload lengths.
2. **Flow extraction** - `extract_flows()` groups segments by `(src_ip, src_port, dst_ip, dst_port)` four-tuple, separating the data sender from the ACK receiver.
3. **RTT estimation** - `estimate_rtts()` pairs each new data segment with the first cumulative ACK that covers it, returning a list of `RttSample` objects.
4. **Smoothed RTT** - `compute_srtt()` applies the RFC 6298 exponential weighted moving average to produce a single reference RTT used for binning.
5. **Loss detection** - `detect_loss_events()` scans the ACK stream for three identical ACK numbers in a row (triplicate-ACK) and for gaps in ACK progression exceeding twice the SRTT (timeout).
6. **cwnd reconstruction** - `reconstruct_cwnd()` bins time into RTT windows, samples the maximum bytes-in-flight per window, and classifies the phase from the growth pattern.
7. **Reference Reno model** - `reference_reno_model()` runs a deterministic Reno state machine fed the same loss events and produces the expected cwnd trajectory; `compare_models()` reports the mean absolute error and phase-agreement percentage.

Run `python3 code/main.py` and read the printed reconstruction table. The reconstructed cwnd starts at 1 MSS, doubles through slow-start RTTs zero to three, transitions to linear growth in RTTs four through eight, drops to roughly half the flight size after the triplicate-ACK at RTT nine, and collapses to 1 MSS after the timeout at RTT sixteen. Mean absolute error should be below 2 MSS and phase agreement above 90%.

## Use It

| Symbol | Meaning |
|---|---|
| `MSS = 1460` | Maximum segment size in bytes, the unit of cwnd |
| `INITIAL_CWND = 1` | Initial cwnd in MSS, the slow-start seed |
| `SRTT ~ 30 ms` | Smoothed RTT, the binning interval |
| `LossType.DUP_ACK` | Triplicate-ACK event, triggers fast retransmit |
| `LossType.TIMEOUT` | RTO event, collapses cwnd to 1 MSS |
| `TcpPhase.SLOW_START` | Exponential growth, cwnd doubles per RTT |
| `TcpPhase.CONGESTION_AVOIDANCE` | Linear growth, cwnd += 1 MSS per RTT |
| `TcpPhase.FAST_RECOVERY` | Brief inflation then halving |
| `TcpPhase.TIMEOUT` | cwnd reset to 1 MSS |

## Ship It

Outputs land in `outputs/`:

- `cwnd-reconstruction.txt` - The reconstructed cwnd timeline with per-RTT samples, phase labels, ssthresh values, and loss-event annotations.
- `loss-event-log.txt` - A structured log of every detected loss event: type, timestamp, triggering ACK number, duplicate-ACK count, and implied ssthresh.
- `reno-comparison.txt` - Side-by-side comparison of reconstructed vs. reference Reno cwnd with per-RTT absolute error and overall phase agreement.
- `reconstruction-runbook.md` - A one-page runbook describing how to apply this technique to a real pcap from `tcpdump` or Wireshark export, including how to handle window scaling, delayed ACKs, and ACK compression.

## Exercises

1. **Window scaling impact** - Add support for RFC 7323 window scaling and show how a scaled receiver window changes the cwnd ceiling during slow-start. Generate a trace with `window_scale=4` and compare the reconstruction against the unscaled reference.
2. **CUBIC reconstruction** - Modify the synthetic trace generator to model CUBIC instead of Reno (cubic growth function over time since last loss) and adjust the reference model. How does the reconstructed cwnd curve differ in slow-start and congestion avoidance?
3. **Delayed ACK sensitivity** - Introduce delayed ACKs (every other segment acknowledged) and show how it changes the dup-ACK threshold sensitivity. What happens to false-positive loss detection when the threshold is set to two instead of three?
4. **ECN-aware congestion** - Add ECN-marked packets (using a synthetic flag) and reconstruct an ECN-aware congestion response where cwnd halves on the first CE mark instead of waiting for 3 dup ACKs. How does the phase machine expand?
5. **Application-limited intervals** - Generate a trace with application-limited periods (sender has no data to send) and show how to distinguish "cwnd is not growing because of congestion" from "cwnd is not growing because the application is idle." What additional signal is needed?
6. **BBR vs. Reno discrimination** - Model a BBR-style sender that probes bandwidth and round-trip-time separately. How would the bytes-in-flight trajectory look, and what signature would distinguish it from a Reno or CUBIC sender at the wire level?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Congestion window (cwnd) | A TCP knob the OS tunes | The maximum bytes-in-flight the sender allows, inferred from the largest unacked burst per RTT |
| Slow-start threshold (ssthresh) | Where slow-start stops | The cwnd value at which growth switches from exponential to linear, set to half the flight size at the last loss |
| Fast retransmit | Resending after dup ACKs | Sending the lost segment after three duplicate ACKs without waiting for a timeout |
| Fast recovery | A Reno trick | Inflating cwnd by 1 MSS per additional dup ACK to keep the pipe full during retransmit |
| Bytes-in-flight | Unacknowledged data | `(highest_seq_sent - highest_ack_received)`, bounded by `min(cwnd, rwnd)` |
| Triplicate-ACK | Three dup ACKs | Wire signature of a single packet loss in the receiver's view, triggering fast retransmit |
| RTO timeout | The retransmission timer fires | Sender gave up waiting for an ACK and reset cwnd to 1 MSS |
| Window scaling | The window field is too small | RFC 7323 multiplier (2^scale) applied to the 16-bit advertised window |
| Delayed ACK | One ACK per two segments | RFC 1122 optimization that halves ACK rate; trips naive loss detectors if threshold is wrong |
| SRTT | Smoothed RTT | RFC 6298 exponentially-weighted RTT used as the binning clock |

## Further Reading

- RFC 5681 - TCP Congestion Control (the Reno specification, defines slow-start, congestion avoidance, fast retransmit, fast recovery)
- RFC 6298 - Computing TCP's Retransmission Timer (the SRTT and RTO computation used for binning)
- RFC 7323 - TCP Extensions for High Performance (window scaling, timestamps, PAWS)
- RFC 8312 - CUBIC for Fast Long-Distance Networks (modern replacement for Reno/AIMD)
- RFC 9002 - QUIC Loss Detection and Congestion Control (a modern comparison point with explicit cwnd signaling)
- Jacobson, Van. "Congestion Avoidance and Control." SIGCOMM 1988 (the original slow-start paper)
- Mathis, Semke, Mahdavi, Ott. "The Macroscopic Behavior of the TCP Congestion Avoidance Algorithm." 1997 (the `cwnd^2 / RTT` throughput model)
- Cardwell, Cheng, Gunn, Yeganeh, Jacobson. "BBR: Congestion-Based Congestion Control." ACM Queue 14(5), 2016 (the BBR model)
- Wireshark TCP analysis display filters: `tcp.analysis.flags`, `tcp.analysis.acks_frame`, `tcp.analysis.bytes_in_flight`, `tcp.analysis.rto`
- tcptrace and tcpstat for aggregate validation of the reconstruction
