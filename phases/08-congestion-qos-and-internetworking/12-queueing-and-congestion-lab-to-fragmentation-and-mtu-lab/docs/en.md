# Queueing and Congestion Lab to Fragmentation and MTU Lab

> Congestion is a queueing problem: packets arrive at a router faster than the output link can drain them, so they wait in a buffer. The **M/M/1** model approximates this with Poisson arrivals at rate **λ**, exponential service at rate **μ**, and a single FIFO server, giving utilization **ρ = λ/μ**, mean occupancy **L = ρ/(1−ρ)**, and mean delay **W = 1/(μ−λ)** — **Little's law** ties them as **L = λW**. As ρ → 1 the queue and latency blow up nonlinearly: congestion collapse in queueing terms. Routers fight back with **tail-drop** (drop when full), **RED** (drop early to signal before collapse), and **ECN** (mark instead of drop). On the internetworking side, each link has a maximum packet size (**MTU**): when a datagram exceeds it, routers fragment or the sender discovers the path MTU with **PMTUD** using `ping -M do -s N` probes with the Don't-Fragment bit set. `tracepath` automates this. This lab builds an M/M/1 simulator to watch congestion form, runs MTU discovery, and traces the fragmentation offsets that result when discovery fails.

**Type:** Build
**Languages:** Python, ping, tracepath
**Prerequisites:** Phase 08 lessons 01-11 (congestion control, traffic shaping, scheduling, fragmentation)
**Time:** ~90 minutes

## Learning Objectives

- Build a discrete-event M/M/1 queue simulator and confirm that empirical queue length and wait converge to the theoretical formulas L = ρ/(1−ρ) and W = 1/(μ−λ).
- Measure how queue length and delay respond as utilization ρ climbs from 0.6 to 0.98, and identify the ρ > 0.8 knee where congestion becomes nonlinear.
- Distinguish tail-drop, RED, and ECN as buffer-management strategies and explain why dropping early can prevent congestion collapse.
- Run path MTU discovery with `ping -M do -s N` and `tracepath`, and read the resulting ICMP "Frag needed" messages.
- Observe IP fragmentation offsets, the More-Fragments flag, and reassembly when a datagram exceeds the discovered MTU.

## The Problem

A branch office reports that video calls freeze and file transfers crawl every afternoon. The link is a 100 Mbps MPLS circuit that, on paper, should handle the load. `ping` shows occasional loss; `traceroute` shows no extra hops. The NOC blames the ISP; the ISP blames the branch router.

The real cause is queue buildup at the branch router's egress interface. During peak hours aggregate traffic reaches ~92 Mbps on a 100 Mbps link — ρ ≈ 0.92. M/M/1 predicts L ≈ 0.92/(1−0.92) ≈ 11.5 packets and W ≈ 1/(100−92) ≈ 0.125 ms per packet at the queue, but real routers have finite buffers, so tail-drop kicks in and TCP backs off, ramps up, backs off — oscillation that reads as "random" loss to applications. Separately, a 4000-byte backup datagram hits a 1400-byte MPLS MTU and fragments into three pieces; if the middle fragment is dropped by the congested queue, the whole datagram is lost and TCP retransmits all 4000 bytes — amplifying the congestion. The lab untangles both: model the queue to see the congestion knee, and discover the path MTU to avoid fragmentation-induced loss amplification.

## The Concept

Two mechanisms meet at a router: **queueing** (how packets wait when the output link is busy) and **fragmentation** (how oversized packets are split when the next link's MTU is smaller). The SVG diagrams a router queue filling up and the utilization curve bending toward infinity; `code/main.py` simulates both.

### The M/M/1 queue model

The simplest useful queueing model is **M/M/1**: **M**arkovian (Poisson) arrivals, **M**arkovian (exponential) service, **1** server, infinite buffer, FIFO discipline.

| Symbol | Name | Formula |
|---|---|---|
| λ | arrival rate | packets/sec, Poisson (memoryless inter-arrivals) |
| μ | service rate | packets/sec, exponential service times |
| ρ | utilization | ρ = λ/μ; must be < 1 for stability |
| L | mean in system | L = ρ/(1−ρ) |
| Lq | mean in queue | Lq = ρ²/(1−ρ) |
| W | mean time in system | W = 1/(μ−λ) |
| Wq | mean wait in queue | Wq = λ/(μ(μ−λ)) |

The formulas only hold for ρ < 1. As ρ → 1, L and W diverge — the queue grows without bound in the idealized model; in a real router the buffer fills and drops start.

### Little's law

**L = λW** is one of the most general results in queueing theory: the average number of customers in a system equals the arrival rate times the average time spent in it. It holds for M/M/1, M/M/c, M/G/1, and most stable systems regardless of distribution. It is the bridge between "how many packets are in the router" and "how long each waits" — measure one and you know the other.

```
  arrivals λ        queue (FIFO)         server μ
  ----------->   [ ][ ][ ][ ][ ]   ----> departures
                   Lq waiting       1 in service
                   <-- L = Lq + ρ -->   W = Wq + 1/μ
```

### The congestion knee: why ρ > 0.8 hurts

The queue length L = ρ/(1−ρ) is a hyperbola. Below ρ = 0.5 the queue is short and insensitive to small load changes. Above 0.8 the curve steepens sharply:

| ρ | L (packets) | W (at μ=100) | Interpretation |
|---|---|---|---|
| 0.50 | 1.0 | 0.020 s | comfortable |
| 0.80 | 4.0 | 0.050 s | the knee |
| 0.90 | 9.0 | 0.100 s | steep |
| 0.95 | 19.0 | 0.200 s | dangerous |
| 0.99 | 99.0 | 1.000 s | near collapse |

A 5% load increase from 0.90 to 0.95 doubles the queue. This is why operators alert at ρ > 0.8 and why TCP congestion avoidance backs off long before the link saturates.

### Tail-drop, RED, and ECN

When the buffer fills, the router must drop. The choice of *when* and *how* to drop is a congestion-control mechanism in its own right.

| Strategy | Rule | Effect |
|---|---|---|
| **Tail-drop** | Drop arriving packets when the queue is full | Simple, but causes global synchronization: many TCP flows detect loss simultaneously, back off together, then ramp up together — oscillation |
| **RED** (Random Early Detection) | Drop with probability rising as the average queue length grows from min_threshold to max_threshold | Breaks synchronization; signals senders *before* the buffer fills; spreads loss across flows |
| **ECN** (Explicit Congestion Notification) | Mark the IP header CE bit instead of dropping (if both endpoints support it) | No packet loss — TCP sees the mark and halves cwnd. Requires ECN-capable sender and receiver |

**RFC 2309** argues that tail-drop is the wrong default and that active queue management (RED/ECN) is essential at high load.

### Path MTU discovery

Every link has a maximum transmission unit (MTU). Ethernet: 1500. 802.11: 2272. PPPoE: 1492. MPLS: varies. When a datagram crosses from a large-MTU link to a small-MTU link, something has to give.

**Path MTU Discovery (PMTUD)**, defined in **RFC 1191**, works as follows: the sender sets the **Don't Fragment (DF)** bit and sends progressively smaller probes. If a router cannot forward the datagram because it exceeds the next hop's MTU and DF is set, the router drops it and sends back **ICMP "Fragmentation Needed"** (type 3, code 4) carrying the next-hop MTU. The sender lowers its packet size and retries.

```
  host -----> R1(MTU=1400) -----> R2(MTU=1200) -----> R3(MTU=900) -----> dest

  probe 1500B DF=1  ->  R1 drops, ICMP "Frag Needed, next MTU=1400"
  probe 1400B DF=1  ->  R2 drops, ICMP "Frag Needed, next MTU=1200"
  probe 1200B DF=1  ->  R3 drops, ICMP "Frag Needed, next MTU=900"
  probe  900B DF=1  ->  arrives OK -> path MTU = 900
```

The command-line tools:

- `ping -M do -s N host` — sends a probe of N+28 bytes (N + 20 IP + 8 ICMP) with DF set. If it exceeds the path MTU, you get "Frag needed and DF set."
- `tracepath host` — automates PMTUD by sending increasing-size probes and reporting the path MTU.

### Fragmentation when discovery fails

If PMTUD fails — often because a firewall filters the ICMP "Frag Needed" messages — the sender keeps emitting 1500-byte datagrams that a downstream router must fragment. IP fragmentation splits the datagram at 8-byte boundaries:

| Field | Meaning |
|---|---|
| **Identification** | Same value in all fragments of one datagram |
| **More Fragments (MF)** | 1 = more fragments follow; 0 = last fragment |
| **Fragment Offset** | Position of this fragment's data in the original, in 8-byte units |

A 2000-byte payload over a 900-byte MTU yields three fragments: offset 0 (MF=1, 880B), offset 880 (MF=1, 880B), offset 1760 (MF=0, 240B). The destination reassembles by collecting all fragments with the same Identification, ordering by offset, and concatenating. **Lose any one fragment and the entire datagram is lost** — this is why fragmentation amplifies congestion loss.

### Lab procedure for measuring queue behavior

1. Run `code/main.py` to see the theoretical M/M/1 table and the discrete-event simulation converge.
2. On a real link, measure arrival rate with `tcpdump` packet counts per second; link rate from interface speed. Compute ρ.
3. Run `ping -M do -s 1472 8.8.8.8` to check if 1500-byte Ethernet MTU reaches the destination unfragmented. Reduce `-s` until it succeeds.
4. Run `tracepath 8.8.8.8` and read the "pmtu" line.
5. If fragmentation occurs, capture with `tcpdump -n host <target>` and look for multiple IP packets with the same Identification but different offsets.

## Build It

`code/main.py` ships two stdlib-only tools:

1. **M/M/1 queue simulator** — computes the theoretical metrics (ρ, L, Lq, W, Wq) for a set of (λ, μ) configurations and runs a discrete-event simulation with Poisson arrivals and exponential service. The simulation's empirical averages should track the theory, and the max queue length should grow sharply as ρ → 1. Run it to watch the congestion knee form in the numbers.
2. **MTU discovery tool** — simulates sending DF-set probes across a path with decreasing MTUs (1400 → 1200 → 900), discovers the path MTU, then fragments a 2000-byte payload at that MTU and reassembles it out of order to verify the offset logic.

Run `python3 code/main.py`, then change λ and μ to move the utilization up and down the curve, and change the path MTUs to see how fragmentation count scales.

## Use It

| Task | Command / Evidence | What Good Looks Like |
|---|---|---|
| Find path MTU (Linux) | `tracepath example.com` | Final line reports `pmtu N` — largest DF-set packet that reaches the destination |
| Find path MTU (manual) | `ping -M do -s 1472 example.com` then reduce `-s` | Largest N returning "1 packets received" without "Frag needed and DF set" |
| See fragmentation | `tcpdump -n -v host example.com` | Multiple IP packets share one Identification, different offsets, MF flag transitions 1→0 |
| Measure link utilization | `tcpdump` packet count × avg size ÷ interval ÷ link rate | ρ < 0.8: healthy; ρ > 0.9: congestion knee |
| Detect PMTUD black hole | large packets hang, small packets pass | ICMP "Frag Needed" filtered — fix the firewall or use MSS clamping |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **congestion diagnosis runbook**: how to measure λ and μ on a live link, compute ρ, and decide whether the symptom is a queueing problem.
- A **PMTUD checklist**: the `ping -M do` and `tracepath` commands, how to read ICMP "Frag Needed," and how to detect a PMTUD black hole.
- The **M/M/1 + fragmentation simulator** (`code/main.py`) tuned to your own link parameters and path.

Start from `outputs/prompt-queueing-and-congestion-lab-to-fragmentation-and-mtu-lab.md`.

## Exercises

1. Run `code/main.py` with λ=4.5, μ=5.0 (ρ=0.9). Record theoretical L and simulated average. Now change to λ=4.9 (ρ=0.98). How much does L increase? Explain the knee.
2. On your network, run `ping -M do -s 1472 8.8.8.8`. If it fails, decrease `-s` by 10 until it succeeds. What is your path MTU? Compare with `tracepath 8.8.8.8`.
3. In the simulator, set path MTUs to [1400, 1200, 900] and send a 4000-byte payload. How many fragments result? What are their offsets and MF flags? Which fragment, if dropped, loses the whole datagram?
4. Run `tcpdump -n -v -c 50 host 8.8.8.8` while pinging with `ping -s 3000 8.8.8.8` (no DF). Identify fragments by matching Identification. Record the last fragment's offset and verify it plus its length equals the original payload.
5. Compute ρ for your home link: measure upload rate over 60 seconds, divide by link speed. Is it below 0.8? If not, what would tail-drop look like in `ping`?
6. A PMTUD black hole: large HTTPS transfers hang but SSH works fine. Explain why (ICMP filtered), and name two fixes (MSS clamping, or pass ICMP type 3 code 4).

## Key Terms

| Term | What it actually means |
|---|---|
| M/M/1 | Poisson arrivals, exponential service, 1 server: L = ρ/(1−ρ), W = 1/(μ−λ) |
| Little's law | Average occupancy = arrival rate × average dwell time (L = λW); holds for nearly any stable queue |
| Utilization (ρ) | λ/μ; the single number predicting congestion. Above 0.8 the queue grows nonlinearly |
| Tail-drop | Drop arriving packets once the buffer is at capacity; causes TCP global synchronization |
| RED | Drop with rising probability as average queue grows; breaks synchronization, signals early |
| ECN | Set the IP CE bit to signal congestion without packet loss; requires ECN-capable endpoints |
| MTU | Largest payload a link will carry: Ethernet 1500, 802.11 2272, PPPoE 1492 |
| PMTUD | Send DF-set probes, listen for ICMP "Frag Needed," lower size until it passes (RFC 1191) |
| Fragment offset | Position of a fragment's data in 8-byte units from the start of the original datagram |
| MF flag | 1 = more fragments follow; 0 = last fragment |
| PMTUD black hole | ICMP "Frag Needed" filtered; sender never learns to shrink, large packets silently dropped |

## Further Reading

- **RFC 2309** — Queue Management and Congestion Avoidance (RED, ECN, why tail-drop fails).
- **RFC 1191** — Path MTU Discovery (DF-probe mechanism, ICMP "Frag Needed").
- **RFC 8201** — Path MTU Discovery for IPv6.
- Kleinrock, L., *Queueing Systems* vol. 1 — M/M/1 and Little's law.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.3, §5.5.5.