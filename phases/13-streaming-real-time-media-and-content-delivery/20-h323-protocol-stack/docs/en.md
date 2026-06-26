# The H.323 Protocol Stack

> Before SIP won the VoIP signaling war, H.323 was the ITU standard: a family of protocols for call signaling, control, and media transport over packet networks.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Phase 13 lessons 01-19 (SIP, RTP, Real-time Conferencing)
**Time:** ~75 minutes

## Learning Objectives

- Map the H.323 protocol stack: H.225, H.245, RTP, RTCP, and their roles
- Describe the H.323 call setup phases: RAS, call signaling, control, media
- Compare H.323 with SIP in architecture, encoding, and extensibility
- Identify H.323 entities: terminal, gateway, gatekeeper, MCU
- Trace a complete H.323 call from RAS admission to RTP media

## The Problem

The ITU (telecom world) needed a standard for carrying voice and video over packet-switched networks (IP). Unlike the IETF (which designed SIP as a simple text protocol), the ITU adapted its existing ISDN signaling protocols (Q.931) for IP, producing H.323. The result is a complex, binary-encoded, multi-protocol stack that was widely deployed in enterprise VoIP and video conferencing before SIP displaced it. Understanding H.323 is still important for interoperating with legacy systems and for appreciating why SIP's simpler design won.

## The Concept

### The H.323 stack

```text
          Application (Voice/Video)
                   |
     +-------------+-------------+
     |             |             |
   H.245        H.225          H.225
  (Control)   (Q.931 Call    (RAS:
     |          Signaling)   Registration,
     |             |          Admission,
     |             |          Status)
     +------+------+-------------+
            |             |
          RTP/RTCP      TCP/UDP
            |             |
         UDP           UDP (RAS) / TCP (Q.931, H.245)
            |             |
         IP            IP
```

### Protocol components

| Protocol | Transport | Purpose |
|----------|-----------|---------|
| H.225 RAS | UDP | Registration, admission, status (with gatekeeper) |
| H.225 Q.931 | TCP | Call signaling (setup, connect, release) |
| H.245 | TCP | Control channel: capability exchange, open logical channels |
| RTP | UDP | Media transport |
| RTCP | UDP | Media quality feedback |
| T.120 | TCP | Data sharing (optional) |

### H.323 entities

- **Terminal**: An endpoint (phone, video client) that originates and terminates calls
- **Gateway**: Connects H.323 to other networks (PSTN, SIP)
- **Gatekeeper**: Optional central controller: address translation, admission control, bandwidth management
- **MCU (Multipoint Control Unit)**: Supports multi-party conferencing (multiplexer)

### Call setup phases

1. **RAS Admission**: Terminal asks gatekeeper for permission (ARQ/ACF)
2. **Call Signaling**: Q.931 SETUP -> CONNECT (like ISDN call setup)
3. **Control Channel**: H.245 capability exchange (what codecs do you support?)
4. **Open Logical Channels**: H.245 opens RTP transport channels for each media type
5. **Media Flow**: RTP carries audio/video; RTCP carries quality reports
6. **Close**: H.245 closes logical channels, Q.931 releases call, RAS disengage

### H.323 vs SIP

| Aspect | H.323 | SIP |
|--------|-------|-----|
| Origin | ITU (telecom) | IETF (Internet) |
| Encoding | ASN.1 PER (binary) | Text (HTTP-like) |
| Signaling | Q.931 + H.245 (two channels) | SIP (one protocol) |
| Complexity | High (multiple protocols) | Lower (single protocol) |
| Extensibility | Hard (binary encoding) | Easy (text headers) |
| Media negotiation | H.245 capability exchange | SDP offer/answer |
| Adoption | Legacy enterprise, declining | Dominant in modern VoIP |

### Why SIP won

H.323's binary ASN.1 encoding makes debugging difficult (you cannot read messages in a text capture). The split between Q.931 and H.245 means two separate TCP connections for one call. SIP's text-based, single-protocol design is simpler to implement, debug, and extend. However, H.323's strong telecom lineage gave it robust feature sets (like H.239 dual-stream video) that SIP took years to match.

## Build It

The script below simulates the H.323 call setup flow including RAS, Q.931, and H.245 phases. It demonstrates:

1. RAS admission (ARQ/ACF with gatekeeper)
2. Q.931 call signaling (SETUP/CONNECT)
3. H.245 capability exchange and logical channel opening
4. RTP media establishment
5. Call teardown
6. Comparison table: H.323 vs SIP

```python
# Core idea (see code/main.py)
gatekeeper.admit(terminal)           # RAS
q931.setup(caller, callee)           # Call signaling
h245.exchange_capabilities()         # Control
h245.open_logical_channel(audio)     # Open media path
rtp.flow(audio_channel)              # Media
```

## Use It

```bash
python3 code/main.py
```

Expected output: a phase-by-phase trace of an H.323 call, showing RAS messages, Q.931 signaling, H.245 control exchanges, logical channel setup, and a comparison with SIP.

## Ship It

- Use the trace to understand legacy H.323 captures in Wireshark. Filter by `h323` or `q931`.
- Map each H.323 phase to the equivalent SIP phase and explain the architectural difference.
- Document when H.323 is still encountered (legacy video conferencing, Cisco/Avaya systems).

## Exercises

1. Add a gatekeeper-routed call (gatekeeper in the signaling path) and compare with direct terminal-to-terminal signaling.
2. Simulate a multi-party conference through an MCU and show the additional H.245 messages.
3. Implement H.239 dual-stream (video + presentation) and show two logical channels.
4. Add a gateway scenario where H.323 connects to a SIP network and trace the interworking.
5. Compare the message count and setup time of H.323 vs SIP for the same call.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| H.323 | "Old VoIP" | An ITU standard suite for multimedia communication over packet networks, using multiple binary protocols |
| H.225 RAS | "Gatekeeper protocol" | Registration, Admission, Status protocol between terminals and gatekeepers |
| H.225 Q.931 | "Call setup" | ISDN-derived call signaling protocol for establishing H.323 calls |
| H.245 | "Control channel" | The control protocol that negotiates capabilities and opens media logical channels |
| Gatekeeper | "The controller" | An optional H.323 entity that manages address translation, admission, and bandwidth |
| MCU | "Conference bridge" | Multipoint Control Unit that mixes and distributes media for multi-party calls |
| ASN.1 PER | "Binary encoding" | Abstract Syntax Notation 1 Packed Encoding Rules, the binary format H.323 messages use |
| Logical channel | "Media path" | An H.245-opened transport path for one media stream (audio or video) |

## Further Reading

- [ITU-T H.323](https://www.itu.int/rec/T-REC-H.323) - the official standard
- [H.323 vs SIP comparison](https://en.wikipedia.org/wiki/H.323) - overview and history
- [Wireshark H.323 dissection](https://wiki.wireshark.org/H.323) - capture analysis
