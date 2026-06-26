# A Simplex Stop-and-Wait Protocol for an Error-Free Channel

> Protocol 2 ("Stop-and-Wait") solves *flow control* — preventing a fast sender from overrunning a slow receiver's finite buffer — over a channel that is assumed error-free. The sender transmits exactly one data frame, then blocks on `wait_for_event` until a content-free acknowledgement (ACK) frame returns; only then does it fetch the next packet from the network layer. This enforces strict alternation: DATA, ACK, DATA, ACK. Because frames flow in both directions even though *data* is simplex, the link must be at least half-duplex. The protocol carries no sequence numbers and no checksum field, because by assumption nothing is ever lost or corrupted — that fragile assumption is exactly what breaks in Protocol 3 and motivates timers, the 1-bit alternating sequence number, and the duplicate-delivery problem. Sender throughput is capped at one frame per round-trip time (RTT), so on a long fat link the channel sits idle most of the time. This lesson builds a working stop-and-wait simulator in Python and shows you the timing evidence that proves the sender is idle-waiting.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Phase 04 lessons 01-02 (framing, the Utopia/Protocol 1 simplex sender); basic understanding of the data link layer service model
**Time:** ~75 minutes

## Learning Objectives

- Trace the exact event sequence of Protocol 2 (`from_network_layer` → build frame → `to_physical_layer` → `wait_for_event` on the ACK → repeat) and explain why the sender must block.
- Distinguish *flow control* (this lesson: don't overrun the receiver) from *error control* (next lesson: recover from loss/corruption), and identify which fields each requires.
- Compute stop-and-wait link efficiency from frame size, line rate, and propagation delay, and explain the bandwidth-delay product penalty on long links.
- Explain why an error-free channel needs neither sequence numbers nor a checksum, and predict precisely what fails when you drop that assumption (lost ACK → sender deadlock; lost DATA → sender deadlock).
- Build and run a stop-and-wait simulator (`code/main.py`) that prints a timing ledger and an efficiency report.

## The Problem

You are bringing up a point-to-point serial link between an embedded sensor concentrator and a logging host. The concentrator (sender) can emit frames back-to-back at line rate. The host (receiver) has a single small DMA buffer and must copy each frame up to its application before it can accept the next one. With a naive "pump as fast as you can" sender — Protocol 1, the Utopia design from the previous lesson — the host's buffer overflows the moment the application stalls for even a few milliseconds. Frames are silently dropped on the floor by hardware, and the log shows gaps that look like a flaky cable.

The cable is fine. The problem is that nothing throttles the sender to the receiver's *consumption* rate. Building a receiver fast enough to absorb the worst-case continuous stream means dedicated hardware and big buffers that sit idle most of the time — wasteful, and it just pushes the overrun problem up into the network layer. The general fix is feedback: the receiver tells the sender "I've got that one, send the next." That single idea — one frame, then wait for permission — is stop-and-wait, and it is the foundation every reliable link protocol builds on.

## The Concept

### Why Protocol 1 (Utopia) fails

Protocol 1 assumes the receiver processes input "infinitely quickly" and has infinite buffer space. Its sender is an unbounded loop: `from_network_layer`, copy into `s.info`, `to_physical_layer`, forever. There is no back-pressure. The instant the receiver's real, finite buffer fills, hardware discards arriving frames. Utopia maps onto an *unacknowledged connectionless* service that dumps the loss problem on higher layers. Stop-and-wait keeps the simplex data direction but adds the one missing ingredient: feedback.

### The feedback frame (the ACK)

After the receiver delivers a packet up to its network layer, it sends a small "dummy" frame back to the sender. The frame's *contents do not matter* — only its arrival does. That arrival is the sender's permission slip to transmit the next frame. In real protocols this is an acknowledgement (ACK); here it carries no sequence number and no payload, because the error-free assumption means there is exactly one thing the inbound frame can be.

### Strict alternation and the state machine

The protocol enforces a rigid ping-pong. The sender has two states; the receiver has two states. See `assets/a-simplex-stop-and-wait-protocol-for-an-error-free-channel.svg` for the full timing/state diagram.

| Side | State | Event | Action | Next state |
|------|-------|-------|--------|-----------|
| Sender | READY | (start / ACK arrived) | `from_network_layer`, build frame, `to_physical_layer` | WAIT_ACK |
| Sender | WAIT_ACK | DATA frame departed | block on `wait_for_event` | WAIT_ACK |
| Sender | WAIT_ACK | ACK frame arrived | (no need to inspect it) loop | READY |
| Receiver | WAIT_DATA | DATA frame arrived | `from_physical_layer`, `to_network_layer` | SEND_ACK |
| Receiver | SEND_ACK | packet delivered | `to_physical_layer` (dummy frame) | WAIT_DATA |

The sender "need not even inspect the incoming frame, as there is only one possibility." That line from the source is the whole point of the error-free assumption: zero ambiguity means zero bookkeeping.

### Pseudocode (Tanenbaum Protocol 2)

```
void sender2(void):
    while true:
        from_network_layer(&buffer)     # get a packet to send
        s.info = buffer                 # copy into outbound frame s
        to_physical_layer(&s)           # transmit
        wait_for_event(&event)          # BLOCK until ACK arrives

void receiver2(void):
    while true:
        wait_for_event(&event)          # only possibility: frame arrival
        from_physical_layer(&r)         # pull the inbound DATA frame
        to_network_layer(&r.info)       # deliver packet upward
        to_physical_layer(&s)           # send dummy ACK to wake sender
```

The only difference between `sender1` and `sender2` is the added `wait_for_event` after transmit. The only difference between `receiver1` and `receiver2` is the added `to_physical_layer(&s)` that sends the ACK. Two added lines turn an overrun-prone firehose into a flow-controlled link. `code/main.py` implements exactly this event loop with a simulated channel.

### Frame layout — what's present and what's absent

| Field | Present in Protocol 2? | Why |
|-------|------------------------|-----|
| `kind` (frame type: data/ack) | implicit only | One frame type per direction, so no explicit tag is needed |
| `seq` (sequence number) | **No** | Error-free channel cannot lose or duplicate frames, so ordering bookkeeping is unnecessary |
| `ack` (piggybacked ack number) | **No** | The ACK is content-free; its mere arrival is the signal |
| `info` (network-layer packet) | Yes, on DATA frames | The actual payload being carried, simplex |
| `checksum` (e.g., CRC-32) | **No** | No corruption is possible by assumption, so no detection is required |

Contrast this with a real link frame such as IEEE 802.3 Ethernet (mandatory 32-bit FCS / CRC-32 trailer) or HDLC (16-bit FCS). The *absence* of seq and checksum here is a deliberate teaching device that isolates flow control from error control.

### Efficiency: the round-trip penalty

Stop-and-wait sends one frame per RTT. Let:

- `Tframe` = frame transmission time = frame_bits / line_rate
- `Tprop` = one-way propagation delay
- `Tack`  = ACK transmission time (small)

Line efficiency (the fraction of time the link is busy carrying useful data) is approximately:

```
U = Tframe / (Tframe + 2 * Tprop + Tack)
```

Worked example — a satellite link: line rate 1 Mbps, frame 1000 bits, one-way propagation 270 ms (geostationary).

- `Tframe` = 1000 / 1,000,000 = 1 ms
- `2 * Tprop` = 540 ms
- `U` ≈ 1 / (1 + 540) ≈ **0.0018**, i.e. **0.18% efficiency**

The link is 99.8% idle. This bandwidth-delay-product penalty is the entire motivation for sliding-window protocols (later in this phase): keep multiple frames in flight so the pipe stays full. `code/main.py` computes this U for whatever parameters you give it.

### Where the error-free assumption breaks

Drop the error-free assumption and Protocol 2 deadlocks in two distinct ways:

1. **DATA frame lost in transit** → the receiver never sees it, never sends an ACK, and the sender blocks forever in `wait_for_event`. No timer, no retransmission, permanent stall.
2. **ACK frame lost in transit** → the receiver *did* deliver the packet but the sender never learns, so it blocks forever. The packet is delivered exactly once but the link is dead.

Adding a naive timer (retransmit on timeout) seems to fix case 1, but it introduces the **duplicate-delivery problem**: if only the ACK was lost, the retransmitted DATA frame gets delivered to the receiver's network layer *twice*, and with no sequence number the receiver cannot tell the copy from the original. That bug is exactly what Protocol 3 (stop-and-wait for a noisy channel) fixes with a 1-bit alternating sequence number. This lesson sets up that cliffhanger; you live in the safe error-free world for now.

## Build It

`code/main.py` is a discrete-event stop-and-wait simulator (stdlib only).

1. Read the `Frame` dataclass and confirm it carries `info` but no `seq`/`checksum` — matching the table above.
2. Trace `StopAndWaitSimulator.run`: it models the sender event loop, a channel with configurable propagation delay, and a receiver that delivers then ACKs.
3. Run it: `python3 main.py`. Watch the timing ledger — every DATA departure is followed by an idle gap of `2*Tprop` before the next can start.
4. Read the efficiency report and confirm it matches the hand-computed `U` for the default parameters.
5. Flip `lossy=True` on the channel and observe the simulator detect a sender deadlock (no ACK ever returns) — concrete evidence for the failure modes above.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Confirm flow control is active | Timing ledger from `main.py` showing one DATA per RTT | Sender is idle `2*Tprop` between frames, never back-to-back |
| Prove the link is under-utilized | Efficiency `U` from the report | `U` matches `Tframe/(Tframe+2*Tprop+Tack)` within rounding |
| Spot a lost-frame deadlock | Run with `lossy=True`; sim reports "sender blocked, no ACK" | The stall is attributed to a missing ACK, not a cable fault |
| Read a real ACK on the wire | Wireshark on a TCP flow: tiny segments with the ACK flag, len 0 | You can point to a content-light frame whose *arrival* is the signal |

## Ship It

Produce one artifact under `outputs/`:

- A stop-and-wait timing diagram (export the SVG or redraw with your own link parameters).
- A one-page runbook: "link stalled — is it flow control or a dead cable?" with the two deadlock signatures.
- A small efficiency calculator (extend `main.py` to sweep frame size vs. RTT and plot the U curve as a table).

Start from `outputs/prompt-a-simplex-stop-and-wait-protocol-for-an-error-free-channel.md`.

## Exercises

1. A 64-kbps terrestrial link uses 1000-bit frames and has a one-way propagation delay of 20 ms. Compute stop-and-wait efficiency `U`. At what frame size does `U` reach at least 50%? Verify both with `main.py`.
2. Modify the receiver in `main.py` to delay 5 ms before sending each ACK (simulating slow upper-layer delivery). Predict the new effective throughput, then measure it. Which term in the `U` formula did you change?
3. Inject a single lost ACK at frame 3 in the simulator. Show in the ledger exactly where and why the sender deadlocks, and state which Tanenbaum protocol (and which field) fixes it.
4. The text says a half-duplex channel "would suffice" for Protocol 2 even though frames go both ways. Explain why, citing the strict-alternation property. When would full-duplex actually help here?
5. Capture a real TCP flow in Wireshark over a high-RTT path. Identify the pure-ACK segments (Len=0, ACK flag set) and explain how TCP's window mechanism avoids the stop-and-wait efficiency trap described in this lesson.
6. Argue whether the absence of a checksum in Protocol 2 is "wrong." Under what physical-layer conditions is an effectively error-free channel a reasonable engineering assumption, and what residual risk remains (hint: undetected errors that pass a checksum)?

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Stop-and-wait | "Send one, wait for the reply" | Sender blocks after every frame until an ACK returns; throughput capped at one frame per RTT |
| Flow control | "Don't send too fast" | Matching sender rate to the receiver's finite buffer/processing rate — Protocol 2's whole job |
| Error control | "Handle dropped packets" | Recovering from loss/corruption with seq numbers, checksums, and timers — *not* in Protocol 2 |
| ACK (acknowledgement) | "Confirms delivery" | Here, a content-free frame whose mere *arrival* grants the sender permission to continue |
| Simplex | "One-way link" | Data flows one direction only; ACK frames still flow back, so the channel itself is half-duplex |
| Sequence number | "Packet counter" | Absent in Protocol 2; the 1-bit alternating seq is what Protocol 3 adds to kill duplicates |
| Bandwidth-delay product | "Pipe capacity" | line_rate × RTT — the bits in flight; large values make stop-and-wait catastrophically inefficient |
| `wait_for_event` | "Sleep until something happens" | The blocking call that enforces stop-and-wait; on a lossy channel it can block forever |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 3, §3.3.2 (Protocol 2) and §3.3.3 (Protocol 3, the noisy-channel sequel that motivates sequence numbers).
- RFC 9293 (*Transmission Control Protocol*, the 2022 consolidation of RFC 793) — §3.4 on acknowledgements and §3.8 on flow control / the sliding window, the production answer to stop-and-wait's RTT limit.
- ISO/IEC 13239 — HDLC, whose normal-response-mode and the 16-bit FCS show real-world framing and acknowledgement.
- IEEE 802.3 — Ethernet, whose mandatory 32-bit FCS (CRC-32) contrasts with Protocol 2's deliberate absence of a checksum.
- Wireshark display-filter reference: `tcp.flags.ack == 1 && tcp.len == 0` to isolate pure acknowledgement segments on a live capture.
