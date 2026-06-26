# Services Provided to the Network Layer

> The data link layer's job is to move a network-layer packet across one physical hop and hand it to the peer network layer on the other end. It can offer that handoff at three reliability levels: **unacknowledged connectionless** (Ethernet / IEEE 802.3 — fire frames, no ACK, no sequence numbers, recovery delegated upward), **acknowledged connectionless** (IEEE 802.11 / Wi-Fi — each frame individually ACKed, a retransmit timer of a few hundred microseconds, but still no logical connection), and **acknowledged connection-oriented** (HDLC / PPP over satellite or long-haul — a three-phase setup/transfer/teardown with per-frame sequence numbers that guarantee exactly-once, in-order delivery). The choice is an engineering trade between channel bit-error rate and protocol overhead: on fiber with a BER near 1e-12 the ACK machinery is wasted; on a noisy 802.11 link with a 1-2% frame loss it pays for itself. Acknowledgement at this layer is *always an optimization, never a requirement* — the network layer can always retransmit end-to-end, just far more slowly. The lesson's simulator drives all three classes over a lossy channel and prints the evidence each leaves behind.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib service-class simulator)
**Prerequisites:** Phase 01-02 (OSI layering, physical layer encoding, bit-error rate)
**Time:** ~70 minutes

## Learning Objectives

- Distinguish the three data-link service classes (unacknowledged connectionless, acknowledged connectionless, acknowledged connection-oriented) by the *evidence each leaves on the wire*: ACK frames, sequence numbers, connection-setup frames.
- Justify why Ethernet (802.3) ships unacknowledged service while Wi-Fi (802.11) adds link-layer ACKs, in terms of channel bit-error rate.
- Explain why duplicate delivery happens when an ACK is lost, and how a one-bit or N-bit sequence number suppresses it.
- Compute when link-layer acknowledgement beats pure end-to-end recovery using frame count, loss probability, and the "10 frames, 2 lost" worked example.
- Identify the three phases (establish / transfer / release) of connection-oriented service and the state each side keeps.

## The Problem

A VoIP call and a 4 GB file transfer share the same office Wi-Fi access point. The file transfer is fine. The VoIP call breaks up: callers hear robotic gaps every few seconds. A junior engineer's first instinct is "add reliability — make Wi-Fi retransmit harder." That is exactly wrong.

The two flows want *opposite* services from the same link. The file copy wants every byte eventually, in order, no matter how long it takes — late data is fine, wrong data is not. The voice call wants whatever arrives *now*; a frame that shows up 300 ms late after three link-layer retransmissions is worse than a frame that was simply dropped, because the jitter buffer already played past that moment. "Late data are worse than bad data" for real-time traffic.

To reason about this you have to know precisely what the data link layer offers the network layer, what each offer costs, and what it leaves behind in a packet capture. That is what 802.3, 802.11, and PPP each chose differently, and why.

## The Concept

The data link layer presents the network layer with a **virtual data path**: the network-layer process on Host 1 appears to hand bits directly to the network-layer process on Host 2 (see [`assets/services-provided-to-the-network-layer.svg`](../assets/services-provided-to-the-network-layer.svg)). The *actual* path runs down to the physical layer, across the wire, and back up; the abstraction is two data-link peers talking a data-link protocol. The contract they expose comes in three flavors.

### Service class 1 — Unacknowledged connectionless

The source sends independent frames; the destination never acknowledges them. No connection is set up beforehand or torn down afterward. If a frame is corrupted by line noise, the receiver's checksum fails, the frame is silently discarded, and **no recovery happens at this layer** — it is delegated to a higher layer (TCP) or simply tolerated.

This is **Ethernet (IEEE 802.3)**. It is the right choice when:

- The bit-error rate is very low (modern wired Ethernet BER is around 1e-10 to 1e-12), so loss is rare and end-to-end recovery is cheap.
- The traffic is real-time (voice, video), where late data is useless, so there is no point retransmitting.

Evidence on the wire: you see data frames and *no link-layer ACK frames*. There is no sequence-number field in the classic Ethernet header — just destination MAC, source MAC, EtherType/length, payload, and a 4-byte CRC-32 FCS. The CRC lets the receiver *detect* a bad frame; it does not let it *recover* one.

### Service class 2 — Acknowledged connectionless

Still no logical connection, but **each frame is individually acknowledged**. The sender starts a retransmission timer when it transmits; if no ACK arrives before the timer expires, it retransmits. The sender therefore learns, per frame, whether delivery succeeded.

This is **Wi-Fi (IEEE 802.11)**. On a wireless channel the frame-error rate can be 1-10%, far too high to ignore. Recovering one lost frame across one hop (a SIFS-gap ACK roughly 10-50 µs after the frame, with retransmit timers in the hundreds of microseconds) is dramatically faster than waiting for an end-to-end TCP timeout of hundreds of milliseconds.

Evidence on the wire: in a Wireshark capture of 802.11 you see a 14-byte **Acknowledgement** control frame (frame type/subtype `0x1D`) following each successfully received data frame, with no payload — just the receiver address and FCS. Display filter: `wlan.fc.type_subtype == 0x1d`.

### Why link-layer ACK is an optimization, not a requirement

The network layer can *always* recover on its own: send a packet, wait for the peer to ACK it, retransmit on timeout. So why bother at the link layer? Efficiency. Links impose a strict maximum frame length (Ethernet MTU 1500 bytes) and have known propagation delay; the network layer knows neither. Consider the textbook example:

> A network-layer packet is broken into **10 frames**. The channel loses **2 on average** (20% loss).

With end-to-end-only recovery, the network layer cannot tell *which* 2 frames were lost — it only sees that the whole packet failed, so it resends **all 10**, and may lose 2 again, and again. Expected attempts to push 10 frames through a 20% loss channel grow fast. With per-frame link-layer ACK + retransmit, only the 2 lost frames are resent. `code/main.py` measures exactly this: run it and compare `frames_transmitted` for the connectionless-unack class (which never retransmits) against the acknowledged classes.

### Service class 3 — Acknowledged connection-oriented

The most reliable service. Source and destination **establish a connection** before any data flows. Every frame is **numbered**; the layer guarantees each frame is received **exactly once, in order, with none lost**. This gives the network layer the equivalent of a reliable bit stream. It suits long, unreliable links — a satellite channel (one-way propagation ≈ 250-280 ms for a geostationary hop) or a long-distance circuit — where a lost ACK under acknowledged-connectionless service could cause a frame to be sent and accepted several times, wasting bandwidth.

It runs in **three distinct phases**:

| Phase | What happens | State created / destroyed |
|---|---|---|
| 1. Establishment | Both sides initialize counters and variables that track which frames have been sent/received | `send_seq=0`, `recv_seq=0`, buffers allocated |
| 2. Transfer | One or more numbered frames flow; each is ACKed; out-of-order or duplicate sequence numbers are detected | Sequence counters advance; retransmit timers run |
| 3. Release | Connection torn down | Variables, buffers, and resources freed |

This is the model behind **HDLC** and **PPP** numbered (reliable) mode, and behind LAPB/LAPD.

### The duplicate-delivery failure mode and sequence numbers

Acknowledgement alone is not enough. Suppose the sender transmits frame, the receiver gets it correctly and sends an ACK, but **the ACK is lost**. The sender's timer expires, so it **retransmits**. The receiver now has the *same frame twice* and, without protection, hands it to the network layer twice — a duplicate.

The fix is **sequence numbers** on outgoing frames. With a one-bit sequence number (alternating 0/1, the Stop-and-Wait / alternating-bit scheme), the receiver remembers the sequence number it expects next; a retransmission carries the *already-delivered* number, so the receiver re-ACKs it but does **not** re-deliver. The simulator models this: with `sequence_numbers=False` you will see the duplicate-delivery count climb whenever an ACK is dropped; with it enabled, `duplicates_suppressed` rises instead and the network layer sees each frame exactly once.

### Decision rule

| If the channel is… | And the traffic is… | Choose | Real protocol |
|---|---|---|---|
| Very reliable (fiber, wired LAN) | Anything | Unacknowledged connectionless | Ethernet 802.3 |
| Very reliable | Real-time (voice/video) | Unacknowledged connectionless | Ethernet 802.3 |
| Unreliable (wireless) | Loss-sensitive bulk | Acknowledged connectionless | Wi-Fi 802.11 |
| Long + unreliable (satellite, long-haul) | Needs ordered exactly-once stream | Acknowledged connection-oriented | HDLC / PPP numbered |

## Build It

`code/main.py` is a single-hop link simulator. It models a lossy channel with a tunable frame-loss and ACK-loss probability and drives a fixed network-layer message through each of the three service classes.

1. Read the `Channel` class — it flips frames to lost using a seeded PRNG so runs are reproducible.
2. Read `ServiceClass` config: `acknowledged` and `sequence_numbers` booleans select the three behaviors.
3. Trace `send_message()` — for each frame it transmits, optionally waits for an ACK, and retransmits on timeout up to a retry cap.
4. Run it: `python3 code/main.py`. Compare the three printed reports.
5. Change `seed`, `frame_loss`, and `ack_loss` at the bottom of `main()` and re-run. Watch how `frames_transmitted` and `duplicates_suppressed` move.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Tell which service a link offers | Presence/absence of ACK and sequence-number fields in a capture | You point to the 802.11 ACK control frame or the bare Ethernet frame and name the class |
| Justify Ethernet vs Wi-Fi choice | Channel BER + traffic type | You connect 1e-12 BER → no link ACK and 1-10% FER → link ACK |
| Diagnose duplicate delivery | App sees the same payload twice; capture shows a retransmit after a lost ACK | You trace it to a lost ACK + missing/short sequence space, not "the network is broken" |
| Predict cost of end-to-end-only recovery | The "10 frames, 2 lost" math | You explain why resending all 10 is far worse than resending 2 |

## Ship It

Produce one artifact under [`outputs/`](../outputs/):

- The simulator's three comparison reports saved as a markdown table, **or**
- A one-page runbook mapping a captured link (Ethernet, Wi-Fi, PPP) to its service class and the evidence that proves it.

Start from [`outputs/prompt-services-provided-to-the-network-layer.md`](../outputs/prompt-services-provided-to-the-network-layer.md) and paste in the simulator output for two different loss settings.

## Exercises

1. Run `code/main.py` with `frame_loss=0.0`. All three classes should deliver every frame; explain why `frames_transmitted` is identical and what that proves about overhead on a clean channel.
2. Set `frame_loss=0.3, ack_loss=0.0`. Compare `frames_transmitted` between the unacknowledged class and the two acknowledged classes. Which network-layer packets would simply be lost forever under the unacknowledged class?
3. Set `ack_loss=0.4` and run the acknowledged-connectionless class with `sequence_numbers=False`, then `True`. Report the `duplicates_delivered` count in each case and explain the alternating-bit mechanism that fixed it.
4. A geostationary satellite link has ~270 ms one-way delay and a 2% frame-error rate. Argue which of the three service classes you'd run on it and why acknowledged-*connectionless* would waste bandwidth here.
5. In a Wireshark capture you see data frames but zero `wlan.fc.type_subtype == 0x1d` ACK frames, yet the link is wireless. Give two hypotheses (capture position vs. service configuration) and the next evidence you'd collect.
6. Your VoIP-over-Wi-Fi call is choppy because the AP retransmits lost voice frames up to 7 times, adding latency. Propose a link-layer setting change and explain the "late data worse than bad data" principle behind it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Unacknowledged connectionless | "Ethernet just sends" | No setup, no ACK, no sequence numbers; corrupted frames are detected by FCS and silently dropped, recovery left to higher layers |
| Acknowledged connectionless | "Wi-Fi confirms each frame" | No logical connection, but every frame is individually ACKed with a retransmit timer; still no ordering guarantee across frames |
| Acknowledged connection-oriented | "Reliable mode" | Three-phase setup/transfer/release with per-frame sequence numbers guaranteeing exactly-once, in-order delivery |
| Acknowledgement | "Proof it arrived" | A link-layer optimization, never a requirement — the network layer can always recover end-to-end, just slower |
| Sequence number | "A counter" | The mechanism that lets a receiver tell a retransmission from an original and suppress duplicate delivery |
| Virtual data path | "The two layers talk" | The convenient fiction that peer layers communicate directly; the real path goes down to the physical layer and back |
| FCS / CRC-32 | "The error check" | A 4-byte trailer that *detects* corruption so a bad frame is discarded; it does not *correct* or recover it |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 3, Section 3.1.1 (Services Provided to the Network Layer) and 3.1.3 (Error Control).
- **IEEE 802.3** — Ethernet, the canonical unacknowledged connectionless data-link service.
- **IEEE 802.11** — Wireless LAN; see the ACK control frame and the DCF retransmission procedure for acknowledged connectionless service.
- **RFC 1662** — PPP in HDLC-like Framing.
- **RFC 1661** — The Point-to-Point Protocol (PPP).
- **ISO/IEC 13239** — HDLC (High-level Data Link Control) procedures, the basis of connection-oriented numbered-mode link service.
- **RFC 793 / RFC 9293** — TCP, for the end-to-end recovery that the network/transport layers fall back on when the link layer offers no acknowledgement.
