# Flow Control

> Flow control stops a fast sender from drowning a slow receiver, even on an error-free link. Tanenbaum's section 3.1.4 splits the field into two families: **feedback-based** (the receiver grants permission, e.g. "you may send n frames, then stop") and **rate-based** (a built-in cap with no feedback, normally a transport-layer trick). The link layer almost always uses feedback. The simplest scheme is **stop-and-wait**: send one frame, block until an ACK returns — correct but its throughput collapses to `frame_time / (frame_time + 2·propagation + ack_time)`, so a 1 Gbit/s satellite link can run at under 1% utilization. **Sliding window** fixes this by letting up to `W` frames be outstanding; the link stays full once `W ≥ 1 + 2·BDP/frame_size`, where BDP is the bandwidth-delay product. The same window idea reappears in TCP's 16-bit `Window` field (RFC 9293) scaled by the Window Scale option (RFC 7323), in 802.11 Block-Ack, and in Ethernet PAUSE/PFC frames (IEEE 802.3x / 802.1Qbb). Get the window too small and you waste capacity; too large and you build bufferbloat. This lesson builds a stop-and-wait vs. sliding-window simulator and reads real receiver-advertised windows in a Wireshark trace.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib simulator)
**Prerequisites:** Phase 3 lessons on framing and error detection; bandwidth-delay product from Phase 2
**Time:** ~75 minutes

## Learning Objectives

- Distinguish **feedback-based** from **rate-based** flow control and state which layer each lives in.
- Derive stop-and-wait link utilization from frame time, propagation delay, and ACK time, and compute the window size needed to fill a link from its bandwidth-delay product.
- Trace a sliding-window sender/receiver through window slides, ACKs, and a lost-frame recovery for both Go-Back-N and Selective Repeat.
- Identify the concrete evidence of flow control in a packet trace: TCP `Window` field, zero-window probes, 802.3x PAUSE `quanta`, and 802.11 Block-Ack bitmaps.
- Explain how an over-large window causes bufferbloat and how a zero window stalls a transfer.

## The Problem

A phone requests a web page from a powerful server. The server "turns on the fire hose" and blasts frames faster than the phone's NIC and kernel can drain its receive ring. The link itself is error-free — nothing is corrupted — yet frames are still dropped, because the receiver's buffer overflows. The application sees a stall, retransmissions, and sometimes a half-finished page, and a junior engineer blames "packet loss" or "a bad cable."

The real fault is the absence of *flow control*: the sender was never told how much the receiver could absorb. The fix is a feedback loop. The receiver advertises how much room it has; the sender must not exceed it. Every layer that moves bulk data — link, TCP, even 802.11 — implements some version of this. Your job is to recognize the mechanism, read the evidence it leaves in packets, and tune the one knob that matters: the window.

## The Concept

### Two families: feedback vs. rate

Tanenbaum (3.1.4) names exactly two strategies:

| Family | How it limits the sender | Where it lives | Example |
|---|---|---|---|
| **Feedback-based** | Receiver returns permission ("send n more") or status | Link layer and higher | TCP advertised window, 802.3x PAUSE, HDLC RR/RNR |
| **Rate-based** | Protocol caps the send rate with no return signal | Transport layer (Chap. 5) | ATM ABR, DCCP/TFRC, QUIC pacing |

This lesson studies feedback-based schemes, because rate-based control is essentially a transport-layer topic. Note the modern caveat from the text: many NICs now run at *wire speed* in hardware, so overruns are pushed up to higher layers rather than handled on the link — which is exactly why TCP's window matters so much.

### Stop-and-wait and why it's slow

The minimal feedback protocol: send one frame, then wait for an ACK before sending the next. It is trivially correct (the receiver can never be overrun by more than one frame) but wastes the link. The sender is busy only for `t_frame` out of every round-trip:

```
utilization = t_frame / (t_frame + 2·t_prop + t_ack)
```

Worked example — a 1 Gbit/s link, 1500-byte frames, 250 ms one-way satellite delay, tiny ACK:

```
t_frame = 1500·8 / 1e9        = 12 µs
2·t_prop = 2 · 250 ms          = 500 ms
utilization ≈ 12 µs / 500 ms   ≈ 0.0024  → 0.24 %
```

The link is 99.76 % idle. `code/main.py` computes this for any link with `stop_and_wait_utilization()`.

### Sliding window: keep the pipe full

Let the sender keep up to `W` frames outstanding (un-ACKed) at once. To never stall, `W` must cover one frame plus everything that fits "on the wire" in a round trip — the **bandwidth-delay product (BDP)**:

```
W_min = ceil( (t_frame + 2·t_prop + t_ack) / t_frame )
      = ceil( 1 + 2·BDP / frame_bits )
```

For the satellite link above, `W_min ≈ ceil(500 ms / 12 µs) ≈ 41,667` frames. That is why real protocols need *large* windows and why TCP's base 16-bit field (max 65,535 bytes) is too small for fat-long pipes — RFC 7323's Window Scale option shifts it left by up to 14 bits, giving a 1 GiB ceiling. The diagram in `assets/flow-control.svg` shows the sender window sliding as ACKs arrive while frames are still in flight.

### Window state: send and receive sides

A sliding-window sender tracks three boundaries; the receiver tracks one plus a buffer.

| Variable | Side | Meaning |
|---|---|---|
| `base` (SND.UNA) | Sender | Oldest un-ACKed sequence number |
| `next_seq` (SND.NXT) | Sender | Next sequence number to send |
| `W` (SND.WND) | Sender | Window size; may send while `next_seq < base + W` |
| `rcv_next` (RCV.NXT) | Receiver | Next in-order sequence expected |
| `RCV.WND` | Receiver | Free buffer space advertised back to sender |

The invariant `next_seq - base ≤ W` is what enforces flow control: when the gap fills, the sender blocks until an ACK advances `base`. `code/main.py` implements this as a `SlidingWindowSender` class.

### Go-Back-N vs. Selective Repeat

Both are sliding-window ARQ schemes; they differ in how they recover a lost frame.

| | Go-Back-N | Selective Repeat |
|---|---|---|
| Receiver buffer | 1 frame (in-order only) | `W` frames (out-of-order stored) |
| On loss of frame k | Discard k+1…; sender resends k onward | Receiver NAKs/SACKs k; sender resends only k |
| ACK style | Cumulative | Selective (per-frame) |
| Bandwidth on loss | Wasteful (re-sends good frames) | Efficient |
| Complexity | Simple receiver | Complex receiver, needs `W ≤ 2^(m-1)` |

TCP is essentially Go-Back-N with cumulative ACKs, upgraded toward Selective Repeat by the SACK option (RFC 2018). The `m`-bit sequence space constraint matters: with an `m`-bit sequence number, Selective Repeat requires `W ≤ 2^(m-1)` or the receiver cannot tell a retransmission from a new frame. `code/main.py` demonstrates a single Go-Back-N loss-and-recovery episode.

### The zero window and the persist timer

Feedback flow control has a deadlock hazard. If a receiver advertises `Window = 0` (buffer full), the sender stops. The receiver later frees space and sends a window update — but if *that* segment is lost, both sides wait forever. TCP breaks the deadlock with the **persist timer**: the sender periodically sends a 1-byte **zero-window probe** to force the receiver to re-advertise its window. In Wireshark you see `[TCP ZeroWindow]`, then `[TCP ZeroWindowProbe]`, then `[TCP Window Update]`. This is the single most useful flow-control signature to recognize in a slow-transfer capture.

### Link-layer flow control in the wild

Feedback flow control is not just TCP:

- **Ethernet PAUSE (IEEE 802.3x):** a MAC Control frame (EtherType `0x8808`, opcode `0x0001`) carries a 2-byte `pause_time` in units of 512 bit-times ("quanta"). At 1 Gbit/s one quantum = 512 ns, so a max `pause_time` of 65,535 quanta ≈ 33.5 ms of silence. `code/main.py` converts quanta to microseconds.
- **Priority Flow Control (802.1Qbb / PFC):** eight per-priority PAUSE timers so one congested class doesn't stall the whole link — the backbone of lossless RoCE fabrics.
- **HDLC RR/RNR:** Receive Ready / Receive Not Ready supervisory frames are the classic link-layer "go / stop."
- **802.11 Block-Ack:** acknowledges a burst of frames with a bitmap, a sliding window over the air.

## Build It

1. Open `code/main.py`. Read `stop_and_wait_utilization()` and confirm the satellite example prints ≈ 0.24 %.
2. Run `python3 main.py`. Watch the utilization table sweep RTTs from LAN (0.1 ms) to GEO satellite (500 ms) and see where stop-and-wait collapses.
3. Read `min_window_for_full_link()` and verify the window needed to fill each link matches `1 + 2·BDP/frame`.
4. Step through the `SlidingWindowSender` trace: note where `next_seq` reaches `base + W` and the sender blocks.
5. Run the Go-Back-N loss demo and watch frames k+1…N get re-sent after frame k is dropped.
6. Convert an 802.3x PAUSE of 65,535 quanta to milliseconds at 1, 10, and 100 Gbit/s with `pause_quanta_to_microseconds()`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Spot TCP flow control | `tcp.window_size` column; `tcp.analysis.zero_window` filter | Window shrinks toward 0 under load, then recovers after a window update |
| Diagnose a stalled transfer | `[TCP ZeroWindow]` → `[TCP ZeroWindowProbe]` → `[TCP Window Update]` sequence | Persist-timer probes appear every few seconds; transfer resumes on the update |
| Size a window for a fat pipe | RTT from `ping`, throughput goal, `W = BDP` | Computed window ≥ advertised window scaled by RFC 7323 factor |
| Catch link-layer backpressure | Wireshark filter `eth.type == 0x8808` or `pfc` | PAUSE/PFC frames with non-zero `pause_time` during congestion |
| Detect bufferbloat | RTT inflation under load vs. idle RTT | Latency climbs as an oversized window keeps queues full |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **flow-control diagnostic runbook**: the zero-window probe sequence, the Wireshark filters above, and the BDP window-sizing formula.
- Or extend `code/main.py` into a Selective-Repeat simulator and save its annotated trace.

Start from [`outputs/prompt-flow-control.md`](../outputs/prompt-flow-control.md) and the SVG in `assets/flow-control.svg`.

## Exercises

1. A trans-Pacific link is 100 Mbit/s with 80 ms one-way delay and 9000-byte jumbo frames. Compute stop-and-wait utilization and the minimum window (in frames and in bytes) to fill it. Does 65,535 bytes suffice without RFC 7323 scaling?
2. In a capture you see `tcp.window_size_value == 0` followed three seconds later by a 1-byte segment from the same sender. Name both packets and explain why the 1-byte segment exists.
3. Go-Back-N with `W = 5` loses frame 7. List every frame the sender retransmits and contrast with what Selective Repeat would resend.
4. An 802.3x PAUSE frame carries `pause_time = 0xFFFF`. How long is the link silenced at 10 Gbit/s? At 100 Gbit/s? Why did 802.1Qbb add eight separate timers?
5. A storage team enabled a 16 MB TCP window on a 1 ms LAN and now sees 40 ms latency spikes. Explain the mechanism and what window they should use instead.
6. Selective Repeat uses a 3-bit sequence number. What is the largest safe window, and what failure occurs if you set `W = 7`?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Flow control | "stops congestion" | Stops a fast *sender* overrunning a slow *receiver*; congestion control (a separate thing) protects the *network* |
| Stop-and-wait | "send and ACK" | One outstanding frame; correct but utilization = `t_frame/(t_frame+2t_prop+t_ack)` |
| Sliding window | "TCP windowing" | Up to `W` un-ACKed frames; fills the pipe when `W ≥ 1 + 2·BDP/frame` |
| Bandwidth-delay product | "the pipe size" | `bandwidth × RTT`; the bytes in flight needed to keep a link busy |
| Advertised window | "receive window" | `RCV.WND` the receiver sends back; the sender's hard ceiling |
| Zero-window probe | "keepalive" | Persist-timer 1-byte segment that breaks a lost-window-update deadlock |
| Go-Back-N | "TCP's scheme" | Cumulative-ACK ARQ; on loss, resend from the lost frame onward |
| Selective Repeat | "SACK" | Per-frame ACK/NAK; resend only the lost frame; needs `W ≤ 2^(m-1)` |
| PAUSE / PFC | "Ethernet flow control" | 802.3x / 802.1Qbb MAC frames that silence a link for `pause_time` quanta |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (6th ed.), §3.1.4 (Flow Control) and §3.4–3.5 (sliding-window protocols, Go-Back-N, Selective Repeat).
- RFC 9293 — *Transmission Control Protocol* (the `Window` field and flow-control state variables SND.UNA, SND.NXT, RCV.NXT, RCV.WND).
- RFC 7323 — *TCP Extensions for High Performance* (Window Scale option; the fat-long-pipe problem).
- RFC 2018 — *TCP Selective Acknowledgment Options* (moving TCP from Go-Back-N toward Selective Repeat).
- RFC 1122 — *Requirements for Internet Hosts* (§4.2.2.17, the zero-window probe and persist timer).
- IEEE 802.3 Annex 31B — MAC Control PAUSE operation; IEEE 802.1Qbb — Priority-based Flow Control.
- ISO/IEC 13239 — HDLC, including RR/RNR supervisory frames.
