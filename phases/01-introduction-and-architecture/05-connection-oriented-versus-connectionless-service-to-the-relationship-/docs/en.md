# Connection-Oriented Versus Connectionless Service to The Relationship of Services to Protocols

> Layers offer two service models to the layer above: connection-oriented (telephone model — establish, use, release; bits arrive in order through a "tube") and connectionless (postal model — every message self-addressed and routed independently). Crossing those two with reliability gives the six service classes of Tanenbaum Fig. 1-16: reliable message stream, reliable byte stream, unreliable connection, unreliable datagram, acknowledged datagram, and request-reply. TCP (RFC 9293) implements the reliable byte stream with a 20-byte header carrying a 32-bit sequence number, 32-bit acknowledgement number, and a 16-bit window; UDP (RFC 768) implements the unreliable datagram with just an 8-byte header (source port, dest port, length, checksum) and no sequence numbers, no retransmission, no ordering. The reliable connection setup costs a round trip (the six-packet LISTEN/CONNECT/ACCEPT/SEND/RECEIVE/DISCONNECT exchange of Fig. 1-18) before any data flows, while a datagram fires immediately. The critical engineering distinction is **service vs protocol**: a service is the set of primitives a layer exposes at its interface (the socket API verbs), while a protocol is the on-the-wire format and rules peers exchange — you can swap TCP's congestion-control protocol from Reno to CUBIC to BBR without changing the `send()`/`recv()` service the application sees.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 lessons on layering, protocol stacks, and service interfaces
**Time:** ~75 minutes

## Learning Objectives

- Classify any application (file transfer, VoIP, DNS, SMS, junk mail) into one of the six Tanenbaum service classes using the connection/reliability matrix.
- Distinguish a **reliable byte stream** from a **reliable message sequence** by predicting how a receiver sees two 1024-byte writes versus one 2048-byte write.
- Read the six connection-oriented service primitives (LISTEN, CONNECT, ACCEPT, RECEIVE, SEND, DISCONNECT) and trace the six-packet client-server exchange that implements request-reply over acknowledged datagrams.
- State precisely why the *service* (interface primitives) and the *protocol* (wire format and peer rules) are decoupled, and give one real example of changing a protocol without changing its service.
- Name the header fields that prove connection orientation on the wire: TCP's 32-bit sequence/ack numbers and SYN/ACK/FIN flags versus UDP's port-and-checksum-only 8-byte header.

## The Problem

A team ships a real-time multiplayer game. Players in good network conditions are fine, but anyone behind a lossy mobile link reports the game "freezing and lurching." The transport was chosen as TCP because "TCP is reliable and reliable is good." The freeze is TCP doing exactly its job: a single lost segment triggers head-of-line blocking — every later byte already in the receive buffer is withheld from the application until the missing 32-bit sequence number is retransmitted and arrives, one RTT later. For a position-update stream where only the *latest* coordinate matters, the reliable, in-order byte stream is the wrong service. The fix is not a TCP tuning knob; it is recognizing that this workload wants an **unreliable datagram** service (UDP, RFC 768) where a lost position update is simply skipped and the next one supersedes it.

The same confusion runs the other way: a developer builds a file-transfer feature on UDP "because it's faster," then reinvents sequence numbers, acknowledgements, and retransmission timers — badly — and ships a buggy partial reimplementation of TCP. Choosing the service model wrong, in either direction, is one of the most common and most expensive networking mistakes. This lesson gives you the decision matrix and the on-the-wire evidence to make and defend the choice.

## The Concept

The source for this lesson is `chapters/chapter-01-introduction.md`, the subsections on connection-oriented versus connectionless service, service primitives, and the relationship of services to protocols.

### Two service models: the tube and the post

**Connection-oriented service** is modeled on the telephone system: establish a connection, use it, release it. The connection behaves like a tube — the sender pushes bits in one end and the receiver takes them out the other, and **order is preserved**. At setup time the two ends and the subnet may *negotiate* parameters (maximum message size, quality of service). One side proposes; the other accepts, rejects, or counter-proposes. A connection with reserved resources (e.g., fixed bandwidth) is called a **circuit**.

**Connectionless service** is modeled on the postal system: each message carries the **full destination address** and is routed through intermediate nodes independently of every other message. A network-layer message is a **packet**. Because each packet is routed independently, the first one sent is not guaranteed to arrive first — packet 2 can overtake a delayed packet 1. When an intermediate node receives a message in full before forwarding it, that is **store-and-forward switching**; when it begins forwarding before the message is fully received, that is **cut-through switching**.

### The six service classes (Fig. 1-16)

Cross the two connection models with reliability (acknowledged or not) and you get the six standard service types. See [`assets/connection-oriented-versus-connectionless-service-to-the-relationship-.svg`](../assets/connection-oriented-versus-connectionless-service-to-the-relationship-.svg) for this matrix.

| Service | Connection? | Reliable? | Canonical example | Real protocol |
|---|---|---|---|---|
| Reliable message sequence | Yes | Yes, boundaries kept | Sequence of pages to a typesetter | TCP with app-level framing, SCTP |
| Reliable byte stream | Yes | Yes, no boundaries | Movie / DVD download | TCP (RFC 9293) |
| Unreliable connection | Yes | No | Voice over IP | RTP-style flows |
| Unreliable datagram | No | No | Electronic junk mail | UDP (RFC 768) |
| Acknowledged datagram | No | Yes per message | Text messaging (SMS) | UDP + app ACK, CoAP CON |
| Request-reply | No | Yes per exchange | Database / map query | DNS over UDP, RPC |

`code/main.py` encodes exactly this table as a classifier: feed it `(needs_connection, needs_reliability, keeps_boundaries)` and it returns the service class plus a representative protocol.

### Reliable byte stream versus reliable message sequence

This is the subtlety most engineers get wrong. Both are reliable and connection-oriented; they differ in whether **message boundaries** survive.

- **Message sequence:** boundaries preserved. Send two 1024-byte messages and the receiver gets two distinct 1024-byte reads, never a single 2048-byte blob.
- **Byte stream:** no boundaries. Send 2048 bytes and the receiver cannot tell whether they were one 2048-byte write, two 1024-byte writes, or 2048 single-byte writes.

TCP is a **byte stream**. This is why an HTTP parser must find its own message boundaries using `Content-Length` or chunked transfer encoding — TCP will happily coalesce two `send()` calls into one segment (Nagle's algorithm) or split one `send()` across two segments. A typesetter receiving book pages cares about boundaries; a movie download does not. `code/main.py` includes a `demonstrate_framing()` function that shows two writes arriving as one stream and reconstructs the boundaries using a length prefix.

### Why unreliable service is the dominant form

It is tempting to assume reliable is always better. It is not, for two concrete reasons:

1. **Reliability may not exist at the layer you're on.** Ethernet (IEEE 802.3) does not provide reliable delivery — frames can be damaged and silently dropped. Recovery is pushed up the stack. Most reliable services (TCP) are built *on top of* an unreliable datagram service (IP, RFC 791).
2. **The delay of acknowledgements is unacceptable for real-time media.** For VoIP, a brief burst of noise is far less disruptive than stalling the audio for a retransmission round trip. For video conferencing, a few wrong pixels beat a stuttering image.

So reliable and unreliable coexist by design, and unreliable (UDP/IP datagram) is the dominant substrate.

### Service primitives: the interface verbs

A service is formally specified by its **primitives** — the operations user processes call to access it. When the stack lives in the OS, these are system calls that trap into the kernel. For a reliable byte stream, the six primitives mirror the Berkeley socket API:

| Primitive | Meaning | Berkeley socket analog |
|---|---|---|
| LISTEN | Block waiting for an incoming connection | `listen()` |
| CONNECT | Establish a connection with a waiting peer | `connect()` |
| ACCEPT | Accept an incoming connection from a peer | `accept()` |
| RECEIVE | Block waiting for an incoming message | `recv()` |
| SEND | Send a message to the peer | `send()` |
| DISCONNECT | Terminate the connection | `close()` |

### The six-packet client-server exchange (Fig. 1-18)

A request-reply interaction over acknowledged datagrams using these primitives runs as six packets. `code/main.py` simulates this exchange and prints the packet timeline:

1. **Connect request** — client `CONNECT` sends a packet asking the server to connect; client blocks.
2. **Accept response** — server, unblocked from `LISTEN`, runs `ACCEPT` and replies; this releases the client. Connection established.
3. **Request for data** — client `SEND`s its request, then `RECEIVE`s for the reply.
4. **Reply** — server (which had `RECEIVE`d) does the work and `SEND`s the answer; client unblocks and inspects it.
5. **Disconnect** — client `DISCONNECT`s; a blocking call that tells the server the connection is no longer needed.
6. **Disconnect** — server `DISCONNECT`s in return, acknowledging and releasing; the client is freed and the connection is broken.

In a perfect world a connectionless request-reply needs only **two** packets (request, reply). Six are needed because the real world has large messages, transmission errors, and lost packets: if a reply is hundreds of packets and some are lost, how does the client know which are missing, whether the last packet received was really the last sent, or whether a stray packet 1 belongs to this file or the previous one? Sequence numbers and an ordered byte stream solve exactly these problems — at the cost of connection setup and teardown.

### The relationship of services to protocols

This is the load-bearing distinction of the whole lesson.

- A **service** is the set of primitives a layer provides to the layer above it. It defines *what* operations the layer performs on behalf of its users and says **nothing about how** they are implemented. A service lives at the **interface** between two layers: the lower layer is the *provider*, the upper layer is the *user*.
- A **protocol** is the set of rules governing the **format and meaning of the packets** peer entities exchange *within* a layer, on different machines. Entities use protocols to *implement* their service definitions.

They are **completely decoupled**. Peers may change their protocol at will as long as the service visible to users does not change. The textbook analogy: a service is like an abstract data type or an object — it defines operations without specifying implementation; a protocol is the implementation, invisible to the service user.

Concrete proof: TCP exposes the same byte-stream service (`send`/`recv`) regardless of whether its congestion-control protocol underneath is Reno, CUBIC (Linux default since 2.6.19), or BBR. Applications were never recompiled when the kernel switched defaults — the protocol changed, the service did not. The historical anti-pattern was a `SEND PACKET` primitive where the user hands down a fully assembled packet: now every protocol change is immediately visible to users. Modern designers regard that coupling as a serious blunder.

## Build It

1. Read `code/main.py`. The `classify_service()` function maps `(connection, reliable, keep_boundaries)` to one of the six service classes — this is Fig. 1-16 as executable logic.
2. Run `python3 code/main.py`. Watch three things print: the classification table, the byte-stream framing demonstration, and the six-packet connection-oriented exchange timeline.
3. In `demonstrate_framing()`, note how two separate writes coalesce into one stream and how a 4-byte length prefix recovers the original message boundaries — this is what HTTP `Content-Length` does for you.
4. In `simulate_connection()`, trace each of the six packets back to the primitive (LISTEN/CONNECT/ACCEPT/SEND/RECEIVE/DISCONNECT) that triggered it.
5. Add a new application of your own to the `APPLICATIONS` list and predict its service class before running.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify an app's service need | The connection/reliability/boundary answers | You land on one of the six Fig. 1-16 classes and name a real protocol |
| Prove a flow is connection-oriented | Packet capture showing SYN/SYN-ACK/ACK and sequence numbers advancing | TCP three-way handshake precedes any payload; FIN tears it down |
| Prove a flow is connectionless | Capture showing UDP datagrams with 8-byte headers, no handshake | First DNS query packet carries full payload; no setup round trip |
| Separate service from protocol | One service, two protocol implementations | You can swap CUBIC→BBR (protocol) without touching `send`/`recv` (service) |
| Diagnose head-of-line blocking | TCP retransmit + stalled app reads in the trace | You recommend datagram service for the latest-value workload |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **service-selection runbook** that walks an engineer from application requirements to one of the six service classes and a concrete protocol.
- A **trace-annotation checklist** distinguishing connection-oriented captures (handshake, sequence numbers, FIN) from connectionless ones (bare datagrams).
- The classifier in `code/main.py`, extended with your own applications.

Start from [`outputs/prompt-connection-oriented-versus-connectionless-service-to-the-relationship-.md`](../outputs/prompt-connection-oriented-versus-connectionless-service-to-the-relationship-.md).

## Exercises

1. A weather station broadcasts a full temperature reading every second; clients only care about the most recent value and losing one is harmless. Classify the service, name the protocol, and explain why a reliable byte stream would actively hurt here.
2. An SMS-style "delivered receipt" feature must confirm each message arrived but does not want connection setup overhead. Which of the six classes is it, and which postal-service analogy does the textbook use for it?
3. You capture a flow and see a three-packet handshake, monotonically increasing 32-bit sequence numbers, and a closing exchange of two FIN packets. Which service class and protocol is this, and which Fig. 1-18 primitives map to the opening packets?
4. Send two `write()` calls of 1024 bytes each over a TCP socket. A junior dev expects two 1024-byte `recv()`s. Explain what they will actually observe and how `code/main.py`'s length-prefix framing fixes it.
5. The Linux kernel changed its default TCP congestion control from Reno to CUBIC. No application was recompiled. Use the service-versus-protocol distinction to explain precisely why no recompile was needed.
6. Argue both sides: a teammate wants to build a file-transfer feature on UDP "for speed." List what they would have to reinvent, and state the condition under which building on UDP is nevertheless justified.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Connection-oriented | "It's TCP" | A telephone-style model: establish, use in order through a tube, release; may negotiate parameters at setup |
| Connectionless | "It's UDP" | A postal-style model: each message self-addressed and routed independently; no setup, possible reordering |
| Reliable byte stream | "Reliable data" | Ordered, acknowledged, but **boundary-free** — the receiver cannot recover the sender's write boundaries |
| Reliable message sequence | "Same as a byte stream" | Ordered, acknowledged, **boundaries preserved** — two 1024-byte sends arrive as two 1024-byte reads |
| Datagram | "A UDP packet" | An unacknowledged, independently routed message; "datagram" by analogy with telegram (no return receipt) |
| Acknowledged datagram | "Reliable UDP" | Connectionless but per-message confirmed, like a registered letter with return receipt |
| Service | "The protocol" | The interface primitives a layer offers the layer above; defines *what*, not *how* |
| Protocol | "The service" | The wire format and peer rules within a layer; the *implementation*, invisible to the service user |
| Circuit | "A connection" | A connection with reserved resources such as fixed bandwidth |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 1, sections on connection-oriented vs connectionless service, service primitives, and the relationship of services to protocols (the source for this lesson).
- RFC 9293 — *Transmission Control Protocol (TCP)* (the reliable byte-stream protocol; supersedes RFC 793).
- RFC 768 — *User Datagram Protocol (UDP)* (the unreliable datagram protocol; 8-byte header).
- RFC 791 — *Internet Protocol (IP)* (the connectionless best-effort datagram substrate).
- IEEE 802.3 — Ethernet (the canonical unreliable link-layer datagram service).
- RFC 8200 — *Internet Protocol, Version 6 (IPv6)*, for the modern connectionless network layer.
- Wireshark display filter reference (`tcp.flags.syn == 1`, `udp`) for separating connection-oriented from connectionless captures.
