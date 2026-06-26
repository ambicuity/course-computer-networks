# 802.11 architecture: infrastructure vs ad hoc, AP, BSS, ESS, and the distribution system

> 802.11 is not "wireless Ethernet" with the same topology. The forwarding unit is the Basic Service Set (BSS): one Access Point (AP) plus the stations associated to it, sharing one radio cell called the Basic Service Area (BSA). In **infrastructure mode** every client frame is relayed by an AP, and multiple APs are stitched together through a wired **Distribution System (DS)** into an **Extended Service Set (ESS)** so a station can roam between BSSs while keeping its IP. In **ad hoc / IBSS mode** there is no AP at all — clients talk peer-to-peer over a single shared cell. Identities are explicit: a 32-byte **SSID** names the network, a 48-bit **BSSID** (usually the AP's MAC) names a single BSS, and membership is earned through a deterministic **scan -> authenticate -> associate** state machine. The 802.11 protocol stack mirrors the rest of IEEE 802: a fast-evolving **PHY** (legacy 1997 FHSS/DSSS/IR, 1999 802.11a OFDM at 5 GHz, 1999 802.11b DSSS up to 11 Mbps at 2.4 GHz, 2003 802.11g OFDM up to 54 Mbps at 2.4 GHz, 2009 802.11n MIMO up to 600 Mbps), a single **MAC sublayer** built for collision avoidance, and an **LLC sublayer** (IEEE 802.2) above that hides the PHY differences from the network layer.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Ethernet MAC addresses, the 802 framing family, basic radio concepts (ISM bands, OFDM, spread spectrum), CSMA/CA
**Time:** ~75 minutes

## Learning Objectives

- Distinguish infrastructure mode (clients via AP) from ad hoc / IBSS mode (peer-to-peer, no AP), and state the cost of skipping the AP.
- Define AP, BSS, BSA, ESS, DS, SSID, and BSSID, and explain how they fit together to form a roaming-capable wireless network.
- Walk a station through the **scan -> authenticate -> associate** state machine and identify the management frame at each step.
- Trace a frame from a station in BSS-A to a station in BSS-B through two APs and the wired Distribution System, distinguishing intra-BSS from inter-BSS forwarding.
- Lay out the 802.11 protocol stack (PHY + MAC + LLC) and label the five physical layers (legacy, 802.11a, 802.11b, 802.11g, 802.11n) with band, modulation, and peak rate.
- Apply channel-reuse reasoning: explain why adjacent APs in an ESS should be on non-overlapping channels (e.g. 1, 6, 11 in 2.4 GHz) and what happens when they are not.

## The Problem

A field team is being deployed to a building with no cabling and no controller — just five rugged laptops and a stack of USB power packs. The lead engineer asks: "Can 802.11 connect the laptops without us installing an access point first? And if yes, what do we lose compared to the office Wi-Fi we use back at HQ?"

The honest answer is yes, with a name. 802.11 supports an **ad hoc** mode in which stations form an **Independent Basic Service Set (IBSS)** and talk to each other directly over the air, with no AP, no centralized channel arbitration beyond CSMA/CA, and no bridge to a wired network. They sacrifice three things the office Wi-Fi has: a stable forwarding anchor (the AP), a path between cells (the DS), and an enterprise mobility story (the ESS). For a five-laptop site survey, that tradeoff is often fine; for a hospital or a warehouse, it is not. The exercise in this lesson is to map those words — AP, BSS, BSA, ESS, DS, SSID, BSSID, IBSS — onto real topology boxes so the field team can name what they are giving up.

## The Concept

### Infrastructure mode: the AP is the center of the cell

In **infrastructure mode** (Tanenbaum Fig. 4-23a), every wireless client is a **station (STA)** that associates to exactly one **Access Point (AP)**. The AP has two jobs:

1. Be the **forwarding anchor** for the BSS — every frame from a station to a station in the same BSS is sent *to the AP first*, and the AP re-transmits it; no client ever talks directly to another client.
2. Be the **bridge to the wired Distribution System** so traffic can leave the BSS for the rest of the network.

The cell of one AP and its associated stations is the **Basic Service Set (BSS)**, and the geographic region it covers is the **Basic Service Area (BSA)**. The BSSID — a 48-bit identifier that is normally the AP's own MAC address — names *one* BSS; this is what appears in every 802.11 frame's Address 3 field for traffic inside that cell. The user-visible **SSID** ("MyOfficeWiFi") is a 32-byte string that *groups* BSSs together so the station picks the right network name.

### Ad hoc / IBSS mode: no AP, no anchor

In **ad hoc mode** (Tanenbaum Fig. 4-23b), stations discover each other and form an **Independent Basic Service Set (IBSS)** with no AP, no BSSID that is an AP's MAC, and no bridge to a wired network. Each station implements the full 802.11 MAC: it scans for peers, joins the IBSS, and contends for the channel with CSMA/CA. The IBSS is a peer mesh on a single shared channel; everyone hears everyone, and the BSSID is a locally generated random 46-bit value (with the multicast bit set) so it does not collide with any real MAC address.

The cost of skipping the AP is concrete. There is no AP to:

- **buffer traffic for power-save clients**,
- **act as a clock source for timing synchronization (TBTT)**,
- **forward frames between BSSs**,
- **authenticate and account for clients centrally**,
- **shield clients from each other** — in an IBSS, the hidden-terminal problem is back with a vengeance because every station can hear the medium but the medium is unbounded.

This is why Tanenbaum notes that "Internet access is the killer application for wireless" and why ad hoc mode remains a niche tool for site surveys, mesh bootstrap, and direct file transfer apps, not a general-purpose enterprise technology.

### The BSS, the BSA, and the BSSID

The terms are easy to confuse; the table pins them down:

| Term | What it names | Concrete form |
|---|---|---|
| **STA** (station) | One wireless client | A laptop's wireless NIC |
| **AP** (access point) | The cell's bridge and forwarding anchor | The plastic box in the ceiling |
| **BSS** (Basic Service Set) | The set of one AP plus its associated stations | Cell 1, Cell 2, ... |
| **BSA** (Basic Service Area) | The geographic region covered by one BSS | The radio footprint of one AP |
| **BSSID** | The 48-bit identifier of one BSS | Usually the AP's MAC; for an IBSS, a random locally administered value |
| **SSID** | The 32-byte human-readable network name | "MyOfficeWiFi" |
| **ESS** (Extended Service Set) | A chain of BSSs with the same SSID, tied together by a DS | The campus Wi-Fi |
| **DS** (Distribution System) | The wired backbone that links APs | Ethernet, VLAN trunk, or controller fabric |

The **BSA** is just the radio geometry — the area where your station can hear the AP at the data rate it needs. It is not a separate protocol object; it is a physical property of the BSS. BSS and BSA are routinely used interchangeably when people mean "the AP's cell."

### The ESS: chaining BSSes with a Distribution System

When a campus has twenty APs all named "MyOfficeWiFi," a station walking through the building can move from one BSS to another without its IP address changing and without the user touching anything. The thing that makes this work is the **Extended Service Set (ESS)**: a set of BSSs that share the same SSID and are tied together by a **Distribution System (DS)** so that, from the network layer's point of view, the entire ESS is one logical link.

Forwarding within an ESS is the most important picture in 802.11. Take a station `STA1` in BSS1 (served by `AP1`) sending a frame to `STA2` in BSS2 (served by `AP2`):

1. `STA1` transmits the frame on its BSS channel. The destination address is `STA2`'s MAC.
2. **`AP1` receives the frame on the wireless medium.** Every frame in infrastructure mode is sent to the AP, so this happens naturally.
3. `AP1` puts the frame onto the **DS** — the wired Ethernet that connects the APs. The frame crosses `AP1`'s uplink to the switch.
4. The switch (or wireless controller) decides the frame is destined for a station associated to `AP2` and forwards it down `AP2`'s uplink.
5. **`AP2` transmits the frame wirelessly** into BSS2, addressed to `STA2`.
6. `STA2` receives it.

Three distinct forwarding decisions happen: `STA1 -> AP1` (wireless), `AP1 -> AP2` (DS), `AP2 -> STA2` (wireless). If `STA1` and `STA2` were in the same BSS, step 3-4 would collapse into a single AP re-transmit. If `STA1` and `STA2` were on the same BSS, the AP would still be in the path; clients never talk directly to each other in infrastructure mode.

### AP-to-AP handoff: reassociation, not association

A station moving from one BSS to another inside the same ESS performs a **reassociation**, not a fresh association. The state machine is identical to a cold start, but the trigger and the message names are specific:

| Step | State change | Management frame | Direction |
|---|---|---|---|
| 1. Scan | STA listens on each channel for beacons/probes | `Probe Request` / `Probe Response` | STA -> AP (and back) |
| 2. Authenticate | Prove identity (open or shared key) | `Authentication` (algorithm 0 = open) | STA <-> AP |
| 3. Associate (first time) | Join this BSS | `Association Request` / `Response` | STA <-> AP |
| 3'. Reassociate (move) | Move association to a new AP | `Reassociation Request` / `Response` | STA -> new AP (old AP gets told by DS) |

The DS plays a specific role in step 3': the new AP tells the old AP "the station that was yours is now mine" so the old AP can drop buffered frames and update its forwarding table. Without the DS, the old AP would not know to stop sending traffic to the station that has already left.

### The 802.11 protocol stack: PHY, MAC, LLC

The 802 family shares a structural trick: split the data link layer in two. The bottom half — the **MAC sublayer** — handles channel access, addressing, and framing; the top half — the **LLC sublayer**, defined in IEEE 802.2 — provides a small, stable interface to the network layer that hides the differences between Ethernet, Wi-Fi, and the other 802 variants. The 802.11 stack adds a physical layer with several transmission techniques that have been added over time.

```
+-----------------------------------------------+
|              Upper layers (IP, TCP, ...)      |
+-----------------------------------------------+
|  LLC — Logical Link Control  (IEEE 802.2)     |  <- stable across 802.*
+-----------------------------------------------+
|  MAC — Medium Access Control (CSMA/CA, etc.)  |  <- common to 802.11
+-----------------------------------------------+
|  PHY — physical layer                         |
|     legacy 802.11  (1997): FHSS + DSSS + IR   |
|     802.11b (1999): DSSS  1/2/5.5/11 Mbps     |
|     802.11a (1999): OFDM  6..54 Mbps, 5 GHz   |
|     802.11g (2003): OFDM  6..54 Mbps, 2.4 GHz |
|     802.11n (2009): MIMO-OFDM up to 600 Mbps  |
+-----------------------------------------------+
```

**LLC (802.2)** is a thin shim. In modern networks it identifies the protocol that is riding on top of the 802.11 frame (typically IP via the SNAP encapsulation). The MAC is the same across all five physical layers, which is what makes a single NIC able to advertise "802.11 a/b/g/n" — the radio changes, the MAC contract does not.

### The five physical layers

The 1997 base standard shipped **three** physical layers, of which **only one survived**: direct-sequence spread spectrum (DSSS) at 1 or 2 Mbps in the 2.4 GHz ISM band. The other two — frequency-hopping spread spectrum (FHSS) in 2.4 GHz and infrared line-of-sight — are defunct. Real production Wi-Fi starts with what came next.

| PHY | Year | Band | Modulation | Peak rate | Channel width | Notes |
|---|---|---|---|---|---|---|
| legacy DSSS (802.11) | 1997 | 2.4 GHz | DSSS + Barker / CCK | 1, 2 Mbps | 22 MHz | The only surviving base-mode PHY |
| 802.11b | 1999 | 2.4 GHz | DSSS + CCK | 11 Mbps | 22 MHz | The first hit; ~7x range of 802.11a |
| 802.11a | 1999 | 5 GHz | OFDM, 52 subcarriers | 54 Mbps | 20 MHz | Less interference, shorter range |
| 802.11g | 2003 | 2.4 GHz | OFDM (same as .a) | 54 Mbps | 20 MHz | Backwards-compatible with .b |
| 802.11n | 2009 | 2.4 / 5 GHz | MIMO-OFDM (up to 4x4) | 600 Mbps | 20 or 40 MHz | Frame aggregation, wider channels |

Two patterns are worth naming:

- **OFDM (Orthogonal Frequency Division Multiplexing)** is the modulation that scaled Wi-Fi from 11 to 54 to 600 Mbps. It splits one wide channel into 52 (later more) narrow subcarriers sent in parallel, which is robust to multipath. 802.11a and 802.11g use the same OFDM scheme — only the band differs.
- **MIMO** is what 802.11n adds: multiple antennas transmitting multiple spatial streams at the same time on the same channel, separated at the receiver with signal-processing. Combined with 40 MHz channels and frame aggregation, that is what gets 802.11n to 600 Mbps raw.

All five physical layers use the unlicensed **ISM (Industrial, Scientific, Medical) bands** — 2.4 GHz and 5 GHz — and are subject to FCC power limits (1 W max, ~50 mW typical). The unlicensed nature is also why 802.11 has to compete with microwave ovens, cordless phones, and garage door openers in 2.4 GHz; 5 GHz is cleaner but shorter-range, which is the historical reason 802.11b's longer range beat 802.11a's higher speed to market even though 802.11a was standardized first.

### Rate adaptation and channel reuse

Two PHY-level realities complete the architecture picture. The first is **rate adaptation**: every 802.11 PHY defines multiple rates (802.11b: 1, 2, 5.5, 11; 802.11a/g: 6, 9, 12, 18, 24, 36, 48, 54; 802.11n: 6.5 to 600). The standard does *not* say how to pick one; the NIC chooses based on its own signal-quality measurements, backing off from 54 to 6 Mbps as the signal degrades. The 10x spread between the highest and lowest rate is why "good rate adaptation" is the difference between a usable and a useless cell edge.

The second is **channel reuse**. In 2.4 GHz, 802.11g has three non-overlapping 22 MHz channels in most regulatory domains: **1, 6, 11**. Two APs in the same ESS placed on the same channel will hear each other and share capacity; on channel 1 and channel 6 they will not. The classic three-cell layout of a campus Wi-Fi plan puts adjacent APs on 1, 6, 11 in a hexagonal pattern so that any station hears at most two APs and the airtime is reused spatially. Get this wrong and the cell edge is jammed by co-channel interference from your own ESS; get it right and you can pack 30+ APs into one building and the throughput scales.

The MAC sublayer is built around the same problem: collision avoidance (CSMA/CA) plus RTS/CTS instead of collision detection, because radios are half-duplex and a station cannot hear a collision while transmitting. That is the topic of later lessons; for this lesson, the takeaway is that the architecture is what makes the radio reuse story even possible.

## Build It

The deliverable is `code/main.py`, a stdlib-only Python module that builds a small Wi-Fi topology and walks through the three things this lesson explains — association state, ESS forwarding, and channel reuse.

1. **Open `code/main.py`**. Find the `@dataclass` definitions for `BSS`, `AccessPoint`, `Station`, and `Channel`. The classes are immutable (`frozen=True`) so topology changes are modeled as new objects, mirroring how a station "leaves" one BSS and "joins" another.
2. **Run the `associate_to_ap` state machine demo.** A station goes `UNAUTHENTICATED -> AUTHENTICATED -> ASSOCIATED` by issuing a `Probe Request`, an `Authentication` (open system, algorithm 0), and an `Association Request`. Each step prints the management frame and verifies the next state is reachable.
3. **Run the ESS routing demo.** Build a topology with `BSS1` (AP1, channel 1) and `BSS2` (AP2, channel 6) wired through a `DistributionSystem`. Send a unicast frame from `STA1` (in BSS1) to `STA2` (in BSS2) and watch the trace: `STA1 -> AP1 -> DS -> AP2 -> STA2`. The `DsRouter` class encapsulates the lookup.
4. **Run the IBSS demo.** Build a 3-station IBSS with no AP and watch frames flow peer-to-peer. Note that there is no DS path and the BSSID is a locally generated random 46-bit value with the multicast bit set.
5. **Run the channel-reuse check.** A `ChannelOverlap` function decides whether two (channel, band) pairs are non-overlapping. Use it to lay out three APs on channels 1, 6, 11 and confirm they are co-channel-free. Then try channel 1 vs channel 3 and see the overlap.

Run it with `python3 code/main.py`. The `__main__` block runs all four demos in sequence with labeled headers.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Decide whether to deploy IBSS or infra | A topology sketch with one AP, one DS, multiple BSSs | You name the mode by looking at the BSSID and the presence of an AP |
| Name a BSS vs an ESS | The diagram | One AP = one BSS; multiple APs sharing the same SSID and linked by a DS = one ESS |
| Walk a station through association | Trace of `Probe -> Auth -> Assoc` frames | The STA moves `UNAUTHENTICATED -> AUTHENTICATED -> ASSOCIATED` and the AP records the BSSID |
| Trace inter-BSS forwarding | Frame log on STA1, AP1, DS, AP2, STA2 | You can list the four forwarding hops and explain why the AP is always in the path |
| Plan channels for a 3-cell floor | `ChannelOverlap` result | Adjacent APs land on 1, 6, 11 and `co_channel_interferes` returns False |
| Read a packet capture | Wireshark trace | You identify management vs data frames, the BSSID, and whether a frame is a reassociation |

Wireshark filters: `wlan.fc.type_subtype == 0x00` (association request), `wlan.fc.type_subtype == 0x02` (reassociation request), `wlan.fc.type_subtype == 0x08` (beacon), `wlan.fc.type_subtype == 0x0b` (authentication), `wlan.bssid == aa:bb:cc:dd:ee:ff`.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **BSS/ESS topology diagram** (the SVG in `assets/`) showing two APs in the same ESS, three STAs in BSS1 and two in BSS2, the wired DS between them, and the per-BSS channel.
- A **state-machine cheat sheet** mapping the four association states (`UNAUTHENTICATED`, `AUTHENTICATED`, `ASSOCIATED`, `REASSOCIATED`) to the management frame that moves you out of each one.
- A **channel-plan worksheet** for 2.4 GHz: 1, 6, 11, and the rule that any pair of these three is non-overlapping.
- The **`code/main.py` script** wired to the diagram so you can re-run the four demos against your own ESS layout.

Start from `outputs/prompt-80211-architecture-protocol-stack.md` if it exists, otherwise create `outputs/80211-architecture-state-machine.md`.

## Exercises

1. The field team asks "can the laptops talk if we don't deploy an AP?" Answer in protocol terms, name the mode (BSS type, no AP), and list three things the office Wi-Fi gives them that ad hoc does not.
2. Draw a topology with one AP, one BSS, one BSA, two stations. Then add a second AP with the same SSID, joined to the first by an Ethernet DS, and explain the topology in terms of BSS, ESS, and DS.
3. `STA1` is in BSS1 (AP1) and `STA2` is in BSS2 (AP2) in the same ESS. List the four forwarding hops for a unicast frame from `STA1` to `STA2`, and identify which hops are on the wireless medium and which are on the DS.
4. A station walks from BSS1 to BSS2 inside the same ESS. Which 802.11 management frame does it send to AP2, and which one does AP2 send (or trigger) to AP1? What does AP1 do with that message?
5. A campus Wi-Fi plan puts adjacent APs on channel 1, channel 1, and channel 6. Identify the co-channel interference problem, and rewrite the plan to use the non-overlapping 2.4 GHz channels 1, 6, 11.
6. Match each physical layer to its year, band, modulation, and peak rate: legacy DSSS, 802.11a, 802.11b, 802.11g, 802.11n. Which of these is OFDM? Which one survives from the 1997 base standard?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Station (STA) | "Wi-Fi client" | A wireless device that joins a BSS through association |
| Access Point (AP) | "the cell" | The bridge between the wireless medium and the wired DS; the center of a BSS |
| Basic Service Set (BSS) | "the cell" | One AP and the stations currently associated to it; identified by the BSSID |
| Basic Service Area (BSA) | "the radio footprint" | The geographic region covered by one BSS |
| BSSID | "the cell's MAC" | A 48-bit identifier of one BSS, usually the AP's MAC; for an IBSS, a random value |
| SSID | "the network name" | A 32-byte human-readable string that groups BSSs into an ESS |
| Independent BSS (IBSS) | "ad hoc mode" | A peer-to-peer BSS with no AP; stations contend with CSMA/CA directly |
| Extended Service Set (ESS) | "campus Wi-Fi" | Multiple BSSs with the same SSID joined by a DS, forming one logical wireless service |
| Distribution System (DS) | "the backhaul" | The wired (or wired-like) network that links APs and carries inter-BSS traffic |
| Reassociation | "roaming" | The 802.11 management frame that moves a station's association to a new AP |
| LLC (802.2) | "the glue layer" | A thin shim above the MAC that presents a uniform interface to the network layer |
| OFDM | "the fast modulation" | A multi-subcarrier modulation that 802.11a, 802.11g, and 802.11n all use |
| MIMO | "multiple antennas" | Sending multiple spatial streams on the same channel, separated at the receiver |
| ISM band | "the free band" | The unlicensed 2.4 GHz and 5 GHz bands Wi-Fi shares with microwaves and cordless phones |

## Further Reading

- **IEEE Std 802.11-2007** (and the current 802.11-2020 rollup) — authoritative definitions of BSS, ESS, DS, association, reassociation, and the PHY evolution.
- Matthew Gast, *802.11 Wireless Networks: The Definitive Guide* (O'Reilly) — the practitioner reference for architecture, roaming, and capture analysis.
- Andrew Tanenbaum & David Wetherall, *Computer Networks* (5th ed.), §4.4 "Wireless LANs" — the source of Fig. 4-23 and 4-24.
- Halperin, Hu, Shukla, Weldon, et al. (2010), "Predictable 802.11 Packet Delivery from Wireless Channel Measurements," *SIGCOMM* — a real-world study of rate adaptation and MIMO.
- **RFC 1042** — IP over IEEE 802 networks, including the LLC/SNAP encapsulation that rides on top of 802.11.
