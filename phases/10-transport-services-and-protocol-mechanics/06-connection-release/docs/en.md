# Connection Release

> Releasing a connection sounds easy but is full of pitfalls. Asymmetric release (the phone-system model: one side hangs up, the connection is gone) is unsafe because in-flight data is lost - the textbook's Fig. 6-12 shows a host sending a segment, then a DISCONNECT, while the segment is still in flight; the segment never arrives. Symmetric release treats each direction as a separate connection and requires each side to close independently. Tanenbaum's §6.2.3 walks the four failure modes of the symmetric three-way release handshake: normal (DR -> DR -> ACK), final ACK lost (timer saves the receiver), response DR lost (initiator retransmits), and total loss (both sides time out and release independently). The two-army problem shows that even with three messages, *guaranteed* mutual agreement on release is impossible; TCP's compromise is unilateral timeout plus a keep-alive timer to detect half-open connections.

**Type:** Build
**Languages:** Python (stdlib-only release-protocol simulator)
**Prerequisites:** Addressing to Connection Establishment (lesson 05), Berkeley Sockets (lesson 03)
**Time:** ~70 minutes

## Learning Objectives

- Distinguish asymmetric release (one DR drops the connection, can lose data) from symmetric release (each direction is its own connection, requires two closes) and explain why every reliable protocol uses the latter.
- Trace the textbook's three-way release handshake (DR, DR+ACK, ACK) and the four failure scenarios of Fig. 6-14: (a) normal, (b) final ACK lost, (c) response DR lost, (d) all DRs lost.
- Explain the role of the release timer: the initiator arms it when sending DR, the responder arms it when sending DR+ACK, and a timeout always resolves the protocol in favor of releasing the connection.
- Articulate the two-army impossibility result in the release context: no finite N-message protocol over a lossy channel can guarantee two parties *both* decide to release, so TCP's strategy is to let one side give up unilaterally.
- Describe the half-open connection problem, the inactivity-timer mitigation (often 2 hours on real TCP), and why an `RST` (reset) is sometimes preferred over a graceful FIN for HTTP servers that know the data exchange is over.

## The Problem

Two failure modes recur in production TCP services. First, a server receives a request, sends the response, and closes the connection with a `RST` instead of a FIN because it knows the client is done sending. From the client's perspective, the connection "vanishes" - the next `recv` returns zero bytes mid-stream, the kernel log shows `connection reset by peer`, and any final cleanup work the client intended to do is silently lost. The textbook calls this an "asymmetric close" and uses it deliberately for HTTP because the request-response pattern is known in advance.

Second, a long-lived connection (an SSH session, a database pool) is left open after one of the peers crashes. The other peer keeps sending data, eventually triggering a retransmission storm, then a keep-alive timeout (often 2 hours later) and a `RST` from the kernel. The fix is an explicit inactivity timer and a deliberate close, not a passive timeout.

This lesson is about the four-message (DR, DR, ACK) handshake that TCP uses for graceful close, the timer that backs it up, and the half-open failure mode that no protocol can fully eliminate.

## The Concept

### Asymmetric vs symmetric release

**Asymmetric release** is the phone-system model: one party hangs up, the connection is gone. The textbook's Fig. 6-12 shows why this is unsafe for data transport:

```
   Host 1                            Host 2
   CR ------------------------>
   <------------------------ ACK
   DATA ----------------------->   (arrives)
   DATA -----------------------X   (in flight, never arrives)
   <------------------------ DR
   connection torn down
```

The second DATA was in flight when the DR was processed. Asymmetric release drops the connection and the second DATA segment is silently lost.

**Symmetric release** treats the connection as two independent unidirectional pipes. Each direction is closed separately; either side can keep reading from the other even after it has stopped writing. The connection is fully released only after both sides have closed.

The textbook's three-way release handshake (Fig. 6-14) implements symmetric release:

```
   Host 1                            Host 2
   Send DR, start timer
   DR -------------------------->
                                       receive DR, send DR, start timer
            <------------------------ DR
   receive DR, send ACK
   ACK ------------------------->
   release connection
                                       receive ACK, release connection
```

Each side has its own timer. The initiator's timer catches the case where the response DR is lost. The responder's timer catches the case where the final ACK is lost. After at most one timer expiry, both sides release.

### The four failure scenarios

**(a) Normal case.** DR -> DR+ACK -> ACK. Both sides release. Time: 1.5 RTT plus per-segment transmission.

**(b) Final ACK lost.** The initiator sends the ACK, then releases. The responder's ACK is lost, but the responder's timer expires before the next retransmit, and the responder releases anyway. The connection is gone from both sides. The cost: the responder's "release" happens a few seconds late, after the timer fires.

**(c) Response DR lost.** The initiator's DR arrives, but the responder's DR is lost in the network. The initiator's retransmit timer fires; the initiator re-sends DR. Eventually the responder's DR (or its retransmit) arrives, and the protocol completes as in (a). The number of retransmits is bounded; after N attempts, the initiator gives up and releases unilaterally.

**(d) All DRs lost.** Every DR and every retransmit is lost. After N retransmit attempts, the initiator releases. Independently, the responder's timer expires and the responder also releases. Both sides are done; the cost is that the responder did not actually receive a DR, so the connection is "half-open" from its perspective for the duration of its timer.

### The two-army problem in release

The same two-army argument that defeated absolute establishment agreement defeats absolute release agreement. For any N-message release protocol, the Nth message is either essential (and so can be lost, leaving the sender uncertain) or inessential (and so can be removed). TCP's compromise:

1. The initiator arms a retransmit timer; after N failures, it gives up and releases.
2. The responder arms its own timer; after T seconds of silence, it releases.
3. A keep-alive timer (default 2 hours in Linux) sends a probe; if no response, the connection is torn down.

The result: release is *eventually* symmetric, but in the worst case it can take tens of seconds. For applications that know the data exchange is over (HTTP request-response, single-shot RPC), an `RST` (reset) skips the timer and forces an immediate tear-down. The textbook calls this "more like an asymmetric close" and notes that it works only because the application knows the pattern.

### The two-army impossibility

The textbook's proof (paraphrased from §6.2.3):

> Suppose some N-message protocol guarantees agreement to release. Either the last message is essential or it is not. If it is not, remove it (and any other unessential messages) until every remaining message is essential. If the last essential message is lost, the protocol fails. Since the sender of the last message can never be sure of its arrival, the sender will not release. Since the other party knows this, that party will not release either. QED.

The lesson: do not try to build a "guaranteed simultaneous release" protocol. Build a "release when you are done" protocol and let timers handle the worst case.

### TCP's instantiation

TCP implements the three-way handshake release as a FIN exchange, not a DR/DR/ACK triplet. The four states involved are:

| State | Meaning |
|---|---|
| `ESTABLISHED` | Normal data flow |
| `FIN_WAIT_1` | Local side has sent FIN, waiting for ACK from peer |
| `FIN_WAIT_2` | Local side has received ACK of its FIN, waiting for peer's FIN |
| `TIME_WAIT` | Local side has received peer's FIN and ACKed it; waiting 2 * MSL (60-120 s) to drain stray segments |
| `CLOSE_WAIT` | Peer has sent FIN; local side has not yet sent its own FIN (i.e. application has not called `close()`) |
| `LAST_ACK` | Local side has sent its own FIN, waiting for the final ACK |

The half-open state occurs when one side crashes, the other side's retransmissions fail, and the surviving side keeps the connection in `ESTABLISHED` (or `FIN_WAIT_*`) for the duration of its keep-alive timer. Linux's default `tcp_keepalive_time` is 7200 seconds (2 hours), `tcp_keepalive_intvl` is 75 seconds, and `tcp_keepalive_probes` is 9. That gives 2 hours + 9 * 75 s = ~3.6 hours before the kernel gives up.

### Why a `RST` is sometimes preferred

When a server knows the application-layer dialog is over (the HTTP request-response case), it can send a `RST` instead of a `FIN`. The receiver's kernel immediately tears down the connection - no `TIME_WAIT`, no retransmit. The downside: data the peer might have queued is silently dropped. The textbook's argument for HTTP: the pattern is "client sends request, server sends response, both are done." A `RST` is asymmetric but it is correct precisely because the data exchange is already complete.

## Build It

`code/main.py` implements the release protocols in pure Python:

1. **Asymmetric release** - host 1 sends a `DATA` segment, then immediately a `DR`. The simulator drops the in-flight DATA, demonstrating the data-loss bug.
2. **Three-way symmetric release (Fig. 6-14)** - four scenarios: (a) normal, (b) final ACK lost, (c) response DR lost, (d) all DRs lost. Each scenario prints the messages, the timer events, and the final state of both sides.
3. **Two-army proof sketch** - the simulator walks a 3-message release protocol and shows that the third message is essential. Drop it and the sender cannot be sure the peer released.
4. **Inactivity-timer mitigation** - a half-open connection is detected after a configurable timeout (default 7200 s) and a `RST` is sent.

Run with `python3 code/main.py`. The four scenarios are independent: pass a `--scenario={a,b,c,d}` flag (or run them in order) to see how each failure mode is handled.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Spot asymmetric-release data loss | segment sent before DR is in flight | That segment is dropped - evidence: receiver's `recv` ends before the segment is delivered |
| Trace a 3-way release | DR, DR, ACK messages | Both sides reach `CLOSED` state with no timer expiry |
| Recognize the timer-rescue in (b) | responder's timer fires after final ACK is lost | Connection is released anyway; the only cost is a few seconds |
| Diagnose "TCP: peer reset" | `RST` segment received | The application sees `errno = 104 (ECONNRESET)`; the connection is gone immediately |
| Distinguish FIN from RST | `tcpdump -i lo0` flag bits | FIN has the FIN flag set and proceeds to TIME_WAIT; RST has RST set and is immediate |
| Reason about the two-army problem | the last-message argument | A `RST` is a deliberately asymmetric shortcut that works only when the application knows the dialog is over |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **release-protocol cheat sheet** mapping DR/FIN/ACK messages to TCP states (`FIN_WAIT_1`, `FIN_WAIT_2`, `TIME_WAIT`, `CLOSE_WAIT`, `LAST_ACK`, `CLOSED`).
- A **failure-mode runbook** with the four scenarios of Fig. 6-14, the timer that catches each, and the worst-case delay.
- A **half-open-connection triage guide** - how to detect (`ss -ti` for retransmissions), how to mitigate (lower `tcp_keepalive_time` and `tcp_keepalive_probes`), and when to prefer `RST` over `FIN`.
- A **two-army proof sketch** in plain language.

Start from `outputs/prompt-connection-release.md`.

## Exercises

1. The asymmetric-release example shows host 1 sends DATA, then DR. The DATA is in flight. What does host 2 do with the DR? What happens to the DATA?
2. In the textbook's Fig. 6-14(c), the response DR is lost. The initiator's timer fires and it retransmits. How many retransmits happen before the initiator gives up? What does the responder do during this time?
3. TCP's TIME_WAIT state is held for 2 * MSL. The default MSL is 60 s. How long does a typical active closer wait in TIME_WAIT? Why 2 * MSL, not 1 * MSL?
4. A keep-alive timer is set to 7200 seconds, with 75-second probes and 9 probes. How long until a half-open connection is detected? What happens if the network has been up the whole time but the peer crashed at t=0?
5. A web server sends a `RST` after a response, even though the client might still be reading. The client sees `ECONNRESET`. Why does this work for HTTP? Why would it fail for SSH?
6. The two-army proof shows that no finite protocol can guarantee simultaneous release. Modify `code/main.py` to add a 4-message release protocol (DR, DR+ACK, ACK, ACK+RELEASE) and show that the last message is also essential.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Asymmetric release | "hang up and the call is gone" | One side's DR tears down the entire connection - unsafe because in-flight data is lost |
| Symmetric release | "close each direction" | Each side closes its own direction; the connection is gone only after both close |
| DR (Disconnection Request) | "FIN" | A segment signaling "I have no more data to send" - the receiver may still send, and the receiver's own DR is independent |
| Three-way release | "FIN, FIN+ACK, ACK" | The textbook's symmetric release handshake; defended by per-side retransmit timers |
| TIME_WAIT | "2 * MSL wait" | The 60-120 s hold after active close; lets the peer receive the final ACK and drain stray segments |
| FIN_WAIT_1 / FIN_WAIT_2 | "we sent FIN" | The two intermediate states between sending FIN and receiving the peer's FIN |
| RST (Reset) | "torn down" | An immediate, asymmetric close that bypasses TIME_WAIT; safe only when the application knows the dialog is over |
| Half-open connection | "the peer vanished" | One side still thinks the connection is live while the other has released; detected by keep-alive timer |
| Keep-alive timer | "the 2-hour watchdog" | A probe that fires after `tcp_keepalive_time` (default 7200 s) of silence; if no response after N probes, the connection is closed |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.2.3** - the source chapter for this lesson (Figs. 6-12, 6-13, 6-14).
- **RFC 793** (1981), "Transmission Control Protocol," §3.5 - "Closing a Connection" - the FIN exchange, TIME_WAIT, and the connection state diagram.
- **Postel, J. (1981), "Transmission Control Protocol," RFC 793, §3.9** - the half-open connection discussion.
- **Stevens, W. R. (1994), *TCP/IP Illustrated, Volume 1*, §18** - a packet-level walkthrough of the FIN exchange.
- **Akkawi, A. (2007), "On the Two-Army Problem and Byzantine Generals"** - a clean impossibility proof writeup.
- **`man 7 tcp` on Linux** - the kernel's perspective on `tcp_fin_timeout`, `tcp_keepalive_time`, `tcp_keepalive_intvl`, and `tcp_keepalive_probes`.
- **RFC 1122** (1989), "Requirements for Internet Hosts - Communication Layers," §4.2.2.13 - the host requirements for half-open connections and the abort-on-zero-window defense.
