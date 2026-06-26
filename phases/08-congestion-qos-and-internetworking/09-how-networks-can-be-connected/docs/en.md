# How Networks Can Be Connected

> Networks differ in service model (connectionless 802.11 vs connection-oriented MPLS), addressing (flat MAC vs hierarchical IP vs 128-bit IPv6), maximum packet size (802.11 frames exceed Ethernet's 1500-byte MTU), ordering guarantees, QoS, and reliability — so joining them is not a matter of splicing cables. There are two basic strategies: build devices that **translate** packets from one format into another (protocol conversion, attempted by multiprotocol routers and gateways), or add a **layer of indirection** — a common network layer (IP) on top of the differing link layers, as Cerf and Kahn (1974) proposed and for which they received the 2004 Turing Award. Repeaters and hubs move bits at the physical layer; bridges and switches forward whole frames by MAC address with only minor translation (10/100/1000 Mbps Ethernet); routers extract the packet from the frame, consult the IP address in a routing table, and re-encapsulate for the next link. When source and destination share a protocol but the middle network differs (IPv6 islands separated by an IPv4 Internet), **tunneling** wraps the inner packet inside the foreign protocol's header so it crosses as freight — the basis of VPNs and overlay networks. Protocol conversion fails on hard mismatches: a 128-bit IPv6 address cannot fit in a 32-bit IPv4 field, so IP survives as a lowest common denominator that demands little of underlying networks but offers only best-effort service.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Earlier lessons in Phase 8
**Time:** ~90 minutes

## Learning Objectives

- Distinguish the four interconnection device classes — repeater/hub, bridge/switch, router, gateway — by the OSI layer they operate at and the header fields they actually inspect.
- Trace a packet crossing 802.11, MPLS, and Ethernet: identify where the frame is stripped, where the IP address is consulted, where a virtual circuit is set up, and where fragmentation occurs.
- Explain why a common network layer (IP) won over per-packet protocol conversion, and name the specific failure that dooms translation (128-bit IPv6 addresses vs 32-bit IPv4 fields).
- Describe tunneling as encapsulation: identify the inner header, the outer header, the tunnel endpoints, and the hosts that need not understand the foreign protocol.
- Map the observable evidence of each method onto packet headers — EtherType, IP protocol field, MPLS labels, TTL decrements, fragmentation offset flags.
- Run `code/main.py` to simulate a multi-hop interconnection, observe per-device processing, and confirm that the routed path and the tunneled path produce different header signatures.

## The Problem

A company has an IPv6 datacenter in London, an IPv6 office in Paris, and only an IPv4 transit link between them. The London engineers configure a "multiprotocol router" that tries to translate IPv6 packets into IPv4 packets for the crossing — and lose half the destination address, break flow labels, and drop any packet carrying extension headers. Meanwhile a campus has an 802.11 wireless segment feeding into an MPLS core that terminates on a classic Ethernet LAN, and users complain that large wireless frames arrive truncated or never arrive at all. The engineers blame the wireless AP, the MPLS label-switched path, and the Ethernet switch in turn — but nobody has traced which device is responsible for stripping which header, where fragmentation should happen, and which interconnection strategy applies at each boundary.

The real problem is that connecting dissimilar networks is not one problem but several stacked at different layers. A repeater solves a signal-attenuation problem; a bridge solves a same-technology segmentation problem; a router solves a dissimilar-network routing problem; a tunnel solves a same-protocol-separated-by-foreign-network problem. Picking the wrong device at a boundary — or expecting protocol conversion to work where only a common layer or a tunnel can — is the root cause behind both the London/Paris address loss and the campus frame truncation.

## The Concept

Section 5.5.2 of the source chapter lays out two fundamental strategies and a family of devices. The SVG diagrams the device hierarchy against the OSI layers; `code/main.py` simulates a packet traversing 802.11, MPLS, and Ethernet while logging each boundary's processing, then demonstrates tunneling an IPv6 packet through an IPv4 path.

### Two strategies: translate, or add a common layer

The first strategy is **protocol conversion** — build a device that reads a packet in one network's format and emits a packet in another's. The second is the computer-science reflex — add a layer of indirection and run a **common network layer** (IP) over every link technology, so devices at the boundaries only re-encapsulate, never translate the network-layer header. Cerf and Kahn (1974) argued for the common layer; it became TCP/IP and won so thoroughly that IP now runs on telephone networks, sensor motes, and 802.11 alike. The common-layer approach is what makes the Internet one network rather than a patchwork of incompatible clouds.

### The device hierarchy

| Device | OSI layer | What it inspects | What it does | Example |
|---|---|---|---|---|
| Repeater / hub | Physical (1) | Bits, signal levels | Regenerates and retransmits bits; no protocol awareness | 10BASE5 thick-coax repeater joining two 500 m segments |
| Bridge / switch | Data link (2) | MAC address (frame dest) | Forwards whole frames by MAC; minor translation between same-family links (10/100/1000 Mbps Ethernet) | 802.1D learning bridge joining 802.11 to Ethernet |
| Router | Network (3) | IP address (packet dest) | Strips the frame, consults a routing table, re-encapsulates in the next link's frame | IP router joining 802.11 to MPLS |
| Gateway | Transport/Application (4-7) | Port numbers, application headers | Translates between dissimilar upper-layer protocols | Mail gateway relaying SMTP to an X.400 system |

The key operational distinction: a **switch transports the entire frame** by MAC address and never needs to understand the network-layer protocol; a **router extracts the packet** from the frame, reads the network address, and decides the next hop. That is why routers can join 802.11 to MPLS — two links with nothing in common at layer 2 — while bridges cannot, because a bridge would have to translate frame formats and the differences (max packet size, priority classes, ordering) are too hard to mask.

### The 802.11, MPLS, Ethernet journey

The source's worked example (Fig. 5-39) follows a packet from a wireless host to an Ethernet host through an MPLS core. At each boundary a different operation occurs:

| Boundary | Operation | Header evidence |
|---|---|---|
| Source, 802.11 | Transport data is given an IP header; IP packet is encapsulated in an 802.11 frame addressed to the first router | 802.11 frame, EtherType 0x86DD (IPv6) or 0x0800 (IPv4) |
| 802.11, MPLS | Router strips the 802.11 header, reads the IP destination, looks up the routing table; an MPLS virtual circuit is established and the packet is encapsulated with MPLS labels | MPLS label stack (20-bit label, 3-bit EXP, 1-bit S, 8-bit TTL) |
| MPLS, Ethernet | Router strips MPLS labels, reads IP address again; if the packet exceeds Ethernet's 1500-byte MTU it is **fragmented**; each fragment is encapsulated in an Ethernet frame addressed to the destination | IP fragment flags (MF, offset), Ethernet frame |
| Destination, Ethernet | Ethernet header stripped from each fragment; fragments reassembled by IP layer; packet delivered to transport | Reassembled IP packet |

Observe the essential routed-vs-switched difference repeated at every hop: the frame is discarded and reborn; the IP packet survives the whole journey and is what the routing decision keys on. `code/main.py` logs this sequence.

### Multiprotocol routers and why conversion fails

A **multiprotocol router** handles more than one network-layer protocol (e.g. IPv4, IPv6, IPX, AppleTalk). It has two options: translate between protocols, or punt the connection up to a higher layer (e.g. TCP). Both are unsatisfactory. Punting to TCP requires every network to implement TCP and excludes real-time applications that do not use it. Translation fails on **information loss**: IPv6 addresses are 128 bits and will not fit in a 32-bit IPv4 address field no matter how hard the router tries; IPv6 flow labels, extension headers, and traffic-class fields have no IPv4 equivalent. Conversion between connectionless and connection-oriented protocols is even worse, because the semantics of a virtual-circuit setup do not map onto a stateless datagram service. This is why IP survives as a **lowest common denominator** — it demands little of the networks it rides on, but in return offers only best-effort delivery.

### Tunneling: the manageable special case

The general interworking problem is intractable, but one special case is tractable: **the source and destination use the same protocol, and only the middle network differs.** The solution is tunneling. The canonical example from the source is an IPv6 network in Paris and an IPv6 network in London separated by the IPv4 Internet:

```
[IPv6 host] -> [Paris router] === IPv4 tunnel === [London router] -> [IPv6 host]
```

The Paris router encapsulates the IPv6 packet inside an IPv4 header addressed to the London router. The IPv4 Internet sees only an IPv4 packet and routes it normally. The London router strips the IPv4 header and delivers the original IPv6 packet. The hosts in Paris and London never deal with IPv4; only the two boundary routers understand both protocols. The source's car-through-the-Chunnel analogy is exact: the car drives under its own power in France, is loaded onto a train as freight through the tunnel, and drives again in England.

| Tunneling element | What it is | Evidence |
|---|---|---|
| Inner packet | The protocol that source and destination share (e.g. IPv6) | Inner IP header with IPv6 version (6) and destination in the IPv6 island |
| Outer header | The protocol the middle network understands (e.g. IPv4) | Outer IP header with IPv4 version (4) and destination = tunnel endpoint |
| Tunnel endpoints | The two multiprotocol routers | Routers configured with both protocol stacks; `ip protocol` field = 41 (IPv6 encapsulation, RFC 2473) |
| Overlay | The network that results from the tunnel | The IPv6 islands appear as one contiguous IPv6 network overlaid on IPv4 |

Tunneling's disadvantage: no host in the middle network can be reached from the tunneled protocol, because packets cannot escape mid-tunnel. That limitation becomes an advantage in **VPNs** — a VPN is simply a tunnel used for security, where the encapsulation also provides isolation. `code/main.py` demonstrates both the routed journey and a tunneled IPv6-over-IPv4 path.

## Build It

`code/main.py` is a stdlib-only simulator modeling three dissimilar networks and four interconnection devices. Work through it in this order:

1. **Read the device model** — `Device` dataclasses for repeater, bridge, router, and tunnel endpoint, each logging which header field it inspects and what it strips or adds.
2. **Run the routed path** — `journey_routed()` sends a packet from an 802.11 source through an MPLS core to an Ethernet destination. Watch the log: the 802.11 frame is stripped, the IP address is consulted, an MPLS label is pushed, then the label is popped and the packet is fragmented to fit Ethernet's MTU.
3. **Run the tunneled path** — `journey_tunneled()` sends an IPv6 packet from Paris to London through an IPv4 tunnel. Watch the encapsulation: the IPv6 packet becomes the payload of an IPv4 packet addressed to the London router; the London router strips the IPv4 header and delivers the IPv6 packet intact.
4. **Try the conversion failure** — `attempt_conversion()` tries to translate an IPv6 packet into IPv4 directly and reports which fields are lost (128-bit address, flow label, extension headers).
5. **Change the parameters** — increase the source packet size past Ethernet's MTU, swap the middle network protocol, and observe how the log changes.

Run with `python3 code/main.py`. No pip dependencies, no network calls.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify an interconnection device | Which OSI layer it operates at; which header field it reads | You call a learning bridge a layer-2 device (MAC-based) and an IP router a layer-3 device (address-based), and you never expect a bridge to join 802.11 to MPLS |
| Trace a cross-network packet | Per-boundary log: frame stripped, IP consulted, label pushed/popped, fragments created | The log shows the frame dying at each router and the IP packet surviving; fragments appear only where a smaller MTU is hit |
| Explain why conversion fails | Field-by-field comparison: which fields have no target equivalent | You cite the 128-bit IPv6 address vs 32-bit IPv4 field and name flow labels and extension headers as also lost |
| Identify a tunnel | Inner + outer headers; tunnel endpoints; overlay topology | You spot protocol field 41 in the outer IPv4 header and the IPv6 destination inside, and you explain why mid-tunnel hosts are unreachable |
| Diagnose a real VPN | Wireshark capture of IP-in-IP or GRE (0x6558) or IPv6-in-IPv4 (proto 41) | You identify the inner protocol, the tunnel endpoints, and confirm encapsulation is intact by checking the inner TTL vs outer TTL |

Wireshark filters for evidence: `ip.proto == 41` (IPv6-in-IPv4 tunnel), `mpls`, `eth.type == 0x86DD`, `ip.flags.mf == 1` (more-fragments).

## Ship It

Produce one reusable artifact under `outputs/`:

- A **device-selection runbook**: given two networks to join, which device do you pick and why — a one-page decision tree keyed on OSI layer and protocol compatibility.
- A **tunnel header dissection sheet** showing inner and outer headers for IPv6-over-IPv4, GRE, and IP-in-IP, with the Wireshark filters that expose each.
- A **fragmentation trace** from `code/main.py` showing where the 1500-byte MTU boundary forces a split, annotated with MF and offset values.
- A **conversion-failure case study** documenting the IPv6-to-IPv4 field losses that make translation intractable.

Start from `outputs/prompt-how-networks-can-be-connected.md`.

## Exercises

1. A repeater joins two 10BASE5 segments. A bridge joins an 802.11 access point to an Ethernet switch. A router joins 802.11 to MPLS. For each, state which OSI layer the device operates at, which header field it reads, and what it does to the rest of the frame or packet.
2. Trace a 2300-byte IP packet from an 802.11 source through an MPLS core to an Ethernet destination with a 1500-byte MTU. How many fragments emerge at the final boundary? What are the More-Fragments flag and offset values of each fragment?
3. An engineer proposes a multiprotocol router that translates IPv6 packets to IPv4 for transit across a legacy core. List every IPv6 field that has no IPv4 equivalent and explain why this makes conversion "incomplete and often doomed to failure" rather than merely inconvenient.
4. Two IPv6 islands are separated by an IPv4 Internet. Draw the packet at three points: on the source island, inside the tunnel, and on the destination island. Which two devices must understand both protocols, and which hosts need not?
5. Run `code/main.py` with the source packet size set to 4000 bytes. Report the fragmentation log, the number of Ethernet frames produced, and the offset of each fragment. Then set the size to 1400 bytes and explain why no fragmentation occurs.
6. A VPN admin claims "tunneling gives us security." Refine the claim: what security property does the tunnel's encapsulation provide, what does it not provide, and what additional mechanism (name it) turns a tunnel into a secure VPN?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Common network layer | "IP runs on everything" | A single network-layer protocol (IP) overlaid on differing link layers so boundary devices re-encapsulate rather than translate — Cerf and Kahn's 1974 indirection |
| Repeater | "a signal booster" | Physical-layer (OSI 1) regenerator that moves bits and understands no protocol; cannot join dissimilar networks |
| Bridge / switch | "a frame forwarder" | Data-link (OSI 2) device that forwards whole frames by MAC address; minor translation only (e.g. 10/100/1000 Mbps Ethernet) |
| Router | "the thing that routes" | Network-layer (OSI 3) device that strips the frame, reads the IP destination, consults a routing table, and re-encapsulates in a new frame |
| Multiprotocol router | "a router that speaks two protocols" | A router handling multiple network-layer protocols; must translate (often doomed by field-size mismatch) or punt to a higher layer (requires TCP everywhere) |
| Gateway | "a translation box" | A higher-layer (OSI 4-7) device that translates between dissimilar upper-layer protocols (e.g. SMTP to X.400) |
| Tunneling | "wrapping a packet in a packet" | Encapsulating an inner protocol's packet inside an outer protocol's header so it crosses a foreign network as freight; only the tunnel endpoints understand both protocols |
| Overlay | "a network on top of a network" | The virtual network created by tunneling (e.g. an IPv6 overlay on IPv4); mid-tunnel hosts are unreachable from the inner protocol |
| VPN | "a secure tunnel" | A tunnel used for isolation/security; the encapsulation that makes mid-tunnel escape impossible becomes the security boundary |
| Protocol conversion failure | "translation is hard" | Information loss when source fields (128-bit IPv6 address, flow labels, extension headers) have no target equivalent in the destination protocol's 32-bit IPv4 field |

## Further Reading

- **Cerf, V. & Kahn, R. (1974)**, "A Protocol for Packet Network Intercommunication," *IEEE Trans. Comm.* 22(5) — the original argument for a common network layer; 2004 Turing Award.
- **RFC 791** — Internet Protocol (IPv4): the 32-bit address format and the best-effort service model that made IP the lowest common denominator.
- **RFC 2460 / RFC 8200** — Internet Protocol, Version 6 (IPv6) spec: the 128-bit address and extension-header design that makes IPv4 translation lossy.
- **RFC 2473** — Generic Packet Tunneling in IPv6: protocol field 41, the encapsulation mechanism for IPv6-over-IPv4 tunnels.
- **RFC 2784** — Generic Routing Encapsulation (GRE): EtherType 0x6558, a widely deployed tunneling protocol used by VPNs and overlays.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.5.1-5.5.3 — the source chapter sections on how networks differ, how they are connected, and tunneling.
- Perlman, R., *Interconnections* (2nd ed.) — bridges, routers, and the layering reasoning behind when translation works and when it does not.