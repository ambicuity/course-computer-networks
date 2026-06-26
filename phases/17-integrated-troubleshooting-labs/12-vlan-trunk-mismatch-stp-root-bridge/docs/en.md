# VLAN Trunk Mismatch and STP Root Bridge

> Two Cisco switches are joined by an 802.1Q trunk. Switch A permits VLANs 10-20 on the trunk; Switch B permits VLANs 10-15. The four-byte 802.1Q tag (TPID `0x8100`, then TCI with 12-bit VLAN ID, 3-bit PCP/priority, 1-bit DEI; IEEE 802.1Q §9.6) on a frame from VLAN 16 arrives at Switch B, fails the ingress allowed-VLAN check, and is silently dropped. The user with a phone on VLAN 16 in Building A reports that calls to the call manager in Building C ring once and die; the user on VLAN 15 has no problem. The same physical link carries both VLANs, so `show interface trunk` on Switch A shows VLANs 10-20 active, `show interface trunk` on Switch B shows VLANs 10-15 active, and the network operator has to walk both ends to compare. Compounding the trunk problem, Spanning Tree Protocol (802.1D-2004, superseded by 802.1Q-2014 §13) has elected the wrong root bridge. An access switch with default priority `32768` and a low MAC address won root over the distribution switch whose priority was left at `32768` too. Now interswitch traffic detours through the access layer, the blocking ports are on the high-capacity uplinks, and a single access-switch reboot reconverges STP — taking down the L2 domain for 30-50 seconds. This lab reproduces both failures in one combined scenario: an 802.1Q allowed-VLAN list mismatch across a single trunk AND a tie-on-priority STP root election. The combined effect is that some VLANs blackhole on the trunk and *all* VLANs take a sub-optimal L2 path. The fix on the trunk side is to align the allowed lists (and the native VLAN, IEEE 802.1Q §9.6, default 1) on both ends; the fix on STP is to set `spanning-tree vlan 1-4094 priority 4096` (or `spanning-tree vlan 1-4094 root primary`) on the intended core, enable BPDU Guard (IEEE 802.1Q §11.2.6) on access ports to stop rogue switches, and enable Root Guard (802.1Q §11.2.7) on the distribution-to-access uplinks.

**Type:** Lab
**Languages:** Python, shell, switch CLI (Cisco / FRRouting / Cumulus)
**Prerequisites:** Phase 6 VLAN/STP lesson, Phase 17 lesson 11 (BGP), IEEE 802.1Q / 802.1D / 802.1w
**Time:** ~105 minutes

## Learning Objectives

- Decode an 802.1Q tag (TPID `0x8100`, TCI = PCP 3 bits + DEI 1 bit + VID 12 bits) and identify the VLAN ID and priority code point (PCP) for a tagged frame.
- Diagnose an 802.1Q trunk allowed-VLAN mismatch by reading `show interface trunk` on both ends and comparing the `VLANs allowed` and `VLANs in spanning-tree forwarding` lists.
- Trace STP root bridge election (lowest bridge ID = priority + MAC, IEEE 802.1D §8.5) and identify an unintended root that has a low MAC but a default priority.
- Compute the spanning tree path cost (IEEE 802.1D §8.4: cost = `2.0 × 10^9 / link_bandwidth_bps`, updated in 802.1t to the shorter path-cost table with 1 Gbps = 4, 10 Gbps = 2) for a set of links and find the root port on each non-root bridge.
- Distinguish RSTP (802.1w) convergence (sub-second) from STP (802.1D) convergence (30-50 seconds with default timers).
- Build a Python simulator that computes the root bridge and the trunk's effective VLAN set given two switch configs.

## The Problem

The on-call ticket reads: "Phones in Building A can register to the call manager for 8-12 seconds, then lose registration. The call manager is in Building C. A walk-test of `show cdp neighbor` from a phone shows it reaches a switch in Building A but not the call manager's VLAN. Other VLANs (data, Wi-Fi) work fine. We see the trunk is up; we see both ends in CDP. The users are split: half the building has the issue, half does not." The platform team starts at the access switch and walks the path: `show interface trunk` on Switch A's uplink shows `VLANs allowed: 10-20, active: 10-20`. `show interface trunk` on Switch B's uplink shows `VLANs allowed: 10-15, active: 10-15`. The mismatch is the bug.

A second issue compounds it. While the platform team is on-site, they walk the L2 path with `traceroute mac` (Cisco) or with ARP-table polling and find that a frame from a phone in Building A to the call manager goes Switch A → Switch Access3 → Switch Dist1 → Switch Core → Switch Dist2 → Switch B, then on to the call manager. The path is six switches. They expect three: Switch A → Core → Switch B. Something has made Switch Access3 the root. `show spanning-tree root` on each switch confirms: the root bridge ID is `32768.0cab.abcd.ef00` (priority 32768, MAC `0cab.abcd.ef00`), which is one of the access-layer switches. The intended core switch has priority 32768 too, and MAC `0cab.0000.0001`. The access switch won on the tiebreak (lower MAC).

The combined failure looks like "VLAN 16-20 phones break, and even VLAN 10-15 phones take the long way around." The fix is two independent changes: align the trunk allowed-VLAN list, and pin the root to the intended core with `spanning-tree vlan 1-4094 root primary` (or priority 4096). A third change is preventative: enable BPDU Guard on access ports so that a rogue switch never becomes root again.

`code/main.py` implements the STP root-election algorithm and the 802.1Q trunk verifier, and lets you walk through three scenarios: `trunk_aligned`, `trunk_mismatch`, `wrong_root`.

## The Concept

### The 802.1Q tag and the trunk

An 802.1Q tag is a 4-byte header inserted into an Ethernet frame after the source MAC. The fields are:

```
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |  Type = 0x8100  (TPID)        |  PCP | DEI |    VID (12 bits)  |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |       (followed by original EtherType, then payload)         |
```

- **TPID** (Tag Protocol Identifier) is `0x8100` for customer-tagged 802.1Q; `0x88a8` for service-provider (Q-in-Q, 802.1ad).
- **PCP** (Priority Code Point, 3 bits) maps to one of eight traffic classes; used for QoS scheduling (IEEE 802.1Q §8.6).
- **DEI** (Drop Eligible Indicator, 1 bit) marks frames as drop-eligible under congestion.
- **VID** (VLAN Identifier, 12 bits) — 0 is the priority tag (frame is tagged but has no VLAN), 1 is the default, 4094 and 4095 are reserved.

A *trunk* is a port that carries tagged frames for multiple VLANs. Each trunk has:

- An **allowed-VLAN list**: the set of VLAN IDs the switch will accept on that port. Frames tagged with a VLAN not in the list are silently dropped at ingress (and a counter increments).
- A **native VLAN**: a single VLAN whose frames are sent *untagged* across the trunk. If the native VLAN on Switch A is 1 and on Switch B is 999, a frame from VLAN 1 sent by A arrives at B as untagged, B places it in VLAN 999, and the VLANs leak into each other.

When the lists differ, the symptoms are exactly the partial-VLAN failure seen in the ticket.

### STP bridge ID, root election, and port roles

Every switch running STP has a **bridge ID** = `(priority, MAC)`, 8 bytes total. Priority is a 16-bit value where the lower 12 bits are user-settable and the upper 4 are reserved. The default is `32768` (the "extended" default, which incorporates the VLAN into the upper 4 bits of the priority field in PVST+). The MAC is the bridge's base MAC.

The root election (IEEE 802.1D §8.5) is:

1. Initially every bridge claims to be root with its own bridge ID.
2. BPDUs (Bridge Protocol Data Units, IEEE 802.1D §9.3) are exchanged. A bridge that receives a BPDU with a lower bridge ID stops claiming root.
3. After convergence, the bridge with the lowest bridge ID is root.

Once the root is chosen, every other bridge computes the lowest-cost path to the root. Path cost is 1 Gbps → 4, 10 Gbps → 2 (802.1t table). The port on the lowest-cost path is the **root port**. On each L2 segment, the bridge that has the lowest cost to the root becomes the **designated bridge** for that segment, and its port on the segment is the **designated port**. All other ports on the segment enter the **blocking** state.

If a single bridge has the lowest MAC in a flat priority field of 32768, it wins root over the intended core. The fix is to lower the priority of the intended core to 4096 (the second-lowest settable value is 8192). A `spanning-tree vlan X root primary` macro picks 4096 for the primary and 8192 for the secondary.

### RSTP (802.1w) and MSTP (802.1s)

RSTP replaces 802.1D's 30-50 second convergence with sub-second by:

- Defining new port roles: `Alternate` (backup to a root port) and `Backup` (backup to a designated port).
- Using a proposal-agreement handshake on point-to-point links to fast-transition a port to `Forwarding`.
- Keeping the same bridge-ID election.

MSTP (802.1s) groups multiple VLANs into a single spanning-tree instance. The operator configures 2-16 instances, each with its own root bridge and topology. The benefit is that operators with hundreds of VLANs do not have to run one STP instance per VLAN (CPU cost) and can engineer per-traffic-class topology.

### BPDU Guard and Root Guard

BPDU Guard (IEEE 802.1Q §11.2.6) is an *access-side* defense. When enabled, a port that receives a BPDU transitions to `err-disable`. The use case: access-layer ports should never see BPDUs. If they do, a rogue switch has been plugged in.

Root Guard (IEEE 802.1Q §11.2.7) is an *uplink-side* defense. When enabled, a port that receives a superior BPDU (one that would change the root) transitions to `root-inconsistent` and stops forwarding. The use case: ensure an access switch never becomes root, even if its MAC is lower than the core's.

Together, the two are a complementary pair: BPDU Guard stops the rogue from sending BPDUs, Root Guard stops the network from accepting them as a new root.

### Path cost table (802.1t, 32-bit values)

| Link speed | Path cost (802.1t) |
|---|---|
| 10 Mbps | 2,000,000 |
| 100 Mbps | 200,000 |
| 1 Gbps | 20,000 (rounded; some platforms still use 4 from 802.1D) |
| 10 Gbps | 2,000 |
| 25 Gbps | 800 |
| 40 Gbps | 500 |
| 100 Gbps | 200 |

The simulator uses the 802.1t values for the path-cost computation in the root-port selection.

### How the simulator models this

`code/main.py` has two parts. The first is an 802.1Q trunk verifier: given two switches each with an allowed-VLAN list, it computes the intersection, the VLANs that are dropped at the far end, and reports the native-VLAN match. The second is an STP root election: given a set of bridges with priorities and MACs, plus a graph of links with path costs, the simulator runs the election, picks the root, then walks every bridge to find the root port (lowest cost to root) and the blocked ports (any non-designated, non-root port on a segment). Three scenarios are wired: `trunk_aligned`, `trunk_mismatch`, `wrong_root`, and a combined `trunk_mismatch_and_wrong_root` that reproduces the ticket exactly.

## Build It

1. **Set up a 4-switch lab.** Switch Core (intended root), Switch Dist1 + Dist2 (distribution), Switch Access3 (the rogue root in the ticket). All running FRR or Cumulus. Use VLANs 10-20 on the trunk.
2. **Configure the trunk.** On Switch A: `interface Te0/1; switchport trunk allowed vlan 10-20`. On Switch B: `switchport trunk allowed vlan 10-15`. `show interface trunk` on both ends and compare.
3. **Watch STP fail.** `show spanning-tree root` on each switch. Confirm Access3 is root. Note the bridge ID `32768.0cab.abcd.ef00`.
4. **Run the simulator.** `python3 code/main.py --scenario trunk_mismatch_and_wrong_root` and confirm the simulator's output matches the lab.
5. **Fix the trunk.** Update Switch B to `switchport trunk allowed vlan 10-20`. Re-capture.
6. **Fix STP.** On Core, `spanning-tree vlan 1-4094 priority 4096`. Watch the root move to Core in `show spanning-tree root`.
7. **Add the guards.** `spanning-tree portfast bpduguard default` on access ports, `spanning-tree guard root` on the access-side uplinks.
8. **Ship the runbook.** A trunk + STP hardening runbook with the exact commands and a verification probe.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compare trunk config | `show interface trunk` both sides | Allowed lists identical; native VLAN matches; DTP mode consistent |
| Find root bridge | `show spanning-tree root`, `show sp tree bridge` | Root is the designated distribution/core switch; priority ≤ 8192 |
| Trace blocked port | `show spanning-tree blockedports` | Block on the redundant access-to-access link, not on core uplinks |
| Detect BPDU Guard | `show interfaces status err-disabled` | No err-disabled ports after a clean walk |
| Validate fix | Re-run `show interface trunk`, `show sp root` | All expected VLANs present; root = intended core; blocked port in expected position |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **trunk + STP hardening runbook** with the exact CLI commands, a per-VLAN allowed-list matrix, a root-bridge priority table, and the BPDU Guard / Root Guard placements.
- A monitoring probe (Python + `pysnmp` or a `show` scrape) that asserts the root bridge ID is stable, the trunk allowed lists match on both ends, and the native VLAN is 1 (or whatever unused VLAN is your convention).

Start from `outputs/prompt-vlan-trunk-mismatch-stp-root-bridge.md` and paste in actual `show interface trunk` and `show spanning-tree root` excerpts from your lab.

## Exercises

1. Add a third switch in a triangle and determine which port blocks when the root is correct versus when an access switch wins. Verify with `show spanning-tree blockedports`.
2. Introduce a native-VLAN mismatch (A=999, B=1) and describe the security implication (an attacker on VLAN 999 on Switch A can reach the native VLAN on Switch B untagged, hopping into VLAN 1 if the native matches).
3. Enable BPDU Guard on an access port and simulate a rogue switch sending superior BPDUs; confirm the port goes `err-disable` and `show interfaces status err-disabled` lists the port.
4. Model MSTP with two instances (instance 1 → VLAN 1-200, instance 2 → VLAN 201-400) and show that the root can differ per instance. Explain why operators with hundreds of VLANs prefer MSTP over PVST+.
5. Propose a monitoring probe that parses `show spanning-tree root` hourly and alerts if the root bridge ID changes. What false positives are likely and how would you tune the alert?
6. Enable Root Guard on a distribution uplink and simulate an access switch claiming root. Confirm the uplink enters `root-inconsistent` and stops forwarding.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| 802.1Q trunk | Tagged link | One physical link carrying multiple VLANs via a 4-byte TPID=0x8100 tag (IEEE 802.1Q §9.6) |
| Allowed-VLAN list | Trunk allow list | Per-trunk filter of which VLAN IDs may cross; must match on both ends |
| Native VLAN | Untagged VLAN | The single VLAN whose frames cross the trunk without an 802.1Q tag (default 1) |
| Bridge ID | STP identifier | (priority, MAC) 8-byte value; lowest wins root election (IEEE 802.1D §8.5) |
| Root bridge | STP root | The bridge with the lowest bridge ID; all paths computed toward it |
| Root port | Port toward root | On non-root bridges, the lowest-cost port to the root |
| Designated port | Forwarding port | The port that forwards for a segment toward the root |
| BPDU | STP frame | Bridge Protocol Data Unit; exchanged on every active port (IEEE 802.1D §9.3) |
| BPDU Guard | Access protection | Disables a port that receives a BPDU; prevents rogue switches (IEEE 802.1Q §11.2.6) |
| Root Guard | Uplink protection | Prevents a port from accepting a superior BPDU; protects root election (IEEE 802.1Q §11.2.7) |
| RSTP | Fast STP | 802.1w; proposal-agreement handshake converges sub-second |
| MSTP | Multi-instance STP | 802.1s; groups VLANs into instances; per-instance root election |

## Further Reading

- IEEE 802.1Q-2014 (or later) — Bridges and Bridged Networks (VLAN tagging, TPID, BPDU Guard, Root Guard)
- IEEE 802.1D-2004 — Media Access Control (MAC) Bridges (the STP state machine; superseded by 802.1Q-2014 §13)
- IEEE 802.1w — Rapid Reconfiguration (RSTP, port roles, proposal-agreement)
- IEEE 802.1s — Multiple Spanning Trees (MSTP, instances, mapping)
- Cisco `spanning-tree` command reference (root primary, BPDU Guard, Root Guard)
- FRR `vtysh` configuration manual (BPDU Guard, port-type admin-edge, port-type admin-edge-send-rstp)
