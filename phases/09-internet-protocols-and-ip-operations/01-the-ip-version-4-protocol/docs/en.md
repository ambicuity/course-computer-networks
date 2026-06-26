# The IP Version 4 Protocol

> An IPv4 datagram is a 20-byte fixed header plus variable options (0-40 bytes), defined in RFC 791 (1981). The header carries a 4-bit **Version** (always 4), a 4-bit **IHL** (Internet Header Length, in 32-bit words; min 5, max 15 giving 60 bytes), a **Differentiated Services** field (top 6 bits DSCP per RFC 2474, bottom 2 bits ECN), a 16-bit **Total Length** (max 65,535 bytes), **Identification** for reassembly, 3 flag bits (**DF** Don't Fragment, **MF** More Fragments), a 13-bit **Fragment Offset** in 8-byte units, an 8-bit **TTL** decremented per hop and discarded at zero, an 8-bit **Protocol** number (6=TCP, 17=UDP, 1=ICMP), a 16-bit one's-complement **Header Checksum** recomputed at every hop, and 32-bit **Source** and **Destination** addresses. Bits are big-endian, high-order first. The checksum sums all 16-bit halfwords with the field zeroed, then takes the one's complement.

**Type:** Build
**Languages:** IP tools, Wireshark
**Prerequisites:** Phase 08 (Congestion, QoS & Internetworking)
**Time:** ~90 minutes

## Learning Objectives

- Lay out the IPv4 header field-by-field with exact bit widths and byte offsets, and explain why IHL counts in 32-bit words rather than bytes.
- Decode the Differentiated Services field into its DSCP (6-bit) and ECN (2-bit) subfields, and distinguish the original Type-of-Service interpretation from the modern differentiated-services reuse.
- Explain how Identification, DF, MF, and Fragment Offset cooperate to implement fragmentation and reassembly, including the 8-byte elementary fragment unit and the 13-bit maximum of 8192 fragments.
- Trace TTL from its origin (seconds counter, 255 max) to its modern hop-count behavior, and explain why each router must recompute the checksum.
- Validate a header checksum by summing 16-bit halfwords in one's-complement arithmetic and taking the one's complement of the result.
- Identify the Protocol field against the IANA registry (TCP=6, UDP=17, ICMP=1, OSPF=89) and describe the role of IP options and why they are rarely used today.

## The Problem

A site engineer is debugging why packets from a branch office to a cloud service never arrive. `ping` shows replies, `traceroute` stops at hop 9, and the application times out. Wireshark on the branch gateway shows outgoing packets with TTL 64 and Protocol 6, but the cloud load balancer logs never see them. Someone blames the firewall; someone else blames DNS.

The evidence is in the IPv4 header. A capture at hop 9 reveals ICMP Type 11 Code 0 (Time Exceeded) returning to the branch, with the original packet's TTL stripped to 0. The cloud ingress is behind a path with 18 routers, but the sending host started TTL at 16. The packet is correctly addressed, checksum-valid, and the Protocol field is right — but the TTL counter expired before delivery. TTL is not a performance hint; it is a hard hop limit designed to kill packets caught in routing loops. Understanding the 14 fields, their widths, and interactions is the difference between guessing at a firewall and reading the actual cause off the wire.

## The Concept

The IPv4 header is a compact 20-byte (minimum) control structure that a router reads on every hop. Every field exists to solve a concrete forwarding, integrity, or lifetime problem. The SVG diagrams the layout at byte resolution; `code/main.py` parses raw bytes and validates the checksum so you can verify any captured packet yourself.

### Header layout at 32-bit resolution

The header is transmitted in 32-bit words, left to right, top to bottom, high-order bit first (network byte order / big-endian):

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|Version|  IHL  |DSCP    |ECN|          Total Length           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Identification        |Flags|     Fragment Offset    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  TTL  |Protocol|       Header Checksum                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Source Address                             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Destination Address                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Options (0-40 bytes, padded to 4)          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

The first nibble (Version=4) lets a receiver distinguish IPv4 from IPv6 on the same wire. IHL occupies the low nibble of byte 0 and counts 32-bit words, so a bare 20-byte header has IHL=5 and a maximal 60-byte header (20 fixed + 40 options) has IHL=15.

### Field reference

| Offset | Width | Field | Purpose |
|---|---|---|---|
| 0 | 4 bits | Version | Always 4 for IPv4; enables version transition on shared media |
| 0 | 4 bits | IHL | Header length in 32-bit words; 5-15 (20-60 bytes) |
| 1 | 8 bits | Diff. Services | Top 6 bits DSCP (RFC 2474), bottom 2 bits ECN |
| 2 | 16 bits | Total Length | Entire datagram (header + payload); max 65,535 bytes |
| 4 | 16 bits | Identification | Reassembly tag shared by all fragments of one datagram |
| 6 | 3 bits | Flags | bit0 reserved (0), bit1 DF, bit2 MF |
| 6 | 13 bits | Fragment Offset | Position of this fragment in 8-byte units; max 8192 fragments |
| 8 | 8 bits | TTL | Hop counter; decremented per router, packet discarded at 0 |
| 9 | 8 bits | Protocol | Upper-layer protocol (IANA); 6=TCP, 17=UDP, 1=ICMP |
| 10 | 16 bits | Header Checksum | One's-complement sum of all 16-bit header halfwords |
| 12 | 32 bits | Source Address | Originating interface IP |
| 16 | 32 bits | Destination Address | Target interface IP |
| 20 | 0-40 | Options | Variable; padded to a 4-byte boundary |

### Differentiated Services: TOS reborn

Originally the byte at offset 1 was the **Type of Service** field: 3 precedence bits plus 3 bits signaling delay/throughput/reliability preferences. Routers never knew how to honor those bits, so they sat unused for years. RFC 2474 redefined it: the top 6 bits are **DSCP** (Differentiated Services Code Point) selecting the per-hop behavior class (Expedited Forwarding for voice, Assured Forwarding for prioritized data), and the bottom 2 bits carry **ECN** (Explicit Congestion Notification) so routers signal congestion before dropping packets.

### Fragmentation fields in concert

When a datagram exceeds a link's MTU, a router splits it. All fragments share the same **Identification** value so the receiver can group them. **DF** tells routers not to split — if too big, the router returns an ICMP error instead, which is how Path MTU Discovery works. **MF** is set on every fragment except the last, so the receiver knows when the set is complete. **Fragment Offset** gives the position in 8-byte units (the elementary fragment unit); the 13-bit width caps the count at 8192 fragments, supporting the 65,535-byte Total Length maximum.

### TTL: from seconds to hops

The **Time to Live** field was originally a 1-second resolution timer (255-second max), decremented per hop and on long queue sojourns. In practice every router decrements it by 1 per hop. When TTL reaches 0 the packet is discarded and an ICMP Time Exceeded returns to the source — the mechanism `traceroute` exploits. TTL prevents packets from circulating forever if routing tables form a loop. Because TTL changes at every hop, the **Header Checksum must be recomputed** at every router; incremental update tricks exist but the field is the reason routers cannot just forward verbatim.

### Protocol numbers

The **Protocol** field tells the receiving IP layer which transport or upper-layer protocol owns the payload. The registry is global and maintained by IANA (formerly RFC 1700, now online at iana.org):

| Protocol Number | Name | Common Use |
|---|---|---|
| 1 | ICMP | Control and diagnostics (ping, traceroute) |
| 2 | IGMP | Multicast group management |
| 6 | TCP | Reliable byte-stream transport |
| 17 | UDP | Datagram transport |
| 41 | IPv6 encapsulation | Tunneling IPv6 in IPv4 |
| 47 | GRE | Generic tunneling |
| 89 | OSPF | Interior gateway routing |
| 132 | SCTP | Message-oriented reliable transport |

### Header checksum algorithm

The checksum is a 16-bit one's-complement sum over all 16-bit halfwords of the header, with the field itself treated as zero during computation; the result is the one's complement of the sum. On verification, summing the entire header (including the stored checksum) folds to 0x0000, confirming integrity. It detects but does not correct errors. `code/main.py` implements this exactly: folds carries back into the low 16 bits during accumulation, then inverts.

### IP options

The Options area (0-40 bytes, padded to a 4-byte boundary) was designed as an extensibility escape. Each option begins with a 1-byte code; some carry a length byte and data. The original five were **Security**, **Strict Source Route** (exact path to follow), **Loose Source Route** (routers that must be visited, others allowed between), **Record Route** (each router appends its address), and **Timestamp** (address plus timestamp). The 40-byte cap makes Record Route and Timestamp useless on modern paths, and most routers shunt options to slow-path processing. They are rarely used in production traffic today.

## Build It

`code/main.py` is a stdlib-only IPv4 header parser. Run `python3 code/main.py` and it will:

1. Construct a sample 20-byte header (src 192.168.1.1, dst 192.168.1.2, Protocol 17 UDP, TTL 64), compute the checksum, and parse it back — printing every field with offsets and checksum validity.
2. Build a fragmented packet (MF=1, offset 1480, Protocol 6 TCP) to show fragment fields in action.
3. Flip a byte to corrupt the header and show the checksum failing.

Then feed it your own hex. Extract a raw IP header from a Wireshark capture (Copy → ... as Hex Stream), paste it into the script, and verify the checksum yourself.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decode header fields | Byte offsets 0-19 against field table | Version=4, IHL=5, addresses parse to correct dotted decimal |
| Identify upper protocol | Protocol field vs IANA table | 6 → TCP, 17 → UDP, 1 → ICMP — named without guessing |
| Validate integrity | Recomputed checksum vs stored | Sum of halfwords folds to 0x0000; flipped bit fails |
| Diagnose TTL exhaustion | ICMP Time Exceeded + original TTL | You correlate returned TTL=0 with sender's starting TTL |
| Spot fragmentation | MF flag + Fragment Offset | MF=1 with offset>0 means middle fragment; offset 0 + MF=1 is first |
| Read DSCP/ECN | Diff. Services byte split | Top 6 bits = DSCP class, bottom 2 = ECN — separated correctly |

Wireshark filters: `ip.proto == 6`, `ip.ttl < 10`, `ip.flags.df`, `ip.flags.mf`, `ip.len > 1500`.

## Ship It

Produce one reusable artifact under `outputs/`:

- An **IPv4 header cheat sheet** mapping every byte offset to its field, with the DSCP/ECN split and the protocol-number table.
- A **TTL exhaustion runbook**: how to read ICMP Time Exceeded, correlate it to the sender's starting TTL, and compute the hop count.
- The **parser script** (`code/main.py`) wired to a real capture so you can validate any packet offline.

Start from `outputs/prompt-the-ip-version-4-protocol.md`.

## Exercises

1. A packet has Total Length 1500, IHL 5, Protocol 6. Compute the payload length. If the next link has MTU 576, how many fragments result and what are their offsets?
2. A capture shows a packet with TTL 1 arriving at a router. What does the router do? What message returns to the sender, and what field in that ICMP packet carries the original header?
3. Given the hex `45 00 00 3C 1C 46 40 00 40 06 B1 E6 C0 A8 01 01 C0 A8 01 02`, parse every field by hand, then verify with `code/main.py`. Is the checksum valid?
4. A sender wants Path MTU Discovery. Which flag does it set, and what ICMP type/code signals that the packet was too big? What does the sender do next?
5. Construct a header with DSCP Expedited Forwarding (EF=46) and ECT(0) = 01. What is the raw byte at offset 1?
6. Explain why the Header Checksum is recomputed at every hop but the Ethernet CRC is not. Which layer owns each, and what does that tell you about where errors are detected?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| IHL | "header length" | 4-bit count of 32-bit words; 5 = 20 bytes (no options), 15 = 60 bytes (max options) |
| DSCP | "QoS marking" | Top 6 bits of the Diff. Services byte, selecting per-hop forwarding behavior (EF, AF, etc.) |
| TTL | "time to live" | 8-bit hop counter, decremented per router; packet discarded at 0, returns ICMP Time Exceeded |
| Protocol | "port number" (wrong) | 8-bit IANA registry identifying the upper-layer protocol (6=TCP, 17=UDP, 1=ICMP) |
| Fragment Offset | "fragment number" | 13-bit position of this fragment in 8-byte units; max 8192 fragments per datagram |
| Header Checksum | "the CRC" (wrong) | 16-bit one's-complement sum over header halfwords; recomputed per hop because TTL changes |
| DF / MF | "fragment flags" | DF = don't fragment (Path MTU Discovery); MF = more fragments follow (all but the last) |

## Further Reading

- **RFC 791** (Postel, 1981) — the authoritative standard: header format, fragmentation, options, checksum algorithm.
- **RFC 2474** (Nichols & Blake, 1998) — Differentiated Services field, replacing the original Type of Service.
- **RFC 3168** (Ramakrishnan et al., 2001) — ECN, the bottom 2 bits of the Diff. Services byte.
- Tanenbaum, Feamster & Wetherall, *Computer Networks* (6th ed.), §5.6.1 — the source material.
- IANA Protocol Numbers registry — the live list for the Protocol field (iana.org/assignments/protocol-numbers).