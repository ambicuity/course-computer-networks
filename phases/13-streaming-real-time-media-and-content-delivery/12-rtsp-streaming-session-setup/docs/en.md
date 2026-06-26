# RTSP Streaming Session Setup

> HTTP fetches a file. RTSP controls a stream. It is the remote control protocol that sets up, plays, pauses, and tears down a media session over RTP.

**Type:** Lab
**Languages:** Python, packet traces, Wireshark
**Prerequisites:** Phase 13 lessons 01-11 (Streaming Stored Media, RTP)
**Time:** ~75 minutes

## Learning Objectives

- Describe the RTSP session lifecycle: DESCRIBE, SETUP, PLAY, PAUSE, TEARDOWN
- Map RTSP methods to their state transitions and responses
- Explain how RTSP separates control (TCP) from media (RTP/UDP)
- Identify the Session ID, Transport, and CSeq header fields
- Build a minimal RTSP message exchange simulator

## The Problem

When you watch a streamed video, two things happen: (1) the player negotiates with the server to set up the stream, and (2) the server sends media packets over a separate channel. HTTP can do the first part but only for download-once-then-play. For live streaming with play, pause, seek, and stop, you need a protocol designed for session control. RTSP (Real-Time Streaming Protocol, RFC 2326) is that protocol. It is text-based like HTTP but stateful: the server remembers your session between requests.

## The Concept

### The session state machine

```text
         DESCRIBE
  INIT -----------> READY
                      |
           SETUP      |     PLAY
           (add)      v      |
                    READY <--> PLAYING
                      |        |
                      |  PAUSE |
                      |   <----+
                      |
           TEARDOWN
                      v
                   TEARDOWN (closed)
```

### RTSP methods

| Method | Purpose | State change |
|--------|---------|---------------|
| DESCRIBE | Ask server for media description (SDP) | INIT -> READY |
| SETUP | Negotiate transport (RTP port, protocol) | Adds a stream to the session |
| PLAY | Start or resume sending media | READY -> PLAYING |
| PAUSE | Temporarily stop sending media | PLAYING -> READY |
| TEARDOWN | End the session and free resources | any -> TEARDOWN |
| GET_PARAMETER | Keepalive / query server state | none |
| SET_PARAMETER | Set server parameters | none |

### Key headers

- `CSeq`: sequence number for request-response matching
- `Session`: session ID returned by SETUP, required in all subsequent requests
- `Transport`: negotiated transport (e.g., `RTP/AVP;unicast;client_port=50000-50001`)
- `Content-Type`: usually `application/sdp` for DESCRIBE responses

### Separation of control and media

RTSP runs over TCP (typically port 554) for reliability. The actual media flows over RTP/UDP on dynamically negotiated ports. This separation means you can pause the media without tearing down the TCP control connection, and the media can use UDP for low latency while control uses TCP for reliability.

### SDP (Session Description Protocol)

The DESCRIBE response contains an SDP body describing the media: codecs, sample rates, track IDs. Example:

```text
v=0
o=- 2890844526 2890842807 IN IP4 192.168.1.1
s=Test Stream
c=IN IP4 0.0.0.0
t=0 0
m=video 50004 RTP/AVP 96
a=rtpmap:96 H264/90000
m=audio 50006 RTP/AVP 0
a=rtpmap:0 PCMU/8000
```

## Build It

The script below simulates a complete RTSP session lifecycle with stdlib only. It implements:

1. A minimal RTSP server state machine
2. Request/response message formatting (CSeq, Session, Transport headers)
3. The full lifecycle: DESCRIBE -> SETUP -> PLAY -> PAUSE -> PLAY -> TEARDOWN
4. SDP generation and parsing
5. State transition logging

```python
# Core idea (see code/main.py for full implementation)
session = RTSPSession("rtsp://server/stream")
session.describe()   # get SDP
session.setup(0)     # negotiate transport for track 0
session.play()       # start streaming
session.pause()
session.teardown()
```

## Use It

```bash
python3 code/main.py
```

Expected output: a complete RTSP message exchange log showing each request, response code, headers, state transition, and SDP body. The output looks like a Wireshark follow-stream capture of an RTSP session.

## Ship It

- Use the script as a reference when debugging a real RTSP capture in Wireshark. Filter by `rtsp` and compare the CSeq and Session headers.
- Extend the server to support multiple SETUP calls for audio and video tracks.
- Add a GET_PARAMETER keepalive loop and show how it prevents NAT timeout.

## Exercises

1. Add a SEEK/RANGE header to PLAY and show how the server responds with a specific start time.
2. Implement an authentication challenge (401 Unauthorized + WWW-Authenticate) and the client retry with Authorization.
3. Simulate a SETUP failure (port already in use) and show the error response.
4. Add a second media track (audio) and show two SETUP calls with different Transport headers.
5. Capture a real RTSP session with Wireshark (if you have access to an RTSP camera) and compare the message flow to the simulator.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| RTSP | "Streaming protocol" | A text-based session control protocol that manages media stream lifecycle, separate from the media transport |
| DESCRIBE | "Get info" | An RTSP method that returns the media description as an SDP body |
| SETUP | "Connect" | An RTSP method that negotiates the transport (ports, protocol) and creates a session |
| Session ID | "A token" | An opaque identifier returned by SETUP, required in all subsequent requests |
| CSeq | "Sequence number" | Command Sequence: a per-request counter for matching responses to requests |
| SDP | "Media info" | Session Description Protocol, a text format describing codecs, ports, and media tracks |
| TEARDOWN | "Stop" | An RTSP method that ends the session and frees server-side resources |
| Transport header | "How data moves" | The RTSP header that negotiates RTP/AVP, unicast/multicast, and port numbers |

## Further Reading

- [RFC 2326 - RTSP 1.0](https://www.rfc-editor.org/rfc/rfc2326) - the original standard
- [RFC 4566 - SDP](https://www.rfc-editor.org/rfc/rfc4566) - Session Description Protocol
- [Wireshark RTSP filter reference](https://wiki.wireshark.org/RTSP) - capture analysis guide
