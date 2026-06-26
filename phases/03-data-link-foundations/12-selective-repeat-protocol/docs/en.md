# Implementing Selective Repeat ARQ

> **Selective Repeat** is the sliding-window ARQ that retransmits *only* the lost or damaged frame, not everything after it. Unlike Go-Back-N (Protocol 5, single-frame receiver window), the receiver keeps a **fixed-size window of size `W`** and buffers out-of-order frames in a per-slot buffer pool (`in_buf[NR_BUFS]`) tagged with an `arrived[]` bit map. Each outstanding frame owns an **independent timer** (simulated in software as a linked list of `(ticks_to_go, frame, next)` nodes off one hardware clock), so only the timed-out frame is resent. The headline correctness constraint is the sequence-number rule: with an `n`-bit sequence space `MAX_SEQ = 2ⁿ − 1`, the window must satisfy `W ≤ (MAX_SEQ + 1) / 2` — otherwise an old retransmitted frame can fall inside the receiver's *new* window and be accepted as fresh data, a textbook failure mode the lesson reproduces. Selective Repeat is paired with **NAKs** (one per lost frame, gated by a `no_nak` flag) to trigger retransmission before the timer expires, plus a separate **ack timer** so pure acknowledgements fire even with no reverse traffic to piggyback on. Real deployments include SCTP's selective acknowledgement (SACK) chunks (RFC 9260) and TCP SACK options (RFC 2018, kind 5, the four 32-bit LE/RE edge blocks). This lesson builds a runnable Protocol-6 simulator with a lossy channel, NAK generation, per-frame timers, and an explicit demonstration of the window-overlap bug when the rule is violated.

**Type:** Build
**Languages:** Python
**Prerequisites:** Stop-and-wait ARQ and Go-Back-N (Phase 3 lessons on sliding-window basics), CRC/checksum error detection, circular sequence-number arithmetic
**Time:** ~85 minutes

## Learning Objectives

- State and prove the Selective Repeat window constraint `W ≤ (MAX_SEQ + 1) / 2`, and run the simulator with `W` one larger to observe duplicate-frame acceptance.
- Trace a frame through the receiver's `between()` circular-range check, the `arrived[]` bit map, the `in_buf[]` pool, and the in-order delivery loop that drains contiguous frames to the network layer.
- Distinguish the five event types (`frame_arrival`, `cksum_err`, `timeout`, `network_layer_ready`, `ack_timeout`) and the action each triggers in Protocol 6.
- Explain why NAKs are gated by `no_nak` (one NAK per lost frame) and why a separate ack timer is needed when reverse traffic is absent.
- Compare Go-Back-N (retransmit all, no receiver buffering) versus Selective Repeat (retransmit one, receiver buffers `W`) on bandwidth vs. memory trade-off, and pick one for a given link error rate.
- Read the SACK option layout (RFC 2018 kind 5, LE/RE edge blocks) and map it back to the `arrived[]` bit map the simulator maintains.

## The Problem

A satellite downlink runs at 2 Mbps with a 500 ms round-trip propagation delay. The link's raw bit-error rate is 1×10⁻⁵, so a 1500-byte frame (12,000 bits) has roughly a 11% chance of corruption. With Go-Back-N and a window of 8, every single bit error forces the sender to rewind and retransmit up to 8 frames — and on a 500 ms RTT the timer that catches the loss adds another half-second of idle pipe before the rewind even starts. Effective throughput collapses to a few percent of the channel rate, and the operator watches the link utilization gauge sit near zero even though the modem lights are blinking.

The operator needs the sender to retransmit *just the one bad frame*, not the seven good ones queued behind it, and to do it the instant the loss is detected — ideally without waiting for a timeout. That is exactly what Selective Repeat provides: per-frame timers, receiver-side buffering of out-of-order frames, and NAK-driven fast retransmit. The cost is receiver memory (`W` frame buffers) and a stricter sequence-number budget. This lesson builds the protocol that solves the satellite problem, then shows the precise way it breaks if you relax the window rule.

## The Concept

### Sender and receiver windows in Selective Repeat

Both sides keep a window, but their shapes differ.

| | Sender window | Receiver window |
|---|---|---|
| Size | Grows `0 → W`, capped at `W = NR_BUFS` | Fixed at `W = NR_BUFS`, always full |
| Slides on | Cumulative ack of lower edge | In-order delivery of lower edge |
| Buffers | `out_buf[]` for unacked sent frames | `in_buf[]` per slot + `arrived[]` bit map |
| Per-frame state | One timer per outstanding frame | `arrived[i]` boolean per slot |

In Protocol 6, `NR_BUFS = (MAX_SEQ + 1) / 2`, so with `MAX_SEQ = 7` (3-bit sequence numbers) both windows are 4. The sender's window grows as it transmits and contracts as piggybacked acks arrive; the receiver's window is fixed at 4, and its lower edge (`frame_expected`) advances only when a contiguous run has been delivered to the network layer. `code/main.py` exposes both windows as attributes you can print after each event.

### The frame format and the `between()` circular check

Every frame carries a kind, a sequence number, and a piggybacked ack:

| Field | Meaning | Notes |
|---|---|---|
| `kind` | `data` / `ack` / `nak` | NAKs are unique to Selective Repeat + ack-timer protocols |
| `seq` | Sequence number | Only meaningful for `data` frames |
| `ack` | Piggyback ack | Cumulative: "I have everything through `ack`" |
| `info` | Packet payload | Stored in `in_buf[seq % NR_BUFS]` |

The crux is the circular range test `between(a, b, c)` returning true when `a ≤ b < c` on the ring of size `MAX_SEQ + 1`. The textbook's compact form is:

```
return ((a <= b) && (b < c)) || ((c < a) && (a <= b)) || ((b < c) && (c < a));
```

The receiver accepts a data frame only if `between(frame_expected, r.seq, too_far) && !arrived[r.seq % NR_BUFS]`. The modulo maps the sequence number onto a physical buffer slot — and that mapping is only unambiguous because of the window-size rule below.

### Why the window must be `W ≤ (MAX_SEQ + 1) / 2`

This is the single most important correctness property. Walk through the disaster scenario from the textbook with `MAX_SEQ = 7`:

1. Sender window `[0..6]`, receiver window `[0..6]`. Sender transmits 0–6; all arrive; receiver acks and slides its window to `[7, 0, 1, 2, 3, 4, 5]`.
2. **All acknowledgements are lost** (lightning hits the line). The receiver thinks all is well; the sender knows nothing.
3. Sender times out on frame 0 and retransmits it.
4. The retransmitted 0 arrives at the receiver. Because the new receiver window *contains* 0, the receiver accepts it as a **new** frame, buffers it, and later delivers a duplicate packet to the network layer. Protocol fails silently — no checksum fires, no timer trips; the network layer just gets the same packet twice.

The fix is to forbid overlap between the old and new receiver windows. With `W = (MAX_SEQ + 1) / 2`, after the receiver advances, the new window `[W .. 2W-1]` is disjoint from the old `[0 .. W-1]`. A retransmitted old frame then falls *outside* the current window and is rejected (or recognized as a duplicate via the `arrived[]` map). `code/main.py` lets you set `W = NR_BUFS + 1` and run the scenario; you will watch a duplicate frame get delivered and the in-order delivery counter jump.

### NAKs and the `no_nak` gate

A **NAK** is a negative acknowledgement sent the instant the receiver detects a gap — typically because an out-of-sequence frame arrived (`r.seq != frame_expected`) or a `cksum_err` occurred. NAKs buy speed: they trigger retransmission before the sender's timer expires, which on a 500 ms RTT can save a full timeout interval.

The `no_nak` flag enforces **one NAK per lost frame**. Without it, every subsequent out-of-order arrival would emit another NAK for the same gap, flooding the reverse channel. The flag is cleared when a NAK is sent and reset to `true` only when `frame_expected` finally advances (the gap is closed). The textbook code does exactly:

```
if ((r.seq != frame_expected) && no_nak)
    send_frame(nak, 0, frame_expected, out_buf);
```

### The ack timer: handling one-way traffic

Go-Back-N (Protocol 5) assumed piggyback acks on reverse data traffic. Selective Repeat drops that assumption. When the receiver has no data of its own to send back, it must still acknowledge received frames — otherwise the sender's timers expire and useless retransmissions fire. Protocol 6 introduces a separate **ack timer**: whenever the receiver would have piggybacked an ack but had no data frame to attach it to, it starts the ack timer; when that timer fires, a standalone `ack` frame is sent. The `ack_timeout` event is the fifth event type, and it exists solely to make Selective Repeat correct on unidirectional links.

### Per-frame timers via a single clock

Each outstanding frame needs an independent timer. Naively that means `W` hardware timers; in practice Protocol 6 simulates them with one hardware clock and a sorted linked list of pending timeouts. Each node stores `ticks_to_go` (decremented every tick), `frame` being timed, and a `next` pointer. When `ticks_to_go` hits zero the head node fires and is unlinked. `start_timer(k)` and `stop_timer(k)` scan the list to insert or remove a node. The simulator in `code/main.py` models this with a `HeapTimer` keyed by absolute fire time, which is the production shape (Linux's `timerfd` and BSD's `callout` subsystems both use heap-ordered wheels for the same reason). See `assets/selective-repeat-protocol.svg` for the timing diagram showing independent per-frame expiry.

### Worked numeric example

`MAX_SEQ = 7`, `W = NR_BUFS = 4`. Channel loses frame 1 and frame 4.

| Time | Event | Sender window | Receiver window | Buffers (`arrived[]`) |
|---|---|---|---|---|
| t0 | send 0,1,2,3 | [0..3] | [0..3] | — |
| t1 | 0 arrives, delivered | [0..3] | [0..3], `frame_expected=1` | — |
| t2 | 1 lost | [0..3] | — | — |
| t3 | 2 arrives, buffered, NAK(1) | [0..3] | [1..4] | slot2=full |
| t4 | 3 arrives, buffered | [0..3] | [1..4] | slot2,3=full |
| t5 | NAK(1) arrives, resend 1 | [0..3] | [1..4] | slot2,3=full |
| t6 | 1 arrives, deliver 1,2,3 | [0..3] | [4..7], `frame_expected=4` | — |
| t7 | 4 lost, send 5,6,7 | [4..7] | [4..7] | — |
| t8 | 5,6,7 buffered, NAK(4) | [4..7] | [4..7] | slot5,6,7=full |
| t9 | resend 4, deliver 4,5,6,7 | [4..7] | [0..3] | — |

Total retransmissions: 2 (frames 1 and 4). Go-Back-N would have retransmitted 1,2,3 and then 4,5,6,7 — eight retransmissions for two losses. The receiver paid for it with four buffer slots instead of one.

### Selective Repeat in the real world: TCP SACK and SCTP

The pure textbook protocol lives at the data-link layer, but the same idea appears higher up. **TCP Selective Acknowledgement** (RFC 2018) adds a SACK option (kind 5) listing up to four non-contiguous received blocks as LE/RE edge pairs (each a 32-bit sequence number). A sender that sees `ACK=1000, SACK=[2000:3000], [5000:6000]` knows bytes 1000–1999 and 3000–4999 are missing and retransmits only those. **SCTP** (RFC 9260) builds SACK into the base protocol as a chunk type carrying cumulative TSN plus gap-ack blocks. Both are Selective Repeat with the sequence space scaled to byte streams; the window-overlap rule shows up as the requirement that the SACK blocks stay within the send window.

## Build It

1. Read `code/main.py`. It implements `Sender` and `Receiver` classes mirroring Protocol 6, plus a `LossyChannel` that deterministically drops frames by index and a `HeapTimer` simulating per-frame timers off one virtual clock.
2. Run `python3 code/main.py`. The default demo loses frames 1 and 4 with `MAX_SEQ=7, W=4` and prints the window/buffer state after every event — it should match the worked example table above.
3. Find `W = NR_BUFS` and bump it to `NR_BUFS + 1` (i.e. violate the window rule). Re-run and watch frame 0's retransmission be accepted as a *new* frame — the network layer receives a duplicate. This is the failure mode the rule exists to prevent.
4. Toggle `use_naks = False` in the channel config. Observe that recovery now waits for the per-frame timer instead of firing on NAK; the total simulated time roughly doubles on a long-RTT link.
5. Set `reverse_traffic = False` and confirm the ack timer still drains acks, so the sender's window keeps sliding even with no data flowing back.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify the window rule | Run with `W = NR_BUFS + 1`, show a duplicate delivered | Network layer receives frame 0 twice; you can name *why* (window overlap) |
| Show NAK fast retransmit | Toggle `use_naks`, compare simulated time-to-recovery | NAK path recovers in ~1 RTT; timeout path adds a full timer interval |
| Confirm only the lost frame is resent | Print `retransmit_count` per frame after the run | Frame 1 retransmitted once, frame 4 once, all others zero |
| Verify in-order delivery | Log every `to_network_layer` call with its seq | Sequence delivered is monotonically increasing, no gaps, no duplicates (when rule holds) |
| Demonstrate ack timer on one-way traffic | `reverse_traffic = False`, check sender window slides | Sender window advances despite no reverse data frames |
| Read a SACK option | Decode the byte dump in `parse_sack_option()` | Correctly extracts LE/RE edge blocks from kind-5 TLV |

## Ship It

Author the artifact at `outputs/prompt-selective-repeat-arq.md`: a one-page prompt that asks a model to implement Protocol 6 over a lossy channel, generate NAKs on gaps, enforce `W ≤ (MAX_SEQ+1)/2`, and include a regression test that fails when the window rule is violated. The artifact is what a reviewer runs to confirm you can specify the protocol's invariants precisely.

## Exercises

1. With `MAX_SEQ = 15` (4-bit sequence numbers), what is the largest legal Selective Repeat window? Construct the lost-ack scenario where `W` one larger than that causes a duplicate delivery, and run it in the simulator to confirm.
2. Modify `LossyChannel` so that 2% of frames are *garbled* (not dropped). Show that the `cksum_err` path emits a NAK and that the frame is retransmitted exactly once. Why does the receiver need the `no_nak` flag specifically on the `cksum_err` path?
3. The satellite scenario in The Problem has BER 1×10⁻⁵ and 1500-byte frames. Compute the expected number of retransmissions per 1000 frames under Go-Back-N (`W=8`) versus Selective Repeat (`W=4`). Assume losses are independent and ignore NAKs.
4. Implement the expanding-window hazard as a unit test: drive the simulator so that all acks for window `[0..3]` are lost, force a timeout on frame 0, and assert that with the legal `W` the retransmitted 0 is *rejected* by the receiver's `between()` check. Then set `W` illegal and assert it is *accepted* — the test must fail to prove the rule's necessity.
5. Decode this TCP SACK option bytes `05 0A 00 00 07 D0 00 00 0B B8 00 00 13 88 00 00 15 7C` (kind 5, length 10). Which two byte ranges has the receiver got, and which two ranges must the sender retransmit assuming `ACK = 1000`?
6. Add a third event source — a `link_reset` that wipes the channel in both directions. Show that Selective Repeat recovers correctly (per-frame timers fire, NAKs regenerate) while a naive Go-Back-N implementation that only kept a single base-timer would stall. What invariant does per-frame timing preserve that a single timer cannot?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Selective Repeat | "Re-send only the bad packet" | ARQ where the receiver buffers out-of-order frames and the sender retransmits only the lost frame, requiring `W ≤ (MAX_SEQ+1)/2` |
| Go-Back-N | "Rewind and resend everything" | ARQ with receiver window = 1; on loss, sender retransmits the lost frame and all sent-but-unacked frames after it |
| `NR_BUFS` | "Buffer count" | `(MAX_SEQ + 1) / 2` — the legal window size, also the receiver buffer pool depth |
| NAK | "Negative ack" | A control frame sent on a detected gap or checksum error, gated by `no_nak` to one-per-lost-frame |
| `between(a,b,c)` | "Range check" | Circular test `a ≤ b < c` on the mod-`MAX_SEQ+1` ring; decides if a sequence number is inside the receiver window |
| `ack_timer` | "Standalone ack trigger" | Fires a pure `ack` frame when no reverse data traffic exists to piggyback on; the fifth Protocol-6 event |
| Piggyback | "Ack on a data frame" | Carrying the `ack` field in a reverse-direction data frame's header to avoid sending a separate ack |
| SACK | "TCP selective ack" | RFC 2018 option (kind 5) listing up to four received LE/RE edge blocks so the sender resends only the gaps |
| Window overlap | "The duplicate-frame bug" | When `W > (MAX_SEQ+1)/2`, a retransmitted old frame falls inside the receiver's new window and is accepted as fresh — silent data corruption |

## Further Reading

- RFC 2018 — *TCP Selective Acknowledgment Options* (the SACK kind-5 option with LE/RE edge blocks)
- RFC 9260 — *Stream Control Transmission Protocol* (SCTP SACK chunk with gap-ack blocks, the Selective Repeat analogue for message streams)
- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §3.4.3 "A Protocol Using Selective Repeat" (Protocol 6 source listing)
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, §6.3 — pipelined ARQ and the window-size derivation
- RFC 1323 — *TCP Extensions for High Performance* (RTTM and the window-scaling that makes Selective-Repeat-style windows usable on long-fat pipes like the satellite link in The Problem)
