# Implementation of Connectionless Service to Implementation of Connection-Oriented Service

> The network layer offers two service models, and each maps to a distinct internal organization. A **datagram (connectionless)** network injects packets independently — every packet carries a full destination address (32 bits in IPv4 per RFC 791, 128 bits in IPv6 per RFC 8200), and every router looks that address up in a **forwarding table** keyed by destination. No setup, no per-flow state, and per-packet routing decisions that can change mid-stream (that is exactly why packets 1–3 take A→C→E→F but packet 4 takes A→B→D→F after A's table is updated). A **virtual-circuit (connection-oriented)** network instead runs a **setup phase** that pins one route into every router's table, then each data packet carries only a **short VC identifier** (a 20-bit label in MPLS, RFC 3031) that the router uses to index its table and **swap** for the outgoing label — this is label switching. The trade is sharp: datagrams survive router crashes (only queued packets are lost) but make QoS and congestion control hard; VCs reserve resources up front for easy QoS but every VC through a crashed router is torn down. This lesson builds a working simulator of both so you can watch forwarding tables, label-swap conflicts, and failure behavior with your own eyes.

**Type:** Build
**Languages:** Python (stdlib), routing traces
**Prerequisites:** Phase 07 lessons on network-layer design issues and store-and-forward packet switching
**Time:** ~90 minutes

## Learning Objectives

- Trace a packet through a **datagram network** using per-router forwarding tables, and explain why two packets to the same destination can take different paths.
- Trace connection setup and data transfer in a **virtual-circuit network**, including how a router **swaps** an inbound VC identifier for an outbound one.
- Explain the *label-swap conflict* problem (two sources both choosing VC id 1) and why routers must rewrite identifiers rather than pass them through unchanged.
- Predict, for a given router crash or link failure, which packets/connections survive in each model and justify it from the per-flow-state difference.
- Map the abstract models onto real protocols: IP/IPv4/IPv6 as the connectionless case, MPLS (20-bit label) as the connection-oriented case, and name the field sizes.

## The Problem

You are on call. An ISP customer reports that a long file transfer between two sites "works but reorders packets and sometimes stalls for 200 ms." A second customer on an MPLS L3VPN reports the opposite: "a core router rebooted and our entire tunnel dropped instantly — every flow died at once, no graceful degradation."

These are not random bugs. They are the *designed* behaviors of two different network-layer implementations. The first customer rides the public IP datagram network, where A can reroute packet 4 onto a different path the moment its routing table changes — great for resilience, but it produces reordering and variable latency. The second rides a virtual circuit, where one pinned route means a single router losing its state aborts every connection through it. To diagnose either one you have to reason in terms of *which model is in play*, *what state lives in the routers*, and *what evidence each model leaves behind* — forwarding-table entries and per-packet destination addresses for datagrams, VC-identifier tables and label swaps for virtual circuits.

## The Concept

### Two organizations, one network layer

Section 5.1 of Tanenbaum draws the dividing line: if the network layer offers **connectionless service**, packets are routed individually with no advance setup — these packets are *datagrams* and the network is a *datagram network*. If it offers **connection-oriented service**, a route is chosen once during a **setup phase**, stored in router tables, and reused for the life of the connection — a *virtual circuit (VC)* in a *virtual-circuit network*. IP is the dominant connectionless example; MPLS is the dominant connection-oriented example inside ISP cores.

| Issue | Datagram network | Virtual-circuit network |
|---|---|---|
| Circuit setup | Not needed | Required before any data |
| Addressing | Full source+destination address in every packet | Short VC number per packet |
| Router state | No per-connection state | One table entry per VC per router |
| Routing | Each packet routed independently | Route chosen at setup; all packets follow it |
| Router-failure effect | Only packets queued at the crash are lost | Every VC through the failed router is terminated |
| Quality of service | Difficult | Easy if resources reserved in advance |
| Congestion control | Difficult | Easy if resources reserved in advance |

This table (Fig. 5-4 in the source) is the spine of the whole lesson — `code/main.py` reproduces every row as observable behavior.

### Datagram forwarding: address in, line out

In a datagram network every router holds a **forwarding table**: a set of `(destination → outgoing line)` pairs. Only *directly connected* lines can appear as outputs. Consider the classic topology where router A connects only to B and C. Even a packet destined for distant F must leave A on the line to B or to C.

Walk the worked example from the source. Host H1 hands the transport layer a message four times the maximum packet size, so it is split into packets 1, 2, 3, 4. They reach A over PPP. A stores each briefly, **verifies the checksum**, then forwards per its table:

```
A's table (initially)      A's table (later)
Dest  Line                 Dest  Line
 B  -> B                     B  -> B
 C  -> C                     C  -> B   <- changed
 D  -> B                     D  -> B
 E  -> C                     E  -> B   <- changed
 F  -> C                     F  -> B   <- changed
```

Packets 1–3 arrive while the table still says `F → C`, so they go A→C→E→F. Between packet 3 and packet 4, A learns of congestion on the A–C path and the **routing algorithm** rewrites the table so `F → B`. Packet 4 therefore takes A→B→D→F. Same destination, different path, no coordination — that is the defining property of connectionless service. The 32-bit IPv4 (or 128-bit IPv6) destination address is the *only* thing each packet carries to make this work. See the left panel of the SVG (`assets/implementation-of-connectionless-service-to-implementation-of-connecti.svg`) for the per-packet path split.

### Virtual-circuit forwarding: identifier in, identifier out

A virtual-circuit network avoids choosing a route per packet. At **setup**, a route from source to destination is pinned into every router along the path, and each data packet then carries a short **connection identifier**. The router uses that identifier to index its table, finds the outgoing line *and* the outgoing identifier, **swaps** the identifier, and forwards.

The router table here is richer than a datagram table — it is keyed by `(incoming line, incoming VC id)` and yields `(outgoing line, outgoing VC id)`:

```
A's VC table
In(line, id)     Out(line, id)
(H1, 1)       -> (C, 1)
(H3, 1)       -> (C, 2)    <- remapped to avoid conflict
```

### The label-swap conflict, and why swapping is mandatory

Suppose H1 establishes connection 1 to H2: A→C→E→F, identifier 1 at every hop. Now H3 also wants H2 and — initiating its own first connection — *also* chooses identifier 1. At router A the two are distinguishable because they arrive on different incoming lines (`(H1,1)` vs `(H3,1)`). But both would leave A toward C, and **C cannot tell them apart** if both kept id 1 on the A→C line. So A **rewrites** H3's outgoing identifier to 2. This is why routers must be able to replace identifiers in outgoing packets — without swap capability, the second connection is unbuildable. In MPLS this exact mechanism is called **label switching**: an IP packet is wrapped in an MPLS header carrying a **20-bit label**, and each Label Switching Router performs a label *swap*. The right panel of the SVG shows the conflict and the remap.

### Setup time vs lookup time — the core trade

Why have two models at all? The fundamental trade is **setup cost vs per-packet cost**. Virtual circuits pay a one-time setup (a round trip and reserved router state) but then forwarding is trivial: the VC number is a direct *index* into a table — O(1), tiny. Datagrams pay nothing up front but every packet needs a longer longest-prefix-match-style lookup of a global address, and that address (4 or 16 bytes) is pure overhead on every packet.

For short transactions — a store verifying a credit card — the VC setup cost easily *dwarfs* the data, so datagrams win. For long-running flows — a corporate VPN between two offices — a **permanent virtual circuit** set up once and lasting months amortizes setup to near zero, and the reserved resources give predictable QoS.

### Failure behavior: the decisive operational difference

Because VCs hold per-connection state in routers, a router that **crashes and loses memory** forces *every* VC through it to abort, even if it reboots a second later — the state is gone. A datagram router crashing loses only the packets queued in it at that instant; the senders retransmit and traffic reroutes around the gap. Likewise a failed *link* is fatal to every VC using it but is trivially survivable for datagrams, which simply pick another route mid-stream. This is the "entire tunnel dropped at once" symptom from The Problem — it is connection-oriented behavior working as designed, not a bug.

### Routing vs forwarding

Keep two router processes distinct. **Forwarding** is the per-packet act of looking up the outgoing line (fast path, runs on every packet). **Routing** is the slower control process that *fills in and updates* the tables via a routing algorithm. In a datagram network the forwarding decision is remade for every packet (the best route may have changed); in a VC network the routing decision is made *once* at setup and thereafter packets just follow the pinned route — sometimes called **session routing** because the route holds for the whole session.

## Build It

`code/main.py` is a dual-mode network-layer simulator built on the source's exact topology (routers A–F, hosts H1/H2/H3).

1. Run `python3 main.py` with no arguments to execute the full demonstration.
2. **Datagram mode** builds per-router `(dest → line)` forwarding tables and forwards four packets. After packet 3 it mutates A's table (simulating the congestion-driven update) so packet 4 reroutes — watch the path diverge in the printed trace.
3. **Virtual-circuit mode** runs `setup()` for H1→H2 (id 1) then H3→H2, detecting the id-1 collision on the A–C link and performing a label **swap** to id 2. It then forwards data packets along the pinned route.
4. **Failure mode** crashes router C and reports, for each model, exactly which packets/connections survive — reproducing the Fig. 5-4 "effect of router failures" row.
5. Compare the printed forwarding traces against the SVG panels; the addresses, VC ids, and swaps should line up entry for entry.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a path is datagram-routed | Two packets, same dst IP, different egress interfaces in router counters | You can point to a routing-table change between the two packets, not a load-balancer hash |
| Read a VC/MPLS forwarding entry | `(in-line, in-label) → (out-line, out-label)` table dump | The inbound and outbound labels differ — you can explain the swap |
| Diagnose a "whole tunnel dropped" outage | Control-plane logs showing a core LSR restart | You attribute it to lost per-VC state, and note datagram traffic on the same gear survived |
| Justify model choice for a workload | Flow duration + packet size + QoS need | Short transactions → datagram; long QoS-sensitive flows → VC/PVC, with the setup-vs-lookup trade stated |

## Ship It

Produce one artifact under `outputs/`:

- A **runbook** that, given an outage symptom, classifies it as datagram vs virtual-circuit behavior and lists the table/state evidence to collect.
- Or a **forwarding-table diff tool** that highlights label swaps and per-packet path changes from two router dumps.

Start from `outputs/prompt-implementation-of-connectionless-service-to-implementation-of-connecti.md`.

## Exercises

1. In the datagram trace, A's table changes `F → C` to `F → B` between packets 3 and 4. Modify `code/main.py` so the change happens between packets 1 and 2 instead. Which packets now take A→B→D→F, and does any packet arrive out of order at F?
2. H3 opens a second, *third*, and *fourth* connection to H2, each naively choosing id 1. Extend the VC table logic so A allocates the next free outbound id each time. What is the smallest table that still avoids a collision on the A–C link?
3. Crash router **E** (not C) in failure mode. Enumerate which datagram packets are lost and which virtual circuits are torn down. Explain why the counts differ.
4. A credit-card-verification transaction is a single 200-byte request and a 40-byte reply. Compute the byte overhead of a full 16-byte IPv6 destination address (datagram) versus a 20-bit MPLS label (VC) across both packets, then argue which model the source says wins here and why.
5. Convert connection H1→H2 into a **permanent virtual circuit** by skipping the setup round trip in the simulator. What state must already exist in every router for this to be valid, and what breaks if router C reboots?
6. The source says forwarding and routing are separate processes. Instrument `code/main.py` to count how many times the *routing* update runs versus how many *forwarding* lookups occur, for a 1000-packet datagram flow and a 1000-packet VC flow. Interpret the ratio.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Datagram | "a UDP packet" | A network-layer packet routed independently with a full destination address and no setup; IP is the canonical case |
| Virtual circuit (VC) | "a connection" | A pre-established, route-pinned path stored in every router's table; data packets carry only a short identifier |
| Connection identifier / label | "a port number" | A short, *link-local* tag (20 bits in MPLS) that a router swaps at each hop; it has meaning only on one link, not end to end |
| Label switching | "MPLS magic" | Forwarding by indexing on an inbound label and rewriting it to an outbound label — the VC mechanism in MPLS |
| Forwarding table | "the routing table" | The per-router structure the *forwarding* fast path consults per packet; keyed by destination (datagram) or by (in-line, in-id) (VC) |
| Forwarding vs routing | used interchangeably | Forwarding = per-packet line lookup; routing = the control process that builds/updates the tables |
| Session routing | "sticky routing" | A VC route held for an entire session; routing decision made once at setup, not per packet |
| Permanent virtual circuit (PVC) | "a static tunnel" | A VC configured manually that lasts months/years, amortizing setup cost to ~zero |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, §5.1.3–5.1.5 (the source for this lesson).
- **RFC 791** — Internet Protocol (IPv4): 32-bit addresses, the datagram model in detail.
- **RFC 8200** — Internet Protocol, Version 6 (IPv6): 128-bit addresses.
- **RFC 3031** — Multiprotocol Label Switching Architecture: the 20-bit label and label-swap forwarding.
- **RFC 3032** — MPLS Label Stack Encoding: exact header layout (20-bit label, 3-bit TC, S bit, 8-bit TTL).
- Wireshark display-filter reference for `mpls.label` and `ip.dst` to capture the evidence each model leaves.
