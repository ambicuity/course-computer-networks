# The One-Bit Sliding Window Protocol

> The one-bit sliding window protocol (Tanenbaum's **Protocol 4**) is the smallest bidirectional sliding-window protocol that still works: a window of size 1 forces **stop-and-wait** behavior, so the sender emits exactly one frame and blocks until an acknowledgement arrives. Each frame carries three fields — `seq` ∈ {0,1}, `ack` ∈ {0,1}, and `info` (the packet) — and the two endpoints ping-pong a 1-bit sequence number back and forth using **alternating-bit** arithmetic: the next expected sequence is `1 − frame_expected`, and the sender's piggybacked ack is `1 − frame_expected` as well. Because the window is one frame, every in-order frame is acknowledged by the *next* frame sent in the reverse direction (piggybacking), and a **timeout** retransmits the outstanding frame. The protocol survives lost frames, damaged frames (detected by checksum/CRC), and premature timeouts: duplicates are rejected by sequence-number mismatch, and the acknowledgement field tells the sender when to advance. Its one celebrated pathology is the **simultaneous-start deadlock-lite**: if both A and B send their first frame at the same instant, the frames cross, each side sees a duplicate on every other cycle, and bandwidth is wasted until the sequence resynchronizes — no packets are lost or duplicated at the network layer, but efficiency collapses. This lesson builds a runnable Python simulator of Protocol 4 that replays both the normal and the simultaneous-start scenarios from the textbook's Figure 3-17, so you can watch the sequence and ack bits toggle and the `frame_expected` / `next_frame_to_send` state machines advance.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Framing and error detection (Phase 3 lessons on frames and CRCs), the stop-and-wait ARQ lesson, elementary finite-state reasoning
**Time:** ~75 minutes

## Learning Objectives

- State why a window size of 1 forces stop-and-wait and derive the resulting maximum link utilization of `t_frame / (t_frame + 2·t_prop)` for a noiseless link.
- Given a frame's `seq`, `ack`, and the receiver's `frame_expected`, decide whether the frame is accepted, rejected as a duplicate, or ignored due to checksum error.
- Trace the textbook's simultaneous-start scenario (Figure 3-17b) and explain why no duplicate packets reach the network layer even though half the frames on the wire are redundant.
- Identify the three events Protocol 4 handles — `frame_arrival`, `cksum_err`, `timeout` — and the exact state mutation each triggers on `next_frame_to_send`, `frame_expected`, and the timer.
- Diagnose a premature-timeout storm: describe the sequence of duplicate frames it generates and the ack values that eventually resynchronize the two sides.
- Run `code/main.py` and read its event trace to confirm that every packet delivered to the network layer appears exactly once on each side.

## The Problem

Two point-to-point routers, A and B, are connected by a 64 kbps serial link with a 20 ms one-way propagation delay. A wants to send an unbounded stream of packets to B, and B wants to send its own stream back to A at the same time. The link is noisy: roughly one frame in twenty is corrupted in transit, and occasionally a frame is lost entirely. The data link layer must guarantee that (a) every packet is delivered to the remote network layer **exactly once**, in order, and (b) neither side ever deadlocks waiting for an acknowledgement that will never come.

A naive "send a frame, send a separate ACK frame back" scheme wastes half the bandwidth on bare acknowledgements and cannot tell a retransmitted data frame from a fresh one — after a timeout, the sender cannot know whether its original frame arrived late or was lost, so it might deliver a duplicate to the network layer. The engineer needs a scheme that (1) piggybacks acknowledgements onto reverse-direction data so ACKs ride for free, (2) stamps each frame with a sequence number so duplicates are detectable, and (3) retransmits on timeout without ever losing or duplicating a packet at the network layer. Protocol 4 is the minimal such scheme.

## The Concept

### The frame format: seq, ack, info

Every frame on the wire in Protocol 4 has three logical fields:

| Field | Width | Meaning |
|---|---|---|
| `seq` | 1 bit | Sequence number of the **data** in this frame (0 or 1) |
| `ack` | 1 bit | Sequence number of the last frame the sender of *this* frame correctly received (piggybacked) |
| `info` | one packet | The network-layer payload being delivered |

Because the window is one frame, `seq` and `ack` each need only one bit. The textbook denotes this `(seq, ack, packet)` and the simulator in `code/main.py` mirrors that exactly. The key invariant is that the sequence space is exactly twice the window size (2 × 1 = 2 → one bit), which is the minimum that lets the receiver distinguish a fresh frame from a retransmission of the previous one.

### The two state variables

Each endpoint keeps exactly two variables, both modulo-2:

- `next_frame_to_send` (sender side) — the sequence number of the frame this side is currently trying to deliver. It flips 0→1→0 each time the corresponding ack arrives.
- `frame_expected` (receiver side) — the sequence number of the next frame this side wants to *receive*. It flips 0→1→0 each time a correctly sequenced frame is handed to the network layer.

On startup both are 0. The side that "goes first" fetches a packet, builds `(seq=0, ack=1, info)`, transmits, and starts a timer. The piggybacked `ack=1` is `1 − frame_expected`, i.e. "I have not yet received frame 0, so I am acking frame 1 (which never existed)" — a harmless initial value that the peer will ignore.

### The decision rules on frame arrival

When a frame arrives undamaged, the receiver applies two independent tests — one for the inbound data stream, one for the outbound ack stream. They are decoupled:

```
if frame is damaged (cksum_err):
    # discard silently, do not advance anything
    # the sender's timer will eventually fire and retransmit
else:  # frame_arrival
    if r.seq == frame_expected:
        deliver r.info to network layer
        frame_expected = 1 - frame_expected      # advance receive window
    # else: duplicate, do NOT deliver, do NOT advance

    if r.ack == next_frame_to_send:
        stop timer
        fetch new packet from network layer
        next_frame_to_send = 1 - next_frame_to_send   # advance send window
    # else: the ack does not match; keep retransmitting the same frame
```

Every iteration of the main loop — whether the arriving frame was a duplicate, a fresh data frame, or even arrived with a checksum error that is *not* a `frame_arrival` — ends by **re-sending** a frame: the current packet, the current `next_frame_to_send`, and the piggybacked `ack = 1 − frame_expected`. This is why Protocol 4 is "always sending": it never waits idle, it piggybacks its own ack onto whatever it transmits.

### Worked example: normal operation (Figure 3-17a)

A starts, B waits. The notation is `(seq, ack, packet)`; an asterisk marks a network-layer accept.

| Step | Wire event | A state (`nfs` / `fe`) | B state (`nfs` / `fe`) | Effect |
|---|---|---|---|---|
| 1 | A→B `(0,1,A0)` | 0 / 0 | 0 / 0 | B accepts A0, `fe_B`→1 |
| 2 | B→A `(0,0,B0)` | 0 / 0 | 0 / 1 | A sees `ack==0==nfs_A`, accepts B0, advances; A `nfs_A`→1, `fe_A`→1 |
| 3 | A→B `(1,0,A1)` | 1 / 1 | 0 / 1 | B accepts A1, `fe_B`→0 |
| 4 | B→A `(1,1,B1)` | 1 / 1 | 1 / 0 | A advances `nfs_A`→0 |
| 5 | A→B `(0,1,A2)` | 0 / 0 | 1 / 0 | B accepts A2 |

Every frame arrival delivers a fresh packet to *some* network layer; nothing is wasted. The simulator's `--mode normal` trace reproduces this step for step.

### The simultaneous-start pathology (Figure 3-17b)

Now A and B both send their first frame at the same instant. The two frames cross in flight:

| Step | Wire event | Effect |
|---|---|---|
| 1 | A→B `(0,1,A0)` and B→A `(0,1,B0)` cross | |
| 2 | B gets `(0,1,A0)` | B accepts A0, `fe_B`→1; but `ack=1 ≠ nfs_B=0`, so B does **not** advance its send window |
| 3 | A gets `(0,1,B0)` | symmetric: A accepts B0, `fe_A`→1, but `ack=1 ≠ nfs_A=0` |
| 4 | A→B `(0,0,A0)` (retransmit, same seq) | B sees `seq=0 ≠ fe_B=1` → **duplicate, rejected**; but `ack=0 == nfs_B=0` → B finally advances `nfs_B`→1 |
| 5 | B→A `(0,0,B0)` | symmetric: A rejects the data but advances its send window |

The pattern is: every other frame on each direction is a redundant duplicate carrying no *new* data, but it carries the ack the other side needs to advance. No packet is ever delivered twice to a network layer — the `seq == frame_expected` test guards that — but the effective throughput halves. The textbook generalizes this: "if multiple premature timeouts occur, frames may be sent three or more times, wasting valuable bandwidth." The pathology is a **liveness/efficiency** bug, not a **safety** bug.

### Why the protocol is still correct

Correctness here means three properties, all of which Protocol 4 preserves:

1. **No duplicates at the network layer.** A packet is delivered only when `r.seq == frame_expected`, and `frame_expected` advances immediately afterward, so a retransmission of that same `seq` is always rejected.
2. **No skipped packets.** The sender cannot advance `next_frame_to_send` until it sees an `ack` matching it, which the receiver only emits *after* it has accepted that frame's data.
3. **No deadlock.** The timer guarantees retransmission; every retransmission carries the current piggybacked `ack`, so eventually the other side either accepts the data or sees the ack it needs. Lost frames and premature timeouts only delay progress, they cannot halt it.

The proof rests on the 1-bit sequence space being exactly large enough: with window = 1, there is at most one outstanding unacknowledged frame, so a fresh frame and a retransmission of the previous frame can never share a sequence number at the same instant of receiver state.

### Link utilization and when the window must grow

For a noiseless link of bandwidth `B`, frame size `L` bits, and one-way propagation `t_prop`, stop-and-wait utilization is:

```
U = t_frame / (t_frame + 2·t_prop),   where t_frame = L / B
```

The textbook's satellite example makes the cost vivid: a 50 kbps link, 1000-bit frames, 250 ms one-way delay gives `t_frame = 20 ms`, so `U = 20 / (20 + 500) ≈ 4%`. Ninety-six percent of the channel sits idle while the sender waits. That is the direct motivation for **Protocol 5 (Go-Back-N)** and **Protocol 6 (Selective Repeat)**, which widen the window to `2BD + 1` frames so the pipe stays full. Protocol 4 is the correct but bandwidth-starved base case against which those are measured; `code/main.py` exposes `--bandwidth` and `--propagation` so you can reproduce the 4% figure yourself.

### Timers, retransmission, and the ack ambiguity

Protocol 4 starts a single timer right after each transmit and stops it when a matching `ack` arrives. On `timeout`, the sender retransmits `(seq = next_frame_to_send, ack = 1 − frame_expected, info)`. There is an inherent ambiguity the protocol cannot resolve: when the timer fires, the sender does not know whether the original frame was lost or whether its ack is merely late. It retransmits unconditionally; if the original *did* arrive, the receiver will see the retransmission as a duplicate (`seq ≠ frame_expected`) and silently drop the data while still re-emitting its ack. That is the entire mechanism by which a premature timeout is self-healing. The cost is the wasted retransmission; the benefit is correctness without any extra state.

## Build It

1. Open `code/main.py`. The whole program is stdlib-only — no pip, no sockets.
2. Read the `Frame` dataclass: it is exactly `(seq, ack, info, kind)` mirroring the textbook's `(seq, ack, packet)`.
3. Read `Endpoint.step()`: it is a faithful port of the Protocol 4 main loop — `frame_arrival`, `cksum_err`, and `timeout` are the only events, and the two `if` blocks for `r.seq == frame_expected` and `r.ack == next_frame_to_send` are verbatim in spirit.
4. Run `python3 main.py --mode normal` and read the trace; you should see the four-step ping-pong of Figure 3-17a with every asterisked step delivering a fresh packet.
5. Run `python3 main.py --mode simultaneous` and confirm that half the frames are duplicates but every network-layer delivery still happens exactly once.
6. Run `python3 main.py --mode lossy --loss 0.2` and watch timeouts fire, retransmissions fly, and the two sides resynchronize.
7. Run `python3 main.py --util 50000 0.25 1000` to reproduce the satellite utilization calc (`U ≈ 4%`).

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm correctness under loss | `--mode lossy --loss 0.3 --seed 7` trace | Every `DELIVER` on side A has a matching earlier `SEND` from B; no `seq` is delivered twice to the same network layer |
| Reproduce the simultaneous-start pathology | `--mode simultaneous` trace | Step 2–3 show `DUPLICATE (seq mismatch)` on both sides; no `DELIVER` is repeated; throughput ≈ 50% |
| Reproduce the textbook satellite inefficiency | `--util 50000 0.25 1000` | Prints `U ≈ 0.0385` (≈4%), matching the chapter's 96%-idle claim |
| Verify premature-timeout recovery | `--mode lossy --timeout 5` (aggressive) | Trace shows `TIMEOUT` → retransmit → receiver emits `DUPLICATE` → sender eventually advances |
| Read state after N steps | `--steps 12 --mode normal` | Final state shows `nfs` and `fe` equal on both sides, indicating a clean resync |

## Ship It

Write up your findings in `outputs/prompt-one-bit-sliding-window.md`. The artifact should contain: (1) the event trace from one normal run and one simultaneous run, annotated with where each `DELIVER` and `DUPLICATE` happens; (2) the utilization calculation for a link of your choice; (3) a one-paragraph argument, grounded in the trace, that no packet is ever delivered twice to a network layer even under 30% loss. Reference `assets/one-bit-sliding-window.svg` when explaining the simultaneous-start crossing.

## Exercises

1. **Throughput math.** For a 1 Gbps fiber with 10 ms one-way delay and 1500-byte frames, compute Protocol 4's link utilization. At what frame size would utilization reach 50%? Confirm with `python3 main.py --util 1000000000 0.01 1500`.
2. **Premature-timeout storm.** Configure `--mode lossy --timeout 2 --loss 0.0` so timers fire before any propagation completes. Trace 20 steps. How many frames does A send to deliver packet A3? Explain in terms of `ack` values why the receiver keeps dropping them.
3. **Break the protocol.** The textbook notes window = 1 needs exactly 1 sequence bit. Modify the simulator to use a *2-bit* sequence space but keep window = 1. Does anything break? Now try window = 2 with a 1-bit sequence space — demonstrate a concrete scenario where a duplicate is wrongly accepted.
4. **Piggyback cost.** Protocol 4 always piggybacks; there is no bare-ACK. Modify `main.py` so a side with no pending data sends a bare `(seq, ack, EMPTY)` frame after a 1-step delay instead of retransmitting. Measure how many wire frames are saved over 20 deliveries in `--mode normal`.
5. **Resync after burst loss.** Set `--loss 0.5` for a 5-step burst starting at step 4. Trace the recovery. Identify the exact step at which both sides' `nfs` and `fe` converge again, and prove from the trace that no network-layer delivery was skipped.
6. **Compare to Go-Back-N.** Without writing code, argue why Protocol 5 with window `2BD+1` on the 50 kbps / 250 ms satellite link achieves ~100% utilization where Protocol 4 achieves ~4%. What is the minimum window in frames?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Sliding window | "A window that slides" | A bound on the number of unacknowledged frames a sender may have outstanding; the bound's lower and upper edges advance as acks arrive |
| One-bit / alternating bit | "Just flip the bit" | A sequence-number space of size 2 (one bit), valid only when the window is 1, so a fresh frame and a retransmission can never share a number at the same receiver state |
| Stop-and-wait | "Send one, wait" | The behavior forced by window = 1: the sender blocks after each frame until its ack; the simplest ARQ |
| Piggybacking | "ACKs ride on data" | Carrying the ack for the reverse-direction stream inside the `ack` field of a data frame instead of transmitting a separate ACK frame |
| `next_frame_to_send` | "The send pointer" | 1-bit sender state: the seq of the frame currently outstanding; advances only on a matching ack |
| `frame_expected` | "The receive pointer" | 1-bit receiver state: the seq of the next frame to accept; advances only on a correct in-order arrival |
| Premature timeout | "Timer fired too early" | The timer expires before the (possibly late) ack arrives; the sender retransmits, the receiver drops the duplicate, and the two resync via the piggybacked ack |
| Bandwidth-delay product | "BD" | `bandwidth × one-way propagation`; measured in bits or frames, it sets the window size needed to keep a link full (`2BD + 1`) |

## Further Reading

- Tanenbaum, Wetherall, *Computer Networks*, 6th ed., §3.4.1 "A One-Bit Sliding Window Protocol" — the source of Protocol 4 and Figures 3-15 through 3-17.
- RFC 914 (DDCMP) and the original ARPANET IMP-to-IMP protocol — early real-world alternating-bit-style link protocols.
- Lynch, W. C., "Reliable Full Duplex File Transmission over Half-Duplex Telephone Lines," *Communications of the ACM*, 1968 — the historical root of the alternating-bit protocol.
- Bartlett, Scantlebury, Wilkinson, "A Note on Reliable Full-Duplex Transmission over Half-Duplex Lines," *CACM*, 1969 — the canonical alternating-bit proof of correctness.
- The Go-Back-N (§3.4.2) and Selective Repeat (§3.4.3) lessons in this phase — the natural successors that widen the window past 1.
