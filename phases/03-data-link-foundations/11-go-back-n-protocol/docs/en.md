# Implementing Go-Back-N ARQ

> Go-Back-N is the simplest pipelined sliding-window ARQ protocol: the sender keeps up to **W = 2ⁿ − 1** frames outstanding on a link with an **n-bit sequence-number field** (the textbook's Protocol 5), while the receiver runs a **window of size 1** — it accepts *only* the next in-order frame and silently discards everything else. Each data frame carries a **seq** field, a piggybacked **ack** field (cumulative: "ack k means 0..k−1 are fine"), and a checksum; a damaged or out-of-order frame is dropped with no NAK. On **timeout** of the oldest unacknowledged frame the sender does not resend just that frame — it rewinds to `ack_expected` and retransmits the **entire window** in sequence. The window size must cover the **bandwidth-delay product**: the textbook's 50 kbps satellite link with 250 ms one-way delay holds 12.5 frames, so the rule **W = 2·BD + 1 = 26** keeps the pipe full; stop-and-wait (W=1) on that link wastes ~96% of the bandwidth. Go-Back-N trades receiver simplicity (no reordering buffer) for wasted bandwidth on lossy links, which is exactly why Selective Repeat exists as the alternative. This lesson builds a runnable Protocol-5 simulator with the circular `between()` test, piggybacked cumulative ACKs, per-frame timers, and the go-back-N retransmit rule, then measures link utilization against the W/(1+2·BD) bound.

**Type:** Build
**Languages:** Python
**Prerequisites:** Stop-and-wait ARQ and parity/checksum basics (Phase 3 lessons on error detection and sliding-window fundamentals), sequence numbers, the notion of a bandwidth-delay product
**Time:** ~80 minutes

## Learning Objectives

- Explain why stop-and-wait squanders bandwidth on a long-fat link and derive the window size **W = 2·BD + 1** that keeps a pipe full.
- Implement the circular `between(a, b, c)` sequence-number test on an n-bit ring and justify why it is needed when ACKs wrap past MAX_SEQ.
- Trace a Go-Back-N run where one frame is lost: state which frames the receiver discards, which cumulative ACK is returned, and what the sender resends on timeout.
- Distinguish the **sender window** (up to MAX_SEQ outstanding) from the **receiver window** (exactly 1) and explain why MAX_SEQ — not MAX_SEQ+1 — is the outstanding-frame limit.
- Compute link utilization **U ≤ W / (1 + 2·BD)** and predict when Go-Back-N collapses under loss.
- Identify the evidence — piggybacked ack field, in-order acceptance, full-window resend — that distinguishes Go-Back-N from Selective Repeat.

## The Problem

A ground station pumps telemetry over a 50 kbps satellite transponder with a 500 ms round-trip time. Frames are 1000 bits each. The naive stop-and-wait sender transmits frame 0 at t=0; the frame finishes leaving the antenna at t=20 ms, lands at the satellite at t=270 ms, and the ACK returns at t=520 ms. For 500 of those 520 ms the sender sits idle — **96% of the transponder is wasted**. The engineer's instinct is to "just send more frames," but that raises two questions the data-link layer must answer correctly: *how many* frames may be in flight, and *what happens* when one of them is corrupted by rain fade halfway through the burst?

Send too few and you starve the pipe. Send too many and the sequence-number space wraps and you can no longer tell a fresh frame from a retransmission. And when frame 2 of a 7-frame burst is lost, frames 3–6 still arrive at the receiver — out of order. The data-link layer is contractually obliged to hand packets to the network layer **in sequence**, so something must decide whether to buffer those good-but-early frames or throw them away. Go-Back-N picks the throw-them-away option for simplicity; the cost is retransmitting frames that were received fine. This lesson shows exactly how that trade-off plays out, frame by frame.

## The Concept

### Pipelining and the bandwidth-delay product

Stop-and-wait forces the sender to block on every ACK. The fix is **pipelining**: allow up to **W** unacknowledged frames in flight before blocking. To size W, count how many frames fit inside the link at once — the **bandwidth-delay product** **BD**:

```
BD = (bandwidth in bits/s × one-way delay in s) / frame_bits
```

BD is the number of frames "in the wire" in one direction. The textbook rule is **W = 2·BD + 1**: twice BD because the ACK must travel back, plus one because the receiver cannot ACK a frame until it has fully arrived. For the 50 kbps / 250 ms / 1000-bit satellite link, BD = 12.5, so W = 26. With W = 26 the sender finishes frame 25 at t = 520 ms — exactly when ACK 0 returns — and from then on every new frame is matched by a returning ACK, so the sender never blocks. See `code/main.py`'s `utilization()` for the matching link-budget arithmetic.

| Window W | Utilization U ≤ W/(1+2·BD) | Satellite-link meaning |
|---|---|---|
| 1 (stop-and-wait) | 1/26 ≈ 3.8% | 96% of bandwidth idle |
| 7 (MAX_SEQ, 3-bit) | 7/26 ≈ 26.9% | sender blocks 73% of the time |
| 26 (2·BD+1) | 26/26 = 100% | pipe stays full, no blocking |

### The sequence-number field and the `between()` test

Go-Back-N uses an **n-bit sequence field**, so sequence numbers cycle through **0 .. 2ⁿ−1** (MAX_SEQ = 2ⁿ−1). The textbook example uses n = 3, so MAX_SEQ = 7 and there are 8 distinct values. The window slides around this ring, and because ACKs are cumulative, a sender must decide whether an incoming ACK value falls *inside* its current outstanding window — which wraps past 7 back to 0. The Protocol-5 helper `between(a, b, c)` returns true iff **b** lies on the clockwise arc from **a** (inclusive) to **c** (exclusive) on the ring:

```
between(a,b,c) =  (a <= b < c)  OR  (c < a <= b)  OR  (b < c < a)
```

The three clauses cover the non-wrapping case (`a..c` does not cross 7), and the two wrapping cases. Without this test, an ACK of 2 arriving when `ack_expected = 6` and `next_frame_to_send = 1` would be misread. `code/main.py` implements `between()` exactly and exercises all three clauses.

### Why at most MAX_SEQ frames may be outstanding

There are MAX_SEQ+1 sequence numbers (0..7) but only MAX_SEQ (7) may be outstanding. The textbook's scenario shows why: if a sender shipped 8 frames 0..7 and got an ACK for 7, it cannot tell whether that ACK means "all eight arrived" or "all eight were lost and this is a stale re-ACK of the previous batch's 7." Limiting the window to MAX_SEQ removes the ambiguity — the next batch of outstanding frames always uses sequence numbers disjoint from the previous batch, so any ACK is unambiguous. (Selective Repeat tightens this further to MAX_SEQ/2 because its receiver buffers out-of-order frames.)

### Frame format and piggybacked cumulative ACKs

A Protocol-5 data frame carries three load-bearing fields plus a checksum:

| Field | Meaning |
|---|---|
| `seq` | sequence number of THIS frame's payload (n bits) |
| `ack` | piggybacked **cumulative** ACK: "I have correctly received everything through ack−1; send me ack next" |
| `info` | the network-layer packet (payload) |
| `cksum` | error-detecting code over seq+ack+info; a mismatch ⇒ discard |

Piggybacking means ACKs ride free on the next data frame heading the other way, instead of consuming a separate tiny ACK frame — important on a satellite link where every frame costs 20 ms of transmit time. The ACK is **cumulative**, so `ack = k` acknowledges 0..k−1 at once; a single late ACK can release the entire window. `code/main.py`'s `Frame` dataclass models exactly these fields and seals each frame with a CRC-style checksum before transmission.

### The sender state machine

The sender keeps three sequence-number pointers that bound its window:

| Pointer | Role |
|---|---|
| `ack_expected` | lower window edge — oldest unacknowledged frame |
| `next_frame_to_send` | upper window edge — next sequence number to transmit |
| `frame_expected` | receiver-side pointer, used only to compute the piggyback ACK for the reverse direction |

On a `network_layer_ready` event the sender fetches a packet, buffers it at `next_frame_to_send`, transmits, starts that frame's timer, and advances the upper edge. On a `frame_arrival` event it runs the `between()` loop, sliding `ack_expected` forward for every ACK inside the window and stopping each freed frame's timer. The window is full when `(next_frame_to_send − ack_expected) mod 2ⁿ == MAX_SEQ`; then the network layer is **disabled** so it stops offering packets, which is the flow-control half of the protocol. `code/main.py`'s `GoBackNSender` reproduces this state, including the `enable/disable network layer` decision in `can_send()`.

### The receiver: window of 1, in-order-only acceptance

This is the defining simplification of Go-Back-N. The receiver tracks a single pointer `frame_expected`. When a frame arrives it is accepted **only if** `seq == frame_expected` and the checksum is valid; then the payload is handed to the network layer and `frame_expected` advances. **Any other frame — corrupted, duplicate, or simply ahead of the gap — is silently discarded.** The receiver does not buffer, does not NAK, and does not even look at the seq of a frame it drops. It always returns a cumulative ACK equal to `frame_expected` ("I am still waiting for this one"), which is why a lost frame produces a stream of identical re-ACKs that eventually let the sender's timer do its job. `code/main.py`'s `GoBackNReceiver.receive()` is this logic in five lines.

### Timeout: the go-back-N retransmit rule

When the timer for the oldest outstanding frame (`ack_expected`) expires, the sender does **not** resend just that frame. It rewinds `next_frame_to_send` to `ack_expected` and retransmits **every** outstanding frame in order:

```
next_frame_to_send = ack_expected
for each outstanding frame:
    send_data(next_frame_to_send, ...)
    inc(next_frame_to_send)
```

This is the "go back N" — back up N frames and replay them. It works because the receiver threw away everything after the gap, so resending the whole window is the only way to fill it in. The cost is obvious: if frame 2 of a 7-frame window is lost, frames 3–6 — which already arrived and were discarded — get retransmitted anyway. On a clean link this almost never happens; on a 20%-loss link it dominates the traffic, which is precisely the regime where Selective Repeat wins. `code/main.py`'s `timeout()` returns the full resend list, and the `[Timeout behaviour]` block in `main()` prints it so you can see the whole window rewind.

### Worked example: frame 2 lost, W = 7

`assets/go-back-n-protocol.svg` draws this run as a timing diagram. The sender ships frames 0..6 (seq 7 is reserved outside the window). Frame 2 is lost in the channel. Frames 3, 4, 5, 6 arrive at the receiver, but `frame_expected` is still 2, so each is dropped and the receiver re-ACKs 2. ACK 2 keeps returning (cumulative). When frame 2's timer fires, the sender goes back N: it resends 2, 3, 4, 5, 6 in order. This time frame 2 arrives, the receiver accepts it, advances to 3, and immediately accepts the resent 3, 4, 5, 6 in sequence — finally returning ACK 7. The simulator in `code/main.py` reproduces this exact pattern under a 20% loss model and prints every drop, re-ACK, timeout, and resend.

## Build It

1. Open `code/main.py`. Note the three building blocks: `between()` for ring arithmetic, `Frame` with its `seal()`/`is_valid()` checksum, and the `GoBackNSender`/`GoBackNReceiver` dataclasses.
2. Run `python3 code/main.py`. First confirm the satellite-link utilization table: W=1 → 3.8%, W=7 → 26.9%, W=26 → 100%. These are the numbers that motivate pipelining.
3. Read the `[between]` block — all three clauses return True, proving the circular test handles the wrap past MAX_SEQ.
4. Run the `[Simulation]` block. Trace the log: frames 0..6 are transmitted, several are dropped as out-of-order while the receiver waits on seq 2, then `*** TIMEOUT seq=2` triggers a full-window resend. Confirm the receiver's final `delivered` list equals `[0,1,2,3,4,5,6,7]` in order.
5. Edit `loss_prob` from 0.20 to 0.45 and rerun. Watch the tick count and the number of `*** TIMEOUT` events climb — this is Go-Back-N's failure mode.
6. The `[Timeout behaviour]` block constructs a sender with `ack_expected=2`, `next_frame_to_send=6` and calls `timeout()`. Confirm it resends `[2,3,4,5]` — the full window, not just frame 2.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm pipelining fills the pipe | Utilization table for W=1,7,26 on the satellite link | W=26 hits 100%; W=1 is ~4%, matching the textbook's 96% idle |
| Verify the circular ACK test | `between()` results for the wrap and non-wrap cases | All three clauses handled; an ACK of 2 with window [6..1] is correctly inside |
| Show the go-back-N rewind | `timeout()` output with `ack_expected=2, next_frame_to_send=6` | Resend list is `[2,3,4,5]` — the whole window, in order |
| Demonstrate in-order delivery | Final `delivered` list from the simulator | Equals the input `[0..7]` exactly, in sequence, despite losses |
| Measure loss sensitivity | Tick count and timeout count at loss 0.05 vs 0.20 vs 0.45 | Ticks grow super-linearly with loss; at 0.45 the protocol is clearly thrashing |
| Distinguish from Selective Repeat | Receiver discards out-of-order frames; sender resends the full window | No receiver buffering, no NAK — the textbook signature of GBN |

## Ship It

Produce one artifact under `outputs/` (start from `outputs/prompt-go-back-n-protocol.md`):

- An annotated trace of a Go-Back-N run over 8 frames with one injected loss, showing the sender window, each cumulative ACK, the timeout, the full-window resend, and the final in-order delivery.
- A link-budget card: for a link of your choosing (e.g. 1 Gbps fiber, 1 ms one-way, 12,000-bit frames) compute BD, the recommended W = 2·BD+1, and the stop-and-wait utilization, and state whether a 3-bit sequence field suffices.
- A one-paragraph decision rule: when Go-Back-N is the right choice (clean, high-BD, memory-constrained receiver) versus when Selective Repeat wins (lossy link, cheap memory).

Start from the printed output of `code/main.py` and annotate the failure mode you tested.

## Exercises

1. On a 1 Gbps fiber link with 1 ms one-way delay and 12,000-bit frames, compute BD, the recommended window W = 2·BD+1, and the stop-and-wait utilization. Can a 3-bit sequence field (MAX_SEQ=7) even express that window? If not, how many bits are needed?
2. A sender has `ack_expected = 6`, `next_frame_to_send = 1` (window wraps past 7). An ACK frame arrives with `ack = 0`. Trace `between(6, 0, 1)` clause by clause and state which frames are released. Now suppose `ack = 4` — is it inside the window?
3. In the simulator, set `loss_prob = 0.0` and run. Then set `loss_prob = 0.40`. Report the ratio of total transmissions to useful deliveries in each case and explain why Go-Back-N degrades super-linearly with loss.
4. Frame 2 is lost, but frames 3, 4, 5, 6 arrive correctly and are dropped by the receiver. After the timeout the sender resends 2, 3, 4, 5, 6. The receiver accepts 2 and then immediately accepts 3–6. Why does it not need to re-buffer them? What single field lets it know 3 is now expected?
5. The textbook insists at most MAX_SEQ (not MAX_SEQ+1) frames may be outstanding. Construct the ambiguity scenario with MAX_SEQ = 7: the sender ships 0..7, gets an ACK for 7, ships another 0..7, gets another ACK for 7. Explain the two interpretations the sender cannot distinguish, and how limiting the window to 7 removes the ambiguity.
6. Modify `GoBackNReceiver` to accept a 1-bit "NAK" event on out-of-order arrival and have the sender resend only `ack_expected` immediately. Measure the tick reduction at loss 0.20. Is what you built still Go-Back-N, or have you started implementing Selective Repeat? Justify.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Go-Back-N | "the sliding window one" | A pipelined ARQ with sender window ≤ MAX_SEQ and **receiver window = 1**: only in-order frames are accepted; on timeout the whole outstanding window is resent |
| Sliding window | "send ahead" | A protocol shape where the sender keeps W unacknowledged frames in flight; the window of valid sequence numbers slides forward as ACKs arrive |
| Bandwidth-delay product | "pipe size" | bandwidth × one-way delay, in bits or frames; the number of frames that fit in the wire at once, which sets the window needed to fill the link |
| Piggybacked ACK | "free ACK" | A cumulative ACK riding in the `ack` field of a data frame heading the reverse direction, avoiding a separate ACK frame |
| Cumulative ACK | "ack everything up to N" | An ACK value k meaning "0..k−1 received correctly; send k next" — one number releases the whole prefix |
| `between(a,b,c)` | "the ring test" | The circular test that decides whether ACK b falls inside the sender's outstanding window [a, c) when that window wraps past MAX_SEQ |
| MAX_SEQ | "max sequence" | 2ⁿ−1; both the largest sequence number and the maximum number of outstanding frames in Go-Back-N (one less than the sequence-space size) |
| Pipelining | "sending in bulk" | Transmitting multiple frames before blocking on an ACK, to keep a high-BD link busy |
| Go back N | "rewind and replay" | On timeout, reset `next_frame_to_send` to `ack_expected` and retransmit every outstanding frame in order |
| Selective Repeat | "the other one" | The alternative ARQ with a receiver window > 1 that buffers out-of-order frames and resends only the lost one — the trade-off Go-Back-N refuses |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.4.2** — "A Protocol Using Go-Back-N," including Protocol 5 source and the satellite-link utilization example.
- **RFC 9293** — TCP Congestion Control / state machine references; TCP's cumulative ACK and sliding window are the Internet-scale descendant of these data-link ideas.
- **Stallings, *Data and Computer Communications*, Ch. 7** — Error control and sliding-window ARQ with worked utilization derivations.
- **Kurose & Ross, *Computer Networking: A Top-Down Approach*, Ch. 3.4** — Reliable data transfer, pipelining, and the Go-Back-N versus Selective Repeat comparison.
- **Bertsekas & Gallager, *Data Networks*, Ch. 2** — Rigorous treatment of ARQ throughput and the bandwidth-delay product.
- **ITU-T Q.921 / LAPB** — A real link-layer protocol (X.25 Layer 2) implementing Go-Back-N with modulo-8 and modulo-128 sequence spaces.
- **RFC 1662** — PPP in HDLC-like framing; shows the flag/sequence/checksum frame structure that real Go-Back-N link layers carry.
