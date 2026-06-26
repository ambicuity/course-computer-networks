# Link-Layer Failure Modes

> The data link layer is where bits become frames, and where the most confusing outages originate because the symptoms surface three layers up. This lesson catalogs the canonical Ethernet/802.3 and 802.1 failure modes: FCS (CRC-32) errors from duplex mismatch, runts (<64 bytes) and giants (>1518/1522 bytes), late collisions past the 512-bit slot time, MAC flapping from L2 loops, broadcast storms when STP (802.1D / RSTP 802.1w) fails to converge, and MTU/jumbo-frame black holes. You will learn to read interface counters (`InErrors`, `CRCAlignErrors`, `Collisions`, `Discards`), match them to Wireshark evidence (`eth.fcs.status == "Bad"`, `eth.len < 60`), and reason about the 802.3 frame layout — 7-byte preamble, 1-byte SFD (0xAB), 6+6 MAC addresses, 2-byte EtherType, 46–1500 payload, 4-byte FCS. The included parser computes CRC-32 over real frame bytes and classifies each failure deterministically. RFC 894 defines IPv4-over-Ethernet framing; IEEE 802.3 defines the MAC; IEEE 802.1D/802.1w define the spanning tree that prevents the loops behind most L2 storms.

**Type:** Build
**Languages:** Wireshark, runbooks, Python (stdlib frame parser)
**Prerequisites:** Phase 3 lessons on Ethernet framing, MAC addressing, and switching; basic CRC concepts
**Time:** ~90 minutes

## Learning Objectives

- Classify a captured Ethernet frame as **good, runt, giant, FCS-bad, or jabber** using its byte length and a recomputed CRC-32, and explain which physical/config fault each implies.
- Map four interface counters (`CRCAlignErrors`, `Collisions`, `LateCollisions`, `InDiscards`) to specific root causes (duplex mismatch, half-duplex saturation, cabling distance, MTU mismatch).
- Distinguish a **late collision** from a normal collision using the 512-bit (64-byte) slot time and explain why late collisions are never normal on a correct CSMA/CD segment.
- Diagnose a **broadcast storm / MAC flap** from a CAM table and STP topology, and state the RSTP timer that governs recovery.
- Identify an **MTU black hole** where small frames pass but 1500+ byte frames silently drop, and write the smallest test that proves it.
- Build a runbook that turns a vague "the network is slow" ticket into layer-2 evidence.

## The Problem

A user reports that file transfers "stall" and SSH sessions "freeze and recover" on a specific switch port, but ping works and the speed test looks fine. The application team blames the server. The server team blames the network. Nobody has looked at layer 2.

When you finally check `show interface`, the port has `Speed: 100Mb/s, Full-duplex` configured but is logging a slow trickle of `input errors`, `CRC`, and `frame` counters that climb only under load. Across the link, the other device auto-negotiated to **half duplex**. That single mismatch produces FCS errors and late collisions that TCP papers over with retransmissions — which is exactly why it shows up as "slow" and "stalls," not "down." The job of this lesson is to make that invisible failure *visible* as counters and frame evidence, then to give you a repeatable procedure so the next ticket takes five minutes instead of five hours.

## The Concept

### The 802.3 frame and where each failure lives

Every diagnosis starts from the frame layout. The `assets/link-layer-failure-modes.svg` diagram shows it to scale; here it is in fields:

| Field | Bytes | Notes |
|---|---|---|
| Preamble | 7 | `0x55` repeated; clock sync, stripped by NIC |
| SFD (Start Frame Delimiter) | 1 | `0xAB` (`10101011`); marks frame start |
| Destination MAC | 6 | `ff:ff:ff:ff:ff:ff` = broadcast; bit 0 of first octet = multicast |
| Source MAC | 6 | always unicast (bit 0 = 0) on a valid frame |
| EtherType / Length | 2 | ≥ `0x0600` (1536) = type (e.g. `0x0800` IPv4, `0x0806` ARP, `0x8100` 802.1Q); ≤ 1500 = length |
| Payload | 46–1500 | padded to 46 minimum; 1500 = standard MTU |
| FCS (CRC-32) | 4 | covers DST..payload; polynomial `0x04C11DB7` |

The **minimum on-wire frame is 64 bytes** (DST 6 + SRC 6 + Type 2 + payload 46 + FCS 4). The standard **maximum is 1518 bytes** (1522 with an 802.1Q VLAN tag). These two numbers — 64 and 1518/1522 — define the boundaries that separate the failure classes below.

### Failure class 1 — FCS / CRC errors (the duplex-mismatch fingerprint)

The FCS is a 32-bit CRC computed by the sender over the frame; the receiver recomputes it and compares. A mismatch means the bits changed in transit. In Wireshark the filter is `eth.fcs.status == "Bad"`. The dominant causes:

- **Duplex mismatch.** Full-duplex on one end, half on the other. The half-duplex side runs CSMA/CD and aborts frames it thinks collided; the full-duplex side transmits while receiving, corrupting frames. Symptom: CRC errors that rise *with traffic load*, plus late collisions on the half-duplex side.
- **Bad cabling / EMI / failing transceiver.** CRC errors that rise with cable length, temperature, or vibration, independent of load.

`code/main.py` recomputes CRC-32 over the frame bytes (excluding the trailing FCS) and reports `FCS OK` vs `FCS BAD`, demonstrating exactly what the receiver hardware does.

### Failure class 2 — runts, giants, and jabber (length faults)

| Class | On-wire length | Wireshark hint | Typical cause |
|---|---|---|---|
| **Runt** | < 64 bytes | `eth.len < 60` (post-FCS-strip) | Collision fragment, bad NIC, duplex mismatch |
| **Good** | 64–1518 (1522 tagged) | — | Normal |
| **Giant / baby giant** | > 1518 (untagged) | oversized frame | Jumbo frame on non-jumbo port, VLAN tag confusion |
| **Jabber** | > 1518 *and* FCS-bad | continuous garbage | Stuck transmitter / failed PHY |

A **runt** is a frame that ended before reaching 64 bytes. On a half-duplex segment, a runt is the debris of a collision detected within the slot time — that is *normal* on a busy half-duplex link but should be *zero* on full duplex. A **giant** that appears only between two specific hosts usually means one side enabled jumbo frames (MTU 9000) and the path or peer did not. **Jabber** is a hardware fault: a NIC whose transmitter never stops, flooding the segment with oversized, CRC-bad frames.

### Failure class 3 — collisions and the 512-bit slot time

CSMA/CD only operates on half-duplex segments. The **slot time** is 512 bit-times (64 bytes at 10/100 Mb/s). Within that window, a transmitting station can still detect a collision and abort — this is a **normal collision**.

A **late collision** is a collision detected *after* the first 512 bits have been sent. It is **never normal**. Its causes are mechanical:

- **Duplex mismatch** (the most common): the full-duplex side sends mid-frame.
- **Cable too long**: round-trip propagation exceeds the slot time, so the collision signal arrives after the station has committed to the frame. The 100 Mb/s collision domain diameter limit (~100 m / one repeater) exists precisely to keep round-trip < slot time.

Decision rule:

```text
Collisions > 0  and  duplex == full   -> ALWAYS a fault (full duplex has no collisions)
LateCollisions > 0                     -> duplex mismatch OR segment too long
Collisions high  and  duplex == half   -> congestion; check utilization, not a fault per se
```

### Failure class 4 — L2 loops, MAC flapping, and broadcast storms

A switch learns source MACs into its CAM (forwarding) table and floods unknown-unicast and broadcast frames out all ports. If two switches are connected by two active paths and **STP is not blocking one of them**, a single broadcast frame circulates forever, multiplying at each switch — a **broadcast storm**. CPU and links saturate within seconds; the whole VLAN goes dark.

The fingerprint in logs is **MAC flapping**: the same source MAC appears on port Gi1/0/1, then Gi1/0/2, then back, because the looped copies arrive from both directions:

```text
%MAC_FLAP: Host aa:bb:cc:00:11:22 moving between Gi1/0/1 and Gi1/0/2
```

Prevention and recovery live in spanning tree:

| Protocol | Standard | Convergence (default) |
|---|---|---|
| STP | IEEE 802.1D | ~30–50 s (15 s listening + 15 s learning + 20 s max-age) |
| RSTP | IEEE 802.1w | typically < 1 s on point-to-point edge |
| MSTP | IEEE 802.1s | per-instance, RSTP-speed |

`code/main.py` includes a tiny CAM-flap detector: feed it `(mac, port, time)` observations and it flags any MAC that changes port more than a threshold within a window — the same logic a switch uses to raise the flap alarm.

### Failure class 5 — MTU / jumbo-frame black holes

This one is insidious because *small packets work*. The path MTU is the smallest link MTU end to end. If a host sends a 1500-byte frame across a link configured for a smaller MTU (or sends a 9000-byte jumbo onto a 1500-byte path) and the **Don't Fragment** bit is set, the frame is silently dropped. Symptoms:

- `ping host` works (56-byte payload).
- `ping -M do -s 1472 host` works (1472 + 28 = exactly 1500).
- `ping -M do -s 1473 host` fails — the black-hole boundary, one byte over.
- SSH connects (small) but `scp` hangs at "0%" (full-size data segments).

The smallest decisive test is the DF-bit ping sweep across the 1472/1473 boundary. The fix is to align MTU on every interface in the path or to allow ICMP `Fragmentation Needed` (Type 3, Code 4) through so PMTUD works.

### Reading the counters

These are the interface counters that turn frame-level theory into a one-command diagnosis:

| Counter | Rises when | Most likely L2 cause |
|---|---|---|
| `CRCAlignErrors` / `InErrors` (CRC) | bits corrupted in transit | duplex mismatch, bad cable, dying transceiver |
| `Runts` | frames < 64 bytes | collisions, duplex mismatch |
| `Giants` | frames > 1518 bytes | MTU/jumbo mismatch, tag confusion |
| `Collisions` | half-duplex contention | congestion (half) — but **fault if full** |
| `LateCollisions` | collision after 512 bits | duplex mismatch, segment too long |
| `InDiscards` (no error) | buffer/MTU drops | oversubscription, MTU black hole |

## Build It

1. Read `code/main.py`. It contains a real 802.3 frame parser, a stdlib CRC-32 implementation, and three classifiers (length, collision, CAM-flap).
2. Run it: `python3 code/main.py`. It parses a set of hand-built frames — one good, one runt, one giant, one with a corrupted byte (FCS bad) — and prints the classification with the recomputed CRC.
3. Confirm the CRC logic: flip any single byte in the `GOOD_FRAME` hex string and re-run. The frame must now classify as `FCS BAD`. This is exactly what receiver hardware does.
4. Feed the CAM-flap detector the sample MAC/port observations and watch it raise a flap alarm on the looped MAC.
5. In Wireshark (or `tshark`), apply `eth.fcs.status == "Bad" || eth.len < 60` to a capture and confirm the parser's verdict matches Wireshark's.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm duplex mismatch | `show interface` shows full-duplex; CRC + late collisions rise with load | You can name the half-duplex side and predict the late-collision counter |
| Classify a captured frame | Frame byte length + recomputed CRC-32 | `code/main.py` and Wireshark agree on good/runt/giant/FCS-bad |
| Detect an L2 loop | CAM/MAC-flap log; broadcast counter spiking; CPU high | You identify the unblocked redundant link STP should have blocked |
| Prove an MTU black hole | DF-bit ping sweep across 1472/1473 | 1472 passes, 1473 fails; you name the path interface with the small MTU |
| Rule out the application | L2 counters clean, frames all good | You can show the corruption/loss is *not* at layer 2 and hand off cleanly |

## Ship It

Create one artifact under `outputs/`:

- A **link-layer failure runbook** that maps each symptom ("slow," "stalls," "VLAN down") to the counter to check, the Wireshark filter to apply, and the fix.
- The frame-classification table as a printable cheat sheet (64 / 1518 / 1522 boundaries, slot time, CRC filter).

Start with [`outputs/prompt-link-layer-failure-modes.md`](../outputs/prompt-link-layer-failure-modes.md) and the classifier in `code/main.py`.

## Exercises

1. A 1 Gb/s port configured full-duplex logs a steady 0.2% CRC error rate that **does not change** when you reduce traffic. Duplex mismatch produces load-dependent errors. What is your top hypothesis instead, and what single hardware swap tests it?
2. `show interface Gi1/0/3` reports `Collisions: 4127, Late collisions: 311, Duplex: full`. Explain why *any* collision on a full-duplex port is impossible under correct operation, and give the two faults that produce late collisions.
3. You capture frames between Host A (MTU 9000, jumbo) and Host B. `ping` works but `scp` hangs. Write the exact `ping -M do -s <N>` command that finds the black-hole boundary, and state what N tells you about the path MTU.
4. A switch logs `MAC_FLAP` for one server MAC oscillating between two ports every few seconds, and the VLAN's broadcast counter is climbing 10x per second. Name the failure, the likely cause, and the STP standard whose blocked port should have prevented it.
5. Given a 76-byte frame whose recomputed CRC-32 does **not** match the trailing 4 bytes, classify it (good / runt / giant / FCS-bad) and list two physical causes consistent with that classification.
6. Extend `code/main.py`: add a `is_jabber()` check that returns true only when a frame is **both** > 1518 bytes **and** FCS-bad, and explain why both conditions are required to distinguish jabber from a legitimate baby-giant.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| FCS | "the checksum at the end" | 32-bit CRC over DST..payload using polynomial `0x04C11DB7`; receiver recomputes and drops on mismatch |
| Runt | "a small packet" | A frame that ended before the 64-byte minimum — collision debris or a faulty sender, not just "small" |
| Giant | "a big packet" | A frame over 1518 (untagged) / 1522 (802.1Q) bytes — usually an MTU/jumbo mismatch |
| Late collision | "a collision" | A collision detected *after* the 512-bit slot time — never normal; signals duplex mismatch or an oversized segment |
| Slot time | "collision timing" | 512 bit-times (64 bytes); the window in which CSMA/CD can still abort a frame |
| Duplex mismatch | "a speed problem" | One end full-duplex, one half — produces load-dependent CRC errors and late collisions, *not* a link-down |
| MAC flap | "the switch is confused" | The same source MAC appearing on multiple ports — the signature of an L2 loop |
| Broadcast storm | "the network is flooded" | Broadcast/unknown-unicast frames circulating a loop and multiplying, saturating the VLAN |
| MTU black hole | "scp is broken" | DF-set frames above the path MTU silently dropped; small packets pass, full-size ones vanish |

## Further Reading

- **IEEE 802.3** — Ethernet MAC and physical layer: frame format, slot time, CSMA/CD, collision domain limits.
- **IEEE 802.1D** (Spanning Tree) and **IEEE 802.1w** (Rapid STP) — loop prevention and convergence timing.
- **IEEE 802.1Q** — VLAN tagging; the 4-byte tag that pushes the max frame to 1522 bytes.
- **RFC 894** — A Standard for the Transmission of IP Datagrams over Ethernet Networks (EtherType `0x0800`).
- **RFC 1191** — Path MTU Discovery (the DF bit and ICMP Type 3 Code 4 mechanism behind black holes).
- **RFC 826** — Address Resolution Protocol (ARP, EtherType `0x0806`).
- Tanenbaum & Wetherall, *Computer Networks*, Chapter 4 (The Medium Access Control Sublayer) — CSMA/CD, Ethernet, and bridging.
- Wireshark display-filter reference: `eth.fcs.status`, `eth.len`, `eth.dst`, `vlan.id`.
