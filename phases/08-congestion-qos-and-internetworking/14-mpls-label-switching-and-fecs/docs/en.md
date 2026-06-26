# MPLS Label Switching and Forwarding Equivalence Classes

> MPLS (RFC 3031) is a "layer 2.5" technology that prepends a 32-bit shim — 20-bit label, 3-bit TC, 1-bit S, 8-bit TTL — to every packet, letting core routers swap a short fixed-width label instead of doing longest-prefix match. The shim sits between L2 and L3, riding over Ethernet (0x8847/0x8848) or PPP (0x0281) without disturbing the IP packet. A Forwarding Equivalence Class (FEC) bundles all packets that get the same forwarding treatment (e.g. every packet to 10.1.0.0/16) and assigns them one label; the LER at ingress pushes, interior LSRs swap, and the egress LER pops. Bindings live in the LIB; the data plane uses the LFIB. Labels are advertised by LDP (RFC 5036) over TCP, with RSVP-TE (RFC 3209) for traffic-engineered paths; PHP lets the second-to-last LSR strip the outer label so the egress LER does one lookup. Stacked labels enable BGP/MPLS L3VPNs (RFC 4364) with per-customer VRFs, TE tunnels, and modern Segment Routing.

**Type:** Learn
**Languages:** Python
**Prerequisites:** IPv4 + LPM, TCP/IP stack, dataclasses, bits and bytes
**Time:** ~80 minutes

## Learning Objectives

- Pack and unpack the 32-bit MPLS shim header, interpreting label / TC / S / TTL and explaining why each field has its width.
- Define a Forwarding Equivalence Class and justify "the same forwarding treatment, not the same destination address."
- Distinguish the LER's push/pop role from the LSR's swap role, and the LIB (control plane) from the LFIB (data plane).
- Trace a packet through a 4-router LSP and predict the label and encapsulation at every hop.
- Explain how LDP and RSVP-TE build the LIB, why PHP exists, and how a stack of labels enables L3VPN and traffic engineering.
- Implement a small MPLS data plane in stdlib Python that walks a packet through an LSP.

## The Problem

Pure IP forwarding has two problems at ISP scale. First, every core router does a longest-prefix match in the FIB on every packet, and the FIB today has roughly one million prefixes — even with a TCAM this costs money and power. Second, the IGP only computes shortest paths, so two parallel links between the same pair of cities cannot both carry the same traffic; shortest-path routing overfills the "best" link and leaves the "backup" idle.

MPLS moves the heavy decision to the edge: an LER classifies an IP packet into a FEC and pushes a short fixed-width label. From then on every interior LSR just indexes a small table. The label is local to each link, so each LSR can renumber without coordinating with anyone else. The operator can choose *which* path the labeled LSP takes — over a hot link, around a peering point, through a low-latency slice — independently of the IGP.

## The Concept

### The 32-bit shim header

The MPLS shim header is four bytes wide and sits between the L2 header and the L3 (usually IP) header. Its layout is `Label(20) | TC(3) | S(1) | TTL(8)`, big-endian, in transmission order. The shim rides over Ethernet (EtherType 0x8847 unicast, 0x8848 multicast) or PPP (0x0281).

- **Label (20 bits)** — the index used for forwarding; 1,048,576 possible values per link. Label 0 = "IPv4 Explicit NULL", 1 = "Router Alert", 2 = "IPv6 Explicit NULL", 3 = "Implicit NULL" (PHP — upstream LSR pops). Labels 4–15 are reserved; real traffic uses 16 and up.
- **TC / Traffic Class (3 bits, formerly EXP)** — QoS marking, reconciled with outer L2 802.1p at every hop.
- **S / Bottom-of-Stack (1 bit)** — 1 on the *last* label, 0 on every label above. S=0 after a pop means keep forwarding on the new top label; S=1 means the next header is IP.
- **TTL (8 bits)** — copy of IP TTL when pushed, decremented at every LSR, copied back to IP at the egress LER.

### Forwarding Equivalence Class

A FEC is the set of packets that get the same forwarding treatment inside the MPLS domain. RFC 3031 defines it operationally: "a FEC describes the set of packets that may be forwarded in the same way." That usually means "same destination prefix and same service class," but it can be narrower (a single BGP next hop, a single VRF + route target) or broader (every packet bound for a particular egress LER). The crucial property is that all members of a FEC receive *one* label on a given LSP — that is what lets the core skip the LPM.

### LIB, LFIB, and the control / data plane split

The control plane populates a table; the data plane consults a different one. The **LIB (Label Information Base)** is the control-plane view: for each FEC the router participates in, it records the FEC, the local label it allocated, and the bindings it received from neighbors. LIBs are exchanged via LDP, RSVP-TE, BGP (for VPN labels), or IS-IS / OSPF extensions (for Segment Routing). The **LFIB (Label Forwarding Information Base)** is the data-plane view, built by installing the relevant rows of the LIB as a forwarding fast-path. An LFIB entry is keyed by **incoming interface + incoming label** and gives **outgoing interface + outgoing label + outgoing encapsulation**. The split matters because the LFIB can run in TCAM / NPU / FPGA at line rate.

Three operations drive the LFIB. **Push** at the ingress LER: the LER classifies an IP packet into a FEC and prepends a shim. **Swap** at an interior LSR: the LSR indexes the LFIB by the top label, rewrites it, and forwards. **Pop** at the egress LER (or penultimate LSR with PHP): the top label is removed. If S was 1, the next header is IP. The LER is the only router that has to look at the IP header in the data path; the LSRs in the middle are pure label engines.

### LDP — Label Distribution Protocol (RFC 5036)

LDP is the workhorse for "ordinary" LSPs. It is TCP-based (port 646) and uses the same reliable transport as BGP, so label updates carry no sequence numbers. Each router picks a label for each FEC it is the egress for and tells its neighbors; the neighbor installs a swap, picks *its own* label for the same FEC, and advertises that. LDP runs on top of the IGP and uses the IGP's shortest path — LDP-only networks are still subject to the IGP's hot-link problem.

### RSVP-TE — Traffic Engineering (RFC 3209)

RSVP-TE is the signaling protocol for when the operator does *not* want the IGP's shortest path. An ingress LER builds an explicit-route object (ERO) — a list of strict or loose hops — and sends an RSVP PATH message downstream; the destination replies with RESV carrying a label allocated in the reverse direction. RSVP-TE LSPs can carry bandwidth reservations, use constraint-based routing, and survive failure with fast reroute (FRR) — pre-computed backup LSPs that activate within 50 ms of a link failure.

### Penultimate Hop Popping (PHP)

If the egress LER always had to pop the top label and then look up the next label, it would do two lookups per packet. PHP eliminates that. The egress LER advertises label 3 ("Implicit NULL") for each FEC it terminates; the penultimate LSR sees the LFIB for that FEC say "pop, then forward to the egress LER with **no** label." So the penultimate LSR pops the label locally and hands a bare IP packet to the egress LER, which does *one* IP lookup, not two.

### MPLS L3VPN (RFC 4364)

The killer application. A provider with one MPLS backbone can sell "private network" service to many customers without a separate physical network. Each customer site connects to a provider edge (PE) router — a LER with customer-facing interfaces and a backbone-facing MPLS interface. Each PE has a per-customer **VRF (VPN Routing and Forwarding) table**: a separate RIB and FIB per customer, so 10.0.0.0/8 in customer A's VPN does not collide with 10.0.0.0/8 in customer B's VPN. A PE pushes *two* labels per packet: an inner "VPN" label (egress PE picks the VRF) and an outer "transport" label (P routers reach the egress PE). S is 0 on the outer, 1 on the inner. The outer is PHP-popped by the penultimate P; the inner is popped by the egress PE.

### Segment Routing (SR-MPLS)

The modern evolution that collapses several control protocols into one. IS-IS or OSPF itself advertises label bindings — every router advertises a "node segment" label (its own loopback), and optionally "adjacency segment" labels for each of its links. An ingress router describes a path as a *stack of segment IDs*; intermediate routers do not maintain per-LSP state, they just swap the top segment label.

## Build It

`code/main.py` (~200 lines, stdlib only) builds the data plane from scratch: a 32-bit shim encoder and decoder, a `FECTable` mapping destination prefix to label, a `Router` with LIB and LFIB, a linear four-router LSP (LER1 → LSR2 → LSR3 → LER4), and a packet walker that prints the label stack at every hop. The packet is a tiny Python object — `{src, dst, payload}` plus a list of shim entries — and "wire" operations are pure list manipulation.

```bash
python3 code/main.py
```

You should see two walks: one without PHP (label 21 → 38 → 57 → pop at LER4), and one with PHP at LSR3 (label 21 → 38 → pop at LSR3 → bare IP arrives at LER4).

## Use It

| Function | What you call it for | Returns |
|----------|----------------------|---------|
| `MPLSShim.encode(label, tc, s, ttl)` | Pack a 32-bit shim header. | `bytes` of length 4, big-endian. |
| `MPLSShim.decode(buf)` | Unpack a 4-byte shim from the wire. | `(label, tc, s, ttl)` as ints. |
| `FECTable.longest_match(dst_ip)` | Find the FEC a destination IP belongs to. | `FEC(prefix, prefix_len, label)` or `None`. |
| `Router.install_lfib(in_iface, in_label, out_iface, out_label, next_hop, php=False)` | Program one LFIB row. | `None`; mutates `lfib` dict. |
| `Router.push(ip, fec, in_iface, tc=0)` | Ingress LER action — push a label. | `LabeledPacket` with one shim on top. |
| `Router.swap(pkt, in_iface)` | Interior LSR action — top label in, top label out. | `LabeledPacket` with the top label rewritten. |
| `Router.pop(pkt)` | Penultimate / egress action — pop the top label. | `LabeledPacket` (more labels) or `IPPacket` (empty). |
| `walk_packet(pkt, routers, interfaces, label)` | Simulate the end-to-end LSP. | Prints each hop and the label stack. |

## Ship It

Before calling this done, run:

```bash
python3 -m py_compile code/main.py
wc -c docs/en.md assets/mpls-label-switching-and-fecs.svg
```

You should see a clean compile and both files in size range. Re-read your `__main__` walkthrough and confirm, by hand, that label 21 was pushed at LER1, swapped to 38 at LSR2 and 57 at LSR3, popped before LER4 in the PHP walk, and that LER4 popped nothing in the no-PHP walk.

## Exercises

1. **Stack decoder.** Take a byte buffer of `N` consecutive shim headers plus an IP header and return the list of (label, TC, S, TTL) tuples and the IP header offset. Verify with `00 01 50 3F 00 26 30 3F 45 00 00 1C ...` (labels 0x000150, 0x000263, IP at offset 8).
2. **FEC classifier.** Build a `FECTable` with `10.1.0.0/16`, `10.1.5.0/24`, and `0.0.0.0/0`. For `10.1.5.42`, predict which FEC `longest_match` returns.
3. **Trace the walk.** Make the second LSR a PHP hop for *two* LSPs (different FECs, same egress LER). Print both label stacks side by side and confirm the egress LER still does one IP lookup.
4. **Two-label VPN stack.** Add `vpn_label` to `LabeledPacket` and `vrf` to `FEC`. Simulate ingress pushing `[transport=21, vpn=842]`, interior swapping the transport only, penultimate P popping the transport, egress PE popping the VPN label and selecting the VRF. Verify S bits are 0, 1 top to bottom.
5. **TTL leak.** A packet is pushed at LER1 with IP TTL 64 and label TTL 64. The path has 3 hops. Predict the IP TTL when the packet exits LER4. Add a `traceroute` function that returns `(hop, label_or_ip, remaining_ttl)` tuples.
6. **Label-space exhaustion.** Why is a 20-bit label space actually smaller than 1,048,576 in practice? (Hint: reserved labels, per-link rather than per-router space, per-interface label space on frame-mode MPLS.) Write a paragraph.

## Key Terms

| Term | What it actually means |
|------|------------------------|
| MPLS | "Multiprotocol Label Switching" — a 2.5-layer shim that turns forwarding into a label-table exact match. |
| Shim header | The 32-bit MPLS header (20b label / 3b TC / 1b S / 8b TTL), prepended to the L3 packet. |
| FEC | "Forwarding Equivalence Class" — the set of packets that get the *same* forwarding treatment. |
| LER | "Label Edge Router" — edge of an MPLS domain; classifies into FECs, pushes or pops. |
| LSR | "Label Switch Router" — interior router; swaps the top label via the LFIB. |
| LIB | "Label Information Base" — control-plane table of FEC-to-label bindings. |
| LFIB | "Label Forwarding Information Base" — data-plane (in-label, in-iface) → (out-label, out-iface). |
| LSP | "Label Switched Path" — the end-to-end path a labeled packet follows, ingress LER to egress LER. |
| LDP | "Label Distribution Protocol" (RFC 5036) — TCP-based, advertises bindings along IGP shortest paths. |
| RSVP-TE | "Resource Reservation Protocol — TE" (RFC 3209) — signals LSPs along explicit paths. |
| PHP | "Penultimate Hop Popping" — second-to-last LSR pops so the egress LER does one IP lookup. |
| VRF | "VPN Routing and Forwarding" — per-customer RIB/FIB inside a provider edge router. |
| L3VPN | "Layer 3 VPN" (RFC 4364) — BGP/MPLS IP VPN; stacks a transport label and a per-VRF VPN label. |
| SR-MPLS | Segment Routing over MPLS — paths expressed as a label stack of node/adjacency/Prefix-SIDs. |

## Further Reading

- [RFC 3031 — Multiprotocol Label Switching Architecture](https://www.rfc-editor.org/rfc/rfc3031)
- [RFC 3032 — MPLS Label Stack Encoding](https://www.rfc-editor.org/rfc/rfc3032)
- [RFC 5036 — LDP Specification](https://www.rfc-editor.org/rfc/rfc5036)
- [RFC 3209 — RSVP-TE: Extensions to RSVP for LSP Tunnels](https://www.rfc-editor.org/rfc/rfc3209)
- [RFC 4364 — BGP/MPLS IP Virtual Private Networks (VPNs)](https://www.rfc-editor.org/rfc/rfc4364)
