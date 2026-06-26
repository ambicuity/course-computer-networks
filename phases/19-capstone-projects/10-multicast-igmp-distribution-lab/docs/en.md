# Multicast IGMP Distribution Lab

> Simulate a PIM-SM multicast distribution tree with IGMPv3 host joins, Rendezvous Point election, shared-tree to source-tree switchover, and pruning. Prove that only interested receivers receive traffic.

**Type:** Capstone
**Languages:** Python, Linux networking, Wireshark
**Prerequisites:** Phase 9 multicast lessons; Phase 13 streaming and real-time media lessons
**Time:** ~140 minutes

## Learning Objectives

- Model IGMPv3 host membership reports (join, leave, source-specific join) and router processing
- Build a PIM-SM shared tree (RPT) rooted at the Rendezvous Point (RP)
- Simulate the source-tree (SPT) switchover when a receiver's data rate exceeds the threshold
- Implement PIM prune and graft mechanics for dynamic group membership changes
- Verify that multicast traffic flows only along branches with active receivers
- Calculate bandwidth savings versus unicast replication at each hop

## The Problem

Multicast is the efficient way to deliver the same content to many receivers. Instead of the source sending N copies (unicast), or the network replicating at the source (broadcast), multicast builds a distribution tree that duplicates packets only at fork points. The challenge is managing group membership dynamically: receivers join and leave at any time, sources start and stop sending, and the network must continuously rebuild the distribution tree.

This capstone models a PIM-SM (Protocol Independent Multicast - Sparse Mode) network with IGMPv3 host management. The network has one RP, three sources, and eight potential receivers spread across four LANs connected by five routers. You must simulate IGMP joins and leaves, PIM register messages from sources to the RP, shared-tree construction, SPT switchover, pruning, and bandwidth accounting.

The key insight is that multicast saves bandwidth at every branch point where the tree forks. A unicast delivery to 8 receivers across 4 LANs would send 8 copies over the backbone. Multicast sends 1 copy that forks at the right routers, delivering only to LANs with active receivers. When a receiver leaves, the branch is pruned, and traffic stops flowing to that LAN.

## The Approach

The simulation follows six stages:

1. **Network topology** - Define 5 routers, 4 LANs, 1 RP, 3 sources, and 8 receivers. Establish the unicast routing table (shortest path between all pairs) that PIM uses to build multicast trees.

2. **IGMP host management** - Model IGMPv3 membership reports. Each receiver sends a join for a multicast group (e.g., 239.1.1.1). The designated router (DR) on each LAN processes the report and maintains a group membership table.

3. **PIM-SM shared tree (RPT)** - When a DR learns of a group join, it sends a PIM Join toward the RP. The RP-centric shared tree is built hop-by-hop along the unicast shortest path from each DR to the RP.

4. **Source registration** - When a source starts sending, its DR encapsulates the first packet in a PIM Register message and sends it to the RP. The RP decapsulates and forwards it down the shared tree. The RP then sends a Join toward the source to build the source-to-RP branch.

5. **SPT switchover** - When a receiver's DR detects that traffic on the shared tree exceeds a configured threshold (e.g., 1 Mbps), it sends a PIM Join directly toward the source, creating a shortest-path tree (SPT). Once the SPT is established, the DR sends a prune to the RP to remove the shared-tree branch.

6. **Pruning and bandwidth accounting** - When the last receiver on a LAN leaves the group, the DR sends a PIM Prune toward the RP. The tree is pruned. Track bandwidth at each link: unicast would send N copies; multicast sends 1 copy per active branch.

## Build It

1. Define dataclasses for Router, Lan, Receiver, Source, MulticastGroup, IgmpReport, PimMessage, and TreeBranch.
2. Implement the network topology with 5 routers, 4 LANs, 1 RP, and unicast shortest-path routing.
3. Implement IGMPv3 host join/leave processing at each LAN's designated router.
4. Implement PIM-SM shared-tree construction: join messages propagate from DRs toward the RP.
5. Implement source registration: the source's DR sends Register messages to the RP, which decapsulates and forwards.
6. Implement SPT switchover: when traffic exceeds the threshold, the DR joins directly toward the source and prunes the shared tree.
7. Implement pruning: when all receivers on a LAN leave, the branch is pruned.
8. Implement bandwidth accounting: compare unicast (N copies) vs. multicast (1 copy per active branch) at each link.
9. Run `code/main.py` and study the tree construction, switchover, pruning, and bandwidth savings.

## Expected Outcomes

When you run `code/main.py` you should observe:

- A 5-router, 4-LAN topology with the RP at Router R3
- IGMPv3 joins from receivers on LANs 1, 2, and 4 for group 239.1.1.1
- A shared tree (RPT) built from each DR toward the RP at R3
- Source S1 on LAN 3 registering with the RP, traffic flowing down the shared tree to active receivers
- SPT switchover when DR on LAN 1 detects traffic exceeding the 1 Mbps threshold, creating a direct path from S1 to LAN 1
- Pruning when the receiver on LAN 4 leaves: the branch from R4 to LAN 4 is pruned
- Bandwidth savings: unicast would send 3 copies over the backbone; multicast sends 1 copy that forks at R1
- A tree state table showing which routers have which (S,G) and (*,G) entries

## Deliverables

- `outputs/multicast-tree.txt` - The shared tree and source tree diagrams with branch labels
- `outputs/igmp-log.txt` - IGMPv3 membership report log with join, leave, and source-specific entries
- `outputs/pim-log.txt` - PIM message log showing Join, Register, Prune, and SPT switchover events
- `outputs/bandwidth-analysis.txt` - Per-link bandwidth comparison: unicast vs. multicast
- `outputs/multicast-runbook.md` - A runbook for debugging PIM-SM and IGMP in production networks

## Exercises

1. Add a second RP with Anycast-RP (MSDP) and show how both RPs exchange active source information. What happens when the primary RP fails?
2. Model IGMPv3 source-specific joins (SSM, Source-Specific Multicast) where the receiver joins (S,G) directly without an RP. How does this eliminate the shared tree?
3. Introduce a rogue source that sends to the group without registering with the RP. How does PIM-SM handle unregistered sources? What is the Register-Rate-Limit?
4. Add packet loss to the shared tree and show how it triggers earlier SPT switchover. How does the SPT threshold interact with packet loss?
5. Simulate a dense-mode scenario (PIM-DM) using flood-and-prune. Compare the bandwidth usage with PIM-SM for the same topology. When is dense mode preferable?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Rendezvous Point (RP) | The multicast meeting point | A router where sources register and receivers join to form the shared tree |
| Shared tree (RPT) | The RP-rooted tree | A distribution tree rooted at the RP, used by all sources for a group (*,G) |
| Source tree (SPT) | The shortest path tree | A distribution tree rooted at the source (S,G), used after switchover for lower latency |
| IGMP | Host membership protocol | Internet Group Management Protocol: hosts tell their DR which groups they want to receive |
| Prune | Stopping unwanted traffic | A PIM message that removes a branch from the distribution tree when no receivers remain downstream |

## Further Reading

- RFC 7761 - PIM-SM Protocol Specification (Revised)
- RFC 3376 - Internet Group Management Protocol, Version 3
- RFC 4607 - Source-Specific Multicast for IP
- "Interdomain Multicast Routing" by Brian C. Greene and Tynan Dunstan
- Cisco IOS PIM-SM and IGMP configuration guide