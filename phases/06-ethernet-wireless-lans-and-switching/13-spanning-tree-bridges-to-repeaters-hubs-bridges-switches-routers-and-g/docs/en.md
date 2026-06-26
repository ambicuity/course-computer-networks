# Spanning Tree Bridges to Repeaters, Hubs, Bridges, Switches, Routers, and Gateways

> Redundant links between bridges make a LAN survive a cut cable, but they also create layer-2 loops that the data link layer cannot kill — there is no TTL/hop-limit field in an Ethernet frame, so a flooded frame circulates forever and amplifies into a broadcast storm. The fix is the **Spanning Tree Protocol (STP)**, invented by Radia Perlman and standardized as **IEEE 802.1D**. Bridges exchange **Configuration BPDUs** (Bridge Protocol Data Units) carrying a 8-byte Bridge ID, a 8-byte Root ID, and a 4-byte Root Path Cost, elect the lowest-Bridge-ID bridge as **root**, compute shortest-cost paths to it, and block every port not on the tree — reducing the physical mesh to exactly one loop-free path between any two stations. Classic 802.1D converges in 30–50 seconds through Listening (15 s) and Learning (15 s) states governed by a Forward Delay timer; **RSTP (IEEE 802.1w, 2001)** cuts this to under a second. This lesson also maps the whole device zoo — repeater (L1), hub (L1), bridge/switch (L2), router (L3), transport/application gateway (L4–L7) — onto the layer whose header each one reads to make a forwarding decision.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python
**Prerequisites:** Phase 6 lessons on Ethernet framing, MAC addresses, and backward-learning bridges
**Time:** ~75 minutes

## Learning Objectives

- Explain why a layer-2 loop is fatal (no TTL in an Ethernet frame) and how flooding turns one frame into a broadcast storm.
- Decode a Configuration BPDU: the Root ID, Bridge ID, Root Path Cost, and Port ID fields, and how the four-tuple priority vector decides who wins.
- Run the 802.1D election by hand: pick the root, compute each bridge's root port, pick the designated port per segment, and block the rest.
- Trace the Listening → Learning → Forwarding port state machine and account for the ~30 s convergence using the Forward Delay and Max Age timers.
- Place repeaters, hubs, bridges, switches, routers, and gateways at the correct layer and name the exact header field each device reads to forward.

## The Problem

It is 09:05 on a Monday and an entire office floor drops off the network at once. Pings to the gateway time out, then briefly recover, then die again. The access switches' status LEDs are flickering in unison — all ports, all at once — which is the visual signature of a **broadcast storm**. SSH to a switch is impossible because its CPU is pinned at 100% drowning in flooded frames.

The root cause: a well-meaning technician plugged a spare patch cable between two access switches "for redundancy," forming a physical loop. A single ARP broadcast entered the loop and, because an Ethernet frame has **no TTL or hop-limit field**, every bridge dutifully flooded it out all other ports forever. Two parallel links between a bridge pair turn one frame into two, then four, then eight — exponential growth until the links saturate.

This is exactly the failure Radia Perlman was asked to solve in 1984: *join LANs with redundant links, but never let a frame loop.* Her answer, the spanning tree, is why that loop did **not** take down every modern managed switch — STP detected the loop within seconds and blocked the offending port. Understanding STP is the difference between "reboot everything and pray" and "show me which port STP blocked and why."

## The Concept

### Why loops are fatal at layer 2

Consider Fig. 4-43 from the source: bridges B1 and B2 joined by two parallel links. Station A sends a frame to a destination neither bridge has learned. The backward-learning rule for an unknown destination is **flood** — send out every port except the one it arrived on.

```text
A → B1 floods → two copies (F1, F2) reach B2 over the two links
B2 cannot tell F1 and F2 are duplicates → floods both back → F3, F4 reach B1
B1 sees two new unknown-destination frames → floods again → forever
```

A router would stop this: an IP packet has a **TTL** field (RFC 791) that decrements to zero. An Ethernet frame has no such field. The MAC layer has no loop defense of its own — the *only* defense is to make sure the topology has no loops in the first place. That is the spanning tree's entire job.

### The spanning tree solution

Take the physical mesh of bridges and treat it as a graph: bridges are nodes, point-to-point links are edges. A connected graph with cycles can be reduced to a **spanning tree** — a subgraph that touches every node but contains no cycle. With exactly one path between any two stations, loops are impossible by construction. STP does this dynamically and keeps running so that if a tree link fails, a previously **blocked** backup link is unblocked and the tree heals.

See `assets/spanning-tree-bridges-to-repeaters-hubs-bridges-switches-routers-and-g.svg` for the mesh-to-tree reduction: dashed edges are the links STP blocks to break loops.

### The Configuration BPDU

Bridges build the tree by periodically multicasting **Configuration BPDUs** (every 2 s by default) to the reserved group address `01:80:C2:00:00:00`. BPDUs are **never forwarded** — they exist to build the tree, not to be carried across it. The fields that drive the algorithm:

| Field | Size | Purpose |
|---|---|---|
| Protocol ID | 2 B | 0x0000 for STP |
| Version / BPDU Type | 1 + 1 B | 0x00 / 0x00 = Configuration BPDU |
| Flags | 1 B | Topology Change (TC) and TC-Ack bits |
| **Root ID** | 8 B | 2-byte priority + 6-byte MAC of the believed root |
| **Root Path Cost** | 4 B | Accumulated cost from this bridge to the root |
| **Bridge ID** | 8 B | 2-byte priority + 6-byte MAC of the *sending* bridge |
| **Port ID** | 2 B | Priority + port number of the sending port |
| Message Age / Max Age | 2 + 2 B | Age of info; default Max Age = 20 s |
| Hello Time / Forward Delay | 2 + 2 B | Defaults: Hello = 2 s, Forward Delay = 15 s |

A bridge compares incoming BPDUs against its own using the priority vector **{Root ID, Root Path Cost, Sender Bridge ID, Sender Port ID}**, in that order. Lower is always better. `code/main.py` implements exactly this comparison.

### Electing the root and building the tree

The algorithm runs in three decisions:

1. **Elect the root.** Every bridge starts by claiming to be root (advertising its own Bridge ID as Root ID). On hearing a BPDU with a lower Root ID, it stops claiming and relays the better root. The bridge with the **numerically lowest Bridge ID** (priority first, then MAC, which is manufacturer-unique worldwide) wins. In Fig. 4-44, B1 has the lowest ID and becomes root.

2. **Choose each bridge's root port.** Every non-root bridge picks the one port giving the **lowest Root Path Cost** back to the root. Ties break on lowest sender Bridge ID, then lowest Port ID. In Fig. 4-44, B4 is two hops from B1 via either B2 or B3, so the tie breaks toward the lower-ID bridge (B2).

3. **Choose the designated port per segment, block the rest.** On each LAN segment, the bridge offering the lowest cost to the root owns the **designated port**; all other ports on that segment go to **Blocking**. The root's own ports are all designated.

A worked cost example (classic 802.1D costs are inversely tied to speed):

| Link speed | 802.1D cost | 802.1t (RSTP) cost |
|---|---|---|
| 10 Mbps | 100 | 2,000,000 |
| 100 Mbps | 19 | 200,000 |
| 1 Gbps | 4 | 20,000 |
| 10 Gbps | 2 | 2,000 |

If B4 reaches the root over a 100 Mbps link (cost 19) on one port and a 10 Mbps link (cost 100) on another, the 100 Mbps port becomes the root port and the 10 Mbps port is blocked.

### Port states and why convergence takes ~30 seconds

In 802.1D a port does not jump straight to forwarding — it walks a state machine to avoid creating a transient loop while the tree is still settling:

```text
Blocking ──(selected as root/designated)──► Listening (15 s, Forward Delay)
   ▲                                              │  receive BPDUs, no learning
   │                                              ▼
Disabled                                     Learning (15 s, Forward Delay)
                                                  │  build MAC table, still no forwarding
                                                  ▼
                                             Forwarding  (data passes)
```

Listening (15 s) + Learning (15 s) = 30 s for a port to go live. If a topology change forces a port out of Blocking, add the Max Age wait (20 s) for stale info to expire — hence the familiar 30–50 s outage after a link flaps on legacy STP. **RSTP (IEEE 802.1w, 2001)** replaces this with a proposal/agreement handshake and edge-port designation, converging in well under a second. RSTP is the default in essentially all hardware shipped this decade.

### The device zoo: which layer reads which header

The source's Fig. 4-45 maps every interconnection device to the layer whose header it inspects to forward. This is the single most useful mental model for triage:

| Device | OSI layer | Address/info it reads | Collision domain | Broadcast domain |
|---|---|---|---|---|
| Repeater | L1 Physical | none — amplifies volts/symbols | one (shared) | one |
| Hub | L1 Physical | none — joins lines electrically | one (shared) | one |
| Bridge / Switch | L2 Data link | 48-bit MAC dest (Fig. 4-14) | **one per port** | one |
| Router | L3 Network | 32-bit IPv4 / 128-bit IPv6 dest | per port | **one per port** |
| Transport gateway | L4 Transport | TCP/SCTP connection state | — | — |
| Application gateway | L7 Application | message payload (e.g. SMTP↔SMS) | — | — |

Key distinctions engineers conflate:

- **Repeater vs hub:** both L1, both one collision domain; a hub just has many ports and usually does not amplify. Negligible difference.
- **Bridge vs switch:** technically the same L2 device. "Bridge" is the historical few-port box; "switch" is the modern many-port marketing term. Each switch port is its own collision domain, so CSMA/CD is unnecessary on full-duplex links.
- **Switch vs router:** a switch forwards on the 48-bit MAC and never looks at IP. A router strips the frame header/trailer, reads the IP header, and never sees MAC addresses for its routing decision. A router also **breaks the broadcast domain** — which is why a loop on a switched segment storms but a loop across routers does not.
- **Gateway:** a general term for forwarding at L4–L7 that *translates* protocols (TCP↔SCTP, email↔SMS), not just forwards bits.

A bridge cannot blindly join dissimilar LANs (Ethernet ↔ 802.11): different frame formats need reformatting and a new CRC, different MTUs force drops, and security/QoS features (802.11 has link encryption and priorities; Ethernet does not) cannot be preserved. That is why dissimilar networks are joined by **routers**, not bridges.

## Build It

`code/main.py` is a self-contained 802.1D spanning-tree solver. To work through the mechanism:

1. Define a topology as a list of bridges (each with a Bridge ID) and links (each with two endpoints and a path cost). The included demo recreates the 5-bridge mesh of Fig. 4-44.
2. Run the **root election** — confirm the lowest Bridge ID wins and watch every other bridge stop claiming root.
3. Run **root-port selection** via shortest path costs (a Dijkstra-style relaxation from the root), with ties broken on sender Bridge ID then Port ID.
4. Compute **designated ports** per segment and mark everything else **BLOCKING**.
5. Print the resulting tree and the blocked links — these should match the dashed lines in the SVG.
6. Decode a raw Configuration BPDU hex string into its fields and verify the priority-vector comparison.

Run it with `python3 main.py` — no dependencies, no network access.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm STP is running | `show spanning-tree` / BPDUs to `01:80:C2:00:00:00` every 2 s in Wireshark | One Root ID agreed by all bridges; exactly one root port per non-root bridge |
| Find the blocked port | Port state column / STP topology dump | Each loop has exactly one port in BLK/Discarding; no segment has two designated ports |
| Diagnose a broadcast storm | Skyrocketing broadcast/multicast counters, CPU at 100%, all-port LED flicker | Storm stops the instant the redundant port goes to Blocking |
| Explain a 30 s outage after a link flap | Port walking Listening→Learning→Forwarding | Timing matches 2× Forward Delay (15 s + 15 s); RSTP would heal sub-second |
| Place a device on the layer map | Header the device forwards on (MAC vs IP vs payload) | You can state its collision domain and broadcast domain behavior |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **BPDU decode cheat sheet** mapping each byte offset to its field and the priority-vector comparison order.
- A **one-page STP storm runbook**: symptoms → confirm loop → find blocked port → timer math → RSTP migration note.
- A **device-layer triage card** (the table above) for fast "which layer is this?" calls.

Start from `outputs/prompt-spanning-tree-bridges-to-repeaters-hubs-bridges-switches-routers-and-g.md` and back it with the solver output from `code/main.py`.

## Exercises

1. Four bridges form a square: B-A0, B-B0, B-C0, B-D0 (use the trailing digit as priority) wired A–B, B–C, C–D, D–A, all links 100 Mbps (cost 19). By hand, pick the root, each bridge's root port, the designated port on each segment, and the one blocked port. Verify against `code/main.py`.
2. The link between the root and B2 in Fig. 4-44 is cut. Trace which blocked port unblocks, and compute the worst-case outage on legacy 802.1D using Max Age + 2× Forward Delay. Then state the RSTP figure.
3. You capture BPDUs and see two different Root IDs alternating every few seconds. What physical/configuration fault produces a flapping root election, and what counter or log confirms it?
4. A technician sets a bridge's priority to 0 to "make it the backbone." Explain how the 2-byte priority field overrides the MAC tiebreak, and one risk of forcing the root onto a low-capacity bridge.
5. Given a loop that storms on a pure switched segment but stops at the building's router, explain in terms of broadcast domains why the router contained it and the switches did not.
6. Map each of these to a device and the exact header field it forwards on: (a) extends a 500 m coax run to 2500 m, (b) isolates each port into its own collision domain using 48-bit addresses, (c) joins an Ethernet to an 802.11 WLAN of different MTU, (d) translates SMTP email to SMS.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Spanning Tree (STP) | "the loop-prevention thing" | IEEE 802.1D distributed algorithm reducing a bridge mesh to one loop-free tree by blocking redundant ports |
| BPDU | "STP packets" | Bridge Protocol Data Unit; Configuration BPDUs carry Root ID, Root Path Cost, Bridge ID, Port ID; sent to `01:80:C2:00:00:00`, never forwarded |
| Bridge ID | "the switch's name" | 2-byte priority + 6-byte MAC; the lowest one becomes root |
| Root bridge | "the main switch" | The bridge with the numerically lowest Bridge ID; reference point for all path-cost calculations |
| Root port | "uplink" | The single port on a non-root bridge with lowest cost back to the root |
| Designated port | "the active port on a link" | The one port per segment with lowest cost to root; all others on that segment block |
| Broadcast storm | "network meltdown" | A frame looping endlessly because Ethernet has no TTL, amplified by flooding until links saturate |
| Bridge vs Switch | "different devices" | The same L2 device; "switch" is the modern many-port name, "bridge" the historical few-port one |
| Gateway | "the router IP" (default gateway) | Generally an L4–L7 device that *translates* protocols (TCP↔SCTP, email↔SMS), distinct from a default-route router |
| RSTP | "fast STP" | IEEE 802.1w (2001); proposal/agreement handshake converging sub-second vs 30–50 s for 802.1D |

## Further Reading

- IEEE 802.1D — MAC Bridges (original Spanning Tree Protocol standard).
- IEEE 802.1w (2001) — Rapid Spanning Tree Protocol; later folded into 802.1D-2004.
- IEEE 802.3 — Ethernet, for the 48-bit MAC address and CRC fields a bridge inspects.
- RFC 791 — Internet Protocol, for the TTL field that makes routers loop-safe where bridges are not.
- Radia Perlman, *Interconnections: Bridges, Routers, Switches, and Internetworking Protocols*, 2nd ed. (2000) — the definitive treatment by the inventor of STP.
- Tanenbaum & Wetherall, *Computer Networks*, Chapter 4, "The Medium Access Control Sublayer," §4.8.3–4.8.4.
