# IPv6 Extension Header Fragmentation Firewall Drop

> A user on a dual-stack Linux host tries to `scp big.iso user@2001:db8::1:` and the transfer stalls for exactly 30 seconds, then errors out. The same user can `scp` to a v4 host (`203.0.113.10`) without issue. The server is dual-stack, accepts both `ssh` on `22` and on `[2001:db8::1]:22`, and the user is on a `2001:db8:beef::/64` link. A `tcpdump` shows the client sends an IPv6 packet to `[2001:db8::1]:22`, the packet is 1,484 bytes (the path MTU is 1,500 minus 16 for an additional IPv6 header that should not be there), and the server's conntrack shows the connection. The packet vanishes after the user's edge router. The user does `tracepath6 2001:db8::1` and gets `pmtu 1280` — the IPv6 minimum MTU. The cause: the edge router has a firewall rule `ip6tables -A FORWARD -m exthdr --hdr frag -j DROP` (or `nft add rule ip6 filter forward fraghdr exists counter drop`). The user's TCP stack is sending IPv6 fragments (Fragment Header, RFC 8200 §4.5) for the oversized segment, and the firewall is dropping all packets with the Fragment extension header. The fix is to either (a) remove the rule (fragments are legal in IPv6, RFC 8200 §4.5), (b) lower the MSS on the path so no packet exceeds the path MTU and fragments are never needed, or (c) allow the fragment header through with stateful tracking. The reason fragments are dropped by default in many firewalls is the historical CVE-2003-0001 (a Windows XP IPv6 fragment reassembly bug), but legitimate uses (path MTU smaller than the link, jumbo frames) are blocked by the same rule.

**Type:** Lab
**Languages:** Python, shell, scapy, ip6tables
**Prerequisites:** Phase 09 IPv6 header and extension headers (RFC 8200), Phase 08 PMTUD for IPv6 (RFC 8201)
**Time:** ~95 minutes

## Learning Objectives

- Diagnose an IPv6 connection that stalls because the path has a smaller MTU and the kernel is sending Fragment extension headers that the firewall drops: read `tcpdump -i eth0 -n ip6`, identify the Fragment Header (Next Header = 44), and confirm the firewall rule.
- List the IPv6 extension headers in the canonical order (RFC 8200 §4.1): Hop-by-Hop (0), Destination (60), Routing (43), Fragment (44), Authentication (51), Encapsulating Security Payload (50). Note that fragmentation comes *after* Routing but *before* AH/ESP.
- Distinguish three failure modes: (a) fragment header drop (firewall rule, no reassembly possible), (b) fragment header overlap (security issue, RFC 8200 §4.5 forbids overlapping fragments), (c) atomic fragment (RFC 6946, used for path MTU probing).
- Use `ip6tables -L -n -v` and `nft list ruleset` to read the firewall rule and identify the fragment-drop policy.
- Compute the right MTU for a path that includes a tunnel: outer 1,500 minus tunnel overhead minus the IPv6 Fragment Header (8 bytes), minus the inner IPv6 header (40 bytes).
- Build a Python script that constructs a synthetic IPv6 packet with a Fragment extension header, computes the wire format, and prints the expected verdict.

## The Problem

The on-call SRE for a SaaS company that runs dual-stack services gets a ticket from a customer: "SFTP works for small files, fails for large files, only over IPv6." The customer is on a corporate network that has deployed IPv6 in the past 18 months. The customer's IT team added a "security" rule to their IPv6 firewall: `ip6tables -A FORWARD -m exthdr --hdr frag -j DROP`. The rule was meant to drop malicious fragments (CVE-2003-0001, an old Windows XP bug), but it has the side effect of dropping all legitimate fragments.

The user's connection stalls at the first segment larger than the path MTU. The path MTU on the user's link is 1,500 (Ethernet), but the user's tunnel through a corporate VPN has an MTU of 1,420, and the path MTU that the kernel has discovered is 1,280 (the IPv6 minimum, because the path MTU discovery is failing — the ICMPv6 Type 2 "Packet Too Big" message is also being filtered). The user's TCP stack sends a 1,280-byte segment (the IPv6 minimum MSS = 1,280 - 40 - 20 = 1,220). The first few segments make it. Then a retransmit with slightly different timing. The transfer stalls.

The diagnostic move is `tcpdump -i eth0 -n ip6 host 2001:db8::1`. The output shows the client sending an IPv6 packet with the Fragment extension header (Next Header = 44 in the inner IPv6 header, or 6 for TCP at the end of the chain). The packet is 1,484 bytes. The server's edge receives it, but the upstream firewall has the `-m exthdr --hdr frag` rule and drops the packet. The retransmit timer fires on the client, the same packet is sent, dropped again. After 15 retransmits, the connection is given up.

The fix is to remove the firewall rule, or to use a stateful firewall that tracks fragments and reassembles them. `ip6tables -D FORWARD -m exthdr --hdr frag -j DROP` (or the corresponding `nft delete rule`) restores connectivity. The right long-term fix is to lower the MSS on the tunnel so the kernel never sends a segment larger than the path MTU, eliminating the need for fragments.

## The Concept

### The IPv6 extension header chain

Unlike IPv4, which uses a fixed 20-byte header (plus options) and a single fragment-offset field, IPv6 has a chain of extension headers between the main IPv6 header and the upper-layer payload. The first 8 bits of the main IPv6 header carry the `Next Header` field; if it is not 6 (TCP), 17 (UDP), or 58 (ICMPv6), the bytes following the main header are an extension header. Each extension header has a `Next Header` field pointing to the next header, until the chain terminates at the upper-layer protocol.

The canonical order (RFC 8200 §4.1):

| Order | Header | Next Header value | Notes |
|---|---|---|---|
| 1 | Hop-by-Hop Options | 0 | Must be first if present; examined by every hop |
| 2 | Destination Options | 60 | Examined by the destination and intermediate routers specified in Routing |
| 3 | Routing | 43 | Source routing (deprecated in practice) |
| 4 | Fragment | 44 | RFC 8200 §4.5: used for fragmentation |
| 5 | Authentication (AH) | 51 | IPsec, RFC 4302 |
| 6 | Encapsulating Security Payload (ESP) | 50 | IPsec, RFC 4303 |

The Fragment extension header is 8 bytes: 1 byte Next Header, 1 byte Reserved, 13-bit Fragment Offset, 1 bit M flag (1 = more fragments, 0 = last fragment), and a 32-bit Identification. The Identification is generated by the source and must be unique for fragments of the same packet within the source's lifetime (RFC 8200 §4.5).

### Why fragments are dropped

The history: in 2003, a Windows XP IPv6 stack had a buffer overflow in the fragment reassembly code (CVE-2003-0001). Firewalls added rules to drop fragmented IPv6 packets to protect potentially-vulnerable hosts. The rules persist today, even though modern IPv6 stacks have been safe for two decades. The legitimate cost of these rules: every IPv6 connection that needs to fragment stalls.

The standard "atomic fragment" mechanism (RFC 6946) was introduced to let a sender send a non-fragmented packet whose Fragment extension header indicates offset 0 and M=0. The packet is reassembled without any further fragments. This is used by some PMTUD implementations to probe the path MTU without actually fragmenting. Some firewalls that drop fragments allow atomic fragments through; many do not.

### How the kernel decides to fragment

IPv6's PMTUD (RFC 8201) is the same algorithm as IPv4's: the sender sets a packet with no Fragment header and a payload of the path MTU, and if the path rejects it with an ICMPv6 Type 2 "Packet Too Big" message, the sender lowers the path MTU. The Fragment header is only used when the upper-layer protocol cannot be segmented at a smaller size — i.e., when the kernel *must* send a packet larger than the path MTU and cannot use PMTUD. With a correct PMTUD, fragments should be rare.

The user-visible failure happens when PMTUD is broken (the ICMPv6 Type 2 message is filtered) and the kernel falls back to fragmentation. The fix is to repair PMTUD, not to drop the fragments.

### `ip6tables` and the `-m exthdr` match

The Linux `ip6tables` has an `exthdr` module that can match specific extension headers:

```
ip6tables -A FORWARD -m exthdr --hdr frag -j DROP
ip6tables -A FORWARD -m exthdr --hdr ah -j DROP
ip6tables -A FORWARD -m exthdr --hdr esp -j ACCEPT
```

The `nftables` equivalent is `nft add rule ip6 filter forward fraghdr exists counter drop`. To diagnose, list the ruleset: `nft list ruleset` or `ip6tables-save`.

### The right fix: MSS clamping

The robust fix is to clamp the MSS on the path so the kernel never sends a segment larger than the path MTU. The `tc` filter or `nft` rule rewrites the TCP MSS option in the SYN to `path_MTU - 40 - 8 = path_MTU - 48` (40 for IPv6 header, 8 for the worst-case fragment header). The `iptables` rule:

```
ip6tables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
  -j TCPMSS --clamp-mss-to-pmtu
```

The `nft` equivalent uses the `tcp mss` set. With MSS clamping, the kernel never sends a segment that would require fragmentation, and the firewall rule becomes a non-issue.

### How the simulator models this

`code/main.py` constructs a synthetic IPv6 packet with a Fragment extension header, computes the wire format, and prints the verdict for the four scenarios: `--scenario fragment_drop` (firewall blocks fragments), `--scenario pmfud_ok` (PMTUD works, no fragments), `--scenario atomic` (RFC 6946 atomic fragment), `--scenario mss_clamp` (MSS clamping avoids fragments).

## Build It

1. **Set up the topology.** Two namespaces connected by a veth pair, one namespace has the firewall rule `ip6tables -A FORWARD -m exthdr --hdr frag -j DROP`.
2. **Reproduce the failure.** Run `scp` from a v6 host to a v6 server across the firewall, with a file larger than the path MTU. Confirm the stall.
3. **Capture the wire.** `tcpdump -i any -n ip6` and identify the Fragment Header (Next Header = 44).
4. **Apply the fix.** `ip6tables -D FORWARD -m exthdr --hdr frag -j DROP`, or add the MSS-clamp rule, and re-test.
5. **Run the simulator.** `python3 code/main.py --scenario fragment_drop` should print the matching verdict.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| List IPv6 rules | `ip6tables-save` or `nft list ruleset` | Identify the `frag` drop rule |
| Confirm fragments on wire | `tcpdump -i eth0 -n ip6` and `ip6[6] == 44` | See the Fragment extension header |
| Confirm path MTU | `tracepath6 2001:db8::1` | Reports the path MTU; ideally matches the link MTU |
| Confirm ICMPv6 Type 2 | `tcpdump -i eth0 -n 'ip6[6] == 58 && ip6[48] == 2'` | See the Packet Too Big message |
| Confirm MSS clamp | `nft list ruleset` shows the tcp mss rule | MSS is limited; no fragments needed |

## Ship It

Produce one reusable artifact under `outputs/`:

- An **IPv6 fragment firewall runbook** with the diagnostic commands, the rule explanation, and the MSS-clamp fix.
- A **before/after capture** of the same `scp` flow, showing fragments in the trace before the fix and a clean PMTU path after.

Start from `outputs/prompt-ipv6-extension-header-fragment-firewall-drop.md`.

## Exercises

1. The path MTU is 1,280. The inner TCP MSS is 1,220. The user wants to send a 1,500-byte segment. What happens, and which RFC applies?
2. The Fragment Header is 8 bytes. Compute the effective MSS for a tunnel that has 50 bytes of overhead (VXLAN) and an outer MTU of 1,500.
3. The firewall rule is `ip6tables -A FORWARD -m exthdr --hdr ah -j DROP`. What does this block, and is it a sensible security policy?
4. An ICMPv6 Type 2 message is filtered at the egress firewall. What is the consequence for PMTUD, and which layer of the IPv6 stack is affected?
5. RFC 6946 defines the "atomic fragment" — a Fragment Header with offset 0 and M=0. Why does the kernel send one, and does a firewall that drops fragments drop it?
6. The IPv6 header's Next Header field is 8 bits and is followed by 8 bits of Hop Limit in the main header. If Next Header is 44 (Fragment), the bytes immediately after the main header are the Fragment Header. Compute the offset of the Identification field within the Fragment Header.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| IPv6 extension header | "The chain" | A variable-length chain of headers between the main IPv6 header and the upper-layer payload (RFC 8200 §4) |
| Fragment Header | "IPv6 fragment" | RFC 8200 §4.5: 8-byte header with Next Header, Reserved, Fragment Offset (13 bits), M flag, Identification (32 bits) |
| Atomic fragment | "RFC 6946 fragment" | A Fragment Header with offset 0 and M=0; non-fragmented payload used for PMTUD probing |
| `-m exthdr --hdr frag` | "Drop fragments" | `ip6tables` match for packets with the Fragment extension header |
| Path MTU | "pmtu" | The smallest MTU on the path; for IPv6, the minimum is 1,280 bytes (RFC 8200) |
| ICMPv6 Type 2 | "Packet Too Big" | The IPv6 equivalent of ICMP Type 3 Code 4 (RFC 4443 §3.2) |
| MSS clamp | "Cap the segment" | `ip6tables -t mangle -j TCPMSS --clamp-mss-to-pmtu`; limits segments to path_MTU - 40 - 8 |
| Next Header = 44 | "Fragment" | The IPv6 protocol number for the Fragment extension header |

## Further Reading

- RFC 8200 — Internet Protocol, Version 6 (IPv6) Specification (extension header chain, Fragment Header format)
- RFC 8201 — Path MTU Discovery for IPv6
- RFC 6946 — Processing of IPv6 "Atomic" Fragments
- RFC 4443 — Internet Control Message Protocol for IPv6 (ICMPv6)
- RFC 4302 / RFC 4303 — IPsec AH / ESP (extension headers 51 / 50)
- `ip6tables(8)`, `nft(8)`, `tracepath(8)` man pages
- `tcpdump(8)` — IPv6 extension header byte-offset filter syntax
- CVE-2003-0001 — the historical motivation for fragment-drop firewall rules
