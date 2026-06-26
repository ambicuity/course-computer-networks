# Cloud VPC Connectivity Plan to Branch Office VPN Plan

> A mid-size enterprise with 200 to 5,000 employees typically runs **20% to 60% of its workloads in the public cloud** (AWS, Azure, or GCP) while keeping the rest on premises, and the network team is asked to make the two halves feel like one datacenter. The lesson turns that goal into a runnable design by combining the **AWS VPC + Transit Gateway** model, **Azure vWAN / Virtual WAN hubs**, **GCP VPC with Cloud Router**, and three VPN families — **IPsec IKEv2 site-to-site** (RFC 4301, RFC 7296), **WireGuard** (a modern UDP-based kernel tunnel, RFC-like draft), and **SD-WAN overlays** (Cisco Viptela, Velocloud, Meraki, Aruba EdgeConnect). The deliverable is a Python planner that ingests on-prem CIDRs, cloud VPC CIDRs, and a list of branch offices, then emits a non-overlapping **CIDR plan**, an **IPsec tunnel + BGP** topology with private ASN allocation (per **RFC 6996**), an **MTU / MSS** clamping plan that survives the **VPN MTU overhead** (the 50-70 byte overhead of IPsec ESP + UDP + outer IP), a **DNS resolver strategy** (AWS Route 53 Resolver endpoints, Azure Private DNS Resolver, GCP Cloud DNS), and a **cost estimator** that compares Internet VPN, Direct Connect / ExpressRoute / Cloud Interconnect, and SD-WAN. The artifact is a single `vpc-bgp-vpn-plan.json` ready to hand to a cloud networking engineer.

**Type:** Project
**Languages:** Python (stdlib: dataclasses, json, ipaddress, itertools, statistics, textwrap)
**Prerequisites:** Phase 7 (Network Layer and Routing — BGP fundamentals), Phase 9 (Internet Protocols — IPv4/IPv6 addressing), Phase 16 (Secure Communication and Web Security — IPsec, IKE)
**Time:** ~180 minutes

## Learning Objectives

- Allocate non-overlapping **VPC CIDRs** for a multi-account, multi-VPC topology using **10.0.0.0/8** (or **100.64.0.0/10** CGNAT space, RFC 6598) and a documented hub-and-spoke or full-mesh topology.
- Choose between **AWS Transit Gateway** (TGW, up to 5,000 attachments per region), **AWS VPC peering** (1:1 only, no transitive routing), **Azure vWAN** (Microsoft-managed hub), **GCP VPC** (global, subnet in any region), and **Cisco/Arista MPLS** for the underlay.
- Build an **IPsec IKEv2** configuration with **BGP over the tunnel** (per **RFC 4364**), a **16-byte BGP MD5 auth** (deprecated) or **TCP-AO** (RFC 5925) for newer routers, **BFD** for fast failure detection, and a **DPD** heartbeat for dead-peer detection.
- Calculate the **MTU path** from a workload in a VPC to a host on-prem: typical Internet VPN path MTU is **1,400 bytes** (1,500 - 50 IPsec - 8 UDP - 20 outer IP), typical Direct Connect is **8,500-9,000** (jumbo frames) but usually clamped to **1,500**.
- Configure **PMTUD** (Path MTU Discovery, RFC 1191, RFC 8201) and **MSS clamping** (RFC 879 §2) so that TCP sessions don't fragment, and document the clamping point on every firewall along the path.
- Compute the **monthly cost** of three designs: Internet VPN, Direct Connect / ExpressRoute / Cloud Interconnect, and SD-WAN, against a 100 Mbps and 1 Gbps baseline, and recommend one.

## The Problem

A 1,800-person SaaS company, "Northbeam Software," runs its production platform in **AWS us-east-1** (three VPCs: prod, staging, shared-services), its data warehouse in **Snowflake on AWS**, and its corporate IT (file shares, AD, payroll, internal wiki) in two on-premises datacenters in **Ashburn, VA** and **Salt Lake City, UT**, plus **24 branch offices** (sales offices, R&D labs, customer support centers). Users in branch offices need to reach the AWS workloads as if they were on the corporate LAN.

The current state: each branch office has a consumer-grade VPN terminating on the AWS **Site-to-Site VPN** service, the datacenter has two redundant IPsec tunnels to a **TGW**, and the company DNS is on-prem with **unbound** forwarding to **1.1.1.1**. Pain points: (1) AWS Site-to-Site VPN costs **$0.05/hour per tunnel** (~$36/month per tunnel), which for 24 branches is **$1,728/month** before bandwidth; (2) MTU is misconfigured on the branch firewalls, so large SQL backups fragment and stall over the tunnel; (3) DNS resolution for **internal AWS service endpoints** (`*.prod.us-east-1.rds.amazonaws.com`) takes the long way through on-prem, adding 30 ms of latency; (4) when an AWS Direct Connect link goes down, failover to backup VPN takes **45 seconds** because the on-prem firewalls do not run **BFD**.

The lesson is to design a single plan that fixes all four pain points and document the cost trade-off.

## The Concept

Cloud-to-on-prem connectivity is a routing problem dressed as a security problem. The choices are about **topology** (hub-spoke, full-mesh, transit), **transport** (Internet VPN, private interconnect, SD-WAN), **protocol** (static, BGP, OSPF), and **address plan** (non-overlapping CIDRs). Each choice has a cost and an operational consequence.

### Cloud network primitives: VPC, VNet, VPC

The three hyperscalers all have a "virtual private cloud" object:

- **AWS VPC** — regional, up to 5 VPCs per region per account by default (soft limit). A VPC is a CIDR block from **/16 to /28**, carved into **subnets** mapped to **Availability Zones**. Subnets are public (route to **Internet Gateway**) or private (route to **NAT Gateway**). VPC peering is **non-transitive** (A peered to B and B peered to C does not mean A reaches C). **Transit Gateway** is the AWS-native hub that solves the transitive-routing problem; up to **5,000 attachments** and **50 Gbps per VPC attachment**.
- **Azure VNet** — regional, similar CIDR limits. **Virtual WAN (vWAN)** is the Microsoft-managed hub. **ExpressRoute** is the private interconnect equivalent of Direct Connect.
- **GCP VPC** — **global**, not regional. Subnets can span regions. **Cloud Router** and **Cloud Interconnect** are the equivalents.

The lesson targets **AWS** because it is the most-documented target and because the on-prem customer already uses it; the planner emits a vendor-neutral BGP/IPsec plan that an Azure or GCP engineer can adapt with minimal changes.

### CIDR plan: avoiding overlap

The single most common mistake in cloud connectivity is overlapping CIDRs. If the on-prem network uses **10.0.0.0/16** and the AWS VPC also uses **10.0.0.0/16**, the **BGP** session cannot tell which prefix is which, and traffic black-holes. The fix is a documented CIDR registry with non-overlapping allocations:

| Use case | CIDR | Notes |
|---|---|---|
| On-prem datacenter 1 (Ashburn) | 10.10.0.0/16 | Corporate IT, AD, file shares |
| On-prem datacenter 2 (Salt Lake) | 10.20.0.0/16 | Backup DR, secondary AD |
| Branch offices | 10.100.0.0/16 | /24 per branch, 254 branches of room |
| AWS prod VPC | 10.50.0.0/16 | Subnets /20 per AZ |
| AWS staging VPC | 10.51.0.0/16 | |
| AWS shared-services VPC | 10.52.0.0/16 | AD connector, Route 53 Resolver |
| AWS TGW peer | 10.255.0.0/16 | Reserved for future VPCs |
| Private interconnect (DX) | 10.250.0.0/16 | /30 subnets per VIF |
| VPN overlay (inside-tunnel) | 169.254.0.0/16 | RFC 3927 link-local alt |

The lesson's planner enforces non-overlap by computing the **set of reserved ranges** and rejecting allocations that intersect.

### IPsec IKEv2: the modern tunnel

**IPsec** is the IETF-defined tunnel (RFC 4301-4309 for IPsec v2, RFC 7296 for **IKEv2**). A typical modern configuration uses:

- **IKEv2** (RFC 7296) — faster setup, NAT traversal built-in, supports MOBIKE.
- **AES-256-GCM** for encryption (with **AES-GCM** providing both confidentiality and integrity, so no separate ESP HMAC-SHA256 needed). Note: AES-GCM consumes **one MTU of buffer** for the ICV.
- **SHA-256** or **SHA-384** for PRF (pseudo-random function in IKEv2).
- **Diffie-Hellman group 14** (2,048-bit MODP, RFC 3526) or **group 19/20** (256/384-bit ECP).
- **PFS** (Perfect Forward Secrecy) — re-keys the symmetric key for every SA so compromise of one long-term key does not retroactively decrypt traffic.
- **Lifetime**: IKE SA 24 hours, Child SA 1 hour (or 8-16 hours depending on vendor).
- **DPD** (Dead Peer Detection, RFC 3706) — sends a heartbeat every 10 seconds; if 3 are missed, the SA is torn down and a new one negotiated.

The lesson's planner outputs a vendor-neutral IPsec configuration skeleton that maps cleanly to **strongSwan**, **Cisco IOS-XE**, **Juniper Junos**, **Palo Alto PAN-OS**, and **AWS Site-to-Site VPN** (which is itself a managed strongSwan).

### BGP over IPsec: the modern control plane

Static routes work for 2-3 tunnels. Beyond that, BGP is required. The plan uses **eBGP** (RFC 4271) between each on-prem router and the AWS **VPN CloudHub** or **Transit Gateway** with these parameters:

- **Private ASN** from **64512-65534** (RFC 6996 — the 4-byte ASN range reserved for private use, extended from the original 64512-65535). Each branch gets a unique ASN.
- **eBGP multihop** of **2** (BGP peers are typically 1 hop away, but the tunnel inner-IP is on each end of the IPsec SA so 2 hops is the default).
- **BGP authentication**: **MD5** (RFC 2385) for legacy or **TCP-AO** (RFC 5925) for modern; the planner emits both forms.
- **BFD** (Bidirectional Forwarding Detection, RFC 5880) at **50 ms × 3** for sub-second failure detection — critical for avoiding the 45-second failover in the problem section.
- **Route filtering** by prefix-list: only announce the on-prem summary (e.g., 10.10.0.0/16), not specific /24s, to keep the BGP table small.
- **MED / LOCAL_PREF** for primary/backup preference across two tunnels.

### MTU and MSS clamping

The single most common operational issue with IPsec VPN is **fragmentation**. The math:

- A standard Ethernet frame is **1,500 bytes**.
- IPsec ESP adds **~50 bytes** (16 IV + 16 ICV + 8 ESP header + 4 ESP trailer, plus 4-byte outer IP header for ESP-NULL or 50+ for ESP+UDP).
- GRE + IPsec adds another **24 bytes** (4 GRE + 20 outer IP).
- After encryption, the effective **IP MTU** of the tunnel is typically **1,400 to 1,430 bytes**.

If the server sends a 1,500-byte IP packet, it will be **fragmented** by the tunnel ingress. Many cloud-provider firewalls (AWS Security Groups, Azure NSG) silently drop fragmented packets or perform poorly under fragmentation.

The fix is **PMTUD** (Path MTU Discovery, RFC 1191 for IPv4, RFC 8201 for IPv6) plus **MSS clamping** at the tunnel endpoints (RFC 879 §2 — "The TCP MSS option shall be set to the MTU minus 40"). The lesson's planner computes the safe MSS for every transport (1,400 byte MTU ⇒ MSS 1,360) and emits the iptables / nftables rule to clamp it.

### DNS strategy

Three patterns exist for cloud-to-on-prem DNS:

1. **All-on-prem** — workloads in VPC use on-prem DNS via the VPN. Simple, but adds latency (10-30 ms) for every AWS-internal lookup and saturates the tunnel with DNS traffic.
2. **All-in-cloud** — workloads use **AWS Route 53 Resolver** with **forwarding rules** to on-prem for internal zones, and the on-prem DNS uses **Route 53 Resolver endpoints** for AWS-internal zones. Lower latency but requires bi-directional forwarding.
3. **Split-horizon** — workloads use cloud DNS for cloud zones and on-prem DNS for on-prem zones, joined at a **Route 53 Resolver** that handles the routing. Most complex but lowest latency and best operational separation.

The lesson's planner defaults to **option 3 (split-horizon)** with **Route 53 Resolver endpoints** in each VPC, because the cost is small (~$0.125/hour per endpoint) and the operational benefit is large.

### Cost comparison

For the 1,800-person, 24-branch scenario:

| Option | CapEx | Monthly OpEx | Notes |
|---|---|---|---|
| Internet VPN (AWS Site-to-Site VPN, $0.05/hr per tunnel × 24 branches × 2 tunnels) | $0 | $1,728 + data out ($0.09/GB after first 100GB) | Cheapest CapEx; per-GB egress adds up |
| Direct Connect (1 Gbps, $0.30/hr + data out $0.02/GB) | ~$5,000 install | ~$220 + data out | Predictable cost, private, jumbo MTU |
| SD-WAN (Cisco Viptela, Velocloud, etc.) | ~$50,000 install | ~$2,000 per branch (incl. appliance + cloud subscription) | Best when branch network is itself complex |
| Transit Gateway + Direct Connect (current best practice) | $0 | ~$0.07/hr per attachment + DX + data out | Lowest operational complexity |

The lesson's planner emits a per-option monthly cost estimate and a recommendation based on the user's branch count and bandwidth budget.

## Build It

The deliverable is `code/main.py`, a stdlib-only cloud-to-on-prem connectivity planner. Inputs are the on-prem CIDRs, the AWS VPC CIDRs, the branch list, and the bandwidth budget. Outputs are:

- A **non-overlapping CIDR plan** with summary routes.
- A **VPN topology** (tunnel count per branch, BGP peer list, ASN plan).
- An **IPsec configuration skeleton** (strongSwan, Cisco IOS-XE, Juniper Junos, AWS Site-to-Site VPN).
- An **MTU/MSS clamping plan** with concrete values for every transport.
- A **DNS resolver strategy** with Route 53 Resolver endpoint layout.
- A **cost estimate** for Internet VPN vs Direct Connect vs SD-WAN.

Run it: `python3 main.py`. The output includes the JSON plan, the IPsec skeleton, and a per-option cost table.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| CIDR plan | Non-overlapping, summary-friendly, RFC 1918 + RFC 6598 documented | Generated |
| VPN topology | One IPsec tunnel per branch (×2 for redundancy), BGP peers listed | Generated |
| IPsec config | Vendor-neutral, AES-256-GCM, SHA-256 PRF, DH-14, PFS, DPD 10s×3 | Generated |
| BGP config | Private ASNs (RFC 6996), MD5 + TCP-AO, BFD 50ms×3 | Generated |
| MTU / MSS plan | Path MTU 1,400, MSS clamp 1,360, iptables/nftables rule emitted | Generated |
| DNS strategy | Route 53 Resolver endpoints in each VPC, split-horizon forwarding | Generated |
| Cost estimate | Per-option monthly cost, recommendation, payback period | Generated |

## Ship It

The artifact is `outputs/vpc-bgp-vpn-plan.json` plus `outputs/ipsec-strongswan.conf`, `outputs/ipsec-cisco-iosxe.txt`, `outputs/ipsec-juniper-junos.txt`, and `outputs/cost-comparison.md`. The JSON is the design-of-record, the IPsec files are vendor-specific day-one configs, and the cost document is the budget-review input.

To regenerate after a change: edit the on-prem/VPC CIDR list at the top of `code/main.py` and re-run. The output is deterministic.

## Exercises

1. **CIDR collision**: a junior engineer assigned **10.50.0.0/16** to a new VPC. The on-prem network uses **10.50.0.0/16** for the Ashburn datacenter. Show the symptom (BGP session flapping, black-holed traffic), the diagnosis (overlapping BGP prefix advertisement), and the fix (re-number the VPC to **10.51.0.0/16** with a change window).
2. **IPsec MTU**: a workload in the prod VPC transfers a 1.2 MB file to an on-prem server over the VPN. What TCP MSS does the workload use? If the firewall on-prem does not clamp MSS, what happens? Show the symptom (slow transfer, high retransmits), the diagnosis (large packets fragmenting, some fragments dropped), and the fix (clamp MSS to 1,360 on the tunnel ingress).
3. **BGP failover math**: with BFD at 50 ms × 3, what is the failover time of an IPsec + BGP session when the underlay link drops? Compare to **BGP hold-time of 180 seconds** (default). Why is the BFD value so much smaller?
4. **Direct Connect vs VPN**: a 1 Gbps Direct Connect at $0.30/hr + $0.02/GB egress vs 2× AWS Site-to-Site VPN at $0.05/hr/tunnel + $0.09/GB egress. At what monthly egress volume is Direct Connect cheaper? Show the break-even calculation.
5. **SD-WAN rollout**: the company grows from 24 to 60 branches. Build the SD-WAN cost model (appliance + cloud subscription) and compare against continuing with AWS Site-to-Site VPN. What is the 5-year TCO difference?
6. **DNS resolver design**: the company wants **AWS endpoints** (`*.amazonaws.com`) resolved locally in each VPC without going on-prem. Show the Route 53 Resolver rule set, the inbound endpoint for on-prem-to-VPC queries, and the forwarding rules for the corporate zone `corp.northbeam.io`.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| VPC / VNet | "Cloud network" | An isolated virtual network in AWS / Azure / GCP; CIDR-based, regional (or global in GCP) |
| Transit Gateway | "Cloud hub" | AWS-native hub that interconnects VPCs and VPNs at scale (up to 5,000 attachments) |
| IPsec IKEv2 | "VPN tunnel" | RFC 7296 — the modern tunnel negotiation; supports MOBIKE, NAT-T, PFS |
| ESP / AH | "Encapsulation" | Encapsulating Security Payload (encryption + optional integrity) vs Authentication Header (integrity only) |
| BGP over IPsec | "Dynamic VPN" | Running BGP inside the IPsec tunnel so prefixes are exchanged dynamically, not statically configured |
| RFC 6996 | "Private ASN" | 4-byte ASN range 4,200,000,000-4,294,967,294 (extended); commonly 64512-65534 for 16-bit |
| BFD | "Fast failover" | RFC 5880 — sub-second failure detection for BGP / OSPF / static routes |
| MTU / MSS | "Packet size" | Maximum Transmission Unit / TCP Maximum Segment Size; clamp MSS to MTU-40 to avoid fragmentation |
| PMTUD | "Path discovery" | RFC 1191 / RFC 8201 — discover end-to-end MTU via ICMP / ICMPv6 too-big messages |
| Direct Connect | "Private line" | AWS / Azure / GCP dedicated private interconnect to the cloud provider |
| SD-WAN | "Branch VPN+" | Software-defined WAN overlay (Viptela, Velocloud, Meraki) with central policy and dynamic path selection |
| Route 53 Resolver | "Cloud DNS hub" | AWS-managed DNS service with inbound / outbound endpoints for VPC ↔ on-prem DNS forwarding |
| AWS Site-to-Site VPN | "Managed IPsec" | AWS-managed IPsec VPN service; $0.05/hour per tunnel, two tunnels per connection for redundancy |

## Further Reading

- **AWS VPC documentation** (docs.aws.amazon.com/vpc) — the authoritative source for VPC, TGW, and Site-to-Site VPN.
- **AWS Transit Gateway** (aws.amazon.com/transit-gateway) — pricing and limits.
- **RFC 4301** (Security Architecture for IP), **RFC 7296** (IKEv2), **RFC 4364** (BGP/MPLS IPsec VPNs).
- **RFC 6996** (Autonomous System Reservation for Private Use) — 4-byte private ASNs.
- **RFC 5925** (TCP-AO) — modern TCP authentication option replacing MD5.
- **RFC 5880** (BFD) — Bidirectional Forwarding Detection.
- **RFC 1191** (Path MTU Discovery, IPv4), **RFC 8201** (PMTUD, IPv6), **RFC 879** (TCP MSS option).
- *AWS Networking Cookbook* (Jhalak Modi, Packt 2023) — practical AWS networking recipes.
- *Cloud Native Data Center Networking* (Dinesh G. Dutt, O'Reilly 2019) — the philosophy of cloud-native DC design.
- *Network Warrior* (Gary Donahue, 2nd ed., O'Reilly 2011) — the on-prem side of the same problem.