# A Protocol Using Go-Back-N

> Go-Back-N (Protocol 5 in Tanenbaum) is the sliding-window data link protocol that keeps a pipeline full by letting the sender transmit up to `MAX_SEQ` frames before it must block on an acknowledgement. Each frame carries a `seq` field, a piggybacked `ack` field, and an info payload; the receiver runs a receive window of exactly 1, accepting frames only in strict order and silently discarding everything after a gap. When a frame is lost or fails its checksum, the sender's per-frame timer eventually expires and it retransmits *every* outstanding frame from `ack_expected` onward — the "go back N" behaviour. ACKs are cumulative: an ack for frame `n` implicitly acknowledges `n-1, n-2, …`, so a single piggybacked ack can clear several timers. The window must satisfy `w = 2·BD + 1` to saturate a link of bandwidth-delay product `BD`, and the maximum outstanding frame count is restricted to `MAX_SEQ` (not `MAX_SEQ+1`) to avoid an ambiguity where a stale duplicate cannot be told apart from a fresh frame. This same logic survives in TCP's cumulative-ACK retransmission (RFC 9293) and in HDLC's normal-response mode.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Stop-and-wait and the one-bit sliding window (Phase 04 · 03–04), bandwidth-delay product, CRC/checksum framing
**Time:** ~90 minutes

## Learning Objectives

- Compute the optimal sender window `w = 2·BD + 1` from a link's bandwidth and one-way delay, and predict link utilization for any smaller window.
- Trace the Go-Back-N sender and receiver state (`next_frame_to_send`, `ack_expected`, `frame_expected`, `nbuffered`) through a clean run and through a single-frame loss.
- Explain why a lost middle frame forces retransmission of *all* subsequent in-flight frames, and quantify the bandwidth cost.
- Justify why the outstanding-frame limit is `MAX_SEQ` and not `MAX_SEQ + 1` using the circular `between(a, b, c)` test.
- Distinguish cumulative acknowledgement, piggybacking, and the receive-window-of-1 invariant from the selective-repeat alternative.

## The Problem

You are tuning a link that should be fast but isn't. The pipe is a 50-kbps geostationary satellite channel with a 500-ms round-trip propagation delay, and your file transfer is crawling at roughly 2 kbps. Wireshark shows the sender transmits one 1000-bit frame, then goes idle for almost half a second waiting for an ACK, then sends the next. The link is healthy, the CPU is idle, the error rate is low — and yet 96% of the available bandwidth is wasted.

The math is brutal. At t = 0 the sender starts frame 0. At t = 20 ms (1000 bits ÷ 50 kbps) the frame is fully clocked out. The first bit does not reach the receiver until t = 270 ms (20 ms transmit + 250 ms one-way propagation), and the ACK does not return until t = 520 ms. The sender was blocked for 500 of those 520 ms — utilization 20/520 ≈ 4%. This is the signature failure of stop-and-wait on a high bandwidth-delay link, and Go-Back-N exists to fix it without abandoning in-order, reliable delivery.

## The Concept

### Why a window, and how big

The fix is to let the sender transmit `w` frames before blocking instead of 1. The right size is governed by the **bandwidth-delay product** `BD` — the number of frames that physically fit "in the pipe" one-way:

```
BD = (bandwidth_bps × one_way_delay_s) / frame_bits
w  = 2·BD + 1
```

For the satellite link: `BD = (50 000 × 0.250) / 1000 = 12.5` frames. Then `w = 2(12.5) + 1 = 26`. The factor of 2 covers both the outbound pipe and the return path the ACK must travel; the `+1` exists because the receiver cannot emit an ACK until a *complete* frame has arrived. With `w = 26`, by the time the sender finishes frame 25 at t = 520 ms the ACK for frame 0 has just arrived, and from then on an ACK lands every 20 ms — exactly when the sender needs permission to continue. The link runs at 100%.

For any smaller window the upper bound on utilization is:

```
link_utilization ≤ w / (1 + 2·BD)
```

This is an *upper* bound: it ignores frame-processing time and treats the ACK as zero-length. `code/main.py` computes both `w` and this utilization curve; the SVG (`assets/a-protocol-using-go-back-n.svg`) shows the timeline where the pipe fills and the first ACK returns.

### The frame format

Go-Back-N frames carry three fields that matter at the link layer:

| Field | Width (Protocol 5) | Meaning |
|---|---|---|
| `kind` | enum (data / ack / nak) | frame type; data frames carry payload |
| `seq` | `⌈log₂(MAX_SEQ+1)⌉` bits | sequence number, modulo `MAX_SEQ+1` |
| `ack` | same width as `seq` | piggybacked cumulative ack of the last in-order frame received |
| `info` | payload | one network-layer packet |

With `MAX_SEQ = 7` the sequence space is `{0,1,…,7}` — three bits. The `ack` field is computed as `(frame_expected + MAX_SEQ) % (MAX_SEQ+1)`, i.e. "the frame just before the one I'm still waiting for."

### Sender and receiver state

The sender keeps three variables and a circular buffer of size `MAX_SEQ+1`:

| Variable | Role |
|---|---|
| `next_frame_to_send` | upper edge of the send window; the next new seq to emit |
| `ack_expected` | lower edge; oldest unacknowledged frame still timed |
| `nbuffered` | how many frames are currently outstanding (`< MAX_SEQ` to keep sending) |
| `frame_expected` | (receiver) the only seq the receiver will accept next |

The receive window is size 1: the receiver accepts a frame **only** if `r.seq == frame_expected`, passes it up, and advances `frame_expected`. Anything else is dropped, no ACK sent for it.

### The four events

Protocol 5 is an event loop over four event types:

| Event | Action |
|---|---|
| `network_layer_ready` | fetch a packet, `nbuffered++`, send it with current seq, advance `next_frame_to_send`, start its timer |
| `frame_arrival` | if `r.seq == frame_expected`, deliver and advance; then process the piggybacked ack: while `between(ack_expected, r.ack, next_frame_to_send)`, stop that timer, `nbuffered--`, advance `ack_expected` |
| `cksum_err` | ignore — a damaged frame is simply discarded |
| `timeout` | retransmit **all** outstanding frames: set `next_frame_to_send = ack_expected` and resend `nbuffered` frames in order |

After every event the layer enables the network layer if `nbuffered < MAX_SEQ`, else disables it — that is the flow-control valve.

### Cumulative ACK and the `between` test

Because ACKs are cumulative, an ack for frame `n` retires `n, n-1, n-2, …` all at once. The sliding-window arithmetic wraps modulo `MAX_SEQ+1`, so "is `b` inside the open window `[a, c)` circularly?" cannot use plain `<`. Protocol 5 uses:

```
between(a, b, c) = (a ≤ b < c)  OR  (c < a ≤ b)  OR  (b < c < a)
```

`code/main.py` implements this exactly and the sender loops it to drain the timer list on each incoming ack.

### Why the limit is MAX_SEQ, not MAX_SEQ + 1

There are `MAX_SEQ + 1` distinct sequence numbers but only `MAX_SEQ` frames may be outstanding. Suppose `MAX_SEQ = 7` and the sender could have 8 frames in flight:

1. Sender sends frames 0–7.
2. A piggybacked ack for 7 returns.
3. Sender sends another eight frames, again 0–7.
4. Another piggybacked ack for 7 arrives.

Did the *second* batch all arrive, or did it all get lost (discards-after-error count as lost) and this ack still refers to the first batch? In both cases the receiver's `frame_expected` produces an ack of 7. The sender cannot tell the difference. Capping outstanding frames at `MAX_SEQ` removes the ambiguity — the second "frame 0" can never coexist with an un-retired first "frame 0."

### What a single loss costs

When frame 2 of a long stream is lost, frames 3, 4, 5, … keep arriving at the receiver, but its window is 1, so it discards every one and never advances `frame_expected` past 2. The sender, oblivious, keeps sending until frame 2's timer expires. Then it "goes back" to 2 and resends 2, 3, 4, 5 … — including frames the receiver had already seen and thrown away. On a high error rate this is the protocol's weakness: every loss costs a full window of retransmission. Selective repeat (the next protocol) buffers out-of-order frames and uses NAKs to retransmit only the missing one, trading link-layer memory for bandwidth.

## Build It

`code/main.py` is a discrete, deterministic Go-Back-N simulator (stdlib only). It models a link with configurable `MAX_SEQ`, a window, and a scripted loss, then prints a frame-by-frame event log plus the bandwidth-delay analysis.

1. Run `python3 main.py`. Read the **utilization analysis** block first: confirm `BD = 12.5`, `w = 26`, and that stop-and-wait (`w = 1`) yields ≈ 4%.
2. Read the **clean-run trace**: watch `next_frame_to_send` advance and cumulative acks retire multiple frames at once.
3. Read the **loss trace**: frame 2 is dropped; observe the receiver discarding 3–5, the timeout, and the go-back retransmission of 2,3,4,5.
4. Change `MAX_SEQ` to 3 and re-run. Confirm the window shrinks and utilization on the satellite link falls.
5. Re-derive the `between()` truth table by hand for `a=6, c=2` (a wrapped window) and check it against the code.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Size the window | `BD` and `w = 2BD+1` from link params | You can state `w = 26` for the 50-kbps / 500-ms link and explain the `+1` |
| Confirm pipelining | Trace showing N frames sent before first ack | Sender never idles while `nbuffered < MAX_SEQ` |
| Diagnose a loss | Trace with a gap, then a burst of duplicate seqs after timeout | Retransmission starts at `ack_expected`, covers the whole window |
| Validate the seq cap | Two batches with the same ack value | You can construct the ambiguity that `MAX_SEQ` (not `MAX_SEQ+1`) prevents |
| Read cumulative acks | One ack frame retiring several timers | `between()` returns true for each retired seq in the window |

## Ship It

Produce one artifact under `outputs/`:

- A Wireshark/trace annotation checklist that maps Go-Back-N state (`seq`, `ack`, retransmission bursts) onto a real capture.
- A one-page window-sizing runbook: given bandwidth and RTT, output `BD`, `w`, and predicted utilization.
- The state diagram derived from `assets/a-protocol-using-go-back-n.svg`.

Start with [`outputs/prompt-a-protocol-using-go-back-n.md`](../outputs/prompt-a-protocol-using-go-back-n.md).

## Exercises

1. A 1-Gbps terrestrial link has a 1-ms one-way delay and 12 000-bit frames. Compute `BD` and `w`. How many frames must be buffered to saturate it, and how many sequence bits does that need?
2. On the satellite link the sender is configured with `w = 8` instead of 26. Using `w / (1 + 2BD)`, predict the utilization. Verify with `code/main.py`.
3. Frame 4 is lost in a stream where frames 0–9 are in flight. List, in order, every frame the sender retransmits after the timeout, and every frame the receiver discards before the timeout.
4. Construct the exact two-batch scenario with `MAX_SEQ = 3` (sequence space 0–3) that makes a cumulative ack ambiguous if 4 frames were allowed outstanding. Show why capping at 3 fixes it.
5. The link suddenly drops every ACK frame but data frames arrive fine. Describe what Go-Back-N does, and why "always reverse traffic to piggyback on" is an assumption Protocol 5 depends on.
6. Compare the buffer requirement and worst-case bandwidth waste of Go-Back-N vs selective repeat for a window of 26 at a 10% frame-loss rate.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Go-Back-N | "resend everything on a loss" | Receive window of 1; on timeout the sender retransmits all frames from `ack_expected` forward, in order |
| Bandwidth-delay product (BD) | "the pipe size" | bandwidth × one-way delay ÷ frame size; the in-flight frame count, here 12.5 frames |
| Window `w` | "how many can be outstanding" | `2·BD + 1` to saturate the link; capped at `MAX_SEQ` outstanding |
| Cumulative ACK | "ack the last one" | Acking frame `n` implicitly acks `n-1, n-2, …`, retiring several timers at once |
| Piggybacking | "ack rides on data" | The `ack` field travels inside a reverse-direction data frame instead of a standalone ACK |
| `MAX_SEQ` | "the biggest seq number" | The cap on outstanding frames; sequence *space* is `MAX_SEQ+1`, outstanding limit is `MAX_SEQ` |
| Receive window of 1 | "accept in order" | Receiver accepts only `frame_expected`; everything after a gap is silently dropped |
| Selective repeat | "the smarter one" | Buffers out-of-order frames, NAKs the missing one — more memory, less wasted bandwidth |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §3.4.2 "A Protocol Using Go-Back-N" and Fig. 3-18/3-19 (Protocol 5).
- RFC 9293 — *Transmission Control Protocol (TCP)*: cumulative acknowledgement and retransmission, the modern descendant of go-back-n.
- RFC 1323 / RFC 7323 — *TCP Extensions for High Performance*: window scaling for large bandwidth-delay products, the same `2·BD` problem at internet scale.
- ISO/IEC 13239 — *HDLC*: normal-response and asynchronous-balanced modes implement go-back-n style retransmission at the link layer.
- Wireshark display-filter reference: `tcp.analysis.retransmission`, `tcp.analysis.duplicate_ack` to spot go-back-n-like behaviour in real captures.
