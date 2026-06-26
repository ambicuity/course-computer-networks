# Small Campus Network Design

> A small campus LAN — three to ten buildings, 200 to 2,000 users, one or two upstream ISPs — is the design problem every network engineer must solve at least once with rigor. This lesson walks the three-layer **hierarchical model** (core, distribution, access) as defined by Cisco's original **Campus Architecture** (now part of the Cisco Validated Design program), adds modern twists — **stackable access rings with MLAG/MC-LAG**, **L3 to the distribution**, **PoE+** for 802.11ax APs and VoIP, **EVPN-VXLAN** optional for multi-tenant buildings, and a **10G/25G** uplink budget — and turns the result into a runnable Python plan generator that emits a VLAN/subnet table, switch port allocation, LAG design, first-hop redundancy plan (VRRP/HSRP), wireless sizing, and a bill of materials sized against a real budget. The deliverable is a `design.json` plus a vendor-neutral configuration skeleton suitable for a 60% CapEx / 40% OpEx review.

**Type:** Project
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, itertools, statistics)
**Prerequisites:** Phase 7 (Network Layer Design and Routing — VLANs, OSPF), Phase 8 (Congestion, QoS, and Internetworking — L2/L3 boundaries, HSRP/VRRP), Phase 14-16 (security baseline so VLAN 1 is not used and management is on a separate VRF)
**Time:** ~180 minutes

## Learning Objectives

- Decompose a campus requirement (buildings, floors, user counts, bandwidth per user, wireless density) into a layered design with explicit uplink bandwidth budgets.
- Produce a deterministic IP plan that fits RFC 1918 space, reserves space for growth, follows the **10/8 = 4,096 subnets** rule (or the **172.16/12 = 1,048,576** / **192.168/16** fallbacks), and never overlaps service subnets.
- Choose between **collapsed core** (one switch pair, ≤ 200 users) and **full core-distribution-access** (≥ 500 users) with defensible cost and resilience trade-offs.
- Specify first-hop redundancy (HSRP, VRRP, or stackwise virtual switching) with timer values that converge in under 3 seconds, matching the **IEEE 802.1AX-2020** LAG and **RFC 9568** VRRPv3 expectations.
- Size a wireless network against the **802.11ax** density rule of "one AP per 25-40 clients in office space" and the **CAT6A** PoE++ budget of 60-100 W per AP.
- Output a machine-readable `design.json` plus a vendor-neutral config skeleton, then validate it for plan collisions and budget overruns.

## The Problem

The head of IT at "Northbridge Polytechnic" has approved a new network for a campus with three buildings (Engineering, Liberal Arts, Data Center), each two to four floors, housing 480 students, 90 faculty, 30 admin staff, 12 classrooms with projection and conferencing, and a small on-premise data center that hosts the SIS, LMS, file shares, and one VoIP PBX. The budget is fixed at **$185,000 CapEx** plus **$22,000/year OpEx** for managed switches, AP licensing, and an ISP contract. Old equipment must be decommissioned in a 12-hour weekend window with a documented rollback plan.

The senior engineer who owns this project will be measured on five things: (1) does it boot? (2) does it survive a single switch failure? (3) does the Wi-Fi actually deliver ≥ 100 Mbps per client in dense classrooms? (4) is the IP plan documented well enough that a junior can plug in a new access switch without asking? (5) is the design defensible at a budget review, meaning the math and the citations are visible?

This is a real production problem. Mistakes here are visible every day: a 1 Gbps uplink on a 24-port access switch becomes oversubscribed at 9 AM the first Monday of term, a /23 used for "data" leaves no room for "voice" without re-numbering, and a single-stack distribution switch means one power supply failure takes down a building. The lesson is to build the design once, completely, on paper, before a single cable is pulled.

## The Concept

The campus network is a problem of **hierarchy, redundancy, and headroom**. The 1999 Cisco Internetworking Design Seminar (CCDP) defined the layered model that has survived twenty-five years of evolution: **access** at the edge where users plug in, **distribution** where policy and routing live, **core** where packets cross the campus at line rate. Each layer has a different failure model and a different upgrade cadence. We build the design around that hierarchy, then add the IP plan, the redundancy model, and the wireless sizing.

### The three-layer hierarchical model

The original Cisco Campus Architecture (1999) and the modern **Cisco Validated Design for Campus LAN** (CVD-Campus 6.0, 2023) prescribe the same three layers. Each layer has a well-defined role:

- **Access** — port density, PoE, basic security (802.1X, DHCP snooping, DAI), low per-port cost. One access switch per **wiring-closet** or per **30-48 users**. Stacks of 4-8 members are common; an access stack is one logical switch but physically a ring, which gives **N-1** resilience and lets the closet be wired with **LACP** to a dual-attached distribution pair.
- **Distribution** — policy enforcement, inter-VLAN routing, ACL ingress/egress, first-hop redundancy gateway (HSRP / VRRP / SVL), and aggregation to the core. One pair of distribution switches per building (or per floor in tall buildings), each with **dual uplinks** to the core forming an **MLAG** (Arista, Nokia) or **MCT** (Juniper) or a vendor-proprietary stack.
- **Core** — non-blocking backplane, line-rate L3, no ACLs, no policy. **Dual core switches** in an MLAG or back-to-back VPC pair, redundant supervisors, dual power supplies, redundant fans. Core size scales with the **bisection bandwidth** (the bandwidth required if every user could simultaneously talk to every other user, which is never needed but is the worst-case for sizing).

A **collapsed core** — distribution and core merged into one pair — is acceptable below ~200 users or for branch / small-business sites. Above that, the cost of the merged chassis (24-port 25G line cards + 100G uplinks) is comparable to two pairs, and the operational separation between "policy at distribution" and "transport at core" becomes valuable.

The hierarchy also maps to **failure domains**. An access switch failure takes out 30-48 users in one wiring closet — recoverable. A distribution switch failure takes out a whole building — recoverable with **HSRP/VRRP failover** (typically 3-9 seconds, sub-second with **BFD** + **fast-hello VRRP**). A core switch failure takes out the whole campus — recoverable only with **non-stop forwarding** (NSF), **graceful restart**, and the **NSF-aware** routing protocols that come with OSPFv2/v3 and BGP graceful restart.

### IP plan and subnet sizing

Three RFC 1918 blocks are available: **10.0.0.0/8** (16,777,216 addresses, 4,096 /16s), **172.16.0.0/12** (1,048,576 addresses), **192.168.0.0/16** (65,536). The conventional choice for a campus is **10.x.0.0/16** per building with **/24** subnets per VLAN, leaving **10.x.255.0/24** for management, **10.x.254.0/24** for inter-switch links (point-to-point /31s are even better — see RFC 3021), **10.x.253.0/24** for DHCP pools, and **10.x.252.0/24** for first-hop gateway IPs.

A campus with three buildings and ten VLANs needs at least **30 subnets** for users, plus 6 for routing links, plus 3 for management, plus reserved growth. A **/20** per building (4,096 addresses) gives room for 4 buildings of 16 VLANs each before re-numbering — comfortable for the 5-year lifecycle.

The plan must be **non-overlapping**, **summary-friendly** (one /20 summary route per building, advertised into OSPF area 0 or BGP), and **documented as code**. The lesson's `design.json` outputs this plan as a tree that can be diff-reviewed in git.

### Redundancy: HSRP, VRRP, and stacking

First-hop redundancy protocols all do the same thing: two (or more) physical routers share a **virtual IP** (VIP) and a **virtual MAC** (`0000.0C07.ACxx` for HSRP, `0000.5E00.01xx` for VRRP), and one is the active router at a time. They differ in election logic, hello timers, and authentication.

| Protocol | Standard | Election | Default hello | Default hold | Virtual MAC | Multi-chassis |
|---|---|---|---|---|---|---|
| HSRPv1 | Cisco-proprietary | Higher priority, then higher IP | 3 s | 10 s | `0000.0C07.ACxx` | Stack only |
| HSRPv2 | Cisco-proprietary | Same | 3 s | 10 s | `0000.0C07.ACxx` (extended group) | Stack only |
| VRRPv2 | RFC 3768 | Higher priority, then higher IP | 1 s | 3 s | `0000.5E00.01xx` | No (RFC 5798 adds v3 with MD5) |
| VRRPv3 | RFC 9568 (was RFC 5798) | Same | 100 ms (centisecond) | 300 ms | Same | Yes (RFC 9568 §6) |
| Stackwise Virtual / VSS / MC-LAG | Vendor proprietary | N/A (control plane is one) | N/A | N/A | Same as chassis | Yes |

For a campus that mixes Cisco, Arista, Juniper, and HPE/Aruba, **VRRPv3** is the only protocol that all four vendors implement and is the recommended default. With **fast-hello (100 ms)** timers and **BFD** between switches, failover converges in well under 1 second.

Modern stacks — Cisco **StackWise Virtual**, Arista **MLAG**, Juniper **MC-LAG**, HPE **VSF** — collapse two physical switches into one logical switch, which means the active gateway is one of two supervisor engines inside the same chassis. Failover is **stateful** (NSF), and the virtual MAC does not change because the switch is the same. This is operationally simpler than HSRP/VRRP and is the recommended default for new builds; legacy deployments continue to use HSRP/VRRP because removing it requires a maintenance window.

### Bandwidth oversubscription and uplink math

The access-to-distribution uplink is the most-oversubscribed link in the campus. The rule of thumb: **20:1** for data-only ports, **4:1** for mixed voice/data, **2:1** for converged wireless. A 48-port access switch at 1 Gbps with 1 Gbps uplink is 48:1 oversubscribed at peak; with a 10 Gbps uplink it is 4.8:1 — still acceptable, and 10G is now commodity-priced.

For a wireless AP on **802.11ax** (Wi-Fi 6/6E) the AP can deliver up to **1.2 Gbps** in 80 MHz channels with 2x2 MIMO, so each AP needs at least **1 Gbps** of uplink and ideally **2.5 Gbps** (2.5GBASE-T, **IEEE 802.3bz**) so that two adjacent APs on the same switch do not saturate the uplink.

The distribution-to-core uplink runs at **25 Gbps or 40 Gbps** today (802.3by, 802.3ba) and should be sized at **20% of total access bandwidth**. A building with 20 access switches at 10 Gbps each has 200 Gbps of access; the distribution pair has 80 Gbps of uplink to the core, which is a **2.5:1** oversubscription — comfortable.

### Wireless density and PoE

**802.11ax** doubled the spatial streams per radio and improved the MAC for dense deployments. The deployment rule is now "**one AP per 25-40 clients in office space**, one AP per 12-20 clients in classrooms and lecture halls." Modern APs (Cisco 9166, Aruba AP-655, Ruckus R760) ship with **2x2:2** or **4x4:4** radios and consume **15-25 W** under load. With **802.3bt Type 3/4 PoE** (60 W / 100 W per port) one switch port can power one high-end AP plus a small IP phone or sensor.

For a campus with 480 students and 90 faculty, the **peak simultaneous** population is roughly **350 devices** (one phone + one laptop per person, plus classroom projectors and conferencing). At **30 clients per AP**, that's **12 APs minimum**, but with classroom density it's realistically **24 APs** (one per classroom, plus hallway and common-area coverage). The lesson's planner sizes APs against user density per building and outputs PoE budget per access switch.

### Configuration management and documentation

A design is only as good as the configuration that ships it. The lesson's `code/main.py` outputs a **vendor-neutral config skeleton** — interface descriptions, VLAN IDs, IP addresses, LAG numbers, VRRP/HSRP groups, ACL names — that a network engineer can map to **Arista EOS**, **Cisco IOS-XE**, **Juniper Junos**, or **Nokia SR Linux**. The skeleton is the **contract** between the design and the configuration, and it lives in version control.

## Build It

The deliverable is a single Python module at `code/main.py` that produces a deterministic campus network design. Inputs are buildings (name, floors, users per floor, bandwidth per user), an uplink bandwidth budget, and an AP density rule. Outputs are a JSON design file with VLAN plan, switch allocation, IP plan, uplink LAG, first-hop redundancy, wireless sizing, and a bill of materials priced against a public catalog.

Run it: `python3 code/main.py`. The output includes:

- A **VLAN plan** with one VLAN per access class per building (Data, Voice, Wireless, Management, Guest, IoT).
- An **IP plan** with non-overlapping subnets, summary-friendly boundaries, reserved ranges for management, gateway IPs, and DHCP pools.
- A **switch allocation** with access-stack size per wiring closet, distribution pair per building, core pair for the campus.
- A **LAG design** with LACP bundles between access and distribution, and between distribution and core, sized for the bandwidth budget.
- A **first-hop redundancy** plan using VRRPv3 (default) or HSRPv2 (Cisco-only) with fast-hello timers.
- A **wireless plan** with AP count per building, channel plan summary, and PoE budget per access switch.
- A **bill of materials** with unit prices and a total vs. the $185,000 budget.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| `design.json` — VLAN plan | 6 VLANs per building minimum, non-overlapping subnets, summary-friendly boundaries | Generated |
| `design.json` — IP plan | /24 per user VLAN, /31 for point-to-point links, /24 reserved for management | Generated |
| `design.json` — switch allocation | Access stacks sized to 48 ports, distribution pair per building, core pair | Generated |
| `design.json` — LAG design | LACP bundles between layers, member count = 2 (L2 HA), port speed ≥ bandwidth / N | Generated |
| `design.json` — first-hop redundancy | VRRPv3 fast-hello or HSRPv2 with timers, virtual IP per user VLAN | Generated |
| `design.json` — wireless plan | AP count ≥ users / 30, PoE budget per switch ≤ 80% of switch PoE capacity | Generated |
| `design.json` — BOM | Total ≤ $185,000, line items include model + quantity + unit price | Generated |
| Config skeleton | Vendor-neutral, interface descriptions, VLAN IDs, IP addresses, LAG numbers | Generated |
| Validation report | Plan collisions: 0, budget overrun: ≤ 5% over $185K, PoE overrun: 0 | Generated |

## Ship It

The artifact is `outputs/design.json` plus `outputs/config-skeleton.txt`. The JSON is the design-of-record for the campus, suitable for a budget review or a change-control meeting. The config skeleton is the day-one bootstrap for the access, distribution, and core switches, with placeholders for hostnames, BGP AS numbers, and management IPs.

To regenerate after a change: edit the `buildings` list at the top of `code/main.py` and re-run. The output is deterministic — same inputs produce the same JSON.

## Exercises

1. **Collapse the core**: rebuild the design with `collapsed_core = True` for a 100-user branch and show the CapEx delta. What is the maximum user count for which collapsed core is still defensible?
2. **Bandwidth audit**: an AP cluster in the Engineering building has 60 simultaneous clients each demanding 5 Mbps. Will the existing 2x 10 Gbps uplink to distribution saturate? Show the math and propose a fix (more uplinks, 25G uplinks, traffic shaping on the AP, or client load balancing).
3. **VRRP failover math**: with VRRPv3 fast-hello at 100 ms and BFD at 50 ms, what is the worst-case failover time on a routed link? How does this change if the link is an LACP bundle that takes 2 seconds to fall over on a member-port failure?
4. **Subnet growth**: the campus plans to add a fourth building (Library, 200 users, 2 floors) in 18 months. Without re-numbering, which address blocks are still available? Show the next IP plan for the new building using only unused ranges.
5. **PoE budget**: an access switch has 48 PoE+ ports at 30 W each (802.3at Type 2). It powers 24 APs at 25.5 W each plus 20 IP phones at 7 W each. What is the per-switch PoE draw, and is the switch's 1,440 W budget sufficient? Show the upgrade path.
6. **Vendor-neutral mapping**: take the output config skeleton and write the equivalent `interface` block for **Arista EOS**, **Cisco IOS-XE**, **Juniper Junos**, and **Nokia SR Linux**. Document the syntax differences and the operational impact (commit vs. write memory, rollback, configuration replace).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hierarchical model | "Three layers" | Core (transport), distribution (policy + L3), access (ports + PoE) — each with its own failure domain and upgrade cadence |
| Collapsed core | "One switch pair" | Distribution and core merged into one chassis pair; acceptable under ~200 users |
| MLAG / MC-LAG / VSS | "Two switches acting as one" | Vendor-proprietary protocols that let two physical switches appear as one logical L2/L3 device, removing the need for FHRP |
| HSRP / VRRP | "Gateway redundancy" | First-hop redundancy protocols; VRRPv3 (RFC 9568) is the modern default, VRRPv2 (RFC 3768) legacy |
| Oversubscription | "How busy is the uplink" | Ratio of access bandwidth to uplink bandwidth; 4:1 is acceptable for mixed voice/data, 2:1 for wireless |
| PoE++ (802.3bt) | "Power over Ethernet" | Type 3 (60 W) and Type 4 (100 W) PoE per port; required for modern Wi-Fi 6E / Wi-Fi 7 APs |
| 802.11ax density | "How many APs" | 1 AP per 25-40 clients in offices, 1 per 12-20 in classrooms |
| IP plan | "VLAN map" | Non-overlapping subnets, summary-friendly boundaries, reserved ranges for management, gateway, DHCP |
| BOM | "Bill of materials" | Priced list of hardware + software + support; the design's $ justification |
| Config skeleton | "The day-one config" | Vendor-neutral output that maps to EOS / IOS-XE / Junos / SR Linux with minimal changes |

## Further Reading

- **Cisco Validated Design for Campus LAN** (CVD-Campus 6.x, 2023) — the modern reference for the three-layer model with EVPN-VXLAN.
- **RFC 3768** (VRRPv2) and **RFC 9568** (VRRPv3, formerly RFC 5798) — the open-standard first-hop redundancy protocols.
- **IEEE 802.1AX-2020** (Link Aggregation) — LACP, the modern LAG protocol.
- **IEEE 802.3bt** (PoE++) — Type 3 / Type 4 power budgets and cabling rules.
- **IEEE 802.11ax-2021** (Wi-Fi 6/6E) and **802.11be** (Wi-Fi 7) — the wireless density rules and channel plans.
- *Computer Networking: A Top-Down Approach* (Kurose & Ross), Chapter 5 — the layered-network framing.
- *Network Warrior* (Gary Donahue, 2nd ed., O'Reilly 2011) — the practical campus book; older but still recommended for the access/distribution/core intuition.
- *Campus Network Design Fundamentals* (CDP, Cisco Press 2004) — the original three-layer reference, still useful as a historical anchor.