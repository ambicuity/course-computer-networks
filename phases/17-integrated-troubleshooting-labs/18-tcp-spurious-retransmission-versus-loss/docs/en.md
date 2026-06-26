# TCP Spurious Retransmission versus Genuine Loss Differential

> A capture from a 1 Gbps intra-datacenter link shows `tcp.analysis.retransmission` flags on 0.3% of segments, all clustered on the same source port, all on a single direction of the conversation, and all within a 200 ms window. The retransmissions match the original segments byte-for-byte (same SEQ, same payload, same IP id), but the ACK for the original arrived 1.4 ms after the retransmit was sent. The operator initially concluded "packet loss on the path" and rerouted the flow. The capture actually showed **spurious retransmissions** triggered by the sender's RTO firing 200 ms after the original transmission — but the original was not lost, it was delayed by an ECMP re-convergence in the leaf-spine fabric. The duplicate ACKs that the receiver would have sent never appeared because the segment was not actually missing; the sender's RTO was simply too aggressive for the link's tail latency. Wireshark distinguishes the two with the `tcp.analysis.spurious_retransmission` expert info, which fires when a retransmitted segment's ACK is observed for the *original* segment after the retransmit was sent — proof that the original was not lost, only late. The differential between genuine loss and spurious retransmission is: in genuine loss, you see three or more duplicate ACKs (RFC 5681 fast retransmit) OR a full RTO expires; in spurious retransmission, the original ACK arrives after the retransmit, and there are no duplicate ACKs. The fix is to enable TCP RACK (RFC 8985) or to raise `tcp_retries2` so the kernel does not give up so easily; the wrong fix is to chase a phantom network problem.

**Type:** Lab
**Languages:** Python, Wireshark, tcpdump
**Prerequisites:** Phase 11 TCP retransmission and fast recovery, the SACK extension (RFC 2018), the RACK-TLP scheme (RFC 8985, RFC 8982)
**Time:** ~100 minutes

## Learning Objectives

- Diagnose a TCP capture that shows retransmissions and decide whether each is *genuine* (the segment was lost) or *spurious* (the segment was delayed, the ACK for the original arrived after the retransmit) using Wireshark's expert info.
- Compute the RTO budget: initial RTO is 1s per RFC 6298, then doubles on each retransmission, capped by `tcp_retries2` (default 15 on Linux). Read the retransmit timestamps and verify the exponential backoff.
- Distinguish fast retransmit (triggered by 3 duplicate ACKs, RFC 5681) from RTO-based retransmit (timer-driven). The first is a recovery, the second is a fall-back; their signatures in the capture are different.
- Apply the `tcp.analysis.spurious_retransmission` display filter, and read the original segment's ACK to confirm the spurious verdict.
- Build a Python parser that reads a CSV-exported Wireshark trace, classifies each retransmission event, and prints the spurious/loss verdict per direction.
- Recommend the right fix: RACK (RFC 8985) for low-loss fabrics, larger `tcp_retries2` for lossy long-fat links, ECN marking or CoDel for chronic shallow-buffer drops.

## The Problem

The on-call SRE sees a PagerDuty alert: "TCP retransmission rate > 0.1% on `service-checkout`." The alert was tuned for a real loss signal and is now firing on a benign artifact. The flow is between two services in the same region, on a 1 Gbps link through a leaf-spine fabric. The capture shows 0.3% retransmission, all in one direction, all on the same source port, all in bursts that last under 200 ms. The kernel's `ss -ti` for the source socket shows `cwnd:42` (no congestion window collapse), `rtt:0.4/0.6` (RTT/sRTT smooth and variance), `retrans:3` (three retransmissions in the trace), and `backoff:0` (the RTO has not yet doubled).

The clue that this is *spurious* is in the timing: each retransmit is sent exactly 200 ms after the original, and the ACK for the original arrives 1-3 ms *after* the retransmit was sent. The original was not lost — it was queued in a switch that was undergoing ECMP re-convergence (the leaf was updating its forwarding table for a new path), and the original segment sat in the switch's output buffer for 200 ms. By the time it was forwarded, the sender had already retransmitted. From the sender's perspective, the RTO was 200 ms; from the path's perspective, the segment was delayed but never lost.

The Wireshark display filter that catches this is `tcp.analysis.spurious_retransmission`. The expert info summary (`Analyze > Expert Information > Notes`) lists every such event with a `Note` severity, and the right column says "Retransmission of an already-acked segment." That is the smoking gun: a retransmitted segment whose original ACK arrived after the retransmit.

The differential is simple. In *genuine* loss you see one of two patterns:

- **Fast retransmit:** three duplicate ACKs (same ACK number, no payload) arrive from the receiver, then the sender retransmits before the RTO fires. The retransmit lands at the receiver, the receiver ACKs the recovered segment, and the flow continues. The retransmit's ACK is *not* a duplicate of an earlier ACK.
- **RTO-based retransmit:** the sender's RTO fires (1s, 2s, 4s, 8s — exponential backoff per RFC 6298), the sender retransmits, the receiver ACKs. There are no duplicate ACKs. The retransmit's ACK is the first ACK for that segment.

In *spurious* retransmission, the sender's RTO fires, the sender retransmits, and *then* the ACK for the original arrives. The retransmit's payload duplicates already-acked data. Wireshark notes this and the receiver, on seeing the duplicate, sends a duplicate ACK (the "spurious retransmission" is harmless to the receiver, because the data was already delivered and ACKed).

## The Concept

### The RTO state machine (RFC 6298)

The retransmission timer is set to `SRTT + 4*RTTVAR` after every ACK that advances the send window, where `SRTT` is the smoothed RTT (RFC 6298 §2.2) and `RTTVAR` is the RTT variance. The first RTO when no measurement is available is 1 second. On a retransmit, the RTO doubles (exponential backoff) and the next measurement resets SRTT. The cap on retries is `tcp_retries2` (default 15 on Linux = 924 s of attempts before the kernel gives up).

A 200 ms RTO is *not* the RFC 6298 default. The sender has `tcp_sack=1` and `tcp_timestamps=1` enabled (so it can do RACK and TLP), and the RTT is 0.4 ms — the kernel's `tcp_rto_min` is the floor, and a low `tcp_rto_min` (e.g. 10 ms) is sometimes set to speed recovery on a low-latency fabric. On a 0.4 ms RTT link, 200 ms is 500 RTTs, which is a very conservative floor. A typical mistake is to lower `tcp_rto_min` to "feel snappier" on a low-latency link; the side effect is spurious retransmits when the link's tail latency briefly exceeds the floor.

### The fast retransmit threshold (RFC 5681)

A sender that receives 3 duplicate ACKs (4 ACKs carrying the same ACK number) retransmits the missing segment without waiting for the RTO. This is "fast retransmit." The threshold of 3 was a compromise between "react too early on a reordering artifact" and "react too late on real loss." Modern kernels also implement RACK (RFC 8985) which uses the *timestamp* of the most recently delivered segment to decide whether a gap is loss or reorder. RACK is strictly better at distinguishing the two, and it is the right knob to enable on a low-loss fabric.

### Spurious retransmission detection

The sender can detect a spurious retransmit in two ways:

- **DSACK** (RFC 2883): the receiver, on seeing a retransmitted segment whose data was already ACKed, sends a duplicate ACK with the SACK block pointing at the *original* segment. The sender sees the DSACK block, knows the retransmit was unnecessary, and can undo the congestion window reduction (undo `cwnd = ssthresh`).
- **RACK timeout**: the sender uses the most recently delivered segment's timestamp + a reordering window to decide whether the outstanding segment is lost or just delayed. If the ACK for the original arrives before the RACK timeout, no retransmit; if after, retransmit.

The right fix for a fabric that has occasional reordering or 100 ms-scale jitter is to enable RACK and DSACK. The wrong fix is to raise `tcp_retries2` to "be more patient" — that does not address the spurious retransmit, only the kernel giving up too soon.

### How Wireshark classifies the events

The display filter `tcp.analysis.retransmission` selects all retransmissions. The filter `tcp.analysis.fast_retransmission` selects only the fast-retransmit variants. The filter `tcp.analysis.spurious_retransmission` selects only the spurious variants (those where the ACK for the original arrived after the retransmit was sent). The filter `tcp.analysis.retransmission && !tcp.analysis.spurious_retransmission && !tcp.analysis.fast_retransmission` selects the RTO-based but non-spurious retransmits — the genuine loss.

### Reading the SEQ/ACK numbers

The diagnostic discipline:

1. Find a retransmit (`tcp.analysis.retransmission`).
2. Note the SEQ number, the original segment's timestamp, the retransmit's timestamp.
3. Search for an ACK of the same SEQ + payload length. If the ACK timestamp is *after* the retransmit's timestamp, the retransmit was spurious.
4. Count duplicate ACKs before the retransmit. If 3+ dup-ACKs and the retransmit is fast retransmit, the loss was real.

### How the simulator models this

`code/main.py` reads a synthetic CSV of TCP events (SEQ, ACK, flags, timestamp, expert info) and classifies each retransmission. It does not parse a live pcap. The output is a per-direction breakdown: how many retransmits, how many spurious, how many fast, how many RTO-based. This is the same breakdown `ss -ti` shows, but per-packet and per-flow.

## Build It

1. **Capture a retransmit burst.** `tcpdump -i eth0 -w retrans.pcap tcp and host 10.0.0.5`. Run an `iperf3` for 60 seconds, then stop.
2. **Open in Wireshark.** Filter on `tcp.analysis.retransmission`. Note the SEQ, the original timestamp, the retransmit timestamp.
3. **Search for the ACK.** Use `tcp.seq == <SEQ>` to find the original segment and the ACK that covered it. Confirm the ACK timestamp is *after* the retransmit.
4. **Run the simulator.** `python3 code/main.py --input trace.csv` (or use the built-in sample) should produce a per-direction breakdown.
5. **Ship the runbook.** A one-page runbook that maps each `tcp.analysis.*` filter to the action it implies.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm spurious retransmit | `tcp.analysis.spurious_retransmission` + ACK-for-original-after-retransmit | Retransmit was unnecessary; no cwnd reduction needed |
| Confirm fast retransmit | `tcp.analysis.fast_retransmission` + 3 duplicate ACKs | Genuine single-packet loss, RFC 5681 recovery |
| Confirm RTO-based loss | `tcp.analysis.retransmission` + 200/400/800 ms spacing | Genuine loss with exponential backoff |
| Verify DSACK | `tcp.analysis.duplicate_ack` with SACK block pointing at original | Receiver detected the duplicate; cwnd undo possible |
| Verify RACK | `tcp.analysis.rack_retransmission` (newer Wireshark) | Timestamp-based loss detection; no spurious retransmits |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **TCP retransmission classification runbook** mapping each Wireshark expert info flag to the action it implies.
- A **before/after capture** of the same flow with and without RACK enabled, showing the spurious retransmits disappear.

Start from `outputs/prompt-tcp-spurious-retransmission-versus-loss.md`.

## Exercises

1. A capture shows three duplicate ACKs at `t=0.500s, 0.512s, 0.520s`, then a retransmit at `t=0.532s`. The original SEQ was 1,000,000, payload 1,400 bytes. Classify the retransmit and explain which RFC defines the threshold.
2. The sender's RTO is 200 ms, then 400 ms, then 800 ms after three retransmits. Compute the kernel's expected wait at the 5th retransmit. Is this RFC 6298-compliant?
3. A spurious retransmit is detected via DSACK. What congestion window state does the kernel restore? Cite the specific sysctl.
4. A capture shows `tcp.analysis.retransmission` but `tcp.analysis.spurious_retransmission` is empty and `tcp.analysis.fast_retransmission` is empty. What kind of retransmission is this, and what evidence should you look for to confirm?
5. The RTT is 0.4 ms and the kernel's `tcp_rto_min` is 200 ms. A fabric re-convergence event delays one segment by 220 ms. Will a retransmit be triggered? Justify with the RTO computation.
6. After enabling RACK, the spurious retransmits disappear. Which sysctl did you change, and what is the difference between RACK and the RFC 6298 timer-based scheme?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Spurious retransmission | "Phantom loss" | A retransmit whose original ACK arrives after the retransmit was sent; the original was delayed, not lost |
| Fast retransmit | "3 dup-ACKs" | RFC 5681: retransmit triggered by 3 duplicate ACKs before the RTO fires |
| RTO | "Retransmit timer" | RFC 6298: `SRTT + 4*RTTVAR`, with exponential backoff on each retransmit |
| RACK | "Timestamp loss detection" | RFC 8985: loss detection based on the most recently delivered segment's timestamp, not just dup-ACKs |
| DSACK | "Duplicate SACK" | RFC 2883: receiver reports the duplicate via a SACK block, allowing the sender to undo cwnd reduction |
| TLP | "Tail Loss Probe" | RFC 8982: a probe sent at `2*RTT` after the last ACK to detect tail loss without waiting for the RTO |
| `tcp_retries2` | "Give-up count" | Linux sysctl: how many times the RTO can fire before the kernel gives up; default 15 |
| `tcp_rto_min` | "RTO floor" | Linux sysctl: minimum RTO; lowering this can cause spurious retransmits on a low-latency link |

## Further Reading

- RFC 5681 — TCP Congestion Control (fast retransmit threshold, dup-ACK definition)
- RFC 6298 — Computing TCP's Retransmission Timer (initial RTO 1s, exponential backoff, karn's algorithm)
- RFC 8985 — The RACK Loss Detection Algorithm (timestamp-based loss detection)
- RFC 8982 — TLP (Tail Loss Probe)
- RFC 2883 — DSACK (Duplicate SACK)
- RFC 2018 — TCP Selective Acknowledgment Options
- Wireshark — TCP Analysis flags reference (`tcp.analysis.*`)
- `tcp(7)` man page — `tcp_retries2`, `tcp_rto_min`, `tcp_sack`, `tcp_timestamps` sysctls
