# IP Multicast and IGMP for Live Media

> Unicast sends one copy per viewer; broadcast floods everyone. Multicast sends one copy to a group address and the network replicates it only where interested receivers have joined. IGMP is how receivers tell the local router they want in.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Phase 13 lessons 01-17 (RTP/RTCP, VoIP Packetization)
**Time:** ~75 minutes

## Learning Objectives

- Explain why multicast is more efficient than unicast for live one-to-many media
- Describe the IP multicast address space and the Ethernet MAC mapping
- Trace the IGMP join, query, and leave message lifecycle
- Distinguish IGMPv1, v2, and v3 by their group management features
- Model a multicast forwarding tree and the prune/graft behavior
- Identify the failure modes: multicast not routed, IGMP snooping misconfiguration, scoped TTL
- Implement an IGMP membership simulation showing group state on a router

## The Problem

A live event stream has one source and thousands or millions of viewers. With unicast, the sender transmits one copy per viewer; 100 000 viewers of a 2 Mbps stream means 200 Gbps of egress from the source. With broadcast, every host on the network gets a copy whether they want it or not, which is both wasteful and often blocked by routers. Multicast is the middle ground: the source sends one copy to a group address, and the network replicates it only at the forks where downstream branches have at least one interested receiver. The question is how receivers signal interest, and how routers decide where to forward. That signaling protocol is IGMP, and its interaction with multicast routing (PIM, DVMRP) determines whether a live stream reaches its audience efficiently or not at all.

## The Concept

### The multicast address space

IPv4 class D, 224.0.0.0/4 (224.0.0.0 through 239.255.255.255), is reserved for multicast. Within it:

```text
224.0.0.0/24     link-local (TTL=1, not forwarded by routers)
224.0.1.0-224.0.1.255  internetwork control
232.0.0.0/8      SSM (Source-Specific Multicast)
233.0.0.0/8       GLOP (AS-based assignments)
239.0.0.0/8       administratively scoped (private, like RFC1918)
```

IPv6 multicast is ff00::/8, with scope bits for link-local, organization, global.

### Ethernet MAC mapping

IP multicast packets are delivered over Ethernet using a derived MAC. For IPv4 the mapping is 01:00:5e:00:00:00/25, meaning the low 23 bits of the IP group address are copied into the low 23 bits of the MAC. Because only 23 bits are used and the IP group is 28 bits of effective range, 32 IP groups share one MAC (a 32-to-1 ambiguity). The NIC accepts the matching MAC and the IP stack filters by full IP address.

```text
IP group  224.1.2.3  ->  01:00:5e:01:02:03
IP group  225.1.2.3  ->  01:00:5e:01:02:03   (same MAC! ambiguity)
```

### IGMP: the group management protocol

IGMP runs between a host and its first-hop multicast router. It has three operational versions:

- **IGMPv1**: host sends a Membership Report to join. Router periodically sends General Queries; if no host responds within the query interval, the router times out the group. No explicit leave.
- **IGMPv2**: adds a Leave Group message so the router can prune immediately instead of waiting for the query timeout. Adds group-specific queries. Adds a querier election mechanism when multiple routers share a LAN.
- **IGMPv3**: adds Source-Specific Multicast (SSM). A report can include or exclude specific source addresses, so a host joins (group, source) pairs, not just a group. This enables SSM and suppresses unwanted sources.

### The join-leave-query lifecycle

```text
Host wants group G:
  1. Host sends Membership Report (join) to 224.0.0.22 (v3) or G (v1/v2)
  2. Local router notes: downstream interface has members for G
  3. Multicast routing (PIM) builds a tree from the source to this router
  4. Packets for G now arrive on the LAN; NIC filters by MAC

Router keeps the group alive:
  5. Router sends General Query every Query Interval (default 125 s)
  6. Hosts respond with Reports; if any report arrives, group stays

Host leaves:
  7. Host sends Leave Group (v2/v3) to 224.0.0.2
  8. Router sends Group-Specific Query to G to check for other members
  9. If no response, router prunes G from that interface
```

### IGMP snooping

A layer-2 switch does not route IP, so it cannot rely on the router to know which ports have group members. IGMP snooping has the switch inspect IGMP reports and leaves passing through it, learning which ports joined which groups, and forwarding multicast frames only to those ports. Without snooping, a switch floods multicast to all ports, which defeats much of the efficiency.

### Multicast routing (briefly)

IGMP handles the last hop (host to first router). Multicast routing protocols build the tree across routers:

- **DVMRP**: distance-vector, flood-and-prune. Each router initially gets every stream and prunes back.
- **PIM-DM**: dense mode, also flood-and-prune, simpler.
- **PIM-SM**: sparse mode, uses Rendezvous Points and shared trees, switching to shortest-path trees for high-rate sources. The common choice for live media in modern networks.

### Failure modes

- **Multicast not enabled**: many routers and firewalls block multicast by default. Symptom: viewers see nothing; unicast works.
- **No IGMP snooping**: switch floods every port; bandwidth waste, NIC load on disinterested hosts.
- **TTL scoping**: multicast packets have a TTL that routers decrement; a stream sent with TTL=1 never leaves the local link. Administrative scoping uses TTL thresholds or 239.0.0.0/8 to keep traffic inside an AS.
- **Querier missing**: if no router is elected querier, hosts keep their joins but the router may time out the group.
- **Source-Specific issues**: SSM requires IGMPv3 and a routing protocol that supports it; a v2-only receiver cannot join an SSM channel.

## Build It

The script below models a multicast router's IGMP state table. It:

1. Tracks which interfaces have members for which groups (and sources, for v3).
2. Simulates host join, query/response, and leave with timeouts.
3. Shows how IGMP snooping state maps groups to switch ports.
4. Demonstrates the 32-to-1 IP-to-MAC ambiguity.
5. Compares unicast, broadcast, and multicast bandwidth for a live stream.

```python
# Core idea (see code/main.py)
router = MulticastRouter()
router.join(iface="eth0", group="224.1.2.3")
router.query()
router.leave(iface="eth0", group="224.1.2.3")
```

## Use It

```bash
python3 code/main.py
```

Expected output: the router state table after a series of joins and leaves, a query cycle showing timeouts, a snooping table mapping ports to groups, the MAC-ambiguity demonstration, and a bandwidth comparison table for unicast versus multicast at increasing audience sizes.

## Ship It

- Use the state-table simulation to explain why a missing querier causes groups to time out.
- Extend the model to include a PIM prune/graft decision and document when the tree shrinks.
- Produce a one-page runbook: "Multicast viewers see nothing - check these five things in order."
- Export the bandwidth comparison as CSV for a design review artifact.

## Exercises

1. Add a second router on the same LAN and implement querier election (lowest IP wins). Show what happens when the elected querier fails.
2. Implement IGMPv3 source-specific join and show how a host can receive only one source while ignoring others in the same group.
3. Model TTL scoping: send with TTL=1, TTL=32, and TTL=127 and show which links the stream crosses.
4. Add IGMP snooping to the switch model and measure the bandwidth saved on disinterested ports.
5. Simulate 10 000 viewers on a 5 Mbps stream and compute source egress for unicast versus multicast.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Multicast | "Group send" | One-to-many delivery where the network replicates packets only at branches with interested receivers, using a class D group address |
| IGMP | "Join protocol" | Internet Group Management Protocol: how a host tells its local router it wants traffic for a group |
| Membership Report | "A join" | The IGMP message a host sends to declare interest in a group (or group plus sources in v3) |
| Leave Group | "A quit" | The IGMPv2/v3 message a host sends to drop interest, letting the router prune immediately |
| Querier | "The asker" | The router elected to send periodic General Queries on a LAN to refresh group state |
| IGMP snooping | "Switch awareness" | Layer-2 switch inspection of IGMP to learn which ports have members, avoiding flooding |
| SSM | "Source-specific" | Source-Specific Multicast: a host joins a (source, group) pair, requiring IGMPv3 |
| Rendezvous Point | "RP" | The shared tree root in PIM-SM that receivers join before switching to a shortest-path tree |
| MAC mapping | "Group MAC" | The 01:00:5e:xx:xx:xx Ethernet address derived from the low 23 bits of the IP group |
| TTL scoping | "Hop limit" | Using the multicast TTL to bound how far a stream propagates; routers enforce per-interface thresholds |

## Further Reading

- [RFC 3376 - IGMPv3](https://www.rfc-editor.org/rfc/rfc3376) - the current group management spec
- [RFC 4607 - SSM](https://www.rfc-editor.org/rfc/rfc4607) - source-specific multicast architecture
- [RFC 7761 - PIM-SM](https://www.rfc-editor.org/rfc/rfc7761) - sparse mode multicast routing
- [RFC 1112 - IP Multicast](https://www.rfc-editor.org/rfc/rfc1112) - the original host extensions for multicasting