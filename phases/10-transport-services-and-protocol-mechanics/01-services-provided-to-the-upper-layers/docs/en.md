# Services Provided to the Upper Layers

> The transport layer's ultimate goal is efficient, reliable, cost-effective data transmission for application processes. It sits between the unreliable network layer (operated by carriers on routers the user does not control) and the application layer (which demands a perfect byte pipe). The transport entity runs entirely on the user's machine -- in the OS kernel, a library, or a separate process -- and compensates for network-layer faults via retransmission, reconnection, and error detection. This is why the transport layer exists as a distinct layer rather than being folded into layer 3: the user has no control over the carrier's routers, so reliability must be added on top. The layer forms the major boundary between the transport service provider (layers 1-4) and the transport service user (layer 5+), and its service comes in two flavors: connection-oriented (reliable byte stream, three-phase connection) and connectionless (datagrams, best-effort). The connection-oriented transport service resembles the connection-oriented network service in having establishment, data transfer, and release phases -- but the key difference is that the transport service is reliable while the network service is not.

**Type:** Build
**Languages:** Python, sockets
**Prerequisites:** Earlier lessons in Phase 10
**Time:** ~90 minutes

## Learning Objectives

- Explain source section 6.1.1 in operational terms.
- Identify the packet fields, timers, counters, state, or logs that prove the behavior.
- Connect the concept to at least one realistic failure mode.
- Produce a reusable trace annotation, runbook, diagram, script, or prompt.

## The Problem

A streaming media company runs its application over a raw IP network provided by a transit carrier. The carrier's routers periodically lose packets, occasionally crash, and sometimes reorder datagrams when routes change. The application developers assumed the network was reliable and did not implement their own acknowledgements or retransmissions. Users see frozen video, corrupted downloads, and intermittent connection resets. The team debates whether to switch carriers, buy better routers (which they do not own), or rewrite the application. None of these addresses the real problem: they built directly on the network service instead of on the transport service. The transport layer exists precisely because users cannot control the carrier's network layer and must add reliability on their own machine. Without a transport entity, every application would have to reimplement retransmission, reconnection, and error detection from scratch. The deeper problem is recognizing where the provider-user boundary lies: layers 1-4 are the transport service provider; layer 5+ is the user. Application programmers should program against transport primitives, not network primitives.

## The Concept

Section 6.1.1 of the source chapter provides the theoretical foundation. `code/main.py` implements a working simulation; `assets/services-provided-to-the-upper-layers.svg` diagrams the key structures.

### Why the transport layer is a separate layer

The network layer runs on routers owned by the carrier; the transport layer runs on the user's machine. If the network layer is inadequate (loses packets, crashes, resets connections), the user cannot fix it by upgrading routers or adding error handling to the data link layer because they do not own those devices. The only option is to add another layer on top of the network layer that compensates for the network's faults. This is the transport entity. The transport code runs entirely on the user's machines, making it the one layer the user can fix when the carrier's service is poor. If all real networks were flawless and永不 changed, the transport layer might not be needed -- but in the real world, it isolates the upper layers from the technology, design, and imperfections of the network.

### The provider-user boundary

Layers 1 through 4 form the transport service provider; the upper layer(s) are the transport service user. The transport layer is at the boundary: it is the level that applications see. Application programmers write code against a standard set of transport primitives and those programs work on a wide variety of networks without dealing with different network interfaces or reliability levels. Changing the network merely requires replacing one set of library procedures with another that does the same thing with a different underlying service. This is why the transport layer is in a key position -- it forms the major boundary between the unreliable network infrastructure and the reliable service that applications expect.

### Connection-oriented vs connectionless transport service

There are two types of transport service, mirroring the two network service types. The connection-oriented transport service has three phases (establishment, data transfer, release) and is reliable: the transport entity hides lost packets, retransmissions, and timers so the application sees a perfect byte pipe. The connectionless transport service is unreliable and datagram-based. The connection-oriented transport service is similar to the connection-oriented network service in many ways -- both have the three phases and similar addressing and flow control -- but the transport service is reliable while the network service is not. It is difficult to provide a connectionless transport service on top of a connection-oriented network service, because it is inefficient to set up a network connection just to send one packet and then tear it down immediately.

### Where the transport entity lives

The transport entity can be located in the operating system kernel, a library package bound into network applications, a separate user process, or even on the network interface card. The first two options are most common on the Internet. The transport entity communicates with its peer using a transport protocol that runs over the network layer. The transport service is accessed by the application via transport primitives -- library procedure calls that are independent of the underlying network service primitives. This abstraction means the same application code runs over Ethernet, Wi-Fi, or a connection-oriented WAN without modification.

### End-to-end argument in action

The transport layer is the canonical example of the end-to-end argument: only the end hosts have complete knowledge of whether data was delivered correctly, so reliability must be implemented at the endpoints. Intermediate routers cannot know whether a packet was delivered to the application or whether the application crashed after receiving it. The transport entity on the sender's machine retransmits when the receiver's transport entity does not acknowledge; the receiver's transport entity discards duplicates and reorders segments by sequence number. All of this machinery is invisible to the transport users -- they see a reliable bit pipe.

### Observable evidence: what the transport layer adds

If you capture packets at the network layer, you see raw IP packets with no guarantees. The transport layer's contribution is visible in the transport header: sequence numbers that allow reordering, checksums that detect corruption, acknowledgement numbers that confirm delivery, and flags (SYN, FIN, RST) that manage the connection state. The transport entity also maintains timers, retransmission queues, and congestion windows -- all invisible to the application. The observable evidence of the transport service working correctly is that the application receives an ordered, complete, uncorrupted byte stream despite the network losing, corrupting, and reordering packets underneath.

## Build It

`code/main.py` is a stdlib-only simulator. Work through it in this order:

1. Read the transport entity model in `code/main.py` -- `TransportState` has five states (IDLE, CONNECTING, READY, DISCONNECTING, CLOSED) and `UnreliableNetwork` can drop, reorder, and corrupt packets.
2. Run `run_reliable_transfer()` with drop_rate=0.0 (clean network) and observe the application sees a perfect byte pipe with no retransmissions.
3. Run with drop_rate=0.3 (30 percent packet loss) and watch the transport entity retransmit lost packets while the application still receives the complete, ordered stream.
4. Examine `NetworkPacket` -- it carries `seq`, `ack`, `flags`, `payload`, and `checksum`. The checksum detects corruption; the sequence number enables reordering and duplicate detection.
5. Set drop_rate to 0.5 and observe how throughput degrades but correctness does not. The transport entity retransmits until the receiver acknowledges -- this is the reliability the network layer does not provide.

Run with `python3 code/main.py`. No pip dependencies, no network calls.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify the service boundary | tcpdump at the network layer vs application-level logs | Network-layer capture shows losses/reorders; application log shows complete data -- proving the transport entity compensated |
| Confirm connection-oriented service | SYN, SYN-ACK, ACK in the trace; data segments with sequence numbers; FIN sequence at close | The three phases (establishment, data, release) are present and the byte stream is in-order |
| Detect a transport-layer gap | Application running directly over IP (raw sockets) with no transport entity | Losses appear as missing data in the application -- there is no retransmission, no reordering, no checksum recovery |
| Identify the provider-user boundary | Which layer the application calls into | Application calls transport primitives (socket, connect, send), never network primitives -- the boundary is at the transport API |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page layer-responsibility matrix: for each failure mode (packet loss, corruption, reordering, connection reset, congestion), which layer compensates and how.
- A trace annotation showing the same data transfer at two levels: the network-layer capture (messy, with losses) and the transport-layer log (clean, with retransmissions and acknowledgement numbers).
- A decision runbook: given an application that sees corrupt or missing data, determine whether the problem is a missing transport entity, a broken transport implementation, or an application that bypassed the transport API.

Start from `outputs/prompt-01-services-provided-to-the-upper-layers.md`.

## Exercises

1. Explain why the transport layer is a separate layer even though its connection-oriented service resembles the connection-oriented network service. What specific failure of the network layer makes the transport layer necessary?
2. A router crashes and resets all its state. The transport entity on the sender detects the connection was terminated. Describe the recovery: what query does the sender send, and how does it know which data arrived and which did not?
3. An application sends a single 100-byte packet over a connection-oriented network. Explain why providing a connectionless transport service on top of connection-oriented network service is inefficient for this case.
4. Run `code/main.py` with drop_rate=0.3. Count the number of retransmissions the transport entity performs. Then set drop_rate=0.5 and count again. By what factor does retransmission count increase?
5. An engineer argues 'the network layer already has error control, so the transport layer is redundant.' Refute this with three specific failures that the network layer cannot handle but the transport layer can.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Transport entity | "the transport layer software" | The software/hardware within the transport layer that does the work -- can live in the OS kernel, a library, a separate process, or even on the NIC; it runs on the user's machine, not on carrier routers |
| Transport service | "the byte pipe" | The reliable, end-to-end data transmission service the transport layer provides to applications, hiding the network layer's packet loss, corruption, and reordering |
| Provider-user boundary | "where layer 4 ends" | The boundary between layers 1-4 (transport service provider) and layer 5+ (transport service user); the transport layer is the level applications see and program against |
| Connection-oriented transport service | "reliable connections" | Transport service with three phases -- establishment, data transfer, release -- that is reliable despite the underlying network being unreliable |
| Connectionless transport service | "datagrams at layer 4" | Unreliable, datagram-based transport service used by applications like streaming multimedia and client-server query/response |
| End-to-end argument | "reliability at the endpoints" | Only the end hosts know whether data was delivered correctly; reliability must be implemented at the endpoints, not in the network -- the transport layer is the embodiment of this principle |

## Further Reading

- Saltzer, Reed, & Clark (1984), 'End-to-End Arguments in System Design,' ACM TOCS 2(4) -- the argument that justifies the transport layer as a separate layer.
- RFC 793 -- Transmission Control Protocol: the standard connection-oriented transport service on the Internet.
- RFC 768 -- User Datagram Protocol: the standard connectionless transport service.
- Tanenbaum & Wetherall, Computer Networks (5th ed.), section 6.1.1 -- the source material for this lesson.
