# Firewalls to Virtual Private Networks

> Firewalls are electronic drawbridges: every packet entering or leaving a network passes through a single choke point where rules decide pass or drop. A packet-filter firewall inspects IP headers (source, destination, port, protocol); a stateful firewall tracks connections via TCP/IP header fields so it can allow return traffic only if an internal host initiated the connection; an application-level gateway inspects packet contents beyond TCP to distinguish HTTP browsing from peer-to-peer file sharing. The DMZ (DeMilitarized Zone) sits outside the security perimeter, hosting public-facing servers (web, email) so the firewall can block inbound port 80 to the internal LAN while still serving the Internet. DoS (Denial of Service) and DDoS (Distributed Denial of Service) attacks — like TCP SYN floods that exhaust connection table slots — bypass firewalls because the packets are legitimate in shape. VPNs (Virtual Private Networks) overlay encrypted tunnels on the public Internet using IPsec ESP in tunnel mode, terminating at firewalls or security gateways; every pair of offices negotiates SA parameters (services, modes, algorithms, keys) and the VPN is transparent to all user software. MPLS-based VPNs are an ISP-managed alternative that keeps traffic separate by label-switched paths rather than encryption.

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Lesson 01 (IPsec); Phase 9 IP lessons
**Time:** ~75 minutes

## Learning Objectives

- Explain the three generations of firewall sophistication: stateless packet filter, stateful firewall, and application-level gateway — and what each can and cannot inspect.
- Describe the DMZ architecture and why public servers live outside the security perimeter.
- Identify DoS and DDoS attack patterns (TCP SYN flood) and why firewalls cannot prevent them by filtering alone.
- Define a VPN as an overlay of encrypted tunnels and explain why IPsec ESP tunnel mode is the natural combination with firewalls.
- Contrast IPsec-based VPNs with MPLS-based VPNs: what is encrypted, what is separated, and who manages each.
- Explain why firewalls violate layering and why that makes them fragile (port-based assumptions, encryption hiding content, no feedback to endpoints).

## The Problem

A corporate security manager faces two directions: confidential data leaking out (trade secrets, product plans) and digital pests leaking in (viruses, worms imported by employees). The network needs a single choke point — a firewall — that inspects every packet. But the firewall cannot simply block all external traffic: employees need web access, customers need the company website, and remote workers need to reach internal systems. The engineering challenge is writing rules that allow useful functionality while blocking unwanted traffic, then extending the protected network across the public Internet with VPNs.

## The Concept

### The firewall as packet filter

A firewall inspects every incoming and outgoing packet. Packets meeting criteria described in administrator rules are forwarded; those that fail are dropped. The filtering criterion is typically given as rules or tables listing acceptable and blocked sources and destinations, plus default rules. In a TCP/IP setting, a source or destination consists of an IP address and a port. TCP port 25 is mail; TCP port 80 is HTTP. Some ports can simply be blocked (e.g., port 79 for Finger). Others cannot — blocking port 80 would cut off web browsing.

### The DMZ

The DMZ (DeMilitarized Zone) is the part of the company network that lies outside the security perimeter. By placing a web server in the DMZ, Internet computers can contact it to browse the company site. The firewall is configured to block inbound TCP traffic to port 80 toward the internal network, but permit management connections from internal machines to the DMZ server. This is the standard architecture for public-facing services.

### Three generations of firewall sophistication

| Generation | What it inspects | Example rule | Limitation |
|-----------|------------------|-------------|------------|
| Stateless packet filter | Each packet independently: IP src/dst, port, protocol | "Allow TCP dst port 80 from any to DMZ" | Cannot express "allow return traffic only if internal host initiated" |
| Stateful firewall | Maps packets to connections via TCP/IP header fields | "Allow inbound from web server only if internal host first established connection" | Still relies on port numbering; encryption hides content |
| Application-level gateway | Looks inside packets beyond TCP header at application data | "Allow HTTP browsing, block peer-to-peer file sharing over HTTP" | Fragile; encryption defeats it; must parse every protocol |

Stateful firewalls track connection state so they can allow an external web server to send packets to an internal host, but only if the internal host first established the connection. This is impossible with stateless designs that must either pass or drop all packets from a given source.

### Why firewalls are fragile

Firewalls violate standard layering. They are network-layer devices but peek at transport and application layers. This makes them fragile: they rely on standard port numbering conventions that not all applications follow; peer-to-peer applications select ports dynamically to avoid being spotted; IPsec encryption hides higher-layer information from the firewall entirely. A firewall cannot tell endpoints why a connection was dropped — it pretends to be a broken wire. Networking purists consider firewalls a blemish; but the Internet is dangerous, so firewalls persist.

### DoS and DDoS attacks

Even a perfectly configured firewall cannot stop Denial of Service attacks. To cripple a website, an intruder sends a TCP SYN packet to establish a connection. The site allocates a table slot and sends SYN+ACK. If the intruder never responds, the table slot is tied up until timeout. Thousands of connection requests fill all table slots and no legitimate connections get through. The request packets have false source addresses so the intruder cannot be traced. When the intruder has already broken into hundreds of machines and commands them all to attack simultaneously, it is a DDoS (Distributed Denial of Service) attack — more firepower, lower detection chance.

### Virtual Private Networks

Many companies have offices scattered over cities and countries. Leasing dedicated T1 lines costs thousands of dollars per month. VPNs are overlay networks on top of public networks but with most properties of private networks — "virtual" because they are merely an illusion, like virtual circuits and virtual memory.

A common VPN design equips each office with a firewall and creates IPsec tunnels through the Internet between all pairs of offices. When the system starts, each pair of firewalls negotiates SA parameters: services, modes, algorithms, and keys. IPsec ESP tunnel mode aggregates all traffic between any pair of offices onto a single authenticated, encrypted SA, providing integrity control, secrecy, and immunity to traffic analysis. Many firewalls have VPN capabilities built in.

### IPsec VPN vs MPLS VPN

| Aspect | IPsec VPN | MPLS VPN |
|--------|-----------|---------|
| Mechanism | Encryption (ESP tunnel mode) | Label-switched paths separate traffic |
| Managed by | Company firewalls / security gateways | ISP |
| Confidentiality | Cryptographic | Logical separation (no encryption by default) |
| QoS guarantees | None (rides best-effort Internet) | Bandwidth guarantees possible |
| Transparency | Fully transparent to user software | Fully transparent to user software |
| Setup cost | Negotiate SAs between firewalls | ISP configures MPLS paths |

A key advantage of both approaches: the VPN is completely transparent to all user software. Only the system administrator configuring the security gateways or the ISP administrator configuring MPLS paths is aware of it. To everyone else it is like having a leased-line private network.

### Failure modes

- **Port-spoofing**: peer-to-peer apps use dynamic ports to evade port-based rules. Stateful firewalls mitigate but application-level gateways are stronger.
- **Encryption blind spot**: IPsec or TLS hides packet content from the firewall. Application-level inspection becomes impossible without TLS interception.
- **Insider attacks**: three-quarters of attacks come from outside, but inside attacks (disgruntled employees) are typically the most damaging. Firewalls do not help here.
- **Single perimeter**: if the firewall is breached, all bets are off. Layered defense (perimeter firewall plus host firewalls) mitigates.
- **DoS/DDoS**: legitimate-shaped packets in great numbers collapse the target. Firewalls cannot filter by shape alone.

`code/main.py` is a firewall rule matcher that evaluates packets against stateless and stateful rule sets; `assets/firewalls-to-virtual-private-networks.svg` diagrams the DMZ, firewall, and VPN tunnel topology.

## Build It

1. Run `python3 code/main.py` to see packets matched against stateless and stateful rule sets.
2. Examine the DMZ rule example: inbound port 80 goes to the DMZ web server, not the internal LAN.
3. Trigger the stateful path: an inbound SYN+ACK is allowed only if an internal host first sent a SYN.
4. Run the DoS SYN-flood simulation and observe table-slot exhaustion.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify firewall rules | Rule table listing: src, dst, port, action | Every rule has a documented purpose; default-deny is explicit |
| Confirm stateful tracking | Connection state table with SYN, SYN+ACK, ESTABLISHED entries | Return traffic allowed only for connections initiated internally |
| Detect DMZ misconfiguration | Packet capture showing inbound port 80 traffic to internal LAN | Inbound port 80 routes only to DMZ; internal LAN is blocked |
| Diagnose VPN tunnel failure | IPsec SA state on both firewalls; ESP packet counters | SAs match on both ends; byte counters increment; no IKE errors |

## Ship It

Create one artifact under `outputs/`:

- A firewall rule-set document (table format) for a two-zone (DMZ + internal) network.
- A VPN SA parameter sheet for a three-office IPsec tunnel mesh.
- A one-page DoS/DDoS incident runbook.

Start with [`outputs/prompt-firewalls-to-virtual-private-networks.md`](../outputs/prompt-firewalls-to-virtual-private-networks.md).

## Exercises

1. Write a stateless rule set that allows outbound HTTP (port 80) and HTTPS (port 443) from the internal LAN, blocks inbound port 79 (Finger), and directs inbound port 80 to the DMZ web server at 10.0.0.100.
2. A stateful firewall allows return traffic only if an internal host initiated the connection. Describe the connection-state table entries for: internal host SYN to external port 443, external SYN+ACK, external data, and then a separate inbound SYN from the external host to internal port 22.
3. A SYN flood sends 10,000 SYN packets per second. If the connection table has 4,096 slots and each slot times out after 60 seconds, how many legitimate connections can survive? What mitigation would you add?
4. Company A uses IPsec ESP tunnel mode between firewalls. Company B uses MPLS VPNs managed by their ISP. Which provides cryptographic confidentiality? Which can guarantee bandwidth? Which is transparent to applications?
5. A peer-to-peer application uses port 443 to evade port-based filtering. Which firewall generation can detect this? What does it need to inspect?
6. Why does a firewall "pretend to be a broken wire" instead of telling the endpoint why a connection was dropped? What protocol-layer assumption does this respect?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Firewall | "the security box" | A packet filter at a network choke point; inspects IP/transport/app layers; violates layering |
| DMZ | "the public zone" | Network outside the security perimeter; hosts public-facing servers so the internal LAN stays protected |
| Stateful firewall | "connection-aware" | Tracks TCP connection state so return traffic is allowed only if an internal host initiated the connection |
| Application-level gateway | "deep inspection" | Inspects packet payload beyond TCP to distinguish application behavior; defeated by encryption |
| DoS | "flood attack" | Denial of Service: legitimate-shaped packets in great numbers exhaust table slots or CPU |
| DDoS | "botnet flood" | Distributed DoS: hundreds of compromised machines attack the same target simultaneously |
| VPN | "encrypted tunnel" | Virtual Private Network: overlay of encrypted IPsec tunnels on the public Internet; transparent to user software |
| MPLS VPN | "ISP VPN" | Label-switched-path separation managed by the ISP; no encryption, but logical traffic separation and possible QoS |

## Further Reading

- RFC 4301 — Security Architecture for the Internet Protocol (IPsec framework for VPNs)
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 sections 8.6.2 and 8.6.3
- Lewis, M. — *Comparing, Designing, and Deploying VPNs* (Cisco Press)
- Cheswick, Bellovin, and Rubin — *Firewalls and Internet Security* (Addison-Wesley)
- Verizon Data Breach Investigations Report — insider attack statistics
