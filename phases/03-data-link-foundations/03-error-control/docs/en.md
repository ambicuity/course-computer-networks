# Error Control

> Error control is the set of link-layer mechanisms — acknowledgements (ACK/NAK), retransmission timers, and sequence numbers — that turn an unreliable channel into reliable, in-order delivery. The canonical building block is **stop-and-wait ARQ** (Automatic Repeat reQuest): the sender transmits one frame, starts a retransmission timer (RTO), and waits for a positive ACK before sending the next. A lost data frame, a lost ACK, or a premature timeout each trigger a retransmission — and without a 1-bit alternating sequence number, that retransmission causes the receiver to deliver a **duplicate** to the network layer. The classic failure mode is the **premature timeout**: an ACK that arrives just after the timer fires produces a needless retransmit, which the sequence number then silently discards. Real protocols inherit this design: HDLC and PPP carry N(S)/N(R) sequence fields and a CRC-16/CRC-32 FCS; TCP generalizes the same ideas with 32-bit sequence numbers and cumulative ACKs (RFC 9293). This lesson builds a working stop-and-wait simulator in `code/main.py`, traces the ACK/timeout/duplicate cycle, and ships a runnable evidence model you can map onto any real ARQ trace in Wireshark.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib stop-and-wait simulator)
**Prerequisites:** Phase 3 · 02 (Framing), basic understanding of CRC/checksum error detection, basic packet-capture reading
**Time:** ~75 minutes

## Learning Objectives

- Trace the stop-and-wait ARQ cycle: frame → timer start → ACK → timer cancel, and reconstruct it from a packet capture.
- Explain why a 1-bit alternating sequence number is mathematically sufficient for stop-and-wait, and where it breaks for pipelined protocols.
- Distinguish the four canonical error-control failure modes — lost frame, lost ACK, premature timeout, and duplicate delivery — and name the evidence each leaves.
- Compute the protocol efficiency of stop-and-wait from link rate, frame size, and round-trip time, and show why it collapses on long fat links.
- Map textbook ARQ fields onto real protocol headers: HDLC/PPP control fields and TCP's seq/ack numbers.

## The Problem

A field tech reports that a point-to-point serial link "works but is slow, and the application sometimes processes the same record twice." The physical layer is up; framing is correct; the CRC is passing on most frames. Yet throughput is a fraction of the line rate and occasional duplicate records appear downstream.

This is an error-control problem, not a wiring problem. The link is using stop-and-wait ARQ. Two things are happening at once: (1) the round-trip time is large relative to the frame transmission time, so the sender spends most of its time *idle*, waiting for ACKs — that is the slowness; and (2) the retransmission timer is set too aggressively, so ACKs that arrive late trigger retransmissions, and a subtle off-by-one in sequence-number handling lets a duplicate slip through to the application — that is the double-processing.

To fix it you need the same thing the data link layer needs: a precise model of how acknowledgements, timers, and sequence numbers interact, and the exact evidence (which frame, which ACK number, which timer event) that confirms each hypothesis.

## The Concept

Error control assumes the receiver can already tell a *correct* frame from a *damaged* one — that is the job of the error-detecting code (CRC/checksum, covered separately). Given that detector, error control answers a different question: **how do we make sure every frame is eventually delivered to the network layer, exactly once, in order, even when frames or acknowledgements vanish?**

Three primitives do all the work: **acknowledgements**, **timers**, and **sequence numbers**.

### Acknowledgements (ACK / NAK)

The receiver sends back a control frame reporting the fate of each data frame:

- **Positive ACK** — "frame received correctly, send the next one."
- **Negative ACK (NAK / REJ)** — "frame arrived damaged or out of order, resend it."

A positive-ACK-only protocol is the common case: silence (no ACK before the timer expires) is treated as loss. NAKs are an *optimization* — they let the sender retransmit immediately instead of waiting for a timeout, but they are never strictly required for correctness.

### Timers and the retransmission timeout (RTO)

A pure ACK/NAK scheme deadlocks the moment a frame *vanishes completely* (a noise burst eats it). The receiver has nothing to react to, so it stays silent; the sender waits forever. The fix is a **timer started when the frame is sent**:

```
RTO ≈ transmit_time + 2·propagation_delay + processing_time + margin
```

- If the ACK returns before RTO, the timer is **canceled**.
- If RTO expires first, the sender assumes loss and **retransmits**.

Setting RTO is a balancing act. Too long → slow recovery from real losses. Too short → **premature timeouts**: the ACK was actually on its way, the sender retransmits anyway, and the link wastes a frame slot. The premature timeout is the single most common self-inflicted error-control pathology, and it is exactly the bug in *The Problem*.

### Sequence numbers and the duplicate hazard

Retransmission creates a new danger: the receiver may now see the **same frame twice** and deliver it to the network layer twice. Consider the lost-ACK case:

1. Sender sends frame 0. Receiver gets it, delivers it, sends ACK.
2. The **ACK is lost**.
3. Sender's timer expires; it resends frame 0.
4. Receiver gets frame 0 *again* — but it has no way to know this is a retransmission rather than a brand-new frame.

The cure is a **sequence number** on every frame. The receiver tracks the next sequence number it *expects*; a frame whose number it has already delivered is ACKed again but **not** redelivered. For stop-and-wait, a single bit (alternating 0,1,0,1,…) is provably sufficient, because only one frame is ever outstanding at a time — the receiver only needs to disambiguate "the one I'm waiting for" from "the one I just delivered."

The four failure modes and their evidence:

| Failure mode | What happens | Evidence in a trace |
|---|---|---|
| Lost data frame | Frame never arrives; no ACK returns | Timer expiry + retransmit of same seq; no ACK between |
| Lost ACK | Frame delivered, ACK dropped | Duplicate data frame (same seq) followed by duplicate ACK |
| Premature timeout | RTO too short; ACK in flight | Retransmit of seq N while ACK(N) is still on the wire |
| Duplicate delivery | Seq logic broken / 1-bit reused too early | Same record processed twice at the network layer |

The state machine and these transitions are drawn in `assets/error-control.svg`.

### Stop-and-wait ARQ as a state machine

The sender alternates between two states for the current sequence bit `s`:

```
SEND(s): transmit frame[s]; start timer; → AWAIT(s)
AWAIT(s):
   on ACK(s):    cancel timer; s ← 1 - s; → SEND(s)   (advance)
   on ACK(1-s):  ignore (stale/duplicate ACK)
   on timeout:   → SEND(s)                              (retransmit, same s)
```

The receiver mirrors it with an expected bit `e`:

```
on frame(e):     deliver to network layer; send ACK(e); e ← 1 - e
on frame(1-e):   send ACK(1-e); DO NOT deliver (duplicate)
```

This is the smallest correct ARQ. `code/main.py` implements exactly this pair and runs it over a lossy channel.

### Efficiency: why stop-and-wait collapses on long links

Because only one frame is outstanding, the sender is idle for an entire round trip per frame. Define:

- `T_frame = frame_bits / link_rate` (time to clock the frame onto the wire)
- `RTT = 2 · propagation_delay`

Then **link utilization** is:

```
U = T_frame / (T_frame + RTT)
```

Worked example — a 1500-byte frame on a 1 Gbps link spanning a 30 ms RTT satellite hop:

- `T_frame = (1500 · 8) / 1e9 = 12 µs`
- `U = 12 µs / (12 µs + 30 ms) ≈ 12 / 30012 ≈ 0.0004 = 0.04%`

Stop-and-wait wastes **99.96%** of a fat satellite link. That number is *why* sliding-window protocols (go-back-N, selective repeat) exist: they pipeline `W` frames so utilization becomes `min(1, W · T_frame / (T_frame + RTT))`. The bandwidth-delay product `link_rate · RTT` is the number of bits "in flight," and the window must cover it to fill the pipe. `code/main.py` prints this efficiency calculation for several link profiles.

### Where this lives in real protocols

The textbook fields are not academic — they are the ancestors of fields you will see in captures:

| Concept | HDLC / PPP | TCP (RFC 9293) |
|---|---|---|
| Sequence number | `N(S)` send seq (3 or 7 bits) | 32-bit Sequence Number |
| Acknowledgement | `N(R)` receive seq (piggybacked) | 32-bit Acknowledgment Number, ACK flag |
| Negative ACK | `REJ` / `SREJ` supervisory frames | duplicate ACKs / SACK blocks |
| Error detection | 16-bit FCS (CRC-CCITT) | 16-bit checksum |
| Retransmission timer | T1 timer | adaptive RTO (Karn/Jacobson, RFC 6298) |

PPP (RFC 1662) runs *unacknowledged* by default — it carries the CRC-16/CRC-32 FCS for detection and leaves retransmission to higher layers — but the HDLC framing it borrows defines the full ARQ machinery. TCP is stop-and-wait's pipelined descendant.

## Build It

1. Read `code/main.py`. It defines a `StopAndWaitSender`, a `StopAndWaitReceiver`, and a `LossyChannel` with tunable frame-loss and ACK-loss probabilities and a fixed RTO.
2. Run `python3 main.py`. Watch the printed event log: each line is a `SEND`, `ACK`, `TIMEOUT`, `DUP-DROP`, or `DELIVER` event with its sequence bit.
3. In the demo, identify one occurrence of each of the four failure modes from the table above. Confirm that no duplicate is ever *delivered* even when duplicates are *received*.
4. Read the efficiency block: it computes `U` for a LAN, a WAN, and a satellite link. Confirm the satellite figure matches the ~0.04% worked example.
5. Change `ACK_LOSS` to a high value and rerun. Note how many retransmissions are needed and how the 1-bit sequence number still prevents duplicate delivery.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a link uses ARQ | Periodic data frames each followed by an ACK before the next data frame | You can point to the ACK that releases each new frame |
| Diagnose slowness | `T_frame` vs `RTT` from frame size and capture timestamps | You compute `U` and show the link is RTT-bound, not rate-bound |
| Diagnose duplicate processing | Two data frames with the *same* sequence number; downstream double-effect | You trace it to a lost ACK or premature timeout, not a re-sent payload |
| Tune the timer | Retransmits firing while an ACK timestamp is still earlier than the retransmit | You show RTO < observed RTT and recommend raising it |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/skill-arq-tracer.md` — a runbook that, given a packet capture, classifies every retransmission into one of the four failure modes and recommends an RTO or window change.
- Alternatively: the annotated state diagram, or an extended `main.py` that adds go-back-N so you can compare utilization directly.

Start from the event log your own run of `code/main.py` produces — paste it into the runbook as the worked reference trace.

## Exercises

1. A 1500-byte frame travels a 100 Mbps link with 5 ms one-way propagation delay. Compute `T_frame`, `RTT`, and stop-and-wait utilization `U`. What window size `W` would push `U` above 0.95?
2. In `code/main.py`, set frame loss to 0 but ACK loss to 0.5. Run it and explain in one paragraph why the *receiver* sees duplicates but the *network layer* never does. Cite the exact line in the event log that drops the duplicate.
3. A capture shows: `frame seq=0`, then 40 ms later `frame seq=0` again, then `ACK seq=0`, then `ACK seq=0`. Classify the failure mode and state whether the timer was too short or a frame was genuinely lost. What additional timestamp would settle it?
4. Stop-and-wait uses a 1-bit sequence number. Go-back-N with a window of 7 needs at least how many sequence-number bits, and why must the sequence space exceed the window size?
5. PPP (RFC 1662) ships *without* link-layer retransmission. Argue when that is the right design choice and which layer then owns error control — reference the satellite efficiency number to justify pushing ARQ up the stack.
6. Modify the simulator's RTO to be *adaptive* (track a smoothed RTT like Jacobson's algorithm). Show one event-log run where the adaptive timer avoids a premature timeout that the fixed timer triggered.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ARQ | "the retransmit thing" | Automatic Repeat reQuest: the family of error-control protocols built on ACK + timer + sequence number |
| ACK / NAK | "the receipt" | Control frame reporting a data frame's fate; positive ACK is mandatory, NAK is an optional speedup |
| Sequence number | "a counter on the packet" | The field that lets the receiver reject duplicates and deliver in order; 1 bit suffices for stop-and-wait |
| RTO | "the timeout" | Retransmission timeout — the interval after which unacknowledged data is presumed lost and resent |
| Premature timeout | "a spurious retransmit" | RTO fired while the ACK was still in flight; wastes a frame slot, masked (not caused) by sequence numbers |
| Duplicate delivery | "double processing" | The same payload reaching the network layer twice — the bug sequence numbers exist to prevent |
| Utilization (U) | "link efficiency" | Fraction of time the sender is actually transmitting; for stop-and-wait, `T_frame / (T_frame + RTT)` |
| Piggybacking | "free ACKs" | Carrying `N(R)` acknowledgement data inside a reverse-direction data frame instead of a standalone ACK |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §3.1.3 (Error Control), §3.3 (Elementary Data Link Protocols), and §3.4 (Sliding Window Protocols).
- RFC 9293 — *Transmission Control Protocol (TCP)*: sequence/acknowledgement number semantics and retransmission.
- RFC 6298 — *Computing TCP's Retransmission Timer* (Jacobson/Karn-derived adaptive RTO).
- RFC 1662 — *PPP in HDLC-like Framing*: flag bytes, control field, and the 16/32-bit FCS.
- ISO/IEC 13239 — HDLC procedures, defining the `N(S)`/`N(R)` control fields and REJ/SREJ supervisory frames.
- Wireshark display-filter reference: `tcp.analysis.retransmission`, `tcp.analysis.duplicate_ack`, and `ppp` for inspecting ARQ-style evidence on real captures.
