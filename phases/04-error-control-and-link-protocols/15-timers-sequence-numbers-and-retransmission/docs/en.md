# Timers, Sequence Numbers, and Retransmission

> Reliable delivery over an unreliable link is built from three primitives: a **retransmission timer** the sender arms on every transmitted frame, **sequence numbers** that stamp each frame so the receiver can tell a fresh frame from a stale retransmission, and a **retransmission** rule that fires when the timer expires before an acknowledgement arrives. The textbook (Sec. 3.1.3) frames it as error control: a sender transmits, the receiver returns a positive (**ACK**) or negative (**NAK**) acknowledgement, and if either the frame or the ACK vanishes — a noise burst on a wireless link, a faulty transceiver, a dropped ACK — the sender's timer goes off and the frame goes out again. The danger retransmission introduces is **duplicate delivery**: without a sequence number the receiver cannot tell whether an arriving frame is the original or a retransmission, and would hand the same payload to the network layer twice. Stop-and-wait ARQ solves the minimum case with a **1-bit (alternating) sequence number**: the sender and receiver each flip a bit, so a retransmitted frame carries the *old* bit, the receiver re-ACKs it but never delivers it again. Real protocols generalize this — HDLC (ISO 13239) uses 3-bit sequence numbers in N(S)/N(R) fields with a window; PPP over serial links (RFC 1662) frames HDLC; TCP (RFC 9293) carries a 32-bit sequence number per byte and uses a retransmission timeout (**RTO**) governed by RTT estimators (RFC 6298) with Karn's algorithm to exclude retransmitted segments. The failure modes are concrete: too-short a timer burns bandwidth on spurious retransmissions; too-long a timer leaves the link idle; a lost ACK forces a retransmission the receiver must suppress; a wraparound of an undersized sequence field corrupts ordering. This lesson builds a runnable stop-and-wait ARQ simulator (`code/main.py`) with a lossy channel, a tick-driven timer, and a 1-bit sequence-number state machine, illustrated by the timing diagram in `assets/timers-sequence-numbers-and-retransmission.svg`.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Framing and byte/packet delineation (Phase 4 framing lessons); error-detection codes such as CRC (Phase 4 lesson on error detection)
**Time:** ~75 minutes

## Learning Objectives

- Explain why a sender that only retransmits on explicit negative acknowledgement can hang forever, and why a timer is the only complete fix.
- Trace a stop-and-wait exchange frame-by-frame, naming the sender state `(next_seq, frame_in_flight, timer)` and receiver state `expected_seq` at each step.
- Justify why a 1-bit sequence number is the *minimum* sufficient for stop-and-wait, and why it is insufficient once pipelining (a sliding window > 1) is introduced.
- Distinguish a **lost frame**, a **lost ACK**, and a **corrupted frame/ACK**, and state for each whether the receiver delivers, re-ACKs, or drops silently.
- Compute the effect of timer duration on spurious-retransmission rate and idle time given a known round-trip time distribution.
- Map the data-link mechanism onto HDLC's N(S)/N(R) fields and TCP's 32-bit sequence number + RTO (RFC 6298, Karn's algorithm).

## The Problem

A point-to-point serial link carries telemetry frames from a remote sensor to a collector. The link is mostly clean but suffers occasional noise bursts that corrupt or erase a frame. The sensor sends frame 0, frame 1, frame 2 in order and expects the collector's network layer to see exactly those three, exactly once, in order.

The first symptom the engineer sees: occasionally the collector's log shows a *gap* — frames 0 and 2 arrive, frame 1 is missing. The sensor thought it sent it. The second symptom, subtler: occasionally the log shows frame 1 *twice*, with identical timestamps, and downstream deduplication logic trips. The engineer's first instinct — "the sensor should resend if it hears nothing back" — fixes the gaps but worsens the duplicates, because now a frame that *was* delivered but whose ACK was lost gets resent and accepted again. The link needs a discipline that retransmits when something is genuinely lost and suppresses delivery when a retransmission is redundant. That discipline is ARQ with timers and sequence numbers.

## The Concept

### Why feedback alone is not enough

The textbook starts from the observation that reliable delivery needs *feedback*: the receiver sends back control frames — positive acknowledgements (**ACK**, "I got it") or negative acknowledgements (**NAK**, "it was corrupted, resend"). A protocol that sends a frame and waits for feedback sounds safe, but it has a fatal hole: if the frame vanishes entirely (a noise burst erases it, a cable is unplugged, a buffer overruns), the receiver has nothing to react to and sends nothing. If the ACK vanishes, the sender likewise hears nothing. Either way the sender waits forever. The fix is the **timer**: when the sender transmits, it arms a timer set to an interval long enough for the frame to arrive, be processed, and have the ACK propagate back. If the timer expires first, the sender assumes loss and retransmits. A NAK is therefore not strictly necessary — a timer plus retransmission covers the corrupted-and-detected case too, which is why most real protocols drop NAKs and rely on timeouts and cumulative ACKs alone.

### The duplicate-delivery problem and the 1-bit sequence number

Retransmission creates a new hazard. Suppose frame 0 was delivered fine but its ACK was lost. The sender times out and retransmits frame 0. The receiver now sees frame 0 a second time. If it has no memory of having already delivered it, it hands the payload to the network layer again — a duplicate. The fix is a **sequence number** stamped on every frame. For stop-and-wait — where at most one unacknowledged frame is in flight at any time — a single bit suffices. The sender alternates `0, 1, 0, 1, ...`; the receiver expects the matching bit and flips its expectation only after a successful delivery. The state table:

| Event at receiver | Receiver state before | Frame seq | Action | Receiver state after |
|---|---|---|---|---|
| Frame arrives, correct | expected = 0 | 0 | Deliver, send ACK(0) | expected = 1 |
| Frame arrives, correct | expected = 1 | 1 | Deliver, send ACK(1) | expected = 0 |
| Retransmission arrives | expected = 1 | 0 | Do **not** deliver, send ACK(0) | expected = 1 |
| Retransmission arrives | expected = 0 | 1 | Do **not** deliver, send ACK(1) | expected = 0 |

The retransmitted frame carries the *old* sequence bit, which the receiver recognizes as a duplicate. It re-ACKs (so the sender stops retransmitting) but does not deliver. This is exactly the behavior implemented in `code/main.py`'s `Receiver.on_data` and demonstrated in the duplicate-suppression check at the bottom of `main()`. A 1-bit window is the **minimum** — with zero bits the receiver cannot distinguish original from retransmission; with one bit it can, because at most one unacknowledged frame exists.

### The sender state machine

The sender holds three pieces of state: the **sequence number of the frame it may send next** (`seq`), the **frame currently in flight** (or `None`), and the **timer countdown**. Its state transitions:

| Trigger | Action | New state |
|---|---|---|
| Idle, data available | Build `DATA(seq)`, send, arm timer | in_flight = frame, timer = T |
| ACK arrives, ack == in_flight.seq | Cancel timer, deliver confirmation, flip seq | in_flight = None, seq ^= 1 |
| ACK arrives, ack != in_flight.seq | Ignore (stale/duplicate ACK) | unchanged |
| Timer expires | Increment retransmission count, resend in_flight, re-arm timer | timer = T |

The receiver holds a single piece of state: `expected`. Note that the sender does not advance its sequence number on a retransmission — it resends the *same* frame with the *same* sequence bit. The bit flips only on confirmed delivery. This invariant is what makes the receiver's duplicate detection work.

### Choosing the timer value

The timer must be longer than the round-trip time (RTT) but short enough that retransmission happens before the application gives up. For a fixed-latency link this is easy: set `T = 2 * one-way-delay + processing + margin`. For a variable-latency link (the general case), the choice is a trade-off captured in two failure modes:

- **T too short:** the timer fires before a slow-but-successful ACK returns, producing a **spurious retransmission**. The link carries duplicate data; the receiver suppresses the delivery but the bandwidth and the sender's retransmission counter are wasted. Worse, on a multi-hop path spurious retransmissions can add congestion that *causes* further delay — a feedback loop.
- **T too long:** a genuinely lost frame sits idle for the full timeout before being recovered, slashing throughput. In stop-and-wait the link utilization is at most `1 / (1 + 2a)` where `a = propagation-delay / transmission-time`, so idle time is already the dominant cost; a long T compounds it.

Real transport-layer protocols estimate RTT dynamically. TCP (RFC 9293) keeps an EstimatedRTT and RTTVAR (RFC 6298) and sets `RTO = EstimatedRTT + max(G, 4*RTTVAR)`, with a floor of 1 second. **Karn's algorithm** (Karn & Partridge 1987, codified in RFC 6298) excludes retransmitted segments from the RTT sample — because when a segment is retransmitted you cannot know whether the ACK acknowledges the original or the retry, so the sample is ambiguous and would pollute the estimator. The data-link equivalent on a fixed link is simpler: pick a constant based on the physical RTT plus margin. `code/main.py` uses a fixed `timeout_ticks` of 4 ticks for clarity.

### Worked example: a lost ACK

Sender sends `DATA(seq=0, "GET /")`. Receiver gets it, delivers "GET /", flips expected to 1, sends `ACK(ack=0)`. The ACK is lost. Sender's timer expires; sender retransmits `DATA(seq=0, "GET /")`. Receiver sees `seq=0` but `expected=1` — duplicate. It does **not** deliver (the network layer already has "GET /"), and re-sends `ACK(ack=0)`. This ACK reaches the sender, which accepts it (ack matches in_flight.seq=0), flips seq to 1, and proceeds to the next payload. Net result: one payload delivered exactly once, one spurious retransmission, one extra ACK. The trace in `code/main.py` prints each of these steps. See `assets/timers-sequence-numbers-and-retransmission.svg` for the timing diagram of this exact scenario, including the lost-frame and timer-expiry arrows.

### Beyond stop-and-wait: windows and multi-bit sequence numbers

Stop-and-wait wastes the link: while waiting for an ACK the sender transmits nothing. Pipelining lets the sender have several unacknowledged frames in flight — a **sliding window**. Go-Back-N (used by HDLC in its ABM with a window, and by classic TCP before selective ACKs) numbers frames with an N-bit sequence space and allows up to `2^N - 1` outstanding frames; the receiver accepts only in-order frames and a single NAK or timeout rolls back to the lost frame. Selective Repeat allows out-of-order acceptance and a larger window; it needs a sequence space of at least `2 * window` so the receiver never confuses a new frame with a retransmission — the same duplicate-ambiguity problem, now generalized. The 1-bit scheme of stop-and-wait is simply Selective Repeat with window = 1, sequence space = 2. HDLC (ISO 13239) carries the sequence in the 3-bit **N(S)** (send sequence) and **N(R)** (receive sequence, a piggybacked cumulative ACK) fields of its control byte; extended mode widens these to 7 bits. TCP scales the idea to a 32-bit byte-sequence number with cumulative ACKs and optional selective ACK blocks (RFC 2018). The lesson's simulator is the 1-bit ancestor; the field layouts and the duplicate-ambiguity invariant scale unchanged.

## Build It

The artifact is `code/main.py`, a stdlib-only stop-and-wait ARQ simulator.

1. Read `Channel.deliver`: it returns `None` for a lost frame (with probability `loss_prob`) and a bit-flipped frame for a corrupted one (probability `corrupt_prob`). These are the two failure modes the timer-and-sequence machinery must tolerate.
2. Read `Sender.send`, `Sender.tick`, `Sender.on_ack`, `Sender.resend`: the four transitions of the sender state machine. Confirm that `seq` flips only on an accepted ACK, never on a retransmission.
3. Read `Receiver.on_data`: the duplicate-suppression rule. A frame whose `seq` matches `expected` is delivered and ACKed; a frame whose `seq` does not match is re-ACKed with the *old* ack number and not delivered.
4. Run `python3 main.py`. The demo seeds the lossy channels so you will see at least one timer expiry and one lost ACK. Confirm the summary reports `Delivered exactly once, in order: True` despite the losses.
5. Vary the seeds: edit the `random.Random(7)` calls and the loss probabilities and re-run. Increase `loss_prob` to 0.5 and watch the retransmission count climb while delivery order stays correct.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm reliable delivery under loss | Run the simulator; inspect `receiver_payloads` vs. input `payloads` | Lists equal; no missing or duplicated payloads |
| Verify duplicate suppression | Read the duplicate-suppression check output at end of `main()` | First `DATA(seq=0)` delivered; second `DATA(seq=0)` re-ACKed, `delivered` unchanged |
| Observe timer-driven retransmission | Grep the trace for `*TIMER*` lines | Each timer expiry followed by a retransmit of the same `seq` |
| Stress the timer value | Set `timeout_ticks` to 1 and to 20; compare `retransmissions` and `ticks` | Short T: many spurious retransmissions; long T: few retransmissions but high `ticks` |
| Confirm ACK-loss recovery | Set `ack_channel.loss_prob` high, `data_channel.loss_prob` to 0 | Receiver still gets each payload once; sender retransmits once per lost ACK |

## Ship It

Produce a short artifact at `outputs/prompt-timers-sequence-numbers-and-retransmission.md` containing: the full trace from one simulator run, the summary line, and a one-paragraph analysis of how many retransmissions were *spurious* (the frame had actually arrived) versus *necessary* (the frame was lost). The simulator distinguishes these only in the trace — a retransmission following a `frame LOST` line is necessary; one following a successful `RX` is spurious. Counting both is the evidence that the timer value is well-tuned.

## Exercises

1. **Minimum sequence number.** Modify `Receiver.on_data` to accept frames with *any* sequence number (i.e., remove the duplicate check) and run with `ack_channel.loss_prob = 0.5`. Show a run where the receiver delivers a duplicate. Explain in one sentence why a 1-bit number is the minimum fix.
2. **Spurious vs. necessary retransmissions.** Add instrumentation to `Sender` that classifies each retransmission as spurious (the original frame was delivered) or necessary (it was lost). Hint: the receiver knows — have it expose a `last_delivered_seq`. Report the split over 1000 payloads with `loss_prob = 0.2` on both channels.
3. **Timer tuning.** Sweep `timeout_ticks` over {1, 2, 3, 4, 8, 16} with a fixed loss profile. Plot total `ticks` to deliver 50 payloads. Identify the value that minimizes total time and explain why both extremes are bad.
4. **Corruption as loss.** The simulator models corruption as a sequence-bit flip, which the receiver treats as a wrong-seq duplicate and re-ACKs. Modify the model so corruption instead flips a payload byte and the receiver has a CRC check that drops the frame silently. Confirm the timer still recovers it, and that no duplicate is delivered.
5. **From 1-bit to 3-bit.** Generalize `Frame`, `Sender`, and `Receiver` to a 3-bit sequence space with a Go-Back-N window of 4. Send 20 payloads over a lossy channel. Verify in-order, exactly-once delivery and identify where Go-Back-N wastes bandwidth versus stop-and-wait.
6. **Karn's algorithm, in miniature.** Add an RTT estimator to the sender that samples `ticks` between send and ACK for *non-retransmitted* frames only, and skips samples for retransmitted frames. Show that including retransmitted samples biases the estimator upward under bursty loss.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ARQ | "Automatic repeat request" | A discipline where the receiver acknowledges frames and the sender retransmits unacknowledged ones; stop-and-wait, Go-Back-N, and Selective Repeat are the three canonical variants |
| ACK | "The receiver said OK" | A control frame carrying the sequence number of the highest in-order frame accepted; in stop-and-wait it echoes the just-accepted frame's seq bit |
| NAK / NACK | "Negative acknowledgement" | A control frame signalling a detected error; optional — a timer plus retransmission covers the same case, which is why most protocols omit NAKs |
| Sequence number | "The frame's ID" | A counter stamped on each frame so the receiver can distinguish an original from a retransmission; stop-and-wait needs 1 bit, Go-Back-N needs N bits for a window of `2^N - 1` |
| Retransmission timer | "The sender's alarm clock" | A countdown started when a frame is sent; expiry means "no ACK in time, resend"; its value trades spurious retransmissions against idle time |
| Stop-and-wait | "Send one, wait one" | ARQ with a window of 1: at most one unacknowledged frame in flight, hence a 1-bit sequence number suffices |
| Piggybacking | "ACKs ride on data frames" | Carrying the acknowledgement number in the receiver's own outgoing data frame's N(R) field (HDLC) instead of sending a standalone ACK, saving frame overhead |
| Karn's algorithm | "Don't time retransmits" | The rule (RFC 6298) that RTT samples from retransmitted segments are excluded from the RTO estimator, because the ACK could match either copy |
| RTO | "Retransmission timeout" | The computed interval at which TCP retransmits; per RFC 6298, `EstimatedRTT + max(G, 4*RTTVAR)` with a 1-second floor |

## Further Reading

- RFC 9293 — *Transmission Control Protocol (TCP) Specification* — the 32-bit byte-sequence number, cumulative ACK, and retransmission model. <https://www.rfc-editor.org/rfc/rfc9293>
- RFC 6298 — *Computing TCP's Retransmission Timer* — the RTT estimators (SRTT/RTTVAR) and Karn's algorithm for excluding retransmitted segments. <https://www.rfc-editor.org/rfc/rfc6298>
- RFC 2018 — *TCP Selective Acknowledgment Options* — selective repeat at the transport layer. <https://www.rfc-editor.org/rfc/rfc2018>
- ISO/IEC 13239 — *High-level data link control (HDLC) procedures* — the N(S)/N(R) 3-bit (and extended 7-bit) sequence fields and ABM/Go-Back-N operation.
- RFC 1662 — *PPP in HDLC-like Framing* — the link-layer framing that wraps HDLC over serial, including the 1-byte sequence/ack fields in practice. <https://www.rfc-editor.org/rfc/rfc1662>
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Sec. 3.1.3 (Error Control) and Sec. 3.3 (Data Link Protocols) — the stop-and-wait, Go-Back-N, and Selective Repeat protocol state machines this lesson simulates.
- Karn, P. & Partridge, C. (1987), *Improving Round-Trip Time Estimates in Reliable Transport Protocols* — the original Karn's algorithm paper. <https://doi.org/10.1145/164951.164969>
