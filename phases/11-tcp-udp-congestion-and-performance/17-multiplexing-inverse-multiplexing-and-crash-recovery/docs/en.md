# Transport multiplexing, inverse multiplexing (SCTP), and host crash recovery

> A host has many transport connections and only one (or a few) network addresses. **Multiplexing** is the job of mapping many transport endpoints (TSAPs) onto a smaller number of network endpoints (NSAPs) so the kernel can deliver each incoming segment to the right socket. The reverse — **inverse multiplexing**, or splitting one logical connection across multiple network paths for higher bandwidth or survivability — is the design point of SCTP (RFC 4960) and the modern MPTCP (RFC 8684). This lesson also covers the chapter's host-crash-recovery impossibility result (Figure 6-18): with two choices for the server (ack-then-write, write-then-ack) and four for the client (always, never, in S0 only, in S1 only retransmit), all eight combinations have at least one event ordering that loses or duplicates a message. The conclusion: "recovery from a layer N crash can only be done by layer N+1". The companion `code/main.py` is a stdlib-only simulator that maps many 5-tuple connections to one IPv4 NSAP (multiplexing), round-robins a single logical stream over N parallel paths (inverse multiplexing, SCTP-style), and walks the 8 × 6 crash-event matrix to confirm the chapter's claim.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Lesson 14 (Berkeley sockets); lesson 15 (TSAP/NSAP); chapter sections 6.2.5 and 6.2.6
**Time:** ~90 minutes

## Learning Objectives

- Distinguish **upward multiplexing** (many transport connections on one NSAP) from **inverse multiplexing** (one transport connection over many NSAPs) and give a real protocol example of each.
- Trace the demultiplexing step on segment arrival: the 5-tuple `(proto, src_ip, src_port, dst_ip, dst_port)` selects exactly one socket.
- Implement a round-robin inverse multiplexer in pure Python, including the reorder/reassembly buffer that SCTP requires to deliver in-order to the application.
- Reproduce the chapter's Figure 6-18 matrix: for every (server-strategy × client-strategy) combination, find an event ordering that causes data loss or duplication.
- State the "recovery from a layer N crash can only be done by layer N+1" result and identify which layer is responsible for what after a host crash.
- Distinguish SCTP's multi-homing (RFC 4960) from MPTCP's multi-path (RFC 8684) and explain when each is the right tool.

## The Problem

You run a busy HTTP server on a single machine with one IPv4 address. The server handles 50,000 concurrent connections from 50,000 different clients. How does the kernel deliver each incoming segment to the right socket? The answer is the **transport demultiplexer**: for every arriving segment, the kernel looks up the 5-tuple `(protocol, src_ip, src_port, dst_ip, dst_port)` in a hash table, finds the matching TCB, and appends the segment to that socket's receive queue. Without this hash table, the kernel has no way to tell which process owns a given segment.

The reverse problem is the inverse multiplexer. Your server has two 10 Gbps links to the ISP, but TCP is bound to a single 5-tuple and therefore a single path. A single TCP connection uses only one link at a time; the second link is wasted on the bytes of any one flow. SCTP (RFC 4960) and MPTCP (RFC 8684) fix this by letting a single association use multiple paths simultaneously: round-robin the data, reassemble in order, and survive the loss of any one path. This is the inverse-multiplexer design point.

A third problem is the one the chapter proves impossible: host crash recovery. The transport entity is in the kernel; the user data is in the application. If the host crashes between "server writes to the application" and "server ACKs to the client", the client cannot tell whether the data was delivered. The chapter's 8 × 6 matrix shows there is no combination of strategies that avoids both loss and duplication in all six possible orderings of the three events (send ACK, write data, crash). The conclusion is structural: only the application can decide what to do, because only it has persistent state that survives a crash (e.g. a write-ahead log, a database transaction ID, an idempotency key).

## The Concept

### Multiplexing: many TSAPs onto one NSAP

Figure 6-17(a) of the chapter shows four distinct transport connections sharing one network path between the same two hosts. Each connection is identified by its 5-tuple: `(proto, src_ip, src_port, dst_ip, dst_port)`. The same pair of hosts can have hundreds of connections; the kernel keeps a hash table of all live 5-tuples and routes each arriving segment to the matching socket.

The hash table is the demultiplexer. On the sending side, the kernel does the same in reverse: each socket has a 5-tuple, and the IP/UDP/TCP headers are filled in from it. The two ends agree on the 5-tuple during connection establishment (TCP three-way handshake) or first datagram (UDP). The protocol number (TCP=6, UDP=17) is in the IP header; the ports are in the transport header; the IPs are in the IP header. The five fields are all in the on-wire packet, so any router along the path can inspect them but only the endpoints act on them.

Multiplexing raises two practical concerns:

1. **Port collisions**: two clients on the same host picking the same ephemeral port for two different servers. The kernel prevents this by allocating from a range and avoiding ports already in use.
2. **Connection stealing**: an attacker spoofs the source IP and port of an existing connection to inject data. TCP mitigates this with sequence numbers (the attacker must guess the next sequence number to inject an acceptable segment); modern kernels add a randomised initial sequence number (RFC 1948) and a TCP MD5 signature option (RFC 2385) for high-stakes paths.

### Inverse multiplexing: one TSAP over many NSAPs

Figure 6-17(b) of the chapter shows the inverse case: a single transport connection distributed over multiple network paths. The motivation is bandwidth and survivability. A 10 Gbps server with two 10 Gbps uplinks cannot saturate either with a single TCP connection; with inverse multiplexing, the connection can use both and reach 20 Gbps aggregate. The secondary benefit is failover: if one path drops, the connection continues on the remaining paths.

Two protocols implement this in production:

| Protocol | RFC | Use case |
|---|---|---|
| SCTP (Stream Control Transmission Protocol) | RFC 4960 | Telecom signalling (SS7-over-IP, Diameter), one-to-many sockets, multi-homing |
| MPTCP (Multi-Path TCP) | RFC 8684 | Apple iOS, Samsung Android, Linux kernel: aggregate Wi-Fi and cellular on phones |

SCTP's multi-homing is a "primary + failover" model: the association has one primary path and one or more alternates; data flows on the primary until it fails, then the secondary is promoted. MPTCP's multi-path is "use them all": the connection schedules segments across all available paths to maximise throughput.

Both protocols face the same fundamental challenge: **reordering**. With one path, segments arrive in order; with two paths, they may not. The receiver must buffer out-of-order segments and deliver them to the application in sequence number order. SCTP uses a 32-bit stream sequence number; MPTCP uses the underlying TCP sequence number on each subflow. The reassembly buffer is the additional cost of inverse multiplexing.

### SCTP's connection model: association, not connection

SCTP replaces the single-stream "connection" with a multi-stream "association". A single association can carry many independent streams (think of them as sub-channels within one connection), each with its own sequence numbers. Loss on one stream does not block delivery on the others — the famous TCP "head-of-line blocking" problem. This is why SCTP is used for SS7-over-IP: a lost signalling message on one circuit should not stall signalling on other circuits.

SCTP also runs a four-way handshake (INIT, INIT-ACK, COOKIE-ECHO, COOKIE-ACK) with a 32-bit verification tag and a cookie that proves the client received the INIT-ACK. This closes the SYN-flood denial-of-service attack that plagues TCP's three-way handshake: the server allocates no state for a client until the client proves it received the server's INIT-ACK by echoing the cookie. TCP added SYN cookies (RFC 4987) later for the same reason.

### Host crash recovery: the 8 x 6 matrix

Figure 6-18 of the chapter proves a structural result. Three events at the server can occur in six orderings (AC, AWC, C(AW), C(WA), WAC, WC(A) — where C cannot be followed by A or W). Two server strategies (ack-then-write vs. write-then-ack) and four client strategies (always retransmit, never retransmit, retransmit in S0 only, retransmit in S1 only) give 8 combinations. For each combination, the matrix shows which event orderings cause OK, DUP, or LOST.

| Server: | First ACK, then write | First write, then ACK |
|---|---|---|
| Client: always retransmit | DUP on AWC, DUP on C(WA) | DUP on AC(W) |
| Client: never retransmit | LOST on AC(W), AWC, C(AW), C(WA) | LOST on AWC, C(AW), C(WA) |
| Client: retransmit in S0 | DUP on AWC, LOST on C(AW), C(WA) | DUP on C(WA) |
| Client: retransmit in S1 | LOST on AC(W) | DUP on WC(A) |

Every cell has at least one LOST or DUP. The conclusion, restated in the chapter, is:

> Recovery from a layer N crash can only be done by layer N+1.

In the Internet stack, this means the *application* is responsible for crash recovery, because the application is the only layer that persists state across the crash. The transport layer can detect the crash (via keepalive, RST, or a connection-timeout) but cannot decide whether the last operation completed. The application uses durable mechanisms — write-ahead logs, idempotency keys, two-phase commit — to ensure that the operation either happened exactly once or did not happen at all.

The 2020s echo of this result is the "exactly-once delivery" problem in Kafka, RabbitMQ, and other message brokers. No broker can provide exactly-once delivery to a consumer that might crash mid-processing; the consumer must use an idempotency key (e.g. a database row with a unique constraint) to deduplicate retries. The same structural impossibility, the same architectural solution.

### Why this matters for protocol design

The lesson generalises: a layer cannot fix a problem that occurs in a layer above it. The transport layer cannot make the application crash-safe. The application cannot make the link layer reliable. The link layer cannot make the physical layer error-free. Every layer can only provide a *contract* that the layer below either satisfies or violates. The interesting protocol design work is in the contracts: what does TCP promise to the application? What does the application promise to TCP? What does Ethernet promise to the IP layer? What does the fibre promise to the Ethernet layer?

The end-to-end argument of lesson 16 and the crash-recovery result of this lesson are the two pillars of that design philosophy. Together they say: lower layers provide best-effort service; the endpoints are responsible for correctness; the application is the last line of defence.

## Build It

1. Run `code/main.py`. It executes four demonstrations:
   - A 5-tuple hash table that routes incoming segments to the right socket (multiplexing).
   - A round-robin inverse multiplexer that splits a single byte stream across three paths and reassembles in order.
   - The 8 × 6 crash-recovery matrix from Figure 6-18.
   - A short comparison of SCTP vs. MPTCP.
2. Inspect the multiplexing trace: confirm that segments from the same 5-tuple all land in the same socket, and segments with different source ports land in different sockets even when the destination is identical.
3. Inspect the inverse-multiplexing trace: confirm the byte stream is split round-robin across three paths, and the receiver reassembles in order despite path 2 being slower.
4. Walk the crash-recovery matrix: pick the cell "Client always retransmits, Server ACK first" and confirm that the `AWC` ordering produces a duplicate message (server wrote, then crashed, then client retransmitted, then server recovered and ACKed again).
5. Add a fifth event ordering you think the chapter missed. Re-run; predict whether it adds a new failure mode.
6. Replace the round-robin scheduler in the inverse multiplexer with a lowest-RTT-first scheduler. Verify the receiver still reassembles correctly.

## Use It

| Task | Real tool | What good looks like |
|---|---|---|
| Inspect 5-tuple routing | `ss -tna` | Each row is one 5-tuple; the `Recv-Q` and `Send-Q` columns are the per-socket buffer counts |
| Watch SCTP multi-homing | `ss -0na` (SCTP family) | One association with multiple local and remote addresses; the kernel marks one as primary |
| Watch MPTCP on a phone | `ss -Mta` (with `CONFIG_MPTCP` enabled) | The `subflows` count is > 1, showing the kernel is using Wi-Fi and cellular in parallel |
| Reproduce TCP head-of-line blocking | `iperf3 -c host -P 1` with a 1% drop rate on the path | Throughput collapses even when only one stream of one connection is dropping — the stream stalls behind the lost packet |
| Trace crash recovery | `kill -9 server; ps aux \| grep server`; tail the application log | The new server starts; the client sees a RST or a connection timeout; the application log shows a "recovered, last operation status unknown" message |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `ss -tna` capture of a busy server showing 50,000 connections multiplexed over one NSAP, with the per-connection state summarised.
- A demonstration of MPTCP on a Linux box with two interfaces (loopback and a real NIC, or two NICs), showing the per-subflow counters.
- A written design for a small application's crash-recovery story: which operations are idempotent and safe to retry, which require an idempotency key, which require two-phase commit.

Start from [`outputs/prompt-multiplexing-inverse-multiplexing-and-crash-recovery.md`](../outputs/prompt-multiplexing-inverse-multiplexing-and-crash-recovery.md).

## Exercises

1. In the multiplexing simulation, two segments arrive with the same destination IP and port but different source ports. Which socket does each go to? Why?
2. The inverse multiplexer in `code/main.py` round-robins by sequence number. What happens if path 2 has a 50% packet loss but paths 1 and 3 are perfect? Compute the throughput penalty.
3. In the crash-recovery matrix, the cell "Client always retransmits, Server write first" has the WC(A) ordering produce a DUP. Walk through the events and explain why.
4. RFC 4960 §6.8 defines SCTP's "verification tag" — a 32-bit random number chosen by the receiver. Compare this to TCP's initial sequence number. Why does SCTP need a tag in addition to the sequence number?
5. MPTCP's default scheduler picks the path with the lowest smoothed RTT. Under what conditions does this produce worse throughput than a round-robin scheduler? (Hint: think of paths with very different bandwidths.)
6. The chapter says "recovery from a layer N crash can only be done by layer N+1". Give one example of a recovery that a lower layer *can* do, and explain why it does not violate the rule.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Multiplexing | "many connections on one IP" | The transport layer's job of mapping many TSAPs to one NSAP so the kernel can route each segment to the right socket |
| Demultiplexer | "the 5-tuple lookup" | The hash table in the kernel that maps the 5-tuple of an incoming segment to a TCB |
| 5-tuple | "the connection ID" | `(proto, src_ip, src_port, dst_ip, dst_port)` — the unique identifier of a transport connection in the kernel |
| Inverse multiplexing | "use many paths" | Splitting a single transport connection over multiple network paths for bandwidth or survivability |
| SCTP | "Stream Control Protocol" | RFC 4960; a transport with multi-homing and multi-streaming, used for telecom signalling |
| MPTCP | "Multi-Path TCP" | RFC 8684; TCP that schedules across multiple paths to aggregate bandwidth |
| Association | "an SCTP connection" | An SCTP endpoint state, distinct from a connection in that it can have many streams and many paths |
| Head-of-line blocking | "the stalled stream" | The TCP property that a lost segment stalls all later segments on that connection; SCTP streams avoid this |
| Crash recovery | "what about the data?" | The structural problem that a host crash between the server's "write" and "ack" leaves the client unsure whether the operation happened |
| Idempotency key | "the dedup ID" | A unique tag the application attaches to an operation so a retried request is deduplicated if the original succeeded |

## Further Reading

- RFC 793 — Transmission Control Protocol (the original single-path, single-stream contract)
- RFC 4960 — Stream Control Transmission Protocol (multi-homing, multi-streaming, the four-way handshake, verification tags)
- RFC 8684 — TCP Extensions for Multipath Operation with Multiple Addresses (MPTCP)
- RFC 1948 — Defending Against Sequence Number Attacks (why TCP needs unpredictable ISNs)
- RFC 2385 — Protection of BGP Sessions via the TCP MD5 Signature Option (a connection-level integrity check)
- Saltzer, Reed & Clark, "End-to-End Arguments in System Design", ACM TOCS 2(4), 1984
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — sections 6.2.5 and 6.2.6
- `ss(8)`, `sctp(7)`, `ip(7)` Linux man pages
- "Killed by a legend: the SCTP story" (Stewart & Xie, *Stream Control Transmission Protocol*, 2001)
