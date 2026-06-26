# Internet Control Protocols to Label Switching and MPLS

> IP only moves datagrams; the Internet needs companion control protocols to report errors, map addresses, configure hosts, and, in carrier backbones, to short-circuit per-hop longest-prefix lookup with labels. **ICMP** (RFC 792) rides inside IP (protocol 1) and carries about a dozen message types — `DESTINATION UNREACHABLE` (type 3), `TIME EXCEEDED` (type 11, the engine of traceroute), `ECHO REQUEST/REPLY` (types 8/0, the engine of ping), `REDIRECT` (type 5), `PARAMETER PROBLEM` (type 12). **ARP** (RFC 826) resolves a 32-bit IPv4 address to a 48-bit Ethernet MAC by broadcasting on the LAN and caching the reply; IPv6 replaces it with NDP (RFC 4861). **DHCP** (RFC 2131) leases an IP address plus mask, default gateway, and DNS servers using a four-way `DISCOVER → OFFER → REQUEST → ACK` exchange keyed on the client's Ethernet address, with lease times that prevent address leakage. **MPLS** (RFC 3031) inserts a 4-byte "shim" header between PPP (or Ethernet) and IP — a 20-bit Label, 3-bit Traffic Class, 1-bit S (bottom-of-stack), 8-bit TTL — so a Label Switched Router forwards by exact table index instead of longest-prefix match, turning IP into a 2.5-layer virtual-circuit overlay that is perilously close to circuit switching. The observable evidence lives in well-defined fields: ICMP type/code octets, ARP `opcode = 1` (request) or `2` (reply), DHCP option 53 (`53`=DHCP message type), and the MPLS label stack that a Wireshark `mpls` filter exposes. Failure modes are equally concrete: a low-TTL ICMP `TIME EXCEEDED` reveals a routing loop; a missing ARP reply is silent broadcast delivery; a lapsed DHCP lease drops a host off the network mid-session.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Phase 9 lessons 01-03 (IPv4 header, IP addresses, IPv6)
**Time:** ~90 minutes

## Learning Objectives

- Name the principal ICMP message types and their numeric codes, and predict which one a router emits for each of four failure scenarios (unreachable destination, looped packet, illegal header, liveness check).
- Walk an ARP exchange step by step on a multi-network diagram — broadcast request, unicast reply, cache insertion, gratuitous ARP, proxy ARP — and state which addresses change and which stay constant across router boundaries.
- Trace the DORA DHCP sequence (`DISCOVER/OFFER/REQUEST/ACK`), explain why it keys on the Ethernet address, and justify lease renewal timing using the T1 (50%) and T2 (87.5%) thresholds from RFC 2131.
- Decode the 4-byte MPLS shim by field (Label, TC, S, TTL), describe push/swap/pop operations at LSRs, and explain why it is called a "layer 2.5" protocol.
- Distinguish `forwarding` (longest-prefix-match on IP destination) from `switching` (exact label index into a forwarding table) and explain why MPLS gained fast lookup, traffic engineering, and FEC aggregation.

## The Problem

A user reports three unrelated symptoms that are really one problem: control-plane plumbing. First, `ping` to a server works but `traceroute` stops printing routers after hop 6 — the path goes dark for three hops, then resumes. Second, a freshly imaged laptop on a VLAN fails to reach anything even though the NIC link is up; an `ipconfig`-equivalent shows no address at boot. Third, a carrier's transit LED shows steady traffic but `tcpdump` on the edge router shows no IP packets at all, only frames starting with `88 47` followed by 4 bytes that are not protocol 4 or 6.

All three symptoms point at the Internet's control protocols: ICMP (and its repurposed `TIME EXCEEDED`), DHCP (which has not handed out a lease yet), and MPLS (the `0x8847` Ethertype on Ethernet, followed by a 4-byte shim that hides the IP header from naive `tcpdump` filters). The engineer who only knows "IP and TCP" cannot diagnose any of these. The ICMP engineer needs to know that a router drops a packet at TTL 0 and emits a `TIME EXCEEDED` on the return path — and that if a middle hop is silently dropping ICMP echo requests, `traceroute` prints asterisks even though the data path works fine. The DHCP engineer needs to recognize the DHCP `DISCOVER` broadcast and the lease-timer arithmetic that determines how long the host can keep its address. The MPLS engineer needs to know that the 4-byte shim replaces longest-prefix lookup with exact-match label lookup and that the S-bit tells the egress LSR when the label stack is empty and IP forwarding resumes.

## The Concept

Source material: [`chapters/chapter-05-the-network-layer.md`](../../../../chapters/chapter-05-the-network-layer.md), sections 5.6.4 (Internet Control Protocols) and 5.6.5 (Label Switching and MPLS). [`code/main.py`](../code/main.py) encodes/decodes ICMP messages and simulates an MPLS label stack across a three-LSR path; the SVG diagrams ICMP and label-swapping side by side.

### ICMP — the Internet's error and probe channel

Routers monitor every packet they forward. When something unexpected happens at the network layer, the router sends an **ICMP** (Internet Control Message Protocol) message back to the source. ICMP rides *inside* IP — its protocol number is 1, so an ICMP message looks to IP like just another payload except that the protocol field distinguishes it from TCP (6) or UDP (17). RFC 792 defines about a dozen message types; the most important ones map to concrete operational clues:

| Type | Name | Emitting event | Operational tool |
|---|---|---|---|
| 0 | Echo Reply | Response to type 8 | ping |
| 8 | Echo Request | Operator-initiated liveness check | ping |
| 3 | Destination Unreachable | Router cannot forward (net/host/port/protocol unreachable, or DF set and fragmentation needed) | mtu discovery, firewall hints |
| 5 | Redirect | Router sees a better next hop on the *same* LAN | routing table tuning |
| 11 | Time Exceeded | Router decremented IPv4 TTL or IPv6 Hop Limit to 0 | traceroute |
| 12 | Parameter Problem | Illegal header field value | bug reports |
| 13/14 | Timestamp Request/Reply | Clock skew probe | NTP precursor |

The **`ECHO` / `ECHO REPLY`** pair powers `ping` — every `ping` is one type-8 request followed by one type-0 reply. **`TIME EXCEEDED`** is the engine of `traceroute`: Van Jacobson's 1987 probe loop sends a packet with TTL 1, records the router that replies with type 11, then tries TTL 2, 3, ..., unmasking each hop along the path. The router whose decrement reaches 0 drops the packet and emits the `TIME EXCEEDED` response back to the source. **`DESTINATION UNREACHABLE`** has six defined codes (0 = net, 1 = host, 2 = protocol, 3 = port, 4 = fragmentation needed and DF set, 5 = source route failed); code 4 is the basis of path MTU discovery before RFC 1191 and the source-quench regulatory counting now used by TCP. The **`REDIRECT`** message lets a router teach a host about better geography on its local Ethernet: "send future packets for 192.32.63.0/24 directly to E4, not to me." **`SOURCE QUENCH`** (type 4) is deprecated; modern congestion control works at the transport layer using packet loss as a signal.

### ARP — turning an IP address into an Ethernet frame destination

Every NIC ever manufactured has a 48-bit Ethernet address assigned at the factory; IPs are 32-bit (or 128-bit for IPv6) and assigned by the network operator. The data link layer forwards frames by MAC, so IP cannot deliver a packet until the sender discovers the destination's Ethernet address. **ARP** (Address Resolution Protocol, RFC 826) does this by broadcasting a query onto the LAN:

```
1. host 1 broadcasts on CS LAN: "Who has 192.32.65.5? Tell 192.32.65.7 (E1)"
2. host 2 sees the broadcast, recognizes its own IP, and unicasts: "192.32.65.5 is at E2."
3. host 1 caches (192.32.65.7 -> E1, 192.32.65.5 -> E2) and sends the frame.
```

The source includes its own IP-to-MAC mapping in the request, so every host on the LAN can poison-fill its cache in a single broadcast — and host 2 does not need a second ARP round trip to reply. Entries time out after a few minutes so the cache heals when IPs move (a host gets a new IP but the same MAC). A **gratuitous ARP** is a station asking "who has *my* IP?" — any reply indicates a duplicate address and also primes every neighbor's cache. **Proxy ARP** has the router answer for a host on the far side, letting host 1 send host 4 frames addressed to the router's MAC without ever knowing host 4 is on another network. Across a router hop, the MAC addresses in the frame change at every boundary; the IP addresses stay constant end-to-end.

| Frame observed on | Source MAC | Dest MAC | Source IP | Dest IP |
|---|---|---|---|---|
| CS network, host 1 → host 2 | E1 | E2 | IP1 192.32.65.7 | IP2 192.32.65.5 |
| CS network, host 1 → host 4 | E1 | router E3 | IP1 192.32.65.7 | IP4 192.32.63.8 |
| EE network, host 1 → host 4 | router E4 | E6 | IP1 192.32.65.7 | IP4 192.32.63.8 |

### DHCP — leasing an address automatically

ARP assumes every host already has an IP. **DHCP** (Dynamic Host Configuration Protocol, RFC 2131) hands one out. When a computer boots with no IP — only its embedded Ethernet address — it broadcasts a **DHCP DISCOVER**. A DHCP server (or a relay that forwards the broadcast unicast to a remote server) responds with a **DHCP OFFER** containing a free IP, the lease duration, the subnet mask, the default gateway, and DNS servers. The client sends a **DHCP REQUEST** broadcasting which offer it accepted (so losing servers can reclaim their offered addresses). The winning server responds with a **DHCP ACK**:

```
client ── DISCOVER ──> (broadcast)
server ── OFFER  ──> client  (offered IP, lease time, mask, gw, DNS)
client ── REQUEST ──> (broadcast, "I accept server A's offer")
server ── ACK     ──> client  (lease confirmed)
```

Leases prevent address leakage. RFC 2131 specifies two timers: **T1** at 50% of the lease, when the client must request renewal from the original server; **T2** at 87.5%, when the client may seek any server if the original is unreachable. If neither succeeds before lease expiry, the client stops using the address and starts over. Option 53 inside a DHCP message is "DHCP Message Type" (`1`=DISCOVER, `2`=OFFER, `3`=REQUEST, `4`=DECLINE, `5`=ACK, `6`=NAK, `7`=RELEASE, `8`=INFORM). A hijacked or misconfigured DHCP server is a powerful attack tool — it controls the default gateway and DNS — which is why enterprise switches implement DHCP snooping to drop rogue offers.

### MPLS — the "layer 2.5" virtual circuit overlay

Pure IP forwarding consults the routing table for every packet using longest-prefix match: inspect destination, find the entry whose prefix matches the most address bits, send on that line. The lookup is expensive at millions of packets per second. **MPLS** (MultiProtocol Label Switching, RFC 3031) inserts a 4-byte shim header between layer 2 and IP, so a Label Switched Router (LSR) forwards by exact table index on the label, not by prefix matching. The shim format on a PPP link is shown in Fig. 5-62 of the source:

```
| PPP hdr | [Label(20)|TC(3)|S(1)|TTL(8)] | PPP hdr cont... |
                                          ^^^ MPLS shim, 4 bytes
```

| Field | Bits | Purpose |
|---|---|---|
| Label | 20 | Index into the LSR's forwarding table |
| Traffic Class (TC) | 3 | QoS markings (formerly EXP) |
| S (Bottom of Stack) | 1 | 1 if this is the last label; 0 if labels stack |
| TTL | 8 | Hop counter, decremented at each LSR; loops die |

The shim sits on PPP or below the EtherType `0x8847` on Ethernet, *neither* a layer-3 protocol (it depends on IP for label-path setup) *nor* a layer-2 protocol (it can span multiple hops). The standard quip is that MPLS lives at **layer 2.5**. The path setup is unlike traditional virtual circuits — users never invoke it; control protocols (RSVP-TE, LDP, BGP-LU) handle label distribution among routers when they boot.

At the ingress **Label Edge Router (LER)**, the shim is *pushed* onto the IP packet after inspecting the IP destination and any QoS fields. Inside the network, each **Label Switched Router (LSR)** performs `swap`: use the incoming label as an index to look up the outgoing interface and the new label, decrement TTL, send the packet on. At the egress LER, the shim is *popped* (or PHP — penultimate hop popping — lets the second-to-last LSR pop it, saving one lookup at the egress). The S bit is set to 1 for the bottom label and 0 above it, so stacks of multiple labels can support nested traffic engineering, VPNs over a backbone, and fast reroute.

The crucial difference from old-style virtual circuits is **aggregation by FEC** (Forwarding Equivalence Class). A label does not represent a flow; it represents a *class* of packets — all those routed the same way for the same QoS — and multiple flows that share a destination and service level can travel under a single label. The forwarding tables at every LSR can be set up so that labels get remapped at each hop exactly as in Fig. 5-3 of the source. `code/main.py` simulates this push/swap/pop sequence across three LSRs.

### Why MPLS gained traction, and why it still sits alongside IP

MPLS won because it offered three properties that longest-prefix IP forwarding lacked: (1) **fast forwarding** at line rate — table index beats prefix trie; (2) **traffic engineering** — you can pin a label-path along a non-shortest physical path to load-balance a busy ink, which IP's distributed computation cannot do; (3) **service differentiation** — labels can carry QoS class, VPN membership, and pseudowire semantics. MPLS still depends on IP for path setup; it cannot replace IP because it cannot stand alone — packets still carry their IP destination through the label stack so that at egress the IP can resume routing if the label path fails.

## Build It

`code/main.py` is stdlib-only. Work through it in this order:

1. **ICMP encode/decode.** `ICMPMessage` builds a message with a correct Internet checksum (ones-complement sum of the 16-bit words). Encode `ECHO REQUEST` (type 8, code 0, identifier `0x1234`, sequence 1), inspect the canonical byte hexdump, then decode the bytes back and verify the checksum.
2. **ICMP inside IP.** `icmp_in_ip(src, dst, icmp)` wraps the ICMP message in a 20-byte IPv4 header (protocol 1), and prints the 37-byte packet — exactly the format a router forwards when it triggers `ping`.
3. **`DESTINATION UNREACHABLE` code 4** — fragment-needed with DF set. Encode this and verify the next-hop MTU field in the payload.
4. **MPLS shim encode/decode.** `MPLSLabel(label, tc, s, ttl).encode()` produces the 4 bytes. Stack two labels (outer `0x001064`, inner `0x000020` with S=1) and decode the byte string back.
5. **Label-swap walkthrough.** Simulate a 3-LSR path: ingress LER pushes label 1000 with TTL 64; LSR1 swaps 1000→2000 and decrements to 63; LSR2 swaps 2000→3000 and decrements to 62; egress LER pops the shim. The egress sees the plain IP packet again.

Run with `python3 code/main.py`. No pip dependencies, no network calls.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Recognize an ICMP error | Wireshark `icmp`, type and code octets at offset 0/1 of the ICMP header | You call a TTL-die event type 11 code 0, point at `traceroute`, and read the source IPs in the replies |
| Diagnose a ping failure | Echo Request outgoing, Echo Reply missing, or ICMP error back | You distinguish "host unreachable" (no reply) from "host filters ICMP" (route works, ping blocked) |
| Trace an ARP exchange | `arp -an`, ARP cache entries, `tcpdump arp` | You see `who-has`/`is-at` pairs; cache timeout set to a few minutes; gratuitous ARP on address change |
| Diagnose DHCP events | DISCOVER/OFFER/REQUEST/ACK four-tuple, option 53 | You name which step failed: no server (DISCOVER only), pool exhausted (NAK), conflict (DECLINE) |
| Decode an MPLS trickle | Wireshark `mpls`, label and S-bit fields | You read the 20-bit label, the TC, the S-bit telling bottom-of-stack, count TTL decrements between LSRs |

## Ship It

Produce one reusable artifact under `outputs/`:

- An **ICMP type/code cheat sheet** mapping the dozen principal message types to the debugging tools that rely on them (`ping` for 8/0, `traceroute` for 11, path-MTU for 3/4, redirect for 5).
- An **ARP cache+proxy runbook** with the four-message sequence, the timeout policy, the gratuitous-ARP duplicate-address detection procedure, and the Wireshark `arp` filter list.
- A **DHCP lease-timer card** that shows T1=50%, T2=87.5%, lease expiry, and the four option-53 message types that any network admin should be able to spot in a `tcpdump -v` dump.
- An **MPLS label-stack decoder** that takes a hexdump of a PPP frame, points out the shim, and walks the operator through push/swap/pop with the S-bit, based on the model in `code/main.py`.

Start from [`outputs/prompt-internet-control-protocols-to-label-switching-and-mpls.md`](../outputs/prompt-internet-control-protocols-to-label-switching-and-mpls.md).

## Exercises

1. A router forwarding a packet decrements IPv4 TTL from 1 to 0. Name the ICMP message type and code it emits, the destination it goes to, and the four-byte contents the source will see in the original packet that triggered the report.
2. A `ping` to `192.168.1.1` returns "Destination Host Unreachable (type 3 code 1)." Name three operational causes ranked by likelihood on a small office network, and the exact Wireshark filter you would use to confirm each.
3. Two hosts share the same IP address by accident. Describe how **gratuitous ARP** reveals the collision during boot, and what the network administrator should look for in `tcpdump` output.
4. A laptop fails to get a DHCP address at boot. Capture shows only `DISCOVER` packets, no `OFFER`. Give three hypotheses for where the failure lives and the one-line command you would run on the switch to confirm the most likely one.
5. Run `code/main.py` and report the four bytes of the MPLS label whose label value is `0x001064`, traffic class `0b101`, S bit `0`, TTL `12`. Decode the same bytes manually using bit-shifts and confirm.
6. An LSR decrements the MPLS TTL to 0. What happens to the packet, what message gets emitted (name the protocol) and back to whom? Compare this to the corresponding behavior for a pure IP router.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ICMP | "ping protocol" | Internet Control Message Protocol (RFC 792, IP protocol 1) that carries about a dozen error/probe message types *inside* IP packets |
| `TIME EXCEEDED` | "traceroute's response" | ICMP type 11 emitted when a router decrements TTL/Hop Limit to 0; traceroute abuses it by sending sequentially-larger TTLs to map each hop |
| ARP | "IP-to-MAC lookup" | Address Resolution Protocol (RFC 826); broadcast `who-has`, receive unicast `is-at`, cache the pair for a few minutes, gratuitous ARP refreshes on boot |
| Proxy ARP | "router answers for the remote host" | An ARP mode in which a router replies for a host on the far side of itself, so the sender stays on the same network frame-wise without knowing the host is remote |
| DHCP | "automatic IP" | Dynamic Host Configuration Protocol (RFC 2131) leases an IP plus mask, gateway, and DNS; DORA four-message exchange; T1/T2 timers at 50%/87.5% |
| Lease time | "the address lifetime" | The number of seconds a DHCP client may use an IP before it must renew; failure to renew before expiry relinquishes the address |
| MPLS | "labels on packets" | MultiProtocol Label Switching (RFC 3031); 4-byte shim between PPP/Ethernet and IP; LSRs swap labels instead of longest-prefix matching; "layer 2.5" protocol |
| FEC | "the label's meaning" | Forwarding Equivalence Class — the set of packets that share a label (same destination, same QoS); unlike a VC, a label represents a class, not a flow |
| S-bit | "bottom-of-stack" | 1-bit flag in an MPLS shim marking the bottom label; set to 1 on the innermost label so the egress knows when to resume IP forwarding |
| LER | "the edge label box" | Label Edge Router — pushes the first shim at ingress, pops the last shim at egress; turns IP forwarding on/off the labeled path |

## Further Reading

- **RFC 792** — Internet Control Message Protocol; full type/code list, the ones-complement checksum algorithm, and the role of ECHO/TIME EXCEEDED.
- **RFC 826** — Address Resolution Protocol; the broadcast-request, unicast-reply design, ARP cache, and the gratuitous and proxy variants.
- **RFC 2131** — Dynamic Host Configuration Protocol; the DORA exchange, the lease lifecycle with T1 and T2 timers, and option 53 message types.
- **RFC 4861** — Neighbor Discovery for IPv6; the protocol that replaces ARP for IPv6.
- **RFC 3031** — MPLS architecture; the 4-byte shim, label stack, push/swap/pop semantics, and the layered quip about "2.5".
- **RFC 1191** — Path MTU Discovery; how `DESTINATION UNREACHABLE` code 4 propagates the next-hop MTU back to the source.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.6.4-5.6.5 — the source chapter section pairing the Internet control protocols with label switching and MPLS.
- Van Jacobson, "Traceroute" (1987) — the original inspiration for repurposing ICMP `TIME EXCEEDED` for path discovery.
