# Service Primitives and the Berkeley Socket Client-Server Protocol

> A **service** is the contract a lower layer offers the layer above it, expressed as a small set of **service primitives** — operations like LISTEN, CONNECT, ACCEPT, RECEIVE, SEND, and DISCONNECT. When the protocol stack lives in the kernel, these primitives are **system calls** that trap to kernel mode and cause the OS to emit packets; the Berkeley socket interface is the canonical example, shipped in 4.2BSD (1983) and codified by POSIX as `socket()`, `bind()`, `listen()`, `accept()`, `connect()`, `send()/recv()`, and `close()`. The textbook illustrates the smallest connection-oriented service with **six primitives** and a **six-packet exchange** (Fig. 1-18) running over *acknowledged datagrams*: (1) connect request, (2) accept response, (3) data request, (4) data reply, (5) client disconnect, (6) server disconnect ack. Real TCP (`SOCK_STREAM`, RFC 9293) upgrades this skeleton into a reliable byte stream with a **32-bit sequence number**, a **16-bit adaptive retransmission timer** (Karn's algorithm, RFC 6298), a three-way handshake (SYN, SYN+ACK, ACK with segment 0 consumed), and a **four-way FIN teardown** with `TIME_WAIT` holding the socket for 2×MSL (typically 60–120 s) to catch stray segments. The classic failure modes are CONNECT before LISTEN (refused), lost SYN (retransmitted at ~3 s, RFC 6298 exponential backoff), and a client that vanishes mid-exchange leaving the server blocked in `recv()` — which is why every real server sets `SO_REUSEADDR` and wraps accept in a per-connection timeout. This lesson builds a runnable, dependency-free simulator of the six-primitive protocol over a lossy datagram channel and shows exactly the state each primitive leaves behind.

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Layered architecture and service/protocol separation (Phase 1 lessons on layers and encapsulation); the notion of a connection-oriented vs. connectionless service
**Time:** ~85 minutes

## Learning Objectives

- Name the six connection-oriented service primitives and map each to its POSIX socket system call and its Linux kernel trap (`sys_listen`, `sys_connect`, `sys_accept4`, `sys_recvfrom`, `sys_sendto`, `sys_close`).
- Trace the six-packet exchange of Fig. 1-18 over a lossy channel, stating which primitive on which machine emits each packet and which unblocks the peer.
- Distinguish a **service** (the interface between two layers, invisible to peers) from a **protocol** (the wire format between peer entities), and explain why TCP may swap its on-the-wire handshake without touching the `recv()` call a program makes.
- Explain retransmission and the adaptive timer: Karn's algorithm, exponential backoff (1×, 2×, 4× RTO per RFC 6298), and why a SYN that never elicits a SYN-ACK is retried ~3 times before `connect()` returns `ETIMEDOUT`.
- Read the simulator's printed trace and diagnose a lost packet from the retransmit/retry evidence, naming the state the client and server hold while suspended.
- Justify when connectionless service (`SOCK_DGRAM`, two packets) beats the six-packet connection-oriented exchange, and when it breaks down (large messages, reordering, lost final packets).

## The Problem

A monitoring agent on a worker node posts a 4 KB metrics blob to a collector every 60 s. The engineer writes it with bare UDP datagrams — one request, one reply — because "two packets are cheaper than six." It works in the lab. In production the link drops roughly 1% of datagrams. Now the collector occasionally receives a metrics blob whose first 1 KB belongs to this minute and whose last 3 KB belongs to *last* minute (an old, delayed packet resurfaced), and once a month the agent reposts the same blob 47 times because the reply was lost and the agent cannot tell whether the server is slow, dead, or has already stored the data.

The engineer's instinct is to bolt on timeouts and sequence numbers by hand. That is exactly the situation the textbook warns against: in the real world a bare request-reply protocol over an unreliable network is "often inadequate." The trained answer is to step back to the **service primitive** level, where a connection's state — synchronized sequence numbers, agreed window, established teardown — does the bookkeeping the agent needs. This lesson is that step back: the six primitives, the six packets, and what each one buys you.

## The Concept

### Services, primitives, and the service/protocol wall

A **service** is formally specified by the set of **primitives** (operations) available to user processes. If the stack is in the OS kernel, the primitives are **system calls**: each `trap`/`syscall` switches to kernel mode and hands control to the OS, which builds and emits the packets. Crucially, the service says *what* the layer will do for the layer above — it says nothing about *how*. A **protocol**, in contrast, is the set of rules governing the format and meaning of the packets exchanged between **peer entities** within a single layer. Entities are free to change their protocol at will provided they do not change the service visible to users. This is the textbook's "key concept": service = the inter-layer interface (vertical); protocol = the peer wire format (horizontal). TCP may replace its segment layout, handshake, or timer math between releases, but a program calling `recv(sock, buf, len)` on a `SOCK_STREAM` socket is utterly unaware.

| Concept | Scope | Visibility | Example |
|---|---|---|---|
| Service | Between adjacent layers (vertical) | The layer above sees only the primitives | `recv()` returns ordered bytes |
| Protocol | Between peer entities (horizontal) | Invisible to the service user above | TCP's SYN/SYN-ACK/ACK on the wire |
| Primitive | One operation in the service | System call to the layer below | CONNECT → `sys_connect` |
| SAP | Service Access Point — where a layer is accessed | Addressed like a port | IP protocol field 6 → TCP SAP |

An older anti-pattern — a single `SEND_PACKET` primitive where the user hands the layer a fully assembled packet — leaks every protocol change straight into user code. Modern designs (sockets, XTI, WINSP) keep the protocol below the interface.

### The six service primitives and their POSIX mappings

The textbook's minimal connection-oriented service exposes exactly six primitives. Each maps onto a real socket call and a real Linux kernel entry point:

| Textbook primitive | Meaning | POSIX call | Linux syscall | Direction |
|---|---|---|---|---|
| LISTEN | Block waiting for an incoming connection | `listen(fd, backlog)` then `accept()` | `sys_listen` / `sys_accept4` | Server |
| CONNECT | Establish a connection with a waiting peer | `connect(fd, *addr, len)` | `sys_connect` | Client → Server |
| ACCEPT | Accept an incoming connection from a peer | `accept(fd, *addr, *len)` | `sys_accept4` | Server |
| RECEIVE | Block waiting for an incoming message | `recv()` / `recvfrom()` / `read()` | `sys_recvfrom` | Either |
| SEND | Send a message to the peer | `send()` / `sendto()` / `write()` | `sys_sendto` | Either |
| DISCONNECT | Terminate the connection | `close(fd)` (sends FIN) | `sys_close` + `tcp_close` | Either |

`LISTEN` is commonly implemented as a blocking call: after it, the server process is **suspended** until a connection request arrives. `CONNECT` typically takes an address parameter (the server's `struct sockaddr_in`, carrying a 32-bit IPv4 address + 16-bit port) and *also* blocks the caller until a response arrives. The simulator in `code/main.py` reproduces this blocking semantics with explicit `blocked` flags so you can see which process is suspended at each step.

### The six-packet exchange (Fig. 1-18) over acknowledged datagrams

The textbook sketches the protocol using **acknowledged datagrams** — each packet must be acknowledged or it is retransmitted — so we can momentarily ignore lost packets. The full exchange between client machine and server machine:

| Step | Packet | Emitted by | Triggered by primitive | Unblocks | State after |
|---|---|---|---|---|---|
| 1 | Connect request | Client OS | client `CONNECT` | server's `LISTEN` | server ready to ACCEPT |
| 2 | Accept response | Server OS | server `ACCEPT` | client's `CONNECT` | connection established both sides |
| 3 | Request for data | Client | client `SEND` | server's `RECEIVE` | server processing |
| 4 | Reply | Server | server `SEND` | client's `RECEIVE` | client has answer |
| 5 | Disconnect | Client | client `DISCONNECT` | server's `RECEIVE` | server notified |
| 6 | Disconnect ack | Server | server `DISCONNECT` | client's `DISCONNECT` | connection closed, client released |

Between step 2 and step 3 the server issues `RECEIVE` *before* the ack in step 2 propagates back, so it is already blocked waiting for data when the request lands. The analogy the textbook leans on is phoning customer service: the manager sits by the phone (LISTEN), the customer dials (CONNECT), the manager picks up (ACCEPT), conversation flows (SEND/RECEIVE), and finally one party hangs up (DISCONNECT) and the other confirms (ack). See `assets/socket-service-primitives-client-server.svg` for the full timing diagram with the two blocked processes drawn explicitly.

### From six primitives to TCP: sequence numbers, the three-way handshake, and TIME_WAIT

Real TCP keeps the same six-primitive skeleton but thickens the wire protocol. The seg-level fields that do the bookkeeping the bare protocol lacks:

| TCP header field | Size | Role in the exchange |
|---|---|---|
| Sequence number | 32 bits | Byte position of the first data byte in this segment; the SYN consumes one sequence number |
| Acknowledgement number | 32 bits | Next byte the sender expects; piggybacks the ack |
| Flags (SYN/ACK/FIN/RST) | 9 bits | Mark the connect/data/teardown phases |
| Window | 16 bits | Bytes of receive buffer currently free (flow control) |
| Checksum | 16 bits | Covers pseudo-header + header + data (RFC 9293) |

The textbook's "connect request" becomes a **three-way handshake**: client `connect()` emits SYN (seq `x`); server `accept()` replies SYN+ACK (seq `y`, ack `x+1`); client completes with ACK (ack `y+1`). The single "disconnect" becomes a **four-way FIN teardown**: active closer sends FIN, peer ACKs, peer sends its own FIN, active closer ACKs and enters **TIME_WAIT**, holding the socket for **2×MSL** (Maximum Segment Lifetime; MSL is 2 min in RFC 9293, so ~4 min, though Linux defaults `TIME_WAIT` to 60 s). TIME_WAIT exists purely to absorb a stray retransmitted FIN or data segment from a peer that did not realize the connection was closed — the textbook's "how would the client know whether the last packet received was really the last packet sent?" answered by a timed hold.

### Retransmission, Karn's algorithm, and the adaptive timer

The bare protocol assumes acknowledged datagrams; building those acknowledgements is the real work. TCP estimates the round-trip time and sets a **Retransmission Timeout (RTO)** per RFC 6298:

- SRTT = (1−α)·SRTT + α·RTT_sample, with α = 1/8 (EWMA, like RTT smoothing in TCP Vegas).
- RTTVAR = (1−β)·RTTVAR + β·|SRTT − RTT_sample|, β = 1/4.
- RTO = SRTT + max(G, 4·RTTVAR), floored at 1 s, never below 1 s.

**Karn's algorithm** solves two coupled problems: do not sample RTT on a retransmitted segment (you cannot tell whether the ack is for the first or second send), and back off exponentially on each retransmission (1×RTO, 2×, 4×, 8× ...) so a congested link is not hammered. A `connect()` whose SYN is lost is retried ~3 times (Linux default `tcp_syn_retries = 6`, doubling each time → roughly 3 s, 6 s, 12 s ...) before `errno = ETIMEDOUT`. The simulator models this with a fixed `BASE_RTO` and the same doubling, and prints each retransmit so you can read the backoff off the trace.

### When connectionless wins and when it loses

A connectionless protocol needs only **two packets** (request, reply) — six is three times the traffic. The textbook's reason to pay the six-packet tax is real-world messiness:

- **Large messages** spanning many datagrams need reassembly with sequence and length; a bare request cannot track "which piece is missing."
- **Reordering**: a delayed packet 1 from the first file can masquerade as packet 1 of the second file. A connection's monotonic sequence space (or TCP's 32-bit sequence number wrapping safely via the PAWS check, RFC 7323) prevents this.
- **Lost final packet**: without a teardown the receiver cannot know whether more data is coming or the sender died. Connection state plus a teardown exchange answers it; a bare protocol cannot.

So the decision rule is: small, idempotent, single-datagram exchanges (DNS lookups — one 512-byte UDP request, one reply, RFC 1035) gain from connectionless; anything with ordering, large payloads, or non-idempotent state changes (file transfer, remote procedure call with side effects) earns the six-packet overhead. `code/main.py` runs both modes through the same lossy channel so the difference is visible in the trace.

## Build It

1. Run `python3 code/main.py`. The simulator executes the six-packet exchange (Fig. 1-18) on a clean channel, then repeats it on a channel that drops one packet, showing the retransmit and the state held during the block. Finally it runs the two-packet connectionless exchange for contrast and counts retries on a lossy channel.
2. Read the `Primitive` enum and the `Packet` dataclass — they are the textbook's six primitives and the wire records that carry them.
3. Walk `ConnectionOrientedClient` and `ConnectionOrientedServer`: each `step_*` method corresponds to one primitive; the `self.blocked` flag is the kernel suspending the process.
4. In `LossyChannel`, set `drop_at` to step 1 (drop the SYN) and rerun — watch the client's `CONNECT` retransmit with exponential backoff until it gets through.
5. Set `drop_at = 3` to drop the data request and confirm the server stays blocked in `RECEIVE` while the client retransmits until the ack returns.
6. Run `ConnectionlessClient` on a 30% loss channel and read the retry counter — it has no sequence state, so it cannot distinguish a slow reply from a lost one.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the six-packet exchange | Steps 1-6 printed in order, each tagged with emitter and which peer it unblocks | Server LISTEN precedes client CONNECT; both blocked flags clear by step 2 |
| Diagnose a lost CONNECT | Retransmit log at 1×, 2×, 4× RTO; server never left LISTEN until receipt | Client's `connect()` eventually returns after one successful retransmit; no duplicate connection |
| Diagnose a lost data request | Client retransmits step 3; server still blocked in RECEIVE | Server processes once; the retransmit is the dedup生源, not a second request |
| Verify teardown prevents resurrection | Steps 5-6 both logged; client released only after server's disconnect ack | A late duplicate data segment would be rejected, not re-processed |
| Contrast connectionless on lossy link | Retry count with no bearer state | Sender cannot tell lost reply from slow server; may double-commit an idempotent-unaware operation |
| Name the service/protocol boundary | `recv()` never changes while the wire protocol changes | A test that assert on `recv()` return values survives a TCP version bump |

## Ship It

Produce one artifact under `outputs/prompt-socket-service-primitives-and-client-server-protocol.md`:

- An annotated trace of the simulator's six-packet exchange with each primitive named and each "unblocks X" arrow called out.
- A failure-injection log: pick three drop points (CONNECT, data request, disconnect) and for each paste the retransmit/backoff evidence and the final outcome (established / closed / `ETIMEDOUT`).
- A one-paragraph decision card: when to use `SOCK_STREAM` (six-packet connection-oriented) vs `SOCK_DGRAM` (two-packet connectionless) for a given message size, loss rate, and idempotency.

Start from `python3 code/main.py` output and annotate it with the primitive and the state at each line.

## Exercises

1. The simulator drops the CONNECT request (step 1). Trace exactly: how many retransmits occur before `connect()` returns, what RTO each uses under Karn's doubling, and what state the server holds throughout. Now drop the ACK half of the three-way handshake (step 2) instead — does the client still block, and on what?
2. A client `SEND`s a 1.5 MB file as one logical request over the six-primitive protocol. Roughly how many MTU-1500 datagrams is that, and why does the bare two-packet connectionless exchange not scale to it? Name the specific textbook problem (reassembly, reordering, lost-final-packet) that each extra mechanism addresses.
3. Replace the simulator's fixed `BASE_RTO` with the RFC 6298 EWMA (SRTT, RTTVAR, RTO). Feed it RTT samples of [10, 12, 9, 50, 11] ms and report the RTO after the 50 ms outlier. Why does Karn's algorithm forbid sampling the retransmitted segment?
4. `listen(fd, 5)` sets a backlog of 5. Explain what happens on the client side when 8 clients CONNECT faster than the server ACCEPTs, naming the kernel queue involved (the accept queue / completed-connection queue) and the `ECONNREFUSED` condition.
5. TCP teardown uses a four-way FIN with TIME_WAIT of 2×MSL. A server closes a connection and immediately restarts, binding the same port. Why does `SO_REUSEADDR` let the bind succeed, and what residual risk does TIME_WAIT still guard against for exactly 2×MSL?
6. Argue for DNS (RFC 1035) staying connectionless UDP despite a 1% loss rate, then argue for a database commit RPC having to be connection-oriented, naming which of the textbook's "real world" failure modes each choice respects or violates.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Service primitive | "an API call" | One operation in the service offered by a layer; expressed as a system call (trap to kernel) when the stack is in the OS |
| Service vs protocol | "same thing" | Service = vertical inter-layer contract (what); protocol = horizontal peer wire format (how) — freely swappable without the other noticing |
| SAP | "a port" | Service Access Point — the address at which a layer is reached, e.g. IP protocol field 6 selects the TCP SAP |
| LISTEN | "wait for clients" | Blocking primitive that suspends the server process until a CONNECT packet arrives; the accept queue is then populated |
| Acknowledged datagram | "a packet with a reply" | A datagram whose delivery is confirmed by a returning ack, retransmitted on timeout — the substrate the six-primitive exchange assumes |
| Three-way handshake | "the TCP open" | SYN → SYN+ACK → ACK; the textbook's single connect request expanded with a 32-bit sequence number each way |
| TIME_WAIT | "a stuck socket" | 2×MSL hold after the active close so stray retransmitted FINs/data are absorbed, not misdelivered to a new connection |
| Karn's algorithm | "the timer trick" | Don't sample RTT on retransmitted segments and back off RTO exponentially on each retry; keeps RTO estimates honest |
| RTO | "the timeout" | Retransmission Timeout, computed per RFC 6298 as SRTT + max(G, 4·RTTVAR), floored at 1 s |
| Connectionless service | "just send it" | Two-packet request-reply with no bearer state — fine for small idempotent exchanges, broken by reordering and lost final packets |
| Berkeley socket | "the C API" | The 4.2BSD (1983) programming interface — `socket`/`bind`/`listen`/`accept`/`connect`/`send`/`recv`/`close` — POSIX-standardized and still the canonical service interface |

## Further Reading

- **RFC 9293** — Transmission Control Protocol (the current TCP standard; sequence numbers, three-way handshake, four-way FIN, TIME_WAIT 2×MSL).
- **RFC 6298** — Computing TCP's Retransmission Timer (SRTT/RTTVAR EWMA, RTO floor of 1 s, exponential backoff).
- **RFC 7323** — TCP Extensions for High Performance (window scale and the PAWS check that defeats old-segment resurrection).
- **POSIX.1-2017** — `sys/socket.h`: `socket`, `bind`, `listen`, `accept`, `connect`, `send`, `recv`, `close`.
- Leffler, McKusick, Karels & Quarterman, *The Design and Implementation of the 4.3BSD UNIX Operating System*, Addison-Wesley, 1989 — the Berkeley socket interface as shipped.
- Stevens, Fenner & Rudoff, *UNIX Network Programming, Volume 1: The Sockets Networking API*, 3rd ed., Addison-Wesley.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §1.3.4 (Service Primitives) and §1.3.5 (Relationship of Services to Protocols).