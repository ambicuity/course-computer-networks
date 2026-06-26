# Virtual LANs to Bridge Learning Table Lab

> A VLAN turns one physical bridged LAN into several logical broadcast domains. IEEE 802.1Q (1998) implements this by inserting a 4-byte tag after the Source MAC: a 2-byte Tag Protocol Identifier fixed at 0x8100, then a 2-byte Tag Control Information field carrying a 3-bit PCP priority (802.1p), a 1-bit DEI/CFI flag, and a 12-bit VLAN Identifier (VID, 0..4095, with 0 = priority-only and 4095 reserved). Tagging raises the maximum Ethernet frame from 1518 to 1522 bytes and forces the FCS to be recomputed because the new bytes are covered by the CRC. A VLAN-aware switch keeps a per-VLAN learning table — a {VLAN, source MAC} -> port mapping with a 300 s default aging timer (IEEE 802.1D) — so the same MAC can legitimately live on different ports in different VLANs. Frames flood only within their VID, so VLAN 10 broadcasts never reach VLAN 20. The classic failure mode is a VLAN-mismatched trunk or a forgotten native VLAN: traffic silently black-holes because the egress switch has no port labeled with that VID. In this lab you parse real 802.1Q tags, simulate the per-VLAN learning table, and ship a diagnostic for live captures.

**Type:** Build
**Languages:** Wireshark, diagrams, Python
**Prerequisites:** Phase 06 lessons on Ethernet framing, transparent bridging, and the spanning tree protocol
**Time:** ~90 minutes

## Learning Objectives

- Decode an 802.1Q tag from raw hex: locate the 0x8100 TPID, then split the 16-bit TCI into PCP (3 bits), DEI (1 bit), and VID (12 bits).
- Explain why tagging raises the frame maximum to 1522 bytes and forces the FCS to be recomputed.
- Build a per-VLAN learning table keyed on `(vid, src_mac)` and reason about flood-vs-forward per VLAN.
- Trace how a frame floods only on ports labeled with its VID, and predict where it drops when a label is missing.
- Distinguish access ports (untagged, one VID) from trunk ports (tagged, many VIDs) and spot native-VLAN mismatch.
- Produce a reusable Wireshark filter set and a Python parser/simulator that confirms VLAN segmentation from evidence.

## The Problem

Two engineers sit on the same access switch, same subnet `10.0.10.0/24`, same cable run. One reaches the file server; the other gets nothing — no ARP reply, no ping, not even a broadcast. `tcpdump` on the dead host shows ARP requests leaving and never returning. The link is up, NIC counters increment, the port shows no errors. Layer 1 is fine. Layer 2 framing is fine. Yet the broadcast that should reach every neighbor never arrives.

The cause is invisible to the host: the working port is access VLAN 10, the dead port was left on default VLAN 1. Same wire physically, two broadcast domains logically. The ARP broadcast floods only on ports labeled with the frame's VID, and there is no VLAN-1 path to the server. The frame is not corrupted or lost on the medium — it is correctly delivered to the void. To diagnose, read the 802.1Q tag on the trunk, reconstruct the per-VLAN learning table, and see which VID a frame carries and which ports carry that VID. That is what `code/main.py` and `assets/virtual-lans-to-bridge-learning-table-lab.svg` make concrete.

## The Concept

### Why VLANs exist: collapsing geography into logic

In the thick-coax era a LAN was defined by the cable: whoever you passed, you joined. Twisted pair and switches let you rewire the building, but the broadcast domain stayed one flat physical LAN — every ARP, DHCP discover, and unknown-unicast flood hit every host. VLANs (Virtual LANs) let one administrator carve that physical bridged LAN into multiple logical LANs. A frame on VLAN 10 ("gray") and one on VLAN 20 ("white") share the same switches and trunk cables but never mix: a broadcast on gray reaches only gray ports. The administrator decides how many VLANs exist, which machines join each, and what each is called — VID 1..4094, often labeled by color.

### The 802.1Q tag, byte by byte

Ethernet had no spare field for a VLAN identifier, so the IEEE 802 committee changed the frame format. IEEE 802.1Q (1998) inserts a 4-byte tag *after* the Source MAC and *before* the EtherType/Length field:

| Field | Size | Value / meaning |
|---|---|---|
| Destination MAC | 6 bytes | unchanged |
| Source MAC | 6 bytes | unchanged |
| **TPID** (Tag Protocol ID) | 2 bytes | always `0x8100`. Because 0x8100 > 1500, legacy NICs read it as a Type, never a Length |
| **TCI** (Tag Control Info) | 2 bytes | three subfields, below |
| EtherType / Length | 2 bytes | the original type, now shifted 4 bytes right |
| Payload + Pad | 46..1500 | unchanged |
| FCS | 4 bytes | **recomputed** — the new bytes are inside the CRC |

The 16-bit TCI splits as:

```
 bit  15 14 13 | 12 | 11 10 9 8 7 6 5 4 3 2 1 0
       PCP     |DEI |        VLAN Identifier (VID)
      (3 bits) |(1) |              (12 bits)
```

- **PCP** (Priority Code Point, old 802.1p): 3 bits, 8 QoS classes separating hard real-time from best-effort. Nothing to do with VLAN segmentation; it rode along because changing the header is a once-a-decade event.
- **DEI/CFI**: 1 bit. Originally the Canonical Format Indicator (bit-order flag for embedded 802.5 frames), now reused as Drop Eligible Indicator.
- **VID**: low 12 bits, 0..4095. VID 0 = priority-tagged, no VLAN; VID 4095 reserved; 1..4094 usable; VID 1 is the conventional default/native VLAN.

`code/main.py` parses exactly these bytes from a hex frame and prints each subfield.

### Maximum frame size and the FCS consequence

The original 802.3 frame maxed at 1518 bytes (14-byte header + 1500 payload + 4-byte FCS). The tag pushes a full-size frame to 1522, so 802.1Q raised the limit to **1522 bytes**; only VLAN-aware gear need support it. Critically, the 4 tag bytes fall *inside* FCS coverage, so any device that inserts or strips a tag must recompute the 32-bit CRC. A capture showing the old FCS over a tagged frame means the tag was injected without re-checksumming — a malformed frame a switch would drop.

### Per-VLAN learning table

A transparent bridge learns by watching source addresses: see `S` arrive on port `p`, remember `S -> p`. A VLAN-aware bridge keys the table on `(VID, source MAC)`:

| VID | Source MAC | Port | Age (s) |
|---|---|---|---|
| 10 | 00:11:22:aa:bb:01 | 2 | 12 |
| 10 | 00:11:22:aa:bb:09 | 4 | 45 |
| 20 | 00:11:22:aa:bb:0f | 3 | 5 |

Two facts fall out of the compound key. First, the *same* MAC may appear on different ports in different VLANs without conflict — separate rows. Second, forwarding lookup is scoped to the frame's VID: a frame on VLAN 10 destined for `...bb:0f` (which lives only in VLAN 20) is an unknown unicast *within VLAN 10* and floods on VLAN-10 ports only. Each row ages with the IEEE 802.1D default of **300 seconds**; if no frame from that `(VID, MAC)` is seen within the timer, the row is evicted and the next frame to it floods again. `code/main.py` implements learn, lookup, flood, and age.

### Flood-vs-forward, scoped by VID

When a tagged frame arrives, the switch indexes the VID into its port-membership table to decide the egress set:

```
on frame (vid, dst, src) arriving on port p:
    learn (vid, src) -> p          # update/refresh table
    egress = ports_labeled_with(vid) - {p}
    if dst is broadcast/multicast OR (vid,dst) not in table:
        forward on all of egress            # flood within VLAN
    else:
        forward only on table[(vid,dst)]    # known unicast
```

In the two-VLAN example (gray=10, white=20) the SVG shows a port labeled with *both* VIDs because it carries machines from both VLANs; a port labeled only gray never carries a white broadcast. A trunk must be labeled with every VID that needs to cross it — the label set operators most often get wrong.

### Access ports, trunk ports, and the tagging boundary

Because legacy hosts cannot understand tags, the **first VLAN-aware bridge to touch a frame adds the tag and the last one removes it**. This gives two port roles:

- **Access port**: faces an end host, carries one VLAN *untagged*. The switch colors frames by the port's VLAN on ingress and strips the tag on egress. All hosts on one access port share one VID.
- **Trunk port**: connects switches or VLAN-aware hosts, carries many VLANs *tagged*. The tag tells the far switch which VLAN the frame belongs to.

802.1Q also allows coloring by higher-layer protocol (IP vs PPP) or, outside the standard, by source MAC (useful for roaming 802.11 laptops). Tags need only exist on inter-switch lines, not on wires to end stations.

### The native-VLAN / VID-mismatch failure mode

The dominant operational failure: a frame carries a VID the egress switch has no port labeled for, so the candidate egress set is empty and the frame is silently dropped — no error counter, no ICMP, nothing. Two flavors:

1. **Trunk omits a VID.** Switch A trunks VLANs 10 and 20 to B, but B's trunk allows only 10. VLAN-20 frames reach B and die. Evidence: tagged VID 20 frames egress A's trunk but never appear on B's access ports.
2. **Native-VLAN mismatch.** Each trunk has a *native VLAN* sent untagged. If A's native is 1 and B's is 99, A's untagged frames are absorbed into B's VLAN 99 — the opening scenario's silent black hole.

The fix is always: confirm the VID on the wire (parse the tag), confirm the port label set on both ends, and confirm native VLANs match.

## Build It

1. Open `code/main.py` and read `parse_8021q_frame()` — it slices MACs, checks the TPID equals 0x8100, and unpacks the 16-bit TCI into PCP/DEI/VID via bit masks (`tci >> 13`, `(tci >> 12) & 1`, `tci & 0x0FFF`).
2. Run `python3 main.py`. Confirm it prints VID, PCP, and the 1522-byte max for the tagged frame and treats the 0x0800-TPID frame as untagged.
3. Read `BridgeLearningTable`: trace `learn()`, `lookup()`, and `age()`, noting the `(vid, mac)` compound key.
4. Watch the simulation replay a frame sequence across a two-VLAN switch — each learn/flood/forward decision, then aging out stale rows.
5. In Wireshark apply `vlan` to isolate tagged frames, `vlan.id == 10` to scope one VLAN, and `vlan.priority` to check QoS marking.
6. Replace the sample sequence with frames from your own capture; confirm the simulated table matches `show mac address-table vlan 10` on the switch.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame is tagged | TPID `0x8100` after the source MAC; filter `vlan` | Frame is 4 bytes longer than untagged (up to 1522) |
| Read the VLAN ID | Low 12 bits of the TCI; `vlan.id == N` | VID matches the access port's configured VLAN |
| Verify QoS marking | PCP = top 3 bits of TCI; `vlan.priority` | Voice shows PCP 5/6, bulk data PCP 0 |
| Prove two hosts are isolated | VLAN-10 broadcast never seen on VLAN-20 ports | Cross-VLAN broadcast appears in zero VLAN-20 captures |
| Diagnose a black hole | Tagged frame egresses trunk, no egress port labeled with its VID | Missing trunk VID or native-VLAN mismatch identified |

## Ship It

Produce one reusable artifact under `outputs/`:

- A Wireshark filter cheat-sheet for VLAN triage (`vlan`, `vlan.id == N`, `vlan.priority >= 5`).
- A native-VLAN-mismatch runbook with the three checks (VID on wire, port label set, native VLAN).
- The `BridgeLearningTable` simulator extended to load frames from a `tshark -T fields` export.

Start from [`outputs/prompt-virtual-lans-to-bridge-learning-table-lab.md`](../outputs/prompt-virtual-lans-to-bridge-learning-table-lab.md).

## Exercises

1. Given hex `... 8100 a00a 0800 ...`, decode the TPID, PCP, DEI, and VID from the `0xa00a` TCI. Which VLAN, and what priority class?
2. A trunk allows VLANs 10 and 30, but a VLAN-20 host cannot reach a server two switches away. Without touching the host, where is the frame dropped and what single trunk change fixes it?
3. Switch A native VLAN = 1, B native VLAN = 99, trunk between them. A host sends an untagged frame on A. Which broadcast domain does it land in on B, and what capture evidence proves it?
4. The same MAC appears on port 2 in VLAN 10 and port 5 in VLAN 20 in your table. Loop/flapping bug or legitimate? Justify using the compound key.
5. A frame tagged VID 10 reaches a legacy VLAN-unaware NIC. What must the last switch do before delivery, and what happens to the frame length and FCS?
6. Age every table row past 300 s, then send one broadcast on VLAN 10. Predict the flood set before and after aging and explain the difference.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| VLAN | "a separate network on the switch" | One logical broadcast domain carved from a physical bridged LAN, identified by a 12-bit VID |
| 802.1Q tag | "the VLAN header" | A 4-byte field (TPID 0x8100 + 2-byte TCI) after the source MAC; carries PCP, DEI, and VID |
| VID | "the VLAN number" | Low 12 bits of the TCI; 1..4094 usable, 0 = priority-only, 4095 reserved |
| PCP / 802.1p | "the priority bits" | Top 3 bits of the TCI; 8 QoS classes, unrelated to VLAN isolation |
| Trunk port | "the uplink" | Carries many VLANs *tagged*; the tag tells the far switch the VID |
| Access port | "the host port" | Carries one VLAN *untagged*; the switch colors frames by port config |
| Native VLAN | "VLAN 1" | The VLAN sent untagged on a trunk; a mismatch silently mixes broadcast domains |
| Per-VLAN learning table | "the MAC table" | A `(VID, MAC) -> port` map with 300 s aging; same MAC can repeat across VLANs |

## Further Reading

- IEEE 802.1Q-2022, *Bridges and Bridged Networks* — authoritative VLAN tagging and frame format.
- IEEE 802.1D, *MAC Bridges* — transparent bridging, learning, 300 s aging default.
- IEEE 802.3, *Ethernet* — base frame format and the 1518-to-1522-byte length change.
- Tanenbaum & Wetherall, *Computer Networks*, Ch. 4, section on Virtual LANs and the 802.1Q standard.
- Seifert & Edwards, *The All-New Switch Book* — VLAN, trunking, and learning-table behavior.
- Wireshark docs: the `vlan` dissector and `vlan.id` / `vlan.priority` filters.
