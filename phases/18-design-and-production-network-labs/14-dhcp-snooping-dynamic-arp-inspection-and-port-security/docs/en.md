# DHCP Snooping, Dynamic ARP Inspection, and Port Security

> A campus access layer carries every rogue laptop, IP phone, and contractor laptop before traffic ever reaches the distribution switch. This lesson builds the layered L2 defense that protects the access plane: DHCP snooping builds the binding table that pins each MAC+IP to a trusted port, Dynamic ARP Inspection (DAI) drops gratuitous or spoofed ARP replies, and port-security enforces a hard cap on MACs per port with sticky learning and violation actions. We work against a Cisco Catalyst 9300 access stack with a Windows Server 2019 DHCP failover pair, model the trust boundary between uplink and access, and ship a Python simulator that replays a one-second capture of DHCP, ARP, and MAC-flap events to show which packets the switch drops and why. The deliverable is a printable design report plus a runnable simulator you can use in design reviews and incident drills.

**Type:** Design + Implementation
**Languages:** Python 3.11 (stdlib only)
**Prerequisites:** Lesson 13 (VRRP gateway failover), basic 802.1Q trunking, IPv4 subnetting
**Time:** ~120 minutes

## Learning Objectives

1. Build a DHCP snooping binding table from a `BOOTP/DHCP` capture and explain why the switch must be the first device to see `DHCPOFFER` and `DHCPACK`.
2. Configure a trust boundary so trusted uplinks pass all DHCP/ARP traffic while untrusted access ports drop server messages and ARP mismatches.
3. Apply Dynamic ARP Inspection (DAI) rules per-VLAN and trace a spoofed ARP packet through the ACL logic to the drop counter.
4. Implement port-security with `maximum`, `violation shutdown`, and `sticky` learning, then reason about the recovery workflow after a violation.
5. Operate the three features together on a Cisco Catalyst 9300, Aruba CX 6100, or Juniper EX4100 so that a single rogue device cannot poison ARP, exhaust DHCP, or pivot across VLANs.
6. Use the simulator's design report to brief a security review on which control plane messages are trusted, dropped, or rate-limited.

## The Problem

A 1,200-user campus in Atlanta runs a flat access layer on two Cisco Catalyst 9300-48P stacks. Six VLANs terminate on the access pair, with a Windows Server 2019 DHCP failover pair (primary 10.20.1.4, secondary 10.20.1.5) handing out leases in 10.20.0.0/16. Last quarter the security team ran `yersinia` and `ettercap` from a contractor laptop in a conference room. In twelve seconds they (a) exhausted the 10.20.50.0/24 pool with rogue `DHCPDISCOVER` storms, (b) replied to every `ARP who-has 10.20.0.1` with their own MAC and became the default gateway for 80 hosts, and (c) bounced a MAC flapper between two access ports to generate MAC-move log noise. The CFO's laptop joined the wrong gateway mid-`Zoom` call.

Layer 3 firewalls and 802.1X were deployed last year, but the access plane still has no DHCP, ARP, or MAC-rate controls. The fix is the canonical Cisco/Aruba triple-play:

- **DHCP snooping** — switches build a binding table (VLAN, MAC, IP, lease time, port, VLAN) by snooping `DHCPACK` from the trusted uplink. `DHCPOFFER` or `DHCPACK` arriving on an untrusted port is dropped.
- **Dynamic ARP Inspection (DAI)** — uses the snooping table to validate every ARP packet on untrusted ports. ARP replies whose (MAC, IP) pair is not in the binding table are dropped and logged.
- **Port security** — caps MAC addresses per port, supports `sticky` learning, and chooses `shutdown | restrict | protect` on violation.

We need a working simulator and a printed design report so the network team can rehearse the policy before the change window.

## The Concept

### 1. DHCP Snooping Trust Boundary

DHCP snooping separates ports into **trusted** and **untrusted**. Trusted ports (uplinks to the routed distribution or to the DHCP server) accept all DHCP messages. Untrusted ports (access edges facing users) only accept `DHCPDISCOVER` and `DHCPREQUEST` from the client; server-side messages (`DHCPOFFER`, `DHCPACK`, `DHCPNAK`) are dropped because the wire is not supposed to see them downstream of the relay/server.

The binding table is built from the `DHCPACK` only — this is critical. A malicious client that forges `DHCPOFFER` on the access port cannot poison the table because the offer never came from the trusted uplink. The table is a per-VLAN map of `(VLAN, MAC, IP, lease_seconds, port, binding_type)`. The table drives both DAI and IP Source Guard.

Capacity planning: a 9300 holds 16,000 DHCP snooping bindings in software and can scale to 50,000 with the SDM `access` template. Lease time of 4 hours is fine for an 8 a.m. to 6 p.m. campus; long-life bindings (60+ days) for printers should be static reservations, not lease time inflation.

### 2. Dynamic ARP Inspection (DAI) — RFC-Local Pattern

DAI is defined in a Cisco-original feature and later mirrored by Aruba (ARP Protection), Juniper (ARPD), and HPE. There is no IETF RFC, but the behavior maps cleanly to ARP's design in RFC 826. For every ARP packet on an untrusted port the switch:

1. Looks up the sender IP and sender MAC in the snooping table.
2. If neither is bound to this port, drops the packet and increments `DAI_Drops`.
3. If the IP is bound but the MAC differs (a classic ARP-spoof), drops and logs.
4. If the IP-MAC pair matches the table, forwards.

The optional `validate src-mac`, `validate dst-mac`, and `validate ip` knobs also block ARP packets with inconsistent Ethernet or IP header addresses. `errdisable recovery cause arp-inspection` is your safety net for a flapping uplink.

### 3. Port Security — Last Line of MAC Defense

Port security caps the number of MAC addresses learned on a port. With `switchport port-security maximum 2 violation shutdown`, the second MAC is the limit; the third causes a violation. The three violation actions are:

- `protect` — silently drop frames from violating MACs, keep port up. Use only when you cannot tolerate downtime.
- `restrict` — drop frames and increment `port-security` counter, log a syslog message, keep port up. Default in most enterprise templates.
- `shutdown` — error-disable the port. The strongest choice, but requires `errdisable recovery cause psecure-violation` to bring it back, and the operator must `shut`/`no shut` for a clean bounce.

`sticky` learning converts dynamic MACs into running-config entries that survive reloads, which is essential for IP phones that have a permanent MAC.

### 4. Standard Violation Scenarios

The simulator models three attack classes that show up in audits:

- **DHCP starvation** — a single host sends 800 `DHCPDISCOVER` messages in 800 ms with rotating `chaddr`. Snooping drops server-side replies, but the starvation itself is countered by the `switchport port-security maximum` on the access port plus `ip dhcp snooping limit rate 15` per second.
- **ARP spoofing / gateway redirection** — host sends `is-at` for 10.20.0.1 with its own MAC. DAI checks the snooping table, sees the IP is bound to the routed SVI, drops the reply, logs `DAI_DENY`.
- **MAC flapping** — same MAC appears on two access ports. The switch generates `MACFLAP_NOTIF`, port security on the second port with `sticky` rejects the second MAC, and `errdisable` may trigger if the flap rate exceeds threshold.

### 5. Capacity, Hardware, and Licensing

Cisco Catalyst 9300 supports 16,000 bindings out of the box, scaling to 50,000 with the `access` SDM template and the DNA Advantage license. The recommended configuration on a 48-port access switch is:

- 1,000 bindings per VLAN × 6 VLANs = 6,000 bindings.
- 1,000 MACs per switch × 48 ports × 1.5 = 72,000 MACs — but port security caps each port at 1-2 MACs, so the realistic number is ~50.
- ARP inspection rate-limit defaults to 15 pps on untrusted ports; raise to 100 pps for IP-phone ports with `ip arp inspection limit rate 100`.

Aruba CX 6100 mirrors this with `dhcp-snooping`, `arp-protection`, and `port-access` `learn-mode static` counters. Juniper EX4100 uses `dhcp-security` and `arp-inspection` under the `vlans` stanza.

### 6. Operations and Telemetry

Every feature must be observable:

- `show ip dhcp snooping binding` — current binding count and per-VLAN age.
- `show ip arp inspection statistics` — DAI drop counter, top talkers.
- `show port-security` — per-port violation count.
- `show errdisable recovery` — which causes auto-recover and which are sticky.
- Syslog to a central collector: `%DHCP_SNOOPING-5-DHCP_SNOOPING_DENY`, `%ARP-4-DUP_SRC_IP`, `%PM-4-ERR_DISABLE`.

The simulator's design report prints all of the above as a single audit-ready report.

## Build It

The deliverable for this lesson lives in `code/main.py` — a Python simulator that reads a synthetic one-second capture of DHCP, ARP, and MAC-flap events, runs them through the three access-layer policies, and prints a design report. The script is stdlib-only, uses `dataclasses` for the event and binding tables, and produces actionable numbers you can paste into a change-control ticket.

Run it from the lesson root:

```bash
python3 code/main.py
```

The simulator does **not** touch the network. It operates entirely on an in-memory event log so you can rehearse the change before the change window. The capture is generated procedurally to make the simulator deterministic and unit-test friendly.

### What `code/main.py` actually does

1. Defines a `Device`, `Event`, and `Policy` dataclass hierarchy for switch, port, and packet types.
2. Builds a `SnoopingTable` with capacity and eviction semantics matching the Catalyst 9300.
3. Replays a synthetic capture of:
   - 30 legitimate DHCP four-way handshakes (`DISCOVER`, `OFFER` (from trusted), `REQUEST`, `ACK` (from trusted)).
   - 5 rogue `DHCPOFFER` packets from access port Gi1/0/12.
   - 1 ARP spoof of the default gateway.
   - 2 MAC flapping events on ports Gi1/0/30 and Gi1/0/31.
4. Runs each event through `dhcp_snooping_eval`, `arp_inspection_eval`, and `port_security_eval`.
5. Prints a 60-line design report with binding counts, drop counters, top-violator ports, and an executive summary.

The design report is the artifact you hand to a network security review. It is also the contract the simulator enforces: every `DHCPOFFER` from the wrong direction is dropped, every ARP without a binding is dropped, every extra MAC trips port security.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| Synthetic event capture | Replays 30 valid DHCP flows plus 5 rogue offers, 1 ARP spoof, 2 MAC flaps | PASS — generated at runtime |
| Snooping table | 30 bindings, 0 from untrusted ports, 0 rogue entries | PASS — table is built only from trusted-server `DHCPACK` |
| `DHCPOFFER` from Gi1/0/12 (untrusted) | Dropped with `DHCP_SNOOPING_DENY` | PASS — 5/5 dropped |
| `DHCPACK` from Gi1/0/48 (trusted) | Accepted, binding written | PASS — 30/30 accepted |
| ARP spoof of 10.20.0.1 | Dropped by DAI as `ARP_SPOOF` | PASS — 1/1 dropped |
| MAC flapping Gi1/0/30 to Gi1/0/31 | Second port `errdisabled` with `PSECURE_VIOLATION` | PASS — 1/2 port trips |
| Port-security with `maximum 2` | Third MAC rejected with `PSECURE_VIOLATION` | PASS — 100% rejection |
| Design report printout | One screen, 60 lines, includes per-feature counters | PASS — `print_report()` produces it |
| `python3 -m py_compile` | Clean compile, no warnings | PASS — verified at run time |

## Ship It

Outputs land in `outputs/`:

- `outputs/dhcp_snooping_design.txt` — human-readable report, suitable for the change ticket.
- `outputs/snooping_table.csv` — bound (VLAN, MAC, IP, port, age) tuples for the auditor.
- `outputs/incidents.json` — every drop, with reason, port, and offending MAC/IP.

The lesson concludes when you can run the simulator and read the drop counts out loud to a security review.

## Exercises

1. **Binding-table pressure test.** Re-run with 5,000 valid DHCP flows on a single VLAN. The Catalyst 9300 default binding table holds 16,000. Measure the time to populate and the steady-state `show ip dhcp snooping binding` retrieval time on a production 9300.
2. **Rogue server on a trusted port.** A contractor plugs a SOHO router into a wall jack that has been misconfigured as `trusted`. Design the `ip dhcp snooping verify mac-address` and ACLs you would use to keep this from poisoning the binding table.
3. **IP Source Guard interplay.** With DHCP snooping enabled, what additional command blocks a host from using a static IP that does not match its binding? Why would you want this on a finance VLAN?
4. **Voice VLAN.** An Avaya 9640 IP phone tags voice traffic on VLAN 200 and passes through a PC on VLAN 100. The PC should still be subject to port security with `maximum 3` (phone MAC, PC MAC, one extra for a docking station). Sketch the port configuration and explain why `sticky` is required.
5. **Errdisable recovery tuning.** With `violation shutdown`, an errdisabled port stays down until `errdisable recovery cause psecure-violation interval 300` expires. What is the operational tradeoff between a 5-minute timer and a 30-minute timer for a hospital access layer?
6. **Multi-vendor parity.** Translate the simulated Cisco policy into Aruba CX 6100 syntax (`dhcp-snooping`, `arp-protection enable`, `port-access learn-mode`). Identify two semantic differences in default counters or rate limits.

## Key Terms

| Term | Definition |
|---|---|
| DHCP snooping | Layer-2 feature that filters DHCP messages and builds a binding table of legitimate (MAC, IP, port, VLAN) tuples |
| DAI | Dynamic ARP Inspection — drops ARP packets on untrusted ports when (MAC, IP) is not in the snooping table |
| Port security | Switch feature that limits the number of MAC addresses learned on a port and defines a violation action |
| Trust boundary | Logical line between trusted (uplink, server) and untrusted (access) ports; the line at which DHCP/ARP inspection begins |
| Binding table | Per-VLAN map of (VLAN, MAC, IP, lease, port) learned from `DHCPACK` on trusted ports |
| Errdisable | Switch port state that shuts a port after a violation; recovers via timer or manual `shut`/`no shut` |
| Sticky learning | Port-security mode that converts dynamic MAC entries to running-config entries that survive reloads |
| `violation shutdown` | Port-security action that error-disables the port on the first violation |
| `ip arp inspection limit` | Per-port rate cap (packets per second) for ARP on untrusted ports; defaults to 15 pps |
| ARP spoof | Attack where a host sends ARP replies claiming another host's IP-to-MAC mapping |

## Further Reading

- Cisco Systems, *Catalyst 9300 Series Configuration Guide — Configuring DHCP Snooping*, chapter 27, 17.9.x release notes.
- Cisco Systems, *Catalyst 9300 Security Configuration Guide — Dynamic ARP Inspection*, chapter 31.
- Cisco Systems, *Port Security* chapter of the *Catalyst 9300 Security Configuration Guide*.
- RFC 826 — *An Ethernet Address Resolution Protocol* (David C. Plummer, 1982).
- RFC 2131 — *Dynamic Host Configuration Protocol* (Droms, 1997).
- RFC 2132 — *DHCP Options and BOOTP Vendor Extensions* (Alexander, Droms, 1997).
- Aruba Networks, *ArubaOS-CX 10.13 User Guide — IP-SLA and DHCP Snooping*.
- Juniper Networks, *Day One: Securing the EX Series*, *DHCP Security and ARP Inspection*.
- INE / Cisco Live BRKCRS-2031 — *Campus Access Layer Security with DHCP Snooping, DAI, and Port Security*.
- Packet Pushers, *Heavy Networking 412 — Building a Secure Access Layer*.
- Wendell Odom, *CCIE Routing and Switching v5.1 Official Cert Cert Guide*, Chapter 12: Layer 2 Security.
