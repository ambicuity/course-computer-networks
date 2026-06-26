# A Simplex Stop-and-Wait Protocol for a Noisy Channel to A One-Bit Sliding Window Protocol

> A noisy link drops and corrupts both data and ACK frames, so a bare stop-and-wait sender that just adds a timer will silently deliver duplicate packets to the network layer when an acknowledgement is lost. The fix is a **1-bit sequence number** plus a retransmission timer — the scheme Tanenbaum calls **Protocol 3 (PAR — Positive Acknowledgement with Retransmission)**, also known generically as **stop-and-wait ARQ**. The sender holds `next_frame_to_send` (0 or 1), starts a per-frame timer after each transmission, and only advances when an ACK whose `ack` field equals the outstanding sequence number arrives. The receiver holds `frame_expected`, accepts a frame only when `seq == frame_expected`, increments modulo 2, and re-acknowledges the *last good* frame on any duplicate. **Protocol 4 (the one-bit sliding window)** generalizes this to full-duplex by piggybacking the ACK in the `ack` header field of outgoing data frames, with a sender and receiver window each of size 1. It is provably correct against any pattern of loss, corruption, and premature timeout, but a simultaneous-start race makes half the frames duplicates and wastes bandwidth. These ideas are the direct ancestors of TCP's sequence/acknowledgement numbers (RFC 9293) and 802.11's per-frame ACK with retransmission.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Framing and the error-free stop-and-wait protocol (Phase 4 · 03); checksums/CRC for damage detection (Phase 4 · 02)
**Time:** ~90 minutes

## Learning Objectives

- Trace the lost-ACK duplicate-delivery failure of a naive timer-only stop-and-wait protocol and explain why it violates the data link layer's "deliver each packet exactly once, in order" contract.
- Justify why a **1-bit** sequence number is sufficient for stop-and-wait, using the "only ambiguity is between frame *m* and *m+1*" argument.
- Name and locate the four state variables that make PAR work: `next_frame_to_send`, `frame_expected`, the per-frame timer, and the `seq`/`ack` header fields.
- Distinguish Protocol 3 (simplex PAR, separate ACK frames) from Protocol 4 (full-duplex, piggybacked ACK, window size 1).
- Predict the duplicate-generating behaviour of Protocol 4 under a simultaneous start and under repeated premature timeouts.
- Read a stop-and-wait exchange in Wireshark / a trace and identify retransmissions, duplicate ACKs, and the RTT that should bound the timeout.

## The Problem

You are debugging a serial telemetry link between an embedded sensor (A) and a collector (B) over a noisy RS-485 bus. The application sees the right *number* of readings most of the time, but every few minutes a reading appears **twice** in the database with identical timestamps. Packet counters at B show no checksum errors during those windows, so "the wire is corrupting data" is not the explanation.

The link uses a hand-rolled stop-and-wait scheme: A sends a frame, starts a timer, and retransmits if no ACK arrives in time. The author reasoned that a checksum plus a timeout is enough — damaged frames are discarded and eventually resent, so nothing is lost. That reasoning has a fatal hole. When a *data frame arrives intact at B* but its *acknowledgement is lost on the way back*, A times out and resends a frame that B has already delivered. Without a way to tell "new frame" from "retransmission," B delivers the packet to its network layer a second time. The duplicate is not a corruption bug — it is a **protocol correctness** bug, and it is exactly the trap Protocol 3 is designed to close.

## The Concept

Source: [`chapters/chapter-03-the-data-link-layer.md`](../../../../chapters/chapter-03-the-data-link-layer.md), the Elementary Data Link Protocols and Sliding Window Protocols sections (Tanenbaum & Wetherall, *Computer Networks*, 5/6e, §3.3.3 and §3.4.1).

### Why a timer alone is not enough

Start from the error-free stop-and-wait protocol (Protocol 2): A sends one data frame, then blocks until B's dummy ACK frame returns. On a noisy channel two new events appear: frames can be **damaged** (caught by the checksum, then discarded) and frames can be **lost entirely** (nothing arrives, so nothing fires). The obvious patch is a timer: if no ACK comes back within an interval, resend.

This breaks on a single benign scenario:

1. A gives packet 1 to its data link layer. B receives it intact, passes it up, and sends an ACK.
2. The **ACK frame is lost** — the channel does not discriminate between data and control frames.
3. A's timer expires. Having seen no ACK, A *incorrectly* assumes the data frame was lost and retransmits it.
4. The duplicate arrives intact at B, which has no way to know it is a repeat, and delivers packet 1 to the network layer **a second time**. The protocol has failed.

The data link layer's job is to hand the destination network layer the *identical sequence* of packets it was given — no loss, no duplication, in order. A lost ACK must never become a duplicated packet.

### The 1-bit sequence number argument

The receiver needs to distinguish a *fresh* frame from a *retransmission*. Put a sequence number in the frame header. How many bits? The decisive observation: the only ambiguity is ever between a frame *m* and its immediate successor *m+1*. The sender only starts sending *m+1* after it has received the ACK for *m*, which in turn means *m−1* and its ACK were already handled. So the sender can never be juggling *m−1* and *m+1* at the same time — predecessor and successor are never both in play.

That means **one bit** (values 0 and 1, incremented modulo 2) is enough. The receiver keeps `frame_expected`; a frame whose `seq` matches is accepted, delivered, and `frame_expected` flips; any frame with the wrong `seq` is a duplicate and is discarded — but the receiver still re-sends an acknowledgement so the sender eventually learns the frame got through.

### Protocol 3 (PAR) state machine

PAR — *Positive Acknowledgement with Retransmission*, equivalently *stop-and-wait ARQ (Automatic Repeat reQuest)* — adds three event types to the sender: `frame_arrival`, `cksum_err`, and `timeout`. The control logic:

| Sender state / event | Action |
|---|---|
| Init | `next_frame_to_send = 0`; fetch first packet |
| Send | set `s.seq = next_frame_to_send`; transmit; `start_timer(s.seq)` |
| `frame_arrival` with `s.ack == next_frame_to_send` | `stop_timer`; fetch next packet; `inc(next_frame_to_send)` |
| `frame_arrival` with wrong/`cksum_err`/`timeout` | leave buffer and seq unchanged; resend the *same* frame |

| Receiver state / event | Action |
|---|---|
| Init | `frame_expected = 0` |
| `frame_arrival`, `r.seq == frame_expected` | deliver to network layer; `inc(frame_expected)` |
| `frame_arrival`, wrong seq, or `cksum_err` | discard; do not deliver |
| Any valid frame | reply with `s.ack = 1 − frame_expected` (acks the *last* correctly received frame) |

The `1 − frame_expected` trick is worth pausing on: the receiver acknowledges the sequence number it just *finished* accepting, not the one it is now waiting for. That is what lets a duplicate ACK re-confirm the previous frame. See [`code/main.py`](../code/main.py) for an executable version of exactly this loop, and the [state/timing diagram](../assets/a-simplex-stop-and-wait-protocol-for-a-noisy-channel-to-a-one-bit-slid.svg) for the message flow including a lost ACK.

### Setting the timeout

After transmitting, the sender starts (or resets) a timer. The interval must cover the worst case: frame propagation to B, B's processing time, and the ACK propagation back — one round-trip time (RTT) plus margin. Two failure modes bracket the choice:

- **Too short** → *premature timeout*: the sender retransmits while the original ACK is still in flight. Correctness survives (the sequence number absorbs the duplicate) but bandwidth is wasted and, under Protocol 4, duplicate deliveries to the *peer's* network layer can occur.
- **Too long** → recovery from a real loss stalls for the whole timeout, tanking throughput on a lossy link.

Worked example: a 9600 bps RS-485 link, 256-byte frames (2048 bits), 50 m bus. Transmission time ≈ 2048 / 9600 ≈ 213 ms; propagation at ~5 ns/m is ~0.25 µs (negligible); add ~10 ms receiver processing and a 213 ms ACK frame. A sane timeout is well above 213 + 213 + 10 ≈ 436 ms — round up to ~600 ms for margin. Set it to 300 ms and you will see a storm of premature retransmissions on every slightly slow ACK.

### Throughput cost of stop-and-wait

Stop-and-wait sends exactly one frame per RTT, so link utilization is `Tframe / (Tframe + RTT)`. On the RS-485 example above utilization is fine because the line is slow and short. But on a 1 Mbps satellite hop with a 540 ms RTT and 1000-bit frames, `Tframe = 1 ms` and utilization collapses to `1 / 541 ≈ 0.18%`. This is precisely the motivation for *larger* sliding windows (Go-Back-N, Selective Repeat) covered in the next lessons — Protocol 4 here is the window-size-1 base case.

### Protocol 4 — the one-bit sliding window

Protocol 4 makes the link **full-duplex** and folds the acknowledgement into the data stream. Three changes from PAR:

1. Frames carry a `kind` distinction conceptually, but more importantly every data frame carries an **`ack` field** — the acknowledgement *piggybacks* on outgoing data, costing only 1 bit instead of a whole separate ACK frame (header + ack + checksum).
2. Both endpoints run the *same* program holding both `next_frame_to_send` and `frame_expected`. A frame arrival is handled twice: the **inbound** half (`if r.seq == frame_expected` → deliver, flip `frame_expected`) and the **outbound** half (`if r.ack == next_frame_to_send` → stop timer, fetch next packet, flip `next_frame_to_send`).
3. The sender window and receiver window are each **size 1** (sequence numbers 0/1), so this *is* stop-and-wait, just bidirectional and piggybacked.

Frame notation in the trace is `(seq, ack, packet)`. A normal exchange:

```
A sends (0,1,A0)
B gets  (0,1,A0)*      B sends (0,0,B0)
A gets  (0,0,B0)*      A sends (1,0,A1)
B gets  (1,0,A1)*      B sends (1,1,B1)
```

`*` marks where a network layer accepts a packet — one acceptance per arrival, no duplicates.

### Protocol 4's pathological cases

Protocol 4 is correct under *any* pattern of loss, damage, and premature timeout — it never delivers a duplicate, never skips a packet, never deadlocks. But two scenarios show how subtle that correctness is:

- **Premature timeouts:** if A's timeout is too short while sending frame 0 (`seq=0, ack=1`), A fires off a stream of identical frames. B accepts the first, sets `frame_expected=1`, and *rejects every duplicate* (wrong seq). Because the duplicates also carry `ack=1` and B is still waiting for an ack of 0, B does not fetch a new packet either. B keeps replying `(seq=0, ack=0)` until one reaches A and unblocks it. Correct — but wasteful.
- **Simultaneous start:** if *both* sides start outside the main loop and their first frames cross, you fall into the abnormal case where **half the frames carry duplicates** even with zero transmission errors. The cure is convention: only one side transmits before entering the loop.

## Build It

`code/main.py` is a discrete-event stop-and-wait / PAR simulator (stdlib only). Steps:

1. Read the `Frame` dataclass — note the `seq`, `ack`, `kind`, and `payload` fields, mirroring the textbook header.
2. Run the sender/receiver loop against a `NoisyChannel` whose `loss_prob` and `corrupt_prob` you control with a seeded RNG so runs are reproducible.
3. Watch the event log: each `TX`, `RX`, `ACK`, `DUP-DROP`, `CKSUM-ERR`, and `TIMEOUT` line is the evidence you would otherwise dig out of a packet trace.
4. Flip `loss_prob` on the *ACK direction only* and confirm the receiver drops the retransmitted duplicate (`DUP-DROP`) instead of double-delivering — the exact bug from "The Problem."
5. Tighten the timeout below one RTT and count the premature retransmissions reported in the summary.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm duplicates are suppressed | `DUP-DROP` lines in the log; `delivered` count equals `unique packets` | Lost ACKs trigger retransmission but never a second delivery |
| Size the timeout | Measured RTT vs configured timeout; premature-retransmit counter | Timeout > RTT + processing; premature retransmits ≈ 0 |
| Spot a retransmission in a trace | Two data frames with the *same* `seq`; an ACK between them was lost | You can point to the missing ACK as the cause, not corruption |
| Read a piggybacked ACK | A data frame whose `ack` field advances the peer's window | `ack` field changes value, no standalone ACK frame appears |
| Explain a throughput floor | `Tframe / (Tframe + RTT)` utilization on a long-RTT link | You quote the formula and the ~0.18% satellite figure |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **stop-and-wait ARQ runbook** mapping each symptom (duplicate delivery, retransmit storm, stalled recovery) to its evidence and fix.
- The annotated `(seq, ack, packet)` trace from a `code/main.py` run with a forced lost ACK, marked up like Figure 3-17.
- A timeout-sizing worksheet that computes RTT and a safe timer for a given link rate, frame size, and distance.

Start from [`outputs/prompt-a-simplex-stop-and-wait-protocol-for-a-noisy-channel-to-a-one-bit-slid.md`](../outputs/prompt-a-simplex-stop-and-wait-protocol-for-a-noisy-channel-to-a-one-bit-slid.md).

## Exercises

1. In `code/main.py`, set the channel to lose only ACK frames (data delivered intact) with probability 0.4. Run 50 packets. How many `DUP-DROP` events occur, and is `delivered == 50`? Explain why the count of duplicates does not change correctness.
2. Disable the sequence number (force `seq = 0` always) and re-run with ACK loss. Show the run where a packet is delivered twice, and identify the first frame at which the network-layer delivery count diverges from the packet count.
3. Set the timeout to 0.5× the round-trip time and run a clean (lossless) channel. Count premature retransmissions and compute wasted bandwidth as `(extra frames) / (total frames)`.
4. Hand-trace Protocol 4 for a **simultaneous start**: A sends `(0,1,A0)` and B sends `(0,1,B0)` at the same instant. Produce the next six exchanges and mark every point where a network layer accepts a *duplicate*.
5. For a 2 Mbps link with 1500-byte frames and a 40 ms RTT, compute stop-and-wait utilization. Then state the window size you would need to saturate the link.
6. Capture (or simulate) a TCP transfer in Wireshark, find a retransmitted segment, and explain how TCP's sequence/acknowledgement numbers generalize the 1-bit `seq`/`ack` of Protocol 3.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Stop-and-wait | "Send one, wait for the ACK" | A window-size-1 protocol; one frame per RTT, so utilization is `Tframe/(Tframe+RTT)` |
| PAR / ARQ | "Just retransmit on timeout" | *Positive Acknowledgement with Retransmission* — timer **plus** a sequence number; the timer alone is incorrect |
| 1-bit sequence number | "A toggle bit" | Sufficient because ambiguity is only ever between frame *m* and *m+1*, never *m−1* and *m+1* |
| `frame_expected` | "What the receiver wants" | Receiver state; a frame with `seq != frame_expected` is a duplicate and is dropped, not delivered |
| `ack = 1 − frame_expected` | "Acks the next frame" | Acks the frame just *accepted*; lets a duplicate ACK re-confirm the previous frame |
| Piggybacking | "ACK rides along" | Carrying the acknowledgement in the `ack` field of an outgoing **data** frame instead of a separate frame |
| Premature timeout | "It timed out early" | Timeout < RTT; spawns duplicate transmissions — harmless to correctness, costly to throughput |
| Simultaneous start | "Both sides talk at once" | Protocol 4 race where crossed first frames make half the frames duplicates with zero channel errors |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 3 — §3.3 Elementary Data Link Protocols (Protocols 1–3) and §3.4 Sliding Window Protocols (Protocols 4–6).
- RFC 9293, *Transmission Control Protocol* (2022) — the sequence/acknowledgement number machinery that generalizes PAR to a sliding window over an unreliable network.
- RFC 1122, §4.2 — host requirements for TCP retransmission timers (the RTO sizing problem PAR poses in miniature).
- IEEE 802.11 — per-frame positive acknowledgement with retransmission at the MAC layer; a stop-and-wait ARQ instance on a wireless link.
- W. Stallings, *Data and Computer Communications* — chapter on flow and error control, for the utilization derivation and ARQ taxonomy (stop-and-wait, Go-Back-N, Selective Repeat).
