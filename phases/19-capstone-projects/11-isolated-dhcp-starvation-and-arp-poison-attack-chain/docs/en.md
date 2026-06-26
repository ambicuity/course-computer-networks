# Isolated DHCP Starvation and ARP Poison Attack Chain

> Build a defensive simulation of the canonical L2 attack chain. An attacker first exhausts the DHCP server's address pool by flooding it with Discover messages carrying forged client MAC addresses (sequential 00:11:22:33:00:01..00:FE, or fully random bytes, or OUIs mimicking legitimate vendors), draining the 245-address pool of 10.0.0.10..10.0.0.254 in roughly 750 ms. With legitimate clients unable to obtain leases, the attacker broadcasts gratuitous ARP replies that map the gateway 10.0.0.1 to attacker MAC AA:AA:AA:AA:AA:AA, hijacking the default route of every poisoned host. The capstone pairs the offensive simulation with three production mitigations: DHCP snooping with trusted ports and rate-limited Discovers (10/s), Dynamic ARP Inspection that validates ARP packets against the snooping binding table, and port security that caps MACs per port at one and shuts down violations. Detection watches pool utilization (alert at 90 percent), OUI entropy, and gratuitous ARP conflicts.

**Type:** Capstone
**Languages:** Python (stdlib only), packet traces, shell
**Prerequisites:** Phase 17 packet-capture tooling; understanding of DHCP DORA from Phase 8; ARP mechanics from Phase 5; familiarity with switch forwarding tables
**Time:** ~180 minutes

## Learning Objectives

- Implement the DHCP DORA exchange (Discover, Offer, Request, Acknowledge) as a stateful four-message protocol, including NAK handling when the pool is exhausted.
- Reproduce DHCP starvation by flooding a 245-address pool with forged MACs and demonstrate the failure mode for the next legitimate client that asks for a lease.
- Reproduce ARP poisoning via gratuitous ARP replies that overwrite the gateway mapping in victim ARP caches, and quantify the man-in-the-middle blast radius.
- Detect starvation by monitoring pool utilization, MAC entropy, OUI distributions, and Discover rate over a sliding window.
- Detect ARP poisoning by comparing gratuitous ARP replies against the DHCP snooping binding table.
- Configure DHCP snooping with trusted uplink ports, untrusted access ports, and per-port Discover rate limits.
- Configure Dynamic ARP Inspection (DAI) so ARP packets are dropped when their IP-to-MAC binding does not match the snooping table.
- Configure port security with MAC limits (default one) and violation actions (protect / restrict / shutdown).
- Reason about defense-in-depth composition: snooping filters the DHCP layer, DAI filters the ARP layer, port security filters the MAC layer, and the three together close the attack chain.

## The Problem

A small office LAN has a /24 subnet on 10.0.0.0/24, a DHCP server at 10.0.0.2 with pool 10.0.0.10..10.0.0.254 (245 addresses), and a gateway at 10.0.0.1. There is no switch security configured. An attacker with physical or wireless access to the LAN plugs in and runs a stock tool. Within one second, every legitimate user loses connectivity. No router, firewall, IDS, or application is involved. The compromise happens entirely on Layer 2.

The attack has two phases. Phase one is DHCP starvation: the attacker sends hundreds of DHCP Discover messages, each with a different forged source MAC. The DHCP server dutifully responds with an Offer and Ack for each, allocating one address from the pool. After 245 forged requests the pool is empty, and the next legitimate laptop that wakes up gets no IP. The attacker can also stand up a rogue DHCP server on the same segment, but the pool exhaustion alone is sufficient to deny service.

Phase two is ARP poisoning. With legitimate clients cut off from DHCP or, more commonly, already on the network with stale leases, the attacker broadcasts gratuitous ARP replies that say "10.0.0.1 is at AA:AA:AA:AA:AA:AA." Every operating system that receives a gratuitous ARP updates its cache without question. Now when a victim sends traffic to its default gateway, the frame goes to the attacker. The attacker forwards it onward (a transparent man-in-the-middle) or drops it (a denial of service) or modifies it (credential theft). The attacker can also intercept DNS, HTTPS, and any other traffic whose first hop is the gateway.

The defender's answer is a layered switch configuration. DHCP snooping separates the network into trusted ports (the uplink to the DHCP server) and untrusted ports (user access). DHCP server messages (Offer, Ack) are only accepted from trusted ports. DHCP client messages (Discover, Request) are accepted on untrusted ports but rate-limited to roughly 10 per second per port to defeat exhaustion attempts. Each successful lease is recorded in a binding table keyed by VLAN, MAC, IP, port, and lease time. Dynamic ARP Inspection then checks every ARP packet against that binding table. If a host sends an ARP reply claiming "10.0.0.1 is at AA:AA:AA:AA:AA:AA" but the binding table says 10.0.0.1 was never leased to that MAC, DAI drops the packet. Port security caps the number of MACs per port (typically one) and shuts down the port on violation, neutralizing MAC-flooding variants of the same attack.

This capstone simulates both phases in a stdlib-only Python program, instruments detection logic that mirrors what a network monitoring system would flag, and models each of the three mitigations so the operator can see the residual attack surface shrink after each control is applied.

## The Concept

The attack chain is two independent protocol abuses glued together by their prerequisites. Each one alone is a denial of service; chained, they become an active interception. The mitigations are three independent protocol filters that can be applied individually or together. Understanding the protocol mechanics is the prerequisite for understanding why each mitigation works.

### DHCP DORA exchange step by step

DHCP allocates an IP address through a four-message handshake called DORA. Every field matters for the simulation.

| Step | Direction | Source IP | Dest IP | Source MAC | Dest MAC | Key fields | What the server learns |
|---|---|---|---|---|---|---|---|
| 1. Discover | client -> broadcast | 0.0.0.0 | 255.255.255.255 | client MAC | ff:ff:ff:ff:ff:ff | chaddr, xid, requested IP, option 53=1 | A new client is asking for an address |
| 2. Offer | server -> broadcast (or unicast in RENEW) | server IP | 255.255.255.255 | server MAC | ff:ff:ff:ff:ff:ff | yiaddr (offered IP), siaddr, xid copy, lease time, option 53=2 | The server picked an address and is telling the client |
| 3. Request | client -> broadcast | 0.0.0.0 | 255.255.255.255 | client MAC | ff:ff:ff:ff:ff:ff | xid copy, server identifier, requested IP, option 53=3 | The client accepts the offer and asks the server to confirm |
| 4. Ack | server -> broadcast | server IP | 255.255.255.255 | server MAC | ff:ff:ff:ff:ff:ff | yiaddr (confirmed), lease time, option 53=5 | The server commits the binding |

The `chaddr` field is the client's hardware address (MAC). It is the field the attacker forges. The `xid` is a random 32-bit transaction identifier chosen by the client; the server echoes it so the client can match responses to requests. The `yiaddr` is "your IP address," the one being offered or assigned. A DHCP server checks its pool for a free lease, sets it to IN-USE keyed by chaddr, and emits the Offer. The client typically sends Request broadcast to confirm; the server replies with Ack (or NAK if the request cannot be honored).

When the pool is exhausted, the server still responds to Discover but with a NAK instead of an Offer. A NAK tells the client to stop asking and either use a previously cached lease (if any) or fall back to link-local addressing (169.254.0.0/16 on most OSes). From the defender's perspective, NAKs at high rates are a signal that starvation is in progress.

### Address pool mechanics and exhaustion timeline

The pool in this capstone spans 10.0.0.10 through 10.0.0.254 inclusive, which is 245 addresses. The reservation 10.0.0.1 is the gateway, 10.0.0.2 is the DHCP server, and 10.0.0.3..10.0.0.9 are reserved for infrastructure (printers, switches, APs). The attacker must consume all 245 to deny service to the next client.

| Stage | Addresses consumed | Pool remaining | Time elapsed (3 ms spacing) |
|---|---|---|---|
| Boot | 0 | 245 | 0 ms |
| 10 legitimate clients | 10 | 235 | 500 ms (50 ms each) |
| Starvation begins | 10 | 235 | 600 ms |
| 90 percent threshold | 220 | 25 | ~1260 ms |
| 100 percent exhaustion | 245 | 0 | ~1335 ms |

A naive attacker that sends Discovers at 3 ms intervals exhausts the pool in under 1.4 seconds. A script kiddie running a tool that hammers the network at line rate (one Discover per 100 microseconds) does it in 25 ms. The defender's job is to detect this before the 90 percent threshold so operations can intervene.

### Forged MAC patterns: sequential, random, OUI-mimicry

Forged MACs fall into three patterns that detection logic must distinguish from legitimate client behavior.

Sequential MACs (low effort): The attacker increments the low byte, producing a stream like 02:00:00:00:00:01, 02:00:00:00:00:02, 02:00:00:00:00:03. Detection catches this with a simple monotonic-increment test on the low 24 bits across consecutive samples.

Random MACs (medium effort): The attacker uses a cryptographically random source for all six bytes. The forged stream has high entropy in every byte position. Detection catches this by computing the byte-level Shannon entropy of the captured MACs; a legitimate enterprise client population has 1-3 distinct OUIs (Dell, Lenovo, Apple), so the entropy is bounded. Random forgery produces near-maximum entropy across all 245 samples.

OUI-mimicry (high effort): The attacker forges the first three bytes to match a real vendor OUI (Dell, Cisco, Intel, Apple) and randomizes the remaining three. Detection must compare the OUI distribution against the known vendor mix for that site; an anomalous spike in OUIs that the organization has never purchased is a strong signal. Locally administered MACs (where the least significant bit of the first byte is set) are a useful tell because most legitimate clients use the burned-in address, while tools like `yersinia` and `dhcpstarv` set the locally administered bit to avoid collisions.

### ARP cache state machine

Every IPv4 host maintains an ARP cache mapping IP addresses to MAC addresses. The cache has four observable states.

| State | Cause | Transition | Defender signal |
|---|---|---|---|
| INCOMPLETE | ARP request sent, no reply yet | -> REACHABLE on reply | High INCOMPLETE count for a given IP is a probe signal |
| REACHABLE | Reply received within reachable-time | -> STALE after reachable-time expires | Normal |
| STALE | Reachable-time expired | -> DELAY on next packet to that IP | Normal aging |
| PROBE | Host is verifying a STALE entry | -> REACHABLE on reply, -> FAILED on no reply | Rapid PROBE->FAILED cycles indicate ARP instability |

A gratuitous ARP is an unsolicited ARP reply broadcast to ff:ff:ff:ff:ff:ff, not triggered by a request. The receiving host, upon seeing a gratuitous ARP, updates its cache regardless of the previous state. This is the mechanism the attacker exploits: one gratuitous ARP per victim transitions every victim's gateway entry from REACHABLE to a poisoned REACHABLE.

### Gratuitous ARP attack mechanics

A gratuitous ARP has two shapes: a request where sender IP equals target IP, or a reply with arbitrary mapping. In either case the receiver updates its cache. The attack flow:

```
attacker              broadcast segment
   |                          |
   |--- ARP reply (gratuitous)---|
   |    sender IP  = 10.0.0.1  |
   |    sender MAC = AA:AA:AA:AA:AA:AA  |
   |    target IP  = 10.0.0.1  |
   |    target MAC = AA:AA:AA:AA:AA:AA  |
   |                          |
   |<----- broadcast to all hosts ----|
   |                          |
   |   victim_1 updates ARP: 10.0.0.1 -> AA:AA:AA:AA:AA:AA
   |   victim_2 updates ARP: 10.0.0.1 -> AA:AA:AA:AA:AA:AA
   |   ...
```

Because ARP has no authentication, every victim trusts the unsolicited update. The attacker only needs one packet per victim (or even one packet broadcast to the whole segment, since ARP is not routed). Modern operating systems do honor gratuitous ARPs for updates, though some ignore gratuitous ARPs that conflict with an entry learned via secure NDP or 802.1X.

### DHCP snooping: trusted ports, rate limits, binding table

DHCP snooping divides switch ports into two classes. Trusted ports are the uplinks to legitimate DHCP servers; they are allowed to emit DHCP server messages (Offer, Ack, NAK). Untrusted ports are user access ports; they may emit DHCP client messages (Discover, Request) but not DHCP server messages. Any DHCP server message that arrives on an untrusted port is dropped, and the switch logs a violation.

The switch maintains a binding table populated only from DHCP transactions observed on trusted ports. Each entry contains VLAN, MAC, IP, port, lease time, and a binding type (static or dynamic). The table is consulted by DAI and by IP source guard.

Rate limiting defends against starvation. The switch counts DHCP Discover messages per second per untrusted port. When the count exceeds a configured threshold (commonly 10-15 per second), further Discovers are dropped until the window resets. The rate limit does not block legitimate clients (a real client sends at most a handful of Discovers spaced seconds apart), but it caps the attacker's rate to roughly 10 leases per second, turning a 25 ms exhaustion into a 24.5 second exhaustion that detection can catch.

### Dynamic ARP Inspection (DAI) logic

DAI intercepts every ARP packet on an untrusted port and checks the IP-to-MAC binding against the DHCP snooping table. The check has three cases:

| ARP packet shape | Binding table lookup | Result |
|---|---|---|
| ARP request, sender IP matches a binding | Binding MAC == ARP sender MAC | Allow |
| ARP request, sender IP matches a binding | Binding MAC != ARP sender MAC | Drop, log violation |
| ARP request, sender IP has no binding | (none) | Drop (no legitimate lease) |
| ARP reply, sender IP + MAC match a binding | Match | Allow |
| ARP reply, sender IP + MAC do not match any binding | (none) | Drop (gratuitous ARP with forged mapping) |

The fifth case is the one that defeats the attack. The attacker's gratuitous ARP says "10.0.0.1 is at AA:AA:AA:AA:AA:AA," but the binding table says 10.0.0.1 was never leased to AA:AA:AA:AA:AA:AA (the legitimate binding is to 10.0.0.1's MAC, which is the gateway itself, or 10.0.0.1 is statically bound). DAI drops the packet and increments a violation counter.

### Port security: MAC limits and violation actions

Port security is the third independent filter. It caps the number of source MAC addresses that can be active on a single switch port and configures what happens when the limit is exceeded.

| Violation action | Behavior | Use case |
|---|---|---|
| protect | Silently drop frames from violating MACs | Quiet environments where logging matters more than containment |
| restrict | Drop frames and log a violation (syslog + SNMP trap) | Most enterprise defaults |
| shutdown | Put the port in err-disabled state, requiring manual intervention | High-security environments, often paired with port-security auto-recovery timers |

A typical configuration caps each access port at one MAC. The first MAC seen is learned and becomes the only allowed MAC; any other source MAC triggers the violation action. This defeats two attack variants at once: MAC flooding (where an attacker sends frames with many source MACs to overflow the switch CAM table) and DHCP starvation with a single MAC (where the attacker tries to obtain many leases from the same MAC). The default MAC limit of one matches the physical reality of one workstation per port.

### Defense-in-depth composition

The three controls stack. Snooping filters DHCP at the protocol layer. DAI filters ARP at the protocol layer but depends on snooping's binding table. Port security filters at the MAC layer and is independent. The composition closes the attack chain at every step.

| Attack step | Snooping block | DAI block | Port security block |
|---|---|---|---|
| Forged DHCP Discover | Rate-limit (10/s) | (not applicable) | MAC limit (1) |
| Rogue DHCP server offer | Trust filter (drop on untrusted) | (not applicable) | (not applicable) |
| Gratuitous ARP poison | (not applicable) | Binding mismatch drop | (not applicable) |
| Forged MAC from same port | (rate-limit still applies) | (not applicable) | MAC limit (1) triggers shutdown |
| Sustained starvation | Rate-limit extends exhaustion from 25 ms to 24 s | (not applicable) | Shutdown cuts attacker off entirely |

A defender who only enables snooping still has a residual ARP poisoning risk if the attacker uses an ARP flood to race the snooping binding table. A defender who only enables DAI still has a residual DHCP starvation risk. A defender who only enables port security still has an ARP risk if the attacker compromises a legitimate MAC. All three together cover the full chain.

## Build It

`code/main.py` is a stdlib-only Python simulation that runs all seven phases of the capstone: network setup, normal DHCP, starvation, ARP poisoning, detection, mitigation, and post-mitigation verification.

1. **Network model** - `DhcpServer` initializes a 245-address pool keyed by IP, plus a binding table (`ip -> mac`) that doubles as the DAI reference. `SwitchPort` tracks trusted status, learned MACs, MAC limit, DHCP rate limit, and Discover counter.

2. **Normal DORA** - `simulate_normal_dora()` walks the four-message handshake for a legitimate client: Discover broadcast, Offer unicast, Request broadcast, Ack unicast. Each step appends a `DhcpMessage` to the message log and a lease to the pool.

3. **Starvation** - `simulate_starvation()` iterates 300 forged Discovers (3 ms apart), each with a freshly generated random MAC. The server allocates until the pool hits the 90 percent threshold or the loop exhausts the pool. The function returns the count of forged leases consumed.

4. **ARP poisoning** - `simulate_arp_poison()` iterates the list of victim MACs (the legitimate clients from phase 1) and writes a poisoned `ArpEntry` mapping 10.0.0.1 -> AA:AA:AA:AA:AA:AA into each victim's ARP cache.

5. **Detection** - `detect_starvation()` checks pool utilization (alert above 90 percent) and MAC entropy (count of unique OUIs above threshold). `detect_arp_poison()` counts gratuitous ARP entries and flags any conflict with the binding table.

6. **Snooping mitigation** - `apply_dhcp_snooping()` marks only the server-facing port as trusted, blocks Offers/Acks from untrusted ports, and rate-limits Discovers to 10 per second per port.

7. **DAI mitigation** - `apply_dai()` compares each ARP packet against the binding table and drops any packet whose IP-MAC pair does not match a learned binding.

8. **Port security mitigation** - `apply_port_security()` enforces the one-MAC-per-port rule, marks the attacker's port as violated, and applies the configured violation action (shutdown).

Run `python3 code/main.py` and read the printed report. The pool starts at 245 available, drops to 235 after the ten legitimate clients, falls to 0 after starvation, the eleventh client fails to lease, ten ARP caches flip to the attacker MAC, three detection alerts fire (high pool utilization, random MAC pattern, gratuitous ARP conflict), and the three mitigations report their effectiveness.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Run the simulation | `python3 code/main.py` | Prints seven phase banners, attack timeline, detection alerts, mitigation results |
| Verify pool exhaustion | Pool status line shows `245/245 (100.0%)` | All 245 addresses allocated to forged or legitimate MACs |
| Verify attack chain | Victim ARP cache line shows `10.0.0.1 -> AA:AA:AA:AA:AA:AA [POISONED]` | Every victim's gateway entry points at the attacker |
| Verify detection | Detection section prints at least three CRITICAL alerts | Pool utilization > 90 percent, random MAC pattern, gratuitous ARP conflict |
| Verify snooping | Mitigation section shows attacker port blocked and rate-limited | Untrusted port cannot send Offers/Acks, Discovers capped at 10/s |
| Verify DAI | Mitigation section shows ARP replies dropped | Gratuitous ARP packets fail binding check, are dropped, count logged |
| Verify port security | Mitigation section shows attacker port shut down | MAC violation triggers violation action, port enters err-disabled |
| Verify recovery | Post-mitigation section shows five legitimate clients getting leases | Normal clients unaffected by the mitigation |

## Ship It

Outputs land in `outputs/`:

- `attack-timeline.txt` - Chronological log of every `AttackEvent` with timestamp, phase, event type, severity, and description.
- `dhcp-pool-status.txt` - Pool utilization at each phase boundary: boot, after legitimate clients, after starvation, after mitigation, after recovery.
- `arp-cache-state.txt` - ARP cache entry for each victim before and after poisoning, showing the gateway MAC transition.
- `detection-alerts.txt` - All detection events with the evidence that triggered them and the recommended response.
- `mitigation-config.txt` - The simulated switch configuration with trusted ports, rate limits, binding table, MAC limits, and violation actions, plus the count of packets each control dropped or accepted.
- `attack-chain-runbook.md` - A one-page defensive runbook for production response: how to identify each phase, what evidence to capture, what configuration to apply, and how to verify recovery without disrupting legitimate users.

## Exercises

1. **Rogue DHCP server** - Add a rogue DHCP server at attacker MAC AA:AA:AA:AA:AA:AA that hands out addresses with the attacker as the gateway. Combine with starvation to push legitimate clients onto the rogue server. What mitigation breaks the rogue DHCP, and at what layer?
2. **802.1X port-based authentication** - Add a model of 802.1X that requires EAP authentication before any L2 traffic is forwarded. Show that the attacker cannot even send a forged Discover without first authenticating. Compare the residual attack surface to DHCP snooping alone.
3. **VLAN hopping via double tagging** - Model an attacker that sends 802.1Q double-tagged frames to reach a VLAN they are not a member of. How does this change the blast radius of ARP poisoning, and what switch feature prevents it?
4. **ARP rate limiting** - Add per-port ARP rate limiting (e.g., 15 ARP packets per second per port) and show how it caps the speed of an ARP flood. Pick the rate threshold: too low breaks legitimate re-ARP storms; too high lets an attacker saturate the binding table.
5. **NetFlow anomaly detection** - Design a detection rule on `udp.src_port == 68 and udp.dst_port == 67` that flags hosts sending more than 20 Discovers per minute. What is the right window length to catch starvation before pool exhaustion?
6. **IPv6 NDP poisoning** - Extend the simulation to IPv6 Neighbor Discovery Protocol poisoning. Which IPv6 control (RA-Guard, DHCPv6 Snooping, IPv6 Snooping, or SeND) defeats each variant?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DHCP DORA | The four-message dance | Discover (client broadcast) -> Offer (server) -> Request (client broadcast) -> Ack (server); NAK replaces Offer/Ack when pool is empty |
| DHCP starvation | Pool exhaustion attack | Flooding Discovers with forged source MACs (sequential, random, or OUI-mimicry) to consume every lease in the pool |
| Gratuitous ARP | An unsolicited ARP reply | An ARP reply broadcast without a preceding request; receivers update cache, attackers use it to overwrite gateway mappings |
| ARP poisoning | Cache overwrite attack | Forcing victim ARP caches to map a legitimate IP (usually the gateway) to an attacker-controlled MAC |
| DHCP snooping | A switch security feature | Filter that allows DHCP server messages only on trusted ports, rate-limits Discovers on untrusted ports, builds a binding table |
| Dynamic ARP Inspection | ARP validator | Cross-checks every ARP packet against the DHCP snooping binding table and drops packets whose IP-MAC pair does not match |
| Port security | MAC limiter | Caps the number of source MACs per port (default one) and triggers protect/restrict/shutdown on violation |
| Binding table | IP-MAC-Port ledger | The DHCP snooping data structure used by DAI to validate ARP packets |
| Man-in-the-middle | The attacker relays traffic | Once ARP is poisoned, all victim-to-gateway frames route through the attacker; attacker can forward, drop, or modify |
| OUI | The first 24 bits of a MAC | Identifies the hardware vendor; tools that set the locally administered bit or randomize OUIs are detectable via entropy analysis |
| Reachable-time | ARP cache aging | RFC 826 entry validity window (typically 30 s on Linux, 20 s on Windows); transitions REACHABLE -> STALE -> PROBE -> FAILED |
| Trusted port | A snooping exemption | A switch port allowed to emit DHCP server messages; typically the uplink to the legitimate DHCP server only |

## Further Reading

- RFC 2131 - Dynamic Host Configuration Protocol (the DORA specification, lease state machine, message format)
- RFC 2132 - DHCP Options and BOOTP Vendor Extensions (option 53 message type, option 61 client identifier)
- RFC 826 - An Ethernet Address Resolution Protocol (the ARP specification, including gratuitous ARP semantics)
- RFC 5227 - IPv4 Address Conflict Detection (the ARP probe / announcement dance for address uniqueness)
- Cisco - Configuring DHCP Snooping, Dynamic ARP Inspection, and IP Source Guard (the canonical deployment guide)
- IEEE 802.1X - Port-Based Network Access Control (EAP authentication before L2 forwarding)
- IEEE 802.1Q - Virtual Bridged Local Area Networks (VLAN tagging, double-tagging attack surface)
- Tripwire - "Yersinia" tool documentation (the open-source L2 attack toolkit used to reproduce DHCP starvation and ARP poisoning)
- US-CERT - "Vulnerability Note VU#411675: DHCP client implementations mishandle forged DHCP packets" (advisory on rogue DHCP server risks)
- "Hacking Exposed 7: Network Security Secrets and Solutions" by Stuart McClure, Joel Scambray, and George Kurtz (Chapter 4 covers the L2 attack chain end-to-end)