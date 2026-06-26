# Multiplexing

> Multiplexing is the sharing of a scarce resource across many users. In the transport layer, the scarce resource is the **network address (NSAP)**: most hosts have one IP, but they may run thousands of transport connections at once. The transport entity demultiplexes incoming segments to the right socket by reading the destination port (and, for some flows, a 4-tuple). Tanenbaum's §6.2.5 contrasts two directions: **upward multiplexing** (many transport connections sharing one network connection, the common case) and **downward (inverse) multiplexing** (one transport connection distributing its traffic across several network paths, used by SCTP and by link-aggregation protocols but not by TCP). The tradeoff is concrete: upward mux saves addresses, downward mux increases throughput and resilience.

**Type:** Build
**Languages:** Python (stdlib-only multiplexer simulator)
**Prerequisites:** Berkeley Sockets (lesson 03), Error Control and Flow Control (lesson 07)
**Time:** ~65 minutes

## Learning Objectives

- Explain why one host with one IP address can serve thousands of transport connections, and what the transport entity's demultiplexing table looks like.
- Draw Fig. 6-17(a) - four distinct transport connections sharing one NSAP - and identify the 4-tuple (source IP, source port, dest IP, dest port) that the kernel uses as the demux key.
- Implement round-robin inverse multiplexing (Fig. 6-17(b)) and show that the effective bandwidth is approximately k * single_path_bandwidth, where k is the number of paths.
- Distinguish TCP (single NSAP per connection) from SCTP (multi-homing, can use multiple NSAPs) and from MPTCP (multi-path TCP, RFC 8684) at the level of "how many NSAPs does a transport connection span?"
- Calculate the bandwidth gain of inverse multiplexing for a 3-path setup where each path has independent 100 Mbps capacity and 20 ms RTT.

## The Problem

A streaming-video service reports that its peak-hour throughput to mobile clients is bounded by the single-Wi-Fi path on the client's phone. When the phone moves to a cell with both Wi-Fi and LTE, the service could in principle use both, but TCP forces it to pick one. The product team wants "bonded" connections that combine both paths.

The textbook's answer is inverse multiplexing (Fig. 6-17(b)): one transport connection whose segments are distributed round-robin across k network paths. SCTP supports this natively via its multi-homing feature (RFC 4960). MPTCP (RFC 8684) adds it to TCP. The kernel picks the next path for each segment, the receiver reassembles, and the application sees a single byte-stream connection that runs at the sum of the path bandwidths.

The complementary problem on the server side is upward multiplexing: 50,000 simultaneous HTTP connections share one IP address. The kernel maintains a demultiplexing table keyed on the 4-tuple `(src_ip, src_port, dst_ip, dst_port)` and dispatches each incoming segment to the right socket. Without port-based demultiplexing, the server could not run more than one socket at a time.

This lesson is the toolkit for both directions of the multiplexing question.

## The Concept

### Upward multiplexing (Fig. 6-17(a))

The common case. One network address (one NSAP, e.g. `10.0.1.5`) carries many transport connections. The transport entity at the receiving host maintains a table:

| Local IP | Local port | Remote IP | Remote port | Socket |
|---|---|---|---|---|
| 10.0.1.5 | 80 | 203.0.113.7 | 51234 | conn 1 |
| 10.0.1.5 | 80 | 198.51.100.42 | 44321 | conn 2 |
| 10.0.1.5 | 22 | 203.0.113.7 | 51240 | conn 3 |
| 10.0.1.5 | 443 | 198.51.100.42 | 44322 | conn 4 |

When a TCP segment arrives, the kernel reads the 4-tuple in the IP + TCP headers and looks it up. The matched socket's receive queue gets the segment's payload. The application that owns the socket does a `recv()` and gets the bytes.

The 4-tuple is what makes the demultiplex unambiguous even when two remote peers happen to use the same source port. As long as the source IP, source port, destination IP, and destination port 4-tuple differs, the segments go to different sockets.

The same port on the same IP can carry thousands of inbound connections because the *destination* port is shared (e.g. 80 for HTTP) but the *source* port is the client's ephemeral port, and that is enough to disambiguate.

### Why port numbers are enough

Each transport connection is identified by the 4-tuple. The 16-bit port space on each end is large (65,536 values), so the effective key space is `2^16 * 2^32 * 2^16 * 2^32 = 2^96`, far more than the IPv4 address space can route. A single web server with port 80 open can have 2^32 * 2^16 = ~280 trillion theoretical connections; in practice, the kernel's connection-tracking table and the file-descriptor limit are the bottleneck.

### Downward (inverse) multiplexing (Fig. 6-17(b))

The other direction. One transport connection is split across k network connections. Each network connection is its own NSAP (e.g. a different Wi-Fi interface and a different LTE interface on the same device). The transport entity distributes segments across the k paths:

- **Round-robin**: segment 1 on path A, segment 2 on path B, segment 3 on path C, segment 4 on path A, ...
- **Weighted round-robin**: paths with more capacity get more segments
- **Lowest-RTT-first**: send on the path with the smallest RTT estimate
- **Redundant**: send the same segment on multiple paths for resilience (used by some financial networks)

The receiver buffers segments and reassembles them in sequence-number order. If path B drops a segment, the receiver waits for the retransmit; the sender's RTO is based on the worst of the k paths unless it tracks them separately.

SCTP's multi-homing does this for "initially active" plus "standby" paths - it can fail over in milliseconds, but it does not aggregate bandwidth by default. MPTCP's "coupled" congestion control does aggregate, by running a separate cwnd per subflow but coupling the total across them.

### The bandwidth gain (worked example)

Setup: 3 paths, each 100 Mbps capacity, 20 ms RTT, independent congestion.

- Single-path TCP: throughput = min(cwnd / RTT, link_capacity). With cwnd saturating, throughput ~= 100 Mbps.
- Inverse-muxed transport: throughput = sum of paths = 300 Mbps * efficiency_factor.

The efficiency factor accounts for:
- Reordering: if paths have different RTTs, segments arrive out of order, the receiver buffers, the cwnd cannot grow as aggressively
- Loss correlation: if paths share a bottleneck (e.g. the same upstream ISP), losses are correlated
- Per-path RTO: a loss on the slowest path blocks the whole connection unless each path has its own RTO

In practice, inverse multiplexing delivers 60-90% of the sum-of-bandwidths. The textbook's wording is careful: "the effective bandwidth might be increased by a factor of k."

### Why TCP does not do this

TCP binds a connection to a single 4-tuple. The connection is identified by `(src_ip, src_port, dst_ip, dst_port)`. If the client's IP changes (Wi-Fi to LTE handoff), the 4-tuple changes, and the connection is effectively a new one. The kernel's `tcp_migrate` and mobile-IP tricks work around this for vertical handoffs, but they are hacks.

SCTP's multi-homing and MPTCP fix this at the protocol level by allowing a single transport connection to span multiple addresses. MPTCP is increasingly deployed: Apple uses it for Siri, Cisco for some products, Korean ISP KT for bandwidth aggregation. SCTP is in the Linux kernel and in some telecom stacks.

### Where multiplexing appears at other layers

The textbook notes that multiplexing is not unique to the transport layer. Examples:

| Layer | Multiplexing | Inverse multiplexing |
|---|---|---|
| Link | Ethernet switch: many hosts on one wire | Link aggregation (LACP, IEEE 802.3ad) |
| Network | IP: many flows share one router | (Rare) MPLS LSP bundling |
| Transport | Port numbers demux to sockets | MPTCP, SCTP multi-homing |
| Application | HTTP/2 streams share one TCP connection | HTTP/3 over QUIC (multiple UDP paths) |

The pattern recurs at every layer: share an expensive resource, demultiplex at the receiver.

## Build It

`code/main.py` implements both directions:

1. **Upward multiplexer** - a `ConnectionTable` keyed on the 4-tuple, a `Multiplexer` that dispatches incoming segments to the right socket by exact match, and a simple `accept` loop that creates a new socket per arriving connection. The simulator prints the 4-tuple for every segment and the socket it was dispatched to.
2. **Inverse multiplexer** - a `RoundRobinMux` that takes one transport connection's segment stream and distributes it across k network paths. The simulator runs a 3-path case with synthetic 100 Mbps paths and 20 ms RTT, and reports the effective throughput.
3. **Demultiplexing decision** - given an incoming segment, the simulator shows which 4-tuple fields are read, in what order, and where in the table the match is found.
4. **Efficiency calculation** - the simulator's inverse-muxed throughput vs. the sum of single-path throughputs, with a configurable reordering penalty.

Run with `python3 code/main.py`. Pass `--paths=N` to change the number of inverse-mux paths. The output shows the per-path segment count and the aggregate throughput.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Demux a 4-tuple | segment's src/dst IP and src/dst port | One match in the connection table; the segment goes to that socket's recv queue |
| Detect a missing slot | the 4-tuple has no entry | The kernel sends a RST; the application sees `ECONNRESET` |
| Compute inverse-mux bandwidth | 3 paths x 100 Mbps | Effective throughput 200-300 Mbps depending on reordering |
| Decide SCTP vs MPTCP | the application's needs | SCTP for messaging with multi-homing; MPTCP for TCP-compatible bandwidth aggregation |
| Diagnose MPTCP failure | `ss -M` shows subflows stuck | One path's RTO firing on every loss; check `net.mptcp.subflow_failures` |
| Spot LACP at the link layer | `ip link show` shows `bond0` | Multiple NICs aggregated; the same pattern as inverse mux, one layer down |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **4-tuple reference card** showing exactly which fields are read, in which order, and where in the kernel the lookup happens.
- An **inverse-mux decision matrix** - when to use round-robin vs weighted vs lowest-RTT, with the bandwidth math for each.
- A **TCP vs SCTP vs MPTCP comparison table** with one-line deployment guidance for each.
- A **link-layer to transport-layer multiplexing map** showing how the same pattern recurs at every layer.

Start from `outputs/prompt-multiplexing.md`.

## Exercises

1. A server has IP `10.0.1.5` and listens on port 80. Two clients connect: client A from `203.0.113.7:51234`, client B from `203.0.113.7:51235`. The server's connection table has two entries. What are the four 4-tuple fields for each?
2. Inverse multiplexing across 4 paths, each 50 Mbps, 30 ms RTT. What is the maximum possible effective throughput? What is the realistic range given typical reordering?
3. A MPTCP connection has 3 subflows. Subflow 1 has cwnd=10, subflow 2 has cwnd=4, subflow 3 has cwnd=2. How many bytes may the sender have in flight? What happens when subflow 2 times out?
4. The textbook says "the effective bandwidth might be increased by a factor of k." Why "might" rather than "will"?
5. A SCTP association is multi-homed with 2 addresses. The primary path fails. How long does the failover take? What does the application see?
6. Run `code/main.py`'s inverse-mux simulator with `--paths=1, --paths=3, --paths=10` and report the effective throughput. Explain the shape of the curve.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Multiplexing | "many over one" | Sharing a scarce resource (an address, a link, a socket) across many users |
| 4-tuple | "the connection key" | `(src_ip, src_port, dst_ip, dst_port)`; what the transport entity uses to demux incoming segments to sockets |
| Upward mux | "TCP clients on one IP" | Many transport connections sharing one network connection; the common case |
| Downward (inverse) mux | "split the connection" | One transport connection distributed across multiple network paths; SCTP, MPTCP |
| MPTCP | "multi-path TCP" | RFC 8684; allows a single TCP byte stream to span multiple 4-tuples via subflows |
| SCTP multi-homing | "one association, many addresses" | RFC 4960; the transport association has a primary path plus standbys for failover |
| Connection table | "the demux table" | The kernel's map of 4-tuples to sockets; the data structure that makes upward mux work |
| LACP | "link aggregation" | IEEE 802.3ad; link-layer inverse mux; same pattern, one layer down |
| QUIC | "HTTP/3's transport" | UDP-based transport that natively supports connection migration and (with extensions) multi-pathing |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §6.2.5** - the source chapter for this lesson (Fig. 6-17).
- **Stevens, W. R. (1994), *TCP/IP Illustrated, Volume 1*, §18.2** - the 4-tuple and the connection table in BSD.
- **RFC 4960** (2007), "Stream Control Transmission Protocol" - the canonical multi-homing transport protocol.
- **RFC 8684** (2020), "TCP Extensions for Multipath Operation with Multiple Addresses" - MPTCP.
- **Ford, A., Raiciu, C., Handley, M., & Bonaventure, O. (2013), "TCP Extensions for Multipath Operation with Multiple Addresses," RFC 6824** - the original MPTCP proposal.
- **`man 7 tcp` on Linux** - the kernel's `TCP_REPAIR`, `TCP_FASTOPEN`, and connection-migration knobs.
- **Raiciu, C. et al. (2011), "How Hard Can It Be? Designing and Implementing a Deployable Multipath TCP"** - the experience report from the first real MPTCP deployment.
- **Pahdye, J. & Floyd, S. (2000), "On Inferring TCP Behavior"** - the bandwidth-delay product framework that inverse-mux scheduling builds on.
