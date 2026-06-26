# Transport service primitives and the Berkeley socket API

> Applications do not talk directly to the network. They call a small set of transport-layer primitives that hide the segment machinery and expose either a reliable byte stream (TCP, RFC 793) or an unreliable datagram service (UDP, RFC 768). This lesson works through the two interfaces every Internet programmer uses: the simple five-primitive hypothetical model (LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT) and the Berkeley sockets API (SOCKET, BIND, LISTEN, ACCEPT, CONNECT, SEND, RECEIVE, CLOSE) released with 4.2BSD in 1983 and still the lingua franca of `winsock`, libuv, and Go's `net` package. The asymmetry between symmetric release (each direction closes independently) and the abrupt `RST` pattern a Web server uses to kill an idle connection is explained through the two-army problem and the half-open-connection hazard. The companion `code/main.py` is an offline harness that exercises the eight Berkeley socket primitives in a state machine, walks a tiny HTTP file-server through its lifecycle, and prints the segment types each primitive would emit. It mirrors the Tanenbaum Figure 6-6 client and server so you can run the lesson without ever opening a real socket.

**Type:** Learn
**Languages:** Python, C
**Prerequisites:** Phase 00 lab environment; basic POSIX process model; Chapter 3 framing; Chapter 6 introduction
**Time:** ~75 minutes

## Learning Objectives

- Map the five hypothetical primitives (LISTEN, CONNECT, SEND, RECEIVE, DISCONNECT) to the segment types they imply (CONNECTION REQ, CONNECTION ACCEPTED, DATA, DISCONNECTION REQ).
- Distinguish symmetric release (each side closes its half with a FIN) from the asymmetric RST pattern a Web server issues because it knows the request was the only client data.
- Trace the Berkeley socket lifecycle (SOCKET, BIND, LISTEN, ACCEPT, CONNECT, SEND/RECEIVE, CLOSE) and the server fork/thread model that accepts in a loop.
- Predict the `socket(2)` arguments a TCP server passes: `AF_INET`, `SOCK_STREAM`, `IPPROTO_TCP` (RFC 793), and the `SO_REUSEADDR` reason for the `setsockopt` call.
- Reason about the half-open-connection hazard (lost final ACK, N retransmissions all fail) and the keepalive rule that auto-disconnects after a quiet period.
- Use `code/main.py` to drive a state machine through the socket lifecycle and inspect the segment sequence it would put on the wire.

## The Problem

A junior developer reads Tanenbaum Figure 6-6, the 20-line C file server, and asks: "If TCP is reliable and ordered, why do I need to call `bind` before `listen`? Why does `accept` return a brand new file descriptor? Why does my HTTP server close the connection with `RST` instead of `FIN`, and what is the difference between `close` and `shutdown`?" These are exactly the questions the transport-layer API exists to answer. The socket API is a thin shim over the kernel's TCP/UDP state machines, and the eight primitives are the only knobs applications have. Misuse of the lifecycle produces well-known failure modes: address already in use when restarting a server (no `SO_REUSEADDR`), a `bind` that fails because the port is privileged (under 1024), a `listen` backlog that drops SYNs under load, and a connection that goes half-open and never notices because no traffic flows.

The deeper question is philosophical: why have a transport service at all when the network layer already delivers packets? The answer is that the network layer runs on routers you do not own, the transport layer runs on the hosts you do own, and only the hosts can compensate for lost segments, reordered packets, and crash recovery. The transport primitives are the boundary at which reliability, flow control, and congestion control are decided — and they are the boundary at which every networked program in the world is written.

## The Concept

### The five-primitive hypothetical model

Tanenbaum introduces a bare-bones transport service so the segment machinery is visible. A process on each host calls into the transport entity (usually the kernel); segments flow between transport entities; the application sees a reliable bit pipe. The five primitives are enough to express every transport interaction:

| Primitive | Segment sent | Meaning |
|---|---|---|
| LISTEN | (none) | Block until a peer tries to connect |
| CONNECT | CONNECTION REQ | Actively attempt to establish a connection |
| SEND | DATA | Send information on an established connection |
| RECEIVE | (none) | Block until a DATA segment arrives |
| DISCONNECT | DISCONNECTION REQ | Request release of the connection |

The server executes LISTEN first and blocks. A client issues CONNECT, which causes the transport entity to send a CONNECTION REQ segment. The server's transport entity unblocks it on receipt; the server then sends CONNECTION ACCEPTED. The client unblocks; the connection is established. Now both sides can SEND and RECEIVE in a half-duplex dance. When done, both issue DISCONNECT.

The model in Figure 6-4 of the chapter is a six-state machine: IDLE -> CONNECT (client path) or LISTEN (server path) -> ESTABLISHED -> DISCONNECTING -> IDLE. The state diagram makes one thing explicit that the prose hides: **the connection lifecycle is symmetrical**. Each peer is a state machine; the segment on the wire drives transitions in both.

### Why a transport layer at all?

If the network layer is best-effort datagrams and the transport layer is best-effort datagrams (UDP), why not skip the transport? The chapter gives the answer in two sentences: the transport code runs entirely on the users' machines, but the network layer mostly runs on routers operated by the carrier. Users do not control routers, so they cannot fix poor service by upgrading them. They compensate by adding reliability in a layer they do control. The transport entity can detect lost segments and retransmit, can re-establish a network connection when one is broken, and can ask the peer which data arrived and which did not. This is the **end-to-end argument** in its positive form: only the endpoints have the information needed to deliver a reliable service, and a lower layer cannot substitute.

This is also why transport primitives are a library call rather than a network interface. They are platform-independent: the same `SEND` works whether the network underneath is Ethernet, Wi-Fi, or a long-haul fibre. The transport service is a contract; the network is an implementation detail.

### Berkeley sockets: the eight primitives that won

Released in 4.2BSD (1983) and now in `winsock` on Windows, sockets became the de facto standard. The eight primitives map almost one-to-one onto the hypothetical five, with two extras (BIND, SOCKET) to give applications control over addressing and resource allocation:

| Primitive | Meaning | Order (server) | Order (client) |
|---|---|---|---|
| SOCKET | Create a new communication endpoint and return a file descriptor | 1 | 1 |
| BIND | Associate a local TSAP (IP + port) with the socket | 2 | (skipped — kernel picks an ephemeral port) |
| LISTEN | Announce willingness to accept; set the queue size | 3 | n/a |
| ACCEPT | Block, then return a new FD for the next incoming connection | 4 (loop) | n/a |
| CONNECT | Actively start the connection; blocks until established | n/a | 2 |
| SEND / WRITE | Send bytes | 5 | 3 |
| RECEIVE / READ | Receive bytes | 5 | 3 |
| CLOSE | Release the connection | 6 | 4 |

Two things make this more than a re-statement of the hypothetical model:

- **BIND** is separate from SOCKET so a server can claim a specific well-known port (`/etc/services` lists port 25 for SMTP, 80 for HTTP, 22 for SSH). Clients usually skip BIND and let the kernel assign an ephemeral port in the 32768-60999 range (Linux's `ip_local_port_range`).
- **ACCEPT** is a *factory*: it does not just block, it returns a *new* file descriptor representing the per-connection socket, leaving the original listening FD free to accept the next connection. The standard pattern is `while True: client_fd, _ = accept(listen_fd, ...); fork(); handle(client_fd)`.

The `socket(2)` system call takes three arguments that map directly to the protocol stack: address family (`AF_INET` for IPv4, `AF_INET6` for IPv6, `AF_UNIX` for local sockets), socket type (`SOCK_STREAM` for TCP, `SOCK_DGRAM` for UDP, `SOCK_SEQPACKET` for SCTP), and protocol number (`IPPROTO_TCP`, `IPPROTO_UDP`, or 0 to default). The successful return is a small non-negative integer — the file descriptor that you will use with `read`, `write`, `close`, and the rest of the POSIX API.

### The C file server, line by line

The Tanenbaum Figure 6-6 client and server are the minimum viable Internet file server. The server does nine things, in this exact order:

1. **Zero a `sockaddr_in` structure** with `memset`, then fill `sin_family = AF_INET`, `sin_addr.s_addr = htonl(INADDR_ANY)` (0.0.0.0 — accept on any local interface), and `sin_port = htons(SERVER_PORT)`. The `htonl`/`htons` calls convert host byte order to network byte order (big-endian) so the code runs correctly on little-endian x86 and big-endian SPARC alike.
2. **Create the socket** with `socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)`. The trio of arguments is the contract with the kernel: IPv4, byte stream, TCP (RFC 793).
3. **Set `SO_REUSEADDR`** with `setsockopt`. Without this, a server that crashes leaves the port in `TIME_WAIT` (2× MSL, typically 60 s on Linux) and the restart fails with `EADDRINUSE`. With `SO_REUSEADDR`, the new socket can claim the port immediately.
4. **Bind** the address to the socket. If the port is < 1024, this call requires root (CAP_NET_BIND_SERVICE on Linux).
5. **Listen** with a backlog of 10. The kernel will now queue up to 10 incomplete SYNs; the 11th is dropped (or, with `SYN cookies`, silently accepted).
6. **Accept** in a loop. Each successful accept returns a brand-new FD bound to a different remote endpoint.
7. **Read** the filename (the client sent it, NUL-terminated).
8. **Open** the file with `O_RDONLY`, then loop: read 4096 bytes from the file, write to the socket, until EOF.
9. **Close** the connection (the file too) and go back to step 6.

The client mirrors the structure with two simplifications: it skips BIND (kernel picks an ephemeral port) and uses `gethostbyname` to resolve the server name to an IPv4 address (the modern replacement is `getaddrinfo`, which handles IPv6 and CNAMEs). The one line the chapter calls out — `write(s, argv[2], strlen(argv[2])+1)` — sends the filename plus its trailing NUL so the server knows where the string ends. The author's "medieval" assumption is that the filename fits in one TCP segment and is delivered atomically; in practice a real server uses length-prefixed framing or `readn()`.

### Symmetric release vs. the Web-server RST

The hypothetical model says DISCONNECT is symmetric: each side issues it independently, and the connection is fully released only when both have done so. The corresponding TCP mechanism is the FIN handshake — each side sends FIN, each ACKs the other's FIN, and only then is the connection fully closed. This is the model most servers follow.

HTTP/1.0 and many HTTP/1.1 servers break this rule. The request/response pattern is known: client sends request, server sends response, both sides are done. After writing the response, the server can issue a RST (asymmetric close) instead of FIN. The client, if it gets the RST, releases its state immediately; if the RST is lost, the client eventually times out and releases anyway. Either way, no data is lost because the request was the only client data and the response is already on the wire. The server trades politeness for a prompt connection cleanup — important for high-volume servers holding thousands of sockets in `TIME_WAIT`.

The "no protocol exists for two-army problem" reasoning in the chapter explains why this is necessary. If each side waits for the other to confirm, neither ever attacks. If the protocol has N+1 messages, removing the last one returns the protocol to N messages, so a finite handshake never suffices. TCP's symmetric FIN handshake is the practical compromise: not provably correct, but adequate. The `TIME_WAIT` state and the half-open-connection hazard (lost ACK, N retransmissions all fail) are the two ways the protocol leaks.

### Half-open connections and the keepalive rule

A **half-open connection** exists when one side has crashed and the other has not. The alive side has a TCB (transmission control block) with state, but the dead side's state is gone. The only way to recover is the keepalive rule: if no segment has arrived for K seconds (often 7200 s by default, 60 s after `tcp_keepalive_time` on Linux), the connection is automatically disconnected. The transport entity runs a timer that is stopped and restarted on every segment; when it expires, it sends a zero-window probe (a "dummy" segment) to test liveness.

The rule handles three failure modes at once: the peer crashed, the network partition severed the path, and the peer is alive but silent. The first two are indistinguishable to TCP — the timer fires, the probe is unacknowledged, and the connection is closed. The third (silent peer) is rarer but the same mechanism catches it.

### `connect(2)`, `accept(2)`, and the three-way handshake

The textbook figures 6-11 (a), (b), (c) walk the three-way handshake with delayed-duplicate CONNECTION REQ segments. The C calls map onto the segment types:

- `connect()` returns when the third segment (the client's ACK of the server's SYN+ACK) has been sent. From the client's perspective, the connection is open.
- `accept()` returns when the server's transport entity has sent the SYN+ACK and received the client's ACK. From the server's perspective, the connection is open.
- The two unblock independently; in practice they unblock within one RTT of each other.

The crash-and-restart case in Figure 6-10 motivates why initial sequence numbers must be (a) at least k bits where the ISN space is much larger than the maximum packets per T seconds, and (b) chosen from a clock so they never repeat inside T. Modern TCP uses pseudo-random ISNs (RFC 1948) to defeat off-path attackers who would otherwise predict the ISN and inject acceptable SYNs.

## Build It

1. Read `code/main.py` and run it: `python3 phases/11-.../14-.../code/main.py`. It walks a state machine through the eight Berkeley primitives and prints the segment each primitive would emit.
2. Compare its output to the chapter's Figure 6-5 table. Every row of the table should appear in the simulation.
3. Inspect the `BIND` step: it shows the `sockaddr_in` structure byte by byte, the `htons(12345)` conversion, and the reason `SO_REUSEADDR` is needed.
4. Trace the `accept()` loop: each iteration allocates a fresh FD, the server forks (modeled as a child state record), and the listening FD is preserved.
5. Modify `SERVER_PORT` to a privileged port (`80` or `22`) and observe the `bind()` failure. Switch back to a port >= 1024 to confirm the success.
6. Try `SOCK_DGRAM` in the `SOCKET` step and observe that the simulation rejects `LISTEN` and `ACCEPT` (UDP is connectionless).

## Use It

| Task | Real tool | What good looks like |
|---|---|---|
| Resolve a service name | `getent services http` (or `getaddrinfo`) | Returns `80/tcp` from `/etc/services` — proves the BIND step has a real well-known port to claim |
| Watch the three-way handshake | `tcpdump -ni any 'tcp[tcpflags] & (tcp-syn\|tcp-ack) != 0'` | Capture the SYN, SYN+ACK, ACK triple the chapter describes |
| Inspect the socket FD table | `ss -tna '( dport = :http or sport = :http )'` | Each connection has a paired `Local Address` and `Remote Address` row, exactly what the `accept()` FD factory produces |
| Simulate half-open detection | `tcpdump -ni any 'tcp[tcpflags] & tcp-rst != 0'` | After a peer process is killed, the next segment from the still-alive side elicits a RST — the keepalive rule in action |
| Reuse address after crash | `python3 -c "import socket; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('',12345))"` | `bind` succeeds even if a previous instance is in `TIME_WAIT` — exactly the role of `SO_REUSEADDR` |

## Ship It

Produce one reusable artifact under `outputs/`:

- A annotated state diagram of the eight-primitive lifecycle, drawn from the simulation in `code/main.py`, with the segment each transition emits.
- A one-page cheat sheet mapping each `socket(2)` argument (`AF_INET`, `SOCK_STREAM`, `IPPROTO_TCP`) to the protocol stack position it implies.
- A failure-mode runbook: `EADDRINUSE` -> enable `SO_REUSEADDR`; `ECONNREFUSED` -> server is not in LISTEN; `EPIPE` -> peer closed; `ETIMEDOUT` -> SYN unacknowledged after the configured retries.

Start from [`outputs/prompt-transport-service-primitives-and-berkeley-sockets.md`](../outputs/prompt-transport-service-primitives-and-berkeley-sockets.md).

## Exercises

1. Read the simulation in `code/main.py` and predict the segment sequence the textbook Figure 6-6 client would emit for `client flits.cs.vu.nl /etc/hosts`. Run the simulation; verify the SYN, the PSH+ACK carrying the filename, the data segments, and the FIN.
2. Why does the Web-server RST pattern not work for, say, an SSH session? Identify the property of HTTP/1.0 that makes the RST safe.
3. In the simulation, replace `SOCK_STREAM` with `SOCK_DGRAM`. Which primitives become invalid? Which pair is the UDP analog of CONNECT-then-SEND?
4. Add a `shutdown(SHUT_WR)` call after the last write. What is the difference between this and `close()`? How does it map to the "symmetric release" each direction closes independently model?
5. Predict what `ss -tna` shows after a server runs `accept()` and forks a child but the client crashes before the child writes anything. Which side eventually times out, and which timer fires?
6. The chapter says initial sequence numbers are pseudo-random in modern TCP. Why is the security argument (RFC 1948) necessary? What does an off-path attacker do with a predictable ISN?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TSAP | "port number" | A transport-service access point, the endpoint a process binds to; TCP and UDP both use 16-bit port numbers (0-65535) |
| NSAP | "IP address" | A network-service access point; IPv4 NSAPs are 32 bits, IPv6 NSAPs are 128 bits |
| Socket | "an open connection" | A kernel-managed endpoint: an FD plus a 5-tuple (proto, local IP, local port, remote IP, remote port) |
| `bind` | "open the port" | Assigns a local IP+port to a socket; ports < 1024 require root; without BIND, the kernel picks an ephemeral port |
| `listen` | "wait for clients" | Allocates a queue for incoming SYNs; the second argument is the backlog (kernel may cap it via `somaxconn`) |
| `accept` | "get a client" | Blocks, then returns a brand-new FD for the next connection; the listening FD is unchanged |
| Three-way handshake | "SYN, SYN+ACK, ACK" | RFC 793 connection establishment; rejects delayed duplicates because each side confirms the other's ISN |
| Symmetric release | "FIN, FIN, ACK" | Each side independently closes its half of the connection; both FINs and both ACKs required to fully tear down |
| Half-open connection | "stuck socket" | One peer has lost its TCB; the other only finds out via the keepalive timer or the next retransmission timeout |
| Keepalive | "is the peer alive?" | A timer that fires after K seconds of silence and probes the peer; if N probes fail, the connection is closed |

## Further Reading

- RFC 793 — Transmission Control Protocol (the original TCP, including the three-way handshake and FIN teardown)
- RFC 1122 — Requirements for Internet Hosts — Communication Layers (clarifies and corrects RFC 793; the modern baseline)
- RFC 1948 — Defending Against Sequence Number Attacks (pseudo-random ISNs)
- RFC 768 — User Datagram Protocol (the connectionless sibling)
- RFC 9293 — Transmission Control Protocol (2022, the consolidated TCP spec that obsoletes RFC 793)
- Stevens, Fenner & Rudoff, *Unix Network Programming, Volume 1: The Sockets Networking API*, 3rd ed.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Ch. 6 (transport service and Berkeley sockets)
- `socket(2)`, `bind(2)`, `listen(2)`, `accept(2)`, `connect(2)` Linux man pages
- `ss(8)` — modern replacement for `netstat` for inspecting the socket table
