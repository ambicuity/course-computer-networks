# TCP Three-Way Handshake and State Machine from Packet Traces

> A TCP connection is not "opened" — it is *negotiated* by exchanging Initial Sequence Numbers (ISNs) so that both ends agree on the first byte each will send. RFC 793 defines the **three-way handshake**: the active opener sends a **SYN** carrying its 32-bit ISN; the passive opener replies with a single **SYN+ACK** that both acknowledges `ISN_client+1` and announces its own `ISN_server`; the active opener closes the exchange with a bare **ACK** acknowledging `ISN_server+1`. Both SYN and FIN flags each **consume one sequence number** even though they carry no payload, which is why the first data byte is `ISN+1`, not `ISN`. The connection runs through an **11-state finite state machine** (CLOSED, LISTEN, SYN_SENT, SYN_RCVD, ESTABLISHED, FIN_WAIT_1, FIN_WAIT_2, CLOSING, TIME_WAIT, CLOSE_WAIT, LAST_ACK) whose transitions are driven by segment arrival and application calls. The teardown is a **four-wave** FIN exchange that leaves the active closer in **TIME_WAIT** for `2·MSL` (typically 60–120s) so a retransmitted FIN or a wandering old segment cannot reopen the port or corrupt a reincarnated connection. The 16-bit **checksum** covers the 20-byte header, the payload, and a 12-byte **pseudo-header** (src IP, dst IP, protocol=6, TCP length) per RFC 1071's one's-complement sum; a bad checksum is **silently dropped**, never NACKed. This lesson parses real TCP header bytes, recomputes that checksum, and drives the full FSM so you can read the state a trace leaves behind.

**Type:** Lab
**Languages:** Python, tcpdump, Wireshark
**Prerequisites:** IP addressing and the IP datagram, byte order and `struct` parsing, basic transport-layer concepts (Phase 00 labs on packet capture and the IP header)
**Time:** ~80 minutes

## Learning Objectives

- Decode a 20-byte TCP header from raw bytes, naming every field, its width, and its byte offset, and explain why the data offset is measured in 32-bit words.
- Trace the three-way handshake and compute `SEG.SEQ` / `SEG.ACK` at each step, accounting for the fact that SYN and FIN each consume one sequence number.
- Walk a connection through the 11-state FSM on both the active and passive sides, naming the segment or application call that triggers each transition.
- Compute and validate the RFC 1071 Internet checksum over the TCP header, payload, and the 12-byte pseudo-header, and explain why a checksum failure is a silent drop.
- Diagnose a stuck or half-open connection from a packet trace (SYN without SYN+ACK, duplicate SYN, FIN without final ACK) and name the offending state.
- Justify the `2·MSL` TIME_WAIT hold and the classic ISN-prediction hazard that made early TCP spoofing possible.

## The Problem

A service desk reports that connections to `10.0.0.7:8080` hang for about 30 seconds and then fail, but only from one client subnet. A `tcpdump -n -i eth0 'tcp port 8080'` shows the client's SYN going out, the server's SYN+ACK coming back, and then... silence — no final ACK. The client retransmits the SYN; the server retransmits the SYN+ACK; after a few seconds both sides give up. The application log shows nothing because the connection never reached `ESTABLISHED`. The engineer needs to read those three packets off the wire, confirm which side dropped the ball, and figure out whether a stateful firewall is eating the final ACK or the client's TCP stack is miscomputing the checksum.

The same skill set answers the inverse question: a load test opens 50,000 short-lived connections and the server runs out of ephemeral ports even though throughput is low. The trace shows tens of thousands of sockets parked in TIME_WAIT. Understanding the state machine — and the `2·MSL` hold that produces TIME_WAIT — is what turns "mysterious port exhaustion" into a known, tunable condition. This lab builds the parser and the FSM that make those traces readable.

## The Concept

### The TCP header, byte by byte

The fixed TCP header is 20 bytes; options (MSS, SACK-Permitted, Timestamps, Window Scale) ride in the variable part whose length the **Data Offset** field encodes. The layout (RFC 793 §3.1):

| Offset | Field | Width | Meaning |
|---|---|---|---|
| 0 | Source Port | 16 bits | Sending port |
| 2 | Destination Port | 16 bits | Receiving port |
| 4 | Sequence Number | 32 bits | `SEG.SEQ` — first byte in this segment (or ISN if SYN) |
| 8 | Acknowledgment Number | 32 bits | `SEG.ACK` — next byte the sender expects to receive |
| 12 | Data Offset | 4 bits | Header length in 32-bit words (5 ⇒ 20-byte header, 15 ⇒ 60-byte max) |
| 12 | Reserved | 3 bits | Must be zero (historically; some reused for ECN/CWR) |
| 12 | Control flags | 9 bits | URG, ACK, PSH, RST, SYN, FIN (plus NS, CWR, ECE) |
| 14 | Window | 16 bits | Receive window in bytes (scaled by Window Scale option if negotiated) |
| 16 | Checksum | 16 bits | One's-complement sum over pseudo-header + header + data |
| 18 | Urgent Pointer | 16 bits | Offset to urgent data; valid only when URG set |
| 20 | Options | 0–40 bytes | Padded to a 4-byte boundary |

The Data Offset packs into the top 4 bits of bytes 12–13; the flags occupy the low 9 bits of that same 16-bit word. `code/main.py` extracts them with `(off_flags >> 12) & 0xF` and `off_flags & 0x1FF`, exactly as a dissector must.

### Sequence numbers and the ISN arithmetic

TCP numbers every byte in a stream with a 32-bit counter that wraps modulo 2³². The **Initial Sequence Number** is chosen per connection (ideally unpredictable, per RFC 6528) so that a stray segment from an old incarnation cannot land in the new stream. The handshake's real job is to synchronize these two independent counters.

Consider a client ISN `ISN_c = 0x93bccacf` and server ISN `ISN_s = 0x442f3231` (the values `code/main.py` prints with seed `0x793`):

| Step | Segment | SEQ | ACK | After this, client sends from | After this, server sends from |
|---|---|---|---|---|---|
| 1 | SYN | `ISN_c` | 0 (ACK bit clear) | `ISN_c + 1` | — |
| 2 | SYN+ACK | `ISN_s` | `ISN_c + 1` | `ISN_c + 1` | `ISN_s + 1` |
| 3 | ACK | `ISN_c + 1` | `ISN_s + 1` | `ISN_c + 1` | `ISN_s + 1` |

After step 3, `snd_nxt = ISN_c + 1` on the client and `rcv_nxt = ISN_s + 1`; the first data byte the client ships carries `SEQ = ISN_c + 1`. SYN and FIN are *phantom bytes*: they advance the sequence counter by one but carry no payload. That is why an ACK of `ISN_c + 1` (not `ISN_c`) means "I saw your SYN." `code/main.py` reproduces this arithmetic in `client_open` / `server_open` and logs `SEG.NEXT` at each step.

### The 11-state connection FSM

Each endpoint keeps a **Transmission Control Block (TCB)** holding `snd_una` (oldest unacknowledged), `snd_nxt`, `rcv_nxt`, the ISNs, and the current state. The state transitions are driven by three event classes: segment arrival, application calls (`connect`, `listen`, `close`), and timers.

| State | Entered by | Exited by |
|---|---|---|
| CLOSED | start / final | `connect()` → SYN_SENT; `listen()` → LISTEN |
| LISTEN | `listen()` | recv SYN → SYN_RCVD (send SYN+ACK) |
| SYN_SENT | `connect()` sends SYN | recv SYN+ACK → ESTABLISHED (send ACK); recv SYN → SYN_RCVD (simultaneous open) |
| SYN_RCVD | sent SYN+ACK | recv ACK → ESTABLISHED |
| ESTABLISHED | handshake done | `close()` → FIN_WAIT_1 (active) / CLOSE_WAIT (passive) |
| FIN_WAIT_1 | sent FIN | recv ACK → FIN_WAIT_2; recv FIN → CLOSING |
| FIN_WAIT_2 | our FIN acked, half-closed | recv FIN → TIME_WAIT (send ACK) |
| CLOSING | simultaneous close | recv ACK → TIME_WAIT |
| TIME_WAIT | sent final ACK | `2·MSL` timer → CLOSED |
| CLOSE_WAIT | recv FIN, sent ACK | `close()` → LAST_ACK (send FIN) |
| LAST_ACK | sent our FIN | recv ACK → CLOSED |

The diagram in `assets/tcp-three-way-handshake-and-state-machine-from-packet-traces.svg` lays out both the handshake ladder and the FSM graph; the berry-colored nodes (SYN_SENT, SYN_RCVD, ESTABLISHED, TIME_WAIT) are the ones whose presence in a trace is the most diagnostic.

### Teardown: the four-wave FIN exchange and TIME_WAIT

Closing is symmetric and costs four segments because each direction must be shut independently (TCP is full-duplex):

1. Active closer sends FIN (`FIN_WAIT_1`).
2. Passive side ACKs it and enters `CLOSE_WAIT`; it may still drain queued data.
3. Passive side's app calls `close()`, sending its own FIN (`LAST_ACK`).
4. Active closer ACKs it and enters `TIME_WAIT`, holding the TCB for `2·MSL`.

**MSL** (Maximum Segment Lifetime) is the longest a segment can survive in the network — RFC 793 specifies 2 minutes, so `2·MSL = 4 minutes`, though most kernels (Linux `tcp_fin_timeout`, `net.ipv4.tcp_fin_timeout`/TIME_WAIT reuse) use 60s in practice. TIME_WAIT exists for two reasons: (a) the active closer's final ACK might be lost, so it must stay to re-ACK a retransmitted FIN; (b) it prevents a delayed segment from an *old* incarnation of the 4-tuple from being delivered to a *new* connection that reuses the same ports. TIME_WAIT is the price the closer pays for reliability; it is also why servers that open many short connections (HTTP keep-alive off) accumulate thousands of TIME_WAIT sockets and can exhaust ephemeral ports. The fix is `SO_REUSEADDR`/`tcp_tw_reuse`, not disabling the hold.

### The checksum: pseudo-header and one's-complement sum

TCP's correctness check is the 16-bit Internet checksum of RFC 1071 — the same algorithm IP uses, but over a wider scope. The key subtlety: the sum covers not just the TCP header and payload but a 12-byte **pseudo-header** synthesized from the IP header, so that a delivery to the wrong IP address or the wrong protocol is detected:

| Pseudo-header field | Width | Source |
|---|---|---|
| Source Address | 32 bits | IP header src |
| Destination Address | 32 bits | IP header dst |
| Zero | 8 bits | constant 0 |
| Protocol | 8 bits | 6 (TCP) |
| TCP Length | 16 bits | header + payload length |

The algorithm folds all 16-bit words into a 32-bit accumulator, adds back the carries, and takes the one's complement. To validate, the receiver sums the same region *including* the stored checksum; a correct segment sums to `0xFFFF` (equivalently, recomputing the checksum over the header yields 0). `code/main.py` implements this in `internet_checksum` and `tcp_checksum`, builds a real 20-byte header with a valid checksum in `make_segment`, then re-parses and validates it — and corrupts one byte to show the receiver would **silently drop** the segment (RFC 793 specifies no negative acknowledgment for bad checksums; the sender's retransmission timer is the only recovery).

### Reading it off the wire with tcpdump and Wireshark

The point of the lab is to map bytes to states. A typical capture filter and display:

```bash
sudo tcpdump -n -i eth0 -S 'tcp port 8080'        # -S prints absolute seq numbers
```

`-S` is essential: by default tcpdump shows *relative* sequence numbers (starting at 1) which hides the ISN arithmetic. With `-S` you see the real 32-bit values and can verify `ack == seq + 1` for the SYN. In Wireshark, *Edit → Preferences → Protocols → TCP → "Relative sequence numbers"* toggles the same thing; turn it off for this lab. The three handshake packets appear in order: `[S]`, `[S.]`, `[.]` in tcpdump's flag shorthand (`S`=SYN, `.`=ACK). A connection that never reaches ESTABLISHED shows the first two but not the third — the diagnostic that pins a dropped final ACK. The accompanying `code/main.py` reproduces exactly these three segments with real checksums so you can compare its output line-for-line against a live capture.

### Why ISNs must be unpredictable: the spoofing hazard

Because TCP authenticates a connection only by the 4-tuple (src IP, src port, dst IP, dst port) and the sequence numbers, an attacker who can *predict* the server's ISN can forge the final ACK and inject data into a half-open connection — the classic Mitnick attack (Shimomura, Christmas 1994). Early BSD-derived stacks generated ISNs by incrementing a counter at a fixed rate, making the next ISN trivially guessable. RFC 6528 mandates a **cryptographic, per-connection ISN** derived from a hash of the 4-tuple and a secret so successive ISNs are uncorrelated. The handshake itself does not prevent this; the unpredictable ISN does. Knowing this is why `code/main.py` draws its ISNs from a seeded RNG rather than `+1`-ing a counter, and why a trace showing ISNs that march up by a constant delta is a red flag on a legacy stack.

## Build It

1. Read `code/main.py`. Note `parse_tcp_header` (struct unpack of the 20-byte header), `internet_checksum`/`tcp_checksum` (RFC 1071 + pseudo-header), and the FSM functions `client_open`, `server_open`, `close_active`, `close_passive`.
2. Run it: `python3 code/main.py`. Confirm the three wire segments print with `cksum_ok=True` and that the client's SYN+ACK `ack` equals `client_isn + 1`.
3. Run `sudo tcpdump -n -i lo -S 'tcp port 8080'` in one terminal and `python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8080))"` against a local server in another. Match the captured `[S]`/`[S.]`/`[.]` triple to the three segments `main.py` prints.
4. In Wireshark, capture the same loopback exchange, disable *Relative sequence numbers*, and verify the SYN's checksum field against the value `make_segment` produces for the same ports and ISN.
5. Edit the FSM: add a `simultaneous_open()` that has both sides send SYN and converge on SYN_RCVD → ESTABLISHED without a clear client/server role. Print the resulting state log.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a clean handshake | Three segments SYN, SYN+ACK, ACK with `ack = peer_seq + 1` each time | The third ACK carries no payload and closes the exchange; both sides reach ESTABLISHED |
| Spot a dropped final ACK | SYN and SYN+ACK present, ACK missing; SYN+ACK retransmits | The server retransmits SYN+ACK (exponential backoff); client never leaves SYN_SENT |
| Validate a checksum | Recompute over pseudo-header + header + payload; compare to stored field | Sum-including-checksum equals 0xFFFF; a one-bit flip makes it non-zero and the segment is dropped |
| Diagnose TIME_WAIT flooding | Many sockets in TIME_WAIT after a load test; ephemeral port allocation failing | Active closers hold `2·MSL`; fix is reuse/tw_reuse or making the *server* the active closer |
| Detect a half-open connection | One side thinks ESTABLISHED, the other gave up after SYN_SENT | A RST from the dead side on the next data send is the cleanup; the surviving side should treat it as connection reset |
| Recognize simultaneous open | Both sides send SYN, both go SYN_SENT → SYN_RCVD → ESTABLISHED | Four segments (SYN, SYN, SYN+ACK, SYN+ACK) instead of three; rare but legal |

## Ship It

Produce one artifact under `outputs/prompt-tcp-three-way-handshake-and-state-machine-from-packet-traces.md`:

- An annotated handshake+teardown trace (the eight segments) for a connection you open against `127.0.0.1:8080`, with absolute sequence numbers and the per-segment state transition on both endpoints called out.
- A checksum validation table: for each of the three handshake segments, the pseudo-header bytes, the computed checksum, and the stored checksum.
- A failure-mode card: the four traces (dropped SYN, dropped SYN+ACK, dropped final ACK, lost final FIN) with the state each endpoint ends in and the observable retransmit pattern.

Start from the printed output of `code/main.py` and annotate it with the live capture evidence.

## Exercises

1. A SYN carries `SEQ = 0x1000` and a 1460-byte MSS option. The SYN+ACK replies with `SEQ = 0x9a00`, `ACK = 0x1001`. What does the client's third segment carry for SEQ and ACK, and what is the SEQ of the client's first data byte?
2. Capture a connection to a real web server with `tcpdump -S`. Disable relative sequence numbers. Show that the server's ISN is not `client_ISN + 1` and argue why RFC 6528's per-connection cryptographic ISN matters for security.
3. `code/main.py` corrupts byte 16 of the header (the checksum). Change it to corrupt a byte in the *payload* instead and confirm the checksum still fails. Then corrupt a byte in the pseudo-header's destination IP and explain why the receiver's check would catch a misrouted segment.
4. Implement `simultaneous_open()` in `main.py`: both endpoints call `connect()` and both send a SYN before either sees the other's. Walk the four-segment exchange and the SYN_SENT → SYN_RCVD → ESTABLISHED path. Why is the result still a single connection, not two?
5. A load test opens 20,000 connections that each transfer 1 byte and close, with the *client* as active closer. Predict how many TIME_WAIT entries appear on the client and for how long. Then change the test so the *server* closes first and recompute. Which side should close in a busy HTTP keep-alive server, and why?
6. A firewall between client and server drops the final ACK of the handshake but lets retransmits through. Describe exactly what each side's FSM does over the next 5 seconds and which side's retransmit count you would see climbing in `netstat -s | grep -i retrans`.
7. Two segments arrive at a server for the same 4-tuple: one is a retransmitted FIN from a connection that closed 90 seconds ago (within `2·MSL`), the other is the SYN of a freshly opened connection reusing those ports. Explain how TIME_WAIT on the old connection's closer distinguishes them, and what would go wrong if TIME_WAIT did not exist.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Three-way handshake | "the SYN thing" | The SYN / SYN+ACK / ACK exchange that synchronizes both endpoints' 32-bit ISNs so each knows the other's first byte number |
| ISN | "a random start number" | Initial Sequence Number — per-connection, cryptographically unpredictable (RFC 6528) starting point of a stream's 32-bit byte counter |
| Sequence number | "the packet number" | The 32-bit byte offset of the first byte in this segment within the stream; SYN and FIN each consume one even with no payload |
| TCB | "the connection record" | Transmission Control Block — per-connection state: ISNs, snd_una, snd_nxt, rcv_nxt, window, retransmit timer, current FSM state |
| Data offset | "header length" | The 4-bit field giving header length in 32-bit words (5–15); the only TCP header field measured in words, not bytes |
| Pseudo-header | "the fake header" | A 12-byte synthesized block (src/dst IP, proto=6, TCP length) prepended only for the checksum so misdelivery is detected |
| TIME_WAIT | "the slow close" | The `2·MSL` state the active closer holds after the final ACK, to catch retransmitted FINs and bar old segments from a re-incarnated 4-tuple |
| MSL | "a timeout" | Maximum Segment Lifetime — the longest a segment can survive in the net; RFC 793 says 2 minutes, so `2·MSL ≈ 4 min` (kernels often use 60s) |
| Half-open / half-close | "broken connection" | Half-open = one side thinks it's up, the other gave up; half-close = FIN sent and acked but the reverse direction still carries data (FIN_WAIT_2) |
| Simultaneous open | "both sides connect at once" | Both endpoints send SYN before seeing the other's; both pass through SYN_RCVD to a single ESTABLISHED connection via four segments |
| Internet checksum | "the TCP checksum" | RFC 1071 one's-complement 16-bit sum over pseudo-header + header + payload; failure is a silent drop, never a NACK |

## Further Reading

- **RFC 793** — Transmission Control Protocol, the original specification of the header, the three-way handshake, and the 11-state FSM (see especially §3.2 state machine and §3.4 event processing).
- **RFC 1071** — Computing the Internet Checksum (one's-complement sum algorithm and the pseudo-header concept).
- **RFC 7323** — TCP Extensions for High Performance (Window Scale, Timestamps, and PAWS, which extend the handshake options).
- **RFC 6528** — Defending against Sequence Number Attacks, mandating cryptographically unpredictable ISNs.
- **RFC 1323** — TCP Extensions for High Performance (the original Window Scale/Timestamps spec, obsoleted in parts by RFC 7323).
- **RFC 6691** — TCP Options and Maximum Segment Size, clarifying how MSS interacts with the Data Offset / options length.
- W. Richard Stevens, Bill Fenner, Andrew Rudoff, *UNIX Network Programming, Volume 1*, 3rd ed., Chapters 2 and 7 (socket states and the TIME_WAIT discussion).
- Kevin R. Fall, W. Richard Stevens, *TCP/IP Illustrated, Volume 1*, 2nd ed., Chapter 13–14 (TCP connection establishment and timeout/retransmission with traces).
- Shimomura's account of the 1994 Mitnick attack — the canonical ISN-prediction incident that motivated RFC 1948 / RFC 6528.
