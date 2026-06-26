# TCP Service Model, Byte Stream, and Segments

> TCP is a connection-oriented, reliable, full-duplex **byte stream** that runs over an unreliable IP internetwork (RFC 793, originally defined in September 1981 and since clarified by RFC 1122, RFC 1323, RFC 2018, RFC 2581, RFC 2873, RFC 2988, and RFC 3168). The sending application writes any number of bytes from 1 to 64 KB into a socket, and TCP is free to chop that data into segments of whatever size fits the path's MTU — typically 1460 data bytes after the 20-byte TCP header plus the 20-byte IPv4 header sit inside one 1500-byte Ethernet frame. On arrival, TCP places the bytes back into the receiving application's read buffer **without preserving message boundaries**: four 512-byte `write()` calls on the sender may appear as four 512-byte reads, one 2048-byte read, or anything in between. Each byte has its own 32-bit sequence number, the acknowledgement number is the next in-order byte expected, and a 16-bit window field controls flow control. The service also exposes out-of-band signaling through the URG flag and Urgent pointer, and a PUSH flag (mostly vestigial) that asks the receiver to deliver data without buffering. There is no support for multicast or broadcast — every TCP connection is point-to-point between exactly two sockets identified by the 5-tuple `{protocol, src IP, src port, dst IP, dst port}`.

**Type:** Learn
**Languages:** Python, Wireshark
**Prerequisites:** Layer 4 concepts from Phase 09 (Berkeley sockets, port numbers), IPv4 header layout (RFC 791), basic packet-capture reading
**Time:** ~75 minutes

## Learning Objectives

- Explain why TCP is a **byte stream** rather than a message stream, and predict how four 512-byte writes may be reassembled at the receiver.
- Compute the standard 20-byte TCP header layout and the default 1460-byte MSS that fits a TCP segment plus IPv4 header in one 1500-byte Ethernet frame.
- Trace a single byte from a `write()` call through the sender's send buffer, into one or more TCP segments, across the IP layer, into a reassembly queue, and out a `read()` call on the receiver.
- Use `code/main.py` to segment a 2,048-byte application write into MSS-sized TCP segments and verify the receiver can deliver the same 2,048 bytes in any chunking the application requests.
- Read the 5-tuple that identifies a TCP connection in `ss -tnp` or Wireshark, and explain why two sockets can host many simultaneous connections.
- Articulate the difference between the PSH flag (delivery hint) and the URG flag (out-of-band byte offset), and why URG is rarely used in practice today.

## The Problem

You are debugging a chat application. The client calls `send()` four times with 512 bytes each, and the server-side `recv()` reads come back as **one** 2,048-byte chunk. Worse, the server logs sometimes show **no** data for 200 ms even though the client just hit Enter. The protocol designer swears the application uses "TCP message framing," and you need to explain — with packet captures, not hand-waving — why TCP guarantees a byte stream and nothing more.

The deeper trap is the term "reliable." TCP is reliable in the sense that every byte the application wrote will eventually be delivered, in order, exactly once. It is **not** reliable in the sense of preserving the boundaries of `write()` calls, the urgency of an out-of-band interrupt, or any timing guarantee. Confusing those two contracts is the source of most "TCP randomly dropped my message" bug reports.

## The Concept

### The service: connection-oriented, full-duplex, byte stream

TCP exposes a connection as a pair of byte streams, one flowing each way, multiplexed onto the same 5-tuple. The contract is:

| Property | What TCP promises | What TCP does **not** promise |
|---|---|---|
| Connection-oriented | Explicit setup via 3-way handshake (lesson 19), explicit teardown | Anything about when data is "ready" |
| Reliable | Every byte delivered, in order, exactly once | That `write()` boundaries are visible at the receiver |
| Full-duplex | Independent byte streams in each direction | That data is delivered the moment you call `write()` |
| Flow-controlled | Sender never overruns receiver buffer | That a small write produces a small segment |
| Congestion-controlled | Sender never overwhelms the network | A specific latency or bandwidth floor |

There is no such thing as a "TCP message." If the application writes `"HELLO"` followed by `"WORLD"`, the receiver may see `"HELLOWORLD"`, `"HELLO"+"WORLD"`, or `"HELL"+"OWORLD"` — depending on how TCP and the OS scheduled the buffers.

### The byte stream has its own 32-bit coordinate system

Every byte on a TCP connection has a unique 32-bit sequence number. RFC 793 numbers the first byte of data the SYN carries as `ISN+1` (where `ISN` is the **initial sequence number** chosen at handshake time). Acknowledgements are **cumulative**: the receiver tells the sender "I have bytes up to but not including `N`." That single integer fully describes the in-order portion of the stream; out-of-order bytes must be buffered and reassembled.

Why 32 bits? In 1981 a 56-kbps line took over a week to wrap the sequence space. On a modern 1-Gbps link the wrap time is roughly 34 seconds — which is why RFC 1323 introduced **PAWS** (Protection Against Wrapped Sequence numbers) using the timestamp option to disambiguate old from new data.

### Anatomy of a TCP segment

A segment has a fixed 20-byte header (40 if options are used), plus zero or more data bytes. The hard limits are:

| Limit | Value | Reason |
|---|---|---|
| Header (no options) | 20 bytes | RFC 793 fixed part |
| Max header with options | 60 bytes | 4-bit data offset field can encode 0–15 32-bit words |
| Max data per segment | 65,495 bytes | 65,535 (16-bit length field max) − 20 IP header − 20 TCP header |
| Practical MSS over Ethernet | 1,460 bytes | 1,500 Ethernet MTU − 20 IP − 20 TCP |
| Default MSS when none negotiated | 536 bytes | RFC 879 / RFC 1122 fallback |

The MSS option is negotiated during the handshake. If neither side advertises it, both sides must accept at least 536 + 20 = 556-byte segments.

### What the sender actually does

When an application writes 10 KB, TCP does **not** push 10 KB onto the wire. It copies the bytes into the socket's **send buffer** and returns immediately. Then the TCP state machine decides how to drain the buffer:

1. Pack into segments of at most `min(MSS, cwnd, receiver window)` bytes.
2. Wrap each segment with a 20-byte TCP header (with the appropriate sequence number, ack number, window advertisement, and flags).
3. Hand the segment to IP, which prepends its own 20-byte header and fragments only if needed (modern stacks do path MTU discovery per RFC 1191 and avoid fragmentation).
4. If the segment fits the MTU, IP emits one Ethernet frame. If not, IP fragments.

The receiver mirrors the process in reverse: strip Ethernet, strip IP, deliver the segment to the TCP engine by 5-tuple lookup, place the bytes into the receive buffer at the correct sequence-number offset, advance the cumulative-ack counter, and generate an ACK. The application later reads from the buffer, and may get any contiguous slice the OS chooses to deliver.

### The 5-tuple: how one socket holds many connections

A socket is `(host IP, local port)`. A connection is `(local IP, local port, remote IP, remote port, protocol=TCP)`. Because the remote IP and remote port vary, the same listening socket on port 80 can host thousands of concurrent connections — one per client. `ss -tnp` on a busy web server shows hundreds of rows all with `Local Address: 10.0.0.1:80`, each with a different peer.

### PUSH and URGENT: signals almost no one uses

Two flags remain in the protocol but are practically obsolete:

- **PSH (Push)** — historically asked the receiver to deliver buffered data to the application without waiting for more. Modern implementations ignore it; Linux's `TCP_NODELAY` and Windows's equivalent are the real mechanisms to flush a small write immediately.
- **URG (Urgent)** plus the 16-bit Urgent pointer — meant to mark an offset from the current sequence number at which "urgent" data ends, used to interrupt a remote process (the famous telnet `CTRL-C` trick). The start of the urgent data is **not** marked, so the application has no portable way to find it. RFC 6093 (2011) recommends not using URG at all.

## Build It

Run the simulation offline:

```bash
cd phases/10-transport-services-and-protocol-mechanics/17-tcp-service-model-and-bytestream-segments
python3 code/main.py
```

The script prints:

1. The 5-tuple for a sample connection between two sockets, including two simultaneous connections that share a socket.
2. How a 2,048-byte `write()` is segmented into MSS-sized TCP segments, each labeled with its sequence number and length.
3. How four 512-byte writes produce the same on-the-wire segments (TCP coalesces), then how the receiver can deliver them as four reads, one read, or any mix.
4. The byte accounting for a single 1,460-byte segment, including the 14-byte Ethernet header, 20-byte IPv4 header, and 20-byte TCP header.
5. A worked example showing the sequence-number progression of a 1 KB → 2 KB → 4 KB data transfer during the slow-start phase.

Use the `segments()` function to plug your own write sizes and verify the wire layout.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| "TCP doesn't preserve message boundaries" | `simulate_application_boundary_loss()` prints four 512-byte writes coalesced into a single 2,048-byte segment | Wireshark `tcp.stream` shows the same bytes regardless of how `recv()` returned them |
| "Every byte has a sequence number" | `segment_layout(2048)` lists `SEQ=<N>, len=1460` for each segment | Wireshark right-click → Follow TCP Stream shows the byte offset |
| "MSS = MTU − 40" | `mtu_math(1500)` returns 1460 data bytes | `ip route show` + `cat /proc/sys/net/ipv4/tcp_window_scaling` |
| "Two clients can share port 80" | `five_tuple_demo()` shows the 5-tuple varies per connection | `ss -tnp state established` on any web server |
| "Data offset tells you the header length" | `header_layout()` enumerates the 20-byte fixed part | Wireshark TCP detail pane under "Header Length" |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable one-page TCP service contract (the table at the top of this lesson) and a wire-format diagram (the SVG asset).
- The byte-accounting table for your most common MSS — typically Ethernet's 1,460 bytes — so the team can quote overhead without thinking.

Start from [`outputs/prompt-tcp-service-model-and-bytestream-segments.md`](../outputs/prompt-tcp-service-model-and-bytestream-segments.md).

## Exercises

1. An application writes 5,000 bytes into a TCP socket. MSS is 1,460. How many segments does TCP send, what are their sequence numbers, and what does each segment look like on the wire (bytes on the cable)?
2. The receiver does one 5,000-byte `read()`. Does the kernel guarantee it returns 5,000 bytes, or might it return less? What flag or syscall would you use to handle short reads?
3. A web server listens on port 80. Two clients connect from the same NAT, both with source port 49152. Can the server distinguish them? What field in the 5-tuple breaks the tie?
4. Two independent writes of 200 bytes each happen 1 µs apart. Will they always produce two segments? Show the conditions under which Nagle's algorithm collapses them into one.
5. Using `code/main.py`, run `simulate_application_boundary_loss()` for writes of sizes `[100, 100, 100, 100]` and `[400]`. Compare the resulting segments and explain why.
6. The Urgent pointer points to byte offset `N+10` from the current sequence number `N`. How many bytes of urgent data does that imply, and why is the **start** of the urgent data not marked?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Byte stream | "TCP sends messages" | TCP sends an ordered sequence of bytes with no record boundaries |
| 5-tuple | "the socket pair" | `{protocol, src IP, src port, dst IP, dst port}` — uniquely identifies one connection |
| MSS | "segment size" | Maximum **data** bytes in one segment; default 1,460 on Ethernet |
| Sequence number | "packet number" | The 32-bit offset of the **first data byte** in this segment |
| Cumulative ACK | "what I received" | The next in-order byte the receiver expects; summarizes all earlier bytes |
| PSH flag | "flush now" | Historical hint to deliver data without buffering; ignored by modern stacks |
| URG flag | "interrupt the peer" | Marks an out-of-band offset; start is undefined, deprecated by RFC 6093 |
| ISN | "starting packet" | Initial Sequence Number chosen at handshake; bytes are numbered `ISN+1, ISN+2, …` |

## Further Reading

- RFC 793 — Transmission Control Protocol (original TCP specification, September 1981)
- RFC 1122 — Requirements for Internet Hosts — Communication Layers (clarifications and bug fixes)
- RFC 879 — The TCP Maximum Segment Size and Related Topics
- RFC 1323 — TCP Extensions for High Performance (window scale, timestamps, PAWS)
- RFC 1191 — Path MTU Discovery (how TCP avoids IP fragmentation)
- RFC 6093 — On the Implementation of the TCP Urgent Mechanism (deprecates URG)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, sections on TCP service model and segments
- Wireshark User's Guide — Follow TCP Stream and the TCP header detail pane