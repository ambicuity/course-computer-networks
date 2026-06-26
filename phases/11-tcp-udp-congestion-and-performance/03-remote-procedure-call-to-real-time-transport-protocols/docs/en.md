# Remote Procedure Call to Real-time Transport Protocols

> Section 6.4.2 turns the network's request-reply into something that *looks* like a local function call. **Remote Procedure Call (RPC)** inserts a **client stub** and **server stub** (Birrell and Nelson, 1984) so the application programmer writes `result = get_ip_address("example.com")` and the wire format is hidden. The five canonical steps are *call → marshal → send → receive → unmarshal*, and the textbook calls out three snags: **pointer parameters** (replaced by call-by-copy-restore), **weakly typed languages** (the stub has no way to know the array length), and **type deduction**. Section 6.4.3 introduces **RTP** (RFC 3550) on top of UDP for real-time media: a 12-byte fixed header with **V/P/X/CC/M/PT** flags, a 16-bit sequence number, a 32-bit timestamp, and a 32-bit **SSRC** identifier. RTCP (RFC 3550, the sibling) carries feedback and caps its bandwidth at **5% of media bandwidth**. A receiver runs a **playout buffer** to absorb jitter, picking a playback point that captures ~99% of late packets (typically ~10 s for streaming, ~100 ms for live voice).

**Type:** Build
**Languages:** Python, no external dependencies
**Prerequisites:** UDP header (lesson 02 of this phase), basic binary protocol framing, sample-rate audio concepts
**Time:** ~100 minutes

## Learning Objectives

- Sketch the five-step RPC flow (client call → marshal → send → receive → unmarshal) and identify which step happens on which machine.
- Explain why pointers and variable-length arrays cannot be passed naïvely across an RPC boundary and how call-by-copy-restore papers over the first problem.
- Construct a minimal **XDR-style** argument marshaling for two fixed-argument RPCs and decode the matching server-stub call.
- Decode an **RTP header** (version 2, padding bit, extension bit, CSRC count, marker, payload type, sequence number, timestamp, SSRC) from raw bytes.
- Compute the **RTCP bandwidth budget** (5% of media) and reason about why the rate scales with the number of participants.
- Simulate a **playout buffer** that absorbs jitter and explain the trade-off between buffer size, late-packet loss, and interactivity.

## The Problem

A small fintech startup builds a *portfolio dashboard* on top of six microservices: account service, position service, pricing service, FX service, market-data service, and tax service. The front-end in the browser makes dozens of cross-service calls per page render. The simplest implementation, *direct HTTP*, forces the front-end to know the URL of every service, the retry policy of every service, the serialization format of every service, and the timeout of every service. When the pricing service moves from gRPC-Web to plain JSON over WebSocket because the WebSocket reverse proxy cannot handle HTTP/2 trailers, every consumer of the pricing service has to change.

The textbook's response is the **RPC abstraction**: write `price = pricing.GetQuote(symbol)` and let the stubs handle transport, framing, retry, and serialization. The same principle appears in voice-over-IP — *play out this audio sample* must look local to the audio renderer, not like *receive UDP datagram from 192.0.2.7*.

This lesson is about the textbook's two layered abstractions on UDP:

- **RPC** at the application layer (Sec. 6.4.2) for the request-reply shape.
- **RTP** at the transport layer (Sec. 6.4.3) for streaming media with timing and feedback.

## The Concept

### The five steps of an RPC

Section 6.4.2 lays out RPC's five-step flow (Fig. 6-29). The application calls a normal-looking procedure; the call enters a **client stub** (sometimes called a *proxy*), which marshals the arguments into a wire message and dispatches a UDP datagram (or TCP stream) to the server. On the server side, the **server stub** unmarshals the bytes and calls the actual server procedure with the recovered arguments. The result traces the reverse path.

| Step | Location | Action |
|---|---|---|
| 1 | Client | Application calls client stub as if it were local. |
| 2 | Client | Stub **marshals** arguments into a message and writes it to a socket. |
| 3 | Network | OS transmits the datagram(s) to the server. |
| 4 | Server | OS hands incoming bytes to server stub. |
| 5 | Server | Stub **unmarshals** arguments and calls the server procedure. |

The crucial observation is that *the application programmer sees none of this*. The client procedure and client stub are in the same address space; the parameters are passed through the normal C/Go/Java calling convention. The server procedure is called by a procedure in the same address space on the server. From the application's perspective, "I/O is done on sockets" has been replaced by "faking a normal procedure call."

### Three problems with RPC and their textbook responses

**Pointer parameters.** A local call passes `int *p` by sharing the address. Across machines, that address is meaningless. The textbook's trick is **call-by-copy-restore**: the client stub dereferences the pointer, sends the value to the server, the server stub allocates a fresh pointer to a local copy, the server modifies it, and the modified value is sent back. The client stub writes it over the original location. The technique works for scalars and fixed structs; it fails for graphs, linked lists with cycles, and anything with embedded pointers whose target is also remote.

**Weakly typed languages.** In C, `int inner_product(int a[], int b[])` says nothing about the array lengths. The stub cannot marshal what it cannot size. The textbook's response: restrict RPC parameters to typed languages (Java, Go) or to IDL-defined interfaces (Sun XDR, DCE RPC, gRPC protobuf), where the wire types are declared at compile time.

**Type deduction.** Closely related: in older systems the stub compiler could not recover the types at the call site. Modern IDLs solve this by generating stubs from a `.proto` / `.x` / `.thrift` file.

### RPC in practice today

The textbook's exposition is the ancestor of three things you will see in production:

- **Sun RPC / ONC RPC** (RFC 5531, originally RFC 1050 in 1988): the original UDP/TCP-switching RPC. Uses XDR for marshaling. Port 111 for the portmapper. The `rpcbind` service maps a program number and version to a port.
- **gRPC**: HTTP/2 + protobuf + TLS. The stub compiler produces client and server stubs in 11 languages. Most cloud-internal RPC today.
- **Thrift** (originally Facebook, now Apache): IDL + code generation, predates gRPC.

All three preserve the textbook's five-step model, but they layer in TLS for confidentiality, multiplexing for parallelism, and a stub compiler so the programmer never hand-rolls a marshaling routine.

### RPC failure modes worth knowing

The textbook mentions three but the modern reality adds a fourth:

| Failure mode | Textbook response |
|---|---|
| Lost request | Client retransmits after timeout (at-least-once). |
| Lost reply | Client retransmits; the server procedure runs **twice** unless the procedure is idempotent. |
| Server crash before reply | Client retries; semantics shift to *at-least-once* or *at-most-once* depending on the protocol. |
| Duplicate retry after a slow reply | Idempotency is the application's job — stripe a request ID, deduplicate by ID, or design the operation to be safe to repeat. |

### RTP: real-time media on top of UDP

Section 6.4.3 shifts to a different abstraction. **RTP** (Real-time Transport Protocol, RFC 3550) is the standard framing for audio and video over UDP. It does **no retransmission** — late packets are dropped, not recovered — and it adds four things that UDP alone does not provide:

1. A **sequence number** so the receiver can detect loss.
2. A **timestamp** so the receiver can play each sample at the right wall-clock time regardless of when it arrived.
3. A **payload type** so the receiver knows the encoding (PCM, MP3, Opus, VP8, H.264, ...).
4. A **synchronization source identifier (SSRC)** so multiple senders can share one UDP socket.

The RTP header (Fig. 6-31 of the textbook) is at minimum 12 bytes:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M| Payload Type|       Sequence Number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           Timestamp                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             Synchronization Source (SSRC) identifier         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|            Contributing Source (CSRC) identifiers             |
|                             ....                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Bits | Meaning |
|---|---|---|
| V | 2 | Version; always `2`. (3 is reserved as an escape.) |
| P | 1 | Padding byte count at end of payload (last byte tells how many). |
| X | 1 | Extension header present. |
| CC | 4 | CSRC count (0-15). |
| M | 1 | Marker; app-defined (start of talkspurt, end of video frame). |
| PT | 7 | Payload type (0 = PCM mu-law, 8 = PCM 8 kHz, 96-127 = dynamic). |
| Sequence | 16 | Increment by 1 per packet; receiver detects loss. |
| Timestamp | 32 | Sample timestamp of the first sample in this packet. |
| SSRC | 32 | Identifier of the synchronization source (random). |
| CSRC | 32 each | Contributing sources when a mixer is in play. |

The textbook notes that RTP itself has no acknowledgements and no retransmission. The application decides whether a missing packet is "skip the video frame," "interpolate the audio," or "do nothing."

### RTCP: feedback, sync, and naming

**RTCP** (Real-time Transport Control Protocol, RFC 3550 § 6) is the sibling control protocol. It runs on the *next* UDP port number above the RTP port (so if RTP is 5004, RTCP is 5005) and carries:

- **Sender reports (SR)**: how many packets sent, how many bytes sent, the sender's NTP timestamp at the time of the report.
- **Receiver reports (RR)**: fraction lost, cumulative packets lost, jitter estimate (the RFC 3550 algorithm), last SR timestamp, delay since last SR.
- **Source descriptions (SDES)**: CNAME (canonical name), NAME (real name), EMAIL, PHONE, LOC, TOOL, NOTE, PRIV.
- **BYE**: end of participation.
- **APP**: application-defined.

The 5%-of-media rule: RTCP traffic from all participants must collectively consume at most 5% of the session bandwidth. With more participants, each sender slows its RTCP rate proportionally. The math: each participant sends a compound RTCP packet at intervals proportional to `(number of senders + number of receivers)`, so a 100-party conference sees each participant report roughly once every 30 seconds rather than every 5.

### Playout buffer: trading latency for late-packet tolerance

Section 6.4.3's last topic is the **playout buffer** at the receiver. The textbook's Fig. 6-32 shows a stream of packets arriving with substantial jitter; without buffering, the audio skips or distorts every time a packet is late.

The fix is to delay playout by a fixed interval `P`. Packets are queued as they arrive; the playout scheduler pulls them from the queue at uniform intervals. The size of `P` is the **playout point** (sometimes called the *jitter buffer depth*).

| Application class | Typical playout point | Rationale |
|---|---|---|
| Live VoIP | 50-200 ms | Low latency dominates; some late loss is acceptable. |
| Video conferencing | 100-300 ms | Slightly larger to accommodate video frames. |
| Streaming audio | 5-15 s | Smooth playback dominates; user has already waited for buffering. |
| Streaming video | 5-30 s | Same; large pre-roll hides jitter. |

The trade-off is fundamental: a larger `P` captures more packets at the cost of end-to-end delay. The textbook notes the clever adaptation of changing `P` *between talkspurts* in voice — the M marker bit signals the start of a new talkspurt, the receiver can lengthen or shorten `P` at that boundary, and the user perceives no glitch because a slightly different silence is invisible.

## Build It

The artifact is `code/main.py`, a stdlib-only demonstration of three things from Sec. 6.4.2 and 6.4.3:

1. **Five-step RPC simulator**
   - Define a `procedure` (e.g., `add(a, b)` and `get_quote(symbol)`).
   - Implement a `client_stub` that marshals `(proc_id, args)` into a byte string.
   - Implement a `server_stub` that unmarshals, dispatches, marshals the result, and returns it.
   - Trace the five-step flow with print statements showing where each step happens.

2. **RTP packet encoder and decoder**
   - Define a `RTPPacket` dataclass with `version`, `padding`, `extension`, `cc`, `marker`, `pt`, `seq`, `timestamp`, `ssrc`, `payload`.
   - Implement `encode_rtp(pkt)` that produces the 12-byte header plus payload.
   - Implement `decode_rtp(raw)` that parses the same bytes back.
   - Show the byte layout for a typical Opus audio packet (PT=111, M=1 on the first packet of a talkspurt).

3. **Playout-buffer simulator**
   - Simulate a sender producing 20 packets at uniform intervals with **jittered arrival** at the receiver.
   - Run a playout buffer with `P = 4` packet-times.
   - Print which packets were played on time, which arrived late and were skipped, and the average wait.

4. **RTCP bandwidth budget**
   - For a 64 kbps voice call with N participants, compute the allowed RTCP rate per participant.
   - Verify the total stays below 5% of media bandwidth.

Run with `python3 code/main.py`. No pip dependencies.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm RPC | Wire dump from `tcpdump -i lo -nn -X port 12345` showing request and reply. | The first 4 bytes identify the procedure and version; the remainder is the marshaled args. |
| Confirm RTP | Wireshark decode of `rtp` traffic with PT, seq, timestamp, SSRC shown. | Sequence numbers increment by 1; timestamps increment by the samples-per-packet; SSRC stable for the stream. |
| Diagnose jitter | Receiver's `jitter` calculation (RFC 3550 formula) over the last 16 packets. | Jitter > 50 ms means the playout buffer should grow; jitter < 5 ms means it can shrink. |
| Confirm playout point | Receiver log of `late_packets / total_packets` over a window. | Rate below 1% is acceptable for voice; above 5% means the playout point is too small. |
| Diagnose RTCP overuse | Aggregate RTCP bytes per second for the session. | Total must stay below 5% of the media bandwidth, or participants must scale down. |

## Ship It

The `outputs/` directory should contain `rpc-rtp-runbook.md` with three sections:

1. **Stub generation recipe**: the gRPC/Thrift command line that generates client and server stubs from your `.proto`.
2. **RTP field checklist**: a header-field reference table for the streams you actually use, with the SSRC allocation policy documented.
3. **Playout-point selection table**: a table of recommended `P` for each application class in your deployment, with the jitter budget that justifies each value.

## Exercises

1. **Stub generator for `add(a, b)`**. Implement a 5-byte message format: 1 byte procedure ID, 4 bytes for two 16-bit integers. Marshal and unmarshal by hand; confirm round-trip equality.
2. **Pointer parameter via copy-restore**. Simulate a remote procedure that increments `*p` by 1. Verify that the change propagates back to the caller after the call returns.
3. **RTP round-trip**. Build an RTP packet with `seq = 1000, timestamp = 48000, ssrc = 0x12345678, payload = b"\x00\x01"`. Decode it and confirm all four fields match.
4. **CSRC field**. Construct an RTP packet with two CSRC values (`0xDEADBEEF, 0xCAFEBABE`) and confirm the header length grows by 8 bytes.
5. **RTCP bandwidth**. For a 100-party video conference at 2 Mbps, compute the maximum allowed aggregate RTCP rate and the per-participant report rate if each compound packet is 100 bytes.
6. **Playout buffer**. Simulate 20 packets emitted at 20 ms intervals with ±5 ms jitter. Run a playout buffer with `P = 60 ms`. Count the packets played on time and the packets that arrived after their playout slot.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Stub | "A local function that fakes the server." | The client-side (or server-side) procedure that hides the network from the application; generated by an IDL compiler in modern systems. |
| Marshaling | "Packing arguments into bytes." | Converting in-memory data structures into a wire format; the reverse is unmarshaling. |
| Call-by-copy-restore | "Pretend pointers are values." | Marshal the value, send it, modify on the server, return the modified value, write it back. Works for scalars, breaks for graphs. |
| RTP | "Audio/video over UDP." | A framing protocol with sequence number, timestamp, SSRC, payload type; the standard for streaming media. |
| RTCP | "RTP's sibling for feedback." | Periodic sender/receiver reports on a separate UDP port; bandwidth capped at 5% of media. |
| SSRC | "Stream ID." | A 32-bit random identifier that lets one UDP port multiplex many senders. |
| Playout point | "How long the receiver waits." | The size of the jitter buffer; larger means more late-packet tolerance, more end-to-end delay. |
| Idempotency | "Safe to retry." | The property that makes at-least-once RPC correct: re-running the procedure has the same effect as running it once. |

## Further Reading

- Tanenbaum, Feamster, Wetherall — *Computer Networks*, Sec. 6.4.2 and 6.4.3.
- Birrell and Nelson, "Implementing Remote Procedure Calls," *ACM TOCS* 2(1), 1984 — the original RPC paper.
- RFC 5531 (Thurlow, 2009) — RPC: Remote Procedure Call Protocol Specification Version 2 (replaces RFC 1050).
- RFC 4506 (Srinivasan, 2006) — XDR: External Data Representation Standard.
- RFC 3550 (Schulzrinne et al., 2003) — RTP: A Transport Protocol for Real-Time Applications (and the companion RTCP).
- Perkins, *RTP: Audio and Video for the Internet*, Addison-Wesley, 2003 — the practical guide.
- RFC 5109 (Li et al., 2008) — RTP Payload Format for Generic FEC.
- "gRPC: A high-performance, open-source universal RPC framework" — grpc.io.
