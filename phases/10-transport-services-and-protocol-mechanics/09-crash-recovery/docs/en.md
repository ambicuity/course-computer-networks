# Crash Recovery in Reliable Transport Protocols

> A reliable transport that survives packet loss must also survive the loss of an *endpoint*: a host may crash, reboot, or drop a connection mid-transfer and leave its peer in a half-up state. Crash recovery is the subset of reliable data transfer that addresses what happens when one of the two parties disappears between sending a byte and acknowledging it. The classic taxonomy from Tanenbaum distinguishes seven cases based on (a) which side sent data last, and (b) which side crashes first. RFC 793 specifies how TCP handles a client crash in the OPEN/CALL state using a "user timeout" that the server arm waits before flushing partial state, and RFC 1122 (Requirements for Internet Hosts) sharpens these rules with the keep-alive timer. A central impossibility result — the **Two-Army Problem** (also called the Byzantine Generals' Problem for agreement) — shows that no finite number of deterministic ACKs can *prove* a final delivery over a lossy channel, which is why TCP uses timeouts and a 2-Minute Silly Window Syndrome fix rather than multi-round synchronous commit. This lesson walks through the seven cases, the Two-Army proof sketch, the TCP user-timeout / keep-alive interaction, and a small simulator that drives a state machine through crash + restart.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 10 lessons 06 (connection release) and 08 (error and flow control); familiarity with finite state machines, ACKs, sequence numbers, retransmission
**Time:** ~70 minutes

## Learning Objectives

- Enumerate the seven crash-recovery cases (1=client OK, 2-6=client crashes, 7=server crash) and predict for each whether the connection can be resumed cleanly or must be reset.
- Explain why the **Two-Army Problem** prevents a finite deterministic handshake from guaranteeing a final byte delivered, and how TCP escapes the impossibility by using timeouts rather than N-th-ACK.
- Distinguish a **hard crash** (host down, memory lost) from a **soft crash / restart** (process dies, sockets torn down) and trace which control blocks survive.
- Compute the **TCP user timeout** (RFC 793, refined in RFC 5482) and the **keep-alive** interval (RFC 1122 §4.2.3.6) and explain why the server "arms" both when it first detects silence.
- Build a finite state machine that processes CRASH, RESTART, TIMEOUT, and ACK events and produces a state-transition trace you can inspect after the run.

## The Problem

A file-transfer daemon is moving 1.4 GB between two machines. The sender has transmitted 1.1 GB; the receiver has ACKed 1.05 GB; the sender's socket buffer is full. Suddenly, the receiver host loses power. Five seconds later, the receiver's supervisor reboots, the file-transfer process restarts, and the kernel tears down every socket that the dead process owned. The sender, meanwhile, has no idea anything happened: TCP's retransmission timer hasn't fired yet, the window is open, and the user is staring at a progress bar that says "1.1 / 1.4 GB — 78%."

What should the sender do? Wait forever? Send a probe? Tear down? The choice depends on whether (a) the receiver crashed and will return, (b) the application on the receiver died but the host is alive, or (c) the connection is gone forever. This lesson maps those cases to actions a real TCP stack can take, and shows why no finite handshake can settle the question with certainty.

## The Concept

Crash recovery sits on top of error control (retransmit lost segments) and flow control (don't overrun the buffer) and adds a third concern: what state survives the disappearance of one party. The SVG shows the seven-case matrix above the state machine; `code/main.py` simulates the state machine for a small file transfer.

### The seven crash-recovery cases

Tanenbaum & Wetherall (Computer Networks, 5th ed., §6.6) classify crash recovery by which side sent last and which side crashed first. The asymmetry exists because ACKs travel on the data channel and "the side that sent last" is the only one with unacknowledged work to recover.

| Case | Last data was sent by | Crash victim | Effect on surviving side | Action |
|---|---|---|---|---|
| 1 | Client | Server | Server loses partial state; client thinks connection open | Reset by server on its return; client retransmits |
| 2 | Server | Server | Server retransmits its last segments; client may already have them | OK after retransmit; duplicates dropped by seq# |
| 3 | Client | Client | Server has outstanding ACK; client loses everything | Server probes; client re-issues the transfer |
| 4 | Server | Client | Server is mid-send; client loses everything | Server eventually retransmits; user-timeout on client |
| 5 | Client | Server | Server may have committed bytes to its app before crash | App-level idempotency required (or out-of-band recovery) |
| 6 | Server | Server | Server's "last sent" set is on the wire | Idempotent receiver, no work needed |
| 7 | Either | Either, then both | Both lose state | Cold start: re-open connection, re-transfer from a checkpoint |

Cases 1, 3, 4, and 5 are the dangerous ones. Cases 2 and 6 are recovered automatically by sequence numbers; case 7 is mitigated by application-level checkpointing (the only real defense against simultaneous host failure).

### Finite state machine for the sender side

Each side of a connection is modeled as a small FSM. Adding crash and recovery means adding two events: `CRASH(host)` and `RESTART(host)`. The simplified sender transitions:

```
S_IDLE --OPEN--> S_OPENED --SEND x--> S_SENT_x --ACK--> S_DELIVERED
                      |                  |  ^              |
                      | CRASH            |  +--retransmit--+
                      v                  v
                  S_DOWN            S_TIMED_OUT
```

- `S_IDLE`: no connection.
- `S_OPENED`: connection established, no unacked data.
- `S_SENT_x`: byte range `x` sent, waiting for ACK.
- `S_DELIVERED`: ACK received, byte range is durable.
- `S_DOWN`: peer or self in `CRASH` state; timers running.
- `S_TIMED_OUT`: user timeout fired; emit RST or app-level abort.

On `CRASH(self)`, the side writes "unacked ranges" to non-volatile storage if it wants to resume after restart (this is application-level — TCP does not do it for you). On `CRASH(peer)`, the side arms a user-timeout and may begin sending keep-alive probes.

### The Two-Army Problem (and why no ACK is "final")

Imagine two armies camped in separate valleys, each needing the other to attack at dawn to win. They can only communicate by unreliable messenger. Question: is there a finite message exchange that *guarantees* both armies attack together?

Answer: **no.** Proof sketch: let the last message be from A to B. If B does not attack on receiving it, B attacks for no reason (A might not have received B's last ACK); if B *does* attack on receiving it, B might attack alone because A's previous message could have been lost. By induction, no matter how many rounds of ACK, the sender of the *final* message cannot be sure it was received. The same logic applies to a final data segment: you cannot, with a finite number of deterministic acknowledgements, prove the last byte was delivered over a lossy channel.

TCP escapes this impossibility with two design choices:

1. **Timeouts instead of N-th-ACK.** A retransmission timer converts "I'm not sure" into "I'll resend if I don't hear back." The receiver may now receive duplicates; TCP discards them by sequence number.
2. **Application-level semantics.** The user (e.g., `rsync`, `scp`) decides what a "successful transfer" means and writes idempotent code. TCP does not promise atomicity — that is the application's job.

This is why the **2-Minute Silly Window Syndrome** discussion (RFC 1122 §4.2.3.4) is really about *avoiding* small unacked windows: small windows mean small retransmissions, which the receiver may already have, but they also keep the sender's view of unacked state narrow enough to recover after a crash.

### TCP user timeout and keep-alive (RFC 793, 1122, 5482)

TCP's defense against a silent peer is two timers:

| Timer | Set by | Default | RFC | Purpose |
|---|---|---|---|---|
| Retransmission timer | Sender | dynamic (RTO, RFC 6298) | RFC 6298 | Per-segment, fires on no ACK |
| User timeout | Both sides, app-tunable | 5 minutes (BSD) | RFC 793 §3.9 | Caps total unacked time before RST |
| Keep-alive | Optional, opt-in | 2 hours idle / 75 s probe / 8 probes | RFC 1122 §4.2.3.6 | Detects half-open connections |

When the receiver side suspects the peer is dead, the *server arm* of the connection runs both timers. The **server arm** is the side that last received data and is waiting for the next message — a designation from RFC 793, not a process role. After `user_timeout` of silence, TCP sends a RST and tears down. With keep-alive enabled, after `tcp_keepalive_time` of idle, a probe is sent; after `tcp_keepalive_probes` unanswered probes, the connection is killed.

RFC 5482 (TCP User Timeout Option) exposes the user timeout as a socket option (`TCP_USER_TIMEOUT`) so applications can tune it. A database driver, for instance, may set 30 seconds; a long file copy, 5 minutes; an interactive shell, hours.

### Why "safe" data transfer is not the same as "delivered"

Even with all the timers and sequence numbers, TCP cannot promise:

- That an application that *received* a byte has *persisted* it.
- That an application that crashed didn't process a byte and forget.
- That a peer that ACKed isn't lying (TCP is at the wrong layer to detect that).

End-to-end arguments (Saltzer, Reed, Clark, 1984) tell you the application is the only layer that can give you atomicity guarantees. TCP gives you a clean shutdown *handshake* (FIN/FIN-ACK/FIN-ACK); what the application did with the data on the way to its storage is the application's problem. This is the deep reason case 5 ("the server may have committed bytes to its app before crash") is dangerous: the client cannot know whether the side effect happened.

## Build It

`code/main.py` is a stdlib-only simulator with two parts tied to the concept.

1. **Seven-case classifier** — given `(last_data_sender, crash_victim)`, return the Tanenbaum case number, the surviving side's dilemma, and the recommended action.
2. **State machine** — `TransferFSM` runs an event sequence (OPEN, SEND, ACK, CRASH, RESTART, TIMEOUT) and prints each transition. It also computes user-timeout expiry using a configurable `user_timeout_seconds`.
3. **Two-Army counter-example** — for any finite round count `k`, the function `two_army_worst_case_messages(k)` returns the maximum number of distinct message types the protocol would need to be certain, illustrating the impossibility by exhaustion.

Run `python3 code/main.py`. Adjust `events=` in `main()` to drive different crash scenarios; the trace shows the FSM walking through them.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Identify a crash case | `(last_sender, victim)` pair | You name the case (1-7) and the action: reset, retransmit, probe, restart, or check-point |
| Read the FSM trace | Each `S_xxx` transition in order | Sender moves `SENT_x -> TIMED_OUT -> RST` on a peer's silent crash |
| Compute user-timeout | `TCP_USER_TIMEOUT` value | For a 30 s SLA, set `user_timeout=30`, keep RTO at RFC 6298 default |
| Reason about atomicity | Crash case 5 scenario | You say "application idempotency required" and sketch a write-ahead log |
| Two-Army impossibility | Function trace with k=3, 4, 5 | You can argue no finite message count settles it |

Wireshark filter to see retransmissions on a live trace: `tcp.analysis.retransmission`. A long stream of these after a single RST is a half-open connection — exactly what keep-alive is meant to detect.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **crash-case cheat sheet** — the seven-case table with one line of "what the survivor should do" per row, plus a one-paragraph Two-Army proof sketch.
- A **timeout-tuning runbook** — the formulas for `TCP_USER_TIMEOUT`, the keep-alive trio (`tcp_keepalive_time`, `_intvl`, `_probes`), and a decision tree for "DB driver vs long file copy vs interactive shell."
- A **state-machine diagram** (the SVG) annotated with your own RTO and user-timeout values.
- The **simulator script** (`code/main.py`) wired to your own event log.

Start from `outputs/prompt-crash-recovery.md`.

## Exercises

1. A client sends bytes 100-199, then crashes. The server's user-timeout is 60 s; no data is sent for 65 s. What does the server do? What if the client restarts at 30 s?
2. Classify: server sent last, server crashed. What is the case? What does the client see on the wire, and what does the recovered server do?
3. The Two-Army Problem says N rounds of ACK are insufficient. The first ACK was sent by the receiver — could a "final ACK" that the sender-of-final-data *also* acknowledges resolve it? Why or why not?
4. The simulator runs 3 retransmissions before a TIMEOUT. The user-timeout is set to 2 x RTO. Is the connection still up after the 4th event, and what state is the FSM in? Adjust `user_timeout` and observe.
5. A web server has keep-alive disabled. Does it still need a user-timeout? What does disabling keep-alive change about case 1 from the server's perspective?
6. Implement case 7 (both sides crash) in the simulator: schedule a CRASH on both sides between two SEND events, then drive a RESTART on the receiver only. What does the FSM do, and where would an application-level checkpoint help?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hard crash | "the box died" | The host powered off or kernel panicked; all in-RAM control blocks are lost; non-volatile storage survives |
| Soft crash | "the process died" | A specific process exited; the kernel reaped its sockets; other processes and the host are alive |
| Server arm | "the side that last received" | RFC 793 terminology: the side that owns the right to send a RST or keep-alive probe after silence |
| User timeout | "max wait" | A bound on how long TCP lets unacked data sit before giving up; tunable via `TCP_USER_TIMEOUT` (RFC 5482) |
| Keep-alive | "ping the peer" | Optional opt-in probes (RFC 1122) that detect half-open connections after a long idle |
| Two-Army Problem | "just add another ACK" | Impossibility result: no finite deterministic protocol can guarantee final delivery over a lossy channel |
| FIN / RST | "graceful vs abrupt close" | FIN is a clean 3-way shutdown; RST is an immediate, unacknowledged abort used after a crash or invalid packet |
| Half-open connection | "the socket thinks it's open" | A state where one side considers the connection alive but the other has dropped it; keep-alive probes detect it |

## Further Reading

- **RFC 793** — *Transmission Control Protocol* (1981), sec 3.9 "Event Processing" and the user-timeout discussion. The canonical source for the server arm and FIN/RST handling.
- **RFC 1122** — *Requirements for Internet Hosts — Communication Layers* (1989), sec 4.2.3.6 (keep-alive), sec 4.2.3.4 (silly window). Sharpens RFC 793 and is normative for host behavior.
- **RFC 5482** — *TCP User Timeout Option* (2009). Defines `TCP_USER_TIMEOUT` so applications can bound how long they wait for ACKs.
- **RFC 6298** — *Computing TCP's Retransmission Timer* (2011). Karn's algorithm and the RTO computation, which interact with crash recovery because RTO governs retransmit timing.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), sec 6.6 "Crash Recovery" — the seven-case classification.
- Saltzer, Reed & Clark, "End-to-End Arguments in System Design," *ACM TOCS* 2(4), 1984 — the deep reason application-level semantics are the only place atomicity lives.
- Kurose & Ross, *Computer Networking* (8th ed.), sec 3.5 "Connection-oriented transport: TCP" — a clean second look at the same state machine.
