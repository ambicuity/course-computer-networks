# The OSI Reference Model to The Model Used in This Book

> The seven-layer ISO OSI Reference Model (ISO/IEC 7498-1, revised 1994) is a *model*, not a protocol stack: layers 1-3 (Physical, Data Link, Network) are chained hop-by-hop, while layers 4-7 (Transport, Session, Presentation, Application) run end-to-end between source and destination hosts. The competing TCP/IP model (Cerf & Kahn, 1974; RFC 1122) collapses these into four layers — Link, Internet (IP/ICMP), Transport (TCP/UDP), Application (HTTP, SMTP, DNS, RTP) — and drops Session and Presentation as redundant. OSI's strength is the model; TCP/IP's strength is the protocols. Tanenbaum resolves this by teaching from a **five-layer hybrid**: Physical, Link, Network, Transport, Application. Each layer adds its own Protocol Data Unit (PDU) — a TCP segment becomes an IP packet (RFC 791) becomes an Ethernet frame (IEEE 802.3) becomes bits on the wire — and every encapsulation step prepends a header you can read in a packet capture. This lesson shows how to map any symptom to the layer that owns it, and ships a Python tool that encapsulates and then dissects a five-layer stack frame so the layering becomes concrete rather than memorized.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Lessons 01-05 of Phase 1 (protocol hierarchies, services vs. protocols, connection-oriented vs. connectionless service)
**Time:** ~75 minutes

## Learning Objectives

- Recite the seven OSI layers, the four TCP/IP layers, and the five-layer book model, and state exactly which OSI layers each book layer absorbs.
- Classify a layer as **chained** (hop-by-hop: Physical, Link, Network) or **end-to-end** (Transport and above), and explain why a router never touches a TCP header.
- Name the PDU and header at each layer (bit, frame, packet, segment, message) and identify the addressing each uses (no address, MAC, IP, port, name).
- Map a concrete symptom — duplex mismatch, MTU black hole, routing loop, port unreachable — to the single layer that owns it.
- Encapsulate an application message down the five-layer stack and dissect it back up using `code/main.py`, reading each header field.

## The Problem

A user reports: "The website is slow and sometimes the page just doesn't load." That single sentence could be caused at any layer:

- **Physical:** a half-duplex/full-duplex mismatch on a copper link producing late collisions and retransmits.
- **Link:** an MTU of 1500 on Ethernet but a 1492-byte path over PPPoE, so a 1500-byte frame is silently dropped (an **MTU black hole**).
- **Network:** an IP routing loop bouncing the packet until its TTL (RFC 791, 8-bit field) hits 0 and an ICMP Time Exceeded (Type 11) is returned.
- **Transport:** a TCP three-way handshake whose SYN never gets an ACK because a firewall sends RST, or a server returning `ICMP Port Unreachable` (Type 3, Code 3) for a UDP probe.
- **Application:** a DNS lookup (UDP/53) timing out, so the name never resolves and the browser never even opens a socket.

Without a layered model you guess. With one, you bisect: you ask "at which layer does the evidence first disappear?" and you only need to test the layer above and below your hypothesis. The OSI/TCP-IP/book mapping is the index that makes that bisection possible. The reference SVG, `assets/the-osi-reference-model-to-the-model-used-in-this-book.svg`, is exactly that index drawn as three aligned columns.

## The Concept

### The three models side by side

| Book (5) | OSI (7) | TCP/IP (4) | PDU | Address | Example protocol/standard |
|---|---|---|---|---|---|
| Application | Application, Presentation, Session | Application | Message / data | Name (FQDN) | HTTP, SMTP, DNS, RTP |
| Transport | Transport | Transport | Segment (TCP) / Datagram (UDP) | Port (16-bit) | TCP, UDP |
| Network | Network | Internet | Packet | IP address (32/128-bit) | IP, ICMP |
| Link | Data Link | Link | Frame | MAC (48-bit) | Ethernet (802.3), 802.11 |
| Physical | Physical | (part of Link) | Bit / symbol | none | Twisted pair, fiber, SONET |

The book model deletes OSI's **Presentation** and **Session** layers — experience showed most applications either don't need them or roll their own (TLS handles presentation-style encoding and session resumption inside the application stack today). It keeps the OSI **Network/Link/Physical** split, which TCP/IP blurs into a single under-specified "Link" interface.

### Chained vs. end-to-end layers

This is the most operationally important distinction in the whole chapter. In Figure 1-20, layers 1-3 are drawn *between each pair of adjacent boxes* (Host A — Router — Router — Host B), while layers 4-7 are drawn as one arc straight from Host A to Host B.

- **Chained (1-3):** Physical, Link, Network. Each hop re-runs these. A router **decrements the IP TTL, recomputes the IP header checksum, and rewrites the layer-2 frame header** (new source/destination MAC) at every hop. The frame from your laptop to your gateway is destroyed and a new frame is built for the next link.
- **End-to-end (4-7):** Transport and above. A router **never reads or modifies a TCP/UDP header** in normal forwarding. The TCP sequence numbers, window, and checksum set by the source host are read only by the destination host. This is why TCP can survive a route change mid-connection: the chained layers reroute underneath while the end-to-end conversation continues.

Failure-mode consequence: if a middlebox *does* rewrite a port (NAT) or reset a connection (stateful firewall RST), it is violating the end-to-end property of layer 4 — and that is precisely why NAT traversal and firewall debugging are layer-4 problems even though the box lives "in the network."

### Encapsulation: one message, four headers

When a browser sends `GET / HTTP/1.1`, the message is wrapped on the way down. Each layer prepends its header (and Link adds a trailer):

```
[ Eth hdr | IP hdr | TCP hdr | HTTP "GET / HTTP/1.1\r\n..." | Eth FCS ]
  14 bytes  20 bytes  20 bytes      payload                    4 bytes
```

- **Ethernet header (IEEE 802.3):** 6-byte dest MAC, 6-byte src MAC, 2-byte EtherType (`0x0800` = IPv4). 4-byte FCS trailer carries a CRC-32.
- **IP header (RFC 791):** 20 bytes minimum — Version/IHL, TTL, Protocol (`6` = TCP, `17` = UDP, `1` = ICMP), 16-bit header checksum, source and destination IPv4 addresses.
- **TCP header (RFC 9293):** 20 bytes minimum — 16-bit source/dest ports, 32-bit sequence and acknowledgement numbers, flags (SYN/ACK/FIN/RST), 16-bit window, 16-bit checksum.
- **HTTP:** the actual application bytes.

`code/main.py` builds exactly this stack from a high-level intent, then dissects it field by field on the way back up, so you can see how the destination host peels headers in reverse order (Physical → Link → Network → Transport → Application) until only the HTTP message remains.

### Which layer owns the addressing

A common confusion is "isn't the MAC address the same as the IP address?" No — they live at different layers and answer different questions:

| Question | Layer | Identifier | Scope |
|---|---|---|---|
| Which physical NIC on *this link*? | Link | 48-bit MAC | One broadcast domain |
| Which host on *the internet*? | Network | 32-bit IPv4 / 128-bit IPv6 | Global |
| Which process/socket on the host? | Transport | 16-bit port | One host |
| Which service by human name? | Application | FQDN | Global, via DNS |

ARP is the glue: it maps a layer-3 IP to a layer-2 MAC *within one link*. DNS is the glue above: it maps a layer-7 name to a layer-3 IP. Neither is "a layer" itself; they are translation protocols between layers.

### Why OSI's protocols died but its model lived

The OSI *protocols* (ISO standards published separately from 7498-1) lost to TCP/IP for non-technical reasons: TCP/IP shipped first in Berkeley UNIX (BSD sockets, ~1983) and was free, while OSI implementations arrived late, were expensive, and the seven-layer split was "more political than technical" (the Session and Presentation layers were nearly empty). But the OSI *vocabulary* — "that's a layer-2 problem," "this is layer-7 routing" — became universal. The book model is the pragmatic settlement: OSI's clear layering for *teaching and diagnosis*, TCP/IP's protocols for *practice*.

### Reading a capture against the model

In Wireshark, the dissector tree literally is the OSI/book stack top-to-bottom: Frame → Ethernet II → Internet Protocol → Transmission Control Protocol → Hypertext Transfer Protocol. Useful display filters that pin a symptom to a layer:

- `eth.fcs.status == "Bad"` — Link/Physical corruption.
- `ip.ttl < 5` — packet near death, suspect a routing loop (Network).
- `tcp.flags.reset == 1` — connection refused/torn (Transport).
- `dns.flags.rcode != 0` — name resolution failure (Application).

Each filter targets exactly one layer's header field, which is the model in action.

## Build It

1. Read `code/main.py`. It defines a small dataclass per layer header (`EthernetHeader`, `IPv4Header`, `TCPHeader`) plus an `encapsulate()` that wraps an HTTP message and a `dissect()` that unwraps it.
2. Run `python3 main.py`. Watch it print the message descending through Application → Transport → Network → Link → Physical (encapsulation), then ascending back up (dissection), printing each header's key fields and the EtherType/Protocol demultiplexing decisions.
3. Note the **demultiplexing keys**: EtherType `0x0800` routes to IPv4; IP Protocol `6` routes to TCP; TCP dest port `80` routes to HTTP. These three numbers are how a real stack knows which handler to call next.
4. Change the transport from TCP to UDP (Protocol `17`) in `main()` and re-run; observe the demux path change and the segment PDU become a datagram.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Place a symptom on a layer | The header field that is wrong (bad FCS, TTL=0, RST, NXDOMAIN) | You name one layer and can say what you'd test one layer up and one down |
| Explain a router's job | TTL decrement + checksum recompute + MAC rewrite, TCP header untouched | You articulate chained (1-3) vs. end-to-end (4-7) without prompting |
| Map MAC vs. IP vs. port vs. name | The four-row addressing table, ARP and DNS as glue | You assign each identifier to its layer and scope correctly |
| Read a capture | Wireshark dissector tree top-to-bottom | The tree's order matches the encapsulation order your code prints |

## Ship It

Produce one artifact under `outputs/`:

- A **layer-mapping cheat sheet** (the three-model table plus the chained/end-to-end rule) you can paste into a runbook.
- Or extend `code/main.py` into an IPv6 + UDP variant and capture its dissection output as the artifact.

Start from [`outputs/prompt-the-osi-reference-model-to-the-model-used-in-this-book.md`](../outputs/prompt-the-osi-reference-model-to-the-model-used-in-this-book.md).

## Exercises

1. A `traceroute` shows the same three router IPs repeating until TTL is exhausted, then ICMP Time Exceeded. Which layer owns this, and which header field is the direct evidence? What single-layer fix space do you investigate?
2. Your laptop pings `8.8.8.8` fine but `dns.google` fails. Using the addressing table, identify which layer's glue protocol is broken and why ping-by-IP isolates it.
3. A 1500-byte HTTP POST over a PPPoE link (MTU 1492) hangs while small requests succeed. Name the layer, the PDU that's too large, and the field (DF bit, RFC 791) that turns this into a black hole instead of fragmentation.
4. Explain to a teammate why a NAT box that rewrites TCP source ports is, strictly, violating a layering principle — and which layers (network vs. transport) it is reaching across.
5. Take the encapsulation diagram in the SVG and annotate which two layers a classic L3 router rewrites at each hop and which one it leaves byte-for-byte intact end-to-end.
6. The OSI model has Session and Presentation; the book model deletes them. Name one modern protocol that performs a presentation-layer function and one that performs a session-layer function, and say which book layer they now live in.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| OSI model | "The seven layers" | ISO/IEC 7498-1 reference model; a teaching/diagnosis model, **not** a deployed protocol stack |
| TCP/IP model | "The internet's layers" | Four-layer model (Link, Internet, Transport, Application) defined by RFC 1122; protocols-first, model-second |
| Book model | "Tanenbaum's layers" | Five-layer hybrid: OSI's Physical/Link/Network/Transport + a single Application layer absorbing OSI 5-7 |
| Chained layer | "The bottom layers" | Layers 1-3, re-run at every hop; a router rewrites Link and decrements/rechecksums Network |
| End-to-end layer | "The top layers" | Layer 4+, read only by source and destination hosts; routers don't touch the TCP header |
| Encapsulation | "Wrapping the packet" | Each layer prepending its header (Link adds a trailer/FCS) as the PDU descends the stack |
| PDU | "The packet" | Layer-specific unit: bit, frame, packet, segment/datagram, message — they are not interchangeable |
| Demultiplexing key | "The next-protocol field" | EtherType (0x0800), IP Protocol (6/17/1), dest port (80/443) that select the next layer's handler |

## Further Reading

- ISO/IEC 7498-1:1994 — *Open Systems Interconnection — Basic Reference Model*.
- RFC 1122 — *Requirements for Internet Hosts — Communication Layers* (Braden, 1989).
- RFC 791 — *Internet Protocol* (IPv4 header, TTL, Protocol field, header checksum).
- RFC 9293 — *Transmission Control Protocol* (TCP header, handshake, flags).
- IEEE 802.3 — *Ethernet* (frame format, EtherType, FCS/CRC-32).
- Cerf, V. & Kahn, R. (1974), *A Protocol for Packet Network Intercommunication*.
- Tanenbaum & Wetherall, *Computer Networks*, Chapter 1, Section 1.4 (Reference Models).
