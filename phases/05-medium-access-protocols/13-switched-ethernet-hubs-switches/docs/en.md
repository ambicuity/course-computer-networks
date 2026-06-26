# Switched Ethernet: hubs, switches, collision domains, and full-duplex links

> Trace the operational difference between a hub that repeats bits and a switch that learns where stations live. A hub creates one shared collision domain: every attached station hears every frame, and half-duplex CSMA/CD decides who gets the medium. A switch creates one collision domain per port, learns source MAC addresses into a forwarding table, floods unknown destinations, and forwards known unicasts only out the selected port. When each switch port runs full duplex, collisions disappear entirely. This lesson shows why switching changed Ethernet from a shared bus into a fabric, and how to debug the remaining failure modes: unknown-unicast flooding, MAC table churn, loops, duplex mismatches, and broadcast storms.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Ethernet frame format, MAC addresses, CSMA/CD, collision domains
**Time:** ~75 minutes

## Learning Objectives

- Distinguish a hub, bridge, and switch by the layer at which each device operates and the forwarding decision it can make.
- Explain how a switch learns a MAC address table from source addresses and ages entries out over time.
- Predict whether a frame is forwarded, filtered, or flooded for known unicast, unknown unicast, broadcast, and multicast destinations.
- Explain why full-duplex switch ports remove CSMA/CD and why duplex mismatches still cause collision-like symptoms.
- Diagnose switch-table failures: MAC flapping, flooding, loops, and broadcast storms.

## The Problem

An office replaces an old hub with an unmanaged Ethernet switch. File transfers get faster immediately, but a packet capture on one workstation no longer sees every other workstation's unicast traffic. Later, a user plugs both ends of a spare patch cable into wall jacks, and the whole floor melts down under broadcast traffic. The team has two questions: why did switching make normal traffic private and fast, and why did one cable loop break everything?

Both answers come from the switch forwarding database. A switch is not a magic faster hub. It is a learning bridge with many ports. It watches source MAC addresses, records which port last sent from each address, forwards known destinations to one port, and floods traffic when it lacks enough information. That learning behavior is powerful, but it assumes the Layer 2 topology is loop-free unless a loop-prevention protocol such as Spanning Tree is active.

## The Concept

### Hubs repeat bits

A hub is a physical-layer repeater. If a bit arrives on one port, the hub regenerates it out every other port. It has no frame parser, no MAC table, and no notion of destination. Every attached station shares the same half-duplex medium:

```
Host A ----\
Host B ----- Hub ----- Host D
Host C ----/
```

Only one station can transmit successfully at a time. Collisions are normal, CSMA/CD is active, and a capture on any host can observe other hosts' unicast frames because the hub repeats them everywhere.

### Switches learn from source addresses

A switch reads Ethernet frames. On ingress, it updates its forwarding table using the source MAC address:

```
table[source_mac] = ingress_port, last_seen_time
```

Then it makes a destination decision:

| Destination type | Table state | Switch action |
|---|---|---|
| Known unicast | Destination MAC maps to another port | Forward only to that port |
| Same-port unicast | Destination MAC maps to ingress port | Filter; do not send it back |
| Unknown unicast | Destination MAC not in table | Flood out all ports except ingress |
| Broadcast | ff:ff:ff:ff:ff:ff | Flood out all ports except ingress |
| Multicast | Group address | Flood unless multicast snooping or filtering is configured |

This is why switching improves throughput. Host A and Host B can talk while Host C and Host D talk on different ports. The switch fabric, not a shared coax, carries the parallel conversations.

### Collision domains and broadcast domains

A switch breaks collision domains but not broadcast domains. Each port is its own collision domain; in full duplex, even that domain has no collisions. But broadcasts still flood across the VLAN. ARP, IPv4 DHCP discovery, and many discovery protocols still reach every port in the same VLAN.

```
Hub:     one collision domain, one broadcast domain
Switch:  one collision domain per half-duplex port, one broadcast domain per VLAN
Router:  separates broadcast domains
```

That distinction explains a common misconception: replacing hubs with switches reduces collisions and unicast visibility, but it does not contain broadcast storms unless VLANs, routers, or storm-control policies are used.

### Full duplex removes CSMA/CD

On a full-duplex switch link, the host and switch have separate transmit and receive paths. There is no shared medium and therefore no collision detection. Modern Ethernet NICs disable CSMA/CD when full duplex is negotiated.

A duplex mismatch recreates pain. If one side believes full duplex and the other half duplex, the half-duplex side detects collisions and backs off, while the full-duplex side keeps transmitting and reports frame check sequence errors or drops. Symptoms include terrible throughput, late collisions on one side, CRC/FCS errors on the other, and asymmetric performance.

### MAC table churn and loops

Switch learning assumes a MAC address is reachable through one stable port. If the same source MAC appears on two ports rapidly, the switch logs **MAC flapping** and repeatedly rewrites its table. Causes include physical loops, misconfigured bonding, virtualization bridges, or duplicate MAC addresses.

Layer 2 loops are especially dangerous because Ethernet frames have no TTL. A broadcast frame can circulate forever, multiplying as switches flood it. Spanning Tree Protocol exists to block redundant links until they are needed, creating a loop-free active topology.

## Build It

1. Open `code/main.py` and find the switch model or forwarding-table functions.
2. Create a four-host topology with a hub behavior: every unicast frame is visible on every port. Record the collision-domain and visibility result.
3. Run the same traffic through switch behavior. Confirm the first frame to an unknown destination floods and the reply teaches the reverse path.
4. Send a second unicast between the same hosts. Confirm it forwards only to the learned port.
5. Lower the MAC aging timer or manually expire an entry, then send again. Confirm unknown-unicast flooding returns.
6. Optional extension: create a loop between two switch ports and show why repeated broadcast flooding requires STP or a loop guard.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Show hub behavior | Frame visibility log | Every port except ingress receives every frame |
| Show switch learning | MAC table after each frame | Source MACs map to ingress ports and age over time |
| Explain unknown flood | First packet to an unseen MAC | Flood occurs once, then learned unicast narrows forwarding |
| Diagnose mismatch | Error-counter explanation | Collisions on half-duplex side, FCS/CRC or drops on full-duplex side |
| Explain loop risk | Broadcast forwarding trace | Frame has no TTL; loop repeats until STP/storm control stops it |

## Ship It

Produce one artifact under `outputs/`:

- A switch learning table trace with at least six frames: source, destination, ingress port, table before, action, table after.
- A one-page troubleshooting note for "users report slow Ethernet after switch replacement" that separates duplex mismatch, table flooding, broadcast storm, and physical errors.
- A diagram showing collision domains and broadcast domains before and after replacing a hub with a switch.

Start from `outputs/prompt-switched-ethernet-hubs-switches.md` if present, or create `outputs/switched-ethernet-forwarding-trace.md`.

## Exercises

1. A switch table contains `AA:AA -> port 1` and `BB:BB -> port 2`. A frame enters port 1 from `AA:AA` to `BB:BB`. What does the switch do, and does the table change?
2. The same switch receives a frame from `CC:CC` to `DD:DD` on port 3. List the forwarding action and the table update.
3. Explain why a packet capture on a switched host usually misses other hosts' unicast traffic, but still sees ARP broadcasts.
4. A switch log reports the same MAC address moving between ports 5 and 9 every second. Give three possible causes and the first evidence you would collect.
5. Compare a hub, switch, and router for collision domains and broadcast domains in a 24-host network.
6. A link has late collisions on one side and FCS errors on the other. Explain why this points to duplex mismatch rather than normal congestion.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Hub | "Dumb switch" | Physical-layer repeater that sends every bit out every other port |
| Switch | "Smart hub" | Multiport learning bridge that forwards frames based on destination MAC address |
| Forwarding database | "MAC table" | Mapping from learned source MAC addresses to switch ports and aging timers |
| Flooding | "Send everywhere" | Forwarding out all ports except ingress when the destination is broadcast, multicast, or unknown |
| Filtering | "Drop locally" | Suppressing a frame because the destination is learned on the same ingress port |
| Collision domain | "Who can collide" | Set of stations sharing a half-duplex medium where simultaneous transmissions interfere |
| Broadcast domain | "Who hears ARP" | Set of interfaces reached by Layer 2 broadcasts, usually one VLAN |
| MAC flapping | "MAC moving ports" | Same source address learned on different ports rapidly, often indicating a loop or bonding issue |
| Duplex mismatch | "One side half, one full" | Negotiation/configuration error that causes collisions, FCS errors, and poor throughput |

## Further Reading

- IEEE 802.1D — MAC bridges, learning, forwarding, filtering, and spanning tree.
- IEEE 802.3 — Ethernet MAC behavior, full-duplex operation, and auto-negotiation interactions.
- A. Tanenbaum & D. Wetherall, *Computer Networks*, 5th ed., Chapter 4 — bridges, switches, and LAN interconnection.
- Radia Perlman, *Interconnections* — bridges, spanning tree, and the design logic behind loop-free Layer 2 topologies.
