# IP Version 6

> IPv6 (RFC 8200, the successor to IPv4) uses **128-bit** addresses written as **8 groups of four hex digits** separated by colons, with **`::` compression** for one run of zero groups and leading-zero omission within each group. Addresses split into **global unicast** (currently `2000::/3`), **link-local** (`fe80::/10`, one per interface, never routed), **unique local** (`fd00::/8`), **multicast** (`ff00::/8`, scoping via the first quarter-byte), and the **loopback** `::1`. A host can build a **link-local** address without any server by folding its 48-bit MAC into a 64-bit **EUI-64** interface ID (insert `FF:FE`, flip the `U/L` bit 6) and prepending `fe80::/10` — this is **Stateless Address Autoconfiguration (SLAAC)**. The fixed **40-byte** base header carries only seven fields: Version, Traffic Class (8 bits), **Flow Label** (20 bits), **Payload Length** (excludes the base header), **Next Header**, **Hop Limit** (8 bits, replaces IPv4 TTL), and two 16-byte addresses. Optional functionality moves into a chain of **extension headers** (hop-by-hop, destination, routing, fragment, authentication, ESP) pointed to by **Next Header**. **Fragmentation is source-only**: routers never fragment — they drop and send an ICMPv6 Packet Too Big so the source runs Path MTU Discovery. **ICMPv6** subsumes ARP (Neighbor Discovery / RS-RA-NS-NA), DHCP-style config, and multicast group management. The result is a leaner, faster-to-forward network layer with effectively unlimited address space.

**Type:** Build
**Languages:** IP tools, Wireshark
**Prerequisites:** IPv4 header and addressing (Phase 9 L01-L02), fragmentation and path MTU (Phase 8 L11-L12)
**Time:** ~90 minutes

## Learning Objectives

- Parse a 128-bit IPv6 address, expand `::` compression, and write the RFC 5952 canonical compressed form by hand.
- Classify an address as global unicast, link-local, unique local, multicast (with scope), loopback, or unspecified, from its leading bits alone.
- Build a link-local address from a MAC via EUI-64, explaining the `FF:FE` insertion and the `U/L` bit flip.
- Decode the 40-byte fixed header field-by-field and contrast it with the 13-field IPv4 header: name every field that was removed and why.
- Walk an extension-header chain using **Next Header**, and explain why routers can skip options not meant for them.
- Explain source-only fragmentation and the ICMPv6 Packet Too Big / Path MTU Discovery loop that replaces router fragmentation.
- Identify the observable evidence of IPv6 on a live interface (`ip -6 addr`, RA flags, Neighbor Cache) and in a Wireshark capture.

## The Problem

A network team at a growing mobile carrier has been told to provision a million new IoT endpoints. IPv4 with NAT has worked for years, but the pool is exhausted and each private `/10` is now carved into overlapping NAT layers that break SIP, FTP active mode, and IPsec tunnel endpoints. The team tries to roll out IPv6 and hits three walls: addresses look untypeable (`2001:0db8:0000:0000:0000:8a2e:0370:7334`), hosts are autoconfiguring addresses nobody provisioned, and Wireshark shows packets the team cannot map to the IPv4 mental model — no IHL, no Protocol field, no checksum, a Next Header chain, and ICMPv6 messages labeled RS/RA/NS/NA that nobody has seen before.

The walls are one wall: IPv6 is a deliberately different network layer. The address notation is compressed, not random — learn the three rules and the giant string becomes `2001:db8::8a2e:370:7334`. The autoconfigured addresses are **SLAAC** doing its job — a host folds its MAC into EUI-64, prepends `fe80::`, and is reachable on-link immediately; a Router Advertisement later adds a global prefix. The Wireshark unfamiliarity is the header simplification: IPv4's IHL, Protocol, fragmentation fields, and header checksum were *removed* — Next Header chains replace them, routers no longer fragment, and ICMPv6 absorbed ARP's job via Neighbor Discovery. Once you can read the header, the address types, and the ND exchange, the million IoT endpoints each get a globally reachable address with zero manual configuration.

## The Concept

IPv6 is a redesign of the network layer driven by one acute problem (address exhaustion) and nine IETF design goals: support billions of hosts, shrink routing tables, simplify the header for faster forwarding, add authentication and privacy, attend to type-of-service, scope multicasts, permit roaming, allow protocol evolution, and let old and new coexist. The result keeps the datagram service of IP but replaces the header, the address width, the fragmentation model, and the link-local control protocol.

### IPv6 header vs IPv4 header

The fixed IPv6 base header is 40 bytes with seven fields. Compare with IPv4's 13-field variable-length header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Version|   Traffic Class   |           Flow Label             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        Payload Length       |  Next Header |   Hop Limit      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                     Source Address (128 bits)                 +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                  Destination Address (128 bits)               +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| IPv4 field | IPv6 fate | Why |
|---|---|---|
| IHL (header length) | **Removed** | IPv6 base header is fixed at 40 bytes; no variable options inside it |
| Protocol | **Renamed** → Next Header | Now also chains extension headers, not just transport demux |
| Identification / Flags / Fragment Offset | **Removed from base** → Fragment extension header | Source-only fragmentation, optional |
| Header Checksum | **Removed** | Per-hop checksum is a major router cost; link + transport already checksum |
| Total Length | **Renamed** → Payload Length | Now excludes the 40-byte base, so max payload is 65535 not 65515 |
| TTL | **Renamed** → Hop Limit | Honest name: every router decrements by 1, never seconds |
| DSCP/ECN (Diff. Services) | Kept (8 bits) | Same QoS and explicit congestion signaling as IPv4 |
| Options | **Removed from base** → extension headers | Routers skip chain entries not meant for them — faster |

The **Flow Label** (20 bits) is IPv6's new idea: a source stamps a flow identifier so routers can give a stream of packets consistent treatment (a pseudo-circuit inside a datagram network). Flow labels should be chosen randomly, not sequentially, so routers can hash them.

### Address types and scope

IPv6 addresses are 128 bits, written as eight groups of four hex digits:

```
2001:0db8:0000:0000:0000:8a2e:0370:7334   <- full form
2001:0db8:0000:0000:0000:0000:0000:0001   <- full form
```

Three compression rules (RFC 5952):

1. Drop leading zeros in each group: `0db8` → `db8`, `0000` → `0`.
2. Replace one contiguous run of all-zero groups with `::` (only once): `2001:0db8:0:0:0:0:0:1` → `2001:db8::1`.
3. IPv4-mapped addresses can use dotted-quad for the last 32 bits: `::ffff:192.0.2.1`.

Address types by prefix:

| Prefix | Type | Scope / use |
|---|---|---|
| `::` (all zero) | Unspecified | Source when host has no address yet (e.g. DHCPv6 solicit) |
| `::1` | Loopback | Host to itself, never leaves the interface |
| `fe80::/10` | Link-Local unicast | One per interface, autoconfigured, **never routed** off-link |
| `fc00::/7` (commonly `fd00::/8`) | Unique Local Address (ULA) | Private IPv6, site-local, may be routed inside a site |
| `2000::/3` (currently `2001::`, `2002::`, `2003::`…) | Global Unicast | Routed on the public Internet |
| `ff00::/8` | Multicast | One-to-many; scope encoded in the second quarter-byte |
| `::ffff:0:0/96` | IPv4-mapped | IPv6 representation of an IPv4 address for dual-stack |

Multicast scopes (the quarter-byte after `ff`):

| Flag+Scope (hex) | Meaning | Example |
|---|---|---|
| `ff01::` | Interface-local | loopback to self |
| `ff02::` | Link-local | `ff02::1` all-nodes, `ff02::2` all-routers |
| `ff05::` | Site-local | site-wide services |
| `ff0e::` | Global | Internet-wide multicast |
| `ff02::1:ffXX:XXXX` | Solicited-node | ND resolution, derived from unicast last 24 bits |

Anycast — one address shared by multiple interfaces, routed to the nearest — exists too: an address is anycast only by configuration, not by prefix. The same address block serves unicast and anycast; the routing tells the difference.

### Stateless Address Autoconfiguration (SLAAC)

SLAAC is how an IPv6 host gets a globally routable address with no DHCP server and no manual entry. The two-step recipe:

1. **Link-local first.** The host takes its 48-bit MAC, inserts `FF:FE` in the middle to make a 64-bit **EUI-64**, flips bit 6 (the Universal/Local bit) of the first byte, and prepends `fe80::/10`. Example: MAC `00:11:22:33:44:55` → flip U/L bit → `02:11:22:FF:FE:33:44:55` → link-local `fe80::211:22ff:fe33:4455`. The host then runs Duplicate Address Detection (DAD) via Neighbor Solicitation before using it.
2. **Global from a Router Advertisement.** The host sends a Router Solicitation (RS, ICMPv6 type 133); a router replies with a Router Advertisement (RA, type 134) carrying a prefix (e.g. `2001:db8:1a2b::/64`) and flags. The host takes that prefix, appends its EUI-64 (or a privacy-randomized 64-bit token), and forms a global address. The RA's M/O flags decide whether DHCPv6 is also needed.

This is why the mobile carrier's million IoT endpoints self-provision: each device has a unique MAC, each MAC yields a unique EUI-64, and one RA on the link seeds a global address per device.

### Extension header chain

The **Next Header** field of the base header is the key to the simplification. It names either the transport protocol (TCP=6, UDP=17, ICMPv6=58) or the first extension header. Each extension header starts with its own Next Header byte naming what follows, forming a linked list. Defined extension headers:

| Next Header value | Header | Purpose |
|---|---|---|
| 0 | Hop-by-Hop Options | Every router examines (e.g. jumbograms > 65,535 B) |
| 43 | Routing | Loose source route — list of routers to visit |
| 44 | Fragment | Source fragmentation info (id, offset, M flag) |
| 50 | Encapsulating Security Payload (ESP) | Encryption + integrity |
| 51 | Authentication Header (AH) | Sender authentication + integrity |
| 59 | No Next Header | End of chain, no payload |
| 60 | Destination Options | Examined only by destination |

Routers only have to read Hop-by-Hop (and Routing, if present) — they skip the rest, which is what makes the design faster than IPv4 options.

### Fragmentation in IPv6 (source-only)

IPv6 breaks with IPv4 here: **routers never fragment**. A router that receives a packet bigger than the next link's MTU drops it and sends an ICMPv6 **Packet Too Big** message (type 2) back to the source, carrying the link MTU. The source then runs **Path MTU Discovery**: it lowers its packet size and retransmits. If the source *must* fragment (e.g. an app hands it a 100 KB buffer), it uses the Fragment extension header with a 32-bit identification and a 13-bit offset — but only the source does this, never an intermediate router. All IPv6-conformant hosts must accept packets of at least **1280 bytes** (the minimum MTU), raised from IPv4's 576.

### ICMPv6 and Neighbor Discovery

ICMPv6 (Next Header 58) subsumes four IPv4-era jobs:

| ICMPv6 type | Name | Replaces (IPv4) |
|---|---|---|
| 133 | Router Solicitation | Router Discovery (ICMPv4) |
| 134 | Router Advertisement | Router Discovery (ICMPv4) |
| 135 | Neighbor Solicitation | ARP request |
| 136 | Neighbor Advertisement | ARP reply |
| 137 | Redirect | ICMPv4 Redirect |
| 2 | Packet Too Big | ICMPv4 Fragmentation Needed |

Neighbor Discovery (ND, RFC 4861) replaces ARP without broadcasts: a host multicasts a Neighbor Solicitation to the **solicited-node** address `ff02::1:ffXX:XXXX` (derived from the target's last 24 bits), and the owner unicasts a Neighbor Advertisement back. This is why `ip -6 neigh` is the IPv6 equivalent of `arp -a`.

Reference implementation: `code/main.py` parses the base header, compresses addresses to canonical form, classifies address type, extracts prefix ranges, and generates EUI-64 / link-local addresses. Header diagram and address ranges are in `assets/ip-version-6.svg`.

## Build It

`code/main.py` is a stdlib-only IPv6 toolkit. Run `python3 code/main.py` and you get four demonstrations:

1. **Header parser** — feed it a 40-byte hex payload; it slices out Version, Traffic Class, Flow Label, Payload Length, Next Header (with name lookup), Hop Limit, and the two addresses, then prints a labeled dump.
2. **Address compressor** — takes a full-form address, expands `::`, then writes the RFC 5952 canonical compressed form (longest zero run, no leading zeros, lowercase).
3. **EUI-64 generator** — takes a MAC, inserts `FF:FE`, flips the U/L bit, and forms the link-local `fe80::` address.
4. **Subnet extractor** — takes `prefix/len`, computes the network, first and last host, and count.
5. **Address classifier** — identifies global unicast, link-local, ULA, multicast (with scope), loopback, and unspecified.

Change the sample addresses and raw bytes to match your own capture; replace the printed observations with evidence from your lab.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify an address | Leading bits vs prefix table | `fe80::1` → link-local; `ff02::1` → multicast link-scope; `2001:db8::1` → global |
| Compress canonical | RFC 5952 longest-zero-run rule | `2001:0db8:0:0:0:0:0:1` → `2001:db8::1`, never `2001:db8:0::1` |
| Generate link-local | MAC → EUI-64 → fe80:: | MAC `02:00:5e:10:00:00` → `fe80::00:5e:10ff:fe10:0:0` (note U/L flip back) |
| Walk extension headers | Next Header chain | base NH=0 → hop-by-hop → NH=6 TCP → payload is TCP segment |
| Diagnose "host unreachable" | Neighbor Solicitation / Advertisement, Router Advertisement presence | NS sent with no NA → link-layer issue; no RA → no router on-link |
| Spot source-only fragment | Fragment extension header present, id + offset | Only the source sets it; a router forwarding it does not fragment further |

Wireshark filters: `ipv6`, `icmpv6.type == 134` (RA), `icmpv6.type == 135` (NS), `ip6.hlim == 64`, `ipv6.addr == fe80::/10`.

## Ship It

Produce one reusable artifact under `outputs/`:

- An **IPv6 address decoder cheat sheet** — the three compression rules, the prefix table, the EUI-64 recipe, and the multicast scope byte, in one page.
- An **ND exchange runbook** — RS/RA/NS/NA sequence with the exact ICMPv6 type numbers and what absence of each message means.
- The **header + classifier script** (`code/main.py`) wired to your own captures — replace the sample bytes with a real packet from `tcpdump -x`.

Start from `outputs/prompt-ip-version-6.md`.

## Exercises

1. Expand `2001:db8::8a2e:370:7334` to its full 8-group form, then re-compress using the RFC 5952 rule. Does it match? Why is `2001:db8:0:0:0:0:0:1` preferred over `2001:db8::0:1`?
2. A host with MAC `00:1b:44:11:3a:b7` boots on an IPv6 link. Compute its link-local address, then show the Neighbor Solicitation it sends for DAD and the solicited-node multicast address.
3. Given the raw header hex `6000000004060640 20010db8000000000000000000000001 20010db8000000000000000000000002`, decode every field by hand and label the Next Header.
4. A router receives a 5000-byte IPv6 packet and the next link's MTU is 1500. Describe exactly what the router does, the ICMPv6 message it sends, and what the source does next.
5. Compare the IPv4 and IPv6 headers field-by-field. Name every IPv4 field that was removed and the reason. Which removals are controversial?
6. Run `code/main.py` and then change the sample MAC and CIDR to your own. Annotate each line of output with the rule that produced it.
7. In Wireshark, capture `icmpv6` on your Wi-Fi interface. Identify at least one Router Advertisement and one Neighbor Solicitation. What prefix is the RA advertising?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| `::` compression | "the shortcut" | Replace one longest run of all-zero groups with `::`; allowed once, per RFC 5952 |
| EUI-64 | "the MAC trick" | 48-bit MAC + `FF:FE` insertion + U/L bit flip → 64-bit interface ID for SLAAC |
| Link-local | "the fe80 address" | `fe80::/10`, one per interface, autoconfigured, never routed off-link |
| Flow label | "the QoS tag" | 20-bit source-set tag so routers can give a packet stream consistent treatment |
| Next Header | "the new Protocol field" | Chains extension headers or names the transport (6=TCP, 17=UDP, 58=ICMPv6) |
| Hop limit | "the new TTL" | 8-bit decremented per hop; renamed because nobody ever treated TTL as seconds |
| Extension header | "the new options" | Linked-list of optional headers; routers skip any not meant for them |
| SLAAC | "auto address" | Stateless Address Autoconfiguration: link-local from MAC, global from RA prefix |
| Neighbor Discovery | "IPv6's ARP" | ICMPv6 RS/RA/NS/NA replacing ARP, using multicast solicited-node addresses |
| Path MTU Discovery | "the no-fragment dance" | Source learns smallest link MTU via ICMPv6 Packet Too Big; routers never fragment |

## Further Reading

- **RFC 8200** — IPv6 for the IPv6 specification (obsoletes RFC 2460); the authoritative current spec.
- **RFC 4291** — IPv6 Addressing Architecture; prefix assignments and address types.
- **RFC 4861** — Neighbor Discovery for IPv6; RS/RA/NS/NA.
- **RFC 4862** — IPv6 Stateless Address Autoconfiguration (SLAAC).
- **RFC 5952** — A Recommendation for IPv6 Address Text Representation (canonical compression rules).
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.6.3 — the source material for this lesson.
- Wireshark display filter reference: `ipv6`, `icmpv6`, `ip6.nxt`.