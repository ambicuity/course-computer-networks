# Protocol Trace Portfolio

> A working portfolio of annotated packet traces, request/response timings, and a reusable annotation framework that proves you can read traffic the way a real network engineer does. This capstone stitches together Phases 02-13 (the physical medium, Ethernet framing, IP addressing, TCP mechanics, DNS resolution, HTTP semantics, and TLS) into one set of trace artifacts you can use to debug any production service. You will run `code/main.py` to parse a synthetic multi-layer trace, generate a layer-by-layer annotation, and compute handshake, request-response, and tear-down timings that mirror what Wireshark and `tcpdump` report. The deliverable is a self-contained trace report under `outputs/`, paired with the diagram in `assets/protocol-trace-portfolio.svg`.

**Type:** Capstone
**Languages:** Python, Wireshark/tshark output, Markdown
**Prerequisites:** Phases 02-08 (physical, Ethernet, IPv4, TCP, UDP), Phase 12 (DNS, HTTP, TLS basics), Phase 17 (integrated troubleshooting workflow)
**Time:** ~180 minutes

## Learning Objectives

- Annotate a captured or synthetic packet trace across Ethernet, IPv4, TCP/UDP, and the application layer, naming every field that matters for troubleshooting.
- Compute TCP three-way handshake time, request-response RTT, and tear-down latency directly from packet timestamps.
- Distinguish a normal protocol exchange from a degraded one using only the per-layer state you can see in a trace (SYN retransmit, duplicate ACK, zero window, RST).
- Build a reusable trace report template with clear "what good looks like" rows for each protocol stage.
- Map a single user-visible symptom to a hypothesis list ordered by layer, then design the smallest trace that would confirm or reject each one.
- Produce an interview-grade artifact: one Markdown trace report, one annotated pcap excerpt, one timing analysis, and one diagram.

## The Problem

A user reports "the dashboard is slow." A junior engineer opens a browser, hits refresh three times, declares the database slow, and the next two hours get spent arguing about indexes. The senior engineer takes a 30-second `tcpdump`, sees three duplicate ACKs in the trace, points at the Wi-Fi driver, and the issue is closed before lunch. The difference is the ability to read a packet trace like a sentence — to know what the SYN, ACK, FIN, RST, retransmission, zero window, and out-of-order flag are telling you, layer by layer, byte by byte.

Every other lesson in the course has taught a single mechanism. This capstone asks you to prove that you can combine those mechanisms into a working diagnosis. A protocol trace portfolio is a curated set of annotated captures that you have personally read, written up, and understood. It is the artifact a hiring manager or an on-call lead will ask for when they want to know if you can debug. The portfolio is also the right place to consolidate the layered model: each layer leaves its own evidence in a trace, and a portfolio is the proof that you can move between layers without losing the thread.

## The Concept

### What "evidence" means at each layer

A trace is more than a list of bytes. It is layered evidence, and the order matters. The physical layer (Phase 02) leaves evidence in link-state counters, signal-to-noise ratios, and interface statistics. The data-link layer (Phase 06) leaves evidence in MAC addresses, EtherType fields, and frame check sequences. The network layer (Phase 09) leaves evidence in IP headers, TTL, identification, fragmentation, and the address pair. The transport layer (Phase 11) leaves evidence in port numbers, sequence and acknowledgment numbers, flag bits, window size, and the timing between packets. The application layer (Phase 12) leaves evidence in DNS query/response contents, HTTP request/response lines and headers, and TLS version and cipher suite negotiation.

A good trace report never reports a single layer in isolation. It threads the evidence from frame 1 to the application payload. The synthetic trace in `code/main.py` has nine packets covering a full HTTP transaction. Every packet has all four layer headers populated, plus an annotation pointing at the field that is interesting.

### The TCP state machine as a story

The trace tells a story about the TCP state machine, and the timings between packets let you read the path. Packet 1 at `t=0.000` is a SYN from client to server. Packet 2 at `t=0.015` is a SYN-ACK from server to client. The 15-millisecond gap is the *server-side* round-trip: the SYN traveled one way, the server received it, the kernel scheduled the SYN-ACK, and the SYN-ACK traveled back. A 15 ms gap is consistent with a low-latency metro Ethernet or a fiber link in the same region; a 250 ms gap would point at a long-haul link or a congested buffer.

Packet 3 at `t=0.016` is the final ACK from the client, completing the three-way handshake. The 1 ms gap between packets 2 and 3 is purely client-local. Packet 4 at `t=0.020` carries the HTTP GET. The 4 ms gap from handshake completion to the GET is application "think time" — the first place a slow application shows up. Packet 5 at `t=0.080` is the HTTP 200 OK response, 60 ms after the GET. Packet 7 at `t=0.100` is the client's FIN; packets 8-9 are the server's FIN-ACK and the final ACK. The connection goes into TIME_WAIT, which is what RFC 9293 specifies for a clean close.

### Reading the retransmission, the duplicate ACK, and the zero window

Three failure markers are the bread and butter of trace reading. A *retransmission* is a packet with a sequence number identical to a packet sent earlier that has not been acknowledged. It is the strongest single signal of loss: the sender has waited a retransmission timeout (typically 1 s on Linux) and given up. The trace shows the original packet, then a gap equal to the RTO, then the retransmit with the same sequence number.

A *duplicate ACK* is sent by the receiver when it gets an out-of-order segment. Three duplicate ACKs in a row trigger *fast retransmit* on the sender: the sender retransmits the missing segment immediately, before the RTO expires.

A *zero window* is announced by the receiver when its buffer is full. The sender stops, periodically sends a window probe, and waits for the receiver to advertise a non-zero window when the application drains the buffer. A trace that shows the window dropping, holding at 0, then climbing back up is a textbook case of an application that reads data too slowly.

### DNS as the gateway to the trace

Before the TCP three-way handshake can even start, the client usually has to do a DNS lookup. The trace in `code/main.py` includes a short DNS prelude so the portfolio covers the full path. NXDOMAIN, SERVFAIL, and a long DNS RTT each tell different stories. The portfolio should include one annotated DNS trace alongside the HTTP trace so you can show: name → address → SYN → SYN-ACK → ACK → GET → 200 → FIN → FIN-ACK → ACK.

### What the diagram shows

The diagram in `assets/protocol-trace-portfolio.svg` lays out the trace as a sequence diagram: client on the left, server on the right, nine arrows for nine packets, with the timestamps, the per-packet sequence and acknowledgment numbers, and the TCP state transitions. Read left-to-right, top-to-bottom, and the trace tells the same story as the annotated output of `code/main.py`. The diagram is a teaching aid, not a replacement for the trace: in production you read the actual capture, and the diagram is the cleaned-up version you put in a post-incident report.

## Build It

1. **Read `code/main.py`.** It defines dataclasses for Ethernet, IPv4, TCP, UDP, HTTP, and DNS messages, a `Packet` type that nests all four layers, and an `annotate()` function that walks the layers and prints a human-readable summary.
2. **Run it:** `python3 code/main.py`. Confirm the printed annotation lists the DNS prelude, the nine HTTP transaction packets, and the SYN-retransmit failure case.
3. **Inspect `annotate()`.** Note the dispatch on `isinstance(p.tr, TCP)` versus UDP, and the optional `HTTP` / `DNS` message that adds application-layer context.
4. **Add a per-packet RTT field.** Compute and display the time delta from the matching data packet for each ACK packet. This is the trace timing analysis you would do by hand with Wireshark's "Follow TCP Stream" view.
5. **Inject a failure case.** Modify `build_retransmission_trace()` to also produce a three-duplicate-ACK trace.
6. **Capture a real trace.** Use `tshark -i any -w portfolio.pcap` while you load a real page over HTTP. Open the capture, find the three-way handshake, and write a one-paragraph annotation per packet.
7. **Build the portfolio.** Compose `outputs/trace-report-portfolio.md` from three sections: a synthetic trace, a real trace, and a failure-mode runbook.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Annotate a trace | Per-layer header dump with bytes-to-meaning commentary | Every byte of every header is named; no field is left as "..." |
| Compute handshake time | `t_syn_ack - t_syn` from packet timestamps | 1-50 ms on a metro path; longer values point at long-haul or buffer |
| Read TCP flags | SYN, SYN-ACK, ACK, FIN, FIN-ACK, RST in order | Flags match the state machine; retransmits and duplicate ACKs are flagged |
| Diagnose a retransmission | Two packets with identical `seq` and a gap ≥ RTO | Annotate original packet, RTO gap, and retransmit; identify the missing ACK |
| Diagnose a slow path | RTT, handshake time, and segment spacing from timestamps | 60 ms RTT on a transcontinental link is fine; 600 ms is the buffer |
| Distinguish DNS, TCP, TLS, HTTP errors | Capture starts at the failing layer; error message in payload | NXDOMAIN ends the trace before the SYN; cert error ends it during TLS |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/trace-report-portfolio.md` — a Markdown report with three sections: synthetic trace (output of `code/main.py`), real trace (your annotated tshark capture), and a failure-mode runbook covering SYN retransmit, three duplicate ACKs, and zero window.
- `outputs/annotated-pcap.md` — a per-packet annotation of one real capture, using the same per-layer format as the synthetic trace.
- `outputs/timing-analysis.md` — a single table that lists handshake time, GET-to-200 RTT, FIN-to-final-ACK, and total session time, with a one-sentence interpretation of each.
- `outputs/portfolio-index.md` — a top-level index of the portfolio, listing every artifact and pointing at the diagram.

The deliverable is the *set* of artifacts, not any single one. The trace report proves you can read; the timing analysis proves you can measure; the runbook proves you can teach; the index proves you can organize.

## Exercises

1. **Reverse-engineer a fresh trace.** Capture `curl -v http://example.com/ -o /dev/null` with `tshark -i any -w mystery.pcap` running in another shell. Find the SYN, the SYN-ACK, the GET, the 200, and the FIN. Compute the handshake time, the request-response RTT, and the tear-down time. Compare to `code/main.py`'s synthetic numbers and explain any difference.
2. **Inject a failure mode.** Add a synthetic trace of an RTO-based SYN retransmit: packet 1 is a SYN at `t=0.000`, packet 2 is a SYN retransmit at `t=1.000`, packet 3 is a SYN-ACK at `t=1.020`, packet 4 is a final ACK at `t=1.021`. Print the trace and explain what the RTO-based retransmission tells you about the path.
3. **Three duplicate ACKs.** Build a synthetic trace where packet 5 (the server's response) is lost, packets 6-8 are the client's three duplicate ACKs, and packet 9 is the server's retransmit. Annotate it and explain why three duplicate ACKs trigger fast retransmit.
4. **Zero window.** Build a synthetic trace where the receiver's window drops to 0, then climbs back to 1024 over five subsequent ACK packets. Annotate the trace and explain the interaction between the application layer's read rate and the receiver's advertised window.
5. **DNS as the first step.** Add a DNS section to the trace: a query for `example.com A` returning `93.184.216.34` with a 5 ms RTT, then `AAAA` returning the IPv6 address, then `MX` returning `10 mail.example.com`.
6. **Tear the trace apart by layer.** Take the output of `code/main.py` and write a one-paragraph interpretation per packet from the *application* layer's perspective and from the *transport* layer's perspective.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Trace | "the pcap" | A timestamped sequence of bytes captured at a single observation point; the raw evidence layer-1 through layer-7 leave behind |
| Annotation | "comments on packets" | A per-packet walk through the headers and payload, naming each field and what it tells you about the path |
| Three-way handshake | "SYN, SYN-ACK, ACK" | The TCP state transition that establishes a connection; timing between the three packets is the path round-trip |
| Retransmission | "the same packet twice" | A copy of an earlier segment sent after a retransmission timeout, signaling loss |
| Duplicate ACK | "an ACK with no new data" | A signal that the receiver got an out-of-order segment; three in a row trigger fast retransmit |
| Zero window | "the receiver paused" | The receiver's TCP window field has dropped to 0, telling the sender to stop transmitting |
| RTO | "retransmit timeout" | The time a sender waits for an ACK before retransmitting; doubles after each loss on most kernels |
| cwnd | "congestion window" | The sender's estimate of how much data the network can carry; grows on success, shrinks on loss |
| TIME_WAIT | "the 2*MSL wait" | The state a socket enters after a clean close, holding for 2*MSL (typically 60 s) |
| Follow TCP Stream | "Wireshark's reassemble" | A Wireshark feature that reassembles a TCP connection's bytes into a single application-layer view |

## Further Reading

- **RFC 9293** — Transmission Control Protocol (the modern TCP specification that supersedes RFC 793).
- **RFC 3168** — The Addition of Explicit Congestion Notification (ECN) to IP, the second-most-common congestion signal after loss.
- **Wireshark display filter reference** — the canonical list of `tcp.flags.syn`, `tcp.analysis.retransmission`, `tcp.analysis.duplicate_ack`, and `tcp.window_size_value == 0` filters.
- **tshark man page** — the CLI counterpart to Wireshark, used to capture and filter traffic in scripts.
- **Tanenbaum & Wetherall, *Computer Networks*, 5th ed.**, Chapters 4-5 for the layered model this portfolio instantiates.
