# TCP Connection Release and the Connection State Machine

> Although TCP is full-duplex, the cleanest way to think about release is as a pair of independent simplex connections, each closed by its own FIN exchange (RFC 793 §6.5.6). A graceful close normally takes three segments when one side is done: that side sends `FIN`, the peer ACKs and may continue sending data, then sends its own `FIN`, which is ACKed. With piggybacking that is three wire segments; without piggybacking it is four. Both sides may also initiate close simultaneously, in which case two FINs cross in flight and resolve with two ACKs. The TCP connection-management finite state machine (RFC 793 Figure 6-39) lists 11 states — `CLOSED, LISTEN, SYN_SENT, SYN_RCVD, ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, CLOSE_WAIT, LAST_ACK, TIME_WAIT, CLOSING` — and labels every transition with an event (`CONNECT`, `LISTEN`, `SEND`, `CLOSE`, segment arrival, `2*MSL` timeout) and an action (`SYN`, `FIN`, `ACK`, `RST`, `-`). After both FINs are ACKed the closing side lingers in `TIME_WAIT` for **2 × MSL** (typically 60 seconds) so that any delayed duplicate from the connection can no longer arrive and confuse a new connection that reuses the same 4-tuple. This lesson builds the FSM, walks both the client and the server through their release paths, and answers "why does `ss -tn` show hundreds of TIME_WAIT sockets on a busy web server?"

**Type:** Learn
**Languages:** Python, state diagrams
**Prerequisites:** Lessons 17–19 (TCP byte stream, segment header, three-way handshake)
**Time:** ~75 minutes

## Learning Objectives

- Walk the client and the server through their respective release paths on the 11-state FSM (RFC 793 Figure 6-39) and explain every transition.
- Predict the on-the-wire segments for the three close variants: normal close, simultaneous close, and abortive close (`RST`).
- Compute `TIME_WAIT = 2 × MSL` from the maximum-segment-lifetime and explain why a connection that initiated an active close must wait before fully releasing.
- Explain why a closing client sends a final ACK and then waits, while the closing server sends FIN+ACK and enters `LAST_ACK`.
- Distinguish `CLOSE_WAIT` (peer has closed, my side still sending) from `TIME_WAIT` (I closed, waiting for duplicates to die).
- Implement the FSM in code and verify it accepts valid close sequences and rejects illegal ones (e.g., `FIN` from `LISTEN`).

## The Problem

Your web server is healthy, but `ss -tn | wc -l` returns tens of thousands and most rows show `TIME_WAIT`. Operations is asking whether the server is leaking connections. Worse, a colleague insists `TIME_WAIT` is a bug because "we already sent FIN, why are we holding the port?" If you change `net.ipv4.tcp_tw_reuse` or `tcp_tw_recycle` blindly you will eventually break load balancers that NAT many clients into one IP.

The deeper problem is that closing a connection is fundamentally ambiguous — the **two-army problem** (Agnem 1975) proves no finite protocol can guarantee both sides agree they have both finished. TCP solves this with a timeout (`TIME_WAIT`) and accepts the residual ambiguity as a cost.

## The Concept

### The 11 states

| State | Description | Reached from |
|---|---|---|
| `CLOSED` | No connection active or pending | initial; after `TIME_WAIT` expires |
| `LISTEN` | Server waiting for a SYN | `CLOSED` → `LISTEN` |
| `SYN_SENT` | Client has sent SYN, waiting for SYN+ACK | `CLOSED` → `SYN_SENT` (active open) |
| `SYN_RCVD` | Server received SYN, sent SYN+ACK, waiting for ACK | `LISTEN` → `SYN_RCVD` |
| `ESTABLISHED` | Data transfer | both sides after 3-way handshake completes |
| `FIN_WAIT_1` | Active closer sent FIN, waiting for ACK | `ESTABLISHED` → `FIN_WAIT_1` |
| `FIN_WAIT_2` | Active closer got ACK of its FIN, waiting for peer's FIN | `FIN_WAIT_1` → `FIN_WAIT_2` |
| `CLOSE_WAIT` | Passive closer got FIN, has not yet called `close()` | `ESTABLISHED` → `CLOSE_WAIT` |
| `CLOSING` | Simultaneous close: both sides sent FIN at once | `FIN_WAIT_1` → `CLOSING` |
| `LAST_ACK` | Passive closer sent its FIN, waiting for final ACK | `CLOSE_WAIT` → `LAST_ACK` |
| `TIME_WAIT` | Both FINs ACKed, waiting `2 × MSL` | `FIN_WAIT_2`, `CLOSING` → `TIME_WAIT` |

### The three close variants

**Normal close (client active close, server passive close):**

```
Client                              Server
ESTAB         ---FIN seq=u-------->  CLOSE_WAIT
FIN_WAIT_1    <--ACK ack=u+1-------  ESTAB
FIN_WAIT_2    <--FIN seq=v---------  LAST_ACK
TIME_WAIT     ---ACK ack=v+1----->  CLOSED
(2*MSL)       CLOSED
```

Four segments. The first ACK can be piggybacked on the server's FIN, yielding three segments; that is the typical case in modern stacks.

**Simultaneous close (both sides initiate at once):**

```
A                                B
ESTAB        ---FIN seq=u------>  ESTAB
FIN_WAIT_1   <--FIN seq=v------   FIN_WAIT_1
CLOSING      ---ACK ack=v+1---->
             <--ACK ack=u+1----   TIME_WAIT
TIME_WAIT    (2*MSL)             (2*MSL)
CLOSED                              CLOSED
```

**Abortive close (`RST`):**

Any side can send a segment with `RST=1` to terminate immediately. The receiver drops the connection, sends no further segments, and the kernel frees the TCB. RST is used when an application crashes, when a segment arrives for a non-existent connection, or when the peer needs to be told "go away" without ceremony. RST does **not** consume sequence space and does not wait in `TIME_WAIT`.

### Why `TIME_WAIT` exists

After the final ACK is sent, the connection is "logically" closed but the kernel keeps the 4-tuple around for `2 × MSL` (typically 60 seconds — `MSL` is usually 30 s per RFC 793 / RFC 1323 / Linux defaults). The two reasons:

1. **Delayed duplicates.** A segment from the connection could still be in flight (or buffered in a router). If the same 4-tuple were reused immediately, a stale segment could be accepted as belonging to the new connection. `TIME_WAIT` ensures all duplicates die before the 4-tuple is freed.
2. **Ensuring the final ACK arrives.** If the final ACK is lost, the peer will retransmit its FIN. The `TIME_WAIT` side must be able to receive and re-ACK that FIN. After `2 × MSL` the peer will have given up, so any further segment is by definition a duplicate and can be dropped.

### `TIME_WAIT` is the active-closer's burden

Only the side that initiated the close goes into `TIME_WAIT`. A web server that sends `FIN` first (because it called `close()` after writing the response) pays the wait. A client that keeps its socket open with HTTP/1.1 keepalive pays it. This is why a busy HTTPS server can have hundreds of `TIME_WAIT` sockets — it is doing the work the protocol requires, not leaking.

### The two-army problem and why TIME_WAIT is the best we can do

Imagine two generals trying to agree on a time to attack. Each must know the other knows. No finite sequence of messengers can establish this with certainty (Agnem 1975). TCP accepts the same impossibility: the final ACK can be lost, and the peer's retransmitted FIN might itself be lost. The `2 × MSL` timeout guarantees that after the wait, both sides will give up and converge on `CLOSED` — even if no specific segment was the last one delivered.

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/20-tcp-connection-release-and-the-connection-state-machine
python3 code/main.py
```

The script:

1. Defines the 11 states and the full transition table (event, action, next state).
2. Walks the client through the active-close path: `ESTABLISHED → FIN_WAIT_1 → FIN_WAIT_2 → TIME_WAIT → CLOSED`.
3. Walks the server through the passive-close path: `ESTABLISHED → CLOSE_WAIT → LAST_ACK → CLOSED`.
4. Walks the simultaneous-close case from both sides' points of view.
5. Walks the abortive-close case with `RST` and shows no `TIME_WAIT` is entered.
6. Prints the segment timeline for each variant and the `TIME_WAIT` countdown.

Use `walk(active_close)` or `walk(simultaneous_close)` to plug in your own event sequences.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| Active close ends in `TIME_WAIT` | `walk(active_close)` enters `TIME_WAIT` | `ss -tn` shows the state on the closing socket |
| Passive close ends in `CLOSED` directly | `walk(passive_close)` ends in `CLOSED` | `ss -tn` on the server |
| Simultaneous close visits `CLOSING` | `walk(simultaneous_close)` includes `CLOSING` | Wireshark shows two FINs in flight |
| Abort skips `TIME_WAIT` | `walk(abortive_close)` skips to `CLOSED` | RST in capture |
| `TIME_WAIT` length | `time_wait_duration_msl(30)` returns 60 s | `cat /proc/sys/net/ipv4/tcp_fin_timeout` |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable 11-state FSM diagram with both normal and simultaneous close paths highlighted.
- A runbook for `TIME_WAIT`: when it is healthy, when to tune `tcp_tw_reuse` (only on the active opener of outgoing connections), and why `tcp_tw_recycle` must never be enabled.

Start from [`outputs/prompt-tcp-connection-release-and-the-connection-state-machine.md`](../outputs/prompt-tcp-connection-release-and-the-connection-state-machine.md).

## Exercises

1. List, in order, the segments exchanged for a normal active close with piggybacking. Show state transitions for both client and server.
2. A client calls `close()` immediately after writing its request. Will the connection be in `TIME_WAIT` from the client's side, the server's side, or both? Why?
3. The server's response to a `FIN` is lost in the network. What does the client retransmit and at what times? Use `retransmit_schedule()` from lesson 19.
4. Walk the FSM for a simultaneous close: at what point do both sides reach `TIME_WAIT`? Are their `TIME_WAIT` timers synchronized?
5. Why does an `RST` not consume sequence space and not require `TIME_WAIT`?
6. Linux default `MSL` is 60 seconds. What is `TIME_WAIT`? What does `net.ipv4.tcp_tw_reuse=1` change, and on which side of the connection?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| FIN | "close the connection" | Closes one direction; the peer may continue sending until it also sends FIN |
| Active close | "I initiate the close" | Side that calls `close()` first, sends first FIN, enters `TIME_WAIT` |
| Passive close | "the other side closed" | Side that receives the first FIN, sends ACK, may keep sending until its own `close()` |
| `TIME_WAIT` | "leaked socket" | Active-closer waiting `2 × MSL` so duplicates die and final ACK can be retransmitted |
| `CLOSE_WAIT` | "peer closed, my side open" | Passive closer; application still has unsent data or has not called `close()` |
| `LAST_ACK` | "waiting for final ACK" | Passive closer sent its FIN; waiting for active closer to ACK |
| `CLOSING` | "simultaneous close" | Both sides sent FIN at the same time; each waiting for ACK of its own FIN |
| MSL | "Maximum Segment Lifetime" | The longest time a segment can live in the network before being dropped (typically 60 s) |
| 2 × MSL | "TIME_WAIT duration" | 120 s typical; guarantees duplicates die and final ACK is delivered |

## Further Reading

- RFC 793 — Transmission Control Protocol (the 11-state FSM in Figure 6-39)
- RFC 1323 — TCP Extensions for High Performance (MSL considerations, timestamp interactions)
- RFC 6191 — Reducing the TIME-WAIT State of TCP Connections
- Agnem (1975) — The Two-Army Problem (the proof that no finite protocol can solve the agreement problem perfectly)
- Stevens, *TCP/IP Illustrated, Volume 1*, 2nd ed. — Chapter 13, TCP connection management
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP connection release
- `ss(8)` man page — `TIME-WAIT`, `CLOSE-WAIT`, `FIN-WAIT-1`, `FIN-WAIT-2` columns
- `tcp(7)` man page — `tcp_tw_reuse`, `tcp_tw_recycle` (the latter is dangerous)