# Address Plan and VLAN Design to QoS Policy for Voice and Video

> A modern campus carries at least four traffic classes with very different latency and loss budgets: **voice** (≤ 150 ms one-way, ≤ 1% loss, ≤ 30 ms jitter), **video conferencing** (≤ 200 ms one-way, ≤ 0.5% loss), **streaming / broadcast video** (≤ 5 s latency, ≤ 0.1% loss), and **best-effort data** (everything else). The lesson teaches the design that makes these classes coexist on the same wires: a **hierarchical IPv4/IPv6 address plan** (RFC 6177 IPv6, RFC 1918 IPv4, RFC 6598 CGNAT), a **VLAN design** (IEEE 802.1Q, with **voice VLAN** + **data VLAN** per access switch), and a **QoS policy** that combines **DSCP marking** (RFC 2474, RFC 3246 EF, RFC 2597 AFxx, RFC 2475 DiffServ architecture), **802.1p CoS** (IEEE 802.1D-2004), and **LLQ** (Low-Latency Queuing, RFC 3246) on the WAN. The deliverable is a runnable Python toolkit that ingests a building list, generates a **hierarchical IP plan** with **summary routes**, allocates **VLANs per access class**, emits **DSCP markings** for each class (EF / AF41 / AF31 / CS5 / BE), produces an **LLQ + WRED** policy for the WAN edge, and computes a **bandwidth budget** for voice (G.711 64 kbps + RTP + cRTP), video (H.264 1080p30 ~3 Mbps, Opus audio ~32 kbps), and a recommended **queuing strategy**. The artifact is a **policy-of-record** for voice and video quality that can be deployed to Arista EOS, Cisco IOS-XE, Juniper Junos, or Nokia SR Linux with minimal changes.

**Type:** Project
**Languages:** Python (stdlib: dataclasses, json, ipaddress, statistics, itertools, textwrap)
**Prerequisites:** Phase 7 (VLAN, OSPF), Phase 8 (Congestion, QoS, Internetworking), Phase 13 (Streaming media — for the codec bandwidths)
**Time:** ~180 minutes

## Learning Objectives

- Design a **hierarchical IP plan** that uses **RFC 1918** (10/8, 172.16/12, 192.168/16) for IPv4 and **RFC 6177** (/48 per site) for IPv6, with summary routes and predictable growth.
- Allocate **VLANs** per access class (Data, Voice, Wireless, Mgmt, Guest, IoT) and produce the **802.1Q** trunk plan with **voice VLAN** (`switchport voice vlan`) on every access port.
- Choose the right **DSCP marking** per class (EF for voice, AF41 / CS5 for video conferencing, AF31 / CS4 for streaming video, AF21 for call signaling, BE for data).
- Configure **LLQ (Low-Latency Queuing)** for voice, **CBWFQ** for video and signaling, and **WRED** (Weighted Random Early Detection, RFC 2309) for best-effort, on the WAN edge.
- Compute a **bandwidth budget** per site (voice = 80 kbps per call × concurrent calls + video = 3 Mbps per meeting × concurrent meetings + safety margin).
- Produce a **vendor-neutral QoS policy** skeleton that maps cleanly to **Arista EOS**, **Cisco IOS-XE**, **Juniper Junos**, and **Nokia SR Linux**.

## The Problem

The "Northbridge Polytechnic" campus from Lesson 01 is now in production with **480 students, 90 faculty, 30 admin staff** and the following real-time traffic patterns:

- **Voice**: 24 Cisco IP phones in admin offices, 12 in faculty offices, 6 in the Data Center, 4 at reception. Concurrent calls in peak hour: **8 to 12** calls (about 25% of phones busy).
- **Video conferencing**: 4 large conference rooms with **Polycom Studio X70** systems, plus 25 laptops running **Zoom / Teams**. Peak concurrent meetings: **6 to 10**.
- **Lecture capture**: 12 classrooms with **Panasonic AW-UE4** cameras recording H.264 1080p30 streams to a central media server, ~3 Mbps per stream.
- **Wi-Fi calling**: ~40% of voice calls now originate on Wi-Fi, requiring **WMM access categories** (IEEE 802.11e, superseded by **IEEE 802.11-2020**) on every AP.
- **Best-effort data**: everything else — web, file shares, email, IoT sensors.

The current network treats all traffic as best-effort. Voice calls have **noticeable clipping** (lost syllables), video meetings freeze every 5-10 minutes, and lecture capture streams drop frames during peak hours. The Wi-Fi calling experience is the worst because the AP and the wired network both compete for the same queues.

The lesson is to design a single QoS plan that fixes all of these problems and produces a deployable configuration skeleton.

## The Concept

A QoS plan is a **classification** problem (which packet is which class?), a **marking** problem (where in the network do we tag the class?), a **queuing** problem (how do we schedule the packets on the wire?), and a **policy** problem (what do we do when the class exceeds its budget?). Each step has well-defined standards and vendor implementations.

### DiffServ architecture (RFC 2475)

The IETF **Differentiated Services** (DiffServ) architecture divides the problem in two:

1. **Edge** — classify and mark packets at the network ingress (where the source is known).
2. **Core** — schedule packets based on the marking, without re-classifying.

This is **opposite** to IntServ (RFC 1633), which asks every router along the path to reserve state per flow. DiffServ scales to the Internet because the marking is per-class (8 bits in the **DS field**, formerly the IPv4 TOS / IPv6 Traffic Class octet), and the core router only reads 8 bits per packet.

The **DS field** is a byte, the high 6 bits are the **DSCP** (Differentiated Services Code Point), the low 2 bits are **ECN** (Explicit Congestion Notification, RFC 3168). The DSCP values are standardized:

| DSCP | Name | Per-hop behavior | Typical use |
|---|---|---|---|
| 46 (101110) | **EF** (Expedited Forwarding) | Low-loss, low-latency, low-jitter | VoIP bearer (RTP) |
| 48 (110000) | **CS6** | Network control (high priority) | Routing protocols (BGP, OSPF) |
| 40 (101000) | **CS5** | Broadcast video | Lecture capture, IPTV |
| 34 (100010) | **AF41** | Assured Forwarding class 4, level 1 | Video conferencing (Zoom, Teams) |
| 36 (100100) | **AF42** | AF class 4, level 2 | (drop precedence 2) |
| 38 (100110) | **AF43** | AF class 4, level 3 | (drop precedence 3) |
| 26 (011010) | **AF31** | AF class 3, level 1 | Streaming video (Netflix, YouTube) |
| 18 (010010) | **AF21** | AF class 2, level 1 | Call signaling (SIP, H.225, H.248) |
| 0 | **BE** (Best Effort) | Default | Everything else |

EF is the only class that requires **strict priority** queuing. AF classes use **CBWFQ** (Class-Based Weighted Fair Queuing) with **WRED** per drop-precedence level.

### 802.1p CoS and 802.1Q VLAN tagging

On a single Ethernet link with multiple VLANs, the **802.1Q** tag adds **4 bytes** to the Ethernet header, with a **3-bit PCP** (Priority Code Point, also called CoS for Class of Service) field. The PCP maps to one of 8 priority levels, which are commonly aliased to the IP DSCP values:

| PCP | 802.1D name | DSCP mapping | Typical use |
|---|---|---|---|
| 7 | Network Control | CS6 | Routing |
| 6 | Internetwork Control | CS6 | Routing |
| 5 | Voice (< 10 ms) | EF | VoIP bearer |
| 4 | Video (< 100 ms) | AF41 / CS5 | Video conf |
| 3 | Critical Applications | AF31 | Streaming |
| 2 | Excellent Effort | AF21 | Signaling |
| 1 | Background | BE | Bulk data |
| 0 | Best Effort | BE | Default |

The lesson's access policy marks the **DSCP** at the phone or AP ingress, then the switch copies the DSCP to PCP on egress to the trunk. On the WAN edge, the router copies DSCP to PCP on the 802.1Q trunk to the carrier.

### WMM (Wi-Fi Multimedia, IEEE 802.11e / 802.11-2020)

Wi-Fi is a **shared medium** with very different latency characteristics than wired Ethernet. The IEEE 802.11e amendment (now folded into the base 802.11-2020 standard) defines **WMM** (Wi-Fi Multimedia), which adds four **Access Categories** to the wireless MAC:

| AC | 802.1D name | DSCP mapping | Use |
|---|---|---|---|
| AC_VO | Voice | EF | VoIP bearer |
| AC_VI | Video | AF41 | Video conf |
| AC_BE | Best Effort | BE | Default |
| AC_BK | Background | BE | Bulk transfers |

WMM uses **EDCA** (Enhanced Distributed Channel Access), which is **CSMA/CA with priority-based backoff**. The lesson's planner emits the WMM policy for the APs so that voice gets the lowest contention window and the shortest AIFS (Arbitration Inter-Frame Space).

### LLQ (Low-Latency Queuing)

LLQ is the **strict-priority queue** that Cisco (and now Arista, Juniper) implement for voice. It is a **priority queue inside a CBWFQ policy**. The configuration looks like:

```
policy-map WAN-EDGE
  class VOICE
    priority 512           # 512 kbps of strict priority for voice
  class VIDEO-CONF
    bandwidth percent 30   # 30% of remaining for video conf
  class SIGNALING
    bandwidth percent 5    # 5% for SIP / H.323 / H.248
  class DATA
    bandwidth percent 60   # 60% for everything else
    random-detect          # WRED on the data class
```

The **strict priority queue is policed** to the configured rate. If voice exceeds 512 kbps, the excess is dropped (not queued), so it cannot starve the other classes. The recommendation is **25-33% of link bandwidth for the strict-priority queue** to absorb burst without starving other classes, but the absolute amount depends on the call count.

### Bandwidth budgets

For voice, the math per call:

- **G.711** (the default VoIP codec, 64 kbps PCM) + **RTP** (12 kbps overhead) + **UDP** (8 bytes) + **IP** (20 bytes) + **Ethernet** (38 bytes with 802.1Q) + **cRTP** (compressed RTP, RFC 2508) reduces 64 kbps to about **24 kbps** per call.
- **G.722** (wideband, 64 kbps) — same bandwidth as G.711, better quality.
- **G.729** (narrowband, 8 kbps) + cRTP = **12 kbps** per call — the modern choice for WAN.
- **Opus** (the modern VoIP codec, used by WebRTC and modern softphones) at 32 kbps + RTP = **50 kbps** per call.

For video:

- **H.264 720p30** ~ 1.5 Mbps
- **H.264 1080p30** ~ 3 Mbps
- **H.265 4K30** ~ 15 Mbps
- **VP9 1080p30** ~ 2 Mbps
- **AV1 1080p30** ~ 1.5 Mbps

The lesson's planner emits a per-call bandwidth table and a site budget that includes a **safety margin** (typically 30%) for re-keying, retransmissions, and burst.

### Hierarchical IP plan with summary routes

A **hierarchical IP plan** is one where the addressing mirrors the topology: the top bits identify the region, the next bits identify the site, the next bits identify the building, the next bits identify the VLAN, and the low bits identify the host. This makes **summary routes** possible — one route covers many subnets.

| Bits | Purpose | Example |
|---|---|---|
| 8 | Region | 10.<b>10</b>.0.0/8 |
| 8 | Site | 10.10.<b>0</b>.0/16 |
| 8 | Building | 10.10.0.<b>0</b>/24 |
| 8 | VLAN | 10.10.0.<b>10</b>.0/24 |
| 8 | Host | 10.10.0.10.<b>50</b>/24 |

The summary route for "Building Engineering" is **10.10.10.0/24**, advertised into OSPF / BGP as a single route. The summary route for "All Engineering VLANs" is **10.10.0.0/16**.

### VLAN design with voice VLAN

A modern access switch has two VLANs per access port:

- **Data VLAN** — for the laptop, PC, or phone's PC port.
- **Voice VLAN** — for the IP phone, configured with `switchport voice vlan X`.

The IP phone tags its bearer traffic with **DSCP EF**, the laptop's data is **BE**. The access switch classifies based on the **source MAC OUI** (Cisco, Polycom, Yealink have known OUIs) or the **LLDP-MED** (Link Layer Discovery Protocol - Media Endpoint Discovery, IEEE 802.1AB-2016) policy advertised by the phone. The lesson's planner emits the LLDP-MED policy so the access switch knows the phone is a phone.

## Build It

The deliverable is `code/main.py`, a stdlib-only QoS + addressing planner. Inputs are the building list, the per-building user count, the call count, and the WAN bandwidth budget. Outputs are:

- A **hierarchical IP plan** with summary routes.
- A **VLAN plan** with voice VLAN per access port.
- A **DSCP marking** table.
- An **LLQ + WRED** policy for the WAN edge.
- A **bandwidth budget** per site.
- A **vendor-neutral QoS config skeleton** for EOS / IOS-XE / Junos / SR Linux.

Run it: `python3 main.py`. The output is deterministic.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| Hierarchical IP plan | Non-overlapping subnets, summary routes, RFC 1918 / 6177 | Generated |
| VLAN plan | Data + Voice + Wireless + Mgmt + Guest + IoT per building | Generated |
| DSCP marking table | EF / CS6 / CS5 / AF41 / AF31 / AF21 / BE per class | Generated |
| LLQ + WRED policy | Strict priority for voice, CBWFQ for video, WRED for data | Generated |
| Bandwidth budget | Per-site voice + video + signaling + data budget with 30% margin | Generated |
| WMM policy | Voice / Video / Best Effort / Background ACs on APs | Generated |
| Vendor-neutral config | Maps to EOS / IOS-XE / Junos / SR Linux | Generated |

## Ship It

The artifact is `outputs/qos-policy.json`, `outputs/llq-policy.txt`, `outputs/wmm-policy.txt`, `outputs/vlan-plan.csv`, and `outputs/ip-plan.csv`. The JSON is the design-of-record; the LLQ and WMM configs are deployment-ready for the WAN edge and the APs.

To regenerate after a change: edit the buildings list at the top of `code/main.py`, re-run, diff the outputs.

## Exercises

1. **DSCP classification**: a packet arrives at the WAN edge with **DSCP 34 (AF41)**. Which traffic class does it belong to, and how is it scheduled? What happens if the class exceeds its bandwidth budget?
2. **cRTP math**: a WAN link carries 10 concurrent G.711 calls. Without cRTP, what is the bandwidth consumption? With cRTP, what is it? How much bandwidth is saved?
3. **LLQ starvation**: the WAN link is 10 Mbps. The LLQ policy gives voice 5 Mbps strict priority. Can voice starve video and data? Why or why not? What is the recommended maximum for the strict-priority queue?
4. **WRED curves**: WRED uses **min-threshold**, **max-threshold**, and **mark-probability-denominator**. For an AF41 class with min=40, max=80, denominator=10: what fraction of packets are dropped when the queue depth is 50, 70, and 90 packets?
5. **Voice VLAN detection**: a Cisco IP phone and a softphone (laptop running Zoom) are both plugged into the same access port. How does the switch differentiate them? What configuration is required on the switch to make the voice VLAN work?
6. **WMM vs wired QoS**: an AP receives a VoIP packet (DSCP EF) from a wireless phone. What WMM access category does it go into? On the wired uplink, what 802.1p PCP and DSCP does the AP set on the egress packet?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DiffServ | "QoS architecture" | RFC 2475 — classify and mark at edge, schedule at core |
| DSCP | "QoS tag" | 6-bit Differentiated Services Code Point in the IP header; EF / AFxx / CSx |
| EF | "Voice class" | Expedited Forwarding (DSCP 46); strict-priority queue, low jitter |
| AF41 | "Video class" | Assured Forwarding class 4, level 1 (DSCP 34); CBWFQ + WRED |
| 802.1p / PCP | "VLAN priority" | 3-bit Priority Code Point in the 802.1Q tag |
| LLQ | "Priority queue" | Low-Latency Queuing — strict-priority inside CBWFQ |
| CBWFQ | "Class-based queue" | Class-Based Weighted Fair Queuing |
| WRED | "Congestion avoidance" | Weighted Random Early Detection — drops early to signal congestion |
| cRTP | "Compressed RTP" | RFC 2508 — compresses IP/UDP/RTP headers from 40 bytes to 2-4 bytes |
| WMM | "Wi-Fi QoS" | IEEE 802.11e / 802.11-2020 — Access Categories AC_VO / AC_VI / AC_BE / AC_BK |
| EDCA | "Wi-Fi MAC QoS" | Enhanced Distributed Channel Access — priority-based contention |
| Voice VLAN | "Aux VLAN" | Separate VLAN for IP phones; configured via LLDP-MED |
| LLDP-MED | "Phone discovery" | IEEE 802.1AB-2016 — Media Endpoint Discovery; tells the switch the phone is a phone |
| Summary route | "Aggregate" | One route covers many subnets; reduces routing table size |
| Hierarchical IP | "Top-down addressing" | Addressing mirrors topology; enables summary routes |

## Further Reading

- **RFC 2474** (Definition of the Differentiated Services Field), **RFC 2475** (DiffServ Architecture), **RFC 3246** (EF PHB), **RFC 2597** (AF PHB), **RFC 3168** (ECN).
- **RFC 2508** (cRTP), **RFC 2309** (WRED), **RFC 1633** (IntServ for context).
- **IEEE 802.1Q-2018** (VLAN tagging), **IEEE 802.1p-1998 / 802.1D-2004** (traffic class), **IEEE 802.1AB-2016** (LLDP / LLDP-MED).
- **IEEE 802.11-2020** (Wi-Fi base standard, includes 802.11e WMM).
- *Cisco QoS Exam Guide* (Wendell Odom, Cisco Press 2004) — the practical Cisco reference.
- *End-to-End QoS Network Design* (Tim Szigeti, Cisco Press 2013) — the modern QoS book; covers voice, video, and data.
- *CVOICE 8.0* (Cisco Press) — the Cisco Voice over IP study guide.
- *The Polycom Unified Communications Deployment Guide* — practical voice / video deployment.