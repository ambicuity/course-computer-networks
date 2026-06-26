# Streaming Stored Media to Streaming Live Media

> Stored media streaming uses a metafile handoff: the browser fetches a one-line ASCII file (e.g. `rtsp://joes-movie-server/movie-0025.mp4`), hands it to the media player, and the player contacts a specialized media server directly — bypassing the browser for the bulk transfer. The media player has four jobs: user interface, transmission-error handling, decompression, and jitter elimination. Error handling splits on transport: TCP (HTTP) gives reliability via retransmission but increases jitter; UDP (RTP) has no retransmissions, so the player must tolerate loss using FEC (parity across packets — every 4 data packets carry a 5th XOR parity packet, 25% overhead, recovers any single erasure) and interleaving (send even/odd samples in separate packets so a lost packet becomes reduced temporal resolution, not a gap). Jitter is killed by a playout buffer with low-water and high-water marks: 5–10 sec of media is buffered before playback starts; the buffer drains at constant playout rate and fills at network rate. RTSP (RFC 2326) is the remote control — text commands like HTTP: DESCRIBE, SETUP, PLAY, PAUSE, TEARDOWN. Firewalls usually block RTP (5004) and RTSP (554) but allow HTTP (80), so streaming often tunnels RTP over HTTP over TCP. Live media differs in three ways: (1) it is sent at exactly the playout rate, never faster, so the buffer must cover the full jitter range (10–15 sec startup is usual); (2) hundreds or thousands of viewers watch the same content simultaneously, so IP multicast + IGMP is the natural fit —.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Lessons 01, 02 (Digital Audio, Digital Video); Phase 11 RTP/UDP basics
**Time:** ~75 minutes

## Learning Objectives

- Trace the stored-media streaming sequence: HTTP metafile fetch → browser handoff → RTSP media request → RTP/TCP or RTP/UDP media response.
- Name the four media-player jobs (UI, error handling, decompression, jitter elimination) and explain which transport choice (TCP vs UDP) shifts work between them.
- Describe FEC parity across packets: 4 data + 1 parity, 25% overhead, recovers any single erasure, fails on two losses; explain the multicast benefit.
- Describe interleaving: even/odd samples in separate packets turn a 5 ms gap into 10 ms of reduced resolution, at no bandwidth cost but added latency.
- Explain the playout buffer with low-water and high-water marks, and why live streaming needs a larger buffer than stored streaming.
- List the six RTSP commands (DESCRIBE, SETUP, PLAY, RECORD, PAUSE, TEARDOWN) and state why TCP-over-HTTP tunneling is common in practice.

## The Problem

A video-on-demand site wants users to start watching within 2 seconds of clicking, not after a 30-minute download. A live Internet radio station wants to broadcast to 5,000 simultaneous listeners without melting its uplink. The two cases look similar — both push media over IP — but they have different constraints: stored media can be sent faster than playout rate to build buffer; live media cannot. The engineer must choose transport (TCP vs UDP), error strategy (retransmission vs FEC/interleaving), buffer depth, and signaling protocol (RTSP vs HTTP) per case, and understand why the public Internet defeats naive IP multicast for live streaming.

## The Concept

### The naive download model and why it fails

The easiest way to handle stored media is not to stream it: browser sends HTTP request, server sends the whole MP4, browser saves it to disk and starts the media player on the scratch file. This works but the entire video must transfer before playback starts. A 4 MB MP3 over 1 Mbps broadband = 30 seconds of silence before preview. This model sells no albums. `code/main.py` prints this delay for a few file sizes and link rates.

### The metafile handoff

Instead of linking to the movie, the page links to a tiny metafile — one line of ASCII text naming the movie URL:

```
rtsp://joes-movie-server/movie-0025.mp4
```

Sequence: (1) browser HTTP-requests the page; (2) server returns the one-line metafile; (3) browser hands the metafile to the media player; (4) media player reads the URL and contacts the media server with RTSP; (5) media streams directly to the player, bypassing the browser. The player starts playing before the full file arrives. The media server is usually a specialized RTSP/RTP server, not the HTTP server.

### The four media-player jobs

1. **User interface**: skins, buttons, sliders, visualizations.
2. **Transmission error handling**: depends on transport. TCP: retransmissions handle errors for free, but increase jitter. UDP: no retransmissions, so the player must tolerate loss.
3. **Decompression**: computationally intensive but straightforward. The catch: many codecs cannot decode later data until earlier data is decoded, so the codec must be designed to recover from packet loss (MPEG I-frames are the recovery points).
4. **Jitter elimination**: a playout buffer.

### FEC: parity across packets

For every 4 data packets (A, B, C, D) a 5th parity packet P is constructed as the XOR of bits across the four. If all five arrive, P is discarded. If any one of A, B, C, D is lost, it is reconstructed via XOR: `B = P XOR A XOR C XOR D`. If P is lost, no harm. If two packets are lost, recovery is impossible. Cost: 25% extra bandwidth, plus decoding latency (wait for parity before reconstructing an earlier loss).

This is *error correction* here even though parity is usually *error detection*, because the lost packet is known — an *erasure*. With unknown bit positions (Chapter 3), parity only detects. `code/main.py` simulates FEC: it XORs 4 packets, drops one at random, reconstructs it.

### FEC + multicast: a clever interaction

When the media is multicast, different clients lose different packets. Client 1 loses B, client 2 loses P, client 3 loses D, client 4 loses nothing. Even though three different packets are lost across the clients, every client can recover — each lost no more than one. One parity packet repairs any single erasure, whoever lost it.

### Interleaving

Mix samples before transmission, unmix on reception. A packet might hold 220 stereo samples (5 ms of music). Instead of sending samples in order, send all even samples for a 10 ms interval in one packet, all odd samples in the next. Loss of packet 3 no longer creates a 5 ms gap — it creates the loss of every other sample for 10 ms, which the player interpolates from neighbors. Result: lower temporal resolution for 10 ms, no time gap. Interleaving needs no extra bandwidth but adds latency (must wait for a group to de-interleave). RFC 3119 defines a scheme for compressed audio. `code/main.py` demonstrates interleaving by separating even/odd samples of a sine and showing the loss pattern.

### The playout buffer

All streaming systems buffer 5–10 sec of media before playing. The buffer drains at constant playout rate; the network fills it variably. If the buffer empties, playout stalls. The low-water mark triggers "resume sending"; the high-water mark triggers "pause sending." The high-water mark must exceed the bandwidth-delay product so that in-flight packets do not overflow after a pause; the low-water mark must also account for bandwidth-delay product so the server can resume before underrun.

### UDP vs TCP for streaming

| Factor | UDP (RTP) | TCP (HTTP) |
|--------|-----------|------------|
| Reliability | None; FEC/interleave | Retransmission |
| Jitter | Lower; small buffer | Higher; larger buffer |
| Send rate | Match playout (live) or faster (stored) | As fast as network allows |
| Firewall | Often blocked (5004) | Allowed (80) |
| Seek/rewind | Lost data is gone | Complete copy on disk |
| Mobile | Hard with changing connectivity | Buffer ahead, survive drops |

TCP is often chosen in practice because it passes firewalls (port 80), gives a complete copy for rewind, and lets mobile clients buffer ahead. Disadvantage: TCP startup latency and a higher low-water mark. But when network bandwidth exceeds media rate, the buffer fills and underruns stop mattering.

### RTSP — the remote control

RTSP (RFC 2326) is a text protocol like HTTP, usually over TCP (can run over UDP since each command is acked). Commands:

| Command | Server action |
|---------|---------------|
| DESCRIBE | List media parameters |
| SETUP | Establish logical channel |
| PLAY | Start sending data |
| RECORD | Start accepting data |
| PAUSE | Temporarily stop |
| TEARDOWN | Release the channel |

RTSP does *not* carry the data stream — that is RTP over UDP or RTP over HTTP over TCP.

### Live media: three key differences

1. **No faster-than-playout send**: live media is generated at the playout rate. The buffer must cover the full network jitter range. 10–15 sec startup is usually adequate.
2. **Many simultaneous viewers of the same content**: natural fit for IP multicast. Clients join the group with IGMP, not RTSP. Server sends each packet once; the network replicates it.
3. **Public Internet defeats multicast**: IP multicast is not broadly available across ISP boundaries. So in practice, each viewer gets a separate TCP connection — feasible for moderate audiences, especially audio. For very large audiences, a set of geographically spread servers is used (a CDN, Lesson 06).

The exception is the provider walled garden: a cable company running IPTV to set-top boxes controls its own network, so multicast + UDP + RTP + FEC works. The customer sees cable TV; underneath it is IP.


## Build It

1. Run `python3 code/main.py` and read the download-delay table — note why the naive model fails.
2. Watch the FEC demo XOR 4 packets, drop one, reconstruct it. Try dropping two — reconstruction fails.
3. Run the interleaving demo: see how a lost packet becomes reduced resolution instead of a gap.
4. Run the playout-buffer simulation: observe underruns when jitter exceeds the buffer, and the effect of the low/high-water marks.
5. Open `assets/streaming-stored-media-to-streaming-live-media.svg` and trace the metafile handoff and the playout buffer.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Diagnose slow start | Download delay vs streaming start | <2 sec with metafile, not full-download wait |
| Choose error strategy | FEC vs interleaving vs TCP retrans | TCP if firewall/rewind; FEC/interleave if UDP latency budget |
| Size playout buffer | Jitter range + bandwidth-delay product | Low-water mark avoids underrun; high-water avoids overflow |
| Pick live transport | Multicast if walled garden; TCP otherwise | Audience size + ISP multicast support drive decision |
| Trace RTSP | DESCRIBE/SETUP/PLAY/PAUSE/TEARDOWN | Commands map to player remote-control actions |

## Ship It

Produce `outputs/streaming-transport-decision.md`: given a scenario (stored/live, audience size, firewall strictness, mobile vs fixed), record transport choice (UDP/RTP, TCP/HTTP, multicast), error strategy (FEC %, interleave depth, TCP retrans), buffer depth, and signaling (RTSP, HTTP Live Streaming). Reusable for any streaming product.

## Exercises

1. A 4 MB MP3 is served over a 1 Mbps link using the naive download model. Compute the silence-before-preview delay. What metafile streaming reduces it to.
2. Design an FEC scheme with 25% overhead that recovers any single erasure in a group of 5. What happens when two packets in the same group are lost? Why can't parity recover them?
3. A live concert is multicast to 10,000 viewers. Three different clients each lose a different packet in the same FEC group. Explain how all three recover from the single parity packet.
4. An interleaving scheme packs 220 even samples in one packet, 220 odd in the next. Packet 3 is lost. Describe exactly what the listener hears, and why this is preferable to a 5 ms gap.
5. A live stream cannot send faster than playout rate. Explain why this forces a larger playout buffer than stored media, and why 10–15 sec startup is usually enough.
7. A cable company broadcasts TV to set-top boxes using IPTV with multicast + UDP + RTP + FEC. The same company's over-the-top Internet service uses TCP. Why the difference?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Metafile | "the pointer file" | One-line ASCII naming the media URL; browser hands to player |
| RTSP | "remote control" | RFC 2326; DESCRIBE/SETUP/PLAY/PAUSE/TEARDOWN |
| FEC | "parity packet" | XOR across N data packets; recovers any single erasure; 25% overhead at N=4 |
| Erasure | "known-lost packet" | Lost packet whose position is known; parity corrects, not just detects |
| Interleaving | "mix samples" | Even/odd in separate packets; loss → reduced resolution, not a gap |
| Playout buffer | "jitter buffer" | 5–10 sec (stored) or 10–15 sec (live); low/high-water marks |
| Low-water mark | "resume line" | Trigger server to resume; must cover bandwidth-delay product |
| High-water mark | "pause line" | Trigger server to pause; room for in-flight packets |
| IGMP | "multicast join" | Group join/leave protocol for live multicast receivers |
| IPTV | "cable over IP" | Provider-walled-garden multicast TV; set-top box is a computer |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Sections 7.4.3 (Streaming Stored Media) and 7.4.4 (Streaming Live Media).
- RFC 2326 — Real Time Streaming Protocol (RTSP).
- RFC 3550 — RTP: A Transport Protocol for Real-Time Applications.
- RFC 3119 — A more efficient loss-tolerant RTP packing for compressed audio.
- Nonnenmacher et al. (1997), "Reliable Multicast Transport," FEC for multicast reliability.
