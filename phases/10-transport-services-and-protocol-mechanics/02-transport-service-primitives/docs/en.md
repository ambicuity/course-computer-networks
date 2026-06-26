# Transport Service Primitives

> The transport service is accessed through a set of primitives -- library procedure calls that application programs use to establish connections, send data, receive data, and release connections. A minimal connection-oriented transport service has five primitives: LISTEN (block until a client connects), CONNECT (actively establish a connection), SEND (transmit data), RECEIVE (block until data arrives), and DISCONNECT (release the connection). The transport service is reliable while the network service is unreliable; the transport entities manage acknowledgements, timers, and retransmissions invisibly to the users. A segment (the unit exchanged between transport entities) is nested inside a packet (the network-layer unit), which is nested inside a frame (the data-link unit). Connection release has two variants: asymmetric (either side issues DISCONNECT and the connection is released) and symmetric (each direction is closed separately; the connection is released only when both sides have DISCONNECTed). The Berkeley socket API extends these primitives with SOCKET, BIND, LISTEN, ACCEPT, CONNECT, SEND, RECEIVE, and CLOSE.

**Type:** Build
**Languages:** Python, sockets
**Prerequisites:** Earlier lessons in Phase 10
**Time:** ~90 minutes

## Learning Objectives

- Explain source section 6.1.2 in operational terms.
- Identify the packet fields, timers, counters, state, or logs that prove the behavior.
- Connect the concept to at least one realistic failure mode.
- Produce a reusable trace annotation, runbook, diagram, script, or prompt.

## The Problem

A distributed system uses a custom inter-process communication layer that exposes only raw network send/receive calls -- no transport primitives. Developers must implement their own connection establishment, data transfer, and release for every new client-server pair. One service uses asymmetric disconnect (any side can tear down the whole connection), and another uses symmetric disconnect (each side closes its direction independently). The inconsistency leads to bugs: a client that does asymmetric disconnect while the server is mid-transfer loses data, while a symmetric implementation hangs because one side never sends its DISCONNECT. The root problem is the absence of a standard transport service interface that hides the connection state machine. Developers should call well-defined transport primitives -- LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT -- and let the transport entity manage the wire protocol.

## The Concept

Section 6.1.2 of the source chapter provides the theoretical foundation. `code/main.py` implements a working simulation; `assets/transport-service-primitives.svg` diagrams the key structures.

### The five primitive model

The minimal transport service has five primitives. LISTEN blocks the server until a client tries to connect. CONNECT causes the client's transport entity to send a CONNECTION REQUEST segment and block the caller. When the segment arrives, the server's transport entity unblocks the server and sends CONNECTION ACCEPTED back. When that arrives, the client is unblocked and the connection is established. SEND and RECEIVE exchange data with the transport entities handling acknowledgement and retransmission invisibly. DISCONNECT releases the connection. This is the bare-bones set; real APIs like Berkeley sockets add more.

### Segment nesting: segments in packets in frames

Segments are exchanged by transport entities, packets by network entities, and frames by data link entities. A segment is the payload of a packet; a packet is the payload of a frame. When a frame arrives, the data link layer processes the frame header and passes the frame payload (the packet) up to the network entity. The network entity processes the packet header and passes the packet payload (the segment) up to the transport entity. This three-level nesting is the structural reason each layer's header is stripped and reborn at each hop while the payload survives.

### The transport service is reliable -- the network service is not

The network service is intended to model what real networks offer, warts and all: real networks lose packets, so the network service is unreliable. The connection-oriented transport service, in contrast, is reliable. Real networks are not error-free, but that is precisely the purpose of the transport layer: to provide reliable service on top of an unreliable network. Two processes connected by a UNIX pipe assume 100 percent reliability; they do not want to know about acknowledgements, lost packets, or congestion. The transport service provides exactly that abstraction: one user puts bits in, they appear in order at the other end. All the machinery (ACKs, timers, retransmissions) is managed by the transport entities and is invisible to the transport users.

### Asymmetric vs symmetric disconnect

Disconnection has two variants. In asymmetric release, either transport user can issue a DISCONNECT, which sends a DISCONNECT segment and releases the connection when it arrives. It is simple but can lose data if one side disconnects while the other is still sending. In symmetric release, each direction is closed separately. When one side does DISCONNECT, it means it has no more data to send but is still willing to receive. The connection is released only when both sides have DISCONNECTed. Symmetric release avoids data loss but requires both sides to coordinate -- and since the network can lose the final DISCONNECT segments, guaranteeing clean release is equivalent to the two-army problem (covered in lesson 06).

### The connection state machine

The connection management state diagram has states for idle, passive/active establishment pending, established, and passive/active disconnect pending. The client follows a solid-line path through the states; the server follows a dashed-line path. Transitions are triggered either by a primitive the local user executes (e.g., CONNECT) or by an incoming segment (e.g., CONNECTION REQUEST received). The state machine makes the connection lifecycle explicit: LISTEN puts the server in passive establishment pending; CONNECT puts the client in active establishment pending; the CONNECTION ACCEPTED segment transitions both to established. This is the model TCP refines with its 11-state machine.

### Observable evidence: what a trace shows

A packet capture of a simple transport exchange shows: a CONNECTION REQUEST segment (with no payload), a CONNECTION ACCEPTED segment, data segments with sequence numbers and their acknowledgements, and a DISCONNECT segment. All segments carry transport headers (sequence, ack, flags) even though the application-level primitive calls say nothing about these. The transport entities add the headers, manage the ACKs, and run the timers. The application only sees LISTEN, CONNECT, SEND, RECEIVE, and DISCONNECT.

## Build It

`code/main.py` is a stdlib-only simulator. Work through it in this order:

1. Read `code/main.py` -- `TSState` enumerates the six states (IDLE, LISTENING, CONNECTING, READY, CLOSING, CLOSED) and `Segment` carries type, seq, ack, payload, and flags.
2. Run `run_normal_lifecycle()` and trace the state transitions: LISTEN -> LISTENING, CONNECT -> CONNECTING, CONNECTION ACCEPTED -> READY, SEND/RECEIVE exchanges, DISCONNECT -> CLOSED.
3. Run `run_connect_refused()` to see what happens when no server is listening -- the CONNECT blocks and times out.
4. Run `run_duplicate_cr()` to observe how a delayed duplicate CONNECTION REQUEST is rejected by the state machine.
5. Run `run_symmetric_disconnect()` and compare with the asymmetric variant -- each side closes its direction independently; the connection is released only when both have closed.

Run with `python3 code/main.py`. No pip dependencies, no network calls.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the transport primitive | Application-level function call vs wire-level segment | You map `connect()` to a CONNECTION REQUEST segment and `send()` to a DATA segment, proving the primitive maps to a wire action |
| Trace segment/packet/frame nesting | Capture at the data link layer; peel headers | Frame header -> packet header -> segment header -> payload -- each layer strips its header and passes the payload up |
| Distinguish symmetric from asymmetric release | pcap showing one vs two FIN segments | Asymmetric releases on the first DISCONNECT; symmetric requires both sides to DISCONNECT -- two FIN sequences, not one |
| Verify transport service reliability | Compare application-level data integrity with network-level loss rate | Application receives complete ordered data despite network losses -- the transport entities retransmitted transparently |

## Ship It

Produce one reusable artifact under `outputs/`:

- A primitive-to-segment mapping table: for each transport primitive (LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT), the segment sent on the wire and the state transition it triggers.
- A state diagram annotation of a real pcap trace: label each packet with the state transition it causes on both client and server.
- A disconnect-strategy decision guide: when to use symmetric vs asymmetric release, with the data-loss risk of each and the two-army problem as the reason symmetric release cannot guarantee clean termination.

Start from `outputs/prompt-02-transport-service-primitives.md`.

## Exercises

1. Draw the segment/packet/frame nesting for a SEND primitive. Which headers are added by which layer, and which layer's header is stripped first when the frame arrives?
2. A server issues asymmetric DISCONNECT while the client is mid-transfer. Describe exactly which data is lost and why symmetric release would have prevented the loss.
3. Run `code/main.py` and list every state transition in `run_normal_lifecycle()`. Then mark which transitions are triggered by a local primitive and which by an incoming segment.
4. An application developer says 'I do not need transport primitives; I will just send raw packets.' List three transport-layer responsibilities (acknowledgement, retransmission, sequencing) that the developer must now reimplement.
5. Explain why LISTEN is a blocking primitive in the five-primitive model but non-blocking in the Berkeley socket API. What does the socket server do instead of blocking on LISTEN?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Transport primitives | "the API calls" | The set of library procedure calls (LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT) that application programs use to access the transport service |
| Segment | "a transport-layer message" | The unit exchanged between transport entities; it is nested inside a network-layer packet, which is nested inside a data-link frame |
| Asymmetric release | "one side hangs up" | Connection release where either side issuing DISCONNECT releases the entire connection; simple but can lose in-flight data |
| Symmetric release | "both sides hang up" | Connection release where each direction is closed separately; the connection is released only when both sides DISCONNECT; avoids data loss but cannot guarantee clean termination (two-army problem) |
| Connection state machine | "the state diagram" | The set of states (idle, pending, established, disconnect pending) and transitions that describe the connection lifecycle; triggered by local primitives or incoming segments |
| Reliable transport service | "the perfect pipe" | The service that hides all network imperfections (loss, corruption, reordering) so the application sees an error-free, ordered byte stream |

## Further Reading

- RFC 793 -- TCP specification: the real-world refinement of these primitives with the 11-state connection management model.
- Stevens, Fenner, & Rudoff, UNIX Network Programming (Vol. 1): the socket API, which extends the five-primitive model.
- Tanenbaum & Wetherall, Computer Networks (5th ed.), section 6.1.2 -- the source material for the five-primitive model and the state diagram.
- RFC 4960 -- SCTP: a transport protocol that extends the primitive set with multi-streaming and multi-homing.
