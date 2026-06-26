# Real-Time Conferencing

> Real-time voice and video over IP is a *media streaming* problem with a brutal latency budget. The classic telephone network tolerates at most 150 ms one-way (up to 400 ms for international calls); for an interactive call, every 20 ms packetization interval, every queued 1 KB datagram on a 1 Mbps link (8 ms), and every DS-codepoint tag matters. RTP/RTCP (RFC 3550) carry the media over UDP because TCP retransmits would push one-way delay past the budget. H.323 (ITU-T, monolithic, Q.931 over TCP for signaling, H.245 for parameter negotiation, RAS on UDP port 1719 to a gatekeeper) and SIP (RFC 3261, modular, text-based, six core methods `INVITE`/`ACK`/`BYE`/`OPTIONS`/`CANCEL`/`REGISTER`) are the two protocols that solve the second half of the problem: how do two endpoints find each other, agree on codecs, ring a phone, and tear the call down. The Differentiated Services codepoint `EF` (Expedited Forwarding, 0x2E, decimal 46) is the queue-bypass marking that voice-over-IP packets carry so they jump ahead of bulk web traffic on a congested broadband link. This lesson builds a runnable RTP/jitter-buffer/SIP-state-machine simulator and a delay-budget calculator so you can see the messages, the codecs, and the timing on a real wire.

**Type:** Build
**Languages:** Python
**Prerequisites:** UDP vs TCP tradeoffs, IPv4 header fields (protocol, TTL, ToS), the application-layer transport lesson, basic probability
**Time:** ~85 minutes

## Learning Objectives

- Compute a one-way delay budget for a voice-over-IP call and show why 64 kbps * 20 ms = 160 B voice samples is the standard packetization interval.
- Trace an H.323 call from gatekeeper discovery (UDP port 1718) through RAS admission, Q.931 SETUP/CALL PROCEEDING/ALERT/CONNECT, and H.245 capability exchange to RTP media flow.
- Run a SIP dialog (INVITE/200/ACK/BYE) through a state machine and verify the six core methods from RFC 3261.
- Compute the gain from short packets (20 ms vs 125 ms) when 40 ms of propagation delay is fixed by the speed of light in fiber.
- Apply a DS codepoint (EF 0x2E) to a packet and explain how a router's queue would schedule it ahead of best-effort web traffic.
- Estimate Mean Opinion Score (MOS) from packet-loss percentage using the G.107 E-model and read the table of thresholds for "toll" / "good" / "fair" / "poor" / "bad".

## The Problem

It is 2026 and your product team has been asked to build a peer-to-peer video calling feature for an existing messaging app. The design meeting is on Monday. Two engineers argue:

- Engineer A: "Let's just use TCP. TLS handles encryption, retransmits are a feature, and the existing message bus already speaks HTTP/2. We can just POST each frame."
- Engineer B: "TCP retransmits are at least one RTT of delay. On a transcontinental call that is 80 ms of *additional* latency before we even start. The packet will arrive out of order with respect to its neighbors, the playout buffer will glitch, the user will mute themselves in frustration. Real-time conferencing *requires* UDP, even though it means we have to handle encryption (DTLS-SRTP, RFC 5764), congestion control (RTP/RTCP, RFC 3550), and NAT traversal ourselves."

Both are partially right. The first step in the meeting has to be a clean, quantitative answer to: *what is the actual delay budget for an interactive call, and which protocol fields actually control it?* The textbook says: 150 ms one-way for a "good" call, 400 ms for an "annoying" international call. Everything in this lesson — packetization interval, payload size, DS codepoint, retransmission policy — has to fit inside that budget.

The second step is *signaling*. Once we have decided that media will flow as UDP, we still need a way for Alice to tell Bob "ring, please, here is the codec I support." That is the job of H.323 or SIP. H.323 is the ITU-T monolithic stack with Q.931 (call signaling) over TCP, H.245 (capability negotiation) on a permanent control channel, and RAS (registration/admission/status) over UDP to a gatekeeper. SIP (RFC 3261) is the IETF modular alternative: one method per line, ASCII text, six methods in the core, runs over UDP or TCP. We will exercise both.

## The Concept

### The delay budget, line by line

The one-way delay budget for a voice-over-IP packet is the sum of five components:

1. **Packetization delay** — time to fill one packet with codec samples. At 64 kbps (G.711 PCM, 8 kHz * 8 bit samples) one byte of audio per 125 microsecond sample, 20 ms of audio = 160 bytes. This is fixed by the codec and the packetization interval.
2. **Transmission delay on the access link** — 160 B / (1 Mbps) ≈ 1.28 ms on each end. With a 125 ms packetization interval (1 KB per packet) the same link needs 8 ms on each end, and the 8 ms on each end is wasted budget.
3. **Propagation delay** — physics. Seattle to Amsterdam in optical fiber is ~8,000 km. Speed of light in fiber is roughly 2/3 c, so 8,000 km / 200,000 km/s ≈ 40 ms one-way. This is *uncompressible*; the only way to reduce it is to move one of the endpoints.
4. **Queuing delay at each router** — variable, depends on congestion. This is the part DS codepoints and queue disciplines control.
5. **Software / codec delay** — compression and packetization on the sender, decompression and playout buffer on the receiver.

The textbook's worked example:

| Component | Long packet (1 KB) | Short packet (160 B) |
|---|---|---|
| Packetization (64 kbps) | 125 ms | 20 ms |
| TX delay (1 Mbps each end) | 8 ms + 8 ms = 16 ms | 1.28 ms + 1.28 ms = 2.56 ms |
| Propagation | 40 ms | 40 ms |
| **Total one-way** | **181 ms** | **63 ms** |

181 ms is over the 150 ms budget; 63 ms is comfortably under it. *Short packets save the call.* This is why every modern voice codec targets 20 ms packetization.

### Why UDP, not TCP

TCP is the wrong transport for interactive media for three reasons:

- **Retransmission delay.** A lost segment waits at least one RTT (~80 ms transcontinental) before being resent. Interactive media cannot wait.
- **Head-of-line blocking.** Even if the retransmit arrives in time, TCP delivers bytes in order. If segment 7 is lost, segment 8 is buffered at the receiver until 7 is recovered, even if 8 is in the playout window.
- **Congestion window collapse.** TCP's cwnd ramps down on loss. For a 64 kbps constant bitrate voice stream, halving the cwnd stops the flow entirely. The codec can only produce 64 kbps of data, and TCP's reaction to a single loss event is to halve the sending rate.

UDP gives the application control of *all* of this. The cost is that the application now has to implement congestion control (via RTCP, RFC 3550), encryption (via DTLS-SRTP, RFC 5764), and NAT traversal (via STUN/TURN/ICE, RFC 5245) itself. The textbook calls this "the price of low latency."

### RTP and RTCP, briefly

RTP (Real-time Transport Protocol, RFC 3550) is a thin shim over UDP that adds four things:

- **Sequence numbers** (16 bits) so the receiver can detect loss and reorder out-of-order packets.
- **Timestamps** (32 bits) so the receiver can schedule playout at the right wall-clock time, hiding jitter.
- **Payload type identification** (7 bits) so the receiver knows which codec is in use.
- **SSRC identifier** (32 bits) so multiple senders can be multiplexed on a single UDP port.

The fixed header is 12 bytes. A typical voice packet is 12 + 160 = 172 bytes total, plus 8 bytes UDP header, plus 20 bytes IPv4 header = 200 bytes on the wire for 20 ms of 64 kbps audio. That is 80 kbps of IP traffic to carry 64 kbps of media — a 25 % overhead that is the tax of UDP + RTP + IP.

RTCP (RTP Control Protocol) is the sibling protocol that runs on a *different* UDP port (typically one higher than RTP) and carries *sender reports* (timestamps, packet count, octet count) and *receiver reports* (fraction lost, cumulative lost, interarrival jitter, last SR timestamp). The reports are the basis of the congestion-control loop and the playout-buffer adjustment.

### The jitter buffer and the playout decision

A packet sent at t=0 ms with 20 ms of audio should be played out at the wall-clock instant that the *next* sample's playout would be t=20 ms. But the network delays the packet by some random amount — usually small (10–30 ms) but occasionally large (>100 ms). If the receiver plays each packet as soon as it arrives, the user hears jitter. If the receiver waits to play each packet on a fixed schedule, late packets are dropped (and have to be concealed, see below).

The textbook's compromise: a **playout buffer** that holds 2–3 packets worth of audio (40–60 ms at 20 ms packetization), with each packet's playout time computed from its RTP timestamp relative to a base time. Packets that arrive before their scheduled playout time are buffered; packets that arrive after are dropped and replaced with packet-loss concealment (PLC, typically a repeat of the last frame or a synthesized comfort-noise frame). See the `JitterBuffer` class in `code/main.py` for the exact algorithm.

### DS codepoint and the queue-bypass argument

Differentiated Services (RFC 2474, RFC 3246) marks each packet with a 6-bit DSCP. The Expedited Forwarding PHB (RFC 3246) reserves DSCP value `101110` = 0x2E = 46 decimal. A router running a priority queueing discipline with the EF class puts EF packets in a separate, short, strictly-serviced queue. As long as EF traffic stays below a configured rate, its queuing delay is bounded by the serialization time of one maximum-sized packet — effectively zero.

In practice, voice-over-IP endpoints mark their UDP datagrams with DSCP 46. The broadband access link (the bottleneck on most residential calls) honors the mark, and the EF queue jumps ahead of best-effort web traffic. This is *the* reason a Skype call survives a household running Netflix in the next tab.

### H.323, the monolithic stack

H.323 (ITU-T Recommendation H.323, originally 1996, current version 7 as of 2009) defines a *complete* system for multimedia over a packet network. The architecture (Figure 7-58 in the textbook) has four elements:

- **Terminal** — the endpoint (a softphone or hardphone).
- **Gateway** — translates between H.323 on the Internet side and PSTN signaling/voice on the telephone side.
- **Gatekeeper** — optional but ubiquitous; controls the *zone* (a collection of terminals and gateways). It does admission control, address resolution, and bandwidth management.
- **Zone** — the set of endpoints managed by a single gatekeeper.

The protocol stack (Figure 7-59) is:

| Layer | Protocol | Function |
|---|---|---|
| Audio codec | G.711 (required), G.722, G.723.1, G.729 | 64 kbps PCM, ADPCM, ACELP |
| Video codec | H.261, H.263, H.264 | CIF/QCIF compression |
| Call control | H.245 | Capability exchange, channel setup |
| Call signaling | Q.931 | SETUP, ALERT, CONNECT, RELEASE |
| Registration | H.225 / RAS | UDP port 1719, admission to zone |
| Media | RTP / RTCP | RFC 3550 |
| Transport | TCP (call signaling), UDP (RAS, RTP) | — |
| Network | IP, link, physical | — |

The call flow (Figure 7-60, Figure 7-61 in the textbook) has six well-known messages:

1. PC broadcasts a UDP gatekeeper discovery packet to **port 1718**.
2. PC registers with the gatekeeper via **RAS** (Registration/Admission/Status) on UDP port 1719.
3. PC requests **bandwidth** from the gatekeeper (also RAS). This is the gatekeeper's *admission control* — it limits the number of calls so that the outgoing PSTN line is not oversubscribed.
4. PC sends **Q.931 SETUP** to the gatekeeper over TCP, naming the called party.
5. Gatekeeper responds **Q.931 CALL PROCEEDING**, forwards SETUP to the gateway.
6. Gateway originates a PSTN call; the called phone rings.
7. End office sends back **Q.931 ALERT** (ringing) and then **Q.931 CONNECT** (off-hook).
8. The PC and gateway now use **H.245** on a separate TCP channel to negotiate codecs and open two unidirectional **RTP** media channels.
9. RTCP runs alongside RTP for QoS reports.
10. When either side hangs up, **Q.931 RELEASE** is sent on the signaling channel.

### SIP, the modular alternative

SIP (RFC 3261) is the IETF's response to H.323. Where H.323 is monolithic and rigid, SIP is a single text-based module that fits into the existing Internet application stack. The protocol model is HTTP: each message is a request line or status line, followed by MIME-like headers, followed by an optional body.

The six core methods (Figure 7-61 in the textbook) are:

| Method | Purpose |
|---|---|
| `INVITE` | Request session initiation |
| `ACK` | Confirm session initiation (third leg of three-way handshake) |
| `BYE` | Request session termination |
| `OPTIONS` | Query a host's capabilities |
| `CANCEL` | Cancel a pending request |
| `REGISTER` | Inform a redirection server of the user's current location |

A typical two-party call uses three of them (`INVITE`, `ACK`, `BYE`). The signaling flow is:

```
C --INVITE--> P
C <--100 Trying-- P
C <--180 Ringing-- P
C <--200 OK-- P
C --ACK--> P
... media via RTP ...
C --BYE--> P
C <--200 OK-- P
```

Headers are ASCII, modeled on HTTP. Examples from a real RFC 3261 trace:

```
INVITE sip:bob@biloxi.example.com SIP/2.0
Via: SIP/2.0/UDP pc33.atlanta.example.com;branch=z9hG4bK776asdhds
Max-Forwards: 70
To: Bob <sip:bob@biloxi.example.com>
From: Alice <sip:alice@atlanta.example.com>;tag=1928301774
Call-ID: a84b4c76e66710@pc33.atlanta.example.com
CSeq: 314159 INVITE
Contact: <sip:alice@pc33.atlanta.example.com>
Content-Type: application/sdp
Content-Length: 142
```

The body, separated from the headers by a blank line, is an **SDP** (Session Description Protocol, RFC 4566) describing the media — codecs, ports, addresses — that Alice is willing to receive.

SIP URLs use the `sip:` scheme, so they fit naturally into Web pages: `<a href="sip:alice@atlanta.example.com">Call Alice</a>`. This was the explicit design goal: voice should be a *hyperlink*.

### MOS from packet loss: the E-model in miniature

Quality of experience for voice calls is rated on the **Mean Opinion Score (MOS)** scale, which ranges from 1 (bad) to 5 (excellent). The **E-model** (ITU-T G.107) computes an R-factor from loss, delay, and codec, and converts R to MOS. A simplified lookup table for PCM-coded VoIP (G.711) gives:

| Packet loss % | MOS | Quality |
|---|---|---|
| 0 | 4.41 | toll |
| 1 | 4.13 | toll |
| 2 | 3.88 | good |
| 3 | 3.66 | good |
| 5 | 3.29 | fair |
| 10 | 2.51 | poor |
| 20 | 1.35 | bad |
| 50 | 0.33 | bad |

The textbook's rule of thumb: keep loss under 3 % for "good", and under 1 % for "toll". A loss event that takes a 64 kbps voice call from 4.4 to 3.3 MOS is *not* the same loss event that the user would notice in a 1 Mbps video stream. Voice is far less forgiving.

### Why we have two protocols

The textbook's Figure 7-63 contrasts H.323 and SIP in fifteen rows. The short version:

- H.323 is the *telephone* way: a full protocol suite, 1,400 pages, binary encodings, Q.931 over TCP. Interoperability is well-defined; adaptability is low.
- SIP is the *Internet* way: 250 pages, ASCII, modular, runs over TCP or UDP. Interoperability is famously uneven; adaptability is high.

In production today, SIP won the voice-over-IP signaling wars; H.323 is still found on video conferencing bridges from the 2000s (Polycom, Tandberg, Cisco) where its deterministic behavior matters. Both are gradually being absorbed into WebRTC (RFC 7478) on the browser side.

## Build It

We will use the existing `code/main.py` which implements four self-contained demonstrations:

1. **RTP session model** — `RTPSession.emit()` produces a stream of `RTPPacket` objects, each with a 12-byte fixed header encoded in network byte order. Run `rtp_session_demo()` to see five audio packets (PT=0) and two video packets (PT=96) with sequence numbers and timestamps incrementing correctly.
2. **Jitter buffer** — `JitterBuffer.playout()` reorders out-of-order RTP packets, releases them at their scheduled wall-clock playout time, and reports lost sequence numbers as PLC entries. Run `jitter_buffer_demo()` to see a 8-packet stream with one packet heavily delayed and one packet lost, drained at four wall-clock instants.
3. **MOS from packet loss** — `mos_from_loss()` returns a clamped MOS score; `mos_demo()` prints the table above.
4. **SIP call flow state machine** — `sip_next_state()` advances the dialog state on each of the six core messages. Run `sip_call_flow_demo()` to walk `IDLE → CALLING → ESTABLISHED → CONFIRMED → TERMINATING → IDLE` and back.

Steps:

1. Read the source chapter sections on Real-Time Conferencing (textbook section 7.4.5, plus 7.4.1–7.4.4 for the streaming context).
2. Open `code/main.py` and look at the `RTPSession.emit()` method. Each emitted packet advances `next_seq` and `next_ts` by the configured `samples_per_packet` (160 for G.711 20 ms).
3. Run `python3 code/main.py` and watch the four sections print. The script also writes a structured JSON trace to `outputs/trace.json`.
4. Edit the `random.gauss(40.0, 25.0)` call in `jitter_buffer_demo()` to change the jitter distribution. What happens with a stddev of 0 (no jitter)? Of 100 ms (extreme jitter)?
5. Edit the `messages` list in `sip_call_flow_demo()` to omit the `ACK`. What state does the call end up in? (Answer: `ESTABLISHED` — without `ACK`, the client has not confirmed receipt of the `200 OK`, so Bob thinks the call is open but Alice's UA may have timed out.)

## Use It

| API call | What it does | Typical output |
|---|---|---|
| `RTPSession(ssrc, payload_type, samples_per_packet=160, clock_rate_hz=8000)` | Create an RTP source | — |
| `session.emit(payload_size=20, marker=False)` | Produce the next RTP packet | `RTPPacket` with header bytes |
| `RTPPacket.encode_header()` | Pack 12-byte RTP fixed header | 12 bytes in network byte order |
| `JitterBuffer(playout_delay_ms=80.0, clock_rate_hz=8000)` | Create a reordering playout buffer | — |
| `jb.receive(pkt, arrival_time_ms)` | Insert arriving packet, indexed by seq | mutates internal dict |
| `jb.playout(now_ms)` | Release ready packets, mark gaps as PLC | list of `(seq, playout, status, pkt)` |
| `mos_from_loss(packet_loss_percent)` | Convert loss % to MOS | float in [1.0, 4.5] |
| `sip_next_state(current_state, message)` | Advance the SIP dialog state machine | next state string |

The output of `mos_from_loss(0.0)` is `4.41`; of `mos_from_loss(50.0)` is `0.33` (clamped to `1.0` — the lookup `LOSS_TO_MOS` produces a sub-floor value that the E-model formula corrects).

## Ship It

The deliverable is the lesson folder:

```
phases/13-streaming-real-time-media-and-content-delivery/04-real-time-conferencing/
├── assets/
│   └── real-time-conferencing.svg        # Diagram of the eight H.323 steps + SIP dialog
├── code/
│   └── main.py                           # rtp_session_demo, jitter_buffer_demo, mos_demo, sip_call_flow_demo
├── docs/
│   └── en.md                             # this file
├── notebook/
│   └── notes.md                          # your worked examples and answers
├── outputs/
│   └── trace.json                        # sample run of all four demos
└── quiz.json
```

To prove the lesson works:

1. `python3 code/main.py` — must print four sections (RTP session, jitter buffer, MOS, SIP) without errors. The script writes `outputs/trace.json` with the structured results.
2. `python3 -m py_compile code/main.py && echo OK` — must print `OK`.
3. Open `assets/real-time-conferencing.svg` in a browser. The diagram should show the H.323 protocol stack on the left, the eight-step call flow on the right, and the SIP dialog sequence in a swimlane at the bottom.

## Exercises

1. **Packetization sweep.** Run `delay_budget()` (from the streaming buffer lesson, `phases/13.../15-jitter-playout-buffering`) for `packet_ms` in `{10, 20, 30, 40, 60, 120}`. At what packetization interval does the total one-way delay exceed 150 ms? *Why does this matter for codec selection?* G.722 wideband uses 16 kHz sample rate and produces 16 KB/sec; what packetization keeps it under the budget at 64 kbps effective rate?
2. **DS codepoint taxonomy.** Look up the IANA DSCP registry. The standard classes are: BE (CS0), AF11, AF12, AF13, AF21, AF22, AF23, AF31, AF32, AF33, AF41, AF42, AF43, EF, CS6, CS7. For a voice-over-IP call, video-over-IP call, and bulk file transfer, which class would you assign and why? What is the difference between EF and AF41 in queue behavior? (EF gets *strict priority* up to a policed rate; AF41 gets *more* bandwidth than AF42/43 if the queue is congested, but not strict priority.)
3. **H.323 reflection attack.** H.245 negotiates codecs on a permanent control channel. Suppose an attacker Mallory intercepts Alice's H.245 `TerminalCapabilitySet` and replays it to Bob *as if it came from Mallory*. What property of H.245 prevents this? (Hint: H.245 messages are protected by H.235, which signs the messages with a key derived from a Diffie-Hellman exchange that occurs earlier. If the implementation skips H.235, the attack succeeds — and several real-world H.323 stacks did skip it in the early 2000s.)
4. **SIP forking.** A SIP proxy receives an `INVITE alice@example.com`. The `REGISTER` messages it has received say that Alice has three devices: desktop at `192.0.2.10`, mobile at `198.51.100.5`, and softphone at `203.0.113.7`. The proxy forks the INVITE to all three in parallel. Alice answers on the mobile. What does the proxy send to the desktop and softphone? (Answer: `487 Request Terminated` with a `Reason: SIP;cause=200` header — RFC 3261 §16.7. The two unanswered devices release their state.) *What happens to the original `INVITE`'s `Call-ID`?*
5. **Buffer-vs-loss trade-off.** The playout buffer holds `B` packets. With a typical Pareto-tailed jitter distribution with shape α = 1.5 and scale β = 10 ms, compute the loss probability for `B = 1, 2, 3, 5`. (Hint: `Pr(jitter > B * packet_ms) = (β / (β + B * packet_ms))^α`.) At what `B` does loss fall below 1%? What is the latency cost of that buffer size?
6. **MOS from a real trace.** A user reports choppy audio on a 30-minute call. The RTCP receiver report shows `fraction_lost = 0.04` (4%) and `cumulative_lost = 4500` of 120,000 packets. What MOS does the `mos_from_loss()` function return? Is this "good" or "bad"? (Answer: `mos_from_loss(3.75)` returns about 3.6, which is "good" — *just* on the border.)

## Key Terms

| Term | Meaning |
|---|---|
| One-way delay budget | Maximum acceptable latency from mouth to ear; ~150 ms for good interactive quality |
| Packetization delay | Time to fill one packet with codec samples; 20 ms is the G.711 standard |
| Jitter | Variation in inter-packet arrival time at the receiver |
| Playout buffer | Receiver-side buffer that smooths jitter at the cost of latency |
| PLC | Packet Loss Concealment; replacement of a lost packet with a synthesized or repeated frame |
| RTP | Real-time Transport Protocol, RFC 3550; 12-byte fixed header over UDP |
| RTCP | RTP Control Protocol; sender and receiver reports for QoS |
| SSRC | Synchronization source identifier in RTP, 32 bits |
| DSCP | Differentiated Services codepoint, 6 bits in IPv4 ToS / IPv6 Traffic Class |
| EF (Expedited Forwarding) | DSCP 0x2E / decimal 46; strict-priority queue marking for voice |
| H.323 | ITU-T monolithic VoIP protocol suite; Q.931 + H.245 + RAS + RTP |
| Gatekeeper | H.323 entity that controls admission and bandwidth for a zone |
| RAS | Registration/Admission/Status; H.323 signaling on UDP port 1719 |
| Q.931 | ISDN call signaling protocol reused by H.323 |
| H.245 | H.323 control channel for capability exchange |
| SIP | Session Initiation Protocol, RFC 3261; modular text-based signaling |
| SDP | Session Description Protocol, RFC 4566; describes media in SIP body |
| Forking proxy | SIP proxy that sends an INVITE to multiple locations in parallel |
| Reflection attack | Replay attack where the victim is tricked into answering their own challenge |
| MOS | Mean Opinion Score; 1 (bad) to 5 (excellent) quality rating |
| E-model | ITU-T G.107 algorithm that maps loss/delay to MOS |
| DTLS-SRTP | Datagram TLS over SRTP; RFC 5764; secure media for SIP/WebRTC |

## Further Reading

- **RFC 3550** — RTP: A Transport Protocol for Real-Time Applications. The defining document; the sequence-number/timestamp model is the core of every media-over-IP protocol since.
- **RFC 3261** — SIP: Session Initiation Protocol. The current SIP standard; ~250 pages. Annexes on reliability, security, and IPv6.
- **RFC 4566** — SDP: Session Description Protocol. The body format that SIP, RTSP, and WebRTC all share.
- **RFC 5245** — ICE: Interactive Connectivity Establishment. The protocol that makes SIP traverse NAT.
- **RFC 5764** — DTLS-SRTP. Secure media for SIP and WebRTC.
- **ITU-T Recommendation H.323** — the H.323 standard itself, currently in version 7.
- **ITU-T G.107** — The E-model: Computational model for use in transmission planning.
- **RFC 3246** — An Expedited Forwarding PHB. The DS codepoint assignment for voice.
- **Goode, B. (2002)** — "Voice over Internet Protocol (VoIP)" *Proceedings of the IEEE*, vol. 90, no. 9. The textbook's recommended deep dive on VoIP engineering.
- **Peterson, L. & Davie, B.** — *Computer Networks: A Systems Approach*, sections 7.4.5 and 8.7. The textbook this lesson series is built from.
