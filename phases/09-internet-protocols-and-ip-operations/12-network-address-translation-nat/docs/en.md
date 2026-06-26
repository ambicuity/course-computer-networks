# Network Address Translation (NAT)

> NAT (RFC 3022) maps an entire private network behind a single public IP address by rewriting the IP source address and TCP/UDP source port on outbound packets, indexing the original (address, port) pair in a 65,536-entry translation table, and reversing the rewrite on inbound replies — turning the 16-bit source port field into the demultiplexing key that the IP header cannot provide.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** IPv4 addressing, CIDR, TCP/UDP port model, IP header structure
**Time:** ~75 minutes

## Learning Objectives

- Explain why IPv4 address exhaustion made NAT necessary and how dynamic address assignment only partially solves the problem.
- Identify the three RFC 1918 private address ranges and state why packets carrying these addresses must never appear on the public Internet.
- Trace the exact packet transformation performed by a NAT box on both outbound and inbound packets, including which fields are rewritten and why checksums must be recomputed.
- Calculate the maximum number of simultaneous internal hosts supportable through a single public IP address and why the first 4096 ports reduce that number from 65,536.
- Enumerate at least five architectural objections to NAT and map each one to the protocol principle it violates.
- Describe how NAT ALGs (Application Layer Gateways) patch protocols like FTP and H.323 that embed IP addresses in payload data.

## The Problem

A regional ISP has allocated a /16 address block — 65,534 usable host addresses. In 2005 it has 80,000 business subscribers, each of whom runs several always-on servers and workstations. Static allocation is impossible: there are not enough addresses. Dynamic assignment works only for intermittently connected hosts (dial-up, mobile); businesses that need 24/7 reachability cannot give up their addresses at night.

A home user subscribes to ADSL. She has two laptops, a desktop, a NAS device, and a smart TV — five hosts, all expecting simultaneous Internet access. Her ISP provides exactly one public IP address. Without NAT, four of her five devices have no globally routable address and cannot reach any Internet server.

The same ISP also finds that deploying IPv6 on all customer equipment will take years — hardware refresh cycles, firmware updates, ISP backbone upgrades, and application compatibility all create delay. The network needs a stopgap that works today on unmodified IPv4 equipment. NAT provides that stopgap, at the cost of a set of architectural compromises that become visible only when certain applications try to use the network in the way the original Internet design intended.

## The Concept

### Why IPv4 Addresses Are Scarce

IPv4 uses 32-bit addresses. The usable global address space is approximately 3.7 billion addresses after removing multicast, loopback, private, and reserved ranges. The Internet Assigned Numbers Authority (IANA) allocated its last IPv4 /8 blocks to the Regional Internet Registries in February 2011. With billions of smartphones, IoT devices, and always-on broadband customers, the demand for globally unique addresses far exceeds supply.

The IPv6 long-term fix uses 128-bit addresses (3.4 × 10³⁸), but deployment requires upgrading every router, OS, and application stack globally — a process that has been underway since RFC 2460 (1998) and is still incomplete.

### RFC 1918 Private Address Ranges

Three address blocks are reserved for private use (RFC 1918). Packets with these source or destination addresses must not appear on the global Internet — routers drop them at borders:

| Range | CIDR | Hosts |
|-------|------|-------|
| 10.0.0.0 – 10.255.255.255 | /8 | 16,777,216 |
| 172.16.0.0 – 172.31.255.255 | /12 | 1,048,576 |
| 192.168.0.0 – 192.168.255.255 | /16 | 65,536 |

The 10.0.0.0/8 range is the typical choice for home and enterprise networks because it is the largest single block and avoids the need to subnet aggressively.

### The NAT Translation Mechanism

The NAT box sits at the boundary between the private network and the ISP. It maintains a **translation table** with one entry per active TCP connection (or UDP flow).

```
Outbound packet transformation (private → public):

 Before NAT box:                  After NAT box:
 +-----------------+               +-----------------+
 | IP src: 10.0.0.1 |              | IP src: 198.60.42.12 |
 | IP dst: 93.184.216.34 |         | IP dst: 93.184.216.34 |
 | TCP src port: 5544 |            | TCP src port: 3344  |  ← index into table
 | TCP dst port: 80  |             | TCP dst port: 80    |
 +-----------------+               +-----------------+

Translation table entry created:
  external port 3344  →  (10.0.0.1, 5544)
```

```
Inbound packet transformation (public → private):

 Before NAT box:                  After NAT box:
 +-----------------+               +-----------------+
 | IP src: 93.184.216.34 |         | IP src: 93.184.216.34 |
 | IP dst: 198.60.42.12 |          | IP dst: 10.0.0.1  |   ← from table lookup
 | TCP src port: 80  |             | TCP src port: 80   |
 | TCP dst port: 3344 |            | TCP dst port: 5544 |  ← from table lookup
 +-----------------+               +-----------------+
```

After each field rewrite, the NAT box **recomputes both the IP header checksum and the TCP/UDP checksum**. IP checksum covers only the IP header (20 bytes minimum); the TCP checksum covers a pseudo-header plus the TCP segment. Both must be updated because source address and source port — fields covered by the respective checksums — have changed.

### Why the Source Port Is the Demultiplexing Key

The IP header has no spare field that could hold the original internal address. Adding a new IP option would require updating every router and host on the Internet — unacceptable as a quick fix.

Both TCP and UDP carry 16-bit source and destination ports. The NAT designers observed:

1. Most traffic is TCP or UDP.
2. The source port is chosen by the sender's OS from the ephemeral range (1024–65535 in practice, though officially 49152–65535 per RFC 6335).
3. Two internal hosts using the same ephemeral port (e.g., both happen to use port 5000) would create a conflict — the NAT box cannot distinguish them by port alone.

The NAT box therefore replaces the source port with a **synthetic index** into its own 65,536-entry table. This index is unique across all active connections through this NAT device. The table entry stores the original (IP address, port) pair. The mapping is established by the first outbound packet of a connection and aged out when the TCP connection closes (FIN/RST observed) or a UDP idle timer expires (typically 5 minutes for UDP, up to several hours for established TCP).

### Capacity Calculation

With a single public IP address:
- 16-bit port field → 65,536 total entries
- Ports 0–4095 (4096 entries) are reserved or commonly used for well-known services
- Maximum simultaneous internal hosts: **65,536 − 4,096 = 61,440**

If the ISP assigns the customer multiple public addresses, each adds another 61,440 entries.

### Architectural Objections to NAT

The networking community documented objections in RFC 2993. The core violations are:

| # | Violation | Detail |
|---|-----------|--------|
| 1 | Unique address model | RFC 791 states every IP address uniquely identifies one machine. NAT allows thousands of devices to share 10.0.0.1. |
| 2 | End-to-end connectivity | The mapping is created by outbound packets only. A remote host cannot initiate a connection to a device inside NAT without prior configuration. Peer-to-peer protocols, game servers, and VoIP calling fail by default. |
| 3 | Connectionless network made stateful | The NAT box must maintain per-connection state. If it crashes, all active TCP connections are destroyed — behavior identical to a circuit-switched network failure, not an IP router failure. |
| 4 | Protocol layering | NAT modifies Layer 4 (TCP/UDP) ports inside the transport layer payload while operating as a network-layer device. If TCP is later redesigned with 32-bit ports, every NAT box on the Internet breaks. |
| 5 | Transport protocol dependence | NAT works only for TCP and UDP. Any protocol that uses a different transport (e.g., SCTP, custom protocols) cannot be NATted without special support. |
| 6 | Application payload blindness | Some protocols embed IP addresses inside their application payload (FTP PORT command, H.323, SIP). NAT sees only headers; it does not rewrite payload addresses, so these applications break silently. |

### NAT Application Layer Gateways

To fix objection 6, NAT implementations include **ALGs (Application Layer Gateways)**: protocol-specific inspection modules that parse known application protocols, find embedded IP addresses or ports, and rewrite them.

Example: FTP in active mode sends `PORT 10,0,0,1,21,8` in the command channel to tell the server what address and port to connect back to. An FTP ALG intercepts this, rewrites the embedded address to the public IP, and updates the NAT table to accept the incoming data connection. Every new application that embeds network addresses requires a new ALG — demonstrating why this approach is fragile.

### NAT Traversal

When two hosts behind different NAT boxes need a direct connection (VoIP, WebRTC, peer-to-peer):

1. **STUN (RFC 5389):** Each client contacts a public STUN server, which reflects the client's observed public IP and port. Both clients exchange these via a signaling server.
2. **ICE (RFC 8445):** Tries multiple candidate address pairs (STUN-reflexive, relay) in priority order until one works.
3. **TURN (RFC 5766):** If direct connectivity fails, traffic relays through a public server — eliminating the end-to-end property entirely.

```
Host A (behind NAT-A)          STUN server          Host B (behind NAT-B)
       |                            |                       |
       |--- STUN Binding Request -->|                       |
       |<-- Response: A_pub:A_port -|                       |
       |                            |<-- STUN Binding Req --|
       |                            |- Response: B_pub:B_port -->|
       |                (exchange via signaling server)          |
       |<--------------- direct UDP hole-punch attempt ---------->|
```

## Build It

`code/main.py` implements a NAT table simulator with outbound packet rewriting and inbound lookup:

```python
import struct, socket, binascii, random

class NATTable:
    def __init__(self, public_ip):
        self.public_ip = public_ip
        # ext_port -> (private_ip, private_port)
        self.table = {}
        # (private_ip, private_port) -> ext_port
        self.reverse = {}
        self._next_port = 4096

    def _alloc_port(self):
        port = self._next_port
        self._next_port = (self._next_port % 61439) + 4096
        return port

    def outbound(self, private_ip, private_port):
        key = (private_ip, private_port)
        if key not in self.reverse:
            ext_port = self._alloc_port()
            self.table[ext_port] = key
            self.reverse[key] = ext_port
        return self.public_ip, self.reverse[key]

    def inbound(self, ext_port):
        return self.table.get(ext_port)

    def dump(self):
        print(f"{'Ext Port':<12} {'Private IP':<16} {'Private Port'}")
        print("-" * 40)
        for ep, (ip, pp) in sorted(self.table.items()):
            print(f"{ep:<12} {ip:<16} {pp}")

def ip_checksum(header_bytes):
    if len(header_bytes) % 2:
        header_bytes += b'\x00'
    s = sum(struct.unpack('!%dH' % (len(header_bytes)//2), header_bytes))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF

def demo():
    nat = NATTable("198.60.42.12")
    # Three internal hosts making connections
    clients = [
        ("10.0.0.1", 5000),
        ("10.0.0.2", 5000),   # same private port, different IP
        ("10.0.0.1", 5001),
    ]
    print("=== Outbound translations ===")
    for priv_ip, priv_port in clients:
        pub_ip, pub_port = nat.outbound(priv_ip, priv_port)
        print(f"  {priv_ip}:{priv_port} -> {pub_ip}:{pub_port}")

    print("\n=== NAT table ===")
    nat.dump()

    print("\n=== Inbound lookup for ext port 4096 ===")
    result = nat.inbound(4096)
    print(f"  -> {result}")

if __name__ == "__main__":
    demo()
```

Run with:
```
python3 code/main.py
```

No external dependencies required. Expected output shows three distinct external ports assigned — including separate entries for the two hosts that both chose private port 5000 — and the correct reverse lookup.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Observe NAT in action | `curl -s ifconfig.me` from inside a NATted network | Returns the router's public IP, not 10.x or 192.168.x |
| Inspect NAT table on a Linux router | `conntrack -L` or `cat /proc/net/nf_conntrack` | Shows per-connection state with original and translated tuples |
| Identify private addresses in a packet capture | Open a Wireshark capture, filter `ip.src == 10.0.0.0/8` | Frames present only on the LAN segment, stripped before ISP |
| Test inbound failure | Run a server on an internal host, try to reach it from outside without port forwarding | Connection refused or timeout — no entry in NAT table |
| Force a NAT capacity exhaustion | Open 61,440+ simultaneous connections from one IP | New connections are dropped; existing ones continue |

## Ship It

The `code/main.py` NAT simulator can be used as a test harness. Run it and redirect output:

```
python3 code/main.py > outputs/nat-table-demo.txt
```

To observe real NAT state on a Linux gateway:
```bash
# View current connection tracking table (requires conntrack-tools)
conntrack -L --output extended 2>/dev/null | head -40

# Count active NAT entries
conntrack -L 2>/dev/null | wc -l

# Show only TCP established mappings
conntrack -L -p tcp --state ESTABLISHED 2>/dev/null
```

## Exercises

1. **Port exhaustion calculation:** A small ISP gives each customer one public IPv4 address. Customer A runs a load test that opens 1,000 simultaneous HTTP connections per second from a single internal host. After how many seconds will the NAT table be exhausted? What happens to the 61,441st connection attempt?

2. **Checksum recomputation trace:** A packet has source IP 10.0.0.5, source port 8080. The NAT box changes source IP to 203.0.113.7 and source port to 4100. List every header field in both the IP header and the TCP header that must be updated, and explain why each one changes.

3. **FTP active mode failure:** A host at 10.0.0.1 behind NAT sends `PORT 10,0,0,1,20,5` (decimal octets of IP address, then port as two bytes: 20×256+5 = 5125) to an FTP server. Without an ALG, what does the server see when it tries to open the data connection? Describe the failure mode precisely.

4. **STUN hole-punching:** Host A is behind NAT-A (public IP 198.51.100.1) and Host B is behind NAT-B (public IP 203.0.113.1). Both contact STUN server 8.8.8.8 and learn their public (IP, port). Sketch the UDP hole-punching sequence that allows them to communicate directly. What assumption must both NAT boxes satisfy for this to work?

5. **NAT and TCP connection state:** A user's TCP connection to a web server passes through a NAT box. The NAT box crashes and restarts with an empty table 10 seconds into the connection. Describe exactly what happens to the TCP connection on both ends, contrasting this with what would happen if a plain IP router (no NAT) crashed and restarted.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| NAT | "the router rewrites addresses" | Network Address Translation; a device that rewrites IP addresses and transport-layer ports to share one public IP among many private hosts |
| RFC 1918 | "private address space" | Three address ranges (10/8, 172.16/12, 192.168/16) reserved for private use; these addresses must not be routed on the global Internet |
| Translation table | "NAT table" | Per-connection mapping from (public IP, ext port) to (private IP, private port); created by first outbound packet, aged out on connection close |
| Port forwarding | "opening a port" | Static NAT table entry that maps an inbound (public IP, port) to a fixed (private IP, port) before any outbound packet is seen |
| Hairpin NAT | "NAT loopback" | Configuration allowing internal hosts to reach internal servers using the server's public IP address |
| ALG | "protocol helper" | Application Layer Gateway; NAT extension that parses specific protocols (FTP, SIP, H.323) and rewrites embedded IP addresses in the payload |
| STUN | "get my public IP" | Session Traversal Utilities for NAT (RFC 5389); a protocol that lets a host discover its NAT-translated public address and port |
| Endpoint-independent NAT | "full cone NAT" | NAT variant in which a (private IP, port) always maps to the same external port, regardless of destination — enables hole-punching |
| Symmetric NAT | "strict NAT" | NAT variant in which a different external port is used for each distinct destination; breaks STUN hole-punching |

## Further Reading

- **RFC 3022** (2001) — Traditional IP Network Address Translator (Traditional NAT); the canonical specification describing NAT operation, the translation table, and handling of ICMP.
- **RFC 1918** (1996) — Address Allocation for Private Internets; defines the three private address ranges and the rule against routing them on the public Internet.
- **RFC 2993** (2000) — Architectural Implications of NAT; documents the objections from the networking community, including end-to-end, layering, and protocol-independence violations.
- **RFC 5389** (2008) — Session Traversal Utilities for NAT (STUN); the protocol clients use to discover their public IP and port through a NAT box.
- **RFC 8445** (2018) — Interactive Connectivity Establishment (ICE); the framework used by WebRTC and VoIP to negotiate direct connectivity between peers behind NAT.
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., Pearson 2011 — Section 5.6.2 (NAT); source textbook for this course.
