# Services Provided to the Transport Layer

> The network layer hands the transport layer one of two service models at the network/transport interface, and the choice shapes every header above it. **Connectionless (datagram)** service offers little more than `SEND PACKET` / `RECEIVE PACKET`: every packet carries a full destination address (32 bits in IPv4, 128 bits in IPv6), is routed independently, and routers hold *no* per-flow state — IP is the canonical example. **Connection-oriented (virtual-circuit)** service sets up a route once at connection time, stores it in router tables, and tags every packet with a short circuit identifier — MPLS uses a 20-bit label, ATM used a 24-bit VPI/VCI pair. The split traces to a real engineering argument: the Internet camp invokes the end-to-end argument (Saltzer, Reed & Clark, 1984) to push error and flow control to the hosts; the telephone camp wants in-network quality of service. The choice has hard consequences — a router crash drops *only* in-flight datagrams in a datagram net, but tears down *every* VC that crossed it in a virtual-circuit net. This lesson builds a side-by-side simulator that forwards the same four-packet message through both models and proves these differences with routing-table dumps.

**Type:** Build
**Languages:** Python, routing traces
**Prerequisites:** Phase 7 lesson 01 (Store-and-Forward Packet Switching); basic IP addressing
**Time:** ~75 minutes

## Learning Objectives

- State the three design goals the network/transport interface must satisfy (router-technology independence, topology shielding, uniform addressing) and explain why each matters.
- Forward a multi-packet message through a datagram network and show why packet 4 can legally take a different path than packets 1–3.
- Set up, use, and tear down a virtual circuit, including the **label-rewriting** step routers perform when two VCs collide on a shared link.
- Read a six-row comparison table (setup, addressing, state, routing, failure effect, QoS) and predict behavior for a given failure scenario.
- Map both abstract models onto real protocols: IP/UDP for connectionless, MPLS and ATM for connection-oriented.

## The Problem

You are on call. A backbone router (call it `C`) reboots for a firmware patch at 02:14. Two things happen at once and they look contradictory:

- A team running plain UDP telemetry reports a *tiny* blip — a handful of datagrams lost during the ~900 ms the router was down, then full recovery with no human action.
- A team whose traffic rides an MPLS label-switched path through `C` reports that **every** session through that path died and stayed dead until the path was re-signaled ~6 seconds later.

Same router, same outage, opposite blast radius. If you cannot explain *why*, you will misdiagnose the second incident as an application bug. The answer is not in the application — it is in which **service model** the network layer handed each flow. This lesson makes that distinction concrete enough to predict the blast radius before the pager goes off.

## The Concept

The network layer sits directly below the transport layer and exposes a service at the **network layer / transport layer interface**. The designers had freedom, but the service had to meet three goals (Tanenbaum & Wetherall, §5.1.2):

1. **Independent of router technology** — the transport layer must not break when an operator swaps a Cisco core for a Juniper core.
2. **Shield the transport layer** from the number, type, and topology of routers — a TCP socket must not need to know there are 14 hops or that hop 9 is a satellite link.
3. **Uniform numbering plan** — addresses must look the same across LANs and WANs, so software written for one works on the other. IPv4's flat 32-bit address space is exactly this.

Given those goals, one decision dominates everything: **connectionless or connection-oriented?**

### The two camps and the end-to-end argument

The **Internet camp** says a router's only job is moving packets; the network is unreliable no matter what, so hosts should do error and flow control themselves. Doing it twice — once in the net, once in the host — usually buys nothing. This is the **end-to-end argument** (Saltzer, Reed & Clark, 1984). It leads to a connectionless service with essentially two primitives, `SEND PACKET` and `RECEIVE PACKET`, no ordering, no in-network flow control, and a **full destination address in every packet**.

The **telephone camp** says 100 years of the phone network prove that reliable, connection-oriented service is the way to get **quality of service** — essential for real-time voice and video. History went mostly the Internet's way: X.25 (1970s) and Frame Relay (1980s) were connection-oriented; ATM tried to overthrow IP in the 1980s and lost. But the Internet quietly grew connection-oriented features back in — **MPLS** and **VLANs** — once QoS mattered. The debate is not settled; it is layered.

### Connectionless service: the datagram network

With connectionless service, packets are injected individually and routed independently. They are called **datagrams**, the network a **datagram network**. There is no setup. Each datagram carries the **full source and destination address** because nothing remembers it from one packet to the next.

Here is the worked example from the source (Fig. 5-2), reproduced by `code/main.py`. Host `H1` has a message for `H2` that is four times the maximum packet size, so the network layer splits it into packets 1, 2, 3, 4. They enter at router `A`. Every router holds a table of `(destination, outgoing line)` pairs, and **only directly connected lines** can be used. `A` connects only to `B` and `C`:

```
A's table (initially)      A's table (later)
Dest | Line                Dest | Line
  A  |  –                     A  |  –
  B  |  B                     B  |  B
  C  |  C                     C  |  C
  D  |  B                     D  |  B
  E  |  C                     E  |  B   <-- changed
  F  |  C                     F  |  B   <-- changed
```

Packets 1, 2, 3 arrive, have their checksums verified, are stored briefly, then forwarded `A→C→E→F` and over the LAN to `H2`. But **packet 4 takes `A→B`** instead — between packet 3 and packet 4, `A` learned of congestion on the `A–C–E` path and rewrote its table (the "later" column). The component that rewrites tables and makes these choices is the **routing algorithm**, the subject of the rest of Phase 7. IP is the dominant real-world instance: each packet carries a 32-bit (IPv4) or 128-bit (IPv6) destination address, forwarded independently.

The SVG in `assets/services-provided-to-the-transport-layer.svg` shows both topologies side by side; the datagram side highlights packet 4's divergence in berry pink.

### Connection-oriented service: the virtual-circuit network

To avoid choosing a route per packet, connection-oriented service sets up a **virtual circuit (VC)** once. A route from source to destination is chosen at **connection setup** and stored in router tables; all traffic for that connection follows it; releasing the connection tears the VC down. Each packet carries a **connection identifier** instead of a full address.

The subtlety is **label collision**, straight from the source (Fig. 5-3). `H1` opens connection `1` to `H2`. Then `H3` also opens a connection and, knowing only its own circuits, *also* picks identifier `1`. At router `A` the two are distinguishable (different incoming lines), but downstream at `C` they would clash. So `A` **rewrites** the outgoing identifier for the second connection. This is why a VC table needs four columns — `(in-line, in-label) → (out-line, out-label)` — and why routers must be able to swap labels in flight. The general name for this is **label switching**:

```
A's VC table
In                Out
(line, label)     (line, label)
(H1,  1)    ->    (C, 1)
(H3,  1)    ->    (C, 2)    <-- relabeled to avoid clash at C
```

The real-world instance is **MPLS (MultiProtocol Label Switching)**: an IP packet is wrapped in a 4-byte MPLS shim header carrying a **20-bit label** (plus 3 experimental/TC bits, 1 bottom-of-stack bit, and an 8-bit TTL). MPLS runs inside ISP cores, usually hidden from customers, to support QoS and traffic engineering. ATM, the older instance, used a 24-bit VPI/VCI per cell.

### The six-axis comparison (Fig. 5-4)

This table is the payoff. `code/main.py` prints it and then *demonstrates* each row.

| Issue | Datagram network | Virtual-circuit network |
|---|---|---|
| Circuit setup | Not needed | Required before any data |
| Addressing | Full source + dest address in every packet | Short VC number per packet |
| State in routers | None about connections | One table entry per VC per router |
| Routing | Each packet routed independently | Route chosen at setup; all packets follow it |
| Effect of router failure | Only packets in flight during the crash are lost | **Every VC through the failed router terminates** |
| Quality of service / congestion control | Difficult (no per-flow reservation) | Easy *if* resources reserved in advance per VC |

The failure row is the on-call story from "The Problem." The QoS rows explain why MPLS exists despite IP's dominance.

### Trade-off summary

Datagrams trade per-packet header overhead (full addresses) and harder QoS for **resilience and zero setup**. Virtual circuits trade setup latency and fragile state for **predictable paths and easy reservation**. Neither is universally right — which is why the Internet runs IP datagrams end-to-end *and* MPLS circuits inside ISP cores.

## Build It

`code/main.py` is a self-contained simulator. Walk through it in this order:

1. **Build the topology** — the six-router graph `A–F` from Fig. 5-2/5-3, encoded as an adjacency map.
2. **Datagram forward** — `forward_datagram()` walks each of the four packets hop-by-hop using each router's independent next-hop table. Re-run after calling `reroute()` to reproduce packet 4 taking `A→B`.
3. **VC setup** — `setup_virtual_circuit()` reserves a path, installs `(in→out, label)` rows in every router on the path, and demonstrates the relabel when a second VC collides on identifier `1`.
4. **Inject a failure** — `fail_router("C")` then re-run both models. Watch the datagram model lose only the packet currently at `C`, while every VC crossing `C` is reported as terminated.
5. **Print Fig. 5-4** — `print_comparison_table()` dumps the six-axis table and tags each row with the observed evidence from steps 2–4.

Run it: `python3 code/main.py`. No dependencies, no network calls.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify a flow's service model | Header inspection: full dst address vs short label | UDP/IP shows 32-bit dst per packet; MPLS shows a 20-bit label that changes hop-to-hop |
| Explain a datagram reroute | Two routing-table dumps (before/after) | You can point to the single changed `(dest→line)` entry that moved packet 4 |
| Predict failure blast radius | Topology + which model the flow uses | "Router C down → N VCs terminated, but datagram flows lose only in-flight packets" |
| Diagnose a VC label clash | Per-router `(in,label)→(out,label)` table | You can show where a router relabeled to keep two circuit-1s distinct downstream |

## Ship It

Produce one artifact under `outputs/`:

- A **runbook page** titled "Blast radius by service model" that, given a failed core router, lists which flow types lose only in-flight packets vs which lose entire sessions.
- Or a **labeled diagram** of your own network marking which links are pure-IP datagram paths and which are MPLS LSPs.

Start from the simulator's printed comparison table and the SVG. The deliverable should let a teammate predict outage impact *before* the next reboot window.

## Exercises

1. In Fig. 5-2, packet 4 went `A→B` while 1–3 went `A→C`. Modify `reroute()` so the change happens *between packet 2 and packet 3* instead. Which packets now arrive out of order, and why is reordering legal in a datagram network but not on a single VC?
2. Two hosts `H1` and `H3` both open a VC and both pick label `1`. Trace the relabeling through routers `A` and `C`. At which router does the clash *first* become unavoidable, and why can `A` get away without relabeling?
3. Router `C` fails. Compute the exact set of lost datagrams (those whose current hop is `C`) versus the exact set of terminated VCs (those whose stored path includes `C`). Show both from the simulator output.
4. An MPLS shim header is 4 bytes for a 20-bit label; an IPv4 destination address is 4 bytes too. Argue when carrying a *full* address per packet is actually cheaper overall than maintaining per-VC state in every core router.
5. Your real-time video flow needs guaranteed bandwidth. Using the Fig. 5-4 QoS rows, explain why a VC makes this "easy if resources are allocated in advance" and what a pure datagram network would have to bolt on (hint: RSVP / DiffServ) to approximate it.
6. The end-to-end argument says hosts should do error control. Find one case where doing error control *inside* the network is justified anyway (hint: a high-loss wireless link) and explain the cost/benefit.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Datagram | "A UDP packet" | A self-contained packet carrying its full source+dest address, routed independently with zero router state |
| Virtual circuit (VC) | "A connection" | A pre-established, table-stored path identified by a short label; all packets follow it |
| Connectionless service | "IP" | `SEND/RECEIVE PACKET` primitives, no setup, no ordering, full address per packet |
| Connection-oriented service | "Like a phone call" | Setup → labeled data flow → teardown, with per-flow state in every router on the path |
| End-to-end argument | "Keep the network dumb" | Saltzer/Reed/Clark 1984: put functions like error/flow control at the endpoints unless the net can do it strictly better |
| Label switching | "MPLS magic" | Forwarding on a short circuit identifier that routers may *rewrite* hop-to-hop to avoid downstream clashes |
| Routing algorithm | "How packets find their way" | The component that builds/updates the `(dest→line)` tables a datagram router forwards on |
| Quality of service (QoS) | "Fast internet" | Per-flow guarantees (bandwidth, delay, jitter) — easy on VCs with reservation, hard on bare datagrams |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., §5.1.2–5.1.5 (the source for this lesson; Fig. 5-2, 5-3, 5-4).
- Saltzer, Reed & Clark, "End-to-End Arguments in System Design," *ACM TOCS* 2(4), 1984.
- **RFC 791** — Internet Protocol (IPv4): the 32-bit address, connectionless datagram model.
- **RFC 8200** — IPv6 specification: 128-bit addresses, same connectionless model.
- **RFC 3031** — Multiprotocol Label Switching Architecture; **RFC 3032** — MPLS Label Stack Encoding (the 4-byte shim, 20-bit label, 3-bit TC, S bit, 8-bit TTL).
- **RFC 768** — User Datagram Protocol, the thinnest transport over connectionless IP.
- ITU-T I.361 — B-ISDN ATM layer specification (VPI/VCI), for the historical connection-oriented contrast.
