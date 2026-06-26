# Packet Fragmentation

> Every link has a maximum payload — **1500 bytes** for Ethernet, **2272** for 802.11, as small as **576 bytes** (IPv4 minimum) or **1280 bytes** (IPv6 minimum) — and when a packet crosses a link whose MTU is smaller than the packet, something must give. IPv4 routers may **fragment** the datagram on the fly: each fragment is a self-contained IP packet carrying the original **Identification** field, a **Fragment Offset** measured in 8-byte units, and the **More Fragments (MF)** flag set on every fragment except the last. The destination reassembles by placing each fragment's payload at `offset * 8` in a buffer, stopping when the fragment with `MF=0` arrives. IPv6 took the opposite path — routers **never** fragment; only the source does, via a Fragment extension header, after learning the path MTU from ICMP errors. **Path MTU Discovery (PMTUD)** sends packets with **DF=1**; a too-small router drops them and returns an ICMP "Fragmentation Needed" error carrying the next-hop MTU, so the source shrinks its packets. When a firewall blocks that ICMP, the source never learns and the packet vanishes — the **PMTUD black hole**. RFC 791 defines IPv4 fragmentation; RFC 8201 defines PMTUD for IPv6; RFC 2460 (now 8200) defines the IPv6 Fragment extension header.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 earlier lessons (internetworking, tunneling, IP headers)
**Time:** ~90 minutes

## Learning Objectives

- Decode the three IPv4 fragmentation fields — Identification, MF flag, Fragment Offset (13 bits, units of 8 bytes) — and explain why the offset uses 8-byte granularity.
- Fragment a 1500-byte IP packet for a 576-byte MTU link by hand: compute fragment count, payload sizes, offsets, and MF flags, then verify the byte accounting.
- Explain the reassembly algorithm: in-order placement is not required, a reassembly timer bounds wait time, and loss of one fragment dooms the entire datagram.
- Contrast IPv4 (router fragmentation) with IPv6 (source-only fragmentation via the Fragment extension header) and explain the performance and operational rationale.
- Trace the Path MTU Discovery (PMTUD) loop: DF=1, ICMP "Fragmentation Needed and DF Set", back-off to the advertised MTU; then diagnose the PMTUD black hole when ICMP is filtered.
- Run `code/main.py` to fragment and reassemble synthetic packets, and reproduce the textbook Fig. 5-43 worked example with 10 bytes through an 8-byte and 5-byte MTU.

## The Problem

A site migrates an application server behind a VPN tunnel. The tunnel adds a 56-byte encapsulation header. The LAN MTU is 1500 bytes, so the server happily sends 1500-byte TCP segments. Inside the tunnel the effective MTU is 1444, but the tunnel path also crosses an MPLS core with a 1400-byte MTU. The server sets DF=1 (PMTUD is on by default in modern TCP/IP stacks). The core router that cannot forward the 1500-byte packet generates an ICMP "Fragmentation Needed, Next-Hop MTU = 1400" message and drops the packet — but a stateful firewall in the return path silently drops the ICMP. The server never receives the error, never shrinks its segments, and retransmits full-size packets forever. TCP connections to the server hang at the SYN-ACK or first data segment.

This is a **PMTUD black hole**: fragmentation was moved out of the network to improve router performance, PMTUD was designed to let the source adapt, and a single filtered ICMP breaks the feedback loop. The fix requires understanding the fragmentation fields, the DF bit, the ICMP error, and why "let the router fragment it" is no longer the fallback it was in IPv4. This lesson builds that understanding from the fields up.

## The Concept

Source material: [`chapters/chapter-05-the-network-layer.md`](../../../../chapters/chapter-05-the-network-layer.md) section `5.5.5`. The SVG diagrams the fragmentation of a 1500-byte packet; `code/main.py` is a stdlib-only fragmentation and reassembly simulator you can check against Wireshark.

### Why fragmentation exists

Every network or link has a maximum packet size — driven by hardware (Ethernet frame buffers), protocols (the IP Total Length field is 16 bits, so 65,535 bytes max), OS buffers, standards, or the desire to bound retransmission cost and channel occupancy. Hosts prefer large packets because header overhead is amortized. When a large packet enters a network with a smaller MTU, two strategies exist:

- **Transparent fragmentation** — the entry router splits the packet, the exit router reassembles it; subsequent networks are unaware. Cost: exit router must buffer, routes are constrained, repeated fragment/reassemble cycles.
- **Nontransparent fragmentation** — fragments are never reassembled until the destination host; each fragment is treated as its own packet. IP chose this path because it moves work out of routers.

Neither is free: fragment headers add overhead, and losing one fragment loses the entire datagram (the source retransmits the whole thing, not just the missing piece).

### IPv4 fragmentation fields

The IPv4 header carries three fields that implement fragmentation:

| Field | Bits | Meaning |
|---|---|---|
| Identification | 16 | Same value on every fragment of one datagram; lets the receiver group fragments |
| MF (More Fragments) | 1 | Set to 1 on all fragments except the last; 0 on the last (or on unfragmented packets) |
| Fragment Offset | 13 | Byte offset of this fragment's data in the original datagram, **divided by 8** |

The 8-byte unit is the **elementary fragment unit**: 13 bits × 8 = 65,536 bytes, matching the 16-bit Total Length field's ceiling. The constraint is that every fragment except the last must carry a payload whose length is a multiple of 8, so the offset of the next fragment is integral.

```
IPv4 header (20 bytes) showing fragmentation fields:
+-----+-----+-------+--------+-----------+----------+---+---+
| Ver | IHL | ToS   | Total  | Identif-  | Flags    |Frag| ...
|  4  |  4  | 1 B   | Length | ication   | DF|MF|xx |Off |
|     |     |       | 2 B    |   2 B     |  1 bit ea |13b |
+-----+-----+-------+--------+-----------+----------+---+---+
                                       \___ these three implement fragmentation ___/
```

The **DF (Don't Fragment)** bit is a fourth 1-bit field adjacent to MF. Set to 1, it tells routers "do not fragment — if it does not fit, drop it and tell the source via ICMP." PMTUD uses DF=1 to probe the path.

### A worked example: 1500 → 576 MTU

A 1500-byte IP packet (1480 bytes payload + 20 bytes header) hits a link with MTU 576. Each fragment carries a 20-byte IP header, so the payload per fragment is at most 576 − 20 = 556 bytes, rounded down to a multiple of 8 = 552 bytes.

| Fragment | Payload bytes | Offset (bytes) | Offset field | MF |
|---|---|---|---|---|
| 1 | 552 | 0 | 0 | 1 |
| 2 | 552 | 552 | 69 | 1 |
| 3 | 376 | 1104 | 138 | 0 |

Total payload: 552 + 552 + 376 = 1480 bytes. The offset field stores `byte_offset / 8`. Fragment 3 has MF=0 because it is the last; its payload (376) need not be a multiple of 8. `code/main.py` reproduces this arithmetic.

### Reassembly at the destination

The destination allocates a buffer the size of the original datagram (it learns the total length from the last fragment: `last_offset*8 + last_payload_length`). Each fragment is placed at its offset. Fragments may arrive out of order, duplicates are discarded, and fragments of fragments are handled because the offset is absolute. A **reassembly timer** bounds the wait: if the timer expires before all fragments arrive, the partial datagram is discarded — and because IP provides no retransmission, the entire original packet is lost. The source (via TCP or another transport) must retransmit the whole packet.

### IPv6 fragmentation: source-only, extension header

IPv6 removed all fragmentation fields from the fixed header. Routers **never** fragment IPv6 packets. If a router cannot forward an oversized packet, it drops the packet and sends an ICMPv6 "Packet Too Big" message with the next-hop MTU back to the source. The source then re-fragments using the **Fragment extension header**, which carries the Identification, the Fragment Offset (again in 8-byte units), and an M flag (equivalent to MF):

```
Fragment extension header (8 bytes):
+---------+----+-----+-------------+----------+
|Next Hdr | rs | rs  | Fragment    |Identif-  |
|  1 B    | 1B | 1B  | Offset + M  | ication  |
|         |    |     |   2 B       |   4 B    |
+---------+----+-----+-------------+----------+
```

The minimum MTU every IPv6 link must support is raised to **1280 bytes** (vs IPv4's 576), giving sources a guaranteed floor and reducing the need for fragmentation in the first place.

### Path MTU Discovery and the black hole

PMTUD (RFC 1191 for IPv4, RFC 8201 for IPv6) is the modern mechanism:

1. Source sends a packet sized for the first-hop MTU (e.g. 1500) with **DF=1**.
2. A downstream router whose MTU is smaller drops the packet and returns **ICMP Type 3 Code 4** ("Destination Unreachable — Fragmentation Needed and DF Set") carrying the **next-hop MTU**.
3. Source lowers its packet size to the advertised MTU and retries. Repeat until the packet gets through.

The failure mode: if a firewall between the router and the source filters that ICMP — a common misconfiguration because admins block all ICMP "for security" — the source never receives the error, keeps sending full-size DF=1 packets, and they keep getting dropped. Connections stall. This is the **PMTUD black hole**, the single most common cause of "large packets fail, small packets work" symptoms on the modern Internet. Detection: `ping -M do -s 1472` fails but `ping -s 1400` works. Fix: allow ICMP Type 3 Code 4, or enable TCP MSS clamping on the tunnel.

## Build It

`code/main.py` is a stdlib-only simulator with three parts tied to the concept:

1. **Fragmentation engine** — `fragment(packet_size, mtu, header_size)` splits a datagram into fragments on 8-byte boundaries, computing each fragment's offset field and MF flag exactly as IPv4 does.
2. **Reassembly engine** — `reassemble(fragments)` places fragments at their byte offset, detects completeness via MF=0 and contiguous coverage, and handles out-of-order and duplicate fragments.
3. **PMTUD simulator** — `path_mtu_discover(path_mtu_list)` probes a path by sending DF=1 packets and backing off to the smallest advertised MTU.

Run `python3 code/main.py` to see the 1500→576 example, the textbook Fig. 5-43 (10 bytes → 8-byte MTU → 5-byte MTU), and a PMTUD trace through a three-hop path. Change the MTU and packet sizes to watch the fragment counts and offsets shift.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute fragment offsets | Fragment table with payload, byte offset, offset field, MF | Offset field = byte_offset / 8; all but last payload is a multiple of 8 |
| Verify reassembly | Byte buffer filled contiguously from offset 0 | MF=0 fragment present and no gaps before it |
| Diagnose PMTUD black hole | `ping -M do -s 1472` fails, `-s 1400` works | ICMP Type 3 Code 4 is being filtered; fix firewall or enable MSS clamping |
| Distinguish IPv4 vs IPv6 | Who fragments and where | IPv4: any router may fragment. IPv6: only the source, via Fragment extension header |
| Spot the doomed datagram | Reassembly timer + fragment loss | One missing fragment ⇒ entire datagram discarded and retransmitted by the transport layer |

Wireshark filters: `ip.flags.mf == 1`, `ip.fragment_offset > 0`, `icmp.type == 3 && icmp.code == 4`.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **fragmentation calculator runbook**: the 8-byte-unit rule, the offset-field formula, the MF flag table, and a worked 1500→576 example with byte accounting.
- A **PMTUD black-hole diagnostic script**: `ping -M do -s {1472,1452,1400,1380,...}` sweep that finds the working MTU and reports the likely filtered ICMP.
- The **fragmentation/reassembly simulator** (`code/main.py`) wired to your own captures or trace data.

Start from `outputs/prompt-packet-fragmentation.md`.

## Exercises

1. A 4000-byte IP datagram (3980 payload + 20 header) crosses a link with MTU 1500. Compute the number of fragments, each fragment's payload size, byte offset, offset field value, and MF flag. Verify the total payload equals 3980.
2. The textbook Fig. 5-43 starts with 10 data bytes in packet 27, fragments through an 8-byte-MTU network, then a 5-byte-MTU network. Trace the three fragment tables and confirm the offset and MF values match the figure.
3. A router receives a packet with DF=1 that is 100 bytes too large for the next hop. What ICMP message does it send, what field in that message tells the source the correct size, and what does the source do? What breaks if that ICMP is filtered?
4. An IPv6 host sends a 2000-byte packet toward a path with a 1280-byte minimum link. Describe the sequence of ICMPv6 "Packet Too Big" messages and the final packet size the source uses. Why can the router not fragment instead?
5. You are debugging a connection that hangs transferring large files but works for small ones. Write the exact `ping` commands to confirm a PMTUD black hole and the one firewall rule that fixes it.
6. Run `code/main.py` with `fragment(10000, 1492, 20)`. How many fragments? What is the offset field of the last fragment? Change the MTU to 576 and recompute.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| MTU | "max packet size" | Maximum payload bytes a link will carry in one frame (Ethernet: 1500); bounds the IP datagram that crosses that link |
| Fragment offset | "where the piece goes" | 13-bit field = byte offset / 8; the divisor 8 is the elementary fragment unit that keeps offsets integral |
| MF flag | "more coming" | More Fragments: 1 on all fragments except the last; the receiver uses it to detect the final fragment and learn total length |
| DF bit | "don't split it" | Don't Fragment: 1 tells routers to drop (not fragment) oversized packets and signal via ICMP — the probe mechanism for PMTUD |
| Identification | "fragment ID" | 16-bit value shared by all fragments of one datagram so the receiver groups them correctly |
| Reassembly timer | "the deadline" | Per-destination timer; if it expires before all fragments arrive, the partial datagram is discarded — one lost fragment dooms the whole packet |
| PMTUD | "path MTU discovery" | Source sends DF=1, routers reply with next-hop MTU via ICMP 3/4, source backs off until the packet fits the entire path |
| PMTUD black hole | "big packets die" | ICMP Type 3 Code 4 filtered by a firewall; source never learns the MTU and keeps sending oversize DF=1 packets that are silently dropped |
| IPv6 Fragment header | "the IPv6 way" | Extension header carrying Identification + Offset + M flag; only the source fragments, never routers, after learning the MTU via ICMPv6 Packet Too Big |

## Further Reading

- **RFC 791** — Internet Protocol, DARPA Internet Program Protocol Specification (IPv4 fragmentation fields, reassembly algorithm).
- **RFC 1191** — Path MTU Discovery (the IPv4 PMTUD mechanism, DF-bit probing).
- **RFC 8201** — Path MTU Discovery for IP version 6 (the IPv6 PMTUD update).
- **RFC 8200** — Internet Protocol, Version 6 (IPv6) Specification (successor to RFC 2460; Fragment extension header).
- Kent & Mogul (1987), "Fragmentation Considered Harmful," *SIGCOMM CCR* — the argument that moved fragmentation out of routers.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.5.5 "Fragmentation" — the source chapter and worked Fig. 5-43.