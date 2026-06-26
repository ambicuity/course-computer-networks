# Real-Time Transport: RTP and RTCP

> The Real-time Transport Protocol (RTP) and its control sibling RTCP are the de facto standard for carrying real-time media (voice, video, telemetry) over IP networks. RFC 3550 (2003, replacing RFC 1889) defines RTP as an *application-layer* protocol: a thin framing layer on top of UDP that gives each media packet a sequence number, a timestamp, a synchronization source identifier (SSRC), and a payload type. RFC 3550 also defines RTCP, the periodic out-of-band control channel that carries sender/receiver reports so the participants can measure round-trip time, packet loss, jitter, and inter-arrival skew. RTP is *intentionally* not a transport: it does not retransmit lost packets, does not reserve bandwidth, and does not guarantee delivery. The expectation is that audio and video decoders can absorb loss and reorder, and the application will use the RTCP reports to adapt codec bitrate, FEC, or jitter-buffer depth. This lesson walks the 12-byte RTP header, the 24-byte SR/RR report blocks, the canonical AV profile (RFC 3551) for audio/video payload types, and a stdlib-only parser/generator that decodes a captured packet and prints every field.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 10 lesson 14 (UDP) and 15 (XDR); familiarity with audio/video codecs and the concept of jitter buffers
**Time:** ~70 minutes

## Learning Objectives

- Lay out the 12-byte RTP header bit-by-bit (V, P, X, CC, M, PT, sequence number, timestamp, SSRC, CSRC list) and decode a real packet from Wireshark.
- Distinguish the five payload classes — audio, video, text, application, other (RFC 5761) — and identify the canonical payload types from RFC 3551.
- Read an RTCP **Sender Report (SR)** and a **Receiver Report (RR)** block, extract the NTP/RTP timestamp pair, the packet/octet counts, and the eight-block fraction-lost/cumulative-loss/jitter/LSR/DLSR fields.
- Explain why RTP's sequence number is 16 bits and unsigned (wrap-around handling matters) and why the RTP timestamp is 32 bits at a media clock (e.g. 90 kHz for many video codecs, 8 kHz for G.711 audio).
- Build a tiny RTP sender that emits one packet per call (with header + payload), and a parser that decodes a hex string into the named fields and computes jitter using the RFC 3550 formula.

## The Problem

A junior engineer joins a WebRTC project. They see `rtp` packets in Wireshark with mysterious numbers — sequence numbers increasing by 1, then suddenly jumping by tens of thousands, and a "jitter" field in RTCP that doesn't match anything they can measure. They write a custom UDP sender for an audio stream and the receiver drops half the packets. The bug: they were using a single timestamp base for every packet, so the jitter buffer on the receiver thought all packets were simultaneous. The fix is to use the *media clock* (8 kHz for narrowband audio, 90 kHz for most video) and the *RTP timestamp* (32 bits, monotonically increasing per packet) for jitter calculations, and the *sequence number* (16 bits, just incrementing) only for loss and reorder detection.

RTP is small, but its design choices are deeply tied to the *application* assumptions. Read the spec wrong and your jitter buffer misbehaves; read the timestamps wrong and your lip-sync drifts. The lesson is a hands-on tour of every byte.

## The Concept

RTP sits in a small stack: application generates media frames, RTP frames each one, UDP carries it, IP delivers it. RTCP is a *parallel* UDP stream that carries statistics. The SVG shows the header layout and the SR/RR report block; `code/main.py` parses both.

### The 12-byte RTP header (RFC 3550 §5.1)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M|     PT      |       sequence number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           timestamp                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           synchronization source (SSRC) identifier            |
+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+
|            contributing source (CSRC) identifiers             |
|                             ....                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       header extension (optional)             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       payload (variable)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Bits | Meaning |
|---|---|---|
| V (version) | 2 | Always 2 for RFC 3550 |
| P (padding) | 1 | Set if the payload ends in one or more padding octets (last byte = count) |
| X (extension) | 1 | Set if a header extension follows the CSRC list |
| CC (CSRC count) | 4 | Number of CSRC identifiers after the SSRC, 0-15 |
| M (marker) | 1 | Application-defined; for video, marks the last packet of a frame; for audio, marks talk spurt start |
| PT (payload type) | 7 | Identifies the codec (RFC 3551, RFC 5761, dynamic) |
| Sequence number | 16 | Increments by 1 per packet; used for loss/reorder detection |
| Timestamp | 32 | Media clock ticks at the time of the *first* sample in the packet |
| SSRC | 32 | Random source identifier; identifies the participant |
| CSRC list | 32 each, 0-15 | Contributing sources (e.g. mixers include their inputs) |
| Extension | variable | RFC 3550 §5.3.1; first word = profile, second = length, then data |

The total fixed header is 12 bytes; with N CSRC entries it is 12 + 4*N bytes. Extensions are 4-byte aligned.

### Sequence number vs timestamp: they measure different things

- **Sequence number** increments by 1 per RTP packet. It detects loss and reorder. Wrap-around at 65535 → 0 is *expected*; the receiver uses sequence-number arithmetic that handles wrap (RFC 1984 "Serial number arithmetic").
- **Timestamp** is in units of the *media clock*: 8000 Hz for narrowband audio, 90000 Hz for most video (H.264, VP8, VP9), 48000 Hz for Opus. It tells the receiver *when* in the media stream this packet belongs. Wrap-around at 2^32 is also handled; for 90 kHz that's ~13.25 hours of continuous media.

A common bug: setting the timestamp to wall-clock time. That breaks the jitter formula. Another common bug: using the same timestamp for every packet in a frame; that breaks the jitter buffer.

### Payload types and the AV profile (RFC 3551)

Static payload types are 0-95; dynamic (negotiated via SDP) are 96-127. The AV profile's static audio mappings:

| PT | Codec | Clock (Hz) | Channels | Notes |
|---|---|---|---|---|
| 0 | PCMU (G.711 mu-law) | 8000 | 1 | North American PSTN |
| 3 | GSM 06.10 | 8000 | 1 | 13 kbps |
| 8 | PCMA (G.711 A-law) | 8000 | 1 | European PSTN |
| 9 | G.722 | 8000 | 1 | 64 kbps, 16 kHz sample rate |
| 11 | L16 (linear 16-bit) | 44100 | 2 | High quality |
| 14 | MPA (MPEG-1/2 audio) | 90000 | 1/2 | 32-256 kbps |
| 34 | H.263 | 90000 | n/a | Video, first version |
| 96-127 | dynamic | any | any | SDP `rtpmap:` maps them to a codec |

### RTCP packet types (RFC 3550 §6)

RTCP uses the *same* numeric range as RTP for its first byte: PT 200 = SR, 201 = RR, 202 = SDES, 203 = BYE, 204 = APP. The RTCP stream is itself a sequence of RTCP packets, one or more per UDP datagram, distinguished by length and PT.

| PT | Name | What it carries |
|---|---|---|
| 200 | SR (Sender Report) | Sender stats + reception report blocks for up to 31 sources |
| 201 | RR (Receiver Report) | Reception report blocks for up to 31 sources |
| 202 | SDES | Source Description: CNAME, NAME, EMAIL, PHONE, LOC, TOOL, NOTE, PRIV |
| 203 | BYE | End of participation |
| 204 | APP | Application-defined |

The minimum RTCP interval is 5 seconds; the *bandwidth budget* is 5% of session bandwidth. With many participants, the interval grows so that the RTCP traffic stays within budget.

### The Sender Report (SR) packet (RFC 3550 §6.4.1)

28 bytes fixed + zero or more reception report blocks (24 bytes each):

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|    RC   |   PT=200=SR   |             length            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         SSRC of sender                        |
+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+=+
|              NTP timestamp (most significant word)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|             NTP timestamp (least significant word)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         RTP timestamp                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     sender's packet count                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      sender's octet count                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  report block 1 (24 bytes)                    |
|                             ....                              |
|                  report block RC (24 bytes)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

The NTP timestamp is a 64-bit value: 32 bits of seconds since 1900-01-01, 32 bits of fraction. The RTP timestamp is in the *same* media-clock base as the RTP packets. The pair allows a receiver to map RTP time to wall time for inter-stream synchronization (lip-sync).

### The reception report block (24 bytes, RFC 3550 §6.4.1)

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 SSRC_1 (SSRC of first source)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| fraction lost |       cumulative number of packets lost       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           extended highest sequence number received           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      interarrival jitter                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         last SR (LSR)                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    delay since last SR (DLSR)                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Fraction lost**: 8-bit fraction of packets lost in the last report interval (0-255 = 0-100%).
- **Cumulative lost**: 24-bit signed total loss since session start.
- **Extended highest sequence**: 16-bit low bits + 16-bit cycle count, so wrap-around is detected.
- **Jitter**: RFC 3550 §6.4.1 formula `J = J + (|D(i-1,i)| - J) / 16` where D is the transit-time difference between consecutive packets.
- **LSR**: middle 32 bits of the most recent SR's NTP timestamp.
- **DLSR**: delay since last SR, in 1/65536 second units.

The LSR + DLSR pair lets a sender compute the round-trip time to a receiver: `RTT = (now - LSR - DLSR)` in the same NTP units.

### Why RTP is not a transport, and why that is the right design

TCP-style retransmission would *delay* late packets until after their playout deadline — useless for live audio. RTP's "send and forget" matches the media reality: if a frame is lost, the next frame is *now*. The decoders' job is to interpolate, repeat, or freeze; the application's job is to watch the RTCP RR blocks, compute the loss rate, and back off the codec bitrate (or add FEC) when the loss rate exceeds the codec's tolerance. The transport is a *feedback* loop, not a guarantee.

## Build It

`code/main.py` is a stdlib-only RTP/RTCP toolkit with four parts.

1. **`build_rtp(pt, seq, ts, ssrc, payload, marker=False, csrc=[])`** — assembles a 12-byte RTP header (plus CSRCs) and returns the full packet hex.
2. **`parse_rtp(data)`** — decodes a byte string into named fields, validates V=2 and computes the number of CSRC entries.
3. **`build_sr(ssrc, ntp_ts, rtp_ts, packets, octets, reports)`** and **`parse_sr(data)`** — produce and consume a Sender Report, including reception report blocks.
4. **Jitter calculator** — accepts a stream of (seq, rtp_ts, arrival_us) tuples and computes the RFC 3550 jitter using the canonical formula.

Run `python3 code/main.py`. The demo builds an audio packet (PT=0), a video packet (PT=96 dynamic), and a Sender Report, then parses each back and verifies the round-trip.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Decode a packet from Wireshark | Hex bytes | You read V, P, X, CC, M, PT, seq, ts, SSRC correctly |
| Choose a payload type | Audio vs video | Audio: PT 0-23 (RFC 3551 static); video: PT 96-127 (SDP dynamic) |
| Read an RTCP SR | NTP + RTP timestamp pair | You can map RTP time to wall time for lip-sync |
| Compute jitter | RFC 3550 formula | `J = J + (|D| - J) / 16`; values are in media-clock units |
| Compute RTT | LSR + DLSR | `RTT = now - LSR - DLSR` in 1/65536 s |

Wireshark filter for a single RTP stream: `rtp && rtp.ssrc == 0x12345678`. For RTCP: `rtcp`. Right-click → Follow UDP stream to see the parallel control channel.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **RTP header cheat sheet** with the 12-byte layout, the CSRC rule, and the marker-bit conventions per codec.
- A **jitter and RTT cookbook** — the formulas, the units, and a worked example.
- An **RTCP report block decoder card** with the 8 fields and their meanings.
- The **lab code** (`code/main.py`) wired to your own capture.

Start from `outputs/prompt-real-time-transport-rtp-and-rtcp.md`.

## Exercises

1. Build an RTP packet for G.711 mu-law audio, 160 samples (20 ms at 8 kHz), SSRC=0xDEADBEEF, sequence=1, timestamp=0. What is the total packet size?
2. Capture an RTP packet from `rtp.pt == 96` and decode it. What is the dynamic payload type mapping (look in the SDP)?
3. Receive two RTP packets with timestamps 0 and 160 at arrival times 1,000,000 us and 1,020,000 us, both at 8 kHz clock. What is the jitter after the second packet?
4. Build a Sender Report with NTP=0xE000_0000_0000_0000, RTP=0, packets=100, octets=16000, and one reception report block for SSRC=0xCAFEF00D with fraction_lost=2 and cumulative_lost=20. What is the total SR length?
5. The receiver reports cumulative_lost=24 in an RR block 5 seconds after the first report showed 20. What is the loss rate (per second)?
6. Why is the SSRC chosen at random? What happens if two senders accidentally pick the same SSRC? Cite the relevant RFC.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| RTP | "the audio protocol" | RFC 3550: an application-layer framing on top of UDP that adds seq# + timestamp + SSRC + PT to each media packet |
| RTCP | "the stats channel" | RFC 3550: a parallel UDP stream that carries SR, RR, SDES, BYE, APP packets for feedback and CNAME |
| SSRC | "the source ID" | A 32-bit random identifier for a participant; collisions are detected and resolved (RTP collision resolution) |
| CSRC | "the contributing source" | 0-15 SSRCs in the RTP header; mixers include the SSRCs of the sources they mixed |
| PT | "the codec" | 7-bit payload type; 0-95 static (RFC 3551, RFC 5761), 96-127 dynamic (SDP `rtpmap:`) |
| Jitter | "the variance" | RFC 3550 jitter: exponentially-weighted moving average of inter-arrival time differences, in media-clock units |
| LSR / DLSR | "the RTT pair" | Last SR timestamp + delay-since-last-SR; lets a sender compute RTT to a receiver |
| SDES | "the name service" | Source Description RTCP packet; CNAME is mandatory and is the persistent cross-SSRC identifier |
| SDP | "the offer/answer" | Session Description Protocol (RFC 4566); the SDP body that lists PTs, codecs, and addresses for an RTP session |
| Jitter buffer | "the playback queue" | A small application-side queue (typically 50-200 ms) that absorbs network jitter and reorders packets |
| Lip-sync | "the timing" | Cross-stream synchronization of audio and video via NTP + RTP timestamp mapping |

## Further Reading

- **RFC 3550** — *RTP: A Transport Protocol for Real-Time Applications* (Schulzrinne, Casner, Frederick, Jacobson, 2003). The canonical spec; replaces RFC 1889.
- **RFC 3551** — *RTP Profile for Audio and Video Conferences with Minimal Control* (Schulzrinne, Casner, 2003). The AV profile; static payload types.
- **RFC 5761** — *Multiplexing RTP Data and Control Packets on a Single Port* (2010). Why RTP and RTCP can share a port.
- **RFC 4566** — *SDP: Session Description Protocol* (Handley, Jacobson, Perkins, 2006). SDP, the offer/answer for RTP.
- **RFC 5109** — *RTP Payload Format for Generic Forward Error Correction* (2010). FEC over RTP.
- **RFC 4585** — *Extended RTP Profile for RTCP-Based Feedback (RTP/AVPF)* (2006). NACK and other fast feedback.
- **RFC 3711** — *The Secure Real-time Transport Protocol (SRTP)* (2004). Encryption and authentication of RTP.
- **RFC 7876** — *UDP Usage Guidelines for RTP* (2016). When to use RTP over UDP, when to use RTP over DTLS.
- Perkins, *RTP: Audio and Video for the Internet* (Addison-Wesley, 2003) — the practical reference.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.7 "Real-Time Transport Protocols" — the textbook treatment.
