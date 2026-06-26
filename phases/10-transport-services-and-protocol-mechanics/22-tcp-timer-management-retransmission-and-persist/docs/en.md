# TCP Timer Management: Retransmission, Persist, and Keepalive

> TCP keeps the network honest with a small family of timers, each tuned to a specific failure mode. The **retransmission timer** guards every unacked segment and uses Jacobson's algorithm (RFC 6298, formalized from RFC 2988) to set `RTO = SRTT + 4 × RTTVAR`, where `SRTT = (1 − α) × R + α × SRTT` (α = 1/8) is an exponentially-weighted moving average of the round-trip time `R`, and `RTTVAR = (1 − β) × |SRTT − R| + β × RTTVAR` (β = 1/4) is its mean absolute deviation. The RTO is floored at 1 second to avoid spurious retransmits during transient congestion. When a retransmission itself times out, **Karn's algorithm** (RFC 6298 §5) forbids RTT sampling from retransmitted segments (the ack could be for either copy) and doubles the RTO each time, capping at 64 s. The **persist timer** wakes the sender when the receiver advertises a zero window — at exponentially growing intervals the sender injects 1-byte window probes. The **keepalive timer** fires after hours of idleness to verify the peer is still alive (controversial; many middleboxes drop silent flows). Finally, the **2 × MSL TIME_WAIT timer** from lesson 20 absorbs delayed duplicates. This lesson implements all four in stdlib Python and walks Jacobson's EWMA step by step.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Lessons 17–21, basic statistics (EWMA), ability to read RTT samples from a capture
**Time:** ~80 minutes

## Learning Objectives

- Compute `RTO` from a series of RTT samples using Jacobson's algorithm (`α = 1/8`, `β = 1/4`, `RTO = SRTT + 4 × RTTVAR`) and explain why the variance term prevents spurious retransmits.
- Implement Karn's algorithm: skip RTT sampling for retransmitted segments and double the RTO on each timeout (exponential backoff capped at 64 s).
- Distinguish the four TCP timers — retransmission, persist, keepalive, and 2 × MSL — by which failure they defend against.
- Walk the persist-timer schedule (5 s, 10 s, 20 s, …, 60 s) and explain why a window probe is the only way to break a zero-window deadlock.
- Decide whether to enable TCP keepalive for a given application and explain why the default 2-hour idle is usually too long.
- Trace the kernel's choice between fast retransmit (after 3 duplicate acks, RFC 5681) and timeout-based retransmit, and explain why fast retransmit is preferred when loss is single-packet.

## The Problem

You are debugging a file transfer that stalls for several seconds every time the network drops a single packet. The logs show retransmissions, then long pauses, then successful delivery. The throughput is awful on lossy links. The kernel retransmission timer looks "right" but it is firing too late on the first loss and too aggressively on subsequent losses.

The deeper problem is that round-trip times on a real network are not constant — they cluster around a mean with a heavy tail when queues build up. A timer set to `2 × RTT` (the original 1981 rule) does not respond to that variance, so it either fires too soon (congesting the network with useless retransmits) or too late (delaying recovery). Jacobson's contribution was to add a variance term that adapts in real time.

## The Concept

### The retransmission timer (RFC 6298)

Jacobson's algorithm maintains two smoothed quantities:

```
R  = measured RTT for the just-acked segment
SRTT_new   = (1 − α) × R + α × SRTT_old           where α = 1/8
RTTVAR_new = (1 − β) × |SRTT − R| + β × RTTVAR_old where β = 1/4
RTO = SRTT + max(G, 4 × RTTVAR)                  where G is the clock granularity
RTO is floored at 1 second.
```

Worked example with `α = 1/8`, `β = 1/4`, initial `SRTT = 1.0`, `RTTVAR = 0`:

| Sample R | SRTT | RTTVAR | RTO |
|---|---|---|---|
| 0.500 s | 0.9375 | 0.1250 | 1.4375 → 1.44 s |
| 0.600 s | 0.8918 | 0.1562 | 1.5168 → 1.52 s |
| 0.450 s | 0.8423 | 0.1714 | 1.5279 → 1.53 s |
| 0.500 s | 0.8068 | 0.1812 | 1.5317 → 1.53 s |

The RTO adapts to the recent history in roughly 8 samples (because α = 1/8) and tracks the variance closely enough to avoid spurious retransmits.

### Karn's algorithm (RFC 6298 §5)

When a retransmission timer fires, the sender retransmits the segment and doubles the RTO. If the ack arrives, **the sender cannot tell whether the ack is for the original transmission or the retransmission** — and using it as an RTT sample would corrupt SRTT and RTTVAR. Karn's fix:

1. Do **not** update `SRTT` or `RTTVAR` based on any segment that has been retransmitted.
2. Double the RTO on each retransmission, capped at 64 s.
3. Reset the RTO back to its Jacobson value when a non-retransmitted segment is finally acked.

This is what `net.ipv4.tcp_retries2` (default 15) controls: after that many timeouts the kernel gives up and returns `ETIMEDOUT` to the application.

### Fast retransmit vs. timeout-based retransmit (RFC 5681)

A timeout is expensive — minimum 1 second, often more — so TCP has a faster path. When the receiver gets an out-of-order segment, it immediately sends a **duplicate ack** carrying the same acknowledgement number. Three duplicate acks in a row (RFC 5681 §3.2) indicate that **one packet was lost but later packets arrived**. The sender retransmits immediately without waiting for the timer. This is **fast retransmit**.

After fast retransmit, RFC 5681 also specifies **fast recovery**: the sender halves the congestion window (the slow-start threshold becomes `cwnd / 2`) and continues with congestion avoidance rather than dropping all the way back to slow start. This is what distinguishes **TCP Reno** (fast retransmit + fast recovery) from the older **TCP Tahoe** (drops to slow start on any loss).

### The persist timer

When the receiver advertises a zero window, the sender cannot send data. But if the eventual window-update segment is lost, both sides wait forever. The **persist timer** breaks the deadlock by injecting 1-byte probes at exponentially increasing intervals. RFC 793 / Linux default schedule:

```
5 s, 10 s, 20 s, 40 s, 60 s, 60 s, 60 s, ...
```

The probe forces the receiver to re-announce its window. Modern implementations switch the probe to 0 bytes once enough time has passed (zero-byte probe per RFC 793), then back to 1 byte on the next round.

### The keepalive timer

After a connection has been idle for `tcp_keepalive_time` seconds (default 7,200 s = 2 hours on Linux), the sender transmits a **keepalive probe** — a segment with `SEQ = SND.NXT − 1` and no data, which the receiver responds to with an ACK. If no response arrives within `tcp_keepalive_intvl` seconds (default 75 s), another probe is sent. After `tcp_keepalive_probes` unsuccessful probes (default 9), the connection is terminated with `ETIMEDOUT`.

Keepalive is controversial: it adds traffic, can terminate an otherwise-healthy connection through a transient NAT/firewall glitch, and is often better handled at the application layer (a custom heartbeat message). However, it is the only way to free resources held by a peer that crashed silently without sending FIN.

### Initial RTO and clock granularity

RFC 6298 specifies:

- Initial `SRTT = 0` (undefined); set on the first RTT sample.
- Initial `RTTVAR = 0`; set on the first RTT sample.
- First RTO = `min(1 s, 3 × SRTT_initial_guess)` where `SRTT_initial_guess = max(first_R, 1 tick)`. In practice Linux uses 1 second for the very first SYN.
- Minimum RTO = 1 second.
- Maximum RTO = 60 s (RFC 6298; some implementations use 120 s).

### Putting it together: the timeline of a lossy transfer

```
t=0     sender transmits segment 5 (SEQ 4001, len 1000)
t=R     segment 5 lost in the network
t=R+10  receiver gets segment 6 (SEQ 5001) -> sends dup-ack 4001
t=R+11  receiver gets segment 7 (SEQ 6001) -> sends dup-ack 4001
t=R+12  receiver gets segment 8 (SEQ 7001) -> sends dup-ack 4001
t=R+12  sender receives third dup-ack -> FAST RETRANSMIT of segment 5
        sender halves cwnd (ssthresh = cwnd/2), enters fast recovery
t=R+12  sender retransmits segment 5
t=R+12+R receiver acks segment 8 -> fast recovery ends, congestion avoidance resumes
```

If no dup-acks arrive (the very first segment is lost, or all subsequent segments are also lost), the retransmission timer eventually fires and the kernel falls back to timeout-based retransmit with exponential backoff.

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/22-tcp-timer-management-retransmission-and-persist
python3 code/main.py
```

The script:

1. Walks Jacobson's algorithm step-by-step for an RTT sample series.
2. Implements Karn's backoff: a retransmission doubles the RTO up to 64 s and skips RTT sampling for retransmitted segments.
3. Prints the persist-timer schedule (5 s, 10 s, 20 s, …).
4. Computes the keepalive deadline: `tcp_keepalive_time + tcp_keepalive_intvl * tcp_keepalive_probes` with Linux defaults.
5. Simulates a fast-retransmit sequence with three duplicate acks and a successful retransmit.

Use `jacobson_step()`, `karn_backoff()`, and `fast_retransmit_simulator()` to plug in your own samples.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| RTO adapts to RTT variance | `jacson_step(...)` prints the new SRTT, RTTVAR, RTO | `ss -ti` shows `rto:` on a socket |
| Karn's backoff schedule | `karn_backoff(...)` prints the doubled RTOs | `ss -ti` after a timeout |
| Fast retransmit fires after 3 dup-acks | `fast_retransmit_simulator()` walks the sequence | Wireshark `[TCP Fast Retransmission]` |
| Persist timer probes | `persist_schedule()` prints the probe times | `tcpdump` shows 1-byte segments at increasing intervals |
| Keepalive deadline | `keepalive_deadline()` returns seconds | `cat /proc/sys/net/ipv4/tcp_keepalive_time` |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable Jacobson-algorithm worksheet with cells for `R`, `SRTT`, `RTTVAR`, and `RTO`.
- A reference implementation of the four TCP timers in your language, with Karn's algorithm as a parameter.

Start from [`outputs/prompt-tcp-timer-management-retransmission-and-persist.md`](../outputs/prompt-tcp-timer-management-retransmission-and-persist.md).

## Exercises

1. Initial `SRTT = 1.0`, `RTTVAR = 0.1`. The next RTT sample is `R = 0.6`. Compute the new SRTT, RTTVAR, and RTO.
2. The RTO is 1.5 s and the retransmission timer fires. After how many timeouts does the RTO reach its 64 s cap, and at what total elapsed time?
3. Why does Karn's algorithm forbid RTT sampling for retransmitted segments? What would happen if the kernel sampled both copies?
4. Three duplicate acks arrive back-to-back at `t = 1.20 s, 1.21 s, 1.22 s`. Show the sender's actions and the value of `ssthresh` if `cwnd = 20 KB` and MSS = 1 KB.
5. The receiver advertises `WIN = 0`. Show the persistence-timer probes a sender will emit and at what times.
6. A connection is idle for 3 hours and the peer has crashed silently without sending FIN. With Linux defaults, how many seconds pass before the local kernel declares the connection dead?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| RTO | "retransmission timeout" | `SRTT + 4 × RTTVAR`, floored at 1 s, capped at 60 s |
| SRTT | "smoothed RTT" | EWMA of RTT samples with α = 1/8 |
| RTTVAR | "RTT variation" | EWMA of `|SRTT − R|` with β = 1/4 |
| Karn's algorithm | "skip retransmitted RTT" | Do not update SRTT from retransmitted segments; double RTO on each timeout |
| Fast retransmit | "retransmit on 3 dup-acks" | RFC 5681: 3 duplicate acks imply single-packet loss; retransmit immediately |
| Fast recovery | "halve cwnd, keep going" | After fast retransmit, drop cwnd to ssthresh=cwnd/2 and stay in congestion avoidance |
| Persist timer | "zero-window probe" | Timer that fires 1-byte window probes when WIN=0 |
| Keepalive timer | "is the peer alive?" | Long-idle probe to detect a silently crashed peer |
| TIME_WAIT timer | "2 × MSL" | From lesson 20 — absorbs delayed duplicates and lost final ACKs |

## Further Reading

- RFC 6298 — Computing TCP's Retransmission Timer (formalizes Jacobson's algorithm)
- RFC 2988 — Computing TCP's Retransmission Timer (superseded by RFC 6298 but still cited)
- RFC 5681 — TCP Congestion Control (defines fast retransmit and fast recovery)
- Jacobson, 1988 — *Congestion Avoidance and Control* (the original SRTT / RTTVAR paper)
- Karn & Partridge, 1987 — *Improving Round-Trip Time Estimates in Reliable Transport Protocols* (Karn's algorithm)
- RFC 793 — Transmission Control Protocol (persist timer, keepalive timer)
- Stevens, *TCP/IP Illustrated, Volume 1*, 2nd ed. — Chapter 21, TCP timers
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP timer management
- `tcp(7)` man page — `tcp_retries2`, `tcp_keepalive_time`, `tcp_keepalive_intvl`, `tcp_keepalive_probes`