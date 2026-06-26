# Feedback-based versus rate-based flow control

> A sender that can transmit faster than its receiver can consume will overrun it, no matter how error-free the link is. **Feedback-based flow control** makes the receiver the authority: it grants the sender a finite **credit** (a window of N frames) and the sender must stop once that credit is exhausted until the receiver returns permission to continue. The classic link-layer instance is the **sliding window**, where each frame carries a sequence number and each **acknowledgement (ACK)** carries the number of the *next* frame expected (what the textbook calls `ack_expected` / `frame_expected`). **Rate-based flow control** takes the opposite stance: there is no per-frame permission, only a built-in cap on the sender's rate — a token bucket or a fixed inter-frame spacing the sender polices itself. The textbook notes that the data link layer almost always uses feedback schemes (the link is short and the receiver is one hop away), while rate-based schemes appear mainly at the transport layer. Real examples span both: HDLC (ISO 8889) and PPP (RFC 1661) use windowed feedback with 3-bit sequence numbers (window ≤ 7); TCP's sliding window is feedback-based with a 16-bit window advertisement in every segment, *layered* on top of a rate-based congestion controller (the **slow-start** and **AIMD** loop from RFC 5681) and a token-bucket policer in ATM's **ABR** service category (ITU-T I.371). The failure modes are concrete: a feedback scheme with a too-large window still overruns a slow receiver; a feedback scheme with no timer hangs forever on a lost ACK; a rate-based scheme with a too-high rate starves the receiver, and with a too-low rate wastes link bandwidth. This lesson builds a runnable sliding-window simulator next to a token-bucket governor so you can see the credit and the rate evolve against a bursty producer and a slow consumer.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Framing and the data-link service model (Phase 4 lessons on framing and DLC), error detection (CRC), the stop-and-wait protocol
**Time:** ~80 minutes

## Learning Objectives

- Distinguish feedback-based from rate-based flow control by naming the signal each one uses to slow a sender, and state where each appears in the real stack (HDLC/PPP window vs TCP window vs ATM ABR token bucket).
- Trace a sliding window of size N=4 through a send sequence, recording `frame_expected`, `ack_expected`, the available credit, and the moment the sender blocks.
- Compute, for a given propagation delay, frame size, and bandwidth, whether stop-and-wait, a window of 1, or a window of N saturates the link — and the link utilization that results.
- Explain why a lost ACK does not deadlock a windowed protocol (cumulative ACKs and retransmission timers) and why a lost data frame forces a timeout rather than a NACK.
- Model a token bucket: given bucket capacity C bytes, token rate R bytes/s, and a burst of arriving data, compute the queue backlog and the regulated output rate.
- Diagnose, from a trace, whether an observed overrun was caused by an oversized window, a missing timer, or a mis-set rate.

## The Problem

A high-throughput storage server with a 100 GbE NIC blasts snapshots to a low-power backup appliance whose single ARM core can checksum and persist about 200 Mb/s. The link itself is clean — bit error rate below 10⁻¹² — yet the backup appliance drops roughly one in twenty frames. The kernel log on the appliance shows `rx_ring_full: dropping frame`. The server, seeing no ACKs for the dropped frames, retransmits, which only makes the overrun worse: the retransmissions arrive on top of the already-saturated queue.

This is not a bit-error problem and not a congestion problem in the Internet sense. It is a *producer-consumer* mismatch on a single hop. The sender is systematically faster than the receiver. Two questions follow. First, how does the receiver tell the sender to slow down — by sending back permission (feedback), or by the sender policing its own rate (rate-based)? Second, what concrete numbers govern the answer: the window size, the ACK numbering, the retransmission timer, or the token rate and bucket depth? Get either wrong and the ring stays full and frames keep dropping. This lesson is the mechanics of getting it right.

## The Concept

### Two philosophies: permission versus pacing

The textbook states the split plainly. In **feedback-based flow control** the receiver sends back information that gives the sender permission to send more data, or at least reports the receiver's state. In **rate-based flow control** the protocol has a built-in mechanism that limits the sender's transmission rate *without* any feedback from the receiver.

| Aspect | Feedback-based | Rate-based |
|---|---|---|
| Authority | Receiver (grants credit) | Sender (paces itself) |
| Signal | ACK / window advertisement / NACK | Token rate, bucket depth, inter-frame gap |
| Reacts to receiver state? | Yes, every ACK reflects it | No, runs open-loop |
| Typical layer | Data link (HDLC, PPP) and transport (TCP) | Transport / network (ATM ABR, leaky-bucket policers) |
| Failure if mis-set | Oversized window still overruns; lost ACK hangs without timer | Too-high rate starves receiver; too-low rate wastes link |
| Latency to react | One RTT (the ACK turnaround) | None locally; none until a higher-layer signal arrives |

The textbook's reason for assigning rate-based schemes to the transport layer is structural: the link is short, the receiver is one hop away, so feedback is cheap and accurate. Across many hops, per-frame ACKs are expensive and stale by the time they return, so the transport layer combines a coarse feedback signal (TCP's window) with a rate-based congestion limb (slow-start/AIMD).

### The sliding window: sequence numbers, window, and credit

The dominant feedback scheme is the **sliding window**. The sender may have up to N outstanding (unacknowledged) frames in flight at once; N is the **window size**. Each outbound frame carries a **sequence number** drawn from a finite space of size 2ᵏ (k bits). To keep a retransmission distinguishable from a new frame, the window must satisfy **N ≤ 2ᵏ − 1**; with k = 3 the window is at most 7, which is why HDLC's default N(S)/N(R) fields are 3 bits wide.

Two pointers govern the sender and receiver:

| Variable | Side | Meaning |
|---|---|---|
| `ack_expected` | Sender | Lowest sequence number not yet acknowledged (left edge of send window) |
| `next_frame_to_send` | Sender | Next sequence number to transmit (right edge of in-flight frames) |
| `frame_expected` | Receiver | Next sequence number the receiver wants (left edge of receive window) |
| `max_seq` | Both | 2ᵏ − 1, the largest legal sequence number (wraps modulo 2ᵏ) |

The number of frames the sender may still transmit without blocking is the **available credit**: `credit = N − (next_frame_to_send − ack_expected) mod (max_seq + 1)`. When `credit` hits 0 the sender blocks. Each ACK that arrives advances `ack_expected` and restores credit. The textbook's Protocol 5 (a 1-bit sliding window) and Protocol 6 (go-back-n) are the canonical instances; `code/main.py` simulates a windowed sender against a bounded receiver queue so you can watch the credit drain and refill.

### Stop-and-wait is window = 1

The simplest feedback scheme is **stop-and-wait**: send one frame, wait for its ACK, send the next. That is a sliding window of size 1. Its fatal weakness is link utilization. On a link with bandwidth B, frame size L, and one-way propagation delay T_prop, the time to send one frame and get its ACK is `L/B + 2·T_prop`, but only `L/B` of that is actual transmission. Utilization is

```
U = (L/B) / (L/B + 2·T_prop) = 1 / (1 + 2·a),   where a = T_prop · B / L
```

Worked example: a 1 Mb/s satellite link, L = 1000 bits, T_prop = 250 ms. Then a = 10⁶ · 0.25 / 1000 = 250, so U = 1/501 ≈ 0.2%. The link sits idle 99.8% of the time. A window of N lifts utilization to roughly `N / (1 + 2a)` until it saturates at 1.0; to saturate this satellite link you need N ≥ 501. This is exactly why windowed protocols exist — to keep the pipe full while the ACK is in flight.

### Acknowledgements: cumulative, not per-frame

A windowed protocol does not ACK each frame individually. The ACK carries `frame_expected` — the *next* sequence number the receiver wants — which implicitly acknowledges everything below it. This is a **cumulative ACK**. If the receiver has cleanly received frames 0..5, it returns ACK 6 whether those frames arrived in order or were filled in by retransmission. The benefit is robustness: ACK 6 lost in transit is harmless if ACK 7 arrives later, because ACK 7 subsumes ACK 6. The cost shows up on loss: a single dropped data frame in **go-back-n** (Protocol 6) forces the receiver to discard every subsequent frame until the missing one is retransmitted, because the receive window accepts only `frame_expected`. **Selective repeat** (Protocol 7) relaxes this by buffering out-of-order frames, trading receiver memory for fewer retransmissions — its window constraint tightens to `N ≤ 2ᵏ/2` because both sender and receiver windows must not overlap across the wrap.

### Timers: the cure for the lost-ACK deadlock

The textbook is explicit: a protocol in which the sender transmits a frame and waits for an ACK will hang forever if either the frame or the ACK is lost. The fix is a **retransmission timer** started when a frame is sent. If the timer expires before the ACK returns, the frame is resent. Setting the timer is a real engineering problem: too short and you retransmit frames whose ACKs are merely delayed (creating duplicates that the sequence numbers must suppress); too long and a loss stalls the window for the whole timeout. The timer should be set to an estimate of the RTT plus a safety margin — the same idea TCP refines with SRTT/RTTVAR (RFC 6298). `code/main.py` models a per-frame timer so you can observe a lost-ACK recovery and the duplicate-suppression at the receiver.

### Rate-based control: the token bucket

When the textbook turns to rate-based schemes it notes they appear at the transport layer. The cleanest model is the **token bucket** (ITU-T I.371, also RFC 3290 for diffserv). A bucket of capacity **C** (bytes or frames) fills with tokens at rate **R** (bytes/s or frames/s); a sender may transmit a frame only if enough tokens are present, and it consumes them as it sends. Tokens in excess of C spill and are lost.

| Parameter | Meaning | Effect if too large / too small |
|---|---|---|
| R | Token generation rate | Steady-state send rate; too high overruns, too low starves |
| C | Bucket capacity | Largest burst that can be sent at full link speed; too large lets a burst swamp the receiver, too small clips legitimate bursts |

The regulated output over a long interval is exactly R, but a burst of up to C can be emitted at the peak link rate as long as the bucket holds tokens. Worked example: R = 200 Mb/s, C = 1 MB, link = 1 Gb/s. A 1 MB burst drains the bucket in 8 ms at 1 Gb/s; thereafter the sender is paced at 200 Mb/s until the bucket refills (which takes 1 MB / 200 Mb/s = 40 ms). A receiver that can sustain 200 Mb/s but cannot absorb a 1 GB spike is protected — provided C is sized to the receiver's queue, not to the sender's eagerness. The ATM **Available Bit Rate (ABR)** service category uses exactly this: the network returns **resource management (RM) cells** that adjust the sender's allowed cell rate (ACR) between a minimum (MCR) and peak (PCR), which is a feedback signal *driving* a rate-based governor — a hybrid the textbook's clean split understates.

### Why the link layer picked feedback, and when it breaks

The textbook's closing observation is that modern link hardware runs at **wire speed**: a NIC can move frames off the wire into host memory as fast as they arrive, so link-layer overruns are rare and flow control is pushed up to the transport layer. The implication for an engineer is that a `rx_ring_full` drop on a modern NIC is usually *not* a link-layer flow-control failure — the link layer already has pause frames (IEEE 802.3x) and large ring buffers — but a transport-layer window or application read-rate failure. Knowing which layer owns the overrun is the diagnosis skill; `code/main.py` lets you induce both (oversized feedback window vs. under-set token rate) and compare the traces. See `assets/feedback-vs-rate-based-flow-control.svg` for the side-by-side timing diagram of a windowed sender blocking on credit and a token-bucket sender blocking on tokens.

## Build It

1. Read `code/main.py`. It contains three models: `SlidingWindowSender` (tracks `ack_expected`, `next_frame_to_send`, `credit`, per-frame timers), `Receiver` (a bounded queue that accepts only `frame_expected` and emits cumulative ACKs), and `TokenBucket` (consumes tokens at R, refills to capacity C).
2. Run it: `python3 code/main.py`. The demo drives the windowed sender against a slow receiver that drains one frame per tick and prints, per tick, the in-flight count, the credit, and any blocked sends — then runs the token bucket against a bursty producer and prints the regulated output rate and the backlog.
3. Induce a lost ACK: set `loss_positions = {6}` in the demo and rerun. Confirm the timer fires, the frame is retransmitted, and the receiver's duplicate suppression (sequence-number check) drops the copy.
4. Overrun the receiver: raise the window to N = 8 against a receiver queue of 2 and watch the drop count climb. This is the "oversized window" failure.
5. Under-set the token rate: lower R below the producer's long-run rate and watch the bucket backlog grow without bound — the rate-based analogue of an overrun.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the window blocks the sender | `credit == 0` line in the trace when N frames are in flight, sender stops emitting | Sender resumes exactly when an ACK advances `ack_expected`, not before |
| Verify cumulative ACK behavior | A single ACK advances `ack_expected` by more than 1 after a gap is filled | Lost ACKs that are subsumed by a later ACK cause no retransmission |
| Recover from a lost data frame | Timer expiry logged, retransmit of the missing seq, receiver drops the duplicate | No frame is delivered twice to the upper layer |
| Size a window for a link | Computed N ≥ ⌈1 + 2a⌉ matches the utilization reaching ~1.0 | Stop-and-wait U on a satellite link ≈ 0.2%; windowed U ≈ 1.0 |
| Tune a token bucket | Regulated output == R over long intervals; peak burst ≤ C | A burst within C passes at line rate; a sustained over-rate is clipped to R |
| Diagnose a real overrun | Drop counter rises with window size (feedback) or with rate above receiver drain (rate) | You can name which layer's parameter is wrong, not just "it's slow" |

## Ship It

Produce one artifact under `outputs/prompt-feedback-vs-rate-based-flow-control.md`:

- A trace from `code/main.py` for a window of N = 4 against a receiver that drains one frame per tick, annotated with the tick at which the sender first blocks and the tick at which it resumes.
- A token-bucket sizing worksheet: given a receiver drain rate and a producer burst profile, the chosen R and C and the resulting peak backlog.
- A one-paragraph diagnosis rule: "if drops rise with window size, fix the feedback layer; if drops rise with token rate above the receiver drain, fix the rate."

Start from the printed output of `code/main.py` and annotate it with the failure mode you induced.

## Exercises

1. On a 10 Mb/s link with 100 ms one-way propagation and 4000-bit frames, compute the link utilization under stop-and-wait, then the minimum window size N to reach 95% utilization. Show the value of `a` and the formula.
2. In a sliding window with k = 3 sequence-number bits, explain why the maximum window is 7 for go-back-n but only 4 for selective repeat. Draw the overlap that would occur at N = 5 under selective repeat and show how a retransmission becomes indistinguishable from a new frame.
3. A receiver advertises a window of 8 but its application read loop stalls for 5 ticks. Trace the sender's `credit` over those 5 ticks and predict how many frames are buffered at the receiver when the application resumes. Which layer's parameter should the engineer change?
4. Modify `code/main.py` to model a lost ACK (not a lost data frame). Show that the next cumulative ACK subsumes the lost one and that no timer fires. Now make two consecutive ACKs vanish — at what point does the timer fire and why?
5. A token bucket has R = 50 Mb/s, C = 2 Mb, on a 1 Gb/s link. A producer sends a 5 Mb burst. Compute the time to drain the burst, the regulated output rate after the burst, and the backlog at the instant the bucket empties. Is the receiver (drain 50 Mb/s, queue 1 Mb) safe?
6. The textbook says modern NICs run at "wire speed" so link-layer flow control is rarely the culprit. Give one symptom that would point you *away* from a transport-layer window problem and toward an 802.3x PAUSE / ring-buffer issue at the link layer, and the evidence you would collect to confirm it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Feedback-based flow control | "the receiver says stop" | The receiver grants finite credit (a window); the sender blocks when credit is exhausted and resumes only on an ACK |
| Rate-based flow control | "the sender paces itself" | The sender polices its own rate with a token bucket / inter-frame gap, open-loop, no per-frame permission |
| Sliding window | "a window of N" | A feedback scheme letting up to N unacknowledged frames be in flight; bounded by `N ≤ 2ᵏ − 1` for k-bit sequence numbers |
| Credit | "how many more I can send" | `N − (in-flight)`; the number of frames the sender may still transmit before blocking |
| `frame_expected` | "the ACK number" | The next sequence number the receiver wants; returning it cumulatively acknowledges everything below |
| `ack_expected` | "the send pointer" | The left edge of the sender's window; the lowest unacknowledged sequence number |
| Cumulative ACK | "one ACK for many" | An ACK carrying `frame_expected` acknowledges all frames below it; a later ACK subsumes a lost earlier one |
| Go-back-n vs selective repeat | "retransmit styles" | Go-back-n discards out-of-order frames and forces retransmission from the gap; selective repeat buffers them, trading memory for fewer retransmissions and a tighter window bound |
| Token bucket | "a leaky pace" | A bucket of capacity C filled at rate R; sending consumes tokens; bounds sustained rate to R and burst to C |
| Wire speed | "the NIC keeps up" | Link hardware drains the line into host memory as fast as frames arrive, so overruns are a higher-layer, not link-layer, problem |
| 802.3x PAUSE | "Ethernet flow control" | A link-layer feedback frame that asks the peer to stop transmitting for a time; a feedback mechanism living below the sliding window |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 3.1.4 (Flow Control) and the Protocol 5/6/7 analyses later in Chapter 3.
- **RFC 1661** — The Point-to-Point Protocol (PPP), whose LCP negotiates the link-layer window.
- **ISO 8889** / **ISO/IEC 13239** — HDLC, defining the 3-bit N(S)/N(R) sequence-number fields and the window of 7.
- **IEEE 802.3x** — MAC Control PAUSE frames, the Ethernet-level feedback flow-control mechanism.
- **RFC 5681** — TCP Congestion Control, where a rate-based AIMD limb is layered under a feedback window.
- **RFC 6298** — Computing TCP's Retransmission Timer (SRTT/RTTVAR), the timer discipline a windowed protocol needs.
- **RFC 3290** — A DiffServ Model for Token Bucket policers (rate-based shaping at the network edge).
- **ITU-T I.371** — Traffic control and congestion control in B-ISDN (ATM), defining the ABR token-bucket / RM-cell hybrid.
- Kurose & Ross, *Computer Networking*, 8th ed., Sections 3.5–3.7, on TCP flow control versus congestion control.
