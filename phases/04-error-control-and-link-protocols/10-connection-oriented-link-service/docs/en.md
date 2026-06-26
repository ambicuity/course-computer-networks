# Connection-oriented data link service and its three phases

> The data link layer offers the network layer a menu of three services, and the most demanding is **acknowledged connection-oriented service** — the one that hands the network layer the equivalent of a reliable bit stream. Before any data crosses the link, both peers run a **connection establishment** phase that initializes shared state: a **sequence number** counter so each frame is numbered, a **timer** (retransmission timeout, RTO) so a lost frame or lost ACK cannot hang the sender forever, and buffers/counters to track which frames were received. In the **data transfer** phase, every frame carries a sequence number and is acknowledged (positive ACK `RR` "receiver ready" or negative `REJ` "reject"); the sender retransmits on timeout or NAK, and the receiver discards duplicates by sequence number — guaranteeing each frame is delivered **exactly once, in order**. In the **connection release** phase, the variables, buffers, and timers are freed, typically with a graceful `DISC`/`UA` (disconnect / unnumbered acknowledgment) exchange so neither side leaks state. This is the service a long, unreliable link such as a **satellite channel or a long-distance telephone circuit** wants, because acknowledged connectionless service there risks a lost ACK causing a frame to be sent and received several times, wasting precious bandwidth. HDLC (ISO 3309 / ISO 4335, the basis of LAPB in X.25 and PPP's LCP) is the canonical protocol that implements exactly this three-phase, sequence-numbered, ACKed discipline. The failure modes are a stale timer causing needless retransmission, a sequence-number wrap-around if the window exceeds the field width, and a half-open connection when one side crashes mid-transfer — all of which this lesson reproduces in code.

**Type:** Learn
**Languages:** Python, sequence diagrams
**Prerequisites:** Framing and error-detection (CRC) from Phase 4's framing lesson; the three service classes of the data link layer; sliding-window intuition
**Time:** ~80 minutes

## Learning Objectives

- Distinguish the three data-link service classes (unacknowledged connectionless, acknowledged connectionless, acknowledged connection-oriented) and state which real link technology exemplifies each (Ethernet, 802.11 WiFi, satellite/long-haul HDLC).
- Name the three phases of a connection-oriented transfer and list the concrete state (sequence-number counter, RTO timer, buffers, window) each phase touches.
- Explain why a sequence number plus a timer together solve the "lost frame OR lost ACK" ambiguity, and why a 1-bit sequence number suffices for a stop-and-wait protocol but not for a windowed one.
- Trace a frame through HDLC-style fields (flag `0x7E`, address, control byte with N(S)/N(R)/P/F, information, FCS) and identify which field carries the sequence number and which carries the piggybacked ACK.
- Diagnose three failure modes — spurious timeout retransmission, sequence-number wrap when the window exceeds the field, and a half-open connection after a peer crash — and name the protocol mechanism that addresses each.
- Justify, with the textbook's bandwidth argument, why connection-oriented service beats acknowledged connectionless service on a long, unreliable link.

## The Problem

A geostationary satellite ground station in Perth must ship 40 MB of telemetry to a station in Perth's control center over a 64 kbps satellite uplink with a ~270 ms one-way propagation delay and a raw bit error rate around 10⁻⁶. The link is shared and noisy: frames vanish in noise bursts, and occasionally an acknowledgment vanishes too. The network layer above hands the data link layer a stream of 1024-byte packets and expects them to arrive *intact, in order, exactly once* — duplicates would corrupt the telemetry replay, gaps would stall the decoder, and out-of-order delivery would mis-sequence the samples.

The engineer's first instinct is per-frame ACK without a connection: send frame, wait for ACK, retransmit on timeout. But on a 270 ms-delay link, a lost ACK makes the sender retransmit a frame that actually arrived — and because there is no shared connection state, the receiver has no way to know "I already saw sequence 7." The receiver hands sequence 7 to the network layer *twice*, silently corrupting the stream. Multiply by thousands of frames and the telemetry is unusable. The textbook's diagnosis is precise: *"it is conceivable that lost acknowledgements could cause a frame to be sent and received several times, wasting bandwidth."* The cure is to establish shared state first — a connection — so the receiver can distinguish a retransmission of frame 7 from a fresh frame 7.

## The Concept

### The three service classes, side by side

The data link layer's job is to move bits from the network layer on the source machine to the network layer on the destination machine. Three service classes are reasonable:

| Service class | Connection? | ACKs? | Exemplar | When appropriate |
|---|---|---|---|---|
| Unacknowledged connectionless | No | No | Ethernet (802.3) | Low error rate (fiber); real-time voice where late > wrong |
| Acknowledged connectionless | No | Yes, per frame | 802.11 WiFi | Unreliable wireless; recovery at this layer beats end-to-end |
| Acknowledged connection-oriented | Yes | Yes, sequenced | HDLC/LAPB, PPP LCP, satellite long-haul | Long unreliable links where a lost ACK must not cause duplicates |

The progression is one of increasing guarantee at increasing cost. Unacknowledged connectionless does no recovery at all — if a frame is lost to noise, no attempt is made to detect or recover it in the data link layer; that is left to a higher layer. Acknowledged connectionless adds per-frame ACKs and a retransmission timer, so the sender *knows* whether a frame arrived. Acknowledged connection-oriented goes further: it establishes state first, numbers every frame, and guarantees each frame is received **exactly once and in order**. That last guarantee — *exactly once* — is what the connection buys you, because without shared state the receiver cannot tell a retransmission from a fresh send.

### Why per-frame ACK alone is not enough

It is worth pausing on the textbook's subtle point: providing acknowledgements in the data link layer is *an optimization, never a requirement*. The network layer could always send a packet and wait for its peer to ACK end-to-end. The trouble is efficiency. A link has a strict maximum frame length and known propagation delays that the network layer does not know. If the network layer sends a large packet fragmented into 10 frames of which 2 are lost on average, end-to-end retransmission of the *whole packet* is agonizingly slow on a 270 ms satellite hop. Per-frame ACK and retransmission at the data link layer corrects errors directly and quickly. But per-frame ACK without a connection still has the duplicate problem: a lost ACK makes the sender retransmit, and the receiver — having no notion of "I already saw this one" — delivers it twice. The connection is what closes that hole.

### The three phases

When connection-oriented service is used, transfers go through three distinct phases. Each phase manipulates a specific piece of shared state:

| Phase | What happens | State initialized / freed |
|---|---|---|
| 1. Connection establishment | Peers agree to talk; exchange `SABM`/`UA` (HDLC) or SABME/UA; agree parameters (window size, sequence-number width, timeout) | Sequence-number counters → 0; retransmission timer armed; send/receive buffers allocated; window variables (`send_base`, `next_frame_to_send`, `recv_expected`) set |
| 2. Data transfer | Numbered frames sent, ACKed, retransmitted on timeout/NAK; duplicates discarded; order preserved | Counters increment per frame; timer reset on each ACK; window slides forward |
| 3. Connection release | Graceful teardown so neither side leaks state | `DISC`/`UA` exchange; counters, buffers, timers freed; window variables discarded |

Phase 1 is where the *guarantees* are set up. The textbook is explicit: *"both sides initialize variables and counters needed to keep track of which frames have been received and which ones have not."* Without this initialization the receiver's "expected next sequence number" is undefined and duplicate detection is impossible. Phase 2 is where the guarantees are *enforced* — sequence numbers, ACKs, timers, retransmission. Phase 3 is where the guarantees are *retired* — releasing the resources so a future connection on the same link starts clean.

### Sequence numbers, timers, and the lost-frame / lost-ACK ambiguity

The core mechanism lives in phase 2. When the sender transmits a frame it starts a **timer** set to expire after an interval long enough for the frame to reach the destination, be processed, and have the ACK propagate back (the **RTO**). Normally the ACK returns and the timer is canceled. If either the frame *or* the ACK is lost, the timer fires and the sender retransmits.

Retransmission creates a new hazard: the receiver might accept the same frame twice. The defense is a **sequence number** in every frame. The receiver tracks the next sequence number it expects; a frame whose number matches is accepted and the expected counter advances; a frame whose number is *behind* the expected counter is a duplicate and is silently discarded (though the receiver re-ACKs it, so the sender can stop retransmitting). A frame whose number is *ahead* is out of order and the receiver buffers or rejects it per the protocol.

Worked example, stop-and-wait (window = 1), 1-bit sequence number alternating 0/1:

| Step | Sender sends | Receiver expects | Receiver action | Receiver ACKs |
|---|---|---|---|---|
| 1 | Frame seq=0 | 0 | Accept, deliver, advance expected→1 | ACK 1 ("I expect 1 next") |
| 2 | Frame seq=1 | 1 | Accept, deliver, advance expected→0 | ACK 0 |
| 2′ | (ACK 0 lost) | — | — | — |
| 3 | Timer fires; resend seq=1 | 0 | Duplicate! expected is 0, got 1 → discard, re-ACK 0 | ACK 0 |
| 4 | ACK 0 arrives; advance send_base | — | — | — |

The 1-bit sequence number suffices *only* because the window is 1: at any moment there is exactly one outstanding frame, so "is this a retransmission of the last one or a new one?" is a binary question. For a window of W frames the sequence-number space must exceed W (typically ≥ W+1) so the receiver can always distinguish a retransmission of an old frame from a new frame that wrapped around — otherwise **sequence-number wrap-around** corrupts the stream. HDLC uses a 3-bit sequence number (0–7), capping the window at 7; extended HDLC (modulo 128) lifts that to 127.

### Frame format: where the sequence number and the ACK live

In HDLC (ISO 3309 frame structure, ISO 4335 elements of procedure), the connection-oriented discipline is embodied in concrete fields. A standard information frame (I-frame):

| Field | Size | Contents |
|---|---|---|
| Flag | 8 bits | `0x7E` (`01111110`) — frame delimiter; bit-stuffing keeps it unique |
| Address | 8 bits (extensible) | Secondary station address |
| Control | 8 bits (basic) / 16 bits (extended) | Frame type + **N(S)** send sequence + **N(R)** receive sequence (piggyback ACK) + **P/F** poll/final bit |
| Information | variable | Network-layer payload |
| FCS | 16 bits (CRC-16-CCITT) or 32 bits | Frame Check Sequence over Address+Control+Information |
| Flag | 8 bits | `0x7E` — closes the frame |

The control byte of an I-frame encodes: bit 0 = 0 marks an I-frame; bits 1–3 = **N(S)**, the sequence number of *this* frame; bit 4 = P/F; bits 5–7 = **N(R)**, the sequence number of the *next frame this station expects to receive* — i.e. a piggybacked ACK confirming receipt of everything up to N(R)−1. So a single I-frame simultaneously carries new data *and* acknowledges the peer's data, which is far cheaper on a 270 ms satellite link than sending separate ACK frames. Supervisory frames (S-frames, bit 0 = 1, bit 1 = 0) carry only N(R) and a 2-bit type: `RR` (receiver ready, positive ACK), `REJ` (reject, go-back-N negative ACK), `RNR` (receiver not ready, flow control), `SREJ` (selective reject). Unnumbered frames (U-frames, bit 0 = 1, bit 1 = 1) carry the connection-management commands: `SABM`/`SABME` (set asynchronous balanced mode, the connection-establishment command), `DISC` (disconnect), `UA` (unnumbered acknowledgment, the reply to SABM/DISC), `FRMR` (frame rejected). See `assets/connection-oriented-link-service.svg` for the full three-phase exchange with these frame types.

### Phase 1 in detail: connection establishment

Establishment is a three-way agreement in HDLC ABM (Asynchronous Balanced Mode, the symmetric mode used by LAPB and PPP):

1. Side A sends `SABM` (Set Asynchronous Balanced Mode, a U-frame) with the P bit set.
2. Side B initializes its state — `V(S) := 0` (send state variable), `V(R) := 0` (receive state variable), allocates buffers, arms timers — and replies `UA` (unnumbered acknowledgment) with the F bit set.
3. Side A, on receiving `UA`, initializes its own `V(S) := 0`, `V(R) := 0`, allocates buffers, and the connection is *open*. Until `UA` returns, A may retransmit `SABM` on a timer; this is itself a miniature of the data-transfer logic — a command, a timer, a retransmission on timeout.

The crucial invariant: both `V(S)` and `V(R)` start at 0 on both sides *before* any I-frame is sent. This is what makes the first I-frame's sequence number 0 unambiguous — there is no pre-existing frame 0 it could be confused with.

### Phase 3 in detail: connection release

Release is symmetric and graceful. Side A sends `DISC` (disconnect, U-frame) with P set. Side B replies `UA` with F set and frees its buffers, counters, and timers. Side A, on `UA`, frees its own. The connection is closed. If A's `DISC` is lost, A's timer fires and A resends `DISC`. If B's `UA` is lost, A resends `DISC`; B, having already released, replies `UA` again (or `DM`, disconnected mode, depending on state). The graceful exchange prevents the **half-open** failure where one side thinks the connection is alive and keeps sending into a void — a hazard the textbook flags as freeing up resources *"used to maintain the connection."* A real-world half-open happens when B crashes after `DISC` but before `UA`: A waits, times out, resends `DISC`, and eventually gives up. TCP's two-army problem shows that perfectly symmetric graceful close is provably impossible, but the timer-bounded retry makes it practically safe.

### Failure modes and their cures

| Failure | Symptom | Mechanism that catches it |
|---|---|---|
| Lost data frame | Receiver never sees it; sender's timer fires | RTO retransmission; receiver never ACKed so expected counter unchanged |
| Lost ACK | Sender doesn't know frame arrived; timer fires; resends | Sequence number lets receiver discard the duplicate and re-ACK |
| Spurious timeout (ACK merely slow) | Sender retransmits a frame that did arrive | Same as lost ACK — duplicate discarded; the cost is wasted bandwidth, not corruption |
| Sequence-number wrap | Window > field width; receiver mistakes a wrapped new frame for a retransmission | Keep window ≤ field width (HDLC basic: window ≤ 7; extended: ≤ 127) |
| Half-open connection | One peer crashed; other keeps sending | Graceful `DISC`/`UA` with timer; keepalives; eventually give up |
| Peer crash mid-transfer | State lost; counters reset | Re-establish connection (phase 1 again); sequence numbers resync to 0 |

`code/main.py` implements a stop-and-wait connection-oriented link with all three phases and injects exactly the lost-frame, lost-ACK, and spurious-timeout cases so you can watch the sequence numbers, timers, and duplicate-discards do their work.

## Build It

1. Open `code/main.py`. It models a connection-oriented link as a `LinkEndpoint` with `V(S)`, `V(R)`, a send buffer, a retransmission timer, and the three-phase methods `connect()`, `send()`, `release()`.
2. Run `python3 code/main.py`. The demo traces a full session: `SABM`/`UA` establishment, four I-frames with a deliberately dropped data frame and a deliberately dropped ACK, then `DISC`/`UA` release.
3. Read the printed trace line by line: note where the RTO fires, where the duplicate is discarded by sequence number, and where the re-ACK is sent.
4. Change `DROP_FRAMES` to include a third index and rerun — watch the retransmission count climb and confirm delivery still completes exactly once.
5. Set `WINDOW` to 8 in a windowed build (exercise) and observe the wrap-around bug when the sequence field is only 3 bits wide.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm establishment ran | `SABM` sent, `UA` received, `V(S)=V(R)=0` on both sides before any I-frame | No I-frame is sent before both counters read 0 |
| Verify exactly-once delivery | Receiver's delivered list equals sender's sent list, no duplicates, no gaps | A dropped ACK triggers a retransmit that the receiver *discards*, not delivers |
| Diagnose a spurious timeout | ACK arrived late; sender retransmitted; receiver re-ACKed | Stream is intact; only cost is wasted bandwidth, not corruption |
| Catch a half-open | One side `DISC`s, the other crashes; `DISC` timer retries then gives up | No I-frame is sent into a connection no peer is tracking |
| Size the sequence field | Window W needs sequence space > W; HDLC 3-bit caps W at 7 | Picking W=8 with a 3-bit field produces a wrap-around duplicate |

## Ship It

Produce one artifact under `outputs/prompt-connection-oriented-link-service.md`:

- An annotated trace of a three-phase session (establish, transfer of ≥4 frames with one injected loss, release) from `code/main.py`, with each line labeled by phase and each retransmission labeled with the failure it is correcting.
- A one-paragraph decision rule: when to choose connection-oriented service over acknowledged connectionless, using the satellite-vs-Ethernet contrast.
- A sequence-number-width worksheet: for window W, state the minimum sequence-number bits, and show the W=8/3-bit wrap failure.

Start from the printed output of `code/main.py` and annotate it with the failure mode you injected.

## Exercises

1. On a 270 ms one-way satellite link at 64 kbps with 1024-byte frames, compute a sensible RTO and the link's bandwidth-delay product. How many frames could be "in flight" at once, and what does that imply for the minimum sequence-number width if you window the connection?
2. Trace a stop-and-wait session where ACK for frame 1 is lost, then the sender's retransmit of frame 1 is *also* lost. Show the sequence numbers, the timer firings, and the final delivered list. Confirm delivery is still exactly once.
3. HDLC basic mode uses a 3-bit sequence number. A designer sets the window to 8. Construct the exact scenario where a new frame's wrapped sequence number is mistaken for a retransmission, and state the data corruption that results. What is the maximum safe window?
4. Compare the three service classes for a fiber link with BER 10⁻¹² carrying Voice-over-IP. Justify the choice with the textbook's "late data are worse than bad data" argument. Which class is wrong, and why?
5. Side A sends `DISC`; side B crashes before sending `UA`. Walk through the timer behavior on A, the maximum number of `DISC` retransmissions a sane implementation allows, and how A finally concludes the connection is gone. Why is perfectly symmetric graceful close provably impossible (the two-army problem)?
6. In `code/main.py`, add piggybacking: when the receiver has data to send back, ACK via the N(R) field of an I-frame instead of a separate RR. Show the trace and quantify the frame-count saving on the satellite link.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Connection-oriented service | "a reliable link" | A service that establishes shared state (counters, timers, buffers) before transfer so each frame is delivered exactly once, in order |
| Three phases | "setup, send, teardown" | Connection establishment (init V(S)/V(R), buffers), data transfer (sequenced ACKed frames), connection release (free state) |
| Sequence number N(S) | "a frame ID" | The send-state counter value stamped on each I-frame so the receiver can detect duplicates and ordering |
| N(R) | "the ACK number" | The receive-state counter — the next frame this station expects; piggybacked in the control field to ACK everything below it |
| RTO (retransmission timeout) | "the wait timer" | A timer started on each send; if no ACK returns before it fires, the frame is retransmitted — cures both lost frames and lost ACKs |
| V(S) / V(R) | "send/recv variables" | Send-state and receive-state variables; initialized to 0 at connection establishment and advanced per frame |
| SABM / UA | "open / opened" | Set Asynchronous Balanced Mode (U-frame connection request) and Unnumbered Acknowledgment (its reply); together they open the connection |
| DISC | "close" | Disconnect U-frame requesting graceful release; answered by UA, with timer-bounded retry for the two-army problem |
| Half-open connection | "stale connection" | One peer believes the connection is alive while the other has reset; cured by keepalives and bounded `DISC` retries |
| Sequence-number wrap | "ran out of numbers" | When the window equals or exceeds the sequence field width, a new frame's wrapped number is indistinguishable from a retransmission |

## Further Reading

- **ISO 3309** — HDLC frame structure (flag, address, control, FCS definitions).
- **ISO 4335** — HDLC elements of procedure (SABM, UA, DISC, RR, REJ, SREJ, the P/F bit).
- **ISO 7809** — HDLC classes of procedures (Asynchronous Balanced Mode used by LAPB).
- **RFC 1661** — The Point-to-Point Protocol (PPP); its LCP implements the same three-phase establish/terminate discipline over HDLC-like framing.
- **RFC 1662** — PPP in HDLC-like framing (the concrete flag/FCS mapping).
- **ITU-T X.25** — LAPB (Link Access Procedure Balanced), the HDLC ABM profile used in X.25.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.1.1 (Services Provided to the Network Layer) and 3.3 (data link protocols).
- Bertsekas & Gallager, *Data Networks*, 2nd ed., Chapter 2 — stop-and-wait, sliding-window, and the bandwidth-delay product analysis.
