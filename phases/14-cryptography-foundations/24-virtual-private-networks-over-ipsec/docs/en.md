# Virtual private networks built on IPsec ESP tunnels

> A company with offices in London and Paris used to pay thousands of dollars per month for a leased T1 between them; with an IPsec ESP tunnel the same traffic rides the public Internet for the price of two broadband lines, and an outside observer sees only ESP packets whose inner IP header, inner TCP header, and payload are all encrypted. This lesson explains how a Virtual Private Network is actually built: two security gateways run IKEv2 (RFC 7296) to authenticate each other and derive shared keys, then they install a pair of IPsec Security Associations whose ESP header (SPI, sequence number, IV) protects every inner packet in **tunnel mode** — original IP header + payload wrapped inside a fresh outer IP header carrying protocol `50` (ESP). You will trace the byte layout of an ESP packet (RFC 4303), see how tunnel mode hides the corporate addressing plan from intermediate routers, watch the per-packet sequence counter protect against replay, and then exercise the same arithmetic in `code/main.py` — a stdlib-only ESP-tunnel simulator that wraps a sample IP/TCP packet, computes the SPI from the SA triple, walks the Sequence Number counter across a session, and shows why the on-wire packet has zero resemblance to the inner one.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Basic IPv4 header structure, the IPsec AH/ESP overview in Phase 14, familiarity with hex/byte buffers
**Time:** ~75 minutes

## Learning Objectives

- Explain why ESP tunnel mode is the standard building block for site-to-site VPNs and how the on-wire packet differs from the original inner packet.
- Identify the fields of an ESP header (SPI, Sequence Number, IV, padding, pad length, next header, authentication data) and the order in which encryption vs. integrity cover them.
- Read the four phases of IKEv2 (INIT, AUTH, INFORMATIONAL, CREATE_CHILD_SA) and what each phase contributes to the SA database.
- Use `code/main.py` to wrap a synthetic inner IPv4/TCP packet in an ESP tunnel and inspect the resulting byte layout, sequence number progression, and HMAC.
- Distinguish transport mode from tunnel mode by packet layout, overhead, and the address-hiding property each provides.
- Recognize replay protection via the anti-replay window and why the 32-bit ESP sequence counter is *not* allowed to wrap.

## The Problem

A multinational runs an internal application on `10.10.0.50` that employees at the Paris branch must reach. The catch: `10.10.0.0/16` is RFC 1918 private space, so a plain IP packet from the Paris firewall to `10.10.0.50` cannot even be routed on the public Internet — there is no global route to it, and intermediate routers will drop it the moment they see an unroutable source. Even if you renumber the whole company to public addresses, every packet between the two sites would still fly across shared infrastructure, so any router in Amsterdam or Frankfurt could read your trade-secret database queries in cleartext.

The cheapest, most portable answer is a **Virtual Private Network**: the two security gateways (typically the office firewalls) establish a cryptographic tunnel, and *every* packet between the two sites is wrapped in an outer header that *is* globally routable. The outer header has the gateway's public IP as the source and the other gateway's public IP as the destination; the inner packet — including its private `10.x` source and destination — is encrypted and invisible to anyone in between. From the employee's perspective, `ping 10.10.0.50` works exactly as it would on the office LAN. From the Internet's perspective, the only thing flowing is a stream of ESP packets to UDP-port-4500 or protocol-50 endpoints.

The trap most beginners fall into is confusing "encrypted packet" with "VPN". Encryption alone does not give you a VPN. You also need: (1) a way to *establish* a shared key with the peer across the hostile network (IKE), (2) a way to identify which key/algorithm pair a given ESP packet belongs to (the SPI), (3) anti-replay protection so an attacker cannot resend yesterday's packets, and (4) a decision about whether to encrypt the inner IP header or only the inner payload. The last decision is what splits ESP into transport and tunnel mode, and the choice has visible consequences on the wire.

## The Concept

### What a VPN is, and what ESP gives it

A **Virtual Private Network** is an overlay that gives a distributed set of hosts the *illusion* of a private LAN. The illusion is maintained by tunneling every packet through a security gateway at the network edge. The two flavors in production use are:

| Tunnel flavor | What carries the inner packet | Visibility of inner header | Typical use |
|---|---|---|---|
| ESP tunnel mode (RFC 4303) | A fresh IP header + ESP header + ciphertext | Inner IP header is **encrypted** and **not visible** to the Internet | Site-to-site and remote-access VPNs (the default) |
| ESP transport mode (RFC 4303) | The original IP header + ESP header + ciphertext | Inner IP header is **in the clear** but the inner payload is encrypted | Host-to-host inside a trusted network |
| MPLS LSP (RFC 4364) | An MPLS label stack | Inner IP header is visible but routing is segregated by ISP | Carrier-provided L3VPN |

This lesson focuses on the first row, because that is what every firewall and most cloud VPN gateways implement by default.

### The IKEv2 handshake that creates the SAs

Before a single byte of user data is encrypted, the two security gateways must agree on keys. **IKEv2** (RFC 7296) does this in two exchanges (four messages), followed by periodic INFORMATIONAL exchanges and on-demand CREATE_CHILD_SA exchanges. The lifecycle is:

| IKEv2 exchange | Direction | What it carries | What it produces |
|---|---|---|---|
| IKE_SA_INIT | Bidirectional (2 messages) | SA proposal (encryption, PRF, DH group, integrity), nonces Ni/Nr, KEi/KEr for Diffie-Hellman | The IKE SA: `SKEYSEED`, `SK_e` (encryption), `SK_a` (integrity), `SK_d` (key derivation seed) |
| IKE_AUTH | Bidirectional (2 messages) | Identity (IDi/IDr), AUTH payload (signed MAC over the transcript), optional certificate, traffic selectors, and the **first** CHILD_SA proposal | An ESP or AH SA (the "child"), bound to the traffic selectors negotiated |
| CREATE_CHILD_SA | Bidirectional, on demand | Rekey request with a fresh SA proposal and new nonces | A replacement child SA before the old one's lifetime expires |
| INFORMATIONAL | Bidirectional, periodic | Liveness check, delete notification, DPD (RFC 3706) trigger | Re-uses the existing IKE SA to keep NAT mappings alive and signal errors |

The critical property of IKEv2 is **forward secrecy with PFS** (Perfect Forward Secrecy): every CHILD_SA rekey runs a fresh Diffie-Hellman exchange, so compromising a long-term key does not retroactively decrypt past sessions. In contrast, IKEv1 (RFC 2409) reused the original DH value for all child SAs, which is why RFC 7296 is the only IKE you should deploy.

### ESP header layout, byte for byte

Once the child SA exists, every protected packet carries an ESP header (RFC 4303, §2). The on-wire layout in tunnel mode is:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|               Security Parameters Index (SPI)                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Sequence Number                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    IV (variable, cipher-specific)             |
|                       ...                                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|              Encrypted Payload (variable)                     |
|     (inner IP header + inner TCP/UDP header + payload)        |
|                       ...                                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| ~  Padding (0-255 bytes, for block-cipher alignment) ~        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Pad Length | Next Header      |         ICV (variable)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| ~            Integrity Check Value (HMAC-SHA-256)            ~|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Fields explained:

| Field | Size | Meaning |
|---|---|---|
| SPI | 32 bits | The receiver uses this to look up the SA (algorithms, keys, anti-replay window) — it is the only thing in the header that names the connection. The SPI is *not* a secret. |
| Sequence Number | 32 bits | Strictly increasing counter for anti-replay. The counter is reset to 0 (or 1) when the SA is created and **must never wrap**; if it would, the SA is rekeyed via CREATE_CHILD_SA. |
| IV | 8/12/16 bytes | Initialization vector for CBC-mode ciphers (8 bytes for AES-CBC) or the initial counter for AES-GCM (RFC 4106, 8 bytes). For GCM/CCM the IV is also the salt; for AEAD ciphers the ICV is appended after the ciphertext. |
| Encrypted Payload | variable | Inner IP header + inner transport header + payload. For tunnel mode this is a full inner IP packet (RFC 4303 §3.1). |
| Padding | 0–255 bytes | Required to align the payload to the cipher block size (16 for AES) and to obscure the real length from traffic analysis. |
| Pad Length | 8 bits | Length of the padding field. |
| Next Header | 8 bits | Protocol number of the inner header — `4` (IP-in-IP) for plain tunnel mode, `41` (IPv6) when carrying IPv6 inside IPv4, or whatever inner protocol the encapsulation uses. |
| ICV | 12/16/32 bytes | Integrity Check Value: HMAC-SHA-256 (16 B), AES-GCM tag (8/12/16 B), or AES-CCM tag. Covers everything from SPI through Next Header. |

The on-the-wire IP header *preceding* the ESP header carries IP protocol `50` (decimal) — never `6` (TCP) or `17` (UDP), because the encapsulated TCP/UDP has already moved into the encrypted payload.

### Tunnel mode vs. transport mode at a glance

| | Transport mode | Tunnel mode |
|---|---|---|
| Inner IP header | The original IP header stays in place | A new outer IP header is added; original becomes inner |
| ESP inserted | Between IP header and inner TCP/UDP | Before the encrypted inner IP packet |
| Inner source/dest | Visible to every router on the path | Encrypted — invisible to every router on the path |
| Overhead | ESP + ICV (~50–66 bytes) | New 20-byte outer IP header + ESP + ICV (~70–86 bytes) |
| Default use | Host-to-host on a trusted backbone | Site-to-site VPN, remote-access VPN, MPLS edge |
| Specified in | RFC 4303 §3.1 (transport) | RFC 4303 §3.1 (tunnel) |

A worked numeric example: an HTTP GET (500 bytes) from `10.10.0.50` to `10.10.1.50`, encapsulated with AES-CBC-128 (16 B IV, 16 B ICV HMAC-SHA-256), tunnel mode, MTU 1500:

| Stage | Bytes on the wire |
|---|---|
| Inner packet: `10.10.0.50` → `10.10.1.50`, TCP, 500 B payload | 20 (IP) + 20 (TCP) + 500 = 540 |
| Add ESP header (SPI + Seq + IV) | 540 + 4 + 4 + 16 = 564 |
| Pad to 16-byte AES block | next multiple of 16: 576 → 12 bytes of pad |
| Add Pad Length (1) + Next Header (1) | 578 |
| Add HMAC-SHA-256 ICV | 594 |
| Wrap in outer IP header, protocol 50 | 594 + 20 = 614 |
| Then wrap in Ethernet (DMAC/SMAC/EtherType `0x0800` + outer IP) | 614 + 14 = 628 |

Inside the VPN this is one TCP segment; on the public Internet it is 614 bytes of ESP, none of which reveals the inner addressing.

### The anti-replay window

The 32-bit Sequence Number is the heart of replay protection. The receiver maintains a sliding window (commonly 32 or 64 packets wide) of recently-seen sequence numbers. On each ESP packet:

- If `Seq < window_left_edge`: drop (replay, already seen).
- If `Seq > window_right_edge`: shift the window right and accept.
- If `Seq` is inside the window and already marked: drop (replay).
- If `Seq` is inside the window and unmarked: mark and accept.

The window is essential because IPsec runs over IP, which is unreliable — packets can arrive out of order, and the receiver has to tolerate that without confusing an honest retransmission with a malicious replay. The strict "no wrap" rule is a hard constraint: with 1 Gbps and one ESP packet per microsecond, a 32-bit counter would wrap in ~4,294 seconds (~71 minutes), so any high-throughput deployment must trigger CREATE_CHILD_SA well before the counter is exhausted.

### Failure modes you can recognize

| Symptom | Likely cause | What you see |
|---|---|---|
| No ESP packets at all | Phase 1 (IKE_SA_INIT) failing — typically mismatched proposals or blocked UDP 500/4500 | Logs show `INVALID_KE_PAYLOAD` or `NO_PROPOSAL_CHOSEN`; no `STATE_MAIN_I1` progressing to `STATE_QUICK_I1` |
| ESP packets appear but every one is dropped | SPI/keys out of sync between peers; one side rekeyed and the other did not | Receiver logs `ESP sequence number out of window` or `ICV mismatch` |
| Tunnel works for a few minutes, then dies | Anti-replay window stuck (e.g., on a path that reorders heavily), or 32-bit Seq counter near wrap without rekey | Logs show `replay window overflow`; fix is to shorten SA lifetime and to enable PFS rekeying |
| Ping works, large TCP transfers stall | MTU issue — the extra ESP/IP headers push the inner packet over the path MTU, and ICMP "fragmentation needed" is filtered by the firewall | Symptom is small packets work, large ones freeze; fix is to lower the inner MSS to `path_mtu - 70` for tunnel mode |
| Rekeyed but old SA still receives packets | Mismatched lifetime between peers; one side retires the SA before the other | Logs show two SPIs active on one side, one on the other |

## Build It

1. Read the lesson and the SA triple in `code/main.py`. Confirm: an SA is `{SPI, destination IP, protocol (ESP=50)}`; the SPI alone does not name a connection — the destination IP is the lookup key on the receiver.
2. Run `python3 code/main.py`. The simulator:
   - Builds a synthetic IPv4/TCP inner packet for `10.10.0.50 → 10.10.1.50` carrying a small GET request.
   - Wraps it in an ESP tunnel: outer IP header (`203.0.113.5 → 198.51.100.7`, protocol 50), ESP header with a real SPI, AES-CBC-style IV, padding to 16 bytes, HMAC-SHA-256 ICV.
   - Walks the sequence counter through 8 successive packets, prints the on-wire hex of packet 0, and prints the ICV verification result.
3. Re-run with `main.py` arguments that flip the mode flag: with `mode="tunnel"` you see the inner IP header encrypted; with `mode="transport"` you see it in the clear, and the byte count is 20 bytes smaller.
4. Force a rekey by setting `lifetime_packets=4`: the simulator installs a new SPI when the counter would cross the lifetime boundary.
5. To prove replay protection, duplicate packet 3 and try to verify it twice on the receiver side — the second verification must fail.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the ESP header layout | Hex dump of packet 0 from `main.py` | First 4 bytes are SPI, next 4 are Sequence Number, then 16 bytes of IV, then ciphertext |
| Show inner addressing is hidden | Compare inner packet bytes to outer packet bytes | Inner `10.10.0.50` and `10.10.1.50` do not appear anywhere in the encrypted payload |
| Demonstrate replay defense | Re-verify packet 3 in the simulator | First verify: ICV OK. Second verify on the same SeqNum: `REPLAY_DETECTED` |
| Show rekey behavior | Set `lifetime_packets=4`, count SPIs | After 4 packets a new SPI appears in the output; old SPI is shown as retired |
| Map to real deployments | `ip xfrm state` on Linux | Output lists SPIs, destination, AES-CBC key, HMAC-SHA-256 key, anti-replay window — the same fields `main.py` simulates |

## Ship It

Produce one reusable artifact under `outputs/`:

- A reference VPN topology diagram (`vpn-topology.svg`) that shows the two security gateways, the IKE_SA, the ESP tunnel, and the encrypted inner packet.
- A runbook mapping each of the failure modes in the table above to a `tcpdump` or `ip xfrm monitor` evidence pattern.
- A 1-page cheat sheet of the IKEv2 message types and the RFC 4303 ESP fields, sized to print and pin next to a NOC monitor.

Start from `outputs/prompt-virtual-private-networks-over-ipsec.md` (the lesson's prompt record).

## Exercises

1. Compute the per-packet byte overhead of tunnel-mode ESP with AES-CBC-128 + HMAC-SHA-256 for a 1400-byte inner TCP segment. Then for transport mode. Which is smaller, and by how much?
2. The ESP Sequence Number is 32 bits and must never wrap. At 10 Gbps with a 1400-byte inner frame, how long until the counter would wrap, ignoring inter-packet gaps? When must CREATE_CHILD_SA fire to keep us safe?
3. Show, by sketching the on-wire byte layout, that the inner IP source and destination are *not* visible anywhere in the encrypted region of a tunnel-mode ESP packet. Where, if anywhere, are they visible in transport mode?
4. The IKEv2 AUTH payload authenticates the peer by signing a MAC over the transcript of IKE_SA_INIT. Why is this stronger than the IKEv1 model where authentication was based on a pre-shared key hashed with nonces?
5. Walk through what happens when the receiver's anti-replay window is 32 packets wide and the sender rekeys at lifetime 1,000,000. Suppose the network silently drops packets 100–110 of the old SA. What does the receiver do on packet 111?
6. ESP can use AES-GCM (RFC 4106), which is an AEAD cipher. In GCM, where is the ICV placed, and what part of the ESP header does it cover? How does that change the byte layout compared to AES-CBC + HMAC-SHA-256?
7. A corporate VPN policy says "all traffic from 10.10.0.0/16 to 10.20.0.0/16 must be encrypted". Which ESP mode and which traffic selectors satisfy this with the fewest SAs? Could one SA carry it, or do you need two?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| VPN | "encrypted tunnel" | An overlay that makes a public network look like a private LAN — usually built on ESP tunnel mode |
| IPsec | "encryption for IP" | A framework (RFC 4301–4309) of two protocols (AH, ESP) and a key exchange (IKEv2) |
| ESP | "the IPsec encrypting header" | RFC 4303 header (SPI, Seq, IV, ciphertext, ICV) inserted at protocol 50 in the outer IP header |
| AH | "the other IPsec header" | RFC 4302 — integrity only, no encryption; now rare in production |
| Tunnel mode | "wrap the whole IP packet" | ESP inserted between a *new* outer IP header and the encrypted inner IP packet |
| Transport mode | "encrypt just the payload" | ESP inserted between the original IP header and the inner TCP/UDP header |
| SA | "the connection" | A unidirectional Security Association: `{SPI, dest IP, protocol}` plus keys and algorithms |
| SPI | "which key to use" | 32-bit index into the receiver's SAD; chosen by the destination, *not* secret |
| IKEv2 | "the key exchange" | RFC 7296 — 4-message handshake that creates the IKE SA and the first child SA |
| Anti-replay window | "drops duplicate packets" | A sliding window of recently-seen ESP sequence numbers; out-of-window or duplicate = drop |
| PFS | "perfect forward secrecy" | A property of DH-based rekeying: compromising today's key does not retroactively decrypt yesterday's traffic |

## Further Reading

- RFC 4301 — Security Architecture for the Internet Protocol (the IPsec framework)
- RFC 4302 — IP Authentication Header (AH)
- RFC 4303 — IP Encapsulating Security Payload (ESP) — the byte layout used in this lesson
- RFC 4304 — Extended Sequence Number (ESN) for ESP — the 64-bit SeqNum extension
- RFC 4106 — The Use of Galois/Counter Mode (GCM) in IPsec ESP — the modern AEAD profile
- RFC 7296 — Internet Key Exchange Protocol Version 2 (IKEv2) — the key exchange this lesson describes
- RFC 3706 — IKE Dead Peer Detection (DPD) — how peers learn the other side is gone
- RFC 2401 — Security Architecture for the Internet Protocol (obsolete, superseded by RFC 4301; cited for historical context)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Ch. 8 on IPsec and VPNs
- `ip-xfrm(8)` — Linux manual page for `ip xfrm state` and `ip xfrm policy`, the closest CLI to what `main.py` simulates
