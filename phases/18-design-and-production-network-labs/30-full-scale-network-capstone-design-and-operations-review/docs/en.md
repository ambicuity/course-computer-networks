# Capstone: multi-site integrated network design and production operations review

> A network that cannot explain itself — every subnet, every BGP session, every firewall rule, every on-call alert — is not a network that can be trusted in production. This capstone synthesizes the entire Phase 18 curriculum into one build: define a four-site enterprise (HQ, Branch-A, Branch-B, Cloud VPC), validate the addressing plan, routing design, redundancy posture, security baseline, QoS architecture, and monitoring coverage in a single Python program, and score the design against a 44-point production-readiness rubric before the first maintenance window opens.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 18 Lessons 01–29 — addressing and VLAN design (Lesson 05), campus network design (Lesson 01), cloud VPC connectivity (Lesson 03), monitoring and alerting runbook (Lesson 04), OSPF multi-area convergence (Lesson 08), BGP multihoming with two ISPs (Lesson 09), VRRP first-hop redundancy (Lesson 13), DHCP snooping and DAI (Lesson 14), 802.1X wired NAC (Lesson 15), DSCP marking and LLQ QoS (Lesson 24), syslog and NTP correlated logging (Lesson 25), network documentation portfolio (Lesson 07), and production cutover rehearsal (Lesson 29)
**Time:** ~150 minutes

## Learning Objectives

- Design a four-site enterprise topology — HQ, two regional branches, and a cloud VPC — with a consistent VLAN numbering scheme, non-overlapping IP address plan partitioned into /22 per-site blocks, and an OSPF multi-area hierarchy, and articulate why each choice reduces operational risk.
- Configure BGP dual-homing at HQ with two upstream ISPs using LOCAL_PREF asymmetry for outbound path selection and AS-path prepending on the secondary ISP for inbound traffic preference, and explain how BFD reduces inter-AS failover from 90 seconds to under 1 second.
- Apply VRRP to every user-facing gateway at all sites, with alternating master/backup assignments for load sharing, BFD-tracked uplinks, and a preempt delay that prevents a recovering master from seizing the VIP before OSPF has converged.
- Implement a four-layer security baseline: VLAN segmentation with DHCP snooping and Dynamic ARP Inspection, 802.1X EAP-TLS port authentication on all user VLANs, a zone-based firewall policy at every trust boundary, and SNMPv3 with no community strings.
- Mark voice traffic DSCP EF and queue it in a Low Latency Queue, mark video DSCP AF41 and queue it in CBWFQ, apply QoS policy to all WAN links, and explain why an unmarked cloud WAN link is a priority-queue gap even when on-premises interfaces are correctly configured.
- Run the Python production-readiness reviewer against the full design, interpret every PASS/WARN/FAIL finding by tracing it to the Phase 18 lesson that produced the correct configuration, and generate a prioritized remediation plan suitable for Change Advisory Board review.

## The Problem

Meridian Technologies is a fintech with 340 employees across three physical sites — a headquarters in Austin (TX), a secondary engineering office in Denver (CO), and a customer-support center in Charlotte (NC) — plus a production cloud workload running in AWS us-east-1. The network was built incrementally over nine years by three different teams. HQ was designed by a Cisco partner in 2015 with a collapsed-core architecture and a flat /22 address space. Denver was added in 2018 by an internal team using a VLAN scheme that collides with the HQ numbering. Charlotte was opened in 2020 by outsourcing the switch configuration to a local VAR who used the 192.168.0.0/16 range — the same range already in use at HQ for guest Wi-Fi. The AWS VPC was created in 2021 by the cloud team without consulting networking; they chose a /16 block that overlaps the Denver WAN transit links.

The result is a network that routes packets most of the time but cannot survive a rigorous production-readiness review. There are three OSPF areas that all share area 0 but use the same area ID for different physical regions, so a link flap in Charlotte propagates an LSA storm to Austin. The BGP at HQ has a single upstream ISP; the secondary ISP is cabled but not configured because nobody had time to test it. Denver has VRRP on the data VLAN but not on the voice VLAN, so a core switch failure at Denver drops every active call. Charlotte has no 802.1X — anyone who plugs a laptop into an ethernet port reaches the internal network. None of the three sites have DSCP markings on the egress WAN interface, so voice and video packets compete with bulk file transfers for the same 100 Mbps MPLS circuit. Monitoring exists but it is six Zabbix dashboards maintained by two people who leave the company next month.

The board has approved a modernisation budget. Before a dollar is spent, the CTO has asked for a written production-readiness assessment that identifies every gap, quantifies the risk of each gap, and proposes a phased remediation plan. This lesson produces the assessment tool: a Python program that models the target-state design, validates it against the production-readiness rubric developed across all 29 prior Phase 18 lessons, and emits a scored report that the engineering team can defend in front of the CAB.

## The Concept

The capstone design rests on four invariants that every enterprise multi-site network must satisfy before a production sign-off: no address overlap, full path redundancy, explicit security policy at every trust boundary, and observable traffic with linked runbooks. The sections below walk through each layer with enough specificity that the Python reviewer can test each invariant programmatically.

### Site topology and physical connectivity

The target design has four sites connected in a hub-and-spoke WAN with a secondary cloud spoke:

```
                    ISP-1 (AS 64512)   ISP-2 (AS 64513)
                     172.16.1.0/30      172.16.2.0/30
                           │                  │
                    ┌──────▼──────────────────▼──────┐
                    │    HQ — Austin (AS 65001)       │
                    │   Core-A  ────────  Core-B      │
                    │  (VRRP M)          (VRRP B)     │
                    │   OSPF Area 0 — backbone        │
                    └──────────────┬─────────────────-┘
              MPLS WAN             │              MPLS WAN
       172.16.10.0/30              │         172.16.20.0/30
              │                   │ Direct Connect            │
  ┌───────────▼──────────┐        │ 172.16.30.0/30   ┌───────▼───────────────┐
  │  Branch-A — Denver   │        │                  │  Branch-B — Charlotte  │
  │  OSPF Area 1 (stub)  │        │                  │  OSPF Area 2 (stub)    │
  │  BR-A-Sw1 / BR-A-Sw2 │        │                  │  BR-B-Sw1 / BR-B-Sw2  │
  │  10.20.0.0/22        │        │                  │  10.30.0.0/22          │
  └──────────────────────┘        │                  └────────────────────────┘
                          ┌───────▼──────────────────┐
                          │  Cloud VPC — AWS us-east-1│
                          │  10.40.0.0/16             │
                          │  App:  10.40.10.0/24      │
                          │  DB:   10.40.20.0/24      │
                          │  Mgmt: 10.40.99.0/24      │
                          └──────────────────────────-┘
```

HQ is the OSPF backbone (Area 0) and the sole BGP speaker. Both branches run OSPF stub areas (Area 1 and Area 2) to suppress external LSA flooding. The cloud VPC is reachable via iBGP over AWS Direct Connect. All four sites live inside 10.0.0.0/8, partitioned into distinct /22 site blocks.

### Addressing and VLAN plan

The addressing plan uses a structured hierarchy that encodes site, VLAN function, and host range in the third octet. Every subnet is a /24. Within each site block the third octet is the VLAN function number: .10 = user data, .20 = voice, .30 = video, .40 = server, .50 = printer, .99 = management. VLAN IDs follow a site-offset rule — HQ uses the raw function number (VLAN 10, 20, 30…), Branch-A Denver adds 100 (VLAN 110, 120, 130…), Branch-B Charlotte adds 200 (VLAN 210, 220, 230…). This makes every VLAN ID globally unique across all physical sites.

| Site | Block | OSPF Area | WAN Transit |
|------|-------|-----------|-------------|
| HQ Austin | 10.10.0.0/22 | 0 (backbone) | 172.16.1.0/30 (ISP-1), 172.16.2.0/30 (ISP-2) |
| Branch-A Denver | 10.20.0.0/22 | 1 (stub) | 172.16.10.0/30 |
| Branch-B Charlotte | 10.30.0.0/22 | 2 (stub) | 172.16.20.0/30 |
| Cloud VPC | 10.40.0.0/16 | none | 172.16.30.0/30 |
| Mgmt OOB | 10.99.0.0/24 | n/a | console server |

WAN transit links use 172.16.0.0/12 space and are never redistributed into the IGP. They are present only in BGP next-hop and OSPF point-to-point configurations.

### Routing design — OSPF multi-area with BGP dual-homing

**OSPF hierarchy (references Lesson 08):**

Area 0 runs on the HQ core switches Core-A and Core-B. Both switches are ABRs for Area 1 (Denver) and Area 2 (Charlotte). The dual-ABR design means that a single core switch failure at HQ does not partition the OSPF backbone — the surviving ABR continues to inject Type 3 summary LSAs into the branch stub areas. Branches run as stub areas, which blocks all Type 5 external LSAs. The branches receive only a single Type 3 default route from HQ; this keeps branch OSPF databases small and prevents BGP prefix withdrawals at HQ from triggering full SPF recalculations in Denver and Charlotte.

```
Area 0 (HQ) — Core-A loopback 10.10.99.1/32, Core-B loopback 10.10.99.2/32
Area 1 (Denver, stub) — BR-A-Sw1 loopback 10.20.99.1/32
Area 2 (Charlotte, stub) — BR-B-Sw1 loopback 10.30.99.1/32
```

**BGP dual-homing at HQ (references Lesson 09):**

Two eBGP sessions: ISP-1 (AS 64512) on 172.16.1.2 with LOCAL_PREF 200, and ISP-2 (AS 64513) on 172.16.2.2 with LOCAL_PREF 100. HQ prefers ISP-1 for all outbound traffic because 200 > 100. For inbound traffic, ISP-2 receives the enterprise aggregate with the HQ ASN prepended three times, making the AS_PATH artificially longer so that upstream routers prefer ISP-1. BFD runs on both sessions with a 300 ms interval; a link failure is detected in under one second, and BGP fast-external-fallover triggers an immediate session reset without waiting for the hold-down timer.

Both sessions have strict prefix filters: inbound filters reject RFC-1918 prefixes, the default route, and any prefix longer than /24; outbound filters permit only the enterprise 10.0.0.0/8 aggregate and the HQ public IP block.

**Cloud connectivity:**

An iBGP session between Core-A (10.10.99.1) and the AWS Transit Gateway BGP peer advertises the cloud 10.40.0.0/16 aggregate into the enterprise. The enterprise summary 10.0.0.0/8 is announced to the TGW. All VPC route tables point back to the TGW for return traffic.

### First-hop redundancy — VRRP per gateway VLAN (references Lesson 13)

Every user-facing VLAN gateway is a VRRP virtual IP shared between two physical switches. Masters and backups alternate between Core-A and Core-B at HQ, and between BR-X-Sw1 and BR-X-Sw2 at branches, so each switch carries approximately half the forwarding load in steady state:

| Site | VLAN | VIP | Master | Backup |
|------|------|-----|--------|--------|
| HQ | 10 (data) | 10.10.10.1 | Core-A | Core-B |
| HQ | 20 (voice) | 10.10.20.1 | Core-B | Core-A |
| HQ | 30 (video) | 10.10.30.1 | Core-A | Core-B |
| HQ | 40 (server) | 10.10.40.1 | Core-B | Core-A |
| Branch-A | 110/120/130 | 10.20.x.1 | BR-A-Sw1/Sw2 alternating | — |
| Branch-B | 210/220/230 | 10.30.x.1 | BR-B-Sw1/Sw2 alternating | — |

VRRP advertisement interval is 1 second. Preemption is enabled with a 10-second delay — the delay gives the recovering master time to reconverge OSPF before resuming the VIP, preventing a black-hole window where the switch owns the VIP but has no upstream route. BFD tracks the uplink interface; three consecutive 300 ms BFD failures declare the link down and decrement the VRRP priority below the backup's, triggering failover within 900 ms.

### Security baseline (references Lessons 14, 15, and the zone-based firewall design from Lesson 23)

The security baseline has four layers:

**VLAN segmentation and anti-spoofing.** DHCP snooping is enabled on all access VLANs (data, voice, video, printer). Only uplinks toward the server VLAN DHCP server are trusted. Dynamic ARP Inspection validates ARP packets against the DHCP snooping binding table on all user VLANs, blocking ARP cache poisoning without requiring static ARP entries. Trunk ports carry only explicitly named VLANs — DTP is disabled on all ports, VLAN 1 carries no user traffic, and the native VLAN on every trunk is set to an unused VLAN ID.

**802.1X port authentication.** All user-data, voice, and video access ports enforce 802.1X using EAP-TLS with machine certificates from an internal PKI. The RADIUS server runs on Server VLAN 40. Ports that fail authentication are placed in a restricted VLAN (VLAN 998) with no internal reachability. Voice ports use CDP/LLDP-MED to provision the voice VLAN after successful 802.1X or MAC-authentication-bypass with a phone-specific RADIUS policy. The Charlotte video VLAN currently lacks 802.1X — this is the WARN finding in the default run.

**Zone-based firewall policy.** Four zones are enforced at the HQ core SVI layer:

```
Zone: User      — VLANs 10, 20, 30, 50, 110, 120, 130, 210, 220, 230
Zone: Server    — VLAN 40 (HQ only)
Zone: Cloud     — 10.40.0.0/16
Zone: Internet  — default route via ISPs

Inter-zone policy (default: deny all unlisted pairs):
  User → Server   : TCP 443, 3389 (MFA required), 22 (MFA required)
  User → Internet : TCP 80, 443, UDP 5060 (SIP), UDP 10000-20000 (RTP)
  Server → Cloud  : TCP 443, TCP 5432 (DB replication)
  Cloud → Server  : TCP 443 (API callbacks)
  Internet → Server : TCP 443 only (reverse-proxy enforced)
  * → Mgmt VLAN  : DENY (OOB access only via console server)
```

**SNMPv3 and syslog.** SNMPv3 with SHA-256 auth and AES-128 priv is enforced at all sites; all community strings are removed. Every device ships syslog over TCP to the central collector on Server VLAN 40. NTP is synchronised from a stratum-2 server at HQ, which peers with pool.ntp.org — all four sites use the HQ NTP server so log timestamps are comparable across the estate.

### QoS architecture — DSCP and LLQ (references Lesson 24)

The three-class QoS model marks, queues, and polices traffic at every WAN egress interface:

| Class | DSCP | Marking | Queue | Guarantee |
|-------|------|---------|-------|-----------|
| Voice RTP | EF (46) | Set at IP phone / softphone | LLQ strict priority | 20% — never starved |
| Video conferencing | AF41 (34) | Set at access switch ingress | CBWFQ | 30% |
| SIP / SCCP signaling | CS3 (24) | Set at access switch ingress | CBWFQ | 5% |
| Business data | AF21 (18) | Set at access switch ingress | CBWFQ | 25% |
| Best-effort | BE (0) | Default (unmarked) | WFQ | Remaining |
| Scavenger / P2P | CS1 (8) | Set by reclassifier | Policed / drop | 0% |

The trust boundary is at the access switch port. Any DSCP value arriving from a user endpoint that does not match the expected per-VLAN class is reclassified by the ingress policy-map before the packet reaches the WAN egress queue. The MPLS carrier's PE router maps DSCP to MPLS EXP bits preserving the LLQ hierarchy end-to-end.

The Cloud WAN link currently has no QoS policy attached — this is the WARN finding for QoS in the default run. Without the policy, voice traffic crossing the Direct Connect link competes equally with DB replication traffic.

### Production-readiness review framework (references Lesson 07)

The reviewer aggregates findings into five categories and computes a total score out of 440:

| Category | Checks | Max points | 90% threshold |
|----------|--------|-----------|--------------|
| Addressing and Segmentation | 8 | 80 | 72 |
| Routing and Redundancy | 12 | 120 | 108 |
| Security Baseline | 10 | 100 | 90 |
| QoS and Application Delivery | 6 | 60 | 54 |
| Monitoring and Operations | 8 | 80 | 72 |
| **Total** | **44** | **440** | **396** |

Each check scores 10 (PASS), 6 (WARN), or 0 (FAIL). Grading bands mirror the Lesson 07 scorecard: PRODUCTION (≥ 90%), INTERNAL-ONLY (70–89%), NOT-DEPLOYABLE (< 70%). A FAIL in the Routing and Redundancy or Security Baseline categories is treated as a CAB blocker regardless of the total score — no maintenance window opens until that finding is remediated.

## Build It

The deliverable is `code/main.py` — a single stdlib-only Python module that defines the four-site network as frozen dataclasses, runs all checks, and emits a structured scorecard and remediation list. Run it with `python3 code/main.py`.

### Step 1: Model the network as frozen dataclasses

Every network object is a `frozen=True` dataclass so no validator can mutate the data it reads. Eight dataclasses cover the full design: `Site`, `Vlan`, `WanLink`, `BgpSession`, `OspfArea`, `QosClass`, `Alert`, and `VrrpPair`. A ninth dataclass, `Finding`, is mutable — it accumulates the results of each check.

```python
@dataclass(frozen=True)
class Vlan:
    site: str
    vlan_id: int
    name: str
    subnet: str
    category: str       # user_data | voice | video | server | printer | mgmt
    vrrp: bool
    dot1x: bool
    dscp_policy: str | None   # EF | AF41 | AF21 | CS3 | BE | None
    dhcp_snooping: bool
    dai: bool
    acl: bool
    zone: str           # user | server | cloud | mgmt
```

The `category` field drives every check — the security validator iterates over `category == "voice"` VLANs to test 802.1X, the QoS validator iterates over `category == "voice"` to test DSCP EF, and so on. The `zone` field drives firewall-policy checks independently of the physical VLAN function.

### Step 2: Validate address space

The address validator uses `ipaddress.ip_network(subnet, strict=True)` to parse every VLAN subnet and WAN transit subnet, then calls `a.overlaps(b)` for every pair. The stdlib `ipaddress` module handles all prefix arithmetic — no external dependencies.

```python
import ipaddress

def check_no_subnet_overlap(all_subnets: list[str]) -> list[str]:
    nets = [ipaddress.ip_network(s, strict=True) for s in all_subnets]
    return [
        f"{nets[i]} overlaps {nets[j]}"
        for i in range(len(nets))
        for j in range(i + 1, len(nets))
        if nets[i].overlaps(nets[j])
    ]
```

Eight addressing checks run in `check_addressing()`: overlap detection, enterprise-aggregate containment (all VLAN subnets within 10.0.0.0/8), VLAN ID global uniqueness across physical sites, management VLAN presence at every site, absence of VLAN 1 in production, /24 subnet discipline, server/user zone separation, and cloud block non-overlap with enterprise site blocks.

### Step 3: Validate routing design

`check_routing()` runs eight checks against the `OspfArea` and `BgpSession` data objects:

- Area 0 ABR count ≥ 2 (dual ABR at HQ)
- All non-backbone areas are stub (`is_stub = True`)
- Two eBGP sessions with distinct `peer_asn` values (dual-homed)
- `inbound_filter = True` on all BGP sessions
- `outbound_filter = True` on all BGP sessions
- Secondary ISP has `as_path_prepend > 0`
- BFD enabled on all BGP sessions
- `local_pref` values are asymmetric (primary > secondary)

### Step 4: Validate redundancy

`check_redundancy()` runs four checks against `VrrpPair` and `WanLink` data:

- All user VLANs (data, voice, video) have `vrrp = True`
- All `VrrpPair` objects have `master != backup`
- All `VrrpPair` objects have `bfd = True`
- At least two `WanLink` objects with `protocol == "ebgp"` (dual ISP circuits)

### Step 5: Validate security baseline

`check_security()` runs ten checks in sequence. The most operationally significant are 802.1X coverage (checked independently for user-data, voice, and video VLANs), DHCP snooping, DAI, ACL presence on all SVIs, management zone isolation, server zone ACL, and SNMPv3 verification. The checks are binary: a missing flag on any VLAN in the category produces a finding that names the specific site and VLAN ID.

### Step 6: Validate QoS policy

`check_qos()` first iterates over VLANs to verify DSCP policy assignments (voice = EF, video = AF41). It then iterates over `QosClass` objects to verify that an LLQ class with non-zero `bw_pct` exists, a CBWFQ class exists for AF41, and a DROP class exists for CS1 (scavenger). Finally it checks that every `WanLink` has `qos_policy = True`. A `WanLink` without `qos_policy` produces a WARN because the LLQ marking is meaningless if the egress WAN interface has no queue policy — packets land in the default FIFO queue regardless of DSCP.

### Step 7: Validate monitoring coverage

`check_monitoring()` checks eight conditions across `Site` and `Alert` objects:

1. SNMPv3 flag at every site
2. Non-null `syslog_server` at every site
3. Non-null `ntp_server` at every site
4. The five required alert signals are all defined: `bgp_session_change`, `vrrp_state_change`, `ospf_neighbor_loss`, `wan_utilization`, `interface_error_rate`
5. Every alert has a non-empty `runbook` path
6. On-call contacts ≥ 2 at every physical site
7. BFD on all WAN links (as a monitoring/operations readiness proxy)
8. Cloud VPC monitoring integrated with on-premises NOC

### Step 8: Score and report

`score_findings()` aggregates all findings into a summary dictionary keyed by category. `print_report()` renders the scorecard in three passes: the site inventory table, the category score table with per-category PASS/WARN/FAIL, the full finding list sorted by status (FAIL → WARN → PASS), and the two-tier remediation list. The final output is a JSON document containing every finding, suitable for archival in the CAB ticket.

## Use It

| Deliverable | Acceptance criterion | Covered by |
|-------------|---------------------|-----------|
| Non-overlapping address plan | `check_addressing` returns no overlap findings | Step 2 |
| All subnets in 10.0.0.0/8 | Aggregate-containment check PASS | Step 2 |
| OSPF multi-area hierarchy | Area 0 has 2 ABRs; branches are stub | Step 3 |
| BGP dual-homing | 2 eBGP sessions, distinct ASNs, filters on both | Step 3 |
| LOCAL_PREF asymmetry | PRIMARY > SECONDARY confirmed | Step 3 |
| AS-path prepend on secondary ISP | Prepend count > 0 on lower-LOCAL_PREF session | Step 3 |
| VRRP on all user VLANs | All data/voice/video VLANs at all sites: `vrrp = True` | Step 4 |
| VRRP master ≠ backup | No VrrpPair has identical master and backup | Step 4 |
| 802.1X on user-data VLANs | All data VLANs: `dot1x = True` | Step 5 |
| DHCP snooping and DAI | All access VLANs: both flags True | Step 5 |
| Voice DSCP EF | All voice VLANs: `dscp_policy = "EF"` | Step 6 |
| Video DSCP AF41 | All video VLANs: `dscp_policy = "AF41"` | Step 6 |
| LLQ for voice | QosClass with `queue_type = "LLQ"` and `bw_pct > 0` | Step 6 |
| QoS on all WAN links | All WanLink: `qos_policy = True` | Step 6 |
| Centralized syslog | Every site has non-null `syslog_server` | Step 7 |
| All 5 canonical alerts defined | Signal set matches required set exactly | Step 7 |
| Production scorecard | Total score ≥ 90% (396/440) | Step 8 |

## Ship It

The artifact is the JSON block printed at the end of `python3 code/main.py`. It contains the site inventory, the full findings list with score, detail, and remediation text for every check, the category sub-scores, the total score, the grade (PRODUCTION / INTERNAL-ONLY / NOT-DEPLOYABLE), and the two-tier remediation list. Capture it for CAB evidence:

```
python3 code/main.py > capstone-readiness-$(date +%Y%m%d).txt
```

Attach the file to the Change Advisory Board ticket. The review artifact directly maps to the Lesson 07 production-readiness portfolio (the 18-check scorecard becomes a 44-check capstone scorecard), and the remediation format mirrors the Priority 1 / Priority 2 structure from Lesson 07. The rollback planning from Lesson 29 (Production Cutover and Rollback Rehearsal) applies to every FAIL finding: each finding that blocks a maintenance window requires a rollback owner, a rollback script that has been rehearsed in staging, and a SloGate abort criterion before the maintenance window opens.

The prompt artifact at `outputs/prompt-full-scale-network-capstone-design-and-operations-review.md` wraps the same mechanism as a reusable study drill: given any production network description, it produces a five-section analysis — mechanism, observable evidence, normal trace checklist, failure mode diagnostic, and reusable runbook — that connects every design decision to something measurable on the wire.

## Exercises

1. **Baseline review.** Run `main.py` as written and confirm the grade is PRODUCTION. Identify the four WARN findings. For each WARN, trace it to the Phase 18 lesson that covers the correct configuration (e.g., the 802.1X video VLAN finding traces to Lesson 15, the cloud WAN QoS finding traces to Lesson 24). State what observable evidence would prove the finding is remediated (e.g., a packet capture showing DSCP EF on voice packets leaving the cloud WAN interface).

2. **Introduce an address overlap.** Change the Cloud VPC block from `10.40.0.0/16` to `10.20.0.0/16` in the Cloud VPC VLAN definitions (change the three cloud VLAN subnets to `10.20.10.0/24`, `10.20.20.0/24`, `10.20.99.0/24`). Re-run and confirm the address validator catches the overlaps and reports them as FAIL in the Addressing and Segmentation category. State what the routing consequence would be: which route does Core-A install in its FIB for 10.20.10.0/24, and does it point to Denver or to the cloud?

3. **Remove VRRP from a voice VLAN.** Set `vrrp = False` on Branch-A VLAN 120 (voice). Re-run and confirm the redundancy validator catches the gap and reports WARN. Explain the operational consequence: if BR-A-Sw1 loses power during a call, what happens to the RTP stream? What does the VoIP endpoint see at the IP layer, and how long does it take to recover compared to a site with VRRP?

4. **Disable 802.1X at Charlotte.** Set `dot1x = False` on all Branch-B user VLANs (210, 220, 230). Re-run and confirm the security validator reports three WARN findings. Compute the attack surface change: without 802.1X, how many authenticated steps does an attacker with physical access to a Charlotte ethernet port need to reach the Server VLAN? With 802.1X, how many? Explain how DHCP snooping and DAI limit the blast radius even without 802.1X.

5. **QoS gap simulation.** Remove the `dscp_policy` from the Branch-A voice VLAN 120 (set to `None`) and also remove the QoS class list entry for voice (remove the `QosClass("voice", "EF", "LLQ", 20)` from `QOS_CLASSES`). Re-run and confirm two FAIL findings appear in QoS. Then calculate: at 80% WAN utilization between HQ and Denver with no LLQ, a 100 kbyte bulk transfer burst arrives simultaneously with a 160-byte RTP voice packet. Using a 100 Mbps link, what is the serialisation delay added to the voice packet? Compare this to the G.114 recommendation of < 150 ms one-way delay.

6. **Extend the reviewer for rollback readiness.** Add an eighth check function `check_rollback_readiness()` that validates a new dataclass `RollbackPlan` with fields: `change_id`, `rollback_owner`, `rollback_script_path`, `staging_rehearsed` (bool), `slo_gate_pct` (float), and `drain_window_s` (int). The check should FAIL if `staging_rehearsed = False`, FAIL if `slo_gate_pct > 2.0` (too lenient), WARN if `drain_window_s > 60` (longer drain than standard), and PASS otherwise. Reference Lesson 29 for the SloGate and drain-window semantics. Add the function to `main()` and confirm it contributes to the total score.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| OSPF stub area | "the area that doesn't learn external routes" | An OSPF area configured with `area X stub` so that Type 5 external LSAs are suppressed; the ABR injects a single Type 3 default route instead, reducing the branch SPF database size and eliminating LSA churn from BGP prefix withdrawals at HQ. |
| OSPF ABR | "the border router" | Area Border Router — a router with interfaces in two or more OSPF areas; it maintains a separate LSDB per area and generates Type 3 summary LSAs that describe routes from one area to the other. The capstone requires two ABRs at HQ so that a single core switch failure does not partition the backbone. |
| AS-path prepend | "make the backup path look worse" | A BGP technique that inserts extra copies of the local ASN into the AS_PATH attribute of outbound route announcements; upstream routers prefer shorter AS_PATH, so the prepended path is de-preferred, directing inbound traffic to the primary ISP. |
| LOCAL_PREF | "the outbound path knob" | A BGP well-known discretionary attribute used only within an AS; higher LOCAL_PREF is preferred for outbound traffic. Setting LOCAL_PREF 200 on routes learned from ISP-1 and LOCAL_PREF 100 on routes from ISP-2 makes HQ prefer ISP-1 for all outbound flows. |
| BFD | "the fast failure detector" | Bidirectional Forwarding Detection — a sub-second hello protocol that runs alongside BGP, OSPF, and VRRP; when BFD detects a link failure it immediately notifies the routing protocol, reducing failover from 30–90 s (protocol hold-down) to under 1 s (3 × 300 ms BFD interval). |
| VRRP preempt delay | "wait before taking over" | A VRRP parameter that prevents a recovering master from seizing the VIP for a configurable duration after it returns; in the capstone it is 10 seconds, giving OSPF time to reconverge on the recovering switch before it resumes forwarding responsibility for the VIP. |
| DSCP EF | "voice gets the priority queue" | Differentiated Services Code Point 46 (binary 101110), the IETF-standard marking for expedited forwarding; traffic marked EF is placed in the LLQ where it is served before all other classes, bounding one-way latency for voice RTP to well below the G.114 150 ms recommendation. |
| LLQ | "strict priority for voice" | Low Latency Queue — a CBWFQ class configured with `priority percent N`; LLQ is drained completely before any other class is served on each scheduling cycle, guaranteeing voice packets experience minimum queuing delay at the expense of potential starvation of lower classes if the voice class exceeds its bandwidth guarantee. |
| Zone-based firewall | "the firewall that defaults to deny" | A stateful firewall model that groups SVIs into named security zones and enforces zone-pair policies; unlike ACL-based firewalls, a zone-based policy defaults to drop all traffic between zones unless a service-policy explicitly permits it, which means new VLANs added to the design are automatically untrusted until a policy is written. |
| CAB | "the approval committee" | Change Advisory Board — the cross-functional group (networking, security, SRE, application owners) that reviews and approves changes to production infrastructure; the production-readiness scorecard is the primary evidence submitted to the CAB and must show zero FAIL items for a Tier-0 change to be approved. |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 5 §5.6 — OSPF and BGP routing algorithms; the conceptual basis for the multi-area hierarchy and dual-homing design.
- RFC 2328, "OSPF Version 2", §3.6 — stub area definition and Type 3/5 LSA filtering; directly relevant to the branch OSPF design.
- RFC 4271, "A Border Gateway Protocol 4", §9.1 — BGP route selection algorithm that makes LOCAL_PREF the first tie-breaker, explaining why LOCAL_PREF 200 always wins over LOCAL_PREF 100.
- RFC 3768, "Virtual Router Redundancy Protocol", §6 — the VRRP state machine and the preempt timer semantics used in the capstone gateway design.
- RFC 2474, "Definition of the Differentiated Services Field in IPv4 and IPv6 Headers" — the DSCP standard that defines EF (46), AF41 (34), CS3 (24), AF21 (18), and CS1 (8).
- Cisco, "QoS: Low Latency Queuing" (Cisco CCO, IOS 15.x configuration guide) — the reference implementation of LLQ and CBWFQ with the `priority percent` and `bandwidth percent` commands used in the capstone QoS policy.
- NIST SP 800-82 Rev. 3, "Guide to Operational Technology (OT) Security" — the security baseline framework whose zone model maps directly to the four-zone firewall policy in the capstone.
- RFC 5880, "Bidirectional Forwarding Detection (BFD)" — the full BFD specification covering the session state machine, authentication options, and the mapping to BGP and OSPF notification paths.
- Google SRE Book (Beyer et al., O'Reilly), Chapter 8 "Release Engineering" — the change-management philosophy behind the production sign-off requirement and the CAB evidence model.
- Phase 18 Lesson 07 — Network Documentation Portfolio and Production Readiness Review — the 18-check scorecard that the capstone's 44-check scorecard extends; re-reading this lesson alongside the capstone makes the scoring rubric evolution concrete.
