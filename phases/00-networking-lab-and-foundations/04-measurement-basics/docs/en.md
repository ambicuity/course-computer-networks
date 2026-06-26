# Measurement Basics

> Network performance is a distribution, not a number. This lesson builds the measurement vocabulary you will reuse all course: **latency** (one-way delay vs. RTT), **jitter** (RFC 3550 inter-arrival variation), **packet loss**, **throughput vs. goodput**, and the difference between the **mean** and the **tail** (p50/p95/p99). You will learn why ICMP Echo (RFC 792, type 8 request / type 0 reply) timestamps measure RTT and not one-way delay, why averaging hides the p99 that users actually feel, and how the **bandwidth-delay product** (BDP = bandwidth × RTT) sets the in-flight bytes a TCP connection needs to fill a pipe. The accompanying `code/main.py` ingests a list of RTT samples (the kind `ping` prints) and computes count, min/avg/max, mean, standard deviation, jitter, loss rate, and a full percentile table — the same summary every real measurement tool emits. The classic failure mode this lesson kills: reporting "average latency is 40 ms" on a link whose p99 is 800 ms because of bufferbloat, and declaring the network healthy.

**Type:** Build
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 0 lessons 01–03 (lab setup, OSI/TCP-IP layering, addressing); comfort running `ping`/`traceroute`
**Time:** ~90 minutes

## Learning Objectives

- Distinguish **one-way delay**, **round-trip time (RTT)**, and **jitter**, and explain why ICMP Echo can only measure RTT.
- Compute and interpret **p50, p95, p99** percentiles from a sample set, and explain why the **mean** misrepresents tail-sensitive workloads.
- Calculate **packet loss rate** from sent/received counts and relate loss to TCP retransmission and throughput collapse.
- Derive the **bandwidth-delay product** and use it to size a TCP window or explain why a "fast" link delivers low throughput.
- Separate **throughput** from **goodput**, accounting for protocol header overhead (Ethernet + IP + TCP framing).
- Run `code/main.py` against real `ping` output and produce a reusable latency-summary artifact.

## The Problem

A user files a ticket: "the app is slow, but only sometimes." You run `ping app.internal` and see `rtt min/avg/max/mdev = 38.2/41.6/47.9/2.1 ms`. Looks healthy. You close the ticket. The complaints continue.

The mistake is treating the **average** as the truth. That `ping` ran 10 packets over 10 seconds — it never sampled the moment a full router queue added 600 ms of delay (bufferbloat), or the 2% of requests that hit a retransmission timeout. The user's "sometimes slow" is the **tail of the latency distribution**, and the average is mathematically blind to it. A link can have a 41 ms average and a 750 ms p99 simultaneously; the p99 is what a multi-request page load actually waits on.

Measurement Basics is the discipline of reducing a vague symptom ("slow") to a *distribution* you can defend with numbers: how many samples, what spread, what tail, how much loss. Without it, every later lesson — TCP congestion control, queueing, routing convergence — is unfalsifiable hand-waving. With it, you can say "p99 RTT is 750 ms with 2.1% loss, consistent with a saturated egress queue," and that hypothesis predicts what you will find in the next trace.

## The Concept

### One-way delay, RTT, and what ICMP can actually measure

Delay between two hosts has four additive components on each hop:

| Component | Cause | Scales with |
|---|---|---|
| Transmission delay | Serializing bits onto the wire | packet size ÷ link rate |
| Propagation delay | Speed of light in the medium (~5 µs/km in fiber) | distance |
| Processing delay | Router header inspection, lookup | per hop, ~µs |
| Queueing delay | Waiting behind other packets in a buffer | load (the variable one) |

**One-way delay** is the sum of these from source to destination. **RTT** is the source→dest→source sum. They are *not* simply `2 × one-way`: the forward and reverse paths can differ (asymmetric routing), and reverse-path queueing inflates RTT without touching forward delay.

ICMP Echo (RFC 792) measures **RTT only**. The Echo Request (type 8) and Echo Reply (type 0) share an Identifier and Sequence Number field so the sender can match a reply to a request; the sender stamps a local send time, and on reply computes `now − send_time`. Because both timestamps come from *one clock*, no clock synchronization is needed — but you only ever learn the round trip. Measuring true one-way delay requires synchronized clocks (e.g., the OWAMP protocol, RFC 4656, leaning on NTP/PTP), which is why `ping` reports RTT and never one-way.

The ICMP Echo header layout (after the 20-byte IPv4 header):

```text
 0      7 8     15 16            31
+--------+--------+----------------+
|  Type  |  Code  |   Checksum     |   Type=8 (req) / 0 (reply), Code=0
+--------+--------+----------------+
|   Identifier    | Sequence Number|   match reply→request
+-----------------+----------------+
|   Data (timestamp + payload ...)        |
+-----------------------------------------+
```

### Jitter: variation, not delay

**Jitter** is the variation in delay between consecutive packets — it matters for real-time media (VoIP, video) where a playout buffer must absorb it. RFC 3550 (RTP) defines an interarrival jitter estimate as a running mean of the absolute difference `D` between the transit-time deltas of successive packets:

```text
J(i) = J(i-1) + ( |D(i-1,i)| − J(i-1) ) / 16
```

The `/16` is a smoothing factor (an exponential moving average). In practice you can also report jitter as the standard deviation of inter-arrival gaps. `code/main.py` computes mean absolute successive difference — the simplest faithful jitter proxy from RTT samples. High average with low jitter is a long-but-stable path; low average with high jitter is a congested or wireless path, and it destroys VoIP MOS scores even when "average is fine."

### Percentiles and why the mean lies

Latency distributions are **right-skewed**: a floor set by physics, a long tail set by queueing and retransmission. The mean gets dragged by the tail but never reaches it. Report percentiles instead:

| Metric | Meaning | Use |
|---|---|---|
| p50 (median) | half the samples are faster | typical experience |
| p95 | 1 in 20 is slower | SLO threshold for many services |
| p99 | 1 in 100 is slower | what a 100-asset page load hits at least once |
| p99.9 | 1 in 1000 | fan-out / microservice tail amplification |

The **tail-amplification** trap: if a page makes 100 independent backend calls and each has a 1% chance of hitting the p99, the probability the *whole page* hits at least one slow call is `1 − 0.99¹⁰⁰ ≈ 63%`. The p99 of a single service becomes the *median* experience of a fan-out request. That is why averages are operationally useless and `code/main.py` prints the full percentile ladder. The SVG (`assets/measurement-basics.svg`) shows this skewed distribution with the mean sitting well left of p99.

### Packet loss and throughput collapse

Loss rate = `(sent − received) / sent`. `ping` reports it directly ("2% packet loss"). Loss matters far beyond the missing packet: TCP interprets loss as congestion and halves its window (multiplicative decrease). The Mathis approximation for steady-state TCP throughput under random loss:

```text
throughput ≈ MSS / (RTT × sqrt(p))
```

where `p` is loss probability. A link with 1% loss and 100 ms RTT and 1460-byte MSS caps a single flow near `1460 / (0.1 × 0.1) = ~146 KB/s` regardless of how much raw bandwidth exists. This is why a 1 Gbit/s link with 1% loss feels broken: loss, not capacity, is the bottleneck.

### Throughput vs. goodput

**Throughput** is all bits on the wire; **goodput** is application-payload bits delivered, excluding headers and retransmissions. A full-size Ethernet frame carrying TCP over IPv4:

```text
1518 B frame = 14 (Eth hdr) + 20 (IPv4) + 20 (TCP) + 1460 (payload) + 4 (FCS)
+ 8 B preamble/SFD + 12 B interframe gap on the wire
```

Goodput efficiency ≈ `1460 / 1538 ≈ 94.9%` at best, before any retransmission. Reporting "we pushed 940 Mbit/s on a 1 Gbit/s link" is correct *throughput* and a healthy ~95% goodput ceiling — not a defect.

### Bandwidth-delay product: sizing the pipe

**BDP = bandwidth × RTT** is the number of bytes "in flight" needed to keep a link full. For 1 Gbit/s and 80 ms RTT:

```text
BDP = 1e9 bit/s × 0.080 s = 8e7 bit = 10,000,000 B ≈ 10 MB
```

If TCP's window (receive window scaled by RFC 7323 window-scaling option) is smaller than the BDP, the sender stalls waiting for ACKs and throughput is capped at `window / RTT` no matter the link speed. A 64 KB window on that path delivers only `65536 / 0.08 ≈ 819 KB/s` — under 1% of the link. This is the single most common "fast link, slow transfer" root cause, and it is a *measurement* result: you derive it from RTT and observed throughput.

### Sampling matters

A 10-packet `ping` cannot characterize a p99 — you need ≥100 samples just to *have* a p99 bucket, and far more to estimate it stably. Bursty problems need higher sample rate or longer windows. Always report `n` (sample count) alongside any percentile; a "p99 of 800 ms" from 12 samples is noise, not signal. `code/main.py` prints `n` first for exactly this reason.

## Build It

1. Capture real samples: `ping -c 100 1.1.1.1 > outputs/ping-raw.txt` (use `-c 100` for a meaningful percentile set).
2. Read `code/main.py`. It defines `parse_ping_output()` (extracts `time=…` RTTs and the loss line), `Stats` computation (`min/max/mean/stdev`), `percentile()` (linear interpolation, the NIST/`numpy` "linear" method), and `jitter()` (mean absolute successive difference).
3. Run the built-in demo: `python3 code/main.py`. It feeds an embedded skewed sample set and prints the full summary.
4. Pipe your own data: `python3 code/main.py outputs/ping-raw.txt` to summarize the real capture.
5. Compare the printed p99 to the `avg` line `ping` itself reported — confirm the gap, and write it down. That gap is the whole lesson.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Characterize a link | n, min/p50/p95/p99/max, loss%, jitter from ≥100 samples | You report a distribution, not a single "average" number |
| Catch bufferbloat | p99 ≫ p50 with loss near 0 | You attribute the tail to queueing, not capacity, and predict it grows under load |
| Diagnose throughput cap | measured throughput vs. window/RTT and BDP | You show the window or loss — not raw bandwidth — is the limit |
| Validate a VoIP path | jitter (ms) and loss% over a sustained run | Jitter < ~30 ms and loss < 1%; you flag high jitter even when avg RTT is low |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/latency-summary.txt` — the saved output of `code/main.py` on your real capture, annotated with the link under test and your one-line diagnosis.
- Optionally `outputs/ping-raw.txt` — the raw `ping -c 100` capture it was computed from, so the result is reproducible.

Start from [`outputs/prompt-measurement-basics.md`](../outputs/prompt-measurement-basics.md) and fill it with your own numbers.

## Exercises

1. Run `ping -c 100` to a nearby host and a distant one (e.g., a server on another continent). Tabulate min/p50/p99 for both. Explain which component of delay (propagation vs. queueing) dominates each difference using the numbers.
2. You measure p50 = 22 ms, p99 = 610 ms, loss = 0.0% over 200 samples. Bufferbloat or routing flap? Justify from the loss value and the p99/p50 ratio.
3. A 10 Gbit/s WAN link with 90 ms RTT delivers only 58 Mbit/s on a single TCP flow with no loss. Compute the BDP, then the window size that would be needed to fill the link, and identify what is being limited.
4. Apply the Mathis formula: MSS 1460 B, RTT 50 ms, loss 0.25%. Estimate single-flow throughput. Then halve the loss and recompute — by what factor does throughput change, and why is it not linear?
5. A VoIP call has avg RTT 35 ms but jitter 65 ms and 0.5% loss. The "average is fine" but users report choppy audio. Explain which metric the playout buffer cares about and why the average is irrelevant here.
6. Your `ping` ran only 8 packets and reported a 900 ms max. A colleague writes "p99 = 900 ms" in the incident report. Critique this statistically and state the minimum sample count you would require before quoting a p99.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Latency | "the ping number" | One-way or round-trip *delay*; `ping` only gives RTT, not one-way |
| Jitter | "lag spikes" | Variation in inter-packet delay (RFC 3550 EMA); kills real-time media independent of average delay |
| Average latency | "the speed of the link" | The mean — dragged by but blind to the tail; useless for tail-sensitive work |
| p99 | "the worst case" | The 99th percentile; 1 in 100 is slower, *not* the max; becomes the median of a 100-call fan-out |
| Packet loss | "dropped packets" | (sent−received)/sent; triggers TCP window halving — caps throughput via the Mathis bound |
| Throughput | "the bandwidth" | All bits on the wire including headers and retransmissions |
| Goodput | "throughput" | Application payload only; ~95% of throughput at best after framing overhead |
| BDP | "buffer size" | Bandwidth × RTT — the in-flight bytes needed to fill a pipe; caps throughput if the window is smaller |
| RTT | "round trip" | Sum of forward + reverse delay; not 2× one-way when paths are asymmetric |

## Further Reading

- **RFC 792** — Internet Control Message Protocol (ICMP Echo Request/Reply, types 8 and 0)
- **RFC 3550** — RTP, §6.4.1 interarrival jitter computation
- **RFC 4656** — OWAMP, One-Way Active Measurement Protocol (true one-way delay)
- **RFC 7323** — TCP Extensions for High Performance (window scaling, timestamps)
- **RFC 2544** — Benchmarking Methodology for Network Interconnect Devices
- Mathis, Semke, Mahdavi, Ott — "The Macroscopic Behavior of the TCP Congestion Avoidance Algorithm" (1997), the `MSS/(RTT·√p)` model
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §2.1 (the four delay components) and §6.5 (TCP performance)
- Gettys & Nichols — "Bufferbloat: Dark Buffers in the Internet" (ACM Queue, 2011)
