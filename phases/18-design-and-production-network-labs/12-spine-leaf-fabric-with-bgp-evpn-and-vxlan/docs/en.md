# Spine-Leaf Datacenter Fabric with BGP EVPN and VXLAN Encapsulation

> A modern datacenter fabric — a few hundred to a few thousand servers connected by a **spine-leaf** topology with **VXLAN** overlay tunnels and a **BGP EVPN** control plane — is the only network architecture that scales to 100,000+ virtual endpoints while preserving layer-2 semantics for live migration, multi-tenancy, and anycast services. The classic three-tier datacenter (core-aggregation-access) collapses under the weight of east-west traffic: a single 10 Gbps access uplink oversubscribes 480:1 at 1,000 servers, and STP shuts down 50% of the available links. The spine-leaf topology, with every leaf one hop from every other leaf, eliminates STP, gives non-blocking bisectional bandwidth, and lets every server be one hop from every other server. The VXLAN overlay (RFC 7348) provides 16 million logical networks over the IPv4/IPv6 underlay, and BGP EVPN (RFC 7432) is the control plane that distributes MAC/IP/VTEP information across the fabric. This lesson is the working playbook for a production spine-leaf fabric: the topology (N spines, M leaves, any number of servers per leaf), the addressing plan (VTEP IP, loopback IP, anycast gateway, VNI, RD, RT), the BGP design (one address family per leaf, route-reflectors for scale), the overlay (VXLAN-GBP for microsegmentation, symmetric or asymmetric IRB, distributed anycast gateway), the failure modes (leaf failure, spine failure, VTEP failure, BGP session failure), and the migration plan (brownfield from a three-tier to a spine-leaf, with the parallel run, the cutover, and the rollback). The deliverable is a Python fabric planner that takes a leaf count, a server count, a port density, and an oversubscription target, and outputs the spine count, the VTEP/RD/RT plan, the BGP configuration skeleton, the VXLAN bridge-domain table, and the migration runbook.

**Type:** Project
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, itertools), shell, FRRouting, Wireshark
**Prerequisites:** Phase 7 BGP, Phase 8 VLANs, Phase 18 lesson 09 (BGP)
**Time:** ~160 minutes

## Learning Objectives

- Explain the **spine-leaf topology** (N spines, M leaves, ECMP across all spines) and compute the spine count, the oversubscription ratio, and the bisectional bandwidth for a given server count and link speed.
- Design the **VTEP addressing plan**: one VTEP IP per leaf, one loopback IP per leaf, one anycast gateway IP per VNI, and the RD/RT encoding for the BGP EVPN NLRI.
- Configure **BGP EVPN** as the control plane: one address family `l2vpn evpn`, one route-reflector cluster (typically on the spines), one session per leaf, and the right RT policy to share MAC/IP routes across the right set of leaves.
- Implement **VXLAN** with the right encapsulation (VXLAN-GBP for microsegmentation, symmetric IRB for east-west traffic, asymmetric IRB for north-south), the right MTU (1550 for the inner frame inside a 1500-byte outer frame plus the VXLAN header), and the right IGMP/MLD snooping on the underlay.
- Choose between the **distributed anycast gateway** (a single gateway IP per VNI, advertised by every leaf, hot-standby) and the **centralized gateway** (a single pair of leaves acting as the gateway for the VNI) and articulate the failure-recovery trade-off.
- Build a **migration plan** from a three-tier to a spine-leaf: parallel run (new fabric built alongside old, no traffic), cutover (one VLAN at a time, with the rollback window), and the post-migration validation (MAC/IP table parity, BGP session state, VXLAN tunnel state).

## The Problem

"Helix Cloud" operates a 2,500-server datacenter for a SaaS workload. The existing network is a three-tier topology: two core routers, four aggregation routers, and 24 access switches, with 10 Gbps server-facing ports and 40 Gbps aggregation-to-core uplinks. The customer pain is threefold: (1) east-west traffic — between servers in the same rack — must traverse the aggregation tier, which adds 2-4 microseconds of latency and oversubscribes the aggregation-to-core uplinks; (2) live migration of VMs between racks requires L2 adjacency across the aggregation, which is implemented with OTV or vSphere vDS and is fragile; (3) STP shuts down 50% of the aggregation-to-core links, so the design has 2x the physical links it actively uses.

The senior engineer must deliver a spine-leaf fabric: 8 spines, 32 leaves, 100 Gbps spine-leaf links, 25 Gbps server-facing links (one link per server, or four servers per 100 Gbps leaf port via a breakout), and 2,560 server-facing ports at 25 Gbps (with a 4:1 oversubscription, which gives a realistic 6.4 Tbps of fabric capacity). The fabric must support 4,000 VLANs (one per tenant), 100,000 VMs, and live migration of any VM between any two leaves with no more than 1 ms of additional latency.

A wrong choice in this design is invisible for weeks and then becomes a major incident. A VTEP IP that overlaps with a server IP causes silent packet drops; a route-reflector that is single-homed takes the fabric offline when the spine fails; a VNI that is reused for two tenants causes a layer-2 loop. The lesson is to build the plan once, completely, and to test the failure modes before any production traffic flows.

## The Concept

A spine-leaf fabric is a **Clos network** named after Charles Clos, who proved in 1953 that a multi-stage switch fabric built from smaller switching elements can be non-blocking. The datacenter form has two stages: the **spines** (the "middle stage") and the **leaves** (the "input/output stage"). Every leaf connects to every spine, and no spine connects to another spine. The result is a topology in which any two leaves are exactly two hops apart (leaf → spine → leaf) and in which every spine-leaf link is an ECMP path that can carry traffic.

### The topology math and the oversubscription trade-off

The **spine count** is set by the desired oversubscription and the per-server traffic assumption. For Helix Cloud:

- 2,560 server-facing ports at 25 Gbps = 64 Tbps of server-facing bandwidth.
- 32 leaves, each with N spine-facing ports of 100 Gbps.
- 8 spines, each with 32 leaf-facing ports of 100 Gbps = 8 × 32 × 100 = 25.6 Tbps of fabric capacity.
- Oversubscription = 64 / 25.6 = 2.5:1.

The industry rule of thumb is 4:1 for a typical cloud workload and 1:1 for a high-performance cluster (HPC, AI/ML, low-latency trading). Helix Cloud's 2.5:1 is conservative for a SaaS workload and gives room for the east-west traffic to grow without a fabric upgrade. The lesson's planner computes the spine count for a given leaf count, leaf-to-spine link speed, server-facing link speed, and oversubscription target.

The **bisectional bandwidth** is the bandwidth that crosses an imaginary line drawn through the middle of the fabric. For a symmetric spine-leaf with N spines and M leaves, the bisectional bandwidth is `(N × M × link_speed) / 2` (because the line crosses half the spines' uplinks). For Helix Cloud, that is `(8 × 32 × 100) / 2 = 12.8 Tbps` — comfortably more than the typical 1-2 Tbps of east-west traffic in a 2,500-server datacenter.

### The VTEP, the loopback, and the anycast gateway

Every leaf runs a **VTEP** (VXLAN Tunnel Endpoint) that encapsulates and decapsulates VXLAN frames. The VTEP is a software (Linux, SONiC, Cumulus, FRR) or hardware (Arista 7800R3, Cisco Nexus 9300, Juniper QFX) process that listens on a **VTEP IP** — typically a dedicated loopback IP that is reachable across the fabric. The VTEP IP is the "outer destination" of every VXLAN frame, and the inner destination is the actual MAC/IP of the destination VM.

Every leaf also has a **loopback IP** (different from the VTEP IP, on a different subnet) that is used for the BGP session to the route-reflectors. The loopback is the BGP router-ID, and the VTEP is the source/destination of the VXLAN data plane. Separating the two is a best practice because the VTEP IP is in the underlay (and may be in the same subnet as the server-facing gateway, depending on the design) and the loopback is in the routing infrastructure.

The **anycast gateway** is the IP that VMs use as their default gateway. In the distributed anycast gateway model, every leaf that hosts a VNI advertises the same gateway IP (e.g., 172.16.0.1 for VNI 10001) via BGP EVPN, and the VM's local leaf is the active gateway. If the VM migrates to another leaf, the new leaf is the active gateway with the same IP, and the VM's ARP table does not need to be updated. The lesson's planner computes the anycast gateway IP per VNI and the RD/RT encoding for the BGP EVPN NLRI.

### The BGP EVPN control plane

**BGP EVPN** (RFC 7432, updated by RFC 8365 for VXLAN) is the control plane that distributes MAC/IP/VTEP information across the fabric. BGP is the right choice because it is the only routing protocol that scales to 100,000+ routes without per-vendor lock-in, it has a well-defined NLRI for every relevant piece of information, and it has the operational tooling (BGP monitoring, RPKI, route-reflectors) that operators already know.

The NLRI types in BGP EVPN are:

- **Type 1 — Ethernet Auto-Discovery (A-D)**: per-ESI (Ethernet Segment Identifier) routes for multihoming.
- **Type 2 — MAC/IP Advertisement**: per-MAC, optionally with IP, the VTEP that learned the MAC, and the VNI.
- **Type 3 — Inclusive Multicast Ethernet Tag**: per-VTEP, per-VNI, the P-tunnel that the VTEP uses for BUM (Broadcast, Unknown unicast, Multicast) traffic.
- **Type 4 — Ethernet Segment**: per-ESI, used for Designated Forwarder election in multihoming.
- **Type 5 — IP Prefix**: per-IP-prefix route, used for inter-subnet routing (symmetric IRB).

The lesson's planner builds a NLRI table for a sample VNI and a sample MAC, and shows the BGP message that propagates the NLRI from the originating leaf to the other leaves.

The **route-reflector** is the BGP scaling primitive. With 32 leaves and 8 spines, a full mesh would require `32 × 31 / 2 = 496` iBGP sessions. With two route-reflectors (one on two spines, for redundancy), each leaf has two sessions (one to each RR), and the total session count is `32 × 2 = 64`. The route-reflectors are configured with `cluster-id` and `client-to-client reflection`, and the leaves are configured with the route-reflectors as their iBGP neighbors. The lesson's planner computes the session count for a given leaf count and the number of route-reflectors.

### VXLAN encapsulation, the MTU, and the IRB choice

**VXLAN** (RFC 7348) is the data-plane encapsulation. A VXLAN frame is an outer Ethernet/IP/UDP header with a destination port of 4789 (IANA-assigned), an 8-byte VXLAN header with a 24-bit VNI, and the inner Ethernet frame. The total overhead is 50 bytes (14 Ethernet + 20 IP + 8 UDP + 8 VXLAN), so an inner MTU of 1500 requires an outer MTU of 1550 on every underlay link. The lesson's planner enforces the MTU on every spine-leaf link and on the server-facing links (if they participate in the underlay, which is rare).

The choice between **symmetric IRB** and **asymmetric IRB** is the central design decision. Asymmetric IRB is the older model: the ingress leaf routes the packet to the destination VNI, encapsulates it, and the egress leaf decapsulates and bridges. The ingress leaf must know the destination VTEP, which it learns from the BGP EVPN Type 2 NLRI. Symmetric IRB is the newer model: the ingress leaf routes the packet to a "Layer-3 VNI" that carries the routed packet, the egress leaf routes it again, and the destination is reached via the inner MAC. Symmetric IRB is the recommended model in modern designs because it is the only one that scales to per-VRF routing and that supports distributed anycast gateway.

The lesson's planner defaults to symmetric IRB with one Layer-3 VNI per VRF and one Layer-2 VNI per subnet.

### The distributed anycast gateway and the failure-recovery trade-off

The **distributed anycast gateway** model is the recommended default for production. Every leaf that hosts a VNI advertises the same anycast gateway IP, and the VM's local leaf is the active gateway. If the VM migrates to another leaf, the new leaf takes over as the gateway with the same IP. The VM does not need to update its ARP table, and the live migration completes in milliseconds.

The failure-recovery trade-off is that the anycast gateway requires a routing protocol (BGP EVPN with Type 5 NLRI) to advertise the gateway IP and to handle the next-hop change. A centralized gateway (a pair of leaves acting as the gateway for the VNI) is operationally simpler but has the active/standby failover time of 3-9 seconds, which is too slow for live migration. The lesson's planner models both and recommends distributed anycast gateway for production.

### Migration from a three-tier and the parallel run

The migration plan has three phases: **parallel run** (the new spine-leaf is built alongside the old three-tier, no traffic flows on the new fabric), **cutover** (one VLAN at a time is moved from the old to the new, with a documented rollback window), and **post-migration validation** (MAC/IP table parity, BGP session state, VXLAN tunnel state, east-west latency).

The parallel run is the longest phase (typically 4-8 weeks) and is when the new fabric is burned in. The cutover is the riskiest phase and is done one VLAN at a time, in maintenance windows, with a documented rollback plan (the VLAN is moved back to the old fabric by changing the gateway and the ARP table). The post-migration validation is the proof that the cutover was successful and is the basis for the postmortem.

The lesson's planner generates the cutover runbook with the VLAN list, the maintenance windows, the rollback procedure, and the validation criteria.

## Build It

The deliverable is `code/main.py`, a deterministic fabric planner. Inputs are: leaf count, server count per leaf, server-facing link speed, leaf-to-spine link speed, oversubscription target, and a list of tenants (each with a VNI and an RD). Outputs are: spine count, fabric capacity, bisectional bandwidth, VTEP/loopback/anycast gateway plan, BGP NLRI sample, VXLAN bridge-domain table, and a cutover runbook.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout. The printout includes:

- A **fabric summary** with the spine count, the fabric capacity, the bisectional bandwidth, and the achieved oversubscription.
- A **VTEP/loopback/anycast gateway plan** with one VTEP per leaf, one loopback per leaf, and one anycast gateway per VNI.
- A **BGP NLRI sample** for one VNI and one MAC, in the form that would appear in a `show bgp l2vpn evpn` output.
- A **VXLAN bridge-domain table** with one entry per VNI, listing the VTEPs that host the VNI.
- A **route-reflector session count** for the given leaf count and number of RRs.
- A **cutover runbook** with the VLAN list, the maintenance windows, and the rollback procedure.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| Fabric summary | Spine count, fabric capacity, bisectional bandwidth, oversubscription | Pass |
| VTEP/loopback plan | One VTEP per leaf; one loopback per leaf; no overlap with server subnet | Pass |
| Anycast gateway plan | One gateway IP per VNI; RD/RT encoded correctly | Pass |
| BGP NLRI sample | Type 2 NLRI for one MAC; type 5 NLRI for one prefix | Pass |
| VXLAN bridge-domain table | One entry per VNI; list of hosting VTEPs | Pass |
| Route-reflector count | Session count computed; client-to-client reflection enabled | Pass |
| Cutover runbook | VLAN list, maintenance windows, rollback procedure | Pass |
| MTU enforcement | Outer MTU 1550 on every underlay link | Pass |

## Ship It

The artifact is `outputs/fabric_plan.json` plus the printout. The JSON includes the fabric summary, the VTEP/loopback/anycast plan, the BGP NLRI sample, the bridge-domain table, the route-reflector count, and the cutover runbook. The output directory should also contain `bgp_evpn.conf` (the vendor-neutral BGP EVPN configuration skeleton) and `vxlan_bridge_domain.md` (the bridge-domain documentation).

## Exercises

1. **Compute the spine count for 64 leaves, 100 Gbps spine-leaf, 25 Gbps server-facing, 4:1 oversubscription.** Show the math. What is the achieved oversubscription if you use 16 spines instead of 8?

2. **Design the VTEP/loopback plan for 32 leaves with VTEP subnet 10.255.0.0/24 and loopback subnet 10.254.0.0/24.** What is the first VTEP? The first loopback? The last VTEP?

3. **Build a BGP EVPN Type 2 NLRI for the MAC 00:1A:2B:3C:4D:5E on VNI 10001 at the VTEP 10.255.1.5, with IP 172.16.1.42.** Show the encoding (RD, ESI, MAC length, IP length, VNI, VTEP).

4. **Symmetric vs asymmetric IRB.** Explain the failure mode of asymmetric IRB when the destination leaf does not know the source VNI. Why is symmetric IRB the recommended default?

5. **Route-reflector placement.** With 32 leaves, where should the route-reflectors be? On the spines? On a separate pair of switches? What is the failure model if the route-reflector is single-homed?

6. **MTU end-to-end.** A VM sends a 1500-byte packet. The VXLAN encapsulation adds 50 bytes. The outer IP path must support 1550-byte packets. What is the MTU configuration on the VM, the leaf server port, the spine-leaf link, the route-reflector-to-spine link, and the upstream router?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Spine-leaf | "Every leaf is one hop from every other leaf" | A Clos network with two stages: spines (middle) and leaves (edge); no spine-to-spine links |
| VXLAN | "Layer 2 over Layer 3" | RFC 7348 encapsulation with a 24-bit VNI, providing 16 million logical networks over IPv4/IPv6 |
| BGP EVPN | "The control plane for VXLAN" | RFC 7432 NLRI that distributes MAC/IP/VTEP information across the fabric |
| VTEP | "VXLAN Tunnel Endpoint" | A process on the leaf that encapsulates and decapsulates VXLAN frames |
| Anycast gateway | "The same gateway IP on every leaf" | A distributed gateway model where every leaf that hosts a VNI advertises the same IP |
| Symmetric IRB | "Route at both ends" | The newer IRB model: ingress leaf routes to a Layer-3 VNI, egress leaf routes to the destination |
| Asymmetric IRB | "Route only at ingress" | The older IRB model: ingress leaf routes and bridges; egress leaf only bridges |
| Route-reflector | "A BGP scaling primitive" | A BGP speaker that reflects routes from one client to other clients, avoiding a full iBGP mesh |
| Oversubscription | "More server-facing than fabric capacity" | The ratio of server-facing bandwidth to fabric capacity, typically 2:1 to 4:1 |
| Bisectional bandwidth | "The bandwidth across a middle cut" | The bandwidth that crosses an imaginary line through the middle of the fabric |

## Further Reading

- **RFC 7348** — *Virtual eXtensible Local Area Network (VXLAN)* — the VXLAN specification
- **RFC 7432** — *BGP MPLS-Based Ethernet VPN (EVPN)* — the original EVPN specification
- **RFC 8365** — *A Network Virtualization Overlay Solution Using Ethernet VPN (EVPN)* — the EVPN/VXLAN integration
- **RFC 9135** — *Integrated Routing and Bridging in EVPN* — symmetric IRB
- **RFC 9331** — *EVPN Virtual Private Wire Service (VPWS)* — point-to-point EVPN
- **Arista EOS Datacenter Design Guide** — vendor implementation
- **Cisco Nexus 9000 VXLAN EVPN Design Guide** — vendor implementation
- **Juniper Apstra EVPN/VXLAN Reference Design** — vendor implementation
- **NVIDIA Cumulus Linux VXLAN EVPN documentation** — open-source implementation
- **FRRouting EVPN documentation** — open-source implementation
- **SONiC VXLAN EVPN documentation** — open-source implementation
- **Clos, C. (1953). "A Study of Non-Blocking Switching Networks"** — the original Clos paper
- **Albert Greenberg et al. (2008). "VL2: A Scalable and Flexible Data Center Network"** — the modern Clos datacenter
