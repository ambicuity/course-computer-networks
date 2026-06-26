# Trace Annotation Runbook

> A packet trace is raw evidence; an *annotated* trace is a diagnosis. This runbook turns a `.pcap` into a layer-by-layer narrative: which frame carried the SYN, when the SYN-ACK arrived, whether the three-way handshake completed within the OS retransmission timer (typically 1s initial RTO per RFC 6298, doubling on loss), where TCP fast-retransmit (3 duplicate ACKs, RFC 5681) or a TLS `Alert` killed the session, and what the DNS `A`/`AAAA` round-trip cost. You will learn the canonical Wireshark display filters (`tcp.analysis.retransmission`, `dns.time`, `tcp.flags.syn==1 && tcp.flags.ack==0`), the meaning of expert-info flags, and how to compute relative time deltas so a "the site is slow" ticket becomes "TLS ClientHello was sent at t=0.412s, ServerHello at t=1.690s — a 1.28s server-side stall." The deliverable is a reproducible annotation script (`code/main.py`) that parses a captured trace's exported fields and emits a timeline plus a verdict, so the diagnosis is mechanical, not guesswork.

**Type:** Build
**Languages:** Wireshark, Markdown, Python (stdlib)
**Prerequisites:** Phase 0 lessons on the link/IP/TCP layers, basic `tcpdump`/Wireshark capture, the four-layer TCP/IP model
**Time:** ~90 minutes

## Learning Objectives

- Convert a raw `.pcap` into a per-packet annotated timeline that names the layer, protocol, and role of each frame (handshake, data, ACK, teardown, retransmission).
- Write and apply the display filters that isolate the TCP three-way handshake, retransmissions, zero-window events, DNS latency, and TLS records, and explain what each filter selects.
- Compute relative time deltas between key packets to quantify round-trip time, server "think time," and retransmission timeouts instead of describing latency qualitatively.
- Read Wireshark's expert-info classes (Chat, Note, Warning, Error) and map `tcp.analysis.*` flags to concrete TCP state-machine events.
- Produce a one-page runbook artifact that anyone on the team can follow to reduce a vague symptom to packet-level evidence.

## The Problem

A user files a ticket: "the dashboard takes forever to load, sometimes it just spins." You have a 4,000-packet capture taken at the user's machine. Scrolling the packet list tells you nothing — it is a wall of black-and-white rows. Was it DNS? A dropped SYN that waited a full RTO before retrying? A TLS negotiation stall? A server that advertised a zero window and froze the sender? Packet loss triggering fast retransmit? Each of those leaves a *different* signature in the trace, and each points at a *different* owner (resolver, network path, server, application). Without a disciplined annotation pass you will either guess wrong or escalate the whole capture to someone else. This runbook gives you a fixed sequence of filters and time computations that always converges on the responsible layer.

## The Concept

### The annotation pipeline

Annotation is a fixed four-pass sweep over the same trace. Each pass narrows the suspect set. The SVG (`assets/trace-annotation-runbook.svg`) shows this as a funnel from raw capture to verdict.

```text
raw .pcap
   |  pass 1: orient    -> Conversations + name resolution + protocol hierarchy
   v
suspect flow (one 5-tuple)
   |  pass 2: handshake  -> SYN / SYN-ACK / ACK timing, RTT baseline
   v
established session
   |  pass 3: anomalies  -> retransmissions, dup-ACKs, zero-window, resets
   v
quantified fault
   |  pass 4: time math   -> deltas between named packets => server vs network
   v
verdict + evidence
```

`code/main.py` automates passes 2-4 from a CSV the user exports out of Wireshark (`File > Export Packet Dissections > As CSV`).

### Pass 1 — orient with the right summary views

Before reading individual packets, collapse the trace. `Statistics > Conversations` shows every 5-tuple (src IP, src port, dst IP, dst port, protocol) with byte and packet counts; the heaviest or the most-retransmitted conversation is usually the suspect. `Statistics > Protocol Hierarchy` tells you in seconds whether this is TLS-over-TCP, plaintext HTTP, QUIC-over-UDP, or DNS-dominated. Enabling **name resolution** (`View > Name Resolution > Resolve Network Addresses`) turns `93.184.216.34` into `example.com` so you can see *which* server stalled.

### Pass 2 — the three-way handshake and the RTT baseline

The TCP handshake is your latency yardstick. The relevant flag bits live in byte 13 of the 20-byte TCP header:

| Packet | Flags set | Display filter | Meaning |
|---|---|---|---|
| 1. SYN | SYN=1, ACK=0 | `tcp.flags.syn==1 && tcp.flags.ack==0` | Client opens, picks ISN, advertises MSS/WScale/SACK options |
| 2. SYN-ACK | SYN=1, ACK=1 | `tcp.flags.syn==1 && tcp.flags.ack==1` | Server accepts, sends its ISN |
| 3. ACK | SYN=0, ACK=1 | `tcp.flags.syn==0 && tcp.flags.ack==1` | Client confirms; connection ESTABLISHED |

The delta `t(SYN-ACK) − t(SYN)` is your **network RTT baseline**. Every later "think time" is measured against it. If the SYN appears, then reappears ~1s later with the same sequence number before any SYN-ACK, the first SYN was lost on the path and the client waited a full initial RTO (RFC 6298 recommends 1s) — that is a *network* fault, not a server one. A worked example: SYN at t=0.000s, no reply, SYN retransmit at t=1.002s, SYN-ACK at t=1.060s. The user paid ~1.06s for connection setup, ~1.0s of it pure retransmission timeout from one lost packet.

### Pass 3 — anomaly filters and what each one proves

Wireshark's TCP analysis engine flags problems by comparing sequence/ack numbers across the flow. The most load-bearing filters:

| Filter | Selects | What it proves |
|---|---|---|
| `tcp.analysis.retransmission` | A segment whose data was already sent | Loss or excessive RTO somewhere on the path |
| `tcp.analysis.fast_retransmission` | Retransmit triggered by 3 dup-ACKs | Single-packet loss with later data arriving (RFC 5681) |
| `tcp.analysis.duplicate_ack` | Repeated ACK of the same seq | Receiver got out-of-order data; loss before this point |
| `tcp.analysis.zero_window` | Advertised window = 0 | Receiver's buffer is full — the *application* is not reading |
| `tcp.analysis.window_update` | Window reopened after zero | How long the stall lasted: `t(update) − t(zero_window)` |
| `tcp.flags.reset==1` | RST bit set | Abrupt teardown — refused port, firewall, or app crash |

A **zero-window** event is diagnostic gold: the network and TCP are healthy, but the receiving application stopped draining its socket buffer. The sender is *forbidden* from sending until a window update arrives. If the gap is 8 seconds, you have found 8 seconds of pure application-side stall, and no amount of network tuning will fix it.

### Pass 4 — time math turns symptoms into numbers

Qualitative latency ("slow") is useless in a ticket. Compute deltas between named packets. For an HTTPS request the canonical breakdown is:

```text
t0  DNS query sent
t1  DNS response (A/AAAA)        -> resolver time   = t1 - t0
t2  TCP SYN
t3  TCP SYN-ACK                  -> network RTT      = t3 - t2
t4  TLS ClientHello
t5  TLS ServerHello + cert       -> TLS+server setup = t5 - t4
t6  HTTP request (first app byte)
t7  HTTP response first byte     -> server think     = t7 - t6
```

If `t7 − t6` dominates, the application/server is slow. If `t3 − t2` dominates and there was a SYN retransmit, blame the path. If `t1 − t0` is large, blame the resolver. `code/main.py` performs exactly this attribution and prints which phase owns the latency. Wireshark exposes `dns.time` and `http.time` as ready-made fields so you do not even have to subtract by hand for those two.

### Reading expert info

`Analyze > Expert Information` groups annotations by severity: **Chat** (normal: SYN, FIN, window update), **Note** (recoverable: duplicate ACK, retransmission), **Warning** (suspicious: zero window, previous-segment-not-captured), **Error** (malformed: bad checksum, truncated). Scanning Warnings and Errors first is a fast triage; a flood of "Previous segment not captured" usually means *your capture* dropped packets, not the network — fix the capture before trusting the trace.

### Annotating the frame, not just the packet

Good annotation names every layer of one representative packet, top to bottom: Ethernet II frame (14-byte header: 6-byte dst MAC, 6-byte src MAC, 2-byte EtherType `0x0800` for IPv4), the 20-byte IPv4 header (TTL, protocol=6 for TCP, header checksum), the TCP header (ports, 32-bit seq/ack, flags, 16-bit window), then the payload. This proves you can place the symptom at the correct layer — a TTL of 1 in a reply, for instance, is a routing/`traceroute` artifact, not an application bug.

## Build It

1. Capture or open a `.pcap`. For a clean reference trace, run `tcpdump -i any -w trace.pcap host example.com` while loading the page, then stop.
2. Run the four passes above in Wireshark. Note the suspect 5-tuple, the RTT baseline, and any anomaly flags.
3. Export the suspect flow: apply a filter for the conversation, then `File > Export Packet Dissections > As CSV`, including the columns `frame.number,frame.time_relative,ip.src,ip.dst,tcp.srcport,tcp.dstport,tcp.flags,info`.
4. Run `python3 code/main.py` — it ships with a built-in sample trace, so it works with no arguments and prints an annotated timeline plus a verdict.
5. Replace the sample with your own exported rows and re-run to attribute *your* latency.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Find the suspect flow | Conversations + Protocol Hierarchy | One 5-tuple named, with its packet/byte share and retransmit count |
| Establish RTT baseline | `t(SYN-ACK) − t(SYN)` | A number in ms you can compare every later delta against |
| Detect a lost SYN | Duplicate SYN before any SYN-ACK | You can say "~1s of the setup was pure RTO, network fault" |
| Detect app-side stall | `tcp.analysis.zero_window` + `window_update` | Gap quantified; verdict points at the receiver application |
| Attribute total latency | Phase deltas (DNS / RTT / TLS / server think) | One phase named as the dominant cost, with its millisecond figure |

## Ship It

Produce one artifact under `outputs/`:

- A **trace-annotation checklist** (the four passes + their filters) the team can run on any ticket.
- A **filled timeline** for one real capture, with the verdict and the dominant-phase number.

Start from [`outputs/prompt-trace-annotation-runbook.md`](../outputs/prompt-trace-annotation-runbook.md) and paste in your own exported rows.

## Exercises

1. You see SYN at t=0.000, SYN at t=0.998 (same seq), SYN-ACK at t=1.040. Compute the RTT baseline and the setup cost. Who owns the latency, and why is it *not* the server?
2. A flow shows `tcp.analysis.zero_window` at t=2.10s and `tcp.analysis.window_update` at t=10.30s, with no retransmissions. The user reports an 8-second freeze. Write the one-sentence verdict and name the responsible layer.
3. `dns.time` for the lookup is 1.9s; total page-load was 2.3s. Which display filter isolates the DNS exchange, and what is your recommendation to the team?
4. You find three duplicate ACKs for seq 14481 followed by `tcp.analysis.fast_retransmission`. Explain the TCP mechanism being observed and why this recovers faster than waiting for an RTO.
5. Protocol Hierarchy shows 60% "Previous segment not captured" warnings. Before blaming the network, what is the more likely explanation, and how do you confirm it?
6. Export a real capture to CSV and run `code/main.py` on it. Does its computed verdict match your manual annotation? If not, which delta differs and why?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Annotation | "Adding comments to packets" | A disciplined per-layer narrative that reduces a symptom to one responsible layer with a number |
| RTT baseline | "Ping time" | The `SYN-ACK − SYN` delta, measured in-band on the actual flow, used to judge every later delay |
| Retransmission | "A packet sent twice" | A segment whose payload was already transmitted; signals loss or an expired RTO (RFC 6298) |
| Fast retransmit | "Quick resend" | Resend triggered by 3 duplicate ACKs before the RTO fires (RFC 5681), avoiding a full timeout |
| Zero window | "Connection stuck" | Receiver advertised a 0-byte window; its application stopped reading — an app fault, not a network one |
| Expert info | "Wireshark warnings" | Severity-classed annotations (Chat/Note/Warning/Error) mapped to TCP state events |
| Server think time | "It's slow" | `t(first response byte) − t(request byte)` — the part of latency the application owns |

## Further Reading

- RFC 793 / RFC 9293 — Transmission Control Protocol (handshake, state machine, flags)
- RFC 5681 — TCP Congestion Control (fast retransmit / fast recovery, duplicate-ACK threshold)
- RFC 6298 — Computing TCP's Retransmission Timer (initial RTO, backoff)
- RFC 1035 — Domain Names: Implementation and Specification (DNS query/response format)
- RFC 8446 — TLS 1.3 (ClientHello / ServerHello, the 1-RTT handshake)
- IEEE 802.3 — Ethernet framing (14-byte header, EtherType)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Ch. 6 (Transport Layer)
- Wireshark User's Guide — Display Filter Reference and Expert Information chapters
