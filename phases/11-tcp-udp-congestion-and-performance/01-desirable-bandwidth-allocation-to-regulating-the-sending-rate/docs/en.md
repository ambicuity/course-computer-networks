# Desirable Bandwidth Allocation to Regulating the Sending Rate

> Before a transport sender picks any number to send, three questions must be answered: **how much** of the link is available, **how to share** it fairly across competing flows, and **how fast to adjust** when the world changes. Section 6.3.1 fixes the *target* (efficiency + max-min fairness + power, with convergence under churn), and Section 6.3.2 fixes the *control law* — AIMD (Additive Increase, Multiplicative Decrease) under binary congestion feedback (Chiu and Jain, 1989). The big numerical anchors are the **Padhye throughput formula** `B ≈ (MSS / RTT) * 1 / sqrt(2p/3)` (TCP fits loss rate p with a 1/sqrt(p) curve), the canonical **AIMD update**: `W += 1/W` per ACK, halve on loss, and the cross-flow **Jain fairness index** `F = (sum r_i)^2 / (n * sum r_i^2)`. The lab builds all three pieces — water-filling max-min, AIMD convergence to the efficiency/fairness intersection, and a leaky-bucket regulator that turns a bursty source into a steady drain — so the regulatory mechanism is something you can hold in code, not just remember.

**Type:** Build
**Languages:** Python, no external dependencies
**Prerequisites:** IP and datagram forwarding (Phase 5), sliding-window reliability (Phase 10 lessons on Go-Back-N and Selective Repeat), familiarity with bytes/sec as a unit
**Time:** ~90 minutes

## Learning Objectives

- Compute a **max-min fair** allocation on a multi-link topology using progressive-filling (water-filling) and explain why it leaves spare capacity on some links.
- Compute Kleinrock's **power = load / delay** and identify the load that maximizes it as the *efficient* operating point below full link capacity.
- Run an **AIMD** control law on N flows sharing one link and show convergence to the unique fair-and-efficient operating point (Chiu-Jain 1989).
- Apply **Jain's fairness index** `F = (sum r_i)^2 / (n * sum r_i^2)` and explain why `F = 1` is perfectly fair and `F = 1/n` is the worst case.
- Use a **leaky-bucket regulator** (capacity `beta`, drain rate `rho`) to shape a bursty arrival pattern into a steady output and identify when the bucket overflows.
- Diagnose the **TCP-friendly rate** `B ≈ (MSS / RTT) / sqrt(p)` and reason about why a non-AIMD protocol that goes faster starves TCP.

## The Problem

Your team provisions a 1 Gbps campus link that is shared by 40 PhD students running parallel data pipelines, 12 VoIP handsets, the campus learning-management system, and the security camera upload. At 8:55 a.m. the link is nearly empty. At 9:00 a.m. the LMS pushes the morning quiz to 8000 browsers, the cameras double their frame rate because of a sun glare auto-exposure bug, and four post-docs start scp transfers of multi-gigabyte datasets to a sister institution.

A network operator watching a single MRTG graph sees the link "hit capacity" and concludes "we need more bandwidth." But what is actually happening is more interesting:

- The LMS push and the scp transfers are both **elastic** — they would use any bandwidth they could get.
- The VoIP handsets are **inelastic** — they need a fixed ~64 kbps each with bounded jitter.
- The cameras are sending **CBR-like** bursts that the UDP transport does not back off.

Without a *congestion control algorithm* on the elastic senders, every elastic sender pushes harder and harder until the link's queues saturate, drops happen at the tail of every burst, and the throughput of every elastic sender collapses to almost nothing — the textbook calls this **congestion collapse**, and it is the failure Fig. 6-19(a) warns about.

This lesson is about the *target* we want the elastic senders to converge to and the *control law* that gets them there. It is the foundation that TCP's congestion control (later lessons in this phase) is built on.

## The Concept

### Efficiency, power, and where to aim below capacity

The naive goal "use all the bandwidth" is wrong. On a 100 Mbps link, splitting it 20/20/20/20/20 Mbps among five flows looks efficient, but traffic is bursty, and once the offered load approaches capacity, **delays climb** and **goodput falls**. Fig. 6-19 of the textbook plots goodput vs. offered load (a) and delay vs. offered load (b). The goodput curve bends downward before reaching the capacity line; the delay curve bends upward.

To pin the *efficient* load between these bends, Kleinrock (1979) defined

```
power = (offered load) / (delay)
```

Power rises with load while delay stays roughly constant, reaches a maximum, then falls as delay grows rapidly. The transport protocol should aim for the load at the **peak of the power curve** — strictly *below* full capacity, because aiming at full capacity spends most of the throughput budget on queueing delay.

Practical translation: when AIMD later says "send faster until something breaks, then halve," the implicit target is the knee of the goodput curve, not the link's wire rate. RFC 5681 makes this explicit: the loss event that triggers the multiplicative decrease is the signal that the network has crossed into the delay-climbing regime.

### Max-min fairness across overlapping links

Suppose four flows A, B, C, D cross the network shown in Fig. 6-20 of the textbook (every link has capacity 1):

| Link | Flows on the link |
|---|---|
| R1–R2 | A only |
| R2–R3 | A and B |
| R4–R5 | B, C, D |
| R5–R6 | C and D |

Equal division by flow would be unfair: A traverses three hops while D traverses two. The textbook's fairness notion is **max-min**: *no flow's bandwidth can be increased without decreasing the bandwidth of a flow that already has less.* The water-filling (progressive-filling) algorithm finds it:

1. Start every flow at rate 0.
2. Increase all flows together by `delta`, recomputing the bottleneck each step.
3. When a flow's path is saturated, freeze that flow and continue raising the rest.
4. Stop when every flow is frozen.

For the textbook topology this gives **A = 2/3, B = 1/3, C = 1/3, D = 1/3**. Notice the spare capacity on R1–R2 (A is alone on a 1.0 link, but only consumes 2/3) and on R5–R6 (only C and D, each at 1/3, total 2/3). The water-filling algorithm deliberately leaves that capacity unused because redistributing it would hurt a smaller flow.

`code/main.py` computes this exact allocation using progressive filling.

### The four-bandwidth-signal landscape

Section 6.3.2 surveys how senders can be told to slow down. The four well-known families:

| Protocol | Signal | Explicit? | Precise? |
|---|---|---|---|
| XCP (Katabi et al., 2002) | "Send at rate R." | Yes | Yes |
| TCP + ECN (RFC 3168) | "You saw congestion." | Yes | No |
| FAST TCP (Wei et al., 2006) | RTT grew | No | Yes (sort of) |
| Compound TCP (Tan et al., 2006) | Loss + RTT | No | Yes |
| CUBIC TCP (Ha et al., 2008), default in Linux | Loss | No | No |
| Classical TCP (RFC 5681) | Loss | No | No |

In the "explicit + precise" corner (XCP), a sender just adopts the rate the router tells it. In the "implicit + imprecise" corner (classical TCP), the sender probes with `+1 MSS per RTT`, halves on a loss, and hopes the resulting oscillation centers on the power peak. AIMD is the *control law* that works under the imprecise, binary signal the Internet actually provides.

### AIMD: the only control law that converges

Chiu and Jain (1989) showed by a geometric argument that, given **binary** congestion feedback, **AIMD** is the only control law that converges to the intersection of the *fairness line* (`r1 = r2`) and the *efficiency line* (`r1 + r2 = C`). The argument is reproduced in Fig. 6-24 and 6-25 of the textbook.

Other control laws diverge or oscillate without converging:

| Law | Behavior |
|---|---|
| AIAD (additive increase, additive decrease) | Hugs a 45-degree line through the start point; never reaches fairness unless it started there. |
| MIMD (multiplicative increase, multiplicative decrease) | Hugs a line through the origin; converges neither to fairness nor to full efficiency. |
| AIMD | Walks along a sawtooth that intersects the fair-efficient point. |
| MIAD (multiplicative increase, additive decrease) | Diverges away from the optimal point. |

The intuition is that the *decrease* must be aggressive (multiplicative, so it spans the fairness distance in one step) and the *increase* must be gentle (additive, so it does not skip past the fair point).

A modern TCP implementation uses the variants:

- **Slow start**: `cwnd += MSS` per ACK, doubling the window each RTT, until the first loss.
- **Congestion avoidance**: `cwnd += MSS^2 / cwnd` per ACK (equivalent to `+1 MSS per RTT`), halve on each loss (the `cwnd *= 0.5` step is the multiplicative decrease).
- **Fast retransmit / fast recovery** (RFC 2581 → RFC 5681): three duplicate ACKs trigger a retransmit and a halving without going all the way back to slow start.

### Rate vs. window: why TCP adjusts the window

Section 6.3.2 closes with an important implementation note. Rate is a continuous quantity but TCP's natural unit of accounting is the **window** — the number of unacknowledged bytes in flight. Because

```
rate ≈ cwnd / RTT
```

adjusting `cwnd` is equivalent to adjusting the rate, and it is easier to combine with flow control (which already uses a window). A change in `cwnd` shows up in the next ACK-clocked send and takes effect within one RTT.

This is why every TCP congestion-control algorithm — Reno, CUBIC, BBR, Vegas — speaks in windows even when the conceptual object is a rate.

### Leaky-bucket regulator: shaping bursts into a steady drain

A *regulator* in the language of Sec. 6.3.2 is a network-side mechanism (RFC 2574 and others) that smooths the sender's traffic to match the agreed rate. The textbook leaky bucket has:

- A bucket of size `beta` tokens.
- Tokens arrive at the source's offered rate (typically the full burst).
- Tokens drain at the agreed rate `rho`.
- When the bucket is full, additional tokens are discarded (the sender's excess is dropped at the regulator).

This is the same idea as a token-bucket policer in IntServ and as the shaping in RFC 2475. The regulator is a local mechanism that turns the *congestion-control target* (don't send faster than the agreed rate) into something a host can implement without per-flow state on the router.

### TCP-friendly rate and the Padhye formula

For the case of an elastic sender that *does* implement AIMD but competes with a non-AIMD streaming protocol, RFC 5348 defines the **TCP-friendly rate**:

```
B ≤ (MSS / RTT) * (1 / sqrt(2p/3))
```

where `p` is the steady-state loss event rate. This is the Padhye et al. (1998) formula derived from TCP Reno's sawtooth. The key takeaway is the **inverse-square-root dependence on loss**: cutting the loss rate from 1% to 0.01% (a factor of 100) increases the *fair share* by a factor of 10. This is why small loss rates are precious and why AIMD is so gentle on the increase side.

A non-TCP-friendly protocol — one that uses, say, constant-rate UDP at the link's wire rate — will starve TCP senders because every AIMD step of TCP shrinks its window while the UDP sender does not budge. RFC 5348 and the broader **TCP-friendly congestion control** literature (Floyd et al., 2000) exist to head this off.

## Build It

The artifact is `code/main.py`. It contains three independent demonstrations that can be run together or sliced apart:

1. **Progressive-filling max-min fair allocation** (Sec. 6.3.1)
   - Build a `Link` dataclass with a capacity and a list of flow names.
   - Implement `max_min_fairness(flows, links)` that starts every flow at 0 and raises all active flows until the next bottleneck is hit.
   - Reproduce the textbook four-flow example: `A=2/3, B=1/3, C=1/3, D=1/3`.

2. **AIMD convergence to the fair-efficient point** (Sec. 6.3.2)
   - Build a list of `AIMDFlow` dataclasses, each holding a `rate`.
   - At each step, additively increase every flow by 1 Mbps and multiplicatively decrease every flow by 0.5 if the combined rate exceeds capacity.
   - Print snapshots every few steps and report `Jain's fairness index` at the end.

3. **Leaky-bucket regulator** (Sec. 6.3.2 final paragraph)
   - Build a `LeakyBucket` dataclass with `capacity`, `drain_rate`, and `tokens`.
   - At each step, add the incoming burst to the bucket (capped at `capacity`) and drain at `drain_rate * dt`.
   - Trace a bursty arrival pattern and show how the backlog absorbs peaks while the output stays steady.

Run it with `python3 code/main.py`. No pip dependencies.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | IPv4/IPv6 header (protocol = 6 for TCP, 17 for UDP), the TCP segment header (`cwnd`, `rwnd`), and the kernel `/proc/net/snmp` counters. | You can name which header field tracks the regulator's *target rate* (`rcv_wnd`, `snd_cwnd`) and which tracks the *signal* (`retrans_segs`, `tcp_ecn`). |
| Explain normal AIMD behavior | Plot `cwnd` over time on a single bottleneck. | You see a sawtooth: `cwnd` grows by ~1 MSS per RTT, halves on a loss event, the sawtooth amplitude shrinks as the bottleneck stabilizes. |
| Diagnose congestion collapse | Compare `tcpAttemptFails` and `tcpOutSegs` before and after a capacity drop. | When the link becomes lossy, `tcpAttemptFails` jumps and `tcpOutSegs` per second falls — the source keeps sending but useful throughput collapses. |
| Diagnose non-TCP-friendliness | Compute `B_TCP = (MSS/RTT) / sqrt(2p/3)` and compare to a UDP sender's measured rate. | If the UDP rate exceeds `B_TCP`, the UDP sender is *starving* its TCP siblings. |

## Ship It

The `outputs/` directory contains a one-page runbook. The recommended deliverable for this lesson is a Markdown file `outputs/bandwidth-allocation-runbook.md` with three sections:

1. **Diagnosis flow**: what to look at first when throughput drops (link utilization vs. retransmissions, RTT histogram, ECN marks).
2. **Allocation table**: the max-min fair allocation for a *specific* topology in your environment, computed by feeding the topology into `max_min_fairness`.
3. **Sanity check**: the Padhye TCP-friendly rate for your typical `MSS`, `RTT`, and observed `p`, so you know what is the most a TCP sender *should* be achieving.

## Exercises

1. **Modify the topology**. In `code/main.py`, add a fifth flow E that crosses R1–R2 and R3–R6 only (bypassing R2–R3 and R4–R5). Recompute max-min fair rates and explain why A and E end up sharing the R1–R2 bottleneck 50/50 while B, C, D still share R4–R5 1/3 each.
2. **AIMD vs. AIAD**. Implement an AIAD variant (`+1` and `-1` per step) and show that it oscillates along a 45° line without reaching the fairness point, confirming Chiu-Jain by simulation.
3. **Jain index for unequal RTTs**. The textbook notes that AIMD is biased toward flows with shorter RTTs (a closer host wins more bandwidth). Construct a scenario with two flows, RTTs of 20 ms and 200 ms, and compute Jain's index after 100 AIMD steps on a 100 Mbps link.
4. **Leaky-bucket overflow detection**. Feed an arrival pattern of `[20, 0, 20, 0, 20, ...]` into a bucket of capacity 10 and drain rate 5/step. Identify every step where the bucket overflows and compute the total discarded volume.
5. **Padhye sanity check**. For a flow with MSS = 1460 bytes, RTT = 80 ms, observed loss event rate `p = 0.001`, compute `B_TCP` in Mbps. How does it compare to the actual throughput? If actual > `B_TCP`, the sender is being unfair.
6. **ECN vs. drop**. Modify the AIMD simulator so that an ECN-marked ACK halves the window and a dropped segment halves *and* restarts slow start. Show the impact on the time-averaged window size.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Max-min fairness | "Everyone gets the same share." | The rate vector in which no flow can be increased without decreasing a flow with less; spare capacity on some links is *deliberately* unused. |
| Power (Kleinrock) | "Throughput divided by delay." | The objective that picks the efficient load *below* full capacity. The peak of the power curve is the operating point, not the link's wire rate. |
| AIMD | "Add one, halve on loss." | The control law that converges to the unique fair-and-efficient operating point under binary congestion feedback. |
| Jain's index | "A fairness number between 1/n and 1." | `F = (sum r_i)^2 / (n * sum r_i^2)`. Equals 1 when all `r_i` are equal; equals `1/n` when one flow gets everything. |
| Leaky bucket | "Smooths bursts." | A regulator with capacity `beta` and drain rate `rho` that drops arrivals when full; turns a bursty source into a steady drain. |
| TCP-friendly | "Plays nice with TCP." | A rate at most `B ≈ (MSS/RTT) / sqrt(2p/3)` (Padhye); a non-TCP sender faster than this starves its TCP siblings. |
| Congestion collapse | "The link is full but throughput is zero." | The failure mode in which senders retransmit packets that are merely delayed, multiplying load without adding goodput. |

## Further Reading

- Tanenbaum, Feamster, Wetherall — *Computer Networks*, Section 6.3 (this lesson's source).
- Chiu and Jain, "Analysis of the increase and decrease algorithms for congestion avoidance in computer networks," *Computer Networks and ISDN Systems*, 1989 — the AIMD convergence proof.
- Kleinrock, "Power and deterministic rules of thumb for probabilistic problems in computer communications," *ICC 1979* — the power metric.
- Floyd and Fall, "Promoting the Use of End-to-End Congestion Control in the Internet," *IEEE/ACM ToN*, 1999 — the case for TCP-friendly congestion control.
- RFC 2581 (Allman, Paxson, Stevens, 1999) and its successor RFC 5681 (Allman, Paxson, Blanton, 2009) — TCP congestion control.
- RFC 5348 (Floyd et al., 2008) — TCP-friendly rate formula.
- Katabi, Handley, Rohrs, "Congestion Control for High Bandwidth-Delay Product Networks," *SIGCOMM 2002* — XCP, the explicit-precise corner of Fig. 6-23.
- Padhye, Firoiu, Towsley, Kurose, "A TCP-friendly Rate Adjustment Protocol for Continuous Multimedia Flows," *NOSSDAV 1998* — the Padhye throughput formula derivation.
