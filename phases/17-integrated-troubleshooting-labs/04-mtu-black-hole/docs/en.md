# MTU Black Hole

> Small web pages and most API calls work fine, but the moment a user uploads a 2 MB image, transfers a 5 MB file via SFTP, or initiates a database backup, the connection stalls for 30 seconds, then either hangs forever or fails. Meanwhile, `ping` with 1464-byte payloads works, and `curl` of a 5 KB JSON endpoint returns in 80 ms. This is the **MTU black hole** — a router in the path that drops IPv4 packets with the "Don't Fragment" bit set and an MTU exceeding the link's actual capacity, but does not return the ICMP "Fragmentation Needed and DF set" message that would have allowed Path MTU Discovery to recover. This lesson walks the diagnostic discipline: a four-command chain (`ip route get`, `tracepath`, `ip link show mtu`, packet capture with a large DF-bit packet) that pinpoints the bad hop, and the operational fixes (lower the MSS on the tunnel, set the DF bit off, fix the ICMP filter). The synthetic trace generator in `code/main.py` reproduces the exact wire-format of the relevant ICMP and TCP segments so you can recognize them in a real `tcpdump`.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 04 IP fragmentation, Phase 08 TCP MSS, Phase 13 ICMP types, Lesson 01 of this phase
**Time:** ~100 minutes

## Learning Objectives

- Diagnose the MTU black hole failure: large DF-bit packets disappear at a specific hop, no ICMP error is returned, and the connection stalls at the TCP MSS-negotiated value or below the link MTU.
- Apply the four-command diagnostic chain (`ip route get`, `tracepath -m`, `ip link show`, packet capture with a Do-Not-Fragment packet of varying size) to find the exact hop where large packets are dropped.
- Distinguish an MTU black hole from a pathologically small MTU and from a PMTUD failure due to ICMP filtering. The three have different evidence signatures and different fixes.
- Read the IPv4 "Don't Fragment" (DF) bit and the ICMP Type 3 Code 4 "Fragmentation Needed and DF was set" message format, and explain how Path MTU Discovery is supposed to use it.
- Compute the right MSS for a TCP connection that traverses a tunnel (IPsec, GRE, VXLAN, WireGuard) and explain why the effective MTU is reduced by the tunnel overhead.
- Construct a synthetic packet-trace generator (no live capture) that reproduces the wire format of a 1500-byte Ethernet frame, an ICMP Type 3 Code 4 message, and a TCP SYN with MSS option, to practice recognition in `tcpdump`.

## The Problem

A network engineer in a regional ISP support team gets a call: "VPN works for browsing and small file transfers, but large transfers hang and then fail." The customer is a small business that uses an IPsec VPN to a partner company. Small web pages load. Email works. SSH is responsive. But the moment anyone tries to `scp` a 5 MB file, the transfer stalls for 30 seconds, then errors out. The customer also reports that the partner company's database sync (a 50 MB overnight job) has been failing for the past two weeks.

The network engineer does the obvious things first: `ping` works, `dig` works, `curl` of a small JSON endpoint works. The customer insists the VPN "worked perfectly last month." The engineer captures packets with `tcpdump` and sees the TCP three-way handshake complete normally, the client send a 1400-byte segment with the DF bit set, and then... nothing. No ACK from the server, no ICMP error, just retransmissions every 30 seconds until the connection is reset.

The likely cause: a router in the IPsec path has an MTU mismatch. The router's tunnel interface has an MTU of 1420 (a common value for IPsec with AES-GCM-128 and a 20-byte outer IP header), but somewhere along the path there is a link with an MTU of 1400 (a common value for PPPoE links or some MPLS VPNs). The router at that hop should send back an ICMP Type 3 Code 4 "Fragmentation Needed" message to inform the sender of the smaller MTU, but the ICMP filter on the edge firewall is dropping outbound ICMP. The result: the sender never learns the smaller MTU, the DF-bit packet disappears, and the connection stalls.

This lesson is the diagnostic discipline for that scenario. The signature is unmistakable once you know what to look for:

- Small packets (under the black hole's MTU) work
- Large packets (over the black hole's MTU) with the DF bit set vanish
- ICMP Type 3 Code 4 from the black hole hop is missing
- The connection eventually times out after `tcp_retries2` retransmissions

## The Concept

### Path MTU, MSS, and the DF Bit

The Maximum Transmission Unit (MTU) is the largest IP packet that can traverse a link without fragmentation. On Ethernet, the standard MTU is 1500 bytes. On PPPoE, it is 1492 (8 bytes of PPPoE header). On IPsec tunnel mode with AES-GCM, it is typically 1420 (1500 minus 50–80 bytes of IPsec overhead). On VXLAN, it is 1450 (1500 minus 50 bytes of VXLAN + UDP + IP).

The Maximum Segment Size (MSS) is the largest TCP *payload* (data) that can fit in a single TCP segment, after subtracting the IP and TCP headers from the MTU. For a 1500-byte Ethernet MTU, the MSS is typically 1460 (1500 - 20 IP header - 20 TCP header). For a 1420-byte IPsec MTU, the MSS is typically 1380.

The Don't Fragment (DF) bit is a flag in the IPv4 header (and a flag in the IPv6 header, where it is mandatory and cannot be cleared) that tells routers: "if you cannot forward this packet without fragmenting it, drop it and send an ICMP error back to me." Modern TCP stacks set the DF bit on every segment they send, on the assumption that Path MTU Discovery will discover the smallest MTU along the path and shrink the segments accordingly.

Path MTU Discovery (PMTUD) is the mechanism that uses the DF bit and the ICMP Type 3 Code 4 message to discover the smallest MTU on the path:

1. The sender starts with the interface MTU (e.g., 1500) and the corresponding MSS (1460)
2. The sender sets the DF bit on every packet
3. If a router on the path cannot forward the packet without fragmenting, it drops the packet and returns an ICMP Type 3 Code 4 to the sender, including the smaller MTU in the ICMP message's "Next-Hop MTU" field
4. The sender reduces its MSS to fit the new MTU and retries
5. The process repeats until packets get through

PMTUD fails when the ICMP Type 3 Code 4 message is *filtered* somewhere on the return path. This is the **PMTUD black hole** — different from the **MTU black hole** in that an MTU black hole is a link that cannot forward the packet (with or without fragmentation), while a PMTUD black hole is a working link that does not return the ICMP error. The signature is identical: large packets disappear, no ICMP error, connection stalls.

### The Four-Command Diagnostic Chain

| # | Command | Healthy output | Problem output | Points to |
|---|---------|----------------|----------------|-----------|
| 1 | `ip route get <dst>` | `cache entries 0 0 ...` with no MTU info | If using `ip route get`, MTU is not in the output; use `tracepath` instead | Initial state |
| 2 | `tracepath -m 1500 <dst>` | `pmtu 1500` | `pmtu 1400` or `pmtu 1420` reported at some hop | The actual path MTU |
| 3 | `ip -d link show <iface>` | `mtu 1500` for Ethernet, `mtu 1420` for IPsec | `mtu 1400` for PPPoE | Per-interface MTU |
| 4 | `tcpdump -ni <iface> 'tcp[tcpflags] & tcp-syn != 0 and ip[6:2] & 0x4000 != 0'` (SYN with MSS option) | TCP SYN with MSS=1460 | TCP SYN with MSS=1380 (lowered) | Negotiated MSS |
| 5 | `tcpdump -ni <iface> 'icmp'` | ICMP Type 3 Code 4 from a router hop | No ICMP Type 3 Code 4 | ICMP filter in the path |

The order matters: `tracepath` is the most powerful single command because it walks the path hop by hop, sending probe packets of decreasing size, and reports the smallest MTU that worked. If `tracepath` reports `pmtu 1400` at hop 7, hop 7 is the bottleneck. The bottleneck may be a router with a small MTU on one of its interfaces, or it may be a link with a small MTU (PPPoE, MPLS, satellite).

### Reading the ICMP Type 3 Code 4 Message

The ICMP "Fragmentation Needed and DF set" message is defined in RFC 792 (updated by RFC 1191 for the Next-Hop MTU extension). The wire format is:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Type 3    |     Code 4    |          Checksum             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Reserved = 0        |        Next-Hop MTU          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         IP Header + 8 bytes of original packet                |
+---------------------------------------------------------------+
```

The "Next-Hop MTU" field was added by RFC 1191; older routers send Code 4 with a zero MTU field, which forces the sender to fall back to the IPv4 minimum (576) for the next probe. In `tcpdump` you would see:

```
14:32:01.234 IP 10.0.0.1 > 192.168.1.5: ICMP 70: 10.0.0.1 unreachable - need to frag (mtu 1400)
```

The "(mtu 1400)" annotation is Wireshark reading the Next-Hop MTU field for you. If you see this message, you have located the bottleneck. If you do not see this message but the packet disappears at a particular hop, you have located the PMTUD black hole.

### The Tunnel MTU Tax

Tunnels reduce the effective MTU of the path because they wrap the original packet in an outer header. The standard reductions:

| Tunnel | Overhead | Effective MTU on a 1500-byte link |
|--------|----------|-----------------------------------|
| IPsec ESP (AES-GCM-128) | 50–62 bytes | 1438–1450 |
| IPsec ESP (AES-CBC + HMAC-SHA256) | 70–82 bytes | 1418–1430 |
| GRE | 24 bytes | 1476 |
| GRE + IPsec | 74–106 bytes | 1394–1426 |
| VXLAN | 50 bytes | 1450 |
| WireGuard | 32 bytes | 1468 |
| L2TP | 24 bytes | 1476 |
| PPPoE | 8 bytes | 1492 |

The MSS that the TCP endpoints negotiate must be the effective MTU minus 40 (20 IP + 20 TCP). For a WireGuard tunnel, the MSS would be 1428; for GRE + IPsec with full overhead, it would be 1354.

A common operational mistake: configure an IPsec tunnel with a 1500-byte MTU on the tunnel interface, then send a 1500-byte packet. The packet gets encapsulated, becomes 1562 bytes, gets dropped by the next hop with a 1500-byte MTU, no ICMP comes back (PMTUD black hole), and the user sees a stall. The fix is to set the tunnel interface MTU to 1420 (or whatever the inner MTU needs to be) so the kernel knows to set the DF bit only on packets that fit.

### The `ip link` MTU, the `ifconfig` MTU, and the `tcp` Window

There are three MTU-related values that you can configure on a Linux system:

- **Interface MTU** (`ip link set dev <iface> mtu 1400`): the largest frame the kernel will accept for transmission on this interface. Outgoing packets larger than this are fragmented (or dropped, if the DF bit is set).
- **Tunnel MTU** (set when creating a tunnel interface): the largest frame the tunnel wrapper will accept. Typically set to inner MTU minus tunnel overhead.
- **TCP MSS** (`ip route advmss 1380`): the MSS advertised in the TCP SYN to the peer. The peer will use this as the upper bound on segment size.

For PMTUD to work correctly, all three values must be consistent: the interface MTU ≥ tunnel MTU + tunnel overhead, and the advmss ≤ tunnel MTU - 40. A common bug is to leave the default `advmss` of 1460 when the tunnel MTU is 1380 — the kernel advertises a larger MSS than the path can carry, and the connection stalls on the first large segment.

### Why Some Firewalls Filter ICMP Type 3 Code 4

The historical reason: early denial-of-service attacks used ICMP Type 3 Code 4 as a vector to redirect traffic. A malicious router on the path could send a Code 4 with a small Next-Hop MTU, forcing the sender to fragment excessively, exhausting CPU and memory. In response, many operators configured "drop all ICMP" rules on edge firewalls. The result is the PMTUD black hole — large packets work only if the sender happens to pick an MSS that fits the bottleneck, which is essentially never for new connections.

The correct mitigation is *rate-limited* ICMP Type 3 Code 4, not blanket ICMP drop. Modern best practice (BCP 38, RFC 4890) recommends allowing ICMP Type 3 Code 4 to pass at a rate of, say, 100 per second per source. This is enough for PMTUD to function but limits the attack surface.

## Build It

The `code/main.py` in this lesson is a packet-format reference implementation. It builds the wire format of a 1500-byte Ethernet frame, an IPv4 packet with the DF bit set, a TCP SYN with the MSS option, and the ICMP Type 3 Code 4 message that the sender expects to receive. It also implements the four-command diagnostic chain as pure functions that operate on synthetic trace data.

1. **Read** `code/main.py`. Notice the use of `dataclass(frozen=True)` for the immutable packet records, the `ip_checksum` helper, and the `MtuPath` class that walks a synthetic path and identifies the bottleneck.
2. **Run** `python3 code/main.py --mode pmtud_ok` (or `--mode pmtud_blackhole`, `--mode mtu_mismatch`, `--mode tunnel_overhead`). You will see the wire-format hex dump of the relevant packets and the diagnostic chain's output.
3. **Compare** the four modes side by side: `python3 code/main.py --mode all`. The output will show the diagnostic chain produces a different verdict for each case.
4. **Modify** the `MtuPath` class to add a fifth mode where the bottleneck router sets the DF bit on the ICMP error itself (a less common bug — the ICMP error is fragmented and lost). This is the **ICMP fragmentation black hole**, a sub-case of the PMTUD black hole.

The simulator's lesson: the *method* is constant. Only the *evidence* and the *culprit* change.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| Small transfers work, large hang | `tracepath -m 1500 <dst>` | `pmtu 1400` at hop 7 | Path MTU < 1500 |
| No ICMP from bottleneck | `tcpdump -ni <iface> 'icmp'` | No Type 3 Code 4 seen | PMTUD black hole (ICMP filter) |
| Tunnel MTU too large | `ip link show <tunnel>` | `mtu 1500` on a tunnel that should be 1420 | Tunnel MTU not set |
| `ip route get` shows wrong MTU | `ip route get <dst>` | `mtu 1400` reported | Kernel's PMTUD cache has the right value |
| SYN shows high MSS | `tcpdump -ni <iface> 'tcp[tcpflags] & tcp-syn != 0'` | SYN with MSS=1460 on a tunnel that should be 1380 | advmss not set |
| IPv6 works, IPv4 hangs | `ip -6 route get <dst>` and `ip -4 route get <dst>` | IPv6 finds lower MTU, IPv4 stalls | IPv4 ICMP filter only |
| Some destinations work | `tracepath` to each | Different bottleneck per destination | Per-path MTU varies |
| Fix attempt: lower MSS | `ip route change <dst> via <gw> advmss 1380` | Connections succeed | MSS was the issue |
| Fix attempt: clear DF | `iptables -t mangle -A OUTPUT -p tcp --tcp-flags SYN SYN -j TCPMSS --set-mss 1380` | Connections succeed | Clamping MSS at the firewall |

## Ship It

The `outputs/prompt-mtu-black-hole.md` file is your deliverable. Author a one-page runbook for "small transfers work, large transfers hang" that contains:

1. The four-command diagnostic chain with one-line decision rules.
2. A reference table of tunnel overheads and the resulting effective MTU.
3. A list of three common false-positive pitfalls: (a) `ping` with default 56-byte payload works even on a 576-byte MTU link — does not prove the path supports 1500-byte packets, (b) some applications (notably browsers over HTTP/2) implement their own PMTUD and can succeed where the OS fails, (c) some routers send the ICMP error but with a zero Next-Hop MTU field, which forces the sender to fall back to 576 — a different code path than the normal PMTUD case.
4. An "intervention menu" with the specific commands to fix each root cause: lower `ip link mtu`, lower `advmss`, install `iptables` MSS clamp, fix the ICMP filter upstream.

## Exercises

1. **PMTUD math**: A path is Ethernet (1500) → MPLS VPN (1400) → Ethernet (1500). What is the path MTU? What MSS do the TCP endpoints negotiate? (Hint: the path MTU is the minimum of the per-link MTUs.)
2. **Tunnel tax**: An IPsec tunnel uses AES-GCM-128 (16-byte IV, 16-byte authentication tag, 20-byte outer IP header, 8-byte ESP header, 2-byte ESP trailer). What is the tunnel overhead? What is the effective MTU on a 1500-byte link? What is the right MSS?
3. **tracepath reading**: `tracepath` reports `pmtu 1400` at hop 7, then `pmtu 1400` at hops 8–10. What does this tell you about hop 7?
4. **PMTUD black hole**: `tracepath` reports `pmtu 1400` at hop 7, but `tcpdump` shows no ICMP Type 3 Code 4 from hop 7. What is the most likely cause? How do you fix it?
5. **advmss vs. tunnel MTU**: An IPsec tunnel has interface MTU 1420. The kernel's default advmss is 1460. What happens when a TCP connection is initiated to a peer through the tunnel? Why? How do you fix it?
6. **Compare with lesson 01**: Lesson 01's chain reports layer-by-layer evidence for a *complete* failure. This lesson's chain reports bottleneck evidence for a *partial* failure. How does the diagnostic methodology differ?

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| MTU | A measurement | Maximum Transmission Unit — the largest IP packet that can traverse a link without fragmentation |
| MSS | A measurement | Maximum Segment Size — the largest TCP payload, derived as MTU - 40 (IP + TCP headers) |
| DF bit | A bit | "Don't Fragment" — a flag in the IPv4 header that tells routers to drop the packet (and return ICMP) rather than fragment |
| PMTUD | A discovery protocol | Path MTU Discovery — the mechanism that uses the DF bit and ICMP Type 3 Code 4 to find the smallest MTU on the path |
| ICMP Type 3 Code 4 | A number | "Fragmentation Needed and DF set" — the message a router sends back to a sender when it cannot forward a DF-bit packet |
| Next-Hop MTU | A field | The MTU of the next hop, included by modern routers in the ICMP Type 3 Code 4 message |
| PMTUD black hole | A strange term | A path where large DF-bit packets are dropped but the ICMP error is filtered, so the sender never learns the smaller MTU |
| advmss | A route attribute | The MSS value the kernel advertises in the TCP SYN for a given route |
| ESP | A protocol | Encapsulating Security Payload — the IPsec protocol that provides confidentiality and integrity |
| MSS clamping | A fix | A firewall rule that rewrites the MSS option in the TCP SYN to a value that fits the tunnel |

## Further Reading

- **RFC 791** — *Internet Protocol*. Defines the DF bit in the IPv4 header.
- **RFC 792** — *Internet Control Message Protocol*. Defines ICMP Type 3 Code 4.
- **RFC 1191** — *Path MTU Discovery*. Defines the Next-Hop MTU field in the ICMP Type 3 Code 4 message and the PMTUD algorithm.
- **RFC 8201** — *Path MTU Discovery for IP version 6*. The IPv6 equivalent, where the DF bit is always set.
- **RFC 4890** — *Recommendations for Filtering ICMPv6 Messages in Firewalls*. Best practice for ICMP filtering that allows PMTUD to function.
- **Linux `ip-tunnel(8)`** — The tunnel creation command, including the `mtu` and `ttl` options.
- **Linux `ip-route(8)`** — The `advmss` route attribute and its effect on TCP MSS negotiation.
- **Wireshark display filter reference** — `ip.flags.df == 1`, `icmp.type == 3 && icmp.code == 4`, `tcp.options.mss`. Filters for isolating the relevant packets.
- **phases/04-network-layer-and-ip** — IP fragmentation and reassembly fundamentals.
- **phases/08-tcp-and-udp** — TCP MSS, the three-way handshake, and the SYN options.
- **phases/13-icmp** — ICMP message types and their wire format.
- **phases/17-integrated-troubleshooting-labs/19-icmp-redirect-pmtud-blackhole-df** — the deeper PMTUD failure class.
