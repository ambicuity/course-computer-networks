# Comparison of Virtual-Circuit and Datagram Networks

> The network layer can deliver packets in one of two fundamentally different ways. A **datagram** network (IPv4/IPv6) puts a full 32-bit or 128-bit destination address in every packet, holds no per-flow state, and forwards each packet independently with a longest-prefix-match lookup into a forwarding table that has one entry per destination prefix. A **virtual-circuit** network (X.25, ATM, Frame Relay, MPLS) runs a setup phase that pins one route into per-hop tables, then carries a short label — a 12-bit ATM VPI/VCI pair, a 10-bit Frame Relay DLCI, or a 20-bit MPLS label — that each router uses as a direct index, swapping the label on the way out (label switching). The trade is setup time and per-connection table space versus per-packet address parsing and routing freedom. The decisive operational difference is failure behavior: a crashed datagram router loses only the packets queued in it (TCP retransmits), while a crashed VC router tears down **every** circuit that passed through it. This lesson builds a simulator that forwards the same traffic through both fabrics, injects a mid-stream router crash, and prints the surviving versus terminated flows.

**Type:** Build
**Languages:** Python (stdlib), routing/forwarding traces
**Prerequisites:** Phase 07 lessons 01-03 (network-layer service models, datagram forwarding, virtual-circuit setup); familiarity with IP addressing and forwarding tables
**Time:** ~75 minutes

## Learning Objectives

- Contrast datagram and virtual-circuit forwarding across the six axes Tanenbaum lists: setup, addressing, state, routing, failure effect, and QoS/congestion control.
- Compute the per-packet header overhead of a full address (32/128-bit IP) versus a short label (20-bit MPLS, 24-bit ATM VPI/VCI, 10-bit DLCI) and explain when each wins.
- Trace a packet through a VC label-swapping table and through a datagram longest-prefix-match table, and state exactly which field each router reads.
- Predict which flows survive and which are terminated when a single transit router crashes, for both fabrics.
- Decide, for a given workload (one-shot transaction vs. long-lived VPN tunnel), whether a datagram or a (possibly permanent) virtual circuit is the right fabric.

## The Problem

You run the WAN for a regional bank. Two traffic classes share the same fiber between branch offices and the core data center. The first is card-authorization traffic: tiny request/response transactions, a few hundred bytes each, one round trip and done. The second is a site-to-site tunnel carrying replication between two corporate offices, running continuously for months.

A core transit router reboots for a firmware patch and comes back ninety seconds later. The card-auth traffic barely notices — a handful of in-flight packets are lost and TCP retransmits them. But the replication tunnel, which had been provisioned as a virtual circuit through that exact router, is dead: every circuit that traversed the crashed box was torn down and must be re-established end to end. The same ninety-second outage produced two completely different blast radii.

To design the WAN correctly you have to know *why* these two fabrics fail so differently, what each packet actually carries, and how much table memory and setup latency each one costs. That is precisely the datagram-versus-virtual-circuit comparison.

## The Concept

A network-layer fabric is either **connectionless** (datagram) or **connection-oriented** (virtual circuit). The classic summary is six issues; `assets/comparison-of-virtual-circuit-and-datagram-networks.svg` lays them side by side as a packet-flow diagram.

### The six-axis comparison

| Issue | Datagram network | Virtual-circuit network |
|---|---|---|
| Circuit setup | Not needed | Required (a setup packet pins the route before data flows) |
| Addressing | Each packet carries the full source + destination address (32-bit IPv4, 128-bit IPv6) | Each packet carries a short VC number / label that has only local meaning |
| State information | Routers hold no per-connection state | Each VC needs one table entry per connection in every router on the path |
| Routing | Each packet routed independently; route can change mid-flow | Route chosen once at setup; all packets follow it (session routing) |
| Effect of router failure | None except packets queued in the crashed router | All VCs through the failed router are terminated |
| QoS / congestion control | Hard — no place to reserve resources | Easy *if* buffers/bandwidth are reserved in advance at setup |

This is the heart of the lesson. Everything else is consequences of these rows.

### Forwarding: full-address lookup vs. label index

In a datagram network a router has no circuit to key on, so for **every** arriving packet it parses the destination address and runs a **longest-prefix-match** (LPM) lookup over a forwarding table that needs, in principle, one entry per reachable destination prefix. LPM is more expensive than an exact match because several prefixes of different lengths may match and the router must pick the longest. A full forwarding-table example:

```
Prefix              Out interface   Next hop
10.2.0.0/16         eth1            10.2.0.1     (more specific — wins for 10.2.5.9)
10.0.0.0/8          eth2            10.0.0.1
0.0.0.0/0           eth0            203.0.113.1  (default route)
```

In a virtual-circuit network the router does an **exact index** instead. The packet carries a short label; the router looks it up in a per-interface table, finds the outgoing interface and the *new* label, rewrites the label, and forwards. This is **label switching**. The crucial subtlety: labels have only local significance, so a router must be able to **swap** them. Host H1 and host H3 may each pick connection identifier 1 for their own first circuit; the first router can tell them apart by incoming interface, but a downstream router cannot, so the upstream router rewrites one of them to a fresh outgoing label. A VC forwarding ("swap") table:

```
In iface  In label   ->   Out iface  Out label
eth0      1                eth2       1          (H1's circuit to H2)
eth1      1                eth2       7          (H3's circuit — relabeled to avoid the clash)
```

`code/main.py` implements both lookups so you can watch a packet take the LPM path and the label-swap path side by side.

### Header overhead: address bytes vs. label bits

Because a datagram carries a globally meaningful address, its header is larger. A short label carries only local meaning and can be tiny:

| Fabric | Per-packet circuit/address field | Size |
|---|---|---|
| IPv4 datagram | Source + destination address | 32 + 32 = 64 bits |
| IPv6 datagram | Source + destination address | 128 + 128 = 256 bits |
| MPLS label | Label field in the 4-byte shim header | 20 bits |
| ATM VPI/VCI | Virtual path + virtual channel identifier | 8 + 16 = 24 bits |
| Frame Relay DLCI | Data-link connection identifier | 10 bits |

Worked example: a 53-byte ATM cell carries a 5-byte header (≈9.4% overhead) using a 24-bit circuit identifier. A 256-byte IPv4 datagram spends 8 bytes just on source+destination addresses (≈3.1%), but a 64-byte IPv4 datagram spends those same 8 bytes as ≈12.5% overhead. For tiny packets, full addresses are expensive — one reason VC fabrics historically suited short, fixed-size cells. `code/main.py` computes these overhead fractions for any packet size you give it.

### State and table memory

A datagram router needs an entry per *destination prefix* (aggregation via CIDR keeps this bounded — a default-free Internet router carries on the order of a million IPv4 prefixes regardless of how many flows cross it). A VC router needs an entry per *active circuit*. With N simultaneous connections crossing a router, VC table size grows with N; datagram table size does not. The flip side: the datagram lookup is heavier (LPM), and the destination address must be re-parsed on every hop. Note the comparison's caveat — VC setup packets themselves are routed using destination addresses, so the "less addressing" advantage is partly illusory during setup.

### Failure behavior — the decisive difference

This is the row that drove the bank scenario.

- **Datagram router crash:** stateless, so there is nothing to lose except the packets currently queued inside it. When it reboots, the routing protocol reconverges and traffic flows again, often rerouted around the failure. Senders retransmit the few lost packets (TCP's job). Blast radius: a handful of packets.
- **VC router crash:** the per-connection table lives in volatile memory. If the router loses memory — even for one second — **every** virtual circuit that passed through it is gone and must be re-established end to end by the endpoints. A single line failure is likewise fatal to every VC riding that line, whereas a datagram fabric simply reroutes. Blast radius: every flow through the box.

Datagrams also let routers **load-balance** mid-stream: because each packet is routed independently, a long transfer can be split across changing routes. A VC is pinned, so it cannot rebalance without tearing down and rebuilding. The `--crash` mode in `code/main.py` injects a router failure and prints surviving vs. terminated flows for both fabrics. With router `C` crashed, the datagram fabric reconverges onto the backup path `A→B→E` and heals every flow that *has* a backup (only the single-homed branch-D flow stays lost); the VC fabric terminates **all** circuits through `C` regardless of backups, because the route was pinned at setup.

### Choosing a fabric by workload

- **One-shot transactions** (credit-card auth, DNS query): setup/teardown overhead can dwarf the actual data exchange. Datagrams win — no setup tax.
- **Long-lived, QoS-sensitive flows** (a months-long VPN between two offices, a guaranteed-bandwidth video trunk): a **permanent virtual circuit** set up once and held for months amortizes setup to zero and lets the operator reserve buffers/bandwidth in advance. This is "session routing" — one routing decision per session rather than per packet.
- **The modern hybrid:** MPLS wraps IP packets in a 20-bit-label shim and runs VC-style label switching *inside* ISP cores for traffic engineering and QoS, while the edges stay datagram IP. You get fast label-index forwarding and reservable paths in the core without forcing connection state onto every host.

## Build It

`code/main.py` is a stdlib-only simulator with three pieces:

1. **A datagram forwarder** — builds a forwarding table of CIDR prefixes and does real longest-prefix-match (integer/mask arithmetic, no `ipaddress` shortcuts for the match itself) to forward packets hop by hop.
2. **A virtual-circuit fabric** — runs a setup phase that walks a path, allocates a per-hop label, installs swap-table entries (relabeling on clashes), then forwards data packets by exact label index.
3. **A comparison harness** — runs the same set of flows through both fabrics, computes header overhead for a chosen packet size, then crashes one transit router and reports surviving vs. terminated flows.

Steps:

1. Read the six-axis table above and predict, before running, which flows die when router `C` crashes in each fabric.
2. Run `python3 code/main.py` and read the forwarding traces for both fabrics.
3. Re-run with `python3 code/main.py --crash C` and confirm your prediction.
4. Change the packet size argument and watch the overhead percentages move.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the fabric from a capture | Presence of a label/VPI/VCI/DLCI vs. full IP addresses in every packet | You can say "VC: short local label, swapped per hop" or "datagram: full global address, LPM per hop" |
| Explain a forwarding decision | Forwarding-table dump + the matched entry | Datagram: the *longest* matching prefix; VC: the exact in-label → out-label swap |
| Predict failure blast radius | List of flows crossing the failing node | Datagram ≈ only queued packets lost; VC = every circuit through the node terminated |
| Size router memory | Count of prefixes vs. count of active circuits | Datagram bounded by prefix table; VC grows with simultaneous connections |
| Pick a fabric for a workload | Flow lifetime + QoS need | One-shot → datagram; long-lived + reservations → permanent VC / MPLS |

## Ship It

The runnable artifact is `code/main.py`. Save its output as your reference trace under `outputs/` — a side-by-side forwarding trace plus a crash report showing the asymmetric blast radius. Pair it with `assets/comparison-of-virtual-circuit-and-datagram-networks.svg` as a one-page decision aid: the six-axis table, the two forwarding paths (LPM vs. label-swap), and the crash asymmetry. Together they form a reusable "which fabric, and what breaks when a router dies" runbook.

## Exercises

1. **Label clash.** Hosts H1 and H3 each open their first circuit and both choose VC number 1. Trace both through a shared router and show exactly where a relabel must happen and why an exact-index lookup fails without it.
2. **Overhead crossover.** At what packet size does a 24-bit ATM VPI/VCI identifier cost a *smaller* fraction of the packet than IPv4's 64 address bits? Compute it, then verify with `code/main.py`.
3. **Crash asymmetry.** Run `--crash` on the transit router that carries the most flows. Report how many flows die in each fabric and write the one-sentence reason for the difference.
4. **Transaction tax.** A credit-card auth is a 200-byte request and a 200-byte reply. Estimate the setup + teardown packet overhead of a VC for this exchange and argue whether a VC makes sense here.
5. **Permanent VC.** Explain why a months-long office-to-office VPN tunnel is a good fit for a permanent virtual circuit even though VCs are vulnerable to router crashes. What does the operator gain that a pure datagram path cannot offer?
6. **MPLS hybrid.** MPLS uses a 20-bit label and label switching in the ISP core but the hosts still speak datagram IP. Which two rows of the six-axis table does this hybrid optimize, and which datagram advantage does it deliberately keep?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Datagram | "Connectionless / just IP" | Each packet carries a full global address; routers hold no per-flow state and forward each packet independently via longest-prefix match |
| Virtual circuit | "A connection through the network" | A pre-established path pinned into per-hop tables; packets carry a short, locally-meaningful label |
| Label switching | "How MPLS forwards" | Exact-index lookup of an in-label that yields an out-interface and a *new* out-label; the label is rewritten each hop |
| VC number / label | "The circuit ID" | A short identifier (20-bit MPLS, 24-bit ATM VPI/VCI, 10-bit DLCI) with only local meaning, swapped per hop |
| Longest-prefix match | "Routing table lookup" | Among all CIDR prefixes that match a destination, the router picks the most specific (longest) one |
| Session routing | "VCs pick the route once" | The routing decision is made at setup; all later packets follow the pinned route |
| Permanent virtual circuit | "A leased VC" | A VC configured manually and held for months/years, amortizing setup to zero |
| Blast radius (router crash) | "What goes down" | Datagram: only queued packets; VC: every circuit traversing the failed node |

## Further Reading

- A. Tanenbaum & D. Wetherall, *Computer Networks*, 5th ed., §5.1.4–5.1.5 (implementation of connection-oriented service; datagram vs. virtual-circuit comparison).
- RFC 791 — *Internet Protocol* (IPv4 datagram format, 32-bit addresses).
- RFC 8200 — *Internet Protocol, Version 6 (IPv6) Specification* (128-bit addresses).
- RFC 3031 — *Multiprotocol Label Switching Architecture* (label switching, label swapping).
- RFC 3032 — *MPLS Label Stack Encoding* (the 4-byte shim, 20-bit label field).
- ITU-T I.361 — *B-ISDN ATM Layer Specification* (VPI/VCI fields).
- ITU-T Q.922 / Frame Relay — DLCI addressing.
