# UDP Service, Datagram Format, and Checksum

> UDP is the "do almost nothing" transport. RFC 768 defines just eight header bytes: a 16-bit source port, a 16-bit destination port, a 16-bit length (header + payload, minimum 8), and a 16-bit checksum that is *optional* in IPv4 (mandatory in IPv6 per RFC 8200). UDP adds *no* sequencing, no retransmission, no flow control, no congestion control, and no connection state — it is a thin wrapper around IP that gives the application a port-multiplexed channel and a weak end-to-end integrity check. That minimalism is the design. A 30-line kernel module that delivers each datagram independently is what lets DNS (RFC 1035), NTP (RFC 5905), QUIC (RFC 9000), RTP (RFC 3550), and gaming protocols ship packets at line rate with microseconds of stack cost. The trade-off is honesty: applications must implement reliability, ordering, congestion control, and connection management on top — and most famously they forget to do it correctly, leading to a long list of UDP-based vulnerabilities and the never-ending "but UDP is faster" myth. This lesson dissects the header, the checksum (the famous "carry bit around" one's-complement sum), the IPv4 pseudo-header, and the difference between *transport checksum* (detects bit errors in flight) and *application checksum* (validates protocol semantics).

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 10 lessons 02 (transport service primitives), 08 (error control); familiarity with IPv4 header layout
**Time:** ~60 minutes

## Learning Objectives

- Lay out the 8-byte UDP header field-by-field with exact byte offsets and read a real datagram's source/destination ports, length, and checksum.
- Compute the **UDP checksum** by hand: build the IPv4 pseudo-header, append the UDP header + payload, pad to even length, sum 16-bit words with end-around carry, and take the one's complement.
- Distinguish the cases where the checksum is **disabled** (IPv4 sender's choice) vs. **mandatory** (IPv6 RFC 8200, RFC 6935/6936 for tunneled IPv4-in-IPv6) vs. **forced to zero** (jumbograms).
- Compare UDP's contract against TCP's: no retransmission, no ordering, no flow control, no congestion control, and identify the *one* thing UDP adds that raw IP does not (port demultiplexing + weak integrity).
- Implement a small UDP datagram parser and a one-shot sender that exercises checksum on, off, and intentionally corrupt for testing.

## The Problem

A junior engineer is debugging "intermittent packet loss" in a video streaming system. Logs show every UDP datagram from the encoder to the relay, but the receiver periodically glitches and the engineer cannot tell whether the packets were lost, reordered, duplicated, or corrupted. The encoder uses a custom packet format; the relay re-broadcasts over a lossy Wi-Fi link. The bug is that the encoder set `checksum=0` (a valid choice in IPv4!) and the relay re-encodes without recomputing it. The receiver's UDP stack accepts everything, but the *content* of some packets is silently wrong.

Lesson: UDP's checksum is the only integrity check on the wire. If you disable it, you opt out of bit-error detection for the *entire* path. If you re-encode, you must re-checksum. The lesson is a hands-on tour of the header and a strict, stdlib-only checksum implementation you can drop into any UDP code path.

## The Concept

UDP is one of the simplest protocols in the stack. The SVG shows the header layout and the checksum coverage; `code/main.py` parses and generates real datagrams.

### The 8-byte header

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Source Port          |       Destination Port        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Length               |          Checksum              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                       Payload (variable)                      |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Notes |
|---|---|---|
| Source Port | 16 bits | Optional for one-way datagrams; the receiver can reply to a different port if 0 |
| Destination Port | 16 bits | The well-known port for the service (53 = DNS, 123 = NTP, 443 = QUIC) |
| Length | 16 bits | Header + payload; minimum 8 (no payload), maximum 65535 |
| Checksum | 16 bits | 0 in IPv4 means "not computed"; mandatory in IPv6 (RFC 8200) |

Total: 8 bytes. That's the entire fixed header. No sequence number, no flags, no options, no SACK ranges. UDP has no notion of "the next datagram" or "the previous one" — each one is independent.

### The IPv4 pseudo-header

The UDP checksum is computed over a **pseudo-header** that prepends a few fields from the IP layer:

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Source IPv4 address                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  Destination IPv4 address                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      zero     |  protocol (17) |     UDP length (header+data) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

For IPv6 the pseudo-header is similar but with a 16-bit payload length (RFC 8200 §8.1). Including IP addresses in the checksum means a misrouted datagram (wrong destination IP) will fail the checksum at the receiver, which RFC 1122 §4.1.3.4 calls "must." It is the one piece of end-to-end integrity the IP layer silently provides through UDP.

### Computing the checksum

The algorithm is the **one's-complement sum**, with end-around carry, of all 16-bit words in the pseudo-header + UDP header + payload:

1. Build a buffer: pseudo-header (12 bytes for IPv4) + UDP header (8 bytes, with checksum field set to 0) + payload. Pad with a zero byte if the total is odd.
2. Sum all 16-bit words as unsigned 32-bit integers. After every addition, fold the high 16 bits of the accumulator into the low 16 bits.
3. Take the one's complement of the final 32-bit accumulator (after folding) and use that as the checksum.
4. **Self-consistency check**: a correctly-built datagram has the property that the sum of *all* 16-bit words (including the checksum field) is `0xFFFF` (or `0x0000` for the all-zero case). The receiver uses this to validate.

The "fold high 16 into low 16" step is the famous "wraparound carry." The reason UDP uses one's-complement rather than two's-complement is historical (1's complement was a first-class concept on the IMP and early Internet); modern processors don't care, but the algorithm is preserved because the protocol bits are fixed.

### What the checksum actually detects

The 16-bit checksum catches all **single-bit errors**, all **odd-number-of-bit errors**, and most (but not all) even-number-of-bit errors. A burst error of 16 bits that exactly cancels the checksummed sum can slip through. CRC-32 (Ethernet) and TCP's stronger 16-bit ones'-complement sum are more robust; UDP's checksum is intentionally lightweight because UDP was designed to live on top of an IP layer that already had a *header* checksum (in IPv4) and the assumption that the link layer (Ethernet, Wi-Fi) catches most errors. RFC 6935 and 6936 later strengthened the IPv6 case to make the UDP checksum mandatory, after researchers showed that under IPv6 it is *not* safe to disable.

### UDP vs TCP: the real comparison

| Property | UDP | TCP |
|---|---|---|
| Header bytes | 8 | 20-60 |
| Connection state | none | explicit FSM (11 states) |
| Sequencing | none | bytestream with cumulative ACK |
| Retransmission | none | yes, RTO-driven |
| Flow control | none | sliding window |
| Congestion control | none | AIMD / CUBIC / BBR |
| Port multiplexing | yes | yes |
| Integrity | 16-bit checksum (optional IPv4) | 16-bit checksum (mandatory) |
| Maximum message | 65535 bytes (minus IP/UDP overhead) | unlimited bytestream |
| Throughput limit | application-bound | congestion-bound |
| Latency floor | microseconds | RTT-driven |

The right framing: UDP is not "faster than TCP" in any absolute sense — they have different *contracts*. UDP promises "best-effort delivery of a single message." TCP promises "reliable, in-order, flow-controlled, congestion-controlled bytestream." Applications choose based on the contract they need.

### When the checksum is "0" (disabled)

A sender may set the UDP checksum field to `0x0000` in IPv4 to mean "I am not computing the checksum." The receiver, on seeing a zero checksum in IPv4, must accept the datagram without integrity verification. This is occasionally used in:

- **High-speed trading** where every microsecond matters and the underlying network is a known-good fiber with a stronger layer-2 CRC.
- **Bulk video** where corruption shows up as decoder errors and application-layer FEC handles it.
- **Tunneled traffic** that wraps UDP inside another UDP — the outer checksum is the inner payload and may be computed at a different layer.

In IPv6 the checksum is mandatory and cannot be zero (except for jumbograms, RFC 2675, which use a different length field). RFC 6936 specifies a way to tunnel IPv4-in-IPv6 such that the inner UDP checksum of zero is preserved as a deliberate signal rather than being interpreted as a real value.

### Why UDP is not "lossy" — it is "best-effort"

UDP *delivers* every datagram that arrives; the network may *drop* some. The difference matters: TCP *promises* delivery; UDP does not. The retransmission, ordering, and dedup work that TCP does on your behalf you have to do yourself — and if you do it badly, your UDP-based protocol will be worse than TCP, not better. The point of UDP is that *you* get to choose what reliability means: a 16-byte query has different reliability needs than a 5 GB file copy.

## Build It

`code/main.py` is a stdlib-only UDP toolkit with three parts.

1. **`udp_checksum(src_ip, dst_ip, payload, proto=17)`** — computes the IPv4 pseudo-header checksum and returns the 16-bit value plus a self-consistency validator.
2. **`parse_udp(data)`** — slices a raw IP-payload byte string into source port, dest port, length, checksum, and payload; flags truncated or zero-checksum datagrams.
3. **`build_udp(src_port, dst_port, payload, src_ip, dst_ip, want_checksum=True)`** — assembles a valid UDP datagram with the correct length and checksum, including a "deliberately corrupt" mode for testing the parser.

Run `python3 code/main.py`. The demo parses three datagrams: a normal one, a zero-checksum one, and a deliberately corrupted one. It also walks through a checksum calculation step by step so you can match it against Wireshark.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Parse a UDP datagram | Hex bytes from Wireshark | You extract src/dst port, length, checksum, payload without confusion |
| Compute a checksum | `udp_checksum()` output | Matches Wireshark's "udp.checksum" field byte-for-byte |
| Detect corruption | Self-consistency check | Sum of all 16-bit words == 0xFFFF; mismatch means corruption or wrong pseudo-header |
| Decide checksum on/off | IPv4 vs IPv6 | IPv4: optional; IPv6: required; tunneled IPv4-in-IPv6: see RFC 6936 |
| Compare with TCP | Header size, contract | UDP = 8 bytes, no contract; TCP = 20+, bytestream with contract |

`tshark -V -i lo0` shows the checksum for every UDP datagram. Compare its output against `udp_checksum()` to verify the implementation.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **UDP header cheat sheet** with the 4 fields, the IPv4 pseudo-header, and the checksum self-consistency rule.
- A **checksum step-by-step** walkthrough for a 12-byte payload, showing the carry fold at each step.
- A **UDP vs TCP decision table** for common protocols: DNS, NTP, QUIC, RTP, video streaming, gaming.
- The **datagram parser/generator** (`code/main.py`) wired to your own captures.

Start from `outputs/prompt-udp-services-datagram-format-and-checksum.md`.

## Exercises

1. Build a UDP datagram with `src_port=53000`, `dst_port=53`, payload `b"hello"`. Compute the checksum. Now change the source IP from `10.0.0.1` to `10.0.0.2` and re-checksum. What changes? Why?
2. Receive the datagram from exercise 1, set checksum to 0, and re-send. Does the receiver's Wireshark mark it as "checksum zero" or "checksum good"? What does each mean?
3. Compute the checksum for a 7-byte payload. Why does the algorithm need to pad with a zero byte? What would happen without padding?
4. A UDP datagram has length field `0x0008`. What does the receiver conclude? What if the actual bytes after the header are 100 bytes long?
5. Implement a simple "echo over UDP" loop: bind to port 7777, recv 5 datagrams, echo each back with a fresh checksum. Then change the checksum field to zero on the echo and see what Wireshark reports.
6. The UDP checksum self-consistency rule: sum of all 16-bit words including checksum field == 0xFFFF. Prove it. Then prove that flipping a single bit in the payload breaks the rule.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| UDP | "the connectionless transport" | RFC 768: 8-byte header, no state, no retransmit, no ordering; an IP packet with a port number |
| Datagram | "a message" | A self-contained UDP message: a single sendto() maps to a single recvfrom() at the peer |
| Pseudo-header | "the IP part of the checksum" | Source/destination IP + protocol + UDP length, prepended for checksum computation; not transmitted |
| One's-complement sum | "the checksum algorithm" | 16-bit words summed with end-around carry; RFC 1071 describes the folding trick |
| End-around carry | "wrap the high bits" | When the 16-bit sum overflows, add the high 16 bits back into the low 16 bits |
| Checksum disabled | "0x0000" | In IPv4, a zero checksum means the sender did not compute one; receiver must accept the datagram |
| Checksum mandatory | "RFC 8200" | In IPv6, the UDP checksum cannot be zero (except jumbograms, RFC 2675) |
| Length field | "header + payload" | UDP length counts the header; minimum 8 (no payload), maximum 65535 |
| Jumbogram | "huge datagram" | RFC 2675: IPv6 hop-by-hop option to extend payload past 65535 bytes; uses a different length field |
| Connectionless | "no handshake" | A UDP socket is a port; any peer can send to it; no 3-way handshake, no FIN |

## Further Reading

- **RFC 768** — *User Datagram Protocol* (Postel, 1980), the 3-page original. Read it cover to cover; the protocol is shorter than this section.
- **RFC 1071** — *Computing the Internet Checksum* (Braden, Andersen, Paxson, 1988), the algorithm reference.
- **RFC 1122** — *Requirements for Internet Hosts*, §4.1.3.4 (UDP checksums), the host-side MUST/SHOULD.
- **RFC 6935** — *IPv6 and UDP Checksums for Tunneled Packets* (2013), why the IPv6 mandate matters when tunneling.
- **RFC 6936** — *Applicability Statement for the Use of IPv6 UDP Datagrams with Zero Checksums* (2013), the explicit zero-checksum exception.
- **RFC 8085** — *UDP Usage Guidelines* (2017), modern guidance for application designers (message size, fragmentation, concurrent use).
- **RFC 8200** — *Internet Protocol, Version 6 (IPv6) Specification* (2017), §8.1 IPv6 pseudo-header.
- Stevens, *UNIX Network Programming* (3rd ed.) vol. 1, ch. 8 — the practical BSD-socket UDP reference.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.4 "Connectionless Transport: UDP."
- Kurose & Ross, *Computer Networking* (8th ed.), §3.3 "Connectionless Transport: UDP."
