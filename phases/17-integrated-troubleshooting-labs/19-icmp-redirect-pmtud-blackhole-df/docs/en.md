# ICMP Redirect and Path MTU Discovery Blackhole with DF

> A user reports: "Pings work, but every HTTPS connection to `https://download.example.com/big.iso` hangs for exactly 30 seconds and then either retries or fails." The first packet of the TLS handshake (a ClientHello) is 1,424 bytes — 14 bytes of Ethernet, 20 of IP, 20 of TCP, plus the ClientHello's 1,300 bytes of cipher suites, extensions, and ECH. The server's NIC has an MTU of 1,500. The path goes from the user, through a corporate VPN, through an IPsec tunnel, and out to the internet. The IPsec tunnel has an MTU of 1,420 (a typical AES-GCM-128 + SHA-256 + 20-byte outer IP value). The router on the path has the right MTU, the right MSS clamping, and the right DF handling — except the ICMP filter on the edge firewall is dropping outbound ICMP Type 3 (Destination Unreachable) and Code 4 (Fragmentation Needed and DF was set). The result: a 1,500-byte TCP segment is sent with the DF bit set, hits the 1,420-byte tunnel, cannot be fragmented, and is dropped silently. The sender never receives the ICMP that would have told it the path MTU is 1,420. After 30 seconds of `tcp_retries2` retransmits, the connection gives up. The diagnostic is the four-command chain: `ip route get <dest>`, `tracepath -m 5 <dest>`, `ip link show mtu` on every hop's egress, and a packet capture with a 1,500-byte DF-bit packet. The fix is to either (a) clamp the MSS on the tunnel interface to 1,380 (1,420 - 40 for IP+TCP), (b) enable ICMP Type 3 Code 4 outbound on the firewall, or (c) lower the effective MTU on the source host.

**Type:** Lab
**Languages:** Python, shell, scapy
**Prerequisites:** Phase 09 IP fragmentation and the DF bit, Phase 11 TCP MSS, ICMP Type 3 Code 4 (RFC 1191, RFC 8201)
**Time:** ~110 minutes

## Learning Objectives

- Diagnose a Path MTU Discovery black hole: large DF-bit packets disappear, the receiver's ICMP Type 3 Code 4 message is filtered, and the connection stalls at the path MTU rather than the link MTU.
- Apply the four-command chain: `ip route get`, `tracepath -m`, `ip link show mtu`, and a packet capture with a synthetic 1,500-byte DF-bit packet to identify the broken hop.
- Read the IPv4 "Don't Fragment" bit (bit 1 of the Flags field, RFC 791) and the ICMP Type 3 Code 4 "Fragmentation Needed and DF was set" message format (RFC 1191), and explain how PMTUD is supposed to use it.
- Distinguish three failure modes: (a) MTU black hole (DF-bit packet dropped silently), (b) PMTUD failure (ICMP Type 3 Code 4 filtered), (c) tunnel overhead (tunnel MTU smaller than path MTU but no MSS clamping).
- Compute the right MSS for a TCP connection that traverses a tunnel: `MSS = tunnel_MTU - 40` (for IPv4) or `tunnel_MTU - 60` (for IPv6 with extension headers).
- Build a Python script that constructs a synthetic IPv4 packet with the DF bit set, computes the right size, and prints the expected ICMP Type 3 Code 4 reply if the path is well-behaved.

## The Problem

The on-call SRE gets the ticket from the field: "SFTP to a partner site fails for files > 1 MB. SSH works for small commands. Web browsing works." The partner site is on a 1,500-byte Ethernet, the user is on a corporate IPsec tunnel. The same user has been pushing 100 MB files for two years; the change was a recent router firmware update that tightened ICMP filters.

The first thing to do is reproduce locally. The user can `ping download.example.com` and get a reply. The user can `curl -I https://download.example.com` and get a 200. The user can `scp small.txt user@download.example.com:` and it works. The user tries `scp big.iso user@download.example.com:` and it stalls for 30 seconds, then errors out.

The reason small works and big does not is the size of the first segment. The SSH client opens a TCP session, the MSS is negotiated (1,460 is typical for a 1,500-byte path), and the first data segment of an `scp` is the file content, broken into MSS-sized chunks. A 1,460-byte chunk fits a 1,500-byte MTU, so the first chunk makes it. But the *application* overhead of SSH includes a 16-byte packet header, so the effective data is 1,444 bytes — still under 1,500. The first chunk makes it. The second chunk is also 1,444 bytes — also makes it. The third chunk happens to be on a 1,420-byte tunnel because of an intermediate IPsec hop, and the *TCP* MSS that was negotiated was 1,460, so the sender sends a 1,460-byte segment. The tunnel cannot fragment (DF is set), and the ICMP Type 3 Code 4 from the tunnel is filtered at the egress firewall. The segment vanishes. The sender's RTO fires after 200 ms, the segment is retransmitted, the same thing happens. After 15 retransmits (the default `tcp_retries2`), the connection is given up.

The diagnostic move is to bypass the application and look at the path directly. The four commands:

```
ip route get 203.0.113.50                 # which interface, which next-hop
tracepath -m 5 203.0.113.50               # discover the path MTU
ip -d link show ipsec0                    # MTU on the tunnel interface
tcpdump -i any -w pmtud.pcap 'icmp or (host 203.0.113.50 and tcp)' & \
  ping -c1 -M do -s 1472 203.0.113.50     # DF-bit packet, 1500 bytes total
```

The `ping -M do -s 1472` is the diagnostic: it sends a 1,500-byte ICMP Echo Request with the DF bit set, and prints either "Reply from ..." (path is OK) or "Message too long, mtu=1420" (path is 1,420 and a working router returned ICMP Type 3 Code 4) or nothing (the packet was dropped silently — black hole).

## The Concept

### The DF bit and PMTUD

The IPv4 header's Flags field has three bits: the reserved bit (must be 0), the **DF bit** (Don't Fragment, RFC 791), and the MF bit (More Fragments). When a host sets the DF bit, it is asking routers not to fragment the packet; if the packet is too big for a downstream link, the router MUST drop it and return an ICMP Type 3 Code 4 message that includes the next-hop MTU (RFC 1191).

**Path MTU Discovery** (RFC 1191 for IPv4, RFC 8201 for IPv6) is the host's algorithm: send a packet with DF set, if you get an ICMP Type 3 Code 4 back, lower your estimate of the path MTU and retry; if you don't, the path is fine at that size. The end state is `path_MTU = min(link_MTU of every hop)`, cached in the kernel's `rtable` for 10 minutes by default.

The black hole is when the ICMP Type 3 Code 4 message is filtered between the host and the offending router. The packet is dropped, but the host never hears about it. PMTUD gives up, the host keeps trying at the size that was already too big, and the connection stalls.

### ICMP Type 3 Code 4 message format

The ICMP "Fragmentation Needed and DF was set" message has:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Type = 3  |    Code = 4   |          Checksum             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           unused = 0          |        Next-Hop MTU           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Internet Header + 64 bits of Original Data Datagram      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

The Next-Hop MTU is the MTU of the link that could not accept the packet, allowing the sender to skip the binary search and go straight to the new ceiling. The trailing 64 bits are the IP header + the first 64 bits of the original payload, which lets the sender match the ICMP reply to the right flow (using the IP ID, the inner IP header's source/destination, and the inner protocol).

### Tunnel overhead reduces effective MTU

A tunnel adds an outer IP header (20 bytes for IPv4, 40 for IPv6), and the inner protocol's headers are preserved. For a WireGuard tunnel, the overhead is 32 bytes (20 IP + 8 UDP + 4 WG + 0 padding for stream ciphers; 32 for AES-GCM with 16-byte tag and 16-byte Poly1305). For an IPsec tunnel in transport mode, the overhead is typically 36-50 bytes (ESP header + SPI + sequence + IV + integrity + padding). For a VXLAN tunnel, the overhead is 50 bytes (20 IP + 8 UDP + 8 VXLAN + 14 inner Ethernet). For a GRE tunnel, the overhead is 24 bytes (20 IP + 4 GRE).

The effective MTU of the inner interface is `outer_MTU − tunnel_overhead`. A 1,500-byte Ethernet link carrying a WireGuard tunnel has an effective inner MTU of 1,468. The MSS for TCP on that interface is `inner_MTU − 40 = 1,428` (for IPv4) or `inner_MTU − 60 = 1,408` (for IPv6 with extension headers).

### MSS clamping as a workaround

If PMTUD is broken (ICMP Type 3 Code 4 filtered), the next-best fix is to clamp the MSS on the tunnel. The router on the tunnel's egress rewrites the MSS option in the TCP SYN to a value the tunnel can carry. The standard `iptables` rule is:

```
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \
  -j TCPMSS --clamp-mss-to-pmtu
```

This sets the MSS to `path_MTU − 40`, which is the largest the path can carry. The sender's TCP will then never send a segment larger than that. The cost is the connection is now limited to the path MTU, not the link MTU, but the connection works.

### ICMP redirect (RFC 792, RFC 1122)

A different but related problem: an ICMP Redirect (Type 5) tells a host that a better route to a destination exists through a different gateway. The host is supposed to update its routing table (briefly) and use the new gateway. In modern networks, ICMP Redirect is rarely useful and frequently a security risk (it can be used to mount MITM attacks). Most routers do not send it; most hosts ignore it. The diagnostic signal: an ICMP Type 5 in the capture is a misconfiguration on the local router.

### How the simulator models this

`code/main.py` constructs a synthetic IPv4 packet with the DF bit set, computes the expected ICMP Type 3 Code 4 reply, and prints the verdict. The user picks a scenario (`--scenario black_hole`, `--scenario pmtud_ok`, `--scenario mss_clamp`), and the simulator prints the expected packet sizes, the ICMP message that should be returned, and the corrective action.

## Build It

1. **Reproduce the failure.** From a host behind a tunnel, run `scp bigfile user@<remote>:` and capture packets with `tcpdump -i any -w pmtud.pcap host <remote> and tcp`. Confirm the stall.
2. **Run the four-command chain.** `ip route get`, `tracepath`, `ip link show mtu`, `ping -M do`. Confirm the path MTU is 1,420.
3. **Apply the fix.** Add the `iptables` MSS-clamp rule to the tunnel egress and re-test. Confirm the file transfer completes.
4. **Run the simulator.** `python3 code/main.py --scenario black_hole` and `python3 code/main.py --scenario mss_clamp` should print the two verdicts.
5. **Ship the runbook.** A one-page runbook with the four commands and the MSS-clamp rule.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Find path MTU | `tracepath -m 5` output | Reports `pmtu 1420` |
| Confirm black hole | `ping -M do -s 1472` returns nothing | Path is broken; ICMP Type 3 Code 4 missing |
| Confirm PMTUD ok | `ping -M do` returns "Message too long, mtu=1420" | Path is well-behaved; sender can adjust |
| Verify MSS clamp | `iptables -t mangle -L -n -v` shows TCPMSS match | Rule in place; MSS limited to `path_MTU − 40` |
| Verify the fix | Re-run `scp bigfile`; transfer completes | No stall; throughput is `path_MTU × RTT` (BDP-limited) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **PMTUD black hole triage runbook** with the four-command chain and the MSS-clamp fix.
- A **before/after capture** of the same `scp` flow, showing the stall without MSS clamp and the clean transfer with it.

Start from `outputs/prompt-icmp-redirect-pmtud-blackhole-df.md`.

## Exercises

1. The path MTU is 1,400 (PPPoE link). Compute the right MSS for IPv4 TCP and for IPv6 TCP. Show the subtraction.
2. A `tracepath -m 5` reports `pmtu 1500` even though the tunnel MTU is 1,420. Why might this happen, and what is the consequence?
3. The egress firewall drops all outbound ICMP. The host sends a 1,500-byte DF-bit packet. List the order of events that follow and the timer that finally gives up.
4. Compute the inner MTU for a VXLAN tunnel carrying IPv4 over a 1,500-byte link. Then compute the MSS.
5. The MSS-clamp rule is added to the wrong chain (`INPUT` instead of `FORWARD`). What is the symptom, and how would you confirm the rule never matched?
6. An ICMP Type 5 redirect is sent by the local router to a host. The host is configured with `net.ipv4.conf.all.accept_redirects=0`. What does the host do with the redirect, and what is the security motivation?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DF bit | "Don't fragment" | The second bit in the IPv4 Flags field (RFC 791); forbids fragmentation downstream |
| PMTUD | "Path MTU discovery" | The algorithm that probes the path with DF-bit packets and adjusts to the smallest hop MTU (RFC 1191, RFC 8201) |
| MTU black hole | "Packets vanish" | A router drops a DF-bit packet too big for its link, but the ICMP Type 3 Code 4 message does not reach the sender |
| ICMP Type 3 Code 4 | "Frag needed" | The ICMP "Fragmentation Needed and DF was set" message (RFC 1191); carries the next-hop MTU |
| Tunnel overhead | "What the tunnel costs" | Bytes added by the tunnel's outer header (WireGuard 32, IPsec 36-50, VXLAN 50, GRE 24) |
| MSS clamp | "Cap the segment" | `iptables -t mangle ... -j TCPMSS --clamp-mss-to-pmtu`; rewrites the TCP MSS option to `path_MTU − 40` |
| ICMP redirect | "Use this gateway" | ICMP Type 5 (RFC 792); modern hosts and routers usually ignore or filter it |
| Next-Hop MTU | "Tunnel size" | The MTU the ICMP Type 3 Code 4 reply carries in its 16-bit field at offset 6 |

## Further Reading

- RFC 791 — Internet Protocol (Flags field, DF bit, fragmentation)
- RFC 792 — Internet Control Message Protocol (Type 3 Code 4 message format)
- RFC 1191 — Path MTU Discovery (IPv4)
- RFC 8201 — Path MTU Discovery for IPv6
- RFC 1122 — Requirements for Internet Hosts (ICMP redirect handling)
- RFC 4303 — IP Encapsulating Security Payload (ESP, tunnel overhead)
- `ip-route(8)`, `ip-link(8)`, `tracepath(8)`, `iptables-extensions(8)` man pages
- `tcpdump(8)` — `icmp` and `tcp` filters
