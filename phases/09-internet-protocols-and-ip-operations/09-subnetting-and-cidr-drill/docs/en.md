# Subnetting and CIDR Drill

> Subnetting (RFC 950) and **CIDR** (Classless Inter-Domain Routing, RFC 4632) are the two mechanisms that let IP address allocation scale. Subnetting splits an assigned /8 or /16 into smaller pieces using a **subnet mask**: a /24 has 256 addresses, /25 has 128, /30 has 4 (2 usable for point-to-point), /31 has 2 (RFC 3021 lets point-to-point use even these last two). The router computes the prefix by ANDing the destination IP with the mask: `192.208.2.151 AND 255.255.128.0` → `192.208.0.0`, then looks up that prefix in its routing table using **longest-prefix match**. CIDR eliminates the historical Class A/B/C boundaries by allowing arbitrary prefix lengths anywhere in the table — the longest matching prefix wins, so a /32 host route is preferred over a /24 which is preferred over a default /0. A typical enterprise splits a /16 into a /17 (CS), /18 (EE), /19 (Art), and leaves the rest unallocated. The failure mode of mis-subnetting is silent traffic misdelivery; the failure mode of ignoring longest-prefix is leaked default routes and worldwide black holes.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 9 lessons 01-03 (IPv4, IP addresses, IPv6); lesson 04 (ICMP/ARP/DHCP/MPLS)
**Time:** ~90 minutes

## Learning Objectives

- Read the Subnetting, CIDR control plane at the byte-level of evidence — identify which packet fields, timers, counters, or protocol messages prove normal behavior.
- Build or interpret a runnable simulation of the protocol (see [code/main.py](../code/main.py)) and tie every function back to a specific RFC sentence or source chapter section.
- Diagnose at least three concrete failure modes the protocol produces and name the one-line diagnostic command (`tcpdump`, Wireshark display filter, router `show` command, `traceroute -I`) that confirms each.
- Apply Subnetting, CIDR to the source chapter (5.6.2-5.6.3) in operational terms — not "know the section," but be able to reproduce the tables, state diagrams, and numeric examples the textbook gives.
- Produce a reusable artifact under [outputs/](../) — a prompt template, a decision runbook, a trace annotation checklist, or a parser — that teaches the topic from evidence and not from the source diagram alone.

## The Problem

A university is allocated 128.208.0.0/16. The CS department wants half of it, EE wants a quarter, Art wants an eighth. The engineer must compute the exact subnets in dotted decimal, verify which subnet a given host IP (192.208.2.151) belongs to by ANDing with each subnet mask, and confirm that the leak of a default route will be picked up only by the longest-prefix routes. The lab also drills the reverse: given a mask "255.255.240.0," how many host addresses are there? Given a /30 between two routers, why is it only two usable?

## The Concept

Source material: `chapters/chapter-05-the-network-layer.md`, section 5.6.2-5.6.3. The protocol reference is RFC 950, RFC 4632; the runnable model is [`code/main.py`](../code/main.py). The SVG diagram ([`assets/subnetting-and-cidr-drill.svg`](../assets/subnetting-and-cidr-drill.svg)) shows the byte layout, the state machine, or the topology that this lesson centers on — work through it before reading the prose below.

### Why this layer exists

The Internet layer is not just IP forwarding. ICMP, ARP, DHCP, MPLS, OSPF, BGP, IGMP, and Mobile IP each fill a void that pure datagram delivery cannot: error reporting, address resolution, automatic configuration, fast label-based switching, intradomain routing, interdomain policy routing, group membership, and host mobility. Tracing every one of those back to observable packet-level or state-level evidence is what separates a network engineer from a network memorizer.

### Protocol mechanism in detail

Subnetting (RFC 950) and **CIDR** (Classless Inter-Domain Routing, RFC 4632) are the two mechanisms that let IP address allocation scale. Subnetting splits an assigned /8 or /16 into smaller pieces using a **subnet mask**: a /24 has 256 addresses, /25 has 128, /30 has 4 (2 usable for point-to-point), /31 has 2 (RFC 3021 lets point-to-point use even these last two). The router computes the prefix by ANDing the destination IP with the mask: `192.208.2.151 AND 255.255.128.0` → `192.208.0.0`, then looks up that prefix in its routing table using **longest-prefix match**. CIDR eliminates the historical Class A/B/C boundaries by allowing arbitrary prefix lengths anywhere in the table — the longest matching prefix wins, so a /32 host route is preferred over a /24 which is preferred over a default /0. A typical enterprise splits a /16 into a /17 (CS), /18 (EE), /19 (Art), and leaves the rest unallocated. The failure mode of mis-subnetting is silent traffic misdelivery; the failure mode of ignoring longest-prefix is leaked default routes and worldwide black holes.

`code/main.py` reproduces the byte layouts, state machines, timers, and decision rules that this mechanism relies on. The functions are not stubs: each is parameterized to print a worked example that mirrors the source chapter. Run it twice — once to see the happy path, once with a modified parameter that triggers the failure mode described in the problem.

### Decision rules and tables

The source chapter and RFC 950, RFC 4632 give explicit tables — message types, timer values, field encodings. `code/main.py` reproduces them. The lesson''s tables in this document are not summaries; they are *operational checklists* keyed to the evidence you would see in a capture, in a routing daemon log, or in a `show` command.

### Failure modes you can predict

| Symptom observed | Likely protocol failure | Confirming evidence / command | Fix |
|---|---|---|---|
| Path appears shorter than physical path | Hot-potato early exit | `traceroute`; BGP table LOCAL_PREF | Re-LOCAL_PREF |
| Unannounced route appears globally | Prefix leak | AS_PATH in `show ip bgp` | Apply route-map |
| TTL 0 drops | Stuck-in-loop | `traceroute` shows hops repeating | Fix SPF tree / FIB |
| No ARP reply | Filter / detached host | `tcpdump arp`; `arp -an` | Check NIC / VLAN |
| ECHO REQUEST no ECHO REPLY | ICMP filtered | `tcptraceroute` instead | Open ACL |

## Build It

`code/main.py` is stdlib-only and self-contained. Walk through it in this order:

1. **Read the module docstring** at the top of the file — it names the source chapter section and the worked example reproduced.
2. **Run the happy path**: `python3 code/main.py` prints the worked example from the source (byte layout, LSA graph, BGP AS_PATH, subnet calc, etc.).
3. **Run the failure path**: edit the parameter that triggers the failure mode described in *The Problem* above, run again, and observe the diagnostic output.
4. **Cross-check with Wireshark or `tcpdump`**: open a real capture or `tcpdump -v` output and identify the same byte offsets and field values the model produces.

No pip dependencies. No network calls. No requirements beyond `python3` and the patience to read.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read the protocol header | Byte offsets, field widths, type/code octets | You can identify the protocol field from a hexdump without hesitation |
| Confirm normal operation | Wireshark display filter, daemon log, `show` output | You can match printed output of `code/main.py` against a capture |
| Diagnose a failure mode | The confirming diagnostic command | You pick the one-line filter or `show` that distinguishes competing hypotheses |
| Engineer policy | RFC-cited attributes | You write a route-map or an OSPF cost change with a one-sentence justification |
| Produce the artifact | The `outputs/prompt-*.md` | Future you reuses this when the symptom recurs |

## Ship It

Produce one reusable artifact under [`outputs/`](../):

- A **debugging prompt** for Subnetting, CIDR that teaches future you (or any agent) to triage the symptom described in *The Problem*. The existing `prompt-09-subnetting-and-cidr-drill.md` is the skeleton; replace it with a prompt that names the protocol fields, the RFC citations, and the confirm-filter list.

Start from [`outputs/prompt-09-subnetting-and-cidr-drill.md`](../outputs/prompt-09-subnetting-and-cidr-drill.md).

## Exercises

1. Run `code/main.py` and report the exact output. For each printed line, trace it back to a numbered sentence or figure in 5.6.2-5.6.3 of the source chapter.
2. Using the header layout from the lesson, decode a real IPv4 packet (use `tcpdump -xx -c 5` on your workstation) byte-by-byte. List every field and its value; verify the header checksum by hand (16-bit ones-complement sum).
3. Describe the Subnetting, CIDR failure mode named in *The Problem*, name the smallest diagnostic command that confirms it, and write the one-line fix.
4. Compare the OSPF and BGP route-selection processes by producing two trace examples — one intradomain, one interdomain — annotated with which attributes decide the selected path.
5. Implement (in 30 lines of stdlib Python) the *minimal* version of one of the functions in `code/main.py`. Confirm that its output matches the fuller version''s output, then extend it to print one more diagnostic.
6. A junior engineer claims "Subnetting, CIDR is just config." Write the one-paragraph rebuttal that names the protocol fields and state dependencies this lesson covers.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Subnetting, CIDR | "That routing thing" | The 5.6.2-5.6.3 mechanism defined in RFC 950, RFC 4632; observable in LSA, BGP update, or ICMP byte fields |
| Link state (OSPF) | "OSPF" | Each router floods its neighbor costs; every router runs Dijkstra; areas partition the AS so topology scales |
| Path vector (BGP) | "BGP" | Each route advertisement carries the AS_PATH list; the receiving router rejects the route if its own ASN appears in it |
| Hot-potato routing | "BGP weirdness" | A border router hands a packet to the next AS on the shortest **internal** path even if the downstream journey is longer — produces asymmetric paths |
| LSA | "an OSPF packet" | Link State Advertisement; describes a router''s interface costs to its neighbors; the unit of OSPF''s flooded database |
| Area 0 / Backbone | "OSPF backbone" | The hub area that connects all other areas; an inter-area path must transit area 0 |
| Longest-prefix match | "the routing rule" | Among matching prefixes in the FIB, the one with the longest mask wins; /32 beats /24 beats /0 default |
| AS_PATH | "BGP loop detection" | The list of ASNs the route has crossed, newest first; the receiver checks for its own ASN to break loops |

## Further Reading

- **RFC 950, RFC 4632** — the authoritative specification; the byte layouts, the state machines, and the exact timer values.
- **Tanenbaum &amp; Wetherall**, *Computer Networks* (5th ed.), §5.6.2-5.6.3 — the source chapter section.
- **RFC 792** (ICMP), **RFC 2328** (OSPF v2), **RFC 4271** (BGP-4), **RFC 3376** (IGMP v3), **RFC 3344** (Mobile IPv4), **RFC 4632** (CIDR) — the protocol family this lesson is part of.
- **RFC 3031** (MPLS), **RFC 826** (ARP), **RFC 2131** (DHCP) — the companion Internet-layer control protocols covered in lesson 09-04.
- VMware / Cisco official configuration guides — the operational surface where these protocols show up in production.
