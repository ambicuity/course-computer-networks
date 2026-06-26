# TCP Sliding Window and Window Advertisement

> TCP's flow control uses a **variable-sized sliding window** whose size is advertised by the receiver in every segment's 16-bit Window field (RFC 793). The window says "I have buffered up to ACK byte `N`, and you may send up to `WIN` more bytes starting at `N`." Because TCP decouples acknowledgements from permission-to-send, the receiver can throttle the sender independently of the ack stream — a segment can carry `ACK = 4096, WIN = 0` to say "I have everything up to byte 4095, but please stop sending while I catch up." The 16-bit Window field would cap flow control at 64 KB, which was fine in 1981 but useless on a 1-Gbps transcontinental link (40 Mbit bandwidth-delay product), so RFC 1323 introduced the **Window Scale** option that shifts the Window field left by up to 14 bits, giving a 1 GB effective window. This lesson walks the data-flow and ack-flow separately, computes how many bytes are in flight on a 100 ms RTT link at 1 Gbps, and implements a working byte-counter that maintains the sender's `SND.NXT`, `SND.UNA`, and `SND.WND` plus the receiver's `RCV.NXT` and `RCV.WND` per RFC 793.

**Type:** Lab
**Languages:** Python, Wireshark
**Prerequisites:** Lessons 17–20, familiarity with cumulative acks
**Time:** ~85 minutes

## Learning Objectives

- Maintain the five TCP variables (`SND.UNA`, `SND.NXT`, `SND.WND`, `RCV.NXT`, `RCV.WND`) and explain how the sliding window moves as data and acks flow.
- Compute the **bandwidth-delay product** for a path and show why a 64 KB window underutilizes a 1 Gbps transcontinental link.
- Apply the **Window Scale** option (RFC 1323) to extend the 16-bit field to up to 30 bits.
- Walk the receiver-side buffer drain: as the application `read()`s data, the receiver slides `RCV.WND` and announces the new value in a window-update segment.
- Reason about the **zero-window deadlock** and explain how window probes (1-byte segments) break it.
- Explain why Nagle's algorithm and Clark's solution to silly-window syndrome are complementary, and what can go wrong when they interact.

## The Problem

A file transfer between two data centers stalls at exactly 64 KB of in-flight data per RTT, even though both hosts negotiate Window Scale. A second, related problem: a chat application sends one keystroke at a time and produces thousands of tiny 41-byte packets per second. Both are symptoms of misunderstanding how TCP's window, ack, and MSS interact.

The deeper problem is the **bandwidth-delay product**. On a 1 Gbps link with 40 ms RTT, the pipe holds 1 Gbps × 0.04 s = 40 Mbit = 5 MB. A sender that is allowed only 64 KB outstanding will fill the pipe once every 80 ms — and then sit idle for the rest of the RTT, achieving ~1.25% of the link capacity (the calculation in chapter 6).

## The Concept

### The five TCP variables

| Variable | Held by | Meaning |
|---|---|---|
| `SND.UNA` | sender | Lowest unacked sequence number (left edge of sender window) |
| `SND.NXT` | sender | Next sequence number to send (right edge of used portion) |
| `SND.WND` | sender | Window advertised by receiver, permits `SND.UNA + SND.WND - SND.NXT` more bytes |
| `RCV.NXT` | receiver | Next sequence number expected (also the cumulative ack) |
| `RCV.WND` | receiver | Receive-buffer space available, advertised in the Window field |

The sender may have in flight at any moment: `min(SND.WND, cwnd)` bytes. The "used window" is `SND.NXT − SND.UNA`; the "usable window" is `SND.WND − (SND.NXT − SND.UNA)`.

### The bandwidth-delay product

The pipe holds `bandwidth × RTT` bits. The sender's window must be at least that big to keep the pipe full. Worked examples:

| Path | Bandwidth | RTT | BD product | Minimum window |
|---|---|---|---|---|
| Cross-continent 1 Gbps | 1 Gbps | 40 ms | 5 MB | 5,000,000 bytes |
| Geostationary satellite | 50 Mbps | 540 ms | 3.375 MB | 3,375,000 bytes |
| Home FTTH 100 Mbps | 100 Mbps | 10 ms | 125 KB | 125,000 bytes |
| Wi-Fi 600 Mbps | 600 Mbps | 5 ms | 375 KB | 375,000 bytes |

Without Window Scale (RFC 1323), the 16-bit Window field caps advertised window at 65,535 bytes — which on a 1 Gbps transcontinental link caps throughput at ~13 Mbps. With Window Scale = 7 (a typical negotiated value), the effective window is `65,535 × 128 = 8,388,480` bytes, more than enough for a 5 MB pipe.

### Zero-window deadlock and window probes

When the receiver sets `WIN = 0`, the sender must stop. But what if the window-update segment that opens the window back up is lost? Both sides now wait forever: the sender for permission, the receiver for data. The standard defense is the **persistence timer** and **window probes**: the sender transmits a 1-byte segment at exponentially increasing intervals (lesson 22) to force the receiver to re-announce the window. The receiver must respond with the current `RCV.WND`, even if it is still zero — that response alone keeps the persistence timer ticking.

### Receiver-side buffer and the sliding window in action

The receiver has a fixed-size buffer (Linux default ~4 MB but tunable via `net.ipv4.tcp_rmem`). Each segment that arrives in order advances `RCV.NXT` by the data length and reduces `RCV.WND` by the same amount. When the application `read()`s data, `RCV.WND` grows again, and the receiver piggybacks a window update in the next ACK (or sends a dedicated window-update segment if no data is acked).

### Nagle's algorithm and silly-window syndrome

Two complementary heuristics attack the "small-packet problem":

- **Nagle's algorithm** (RFC 896, 1984) on the sender: if there is unacked data in flight, buffer small writes until either the previous segment is acked or enough data accumulates to fill an MSS. This stops one-byte-at-a-time applications from flooding the network.
- **Clark's solution to silly-window syndrome** (1982) on the receiver: do not advertise a window increase unless it is at least one MSS or half the buffer, whichever is smaller. This stops the receiver from saying "send 1 byte" after every application `read()`.

The two interact badly if both sides misbehave: Nagle waits for an ack, Clark waits for a buffer-large-enough update, and the connection can stall. Modern applications disable Nagle with `TCP_NODELAY` when they need low latency (interactive games, financial trading).

### Decoupled ack and window

Unlike HDLC and many link-layer protocols, TCP separates "I received data" (ack number) from "send me more" (window). The same segment can carry `ACK = 4096, WIN = 0` — bytes 0–4095 have been received, but please pause. This decoupling is what lets TCP's flow control respond quickly to receiver-buffer drain without forcing the sender to wait for new data.

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/21-tcp-sliding-window-and-window-advertisement
python3 code/main.py
```

The script:

1. Walks a sender through 10 segments with `SND.WND = 8192`, showing `SND.UNA`, `SND.NXT`, and bytes-in-flight after each step.
2. Computes the bandwidth-delay product for four sample paths and shows how Window Scale closes the gap.
3. Simulates a receiver buffer with `read()` calls and watches `RCV.WND` and the announced window evolve.
4. Reproduces the zero-window deadlock and shows how a window probe unblocks it.
5. Demonstrates silly-window syndrome: 1-byte application writes with Clark's solution disabled, vs. the same traffic with the threshold applied.

Use `step_sender(...)` and `receive(...)` to plug in your own byte counts.

## Use It

| What you want to inspect | How `main.py` shows it | Wireshark evidence |
|---|---|---|
| Bytes in flight | `step_sender(2048)` → `in_flight = SND.NXT - SND.UNA` | `tcp.analysis.bytes_in_flight` |
| Receiver buffer drain | `receive(read_bytes=...)` → new `RCV.WND` | Window field grows in next ACK |
| Window Scale effective size | `effective_window(scale, raw)` | "Window scale: 7" in the options pane |
| Bandwidth-delay product | `bandwidth_delay_product(bw, rtt)` | calculated manually |
| Zero-window probe | `zero_window_probe()` prints the 1-byte probe | `tcp.window_size_value == 0` then `tcp.urgent_pointer == 0` |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable table of bandwidth-delay products for your most common paths, with the minimum window for full utilization.
- A reference implementation of the sender / receiver state machine in your language, with Nagle and Clark toggles as parameters.

Start from [`outputs/prompt-tcp-sliding-window-and-window-advertisement.md`](../outputs/prompt-tcp-sliding-window-and-window-advertisement.md).

## Exercises

1. A sender has `SND.UNA = 1000`, `SND.NXT = 3500`, `SND.WND = 8192`. How many bytes may it send right now? How many are in flight?
2. Compute the bandwidth-delay product for a 1 Gbps link with 100 ms RTT. What window size is needed to keep the pipe full?
3. Window Scale is negotiated at 7. What is the largest window the receiver can advertise?
4. The receiver's application does `read(1)` for every byte the sender writes. Show the receiver's `RCV.WND` sequence with and without Clark's solution.
5. The receiver sets `WIN = 0`. The window-update segment is lost. Describe the persistence-timer sequence that lets the sender discover the new window.
6. Why does TCP decouple the acknowledgement number from the window advertisement? What would go wrong if every ACK had to include new data?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Sliding window | "send a few packets" | The number of bytes the sender may have outstanding, controlled by the receiver |
| Window advertisement | "advertised window" | The 16-bit Window field in every segment, scaled by RFC 1323's Window Scale |
| Bandwidth-delay product | "pipe size" | `bandwidth × RTT` — the bytes that fit in flight; the minimum window to fill the pipe |
| Window Scale | "big window" | RFC 1323 option that shifts the 16-bit Window field left by up to 14 bits |
| `SND.UNA` | "oldest unacked" | Left edge of the sender's sliding window |
| `SND.NXT` | "next to send" | Right edge of the used portion of the sender's window |
| `RCV.WND` | "receive buffer free" | Receive-buffer space available; announced in every segment |
| Zero-window | "pause sending" | The receiver is full; sender stops except for window probes |
| Window probe | "1-byte poll" | A 1-byte segment sent by the sender to elicit a fresh window advertisement |
| Nagle | "coalesce small writes" | RFC 896 algorithm that buffers writes until the previous segment is acked |
| Silly window | "1-byte ack storm" | Clark 1982: receiver should not advertise a tiny window |

## Further Reading

- RFC 793 — Transmission Control Protocol (sliding window in §6.5.8 and §3.9)
- RFC 896 — Congestion Control in IP/TCP Internetworks (Nagle's algorithm)
- RFC 1323 — TCP Extensions for High Performance (window scale, timestamps, PAWS)
- RFC 2581 — TCP Congestion Control (separate cwnd from rwnd)
- Clark, 1982 — *Window and Acknowledgement Strategy in TCP* (silly-window syndrome)
- Mogul & Minshall, 2001 — *Rethinking the TCP Nagle Algorithm* (the Nagle + delayed-ACK deadlock)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP sliding window
- Stevens, *TCP/IP Illustrated, Volume 1*, 2nd ed. — Chapter 21, TCP timers