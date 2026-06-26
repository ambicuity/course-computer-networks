# Socket Lifecycle Lab to Reliable Transport State Machine Lab

> A Berkeley socket is not a wire — it is a *handle* onto a kernel-side state machine. The 11 states in RFC 793 (CLOSED, LISTEN, SYN_SENT, SYN_RECEIVED, ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, CLOSE_WAIT, LAST_ACK, TIME_WAIT, CLOSING) describe the visible behavior of a connection, but the *socket* itself only knows a few of those names because the kernel collapses overlapping transitions. This lab walks a TCP socket through every state using Python's `socket` module: bind, listen, accept, connect, send, recv, shutdown, close. We compare the RFC 793 FSM with what `getsockname` / `getpeername` / `netstat` actually show, trace a graceful FIN/FIN-ACK/FIN-ACK exchange (the three-way close) and an abrupt RST close, and then build a tiny reliable transport on top of UDP using a stop-and-wait state machine so you can see the *same* FSM (S0=ready, S1=waiting) drive both the kernel TCP and your user-space mini-TCP. The key insight: every reliable transport — TCP, DCCP, SCTP, your own custom protocol — is a state machine over an unreliable channel; the difference is who owns the state.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 10 lessons 03 (Berkeley sockets), 05 (addressing to connection establishment), 06 (connection release), 17 (TCP service model)
**Time:** ~85 minutes

## Learning Objectives

- Map the 11 RFC 793 states onto the visible behavior of a Python `socket.socket(AF_INET, SOCK_STREAM)` instance and explain which transitions the kernel hides from the application.
- Trace a full connection through `LISTEN -> SYN_SENT -> ESTABLISHED -> FIN_WAIT_1 -> FIN_WAIT_2 -> TIME_WAIT -> CLOSED` using only the BSD sockets API and `selectors`.
- Distinguish a graceful **FIN** close (3-way FIN/FIN-ACK/FIN-ACK plus 2*MSL TIME_WAIT) from an abrupt **RST** close (no TIME_WAIT, peer discards unacked data).
- Implement a **stop-and-wait reliable transport** on UDP: sequence number 0/1, ACK, retransmission timer, and a four-state FSM (READY, SENT, WAIT_ACK, RETRANSMIT) and verify it against a packet-loss simulator.
- Explain why the kernel owns TCP's state machine (and therefore why user-mode code cannot see all 11 states) while application code *can* see every state in a UDP-based transport it builds itself.

## The Problem

A junior engineer writes a "TCP server" in Python and is confused. `netstat -tn` shows the listener in `LISTEN` and connected peers in `ESTABLISHED`, but after a clean `close()` the line disappears — they never see `FIN_WAIT_1` or `TIME_WAIT`. Meanwhile, a `TIME_WAIT` socket on a busy web server ties up ports and triggers a port-exhaustion bug they cannot reproduce. The same engineer, asked to write a custom reliable protocol over UDP, designs a five-state FSM only to find that the *correct* stop-and-wait protocol has exactly two states: S0 (ready to send) and S1 (waiting for ACK), with the alternation driven by a single bit.

The reason both confusions happen: kernel TCP hides state from user code; user-space UDP exposes everything. This lab makes the two views explicit and builds both.

## The Concept

The Berkeley sockets API was designed to model the **4.2BSD** networking stack (1983), which itself implemented the 11-state TCP FSM from RFC 793. Over the years the kernel collapsed some states, added some (e.g. `CLOSE_WAIT` is visible but `CLOSING` and `FIN_WAIT_2` are usually too brief to see in `netstat`). The application sees a *narrow* API; the kernel implements a *wider* FSM. The SVG shows the visible part of TCP's state machine plus the stop-and-wait FSM; `code/main.py` exercises both.

### The visible subset of the RFC 793 state machine

In RFC 793 the full state machine has 11 states. In practice, the BSD socket API exposes fewer because most transitions complete in microseconds. The ones you can actually observe via `netstat`, `ss`, or `getsockopt(SO_STATE)`:

| RFC 793 state | When visible | What you can do with the socket |
|---|---|---|
| CLOSED | Always, before bind | nothing |
| LISTEN | Server, after `listen()` | `accept()` blocks |
| SYN_SENT | Client, between `connect()` and 3-way handshake | nothing (kernel working) |
| SYN_RECEIVED | Server, between accept and final ACK | nothing (kernel working) |
| ESTABLISHED | After 3-way handshake | `send`, `recv` |
| FIN_WAIT_1 | Initiator of active close, between FIN and FIN-ACK | nothing (kernel draining) |
| FIN_WAIT_2 | Initiator, after receiving peer's FIN-ACK | `recv` only (peer is half-closed) |
| CLOSE_WAIT | Receiver of active close, after receiving FIN | `send` to peer; you must close |
| LAST_ACK | Receiver, between `close()` and peer's final ACK | nothing |
| CLOSING | Both sides closed simultaneously (rare) | nothing |
| TIME_WAIT | Initiator, after final ACK; lasts 2*MSL (~60 s) | nothing — kernel aging |

The TIME_WAIT state is famously controversial. Its purpose is to absorb late-arriving segments from the previous incarnation of the connection (4-tuple: src IP, src port, dst IP, dst port) so they cannot corrupt a new incarnation. RFC 793 sets MSL (Maximum Segment Lifetime) to 2 minutes, but BSD-derived stacks use 30 s and Linux uses 60 s. Some sockets (e.g. HTTP servers) call `SO_REUSEADDR` to bypass it; this is a deliberate violation of the spec and is safe only when the application protocol does not depend on TIME_WAIT's protection.

### The socket as a 5-call state machine

What the BSD socket layer lets the application see is closer to:

```
CLOSED -> BOUND -> LISTEN -> ACCEPTED -> ESTABLISHED -> CLOSE_WAIT -> CLOSED
```

Each arrow corresponds to one POSIX call:

```
socket()           -> CLOSED (no address)
bind(addr)         -> BOUND   (named local endpoint)
listen(backlog)    -> LISTEN  (accept incoming SYN)
accept()           -> ACCEPTED (kernel-completed handshake; returns new fd)
connect() / accept -> ESTABLISHED (data can flow)
shutdown(WR)       -> CLOSE_WAIT peer, FIN_WAIT_1 locally
close() / shutdown -> CLOSED
```

The application never sees SYN_SENT directly: `connect()` is *synchronous from the caller's perspective* in Python (it blocks until the handshake completes or errors), so the SYN_SENT window is closed by the kernel before `connect()` returns. Likewise CLOSING and LAST_ACK are too brief to observe.

### The graceful close: FIN / FIN-ACK / FIN-ACK

When the application calls `close()`, the kernel does a 3-way close:

1. Local kernel sends FIN.
2. Peer ACKs the FIN (peer enters CLOSE_WAIT).
3. Peer sends its own FIN when its application calls `close()`.
4. Local kernel ACKs (enters TIME_WAIT for 2*MSL).
5. After 2*MSL, the socket is fully CLOSED.

A nicer pattern is `shutdown(SHUT_WR)`, which sends FIN but leaves the socket open for reading — useful when you need to receive the peer's final messages. The pair `shutdown(WR)` + `close()` is what `socket.SocketType.close()` actually does internally for blocking sockets in CPython.

### The abrupt close: RST

If the application calls `close()` while the receive buffer has unread data, or the application exits without `close()` and the SO_LINGER timeout is non-zero, the kernel sends an **RST** instead of a FIN. An RST is an immediate, unacknowledged abort: the peer receives it, discards unacked data, and closes its side without TIME_WAIT. RST is the right tool when you have nothing more to say; FIN is the right tool when the application wants the *peer* to also clean up nicely.

### Stop-and-wait over UDP: a 2-state reliable transport

Now flip the perspective. Build your own reliable transport on top of UDP. The simplest correct version has four states on the sender side, but they collapse to two because of the alternation:

```
S0 (READY) --send data 0--> S1 (WAIT_ACK)
S1 (WAIT_ACK) --ACK 0--> S0
S1 (WAIT_ACK) --timeout--> S1 (retransmit)
```

A single bit is enough to name the state: "currently sending sequence bit 0" or "currently sending sequence bit 1." When you receive the matching ACK, flip. When the timer fires, retransmit. The protocol is correct by RFC 913 (informational) and is the basis for the alternating-bit protocol (ABP) used in TFTP (RFC 1350).

A packet-loss simulator with a 20% loss rate shows the protocol surviving: the sender retransmits on timeout, the receiver drops duplicates by sequence number, and the application sees an in-order stream. The state machine is identical in shape to the sender half of TCP — same idea, different owner.

### Why this matters: every reliable transport is a state machine

TCP, SCTP, DCCP, and your UDP-based stop-and-wait all implement the same shape: a sender alternates between "data sent" and "ack received" and a receiver alternates between "data expected" and "ack sent." The differences are:

- Where the state lives (kernel vs. user)
- How many bits of sequence number are used (TCP uses 32)
- Whether ACKs are cumulative or selective (TCP cumulative, SCTP selective)
- How loss is detected (timeout vs. SACK vs. NACK)
- Whether the channel has flow control (TCP yes, stop-and-wait no)

The lesson: do not learn TCP as a special case. Learn the **reliable-transport-over-unreliable-channel** template, and TCP becomes one instance of it.

## Build It

`code/main.py` is a stdlib-only lab with three parts tied to the concept.

1. **Socket state observer** — uses `socket.socket(AF_INET, SOCK_STREAM)` to drive a client and a server through every observable state, prints the state after each call, and demonstrates both `close()` (graceful) and `close()` after buffer is full (RST).
2. **Stop-and-wait reliable transport** — implements `StopAndWaitSender` and `StopAndWaitReceiver` over a `socket.socket(AF_INET, SOCK_DGRAM)`, with a `LossyLink` that drops packets with a configurable probability.
3. **State matrix** — runs N trials and reports per-trial retransmits, duplicate drops, and final correctness.

Run `python3 code/main.py`. To see real wire behavior, set `WIRE_TAP=1` and run with a packet sniffer (e.g. `tcpdump -i lo0 -n`).

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Trace a TCP state | `ss -tn` or `getsockopt` | You see `LISTEN`, `ESTABLISHED`, `TIME_WAIT` in the right order |
| Compare FIN vs RST | `tcpdump` shows FIN-ACK or RST | FIN: 3-way close + TIME_WAIT; RST: no TIME_WAIT, immediate teardown |
| Build stop-and-wait | Sequence 0 then 1 then 0... | Receiver gets every message in order; no duplicates delivered to app |
| Survive 20% loss | Sender retransmits count > 0 | Receiver still gets 100% of messages; duplicates dropped by seq bit |
| Decide shutdown vs close | Linger behavior | Use `shutdown(SHUT_WR)` when you want peer to also clean up |

`ss` is the modern replacement for `netstat`. Try `ss -tn state time-wait` to see all TIME_WAIT sockets on a busy web host.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **socket-lifecycle cheat sheet** mapping each BSD socket call to the resulting RFC 793 state, plus a separate column for "what the application sees."
- A **stop-and-walt protocol spec** — the 4-state sender FSM, the sequence-bit alternation rule, the timeout-retransmit policy.
- A **close-decision tree** — when to use `close()`, `shutdown(SHUT_WR)`, `shutdown(SHUT_RDWR)`, or `SO_LINGER(0)` to force RST.
- The **lab code** (`code/main.py`) wired to your own packet captures.

Start from `outputs/prompt-socket-lifecycle-lab.md`.

## Exercises

1. After `connect()` returns successfully, run `ss -tn` and find the local socket. What state is it in? What state will it be in 1 second later, after a `close()`?
2. Set `SO_LINGER` to 0 and call `close()`. What does the peer see on the wire — FIN or RST? Repeat without `SO_LINGER`. Why the difference?
3. Run the stop-and-wait lab with 0%, 20%, 50%, and 80% packet loss. At what loss rate does the protocol start to thrash? Why?
4. Replace the 1-bit sequence number with a 3-bit number. The receiver must now handle wrap-around (e.g. 7 -> 0 is valid). What new state does the receiver need?
5. A TCP server handles 1000 connections/s. After a day, `ss -s` reports 60,000 TIME_WAIT sockets. What is the *minimum* set of changes (kernel params or socket options) to bound this without breaking correctness? Cite the relevant RFC.
6. Add a "negative ACK" (NACK) to the stop-and-wait protocol: the receiver can send NACK to trigger immediate retransmit instead of waiting for the timeout. How does the FSM change? Does it still fit in 2 states on the sender?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Berkeley socket | "the socket" | A handle onto a kernel-side TCP (or UDP) control block; defined in 4.2BSD, still the POSIX standard |
| ESTABLISHED | "connected" | RFC 793 state where both sides have completed the 3-way handshake and can exchange data |
| TIME_WAIT | "lingering close" | 2*MSL delay (~60 s on Linux) after the final ACK, absorbs late segments from a previous incarnation |
| FIN / FIN-ACK | "graceful close" | 3-way FIN/FIN-ACK/FIN-ACK exchange; the polite way for one side to say "I'm done sending" |
| RST | "abrupt close" | Unacknowledged abort; used when the application has no data to send but does need the peer to drop unacked bytes |
| Stop-and-wait | "the simplest ARQ" | A 1-bit-sequence ARQ protocol: send, wait for ACK, retransmit on timeout; the basis of TFTP (RFC 1350) |
| Alternating bit | "ABP" | A 1-bit sequence number that flips between 0 and 1; distinguishes a fresh message from a duplicate |
| SO_REUSEADDR | "skip TIME_WAIT" | Allows binding to an address whose 4-tuple is in TIME_WAIT; safe only when the application doesn't rely on the protection |

## Further Reading

- **RFC 793** — *Transmission Control Protocol* (1981), sec 3.2 "Terminology" and sec 3.9 for the full state machine.
- **RFC 1122** — *Requirements for Internet Hosts* (1989), sec 4.2.2.13 — clarifies the TIME_WAIT requirement that the spec weakened.
- **RFC 1350** — *TFTP Protocol* (revision 2) — the canonical example of a stop-and-wait protocol on UDP.
- **RFC 913** — *Simple File Transfer Protocol* — an early, precise description of the alternating-bit protocol.
- Stevens, *UNIX Network Programming* (3rd ed.) vol. 1, ch. 4-5 — the definitive reference on the BSD socket API and its state machine.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), sec 6.2 "Transport Service" and sec 6.5 "Connection-Oriented Transport: TCP".
- Kurose & Ross, *Computer Networking* (8th ed.), sec 3.5 — a clean re-derivation of TCP from a state machine.
