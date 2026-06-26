# TCP Three-Way Handshake and Connection Establishment

> A TCP connection is born from a three-message exchange between a client in `SYN_SENT` and a server in `LISTEN`. The client sends a segment with `SYN=1, ACK=0` carrying its Initial Sequence Number (ISN) `x`; the server replies with `SYN=1, ACK=1`, its ISN `y`, and `ACK=x+1` to acknowledge the client's SYN; the client sends a final `ACK=1` with `ACK=y+1` to acknowledge the server's SYN. All three segments may carry TCP options — typically `MSS`, `Window Scale`, `SACK Permitted`, and `Timestamps` — which is why the SYN is so much larger than the bare 20-byte fixed header would suggest. The original reason for three messages rather than two is the **delayed-duplicate problem** (RFC 793, Saltzer-Reed-Clark 1975): a stale SYN from a prior connection could still be in flight, and a two-way handshake cannot distinguish a fresh request from a replay. ISNs were originally picked from a 4 µs clock tick to make the probability of a duplicate vanishingly small; modern stacks add cryptographic randomization (RFC 6528) so attackers cannot guess them. This lesson builds a packet-level simulator of the three-way exchange, including SYN cookies (the defense against SYN flood attacks described in RFC 4987) and simultaneous open (when both sides send SYN at the same time).

**Type:** Build
**Languages:** Python
**Prerequisites:** Lessons 17 and 18 (TCP byte stream and segment header), basic state machines, the connection-state FSM in lesson 20
**Time:** ~90 minutes

## Learning Objectives

- Trace the three segments of a normal TCP open (`SYN → SYN+ACK → ACK`) and explain the role of `ISN`, `ACK`, and consumed sequence numbers.
- Simulate the simultaneous-open edge case, where both sides send SYN at the same time and the resulting four-segment exchange resolves to one connection.
- Compute the SYN-ACK retransmission timer that defends against lost SYNs, and explain why the timer is derived from the round-trip time.
- Implement a simplified SYN cookie generator (RFC 4987) and verify that the third ACK of the handshake can be validated without storing server-side state.
- Predict which TCP options a modern SYN carries (MSS, Window Scale, SACK Permitted, Timestamps) and how the receiver uses them.
- Recognize a SYN flood pattern in a packet capture and explain why SYN cookies or SYN caches are necessary.

## The Problem

A web server crashes under load. You check the kernel's listen queue and find it is full of half-open connections — each is a SYN received, no matching ACK, memory tied up indefinitely. The server is not slow to respond; it has no state to respond from. The classic 1990s SYN flood is back, and you need a defense you can implement and reason about.

The deeper question is the one RFC 793 left half-answered: how do two endpoints agree on each other's ISN before exchanging any data? A two-way handshake cannot tell a fresh SYN from a delayed duplicate. Three messages are the minimum that lets both sides confirm the other's ISN is current.

## The Concept

### The normal three-way handshake

```
Client                              Server
LISTEN                              LISTEN
SYN_SENT  ---SYN seq=x, MSS=1460-->  SYN_RCVD
ESTAB     <--SYN+ACK seq=y, ack=x+1--
          ---ACK ack=y+1---------->  ESTAB
```

Three properties hold at the end:

1. Both sides have confirmed each other's ISN (`x` and `y`).
2. Both sides have allocated state (transmission control block, retransmission timer, congestion window).
3. No delayed-duplicate SYN can produce a phantom connection, because a stale segment will carry a sequence number from a previous epoch and the ACK will not match.

### Why each SYN consumes one byte of sequence space

A SYN carries no application data, but it must be **acknowledged unambiguously**. If `ACK=x+1` were sent in response to a SYN that consumed zero sequence numbers, then `ACK=x+1` would also be a valid response to a hypothetical zero-byte data segment with `SEQ=x`. The receiver could not tell the two apart. By reserving one byte for the SYN, every sequence number corresponds to exactly one byte of stream content, including the SYN itself.

### Simultaneous open (RFC 793 §6.5)

When both sides send SYN at the same time, the exchange looks like this:

```
A                              B
SYN_SENT ---SYN seq=x------>   SYN_SENT  (received SYN while sending its own)
         <--SYN seq=y------   SYN_RCVD
SYN_RCVD  ---SYN seq=x, ack=y+1-->
         <--SYN seq=y, ack=x+1--  ESTABLISHED  (A also ESTABLISHED)
```

The result is one connection identified by the 5-tuple. RFC 793 says the heavy path is the normal one and "lightface lines are unusual event sequences" — but simultaneous open is well-defined and the state machine handles it.

### ISN selection: clock-driven and cryptographic

ISNs must change between connections to defeat delayed-duplicate attacks. RFC 793 originally proposed a 4 µs clock counter; RFC 1948 added a per-connection hash `(src, dst, src_port, dst_port, secret)` so that an attacker who knows one ISN cannot predict the next. Linux's `tcp_syncookies` mode falls back to a hash-based SYN cookie under flood conditions.

### SYN cookies (RFC 4987)

When the listen queue is full or the host is under attack, the server **does not store** the client's ISN. Instead, it computes a cookie:

```
cookie = timestamp_low_5_bits
       | (MSS_index       << 5)   # 3 bits -> 8 possible MSS values
       | (HMAC(secret, src_ip, src_port, dst_ip, dst_port, ts) << 8)
```

The cookie is sent as the server's ISN. The client returns `ACK = cookie + 1`. The server regenerates the cookie from the ACK and validates it — no server-side state needed. Caveats: only one MSS choice (no Window Scale negotiation), no SACK, no partial options.

### Retransmission of the SYN

If the client's SYN is lost, the kernel retransmits with exponential backoff: 1 s, 2 s, 4 s, 8 s, 16 s, 32 s, 64 s (capped at 75 s by RFC 6298 / Linux defaults). Each retransmission doubles the interval. After ~9 attempts the kernel gives up and the `connect()` syscall returns `ETIMEDOUT`.

### Options carried on the SYN

A modern SYN is typically 32–40 bytes because of these options:

| Option | Why on a SYN |
|---|---|
| MSS | Tells the peer the largest segment this host will accept |
| Window Scale | Multiplies the 16-bit Window field up to 14 bits, giving a 1 GB window |
| SACK Permitted | Both sides agree selective ACK is OK |
| Timestamps | Enables PAWS and accurate RTT sampling (RFC 1323) |
| NOP | Padding to align to a 32-bit boundary |

If you see a SYN with payload > 0, look for a TCP Fast Open (TFO, RFC 7413) cookie carrying up to ~15 bytes of application data inside the SYN itself.

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/19-tcp-three-way-handshake-and-connection-establishment
python3 code/main.py
```

The script:

1. Simulates the normal three-way handshake and prints the three segments with their sequence numbers, ACK numbers, and flags.
2. Walks the simultaneous-open edge case (both sides send SYN before receiving the peer's SYN).
3. Implements a SYN cookie scheme: the server computes `cookie = timestamp_low_bits | mss_index | hmac(...); 32 bits total`, returns it as the server ISN, and validates the third ACK without any stored state.
4. Walks the SYN-retransmission timeline: 1 s, 2 s, 4 s, …, 64 s, give up after 9 attempts.
5. Decodes a list of captured options from a SYN into named TLVs.

Use `handshake_normal()`, `handshake_simultaneous_open()`, and `syn_cookie()` to plug in your own parameters.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| Three segments open a connection | `handshake_normal()` prints `SYN → SYN+ACK → ACK` | `tcpdump -i any -nn 'tcp[tcpflags] & tcp-syn != 0'` |
| Simultaneous open converges | `handshake_simultaneous_open()` walks the four-segment exchange | RFC 793 §6.5 walkthrough |
| SYN cookie validity | `syn_cookie()` regenerates the cookie from the ACK and matches | Linux `tcp_syncookies=1` under flood |
| Retransmission timeline | `retransmit_schedule()` prints the backoff sequence | `ss -i` shows the timer on a half-open socket |
| Options negotiation | `decode_syn_options()` names each TLV | Wireshark TCP options pane |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable state-diagram walk-through of the three-way handshake with the simultaneous-open branch.
- A reference SYN cookie implementation in your language of choice, with the secret-key rotation policy called out.

Start from [`outputs/prompt-tcp-three-way-handshake-and-connection-establishment.md`](../outputs/prompt-tcp-three-way-handshake-and-connection-establishment.md).

## Exercises

1. A client picks `ISN = 100000`. The server picks `ISN = 200000`. List the three segments with their `SEQ`, `ACK`, and flag values, in the order they are sent.
2. The first SYN is lost. What does the client retransmit, and at what times? Use `retransmit_schedule()`.
3. A simultaneous open occurs. How many segments are exchanged before both sides enter `ESTABLISHED`, and what is the final ACK value on each side?
4. The server's listen queue is full. Explain step-by-step how a SYN cookie lets the third ACK validate the connection without stored state.
5. A capture shows SYN options `02 04 05 b4 03 03 07 04 02 08 0a 00 00 00 00 00 00 00 00 00`. Decode each TLV.
6. Why must a SYN consume a sequence number, but a SYN+ACK consume only one (not two)?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Three-way handshake | "SYN, SYN-ACK, ACK" | Three-segment exchange to synchronize ISNs and allocate state on both sides |
| ISN | "the starting sequence number" | Initial Sequence Number picked per connection; bytes are numbered `ISN+1, ISN+2, ...` |
| SYN_SENT | "client opened" | Client state after sending the first SYN; waits for SYN+ACK |
| SYN_RCVD | "server accepted" | Server state after sending SYN+ACK; waits for the final ACK |
| Simultaneous open | "both sides connect" | Each side sends SYN before receiving the peer's; resolves to one connection |
| SYN flood | "denial of service" | Attacker sends SYNs without completing the handshake, exhausting the listen queue |
| SYN cookie | "no server state" | Cryptographic ISN encoding so the server can validate the third ACK without storing anything |
| Retransmission timer | "how long to wait" | Backoff sequence for re-sending the SYN: 1 s, 2 s, 4 s, ... (RFC 6298 / Linux defaults) |

## Further Reading

- RFC 793 — Transmission Control Protocol (the three-way handshake in §6.5)
- RFC 6528 — Defending against Sequence Number Attacks (cryptographic ISN selection)
- RFC 1948 — Defending Against Sequence Number Attacks (the basis for modern ISNs)
- RFC 4987 — TCP SYN Flooding Attacks and Common Mitigations (SYN cookies)
- RFC 6298 — Computing TCP's Retransmission Timer (the backoff schedule)
- RFC 1323 — TCP Extensions for High Performance (timestamps, window scale, PAWS)
- RFC 7413 — TCP Fast Open (data in the SYN)
- Saltzer, Reed, and Clark, *End-to-End Arguments in System Design*, ACM TOCS 1984 (why the three-way handshake exists)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, TCP connection establishment