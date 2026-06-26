# PIM-SM Multicast Routing for Live Video Distribution

> This lesson builds a complete Protocol Independent Multicast Sparse Mode (PIM-SM) design for a live video distribution network that carries an enterprise town-hall stream from a single encoder in DC1 to roughly 3,500 receivers across 28 branch campuses and 6 data centers. We configure Any-Source Multicast groups 239.16.32.0/24, designate dual Rendezvous Points (RPs) with Anycast RP using MSDP, elect a Bootstrap Router (BSR) candidate from a pair of Catalyst 9500s running IOS XE 17.12, and reserve IGMP/MLD snooping capacity on the access tier. The Python tool emits an RP-set, BSR-priority, group-to-RP mapping, and SPT-switchover threshold plan that you can paste into Cisco IOS XE, Juniper Junos 22.4R3, and Arista EOS 4.30 configuration blocks without manual translation. All planning math is local — no probes, no live network, just deterministic, RFC 4601/7761/5059/6559-aware design output.

**Type:** Design Lab
**Languages:** Python 3.11+ (stdlib only), IOS XE 17.12 config, Junos 22.4R3, Arista EOS 4.30
**Prerequisites:** Lessons 08-12 (IGP/BGP fabric, spine-leaf, EVPN), basic multicast concepts, IGMPv3 familiarity
**Time:** ~110 minutes

## Learning Objectives

- Designate dual RPs with Anycast-RP + MSDP so a single PIM-SM domain survives RP loss inside 5 seconds, satisfying the operator-runbook SLO for live executive broadcasts.
- Compute a BSR priority ordering, hash-mask, and RP-set that maps every group in 239.16.32.0/24 to exactly one active RP across mixed-vendor fabrics.
- Plan IGMP/MLD snooping and PIM DR election on the access layer so a 3,500-receiver flash crowd cannot trigger a (*,G) prune storm on the L2 distribution.
- Calculate the SPT-switchover threshold that flips receivers from the shared RPT to source-specific shortest path trees at the right bandwidth, saving ~340 Mbps of replicated (*,G) state on the WAN tier.
- Produce vendor-specific configuration snippets (Cisco IOS XE, Juniper Junos, Arista EOS) that match the planning output and are copy-paste safe.
- Reason about PIM-SSM (232/8) and PIM-SSM boundary placement to offload OTT-class streams from the RP entirely.

## The Problem

GlobalCorp Financial runs a quarterly all-hands broadcast from a 4K H.265 encoder in the Chicago data center. The unicast version is fine, but the senior leadership refuses to fund a CDN contract and insists on running the broadcast over the corporate MPLS backbone. The current network is a hybrid: Cisco Catalyst 9500s in the DC and 12 large branches, Juniper MX204s in the European sites, and Arista 7800R3s in the new Hong Kong / Singapore spines. Today every site joins the multicast group 239.16.32.100 via a static `ip igmp static-group` on the WAN edge and the receiver count is small. Next quarter, the company plans to push the stream to every desk phone, lobby display, and atrium screen — that is roughly 3,500 receivers.

Three problems are visible before the broadcast even starts:

1. The RPs are statically configured, and one of them (RTP-CORE-1 in DC1) is the only device that knows the `rp-address` for 239.16.32.0/24. If that chassis fails or is reloaded for a software patch, every receiver sees 4-8 minutes of outage while IGP reconverges and IGMP membership re-establishes.
2. The shared RP-tree causes the WAN edge in Chicago to forward 12 copies of a 25 Mbps stream — one to every region — for every minute that receivers stay on the RPT. At 28 sites that is 300 Mbps of long-haul bandwidth that the corporate carrier bills back as premium transit, on top of the actual 25 Mbps being used.
3. The access switches are running IGMP snooping with no querier election configured, and the lobby displays in the new Singapore office are IGMPv2. The flash crowd of 280 lobby displays joining in 90 seconds causes PIM Assert messages to flap on the 10G uplinks.

The head of network engineering wants a deterministic plan: dual RPs in each region, Anycast-RP peering with MSDP, a BSR that elects the right device on first convergence, and a clear SPT-switchover threshold so the shared tree collapses on schedule. The CFO wants the billable bandwidth back. The auditor wants the design to be repeatable in a runbook.

## The Concept

### Why PIM-SM and not PIM-DM or PIM-SSM for this broadcast

PIM Dense Mode floods the entire domain and prunes receivers that are not interested. For a single source and a known receiver set, dense mode is technically simple but operationally hostile: a single 25 Mbps stream on a 100-node fabric sends 2.5 Gbps of "useless" multicast state everywhere during the prune window. PIM-SM keeps receivers on a shared RP-tree (RPT) until a switchover, and only then builds source-specific shortest path trees. That maps cleanly to the operational problem: the RP is a known entity, the source is fixed, and we want to flatten the tree once receivers stop joining.

PIM-SSM (Source-Specific Multicast) is preferable to PIM-SM for OTT streaming, but SSM requires IGMPv3 on every receiver and a hard-coded `(S,G)` channel. GlobalCorp's lobby displays run IGMPv2 firmware that the vendor will not patch. We therefore reserve 232.0.0.0/8 for the SSM-only inter-DC distribution (where we control every hop) and run 239.16.32.0/24 as full PIM-SM for the receiver-side broadcast.

### RP placement and Anycast-RP

PIM-SM elects a single RP per group range. A failed RP is unrecoverable inside the protocol — receivers stay on the RPT but the source registration times out at 210 seconds (the default Register-Suppression-Timeout) and the stream goes dark. The fix is to give two devices the same IP address (the Anycast-RP) and have them peer with MSDP to share active sources. The receiving routers see one RP; the two physical RPs sync via MSDP SA messages.

We place a paired RP in DC1 (Chicago), DC2 (London), and DC3 (Singapore). The Anycast-RP address is 10.255.255.1/32. The two physical RPs in each region hold loopbacks 10.255.0.1/32 and 10.255.0.2/32, advertised into IS-IS with high IP-preference. MSDP peerings are full-mesh between the six physical RPs. Anycast-RP gives us a worst-case failover of under 5 seconds because the receivers do not need to rejoin — the new physical RP already has the same IP and the PIM BSR does not need to republish.

### BSR election and hash-mask

RFC 5059 replaces the original BSR mechanism. The BSR distributes RP-to-group mappings inside Bootstrap Messages (BSM). When multiple RPs are candidates for the same group range, the receiving routers run a hash function: `((G + M) mod (2^31)) mod N_rp_candidates` against the candidate RP set, with M being the hash-mask length. The hash-mask is the most important knob. A small mask (e.g., `/0`, 0) causes every group in the range to map to the same RP, defeating the load-sharing goal. A mask close to the group range length (e.g., `/24` for 239.16.32.0/24) causes a near-random distribution across the candidate RPs.

For a single broadcast on 239.16.32.100, hash-mask selection is moot. We set the BSR hash-mask to 30 anyway so future one-to-many streams spread evenly across the candidate RP set.

### IGMP/MLD snooping, DR election, and the flash crowd

The L2 distribution is a pair of Cisco Catalyst 9300-48UXM stacks. IGMP snooping is on by default, but the querier election is driven by the IP address of the IGMP querier on each VLAN. If no querier is configured, the snooping switch with the lowest IP becomes querier. The fix is to set the L3 gateway / multicast router (the VTEP-facing SVI) as the querier with `ip igmp snooping querier` and to pin the DR via PIM DR-priority.

For the lobby-display flash crowd we pre-warm the access layer: on every IDF switch we configure `ip igmp join-group 239.16.32.100` on a designated port. This is sometimes called "static join" or "PIM helper" — the access switch stays on the RPT so when a receiver joins it does not have to wait for the PIM Join to propagate back to the RP.

### SPT-switchover threshold

The RPT sends one copy of the stream to each last-hop router with a downstream receiver. The SPT sends one copy per branch. With 28 sites, the RPT is wasteful once the source is known. The IOS XE default is to switch to the SPT on the first packet received (instant switchover). That is the wrong default for this design: instant switchover causes the first hop router to send a PIM Join to the source immediately, which can cause a 30-40 second outage during the first 5-10 receivers joining if the source is behind a slow IGP.

The right threshold is to keep receivers on the RPT for the first 60 seconds (so IGMP membership stabilizes) and then switch to SPT based on bandwidth, e.g., `spt-threshold 1000 100` — 1000 kbps for 100 seconds. The Python tool emits this as a vendor-neutral policy string.

### PIM-SSM boundary for inter-DC replication

The broadcast originates in Chicago and is mirrored to London and Singapore for local re-distribution. Between the DCs we use PIM-SSM with group range 232.16.32.0/24, source address the Chicago encoder's loopback (10.100.0.50/32), and an MSDP boundary at the WAN edges. This removes the inter-DC traffic from the RP-tree entirely and gives us deterministic latency on the trans-Pacific path.

## Build It

The Python tool is `code/main.py` and is fully stdlib-only. It is a planner, not a packet sender. It takes a static inventory of receivers, sites, and RP candidates, runs the BSR hash function exactly as RFC 5059 describes, computes the receiver-bandwidth break-even between RPT and SPT, and emits three vendor-specific configuration files plus a BSR/RP allocation report. Running `python3 main.py` from the lesson directory prints the design report and writes:

- `outputs/rp-set.txt` — the BSR hash output for each group in 239.16.32.0/24
- `outputs/cisco-ios-xe.conf` — Catalyst 9500 / Nexus 9300 config blocks
- `outputs/juniper-junos.conf` — MX204 config blocks
- `outputs/arista-eos.conf` — 7800R3 config blocks
- `outputs/bsr-report.md` — human-readable design summary

The tool models the inventory as a list of `@dataclass` records (`Site`, `Receiver`, `Rpcandidate`, `PimInterface`) and the core algorithm is a 30-line implementation of the BSR hash function. The SPT-threshold math is a 12-line calculation that takes the per-receiver bitrate, the per-site fan-out, and the long-haul transit cost, and returns the seconds-after-join before switchover is profitable.

```bash
$ cd 20-pim-sm-multicast-routing-for-live-video-distribution/code
$ python3 main.py
=== GlobalCorp PIM-SM Design Report ===
Group range: 239.16.32.0/24
Active groups: 16
Anycast-RP: 10.255.255.1/32
Physical RPs: 6 (DC1x2, DC2x2, DC3x2)
BSR hash-mask: 30
Hash winner for 239.16.32.100 -> rp-dc1-2 (10.255.0.2) priority 192
SPT-switchover: 60 s / 1000 kbps
PIM-SSM boundary: 232.16.32.0/24 source 10.100.0.50
Total RPT bandwidth: 0.70 Gbps (estimated)
Total SPT bandwidth (post-switchover): 0.03 Gbps
Savings: 700 Mbps / ~99% reduction on long-haul
```

## Use It

| Deliverable | Acceptance Criteria | Status |
|------------|--------------------|--------|
| `outputs/rp-set.txt` | Maps every group in 239.16.32.0/24 to a primary and backup RP from the 6 physical RPs. Hash function uses BSR hash-mask 30. | Produced by `main.py` |
| `outputs/cisco-ios-xe.conf` | Contains `ip pim rp-address 10.255.255.1`, `ip pim bsr-candidate`, `ip pim rp-candidate`, and IGMP snooping querier config. | Produced by `main.py` |
| `outputs/juniper-junos.conf` | Contains `set protocols pim rp static address 10.255.255.1`, BSR and MSDP stanzas. | Produced by `main.py` |
| `outputs/arista-eos.conf` | Contains `router pim`, `rp-address 10.255.255.1`, `bsr`, and `msdp` stanzas. | Produced by `main.py` |
| `outputs/bsr-report.md` | Lists the chosen primary/backup RP per group with the hash output, the SPT threshold, and the bandwidth-savings estimate. | Produced by `main.py` |
| RP failover time | Bounded by IGP convergence + PIM cache rebuild; design target < 5 s for anycast-RP loss. | Validated by walkthrough in the report |
| SPT switchover | Triggered at 1000 kbps sustained for 100 s, or 60 s after first IGMP join — whichever fires first. | Validated by `main.py` math |

## Ship It

Place the five output files in your change-management system (ServiceNow CR, NetBox config context, or Git repo). Apply the Cisco config during the Sunday maintenance window on Catalyst 9500s in DC1, the Juniper config to MX204s in DC2, and the Arista config to 7800R3s in DC3. Verify with `show ip pim rp mapping` (IOS XE), `show pim rps` (Junos), or `show ip pim rp` (EOS) that the chosen RP matches the BSR hash output. Capture `show ip mroute` count of `(*,G)` and `(S,G)` entries before and after the broadcast; the SPT switchover should halve the `(*,G)` count within 90 seconds of the broadcast start.

The acceptance sign-off lives in the runbook at `runbooks/pim-sm-failover.md` and the bandwidth savings figure goes into the monthly carrier-billing reconciliation under the line item "MPLS multicast reduction".

## Exercises

1. **Hash-mask sensitivity.** Re-run `main.py` with hash-mask lengths 0, 4, 8, 16, 24, 30, and 31. For each, list which RP wins the BSR hash for 239.16.32.100. Explain why a network operator would never set hash-mask to 0 in a mixed-vendor fabric.
2. **Anycast-RP convergence.** Design a failure scenario where the primary physical RP in DC1 loses its MSDP session to the secondary. Within what window do receivers in DC2 see a stream outage? What IGP metric on the loopback would you set to bias BSR election toward the closer secondary?
3. **SSM migration.** Identify which receiver segments in the inventory can be moved from PIM-SM (239/8) to PIM-SSM (232/8). What IGMP version requirement blocks the lobby displays, and what is the smallest firmware upgrade that would unlock SSM for them?
4. **Flash crowd modeling.** The 280 lobby displays in Singapore join within 90 seconds. Compute the IGMP report rate at the access tier and determine whether the default IGMP report suppression on the IDF switches hides the storm from the 10G uplinks. Justify a `ip igmp snooping immediate-leave` decision.
5. **SPT threshold trade-off.** The current threshold is 1000 kbps for 100 seconds. Recompute for a 50 Mbps 4K H.265 stream with the same 28-site fan-out. Is the threshold still profitable, or does instant-SPT become the right default? Show the math.
6. **MSDP SA cache poisoning.** The MSDP mesh uses default SA-cache limits. What is the largest group range you would allow in an SA-cache entry, and how would you filter SA messages from RPs you do not own? Provide an IOS XE filter-list stanza.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Rendezvous Point (RP) | "The meeting point for sources and receivers" | A router that knows the active source for a (*,G) entry and tunnels the first packets to receivers via PIM Register encapsulation until the SPT is built. |
| Anycast-RP | "Two RPs share one IP" | A pair of physical routers announce the same /32 from different sites; MSDP keeps their source registrations in sync so the loss of one is transparent to receivers. |
| BSR | "The router that hands out the RP list" | Bootstrap Router — a PIM-SM role (RFC 5059). It collects candidate-RP advertisements, computes the RP-set, and floods it inside Bootstrap Messages. |
| MSDP | "Source advertisement between RPs" | Multicast Source Discovery Protocol — TCP-based protocol (RFC 3618) used to share active sources between Anycast-RP peers. |
| SPT switchover | "The moment the shortest path tree takes over" | The point at which the last-hop router sends a PIM (S,G) Join directly to the source, replacing the (*,G) RPT path. |
| PIM-SSM | "Source-specific multicast" | PIM-SSM (RFC 4607/6559) uses (S,G) state only; no RP, no (*,G) state, no MSDP. |
| IGMP snooping | "The switch listens for joins" | Layer 2 feature that suppresses multicast flooding by only forwarding groups out ports with active IGMP reports. |
| Register tunnel | "Source-to-RP encapsulation" | A PIM Register message is a unicast PIM packet from the source's DR to the RP, encapsulating the original multicast data. |

## Further Reading

- RFC 4601 — Protocol Independent Multicast - Sparse Mode (PIM-SM) Protocol Specification. The canonical PIM-SM reference.
- RFC 7761 — Protocol Independent Multicast - Sparse Mode (PIM-SM) Protocol Specification (Revised). Clarifies BSR hashing, Embedded-RP, and PIM Assert semantics.
- RFC 5059 — Bootstrap Router (BSR) Mechanism for PIM. Defines BSR election, candidate-RP advertisement, and the hash function.
- RFC 6559 — A Reliable Transport Mechanism for PIM. PIM-SSM transport over TCP, useful for lossy long-haul paths.
- Cisco — *Multicast Quick-Start Configuration Guide*, IOS XE 17.12. Catalyst 9500 / Nexus 9300 PIM-SM and IGMP snooping examples.
- Juniper — *Multicast Features Overview*, Junos 22.4R3. MX204 PIM, MSDP, and BSR configuration.
- Arista — *EOS 4.30 Multicast Configuration Guide*, 7800R3. PIM-SM, Anycast-RP, and IGMP/MLD snooping reference.
- *Developing IP Multicast Networks* — Beau Williamson. The classic 1-volume reference; the Anycast-RP chapter is still the cleanest in print.
