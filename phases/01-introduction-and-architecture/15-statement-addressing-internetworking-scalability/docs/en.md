# Addressing, Internetworking, and Network Scalability

> Three recurring design issues cut across every layer of a network stack: **addressing** (how each layer names the sender and receiver of a message), **internetworking** (how heterogeneous networks that disagree on packet size, ordering, and addressing are glued together), and **scalability** (how the design behaves as the number of nodes grows from a room to the planet). Addressing shows up as 48-bit IEEE 802 MAC addresses at the link layer (RFC 5342), 32-bit IPv4 and 128-bit IPv6 addresses at the network layer (RFC 791, RFC 8200), and 16-bit TCP/UDP port numbers at the transport layer (RFC 768, RFC 9293). Internetworking forces **fragmentation and reassembly** when a packet exceeds a link's **MTU** — IPv4 carries 3 flag bits (`DF`, `MF`, reserved) and a 13-bit **fragment offset** in units of 8 bytes, and a router that cannot forward a 1500-byte frame onto a 576-byte link either splits it or, if `DF` is set, returns ICMP Type 3 Code 4 (RFC 792). Scalability is won with **hierarchical addressing** (CIDR, RFC 4632) so routers keep only prefixes, not per-host routes; with **subnetting** that splits a prefix via a mask; and lost catastrophically when designs that worked in a lab hit counting rules that grow as O(n²) or O(n log n). The classic failure modes are flat address spaces that bloat every routing table, fragmentation that fragments again (cascading fragments), and reassembly buffers that fragment under attack (the original RFC 815 algorithm). This lesson builds a runnable IPv4 fragmenter/reassembler, a CIDR subnet calculator, and a routing-table growth model so you can watch the mechanisms the textbook lists under "design issues for the layers."

**Type:** Learn
**Languages:** Python
**Prerequisites:** Protocol layering and service interfaces (earlier Phase 1 lessons); the IP/TCP header as a layered container; binary and hex basics
**Time:** ~85 minutes

## Learning Objectives

- Identify the addressing element used at each layer (MAC, IP, port) and explain why a flat global address space does not scale to 10⁹ hosts.
- Given an IPv4 datagram and a link MTU, compute the fragment sizes, fragment offsets, and the `MF` flag value for each fragment.
- Distinguish IPv4 in-network fragmentation (routers split) from IPv6 Path MTU Discovery (RFC 8201, senders split), and explain why IPv6 routers never fragment.
- Apply CIDR notation to split a prefix into subnets, compute network/broadcast/host range, and reason about routing-table aggregation.
- Contrast the three scalability levers — hierarchy, aggregation, and statistical multiplexing — and predict which one a given design relies on.
- Read a fragment reassembly buffer state and detect a reassembly-overflow or overlap attack.

## The Problem

A company connects two sites over an MPLS link with a 1500-byte MTU, but one branch sits behind a VPN concentrator that lowers the effective MTU to 1400 bytes, and a remote worker dials in over PPPoE, which adds 8 bytes of header and drops the MTU to 1492. An application sends a 1472-byte UDP payload in a single IPv4 datagram (1500 bytes on the wire including the 20-byte IP header and 8-byte UDP header). It leaves the first site fine. At the VPN concentrator the datagram is too big. The concentrator splits it. At the PPPoE link the first fragment is too big *again*, and splits a second time. The receiving host now has to reassemble three fragments into one UDP datagram — and one fragment never arrives, so the reassembly timer (RFC 791, default 30–60 seconds) expires and the *entire* datagram is silently dropped.

Meanwhile the operator is told that the corporate network just grew from 4,000 hosts to 400,000 hosts after a merger, and the routing table on the core router tripled because the acquired company used flat /24 allocations. Both are the textbook's design issues in the flesh: **internetworking** (different links with different MTUs and different packet-size limits) and **scalability** (the design that worked at 4,000 hosts collapses at 400,000). The tools to reason about them are an addressing hierarchy, fragmentation, and aggregation.

## The Concept

### Addressing at every layer: who is the receiver?

The textbook puts it bluntly: "every layer needs a mechanism for identifying the senders and receivers." Each layer has its own address space, and a packet carries one address from each layer simultaneously.

| Layer | Address | Size | Authority / RFC | Scope |
|---|---|---|---|---|
| Link | IEEE 802 MAC address | 48 bits (EUI-48) | RFC 5342, OUI assigned by IEEE | One broadcast domain |
| Network (v4) | IPv4 address | 32 bits | RFC 791, IANA → RIR → LIR | Globally routable (or RFC 1918 private) |
| Network (v6) | IPv6 address | 128 bits | RFC 8200, format in RFC 4291 | Globally routable or link-local `fe80::/10` |
| Transport | Port number | 16 bits | RFC 768 (UDP), RFC 9293 (TCP) | One host, one protocol |

A 48-bit MAC is flat and burned into the NIC; it names an *interface*, not a location, which is why a packet cannot be routed across the Internet using only MAC addresses. A 32-bit IPv4 address is hierarchical: the left bits are the *network prefix* (where the host lives) and the right bits are the *host identifier* (which host on that network). That split is what makes routing tables small — a router only needs to know the prefix `198.51.100.0/24`, not the 254 hosts behind it. A port number is a 16-bit demultiplexing key that lets one IP carry many concurrent conversations; the tuple `(src IP, src port, dst IP, dst port, protocol)` uniquely identifies a TCP connection (RFC 6275 calls this the *5-tuple*).

### Flat vs hierarchical: why flat does not scale

Imagine every router on the Internet held a route for every host. At ~4.3 billion IPv4 addresses, even a perfect table would need billions of entries — far beyond feasible forwarding-hardware memory (the modern DFZ — Default-Free Zone — already carries ~1 million entries in 2024, and that is *with* aggressive aggregation). The fix is **hierarchy**: a router far away keeps one entry per *network*, not per host. A core router in Frankfurt does not know that `198.51.100.42` is host 42 in some building; it only knows how to reach `198.51.0.0/16`, handed off to a regional router, which knows `198.51.100.0/24`, handed off to a site router, which knows the host.

| Property | Flat address space | Hierarchical address space |
|---|---|---|
| Table size | O(hosts) | O(networks) |
| Address assignment | anywhere | topologically clustered |
| Mobility | easy (address = identity) | hard (address = location) |
| Real example | Ethernet MAC | IPv4/IPv6 prefix |

This is the root tension Mobile IP (a later lesson) has to resolve: hierarchical addresses conflate *identity* and *location*. When you move, your location changes but you want your identity to stay.

### CIDR and subnetting: the modern split

Classful addressing (RFC 791) carved IPv4 into fixed /8, /16, /24 classes and wasted millions of addresses. **CIDR** (Classless Inter-Domain Routing, RFC 4632) replaced it in 1993 with variable-length prefixes written `a.b.c.d/n`, where *n* is the prefix length. The remaining `32 - n` bits are the host part.

Worked example: `198.51.100.0/24`.

```
Address:  198.51.100.0   = 11000110.00110011.01100100.00000000
Mask /24: 255.255.255.0  = 11111111.11111111.11111111.00000000
Network:  198.51.100.0   (host bits zeroed)
Broadcast:198.51.100.255 (host bits set)
Hosts:    2^(32-24) - 2 = 254 usable
```

A `/26` gives 62 usable hosts, a `/22` gives 1022. Subnetting splits a `/24` into four `/26`s: `198.51.100.0/26`, `.64/26`, `.128/26`, `.192/26`. `code/main.py` implements this arithmetic and shows the per-subnet network/broadcast/host-range so you can verify the math by hand. The reverse — **supernetting** or **route aggregation** — lets one router advertise `198.51.0.0/16` instead of 256 `/24`s, which is the single biggest reason the DFZ routing table stays in the millions rather than the billions.

### Internetworking: when networks disagree

The textbook defines internetworking as the problem that arises when "different network technologies often have different limitations." Two disagreements dominate:

1. **Packet size.** Ethernet carries 1500-byte frames; classic X.25 carried 576; jumbo Ethernet frames carry 9000; an IPv4 host must be able to receive a 576-byte datagram (RFC 791). When a 1500-byte datagram hits a 576-byte link, something has to give.
2. **Ordering.** Some lower-layer networks deliver packets out of order. Higher layers that assume in-order delivery need per-packet sequence numbers.

The IP answer to (1) is **fragmentation**: the router (IPv4) or the sender (IPv6) splits the datagram into pieces that fit, each carrying enough header for the receiver to glue them back.

### IPv4 fragmentation, field by field

The IPv4 header (RFC 791) carries three fields that drive fragmentation:

| Field | Bits | Role in fragmentation |
|---|---|---|
| Identification | 16 | Same value on every fragment of one datagram; the reassembly key |
| Flags | 3 | bit 0 reserved (0); bit 1 `DF` (Don't Fragment); bit 2 `MF` (More Fragments) |
| Fragment Offset | 13 | Position of this fragment's payload, in units of **8 bytes**, from the start of the original datagram |

Worked example: a 4000-byte datagram (20-byte IP header + 3980-byte payload) hits a 1500-byte MTU. Each fragment gets its own 20-byte IP header, so the maximum *payload* per fragment is 1480 bytes — and 1480 is divisible by 8, which the offset field demands.

| Fragment | Payload bytes | Offset (field value) | `MF` | Total length |
|---|---|---|---|---|
| 1 | 0–1479 (1480) | 0 | 1 | 1500 |
| 2 | 1480–2959 (1480) | 185 (= 1480/8) | 1 | 1500 |
| 3 | 2960–3979 (1020) | 370 (= 2960/8) | 0 | 1040 |

The last fragment clears `MF`. The receiver buffers fragments keyed by `(src IP, dst IP, identification, protocol)`, waits until offset-0 and an `MF=0` fragment arrive with no gaps, then reassembles. `code/main.py` reproduces this exact split, prints every fragment, and reassembles them to prove the payload is byte-identical.

If the router cannot fragment (because `DF=1`) and the datagram exceeds the MTU, it drops the packet and sends **ICMP Destination Unreachable, Code 4 "Fragmentation Needed and DF Set"** (RFC 792). Modern PMTUD (RFC 1191, RFC 8201) uses that ICMP message to tell the sender to shrink.

### IPv6: routers stop fragmenting

IPv6 (RFC 8200) removes the in-router fragmentation machinery entirely. An IPv6 router that receives a packet too big for the next link drops it and sends **ICMPv6 Packet Too Big** (Type 2); the *sender* is expected to run **Path MTU Discovery** (RFC 8201) and size packets to fit. A host that must fragment puts each fragment in a normal IPv6 packet with a **Fragment extension header** (Next Header 44) carrying a 32-bit Identification, a 13-bit offset (still 8-byte units), and an `M` flag — conceptually identical to IPv4 but moved off the fast path. The minimum IPv6 MTU is 1280 (RFC 8200); links below that must do link-layer fragmentation invisibly.

### Reassembly state and the reassembly timer

Reassembly is stateful and bounded. RFC 791 sets a reassembly timer (commonly 30 s, up to 60 s); if it expires before all fragments arrive, the partial datagram is discarded. A naive reassembly buffer is also an attack target: overlapping fragments (the "Rose attack") or fragments that claim huge offsets can exhaust buffer memory or fool header inspection. RFC 815 gave the first correct algorithm — a hole descriptor list merged as fragments arrive, with explicit rules that overlapping data from an *earlier* fragment is discarded. Modern stacks simply reject overlaps outright. See the SVG `assets/addressing-internetworking-scalability.svg` for the fragment-layout diagram.

### Scalability: hierarchy, aggregation, and statistical multiplexing

The textbook names scalability last: "designs that continue to work well when the network gets large are said to be scalable." Three levers do most of the work:

| Lever | Mechanism | Where it bites |
|---|---|---|
| **Hierarchy** | Address = location prefix + host part | Routing-table size: O(networks) not O(hosts) |
| **Aggregation** | Advertise one prefix instead of many | DFZ table growth; the merging-company problem |
| **Statistical multiplexing** | Share bandwidth by demand, not by fixed reservation | Link utilization; bursts average out |

Statistical multiplexing is the textbook's own phrasing: "sharing based on the statistics of demand." A TDM (Time-Division Multiplexing) link that gives each of N hosts 1/N of the bandwidth wastes the unused share when a host is idle; a statistically multiplexed link lets an active host borrow the idle share, with the risk that all N burst at once and create congestion. That risk is what **flow control** (receiver-paced) and **congestion control** (network-paced) exist to manage — but they are separate lessons. For this lesson the point is that the *same* idea — divide the resource so one host does not starve the others — recurs at every layer, just as addressing and fragmentation do.

### A growth model: when does aggregation break?

`code/main.py` also models routing-table growth. If every new site advertises its own `/24`, the table grows linearly with the number of sites. If a regional ISP can aggregate 256 of its customers' `/24`s into one `/16`, the table grows as 1 entry per ISP, not 1 per customer. The model prints both curves so you can see the divergence: at 65,536 customer sites, the flat model needs 65,536 routes and the aggregated model needs 256 — a 256× reduction from hierarchy alone. When the acquired company in the problem scenario used flat `/24`s, the operator's table tripled because no prefix covered the new sites; reaggregating them under a single `/20` would have added one entry instead of thousands.

## Build It

1. Read `code/main.py`. Three modules sit side by side: `ipv4_fragment(datagram, mtu)`, `reassemble(fragments)`, and `cidr_subnets(prefix, new_prefix)`, plus `routing_table_growth()` for the aggregation model.
2. Run it: `python3 code/main.py`. The demo fragments a 4000-byte datagram to a 1500-byte MTU, prints every fragment with its offset and `MF` bit, then reassembles and asserts the payload is byte-identical.
3. Inspect the CIDR block: the demo splits `198.51.100.0/24` into four `/26`s and prints network, broadcast, and host range for each — verify against the worked example above.
4. Change the MTU in `main()` to 576 (the RFC 791 minimum) and rerun. Count the fragments; note that the offset field's 8-byte granularity forces each fragment's payload length to be a multiple of 8.
5. Drive `routing_table_growth(65536)` and read the flat-vs-aggregated route counts.
6. Re-read `assets/addressing-internetworking-scalability.svg` to map the fragment layout to the offsets the code prints.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm fragmentation is correct | Fragment offsets are multiples of 8, payloads fit the MTU minus 20, last fragment clears `MF` | Reassembled payload equals the original byte-for-byte |
| Justify `DF` + PMTUD | ICMP Type 3 Code 4 returned when a too-big datagram has `DF=1`; sender shrinks and retries | No fragments on the wire; sender learns the path MTU |
| Verify a CIDR split | Each subnet's network and broadcast addresses are 64 apart for a `/26`; no subnet overlaps another | Usable host count = 2^(32-n) - 2 |
| Detect a reassembly hazard | Overlapping offsets, or a fragment whose offset + length exceeds the buffer | The reassembler rejects overlaps rather than silently merging |
| Quantify aggregation gain | Flat route count vs aggregated route count for N sites | Aggregation reduces the table by the aggregation factor (e.g., 256× for /24 → /16) |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/prompt-addressing-internetworking-scalability.md`: an annotated run of `code/main.py` showing (a) the fragment table for a 4000-byte datagram at MTU 1500, (b) the CIDR subnet table for `198.51.100.0/24` → four `/26`s, and (c) the flat-vs-aggregated routing-table growth numbers. For each, write one paragraph explaining which design issue (addressing, internetworking, scalability) it demonstrates and the failure mode it prevents.

## Exercises

1. A 6000-byte IPv4 datagram (20-byte header, 5980-byte payload) crosses a link with a 1500-byte MTU. Compute every fragment's total length, fragment offset field value, and `MF` flag. Verify the offsets are multiples of 8.
2. The same datagram has `DF=1` and the next link is 1400-byte MTU. Describe exactly what the router does, including the ICMP message type and code it sends back, and what the sender does next under Path MTU Discovery (RFC 1191).
3. Split `10.0.0.0/16` into `/23` subnets. How many subnets result? Give the network and broadcast address of the first three and the usable-host count per subnet.
4. Why does IPv6 (RFC 8200) forbid routers from fragmenting, and what is the minimum link MTU? Describe the Fragment extension header (Next Header 44) fields that let the *sender* fragment instead.
5. An acquired company advertises 1,024 individual `/24` prefixes. Show how a single `/20` aggregate could replace them and compute the routing-table reduction. Then give one real reason a provider might be unable to aggregate them (discontiguous blocks).
6. Two fragments arrive for reassembly: offset 0 length 1480, and offset 1480 length 1480 — both `MF=1`, but no further fragment arrives. Describe the reassembly timer behavior (RFC 791) and what the receiver does when it fires.
7. Statistical multiplexing lets an idle host's bandwidth be borrowed by a busy one. Name the two problems this introduces and the two control mechanisms (one receiver-paced, one network-paced) that manage them.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Address | "an IP" | A layer-specific identifier naming the receiver of a message; every layer has its own (MAC, IP, port) |
| CIDR | "slash notation" | Classless Inter-Domain Routing (RFC 4632): `a.b.c.d/n` with a variable-length prefix, replacing fixed classful A/B/C |
| Prefix length | "the /24 part" | The number of leading bits that are the network; the rest are host bits |
| Fragment offset | "position field" | A 13-bit field giving this fragment's payload position in 8-byte units from the datagram start |
| `MF` flag | "more flag" | More-Fragments bit; set on all fragments except the last, which clears it to mark the tail |
| `DF` flag | "don't split" | Don't-Fragment bit; if set and the datagram exceeds MTU, the router drops it and sends ICMP Code 4 |
| MTU | "frame size limit" | Maximum Transmission Unit — largest frame/packet a link will carry; IPv4 min 576, IPv6 min 1280 |
| PMTUD | "path MTU thing" | Path MTU Discovery (RFC 1191, 8201): sender probes downward using ICMP Too Big to size packets to fit the whole path |
| Reassembly timer | "the wait timer" | Bounded wait (RFC 791: ~30–60 s) for all fragments; on expiry the partial datagram is dropped |
| Aggregation | "summarization" | Advertising one short prefix that covers many longer ones, shrinking routing tables |
| Statistical multiplexing | "sharing by demand" | Allocating bandwidth by who needs it now rather than by fixed reservation, at the cost of congestion risk |

## Further Reading

- **RFC 791** — Internet Protocol; defines the IPv4 header, identification/flags/offset, and fragmentation/reassembly.
- **RFC 792** — Internet Control Message Protocol; the Fragmentation Needed (Type 3, Code 4) message that drives PMTUD.
- **RFC 815** — IP Datagram Reassembly Algorithms; the hole-descriptor-list algorithm that handles overlaps correctly.
- **RFC 1191** — Path MTU Discovery, the IPv4 sender-side mechanism that avoids in-network fragmentation.
- **RFC 4632** — Classless Inter-Domain Routing (CIDR); the architecture for hierarchical, variable-length prefixes.
- **RFC 5342** — IEEE 802 Addressing; the 48-bit MAC (EUI-48) structure and OUI assignment.
- **RFC 8200** — IPv6; the ban on router-side fragmentation and the 1280-byte minimum MTU.
- **RFC 8201** — Path MTU Discovery for IPv6.
- **RFC 768** / **RFC 9293** — UDP and TCP, defining the 16-bit port-number demultiplexing key.
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Chapter 1, Section 1.3.2 (Design Issues for the Layers) and Chapter 5 (the network layer).
