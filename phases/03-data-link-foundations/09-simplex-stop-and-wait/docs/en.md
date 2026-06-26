# Simulating the Simplex Stop-and-Wait Protocols

> The three elementary data link protocols of Tanenbaum & Wetherall Section 3.3 — **Utopia** (Protocol 1), **simplex stop-and-wait for an error-free channel** (Protocol 2), and **simplex stop-and-wait for a noisy channel** (Protocol 3) — are the smallest non-trivial ARQ designs in networking. Protocol 1 ignores every failure mode and just pumps frames; Protocol 2 adds a one-bit feedback channel so the sender waits for a dummy **acknowledgement (ACK)** frame before advancing, solving *flow control* on a half-duplex link; Protocol 3 adds a **retransmission timer** and a **1-bit sequence number** (alternating 0/1) so that a lost or damaged data frame, or a lost ACK, cannot silently duplicate a packet at the receiver's network layer. The frame structure carries four fields — `kind` ∈ {data, ack, nak}, `seq`, `ack`, and `info` — and the sender's only events are `frame_arrival`, `cksum_err`, and `timeout`. The fatal flaw Protocol 3 fixes is the duplicate-delivery scenario: ACK for packet 1 is lost, sender times out, resends packet 1, and the receiver — with no way to tell new from old — hands a second copy to its network layer, corrupting the byte stream. A 1-bit sequence number is provably sufficient because stop-and-wait's strict alternation means the only ambiguity at any instant is between frame *m* and its immediate successor *m+1*. This lesson builds a runnable, event-driven simulator for all three protocols in `code/main.py` and traces the exact failure scenarios the textbook warns about.

**Type:** Lab
**Languages:** Python, packet traces
**Prerequisites:** Framing and the CRC/error-detection material from earlier Phase 3 lessons; the layered model (network layer ↔ data link layer ↔ physical layer interface); the concept of a checksum-damaged frame
**Time:** ~85 minutes

## Learning Objectives

- Distinguish the three protocols by which failure modes each addresses: none (Utopia), flow control only (Protocol 2), flow control + loss/damage (Protocol 3).
- Explain why a 1-bit sequence number is sufficient for stop-and-wait, by tracing the strict-alternation argument that bounds the ambiguity to *m* vs *m+1*.
- Reproduce the duplicate-delivery failure that occurs when a naive timer-only scheme retransmits after a lost ACK, and show how the `seq` field defeats it.
- Simulate the four event types — `frame_arrival`, `cksum_err`, `timeout`, `network_layer_ready` — and the timer state machine (`start_timer`, `stop_timer`, reset-on-resend).
- Compute link utilization for stop-and-wait as `U = T_frame / (T_frame + 2·T_prop + T_ack + T_proc)` and explain why it collapses on long-fat pipes.
- Read a frame trace and identify, from `kind`/`seq`/`ack` values alone, whether a retransmission was triggered by a damaged frame or by a lost ACK.

## The Problem

A serial link between an industrial sensor controller and a logging PC runs at 9600 bit/s. The controller streams one 64-byte reading per second. Most of the time everything is fine, but every few hours the log file on the PC ends up with a duplicated reading — the same 64-byte payload appearing twice in a row — and occasionally a reading is missing entirely. The link uses a naive "send, then wait for an ACK, then resend on timeout" rule with no sequence numbers, because the original designer reasoned that a duplicate ACK is harmless and a missing ACK just triggers a harmless retransmission.

That reasoning is exactly the textbook's fatal flaw. When the ACK for reading *N* is lost in the cable, the controller times out and resends reading *N*. The PC, having already handed *N* to its application, has no record that it just did so, so it delivers *N* again — a silent duplicate that corrupts the time series. Conversely, if a data frame is damaged, the PC silently drops it and never ACKs; the controller eventually resends, and recovery works — but only by luck, and only if the controller's timer is long enough that the resend is not mistaken for a fresh frame. The engineer needs the smallest correct fix: a 1-bit sequence number, a timer, and a strict alternation rule. That fix *is* Protocol 3, and the simulator in this lesson is the tool to verify it actually closes the hole.

## The Concept

### The model: three layers, one channel, four events

The textbook models the physical, data link, and network layers as cooperating processes that exchange data through library procedures. The data link layer's view of the world is a single event loop: it calls `wait_for_event(&event)` and blocks until something happens. Across the three protocols the event vocabulary grows:

| Event | Utopia (P1) | Stop-and-wait error-free (P2) | Stop-and-wait noisy (P3) |
|---|---|---|---|
| `frame_arrival` | yes (only event) | yes (only event) | yes |
| `cksum_err` | — | — | yes (damaged frame detected by CRC) |
| `timeout` | — | — | yes (sender's retransmission timer) |
| `network_layer_ready` | — (always ready) | — (always ready) | yes (gated by `enable/disable_network_layer`) |

The frame, defined once in `protocol.h` and reused by all three protocols, has exactly four fields:

| Field | Type | Used by | Purpose |
|---|---|---|---|
| `kind` | enum {data, ack, nak} | P2, P3 | Distinguishes a data frame from a bare control (ACK) frame |
| `seq` | seq_nr (0..MAX_SEQ) | P3 | 1-bit sequence number identifying which frame this is |
| `ack` | seq_nr | P3 (piggybacking later) | Acknowledgement number; in pure stop-and-wait the ACK is implicit |
| `info` | packet (MAX_PKT=1024 bytes) | all | The network-layer packet; unused in control frames |

The sender and receiver each run an infinite `while(true)` loop. The discipline that makes the protocols *correct* is which events they handle and what they do with the `seq` field. `code/main.py` implements all three as Python coroutines driven by a shared event queue so you can watch the alternation happen.

### Protocol 1 — Utopia: the degenerate baseline

Utopia assumes the channel never damages or loses a frame, the receiver is infinitely fast, and the network layer always has data. The sender loop is three lines: fetch a packet, copy it into `s.info`, call `to_physical_layer(&s)`. The receiver loop waits for `frame_arrival`, pulls the frame, and passes `r.info` to its network layer. No sequence numbers, no ACKs, no timer — `MAX_SEQ` is not even defined. It is the structure every later protocol extends, and it corresponds roughly to an unacknowledged connectionless service that offloads all reliability to higher layers. Utopia fails the instant the receiver is slower than the sender: frames pile up and overflow whatever buffer the receiver has, with no feedback path to slow the sender down.

### Protocol 2 — stop-and-wait on an error-free channel: flow control via ACK

Protocol 2 keeps the error-free assumption but admits that the receiver has finite buffering and finite processing speed. The fix is feedback: after the receiver delivers a packet to its network layer, it sends a little dummy ACK frame back. The sender, after `to_physical_layer(&s)`, immediately calls `wait_for_event` and blocks until that ACK arrives. Only then does it loop back to fetch the next packet. Data traffic is simplex, but *frames* travel both ways, so a half-duplex physical channel suffices. The sender does not even inspect the ACK's contents — there is only one thing it can be.

This is the textbook's first flow-control protocol, and it is the simplest possible instance of the broader sliding-window family with a window of size 1. Its weakness is the continuing assumption that the channel is error-free: lose a data frame or an ACK and the protocol hangs forever (no timer) or — if you naively add a timer without a sequence number — silently duplicates packets. The SVG in `assets/simplex-stop-and-wait.svg` draws the strict send/ACK/send/ACK alternation and labels the two failure points (lost data frame, lost ACK) that motivate Protocol 3.

### The fatal flaw: why a timer alone is not enough

The textbook poses the puzzle explicitly: "add a timer to Protocol 2, have the receiver ACK only intact frames, and resend on timeout." At first glance this looks complete. It is not. Walk the canonical failure trace, which `code/main.py`'s `scenario_lost_ack_no_seq()` reproduces verbatim:

1. Sender transmits packet 1; receiver receives it intact, delivers it to its network layer, sends ACK.
2. The ACK is lost in the channel.
3. The sender's timer expires; assuming its data was lost, it retransmits packet 1.
4. The receiver gets the retransmission, has no way to know it is a duplicate, and delivers packet 1 to its network layer a second time.

The network layer on the receiving side has no notion of "lost or duplicated" — the data link layer's contract is to deliver an *identical* stream of packets. A silent duplicate violates that contract and, for a file transfer, corrupts the file undetectably. The missing ingredient is a way for the receiver to distinguish a frame it is seeing for the first time from a retransmission of one it has already accepted.

### Protocol 3 — stop-and-wait on a noisy channel: 1-bit sequence numbers + timer

Protocol 3 adds a `seq` field and a timer. The question the textbook answers rigorously is: *how many bits of sequence number are needed?* The argument:

- The only ambiguity at any instant is between frame *m* and its direct successor *m+1*.
- If the sender is considering transmitting *m+1*, it has already received an ACK for *m*, which means *m* was correctly received *and* its ACK reached the sender — otherwise the sender would still be retrying *m*.
- Therefore the receiver never has to disambiguate *m−1* from *m+1*; only *m* from *m+1*.
- A single bit (0, 1, 0, 1, ...) suffices. The receiver expects a particular bit next; a frame with the expected bit is new (accept, flip the expected bit, ACK), and a frame with the *other* bit is a stale retransmission (silently re-ACK it, do not deliver).

The sender's loop now: fetch packet, set `s.seq = next_frame_to_send`, send, `start_timer`, `wait_for_event`. On `frame_arrival` (the ACK arrived): `stop_timer`, advance `next_frame_to_send` via the circular `inc()` macro. On `timeout`: resend the same frame with the same `seq`, restart the timer. The receiver's loop: `wait_for_event`; on `frame_arrival` with the expected `seq`, deliver to network layer, send an ACK, flip `frame_expected`; on `frame_arrival` with the wrong `seq`, send the ACK again but do not deliver; on `cksum_err`, do nothing (the sender's timer will fire).

### Worked trace: lost ACK with sequence numbers

Re-run the lost-ACK scenario under Protocol 3 (`code/main.py` → `scenario_lost_ack_with_seq()`):

| Step | Sender action | Channel | Receiver state (`frame_expected`) |
|---|---|---|---|
| 1 | Send frame seq=0, start timer | frame 0 in flight | expects 0 |
| 2 | — | frame 0 delivered, ACK sent | delivered pkt 0, flips to expecting 1, sends ACK |
| 3 | timer still running | **ACK lost** | — |
| 4 | timeout → resend seq=0 | frame 0 (dup) in flight | still expects 1 |
| 5 | — | dup frame 0 arrives | seq=0 ≠ expected 1 → **discard, re-ACK**, do not deliver |
| 6 | ACK arrives | ACK delivered | — |
| 7 | stop timer, advance to seq=1 | — | — |

No duplicate reaches the network layer. The 1-bit sequence number turned a silent corruption into a harmless re-ACK. The symmetric case — a damaged data frame — is even simpler: the receiver sees `cksum_err`, sends nothing, the sender times out and resends with the *same* `seq`, and the receiver now sees the expected bit for the first time and accepts it.

### Worked numeric example: link utilization

Stop-and-wait's efficiency is bounded by the round-trip cost. With frame transmission time `T_frame = L/R`, one-way propagation `T_prop`, ACK time `T_ack`, and processing `T_proc`:

```
U = T_frame / (T_frame + 2·T_prop + T_ack + T_proc)
```

Take a 1 Mbit/s link, 1000-bit frames, 500 ms one-way propagation (a geostationary satellite hop), and a negligible 40-bit ACK:

- `T_frame = 1000 / 1e6 = 1.0 ms`
- `2·T_prop = 1000 ms`
- `U ≈ 1.0 / 1001 ≈ 0.001` — one tenth of one percent.

This is why stop-and-wait is taught as the correctness baseline but never used on long-fat pipes; sliding window with window `w` lifts utilization to roughly `min(1, w·T_frame / RTT)`. The same 1-bit-sequence-number *correctness* argument generalizes: for a window of size `w` you need `w+1` distinct sequence numbers, so stop-and-wait (w=1) needs exactly 2 — the 1 bit.

### State machine summary

| Sender state | Trigger | Action | Next state |
|---|---|---|---|
| WAIT_FOR_ACK | `frame_arrival` (ACK) | `stop_timer`, `inc(next_frame_to_send)` | READY |
| WAIT_FOR_ACK | `timeout` | resend same `seq`, `start_timer` | WAIT_FOR_ACK |
| READY | `network_layer_ready` | build frame with `seq=next_frame_to_send`, send, `start_timer` | WAIT_FOR_ACK |

| Receiver state | Trigger | Action |
|---|---|---|
| EXPECT(seq) | `frame_arrival`, `r.seq == seq`, CRC ok | deliver to network layer, send ACK, flip `seq` |
| EXPECT(seq) | `frame_arrival`, `r.seq != seq`, CRC ok | resend ACK (duplicate), keep `seq` |
| EXPECT(seq) | `cksum_err` | do nothing (await sender timeout) |

`code/main.py` implements exactly these tables as a discrete-event simulator with injectable loss/damage, so you can drive each transition and read the printed trace.

## Build It

1. Open `code/main.py`. It defines a `Frame` dataclass (`kind`, `seq`, `ack`, `info`), a `Link` that can lose or damage frames with set probabilities, and a `StopAndWaitSimulator` that runs the sender/receiver event loops against a shared clock.
2. Run `python3 code/main.py`. The default demo executes three scenarios back to back: clean channel (Protocol 2 behavior), lost-ACK without sequence numbers (the duplicate-delivery bug), and lost-ACK with 1-bit sequence numbers (Protocol 3, correct).
3. Read the printed trace column-by-column: each line is `[t=Xms] SENDER: ... | LINK: ... | RECEIVER: ...`. Confirm that in scenario 2 the receiver's `deliver()` fires twice for the same packet, and in scenario 3 it fires once with a `discarded duplicate` line in between.
4. Edit `Link(loss_prob=..., damage_prob=...)` to inject damaged frames and rerun. Verify the receiver's `cksum_err` path triggers a timeout-driven resend rather than a duplicate delivery.
5. Increase `T_prop` in the simulator to a satellite-like 500 ms and rerun the clean scenario; the printed utilization should collapse to the ~0.1% computed above, demonstrating why stop-and-wait is correct but unscalable.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm Protocol 2 stops sender overrun | Sender blocks on `wait_for_event` after each send until ACK arrives | Strict alternation S→R→S→R; no second send before an ACK |
| Reproduce the duplicate-delivery bug | Lost ACK, no `seq` field, receiver `deliver()` called twice for the same packet | The trace shows the second delivery happening with no error flag — silent corruption |
| Verify the 1-bit fix | Same lost-ACK scenario with `seq` on; receiver logs `discarded duplicate` and delivers once | Exactly one `deliver()` per packet; re-ACK sent for the duplicate |
| Handle a damaged frame | Inject `damage_prob>0`; receiver reports `cksum_err`, sends nothing, sender times out and resends | Resend carries the same `seq`; receiver accepts it as new on the retry |
| Justify 1-bit sufficiency | Trace shows the only ambiguity resolved is *m* vs *m+1* | No state where the receiver must choose between *m−1* and *m+1* |
| Measure utilization | Print `U = T_frame / (T_frame + 2·T_prop + T_ack)` for a given config | Long-fat pipe gives U ≪ 1%; matches the closed-form number |

## Ship It

Produce one artifact under `outputs/`: an annotated trace (`prompt-simplex-stop-and-wait.md`) consisting of the three simulator scenarios — clean, lost-ACK-no-seq, lost-ACK-with-seq — with each line labelled by which textbook event fired (`frame_arrival`, `cksum_err`, `timeout`) and a one-paragraph verdict per scenario stating whether a duplicate reached the receiver's network layer. Start from the raw output of `python3 code/main.py` and annotate by hand; the artifact is the evidence that the 1-bit sequence number actually closes the hole.

## Exercises

1. Run `scenario_lost_ack_no_seq()` and capture the exact line at which the duplicate is delivered. Then run `scenario_lost_ack_with_seq()` and identify the line where the duplicate is instead discarded. State which field value the receiver compared to make that decision.
2. Modify the simulator so that *both* a data frame and its retransmission are damaged (two consecutive `cksum_err` events at the receiver). Show that the sender retransmits a third time, the receiver finally accepts, and no duplicate is ever delivered. How many timer expirations occur?
3. Prove the textbook's sufficiency claim concretely: construct a trace in which the sender is about to transmit frame *m+1* and enumerate every precondition that must hold. Use it to argue the receiver never has to distinguish *m−1* from *m+1*, only *m* from *m+1*.
4. Set `T_prop = 250 ms`, `R = 1 Mbit/s`, `L = 4000 bits`, `T_ack = 0`. Compute the closed-form utilization and confirm the simulator's measured `U` matches. Then double `L` to 8000 bits and predict the new `U` before running it.
5. A colleague proposes saving one bit of header by reusing the `ack` field as the sequence number in stop-and-wait (since ACKs and data never collide in time). Describe the scenario — a lost ACK followed by a sender timeout — that breaks this optimization, and explain why the textbook keeps `seq` and `ack` as separate fields even for Protocol 3.
6. Replace the 1-bit `seq` with a 2-bit `seq` (0,1,2,3 cycling) but keep window size 1. Show that the protocol is still correct but that the receiver's "expected next" check now has to compare against one value out of four instead of one out of two. Argue whether the extra bit buys anything in stop-and-wait, and predict what window size it *would* enable in a sliding-window protocol.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Stop-and-wait | "send one, wait one" | An ARQ discipline where the sender transmits a single frame and blocks until an ACK for that frame arrives; sliding window with w=1 |
| Sequence number (`seq`) | "a packet ID" | A small counter in the frame header letting the receiver tell a fresh frame from a retransmission; 1 bit is provably enough for stop-and-wait |
| ACK | "the reply" | A control frame (`kind=ack`) the receiver sends to release the sender; in Protocol 2 it is a bare dummy, in Protocol 3 it acknowledges a specific `seq` |
| `frame_arrival` | "a frame came in" | The event the data link layer's `wait_for_event` returns when an intact frame reaches the physical layer |
| `cksum_err` | "a bad frame" | The event returned when the CRC/checksum of an arrived frame is wrong; the frame is discarded silently and no ACK is sent |
| `timeout` | "the timer fired" | The sender's retransmission timer expiring before an ACK arrived; triggers a resend with the same `seq` |
| `inc()` macro | "add one" | Circular increment of a sequence number modulo `MAX_SEQ+1`; for stop-and-wait `MAX_SEQ=1` so it toggles 0↔1 |
| Utopia (Protocol 1) | "the dumb one" | The degenerate baseline: no flow control, no error control, no sequence numbers; only correct on an error-free channel with an infinite-speed receiver |
| Utilization (U) | "how busy the link is" | Fraction of time the link carries useful data; for stop-and-wait `U = T_frame / (T_frame + 2·T_prop + T_ack + T_proc)`, which collapses on long-fat pipes |
| Duplicate delivery | "a resend bug" | The silent corruption that occurs when a lost ACK causes a retransmission the receiver cannot distinguish from a new frame — the failure the 1-bit `seq` field exists to prevent |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 3.3 ("Elementary Data Link Protocols"), Protocols 1–3 and the `protocol.h` declarations of Fig. 3-11.
- RFC 9293 — *Transmission Control Protocol (TCP)*, Section 3.8 on retransmission timeout and the simplest send-one-ACK-one discipline, as a real-world descendant of stop-and-wait ARQ.
- ITU-T X.25 — *Interface between Data Terminal Equipment (DTE) and Data Circuit-terminating Equipment (DCE)*, LAPB, which implements a 1-bit-window stop-and-wait variant on error-free multi-protocol links.
- Bertsekas & Gallager, *Data Networks*, 2nd ed., Chapter 2 on the ARQ family (stop-and-wait, go-back-N, selective repeat) and the sequence-number lower bounds for each.
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, Chapter 6 on link-layer reliability and the correctness argument for 1-bit alternating-bit protocols.
- The classic "Alternating Bit Protocol" — Bartlett, Scantlebury & Wilkinson, *Comm. ACM*, 1969 — the original published instance of the 1-bit sequence-number scheme that Protocol 3 reinvents.
