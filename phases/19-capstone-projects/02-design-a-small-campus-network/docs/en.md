# Design a Small Campus Network

> Given a four-floor university department building with 200 users, wired and wireless access, a server room, VoIP phones, and a single ISP uplink, produce a complete, documented network design that a junior engineer could hand to a contractor and deploy.

**Type:** Capstone
**Languages:** Python, Diagrams (text-based)
**Prerequisites:** Phase 7 routing, Phase 6 switching, Phase 4 VLANs
**Time:** ~180 minutes

---

## Learning Objectives

1. Translate a prose requirements document into a three-tier campus hierarchy with documented rationale for each layer.
2. Design a VLAN scheme and assign contiguous IP subnets from a given address block without waste or overlap.
3. Choose a spanning tree root placement strategy and explain how it affects convergence and traffic symmetry.
4. Configure HSRP (or VRRP) between distribution-layer switches to give end hosts a resilient default gateway.
5. Write a QoS policy that marks VoIP RTP streams at ingress and enforces a priority queue end-to-end.
6. Produce handoff-ready documentation: a network diagram, IP address plan, VLAN table, and IOS configuration templates.

---

## The Problem

The Computer Science department at Ashford University occupies a four-floor building. There are roughly 200 users spread across the four floors: faculty and staff on floors 1–2, student labs on floors 3–4, and a server room in the basement. Each floor has a wiring closet. The basement also hosts the main distribution frame (MDF) where the ISP hands off a 1 Gbps fiber uplink and where the server room switch lives. Every desk has a wired port; each floor has three ceiling-mounted wireless access points. The department recently deployed a VoIP phone system — every desk phone needs to reach the call manager server in the basement without audio glitches regardless of what the students are doing in the labs.

The university's central IT team has allocated the block 192.168.0.0/16 for this building. They have also mandated that guest wireless traffic must be isolated from all internal VLANs and must exit directly to the internet without touching any internal router. The building currently has no redundancy: a single switch failure anywhere takes down its entire floor. The head of department has approved budget for a second distribution-layer switch to fix this.

Your job is to produce a design that meets all these requirements, is extensible to twice the current user count, and uses only equipment the contractor already stocks (Cisco Catalyst-class IOS switches).

---

## The Concept

### Three-Tier Campus Hierarchy

Campus networks are almost universally designed in three tiers: **access**, **distribution**, and **core**. In a single-building design the core tier collapses into the distribution tier, giving you a two-tier physical layout that still follows the three-tier logical model.

The **access layer** is where end devices connect. Each floor's wiring closet switch is an access-layer device. Its job is to apply VLANs, enforce port security, and trunk up to distribution. Access switches should be stateless with respect to routing — they forward Layer 2 frames and do nothing else. This keeps them cheap and their configuration simple.

The **distribution layer** is the policy layer. Both distribution switches (DSW-1 and DSW-2) in the MDF run inter-VLAN routing, enforce ACLs between VLANs, and provide the building's default gateways via HSRP. Each distribution switch connects to every access switch via a dedicated trunk. This means any single uplink failure only affects one redundant path — the spanning tree or HSRP failover covers it within seconds.

The **core / border layer** in this building is a single router (or a Layer 3 distribution switch with a routed uplink) that connects DSW-1 and DSW-2 to the ISP and that terminates the guest VLAN in a DMZ segment. The guest SSID's traffic reaches the border device directly; a route-map or policy route sends it out the ISP interface without ever crossing the internal VLANs.

### ASCII Topology

```
                        [ ISP ]
                           |
                      [ BORDER-RTR ]
                     /             \
               [ DSW-1 ]         [ DSW-2 ]
              (HSRP active)    (HSRP standby)
             /    |    \       /    |    \
          ASW-B  ASW-1  ASW-2  ASW-3  ASW-4
         (bsmt) (flr1) (flr2) (flr3) (flr4)
           |
        [ SRV-SW ]
     (server room, L2 only)
```

Each ASW connects to both DSW-1 and DSW-2 via 802.1Q trunks (two uplinks per ASW). Spanning tree blocks the DSW-2 uplink on all non-redundancy VLANs, keeping traffic symmetric toward DSW-1 as the primary. When DSW-1 fails, STP unblocks DSW-2 uplinks and HSRP fails over simultaneously.

### VLAN Design

Six VLANs cover the requirements cleanly:

| VLAN ID | Name         | Purpose                              |
|---------|--------------|--------------------------------------|
| 10      | staff        | Faculty and staff workstations        |
| 20      | students     | Student lab machines                  |
| 30      | servers      | Server room — file, DNS, call manager |
| 40      | voice        | VoIP phones (all floors)              |
| 50      | wifi-guest   | Guest wireless, no internal routing   |
| 99      | management   | Switch and AP out-of-band management  |

Phones and data devices share the same physical port using an 802.1Q voice VLAN. The switch sends CDP/LLDP-MED to the phone, which tags its own traffic with VLAN 40; the workstation behind it remains untagged on VLAN 10 or 20.

### IP Addressing

Subnet the 192.168.0.0/16 space by function. Use /24 for user-facing VLANs (254 usable hosts, room to grow), /26 for servers (62 hosts, more than enough), and /28 for point-to-point links and management.

| Subnet             | VLAN | Name        | Hosts |
|--------------------|------|-------------|-------|
| 192.168.10.0/24    |  10  | staff       |  254  |
| 192.168.20.0/24    |  20  | students    |  254  |
| 192.168.30.0/26    |  30  | servers     |   62  |
| 192.168.40.0/24    |  40  | voice       |  254  |
| 192.168.50.0/24    |  50  | wifi-guest  |  254  |
| 192.168.99.0/28    |  99  | management  |   14  |
| 192.168.254.0/30   |   —  | DSW1↔BORDER |    2  |
| 192.168.254.4/30   |   —  | DSW2↔BORDER |    2  |

HSRP virtual IPs are the .1 address in each user VLAN (e.g., 192.168.10.1 for staff). DSW-1 owns .2 and DSW-2 owns .3 in each subnet. DHCP pools live on DSW-1; DSW-2 runs a DHCP relay pointing back to DSW-1's real IP in case it becomes the active HSRP speaker.

### Routing and Spanning Tree

Run OSPF area 0 between DSW-1, DSW-2, and BORDER-RTR on the /30 point-to-point links. Each distribution switch redistributes its directly connected VLANs into OSPF with a type-1 external metric. This keeps routing simple and eliminates the need for a separate IGP within the building.

For spanning tree, use Rapid PVST+ (one instance per VLAN). Explicitly set DSW-1 as root primary and DSW-2 as root secondary for all VLANs. This ensures that when both distribution switches are healthy, all access-to-distribution traffic flows through DSW-1, and STP's blocked ports sit on the DSW-2 uplinks — exactly mirroring the HSRP active/standby assignment.

---

## Build It

Work through these steps in order. Produce a concrete deliverable at each step before moving to the next.

**Step 1 — VLAN table**

Create the six-row VLAN table above (VLAN ID, name, purpose, subnet, HSRP VIP, DSW-1 IP, DSW-2 IP). Add a row for the native VLAN: use VLAN 999 (unused), never VLAN 1. This table becomes the single source of truth for all configuration that follows.

**Step 2 — IP address plan**

Expand the addressing table into a full spreadsheet (or Markdown table) with one row per addressable device:

```
Device        Interface     IP               Mask  Gateway        VLAN
DSW-1         Vlan10        192.168.10.2     /24   —              10
DSW-2         Vlan10        192.168.10.3     /24   —              10
HSRP VIP      Vlan10        192.168.10.1     /24   —              10
DSW-1         Vlan30        192.168.30.2     /26   —              30
...
BORDER-RTR    Gi0/0.254     192.168.254.1    /30   ISP            —
```

Every switch management interface gets an address in 192.168.99.0/28. The border router's WAN IP comes from the ISP.

**Step 3 — Spanning tree root placement**

On DSW-1, set root primary for all VLANs:

```ios
spanning-tree vlan 10,20,30,40,50,99 root primary
```

On DSW-2, set root secondary:

```ios
spanning-tree vlan 10,20,30,40,50,99 root secondary
```

Verify with `show spanning-tree vlan 10` that DSW-1 shows "This bridge is the root" and that DSW-2 shows "Root ID" pointing to DSW-1's bridge ID. Check that all access-switch uplinks toward DSW-2 show BLK state under normal conditions.

**Step 4 — HSRP default gateways**

Configure HSRP on DSW-1 (active, priority 110) and DSW-2 (standby, priority 90) for each user VLAN. Example for VLAN 10:

```ios
! DSW-1
interface Vlan10
 ip address 192.168.10.2 255.255.255.0
 standby 10 ip 192.168.10.1
 standby 10 priority 110
 standby 10 preempt
 standby 10 track 1 decrement 20

! DSW-2
interface Vlan10
 ip address 192.168.10.3 255.255.255.0
 standby 10 ip 192.168.10.1
 standby 10 priority 90
 standby 10 preempt
```

The `track 1 decrement 20` on DSW-1 watches the uplink to BORDER-RTR. If that link goes down, DSW-1's HSRP priority drops to 90 and DSW-2 wins, preventing a black hole where DSW-1 is the HSRP active but has no path to the internet.

Repeat the same pattern for VLANs 20, 30, 40, and 99. VLAN 50 (guest) has no HSRP — it routes only through BORDER-RTR via a sub-interface.

**Step 5 — ISP uplink and guest isolation**

On BORDER-RTR, configure a sub-interface for the guest VLAN:

```ios
interface GigabitEthernet0/1.50
 encapsulation dot1Q 50
 ip address 192.168.50.254 255.255.255.0
 ip nat inside

interface GigabitEthernet0/0
 description ISP uplink
 ip address <ISP-PROVIDED>
 ip nat outside

ip nat inside source list GUEST_ACL interface GigabitEthernet0/0 overload

ip access-list standard GUEST_ACL
 permit 192.168.50.0 0.0.0.255
```

Add a static default route toward the ISP. Internal VLANs reach the internet via OSPF redistribution and a default route propagated from BORDER-RTR. The guest subnet never appears in the internal routing table.

**Step 6 — QoS policy for VoIP**

Mark VoIP RTP at the access layer using DSCP EF (expedited forwarding, decimal 46). IOS voice VLAN configuration already provides implicit trust for phones that present themselves via CDP, but add an explicit policy for defense in depth:

```ios
! Access switch — ingress policy on voice-capable ports
class-map match-all VOIP-RTP
 match ip dscp ef

policy-map MARK-VOICE
 class VOIP-RTP
  set dscp ef
 class class-default
  set dscp default

interface range GigabitEthernet0/1-24
 service-policy input MARK-VOICE
```

On distribution and core uplinks, configure a queuing policy that gives DSCP EF traffic strict-priority scheduling with a bandwidth ceiling of 30% (roughly 300 Mbps on a 1G uplink) to prevent starvation of other traffic:

```ios
! Distribution switch — uplink egress queuing
class-map match-all VOICE-EF
 match ip dscp ef

policy-map WAN-QUEUING
 class VOICE-EF
  priority percent 30
 class class-default
  fair-queue

interface GigabitEthernet1/0/1
 description Uplink to BORDER-RTR
 service-policy output WAN-QUEUING
```

**Step 7 — Wireless SSID to VLAN mapping**

Each wireless AP broadcasts three SSIDs. The AP controller (or each autonomous AP) maps SSIDs to VLANs via trunk:

| SSID              | VLAN | Security        | Notes                          |
|-------------------|------|-----------------|--------------------------------|
| ashford-staff     |  10  | WPA3-Enterprise | 802.1X against RADIUS on VLAN 30 |
| ashford-students  |  20  | WPA3-Enterprise | Same RADIUS server, different policy |
| ashford-guest     |  50  | WPA3-Personal   | Pre-shared key, isolated       |

AP uplink ports are configured as trunk ports carrying VLANs 10, 20, 50, and 99. The management IP of each AP sits in VLAN 99.

**Step 8 — Documentation deliverable**

Generate a Python script (`outputs/generate_ip_table.py`) that reads a YAML config file (`outputs/network_config.yaml`) describing VLANs and prints a formatted IP address table. This gives you a repeatable, version-controlled source of truth that can regenerate documentation after any addressing change.

```python
# outputs/generate_ip_table.py
import yaml, ipaddress, sys

def print_table(config):
    print(f"{'Subnet':<22} {'VLAN':>6} {'Name':<14} {'Gateway':<18} {'Hosts':>6}")
    print("-" * 70)
    for vlan in config["vlans"]:
        net = ipaddress.IPv4Network(vlan["subnet"])
        hosts = net.num_addresses - 2
        gw = vlan.get("gateway", str(next(net.hosts())))
        print(f"{vlan['subnet']:<22} {vlan['id']:>6} {vlan['name']:<14} {gw:<18} {hosts:>6}")

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        print_table(yaml.safe_load(f))
```

---

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Verify VLAN propagation | `show vlan brief` on each switch | All six VLANs present and active; no access port in VLAN 1 |
| Confirm spanning tree root | `show spanning-tree vlan 10` on DSW-1 and DSW-2 | DSW-1 is root, DSW-2 uplinks show BLK on all access switches |
| Test HSRP failover | Ping 192.168.10.1 continuously, then shut DSW-1's uplink | Ping drops for ≤ 3 seconds, then resumes via DSW-2 |
| Validate QoS marking | `show policy-map interface` on access port | VOIP-RTP class shows matched packets; counters increment during a call |
| Confirm guest isolation | From a guest-SSID client, ping 192.168.10.1 | Ping fails; ping to 8.8.8.8 succeeds |
| Stress-test voice quality | Run iPerf3 UDP flood on VLAN 20 while placing a call | Call audio remains intelligible; MOS score ≥ 4.0 |

---

## Ship It

Create the following files under `outputs/`:

- `network-diagram.txt` — ASCII diagram of the full topology with interface labels and IP addresses annotated on every link.
- `ip-address-plan.md` — The full addressing table from Step 2 in Markdown, one row per interface.
- `vlan-table.md` — The six-row VLAN table with subnet, HSRP VIP, and purpose columns.
- `dsw1-config-template.ios` — A complete IOS configuration template for DSW-1 covering VLANs, SVIs, HSRP, OSPF, and spanning tree. Use `<PLACEHOLDER>` tokens for site-specific values (hostname, passwords, ISP address).
- `dsw2-config-template.ios` — Same for DSW-2.
- `access-switch-template.ios` — Template for a single access-layer switch showing trunk uplinks, access ports with voice VLAN, port security, and BPDU guard.
- `generate_ip_table.py` + `network_config.yaml` — The Python documentation generator from Step 8.

---

## Exercises

1. **Redundant uplinks.** The current design uses a single fiber handoff from the ISP. Research dual-homing options (BGP multihoming vs. static floating route) and write a one-page recommendation for a department of this size and budget. What changes in the BORDER-RTR configuration if you add a second ISP?

2. **Capacity planning.** The department expects student enrollment to double in three years (400 users, 8 student lab rooms). Which subnets in the current design would overflow? Re-subnet those VLANs to accommodate 500 hosts each without renumbering the others.

3. **Security additions.** Add dynamic ARP inspection (DAI) and DHCP snooping to the staff VLAN. Write the four IOS commands required on an access switch, explain what each does, and describe one failure mode if the trust port is misconfigured.

4. **IPv6 dual-stack.** The university has been allocated a /48 from their regional internet registry. Extend the IP addressing plan with an IPv6 /64 per VLAN. Show the OSPFv3 configuration required on DSW-1 to advertise these prefixes, and explain how SLAAC interacts with the existing DHCP infrastructure.

5. **QoS tuning.** An audio engineer complains that video conferencing (DSCP AF41) is competing with VoIP (DSCP EF) during peak hours and causing jitter. Extend the `WAN-QUEUING` policy-map to add a second priority class for AF41 with a 20% bandwidth reservation. Show the updated policy-map and explain why the combined priority reservation must stay below 100%.

6. **Wireless density.** Three APs per floor was sufficient for 2023. Perform a basic coverage calculation: assuming each AP handles 30 concurrent associations at full throughput (802.11ac Wave 2, 5 GHz, 80 MHz channel, MCS 9), and each student lab floor has 60 wired-plus-wireless users, is the current AP count adequate? If not, how many APs would you add and where?

---

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Three-tier hierarchy | "The Cisco campus model" | Access, distribution, and core layers with distinct jobs: connect, enforce, and route |
| VLAN | "A separate network" | A Layer 2 broadcast domain identified by a 12-bit tag; isolation is enforced at the switch, not the wire |
| HSRP | "Virtual IP failover" | A Cisco proprietary protocol where two or more routers elect an active speaker that owns a virtual MAC and IP; standby takes over in ~3 seconds if active fails |
| Trunk port | "A port that carries multiple VLANs" | An 802.1Q port that preserves VLAN tags end-to-end; used for switch uplinks and AP connections |
| BPDU Guard | "Blocks rogue switches" | Disables a port immediately if it receives a Bridge Protocol Data Unit, preventing an end device from influencing spanning tree |
| DSCP EF | "Voice priority marking" | Differentiated Services Code Point 46 (binary 101110); the standard marking for delay-sensitive, low-jitter traffic per RFC 3246 |
| OSPF area 0 | "The backbone area" | All OSPF routers in a single area share a complete link-state database; in a single building, one area is sufficient |
| DHCP snooping | "Blocks rogue DHCP servers" | Builds a binding table of legitimate IP-to-MAC-to-port mappings; drop DHCP offers from untrusted ports |
| Rapid PVST+ | "Fast spanning tree" | Cisco's per-VLAN implementation of 802.1w Rapid STP; typical convergence under 1 second vs. 30–50 seconds for classic STP |
| Native VLAN | "The untagged VLAN on a trunk" | Frames on a trunk that carry no 802.1Q tag are assigned to the native VLAN; set to an unused VLAN (e.g., 999) to prevent VLAN hopping attacks |

---

## Further Reading

- **IEEE 802.1Q-2018** — Base standard for VLAN tagging and trunk operation. Read sections 5 (service model) and 9 (port roles) before touching trunk configuration.
- **Cisco Campus LAN and Wireless LAN Design Guide** (Cisco Validated Design, current release) — The authoritative reference for three-tier hierarchy, redundancy patterns, and QoS queuing models at campus scale. Available at cisco.com/go/designzone.
- **RFC 3246 — An Expedited Forwarding PHB** — Defines DSCP EF and the maximum burst constraints required to make strict-priority queuing safe. Essential reading before tuning VoIP QoS.
- **RFC 2328 — OSPF Version 2** — The full OSPF specification. For this lesson, focus on sections 8 (neighbor acquisition), 10 (flooding), and 12.1 (router LSAs). Complement with Cisco's OSPF Design Guide for practical area sizing rules.
- **Cisco IOS Security Configuration Guide: Securing the Data Plane** — Covers DHCP snooping, dynamic ARP inspection, and IP Source Guard in the context of a switched campus. Directly applicable to Exercise 3.
