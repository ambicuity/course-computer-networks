# Dynamic buffer allocation, variable-sliding-window flow control, and the end-to-end argument

> The transport layer cannot pre-allocate one fixed-size buffer per connection — a server with 10,000 connections at 64 KB each is 640 MB sitting idle. Instead, transport protocols use **dynamic buffer allocation**: a variable-sized sliding window where the receiver advertises how much buffer it currently has, and the sender paces itself to that number (Figure 6-16). TCP carries the same idea in its 16-bit Window Size field (RFC 793) and the modern Window Scale option (RFC 7323) that extends it to 30 bits. This lab walks the chapter's four-bit-sequence-number example, identifies the **end-to-end argument** (Saltzer, Reed & Clark, 1984) that explains why the link-layer CRC alone is not enough, and shows how the dynamic window decouples acknowledgements from buffer allocation to avoid the deadlock on line 16 of Figure 6-16. The companion `code/main.py` is a stdlib-only simulator of the variable-window protocol: it runs a 15-step trace of the chapter's example, with the receiver granting and revoking buffers dynamically, and prints the deadlock hazard when an allocation segment is lost.

**Type:** Lab
**Languages:** Python, packet traces
**Prerequisites:** Lesson 14 (Berkeley sockets); Phase 03 link-layer framing; chapter section 6.2.4
**Time:** ~90 minutes

## Learning Objectives

- Walk the chapter's 4-bit-sequence-number example (Figure 6-16) step by step, predicting the sequence number, ACK, and buffer grant on each line.
- Distinguish fixed-window flow control (data link layer) from variable-window flow control (transport layer) and explain why the latter is required at the transport.
- Implement the three buffer-allocation strategies of Figure 6-15: fixed-size chained buffers, variable-size chained buffers, and one large circular buffer per connection.
- Connect the dynamic-window protocol to TCP's receive window (RWND), the Window Scale option (RFC 7323), and the modern flow-control interaction with congestion control (CWND).
- Articulate the end-to-end argument: link-layer checks detect transmission errors on a single hop, but only an end-to-end checksum can detect corruption inside a router (Saltzer et al., 1984).
- Reproduce the deadlock on line 16 of Figure 6-16 in the simulator and fix it with a periodic control segment that breaks the tie.

## The Problem

You inherit a server that handles 50,000 concurrent long-lived connections, each capable of 1 MB/s in either direction. If the kernel allocates 64 KB of buffer per connection up front, that is 3.2 GB of RAM sitting in the socket buffers before a single byte has flowed — and on a 16 GB host with 4 GB free, that is the difference between a healthy system and an OOM kill. The right answer is dynamic allocation: a small per-connection header (a few hundred bytes for the TCB) and a buffer that grows and shrinks with traffic. TCP's receive window does this in the protocol: the receiver advertises its current free buffer in the Window field of every ACK, and the sender never sends more than the minimum of RWND (the receiver's capacity) and CWND (the network's capacity).

A second problem is more subtle. Figure 6-16 of the chapter shows a datagram network with 4-bit sequence numbers and dynamic buffer allocation. Line 16 of the trace has the receiver granting 4 more buffers to the sender, but the *control segment* carrying the grant is lost. The sender, seeing no acknowledgement, is deadlocked: it has work to do (segments 5 and 6 are unacked) but believes the receiver has no buffer space. The fix is to decouple control from data: every ACK piggybacks the current allocation, and a periodic keep-alive control segment re-sends the latest grant even if nothing else is moving. This is the lesson's central mechanism.

A third issue is the end-to-end argument. Why does TCP carry its own 16-bit checksum when the Ethernet frame already has a 32-bit CRC? Because the link-layer CRC protects only one hop, and the chapter's classic example is a packet corrupted *inside a router* (a memory bit flip in the routing lookup). The link-layer CRC passed; the packet is delivered corrupted. Only an end-to-end check, computed by the sender and verified by the receiver, can catch this. The end-to-end argument (Saltzer, Reed & Clark, 1984) states: a correctness check at the lower layer is *not essential*; a correctness check at the endpoints *is* essential; lower-layer checks are a performance optimisation, not a correctness guarantee.

## The Concept

### Why variable windows, not fixed

The data link layer in Chapter 3 used fixed-size buffers, one per link. A router has a small number of links (a few to a few hundred) and each link has known characteristics, so dedicating a buffer pool per link is sensible. The transport layer is different:

- A host may have thousands of connections (a busy web server, a chat server, a database pool).
- Each connection's bandwidth varies over time (idle most of the time, bursting during page loads).
- The cost of dedicating 64 KB to every connection is prohibitive.

A variable-sized sliding window decouples buffer allocation from acknowledgement. The receiver tracks *how much buffer it currently has available*, advertises that number in the Window field of every ACK, and the sender treats it as the upper bound on outstanding bytes. When the application reads bytes from the socket, the receiver advertises more space; when the application stalls, the window shrinks toward zero and the sender stops sending.

The chapter's Figure 6-15 shows three implementations:

| Strategy | Pros | Cons |
|---|---|---|
| Fixed-size chained buffers (a) | Simple, one segment per buffer, easy to allocate | Wasted space for short segments; needs multiple buffers for long segments |
| Variable-size chained buffers (b) | Better memory utilisation | More complex management, fragmentation, harder to coalesce |
| One large circular buffer per connection (c) | Simple, no fragmentation, size-agnostic | Inefficient when most connections are idle |

Modern Linux uses a hybrid: a small per-connection TCB plus a slab-allocated pool of MTU-sized buffers (typically 2 KB or 4 KB) that the socket code pages in and out of the page cache as needed. The receive window is the free count in that pool; the Window field advertises the count in bytes.

### The 4-bit-sequence-number trace (Figure 6-16)

The chapter walks a 15-step trace of a datagram network with 4-bit sequence numbers (0-15, wrap-around). Data flows from A to B; ACKs and buffer grants flow from B to A. The relevant state on each line:

- A's "credits" (how many segments A may send without further ACK)
- B's "buffer pool" (how many free buffers B has)
- The last segment number A sent
- The last ACK number B sent

The trace unfolds:

| Line | Segment | Notes |
|---|---|---|
| 1 | `<request 8 buffers>` | A wants 8; A has 0 |
| 2 | `<ack=15, buf=4>` | B grants 4; A's credits = 4 |
| 3 | `<seq=0, data=m0>` | A's credits = 3 |
| 4 | `<seq=1, data=m1>` | A's credits = 2 |
| 5 | `<seq=2, data=m2>` | A's credits = 1; segment LOST |
| 6 | `<ack=1, buf=3>` | B acks 0 and 1, permits 2-4; A's credits = 3 |
| 7 | `<seq=3, data=m3>` | A's credits = 2 |
| 8 | `<seq=4, data=m4>` | A's credits = 1, blocked |
| 9 | `<seq=2, data=m2>` | A times out, retransmits; consumes a *reserved* buffer, not a credit |
| 10 | `<ack=4, buf=0>` | Everything acked, A still blocked (no credits) |
| 11 | `<ack=4, buf=1>` | A may send 5 |
| 12 | `<ack=4, buf=2>` | B finds 2 more buffers; A's credits = 2 |
| 13 | `<seq=5, data=m5>` | A's credits = 1 |
| 14 | `<seq=6, data=m6>` | A's credits = 0, blocked |
| 15 | `<ack=6, buf=0>` | A still blocked |
| 16 | `<ack=6, buf=4>` | **LOST** -- A does not see this; A is deadlocked |

`code/main.py` runs this exact trace and prints line-by-line state, including the line-16 deadlock. It then shows the fix: a periodic control segment from B that re-sends the latest grant regardless of whether B has new data to send.

### The deadlock hazard and its fix

A control segment carrying the buffer grant is itself a datagram that can be lost. The sender, on receiving *no* control segment, has no way to distinguish "B has no buffer space" from "B's last grant was lost". The protocol is stuck.

Three ways to break the deadlock:

1. **Periodic control segments**: B sends a gratuitous control segment every K milliseconds, carrying the current grant, even if it has nothing else to say. This is what TCP does with its persist timer (RFC 793 §4.4). When the sender's window hits zero, it starts a persist timer; when it expires, it sends a 1-byte window probe to trigger an ACK with the current window. A few such probes are tried before the connection is considered broken.
2. **Make the grant robust to loss**: use the same sequence number and ACK machinery as data, so a lost grant is retransmitted. This doubles the protocol's state and is rarely worth it.
3. **Sender-driven pacing**: A sends a byte anyway, hoping the receiver's buffer freed up. If the receiver's window is still zero, the byte is dropped (or its segment is dropped at the receiver), and the sender retries.

The persist-timer mechanism is the one used in practice. The default TCP persist timer is 5 seconds (Linux: `tcp_persist_timeout`), and the probe is 1 byte so the receiver can ACK it without making buffer commitments.

### The end-to-end argument

Saltzer, Reed & Clark's 1984 paper "End-to-End Arguments in System Design" articulates the principle:

> A function can only be correctly implemented end-to-end. Lower-layer implementations are a performance optimisation, not a correctness guarantee.

The chapter gives the example: a packet is corrupted inside a router (a memory bit flip during the routing-table lookup). The link-layer CRC on the previous hop passed; the link-layer CRC on the next hop will be computed over the corrupted bytes and pass too (it protects transmission, not memory). The packet is delivered to the destination with bit errors; the transport-layer checksum detects it; the segment is dropped and retransmitted.

The argument is stronger than "checksums are good". It is that:

- Lower-layer checks are *necessary for performance* (catching a corruption at hop N saves the cost of forwarding a bad packet to N+1, N+2, ..., end).
- Lower-layer checks are *not sufficient for correctness* (a corruption that occurs at any single hop, including inside a router, escapes them).
- End-to-end checks are *sufficient for correctness* (assuming an end-to-end checksum has enough redundancy, e.g. CRC-32, to detect any plausible in-flight corruption).

TCP's 16-bit checksum is supplemented by an MD5 or SHA-1 signature in some BGP and TLS contexts because the 16-bit checksum is not cryptographically strong — it detects random errors but not malicious tampering.

### Modern TCP flow control

TCP implements variable-window flow control in three layers:

1. **Receive Window (RWND)**: the receiver advertises its current free buffer count. Standard 16-bit field in the TCP header, RFC 793.
2. **Window Scale option (RFC 7323)**: extends the window to 30 bits by multiplying the field by a power of 2 negotiated in the SYN. Without this, a 1 Gbps link with 100 ms RTT has a bandwidth-delay product of 12.5 MB, which does not fit in 16 bits (max 64 KB).
3. **Congestion Window (CWND)**: the sender's view of the network's capacity. The sender's effective window is `min(RWND, CWND)`. The interaction is the modern TCP flow-control story: RWND prevents overflowing the receiver; CWND prevents overflowing the network.

The original chapter (and this lab) is about RWND only. Lesson 8 in this phase covers CWND and the AIMD control law in detail.

### Connection-level failure modes the trace exposes

- **Line 5**: a data segment is lost. The sender retransmits on timeout, but the retransmission *consumes a reserved buffer* (line 9) — it does not require a new credit. This is why credit-based flow control still works under loss: the retransmission is pre-paid.
- **Line 10**: receiver acknowledges everything but grants zero buffers. The sender is blocked but knows the receiver has the data; this is a normal back-pressure signal.
- **Line 16**: the grant is lost. The sender cannot distinguish this from "no grant ever came". The fix is the persist timer.
- **Receiver-only deadlock**: if the receiver's user process never reads from the socket, the window reaches zero and stays there. The persist timer is the only mechanism that ever wakes the sender up.

## Build It

1. Run `code/main.py`. It reproduces the 15-step trace of Figure 6-16 and then steps 16-18 to demonstrate the deadlock.
2. Inspect the line-9 retransmission: it consumes a "reserved" buffer, not a credit. Verify the math: after line 8, A had 1 credit; the retransmission is allowed because the segment is one of the "currently being timed out" set, not a new send.
3. Set the `lost` parameter to a different line (say line 12) and observe how the protocol recovers differently.
4. Add the persist-timer fix: after K seconds of no change, the receiver re-sends the last grant. Verify the deadlock breaks.
5. Implement the variable-size buffer pool: replace the unit buffer with a list of segment-length allocations and verify the credit accounting still works.
6. Compute the end-to-end bandwidth-delay product: 1 Gbps × 100 ms = 12.5 MB. Confirm that 16-bit TCP windows (max 64 KB) cannot cover this without the Window Scale option.

## Use It

| Task | Real tool | What good looks like |
|---|---|---|
| Watch the receive window change | `tcpdump -ni any 'tcp[tcpflags] & tcp-ack != 0' -vv` | The Window field grows when the application reads, shrinks when it stalls, and reaches 0 on back-pressure |
| Set Window Scale | `ss -i` | `wscale:7,7` shows the negotiated shift on both ends (RFC 7323) |
| Reproduce a zero window | `iperf3 -c host -P 1 -t 30 -w 32K` | Receiver window reported as 0 in tcpdump while the sender stalls; the persist timer fires |
| Trace retransmissions | `ss -ti` | `retrans:5/10` -- 5 retransmissions out of 10 sent; the per-connection retransmission accounting is the chapter's "reserved buffer" mechanism |
| Compute BD product | `ping -c 10 host; iperf3 -c host` | RTT × bandwidth gives the buffer size needed to keep the pipe full |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `tcpdump -vv` capture of a 30-second `iperf3` flow with the Window field annotated, showing it grow, shrink, and hit zero on a stalled receiver.
- A one-page writeup of the end-to-end argument with a packet trace that demonstrates an end-to-end check catching a corruption a per-hop CRC would miss (use a loopback test with intentional bit flips).
- A reproduction of the line-16 deadlock from Figure 6-16 in `code/main.py` with the persist-timer fix applied, and the time-to-recovery metric.

Start from [`outputs/prompt-dynamic-buffer-allocation-and-the-end-to-end-argument.md`](../outputs/prompt-dynamic-buffer-allocation-and-the-end-to-end-argument.md).

## Exercises

1. In the trace, what is the difference between A's "credits" and B's "buffer pool"? Why are they not the same number?
2. Predict the line-16 deadlock behaviour if the control segment's loss probability is 50% rather than 100%. How long does it take for the persist timer to break the tie?
3. The chapter lists three buffer pool strategies (Figure 6-15). For each, compute the wasted memory for a workload of 1 KB average segments on a 64 KB maximum-segment connection.
4. The end-to-end argument says a link-layer CRC is not essential for correctness. Identify one correctness property a link-layer CRC provides that an end-to-end checksum does *not*.
5. The chapter says the maximum data rate on a 1 Mbps / 100 ms RTT connection is `cr = 100 Kbit`. With stop-and-wait (window = 1 segment), what is the maximum throughput in segments/second? At 1000-bit segments, what is the throughput in bits/second? Why is it lower than 1 Mbps?
6. Set the `lost` parameter in `code/main.py` to line 9 (the retransmission itself). What does the protocol do? Is the trace still correct?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Sliding window | "the buffer size" | The number of unacknowledged bytes/segments the sender may have outstanding; a function of receiver capacity and network capacity |
| Receive window (RWND) | "the window" | The receiver's current free buffer count, advertised in the TCP Window field; limits the sender to the receiver's drainage rate |
| Congestion window (CWND) | "the cwnd" | The sender's view of the network's capacity; the sender paces to `min(RWND, CWND)` |
| Variable-sized window | "dynamic flow control" | The decoupling of buffer allocation from acknowledgement: the receiver advertises a current count, not a fixed maximum |
| Window Scale option | "wscale" | RFC 7323: extends the 16-bit TCP Window field to 30 bits by multiplying by 2^shift |
| Bandwidth-delay product | "BDP" | `bandwidth × RTT`; the number of bytes in flight needed to keep the pipe full |
| Persist timer | "the keepalive" | A timer that fires when the receiver's window is zero; sends a 1-byte probe to elicit an ACK with the current window |
| End-to-end argument | "checksums at every layer" | The principle that correctness must be implemented end-to-end; lower-layer checks are performance, not correctness |
| Reserved buffer | "retransmission slot" | A buffer pre-paid for a retransmission; consumes a reserved slot, not a new credit, so the credit accounting survives loss |

## Further Reading

- RFC 793 — Transmission Control Protocol (the original 16-bit Window field and the persist timer)
- RFC 7323 — TCP Extensions for High Performance (the Window Scale option, 30 bits, 1 GB windows)
- Saltzer, Reed & Clark, "End-to-End Arguments in System Design", ACM TOCS 2(4), 1984
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — section 6.2.4 (the chapter of this lesson)
- Stevens, *TCP/IP Illustrated, Volume 1: The Protocols*, 2nd ed. — Ch. 20 (TCP sliding window)
- `tcpdump(8)`, `ss(8)`, `iperf3(1)` Linux man pages
- `net.ipv4.tcp_window_scaling` and `/proc/sys/net/ipv4/tcp_persist_timeout` sysctl references
