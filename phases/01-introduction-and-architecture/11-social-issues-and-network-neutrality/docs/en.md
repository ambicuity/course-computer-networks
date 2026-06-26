# Social Issues, Net Neutrality, and Censorship in Computer Networks

> Networks are not neutral by accident — they are neutral (or not) because of engineering decisions about packet handling. **Net neutrality** (Wu, 2003) is the claim that a carrier should forward bits without favoring some sources, destinations, or content classes over others; violating it means an ISP inspects packets with **Deep Packet Inspection (DPI)** and applies per-flow policy, typically by rewriting the IPv4 **TOS / DSCP** field (RFC 2474, 6 bits) or by shaping bandwidth at a token-bucket scheduler. **Censorship** is implemented not by argument but by routing tricks: **DNS poisoning** returns forged A/AAAA records with a short **TTL**, **IP blocking** null-routes prefixes in the BGP table (dropping the route via `ip route 0.0.0.0 0` equivalent), and **TCP RST injection** forges a segment with the RST flag (TCP flags byte bit 0x04) and a guessed 32-bit **sequence number** to tear down a flow mid-stream — the technique behind the Great Firewall's teardown packets. **Copyright enforcement** rides on **DMCA takedown notices** (17 U.S.C. §512) sent to operators, and on automated P2P crawlers that join a swarm and log peer IP:port tuples from the BitTorrent **HAVE/BITFIELD** handshake. The textbook's punchline is correct: a network is a post office that *can* inspect every envelope, and the social question is whether it *may*. This lesson builds a runnable net-neutrality discrimination detector and a censorship-by-DNS-poisoning + RST-injection model so you can read the exact artifacts these policies leave in packets.

**Type:** Learn
**Languages:** Python, shell
**Prerequisites:** IP/TCP header structure (Phase 1 lessons on protocol layering), DNS query/response format, basic token-bucket scheduling
**Time:** ~80 minutes

## Learning Objectives

- Classify a net-neutrality violation from a packet trace by detecting per-flow bandwidth shaping (token-bucket parameters) versus per-content DPI-driven throttling.
- Read an IPv4 header's 1-byte **TOS/DSCP** field (RFC 2474) and a TCP header's flags byte, and explain how each is the lever an ISP uses to differentiate traffic.
- Reconstruct a **DNS poisoning** attack: a forged UDP/53 answer with a spoofed 16-bit **Transaction ID** and a short TTL arriving before the real resolver's response.
- Model **TCP RST injection** and identify the two numbers an attacker must guess or observe (the 4-tuple and the 32-bit sequence number) to forcibly close a connection.
- Map three censorship regimes — DNS-level, IP-level (BGP null-route), and application-level (RST/SNI blocking) — to the protocol layer each operates at and the evidence each leaves.
- Distinguish copyright enforcement (DMCA §512 notice-and-takedown) from network-level censorship, and explain why automated P2P crawlers can misidentify a networked printer as an infringer.

## The Problem

A small video startup streams from `198.51.100.0/24` and measures its flows against a competitor hosted on `203.0.113.0/24` over the same last-mile ISP. Same RTT, same route hop count, same TCP window scaling — yet the startup's 1080p segments stall while the competitor's do not. The on-call engineer captures both flows with `tcpdump` and sees the startup's packets arriving at the customer with inter-packet gaps that grow linearly, while the competitor's arrive at a steady cadence. Something between the two origin networks is treating the flows differently. The engineer has to prove *which* mechanism is in play — bandwidth shaping (a token bucket) or content discrimination (DPI rewriting DSCP) — because the legal and engineering responses diverge. Meanwhile, in another country, users report that typing a certain hostname into a browser yields a connection reset within ~50 ms, every time, from many networks simultaneously — the signature of state-level RST injection, not a flaky server.

## The Concept

### Net neutrality as an engineering property, not a slogan

A network is **neutral** for a flow if the forwarding path treats that flow's packets indifferently to their source, destination, application, and content. Formally, a work-conserving FIFO queue at every hop is neutral: it forwards in arrival order and never idles when work is waiting. Non-neutrality enters the moment a scheduler classifies packets into per-class queues with different service rates. The textbook (section 1.1.4) frames this as "all bits are the same" — the engineering reading is that the forwarding plane must not contain classification rules keyed on anything but the routing table. The carrier's counter-argument, also in the textbook, is economic: P2P traffic is expensive to carry, so the operator shapes it. Both are engineering statements about what the scheduler does.

### Where differentiation lives: the TOS/DSCP field and the scheduler

The lever an ISP uses to mark a flow for differentiated handling is the IPv4 **Type of Service** byte, redefined by RFC 2474 as the **Differentiated Services Field**. Its layout:

| Bits (0-indexed) | 0–5 | 6–7 |
|---|---|---|
| Field | **DSCP** (Differentiated Services Code Point) | **ECN** (Explicit Congestion Notification) |
| Size | 6 bits → 64 code points | 2 bits |

A **DSCP** value such as `EF` (Expedited Forwarding, `101110` = decimal 46, RFC 3246) or `AF41` (`100010` = decimal 34, RFC 2597) tells a downstream DiffServ router to place the packet in a high-priority queue. A net-neutrality violator that rewrites the DSCP of a competitor's video from `EF` to `CS0` (`000000`, default/best-effort) demotes it without changing the routing — the demotion is invisible to the endpoints but visible in the byte. `code/main.py` parses the TOS byte of every captured packet and flags flows whose DSCP changes mid-path, which is the smoking-gun evidence of DPI-driven rewriting.

### Bandwidth shaping: the token bucket as a discriminator

The other discrimination mode is **traffic shaping** at a scheduler, modeled by a **token bucket**: a bucket of capacity *B* bytes fills with tokens at rate *R* bytes/sec; a packet of size *L* is forwarded only if *L* tokens are available, else it is delayed (shaped) or dropped (policed). When the bucket is empty, packets queue and inter-arrival times at the egress stretch by `L / R`. A neutral network presents roughly the same `R` to every flow; a discriminating network assigns a smaller `R` (or a smaller `B`) to disfavored flows.

Worked example. Two 1500-byte packets arrive back-to-back at t=0. Flow A has `R = 10 MB/s`, flow B has `R = 1 MB/s` (the disfavored competitor). Packet spacing at egress:

| Flow | Token rate R | Inter-packet gap at egress |
|---|---|---|
| A (favored) | 10 MB/s | 1500 B / 10 MB/s = **150 µs** |
| B (shaped) | 1 MB/s | 1500 B / 1 MB/s = **1500 µs** |

The 10× gap is what the on-call engineer measured. `code/main.py` implements a `TokenBucket` and replays a trace, reporting the inferred rate per flow so you can read the discrimination numerically rather than by eye. See `assets/social-issues-network-neutrality.svg` for the two-bucket comparison.

### Detecting the mechanism: shaping vs rewriting

The two discrimination modes leave different fingerprints, and the engineer's job is to tell them apart:

| Evidence in the trace | Mechanism | Why |
|---|---|---|
| DSCP byte changes between hop N and hop N+1 | **DPI rewrite** | A middlebox mutated the header |
| DSCP stable, but inter-arrival gap stretches as `L/R` | **Token-bucket shaping** | Scheduler delay, header untouched |
| DSCP stable, packets *dropped* at a rate >0 with no congestion signal | **Policer (hard drop)** | Bucket empty → discard, no ECN |
| All of the above stable, but flow reset by forged RST | **Censorship**, not neutrality | See below |

The decision rule: capture at **two points** (ingress to the suspect ISP and egress). If the DSCP differs between the two captures, the middlebox rewrote it. If only timing differs and the header is intact, the scheduler shaped it. `code/main.py`'s `classify_violation()` encodes this rule.

### Censorship at the DNS layer: poisoning the 16-bit transaction ID

DNS censorship forges a response before the real one arrives. A DNS query over UDP/53 carries a 16-bit **Transaction ID** in the header (RFC 1035, byte offset 0); the resolver accepts the first matching answer (same TxID, same source port, same question section) and caches it for the answer's **TTL**. An attacker who can race the real resolver needs only to guess the 16-bit TxID (~65 536 possibilities) and the resolver's source port — modern resolvers randomize the source port (RFC 5452, "source port randomization"), raising the entropy from 16 bits to ~30 bits, which is why blind DNS poisoning became hard after 2008. On-path attackers (who see the query) need guess nothing: they read the TxID and port and reply instantly with a forged A record and a short TTL so the lie is cached just long enough. `code/main.py` models a `DNSPoisoner` that wins the race when it is on-path and loses probabilistically when off-path.

| DNS header field | Offset | Size | Role in poisoning |
|---|---|---|---|
| Transaction ID | 0 | 2 bytes | Must match the query; the gate |
| Flags | 2 | 2 bytes | QR=1 (response), AA may be set to look authoritative |
| Question count | 4 | 2 bytes | Echo the query's question |
| Answer RDATA | variable | variable | Forged A record, e.g. `0.0.0.0` to null-route |
| TTL in answer | variable | 4 bytes | Short (e.g. 60s) so the lie expires and can be refreshed |

### Censorship at the IP layer: BGP null-routing

The crudest censorship is to withdraw the destination. An operator announces the target prefix to its own routers with a **null next-hop** (the Cisco `ip route <prefix> 255.255.255.255 Null0`, or a Linux `blackhole` route). Packets matching the prefix are silently discarded; no RST, no DNS lie, just a hole. Globally, a censoring AS can also announce a **more-specific route** (a longer prefix) for the target and attract its traffic to a blackhole — this is the BGP-level mechanism behind some country-level blocks. The signature is in the control plane: a `BGP UPDATE` with a path whose next-hop leads to a discarding router, observable in RouteViews/RIS collector data. It is censorship by routing, with no per-packet state.

### Censorship at the transport layer: TCP RST injection

The surgical option is to kill the flow in place. A censor watching a TCP connection (the 4-tuple: srcIP, srcPort, dstIP, dstPort) forges a segment with the **RST flag** set — in the TCP header, the flags byte at offset 12 (low nibble of byte 13 in the full layout): `FIN=0x01, SYN=0x02, RST=0x04, PSH=0x08, ACK=0x10`. For the RST to be accepted, the forged segment's **sequence number** must fall inside the receiver's receive window (RFC 793 §3.4: `RCV.NXT ≤ SEG.SEQ < RCV.NXT + RCV.WND`, or the sequence-number-wrap variants). An on-path censor reads the sequence number off the wire and crafts a perfect RST; an off-path censor must guess it — a 32-bit search made harder by the 4-tuple also needing to match. The textbook's "Great Firewall" teardown is precisely this: an on-path box fires an RST (sometimes two — one to each side) the instant it spots a forbidden keyword or SNI, and the connection dies. `code/main.py`'s `RSTInjector` checks the window-acceptance rule so you can see why an off-path guess usually fails.

### Copyright enforcement: DMCA §512 and the P2P crawler

The textbook notes automated systems search P2P networks and fire off **DMCA takedown notices** under 17 U.S.C. §512. Mechanically, a crawler joins a BitTorrent swarm, completes the protocol's handshake (the `pstrlen=19`, `pstr="BitTorrent protocol"`, 8 reserved bytes, 20-byte info-hash, 20-byte peer-id exchange), receives `BITFIELD` and `HAVE` messages, and logs every `IP:port` that advertises possession of the targeted info-hash. Those tuples become notices sent to the corresponding ISPs. The famous failure mode (Piatek et al., 2008) is that a crawler can misattribute an infringement to a NAT'd printer or an innocent host whose IP was reused, because an IP address is not an identity — a lesson in why evidence at the network layer is weaker than it looks.

### The social question, restated as an engineering one

Every mechanism above is, technically, just classification plus a scheduler decision or a forged packet. The textbook's point is that the *social* question — may a carrier favor, block, or surveil — is inseparable from the *engineering* question of which fields and timers it touches. Net-neutrality regulation (e.g. the U.S. 2015 Open Internet Order, later rescinded then partly restored) bans paid prioritization and blocking/throttling; it is enforceable precisely because the violations produce measurable artifacts (DSCP rewrites, token-bucket gaps). Censorship is the same machinery pointed at a different target. Understanding the packets is what lets an engineer testify about either.

## Build It

1. Read `code/main.py`. It contains five components: `TokenBucket` (the shaper), `TokenBucket`-based `replay_trace()` that infers per-flow rates, `parse_ipv4_tos()` to extract the DSCP, `classify_violation()` that decides shaping-vs-rewriting from two capture points, `DNSPoisoner` (on/off-path race), and `RSTInjector` (window-acceptance check).
2. Run it: `python3 code/main.py`. The demo prints the inferred token rate for a favored vs shaped flow, flags a DSCP rewrite between two simulated capture points, runs a DNS-poisoning race (on-path wins, off-path is probabilistic), and tests an RST injection inside vs outside the receive window.
3. Open `assets/social-issues-network-neutrality.svg`. It shows two token buckets (10 MB/s vs 1 MB/s) feeding the same egress and the resulting inter-packet gap, plus the DNS-race timeline.
4. Edit the `shaped_rate` in `main()` from `1_000_000` to `5_000_000` and rerun. Confirm the inferred gap shrinks proportionally — the discriminator is parametric, not hardcoded.
5. Change `RSTInjector`'s `seq_num` to a value outside `rcv_nxt + rcv_wnd` and confirm the injection is rejected — the window rule is the defense off-path attackers cannot easily beat.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Prove bandwidth shaping | Inferred token rate per flow from `replay_trace()`; inter-arrival gap matches `L/R` | The disfavored flow's rate is materially below the favored flow's at the same congestion level |
| Prove DPI/DSCP rewriting | TOS byte differs between ingress and egress captures for the same packet ID | The header was mutated in transit; neutral networks never rewrite DSCP without an SLA |
| Distinguish shaping from dropping | Drop rate vs queue delay; ECN marks present or absent | Shaping delays; a policer drops without ECN — different legal and engineering fixes |
| Demonstrate DNS poisoning | Forged answer's TxID matches; forged answer arrives first; short TTL | On-path attacker wins the race deterministically; off-path wins ~2^-30 with port randomization |
| Validate an RST injection | Forged RST's sequence number falls in `[RCV.NXT, RCV.NXT+RCV.WND)` | Inside the window → flow dies; outside → silently discarded by RFC 793 §3.4 |
| Triage a censorship report | Which layer: DNS lie / BGP null route / RST / SNI block | The layer tells you the countermeasure (DoH, alternate prefix, TLS without SNI leak, etc.) |

## Ship It

Produce one artifact under `outputs/`:

- A discrimination report: a two-capture trace (ingress + egress) for a favored and a disfavored flow, with the inferred token rates, the DSCP values at each capture point, and a one-line verdict (`SHAPING`, `DSCP_REWRITE`, `POLICER_DROP`, or `NEUTRAL`).
- A censorship mechanism card mapping each of the four techniques (DNS poisoning, BGP null-route, RST injection, SNI/keyword block) to its protocol layer, required vantage point, and observable signature.
- A DMCA-crawler evidence critique: given a list of `IP:port` tuples harvested from a BitTorrent swarm, list three reasons the attribution may be wrong (NAT, IP reuse, swarm poisoning).

Start from the printed output of `code/main.py` and annotate it with the verdict and the window-acceptance result.

## Exercises

1. Two 1400-byte packets enter an ISP at t=0 and t=0.001 s. The egress captures them at t=0.00014 s and t=0.00156 s. Compute the inferred token rate and state whether the gap is consistent with a 10 MB/s neutral pipe or a 1 MB/s shaped pipe. Show the arithmetic.
2. A capture at the ingress router shows DSCP `EF (46)` for a flow; a capture 3 hops later shows DSCP `CS0 (0)` for the same flow ID, with no congestion. Which `classify_violation()` verdict fires, and what does it imply about a middlebox between the two capture points?
3. A resolver sends a DNS query with TxID `0x4A2B` from source port 51200. An off-path attacker can guess the TxID and the port. With RFC 5452 source-port randomization across the full 16-bit ephemeral range, what is the probability a single forged response is accepted? How many forged responses must the attacker send to expect one success?
4. A TCP connection has `RCV.NXT = 1_000_000` and `RCV.WND = 65 535`. An off-path censor guesses sequence number `1_200_000` for a forged RST. Does RFC 793 §3.4 accept it? What range of sequence numbers would have succeeded?
5. A censor null-routes `198.18.0.0/15` via BGP. A user inside the censored network tries to reach `198.18.5.20`. Describe exactly what the user's `traceroute` output will show, and contrast it with what an RST-injection censor would produce for the same destination.
6. A DMCA crawler logs peer `(203.0.113.77:51413)` in a swarm for a copyrighted film. The subscriber at that address runs only a networked HP LaserJet. Give two technical explanations consistent with the textbook's Piatek et al. finding, and propose one piece of evidence that would distinguish them.
7. A regulator wants to prove paid prioritization. Argue for capturing at two points (ingress + egress) rather than one, and name the two fields (`DSCP`, inter-arrival gap) that the two-capture method exposes but a single capture hides.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Net neutrality | "treat all traffic the same" | A forwarding plane with no classification rules beyond the routing table; violations are measurable as DSCP rewrites or token-bucket delays |
| DSCP | "a priority tag" | 6 bits of the IPv4 TOS byte (RFC 2474); `EF`=46, `CS0`=0; the lever a DiffServ middlebox rewrites to demote a flow |
| Token bucket | "a rate limiter" | A bucket of capacity B filled at rate R; shapes (delays) or polices (drops) packets that exceed R — the math of bandwidth discrimination |
| Deep Packet Inspection (DPI) | "looking inside packets" | Classification past L3/L4 headers into application/content, enabling per-flow policy; the engine of non-neutrality |
| DNS poisoning | "fake DNS" | A forged UDP/53 answer with the matching 16-bit TxID arriving before the real one; cached for the forged TTL |
| TCP RST injection | "killing a connection" | A forged segment with RST (flags byte 0x04) and an in-window sequence number; on-path censors read the seq off the wire |
| BGP null-route | "blocking a site" | Announcing the target prefix with a Null0/blackhole next-hop so packets are discarded at the routing layer, no per-flow state |
| DMCA takedown | "a copyright notice" | A §512 notice sent to an operator from a crawler that logged an IP:port in a P2P swarm; weak evidence because an IP is not an identity |
| Source port randomization | "DNS hardening" | RFC 5452; raises DNS forgery entropy from 16 bits (TxID only) to ~30 bits, defeating blind poisoning |
| Receive window | "the TCP buffer" | `RCV.WND`; the range `[RCV.NXT, RCV.NXT+RCV.WND)` of sequence numbers a forged RST must hit to be accepted |

## Further Reading

- **RFC 793** — Transmission Control Protocol, §3.4 on sequence-number validity and RST processing.
- **RFC 2474** — Definition of the Differentiated Services Field (DS Field) in the IPv4 and IPv6 headers.
- **RFC 3246** — An Expedited Forwarding PHB (the `EF` DSCP, decimal 46).
- **RFC 2597** — Assured Forwarding PHB Group (the `AF` DSCPs).
- **RFC 1035** — Domain Names: Implementation and Specification (DNS header, Transaction ID, TTL).
- **RFC 5452** — Measures to Make DNS More Resilient against Forged Answers (source port randomization).
- **T. Wu, "Network Neutrality, Broadband Discrimination,"** Journal of Telecommunications and High Technology Law, 2003 — the origin of the term.
- **Kaminsky, "It Came From Planet X,"** Black Hat 2008 — the cache-poisoning flaw that motivated RFC 5452.
- **R. Clayton, S. Murdoch, R. Anderson, "Forging TCP Connections,"** 2006 — the on-path RST-injection analysis used to study the Great Firewall.
- **Piatek et al., "Pirates or Prisons?,"** USENIX SRUTI 2008 — BitTorrent attribution errors (the printer case).
- **17 U.S.C. §512** — the DMCA notice-and-takedown safe harbor.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §1.1.4 (Social Issues).
