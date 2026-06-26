# ICMP and Traceroute Lab to OSPF and BGP Policy Lab

> This integrative lab ties together four network-layer control-plane protocols using only tools present on every operating system: `ping` (ICMP ECHO), `traceroute` (ICMP TIME EXCEEDED repurposed), `ospfd`/`bgpd` (link-state and path-vector routing) or simulation equivalents. ICMP lessons include: distinguishing unreachable, timeout, redirect, and echo messages; reading the ICMP type/code byte pair; using `traceroute -I` (ICMP) vs `traceroute -U` (UDP probe) vs `tcptraceroute` (TCP SYN to port 80) in the presence of middleware that filters UDP but permits SYN/ACK. OSPF policy lessons include: DR/BDR election, area 0s role, LSA flooding rules, and stub vs NSSA areas. BGP policy lessons include the customer/peer/transit trichotomy, route-maps, LOCAL_PREF, MED, AS_PATH prepending for traffic engineering, and the hot-potato early-exit pattern.

**Type:** Build
**Languages:** ping, traceroute, Wireshark, Diagrams
**Prerequisites:** Phase 9 lessons 01-03 (IPv4, IP addresses, IPv6); lesson 04 (ICMP/ARP/DHCP/MPLS)
**Time:** ~90 minutes

## Learning Objectives

- Read the ICMP, OSPF, BGP control plane at the byte-level of evidence — identify which packet fields, timers, counters, or protocol messages prove normal behavior.
- Build or interpret a runnable simulation of the protocol (see [code/main.py](../code/main.py)) and tie every function back to a specific RFC sentence or source chapter section.
- Diagnose at least three concrete failure modes the protocol produces and name the one-line diagnostic command (`tcpdump`, Wireshark display filter, router `show` command, `traceroute -I`) that confirms each.
- Apply ICMP, OSPF, BGP to the source chapter (5.6.4-5.6.7) in operational terms — not "know the section," but be able to reproduce the tables, state diagrams, and numeric examples the textbook gives.
- Produce a reusable artifact under [outputs/](../) — a prompt template, a decision runbook, a trace annotation checklist, or a parser — that teaches the topic from evidence and not from the source diagram alone.

## The Problem

A new ops engineer s first lab kit: a Linux router, three virtual interfaces, and a real BGP feed from a university peer. The lab requires four deliverables: (1) reproduce a black-hole route by flipping an OSPF cost to make a link preferred even when its down, then confirm recovery time using `traceroute` before, during, and after. (2) Demonstrate hot-potato routing by setting LOCAL_PREF differently on two border routers and watching traffic leave via the wrong exit for one destination. (3) Use `traceroute -T -p 80` vs default `traceroute` to bypass a path that drops UDP probes but permits TCP. (4) Spot a BGP prefix hijack by comparing AS_PATH on the local feed against the published RADB / IRR for a known customer prefix.

## The Concept

Source material: `chapters/chapter-05-the-network-layer.md`, section 5.6.4-5.6.7. The protocol reference is RFC 792, RFC 2328, RFC 4271; the runnable model is [`code/main.py`](../code/main.py). The SVG diagram ([`assets/icmp-and-traceroute-lab-to-ospf-and-bgp-policy-lab.svg`](../assets/icmp-and-traceroute-lab-to-ospf-and-bgp-policy-lab.svg)) shows the byte layout, the state machine, or the topology that this lesson centers on — work through it before reading the prose below.

### Why this layer exists

The Internet layer is not just IP forwarding. ICMP, ARP, DHCP, MPLS, OSPF, BGP, IGMP, and Mobile IP each fill a void that pure datagram delivery cannot: error reporting, address resolution, automatic configuration, fast label-based switching, intradomain routing, interdomain policy routing, group membership, and host mobility. Tracing every one of those back to observable packet-level or state-level evidence is what separates a network engineer from a network memorizer.

### Protocol mechanism in detail

This integrative lab ties together four network-layer control-plane protocols using only tools present on every operating system: `ping` (ICMP ECHO), `traceroute` (ICMP TIME EXCEEDED repurposed), `ospfd`/`bgpd` (link-state and path-vector routing) or simulation equivalents. ICMP lessons include: distinguishing unreachable, timeout, redirect, and echo messages; reading the ICMP type/code byte pair; using `traceroute -I` (ICMP) vs `traceroute -U` (UDP probe) vs `tcptraceroute` (TCP SYN to port 80) in the presence of middleware that filters UDP but permits SYN/ACK. OSPF policy lessons include: DR/BDR election, area 0s role, LSA flooding rules, and stub vs NSSA areas. BGP policy lessons include the customer/peer/transit trichotomy, route-maps, LOCAL_PREF, MED, AS_PATH prepending for traffic engineering, and the hot-potato early-exit pattern.

`code/main.py` reproduces the byte layouts, state machines, timers, and decision rules that this mechanism relies on. The functions are not stubs: each is parameterized to print a worked example that mirrors the source chapter. Run it twice — once to see the happy path, once with a modified parameter that triggers the failure mode described in the problem.

### Decision rules and tables

The source chapter and RFC 792, RFC 2328, RFC 4271 give explicit tables — message types, timer values, field encodings. `code/main.py` reproduces them. The lesson''s tables in this document are not summaries; they are *operational checklists* keyed to the evidence you would see in a capture, in a routing daemon log, or in a `show` command.

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

- A **debugging prompt** for ICMP, OSPF, BGP that teaches future you (or any agent) to triage the symptom described in *The Problem*. The existing `prompt-10-icmp-and-traceroute-lab-to-ospf-and-bgp-policy-lab.md` is the skeleton; replace it with a prompt that names the protocol fields, the RFC citations, and the confirm-filter list.

Start from [`outputs/prompt-10-icmp-and-traceroute-lab-to-ospf-and-bgp-policy-lab.md`](../outputs/prompt-10-icmp-and-traceroute-lab-to-ospf-and-bgp-policy-lab.md).

## Exercises

1. Run `code/main.py` and report the exact output. For each printed line, trace it back to a numbered sentence or figure in 5.6.4-5.6.7 of the source chapter.
2. Using the header layout from the lesson, decode a real IPv4 packet (use `tcpdump -xx -c 5` on your workstation) byte-by-byte. List every field and its value; verify the header checksum by hand (16-bit ones-complement sum).
3. Describe the ICMP, OSPF, BGP failure mode named in *The Problem*, name the smallest diagnostic command that confirms it, and write the one-line fix.
4. Compare the OSPF and BGP route-selection processes by producing two trace examples — one intradomain, one interdomain — annotated with which attributes decide the selected path.
5. Implement (in 30 lines of stdlib Python) the *minimal* version of one of the functions in `code/main.py`. Confirm that its output matches the fuller version''s output, then extend it to print one more diagnostic.
6. A junior engineer claims "ICMP, OSPF, BGP is just config." Write the one-paragraph rebuttal that names the protocol fields and state dependencies this lesson covers.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ICMP, OSPF, BGP | "That routing thing" | The 5.6.4-5.6.7 mechanism defined in RFC 792, RFC 2328, RFC 4271; observable in LSA, BGP update, or ICMP byte fields |
| Link state (OSPF) | "OSPF" | Each router floods its neighbor costs; every router runs Dijkstra; areas partition the AS so topology scales |
| Path vector (BGP) | "BGP" | Each route advertisement carries the AS_PATH list; the receiving router rejects the route if its own ASN appears in it |
| Hot-potato routing | "BGP weirdness" | A border router hands a packet to the next AS on the shortest **internal** path even if the downstream journey is longer — produces asymmetric paths |
| LSA | "an OSPF packet" | Link State Advertisement; describes a router''s interface costs to its neighbors; the unit of OSPF''s flooded database |
| Area 0 / Backbone | "OSPF backbone" | The hub area that connects all other areas; an inter-area path must transit area 0 |
| Longest-prefix match | "the routing rule" | Among matching prefixes in the FIB, the one with the longest mask wins; /32 beats /24 beats /0 default |
| AS_PATH | "BGP loop detection" | The list of ASNs the route has crossed, newest first; the receiver checks for its own ASN to break loops |

## Further Reading

- **RFC 792, RFC 2328, RFC 4271** — the authoritative specification; the byte layouts, the state machines, and the exact timer values.
- **Tanenbaum &amp; Wetherall**, *Computer Networks* (5th ed.), §5.6.4-5.6.7 — the source chapter section.
- **RFC 792** (ICMP), **RFC 2328** (OSPF v2), **RFC 4271** (BGP-4), **RFC 3376** (IGMP v3), **RFC 3344** (Mobile IPv4), **RFC 4632** (CIDR) — the protocol family this lesson is part of.
- **RFC 3031** (MPLS), **RFC 826** (ARP), **RFC 2131** (DHCP) — the companion Internet-layer control protocols covered in lesson 09-04.
- VMware / Cisco official configuration guides — the operational surface where these protocols show up in production.
