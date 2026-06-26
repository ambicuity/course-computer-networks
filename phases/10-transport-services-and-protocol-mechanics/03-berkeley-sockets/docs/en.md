# Berkeley Sockets

> The Berkeley socket API, first shipped in 4.2BSD in 1983, is the de-facto abstraction through which application code touches the transport layer. It exposes eight primitives - `SOCKET`, `BIND`, `LISTEN`, `ACCEPT`, `CONNECT`, `SEND`, `RECEIVE`, `CLOSE` - that map directly onto the kernel's TCP (or UDP) state machine. A server creates a socket, binds a 32-bit address (host + 16-bit port, port range 0-65535, well-known ports 0-1023 reserved for root), listens with a backlog, and accepts connections; a client creates a socket and `connect()`s. The kernel hides every segment, retransmission, ACK, FIN, RST, and timer from the user; the application sees only a reliable, full-duplex byte stream accessed through a file-descriptor-like handle. On Windows the same interface lives as Winsock. The lesson dissects the eight primitives, the states a socket passes through, and the byte-stream model that distinguishes sockets from message-oriented APIs.

**Type:** Build
**Languages:** Python (stdlib-only socket-state simulator)
**Prerequisites:** Transport service primitives (lesson 02), transport layer goals (lesson 01), familiarity with the TCP/IP stack from Chapter 5
**Time:** ~70 minutes

## Learning Objectives

- Name the eight Berkeley socket primitives and place each in either the server's `SOCKET -> BIND -> LISTEN -> ACCEPT` sequence or the client's `SOCKET -> CONNECT` sequence, plus the symmetric `CLOSE` shared by both sides.
- Draw the per-socket state machine `UNCONNECTED -> BOUND -> LISTENING -> ESTABLISHED -> CLOSING -> CLOSED` and explain which primitive triggers each transition.
- Distinguish a **byte-stream** socket (`SOCK_STREAM`, built on TCP) from a **datagram** socket (`SOCK_DGRAM`, built on UDP), and explain why a single `send(8 KB)` may arrive in two `recv(4 KB)` chunks on the wire.
- Map a socket's local address `(host, port)` to the transport-layer TSAP concept and explain why a single host can have thousands of listening sockets on the same IP via port numbers.
- Recognize the three failure modes every socket application must handle: `connect refused` (no listener at port), `backlog full` (SYN dropped at the kernel), and `connection reset by peer` (RST received).

## The Problem

A new hire is writing a tiny service that mirrors files between two machines. Their first version opens a single `socket()`, calls `connect()`, and starts streaming. It mostly works - but periodically the service hangs for thirty seconds, throws `OSError: [Errno 110] Connection timed out`, and the kernel log shows "TCP: drop open request from <ip>". Another failure mode shows up as `OSError: [Errno 111] Connection refused` when the server is not yet up. A third is more subtle: the client sends 8192 bytes, but the server reads them in three chunks - 4096, 2048, 2048 - and the application's parser assumes one message per read.

All three problems stem from misunderstanding what the socket API guarantees. The API does not give you "messages". It gives you a byte stream. It does not give you "successful connect" - it gives you "no RST before timeout". And it does not give you "always works" - it gives you a state machine with named transitions, and you have to know which states accept which calls. This lesson turns that state machine into something you can run, watch, and break.

## The Concept

The Berkeley socket API is a thin shim between user-mode file-descriptor semantics and the kernel's transport engine. Read the eight primitives in Fig. 6-5 of Tanenbaum as a small language: the verbs (SOCKET/BIND/LISTEN/ACCEPT/CONNECT/SEND/RECEIVE/CLOSE) and the states (UNCONNECTED/BOUND/LISTENING/ESTABLISHED/CLOSED/CLOSING) determine which calls are legal from which point in a socket's life. The simulator in `code/main.py` implements every transition in pure Python so you can read state changes off the screen instead of inferring them from `strace` output.

### The eight primitives and who calls them

| Primitive | Caller | Effect | What it returns |
|---|---|---|---|
| `SOCKET` | both | Allocates a new endpoint, table space, fd | File descriptor (>= 0) |
| `BIND` | server | Assigns a local `(host, port)` to the socket | 0 or -1 |
| `LISTEN` | server | Marks the socket as willing to accept; allocates a backlog queue (size N) | 0 or -1 |
| `ACCEPT` | server | Blocks until a connection arrives; creates a **new** socket for that conn | fd of the new socket |
| `CONNECT` | client | Actively opens a connection to a remote `(host, port)` | 0 or -1 |
| `SEND` | both | Hands data to the kernel; returns after copying to the send buffer | number of bytes accepted |
| `RECEIVE` | both | Blocks until at least 1 byte is available; copies up to N bytes from the kernel | number of bytes read |
| `CLOSE` | both | Symmetric release - signals "no more data" to the peer | 0 or -1 |

The first four run on the server in the order listed. The client's first three are `SOCKET` and `CONNECT` (and optionally `BIND` if the client cares about its source port). `SEND`/`RECEIVE` run in either direction once both ends are in `ESTABLISHED`. `CLOSE` is symmetric - either side may initiate; the connection is fully gone only after both sides have called it.

### The per-socket state machine

Every socket has a state. The simulator uses seven:

```
   SOCKET()           BIND()           LISTEN()           ACCEPT() returns
UNCONNECTED -----> BOUND ---------> LISTENING -------> ESTABLISHED
   |                                                            |
   |                                                            |
   |  CONNECT() returns                                         |  CLOSE()
   v                                                            v
ESTABLISHED <------------------------------------------------------- CLOSING -> CLOSED
```

- `UNCONNECTED`: just created by `SOCKET`. No address. `BIND` and `CONNECT` are the legal next moves.
- `BOUND`: a `(host, port)` is associated. The socket still has no peer. `LISTEN` (server) or `CONNECT` (client) is the next move.
- `LISTENING`: only servers reach this. The kernel has a backlog queue and is receiving SYNs. `ACCEPT` is the only meaningful call.
- `ESTABLISHED`: both sides can `SEND`/`RECEIVE`/`CLOSE`. This is where the bulk of a connection's life is spent.
- `CLOSING`: the local side has called `CLOSE`; pending bytes can still be drained. The peer sees an "end-of-stream" on its next read (zero bytes returned, like an `EOF`).
- `CLOSED`: terminal state. The fd should be released.

Two transitions deserve special attention. `ACCEPT` *does not* return the listening socket - it returns a **brand-new** socket that the kernel has already wired to the peer. The original listening socket stays in `LISTENING` and immediately becomes ready to accept the next connection. The `ESTABLISHED -> CLOSING -> CLOSED` path is driven by both sides calling `CLOSE`; if only one side has closed, the other can still read whatever was queued.

### Why a "stream" is not a "message"

A `SOCK_STREAM` socket behaves like a pipe: bytes go in one end, bytes come out the other, in order, with no preserved record boundaries. The kernel may break an 8 KB `SEND` into fifteen TCP segments on the wire; it may coalesce three small `SEND`s into one segment; the receiver's `RECV(4096)` may return 1024 bytes, or 4096, or 8192 (carrying a 4 KB send plus the first half of the next send) - none of these outcomes is an error. This is the single most common bug in beginner socket code: writing a parser that assumes "one `send` per `recv`." If the application needs messages, it has to add its own framing - a length prefix, a delimiter, or a fixed-size record.

`SOCK_DGRAM` (UDP) is the alternative: each `sendto` produces exactly one datagram on the wire, and each `recvfrom` returns exactly one datagram (truncated if the buffer is too small, with no assembly). Datagrams have no connection state and no retransmission; the kernel does not guarantee arrival, order, or uniqueness.

### TSAPs, ports, and the `host:port` address

A socket's local address is a **TSAP** (Transport Service Access Point) - the transport-layer equivalent of an IP address. In the Internet, a TSAP is the pair `(IP address, 16-bit port)`. The port space is 0-65535. The IANA splits it three ways:

| Range | Use |
|---|---|
| 0-1023 | "Well-known" ports - require root on UNIX (HTTP 80, HTTPS 443, SSH 22, DNS 53, SMTP 25) |
| 1024-49151 | "Registered" - allocated to specific services by IANA but open to users (e.g. 3306 MySQL, 5432 Postgres) |
| 49152-65535 | "Ephemeral" - the kernel picks a free one for client-side `connect()` calls |

A single host with one IP address can have tens of thousands of listening sockets because each `(IP, port)` pair is a distinct TSAP. `getpeername()` returns the address of the remote end; `getsockname()` returns the local end. Both are critical for debugging.

### What the API hides

The eight primitives are all the application sees. Behind them, the kernel is running the full TCP machinery: the three-way handshake (SYN, SYN+ACK, ACK) at connect time, the 32-bit sequence numbers, the retransmission timer, the cumulative ACK, the receive window advertisement, the FIN handshake at close, the TIME_WAIT state, and the slow-start congestion controller. A correctly-implemented socket library is the *easiest* way to write a network application precisely because all of that complexity is gone. A correctly-debugged socket application requires understanding the hidden layer well enough to know what "no error yet" actually means (e.g. "no RST has arrived" is not the same as "the peer is healthy").

## Build It

`code/main.py` is a stdlib-only Berkeley socket simulator. It implements the seven-state machine, the eight primitives, and three failure modes:

1. **Happy-path TCP server/client** - server `SOCKET -> BIND -> LISTEN`, client `SOCKET -> CONNECT`, server `ACCEPT`, then full-duplex `SEND`/`RECV`, then symmetric `CLOSE`. Every state transition is printed with a label so you can see the wire equivalent of each API call.
2. **`connect refused`** - the client calls `CONNECT` against an address with no listener. The simulator raises `SocketError: connection refused`; the client stays `UNCONNECTED`.
3. **`backlog full`** - a 2-deep listen queue rejects the third `CONNECT` with `SocketError: backlog full`. This is the kernel-level equivalent of the "TCP: drop open request" message in the prod scenario.

Run with `python3 code/main.py` and read the state columns. To extend: add a `bind` collision test, a `SOCK_DGRAM` mode, or a half-close probe (close the write half, keep reading).

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Order the server setup | `SOCKET -> BIND -> LISTEN -> ACCEPT` | Each call's pre-state is exactly the previous post-state |
| Diagnose "TCP: drop open request" | kernel log + server backlog | The listen socket's `backlog.maxlen` is the cap; either raise it with `LISTEN(N)` or accept faster |
| Read partial byte stream | bytes returned by `RECV(N)` | A single `SEND(8 KB)` may surface as several reads; the application must loop until it has N bytes |
| Pick source port | ephemeral range on UNIX | `getsockname()` on a client socket returns a port in 49152-65535 unless the app `BIND`s |
| Verify symmetric close | both ends reach `CLOSED` | `CLOSE` from one side yields EOF (zero-byte read) on the other; only after *both* close is the connection gone |
| Distinguish refused from timeout | `errno` 111 vs 110 | Refused = immediate, peer RST; Timeout = no SYN+ACK, the kernel retransmits and gives up after ~75 s |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **socket-call flow cheat sheet** showing, side-by-side, the server's and client's primitive sequences with the state transitions and the TCP segments each one corresponds to (SYN, SYN+ACK, ACK, FIN, FIN+ACK, ACK).
- A **failure-mode runbook** with the three error families above and the corresponding `errno` / kernel log signatures.
- A **byte-stream framing decision** - one page on length-prefix vs delimiter vs fixed-record, with a recommendation per protocol (HTTP uses CRLF, DNS uses length-prefix, TLS uses record framing).

Start from `outputs/prompt-berkeley-sockets.md`.

## Exercises

1. A server binds to `INADDR_ANY` (all local interfaces) on port 8080 and a client connects. Does the client see the server's wildcard address, the server's primary interface IP, or its loopback? Justify with the address returned by `getpeername()`.
2. The listen backlog is set to 5. Six clients `CONNECT` simultaneously before the server calls `ACCEPT`. How many succeed? What does the kernel do with the sixth (or, on modern Linux, with all of them once the SYN cookies / `tcp_max_syn_backlog` saturate)?
3. The server sends `"Hello"` (5 bytes) in one `SEND`, and the client calls `RECV(100)`. How many bytes may the client actually read in one call? What is the minimum, and what governs it?
4. Two `SEND(4 KB)` calls land at the receiver. The receiver calls `RECV(8 KB)` once. Is it guaranteed to read all 8 KB in one call? What about `RECV(2 KB)` followed by `RECV(6 KB)`?
5. A UDP socket receives a 1500-byte datagram. The application calls `RECV(2000)`. What happens? What if the application calls `RECV(1000)`?
6. Run `code/main.py`'s happy-path scenario and the "backlog full" scenario. Explain why the third connect is rejected even though the kernel still has memory free.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Socket | "a network connection" | A kernel-managed endpoint with state, an fd, a local address, and (once connected) a peer address |
| TSAP | "a port" | Transport Service Access Point - the pair `(IP, port)` that identifies one transport endpoint on one host |
| Listen backlog | "how many connections I can handle" | The kernel queue of *completed* SYNs awaiting `ACCEPT`; full backlog = kernel drops new SYNs |
| Byte stream | "send and receive data" | `SOCK_STREAM` has no message boundaries - `SEND(N)` and `RECV(M)` can split and coalesce arbitrarily |
| `SOCK_DGRAM` | "UDP socket" | Message-preserving, connectionless; one `sendto` = one `recvfrom`, no retransmission |
| `connect refused` | "the server is down" | The kernel received a RST (or saw no listener) for the target port - errno 111 on Linux |
| TIME_WAIT | "we just closed" | A 2 * MSL wait (typically 60 s) after the active close to drain stray segments and prevent overlap with reincarnated connections |
| FD | "file descriptor" | A small integer returned by `SOCKET()` (and `OPEN()`); the kernel uses it to look up socket state for every call |

## Further Reading

- **4.2BSD Unix release notes (1983)** - the original distribution in which the socket API shipped. Berkeley CSRG archive at `https://www.mckusick.com/csrg/`.
- **Stevens, W. R. (1998), *UNIX Network Programming, Volume 1* (3rd ed.)** - the canonical reference; chapters 3-6 cover sockets, addresses, TCP, and elementary socket programming.
- **RFC 793** (1981), "Transmission Control Protocol" - the protocol the socket API was designed to expose. The connection state machine in section 3.2 maps 1-to-1 onto the per-socket states in this lesson.
- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.1.3** - the source material for this lesson (Fig. 6-5).
- **Donahoo, M. & Calvert, K. (2008), *TCP/IP Sockets in C: Practical Guide for Programmers* (2nd ed.)** - the most-cited pocket guide to writing socket code.
- **Microsoft Winsock reference** (`learn.microsoft.com/en-us/windows/win32/winsock/`) - the Windows implementation of the same eight primitives.
