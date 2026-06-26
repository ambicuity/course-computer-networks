# VRRP First-Hop Redundancy with Sub-Second Gateway Failover

> A default gateway that goes dark for 30 seconds is a 30-second outage for every host that uses it. In a production subnet with 200 hosts, that is 6,000 host-seconds of unreachable service. In a financial trading network, that is 6,000 opportunities to miss a market data packet. The **First-Hop Redundancy Protocol (FHRP)** family — **HSRP** (Cisco-proprietary, RFC 2281), **VRRP** (RFC 3768 for v2, RFC 5798 / RFC 9568 for v3), and **GLBP** (Cisco-proprietary) — solves the problem by giving two (or more) physical routers a shared virtual IP (VIP) and a shared virtual MAC address. The active router forwards traffic for the VIP; the standby router takes over within seconds (or sub-seconds with the right timers and BFD) if the active fails. This lesson is the working playbook for **VRRPv3** in a multi-vendor environment (Cisco, Juniper, Aruba, FRR, Nokia SR Linux), with the timer math, the BFD augmentation, the asymmetric-pitfall (return traffic can land on a different router than the request), the skew-time trick for predictable failover ordering, and the multi-group design for load-balancing across two uplinks. The deliverable is a Python VRRP state-machine simulator that models the active election, the hello/hold timers, the priority/skew precedence, the preemption semantics, and the failover convergence time, and that emits a VRRP configuration skeleton and a verification matrix.

**Type:** Lab
**Languages:** Python (stdlib only: dataclasses, enum, json, ipaddress), shell, keepalived, tcpdump
**Prerequisites:** Phase 7 routing, Phase 8 FHRP concepts
**Time:** ~110 minutes

## Learning Objectives

- Explain the **VRRP state machine** (Initialize, Backup, Master) and the transition triggers (hello received, hold timeout, priority change, preemption).
- Compute the **failover convergence time** from the hello and hold timers, the BFD interval and multiplier, and the FIB install time, and design a sub-second target.
- Use **priority and preemption** to control which router is the active for which VIP, and use the **skew-time** trick (subtracting `(256 - priority) / 256` from the hello interval) to make failover ordering deterministic and predictable.
- Configure **VRRPv3** (RFC 5798, IPv4 and IPv6) with BFD for sub-second detection, on Cisco IOS-XE, Juniper Junos, Aruba CX, and FRR, and verify the virtual MAC (`0000.5E00.01xx`) and the VIP.
- Avoid the **asymmetric-routing pitfall** where the return traffic from the destination lands on a different router than the request, by either (a) using a single active for both directions, or (b) ensuring both routers have a consistent FIB and the upstream accepts traffic from either VIP.
- Build a **multi-group design** that load-balances two uplinks (group 1 is active on router A, group 2 is active on router B) and explain why the load is not perfectly balanced in production.

## The Problem

A regional hospital network, "Mercy Health East," has 12 VLANs across two distribution routers (DIST-A and DIST-B) in a single 1,500-user campus. The two routers are stacked Cisco Catalyst 9300s with VRRPv2 running, and the default hello is 1 second, default hold is 3 seconds. The on-call is paged every 2-3 weeks because DIST-A fails over to DIST-B for 3-4 seconds, during which time the 200 hosts on the affected VLAN lose their default gateway and the in-progress TCP sessions (HL7, EHR, PACS) reset. The hospital's CIO has mandated that VRRP failover be reduced to under 500 ms by end of quarter.

The senior engineer must deliver: (1) a migration from VRRPv2 to VRRPv3 (which supports sub-second timers, BFD, and dual-stack IPv4+IPv6 in a single instance); (2) a BFD profile with 50 ms × 3 = 150 ms detection; (3) a preemption policy with skew time so that DIST-A is always the active for groups 1-6 and DIST-B is always the active for groups 7-12; (4) a verification matrix with 8 test cases that exercise every transition; (5) a runbook that documents the failover behavior and the troubleshooting steps.

The lesson's planner builds the VRRP configuration, simulates the failover with the timer math, and emits the verification matrix.

## The Concept

VRRP, like all FHRP protocols, is a **distributed coordination problem** with three states (Initialize, Backup, Master), three timers (advertisement / hello, hold, skew), and three events (startup, hello received, hold timeout). The state machine is simple; the design decisions (which router is active for which group, whether to preempt, what timers to use, whether to bind BFD) are where the production skill is.

### The state machine and the timer math

The three states are:

- **Initialize**: the router has just started or just received a configuration change. It transitions to Backup if it has a higher priority than the current master, or to Master if it is the only router in the group.
- **Backup**: the router is listening for hello messages from the Master. If a hello is received, the hold timer is reset. If the hold timer expires, the Backup transitions to Master and starts sending hello messages.
- **Master**: the router is forwarding traffic for the VIP. It sends hello messages at the configured interval. If a hello is not received from another router with a higher priority, the Master remains the Master.

The default timers (VRRPv2) are hello = 1 second, hold = 3 seconds (i.e., 3 missed hellos before failover). With these defaults, the failover time is 3-4 seconds: 3 seconds for the hold to expire, plus 0-1 second for the new Master to start sending hello messages and the LAN to update its MAC table. The lesson's planner models the default timer behavior and shows the failover time.

The sub-second failover is achieved by reducing the hello timer to 100 ms and the hold timer to 300 ms (3 × hello), and by binding BFD with a 50 ms × 3 = 150 ms interval. With BFD, the failover time is 150 ms (BFD detection) + 50 ms (BGP / FIB update) = 200 ms — well under 500 ms. The lesson's planner computes the failover time for a given hello, hold, BFD interval, BFD multiplier, and FIB install time.

### The priority, the preemption, and the skew-time trick

The **priority** (0-255, default 100) determines which router is the Master. The router with the higher priority wins the election, and ties are broken by the higher primary IP. A priority of 0 is reserved for "this router is leaving the group" and forces an immediate failover.

The **preemption** flag determines whether a higher-priority Backup that joins the group (or returns from failure) takes over the Master role from a lower-priority Master. With preemption enabled (the default), the higher-priority router takes over; with preemption disabled, the lower-priority Master remains the Master until it fails.

The **skew-time** trick (defined in RFC 3768 and preserved in VRRPv3) makes the failover ordering deterministic. The skew time is `(256 - priority) / 256` seconds, subtracted from the hello interval. A router with priority 110 has a skew of `(256 - 110) / 256 = 0.57` seconds, so its effective hello is 0.43 seconds with a configured 1-second hello. A router with priority 120 has a skew of 0.53 seconds, so its effective hello is 0.47 seconds. The router with the shorter effective hello sends hellos more often and therefore wins the election more often in a tie. The lesson's planner uses skew time to ensure DIST-A is always the Master for groups 1-6 and DIST-B is always the Master for groups 7-12.

### The asymmetric-routing pitfall and the multi-group design

The **asymmetric-routing pitfall** is the most common VRRP design mistake. With multi-group VRRP (group 1 active on A, group 2 active on B), the return traffic from a server to a host on the LAN may land on a different router than the request. The host sends the request to VIP-1 (active on A), the request is forwarded to the server via A, the server sends the response to VIP-2 (active on B), and the response is forwarded to the host via B. If the upstream (the firewall, the ISP) only accepts traffic from VIP-1, the response is dropped. The fix is to either (a) use a single group (single active for both directions), or (b) ensure the upstream accepts traffic from both VIPs, or (c) use source NAT to rewrite the source IP to the active router's loopback.

The lesson's planner models the asymmetric-routing scenario and emits a NAT-based fix.

### BFD augmentation and the verification matrix

**BFD** (Bidirectional Forwarding Detection, RFC 5880 series) is a sub-second hello/ack protocol that runs in the forwarding plane. When BFD is bound to a VRRP session, the VRRP hold-timer is overridden by the BFD detection time. The BFD session is configured with an interval (50-100 ms) and a multiplier (3), giving 150-300 ms detection. The lesson's planner recommends BFD on every VRRP session in the production network.

The **verification matrix** is the operational proof that the failover works as designed. The matrix has 8 test cases:

1. **Steady state**: both routers are up, DIST-A is Master for groups 1-6, DIST-B is Master for groups 7-12, all VIPs respond to ARP, all pings succeed.
2. **DIST-A fails**: DIST-B takes over groups 1-6 within 500 ms, all VIPs still respond, pings succeed after the failover.
3. **DIST-B fails**: DIST-A takes over groups 7-12 within 500 ms.
4. **DIST-A returns**: with preemption, DIST-A takes back groups 1-6 within skew time + 1 hello interval.
5. **DIST-B returns**: with preemption, DIST-B takes back groups 7-12.
6. **Link failure (DIST-A's uplink)**: VRRP remains Master, but traffic forwarding is affected. The fix is object tracking (DIST-A's priority drops to 90 if its uplink fails, and DIST-B takes over).
7. **BFD session failure**: VRRP declares the neighbor down immediately, failover is sub-200 ms.
8. **Asymmetric routing**: a packet from a host on group 1 to a server on group 2 takes the right path; the return traffic takes the right path; no drops at the upstream.

The lesson's `code/main.py` simulates each test case and reports the expected vs. actual outcome.

## Build It

The deliverable is `code/main.py`, a deterministic VRRP state-machine simulator. Inputs are: two router profiles (priority, preemption, hello, hold, BFD), a list of VRRP groups (each with a VIP, a router-A-priority, a router-B-priority, a preemption flag), and a sequence of failure events. Outputs are: a state transition log, a failover-time matrix, a BFD configuration, an asymmetric-routing diagnosis, and a verification matrix.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| State transition log | One entry per state change; timestamp; trigger | Pass |
| Failover-time matrix | Hello + hold + BFD + FIB for each scenario | Pass |
| BFD configuration | 50 ms × 3; sub-200 ms detection; bound to all groups | Pass |
| Skew-time plan | DIST-A active for groups 1-6; DIST-B for groups 7-12; skew documented | Pass |
| Asymmetric-routing diagnosis | Multi-group design flagged; NAT fix recommended | Pass |
| Verification matrix | 8 test cases; expected vs. actual | Pass |
| Configuration skeleton | Cisco / Juniper / FRR vendor-neutral | Pass |

## Ship It

The artifact is `outputs/vrrp_plan.json` plus the printout. The output directory should also contain `vrrp.conf` (the vendor-neutral VRRP configuration) and `vrrp_runbook.md` (the failover runbook with the verification matrix).

## Exercises

1. **Compute the failover time for hello=1s, hold=3s, BFD=50ms×3, FIB=50ms.** What is the failover time? At what priority does skew time become relevant?

2. **Skew-time ordering.** Two routers with priority 100 and 110, hello 1s, hold 3s. What is the effective hello of each? Which router sends hellos more often? Which router wins a tie?

3. **Asymmetric routing detection.** A tracepath from a host on group 1 to a server on group 2 shows the request going via DIST-A and the response going via DIST-B. What is the upstream seeing? How is the asymmetry fixed?

4. **Preemption and the return from failure.** DIST-A is the Master, DIST-B is the Backup. DIST-A fails, DIST-B takes over. DIST-A returns. With preemption enabled, how long does it take for DIST-A to take back the Master role? Without preemption, what happens?

5. **BFD and the missed hello.** BFD interval is 50 ms, multiplier 3. The link drops for 200 ms and then returns. Does the VRRP session flap? What is the BFD state after the link returns?

6. **Object tracking and the uplink failure.** DIST-A is the Master, its uplink to the firewall fails. Without object tracking, what happens? With object tracking (DIST-A's priority drops to 90 on uplink failure), what happens?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| VRRP | "Virtual Router Redundancy Protocol" | An open-standard FHRP defined in RFC 3768 (v2) and RFC 5798 / RFC 9568 (v3) |
| HSRP | "Hot Standby Router Protocol" | A Cisco-proprietary FHRP similar to VRRP; uses a different virtual MAC |
| GLBP | "Gateway Load Balancing Protocol" | A Cisco-proprietary FHRP that load-balances across multiple routers using different virtual MACs |
| Virtual IP (VIP) | "The shared IP" | The IP that the host uses as its default gateway, shared by the active and standby routers |
| Virtual MAC | "The shared MAC" | The MAC address (`0000.5E00.01xx` for VRRP) that responds to ARP requests for the VIP |
| Preemption | "The higher-priority router takes over" | A flag that determines whether a returning higher-priority Backup takes over the Master role |
| Skew time | "Subtracted from the hello interval" | A RFC 3768 mechanism that makes failover ordering deterministic when priorities are close |
| BFD | "Bidirectional Forwarding Detection" | A sub-second hello/ack protocol (RFC 5880) that augments VRRP for faster detection |
| Object tracking | "Track the uplink state" | A mechanism that reduces the router's priority when a tracked interface goes down, triggering a graceful failover |
| Asymmetric routing | "Request and response take different paths" | A multi-group VRRP pitfall where the return traffic lands on a different router than the request |

## Further Reading

- **RFC 2281** — *Cisco Hot Standby Router Protocol (HSRP)* — original HSRP
- **RFC 3768** — *Virtual Router Redundancy Protocol (VRRP)* — VRRPv2
- **RFC 5798** — *Virtual Router Redundancy Protocol (VRRP) Version 3 for IPv4 and IPv6* — VRRPv3
- **RFC 9568** — *Virtual Router Redundancy Protocol (VRRP) Version 3 for IPv4 and IPv6* — VRRPv3 (obsoletes 5798)
- **RFC 5880-5884** — *Bidirectional Forwarding Detection (BFD)* — BFD specification
- **Cisco IOS-XE VRRP configuration guide** — vendor implementation
- **Juniper Junos VRRP configuration guide** — vendor implementation
- **Aruba CX VRRP configuration guide** — vendor implementation
- **FRRouting VRRP documentation** — open-source implementation
- **Nokia SR Linux VRRP documentation** — vendor implementation
- **keepalived documentation** — the open-source VRRP implementation on Linux
