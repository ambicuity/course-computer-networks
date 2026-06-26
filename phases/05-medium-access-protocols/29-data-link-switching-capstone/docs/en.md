# Capstone: backward-learning bridges, 802.1D/RSTP spanning tree, and 802.1Q VLANs

> A transparent bridge keeps a forwarding table keyed on (MAC, port) populated by **backward learning** — record `S -> P` on every received frame, and **flood** unknown destinations on every port except P. IEEE **802.1D** STP breaks loops with BPDUs (multicast `01:80:C2:00:00:00`, version 0); root election picks the lowest Bridge ID (4-bit priority + 12-bit VLAN-aware extension + 48-bit MAC) and the worst-case convergence is 30-50 s. **RSTP** (802.1w, now in 802.1Q-2014) drops convergence to under a second with explicit port roles and a Proposal/Agreement handshake on point-to-point links. **802.1Q VLANs** insert a 4-byte tag between SA and EtherType/Length: TPID `0x8100` + TCI = PCP(3) | DEI(1) | VID(12), so VID 1-4094 identifies the broadcast domain.

**Type:** Capstone
**Languages:** Python (stdlib only: learning bridge, STP/RSTP simulator, 802.1Q tagger)
**Prerequisites:** Classic Ethernet MAC sublayer (CSMA/CD, slot time, 64-byte minimum, CRC-32), 802.3 frame format, hub-vs-bridge-vs-router distinction (Sec. 4.8.4)
**Time:** ~100 minutes

## Learning Objectives

- Build a 3-port transparent bridge in code: maintain a forwarding table with timestamps, perform **backward learning** on every received frame, **flood** unknown destinations, and **filter** frames whose source and destination port are identical.
- Distinguish **store-and-forward** from **cut-through** switching, and identify when cut-through is unsafe (damaged frame, port speed mismatch).
- Trace the STP root election on a triangle topology from initial bridge IDs to a loop-free active topology: pick the lowest Bridge ID as root, compute the lowest path cost, elect one Designated port per segment, and put all other ports into Blocking.
- Contrast 802.1D STP (timers + port states) with RSTP Proposal/Agreement: explain why RSTP can move a previously-blocking point-to-point link to Forwarding inside one round-trip.
- Parse and build an 802.1Q-tagged Ethernet frame: confirm the **TPID 0x8100** marker, decode the 16-bit TCI into PCP (3) / DEI (1) / VID (12), insert/remove the tag, and apply VLAN-aware flooding rules.
- Reason about broadcast storms and the multiple-frame-copy problem in a looped Layer 2 fabric, and explain how MSTP (802.1s) and per-VLAN STP load-balance.

## The Problem

A junior engineer has just cabled three access-layer switches into a triangle: SW1-SW2, SW2-SW3, SW3-SW1. Forwarding looks fine for the first 30 seconds. Then ping latency spikes, ARP requests time out, switch CPU climbs to 100%, and within a couple of minutes the entire VLAN has gone dark. `show interface counters` shows thousands of frames per second going out the *receiving* port, and Wireshark off one uplink shows the same ARP request appearing dozens of times within a few hundred microseconds. This is not a routing loop — TTL is still in the hundreds. It is a **Layer 2 loop**, and the broadcast storm has saturated the wires and destabilized the bridges' MAC tables.

Two questions follow. First, how does **Spanning Tree Protocol** turn a triangle of cables into exactly two active links and one parked link, so loops become impossible? Second, if STP takes 30-50 seconds to converge, how does **RSTP** recover from a link failure in well under a second? Once loops are gone, the engineer still has a separate problem: the same fabric is shared by **Finance** (sensitive, isolated), **Voice** (QoS-tagged, low-latency), and **Engineering** (chatty multicast). How does a single physical switch keep those three broadcast domains apart without a forest of separate boxes? That is the job of **802.1Q VLAN tagging**, and the tag is four bytes wedged exactly where the Ethernet EtherType field used to live.

## The Concept

### Bridge architecture, learning, and the forwarding table

A **transparent bridge** is a Layer 2 device with k ports and one shared **relay function**. The relay owns a **forwarding table** (`MAC -> (port, age)` map), a configurable **aging time** (default 300 s = 5 min), and a per-port **VLAN membership list** once 802.1Q is in play. Each port is its own collision domain; with full-duplex point-to-point links CSMA/CD is not used.

When a frame arrives on port P: (1) **Learn** `(src_mac, P) -> (P, now)`. (2) **Look up** `dst_mac`: known and same port as src -> drop (filter); known and different port -> forward on that single port; unknown -> flood on every port except P, restricted to the frame's VLAN. (3) Broadcast and multicast are also flooded, only on ports that are VLAN members. A background sweeper purges entries older than the aging time. **Store-and-forward** buffers the full frame and verifies the CRC (the default). **Cut-through** reads only the destination MAC for ~11 ns of forwarding delay at 10 Gbps, but damaged frames are forwarded, so cut-through is only safe on same-speed full-duplex links. Without loop prevention, a triangle's broadcast storm saturates the wires and MAC-flaps entries every microsecond.

### Spanning Tree Protocol and RSTP (IEEE 802.1D / 802.1w, now 802.1Q-2014)

The cure is a *distributed algorithm* that elects a **root bridge** and selects, for every other bridge, exactly one **root port** (the port on the bridge's shortest path to the root) and exactly one **Designated port** per segment. Every other port is parked in **Blocking** state and forwards no frames. The result is a loop-free **spanning tree** that reaches every bridge.

**Bridge ID.** 8 bytes: 4-bit priority + 12-bit extended-system-id + 48-bit MAC. The simulator uses 2-byte priority (default `0x8000` = 32768) + 6-byte MAC. **Path cost.** 32-bit unsigned, summed along the path. Classic costs: `4` (1 Gbps), `19` (100 Mbps), `100` (10 Mbps); modern 802.1D-2004 uses 32-bit values.

**BPDU.** A Configuration BPDU layout (bytes): Protocol ID 2 (`0x0000`), Version 1 (`0` STP / `2` RSTP), Type 1, Flags 1, Root Bridge ID 8, Root Path Cost 4, Sender Bridge ID 8, Sender Port ID 2, Message Age 2, Max Age 2 (`20`), Hello Time 2 (`2`), Forward Delay 2 (`15`). BPDUs are sent to the reserved group address **`01:80:C2:00:00:00`**. Convergence budget: **`Max Age + 2 * Forward Delay = 50 s`**. Root election picks the lowest Bridge ID; tie-breaks are lower path cost, then lower sender Bridge ID, then lower sender Port ID.

**RSTP (802.1w, now in 802.1Q-2014)** keeps the BPDU format but changes the timer model. Three port states (Discarding, Learning, Forwarding) and five **port roles**: **Root**, **Designated**, **Alternate** (alternative path to the root), **Backup** (alternative path to the same segment as another port on the same bridge), and **Edge** (access port, transitions to Forwarding immediately on link-up). The convergence trick is the **Proposal/Agreement handshake** on a point-to-point link: a Designated port sends a Proposal; the downstream bridge places all non-edge ports into Discarding (the "sync" step) and replies with an Agreement. The segment moves from blocking to forwarding inside one round-trip — typically a few milliseconds, not 30-50 seconds. The fast path requires (1) the link is **point-to-point** (full-duplex; half-duplex falls back to classic STP), and (2) the new port is **Edge** or the path cost through it is strictly better than the bridge's current Root port's cost.

### Virtual LANs (IEEE 802.1Q)

A **VLAN** is a Layer 2 broadcast domain identified by a 12-bit number — **VID 1-4094** (VID 0 and 4095 are reserved). The bridge carries a per-port **VLAN membership list**; the forwarding table also records the VLAN of every learned MAC. A broadcast in VLAN 10 is flooded only on ports that are members of VLAN 10. A trunk port carries frames for many VLANs and tags them; an access port is a member of exactly one VLAN and carries untagged frames.

The **802.1Q tag** is a 4-byte field inserted between the source MAC and the EtherType/Length field: TPID (16) = `0x8100` and TCI (16) = PCP(3) | DEI(1) | VID(12). TPID is greater than 1500, so legacy Ethernet cards interpret it as a Type. The standard also defines `0x88a8` for service-provider tagging (Q-in-Q, 802.1ad) — the same TCI layout, different outer TPID. The 802.1Q frame is 4 bytes longer than the legacy 802.3 frame, so the maximum frame is 1522 bytes. **Double-tagging (Q-in-Q, 802.1ad)** stacks a second 4-byte tag for service-provider or metro Ethernet use, growing the frame to 1526 bytes. **GVRP** advertises VLAN memberships across switches; **Voice VLAN** lets an access port carry untagged data in one VLAN and tagged voice in another (PCP 5 is the typical voice priority); **MSTP (802.1s)** maps many VLANs to a small number of spanning-tree instances.

A modern access switch does **all three jobs simultaneously**: transparent bridge, spanning-tree participant, and VLAN-aware relay.

## Build It

`code/main.py` is a stdlib-only Python module with three components wired together by a `__main__` block.

1. **Learning bridge (`Bridge` class).** Holds a forwarding table as `dict[mac -> (port, last_seen)]`, an `aging_seconds` argument (default 300), and a `vlan_membership` map. `receive(port, frame)` does backward learning and dispatches to `FORWARD`, `FLOOD`, or `DROP`.
2. **STP/RSTP simulator (`stp_root_election` and `rstp_propose_agree`).** A `Triangle` topology holds three `BridgeStub`s with configurable Bridge ID, port list, and per-port cost. The STP routine runs a fixed-point message-passing algorithm until every bridge stabilizes on the same root and a consistent set of port roles. The RSTP routine demonstrates the Proposal/Agreement handshake by walking a point-to-point link from Blocking to Forwarding in two message exchanges.
3. **802.1Q tagger (`vlan_tag` and `vlan_untag`).** Pure functions over byte sequences: `vlan_tag(frame_bytes, vid, pcp, dei)` returns the 4-byte-elongated frame, `parse_vlan_tag` returns the TCI fields, and `vlan_untag` strips the tag.

Run `python3 code/main.py` to see four scenarios: triangle convergence, RSTP Proposal/Agreement, broadcast storm vs loop-free, and a tagged/untagged VLAN round-trip. Then edit the topology (e.g. change B2's Bridge ID to win the root election) and the VLAN list to see how the simulation reacts.

## Use It

| Task | What good looks like |
|---|---|
| Read a bridge forwarding table | `Bridge.table` is `(mac) -> (port, age)`; entries older than `aging_seconds` are purged |
| Trace backward learning | After A sends on port 1, `A -> 1` is in the table; after a frame from A on port 3, the entry moves to `A -> 3` |
| Trace flood of unknown unicast | Frame appears on every port except the source port, exactly once, restricted to the frame's VLAN |
| Pick the STP root | Lowest 8-byte Bridge ID wins; ties broken by lower path cost, then lower sender Bridge ID, then lower sender Port ID |
| Read port roles | Root and Designated ports move to Forwarding; Alternate/Backup ports are listed explicitly |
| Decode an 802.1Q tag | `TPID=0x8100`, `PCP` in 0-7, `DEI` in 0-1, `VID` in 1-4094 |
| Walk a tagged frame across a trunk | Frame leaves access port as 14-byte Ethernet+payload, becomes 18-byte-`0x8100`-tagged on the trunk, returns to 14 bytes on the egress access port |
| Predict broadcast-storm behavior | Without STP, the same broadcast is re-emitted every iteration; with STP, the triangle's third link carries zero frames |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **bridge + STP + VLAN cheat sheet**: forwarding table lookup rules, BPDU field table, RSTP port roles, 802.1Q tag layout, and the broadcast-storm root cause.
- A **hand-trace of the triangle**: draw the triangle, label each link with its port and cost, and write out the STP root election and the final `Root/Designated/Blocking` roles. Then mark the 802.1Q tag for two example frames (one same-VLAN, one cross-VLAN) and confirm where each is forwarded.
- The **simulator script** (`code/main.py`) wired to your own triangle and VLAN IDs. Re-run with a different root and with a slow port to see the convergence budget change.

Start from `outputs/prompt-data-link-switching-capstone.md`.

## Exercises

1. **Storm math.** A triangle of bridges runs at 1 Gbps; a single ARP broadcast is 60 bytes. Estimate the steady-state broadcast frame rate per port if the loop has latency `L` us and the bridge forwarding latency is `t_f` us. Then place one Designated port into Blocking and re-estimate. (Order-of-magnitude; show the formula.)
2. **Root election.** Five bridges have Bridge IDs `0x8000/..:55`, `0x8000/..:66`, `0x4000/aa:bb:cc:dd:ee`, `0x8000/..:88`, `0x8000/00:00:00:00:01`. Which one becomes root?
3. **Aging.** A bridge has `aging_seconds=300`. A host that is silent for 10 minutes moves to a new port. What is the worst-case window during which its old entry is still in the table? Will a frame sent to that host be delivered, flooded, or dropped?
4. **RSTP convergence timing.** A 1 Gbps P2P link between two RSTP bridges, 100 m of Cat 6 cable. Estimate the wall-clock time from Proposal to Forwarding, including wire propagation and the Sync step. (STP budget is 30-50 s; show the gap.)
5. **VLAN tagging.** A frame arrives on an access port in VLAN 10 with `dst = ff:ff:ff:ff:ff:ff`. Walk it through a trunk to a second access port in VLAN 20. Which bridge drops it, and on which field — TPID, TCI/VID, or membership?
6. **MSTP load balancing.** 200 VLANs and 4 uplinks in a ring. With classic STP, only one uplink carries traffic. Describe how MSTP / per-VLAN RSTP spreads the load, and name the trade-off.

## Key Terms

| Term | What it actually means |
|---|---|
| Transparent bridge | A Layer 2 relay that learns MAC->port by watching frames and floods unknown destinations |
| Backward learning | On every received frame, record `(src -> incoming_port, timestamp)` |
| Flooding | Send the frame on every port except the one it arrived on, restricted to the frame's VLAN |
| Aging time | Entries older than the aging time are purged; default 300 s |
| Store-and-forward / Cut-through | Store-and-forward buffers the full frame and verifies the CRC (the default). Cut-through reads only the destination MAC for ~11 ns of forwarding delay; only safe on same-speed full-duplex links |
| Broadcast storm | Unbounded amplification of Layer 2 broadcasts in a looped fabric, with MAC-table thrash |
| STP / 802.1D | Distributed spanning-tree algorithm; Hello 2 s, Max Age 20 s, Forward Delay 15 s, 30-50 s convergence |
| BPDU | Bridge PDU, multicast `01:80:C2:00:00:00`, version 0 (STP) or 2 (RSTP) |
| Bridge ID | 8 bytes: 4-bit priority + 12-bit VLAN-aware extension + 48-bit MAC; lower wins |
| Path cost | Sum of per-link costs; 4 (1 Gbps), 19 (100 Mbps), 100 (10 Mbps) in classic form |
| RSTP / 802.1w | Same BPDU, 3 port states, 5 port roles, Proposal/Agreement on P2P links, sub-second convergence |
| Proposal/Agreement | Designated sends Proposal; downstream Syncs (Discarding), replies with Agreement; segment goes Forwarding |
| Edge / Alternate / Backup | Edge: an RSTP port to a single host; transitions immediately. Alternate: alternative path to the root. Backup: alternative path to the same segment |
| 802.1Q | 4-byte tag inserted between SA and EtherType: TPID `0x8100`, TCI = PCP(3) / DEI(1) / VID(12) |
| VID | 12-bit VLAN identifier, 1-4094; 0 and 4095 are reserved |
| Access / Trunk port | Access: a port in exactly one VLAN, untagged. Trunk: a port carrying tagged frames for many VLANs |
| Q-in-Q / MSTP | Q-in-Q (802.1ad): stack a second 802.1Q tag (outer TPID `0x88a8`). MSTP (802.1s): map many VLANs to a few spanning-tree instances |

## Further Reading

- **IEEE 802.1D-2004** — Media Access Control (MAC) Bridges. The original STP specification with 32-bit path cost and the GMRP/GVRP machinery.
- **IEEE 802.1Q-2014** — Bridges and Bridged Networks (and 802.1Q-2018 / 802.1Q-2022 updates). The VLAN tag, VID space, PCP/DEI, Q-in-Q (802.1ad), and the integration of RSTP (formerly 802.1w) and MSTP (formerly 802.1s).
- **Radia Perlman, *Interconnections: Bridges, Routers, Switches, and Internetworking Protocols* (2nd ed., Addison-Wesley, 2000)** — the canonical treatment of transparent bridging and the spanning-tree algorithm.
- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Sec. 4.8** — the source chapter for this lesson.
