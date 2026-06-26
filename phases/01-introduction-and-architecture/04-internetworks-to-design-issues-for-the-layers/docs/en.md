# Internetworks to Design Issues for the Layers

> An **internetwork** is what you get when distinct networks — different owners, different link technologies (Ethernet IEEE 802.3, Wi-Fi IEEE 802.11, MPLS, cellular) — are stitched together by **gateways**. The gateway that sits at the "just right" middle layer is the **router**, which forwards on the layer-3 **network-layer** address (32-bit IPv4 per RFC 791, 128-bit IPv6 per RFC 8200). Because the underlying links disagree on MTU (Ethernet 1500 bytes, 802.11 ~2304, classic PPP 1500, some tunnels 1400), the internetwork layer must **fragment and reassemble** — IPv4 carries Identification (16 bit), the DF/MF flags, and a 13-bit Fragment Offset measured in 8-byte units. The same seven concerns recur in *every* layer: reliability (error **detection** via CRC-32 / checksums and **correction** via FEC), routing (Dijkstra, distance-vector), addressing/naming, scalability, statistical multiplexing, flow control (sliding window), congestion control (AIMD), QoS, and security (confidentiality, authentication, integrity). This lesson makes those design issues concrete with a runnable IPv4 fragmentation engine and Internet-checksum verifier in `code/main.py`. The recurring failure mode: a router with a smaller next-hop MTU that must fragment, or a path that black-holes fragments when DF=1 and ICMP "Too Big" is filtered (PMTUD black hole).

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 lessons 01–03 (network types, protocol hierarchies, the OSI/TCP-IP layering model)
**Time:** ~75 minutes

## Learning Objectives

- Distinguish a *subnet*, a *network*, and an *internetwork*, and state the two rules of thumb that say you are looking at an internetwork rather than one network.
- Explain why a **router** (layer-3 gateway) is the "just right" level for joining heterogeneous networks, versus a repeater (L1), bridge/switch (L2), or application gateway (L7).
- Walk an IPv4 datagram through fragmentation: compute the Fragment Offset (in 8-byte units), set the MF flag, and reassemble using Identification + offset + length.
- Name the seven recurring layer design issues and match each to an observable artifact (a header field, a timer, a counter, or a log line).
- Compute and verify the 16-bit one's-complement **Internet checksum** by hand and in code, and predict what a single bit-flip does to it.

## The Problem

A user in London reports that small web pages load fine but large file downloads and a particular VPN "hang forever." Pings succeed. TCP connections establish (you see the SYN/SYN-ACK). Then the transfer stalls after a few kilobytes. Your monitoring shows retransmissions but no resets.

This is a classic **internetworking** symptom. Somewhere on the path two networks with different MTUs meet at a router. The large packets carry **DF=1** (Don't Fragment, set by Path MTU Discovery), so the router cannot fragment them; it should return an ICMP "Fragmentation Needed / Packet Too Big" (Type 3 Code 4) message, but a misconfigured firewall drops that ICMP. The sender never learns to shrink its segments. Small packets fit and pass; large ones silently vanish. This is a **PMTUD black hole** — and you cannot diagnose it without understanding internetworks, gateways, MTU, and fragmentation as *design issues that live at the network layer*.

## The Concept

Source: `chapters/chapter-01-introduction.md`, "Internetworks" and "Design Issues for the Layers."

### Subnet vs. network vs. internetwork

These three words get used loosely, so pin them down:

| Term | Definition | Telephone analogy |
|---|---|---|
| **Subnet** | The routers and communication lines owned and run by the network operator — the *plumbing*, not the endpoints | Switching offices + high-speed trunks owned by the phone company |
| **Network** | A subnet **plus** its hosts, interconnected by a *single* technology | Switching plant + the telephones attached to it |
| **Internetwork** | A collection of distinct networks joined together | The global PSTN spanning many carriers |

Two rules of thumb tell you that you are looking at an internetwork, not a single network:

1. **Different owners.** If separate organizations paid to build and each maintains its own part, it is an internetwork. (Your enterprise LAN + your ISP's backbone = internetwork.)
2. **Different underlying technology.** If parts differ in link type — broadcast vs. point-to-point, wired vs. wireless — it is probably an internetwork.

The worldwide **Internet** (always capitalized) is *one specific* internetwork: ISP networks gluing enterprise, home, and mobile networks together.

### Gateways: choosing the right layer to join networks

A **gateway** is any machine that connects two or more networks and translates between them, in hardware and software. Gateways are classified by the layer at which they operate. See `assets/internetworks-to-design-issues-for-the-layers.svg` for the layer ladder.

| Device | Layer | Joins on | Problem if you stop here |
|---|---|---|---|
| Repeater / hub | 1 (physical) | raw bits / signal | Only extends one physical medium; cannot bridge Ethernet to Wi-Fi semantics |
| Bridge / switch | 2 (link) | 48-bit MAC address | Single broadcast domain; cannot scale across the planet or join different L2 frame formats cleanly |
| **Router** | **3 (network)** | **IP address** | **"Just right"** — connects any networks that speak IP, scales globally |
| Transport gateway | 4 | port / connection | Ties you to TCP/UDP semantics |
| Application gateway | 7 | app messages | Works only for one application (e.g., an email or web proxy) |

Too low a gateway and you cannot connect *different kinds* of networks; too high and the connection only works for *one application*. The middle that is "just right" is the **network layer** — and **a router is a gateway that switches packets at the network layer.** You can spot an internetwork by finding a network that has routers.

### The seven recurring design issues

The same problems reappear in layer after layer. Each leaves *observable evidence*:

| Design issue | What it solves | Mechanism (example) | Observable artifact |
|---|---|---|---|
| **Reliability** | Correct operation from unreliable parts | Error **detection** (CRC-32, Internet checksum), error **correction** (Hamming, Reed–Solomon FEC) | FCS field, checksum field, retransmit counter |
| **Routing** | Find a working path despite broken links | Dijkstra (link-state), Bellman-Ford (distance-vector) | Routing table, traceroute hops |
| **Addressing / naming** | Identify sender + receiver | MAC (L2), IP (L3), DNS names (L7) | Src/Dst address fields |
| **Scalability** | Keep working as the network grows huge | Hierarchical addressing, route aggregation (CIDR) | Prefix length, table size |
| **Statistical multiplexing** | Share bandwidth by demand, not fixed slices | Packet switching, queues | Queue depth, link utilization |
| **Flow + congestion control** | Stop fast senders swamping slow receivers / the network | Sliding window (flow), AIMD (congestion) | Window size, drops, ECN marks |
| **Security** | Defend against threats | Confidentiality (encryption), authentication, integrity (MAC/HMAC) | TLS records, signatures |

A useful test of understanding: name the layer where each issue is *primarily* handled. Error detection per-link lives at L2 (Ethernet FCS); end-to-end integrity lives higher (TCP checksum, TLS). Routing is L3. Flow control appears at both L2 (per hop) and L4 (TCP end-to-end). The point of the lesson: **these are not separate facts to memorize — they are the design vocabulary that recurs everywhere.**

### Reliability: error detection vs. error correction

Both add **redundant information**, but they make different trade-offs:

- **Error detection** (cheaper redundancy): compute a check value, send it, recompute on receipt, compare. On mismatch, *retransmit*. Examples: Ethernet's 32-bit Frame Check Sequence (CRC-32, polynomial 0x04C11DB7), the 16-bit Internet checksum used by IPv4 headers, UDP, and TCP.
- **Error correction** (more redundancy): add enough structure to *reconstruct* the original from the corrupted bits without asking again. Examples: Hamming codes, Reed–Solomon (used in CDs, DVB, deep-space links where retransmission latency is unacceptable).

Choose correction when the round trip is long or the channel is one-way (satellite, broadcast). Choose detection + retransmit when the round trip is cheap (a LAN).

#### The Internet checksum, worked

The 16-bit one's-complement checksum (RFC 1071) is computed by summing all 16-bit words with end-around carry, then taking the one's complement. To *verify*, sum every word including the checksum field; a correct packet yields `0xFFFF`. `code/main.py` implements this. Worked example over two words `0x4500` and `0x003C`:

```
0x4500 + 0x003C = 0x453C  ->  checksum = ~0x453C = 0xBAC3
verify: 0x4500 + 0x003C + 0xBAC3 = 0xFFFF  (no errors)
```

Flip one bit in any covered word and the verification sum stops being `0xFFFF`. Note the weakness: because it is a plain sum, it cannot detect a swap of two words or certain compensating bit-flips — which is why links also carry a stronger CRC.

### Internetworking: MTU, fragmentation, and reassembly

Different link technologies impose different **MTUs** (Maximum Transmission Units):

| Link technology | Typical MTU (bytes) |
|---|---|
| Ethernet (IEEE 802.3) | 1500 |
| Ethernet jumbo frames | 9000 |
| IEEE 802.11 Wi-Fi | ~2304 |
| PPPoE (DSL) | 1492 |
| IPv4 minimum every host must accept | 576 |
| IPv6 minimum link MTU | 1280 |

When a router must forward a 4000-byte IPv4 datagram onto a 1500-byte link, it **fragments**. The relevant IPv4 header fields (RFC 791):

| Field | Size | Role in fragmentation |
|---|---|---|
| Total Length | 16 bit | Bytes in this (fragment) datagram |
| Identification | 16 bit | Same value copied to every fragment of one original datagram |
| Flags | 3 bit | bit 0 reserved; **DF** (Don't Fragment); **MF** (More Fragments) |
| Fragment Offset | 13 bit | Position of this fragment's payload, **counted in 8-byte units** |

Rules: every fragment except the last sets **MF=1**; the last sets MF=0. Each non-final fragment's payload length must be a multiple of 8 so the next offset is an integer. The receiver reassembles by grouping fragments with the same (Src, Dst, Protocol, Identification), ordering them by offset, and detecting completeness when it has offset 0 through the MF=0 fragment with no gaps. `code/main.py` performs exactly this fragmentation and reassembly and prints the per-fragment offset/MF table.

If **DF=1** and the datagram is too big, the router must *drop* it and emit ICMPv4 Type 3 Code 4 ("Fragmentation Needed and DF Set"), which carries the next-hop MTU so the sender can shrink. Lose that ICMP and you get the black hole from "The Problem."

### Resource allocation: multiplexing, flow control, congestion

Networks share scarce link capacity via **statistical multiplexing** — bandwidth is handed out by short-term demand rather than fixed per-host slices, which is why packet switching beats circuit switching for bursty traffic. Two control loops keep it stable:

- **Flow control** stops a *fast sender* from overrunning a *slow receiver*. Mechanism: a feedback window (TCP advertises a 16-bit Receive Window, scalable via the Window Scale option RFC 7323). This is a *two-party* problem.
- **Congestion control** stops *too many senders collectively* from overrunning the *network*. Mechanism: each sender backs off when it sees loss or ECN marks. TCP uses **AIMD** — additive increase, multiplicative decrease (halve the window on loss). This is a *many-party* problem.

Layered on top, **Quality of Service** reconciles competing demands: live video wants low latency/jitter, a bulk download wants high throughput, and both share the same link.

## Build It

1. Read `code/main.py`. It models an IPv4 datagram, fragments it for a given next-hop MTU, reassembles it, and computes/verifies the Internet checksum.
2. Run it: `python3 code/main.py`. Watch the fragment table — note that each non-final fragment payload is a multiple of 8 bytes and offsets advance in 8-byte units.
3. Change the MTU constant to 576 (the IPv4 guaranteed minimum) and re-run. Count how many fragments a 4000-byte datagram now needs.
4. Corrupt one byte before verifying the checksum and confirm verification fails.
5. Map each printed field back to the IPv4 header table above.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a path is an internetwork | `traceroute` shows L3 router hops across different ASNs | You can point to the gateways and say "these are routers at layer 3" |
| Diagnose a PMTUD black hole | Large flows stall; `ping -M do -s 1473` fails, `-s 1472` succeeds; no ICMP Type 3/4 returns | You identify the smallest passing size and the filtered ICMP |
| Validate a checksum | Recompute over the header; verification sum equals `0xFFFF` | Mismatch localizes corruption to the covered bytes |
| Read a fragment set | Wireshark groups by Identification; offsets in 8-byte units; last frame MF=0 | You can reconstruct total length and spot a missing fragment |

## Ship It

Produce one artifact under `outputs/`:

- A **PMTUD black-hole runbook**: the `ping -M do` size-bisection procedure, the ICMP Type 3 Code 4 check, and the fix (allow ICMP, or clamp TCP MSS).
- Or an **IPv4 fragmentation cheat-sheet** derived from `code/main.py` output (offset math, MF rules, reassembly grouping key).

Start from `outputs/prompt-internetworks-to-design-issues-for-the-layers.md`.

## Exercises

1. A 4000-byte IPv4 datagram (20-byte header, 3980-byte payload) must cross a link with MTU 1500. Compute the number of fragments, and the Total Length, MF flag, and Fragment Offset of each. Verify against `code/main.py`.
2. Your firewall allows TCP/UDP but drops all ICMP. Explain step by step why 1473-byte pings with DF set fail while web logins work, and name the exact ICMP message that was suppressed.
3. Given two networks — your home Wi-Fi (802.11) bridged to your ISP's fiber (different owner, different link tech) — apply both internetwork rules of thumb and state whether this is one network or an internetwork.
4. Classify each device for the job: joining two Ethernet segments into one broadcast domain; joining an Ethernet LAN to a cellular WAN; load-balancing HTTP across servers. Give the layer for each.
5. Compute the 16-bit Internet checksum over the words `0xE34F, 0x2396, 0x4400, 0x2210`, then verify by re-summing with the checksum included. Show that the verify sum is `0xFFFF`.
6. For each of the seven recurring design issues, name one header field, timer, or counter you could capture in a packet trace to prove it is operating.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Internetwork | "a big network" | A collection of *distinct* networks (different owners and/or link tech) joined by gateways; the Internet is one instance |
| Subnet | "a /24 of addresses" | In Tanenbaum's WAN sense: the routers + lines owned by the operator, *excluding* hosts (a different meaning from "IP subnet") |
| Gateway | "the default router IP" | Any machine joining networks with translation; classified by the layer it operates at (router = L3 gateway) |
| MTU | "packet size" | The largest L2 payload a link will carry; mismatches force fragmentation |
| Fragment Offset | "where the fragment goes" | Position in the original datagram counted in **8-byte units**, so payloads must be multiples of 8 |
| Internet checksum | "a hash" | A 16-bit one's-complement sum (RFC 1071); detects errors but not reorderings; verify sum is `0xFFFF` |
| Flow control | "congestion control" | Sender-vs-*receiver* pacing (window); distinct from congestion control, which is sender-vs-*network* |
| Statistical multiplexing | "sharing bandwidth" | Allocating capacity by short-term demand rather than fixed slices — why packet switching wins for bursty traffic |

## Further Reading

- RFC 791 — *Internet Protocol* (IPv4 header, fragmentation, Identification/Flags/Fragment Offset)
- RFC 8200 — *Internet Protocol, Version 6* (IPv6; routers do **not** fragment; sender-only fragmentation)
- RFC 1071 — *Computing the Internet Checksum*
- RFC 1191 / RFC 8899 — *Path MTU Discovery* / *Packetization Layer PMTUD* (the black-hole fix)
- IEEE 802.3 (Ethernet, 1500-byte MTU, CRC-32 FCS) and IEEE 802.11 (Wi-Fi)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Ch. 1 §1.2.5 (Internetworks) and §1.3.2 (Design Issues for the Layers)
