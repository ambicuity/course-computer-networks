# Error Control and Flow Control

> The transport layer's two jobs while a connection is open are to make sure the bytes arrive intact and to make sure the sender does not outrun the receiver. The mechanisms are the same as at the data link layer - checksums, sequence numbers, cumulative ACKs, sliding windows - but the parameters are different: 32-bit sequence numbers, bandwidth-delay products of 200 Kbit or more (TCP across the U.S. at 1 Mbps, 100 ms RTT), and dynamic credit-based flow control (Belsnes 1975) where the receiver piggybacks both ACKs and a buffer allocation on the reverse traffic. Tanenbaum's Fig. 6-16 walks through a 4-bit sequence space with 8 buffers, 4 granted, 1 lost, 1 retransmit, and a deadlock that is broken only when the receiver resends a control segment. The end-to-end argument (Saltzer, Reed, Clark 1984) is the theoretical justification for why the transport layer's checksum is essential even though every link already has one.

**Type:** Build
**Languages:** Python (stdlib-only sliding-window + credit-allocation simulator)
**Prerequisites:** Addressing to Connection Establishment (lesson 05), Connection Release (lesson 06)
**Time:** ~85 minutes

## Learning Objectives

- Recite the four mechanisms the transport layer reuses from the data link layer: error-detecting code, sequence number + ARQ retransmit, sliding window for flow control, and bidirectional use of the sliding window for data + ACKs.
- Compute the bandwidth-delay product for a 1 Mbps cross-USA link with 100 ms RTT, and explain why stop-and-wait (window=1) cripples throughput on a long-fat pipe.
- Implement Belsnes' dynamic credit-based flow control: the sender requests N buffers, the receiver grants as many as it can, and every ACK carries a fresh credit allocation that the sender respects.
- Reproduce Fig. 6-16's deadlock scenario (line 16, allocation segment lost) and explain why each host must periodically send control segments even when there is no data to ship.
- Articulate the end-to-end argument: a per-link checksum does not protect against corruption *inside* a router; only an end-to-end check can, and it is therefore essential - per-link checksums are only a performance optimization.

## The Problem

Two production scenarios show what happens when error control and flow control are misunderstood.

First, an application team reports that a file transfer from us-east-1 to eu-west-1 runs at 5 KB/s instead of the link's 50 MB/s. The link has 100 ms RTT. The transport is stop-and-wait (window=1) - either a misconfigured library, a debug flag, or an old protocol. Stop-and-wait sends one segment, waits one RTT, sends the next: throughput = segment_size / RTT = 1460 bytes / 100 ms = 14.6 KB/s, which is in the right ballpark for the 5 KB/s report (smaller segments, retransmit overhead). The fix is to use a sliding window whose size is at least the bandwidth-delay product: 50 MB/s * 100 ms = 5 MB, so the window must be at least 5 MB / 1460 bytes = ~3500 segments.

Second, a memory-constrained server reports that an aggressive client keeps sending data even after the server's receive buffer is full. The server's `RCVBUF` is set to 64 KB; the client has set `SNDBUF` to 1 MB and a 256 KB send window; the kernel queue is full. The fix is credit-based flow control: the receiver tells the sender how much buffer it has, and the sender respects that limit.

This lesson is the toolkit for both problems: ARQ for reliability, sliding window for throughput, credit allocation for safety.

## The Concept

### The four mechanisms, lifted from the data link layer

Tanenbaum's §6.2.4 opens with a brief recap from Chapter 3: the same four ideas do the same job at the transport layer.

| Mechanism | Transport-layer role |
|---|---|
| Error-detecting code (CRC / checksum) | Protects each segment end-to-end through the network |
| Sequence number + ARQ retransmit | Lets the receiver reorder and discard duplicates, lets the sender retransmit losses |
| Sliding window | Bounds the number of unacknowledged segments in flight |
| Bidirectional use of the window | ACKs and credit allocations travel in the reverse direction's segments |

The differences are quantitative, not qualitative. The transport layer has 32-bit sequence numbers (4 billion values), windows of 64 KB to several MB, and ACKs that carry additional fields (window size, selective ACK blocks, timestamps). The link layer typically has 8-bit or 16-bit sequence numbers and windows of 1-127 frames.

### The end-to-end argument

Saltzer, Reed, and Clark (1984) articulated the principle: "an end-to-end function is best implemented at the endpoints, not inside the network." The transport checksum is the canonical example. A packet can be corrupted *inside* a router (a memory error, a software bug) and pass every link-layer checksum it ever crossed. The transport checksum is the only one that sees the packet for its entire journey. Per-link checksums are not redundant - they catch errors early, sparing the rest of the network from forwarding a corrupt packet - but they are not sufficient. The end-to-end check is essential.

### Bandwidth-delay product and the cost of stop-and-wait

The textbook's example: a 1 Mbps cross-USA link, 100 ms RTT. The bandwidth-delay product is 1 Mbps * 100 ms = 100 Kbit = 12.5 KB. This is the amount of data "in flight" - already sent, not yet acknowledged - when the pipe is full.

Stop-and-wait with one segment per RTT:

```
segment_size / RTT = 1460 bytes / 0.1 s = 14.6 KB/s
```

This is 1/1000th of the link capacity. With a sliding window of W segments, throughput is W * segment_size / RTT. To fill a 1 Mbps link at 100 ms RTT, W must be at least 100 Kbit / 1460 bytes = ~9 segments. Modern TCP uses windows of hundreds or thousands of segments.

### Belsnes' credit-based flow control

Fig. 6-16's scenario uses 4-bit sequence numbers (16 values), 8 requested buffers, 4 granted, 1 lost segment, 1 retransmit, and a final deadlock that is broken by a control-segment retransmit. The protocol:

1. Sender requests N buffers: `<request 8 buffers>`
2. Receiver grants K <= N: `<ack=15, buf=4>` (means "acknowledge all up to 15, you may send 4 more")
3. Sender transmits, decrementing its allocation per segment
4. Receiver's ACK carries both cumulative ACK and a fresh buffer allocation
5. Sender respects the allocation; it stops sending when it reaches zero
6. Receiver can grant more buffers when it has them; the segment that grants more can be lost

The crucial property: the allocation and the ACK are **decoupled**. The receiver can acknowledge data it has already received while still refusing to grant more buffer space. This lets the receiver pace the sender without confusing "I have more data ready" with "I have more buffer ready."

### The Fig. 6-16 deadlock

Line 16: the receiver has acknowledged all data (ack=4) and granted 4 new buffers (buf=4). The grant segment is lost. The sender's last `buf=0` allocation is still in force; it has nothing to send, but it also has no new allocation. Without a retransmit, the connection is deadlocked.

The fix: each host must periodically send control segments giving the ACK and buffer status, even when there is no data to ship. The textbook's exact phrase: "each host should periodically send control segments giving the acknowledgement and buffer status on each connection. That way, the deadlock will be broken, sooner or later."

Modern TCP's window-update mechanism does exactly this: if the receiver's window opens up (because the application read some bytes), it sends a window update segment even if there is no ACK to piggyback on. The sender's zero-window-probe timer (RFC 1122) sends a 1-byte segment to elicit a window update from the receiver.

### The sequence-number-space constraint

The textbook calls out a subtle constraint: sender window + receiver window must not exceed the sequence space. With 4-bit sequence numbers (16 values) and a sender window of 8, the receiver's window can be at most 8. Otherwise, after one cycle the receiver cannot tell whether a new segment with sequence number N is a new segment or a duplicate of an old one with the same N.

The formula: `W_sender + W_receiver <= 2^k` where k is the sequence-number bits. With k=32 (TCP), the constraint is irrelevant; with k=4 (the textbook's example), it matters. Modern TCP uses 32-bit sequence numbers and a 16-bit window-size field, with a separate window-scale option (RFC 1323) that lets the effective window exceed 64 KB.

### Retransmission strategies

The textbook (and Chapter 3) describe three ARQ flavors:

| Strategy | Window | Pros | Cons |
|---|---|---|---|
| Stop-and-wait | 1 | Simple | Throughput = segment_size / RTT; cripples long-fat pipes |
| Go-back-N | N | Sender pipeline; receiver discards out-of-order | One loss forces retransmit of the loss and all subsequent segments |
| Selective repeat | N | Sender retransmits only the loss; receiver buffers out-of-order | More state at the receiver (must buffer out-of-order segments) |

TCP uses a hybrid: a cumulative ACK for the left edge of the receive window (like go-back-N) plus an optional Selective Acknowledgment (SACK) option (RFC 2018) that lists out-of-order blocks, so the sender can retransmit only the missing segments.

## Build It

`code/main.py` implements:

1. **Transport-layer checksum** - 16-bit one's-complement sum as the textbook uses, with verification (data + checksum == 0). The simulator shows that a single-bit flip is detected with probability ~1.0.
2. **End-to-end checksum argument** - inject corruption "inside a router" (after a per-link CRC would have caught it) and show that the transport checksum still catches it.
3. **Sliding window with credit allocation (Fig. 6-16)** - the 16-step trace from the textbook, with the deadlock at line 16 and the resolution by control-segment retransmit.
4. **Sequence-space violation** - what happens when `W_sender + W_receiver > 2^k`: a new segment is mistaken for a duplicate.

Run with `python3 code/main.py`. The Fig. 6-16 trace is reproduced line by line; the deadlock step is highlighted; the sequence-space violation is shown as a "ghost segment" that the receiver cannot classify.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute bandwidth-delay product | BDP = bandwidth * RTT | A 1 Gbps link at 50 ms RTT has BDP = 6.25 MB; window must hold at least 6.25 MB |
| Choose window size | `W = ceil(BDP / MSS)` | With 1460-byte MSS, the example needs W >= 4470 segments to fill a 1 Gbps link |
| Detect a checksum miss | one's-complement sum != 0 | The transport layer drops the segment; the sender's RTO fires; retransmit |
| Trace Fig. 6-16's deadlock | line 16 with allocation lost | Sender stuck at buf=0; receiver's retransmit breaks the deadlock |
| Diagnose "zero window" | `netstat -an` shows `rcv_wnd=0` | Application has not read; sender's zero-window probe timer (60 s) is the next signal |
| Verify SACK in use | `tcpdump -Sni lo0` shows SACK option | Out-of-order blocks listed; sender retransmits only the missing range |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **flow-control cheat sheet** mapping BDP, MSS, and RTT to required window size for common link profiles (DSL, cellular, cross-country, trans-Pacific).
- A **Fig. 6-16 trace dissection** with every ACK, every credit allocation, and the deadlock step annotated.
- A **window-scaling decision matrix** - when to enable RFC 1323 window scaling, what `tcp_window_scaling` does in `sysctl`, and how to read the shift count in a SYN.
- An **end-to-end argument one-pager** that the team can hand to a junior engineer asking "do we still need the per-link CRC if we have a transport checksum?"

Start from `outputs/prompt-error-control-flow-control.md`.

## Exercises

1. A link has bandwidth 100 Mbps and RTT 20 ms. The MSS is 1460 bytes. What is the minimum window size (in segments) to fill the pipe? In bytes?
2. The 4-bit sequence number space in Fig. 6-16 has 16 values. The sender's window is 8, the receiver's window is 8. Is the constraint `W_s + W_r <= 2^k` satisfied? What if the receiver's window is 9?
3. A TCP sender has `cwnd = 10` (congestion window) and `rwnd = 64 KB` (receiver window). MSS = 1460 bytes. How many bytes can the sender put in flight? What is the effective window?
4. The transport checksum is a 16-bit one's-complement sum. A segment is corrupted by flipping a single bit. What is the probability the checksum still matches? Why is this acceptable?
5. The Fig. 6-16 deadlock (line 16) is broken by a control-segment retransmit. In TCP, what mechanism serves the same role? What is the default probe interval?
6. Run `code/main.py`'s Fig. 6-16 trace and identify the line at which the deadlock is detected. What does each host do to break it?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ARQ | "retransmit on loss" | Automatic Repeat reQuest: sender retransmits unacknowledged segments after a timeout |
| Stop-and-wait | "send one, wait" | ARQ with window=1; throughput = MSS / RTT; crippling on long-fat pipes |
| Sliding window | "the pipelining" | The set of segments the sender may have outstanding without ACK; bounded by min(cwnd, rwnd) in TCP |
| Cumulative ACK | "ack all up to N" | The receiver's ACK acknowledges every segment up to and including N; TCP's default mode |
| Selective ACK (SACK) | "tell me what's missing" | An RFC 2018 option that lists out-of-order blocks; lets the sender retransmit only the missing ranges |
| Credit allocation | "the buffer grant" | A piggybacked field on the ACK telling the sender how much more it may send; the receiver's pacing lever |
| Bandwidth-delay product | "the pipe size" | bandwidth * RTT = the bytes "in flight" when the pipe is full; sets the lower bound on the window size |
| End-to-end argument | "checksum is essential" | Saltzer/Reed/Clark 1984: an end-to-end check is the only one that catches corruption *inside* the network; per-link checksums are a performance optimization, not a substitute |
| Zero-window probe | "the 1-byte nudge" | A 1-byte segment the sender sends when the receiver's window is 0; elicits a window update |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.2.4** - the source chapter for this lesson (Fig. 6-16).
- **Saltzer, J., Reed, D., & Clark, D. (1984), "End-to-end arguments in system design," *ACM TOCS* 2(4)** - the theoretical justification for transport-layer checksums.
- **Belsnes, D. (1975), "Flow control in a packet-switching network," *Proceedings of the 2nd ICCC*** - the credit-based flow control paper.
- **RFC 793** (1981), "Transmission Control Protocol," §3.7-3.9 - data flow, retransmission, and the sliding window in TCP.
- **RFC 1323** (1992), "TCP Extensions for High Performance" - window scaling, timestamps, and PAWS.
- **RFC 2018** (1996), "TCP Selective Acknowledgment Options" - the SACK option.
- **Stevens, W. R. (1994), *TCP/IP Illustrated, Volume 1*, chapters 20-22** - retransmission, timeout, and congestion avoidance.
- **Kurose, J. & Ross, K., *Computer Networking: A Top-Down Approach* (8th ed.), §3.5** - a clean secondary treatment of sliding-window protocols.
