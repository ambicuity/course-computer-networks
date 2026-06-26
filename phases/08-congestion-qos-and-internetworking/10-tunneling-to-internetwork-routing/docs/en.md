# Tunneling to Internetwork Routing

> **Tunneling** solves the special case where source and destination run the same network protocol but a *different* protocol sits in between — two IPv6 islands joined across an IPv4 Internet (Tanenbaum Fig. 5-40). A multiprotocol router wraps the inner packet in an outer header addressed to a peer router; intermediate nodes see only the outer header. The technique generalizes to **IP-in-IP** (RFC 2003, proto 4, +20 B), **GRE** (RFC 2784, proto 47, +24 B), **6to4** (RFC 3056, proto 41, embeds IPv4 in prefix `2002::/16`), and **L2TP** (RFC 3931, PPP over UDP). Every tunnel shrinks the effective **MTU** by its header overhead, risking fragmentation or PMTU black holes. **Internetwork routing** (5.5.4) is two-level: an **interior gateway protocol** (OSPF, IS-IS) runs inside each network, while **BGP** carries prefix announcements with AS paths and policy across networks. Weights are not comparable across operators, so interdomain routing is policy-driven, not purely shortest-path. This lesson builds a tunnel encapsulation/decapsulation simulator tracking header stacking and MTU shrinkage, then models the two-level routing decision.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 earlier lessons (congestion, QoS, network differences); Phase 7 routing fundamentals
**Time:** ~90 minutes

## Learning Objectives

- Explain the Chunnel analogy (Fig. 5-41): a packet is freight inside a carrier header crossing a foreign network, then resumes under its own power at the far end.
- Lay out the header stack for IP-in-IP (RFC 2003), GRE (RFC 2784), and 6to4 (RFC 3056), and compute the per-tunnel MTU overhead.
- Distinguish tunneling from translation: no field conversion, only wrap/unwrap — the inner packet arrives byte-identical.
- Describe the two-level routing model: IGP inside an AS, BGP across ASes, with weights incomparable across operators and policy overriding metric.
- Identify the "wrong-layer symptom" failure mode: a dead tunnel endpoint produces an IPv6 timeout, not an IPv4 error.
- Produce a reusable MTU-and-routing worksheet from `code/main.py` output.

## The Problem

A bank runs IPv6 natively in Paris and London. The WAN link between offices is leased from a transit provider that only carries IPv4. The Paris team reports that small transfers work but anything above ~1400 bytes stalls — `ping6` default succeeds, `ping6 -s 1452` silently disappears. London sees nothing arrive.

The cause is tunnel MTU shrinkage. The Paris multiprotocol router wraps each IPv6 packet in a 20-byte IPv4 header (IP-in-IP, proto 41). The path MTU on the IPv4 side is 1500, so the effective inner MTU is 1500 − 20 = 1480. IPv6 routers do not fragment — they drop oversize packets and send ICMPv6 "Packet Too Big." If those ICMP messages are filtered by the transit provider (a PMTU black hole), the Paris host never learns to shrink its sends, and large frames vanish. The symptom looks like an IPv6 routing failure; the cause is an IPv4 MTU and an ICMP filter — two layers up. This is why tunnel problems are the hardest to diagnose: the evidence is on the wrong layer.

## The Concept

Tunneling and internetwork routing make heterogeneous networks interwork. The SVG diagrams the encapsulation lifecycle; `code/main.py` simulates it with real header sizes and a two-level routing lookup.

### The tunneling mechanism: wrap, carry, unwrap

Tunneling is encapsulation: the entry router places the entire inner packet (header + payload) as the payload of an outer packet addressed to the exit router. No field conversion occurs — the inner packet is not inspected or modified by intermediate nodes. The analogy (Fig. 5-41): a car drives onto a train in Paris, rides through the Chunnel as freight, then drives off in London.

```
 Paris host        Paris MR          IPv4 Internet       London MR        London host
   |                 |                   |                 |                 |
   | IPv6 dst=2::9   |                   |                 |                 |
   |---------------->| encapsulate      |                 |                 |
   |                 | add IPv4 proto=41|                 |                 |
   |                 | dst=192.0.2.2    |                 |                 |
   |                 |----------------->| (tunnel)        |                 |
   |                 |                   |---------------->| decapsulate     |
   |                 |                   |                 | strip IPv4 hdr  |
   |                 |                   |                 |--------------->|
   |                 |                   |                 |  IPv6 dst=2::9  |
```

Only the two multiprotocol routers must understand both protocols. The IPv4 Internet sees proto 41 and treats the payload as opaque. The trip across the tunnel is, from the inner packet's view, a single hop.

### Tunnel types and their header costs

| Tunnel | RFC | Outer proto | Header overhead | Typical use |
|---|---|---|---|---|
| IP-in-IP | 2003 | IPv4 proto 4 | 20 bytes | IPv6-over-IPv4, mobile IP |
| GRE | 2784 | IPv4 proto 47 | 24+ bytes (4 GRE + 20 IP) | multicast, VPNs, non-IP protocols |
| 6to4 | 3056 | IPv4 proto 41 | 20 bytes | automatic IPv6 over IPv4, `2002::/16` |
| L2TP | 3931 | UDP 1701 | 28+ bytes (8 UDP + 20 IP + L2TP) | PPP over IP, remote access VPNs |
| IPsec ESP | 4303 | IPv4 proto 50 | 30-50+ bytes | encrypted tunnels, site-to-site VPNs |

GRE adds a delivery header so it can carry *any* network-layer protocol and a key for multiplexing. 6to4 encodes the IPv4 address into the IPv6 prefix (`2002:0xC0:0x00:0x02::` for `192.0.2.2`), so the exit router is discoverable from the address. IPsec ESP encrypts the inner packet, turning the tunnel into a VPN.

### MTU and fragmentation in tunnels

Every tunnel header byte is stolen from the payload budget. If the physical path MTU is `M` and the tunnel adds `H` bytes, the effective inner MTU is `M − H`.

| Path MTU | IP-in-IP (−20) | GRE (−24) | 6to4 (−20) |
|---|---|---|---|
| 1500 | 1480 | 1476 | 1480 |
| 1492 (PPPoE) | 1472 | 1468 | 1472 |
| 1280 (IPv6 min) | 1260 | 1256 | 1260 |

IPv4 routers may fragment the outer packet (if DF is clear), reassembling at the exit — expensive and fragile. IPv6 routers *never* fragment; they drop oversize packets and signal via ICMPv6 Packet Too Big. If that ICMP is filtered, the sender never learns and large frames vanish — a **PMTU black hole**. The fix is PMTUD, but inside a tunnel the inner host must discover a *virtual* MTU it cannot directly probe.

### Overlay networks and VPNs

A tunnel creates an **overlay**: a virtual network riding on a physical one. The IPv6 islands in Paris and London become a single connected IPv6 network — the IPv4 Internet in between is invisible. With encryption added (IPsec ESP), the overlay becomes a **VPN**: it provides confidentiality and makes the remote site appear local. The limitation is that packets cannot escape mid-tunnel — no intermediate IPv4 host is reachable — which is exactly the property that makes a VPN private.

### Internetwork routing: two levels

Routing across an internet adds three complications over single-network routing: networks may use *different* interior algorithms (one OSPF, another IS-IS), operators choose *incomparable* metrics (delay vs. cost), and operators may *hide* their internal topology. The resolution is a **two-level** model:

| Level | Protocol family | Scope | Example |
|---|---|---|---|
| Intradomain (IGP) | Interior Gateway | within one AS | OSPF, IS-IS, RIP |
| Interdomain (EGP) | Exterior Gateway | across ASes | BGP-4 (RFC 4271) |

Each network is an **Autonomous System** (AS) — an independently operated routing domain. Inside, the operator picks any IGP and weights. Across ASes, everyone speaks BGP, which carries prefix→AS-path announcements plus policy tags (customer, peer, transit). Shortest path is not well-defined interdomain because weights are not comparable, so BGP selects routes by a policy sequence (LOCAL_PREF → AS_PATH length → MED → IGP metric), not by a single global metric.

### Routing protocol interaction across tunnels

A tunnel appears in routing as a single logical link. From the IGP's perspective, the Paris-to-London tunnel is one hop — the IPv4 Internet in between is collapsed into an arc. BGP can use tunnels too: a tunnel to a remote AS is an arc with a next-hop and policy. The danger is that a tunnel can hide path characteristics (latency, loss, MTU) that the IGP would normally measure, producing topologically correct but operationally poor decisions.

## Build It

`code/main.py` is a stdlib-only simulator with three parts:

1. **Encapsulation/decapsulation engine** — models IP-in-IP (proto 4), GRE (proto 47, +4-byte delivery header), and 6to4 (proto 41, address-embedded exit). Each encapsulate adds the correct outer header; decapsulate strips it and recovers the inner packet byte-for-byte. Prints the header stack at each stage.
2. **MTU tracker** — given a path MTU, computes the effective inner MTU per tunnel type, flags oversize packets, and simulates the IPv6 drop vs. IPv4 fragment path so the PMTU black hole is visible.
3. **Two-level routing lookup** — models three ASes with IGP and BGP tables, performs longest-prefix match, walks the AS path, and prints the policy decision at each hop.

Run `python3 code/main.py`, then change the inner packet size and tunnel type to watch the MTU budget and routing path shift.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Trace a tunneled packet | Outer proto + inner dst | You say which fields intermediate routers see (outer) and which they never see (inner) |
| Compute effective MTU | Path MTU − tunnel overhead | 1500 − 20 (IP-in-IP) = 1480; you predict the drop before it happens |
| Diagnose a PMTU black hole | ping6 default OK, large fails, no ICMP | You identify filtered ICMPv6 PTB, not an IPv6 routing bug |
| Distinguish tunnel types | Protocol number + header size | proto 4 = IP-in-IP (20 B), proto 47 = GRE (24+ B), proto 41 = 6to4 (20 B) |
| Walk a two-level route | IGP prefix → BGP AS path → IGP at dest AS | You separate "which AS" (BGP) from "which router inside" (IGP) |
| Spot the wrong-layer symptom | IPv6 timeout when tunnel endpoint is down | You trace at both layers, not just the one showing the symptom |

Wireshark filters: `ip.proto == 41` (6to4), `gre.proto == 0x86DD` (GRE+IPv6), `icmpv6.type == 2` (Packet Too Big).

## Ship It

Produce one reusable artifact under `outputs/`:

- A **tunnel MTU worksheet**: per tunnel type, the overhead, effective MTU at common path MTUs, and fragmentation/PTB behavior.
- A **two-level routing runbook**: IGP-vs-BGP responsibilities, the BGP decision sequence, and how to read an AS path.
- The **encapsulation simulator** (`code/main.py`) wired to your own topology.

Start from `outputs/prompt-tunneling-to-internetwork-routing.md`.

## Exercises

1. An IPv6 host sends a 1452-byte payload through an IP-in-IP tunnel over a 1500-byte path MTU. Will it fit? Compute the effective MTU and state whether the packet is delivered, fragmented, or dropped.
2. Replace IP-in-IP with GRE. Recompute the effective MTU. By how many bytes did the budget shrink?
3. A 6to4 exit router has IPv4 address `203.0.113.42`. What IPv6 prefix does it advertise? Show the hex derivation.
4. AS 100 learns prefix `10.2.0.0/16` via two BGP paths: `[100, 200, 300]` (metric 50) and `[100, 400, 300]` (metric 80). If LOCAL_PREF is equal and AS_PATH length is the tiebreaker, which wins? If LOCAL_PREF is higher for the second, does it flip?
5. A user reports `ping6` to a remote IPv6 site works but `scp` stalls at 99%. Propose three hypotheses and the single trace that confirms each.
6. Run `code/main.py` with `inner_payload_size=1472` through a GRE tunnel on a 1500-byte path. What does the MTU tracker report, and what would a real IPv6 host do?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Tunneling | "wrapping packets" | Encapsulating an inner packet as the payload of an outer header addressed to a peer router; no field translation, only wrap/unwrap (RFC 2003, 2784, 3056) |
| IP-in-IP | "proto 4" | Simplest tunnel: 20-byte IPv4 outer header, protocol 4 (RFC 2003) |
| GRE | "generic route encapsulation" | Adds a 4+ byte delivery header over IP-in-IP so any protocol can be carried; proto 47 (RFC 2784) |
| 6to4 | "automatic IPv6 tunnel" | Embeds the IPv4 exit address in prefix `2002::/16`; proto 41 (RFC 3056) |
| Effective MTU | "tunnel MTU" | Path MTU minus tunnel header overhead; inner packet must fit or fragment/drop |
| PMTU black hole | "big packets vanish" | ICMPv6 Packet Too Big is filtered; sender never learns the real MTU |
| Overlay network | "virtual network on top" | A network formed by tunnels that appears connected to its hosts while riding a different underlay |
| Autonomous System | "an ISP network" | An independently operated routing domain; IGP inside, BGP across (RFC 4271) |
| IGP / EGP | "interior / exterior" | IGP (OSPF, IS-IS) routes within an AS; EGP (BGP) routes across ASes with policy |
| Two-level routing | "hierarchical routing" | IGP inside each AS, BGP across; weights incomparable, so interdomain is policy-driven |
| VPN | "secure tunnel" | An overlay using encrypted tunnels (IPsec ESP) for confidentiality |

## Further Reading

- **RFC 2003** — IP Encapsulation within IP (IP-in-IP, proto 4).
- **RFC 2784** — Generic Routing Encapsulation (GRE, proto 47).
- **RFC 3056** — Connection of IPv6 Domains via IPv4 Clouds (6to4).
- **RFC 3931** — Layer 2 Tunneling Protocol Version 3 (L2TP).
- **RFC 4271** — BGP-4, the interdomain routing protocol.
- **RFC 4303** — IP ESP, the encrypted tunnel for VPNs.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.5.3 "Tunneling," §5.5.4 "Internetwork Routing" (Figs. 5-40, 5-41).