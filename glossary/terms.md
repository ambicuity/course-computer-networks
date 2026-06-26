# Glossary Terms

### ARP

**What people say:** The thing that turns an IP into a MAC address.

**What it actually means:** A broadcast-based link-layer protocol (not IP) that lets a host ask the whole local segment, "Who has 192.168.1.5? Tell 192.168.1.10." The reply carries the target's MAC, which the sender caches in its ARP table with a timeout (typically minutes). In Wireshark you see an ARP Request as a broadcast (opcode 1, sender MAC/IP, target IP) and a unicast ARP Reply (opcode 2). If you never see a reply, the target is down, on a different VLAN, or silently dropping the broadcast. Entries expire, which is why a working host can suddenly pause for one frame while it re-resolves.

### Bandwidth

**What people say:** How fast the network is.

**What it actually means:** The raw bit capacity of a link in bits per second, nothing more. It is the ceiling on how fast bits can leave an interface, distinct from latency (the delay before the first bit arrives) and throughput (useful payload delivered after headers, retransmissions, and congestion). A 1 Gbps link can still deliver only 40 Mbps of useful data if TCP is in congestion avoidance on a high-RTT path. In a tcpdump capture bandwidth shows up as the inter-packet spacing, not as a field you can read.

### Bridge

**What people say:** A box that joins two networks.

**What it actually means:** A Layer 2 device that forwards Ethernet frames between segments by reading the destination MAC and looking it up in a MAC-to-port table it learned from source MACs of incoming frames. Unknown unicast and broadcast get flooded out all ports except the ingress. In a multi-port capture you can spot bridge behavior by watching the same frame appear on several interfaces. Spanning Tree (STP) sends BPDUs to block redundant ports so frames don't loop forever, and you can watch those BPDUs in Wireshark on a bridge's links.

### Circuit switching

**What people say:** How old telephones worked.

**What it actually means:** A dedicated end-to-end path is reserved before any data flows, and that path's capacity is held whether it carries traffic or not. Setup signaling (ISDN Q.931, SS7) builds the circuit, then samples flow in fixed timeslots with no per-packet addressing, header, or queueing decision along the way. There are no data packets to capture mid-call, only the setup messages. The channel is a reserved slot, not a shared queue, which is why it is inefficient for bursty data but perfectly predictable for voice.

### Congestion control

**What people say:** Traffic management.

**What it actually means:** The sender-side algorithm (mainly in TCP) that reduces its sending rate when it infers network stress from duplicate ACKs, retransmission timeouts, or ECN marks. The congestion window (cwnd) is never a field on the wire, you infer it from the send pattern in a trace. Wireshark shows retransmissions clustering and the receive window shrinking as symptoms; the actual AIMD logic, add a segment per RTT on success, halve on loss, plays out as the spacing between sent segments widens and narrows over time.

### CRC

**What people say:** The error check at the end of a frame.

**What it actually means:** A polynomial division over the frame bits that produces a remainder appended to the frame, which the receiver recomputes and compares. Ethernet uses CRC-32 in the 4-byte FCS field at the end of every frame. In Wireshark a corrupted frame shows "Frame check sequence: 0x... [incorrect]," and the NIC usually drops it before the OS sees it. CRC catches burst errors well but is not cryptographic, it can be spoofed or collide by chance, so it is integrity checking, not security.

### CSMA/CD

**What people say:** How Ethernet works.

**What it actually means:** Carrier Sense Multiple Access with Collision Detection: a station listens for a quiet medium, transmits, and if it senses a collision (voltage collision on the wire) it sends a jam signal, waits a binary-exponential-backoff time, and retries. You can't capture the collision itself, but on a saturated shared segment you see elevated frame counts and retransmitted frames. It is largely historical on modern switched full-duplex links where each direction has its own wire and collisions are impossible, though the spec still requires it for half-duplex.

### DNS

**What people say:** Turns names into IP addresses.

**What it actually means:** A distributed, hierarchical, cached query-response protocol that runs over UDP/53 (and TCP/53 for large responses or zone transfers). A dig trace or Wireshark capture shows a Query with a QNAME, QTYPE (A, AAAA, MX, TXT, CNAME, and so on), and QCLASS, followed by a Response carrying Resource Records each with a TTL. The TTL is how long a resolver may cache the answer, and stale cached TTLs are the root of most "DNS changed but the app still hits the old server" outages.

### Ethernet

**What people say:** The network cable.

**What it actually means:** A family of IEEE 802.3 Layer 1 and 2 standards that frame data into a fixed envelope: 6-byte destination MAC, 6-byte source MAC, 2-byte EtherType (0x0800 for IPv4, 0x86DD for IPv6, 0x0806 for ARP), payload, and 4-byte FCS. In tcpdump with `-e` you see the MAC addresses and EtherType; frame size runs 64 to 1518 bytes (or up to 9000 with jumbo frames). Every higher-layer packet rides inside one of these frames, which is why reading a capture starts with the Ethernet header.

### Flow control

**What people say:** Slowing the sender down.

**What it actually means:** A receiver-driven mechanism that tells the sender how much buffer space it can accept, so the receiver is not overrun. In TCP this is the Window field in the segment header. In Wireshark watch the `Window` value shrink as the receiver applies backpressure; a zero window followed by periodic window updates is a normal pause, not a failure. This is distinct from congestion control, which is the sender reacting to network loss, not to the receiver's state.

### Frame

**What people say:** A packet.

**What it actually means:** The Layer 2 unit that actually hits the wire: the complete envelope of destination MAC, source MAC, EtherType, payload (which is an IP packet), and FCS. In tcpdump `-e` you see the MAC headers, and in Wireshark the top of the dissection tree reads "Frame N: ... length X on wire." A packet is the Layer 3 content inside the frame, the frame is what the NIC transmits and what a switch forwards. Mixing the two words is common but they describe different layers.

### HTTP

**What people say:** The web.

**What it actually means:** A text-based, stateless request-response protocol that runs over TCP (or QUIC in HTTP/3). A `curl -v` or Wireshark follow of a TCP stream shows a request line like `GET /path HTTP/1.1`, headers, an optional body, and a response with a status code (200, 301, 404, 500) and its own headers. Because the protocol is stateless, sessions are bolted on with cookies, tokens, or server-side state; each request is independent and carries everything the server needs to answer it.

### IP

**What people say:** The address.

**What it actually means:** A connectionless, best-effort Layer 3 protocol that prepends a header carrying source and destination IP addresses, a TTL, a protocol number (6 for TCP, 17 for UDP, 1 for ICMP), and fragment fields to a payload, then hands the result to Layer 2 for framing. In Wireshark the IP header dissection shows version, IHL, total length, identification, flags, fragment offset, TTL, and checksum. IP guarantees nothing, not delivery, not order, not integrity. Recovery is the job of TCP or the application.

### Latency

**What people say:** Lag.

**What it actually means:** The time a packet takes from source to destination, decomposed into propagation (distance over speed of light in the medium), transmission (frame size over bandwidth), queueing (buffers in routers and switches), and processing (stack time on each hop). Ping measures ICMP round-trip time; in Wireshark the gap between a TCP SYN and the matching SYN-ACK is your one-way handshake latency. Latency is independent of bandwidth, a 10 Gbps link to a geosynchronous satellite still has roughly 600 ms RTT.

### NAT

**What people say:** Sharing one public IP.

**What it actually means:** A stateful rewrite of the source IP and port (outbound) or destination IP and port (inbound) in packet headers, tracked in a translation table on the NAT device. Capturing on the inside versus the outside interface shows the same packet with different addresses and ports; the table maps an inside local tuple to an inside global tuple. NAT breaks end-to-end address visibility and requires explicit port forwarding for inbound flows, which is why a home host at 192.168.1.10 appears to the world as one public address.

### Packet

**What people say:** Data on the wire.

**What it actually means:** The Layer 3 unit: the IP header plus payload, before it is wrapped in a frame. In Wireshark the IP layer is the packet, and once it is encapsulated with MAC headers and FCS it becomes a frame. Packets larger than the path MTU get fragmented into multiple IP fragments sharing one identification number with different offset values, which you can read in the IP header dissection. Reassembly happens at the destination, not at routers.

### Protocol

**What people say:** A rule for networking.

**What it actually means:** A precise specification of message formats, header fields, state machines, timers, and error handling that two endpoints agree to follow, usually normatively defined in an RFC. A protocol dictates what bytes go on the wire in what order. In Wireshark the dissection tree is literally the protocol's fields decoded per the spec, and a missing or malformed field is a protocol violation, not just a software bug. Without the protocol definition the capture is unreadable bytes.

### QoS

**What people say:** Giving traffic priority.

**What it actually means:** A set of mechanisms that classify, mark, queue, and schedule packets so some traffic classes get preferential treatment when congestion hits. Ethernet carries priority in the 3-bit 802.1p field of the VLAN tag (values 0 to 7); IP carries it in the 6-bit DSCP field of the TOS byte. In a capture you see DSCP values like EF (46) for voice or AF31 for video, and routers use these to pick which queue drains first. QoS does not create bandwidth, it reallocates the existing capacity under contention.

### Router

**What people say:** Connects networks together.

**What it actually means:** A Layer 3 device that receives a framed IP packet, strips the frame, decrements the TTL, recomputes the IP header checksum, looks up the destination prefix in its forwarding table, and re-frames the packet on the egress interface with a fresh MAC header. In a traceroute each router appears as a hop because the TTL-exceeded ICMP message comes from the router's ingress interface. A router makes a per-packet forwarding decision and keeps no per-flow state, unless NAT or a stateful firewall is also enabled on it.

### Routing

**What people say:** Finding the path through the network.

**What it actually means:** The process of building and consulting a forwarding table that maps destination prefixes to next-hop interfaces, populated by static config or by dynamic protocols like distance-vector (RIP) or link-state (OSPF, IS-IS). In Wireshark OSPF shows up as Hello, LSU, and LSA packets (IP protocol 89) flooding link-state information, and BGP uses TCP/179 to exchange Network Layer Reachability Information. The control plane builds the table, the data plane forwards per packet; a routing loop is a control-plane failure that manifests as a storm of TTL-exceeded messages.

### Socket

**What people say:** A connection.

**What it actually means:** An OS kernel endpoint that binds a local IP and port to a transport protocol (TCP or UDP) and hands the application a file descriptor to read and write. A TCP socket carries a state machine (SYN_SENT, ESTABLISHED, CLOSE_WAIT, and so on) visible in `ss` or `netstat`; a UDP socket is connectionless but still bound to a port. In Wireshark a socket corresponds to a 4-tuple of source IP, source port, destination IP, destination port, and closing it is a FIN and FIN-ACK exchange, not just a function call.

### TCP

**What people say:** The reliable protocol.

**What it actually means:** A connection-oriented, byte-stream transport that opens state with a three-way handshake (SYN, SYN-ACK, ACK), numbers every byte with a sequence number, acknowledges received data with ACK numbers, and tears down with FIN. In Wireshark you read seq and ack numbers, flags (SYN, ACK, PSH, RST, FIN), and the window size; retransmissions appear as duplicate segments carrying the same sequence. TCP guarantees in-order, unduplicated delivery to the receiving socket, but it guarantees no timing, no minimum latency, and no maximum delay.

### TLS

**What people say:** Encryption for the web.

**What it actually means:** A protocol layered on TCP that negotiates a symmetric session key with an asymmetric handshake (ClientHello, ServerHello, certificate, key exchange, Finished) so application data is encrypted and integrity-protected with AEAD ciphers such as AES-GCM. In Wireshark you always see the handshake and certificate chain, but the ApplicationData records are opaque unless you log the session keys via `SSLKEYLOGFILE` and feed them to the dissector. TLS authenticates the server (and optionally the client) and protects confidentiality and integrity, but it does nothing for availability.

### UDP

**What people say:** The unreliable protocol.

**What it actually means:** A connectionless transport that prepends an 8-byte header (source port, destination port, length, checksum) to an application payload and sends the result as a single IP datagram, with no handshake, no ACKs, and no retransmission. In Wireshark each UDP segment is one packet, and DNS, DHCP, SNMP, and RTP commonly ride it. "Unreliable" means the protocol does nothing to recover lost packets, not that it is broken; query-response and real-time apps prefer it because there is no head-of-line blocking waiting for a lost packet to be resent.

### VLAN

**What people say:** Separating networks on a switch.

**What it actually means:** A Layer 2 tagging scheme (IEEE 802.1Q) that inserts a 4-byte tag after the source MAC, carrying a 12-bit VLAN ID (1 to 4094) and a 3-bit priority, so one physical switch can carry multiple isolated broadcast domains over the same links. In Wireshark with 802.1Q enabled you see the tag in the Ethernet header; a trunk port carries tagged frames for many VLANs, an access port carries untagged frames for one VLAN. Broadcast stays inside the VLAN unless a router (or Layer 3 switch) routes between them.

### VPN

**What people say:** A secure tunnel.

**What it actually means:** An encapsulation that takes packets from one IP network and wraps them inside packets of a transport network, often encrypted with IPsec ESP, WireGuard, or OpenVPN over TLS. Capturing on the outside link shows ESP (IP protocol 50) or UDP to a VPN port, and the inner packet is invisible inside; with the session key you can decrypt and see the original IP header. A VPN provides confidentiality and integrity over an untrusted path, but it does not make the network behind it safe, it just extends it.

### Wi-Fi

**What people say:** Wireless internet.

**What it actually means:** A set of IEEE 802.11 standards in which stations contend for the air with CSMA/CA: listen, random backoff, optional RTS/CTS, then data and an ACK. Radios cannot reliably detect collisions mid-transmission the way wired Ethernet can, so the protocol avoids them rather than detects them. In a monitor-mode capture you see 802.11 management frames (Beacons, Probes, Association), a MAC header with up to four address fields, and retransmissions when the ACK did not come back. A regular wired capture only shows the 802.3 frame after the access point converted it, so debugging Wi-Fi itself requires monitor mode.

### Wireshark

**What people say:** A packet sniffer.

**What it actually means:** A graphical packet analyzer that decodes captured bytes into a protocol dissection tree, shows per-frame timing, TCP sequence and ack numbers, reassembled streams, and lets you filter with display expressions like `ip.addr == 1.2.3.4` or `tcp.flags.syn == 1`. It reads libpcap files from tcpdump and live interfaces, and the dissection is interpretive, so an encrypted or malformed field shows as "malformed packet" or raw bytes rather than a clean decode. It is the main tool for comparing what the RFC says should happen with what actually came off the wire.