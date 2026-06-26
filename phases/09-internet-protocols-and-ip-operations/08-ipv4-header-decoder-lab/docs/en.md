# IPv4 Header Decoder Lab

> The IPv4 header is 20 bytes minimum plus up to 40 bytes of options, and every field has a purpose and a characteristic failure mode. The visible byte map: **Version/IHL** (0x45 for "IPv4, 5 32-bit words"), **DSCP/ECN** (DiffServ + Explicit Congestion Notification), **Total Length** (u16, big-endian), **Identification** (u16, datagram ID — pairs with the next two fields to enable fragmentation), **Flags/Fragment Offset** (3-bit flags = Reserved | DF | MF, 13-bit offset in 8-byte units), **TTL** (u8, 64 is common, 255 is max), **Protocol** (u8, 6=TCP, 17=UDP, 1=ICMP, 89=OSPF, 41=IPv6-in-IPv4), **Header Checksum** (ones-complement 16-bit sum, recomputed at every TTL decrement), **Source and Destination IPs** (4+4 bytes, dotted-decimal). RFC 791 is the source; Wireshark reads the header exactly this way. Failure modes are concrete: a DF-set datagram hitting a smaller-MTU link triggers an ICMP Destination Unreachable code 4; a TTL counting down to 0 returns a Time Exceeded (traceroute relies on it); a miscompute of the checksum bit-by-bit is detected by every router along the path.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 9 lessons 01-03 (IPv4, IP addresses, IPv6); lesson 04 (ICMP/ARP/DHCP/MPLS)
**Time:** ~90 minutes

## Learning Objectives

- Read the IPv4 header field decoder control plane at the byte-level of evidence — identify which packet fields, timers, counters, or protocol messages prove normal behavior.
- Build or interpret a runnable simulation of the protocol (see [code/main.py](../code/main.py)) and tie every function back to a specific RFC sentence or source chapter section.
- Diagnose at least three concrete failure modes the protocol produces and name the one-line diagnostic command (`tcpdump`, Wireshark display filter, router `show` command, `traceroute -I`) that confirms each.
- Apply IPv4 header field decoder to the source chapter (5.6.1) in operational terms — not "know the section," but be able to reproduce the tables, state diagrams, and numeric examples the textbook gives.
- Produce a reusable artifact under [outputs/](../) — a prompt template, a decision runbook, a trace annotation checklist, or a parser — that teaches the topic from evidence and not from the source diagram alone.

## The Problem

A NOC analyst pastes a 20-byte IP header hex string from a tcpdump capture: `45 00 00 3c 1c 46 40 00 40 06 b1 e6 ac 10 00 01 ac 10 00 02`. She needs to identify which fields she must read to triage: is it TCP/UDP/ICMP? Are DF/MF set? What is the TTL? Is the checksum valid? Without a tool, she flips bits in her head and gets tangled on the flags field because the overall 16-bit word ("0x4000") reads differently from the standalone bits ("DF = 1, MF = 0"). Another capture has `45 00 00 54 00 00 00 00 40 01` — flag bits "00", DF/MF both 0, fragment offset 0 — but a fragment shows `2000` instead of "4000," and she wonders whether the Reserved bit has a meaning today. The authoring goal of this lab is that the reader can confidently read every IPv4 header byte using only an 8-bit and 16-bit understanding.

## The Concept

Source material: `chapters/chapter-05-the-network-layer.md`, section 5.6.1. The protocol reference is RFC 791; the runnable model is [`code/main.py`](../code/main.py). The SVG diagram ([`assets/ipv4-header-decoder-lab.svg`](../assets/ipv4-header-decoder-lab.svg)) shows the byte layout, the state machine, or the topology that this lesson centers on — work through it before reading the prose below.

### Why this layer exists

The Internet layer is not just IP forwarding. ICMP, ARP, DHCP, MPLS, OSPF, BGP, IGMP, and Mobile IP each fill a void that pure datagram delivery cannot: error reporting, address resolution, automatic configuration, fast label-based switching, intradomain routing, interdomain policy routing, group membership, and host mobility. Tracing every one of those back to observable packet-level or state-level evidence is what separates a network engineer from a network memorizer.

### Protocol mechanism in detail

The IPv4 header is 20 bytes minimum plus up to 40 bytes of options, and every field has a purpose and a characteristic failure mode. The visible byte map: **Version/IHL** (0x45 for "IPv4, 5 32-bit words"), **DSCP/ECN** (DiffServ + Explicit Congestion Notification), **Total Length** (u16, big-endian), **Identification** (u16, datagram ID — pairs with the next two fields to enable fragmentation), **Flags/Fragment Offset** (3-bit flags = Reserved | DF | MF, 13-bit offset in 8-byte units), **TTL** (u8, 64 is common, 255 is max), **Protocol** (u8, 6=TCP, 17=UDP, 1=ICMP, 89=OSPF, 41=IPv6-in-IPv4), **Header Checksum** (ones-complement 16-bit sum, recomputed at every TTL decrement), **Source and Destination IPs** (4+4 bytes, dotted-decimal). RFC 791 is the source; Wireshark reads the header exactly this way. Failure modes are concrete: a DF-set datagram hitting a smaller-MTU link triggers an ICMP Destination Unreachable code 4; a TTL counting down to 0 returns a Time Exceeded (traceroute relies on it); a miscompute of the checksum bit-by-bit is detected by every router along the path.

`code/main.py` reproduces the byte layouts, state machines, timers, and decision rules that this mechanism relies on. The functions are not stubs: each is parameterized to print a worked example that mirrors the source chapter. Run it twice — once to see the happy path, once with a modified parameter that triggers the failure mode described in the problem.

### Decision rules and tables

The source chapter and RFC 791 give explicit tables — message types, timer values, field encodings. `code/main.py` reproduces them. The lesson''s tables in this document are not summaries; they are *operational checklists* keyed to the evidence you would see in a capture, in a routing daemon log, or in a `show` command.

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

- A **debugging prompt** for IPv4 header field decoder that teaches future you (or any agent) to triage the symptom described in *The Problem*. The existing `prompt-08-ipv4-header-decoder-lab.md` is the skeleton; replace it with a prompt that names the protocol fields, the RFC citations, and the confirm-filter list.

Start from [`outputs/prompt-08-ipv4-header-decoder-lab.md`](../outputs/prompt-08-ipv4-header-decoder-lab.md).

## Exercises

1. Run `code/main.py` and report the exact output. For each printed line, trace it back to a numbered sentence or figure in 5.6.1 of the source chapter.
2. Using the header layout from the lesson, decode a real IPv4 packet (use `tcpdump -xx -c 5` on your workstation) byte-by-byte. List every field and its value; verify the header checksum by hand (16-bit ones-complement sum).
3. Describe the IPv4 header field decoder failure mode named in *The Problem*, name the smallest diagnostic command that confirms it, and write the one-line fix.
4. Compare the OSPF and BGP route-selection processes by producing two trace examples — one intradomain, one interdomain — annotated with which attributes decide the selected path.
5. Implement (in 30 lines of stdlib Python) the *minimal* version of one of the functions in `code/main.py`. Confirm that its output matches the fuller version''s output, then extend it to print one more diagnostic.
6. A junior engineer claims "IPv4 header field decoder is just config." Write the one-paragraph rebuttal that names the protocol fields and state dependencies this lesson covers.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| IPv4 header field decoder | "That routing thing" | The 5.6.1 mechanism defined in RFC 791; observable in LSA, BGP update, or ICMP byte fields |
| Link state (OSPF) | "OSPF" | Each router floods its neighbor costs; every router runs Dijkstra; areas partition the AS so topology scales |
| Path vector (BGP) | "BGP" | Each route advertisement carries the AS_PATH list; the receiving router rejects the route if its own ASN appears in it |
| Hot-potato routing | "BGP weirdness" | A border router hands a packet to the next AS on the shortest **internal** path even if the downstream journey is longer — produces asymmetric paths |
| LSA | "an OSPF packet" | Link State Advertisement; describes a router''s interface costs to its neighbors; the unit of OSPF''s flooded database |
| Area 0 / Backbone | "OSPF backbone" | The hub area that connects all other areas; an inter-area path must transit area 0 |
| Longest-prefix match | "the routing rule" | Among matching prefixes in the FIB, the one with the longest mask wins; /32 beats /24 beats /0 default |
| AS_PATH | "BGP loop detection" | The list of ASNs the route has crossed, newest first; the receiver checks for its own ASN to break loops |

## Further Reading

- **RFC 791** — the authoritative specification; the byte layouts, the state machines, and the exact timer values.
- **Tanenbaum &amp; Wetherall**, *Computer Networks* (5th ed.), §5.6.1 — the source chapter section.
- **RFC 792** (ICMP), **RFC 2328** (OSPF v2), **RFC 4271** (BGP-4), **RFC 3376** (IGMP v3), **RFC 3344** (Mobile IPv4), **RFC 4632** (CIDR) — the protocol family this lesson is part of.
- **RFC 3031** (MPLS), **RFC 826** (ARP), **RFC 2131** (DHCP) — the companion Internet-layer control protocols covered in lesson 09-04.
- VMware / Cisco official configuration guides — the operational surface where these protocols show up in production.
