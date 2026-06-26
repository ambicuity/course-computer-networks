# Acknowledged connectionless data link service

> The data link layer can hand the network layer three flavors of service. The middle one — **acknowledged connectionless service** — keeps the design of unacknowledged service (no connection setup, no release, each frame independent) but adds a per-frame **acknowledgement (ACK)** and a **retransmission timer**. The sender transmits a frame, starts a timer, and waits; if an **ACK frame** does not return before the timer expires, it retransmits. The textbook names **802.11 (Wi-Fi)** as the canonical example, contrasting it with **Ethernet**, which is unacknowledged connectionless and simply drops lost frames on the floor. The mechanism is a **stop-and-wait** protocol: at most one outstanding unacknowledged frame, a 1-bit **sequence number** to disambiguate retransmissions, and a finite **retransmission count** after which the frame is abandoned. Because there is no connection, no per-flow state is negotiated up front and no guarantees of in-order or exactly-once delivery — a lost ACK can cause a frame to be delivered twice, which is precisely why the heavyweight connection-oriented service exists for long unreliable links like satellite channels. This lesson builds a runnable stop-and-wait simulator with CRC-32 error detection, exponential timeout backoff, and duplicate-frame detection so you can read the state the protocol leaves behind after every loss, timeout, and retransmission.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Framing and byte/flag stuffing, error-detection codes (CRC/checksum), the three data-link service classes
**Time:** ~70 minutes

## Learning Objectives

- Distinguish unacknowledged connectionless, acknowledged connectionless, and acknowledged connection-oriented service, and state the channel type each fits (Ethernet fiber vs Wi-Fi vs satellite).
- Trace a stop-and-wait exchange frame by frame: DATA, ACK, timeout, retransmission, and explain why the sequence bit prevents a duplicate from being accepted.
- Compute retransmission timer behavior given propagation delay, frame size, and bit rate, including the stall in throughput caused by stop-and-wait on a long-fat link.
- Identify the failure mode specific to acknowledged connectionless service — a lost ACK causing duplicate delivery — and explain why connection-oriented service eliminates it.
- Read the per-frame state (sequence bit, retry count, ACK pending flag, in-flight timer) that the simulator prints, and diagnose which event (corruption, loss, ACK drop) produced a given trace.

## The Problem

A warehouse runs a Wi-Fi barcode scanner over a 2.4 GHz link that loses roughly 1 frame in 50 to microwave-oven interference. The scanner hands the data link layer a 1500-byte inventory record. On Ethernet the same record would ride a single frame with no acknowledgement — if a frame is lost, recovery is the transport layer's problem, and on a clean wired link that almost never happens. On the noisy radio link, leaving recovery to TCP end-to-end is painful: the lost frame is one of a burst, the TCP sender is far away, and a single dropped frame stalls a multi-megabyte transfer for an entire RTT against a remote server.

The engineer's question: how do we recover the lost frame locally, in one hop, without paying for the full ceremony of a connection (setup, numbered frames, guaranteed in-order exactly-once delivery, teardown)? The answer is acknowledged connectionless service: keep the connectionless simplicity, but make every frame individually acknowledged and retransmittable. The cost is one ACK frame per data frame, a 1-bit sequence space, and a retransmission timer — and one subtle hazard: a duplicate delivered to the network layer when an ACK is lost. This lesson makes that trade-off concrete in code.

## The Concept

### The three services, side by side

The data link layer serves the network layer by moving bits between two adjacent machines. The textbook lists three service classes; the differences are whether a connection is set up and whether frames are acknowledged.

| Service | Connection setup? | Per-frame ACK? | Order / duplication guarantee | Example | Channel fit |
|---|---|---|---|---|---|
| Unacknowledged connectionless | No | No | None | Ethernet | Low error rate (fiber), real-time voice where late = useless |
| **Acknowledged connectionless** | **No** | **Yes** | None (duplicates possible) | **802.11 Wi-Fi** | Unreliable wireless |
| Acknowledged connection-oriented | Yes | Yes | Exactly once, in order | PPP over a long modem/satellite link | Long, high-delay, lossy links |

The middle row is this lesson. Note what it does *not* promise: because there is no connection, there is no negotiated initial sequence number and no per-flow state, so a lost ACK can leave the receiver unable to tell a retransmission from a new frame unless a sequence number is present. With a 1-bit stop-and-wait sequence, duplicates are detected — but only within the one-frame window. That is the gap the connection-oriented service closes with numbered, sequenced, connection-scoped frames.

### Why acknowledge at the link layer at all?

The textbook stresses that link-layer acknowledgement is an **optimization, never a requirement**. The network layer could always send a packet, wait for an end-to-end ACK, and retransmit the whole packet on timeout. The problem is efficiency. A link imposes a **maximum frame length** (the MTU of the hardware) and has a known **propagation delay**; the network layer knows neither. If it ships a 10-frame packet and 2 frames are lost on average, end-to-end recovery resends all 10 frames after a long timeout. Link-layer acknowledgement recovers each lost frame in place, one hop, one RTT — correcting errors "more directly and more quickly." On reliable fiber the optimization is not worth its overhead; on inherently unreliable wireless it easily pays for itself. That is the design rationale behind 802.11's per-MPDU acknowledgement and retry.

### Stop-and-wait: the protocol that fits a 1-bit sequence space

Acknowledged connectionless service is most simply realized as **stop-and-wait (SW) ARQ**. The sender keeps a single **in-flight frame** and a single-bit **sequence number** `S` (0 or 1); the receiver keeps a single-bit **expected sequence** `R`. The exchange is:

| Step | Sender | Channel | Receiver |
|---|---|---|---|
| 1 | Send DATA(seq=S), start timer | — | — |
| 2 | — | DATA arrives | Check seq == R; if yes accept, deliver, R ^= 1 |
| 3 | — | — | Send ACK(seq=R) (the *next* expected, i.e. the opposite of the accepted frame) |
| 4 | ACK arrives, stop timer, S ^= 1 | — | — |
| 5 | (timer fires before ACK) retransmit DATA(seq=S), restart timer | — | — |

The 1-bit sequence number is what defeats duplicates. If the sender's ACK is lost, the sender retransmits DATA(seq=S); the receiver is now expecting seq=S^1, but sees seq=S again, recognizes the **duplicate**, re-acks it (so the sender can advance), and silently discards the payload — it never reaches the network layer twice. The single-bit window is exactly wide enough for this: because the sender never has more than one unacknowledged frame outstanding, two states (0 and 1) suffice to tell "this is the frame I'm waiting for" from "this is the one I already accepted."

### Frame field layout

A minimal acknowledged-connectionless frame carries the sequence bit, a type, a length, the payload, and an error-check field. The simulator in `code/main.py` uses this layout (all multi-byte fields big-endian):

| Field | Bytes | Meaning |
|---|---|---|
| `type` | 1 | 0=DATA, 1=ACK |
| `seq` | 1 | 0 or 1 — the sequence bit |
| `len` | 2 | Payload length in bytes |
| `payload` | `len` | The network-layer packet (0 bytes for an ACK) |
| `crc32` | 4 | CRC-32 over `type|seq|len|payload` (IEEE 802 polynomial 0xEDB88320 reflected) |

The CRC is recomputed on receive; a mismatch means the frame is **silently discarded** as if it never arrived — neither a DATA nor an ACK is acted on, which forces a timeout and a clean retransmission. This is the error-detection step the textbook places before any recovery logic.

### The retransmission timer and timeout choice

The sender arms a timer when it sends DATA and disarms it on ACK. The **timeout** must exceed the round-trip time: one-way propagation `Tp`, frame transmission time `Tf = L/R` (L bytes, R bit/s), and ACK transmission time `Ta` (an ACK is small, often one symbol). A safe timeout is `2·Tp + Tf + Ta` plus margin. The simulator models `Tp` as a hop delay and lets you inject losses; the worked example below uses concrete numbers.

Worked example: a 1500-byte (12 000-bit) DATA frame on a 1 Mbit/s radio link with 20 ms one-way propagation. `Tf = 12000 / 1e6 = 12 ms`. An ACK is 8 bytes = 64 bits → `Ta = 64 µs`. Round-trip propagation `2·Tp = 40 ms`. Minimum timeout ≈ `40 + 12 + 0.064 ≈ 52 ms`; in practice add margin and pick ~60–80 ms. If the link drops the DATA, the sender waits the full timeout before retransmitting — during which the channel is **idle**. That idle time is stop-and-wait's core inefficiency, quantified next.

### Throughput of stop-and-wait vs a long-fat link

Stop-and-wait caps utilization at one frame per RTT:

`U = Tf / (Tf + 2·Tp)`

| Link | `Tf` (1500 B) | `2·Tp` | Utilization U |
|---|---|---|---|
| 1 Mbit/s Wi-Fi, 20 ms prop | 12 ms | 40 ms | 12 / 52 ≈ **23%** |
| 100 Mbit/s fiber, 1 ms prop | 0.12 ms | 2 ms | 0.12 / 2.12 ≈ **5.7%** |
| 1 Mbit/s satellite, 250 ms prop | 12 ms | 500 ms | 12 / 512 ≈ **2.3%** |

The satellite row is the textbook's reason for connection-oriented service with **sliding windows** there: a window of W frames lifts utilization toward `min(1, W·Tf / (Tf + 2·Tp))`. Acknowledged connectionless stop-and-wait is fine for short, bursty, low-delay Wi-Fi traffic where one frame per RTT is acceptable and simplicity wins; it is the wrong tool for a long-fat pipe.

### Failure mode: the lost ACK and duplicate delivery

The hazard unique to acknowledged connectionless service is **duplicate delivery when an ACK is lost**. Trace it:

1. Sender sends DATA(seq=0); receiver accepts, delivers to network layer, sends ACK(seq=1).
2. ACK(seq=1) is **lost** in the channel.
3. Sender times out, retransmits DATA(seq=0).
4. Receiver sees DATA(seq=0) but is expecting seq=1 → it is a **duplicate**. With the 1-bit sequence check the receiver *discards* the payload and re-sends ACK(seq=1). The network layer sees the record once.

So the duplicate is caught — but only because the receiver still holds `R=1` from step 1. If the receiver had **rebooted** between step 1 and step 3 (losing `R`), it would reset `R=0`, accept the retransmission as fresh, and deliver the record **twice**. There is no connection, so there is no resynchronization handshake. That is the precise sense in which acknowledged connectionless service gives "no guarantee of exactly-once delivery," and the precise reason connection-oriented service numbers frames within a connection that both endpoints initialize together. The simulator in `code/main.py` lets you inject this exact sequence (drop the ACK, then optionally reset the receiver) and observe whether the duplicate is suppressed or delivered.

### Comparison: stop-and-wait vs sliding-window ARQ

| Property | Stop-and-wait (this lesson) | Go-Back-N | Selective Repeat |
|---|---|---|---|
| Window size | 1 | N | N |
| Sequence bits | 1 | log2(N+1) | log2(2N) |
| Connection needed? | No (fits ack-connectionless) | Usually yes | Usually yes |
| Receiver buffer | 1 frame | 1 frame | N frames |
| Loss recovery cost | 1 retransmit + idle timeout | Resend from lost frame onward | Resend only lost frame |
| Typical use | Wi-Fi management, short bursts | HDLC, older satellite | Modern Wi-Fi Block-ACK, TCP-ish |

Stop-and-wait is the simplest ARQ that still delivers the acknowledged-connectionless contract; the sliding-window variants add the connection-scoped bookkeeping that turns "acknowledged" into "acknowledged connection-oriented."

## Build It

1. Read `code/main.py`. It implements `Frame` (build + parse + CRC-32), a `Channel` that can drop or corrupt frames by index, a `Sender` and `Receiver` running stop-and-wait, and a `simulate()` driver.
2. Run it: `python3 code/main.py`. The default scenario drops DATA frame 1 and ACK frame 3; the trace shows the timeout, retransmission, duplicate-suppression, and final sequence-bit advance.
3. Inspect `assets/acknowledged-connectionless-service.svg` for the timing diagram of a normal exchange, a lost DATA, and a lost ACK — the three cases the code models.
4. Edit the `losses` set in `simulate()` to drop every other ACK and rerun; confirm the receiver's duplicate counter climbs but the network layer still sees each record exactly once while `R` is intact.
5. Set `receiver_reset=True` after the first ACK loss to model a receiver reboot, and confirm a duplicate is now *delivered* — the exactly-once failure mode.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame was recovered | Retry count > 0, eventual ACK received, seq bit advanced | The data reaches the receiver; the trace shows DATA → timeout → retransmit → ACK |
| Confirm a duplicate was suppressed | Receiver log "duplicate seq=0, discarded, re-acked" | Network-layer deliver counter increments once per record, not twice |
| Reproduce the exactly-once hazard | Receiver reset after lost ACK → duplicate delivered | Deliver counter increments twice; this is the gap connection-oriented service closes |
| Justify the timeout | `2·Tp + Tf + Ta` plus margin matches the configured timer | No premature retransmissions on a clean link; recovery within one timeout on loss |
| Pick the service class | Channel error rate, delay, real-time? | Noisy wireless + not real-time → acknowledged connectionless; clean fiber → unacknowledged; long-fat lossy → connection-oriented sliding window |

## Ship It

Produce one artifact under `outputs/prompt-acknowledged-connectionless-service.md`:

- An annotated stop-and-wait trace from `code/main.py` covering three scenarios: clean delivery, lost DATA (retransmission), and lost ACK (duplicate suppression). Call out the sequence bit, retry count, and CRC verdict at every step.
- A short design note: given a 2 ms propagation, 54 Mbit/s, 1500-byte frame Wi-Fi link, compute the timeout and the stop-and-wait utilization, and state whether acknowledged connectionless service is the right choice versus connection-oriented sliding window.

Start from the printed output of `code/main.py` and annotate it with the failure mode each scenario exercises.

## Exercises

1. A sender transmits DATA(seq=1) on a link with 30 ms one-way propagation and 1 Mbit/s, 1500-byte frames. Compute the minimum safe timeout, then compute stop-and-wait link utilization. Would sliding window with W=8 improve it, and by roughly how much?
2. The receiver's ACK is corrupted in flight so its CRC fails at the sender. Walk through the resulting exchange: what does the sender do, what does the receiver see on the retransmission, and how many times is the payload delivered to the network layer? Assume `R` is intact.
3. Repeat exercise 2 but assume the receiver **reboots and loses `R`** between accepting the original frame and seeing the retransmission. State exactly why a duplicate is now delivered, and which property of connection-oriented service would have prevented it.
4. Modify `code/main.py` to add a third frame type, NAK (negative acknowledgement), sent immediately on a detected-but-uncorrectable error. Does this change the number of timeouts in the lost-DATA scenario? Argue why classic stop-and-wait omits NAK.
5. A voice-over-Wi-Fi application prefers unacknowledged connectionless service even on a lossy link. Give the textbook's reason ("late data are worse than bad data") and explain why a retransmitted voice frame arriving after its playback deadline is useless or harmful.
6. On a clean fiber link an engineer proposes enabling 802.11-style per-frame ACKs "for safety." Using the utilization table, argue why the overhead is not justified and where recovery should instead live.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Acknowledged connectionless service | "ACKs but no connection" | Each frame is individually ACKed and retransmitted on timeout, with no setup/teardown and no exactly-once guarantee; 802.11 is the textbook example |
| Stop-and-wait ARQ | "send one, wait" | ARQ with a window of one: a single outstanding frame, a 1-bit sequence number, and one retransmission timer |
| Sequence bit | "a 0 or 1" | A 1-bit frame identifier that lets the receiver distinguish a fresh frame from a retransmission of the last accepted one |
| ACK frame | "the reply" | A small control frame (type=ACK) carrying the next expected sequence number; its loss triggers a retransmission, not a data loss |
| Retransmission timer | "the timeout" | A timer armed on DATA send and disarmed on ACK; firing means the frame is presumed lost and resent |
| Duplicate delivery | "the hazard" | A retransmitted frame accepted as fresh because the receiver lost its expected-sequence state — the failure mode connection-oriented service eliminates |
| Exactly once | "no duplicates" | A delivery guarantee that acknowledged connectionless service does *not* make; only connection-oriented service with numbered, connection-scoped frames does |
| CRC-32 | "the checksum" | A 4-byte polynomial remainder (IEEE 802, 0xEDB88320 reflected) appended per frame; mismatch ⇒ silent discard, forcing a timeout |
| Utilization | "efficiency" | Fraction of link time spent sending useful data: `Tf / (Tf + 2·Tp)` for stop-and-wait — the metric that exposes its weakness on long-fat links |

## Further Reading

- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Section 3.1.1 ("Services Provided to the Network Layer") and Section 3.3 (error control / sliding-window protocols).
- **IEEE 802.11-2020**, Clause 9 — the MPDU acknowledgement and retry mechanism that realizes acknowledged connectionless service on Wi-Fi, including the `Retry` bit and short/long retry counters.
- **RFC 1662** — PPP in HDLC-like framing, an example of a connection-oriented data link protocol with numbered frames for contrast.
- **ITU-T Q.921** — LAP-D, an HDLC variant showing the connection-oriented side of the service spectrum.
- Bertsekas & Gallager, *Data Networks*, 2nd ed., Chapter 2 — ARQ analysis: stop-and-wait, go-back-N, and selective-repeat throughput derivations.
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, Chapter 6 — link-layer service models and Wi-Fi's use of link-layer ACKs.
