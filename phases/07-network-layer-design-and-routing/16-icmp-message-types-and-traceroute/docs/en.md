# ICMP Message Types and Traceroute

> ICMP is IP's error-reporting and diagnostic companion: every unexpected event a router encounters while forwarding a packet — TTL expiry, unreachable destination, required fragmentation blocked by DF — generates an ICMP message sent back to the packet's source, and Van Jacobson's traceroute exploits the TTL-expiry message to map the entire path to any destination without privileged network access.

**Type:** Lab
**Languages:** Python, shell, Wireshark
**Prerequisites:** IPv4 header format (TTL field, protocol field), ICMP encapsulation in IP, basic socket programming
**Time:** ~75 minutes

## Learning Objectives

- Identify the eight most important ICMP message types by number and code, and describe the exact network condition each one reports.
- Explain how traceroute exploits ICMP Time Exceeded (Type 11) messages to discover each router hop on a path without any special router support.
- Describe the structure of an ICMP message: Type (1 byte), Code (1 byte), Checksum (2 bytes), and type-specific data.
- Distinguish between ICMP messages that carry the original IP header plus 8 bytes of the failed packet, and those (Echo, Echo Reply) that carry arbitrary payload.
- Implement a traceroute-style hop discovery using raw sockets or ICMP echo probes with incrementing TTL values.
- Identify the failure modes that produce silent traceroute gaps: ICMP-filtering firewalls, load-balanced paths, routers that do not generate Time Exceeded.

## The Problem

A developer reports that connections from their application server to a partner API time out intermittently. `ping` to the partner IP succeeds. The developer concludes "the network is fine." You run `traceroute` and see that hops 7 through 9 return `* * *` (no response), and hop 10 is the partner's edge router. You need to determine whether those silent hops indicate a routing problem or just ICMP filtering — and you need to understand which ICMP message type would appear if the actual problem were a fragmentation black hole, a routing loop, or a misconfigured firewall blocking your protocol.

Without understanding ICMP message semantics, you cannot distinguish "router silently drops ICMP" (normal firewall policy) from "packet never arrives at hop 9" (routing black hole). This lesson gives you the exact message types, codes, and packet-level evidence needed to distinguish them.

## The Concept

### ICMP Overview

ICMP (Internet Control Message Protocol) is defined in RFC 792. It runs directly over IP (Protocol Number 1) and is used by routers and hosts to report errors and exchange diagnostic information. Every ICMP message is encapsulated in an IP datagram.

ICMP messages do not provide reliable delivery — an ICMP error message about a lost packet is not itself acknowledged. ICMP errors are generated only for the first fragment of a datagram (to prevent error storms). ICMP is never generated in response to another ICMP error (to prevent feedback loops).

### ICMP Message Format

All ICMP messages share a common header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Type      |     Code      |          Checksum             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Type-specific data                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      IP header + first 8 bytes of original datagram           |
|      (for error messages only)                                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Type (1 byte):** Message category.
- **Code (1 byte):** Sub-type within the category.
- **Checksum (2 bytes):** One's complement checksum of the ICMP message (header + data).
- For error messages: the body contains the IP header of the original failed packet plus the first 8 bytes of its payload. The 8 bytes is enough to include the source and destination port numbers of TCP or UDP, allowing the receiving host to identify which socket/connection caused the error.

### Principal ICMP Message Types

| Type | Name | Code (selected) | Meaning |
|------|------|-----------------|---------|
| 0 | Echo Reply | 0 | Response to a ping |
| 3 | Destination Unreachable | 0 = net unreachable | Router has no route to destination network |
| 3 | Destination Unreachable | 1 = host unreachable | Router has no route to destination host |
| 3 | Destination Unreachable | 2 = protocol unreachable | Host does not support the transport protocol |
| 3 | Destination Unreachable | 3 = port unreachable | Host has no process listening on that UDP port |
| 3 | Destination Unreachable | 4 = fragmentation needed, DF set | Path MTU discovery: packet too large, DF=1 |
| 3 | Destination Unreachable | 13 = admin prohibited | Firewall explicitly blocked the packet |
| 4 | Source Quench | 0 | (Deprecated) Request to slow down sending |
| 5 | Redirect | 0–3 | Inform host of a better route |
| 8 | Echo Request | 0 | Ping probe |
| 11 | Time Exceeded | 0 = TTL in transit | Packet's TTL reached zero at a router |
| 11 | Time Exceeded | 1 = frag reassembly timeout | Destination did not receive all fragments in time |
| 12 | Parameter Problem | 0 | Invalid field in IP header |
| 13 | Timestamp Request | 0 | Request for current time |
| 14 | Timestamp Reply | 0 | Response with timestamps |
| 17 | Address Mask Request | 0 | (Deprecated) Request for subnet mask |

**Type 3 Code 4** is the most operationally important for troubleshooting. When a router receives a DF=1 packet that is too large for the outgoing link, it generates this message and (per RFC 1191) includes the next-hop MTU in the unused 16-bit field of the ICMP header. Without this message, path MTU discovery fails.

### TTL and ICMP Time Exceeded

Every IPv4 packet carries a TTL (Time to Live) field, 1 byte, initialized by the sender (typical values: 64, 128, or 255 depending on OS). Each router that forwards the packet decrements TTL by 1. When TTL reaches 0, the router:
1. Drops the packet.
2. Sends ICMP Type 11 Code 0 (Time Exceeded, TTL in transit) back to the source.
3. The ICMP message body includes the original IP header and first 8 bytes of the original packet.

This mechanism prevents routing loops from circulating packets forever.

### Traceroute: Exploiting TTL Exhaustion

Van Jacobson invented traceroute in 1987. It requires no special router support. The algorithm:

```
for TTL = 1, 2, 3, ..., max_hops:
    send probe packet to destination with TTL = n
    wait for ICMP response:
        if ICMP Type 11 Code 0 received:
            record source IP of ICMP message (= router at hop n)
            record RTT
        if ICMP Type 0 (Echo Reply) or Type 3 Code 3 (Port Unreachable):
            destination reached; stop
        if timeout:
            print "*" (no response from this hop)
```

The ICMP Time Exceeded message is sent from the router that drops the packet. Its source IP address is the router's IP address — exactly the information traceroute needs.

**Classic Unix traceroute** sends UDP datagrams to a high, unlikely port (33434 + n). When the packet reaches the destination, the destination OS has no process on that port and sends ICMP Type 3 Code 3 (Port Unreachable). This signals the end of the path.

**Windows tracert** and many modern tools send ICMP Echo Request packets instead. The destination responds with ICMP Echo Reply (Type 0) to signal arrival.

```
Traceroute to 8.8.8.8:

 1  192.168.1.1     TTL=1 → ICMP Time Exceeded from 192.168.1.1 (home router)
 2  10.0.0.1        TTL=2 → ICMP Time Exceeded from 10.0.0.1 (ISP edge)
 3  172.16.5.2      TTL=3 → ICMP Time Exceeded from 172.16.5.2 (ISP core)
 4  * * *           TTL=4 → No response (ICMP filtered or no Time Exceeded sent)
 5  216.239.49.3    TTL=5 → ICMP Time Exceeded from Google backbone
 6  8.8.8.8         TTL=6 → ICMP Port Unreachable or Echo Reply (destination)
```

The `* * *` at hop 4 is ambiguous: the packet did reach hop 4 (it continued to hop 5), but that router does not generate ICMP Time Exceeded messages (common firewall policy).

### ICMP Echo and Ping

ICMP Type 8 (Echo Request) and Type 0 (Echo Reply) are the simplest diagnostic messages. The format carries:
- Identifier (2 bytes): identifies which process/socket sent the probe
- Sequence Number (2 bytes): incremented with each probe
- Data (variable): arbitrary, often a timestamp for RTT measurement

`ping` sends Echo Requests at 1-second intervals and reports RTT and loss statistics. It is the simplest test for "is host alive and responding to ICMP?"

### Redirect Messages

ICMP Type 5 (Redirect) is sent by a router when it receives a packet from a host that is using a suboptimal first-hop router. The router forwards the packet but tells the host: "for this destination, send directly to router X instead." Codes 0–3 specify whether the redirect applies to a network, host, network with TOS, or host with TOS.

Redirects are frequently disabled in modern networks for security reasons: an attacker can forge redirect messages to redirect traffic through a malicious router.

## Build It

```python
#!/usr/bin/env python3
"""
icmp_tracer.py — minimal traceroute-style hop discovery using ICMP Echo.
Requires root/administrator privileges for raw socket access.
Usage: sudo python3 code/main.py <destination>
"""
import socket
import struct
import time
import sys
import os

def checksum(data: bytes) -> int:
    """RFC 1071 one's complement checksum."""
    if len(data) % 2:
        data += b'\x00'
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) + data[i + 1]
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF

def build_icmp_echo(identifier: int, seq: int) -> bytes:
    """Build an ICMP Echo Request (Type 8, Code 0)."""
    icmp_type = 8
    code = 0
    payload = b'traceroute-probe'
    header = struct.pack('!BBHHH', icmp_type, code, 0, identifier, seq)
    csum = checksum(header + payload)
    header = struct.pack('!BBHHH', icmp_type, code, csum, identifier, seq)
    return header + payload

def trace(destination: str, max_hops: int = 30, timeout: float = 2.0):
    dest_ip = socket.gethostbyname(destination)
    print(f"traceroute to {destination} ({dest_ip}), {max_hops} hops max")

    identifier = os.getpid() & 0xFFFF

    for ttl in range(1, max_hops + 1):
        # Raw socket for sending ICMP
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

        # Raw socket for receiving ICMP (any ICMP)
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        recv_sock.settimeout(timeout)

        probe = build_icmp_echo(identifier, ttl)
        t_send = time.time()
        send_sock.sendto(probe, (dest_ip, 0))
        send_sock.close()

        try:
            data, addr = recv_sock.recvfrom(1024)
            t_recv = time.time()
            rtt_ms = (t_recv - t_send) * 1000

            # Parse ICMP: skip 20-byte IP header
            icmp_type = data[20]
            icmp_code = data[21]

            hop_ip = addr[0]
            try:
                hop_name = socket.gethostbyaddr(hop_ip)[0]
            except socket.herror:
                hop_name = hop_ip

            print(f"{ttl:3d}  {hop_name} ({hop_ip})  {rtt_ms:.2f} ms  "
                  f"[ICMP type={icmp_type} code={icmp_code}]")

            # Type 0 = Echo Reply (destination reached)
            # Type 3 = Destination Unreachable (also means destination reached)
            if icmp_type in (0, 3):
                break

        except socket.timeout:
            print(f"{ttl:3d}  * * *  (no response)")
        finally:
            recv_sock.close()

if __name__ == '__main__':
    if os.geteuid() != 0:
        print("Run as root: sudo python3 code/main.py <host>")
        sys.exit(1)
    target = sys.argv[1] if len(sys.argv) > 1 else '8.8.8.8'
    trace(target)
```

Run with:
```bash
sudo python3 code/main.py 8.8.8.8
# or trace a local gateway:
sudo python3 code/main.py 192.168.1.1
```

On systems where raw sockets are unavailable, use the OS traceroute:
```bash
# Linux/macOS (UDP probes by default)
traceroute 8.8.8.8

# Linux ICMP probes (requires root)
traceroute -I 8.8.8.8

# Windows
tracert 8.8.8.8
```

## Use It

| Scenario | ICMP type/code expected | How to observe |
|----------|------------------------|----------------|
| Host alive check | Type 8 sent, Type 0 received | `ping <host>` |
| Routing black hole (no route) | Type 3 Code 0 or 1 | `ping` returns "Destination Net/Host Unreachable" |
| PMTU black hole (DF=1, MTU mismatch) | Type 3 Code 4 | `ping -M do -s 1472 <host>` then filter `icmp.type==3 && icmp.code==4` in Wireshark |
| Routing loop detection | Type 11 Code 0 from same IP repeatedly | Traceroute shows same hop IP at multiple TTL values |
| Firewall blocking port | Type 3 Code 13 | `nmap` scan returns "admin-prohibited" |
| Traceroute to destination | Type 11 Code 0 at each hop, Type 0 or 3/3 at end | `traceroute 8.8.8.8` |
| Fragment reassembly timeout | Type 11 Code 1 | Rare; seen when fragments arrive at different rates |

Wireshark display filter for ICMP analysis:
```
icmp                          # all ICMP
icmp.type == 11               # Time Exceeded (traceroute hop responses)
icmp.type == 3 and icmp.code == 4   # PMTU black hole reports
icmp.type == 8 or icmp.type == 0    # ping request/reply only
```

## Ship It

Save a traceroute analysis to a file for baseline documentation:

```bash
sudo python3 code/main.py 8.8.8.8 > outputs/traceroute-$(date +%Y%m%d).txt

# On Linux, also capture ICMP packets during the trace for inspection:
sudo tcpdump -i any -w outputs/icmp-trace.pcap icmp &
TCPDUMP_PID=$!
traceroute -I 8.8.8.8
kill $TCPDUMP_PID
```

Runbook: ICMP-based path diagnostic checklist

```bash
# Step 1: Confirm basic reachability
ping -c 4 <destination>

# Step 2: Map the path
traceroute <destination>

# Step 3: Check for PMTU issues (DF=1 probes)
ping -M do -s 1472 -c 3 <destination>   # 1472 + 28 = 1500 bytes total
ping -M do -s 1024 -c 3 <destination>

# Step 4: Confirm ICMP Type 3 Code 4 if PMTU failure suspected
# (requires Wireshark/tcpdump)
sudo tcpdump -n 'icmp[0] == 3 and icmp[1] == 4'
```

## Exercises

1. **Message type identification:** A router drops a packet because the TTL field reached 0. It sends back an ICMP message. What are the Type and Code values? What is included in the ICMP message body? How many bytes of the original packet are included and why exactly 8 bytes?

2. **Traceroute gap analysis:** A traceroute shows hops 1–6, then `* * *` at hop 7, then a valid response at hop 8. List all possible explanations for the gap at hop 7. Which explanations can be ruled out given that hop 8 responds? Which ICMP message type would appear if hop 7 had a routing loop instead of just filtering?

3. **Implement ping:** Modify `code/main.py` to implement `ping`: send a sequence of ICMP Echo Requests (Type 8) at 1-second intervals, print RTT for each reply (Type 0), and print statistics (packets sent, received, loss %, min/avg/max RTT) on Ctrl-C. Use the Sequence Number field to detect out-of-order or duplicate replies.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| ICMP | "ping protocol" | Internet Control Message Protocol (RFC 792); IP's error reporting and diagnostic companion; Protocol Number 1 |
| Type 3 Code 4 | "fragmentation needed" | ICMP Destination Unreachable with code "fragmentation needed and DF set"; the core message in path MTU discovery |
| Type 11 Code 0 | "TTL exceeded" | ICMP Time Exceeded, TTL in transit; generated when a router decrements TTL to zero; exploited by traceroute |
| TTL | "hop count" | Time to Live; 8-bit IPv4 field decremented at each router; prevents routing loops; typical start values 64, 128, 255 |
| Echo Request / Reply | "ping" | ICMP Type 8 / Type 0; used to test host reachability and measure RTT |
| Source Quench | "deprecated throttle" | ICMP Type 4; former congestion signal from router to sender; deprecated in RFC 6633 (2012) |
| Redirect | "route correction" | ICMP Type 5; router tells a host to use a better first-hop router for a destination |
| Traceroute | "path mapper" | Diagnostic tool using TTL=1,2,3,... probes; maps each router hop by collecting ICMP Time Exceeded messages |
| * * * | "silent hop" | Traceroute output indicating no ICMP Time Exceeded response received; most often due to firewall filtering, not packet loss |

## Further Reading

- **RFC 792** (1981) — Internet Control Message Protocol; the original ICMP specification with all message formats.
- **RFC 1191** (1990) — Path MTU Discovery; defines use of ICMP Type 3 Code 4 with next-hop MTU in the unused header field.
- **RFC 6633** (2012) — Deprecation of ICMP Source Quench Messages; explains why Type 4 was removed.
- **RFC 4443** (2006) — ICMPv6 for IPv6; comparable message types for IPv6 (different numbering; Type 1 = Destination Unreachable, Type 3 = Time Exceeded).
- Jacobson, V., `traceroute(8)` manual page, 1987 — the original traceroute design in the man page.
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., Section 5.6.4 (Internet Control Protocols).
