# Local Area Networks to Wide Area Networks

> Networks are classified by physical scale: a PAN spans ~1 m, a LAN spans a building (~100 m–1 km), a MAN spans a city (~10 km), and a WAN spans a country or continent (100–10,000 km). A LAN like switched Ethernet (IEEE 802.3) carries frames addressed by 48-bit MAC addresses (e.g. `00:1A:2B:3C:4D:5E`), forwarded by switches that learn ports from source addresses and flood unknown destinations; the maximum payload of a standard Ethernet frame is 1500 bytes. Wireless LANs use IEEE 802.11 (Wi-Fi); MANs include IEEE 802.16 (WiMAX) and DOCSIS cable. A WAN's communication subnet is built from leased transmission lines plus routers (switching elements) that pick an outgoing line per packet. Because routers join different technologies — switched Ethernet inside an office, SONET on the long haul — most WANs are really internetworks. Two key WAN variants replace dedicated leased lines: a VPN tunnels office-to-office traffic over the public Internet, and an ISP network is a subnet operated by a third party. The defining LAN property is a bounded, known worst-case propagation delay; WANs trade that bound away for reach. Common failure modes: a switching loop with no spanning tree melts a LAN with broadcast storms; a VPN inherits the variable latency and loss of the underlying Internet path.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 lessons on network uses and the protocol-stack idea; comfort reading a frame/packet field layout
**Time:** ~75 minutes

## Learning Objectives

- Classify a given deployment as PAN / LAN / MAN / WAN from its interprocessor distance and ownership model, and name the dominant standard for each (802.15.1, 802.3/802.11, 802.16, leased-line + routers).
- Trace how a switched-Ethernet LAN forwards a frame: source-MAC learning, the forwarding table, unicast forward vs. flood, and why a loop without spanning tree causes a broadcast storm.
- Distinguish a switch (Layer-2, MAC addresses, single broadcast domain) from a router (Layer-3, joins different network technologies, the WAN switching element).
- Explain why a WAN is usually an internetwork, and contrast a dedicated leased-line WAN, a VPN over the Internet, and an ISP-provided subnet on cost, control, and failure behavior.
- Identify the observable evidence — MAC tables, frame counters, VLAN tags, traceroute hops, latency/jitter — that confirms which scale and topology you are actually looking at.

## The Problem

A finance analyst reports that "the network is down" from the third floor. You look closer: their laptop has a valid IP, can ping the default gateway, can reach the file server in the same building, but cannot reach the ERP system hosted in the Brisbane office. Meanwhile a colleague two desks away — on a different VLAN — has no trouble at all.

Nothing here is a single "network." The laptop sits on a **switched Ethernet LAN**, segmented into VLANs. The path to the file server stays inside that LAN (Layer-2 frames, microsecond delay, bounded). The path to Brisbane leaves the building, crosses a **WAN** built from a router and a leased line or a VPN tunnel — a completely different scale with different ownership, different delay characteristics, and a different failure surface. To diagnose this you must first classify each segment by scale and decide which mechanism owns the symptom. That classification — LAN vs. MAN vs. WAN, switch vs. router, leased line vs. VPN — is the subject of this lesson.

## The Concept

Networks are organized by physical scale because different technologies dominate at different distances. The textbook classification (Tanenbaum, *Computer Networks*, Fig. 1-6) maps distance to network type:

### Classification by scale

| Interprocessor distance | Processors located in | Network type | Dominant standard |
|---|---|---|---|
| 1 m | Square meter (one person) | PAN (Personal Area Network) | Bluetooth (IEEE 802.15.1), RFID |
| 10 m – 1 km | Room / building / campus | LAN (Local Area Network) | Ethernet (IEEE 802.3), Wi-Fi (IEEE 802.11) |
| 10 km | City | MAN (Metropolitan Area Network) | Cable/DOCSIS, WiMAX (IEEE 802.16) |
| 100 – 1000 km | Country / continent | WAN (Wide Area Network) | Leased lines + routers, SONET, MPLS |
| 10,000 km | Planet | The Internet (an internetwork) | IP over everything |

The single most important *property* that changes with scale is the worst-case transmission/propagation time. A LAN is restricted in size, so the worst-case delay is **bounded and known in advance** — this is what lets LAN protocols make timing assumptions (collision windows, ARP timeouts). A WAN gives that bound up in exchange for reach. The SVG (`assets/local-area-networks-to-wide-area-networks.svg`) shows this progression with the building → city → continent boundaries and where switches give way to routers.

### Inside the LAN: switched Ethernet

Most wired LANs today are **switched Ethernet (IEEE 802.3)**. Each host connects to a *switch* by a point-to-point link; the switch relays frames using the destination address in each frame. A switch has multiple ports, each able to connect one host. The Ethernet frame fields the switch reads:

```
 7 bytes  1     6 bytes   6 bytes   2     46–1500 bytes   4
+--------+---+----------+----------+-----+--------------+-----+
|Preamble|SFD| Dst MAC  | Src MAC  |Type |   Payload    | FCS |
+--------+---+----------+----------+-----+--------------+-----+
                ^ used to forward   ^ used to LEARN
```

A switch is self-learning. The forwarding logic is small but exact:

1. Read **Src MAC** of an arriving frame → record `(Src MAC → arrival port)` in the forwarding table with a timestamp (default aging time 300 s).
2. Look up **Dst MAC** in the table.
   - **Hit** → forward only out the recorded port (unicast forward).
   - **Miss** (or broadcast `FF:FF:FF:FF:FF:FF`) → **flood**: send out every port except the one it arrived on.

`code/main.py` implements exactly this learning switch plus a frame parser, so you can watch the table populate and see when a frame is flooded vs. forwarded.

### Why loops are fatal: broadcast storms

To build a larger LAN you plug switches into each other. If two switches are wired in a loop with **no spanning-tree protocol (IEEE 802.1D / STP)** running, a single broadcast (or unknown-unicast) frame is flooded around the loop, re-flooded by each switch, and never decremented — Ethernet has no TTL field. The frame count grows without bound: a **broadcast storm** that saturates every link in milliseconds and takes the LAN down. The fix, STP, deliberately blocks redundant ports to leave a loop-free tree. The symptom an engineer sees: CPU on all switches pinned to 100%, link-utilization counters slammed at line rate, MAC tables flapping as the same source address appears on multiple ports.

### VLANs: one physical LAN, many logical LANs

A single physical LAN can be split into logical LANs when the wiring does not match the org chart — e.g. engineering and finance share a building wing but should be isolated. With **VLANs (IEEE 802.1Q)** each switch port is tagged with a "color." The switch inserts a 4-byte 802.1Q tag carrying a 12-bit VLAN ID (so 1–4094 usable VLANs) and forwards only among ports of the same color. A broadcast on the red (finance) VLAN never reaches a green (engineering) port — two logical LANs on one switch. In the opening scenario, the colleague who "had no trouble" was simply on a VLAN whose gateway and path were healthy.

### MAN: the city-scale middle

A **MAN** covers a city. The classic example is the cable-TV network repurposed for two-way Internet: TV and Internet signals are fed into a centralized **headend** and distributed to homes, with upstream traffic in unused spectrum (this is DOCSIS over coax). The other MAN is **WiMAX (IEEE 802.16)**, high-speed wireless metro access. The MAN sits between LAN and WAN both in distance (~10 km) and in ownership — typically one operator wires the whole city.

### WAN: the subnet of lines and routers

A **WAN** spans a country or continent. Hosts (machines running user programs) connect to a **communication subnet** whose only job is to carry messages host-to-host. The subnet has two component types:

- **Transmission lines** move bits (copper, optical fiber, or radio). Companies rarely own long-haul cable, so they **lease** lines from a carrier.
- **Switching elements** — now universally called **routers** — connect two or more transmission lines. When data arrive on an incoming line, the router chooses an outgoing line.

Three properties separate a WAN from "just a big LAN":

1. **Different owners.** Hosts and subnet are typically operated by different organizations (your IT dept owns the LAN; a carrier owns the long-haul lines).
2. **Mixed technologies.** A router joins switched Ethernet inside the office to a SONET or MPLS link on the long haul. Because it bridges *different* network types, the WAN is really an **internetwork** — a composite of more than one network.
3. **What attaches.** A WAN may connect individual hosts or whole LANs; from the subnet's view the job is identical.

### Two WAN variants: VPN and ISP network

Instead of leasing dedicated lines, two common arrangements appear:

| Arrangement | How offices connect | Advantage | Disadvantage / failure mode |
|---|---|---|---|
| Dedicated leased line | Carrier-provisioned point-to-point circuit per office pair | Known, guaranteed capacity; predictable delay | Expensive; rigid — adding the 4th office means new circuits |
| **VPN (Virtual Private Network)** | Encrypted virtual links *over the public Internet* | Flexible reuse of one Internet connection; trivially add the 4th office | No control over the underlying path — latency, jitter, and loss vary with your ISP |
| **ISP network** | A subnet *run by a third party*, which also connects to the rest of the Internet | You buy connectivity instead of building it; reach the whole Internet | You depend on the provider's routing and SLA |

A VPN's defining trait is virtualization: the office-to-office "line" is virtual, so it inherits the underlying Internet's behavior. When the opening scenario's Brisbane path is a VPN, an upstream Internet congestion event — not your LAN — explains the reachability problem. The evidence is in `traceroute`: extra hops, rising RTT, and loss appearing only beyond your border router.

## Build It

`code/main.py` ties the concepts to runnable code. Work through it in this order:

1. **Classify by scale.** Call `classify_by_distance()` with metres (1, 100, 10_000, 5_000_000) and confirm you get PAN / LAN / MAN / WAN with the right standard.
2. **Parse a frame.** Feed a hex Ethernet frame to `parse_ethernet_frame()` and read back the dst/src MAC, EtherType, and payload length; confirm a broadcast destination is detected.
3. **Run the learning switch.** Build a `Switch`, deliver a sequence of `(src, dst, in_port)` frames, and watch each one logged as **FLOOD** (table miss) or **FORWARD port N** (hit). Inspect the final MAC table and its aging timestamps.
4. **Simulate a loop.** Enable the loop scenario and watch the broadcast frame count climb — the broadcast-storm signature — then re-run with the spanning-tree block in place and see it stop.
5. **Compare WAN options.** Call `compare_wan_options()` to print the leased-line vs. VPN vs. ISP trade-off table with worked latency numbers.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify a segment's scale | Interprocessor distance, ownership, dominant standard | You name PAN/LAN/MAN/WAN *and* the IEEE standard, not just "it's a network" |
| Confirm Layer-2 forwarding | Switch MAC/forwarding table; flood vs. unicast counters | The destination MAC has a table entry on the expected port; no unexplained flooding |
| Detect a switching loop | Broadcast-frame rate, switch CPU, MAC-table flapping | Storm signature is present and STP/802.1D state explains which port is blocked |
| Separate LAN symptom from WAN symptom | Ping to local gateway vs. traceroute to remote office | Local LAN is clean; added latency/loss starts beyond the border router |
| Pick a WAN arrangement | Cost, control, and SLA requirements | Choice (leased / VPN / ISP) is justified by the control-vs-flexibility trade-off |

## Ship It

Create one artifact under `outputs/`:

- A scale-classification + topology decision card (PAN→WAN with standards and the switch-vs-router rule).
- A LAN broadcast-storm runbook: storm signature, STP check, port to disable.
- A LAN→WAN annotated diagram derived from `assets/local-area-networks-to-wide-area-networks.svg`.
- The learning-switch / WAN-comparison script in `code/main.py`, extended with your own frame trace.

Start from [`outputs/prompt-local-area-networks-to-wide-area-networks.md`](../outputs/prompt-local-area-networks-to-wide-area-networks.md).

## Exercises

1. A campus deployment connects buildings 800 m apart with fiber, all under one IT department, running switched Ethernet at 10 Gbps. Classify it (LAN/MAN/WAN) and justify using *both* distance and ownership. Then explain why the same fiber run, if leased from a carrier across a 40 km metro ring, would change the classification.
2. Using `code/main.py`, deliver this frame sequence to a fresh 4-port switch: `(A→B, port1)`, `(B→A, port2)`, `(A→B, port1)`. State exactly which of the three frames is flooded and which is unicast-forwarded, and why.
3. Two access switches are cross-connected with two cables and STP is disabled. Predict the broadcast-frame count after a single ARP broadcast and describe the three counters you would watch to confirm a storm. What single 802.1D action stops it?
4. The opening scenario's Brisbane path is a VPN over the Internet. The local LAN tests all pass. Write the exact ping/traceroute evidence that would let you blame the underlying ISP path rather than your own subnet.
5. Finance and engineering share a switch but must be isolated. Assign VLAN IDs, describe the 802.1Q tag inserted, and prove that a finance broadcast cannot reach an engineering port. How many usable VLAN IDs does the 12-bit field allow?
6. Your company has three offices and wants to add a fourth next quarter. Compare a dedicated-leased-line WAN with a VPN for this growth, citing the specific cost-vs-control trade-off and one failure mode unique to each.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| LAN | "the office network" | Privately owned, building-scale network with a *bounded, known* worst-case delay; usually switched Ethernet (802.3) or Wi-Fi (802.11) |
| Switch | "the box with ports" | A Layer-2 device that *learns* `MAC→port` from source addresses and forwards frames; floods on a table miss; one broadcast domain |
| Router | "the internet box" | A Layer-3 switching element that joins *different* network technologies and picks an outgoing line per packet; the WAN's core component |
| Broadcast storm | "the network is slow" | Unbounded frame replication around a switch loop with no STP — Ethernet has no TTL to stop it |
| VLAN | "splitting the network" | Logical LANs on one physical switch via 802.1Q tags (12-bit VID); broadcasts stay within a color |
| MAN | "city Wi-Fi" | City-scale network: cable/DOCSIS via a headend, or WiMAX (802.16) |
| WAN | "the wide network" | Country/continent-scale subnet of leased transmission lines + routers; usually an internetwork |
| Subnet (original sense) | "the IP range" | Tanenbaum's first meaning: the collection of routers and lines moving packets host-to-host (distinct from the addressing sense in Ch. 5) |
| VPN | "secure tunnel" | Virtual office-to-office links over the *public Internet* — flexible, but inherits the Internet's variable latency/loss |
| Internetwork | "the Internet" | Any composite network joining ≥2 different network technologies; the global Internet is the best-known example |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 1 §1.2.2–1.2.4 (LAN/MAN/WAN classification) and Chapter 4 (the MAC sublayer, switching, VLANs).
- IEEE 802.3 — Ethernet (frame format, FCS, link speeds).
- IEEE 802.1D — Spanning Tree Protocol (loop prevention).
- IEEE 802.1Q — VLAN tagging (the 4-byte tag, 12-bit VLAN ID).
- IEEE 802.11 — Wireless LAN (Wi-Fi).
- IEEE 802.16 — Broadband Wireless Access (WiMAX) for MANs.
- RFC 826 — Address Resolution Protocol (ARP), the IP↔MAC mapping that drives LAN broadcasts.
- RFC 4364 — BGP/MPLS IP VPNs (carrier-grade WAN VPNs).
- RFC 894 — A Standard for the Transmission of IP Datagrams over Ethernet Networks (1500-byte MTU origin).
