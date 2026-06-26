# ICMP, ARP, and Neighbor Discovery

> IP packets carry a 32-bit (or 128-bit) destination address, but the wire speaks in 48-bit Ethernet addresses — and routers, hosts, and diagnostic tools all need a way to *signal*, *discover*, and *recover* that nothing below the IP layer actually cares about. **ARP (RFC 826)** answers "who owns 10.0.0.5 on this wire?" by broadcasting a 28-byte request and caching the reply for 15-20 minutes. **ICMP (RFC 792)** rides *inside* IP with Protocol=1 and carries the diagnostic vocabulary of the internet: Echo (ping), Destination Unreachable, Time Exceeded, Redirect, and Parameter Problem. **ICMPv6 (RFC 4443, Protocol=58)** absorbs ARP and more, and **Neighbor Discovery (NDP, RFC 4861)** replaces ARP with solicited-node multicast at `ff02::1:ffXX:XXXX` and a 5-state reachability machine (INCOMPLETE → REACHABLE → STALE → DELAY → PROBE). **Traceroute** exploits ICMP Time Exceeded by sending probes with TTL=1, 2, 3 … and watching which router drops each one. Together these protocols are the small, often-invisible layer that makes IP routable, debuggable, and survivable on a real Ethernet segment.

**Type:** Build
**Languages:** Python (stdlib only)
**Prerequisites:** IPv4 / IPv6 header basics, the data-link framing lesson, basic subnetting, `ping` and `traceroute` from the shell.
**Time:** ~80 min

## Learning Objectives

- Construct a 28-byte ARP request and reply by hand: HardwareType=1, ProtocolType=0x0800, HLen=6, PLen=4, Opcodes 1 and 2, and the four address slots, then place it inside an Ethernet frame with EtherType 0x0806 and broadcast destination `ff:ff:ff:ff:ff:ff`.
- Encode and verify an ICMP Echo Request with the correct 16-bit Internet checksum (one's complement of the one's complement 16-bit word sum), and verify that the same checksum arithmetic works on an Echo Reply.
- Map the major ICMPv6 types to their jobs: 1/2/3/4 for errors, 128/129 for Echo, 133-136 for NDP, 137 for Redirect.
- Derive a solicited-node multicast address `ff02::1:ffXX:XXXX` from an IPv6 unicast target and explain why it limits flooding to one Ethernet segment.
- Trace the NDP reachability state machine: INCOMPLETE → REACHABLE → STALE → DELAY → PROBE, and identify which event triggers each transition.
- Build a simple traceroute simulator that "probes" with TTL=1, 2, 3 and reports the synthetic TimeExceeded round for each hop.

## The Problem

A new host joins the 10.0.0.0/24 LAN with address 10.0.0.42. It has never seen any other host on the wire. It opens a TCP connection to 10.0.0.7 on port 443 and waits. The TCP SYN never goes out. The reason is invisible: the host has 10.0.0.42 as its *IP* address, but the Ethernet interface does not know the 48-bit MAC address that owns that IP. IP needs Ethernet, and Ethernet needs a 48-bit address it has never heard of. Three things have to happen for that SYN to leave the box:

1. The host broadcasts an **ARP request** — "if your IP is 10.0.0.7, tell me your MAC" — and the matching host replies.
2. While waiting, the host can still send *control* traffic using **ICMP** (Protocol=1 inside IPv4) — that is how `ping` and `traceroute` work — and the kernel's ICMPv6 stack (Protocol=58 inside IPv6) handles both diagnostics and link-layer resolution.
3. The matching host replies with a unicast **ARP reply**; the requester stores it in a kernel cache and the SYN finally goes out.

ARP is the *first* problem. The other two are *continuing* problems: every minute a cache entry ages out and the next packet re-broadcasts, and every time the link goes down the cache is wrong until expiry. ICMP is the network's way of saying "I can't deliver this," "you're looping," "fragmentation needed," and "please reduce your rate." ICMPv6 absorbs the link-layer role too — NDP replaces ARP outright, and the solicited-node multicast address `ff02::1:ffXX:XXXX` (last 24 bits of the target) means a host only has to listen for the 2^24 multicast group that contains the address it cares about, not the entire 2^128 address space.

This lesson is the bridge between *what an IP header says* and *what the wire actually does.* It is also the only place you get to see diagnostic protocols that work even when "the network is down" — and the only place you get to see a state machine (NDP) that explicitly models uncertainty.

## The Concept

### ARP packet format and lookup

The 28-byte ARP packet (for IPv4 over Ethernet) sits inside a regular Ethernet frame whose EtherType is **0x0806**. The frame's destination MAC is `ff:ff:ff:ff:ff:ff` for a **request** and the unicast target MAC for a **reply**. The fields:

| Bytes | Field | Size | Request value | Reply value |
|-------|-------|------|---------------|-------------|
| 0-1 | HardwareType | 2 | 1 (Ethernet) | 1 |
| 2-3 | ProtocolType | 2 | 0x0800 (IPv4) | 0x0800 |
| 4 | HLen | 1 | 6 | 6 |
| 5 | PLen | 1 | 4 | 4 |
| 6-7 | Opcode | 2 | 1 (request) | 2 (reply) |
| 8-13 | SenderHardwareAddress | 6 | sender MAC | sender MAC |
| 14-17 | SenderProtocolAddress | 4 | sender IP | sender IP |
| 18-23 | TargetHardwareAddress | 6 | 00:00:00:00:00:00 (unknown) | target MAC |
| 24-27 | TargetProtocolAddress | 4 | target IP | target IP |

The lookup is dead simple: every host on the wire receives the broadcast, and the host whose IP matches `TargetProtocolAddress` writes its own MAC into the reply and sends it unicast. Other hosts silently drop it. The cache entry then sits in the requester's ARP table for **15-20 minutes** (RFC 826 does not mandate the timeout; Linux defaults to ~60 s for incomplete and 20 min for reachable, and Windows uses 15 s of disuse).

### ARP cache and gratuitous ARP

The kernel ARP cache is a small dictionary keyed by IP. On a Linux box, `ip neigh` shows it; entries move through states: REACHABLE, STALE, DELAY, PROBE (NDP-flavored), and the kernel issues a refresh *just before* a stale entry is used. Three corner cases matter:

- **Gratuitous ARP.** A host sends an ARP request for *its own* IP — broadcast, sender IP = target IP. The point: any switch's MAC learning table updates, and any other host that has a stale entry updates it. Used at boot, on IP change, and on link failover.
- **ARP spoofing.** Because ARP has no authentication, any host on the wire can answer "10.0.0.7 is at *my* MAC" and intercept traffic. The defense is **Dynamic ARP Inspection** on managed switches and static ARP entries on critical hosts.
- **Proxy ARP.** A router answers "10.0.0.7 is at *my* MAC" on behalf of a host on another subnet, and then forwards the frame. Used to bridge subnets without the host noticing. Mostly retired today.

### ICMP types

ICMP is a *peer* of TCP and UDP in the IP stack: it rides inside IP (Protocol=1 for IPv4) and shares the same 8-bit Type/Code/16-bit Checksum/Variable pattern as many other protocols. IPv4 places it directly behind the IP header; IPv6 places it behind the IPv6 header with Protocol=58 and includes the standard 128-bit "pseudo-header" in the checksum (so a corrupted source address is caught). The Type field is the high-level verb; the Code field is the specific failure mode.

| Type | Name | Codes (selected) | Direction | Used for |
|------|------|------------------|-----------|----------|
| 0 | Echo Reply | 0 | reply | `ping` response |
| 3 | Destination Unreachable | 0 net, 1 host, 2 protocol, 3 port, 4 frag-needed + DF set | reply | path/host/port MTU errors |
| 4 | Source Quench | 0 | reply | **deprecated** — was used to ask a sender to slow down; generators were buggy and routers were told to stop emitting it (RFC 6633) |
| 5 | Redirect | 0-3 (network/host/ToS-net/ToS-host) | reply | "use this other router instead" |
| 8 | Echo Request | 0 | request | `ping` |
| 11 | Time Exceeded | 0 TTL, 1 frag-reassembly | reply | **traceroute** exploits code 0 |
| 12 | Parameter Problem | 0 header-error, 1 missing-opt, 2 bad-length | reply | something is wrong with the IP header |
| 13/14 | Timestamp Req/Rep | 0 | both | clock-skew measurement; rarely used today |
| 15/16 | Information Req/Rep | — | both | deprecated, replaced by BOOTP/DHCP |

The **Internet checksum** is the same 16-bit one's-complement sum RFC 1071 specifies for the IP header. Treat the header (Type, Code, Checksum=0, plus the 4-byte "Rest of Header" and any body) as a sequence of 16-bit big-endian words, sum them, fold any carry back into the low 16 bits, then take the one's complement. The receiver re-sums with the checksum in place; the result should be 0xFFFF (or 0x0000 depending on convention) if no bit was flipped in transit. The code in `code/main.py` implements this and verifies it on the resulting Echo Reply.

### ICMPv6 types

ICMPv6 (RFC 4443) folds two jobs into one protocol: classic diagnostics (Error messages + Echo) **and** the link-layer and router-discovery role that ARP and ICMP Router Discovery used to play for IPv4. Type ranges are firm:

- **1-4: Errors.** 1 Destination Unreachable (with codes 0 no-route, 1 admin-prohibited, 2 beyond-scope, 3 addr-unreachable, 4 port-unreachable, 5 src-addr-failed-policy, 6 reject-route), 2 Packet Too Big (the **MTU discovery** message — replaces IPv4 fragmentation), 3 Time Exceeded (TTL or hop-limit), 4 Parameter Problem.
- **128 / 129: Echo Request / Reply.** Same wire format as ICMPv4, but with the 128-bit IPv6 pseudo-header in the checksum.
- **133 / 134: Router Solicitation / Advertisement.** Hosts multicast RS to ask "is there a router here?" Routers periodically unicast RA with prefix, MTU, and lifetime information. Together these are the IPv6 equivalent of DHCP + default-gateway discovery.
- **135 / 136: Neighbor Solicitation / Advertisement.** NS replaces ARP Request ("who owns this IPv6 address?"); NA replaces ARP Reply. NA flags: **R** (Router), **S** (Solicited — was the response triggered by this host's NS), **O** (Override — flush cached entries and install this one).
- **137: Redirect.** "Use this other router for this destination" — same job as ICMPv4 Type 5.

### Neighbor Discovery (NDP, RFC 4861)

NDP is the IPv6 version of ARP plus the version of ARP that knows when it's *wrong*. The wire format is similar (target IPv6 address in the NS, sender link-layer option in the NA), but the **state machine** is the innovation. After a host resolves a neighbor's IPv6 → MAC binding, it tracks how confident it is in the cached answer:

```
INCOMPLETE ──(NS sent)──> INCOMPLETE
       │
       │  NA received
       ▼
   REACHABLE  ──(more than REACHABLE_TIME_MS since last confirmation)──> STALE
       │
       │  first packet sent to a STALE entry
       ▼
    DELAY      ──(DELAY_FIRST_PROBE_TIME expired)──> PROBE
       │
       │  PROBE sends up to MAX_UNICAST_SOLICITS
       ▼
   (re-resolve, or drop the entry)
```

- **INCOMPLETE**: NS just sent, no NA yet.
- **REACHABLE**: NA confirmed the binding within the last `REACHABLE_TIME_MS` (default 30 s) and the upper layer has *not* sent a packet to it since.
- **STALE**: more than `REACHABLE_TIME_MS` since last confirmation. The cached MAC is *believed* but not *fresh*. A packet can be sent; the first one transitions to DELAY.
- **DELAY**: a packet was sent to a STALE entry. We hold off probing for `DELAY_FIRST_PROBE_TIME` (default 5 s), giving upper layers a chance to confirm the MAC works (e.g. an ACK arrived).
- **PROBE**: actively unicasting NS packets at `RETRANS_TIMER_MS` (default 1 s) intervals to re-confirm. After `MAX_UNICAST_SOLICITS` (default 3) failed probes, the entry is deleted.

The **solicited-node multicast** address is how NS limits flooding. The format is `ff02::1:ffXX:XXXX` — the `ff02` prefix is link-local scope, and the last 24 bits are the last 24 bits of the target IPv6 address. So a host trying to resolve `2001:db8::abcd:1234` multicasts the NS to `ff02::1:ff34:1234`, and the kernel only has to *listen* on the 2^24 multicast group containing addresses whose low 24 bits it might own. (In practice the kernel only joins the group for each address assigned to an interface, not 2^24 of them.)

### Traceroute

Traceroute is built on ICMP Time Exceeded (Type=11, Code=0). The technique:

1. Send a UDP packet (or ICMP Echo) to the destination with **TTL=1**. The first router decrements to 0, drops the packet, and returns a TimeExceeded to the sender. Sender now knows the IP of router 1.
2. Send a packet with **TTL=2**. The first router decrements to 1 and forwards; the second router decrements to 0, drops, and returns TimeExceeded. Sender now knows router 2.
3. Continue with TTL=3, 4, 5 … until a packet reaches the destination. The destination returns either ICMP Port Unreachable (for the UDP probe) or Echo Reply (for the ICMP probe) — that ends the trace.

`traceroute` reports the round-trip time for each TTL round, usually by sending three probes per TTL. Modern implementations also include a fallback to TCP probes (when UDP/ICMP are filtered) and to direct probing without the kernel's TTL setting.

### Common failures

Three things go wrong most often in production:

- **ARP storm on a bridge loop.** Two switches with a looped uplink. Each forwards a broadcast from the other, the MAC tables flip-flop, and the broadcast domain is saturated. Spanning Tree Protocol (802.1D) is the fix; ARP itself is just the messenger.
- **Stale ARP cache after a VM migration.** A VM moves to a new host, sends a gratuitous ARP, but the switch has not yet relearned the new port. The right packet is delivered to the wrong physical port. Mitigation: gratuitous ARP on every NIC-up event, or fabric path pinning.
- **ICMP filtered and traceroute fails.** The middlebox drops ICMP TimeExceeded. Traceroute then shows the *first* non-responsive hop and `* * *` for the rest. The fix is to use TCP traceroute (which most firewalls allow on 80/443) or Paris-traceroute that keeps the probe flow-identifier constant.

## Build It

`code/main.py` is a 195-line stdlib-only implementation:

- **ARP packet encoder/parser** — pack the 28-byte ARP message with all the fields above, and unpack one for inspection.
- **ICMP Echo encoder** — Type 8 with a 16-byte payload, correct 16-bit Internet checksum. The same code verifies the checksum on the Echo Reply.
- **ICMPv6 NS/NA encoder** — Type 135/136 with the target IPv6 address; compute the solicited-node multicast group from the target.
- **ARP cache with timeout** — a `dict` of `{ip: (mac, expires_at)}`; on lookup, evict any expired entry and return the rest. Honors a 20-minute default with a configurable timeout.
- **Traceroute simulator** — given a route of "hops" (IP + delay), probes with TTL=1, 2, 3 …, simulates a router that decrements TTL and emits TimeExceeded, and prints a formatted hop list.
- **`__main__`** runs all four demonstrations in order with headers.

Run it:

```bash
python3 code/main.py
```

Expected exit code 0. Output: four labeled sections — "ARP roundtrip," "ICMP Echo + checksum," "ICMPv6 NDP + solicited-node," "Traceroute." Each section prints the wire format and the decoded result.

## Use It

| Task | Evidence | What good looks like |
|------|----------|----------------------|
| Diagnose "first-packet loss" | ARP cache empty for the destination, then a single broadcast, then a unicast reply | One ARP round-trip, then the connection; reproducible |
| Read an `ip neigh` dump | `REACHABLE`, `STALE`, `DELAY`, `PROBE` flags and the second column | You can predict when the next probe will fire and why |
| Verify a ping | 16-byte ICMP Echo with a checksum the receiver sums to 0xFFFF | Both the request and reply pass the same checksum test |
| Decode `traceroute` output | A list of router IPs, one per TTL round | The path the packets actually took, including asymmetric return paths |
| Compute a solicited-node mcast | Last 24 bits of target copied into `ff02::1:ffXX:XXXX` | You can do it on paper for `2001:db8::abcd:1234` |
| Catch a stale ARP entry | Switch MAC table shows a port the host no longer uses | Gratuitous ARP from the new port fixes it; silent otherwise |

## Ship It

Produce one artifact under `outputs/`:

- A Wireshark-style annotation of an ARP request → ARP reply → TCP SYN, with each frame's source/destination MAC, EtherType, and the four ARP address slots. Start from `outputs/prompt-icmp-arp-and-neighbor-discovery.md` (if it exists) or invent your own.
- Or: a one-page reference card for the ICMPv6 error types and NDP messages with their wire layouts and the scenarios that produce them.
- Or: a traceroute trace from your laptop to `1.1.1.1` annotated hop-by-hop, with the autonomous system (or country) of each hop and the reason a hop sometimes returns `* * *`.

## Exercises

1. In `code/main.py`, change the cache timeout from 1200 s to 60 s. Re-run and confirm the second ARP request to the same target now comes from the same host twice. What does this tell you about ARP cache behavior under churn?
2. Compute the 16-bit Internet checksum for an Echo Request with a 16-byte payload of all-zeros. Verify with the simulator that the receiver's recomputed sum is 0xFFFF.
3. Derive the solicited-node multicast address for `fe80::1:2:3:4` and for `2001:db8:1234:5678::abcd`. Run them through `solicited_node_mcast()` and compare.
4. Add a fourth hop to the traceroute simulator with a 50 ms delay and a "drop" flag. Confirm the trace ends at hop 3 with `* * *`.
5. Encode an ICMPv6 Neighbor Solicitation for target `2001:db8::dead:beef` and verify the type field is 135 and the target is in the standard 16-byte IPv6 offset.
6. In Wireshark, capture a single `ping` to `8.8.8.8`. Identify the request, the reply, the checksum, and the IPv4 Protocol field. Compare each value to what `code/main.py` produces.

## Key Terms

| Term | What it actually means |
|------|------------------------|
| ARP | Address Resolution Protocol; IPv4 → Ethernet MAC resolution, 28-byte packet, RFC 826 |
| ICMP | Internet Control Message Protocol; rides inside IPv4 with Protocol=1; diagnostic + error reporting |
| ICMPv6 | Replaces ICMPv4 *and* ARP for IPv6; Protocol=58, includes NDP, RFC 4443 |
| NDP | Neighbor Discovery Protocol; IPv6's ARP + reachability state machine, RFC 4861 |
| Solicited-node multicast | `ff02::1:ffXX:XXXX`; limits NS flood to a 2^24-bit group |
| REACHABLE_TIME | How long a cached NDP entry stays "fresh" before becoming STALE (default 30 s) |
| Internet checksum | One's complement of the one's complement 16-bit word sum; RFC 1071 |
| EtherType 0x0806 | The Ethernet type field marking an ARP frame |
| Time Exceeded | ICMP Type 11 / ICMPv6 Type 3; emitted when a router decrements TTL to 0 |
| Gratuitous ARP | ARP request for one's own IP; refreshes switch MAC tables and ARP caches |

## Further Reading

- RFC 826 — *An Ethernet Address Resolution Protocol* (Plummer, 1982). The original ARP spec.
- RFC 792 — *Internet Control Message Protocol* (Postel, 1981). The ICMPv4 spec.
- RFC 4443 — *Internet Control Message Protocol (ICMPv6) for the Internet Protocol Version 6 Specification* (Conta, Deering, Gupta, 2006). The ICMPv6 spec.
- RFC 4861 — *Neighbor Discovery for IP version 6* (Narten, Nordmark, Simpson, Daydreamer, 2007). The NDP spec; defines the state machine and the message formats.
- Stevens, W. R. — *TCP/IP Illustrated, Volume 1: The Protocols*, 2nd ed., Ch. 4 (ARP) and Ch. 6 (ICMP). The hands-down best walkthrough of the wire format.
- Tanenbaum & Wetherall — *Computer Networks*, 5th ed., Ch. 5 §5.6.x (link-layer addressing, ARP, ICMP). Source chapter.
