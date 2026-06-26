# Reading RFCs and Standards to Layered Debugging Method

> RFCs are the source of truth, but they are written for implementers, not debuggers. This lesson teaches you to extract the three things that matter from a standard — the **wire format** (exact field offsets and widths), the **state machine** (named states and transition triggers), and the **normative timers/limits** — then attach each to a layer so a vague symptom becomes a falsifiable hypothesis. You will learn the RFC 2119 keyword grammar (MUST/SHOULD/MAY), why RFC 793's TCP three-way handshake uses a 32-bit ISN that increments roughly every 4 microseconds, how RFC 826 ARP resolves a 32-bit IPv4 address to a 48-bit MAC, and how the OSI 7-layer / TCP-IP 4-layer split lets you bisect failures top-down or bottom-up. The recurring failure modes — a black-holed MSS over a tunnel (RFC 1191 PMTUD), a half-open connection stuck in `FIN-WAIT-2`, an ARP cache poisoned to the wrong MAC, a DNS `SERVFAIL` masking a DNSSEC chain break — all become tractable once you map the symptom to the layer that owns the evidence. The deliverable is `code/main.py`, a layered-bisection diagnostic engine plus an RFC field-offset parser you can reuse on real captures.

**Type:** Build
**Languages:** RFCs, standards, Python (stdlib), shell
**Prerequisites:** Phase 00 lessons 01–02 (lab setup, `tcpdump`/`ip`/`ping` basics), binary and hex fluency
**Time:** ~90 minutes

## Learning Objectives

- Read an RFC the way a debugger does: locate the ASCII packet diagram, the state machine (Section with ESTABLISHED/FIN-WAIT-1/...), and every MUST/SHOULD timer, ignoring the prose in between.
- Apply RFC 2119 keyword grammar to decide whether an observed behavior is a bug (MUST violation), a tolerated choice (MAY), or a degraded-but-legal mode (SHOULD ignored).
- Map a user-visible symptom (timeout, RST, `SERVFAIL`, "works on LAN not over VPN") to the single OSI layer that owns the falsifying evidence.
- Parse real header bytes (Ethernet, IPv4, TCP) at correct offsets and verify the IPv4 header checksum from RFC 1071's one's-complement algorithm.
- Run a top-down vs bottom-up bisection and justify which direction is cheaper for a given symptom.

## The Problem

A service that has worked for months starts failing for remote users only. The symptom report says: "the site loads on the office WiFi but hangs forever over the company VPN. Small pages work, large pages stall." Three engineers guess: a firewall rule, a DNS issue, an application bug. All three start editing config and restarting daemons. Nobody has looked at a packet.

The real fault is a classic **PMTUD black hole** (RFC 1191): the VPN tunnel reduces the path MTU below 1500 bytes, a router needs to send an ICMP Type 3 Code 4 "Fragmentation Needed and DF set" message, and an over-zealous firewall drops all ICMP. The sender keeps retransmitting full 1500-byte segments that can never traverse the tunnel. Small responses fit; large ones black-hole. The TCP connection sits in `ESTABLISHED` with a growing retransmission timer, looking — from the application — exactly like a hang.

You cannot guess your way to that diagnosis. You get there by reading what RFC 1191 says MUST happen, then checking whether the ICMP message that the standard requires is actually present on the wire. That is the entire method: **standard says X must happen → does the evidence show X → if not, you have found the layer.**

## The Concept

### Reading an RFC for debugging, not implementing

An RFC has far more text than a debugger needs. Train yourself to jump to three structures and skip the rest:

| Structure | What it gives you | Example (RFC 793, TCP) |
|---|---|---|
| ASCII packet diagram | Exact field offsets and bit widths | The 20-byte fixed TCP header; Sequence Number at byte offset 4, 32 bits |
| State machine | Named states + transition triggers | `LISTEN → SYN-RECEIVED → ESTABLISHED`; `FIN-WAIT-2` on receiving ACK of our FIN |
| Normative timers / limits | The numbers a correct peer must honor | MSL = 2 minutes; `TIME-WAIT` = 2·MSL = 4 minutes |

Everything else — motivation, history, security considerations — is context you read once and rarely re-open mid-incident.

### RFC 2119 keyword grammar

RFC 2119 (updated by RFC 8174) fixes the meaning of capitalized keywords. This grammar is what separates a bug from a quirk:

| Keyword | Meaning | Debugging implication |
|---|---|---|
| MUST / REQUIRED / SHALL | Absolute requirement | A violation is a defect; the peer is non-conformant |
| MUST NOT / SHALL NOT | Absolute prohibition | Observing this on the wire is a defect |
| SHOULD / RECOMMENDED | Strong default, deviation needs a reason | Legal but suspicious; investigate why it deviates |
| MAY / OPTIONAL | Truly optional | Not a bug; do not waste time here |

When the VPN firewall drops the ICMP "Fragmentation Needed" message, it violates RFC 1191's requirement that the message MUST be generated and the host MUST act on it. That single keyword turns "maybe the firewall" into "the firewall is provably wrong."

### The layered model as a bisection tool

The OSI 7-layer model and the TCP/IP 4-layer model are not academic trivia — they are a binary search over failure causes. Each layer owns a distinct kind of evidence:

| OSI | TCP/IP | Layer owns | Evidence to collect | Tool |
|---|---|---|---|---|
| 7 Application | Application | HTTP status, DNS RRs, TLS alerts | `curl -v`, response codes, app logs | `curl`, `dig` |
| 6/5 Presentation/Session | Application | TLS handshake, encoding | `openssl s_client`, cert chain | `openssl` |
| 4 Transport | Transport | Ports, SYN/ACK/RST/FIN, seq/ack, window | TCP state, retransmits, RTT | `ss`, `tcpdump` |
| 3 Network | Internet | IP reachability, TTL, MTU, ICMP | `ping`, `traceroute`, ICMP types | `ping`, `mtr` |
| 2 Data Link | Link | MAC, ARP, frame, VLAN | ARP table, link state | `ip neigh`, `ethtool` |
| 1 Physical | Link | Carrier, errors, cabling | Link up/down, error counters | `ip link`, `ethtool -S` |

The decision rule: **bottom-up when you suspect infrastructure** (a new VPN, a cable, a switch port), because a broken lower layer makes every higher-layer test meaningless. **Top-down when the application is the only thing that changed** (a deploy, a config push), because you confirm the lower layers are fine in one cheap `ping` and focus upward. See `assets/reading-rfcs-and-standards-to-layered-debugging-method.svg` for the bisection flow.

### Worked example: the TCP three-way handshake from RFC 793

A connection symptom ("connection refused" vs "connection timed out") is decided entirely by the Layer-4 state machine. Reading the SYN bits tells you which:

```
Client                                  Server
  |  SYN  seq=x                            |   x = 32-bit ISN, ~ +1 every 4 µs
  |--------------------------------------->|   server: LISTEN -> SYN-RECEIVED
  |  SYN, ACK  seq=y, ack=x+1              |
  |<---------------------------------------|   client: SYN-SENT -> ESTABLISHED
  |  ACK  ack=y+1                           |
  |--------------------------------------->|   server: SYN-RECEIVED -> ESTABLISHED
```

Now read the failures off the state machine:

- **RST immediately after SYN** → nothing is in `LISTEN` on that port. The OS rejects per RFC 793 ("connection refused"). Layer 4 application-not-listening, *not* a network problem.
- **SYN with no reply, retransmitted (1s, 2s, 4s, 8s...)** → packet reaching nothing, or reply dropped. Could be Layer 3 (no route) or a firewall silently dropping. "Connection timed out."
- **Stuck in `FIN-WAIT-2`** → we sent FIN, got the ACK, but the peer never sent its FIN. The peer's application is not closing. The `tcp_fin_timeout` (default 60s on Linux) is the only thing that eventually reaps it.

The 32-bit Initial Sequence Number matters here: RFC 793 specifies a clock-driven ISN incrementing about every 4 microseconds (wrapping every ~4.55 hours), and RFC 6528 hardens it against off-path spoofing. A mismatched ACK number on the wire is how you catch an injected or stale segment.

### Worked example: ARP and the Layer-2/3 boundary

RFC 826 ARP maps a 32-bit IPv4 address to a 48-bit Ethernet MAC. The request frame carries `htype=1` (Ethernet), `ptype=0x0800` (IPv4), `hlen=6`, `plen=4`, `oper=1` (request), and is broadcast to `ff:ff:ff:ff:ff:ff`. The reply is `oper=2`, unicast.

The "works on LAN, not the gateway" symptom lives exactly here. If `ip neigh` shows the gateway as `FAILED` or the wrong MAC, you have a Layer-2 resolution fault (or ARP spoofing) — no amount of Layer-3 routing config will fix it. The evidence is one line of the ARP cache, and it falsifies every higher-layer theory at once.

### Verifying the IPv4 header checksum (RFC 1071)

Standards give you arithmetic you can check on real bytes. The IPv4 header checksum (RFC 791, computed per RFC 1071) is the 16-bit one's-complement of the one's-complement sum of the header treated as 16-bit words, with the checksum field itself zeroed. If your parser recomputes it and it does not match the wire value, the header is corrupt or the NIC offloaded the checksum (a common false alarm with `tx-checksumming on`). `code/main.py` implements this so you can tell a real corruption from an offload artifact.

### From symptom to falsifiable hypothesis

The method compresses to a loop:

1. State the symptom in observable terms ("large HTTPS responses hang over VPN").
2. Name the most likely owning layer (here: Layer 3 MTU/ICMP).
3. Quote the standard's MUST/SHOULD for that mechanism (RFC 1191: ICMP Type 3 Code 4 MUST be sent and acted on).
4. Collect the one piece of evidence that confirms or kills it (`tcpdump 'icmp[icmptype]==3'` — is the message there?).
5. If killed, move one layer and repeat. If confirmed, you have the layer and the fix.

## Build It

The code is a layered-bisection diagnostic engine plus an RFC-accurate header parser.

1. Read `code/main.py`. The `LAYERS` table encodes the OSI/TCP-IP mapping and the evidence each layer owns.
2. The `parse_ipv4_header` and `parse_tcp_header` functions read fields at the exact byte offsets from RFC 791 and RFC 793. Note how `IHL` (4 bits) is multiplied by 4 to get header length in bytes.
3. `ipv4_checksum` implements the RFC 1071 one's-complement sum. Run it against the sample header and watch it match the embedded checksum.
4. `diagnose` walks a symptom through the bisection: it picks top-down or bottom-up, asks for the evidence each layer owns, and stops at the first falsified MUST.
5. `classify_tcp_state` maps observed flags/states to RFC 793 named states and the likely fault.
6. Run `python3 code/main.py`. It prints a parsed packet, the verified checksum, a TCP state classification, and a full bisection trace for the PMTUD black-hole scenario.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the owning layer | Symptom phrasing + one cheap test per layer | You can say "this is Layer 3, not the app" and name the test that proves it |
| Read a packet against the RFC | Hex bytes parsed at correct offsets | Field values match `tcpdump -x`; checksum recomputes correctly |
| Classify a TCP failure | `ss -tan` state + SYN/RST/FIN flags | You map `FIN-WAIT-2`/`SYN-SENT` to the RFC 793 transition that explains it |
| Distinguish bug from quirk | The RFC 2119 keyword for the mechanism | A MUST violation is filed as a defect; a MAY deviation is left alone |
| Catch the PMTUD black hole | `tcpdump 'icmp[icmptype]==3 and icmp[icmpcode]==4'` | Absence of the required ICMP confirms the firewall, per RFC 1191 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **layered-bisection runbook** (one page) listing, per layer, the symptom signature, the owning RFC, the MUST/SHOULD to check, and the single command that collects the evidence.
- Or extend `code/main.py` to parse a real `.pcap`-derived hex dump from your own capture and annotate each field with its RFC source.

Start from [`outputs/prompt-reading-rfcs-and-standards-to-layered-debugging-method.md`](../outputs/prompt-reading-rfcs-and-standards-to-layered-debugging-method.md) and fill it with evidence you collected yourself.

## Exercises

1. A new microservice returns "connection refused" instantly to one client and "connection timed out" to another. Using the RFC 793 state machine, explain what is different about the two paths and name the Layer-4 test that distinguishes a missing `LISTEN` from a dropping firewall.
2. `dig example.com` returns `SERVFAIL` but `dig +cd example.com` (checking disabled) returns the A record. Which RFC mechanism is failing, which layer owns it, and what is the falsifying evidence?
3. Take a 20-byte IPv4 header you capture with `tcpdump -x`, zero the checksum field, and recompute it by hand using the RFC 1071 algorithm. Confirm it matches. Then explain why a packet captured *before* NIC transmit may show checksum `0x0000` even though the wire value is correct.
4. A host's `ip neigh` shows the default gateway in state `FAILED`. Build the bisection argument for why this single line falsifies a "DNS is broken" theory and a "TLS cert expired" theory simultaneously.
5. Over a WireGuard tunnel (MTU 1420), large downloads stall. Write the exact `tcpdump` filter that confirms the missing ICMP Type 3 Code 4, cite the RFC that says it MUST be present, and give the one-line mitigation (MSS clamping) and the standard field it edits.
6. Pick any MUST in RFC 826 (ARP). Construct a scenario where a device violates it, and describe the wire evidence that proves the violation rather than a higher-layer symptom.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| RFC 2119 keywords | "MUST means important" | A precise grammar: MUST = conformance requirement (violation is a bug), MAY = optional (not a bug) |
| Layered bisection | "Check the OSI layers" | A binary search: each layer owns falsifiable evidence; you halve the cause space per test |
| PMTUD black hole | "MTU problem" | RFC 1191 ICMP Type 3 Code 4 dropped, so the sender never shrinks segments — small works, large hangs |
| ISN | "the SYN number" | 32-bit Initial Sequence Number, clock-driven (~+1 every 4 µs), hardened by RFC 6528 against spoofing |
| FIN-WAIT-2 | "closing connection" | RFC 793 state after our FIN is ACKed but the peer hasn't sent its FIN; reaped by `tcp_fin_timeout` |
| ARP cache | "the MAC table" | RFC 826 mapping of 32-bit IPv4 → 48-bit MAC; a `FAILED` entry is a Layer-2 fault, not Layer 3 |
| IPv4 checksum | "the error check" | 16-bit one's-complement sum (RFC 1071) over the header only; mismatch means corruption or NIC offload |
| TIME-WAIT | "stuck sockets" | RFC 793 state held for 2·MSL (4 min) to absorb stray segments before reuse |

## Further Reading

- **RFC 2119** / **RFC 8174** — Key words for use in RFCs to Indicate Requirement Levels (MUST/SHOULD/MAY).
- **RFC 791** — Internet Protocol (IPv4 header format, fields, fragmentation).
- **RFC 793** (obsoleted by **RFC 9293**) — Transmission Control Protocol (header, three-way handshake, state machine).
- **RFC 826** — An Ethernet Address Resolution Protocol (ARP request/reply format).
- **RFC 1071** — Computing the Internet Checksum (one's-complement algorithm).
- **RFC 1191** — Path MTU Discovery; **RFC 8201** for IPv6.
- **RFC 6528** — Defending against Sequence Number Attacks (ISN generation).
- **IEEE 802.3** — Ethernet framing and the 48-bit MAC address space.
- Tanenbaum & Wetherall, *Computer Networks*, 6th ed. — Chapter 1 (layered architectures, OSI vs TCP/IP) and Chapter 6 (transport, TCP state machine).
- Stevens, *TCP/IP Illustrated, Volume 1*, 2nd ed. — handshake, state transitions, and on-the-wire diagnosis.
