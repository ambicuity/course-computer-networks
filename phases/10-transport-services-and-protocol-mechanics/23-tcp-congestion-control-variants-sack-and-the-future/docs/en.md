# TCP Congestion Control Variants, SACK, and the Future of TCP

> TCP congestion control began with Jacobson's 1988 paper that introduced **slow start** (exponential `cwnd` growth from an initial window of one MSS, RFC 2581, raised to 4 MSS in RFC 6928 / RFC 3390) and **congestion avoidance** (linear growth of `cwnd` by one MSS per RTT, the **AIMD** rule — Additive Increase, Multiplicative Decrease). When loss is detected by three duplicate acks, **fast retransmit + fast recovery** (RFC 5681) halves `cwnd` and stays in congestion avoidance instead of dropping back to slow start. **Selective Acknowledgment (SACK)**, defined in RFC 2018 and refined in RFC 2883, lets the receiver report up to three ranges of out-of-order bytes it has buffered, so the sender can retransmit exactly what is missing instead of everything from the first lost byte. RFC 3517 standardizes the SACK-aware loss-recovery algorithm. Modern variants replace AIMD with different control laws: **CUBIC** (default in Linux, RFC 8312) grows `cwnd` as a cubic function of time since the last loss; **BBR** (Google, RFC 9067) estimates the bottleneck bandwidth and round-trip propagation delay directly instead of reacting to loss. **Explicit Congestion Notification (ECN)** (RFC 3168) lets routers mark packets instead of dropping them, and the ECE/CWR bits (lesson 18) carry the feedback to the sender. This lesson implements the AIMD saw-tooth, walks CUBIC's window-growth function, and explains where TCP is heading in the face of multi-gigabit links that are delay-limited, not loss-limited.

**Type:** Project
**Languages:** Python, simulation, ns-style traces
**Prerequisites:** Lessons 17–22, basic calculus for the CUBIC function
**Time:** ~120 minutes

## Learning Objectives

- Trace the AIMD saw-tooth: slow start with `cwnd` doubling per RTT, then linear growth of one MSS per RTT, then halving on loss.
- Compare TCP Tahoe (drops to slow start on any loss) and TCP Reno (fast retransmit + fast recovery; halves `cwnd` and stays in CA).
- Implement CUBIC's window-growth function `W(t) = C × (t − K)³ + W_max` and explain why it scales to high-bandwidth paths.
- Show how SACK lets a sender retransmit exactly the missing ranges instead of everything from the first lost byte, and how RFC 3517 turns SACK blocks into a recovery plan.
- Explain ECN: the IP-layer congestion-marking mechanism that uses ECE/CWR to signal the sender instead of dropping packets.
- Sketch BBR's bandwidth-delay product model and explain why a loss-based controller (AIMD/CUBIC) underutilizes a path with non-zero bufferbloat.

## The Problem

Your data-center TCP transfers top out at 1 Gbps even though the path is 10 Gbps. Your colleague says "just turn on CUBIC" but the box is already running CUBIC and you are still capped at 1 Gbps. The link is not dropping packets — it is queuing them. You need to understand that **loss is the wrong signal at multi-gigabit speeds** and what to do about it.

The deeper problem is that congestion control based on packet loss (AIMD and CUBIC) treats any queue build-up as "congestion approaching" and slows down. On a path with a deep buffer (a common data-center switch problem called **bufferbloat**), this gives a saw-tooth pattern that under-utilizes the link. BBR, DCTCP, and other modern schemes change the signal entirely.

## The Concept

### Slow start (RFC 2581)

When a connection opens, the sender knows nothing about the path. It starts with `cwnd = IW` (initial window, RFC 6928 = min(10 MSS, ~14600 bytes), used to be 1 MSS in RFC 2581 and 4 MSS in RFC 3390) and grows `cwnd` exponentially: for every ACK that acknowledges new data, `cwnd += MSS × MSS / cwnd`. The effect is that `cwnd` doubles every RTT until it hits `ssthresh` (slow-start threshold). This is **not** "slow" — it is exponential growth, the fastest safe probe of an unknown path.

### Congestion avoidance and AIMD

After slow start, the sender enters **congestion avoidance** and grows `cwnd` linearly: for every ACK that acknowledges new data, `cwnd += MSS × MSS / cwnd`. Over a full RTT, this adds exactly one MSS. The full rule is **AIMD**:

- **Additive Increase**: `cwnd += MSS` per RTT (in CA).
- **Multiplicative Decrease**: on loss, `cwnd *= 0.5` and `ssthresh = cwnd`.

AIMD converges to fairness and efficiency — the classic Chiu-Jain 1989 result. Two flows sharing a bottleneck converge to equal shares regardless of their starting windows.

### Tahoe vs Reno

- **Tahoe (1988, 4.2BSD)**: any loss drops `cwnd` to 1 MSS and re-enters slow start. Aggressive but wasteful.
- **Reno (1990)**: fast retransmit on three duplicate acks; fast recovery halves `cwnd` and stays in CA. Less wasteful for single-packet loss; still drops to slow start on a timeout.

Reno's saw-tooth (the canonical TCP pattern in textbooks) is `cwnd` growing linearly, halving on each loss event. The area under the saw-tooth is the throughput.

### CUBIC (RFC 8312, default in Linux since 2.6.19)

CUBIC replaces Reno's linear growth with a **cubic function of time since the last loss**:

```
W(t) = C × (t − K)³ + W_max
```

where `W_max` is the `cwnd` at the time of the last loss, `K` is the time it would take to reach `W_max` again under cubic growth, and `C` is a scaling constant (typically `0.4`). The function is concave at small `t` (probes cautiously after a loss) and convex at large `t` (probes aggressively once the path has been silent for a while).

CUBIC's advantage is **RTT-fairness**: under Reno, a flow with a 100 ms RTT grows at the same rate per second as a flow with a 10 ms RTT — but in absolute bytes per second the long-RTT flow is 10× slower. CUBIC scales by time, so a long-RTT flow eventually catches up.

### SACK (RFC 2018, RFC 2883, RFC 3517)

Cumulative ACKs tell the sender only the next in-order byte expected. After packet 2 is lost, the receiver gets packets 3, 4, 5, 6 and acks 2 each time. Without SACK, the sender retransmits everything from 2 onward — wasting bandwidth.

SACK adds a TCP option (Kind 5) listing up to 3 ranges of bytes received out of order. After receiving packets 3–4 and 6, the receiver ACKs `ACK=2` plus `SACK: 3-4, 6-7`. The sender knows exactly what is missing and retransmits only `2` and `5`. RFC 3517 standardizes the SACK-aware loss-recovery algorithm.

### ECN (RFC 3168)

Routers running **Active Queue Management** (AQM, e.g., RED, PIE, CODEL) can mark packets with an ECN codepoint instead of dropping them. The receiver reflects the ECE flag in the next ACK back to the sender, which reacts exactly as it would to a single packet loss. ECN avoids the actual drop, so no retransmission is needed — the sender just slows down. RFC 3168 is the IP/TCP piece; modern AQM (RFC 8289) covers the queue side.

### BBR (RFC 9067)

Bottleneck Bandwidth and Round-trip propagation time (BBR) replaces loss-based control with **model-based control**. The sender estimates two quantities:

- `BtlBw` — the maximum delivery rate observed over a recent window (the bottleneck bandwidth).
- `RTprop` — the minimum round-trip time observed when the path was not queued (the round-trip propagation delay).

The product `BtlBw × RTprop` is the bandwidth-delay product — the number of bytes that fit in the pipe. BBR paces its sends at `BtlBw` and tries to keep `inflight = BDP`. It reacts to **measured delay growth**, not loss, which lets it coexist with bufferbloat instead of saw-toothing against it.

### The future of TCP

Three threads:

1. **Faster feedback.** RTT-independent control (CUBIC) and delay-based control (BBR) replace pure AIMD.
2. **In-kernel extensibility.** Linux's TCP congestion-control API (since 2.6.13) lets researchers swap `tcp_congestion_ops` without recompiling.
3. **Alternatives for new applications.** **QUIC** (RFC 9000) runs over UDP, builds its own ACK and congestion scheme, and lets applicationspace evolve faster than kernel-space.

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/23-tcp-congestion-control-variants-sack-and-the-future
python3 code/main.py
```

The script:

1. Simulates a Reno saw-tooth: linear increase to the link's BD product, halving on each loss, and computes throughput as the area under the curve.
2. Walks CUBIC's window-growth function over a few seconds of simulated time after a loss event.
3. Demonstrates SACK: given a lost-packet set, computes the retransmission list under cumulative ACK vs SACK and reports the bandwidth savings.
4. Walks ECN: a marked packet triggers ECE in the receiver's next ACK, which the sender treats as one congestion event.
5. Compares BBR's model-based control with Reno on a path with 200 ms RTT and 100 ms of buffer-induced delay.

Use `reno_sawtooth()`, `cubic_window()`, `sack_retransmit_plan()`, and `ecn_session()` to plug in your own parameters.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| Reno halves cwnd on loss | `reno_sawtooth(...)` prints `cwnd` per RTT | `ss -ti` shows `cwnd:` field |
| CUBIC scales with time | `cubic_window(...)` over 30 RTTs | `cat /proc/sys/net/ipv4/tcp_congestion_control` (should be `cubic`) |
| SACK retransmits only gaps | `sack_retransmit_plan(...)` lists retransmissions | Wireshark shows SACK option |
| ECN reflects marks as ECE | `ecn_session()` walks the four-segment exchange | `tcp.ecn` filter in Wireshark |
| BBR's model | `bbr_model(...)` prints `BtlBw` and `RTprop` estimates | `ss -ti` with `tcp_congestion_control=bbr` |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable comparison table of Reno, CUBIC, BBR, and DCTCP control laws and their reaction to loss, delay, and ECN.
- A reference CUBIC implementation in your language, with `C` and `W_max` as parameters.

Start from [`outputs/prompt-tcp-congestion-control-variants-sack-and-the-future.md`](../outputs/prompt-tcp-congestion-control-variants-sack-and-the-future.md).

## Exercises

1. With `cwnd = 10 MSS`, MSS = 1 KB, RTT = 100 ms, and one loss per 10 RTTs, compute the average throughput of a Reno saw-tooth.
2. CUBIC's growth function: given `W_max = 100 MSS`, `C = 0.4`, `K = 5 s`, compute `W(t)` at `t = 0, 2, 5, 8, 10` seconds.
3. Without SACK, a sender with `cwnd = 64 KB` loses packets 30 and 50 in a single window. How many bytes does it retransmit? With SACK reporting `SACK: 31-50, 51-64`, how many bytes does it retransmit?
4. Show the four-segment exchange between sender, network, and receiver that uses ECN to signal congestion without dropping packets.
5. BBR measures `BtlBw = 800 Mbps` and `RTprop = 80 ms`. What is the bandwidth-delay product, and how many bytes should `inflight` hold?
6. Why does Reno perform poorly on a path with deep buffers (bufferbloat), while BBR does not?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Slow start | "exponential growth" | `cwnd` doubles per RTT until `cwnd ≥ ssthresh` |
| Congestion avoidance | "linear growth" | `cwnd += MSS` per RTT (the AIMD increase) |
| AIMD | "fairness rule" | Additive Increase, Multiplicative Decrease — Chiu-Jain convergence |
| `ssthresh` | "slow-start threshold" | Boundary between slow start and congestion avoidance |
| Fast retransmit | "retransmit on 3 dup-acks" | RFC 5681 — skip the 1 s timer on single-packet loss |
| Fast recovery | "halve cwnd, keep going" | After fast retransmit, drop to `cwnd/2` and stay in CA |
| CUBIC | "cubic window growth" | RFC 8312 — `W(t) = C × (t − K)³ + W_max` |
| SACK | "selective ack" | RFC 2018 — receiver lists up to 3 out-of-order byte ranges |
| ECN | "early warning" | RFC 3168 — router marks instead of dropping; ECE/CWR carries the signal |
| BBR | "model-based" | RFC 9067 — control based on `BtlBw × RTprop`, not loss |

## Further Reading

- RFC 2581 — TCP Congestion Control (the original AIMD specification, superseded by RFC 5681)
- RFC 5681 — TCP Congestion Control (current AIMD, fast retransmit, fast recovery)
- RFC 3390 — Increasing TCP's Initial Window
- RFC 6928 — Increasing TCP's Initial Window (current 10 MSS)
- RFC 8312 — CUBIC for Fast Long-Distance Networks
- RFC 2018 — TCP Selective Acknowledgement Options
- RFC 2883 — An Extension to the SACK Option
- RFC 3517 — A Conservative Selective Acknowledgment-based Loss Recovery Algorithm
- RFC 3168 — The Addition of Explicit Congestion Notification to IP
- RFC 9067 — BBR Congestion Control (current BBR v1)
- RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport
- Jacobson, 1988 — *Congestion Avoidance and Control* (the original slow-start paper)
- Chiu & Jain, 1989 — *Analysis of the Increase and Decrease Algorithms for Congestion Avoidance* (AIMD convergence)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP congestion control