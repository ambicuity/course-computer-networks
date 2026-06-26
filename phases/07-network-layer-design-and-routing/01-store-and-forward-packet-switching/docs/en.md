# Store-and-Forward Packet Switching

> Store-and-forward is the rule that a router must receive a packet *completely* and verify its frame check sequence (FCS) before forwarding it one hop closer to the destination. A router does not stream bits through; it buffers the whole frame, runs the CRC-32 check (the 4-byte Ethernet FCS, polynomial `0x04C11DB7`), drops it on mismatch, decrements the IPv4 TTL field (offset 8, 1 byte) or IPv6 Hop Limit, recomputes the 16-bit IPv4 header checksum (offset 10), does a longest-prefix-match lookup, and only then queues the packet on the outgoing link. This buffering is why per-hop latency is `transmission_time + propagation_time + queuing_delay + processing_delay`, and why a 1500-byte packet over a 10 Mbps link costs 1.2 ms of serialization *at every hop*. It is the foundation of both connectionless datagram networks (IP, RFC 791) and connection-oriented virtual-circuit networks (MPLS, RFC 3031). Failure modes include silent drops on FCS error, head-of-line blocking when an output queue fills, and the cumulative store-and-forward delay that hurts long multi-hop paths. The alternative, cut-through switching, forwards after reading only the 14-byte Ethernet header and trades integrity checking for ~half the latency.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Phase 03 (data link framing, CRC/FCS), Phase 04 (Ethernet, switches), IPv4 header layout
**Time:** ~75 minutes

## Learning Objectives

- Trace a single packet hop-by-hop through a store-and-forward router and account for each of the four delay components numerically.
- Identify the exact header fields a router reads and rewrites per hop: TTL/Hop Limit, header checksum, and the FCS that gates acceptance.
- Compute end-to-end store-and-forward delay for an N-hop path and explain why it grows linearly with packet size and hop count.
- Contrast store-and-forward with cut-through and fragment-free switching, naming the latency-vs-integrity tradeoff each makes.
- Explain why store-and-forward is a prerequisite for statistical multiplexing, checksum verification, and rate adaptation between links of different speeds.

## The Problem

A monitoring engineer sees a complaint: a file transfer between two data centers is "slow" even though every individual link reports 1 Gbps and almost no packet loss. `ping` shows 9 ms RTT. The path crosses 6 routers. The application team blames the network; the network team blames the application.

The real answer lives in the network layer. Each router on that path is a **store-and-forward** device: it pulls in the *entire* frame, checks the FCS, then transmits it onward. The packet is never on two links at once. So the serialization cost of putting bits on the wire is paid *once per hop*, not once total. With small packets and a deep path, those per-hop costs and the queuing behind them dominate. You cannot diagnose this with bandwidth numbers alone — you need to decompose latency into transmission, propagation, processing, and queuing delay at each hop. That decomposition is exactly what store-and-forward forces, and what this lesson makes concrete with `code/main.py`.

## The Concept

Store-and-forward packet switching is the operating principle of every IP router and every Ethernet switch in store-and-forward mode. The textbook statement (Tanenbaum, *Computer Networks*, §5.1.1) is precise: a host transmits a packet to the nearest router, *"the packet is stored there until it has fully arrived and the link has finished its processing by verifying the checksum. Then it is forwarded to the next router along the path until it reaches the destination host."*

The diagram in `assets/store-and-forward-packet-switching.svg` shows this as a three-router pipeline with a per-hop buffer, the checksum gate, and the four delay terms annotated on one hop.

### Why "store" before "forward"

A router cannot forward a frame it has not finished receiving, because the integrity check covers the whole frame. The 4-byte **Frame Check Sequence (FCS)** is the *last* field on the wire (Ethernet, IEEE 802.3). It is a CRC-32 over everything from the destination MAC through the payload. Until the final bit arrives, the router cannot know whether the frame is corrupt. Store-and-forward says: buffer it all, run the CRC, and only forward frames that pass. Corrupt frames are dropped silently at this layer — there is no NAK; loss recovery is left to higher layers (the end-to-end argument, Saltzer et al., 1984).

### The four delay components per hop

Each hop contributes four independent delays. Treat them as a sum:

| Component | What causes it | Depends on |
|---|---|---|
| Transmission (serialization) | Clocking bits onto the link | `packet_bits / link_rate` |
| Propagation | Signal travels the medium | `distance / propagation_speed` (~2e8 m/s in fiber) |
| Processing | Checksum, TTL, table lookup | Router CPU/ASIC, roughly fixed (µs) |
| Queuing | Waiting behind other packets | Output buffer occupancy (variable) |

Worked example: a 1500-byte packet (12,000 bits) over a 10 Mbps link has transmission delay `12000 / 10e6 = 1.2 ms`. Over 100 km of fiber, propagation is `100000 / 2e8 = 0.5 ms`. If processing is 20 µs and the output queue is empty, that hop costs `1.2 + 0.5 + 0.02 + 0 = 1.72 ms`. Cross 6 such hops with empty queues and you pay ~10.3 ms before any application logic runs — and the transmission term is paid *at every hop because the packet is fully buffered each time*. That is the slow-transfer mystery from The Problem.

### Fields a router reads and rewrites per hop

Store-and-forward is also a *rewrite* point. For an IPv4 datagram (RFC 791) the router:

| Field | Offset (bytes) | Size | Action per hop |
|---|---|---|---|
| Version/IHL | 0 | 1 | Read; locate header end |
| Total Length | 2 | 2 | Read; bound the buffer |
| TTL | 8 | 1 | **Decrement by 1; drop if it reaches 0** |
| Header Checksum | 10 | 2 | **Recompute (16-bit ones'-complement)** |
| Destination Address | 16 | 4 | Read; longest-prefix-match lookup |

Because TTL changes, the header checksum *must* be recomputed every hop (RFC 1071 incremental update is the optimization). When TTL hits 0 the router drops the packet and emits ICMP Time Exceeded (Type 11) — this is exactly the mechanism `traceroute` exploits. `code/main.py` performs all of these steps so you can watch TTL fall and the checksum change across a path.

### End-to-end delay and pipelining

For a path of N store-and-forward hops carrying a single packet, end-to-end transmission delay is `N × (packet_bits / link_rate)` when all links share a rate — the packet is serialized N times. But a *stream* of packets pipelines: while router 2 transmits packet 1, router 1 can transmit packet 2. So for P packets the total is approximately `(N + P − 1) × transmission_time` plus propagation and queuing, not `N × P`. Breaking a long message into many small packets therefore *fills the pipeline* and overlaps serialization across hops — one of the original arguments for packet switching over circuit switching.

### Store-and-forward vs cut-through vs fragment-free

| Mode | Forwards after reading | Latency | Integrity | Use |
|---|---|---|---|---|
| Store-and-forward | Entire frame + FCS verified | Highest (full serialization/hop) | Drops corrupt frames | IP routers; default switching |
| Cut-through | 14-byte dest-MAC header only | ~Lowest | Forwards corrupt frames | Ultra-low-latency fabrics |
| Fragment-free | First 64 bytes (collision window) | Middle | Catches runts/collisions | Legacy Ethernet compromise |

Store-and-forward is mandatory when adjacent links differ in speed (you must buffer to rate-adapt from a 10 Gbps to a 1 Gbps link) and whenever you want to discard corrupt frames before they consume downstream capacity. Cut-through cannot rate-adapt and forwards errors it could not yet detect.

### Connectionless and connection-oriented both rely on it

Store-and-forward is independent of the *service model*. In a **datagram** network (connectionless, IP) each packet carries the full destination address and is routed independently — A's forwarding table maps destination to outgoing line, and the table can change mid-flow so two packets to the same host may take different paths. In a **virtual-circuit** network (connection-oriented, MPLS RFC 3031, ATM, Frame Relay) a path is set up first and packets carry a short label, but each switch *still* stores the whole cell/frame, checks it, swaps the label, and forwards. The store-and-forward mechanic is the same; only the lookup key (destination address vs. VC/label) differs.

## Build It

1. Read the IPv4 header layout and confirm the offsets of TTL (8) and Header Checksum (10).
2. Open `code/main.py`. It builds a real IPv4 header, computes the RFC 1071 ones'-complement checksum, and defines a small topology with per-link rates and distances.
3. Run it: `python3 main.py`. Watch the per-hop trace — TTL decrementing, the header checksum changing each hop, and the four delay terms summed per hop.
4. Change `PACKET_BYTES` from 1500 to 64 and rerun. Note how transmission delay collapses but processing/propagation now dominate.
5. Add a hop with a 1 Gbps link feeding a 100 Mbps link and observe how the slow link's transmission delay dominates end-to-end time — the rate-adaptation case store-and-forward exists to handle.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decompose latency | Per-hop transmission/propagation/queuing/processing from the trace | You can say which term dominates and why, not just "the network is slow" |
| Verify integrity gating | FCS/checksum check before forward in the trace | Corrupt packet is dropped at the hop, never reaches the next router |
| Read the TTL story | TTL value falling 64→63→62… per hop | You predict where a TTL=2 packet dies and what ICMP it triggers |
| Justify packet size | End-to-end time for 64B vs 1500B over N hops | You explain the pipelining/MTU tradeoff with numbers |

## Ship It

Produce one artifact under `outputs/`:

- A per-hop latency-budget worksheet that decomposes a real path into the four delay terms.
- A one-page runbook: "transfer is slow but links are fast" → store-and-forward decomposition checklist.
- The annotated topology + delay diagram derived from `assets/store-and-forward-packet-switching.svg`.

Start from the output of `code/main.py` and paste a real trace into the worksheet.

## Exercises

1. A 9000-byte jumbo frame crosses 4 hops at 1 Gbps each, 50 km fiber per hop, 15 µs processing, empty queues. Compute end-to-end delay. Now redo it for 1500-byte frames carrying the same 9000 bytes of payload (6 packets, pipelined). Which is faster end-to-end, and why?
2. A packet enters a router with TTL=1. Walk through exactly what the router does, which fields it touches, what it forwards (if anything), and what ICMP message (Type/Code) it generates.
3. A switch is reconfigured from store-and-forward to cut-through. A burst of frames arrives with a CRC error in the payload. Describe what now reaches the destination NIC and at which layer the error is finally caught.
4. Two adjacent links run at 10 Gbps and 1 Gbps. Explain why cut-through is impossible here and store-and-forward is mandatory. What buffer behavior emerges if the 10 Gbps link sustains line rate?
5. Using `code/main.py`, corrupt one byte of the payload before the checksum step and rerun. Show that the receiving hop rejects it. Why does the *header* checksum not protect the payload, and what does?
6. In a virtual-circuit (MPLS) network the destination address lookup is replaced by a label swap. Explain why store-and-forward delay is unchanged by this substitution, and what *does* change in the per-hop processing cost.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Store-and-forward | "The router passes the packet along" | The router buffers the *entire* frame, verifies the FCS, then forwards — never streams bits through |
| FCS | "Error checking" | The 4-byte CRC-32 trailer (IEEE 802.3) the router uses to drop corrupt frames before forwarding |
| Transmission delay | "Bandwidth" | `packet_bits / link_rate`, paid *once per hop* under store-and-forward |
| Propagation delay | "Distance lag" | `distance / propagation_speed`, independent of packet size or link rate |
| TTL / Hop Limit | "How long it lives" | A hop counter (IPv4 byte 8) decremented each router; 0 → drop + ICMP Time Exceeded |
| Header checksum | "Checksum" | The 16-bit ones'-complement check over the IPv4 header only, recomputed every hop because TTL changed |
| Cut-through | "Faster switching" | Forwards after the 14-byte header — lower latency, cannot verify FCS or rate-adapt |
| Datagram vs virtual circuit | "Connectionless vs connection" | Different lookup keys (address vs label) over the *same* store-and-forward mechanic |

## Further Reading

- RFC 791 — *Internet Protocol* (IPv4 header, TTL, header checksum).
- RFC 1071 — *Computing the Internet Checksum* (the ones'-complement algorithm and incremental update).
- RFC 1812 — *Requirements for IP Version 4 Routers* (per-hop forwarding rules, TTL handling).
- RFC 3031 — *Multiprotocol Label Switching Architecture* (store-and-forward in a connection-oriented network).
- IEEE 802.3 — Ethernet framing and the 32-bit FCS / CRC-32.
- Saltzer, Reed, Clark (1984) — *End-to-End Arguments in System Design* (why integrity/recovery sit above the network).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §5.1.1 (Store-and-Forward Packet Switching) and §5.1.3 (datagram networks).
