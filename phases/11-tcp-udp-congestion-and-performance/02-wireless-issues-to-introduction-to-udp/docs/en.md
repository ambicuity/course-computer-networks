# Wireless Issues to Introduction to UDP

> Section 6.3.3 exposes the **confounding-signals problem**: a transport protocol using loss as a congestion signal misreads wireless losses as congestion and throttles the connection to near zero. The fix is **timescale separation** — link-layer retransmissions happen in microseconds-to-milliseconds and repair transmission errors before transport-layer loss timers (which fire in milliseconds-to-seconds) ever see them. Section 6.4.1 introduces **UDP** (RFC 768) as the minimal transport — an **8-byte header** (source port, destination port, length, checksum) plus payload, no connection setup, no retransmission, no flow or congestion control, **protocol number 17** in the IPv4 header and **Next Header = 17** in IPv6. The DNS lookup path uses UDP because one request, one reply, no setup. The lesson builds a UDP datagram parser that walks the 8-byte header, validates the pseudo-header checksum, and shows how an application picks a source port (typically ephemeral, **IANA-reserved range 49152-65535** under RFC 6335) to receive a reply.

**Type:** Build
**Languages:** Python, no external dependencies
**Prerequisites:** IPv4 header format (Protocol field), binary/hex arithmetic, basic UDP client-server exposure
**Time:** ~90 minutes

## Learning Objectives

- Describe the **wireless confounding-signals** problem (loss meaning both congestion and transmission error) and explain how timescale separation resolves it.
- Identify the four 16-bit words of the **UDP header** (source port, destination port, length, checksum) and the maximum payload of **65,507 bytes**.
- Verify a UDP checksum manually using one's complement arithmetic across the pseudo-header.
- Explain why a sender uses an **ephemeral source port** and how the receiver routes the reply back using the inverted port fields.
- Distinguish UDP's "no setup, no reliability, no congestion control" model from TCP's and pick appropriate application classes for each.
- Read and explain `ss -ulnp` output and a Wireshark capture of a DNS query/response over UDP.

## The Problem

A research vessel sails from Boston Harbor into the North Atlantic with a 5 Mbps VSAT uplink. The on-board instruments stream temperature, salinity, and current-meter data to shore every second. Each measurement is a small UDP datagram — about 80 bytes. The transport choice is deliberate: a missed sample is meaningless once the next one arrives, and retransmitting a one-second-old temperature reading would waste satellite capacity for no benefit.

Two problems surface once the ship is at sea.

**Problem 1: the link-layer is honest, the transport is not.** The VSAT link uses Reed-Solomon FEC plus ARQ on the satellite hop; bit error rates on the order of `10^-6` per byte are corrected before they leave the modem. But heavy rain fade at 12°N latitude pushes the *uncorrected* loss rate briefly to 3%. The on-board router's queue runs hot during those windows. The transport — running TCP — sees the loss and applies its multiplicative decrease. A 3% loss rate against the Padhye formula `B ≈ MSS/RTT * 1/sqrt(2p/3)` predicts a TCP-friendly throughput of roughly 1/6 of the clean capacity. The whole bulk transfer (a 200 MB nightly upload of the day's acoustic data) grinds to a halt even though the *transmission error* layer below has already recovered most packets and only the queue-tail drops should be blamed on congestion.

**Problem 2: voice and video do not need reliability.** Even when the link is clean, voice and video do not benefit from retransmission — a 250 ms-old audio packet arriving after its playout slot is worse than the packet being absent. The transport for these flows must be connectionless and unreliable: UDP.

This lesson covers both: how to avoid misreading wireless losses (Sec. 6.3.3) and what the connectionless alternative (Sec. 6.4.1, UDP) looks like.

## The Concept

### Wireless losses are not congestion losses

Section 6.3.3 opens with the textbook's blunt assessment: TCP, which uses loss as a congestion signal, is fundamentally incompatible with wireless links in their raw form. The Padhye et al. (1998) formula says throughput scales as `1/sqrt(p)`:

| Steady-state loss rate `p` | TCP-friendly rate on 100 Mbps, RTT 80 ms, MSS 1460 |
|---|---|
| 0.0001 (0.01%) | 80.7 Mbps |
| 0.001 (0.1%) | 25.5 Mbps |
| 0.01 (1%) | 8.07 Mbps |
| 0.1 (10%) | 2.55 Mbps |

The middle row says that a 1% loss rate — perfectly ordinary on a home Wi-Fi link — costs a TCP flow *92%* of its potential throughput. A 10% loss rate, *common* on marginal 802.11 links (especially at range), gives the connection 2.5% of capacity.

The reason this matters is that **wireless losses are not all congestion**. They split into two populations:

| Loss type | Cause | Frequency | Where to fix it |
|---|---|---|---|
| Transmission error | Noise, fading, interference, hidden-node collision | Common on wireless | Link layer (retransmit, FEC) |
| Congestion drop | Queue overflow at a router | Common on wired | Transport layer (slow down) |

The transport layer cannot tell the two apart. If it slows down on every loss, it starves flows over noisy wireless links. If it ignores all loss, congestion collapse returns on wired links.

### Timescale separation is the standard fix

The textbook's resolution, drawn from Fig. 6-26, is **timescale separation**. Link-layer retransmission protocols (802.11's stop-and-wait ARQ on each frame, LTE's HARQ, 5G NR's HARQ with soft combining) repair transmission errors in **microseconds to milliseconds**. TCP retransmission timers fire in **milliseconds to seconds**, three orders of magnitude slower.

The result is a *handoff*: by the time the transport loss timer expires, the link has already retried the frame and either succeeded or genuinely given up. If the link gave up, the loss really was uncorrectable, and dropping the packet to TCP is fine because most wireless link layers have already masked the *common* errors.

The textbook points out that this only works when the link round-trip is short. A geostationary satellite with a 540 ms one-way RTT cannot afford per-frame ARQ without crushing throughput; FEC is the standard mitigation. The deep-space case (Sec. 6.7 DTN) abandons the assumption that loss equals congestion entirely.

A second concern is **variable capacity** — the capacity of a wireless link changes as the node moves or interference rises. The textbook notes this is not as bad as it sounds: a congestion-control algorithm has to handle "another user changed their sending rate" already, and a wireless capacity shift just looks like that. The corner case is *mesh networks* where many wireless hops interact; Sec. 6.3.3 ends with the observation that research-grade transport protocols (Li et al., 2009) target exactly that case.

### UDP: the connectionless, unreliable transport

Section 6.4.1 introduces UDP (RFC 768, Postel, 1980) as the *other* Internet transport. UDP transmits **segments** consisting of an 8-byte header plus the payload. It does almost nothing beyond IP, plus **port demultiplexing** and an optional checksum.

The UDP header layout (Fig. 6-27) is exactly four 16-bit words:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Source Port          |       Destination Port        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          UDP Length           |          UDP Checksum          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Payload (variable)                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Purpose |
|---|---|---|
| Source Port | 16 bits | Reply target; usually ephemeral for clients |
| Destination Port | 16 bits | Server's well-known port (e.g., **53** for DNS, **123** for NTP) |
| Length | 16 bits | Header + payload, **min 8**, max **65,535** |
| Checksum | 16 bits | Optional one's-complement sum over header + payload + pseudo-header |

The Length field's *minimum* value is 8 (header only, no payload). The *maximum* value is 65,535 bytes for the entire UDP datagram, but the practical upper bound is 65,507 because the underlying IPv4 payload is at most 65,515 and the UDP header consumes 8 bytes. (IPv6's jumbogram option can lift the IP-layer limit; the UDP length field stays 16-bit.)

### The pseudo-header checksum and end-to-end argument

The UDP checksum is computed over the UDP header, the payload, *and* an IPv4 pseudo-header (Fig. 6-28) containing the 32-bit source address, the 32-bit destination address, the protocol number (17 for UDP), and the UDP length. The algorithm is one's-complement addition of all 16-bit words, then one's-complement of the sum. If the receiver computes the sum over the entire segment *including* the checksum field, the result must be zero.

The pseudo-header inclusion is an intentional violation of strict layering — UDP is reaching into the IP layer to verify the datagram arrived at the right host. RFC 1122 requires the checksum to be computed and verified; turning it off (sending an all-zero checksum) is allowed but "foolish unless the quality of the data does not matter (e.g., for digitized speech)."

The IPv6 equivalent pseudo-header is similar but uses 128-bit addresses.

### Ports: mailboxes that applications rent

The single feature that justifies UDP over raw IP is **port demultiplexing**. An incoming UDP datagram with destination port 53 is delivered to the local DNS resolver process; one with destination port 123 goes to the NTP daemon; an ephemeral port number chosen by the kernel tells incoming replies where to find the requesting process.

The IANA registry divides the 16-bit port space into three ranges (RFC 6335):

| Range | Decimal | Allocation |
|---|---|---|
| Well-known | 0 – 1023 | Bindable only by privileged processes; assigned by IANA |
| Registered | 1024 – 49151 | Assigned by IANA on request |
| Dynamic / ephemeral | 49152 – 65535 | Free for any use; assigned by the kernel for client sockets |

Clients typically let the kernel pick an ephemeral port for the source; the application supplies the well-known destination port. The server binds to its well-known port with the `BIND` primitive.

### What UDP does *not* do

The textbook's enumeration is the right reference list:

- No connection setup (no three-way handshake).
- No retransmission on loss.
- No flow control (the receiver's window is not advertised).
- No congestion control (the sender keeps firing).
- No ordering (datagrams may arrive out of order).
- No fragmentation awareness at the transport (it just hands IP a datagram; if the datagram is too big, IPv4 will fragment or drop it depending on the `DF` bit).

What UDP *does* do: provide port-based demultiplexing on top of IP, an optional end-to-end checksum for misdelivery and bit-error detection, and an interface that applications can build their own reliability on top of when they need to.

### Why DNS uses UDP

The textbook cites DNS as the canonical UDP application: a single request, a single reply, no setup, no teardown. RFC 1035 specifies UDP as the primary transport for DNS, with TCP fallback for large responses (zone transfers, DNSSEC-signed responses > 512 bytes). The original UDP cap of 512 bytes was lifted by EDNS(0) (RFC 6891) to allow up to 4096 bytes for the response, with modern resolvers typically using 1232 bytes to fit comfortably in the path MTU after IPv6's 1280-byte minimum.

A live query can be inspected with `dig +short` or with `tcpdump -i any -n udp port 53` to see the 8-byte header plus the wire-format DNS query.

### Why voice and video use UDP

Real-time applications need to **discard late packets**, not retransmit them. Retransmitted voice packets arrive after their playout slot, contributing to "buffer bloat" or "robot voice" artifacts. The transport must be connectionless (no handshake delay), unreliable (no retransmission), and expose the application to the network's true conditions so it can adapt codec bitrate. UDP is the only Internet transport with that profile. RTP (Sec. 6.4.3, covered in the next lesson) layers on top of UDP to add sequencing, timestamping, and payload type identification.

## Build It

The artifact is `code/main.py`. It contains a stdlib-only UDP datagram parser and a small application-level reliability demo (request-reply over UDP with a synthetic loss model):

1. **UDP header parser**
   - Take a raw 8-byte header plus a payload.
   - Return a typed `UDPDatagram` dataclass with `src_port`, `dst_port`, `length`, `checksum`, and `payload`.
   - Validate the length (header is exactly 8 bytes; total length ≥ 8; total length ≤ 65,535).
   - Compute the checksum over header + pseudo-header + payload and verify it matches the field.

2. **Pseudo-header builder**
   - Build the IPv4 pseudo-header from a `(src_ip, dst_ip, protocol=17, udp_length)` tuple.
   - Show the byte layout the way it appears in the RFC 768 calculation.

3. **One's-complement checksum**
   - Implement `ones_complement_sum(words)` for a list of 16-bit integers.
   - Handle the odd-length trailing byte by padding with zero.

4. **Ephemeral port allocator**
   - Implement `pick_ephemeral_port()` that returns a port in `49152-65535` and rejects ports in `0-1023` and `1024-49151`.

5. **DNS-style request/reply demo**
   - Build a DNS-like request with a 12-byte header and a question for `example.com`.
   - Synthesize a reply from a "server" function.
   - Show how the reply's source port is the request's destination port and vice versa.

Run with `python3 code/main.py`. No pip dependencies.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | `Protocol = 17` in IPv4 header / `Next Header = 17` in IPv6 header. | You can spot a UDP datagram in Wireshark and read the four header fields. |
| Confirm normal UDP behavior | `ss -ulnp` showing the socket bound to the expected port. | A socket in `UNCONN` state with the right local and remote address. |
| Diagnose misdelivery | Recompute the checksum at the receiver. | Mismatch indicates either a corrupt packet or a NAT/load balancer rewriting fields without updating the checksum. |
| Diagnose voice quality | RTP sequence-number gaps in the receiver's `jitter buffer`. | Gap rate below 1% is acceptable for voice; above 5% the call is unusable. |
| Diagnose wireless throttling | Compare `retrans_segs` to `out_segs` on a TCP connection crossing a wireless link. | If the wireless link's FEC/ARQ is hiding most loss but the transport still slows down, link-layer retransmits are being counted as congestion. |

## Ship It

The `outputs/` directory should contain `wireless-udp-runbook.md` with three sections:

1. **When to prefer UDP over TCP**: a checklist (low latency, small messages, no retransmission value, broadcast/multicast).
2. **Header-decoding crib sheet**: the four 16-bit fields, the pseudo-header, and the checksum verification recipe.
3. **Wireless loss budget**: an estimate of the loss rate tolerable for your application, with the Padhye TCP-friendly rate computed and a recommendation about whether to switch to UDP.

## Exercises

1. **Verify a known checksum.** Construct a UDP datagram with payload `b"hello"` and a known checksum; recompute it and confirm the result is zero. Then flip one bit in the payload and confirm the result is non-zero.
2. **Decode a packet from hex.** Given the bytes `b"\x00\x35\xd8\x6f\x00\x0d\x00\x00\x48\x45\x4c\x4c\x4f"`, decode source port, destination port, length, checksum, and payload. (Hint: destination 53 = DNS.)
3. **Build a pseudo-header.** For source `10.0.0.5`, destination `8.8.8.8`, UDP length `19`, write out the 12-byte pseudo-header byte by byte.
4. **One's complement by hand.** Compute the checksum for a header of `(0x00 0x35, 0xD8 0x6F, 0x00 0x0D, 0x00 0x00)` plus payload `"HELLO"` (treated as `0x48 0x45, 0x4C 0x4C, 0x4F 0x00`). Verify the result equals zero after you write the sum back into the checksum field.
5. **Ephemeral port range.** Write a loop that picks 1000 ephemeral ports and verifies none of them are duplicates. Run it under the kernel's actual allocation if `socket` is available (`SO_REUSEADDR` is not enough for UDP).
6. **Timescale separation.** Compute how many 802.11 retransmissions (each ~1 ms with short inter-frame spacing) can fit inside a single TCP retransmission timer (default 200 ms initial). Explain why the link layer's repair almost always finishes first.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| UDP | "Unreliable, no setup, just packets." | A transport with an 8-byte header (src/dst port, length, checksum), no flow or congestion control, and best-effort delivery — RFC 768. |
| Confounding signals | "Loss could mean either." | Wireless transmission errors and queue overflow both look like packet drops; the transport cannot distinguish them without help. |
| Timescale separation | "Repair faster than you measure." | Link-layer retransmits finish in micro-to-milliseconds; transport loss timers fire in milli-to-seconds. The transport sees only the latter. |
| Pseudo-header | "An IP-layer intrusion in the UDP checksum." | Source and destination IPv4/IPv6 addresses plus protocol number and UDP length, mixed into the checksum so misdelivered packets are detected. |
| Ephemeral port | "Some random high number." | A source port allocated by the kernel from 49152-65535 (RFC 6335) for the duration of a single socket. |
| Well-known port | "The server's mailbox." | A port from 0-1023, bindable only by privileged processes; assigned by IANA (e.g., 53 = DNS, 123 = NTP, 161 = SNMP, 514 = syslog). |
| Padhye rate | "1/sqrt(loss)." | The TCP-friendly throughput formula; a 1% loss rate caps a TCP sender at roughly 8% of link capacity. |

## Further Reading

- Tanenbaum, Feamster, Wetherall — *Computer Networks*, Sec. 6.3.3 and Sec. 6.4.1.
- RFC 768 (Postel, 1980) — the original UDP specification.
- RFC 6335 (Cotton, Eggert, Touch, Westerlund, 2011) — the IANA port-number registry.
- RFC 1122 (Braden, 1989) — Requirements for Internet Hosts, including the checksum requirement.
- Padhye, Firoiu, Towsley, Kurose, "A TCP-friendly Rate Adjustment Protocol," *NOSSDAV 1998* — the 1/sqrt(p) throughput model.
- Perkins, *RTP: Audio and Video for the Internet*, Addison-Wesley, 2003 — the standard RTP reference, used in the next lesson.
- RFC 1035 (Mockapetris, 1987) and RFC 6891 (Damas, Graff, Vixie, 2013) — DNS over UDP and EDNS(0).
