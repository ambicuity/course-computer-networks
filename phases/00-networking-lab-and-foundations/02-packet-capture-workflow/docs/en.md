# Packet Capture Workflow

> A packet capture is only useful if you can drive the workflow from symptom to evidence to verdict. The chain is: a NIC in promiscuous mode hands frames to the kernel, an in-kernel BPF (Berkeley Packet Filter, compiled by `pcap_compile`) drops everything that does not match your filter *before* it reaches userspace, and libpcap writes the survivors to a `.pcap`/`.pcapng` file. That file is a 24-byte global header (magic `0xa1b2c3d4` for microsecond resolution, `0xa1b23c4d` for nanosecond) followed by per-packet records each prefixed with a 16-byte header carrying `ts_sec`, `ts_usec`, `incl_len`, and `orig_len`. Get the **capture filter** (BPF, in-kernel, lossy, irreversible) versus the **display filter** (Wireshark dissector language, post-capture, reversible) distinction wrong and you either drown in traffic or silently discard the packet you needed. The classic failure modes are snaplen truncation (default 262144, but a stale `-s 96` cuts off TCP payload), drops reported in `tcpdump`'s "N packets dropped by kernel" line, and capturing on the wrong interface so the SYN you are hunting never appears. This lesson builds a stdlib pcap reader so you understand the bytes Wireshark renders, plus a repeatable five-step workflow you can rerun under pressure.

**Type:** Build
**Languages:** Wireshark, tcpdump, Python (stdlib pcap parser)
**Prerequisites:** Phase 00 · 01 (lab setup, interfaces, OSI layering); comfort with hex and the TCP/IP four-layer model
**Time:** ~90 minutes

## Learning Objectives

- Distinguish a **capture filter** (in-kernel BPF, applied before write, irreversible) from a **display filter** (post-capture, reversible), and choose the right one per task.
- Parse the pcap format by hand: the 24-byte global header magic numbers, the 16-byte record header, and the `incl_len` vs `orig_len` fields that reveal snaplen truncation.
- Write a tcpdump capture filter from primitives (`host`, `port`, `tcp`, `net`) and operators (`and`, `or`, `not`) that isolates one conversation without dropping handshake or reset packets.
- Read a three-way handshake (SYN / SYN-ACK / ACK) and a teardown (FIN/ACK or RST) from a trace, and spot retransmissions from duplicate sequence numbers.
- Diagnose the three classic capture defects — snaplen truncation, kernel drops, wrong-interface capture — from file and tool evidence.

## The Problem

A user reports that an internal API call "sometimes hangs for 30 seconds, then works." The application logs show only a generic timeout, the load balancer says the backend is healthy, and the database team says queries are fast. Everyone sees nothing wrong on their own layer, because the failure lives *between* the layers — in the network path — and nothing above the socket can see it.

This is the canonical case for packet capture. The 30-second pause is a fingerprint: it matches a TCP SYN retransmission sequence (Linux `tcp_syn_retries` retries at roughly 1s, 3s, 7s, 15s, 31s — exponential backoff doubling the RTO). Capture on the right interface with the right filter and you *see* the SYN go out, *see* no SYN-ACK return, and *see* the kernel retry on that exact schedule — turning "the network is flaky" into "the firewall silently drops SYNs to port 5432; here are the retransmits and timestamps." The workflow below gets you there reliably instead of by luck.

## The Concept

### The capture chain: from wire to file

A packet does not magically appear in Wireshark. It travels a specific path, and every stage can lose or mangle data:

```text
wire ─▶ NIC (promiscuous) ─▶ kernel ring buffer ─▶ in-kernel BPF (capture filter,
        drops non-matching frames HERE) ─▶ libpcap copies to userspace ─▶
        .pcap/.pcapng on disk ─▶ Wireshark dissectors + display filter
```

Promiscuous mode tells the NIC to keep frames not addressed to its MAC. On a switched network you still see only your own traffic plus broadcast/multicast unless you set up a SPAN/mirror port or a TAP. The in-kernel BPF is the single most important stage: whatever it rejects is gone forever and never written to disk.

### Capture filter vs display filter — the distinction that matters most

These use **different syntaxes** at **different times**. Confusing them is the number-one packet-capture mistake.

| | Capture filter | Display filter |
|---|---|---|
| Syntax | BPF / pcap (`tcp port 443`) | Wireshark (`tcp.port == 443`) |
| Applied | In kernel, before write | After capture, on saved bytes |
| Reversible | No — rejected packets are lost | Yes — just re-filter |
| Where | `tcpdump`, Wireshark "Capture Options" | Wireshark filter bar |
| Use when | Volume is huge; you know the target | Exploring; you might be wrong |

Rule of thumb: **capture wide, display narrow.** Use a capture filter only to keep file size sane (e.g. `host 10.0.0.5` on a busy server), and hunt with display filters so you never accidentally discard evidence. Note the operator difference: BPF uses `tcp port 443`; Wireshark uses `tcp.port == 443`.

### The pcap file format, byte by byte

`code/main.py` parses this format directly. The classic `.pcap` layout:

**Global header (24 bytes), written once:**

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0 | 4 | magic | `a1b2c3d4` (µs) or `a1b23c4d` (ns); byte order detected from this |
| 4 | 2 | version_major | usually 2 |
| 6 | 2 | version_minor | usually 4 |
| 8 | 4 | thiszone | GMT offset, normally 0 |
| 12 | 4 | sigfigs | timestamp accuracy, normally 0 |
| 16 | 4 | snaplen | max bytes captured per packet |
| 20 | 4 | network | link-layer type (1 = Ethernet, 101 = raw IP, 0 = loopback) |

**Per-packet record header (16 bytes), one per packet:**

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0 | 4 | ts_sec | capture time, seconds since epoch |
| 4 | 4 | ts_usec | microseconds (or ns if magic says so) |
| 8 | 4 | incl_len | bytes actually saved in the file |
| 12 | 4 | orig_len | bytes on the wire |

The magic number sets endianness: `0xa1b2c3d4` is host order; `0xd4c3b2a1` means the file was written big-endian and you must byte-swap every field. `code/main.py` does exactly this swap. **When `incl_len < orig_len`, the packet was truncated by snaplen** — this is how you prove "I captured the headers but the tool cut off the payload."

### Reading the TCP three-way handshake in a trace

The handshake is the first thing you look for. Its fingerprint in the flags field is unmistakable:

| # | Direction | Flags | Seq | Ack | Meaning |
|---|---|---|---|---|---|
| 1 | client → server | `SYN` | x | — | "open, my ISN is x" |
| 2 | server → client | `SYN, ACK` | y | x+1 | "ok, my ISN is y, got yours" |
| 3 | client → server | `ACK` | x+1 | y+1 | "got yours, connected" |

If packet 1 repeats with the *same* sequence number at ~1s, 3s, 7s intervals and packet 2 never arrives, the SYN is being dropped on the path (firewall, missing route, dead backend). If you see packet 1, packet 2, then a `RST` instead of `ACK`, the server actively refused. Teardown is `FIN, ACK` from each side (graceful) or a single `RST` (abrupt). The SVG (`assets/packet-capture-workflow.svg`) lays out this chain alongside the capture pipeline.

### Snaplen, drops, and wrong interface — the three defects

Every botched capture is usually one of these:

- **Snaplen truncation.** `tcpdump -s 96` saves only 96 bytes per packet — enough for Ethernet+IP+TCP headers but it amputates payload. Modern tcpdump defaults to a full 262144, but blog-copied commands often carry a stale small snaplen. Evidence: `incl_len < orig_len`.
- **Kernel drops.** When capture cannot keep up, the kernel discards frames and tcpdump prints `"N packets dropped by kernel"` on exit. Evidence: that line, plus sequence-number gaps with no retransmission. Fix: tighten the capture filter, raise the ring buffer (`-B`), or write to fast disk with `-w`.
- **Wrong interface.** Capturing on `eth0` when traffic egresses `eth1`, or on the host when traffic is inside a container/VLAN, yields a file with everything *except* what you want. Evidence: your target host/port never appears. Fix: `tcpdump -D` to list interfaces, or capture on `any`.

### The repeatable five-step workflow

The loop you run under pressure — the operational core of the lesson:

1. **State the symptom as a layer hypothesis.** "30s hang" → "SYN retransmission, layer 4." Predict what the trace should show.
2. **Pick the interface and the narrowest *safe* capture filter.** `tcpdump -i eth1 -s 0 -w hang.pcap host 10.0.0.5 and port 5432`. `-s 0` means full snaplen; keep the filter loose enough to catch RSTs and retransmits.
3. **Reproduce the symptom while capturing**, then stop. Note the wall-clock time of the failure to find it fast.
4. **Open in Wireshark, apply a *display* filter** (`tcp.port == 5432`), follow the stream, read flags and timestamps. Confirm or reject the step-1 hypothesis.
5. **Ship the verdict + evidence.** Export the relevant packets, annotate them, write the one-line conclusion ("firewall drops SYN to 5432; see frames 3–7, RTO doubling 1/3/7s").

## Build It

`code/main.py` is a dependency-free pcap reader and TCP-flag annotator. It synthesizes a valid `.pcap` in memory (global header + Ethernet/IPv4/TCP frames for a failing handshake with a retransmitted SYN and a RST), parses the global header (detecting endianness from the magic), walks every record header, flags any packet where `incl_len < orig_len`, dissects Ethernet → IPv4 → TCP for flags/ports/sequence numbers, and prints a trace plus a verdict — the workflow's "read the bytes" step end to end.

Run `python3 code/main.py`; its output mirrors what `tshark -r hang.pcap` shows on a real file — the field names line up.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Choose capture vs display filter | The two syntaxes (`tcp port 443` vs `tcp.port == 443`) | You capture wide, display narrow, and never lose a packet to a bad filter |
| Prove a packet was truncated | `incl_len < orig_len` in the record header | You point at the snaplen and the exact field, not a guess |
| Identify a dropped SYN | SYN repeated at 1/3/7s, no SYN-ACK | You name the RTO backoff schedule and the silent dropper |
| Detect kernel drops | "N packets dropped by kernel" + seq gaps | You re-capture with a tighter filter or bigger buffer |
| Confirm right interface | Target host/port present in file | You ran `tcpdump -D` first instead of capturing blind |

## Ship It

Produce one artifact under `outputs/`:

- A one-page **capture runbook**: the five-step workflow with your team's real interface names and a tcpdump command template.
- A **filter cheat-sheet** mapping common symptoms to a capture-filter + display-filter pair.
- The annotated trace from `code/main.py` (or a real `.pcap`) with the handshake, retransmit, and RST labeled.

Start from [`outputs/prompt-packet-capture-workflow.md`](../outputs/prompt-packet-capture-workflow.md), replacing the sample trace with your own capture.

## Exercises

1. A teammate runs `tcpdump -s 96 -w db.pcap port 5432` and complains Wireshark "won't show the SQL query." Using only the record-header fields, explain what went wrong and give the corrected command.
2. Debug a TLS handshake to `api.example.com` on a server doing 40,000 packets/sec. Write the capture filter (BPF) and the display filter (Wireshark), and justify why one is narrow and one is wide.
3. A trace shows three packets to port 22 with identical sequence numbers at deltas of +1.0s and +2.0s, then nothing. Name the failure, the layer, and the kernel mechanism producing those exact intervals.
4. A `.pcap`'s global header magic reads `0xd4c3b2a1`. Explain what your parser must do before interpreting any length field, and why `code/main.py` checks the magic first.
5. tcpdump exits printing "1842 packets dropped by kernel." Give two distinct root causes with fixes, and explain how this could be mistaken for network packet loss.
6. A switched-network capture shows only your host's traffic plus broadcasts, even in promiscuous mode. Explain why, and name the two infrastructure options that would let you see another host's conversation.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Capture filter | "the tcpdump filter" | In-kernel BPF applied *before* write; rejected packets gone forever |
| Display filter | "the Wireshark filter" | Post-capture, reversible filter over already-saved bytes (`tcp.port == 443`) |
| Promiscuous mode | "see all traffic" | NIC keeps frames not addressed to it — but on a switch you still need a SPAN/TAP |
| Snaplen | "capture length" | Max bytes saved per packet; `incl_len < orig_len` proves truncation |
| BPF | "filter language" | Berkeley Packet Filter — bytecode from `pcap_compile`, run in-kernel |
| pcap magic | "file header" | `a1b2c3d4`/`a1b23c4d` (host) or swapped (`d4c3b2a1`) — sets endianness and µs/ns |
| Three-way handshake | "the SYN thing" | SYN / SYN-ACK / ACK exchanging ISNs; its flag pattern anchors the trace |
| Kernel drop | "lost packets" | Capture couldn't keep up — a *measurement* artifact, not real loss |

## Further Reading

- **RFC 9293** — Transmission Control Protocol (consolidated TCP spec; handshake, flags, RTO).
- **RFC 6298** — Computing TCP's Retransmission Timer (the RTO backoff behind the 1/3/7/15s pattern).
- **RFC 791** — Internet Protocol (the IPv4 header you parse to reach the TCP segment).
- **IEEE 802.3** — Ethernet framing (the 14-byte header `code/main.py` skips to reach IPv4).
- **pcap / pcapng file format** — IETF "PCAP Capture File Format" draft and the `pcapng` spec.
- **Tcpdump Group** `pcap-filter(7)` man page — the complete BPF capture-filter grammar.
- **Wireshark User's Guide** — chapters on capture vs display filters and "Follow TCP Stream."
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 6 (Transport Layer).
