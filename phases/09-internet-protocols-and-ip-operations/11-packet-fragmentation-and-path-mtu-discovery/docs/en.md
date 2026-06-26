# Packet Fragmentation and Path MTU Discovery

> IPv4 fragmentation is a forty-year-old mechanism that lets any host split a single IP datagram into multiple link-layer frames when the path's smallest Maximum Transmission Unit (MTU) is smaller than the datagram. The IPv4 header carries a 16-bit Identification field (replicated in every fragment), three 1-bit flags (Reserved, Don't Fragment, More Fragments), and a 13-bit Fragment Offset measured in 8-byte units so a 4000-byte payload crossing a 1500-byte Ethernet link becomes three pieces: 1480/1480/1040 bytes at offsets 0/185/370. Reassembly at the destination trusts the Identification field and the 8-byte alignment, not the order of arrival. Path MTU Discovery (PMTUD, RFC 1191 for IPv4, RFC 8201 for IPv6) is the modern alternative: the source sets the DF bit, sends a packet, listens for ICMP Type 3 Code 4 (Fragmentation Needed) / ICMPv6 Type 2 (Packet Too Big) which carries the next-hop MTU in the trailer, shrinks its estimate, and re-probes until the path is silent. IPv6 forbids routers from fragmenting (RFC 8200); the source must do it, and only through a Fragment extension header. This lesson walks the bit math, builds an IPv4 fragmenter and a PMTUD probe walker, and contrasts the IPv4 and IPv6 stories.

**Type:** Build
**Languages:** Python
**Prerequisites:** IPv4 header format, IPv6 header format, ICMP basics (Phase 9), 8-bit / 16-bit unsigned arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Split a payload into IPv4 fragments with correct 13-bit Fragment Offset (in 8-byte units), 16-bit Identification, and the More Fragments (MF) bit set on every piece except the last.
- Compute reassembly length from the last fragment (MF=0) and prove that `payload == reassemble(fragments)` for any order of arrival.
- Reconstruct a packet's path MTU by walking a topology, observing ICMP "Fragmentation Needed" / ICMPv6 "Packet Too Big" feedback, and shrinking the estimate.
- Explain why IPv6 routers never fragment: the IPv6 header dropped the Fragment Offset, Identification, and Flags fields to keep the fixed 40-byte header small.
- Encode the IPv6 Fragment extension header (8 bytes: NextHeader, Reserved, Offset/M/2-bit-Res, Identification) used when an IPv6 source chooses to fragment.

## The Problem

A research site has a 4000-byte UDP datagram carrying seismic data. The host sends it from a Linux box onto an Ethernet network, the first router forwards it, the second router sits behind a PPPoE link with an MTU of 1492, and the packet disappears. The user sees no ICMP back, the kernel logs "message too long" and gives up, and the application never knows why. The diagnosis is hidden in three places: the IPv4 header's DF (Don't Fragment) bit, the 8-byte fragment-offset unit, and an ICMP message the upstream ISP filters at its edge.

If the host had set DF, the second router would have replied with an ICMP Type 3 Code 4 carrying the next-hop MTU (1492) in the trailer's unused 16 bits. The host would have lowered its estimate to 1492, re-sent, hit the next link (a tunnel with MTU 1476), and converged. Without DF, IPv4 fragmentation would have chopped the datagram into 1500-byte pieces and the second router would have re-fragmented to fit PPPoE — but with UDP, the loss of any fragment is fatal, and the path that just worked is suddenly mysterious. PMTUD is what you actually want.

## The Concept

Fragmentation and PMTUD are two sides of one question: when a packet is too big for a link, who chops it, who reassembles it, and how does anyone learn the smallest MTU on the path?

### IPv4 fragmentation: the 16-bit ID, the 13-bit offset, and the MF bit

The IPv4 header (RFC 791) sets aside three fields for fragmentation:

| Field | Width | Purpose |
|---|---|---|
| Identification | 16 bits | Same value in every fragment of one datagram; the receiver groups by it |
| Flags | 3 bits | bit 0 reserved (must be 0), bit 1 = DF (Don't Fragment), bit 2 = MF (More Fragments) |
| Fragment Offset | 13 bits | Position of this fragment's data, measured in 8-byte units from the start of the original payload |

The 8-byte unit is the load-bearing trick: a 13-bit offset can address `2^13 * 8 = 65536` bytes, the full IP payload range. The MF bit is 1 on every fragment except the last, where it is 0; the offset plus the MF bit let the receiver know the datagram is complete.

### MTU, total length, and the per-fragment math

The Maximum Transmission Unit is the largest link-layer frame payload, and it includes the IP header. A 1500-byte Ethernet MTU means 1480 bytes of IP data per fragment (after the 20-byte IPv4 header). A 4000-byte payload at MTU 1500 splits as:

| Fragment | Data bytes | Offset (8-byte units) | Offset * 8 | MF bit | Total Length |
|---|---|---|---|---|---|
| 1 | 1480 | 185 | 0 | 1 | 1500 |
| 2 | 1480 | 185 | 1480 | 1 | 1500 |
| 3 | 1040 | 130 | 2960 | 0 | 1060 |

Sum: 1480 + 1480 + 1040 = 4000 bytes. Offsets 185 + 185 + 130 = 500 units = 4000 / 8. Last fragment's `(offset * 8) + data_length == original payload length`. The MF bit is 0 only on the last.

### Reassembly: trust the ID, not the order

The receiver buffers fragments until one has MF=0; that fragment's `(offset * 8) + data_length` is the full payload length. Each fragment lands in `output[offset*8 : offset*8 + len(data)]` regardless of arrival order. Out-of-order arrival, duplicates, and partial overlap are all handled by the same copy-into-buffer logic; the ID is the datagram's name, the offset is the slot, the MF bit is the terminator. If the timer expires (typically 60 seconds) the datagram is dropped.

### Path MTU Discovery (PMTUD, RFC 1191)

The DF bit turns fragmentation from an automatic mechanism into a probe:

1. Source starts with an estimate of the local MTU (e.g. 1500 for Ethernet).
2. Source sends a packet with DF=1, sized to the estimate.
3. If a router cannot forward it, the router drops the packet and sends back ICMP Type 3 Code 4 (Fragmentation Needed) with the router's outbound MTU in the last 4 bytes of the ICMP payload (the IP header + 8 bytes of original datagram).
4. Source reads the next-hop MTU, lowers its estimate, and re-sends.
5. When no router complains, the estimate is the path MTU.

PMTUD is a classic slow-start loop. RFC 1191 also defines the "plateau" values — MTUs that must always succeed without ICMP (1500, 1492, 1480, 1006, 576, etc.) — so a host converges even when every router's ICMP is filtered.

### IPv6: routers never fragment

RFC 8200 (the IPv6 specification) deletes the Fragment Offset, Identification, and Flags fields from the fixed 40-byte IPv6 header. Routers facing a too-big packet drop it and reply with ICMPv6 Type 2 (Packet Too Big) carrying the next-hop MTU. The source, if it cares to send large packets, performs fragmentation by prepending a Fragment extension header (8 bytes: NextHeader, Reserved, Offset/M/2-bit Res, Identification). There is no DF bit. The Offset field is in 8-byte units exactly like IPv4. Each fragment is a full IPv6 datagram with its own header chain.

### Why fragmentation is fragile

UDP does not retransmit, so a single lost fragment is fatal: the receiver never gets the MF=0 terminator and discards everything. TCP detects the missing bytes from acknowledgements and retransmits, but the PMTUD failure mode is famous: a router on the path silently filters ICMP Type 3, the host's estimate stays too large, and a connection eventually black-holes for sends over the path MTU. The fix is PMTUD black-hole detection (RFC 2923 / RFC 4821 Packetization Layer Path MTU Discovery), where the source periodically drops the estimate to a small value to break out of the loop.

## Build It

`code/main.py` is a stdlib-only Python module that exercises the three pieces of the lesson.

1. **IPv4 fragmenter** — `fragment_datagram(payload, mtu, identification)` returns a list of `Fragment` dataclasses. The math rounds the per-fragment data length down to a multiple of 8 (except the last) so the 13-bit offset can address every byte. Run `demo_fragmentation` to see a 4000-byte payload split at MTU 1500.
2. **Reassembler** — `reassemble(fragments)` puts the pieces back. Try passing them in reverse order to prove the receiver does not care about arrival sequence.
3. **PMTUD walker** — `probe_path(path, payload_size, start_estimate)` simulates a 3-hop topology with mixed link MTUs, sending probes, getting back ICMP feedback, and shrinking the estimate. `demo_pmtud` shows the typical 1500 -> 1492 -> 1476 convergence.
4. **IPv6 Fragment header** — `IPv6FragmentHeader` is a 4-field dataclass with a `pack()` method that emits the 8-byte header in network byte order. `demo_ipv6_fragment_header` shows the wire format.

Run `python3 code/main.py` for all three demos. Try changing `start_estimate=4000` to `1500` to see PMTUD converge in fewer steps, or extend the topology to a 5-hop chain to see more ICMP traffic.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute fragment offsets | payload / 8 alignment | All non-final fragments are offset multiples of 8; final is 0..7 mod 8 |
| Spot a missing fragment | Wireshark capture, no MF=0 | Receiver drops the whole datagram after timeout; TCP sees a hole |
| Reassemble out of order | `reassemble(shuffled)` | Output equals the original payload exactly |
| Walk a PMTUD path | `probe_path` log | Estimate monotonically shrinks; final value equals min(link.mtu) |
| Decode ICMP feedback | ICMP Type 3 Code 4 (IPv4) / Type 2 (IPv6) | You read next-hop MTU from the trailing 4 bytes and use it |
| Encode IPv6 Fragment header | 8-byte `pack` output | Hex matches NextHeader | Reserved | Offset/M/Res | Identification |

CLI hints: `ping -M do -s 1472 host` forces DF on Linux and prints the path MTU. `ip route get <ip>` shows the cached PMTU. `tcpdump -vv -i eth0 'icmp'` exposes Type 3 Code 4 traffic during PMTUD.

## Ship It

Produce one reusable artifact under `outputs/`:

- An **IPv4 fragmentation worksheet** with a worked 4000-byte example, the ID/Offset/MF table, and the reassembly byte-budget.
- A **PMTUD runbook** with the RFC 1191 plateau values, the ICMP Type/Code matrix for IPv4 and IPv6, and the standard "DF + shrink" loop.
- The **fragmenter and PMTUD walker** (`code/main.py`) extended with a `force_blackhole=True` option that simulates an upstream router that filters ICMP and demonstrates RFC 4821 PLPMTUD recovery.

Start from `outputs/prompt-packet-fragmentation-and-path-mtu-discovery.md`.

## Exercises

1. Split a 9000-byte payload at MTU 1500. How many fragments, what are the offsets, and what is the offset of the last fragment? Now split the same payload at MTU 9000 (jumbo). How many fragments?
2. A packet with Identification 0xBEEF arrives in three fragments at offsets 0, 185, and 370. The first carries MF=1 and 1480 bytes, the second MF=1 and 1480 bytes, the third MF=0 and 1040 bytes. What is the original payload length, and what offset/MF would a 4th fragment at offset 555 carry?
3. You start PMTUD with estimate 1500 on a path whose MTUs are 1500, 1492, 1476. List the ICMP feedback messages you receive and the estimate after each. What is the final path MTU?
4. A user reports that `scp` of a large file hangs at exactly 1464 bytes per packet. What PMTUD failure is most likely, and what is the minimum and maximum estimate that would let the transfer complete?
5. The IPv4 Flags field is 3 bits wide but only 2 are defined. The reserved bit must be 0 today but was set in early implementations. What does a modern router do with a non-zero reserved bit, and what does RFC 791 say?
6. Modify `code/main.py` to add an `is_ipv4_fragmentable(mtu, df_bit)` helper that returns False if the packet must be fragmented but DF=1 is set. Use it to test RFC 1191 compliance for a list of probe sizes.

## Key Terms

| Term | Common Saying | Actual Meaning |
|---|---|---|
| MTU | "frame size" | Largest IP packet a link can carry; Ethernet default is 1500, PPPoE 1492, tunnel 1476 |
| Fragment | "a piece of a packet" | A standalone IP datagram carrying a slice of the original payload, identified by the 16-bit ID |
| Identification | "the packet name" | 16-bit value in the IPv4 header; the receiver groups all fragments with the same ID into one reassembly buffer |
| Fragment Offset | "where this piece goes" | 13-bit position in 8-byte units; 0 to 65528 in 8-byte steps |
| MF bit | "more coming" | IPv4 flag bit 2; 1 on every fragment except the last, which carries MF=0 |
| DF bit | "don't fragment" | IPv4 flag bit 1; with DF=1, routers reply ICMP Type 3 Code 4 instead of fragmenting |
| PMTUD | "find the smallest MTU" | Iterative DF=1 probe with ICMP feedback; the path MTU is the smallest MTU the source can use without hearing back |
| ICMP Type 3 Code 4 | "Fragmentation Needed" | RFC 792 message; payload carries the original IP header plus 8 bytes plus the next-hop MTU in the last 4 bytes |
| ICMPv6 Type 2 | "Packet Too Big" | RFC 4443 message; the MTU of the outgoing interface is the first 4 bytes of the payload |
| Path MTU black hole | "PMTUD hangs" | When a router on the path filters ICMP Type 3 Code 4; the source never learns and never shrinks |

## Further Reading

- **RFC 791** — Internet Protocol (IPv4), section 3.1 "Fragmentation and Reassembly" and section 3.2 "Reassembly."
- **RFC 1191** — Path MTU Discovery (IPv4), with the standard plateau table.
- **RFC 8200** — Internet Protocol, Version 6 (IPv6) Specification, section 4.5 "Fragment Header."
- **RFC 8201** — Path MTU Discovery for IPv6.
- **RFC 4443** — ICMPv6 for IPv6, Type 2 Packet Too Big.
- **RFC 4821** — Packetization Layer Path MTU Discovery (PLPMTUD), the modern robust alternative to classic PMTUD.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), section 5.5.4 "Fragmentation."
- Stevens, *TCP/IP Illustrated, Volume 1* (2nd ed.), chapters 11 and 22 — IP fragmentation and PMTUD in practice.
