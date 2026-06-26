# IPv6 Dual-Stack Rollout with SLAAC and DHCPv6 Prefix Delegation

> IPv4 addresses are exhausted, ARIN is in its "phase 4" of IPv4 exhaustion with no new allocations, and the per-IP cost on the secondary market is now $35-$60 per usable address. The transition to IPv6 is no longer optional — it is the cost of staying in business. A well-planned IPv6 dual-stack rollout gives a production network the same services on IPv6 that it has on IPv4, with the same or better operational properties, and it does so in 12-18 months with a per-site capex of $5K-$30K. This lesson is the working playbook for an enterprise dual-stack rollout: the addressing plan (the global unicast block, the site allocations, the prefix delegation hierarchy), the host autoconfiguration (SLAAC for stateless, DHCPv6 for stateful, RDNSS for DNS server discovery, RFC 8106 for DNS configuration), the prefix delegation (DHCPv6-PD from the upstream to the customer edge, then to the internal subnets), the transition mechanisms (464XLAT, NAT64, DS-Lite, MAP-E for IPv4-as-a-service over an IPv6-only access), the security baseline (RA Guard, DHCPv6 Guard, IPv6 firewall), and the operational runbook (the dual-stack cutover, the IPv4 deprecation, the monitoring and alerting). The deliverable is a Python dual-stack planner that takes a site count, a user count, an upstream IPv6 block, and a set of internal subnets, and outputs the addressing plan, the SLAAC/DHCPv6 configuration, the prefix delegation hierarchy, the transition-mechanism selection, and the cutover runbook.

**Type:** Project
**Languages:** Python (stdlib only: dataclasses, ipaddress, json, enum), shell, radvd, Wireshark
**Prerequisites:** Phase 8 IPv6 fundamentals, Phase 12 DNS, Phase 18 lessons 09 (multihoming) and 16 (anycast)
**Time:** ~150 minutes

## Learning Objectives

- Explain the **dual-stack model** (every host has both an IPv4 and an IPv6 address, every service listens on both, DNS returns both) and the **IPv6-only model** (hosts have only IPv6, services listen only on IPv6, IPv4 is provided via 464XLAT / NAT64 / DS-Lite) and choose the right model for the network.
- Design the **addressing plan**: a global unicast block (typically /32 from the upstream or a RIR allocation), a per-site /48 (65,536 subnets), a per-subnet /64 (the SLAAC minimum), and a prefix delegation hierarchy (the upstream delegates a /48 to the customer edge, the edge delegates /56s to the site routers, the site routers delegate /64s to the LANs).
- Configure **SLAAC** (RFC 4861/4862) with Router Advertisements from `radvd` or the router's built-in RA, with the A, M, and O flags controlling whether the host uses SLAAC-only, DHCPv6-only, or SLAAC+DHCPv6, and with **RDNSS** (RFC 8106) advertising the DNS server addresses in the RA.
- Configure **DHCPv6** (RFC 8415) for stateful address assignment, for prefix delegation (the IA_PD option), and for DNS server option (RFC 3646), with the right authentication and the right logging.
- Choose the right **transition mechanism** (464XLAT for mobile/IoT, NAT64 for enterprise, DS-Lite for residential broadband, MAP-E for service-provider access) and configure the corresponding CLAT (Customer-side Translator) and PLAT (Provider-side Translator).
- Build a **cutover runbook** for the dual-stack migration: the IPv6 addressing plan validation, the per-service dual-stack cutover, the DNS AAAA record addition, the IPv4 deprecation, and the monitoring of IPv4 vs IPv6 traffic.

## The Problem

"Meridian Manufacturing" operates 22 factories, each with 100-300 industrial controllers, 50-100 engineering workstations, and a corporate WAN. The IT team has been told by the board that the IPv4 address budget is exhausted (they are using carrier-grade NAT for 40% of their IPv4 egress, and the cost is $0.0008 per IPv4 address per month) and that an IPv6 rollout is required within 18 months. The senior engineer must deliver a dual-stack rollout: every factory gets a /48 from the upstream, every subnet gets a /64, every host has an IPv6 address, every service listens on IPv6, and the DNS returns both A and AAAA records.

The lesson's planner builds the addressing plan, the SLAAC/DHCPv6 configuration, the prefix delegation hierarchy, and the cutover runbook.

## The Concept

### The addressing plan and the /48-per-site rule

The **addressing plan** is the foundation of a successful IPv6 rollout. The plan is built from a global unicast block (typically a /32 from the RIR for a large enterprise, or a /48 delegated by the upstream for a small enterprise) and is partitioned into per-site blocks, per-subnet blocks, and per-host addresses. The /48-per-site rule (RFC 6177) gives each site 65,536 /64 subnets, which is more than enough for a factory of 300 hosts (typically 10-20 subnets: one per VLAN, plus a few for the management plane, the industrial control plane, the guest network, and the future growth).

The upstream (e.g., the ISP or the corporate WAN provider) delegates a /48 to the customer edge via DHCPv6-PD. The customer edge delegates a /56 to each site router via DHCPv6-PD (a /56 has 256 /64 subnets, which is plenty for a factory). The site router assigns a /64 to each VLAN. The host configures its address via SLAAC or DHCPv6.

The lesson's planner computes the addressing plan for a given number of sites, subnets per site, and hosts per subnet.

### SLAAC, DHCPv6, and the A/M/O flag matrix

**SLAAC** (RFC 4861/4862) is the host's stateless mechanism for configuring its own IPv6 address. The router sends Router Advertisements (RAs) periodically (typically every 30-60 seconds) and in response to Router Solicitations. The RA contains the prefix (e.g., 2001:db8:1::/64), the A flag (SLAAC address assignment), the M flag (DHCPv6 managed address), the O flag (other DHCPv6 options, e.g., DNS), and the router lifetime.

The flag matrix is:

| A flag | M flag | O flag | Behavior |
|--------|--------|--------|----------|
| 1 | 0 | 0 | SLAAC only (host configures its own address, no DHCPv6) |
| 0 | 1 | 1 | DHCPv6 only (host gets address from DHCPv6) |
| 1 | 1 | 1 | SLAAC + DHCPv6 (host configures its own address, gets DNS from DHCPv6) |
| 0 | 0 | 1 | No address, but get DNS from DHCPv6 (rare) |

The lesson's planner emits the RA configuration for each combination, with the right M and O flags, the right prefix, and the right RDNSS (RFC 8106) for DNS server advertisement.

**DHCPv6** (RFC 8415) is the stateful mechanism. The host sends a Solicit, the server responds with an Advertise, the host sends a Request, the server responds with a Reply. The state is held on the server, and the server logs every assignment for audit. The IA_PD (Identity Association for Prefix Delegation) option is used for prefix delegation, and the IA_NA (Identity Association for Non-temporary Address) option is used for address assignment.

### Prefix delegation and the IA_PD hierarchy

**Prefix delegation** (RFC 8415 section 6.6) is the mechanism by which a customer edge requests a prefix from the upstream, and the upstream delegates a /48 (or whatever the customer's allocation is) to the customer edge. The customer edge then delegates /56s to the site routers, which delegate /64s to the LANs. The IA_PD option carries the prefix length, the valid lifetime, and the preferred lifetime.

The lesson's planner emits the DHCPv6 configuration for each tier (upstream, customer edge, site router) with the right IA_PD lengths and the right lifetime values.

### Transition mechanisms: 464XLAT, NAT64, DS-Lite, MAP-E

The transition mechanisms are the IPv4-as-a-service-over-IPv6 architectures that let an IPv6-only host reach an IPv4-only destination:

- **464XLAT** (RFC 6877): the host runs a CLAT (Customer-side Translator) that translates IPv4 to IPv6 and vice versa. The provider runs a PLAT (Provider-side Translator) that does the inverse. The host's IPv4 socket is translated to an IPv6 packet that is routed over the IPv6-only access to the PLAT, which translates it back to IPv4 for the destination. 464XLAT is appropriate for mobile and IoT, where the host stack may be IPv6-only.
- **NAT64** (RFC 6146): the provider runs a NAT64 gateway that translates IPv6 to IPv4 and vice versa. The host has an IPv6 address and an IPv4-mapped IPv6 address (the well-known prefix `64:ff9b::/96`). When the host queries an IPv4-only destination, the DNS64 (RFC 6147) returns the IPv4-mapped IPv6 address, and the host sends the packet to the NAT64, which translates and forwards.
- **DS-Lite** (RFC 6333): the customer edge encapsulates the IPv4 packet in an IPv6 tunnel to the provider's AFTR (Address Family Transition Router), which decapsulates and forwards. DS-Lite is appropriate for residential broadband.
- **MAP-E** (RFC 7597): the customer edge and the provider share a mapping rule (port-set + IPv6 prefix), and the customer edge translates the IPv4 packet to an IPv6 packet using the mapping rule. MAP-E is appropriate for service-provider access where the operator wants fine-grained control over port allocation.

The lesson's planner selects the right mechanism for the network (typically 464XLAT for mobile, NAT64 for enterprise, DS-Lite for residential).

### Security: RA Guard, DHCPv6 Guard, IPv6 firewall

The IPv6 security baseline includes:

- **RA Guard** (RFC 6105): the switch drops RAs from any port that is not a router port. This prevents a malicious host from sending RAs and becoming the default router.
- **DHCPv6 Guard**: the switch drops DHCPv6 server messages from any port that is not a server port. This prevents a malicious host from becoming a DHCPv6 server.
- **IPv6 firewall**: every IPv6-aware firewall should block inbound ICMPv6 to the global unicast addresses (except for the necessary ICMPv6 types: Neighbor Discovery, Router Advertisement, etc.), block IPv6 source routing, and log all other inbound traffic.

The lesson's planner emits the switch and firewall configuration with the right RA Guard, DHCPv6 Guard, and IPv6 firewall rules.

## Build It

The deliverable is `code/main.py`, a deterministic dual-stack planner. Inputs are: a global /32 (or /48), a list of sites (name, subnets per site, hosts per subnet), an upstream IPv6 block, and a transition-mechanism choice. Outputs are: the addressing plan, the SLAAC/DHCPv6 configuration per site, the prefix delegation hierarchy, the transition-mechanism configuration, and the cutover runbook.

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| Addressing plan | One /48 per site; one /64 per subnet; no overlap | Pass |
| SLAAC configuration | RA per VLAN; A/M/O flags correct; RDNSS correct | Pass |
| DHCPv6 configuration | IA_NA for hosts; IA_PD for prefix delegation; lifetime correct | Pass |
| Prefix delegation hierarchy | Upstream /32 -> customer /48 -> site /56 -> subnet /64 | Pass |
| Transition mechanism | 464XLAT / NAT64 / DS-Lite / MAP-E selected and configured | Pass |
| Security baseline | RA Guard, DHCPv6 Guard, IPv6 firewall | Pass |
| Cutover runbook | Per-service dual-stack cutover; DNS AAAA addition; IPv4 deprecation | Pass |

## Ship It

The artifact is `outputs/dualstack_plan.json` plus the printout. The output directory should also contain `radvd.conf.site-XX` (the SLAAC configuration per site), `dhcpd6.conf.site-XX` (the DHCPv6 configuration per site), and `cutover_runbook.md` (the cutover runbook).

## Exercises

1. **Compute the /48 per site for 22 sites and 5 subnets per site.** How many subnets are available per site? How much growth room?

2. **Design the RA for a subnet that should use SLAAC only.** What are the A, M, O flags? What is the prefix? What is the RDNSS?

3. **Design the RA for a subnet that should use DHCPv6 only.** What are the A, M, O flags?

4. **Compute the IA_PD lifetime for a 30-day lease.** What is the preferred lifetime? The valid lifetime?

5. **464XLAT vs NAT64.** A smartphone has only an IPv6 address. It needs to reach an IPv4-only web server. Which mechanism is appropriate? How is the translation performed?

6. **RA Guard and the rogue RA attack.** A malicious host sends RAs on a user port. What is the impact? How is RA Guard configured?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| SLAAC | "The host configures its own address" | RFC 4861/4862 stateless address autoconfiguration using Router Advertisements |
| DHCPv6 | "The server configures the host's address" | RFC 8415 stateful address configuration with IA_NA, IA_PD, and other options |
| RDNSS | "DNS server in the RA" | RFC 8106 mechanism for advertising DNS server addresses in Router Advertisements |
| Prefix delegation | "Upstream gives me a /48" | RFC 8415 mechanism for an upstream to delegate a prefix to a downstream router |
| 464XLAT | "IPv4 over IPv6 access" | RFC 6877 mechanism with CLAT (customer) and PLAT (provider) translators |
| NAT64 | "Translate at the provider edge" | RFC 6146 mechanism with NAT64 gateway and DNS64 (RFC 6147) |
| DS-Lite | "Tunnel IPv4 over IPv6" | RFC 6333 mechanism with IPv4-in-IPv6 tunnel to the AFTR |
| MAP-E | "Map IPv4 to IPv6 with rules" | RFC 7597 mechanism with port-set + IPv6 prefix mapping |
| RA Guard | "Drop rogue RAs" | RFC 6105 switch feature that drops RAs from non-router ports |
| A/M/O flags | "The RA's three flags" | RFC 4861 flags that control SLAAC, DHCPv6 managed, and DHCPv6 other-options behavior |

## Further Reading

- **RFC 4291** — *IP Version 6 Addressing Architecture* — the IPv6 address architecture
- **RFC 4861, 4862** — *Neighbor Discovery / IPv6 Stateless Address Autoconfiguration* — SLAAC
- **RFC 4941** — *Privacy Extensions for SLAAC* — privacy addresses (random IIDs)
- **RFC 6105** — *IPv6 Router Advertisement Guard* — RA Guard
- **RFC 6177** — *IPv6 End Site Addressing* — /48 per site
- **RFC 8106** — *IPv6 Router Advertisement Options for DNS Configuration* — RDNSS
- **RFC 8415** — *Dynamic Host Configuration Protocol for IPv6 (DHCPv6)* — DHCPv6
- **RFC 6877** — *464XLAT* — 464XLAT
- **RFC 6146, 6147** — *NAT64 / DNS64* — NAT64 and DNS64
- **RFC 6333** — *Dual-Stack Lite Broadband Deployments* — DS-Lite
- **RFC 7597** — *Mapping of Address and Port (MAP)* — MAP-E
- **Cisco IPv6 configuration guides** — vendor implementation
- **Juniper Junos IPv6 User Guide** — vendor implementation
- **radvd documentation** — the open-source SLAAC daemon
- **wide-dhcpv6 documentation** — the open-source DHCPv6 server
- **ISC Kea DHCP documentation** — modern DHCPv4/DHCPv6 server
- **ARIN IPv6 allocation policies** — RIR allocation rules
