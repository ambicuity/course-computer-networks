# Reliability, Error Detection, and Routing as Layer Design Issues

> A network is a stack of unreliable parts that has to behave as if it were reliable. The textbook frames this as a **design issue that recurs at every layer**: bits arrive inverted from electrical noise, wireless interference, or hardware and software faults, so each layer adds **redundant information** to detect — and sometimes correct — the damage. At the link layer an Ethernet frame ends in a **4-byte FCS** computed as a CRC-32 polynomial (IEEE 802.3), while IPv4 carries a **16-bit one's-complement header checksum** (RFC 1071) and TCP/UDP add a **pseudo-header** covered checksum (RFC 9293). Detection only tells you a frame is bad; recovery is a separate decision — drop it silently (Ethernet), or flag it for retransmission via ACKs and timeouts (TCP, RFC 9293, with the **RTO** from RFC 6298 and `SRTT = (1−α)·SRTT + α·R`, RTTVAR/SRTT EWMA). **Error-correcting codes** (Hamming, Reed-Solomon, convolutional/Viterbi) recover the message without a round trip, trading bandwidth for latency. The other face of reliability is **finding a working path**: when a link or router in Germany is down, London-to-Rome traffic must reroute via Paris automatically — that is **routing**, and it too is layered (link-state OSPF IS-IS at L3, BGP-4 RFC 4271 at the inter-domain level). This lesson models both faces as concrete mechanisms — a CRC-32 checker, a one's-complement Internet checksum, a sliding-window ARQ simulator, and a Dijkstra routing solver — so you can read the exact bytes a protocol leaves behind.

**Type:** Learn
**Languages:** Python
**Prerequisites:** The protocol layering and service-interface model from the earlier lessons in this phase; basic familiarity with bits, bytes, and polynomials
**Time:** ~80 minutes

## Learning Objectives

- Compute an Ethernet CRC-32 FCS and an IPv4 one's-complement header checksum by hand and confirm they match the values `code/main.py` produces.
- Distinguish **error detection** (flag and drop/retransmit) from **error correction** (recover in place) and name the bandwidth-vs-latency trade-off that decides which a layer uses.
- Trace a sliding-window ARQ sender through the Idle/Wait/Retransmit states and explain how sequence numbers, ACKs, and a retransmission timeout (RTO) deliver reliable transfer over an unreliable link.
- Explain why a damaged IP header is dropped at every hop while a damaged TCP segment is silently discarded but counted, and how each choice maps to a layer's responsibility boundary.
- Run Dijkstra's algorithm on a small topology with one failed link and identify the alternate path the routing computation selects — the textbook's London→Paris→Rome reroute in miniature.
- Read a real frame/packet and point to the exact bytes that carry detection (FCS), addressing (dst/src MAC, IP), and routing (TTL, next-hop) information.

## The Problem

A router on the path between a London office and a Rome data center sits in Frankfurt. During a thunderstorm a burst of electrical noise flips three bits in the middle of a 1500-byte IP packet carrying a chunk of a database backup. The receiving router in Paris sees the frame arrive with a valid-looking preamble and a correct destination MAC, forwards it, and the corrupted payload propagates onward — except the application now restores a backup with three wrong bytes, and nobody notices for a week.

Worse, the Frankfurt router loses power an hour later. Every route that crossed Frankfurt now points into a hole. Packets loop, time out, or vanish. The backup must still get through, but no human is available to reconfigure routes at 3 a.m.

Both symptoms — corrupted bits and a dead router — are instances of the same textbook problem: *make a network that operates correctly even though it is made of unreliable components.* The first is fixed by **error detection and retransmission**, the second by **routing** that automatically finds a working path. Neither is a single protocol; each is a design issue that recurs at every layer, solved with different mechanisms depending on what that layer can see and afford.

## The Concept

### Reliability as a recurring layer issue

The textbook's claim is precise: reliability is not a service that one layer provides once. It is a *design issue* that shows up at the data-link, network, transport, and application layers, each solved with the cheapest mechanism that layer can deploy. A link layer that sees every frame and can retransmit cheaply over one hop uses a strong **FCS** and ARQ. The network layer, which forwards billions of packets across many hops and cannot afford per-packet retransmission state, uses only a **header checksum** and drops damaged datagrams — recovery is the host's problem. The transport layer (TCP) re-adds end-to-end reliability with sequence numbers, ACKs, and RTO because the network layer refused to. The application layer adds its own integrity checks (TLS MAC, HTTP-level hashes) when it cannot trust the layers below. The recurring question at each layer is: *what is the cheapest redundancy that catches the failures this layer is responsible for, without paying for the ones the layer below already handled?*

### Error detection: redundancy that flags damage

Detection works by adding **check bits** computed as a function of the data bits. A single flipped data bit changes the check bits in a predictable way; a receiver recomputes the check bits and compares. The three mechanisms that matter at different layers:

| Mechanism | Layer(s) | Check size | Polynomial / method | RFC / standard |
|---|---|---|---|---|
| **CRC-32** | Ethernet (802.3) link, Wi-Fi (802.11) | 4 bytes (FCS) | `0x04C11DB7`, reflected `0xEDB88320` | IEEE 802.3 clause 3.1.1 |
| **One's-complement checksum** | IPv4 header, TCP/UDP (+pseudo-header) | 2 bytes | 16-bit one's-complement sum of 16-bit words | RFC 1071, RFC 9293 |
| **MAC (HMAC/CRC within TLS)** | TLS record, application | 16–32 bytes | HMAC-SHA256 over record+seq | RFC 8446 (TLS 1.2/1.3) |

The **CRC** is the strongest of the three for burst errors: because it is a polynomial remainder in GF(2), any burst of ≤ 32 corrupted bits is guaranteed caught, and the probability of a longer burst slipping through is `2⁻³²`. The one's-complement checksum is weaker — it catches any single-bit error but can miss reordering of 16-bit words — but it is *cheap to compute in software* and self-complementing, which is why the Internet architecture kept it. The trade-off table in `code/main.py` prints the detection strength and per-packet cost of each.

#### Worked example: IPv4 one's-complement checksum

Take a 20-byte IPv4 header with `Version/IHL = 0x4500`, `Total Length = 0x001C`, and the rest zeroed except the source `10.0.0.1` and destination `10.0.0.2`. Treat the header as ten 16-bit words, sum them with end-around carry, fold any overflow back, and take the one's complement. The `internet_checksum()` function in `code/main.py` does exactly this and returns `0x26CF` for that header — which is the value a real stack would emit in the header's checksum field. Inject a single bit into the Total Length word and recompute: the receiver's sum is no longer `0xFFFF`, so the datagram is dropped at the next router. That drop is the network layer's entire recovery strategy.

### Error correction: recover without a round trip

Detection plus retransmission (ARQ) costs a round trip per damaged frame. On a 90 ms RTT transatlantic link, retransmitting a 1500-byte frame that lost one bit is wasteful. **Forward Error Correction (FEC)** adds enough redundancy that the receiver reconstructs the original without asking again. The classic codes:

- **Hamming(7,4)** — 4 data bits + 3 parity bits; corrects any single-bit error, detects any double-bit error. Used in ECC RAM and historically in protocol headers that needed cheap single-bit repair.
- **Reed-Solomon** — operates on symbols (typically 8-bit bytes); corrects up to `(n−k)/2` symbol errors in an `(n, k)` codeword. Used on optical media (CD/DVD), in QR codes, and in DVB/DOCSIS forward links.
- **Convolutional codes + Viterbi decoding** — a stream of bits convolved with generator polynomials (e.g. rate 1/2, generators `0x7` and `0x5`); the Viterbi algorithm finds the maximum-likelihood path through the trellis. The workhorse of 2G/3G radio and deep-space links (Voyager used concatenated convolutional + Reed-Solomon).

The decision rule: if the channel has **low error rate but high RTT** (satellite, deep space), FEC wins. If the channel has **high error rate but low RTT** (LAN, well-engineered Wi-Fi with retransmission), pure ARQ or hybrid ARQ (FEC + retransmission of leftover errors) wins. The `hamming_encode`/`hamming_correct` functions in `code/main.py` let you inject a single-bit error into a 4-bit nibble and watch the (7,4) code repair it — the parity bits point to the offending position by their syndrome.

### ARQ and the sliding window: making an unreliable link reliable

When a layer chooses detection + retransmission, it needs three things: **sequence numbers** to detect duplicates and gaps, **acknowledgements (ACKs)** so the sender knows what arrived, and a **timer (RTO)** so the sender retransmits if an ACK never comes. The state machine a stop-and-wait ARQ sender cycles through:

| State | Trigger | Transition | Action |
|---|---|---|---|
| **Idle** | `send(frame)` | → Wait | Transmit frame N, start RTO timer |
| **Wait** | `ACK(N)` received | → Idle | Stop timer, advance N |
| **Wait** | RTO expires | → Wait | Retransmit frame N, restart timer |
| **Wait** | `ACK(N−1)` (duplicate) | → Wait | Ignore; frame N still in flight |

Stop-and-wait wastes the link: only one frame is outstanding. A **sliding window** (Go-Back-N or Selective Repeat) keeps W frames in flight. The window advances as ACKs arrive; the sender may transmit any frame whose sequence is within `[base, base+W−1]`. Go-Back-N retransmits everything from the lost frame onward (simple receiver, wasteful on lossy links); Selective Repeat retransmits only the lost frame (selective ACKs via SACK, RFC 2018). `code/main.py` simulates a sliding-window sender over a lossy channel and prints the per-frame timeline, showing exactly which frames are retransmitted and why.

The RTO itself is not a guess. RFC 6298 sets `SRTT = (1−α)·SRTT + α·R` and `RTTVAR = (1−β)·RTTVAR + β·|R − SRTT|` with `α = 1/8, β = 1/4`, then `RTO = SRTT + 4·RTTVAR` (clamped to ≥ 1 s). Too short and the sender retransmits packets that are merely delayed, inflating load; too long and recovery crawls. This is the textbook's flow-control-and-congestion concern, already visible at the transport layer as a reliability mechanism.

### Routing: finding a working path automatically

The other face of reliability is topology. The textbook's example: London to Rome via Germany fails, but London to Rome via Paris works. The network must make that decision without human intervention. **Routing** is the layer-3 mechanism, and it splits into two families:

- **Link-state** (OSPF RFC 2328, IS-IS ISO 10589): every node floods the cost of its local links; every node then runs **Dijkstra's shortest-path** on the full map. Converges fast, scales to moderate domains, and gives loop-free paths because every router has the identical view.
- **Distance-vector** (RIP RFC 2453, BGP RFC 4271 as a path-vector variant): each node advertises its `(destination, cost)` table to neighbors; neighbors add the link cost and keep the minimum. Cheaper to run but suffers **count-to-infinity** after a break, fixed in BGP by carrying the full AS path and in RIP by a hop-count horizon of 15.

`code/main.py` implements Dijkstra over a small Europe-shaped topology (London, Frankfurt, Paris, Rome) and recomputes shortest paths after the Frankfurt node is removed. Normally London sends through Frankfurt (cost 8: London→Frankfurt 4, Frankfurt→Rome 4); when Frankfurt dies the London→Paris→Rome path takes over automatically, with cost 14. Exactly the textbook reroute, in miniature. The diagram in `assets/reliability-error-detection-routing-issues.svg` shows the before/after topology with the failed node greyed and the new solid path highlighted.

### How the design issues compose

The recurring-theme point is that detection, ARQ, and routing are not three separate protocols — they are three *instances* of the same idea (add redundancy, then recover) applied at different granularities. Detection adds check bits to a frame; ARQ adds sequence numbers and ACKs to a stream; routing adds topology state and recomputation to a network. Each layer picks the granularity it can afford. See `assets/reliability-error-detection-routing-issues.svg` for the layer-by-layer map of which mechanism lives where.

## Build It

1. Open `code/main.py` and read the four modules in order: `crc32()` (link FCS), `internet_checksum()` (IP/TCP header), `Hamming74` (FEC), `SlidingWindow` (ARQ), and `dijkstra()` (routing).
2. Run `python3 code/main.py`. The demo prints: a CRC-32 over a sample frame, the IPv4 checksum of a 20-byte header (verify against `0x26CF`), a Hamming(7,4) single-bit repair, a sliding-window trace with a real RTO rewind, and a Dijkstra reroute around Frankfurt.
3. Edit the header bytes passed to `internet_checksum()` — flip one bit in the Total Length field — and rerun. Confirm the receiver's sum is no longer `0xFFFF`, which is what makes a router drop the datagram.
4. In `SlidingWindow`, raise `loss_prob` to 0.4 and increase `window` from 4 to 8. Observe throughput rise (more in flight) until loss overwhelms the window and retransmissions dominate.
5. In the routing demo, remove a different edge (e.g. London–Paris) and rerun Dijkstra. Confirm the new shortest path and the total cost the solver reports.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame's FCS | CRC-32 matches the 4-byte FCS an Ethernet NIC appends | A single flipped bit produces a different remainder; the receiver drops the frame |
| Validate an IP header | One's-complement sum over the header (with checksum field included) equals `0xFFFF` | Injecting any bit makes the sum ≠ `0xFFFF`, so the router discards the datagram |
| Show FEC repairing damage | Hamming(7,4) syndrome points at the bad bit and the corrected nibble equals the original | One-bit errors are corrected silently; two-bit errors are detected but not corrected |
| Trace ARQ recovery | Sliding-window log shows frame retransmitted only after RTO or explicit NAK | No duplicate delivery; window advances monotonically as ACKs arrive |
| Verify a reroute | Dijkstra output before/after node removal: cost rises, path changes, no loop | London→Rome goes via Paris when Frankfurt dies, with a higher but finite cost |
| Justify layer placement | A one-paragraph argument why IP uses only a header checksum while TCP adds full reliability | IP is per-hop and stateless; TCP is end-to-end and can afford per-byte state |

## Ship It

Produce one artifact under `outputs/` — a `prompt-` markdown file (e.g. `outputs/prompt-reliability-error-detection-routing.md`) that contains:

- The printed output of `python3 code/main.py` for the default topology and loss rate, annotated to label each mechanism (FCS, header checksum, FEC, ARQ, routing).
- A worked checksum computation for a 20-byte IPv4 header of your choice, showing the 16-bit word sum, the carry fold, and the final one's-complement.
- A before/after routing table from Dijkstra with Frankfurt up and with Frankfurt removed, with the new path and cost called out.
- A one-paragraph design rationale: which detection mechanism each of {Ethernet, IP, TCP, TLS} uses and why that granularity is right for that layer.

## Exercises

1. Take the IPv4 header `45 00 00 1C 00 00 40 00 40 11 ?? ?? 0A 00 00 01 0A 00 00 02` (a 20-byte UDP datagram). Compute the header checksum by hand as a one's-complement sum of the ten 16-bit words, then confirm with `internet_checksum()` in `code/main.py`.
2. A 1500-byte Ethernet frame carries a CRC-32 FCS. Two bits flip in adjacent bytes (a 2-bit burst) and another two bits flip 800 bytes apart. Which, if either, does CRC-32 still catch? Justify with the burst-length guarantee and the `2⁻³²` residual probability.
3. Encode the nibble `0b1011` with Hamming(7,4). Flip bit position 5 of the codeword and run the correction routine. Show the syndrome, the located bit, and the recovered nibble. Now flip *two* bits — what does the syndrome report, and why is correction unsafe?
4. In the `SlidingWindow` simulator with `window=4` and `loss_prob=0.2`, identify a run where frame 3 is lost and frame 4 arrives. Under Go-Back-N semantics, what does the sender retransmit, and how does that differ from Selective Repeat with SACK (RFC 2018)?
5. Add a fifth node, "Milan", connected to Rome and Paris with costs 2 and 5, to the routing topology in `code/main.py`. Re-run Dijkstra from London to Rome with Frankfurt removed. Does Milan ever appear on the shortest path? Prove it with the cost arithmetic.
6. The network layer drops a datagram whose header checksum fails, but it does *not* retransmit. The transport layer (TCP) does retransmit. Frame the trade-off in the textbook's own terms: why does the layer that sees many hops refuse the per-packet state that the end-to-end layer can afford?
7. A satellite link has a 600 ms RTT and a bit-error rate of `10⁻⁵`. Argue whether pure ARQ, pure FEC (Reed-Solomon), or hybrid ARQ is the right reliability mechanism, and quantify the retransmission cost ARQ would pay per 1500-byte frame that FEC would avoid.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| FCS | "the checksum at the end" | Frame Check Sequence — the 4-byte CRC-32 remainder an Ethernet NIC appends; a damaged frame is dropped at the link |
| CRC | "a fancy checksum" | Cyclic Redundancy Code — a polynomial remainder in GF(2); guarantees catching any burst ≤ the polynomial degree |
| One's-complement checksum | "the IP checksum" | A 16-bit end-around sum of 16-bit words, folded and inverted; cheap in software, weak against word reordering |
| ARQ | "retransmit on error" | Automatic Repeat reQuest — sequence numbers + ACKs + RTO so a sender retransmits frames the receiver did not get |
| Sliding window | "TCP's send buffer" | The number W of unacknowledged frames a sender may keep in flight; larger W fills a high-bandwidth×delay link |
| RTO | "the timeout" | Retransmission TimeOut — from RFC 6298, `SRTT + 4·RTTVAR`; too short causes spurious retransmits, too long stalls recovery |
| FEC | "forward correction" | Forward Error Correction — redundancy (Hamming, Reed-Solomon, Viterbi) that lets the receiver repair damage without a round trip |
| Link-state routing | "OSPF-style" | Each node floods its local link costs; all nodes run Dijkstra on the identical map; fast, loop-free convergence |
| Distance-vector routing | "RIP-style" | Each node advertises `(destination, cost)` to neighbors; cheap but vulnerable to count-to-infinity after a break |
| Count-to-infinity | "a routing loop bug" | A distance-vector failure where a broken route's cost climbs hop by hop until the horizon (RIP's 15) kills it |
| Dijkstra's algorithm | "shortest path" | Greedy expansion from the source: relax every neighbor of the settled node with the lowest tentative distance |
| Redundancy | "extra bits" | Information added beyond the data (check bits, sequence numbers, topology state) that lets a layer detect or recover from failure |

## Further Reading

- **RFC 1071** — Computing the Internet Checksum (the one's-complement algorithm used by IPv4/TCP/UDP).
- **RFC 9293** — Transmission Control Protocol (TCP) — the modern consolidated spec; pseudo-header checksum, sequence numbers, ACKs.
- **RFC 6298** — Computing TCP's Retransmission Timer (`SRTT`, `RTTVAR`, `RTO = SRTT + 4·RTTVAR`).
- **RFC 2018** — TCP Selective Acknowledgment Options (SACK, the mechanism Selective Repeat ARQ uses).
- **IEEE 802.3, clause 3.1.1** — Frame Check Sequence (CRC-32) field definition and the polynomial `0x04C11DB7`.
- **RFC 2328** — OSPF Version 2 (link-state routing with Dijkstra).
- **RFC 2453** — RIP Version 2 (distance-vector routing, hop-count horizon of 15).
- **RFC 4271** — BGP-4 (path-vector routing at the inter-domain scale).
- **RFC 8446** — TLS 1.3 (application-layer integrity via HMAC over the record + sequence number).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.3.2 "Design Issues for the Layers," and Chapter 3 (data link) for CRC/ARQ depth.
- Lin & Costello, *Error Control Coding*, 2nd ed. — Hamming, Reed-Solomon, and convolutional/Viterbi codes in full detail.
