# IPsec

> IPsec (IP Security) is a network-layer security framework standardized in RFCs 2401, 2402, and 2406 that authenticates and optionally encrypts IP packets. It operates through two protocols — AH (Authentication Header, protocol 51) for integrity and anti-replay only, and ESP (Encapsulating Security Payload, protocol 50) for integrity plus confidentiality. Security state is organized as Security Associations (SAs), each a simplex connection identified by a 32-bit Security Parameters Index (SPI), a destination IP, and the protocol (AH or ESP). Keys are negotiated by IKE (Internet Key Exchange) version 2 (RFC 4306); the earlier IKEv1 was deeply flawed. IPsec runs in transport mode (IPsec header inserted after the IP header, before TCP) or tunnel mode (the entire IP packet is encapsulated inside a new IP packet — the basis of VPNs). The AH header carries a Next Header field, Payload Length, SPI, Sequence Number, and a variable-length HMAC Authentication Data field; ESP carries SPI, Sequence Number, an IV, encrypted payload+padding, and a trailing HMAC. Sequence numbers never wrap — when all 2^32 are exhausted a new SA must be established.

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Phase 15 lessons on keys, signatures, and authentication; Phase 9 IP lessons
**Time:** ~75 minutes

## Learning Objectives

- Explain why IPsec lives in the IP layer and why that choice was politically contested versus end-to-end application-layer encryption.
- Distinguish AH from ESP: which provides confidentiality, which authenticates parts of the IP header, and why ESP is preferred for new deployments.
- Describe an SA (Security Association) as a simplex, connection-oriented state record keyed by SPI + destination IP + protocol, and explain why bidirectional traffic needs two SAs.
- Contrast transport mode and tunnel mode: packet structure, MTU overhead, traffic-analysis resistance, and the VPN use case.
- Walk through the IKEv2 key-exchange role and identify the failure mode of IKEv1.
- Identify the exact packet fields (SPI, Sequence Number, Authentication Data) a Wireshark dissector would show for an AH or ESP packet.

## The Problem

A company has two offices — one in London, one in Paris — connected over the public Internet. The security team demands that all inter-office traffic be authenticated and encrypted, but nobody wants to modify every application. Putting crypto in the network layer is the compromise: applications stay oblivious, and the IP stack (or a security gateway) handles protection. The engineering challenge is choosing the right mode (transport vs. tunnel), the right protocol (AH vs. ESP), and the right key-exchange protocol (IKEv2) — then verifying the protection is actually applied to every packet, not just the first few.

## The Concept

### The layering war: where does security belong?

Most security experts argued for end-to-end encryption in the application layer — the source process encrypts, the destination process decrypts, and any tampering in between (including inside the OS) is detectable. The objection: this requires changing every application. The next-best proposal placed crypto in the transport layer, still end-to-end but application-transparent. The winning view for IPsec was that users do not understand security and will not use it correctly, so the network layer should authenticate and encrypt packets without user involvement. IPsec does not prevent security-aware users from adding their own end-to-end protection — it just raises the floor for everyone else.

### The Security Association (SA)

An SA is a simplex connection between two endpoints with an associated security identifier. If secure traffic is needed in both directions, two SAs are required. The SPI (Security Parameters Index) — a 32-bit value carried in every AH or ESP header — is used by the receiver to look up the shared key, algorithm, and other state for that connection. An SA is identified by the triple (SPI, destination IP, protocol). SAs live in the Security Association Database (SAD); the Security Policy Database (SPD) decides which traffic gets which protection.

### AH — Authentication Header (protocol 51)

| Field | Bits | Purpose |
|------|------|---------|
| Next Header | 8 | Original IP Protocol value (e.g., 6 for TCP) |
| Payload Length | 8 | 32-bit words in AH header minus 2 |
| Reserved | 16 | Zero, reserved for future use |
| Security Parameters Index | 32 | Connection identifier — look up shared key |
| Sequence Number | 32 | Anti-replay counter; unique per packet; no wraparound |
| Authentication Data (HMAC) | variable | Digital signature over packet plus shared key |

AH provides integrity and anti-replay but **no confidentiality**. Its integrity check covers immutable IP header fields (e.g., source address) but excludes hop-varying fields like TTL. The HMAC (Hashed Message Authentication Code) is computed with a negotiated symmetric key — public-key crypto is too slow for per-packet processing. AH is likely to be phased out: ESP can do everything AH does, plus encryption, more efficiently.

### ESP — Encapsulating Security Payload (protocol 50)

ESP provides integrity (HMAC), confidentiality (encryption), and anti-replay (sequence numbers). Unlike AH, the HMAC is placed **after** the payload as a trailer, which lets hardware compute the MAC as bits stream out the interface — no buffering required. ESP's header is two 32-bit words: SPI and Sequence Number. A third word — the Initialization Vector — generally follows unless null encryption is used. The null algorithm is formally defined and praised in RFC 2410, satisfying the "encryption required but optional in practice" design.

### Transport mode vs. tunnel mode

| Aspect | Transport mode | Tunnel mode |
|--------|---------------|------------|
| Packet structure | IP header then IPsec header then TCP then payload | New IP header then IPsec header then old IP header then TCP then payload |
| MTU overhead | Small | Large (extra 20-byte IP header) |
| Endpoint | Original source/destination | Security gateway (e.g., firewall) |
| Traffic analysis | Exposed: visible source, destination, flow | Resistant: outer header shows only gateway addresses |
| Typical use | Host-to-host | VPN between offices, remote access |

Tunnel mode aggregates a bundle of TCP connections into one encrypted stream, preventing an intruder from seeing who sends how many packets to whom — a defense against traffic analysis. This is the basis of VPNs: the tunnel terminates at a security gateway, so machines on the company LAN need not be IPsec-aware.

### IKE — Internet Key Exchange

ISAKMP is a framework for establishing keys; IKE is the protocol that does the work. IKEv2 (RFC 4306) should be used — IKEv1 was deeply flawed (Perlman and Kaufman, 2000). IKE negotiates the SA parameters: services, modes, algorithms, and keys. Because IPsec is connection-oriented (an SA must exist before protected packets flow), key establishment amortizes setup cost over many packets.

### Failure modes

- **Replay attack**: an intruder re-sends a captured packet. ESP/AH sequence numbers with anti-replay windows defeat this. Sequence numbers never wrap — exhausting all 2^32 forces a new SA.
- **Traffic analysis**: even encrypted packets reveal who talks to whom. Tunnel mode hides this behind a single gateway-to-gateway flow.
- **AH/ESP mismatch**: if one side uses AH and the other expects ESP, packets are dropped. The SPD must agree on both sides.
- **IKE failure**: if IKE cannot negotiate keys (policy mismatch, expired credentials), no SA is established and no protected traffic flows.
- **MTU fragmentation**: tunnel mode adds an extra IP header, which can push packets over the path MTU and cause fragmentation or black holes.

### Worked example: a VPN SA

Two firewalls negotiate an IKEv2 SA. The result: an ESP tunnel-mode SA with SPI 0xC0FFEE01, AES-128-CBC for encryption, HMAC-SHA-1 for integrity, sequence numbers starting at 0. Every packet from London to Paris is encapsulated: new IP header (src = London firewall, dst = Paris firewall) then ESP header (SPI, Seq) then old IP header (src = London host, dst = Paris host) then TCP then encrypted payload then HMAC trailer. A Paris-bound router in the Internet sees only an ordinary packet with protocol 50; the Paris firewall decapsulates and forwards to the internal host.

`code/main.py` models an IPsec SA with negotiated parameters and simulates packet processing; `assets/ipsec.svg` diagrams the AH and ESP header layouts in both modes.

## Build It

1. Run `python3 code/main.py` to see an SA negotiated and a packet processed through transport and tunnel modes.
2. Examine the printed AH and ESP header field layouts — match them to the tables above.
3. Trigger the replay-detection path by re-sending a sequence number the simulator has already seen.
4. Note the byte overhead of tunnel mode versus transport mode in the output.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm IPsec is applied | Wireshark capture on the gateway interface showing protocol 50 (ESP) or 51 (AH) | Every inter-office packet carries the IPsec header, not raw TCP |
| Verify SA state | ip xfrm state (Linux) or setkey -D (BSD) listing SPI, algorithms, byte counters | SPI, encryption algorithm, and sequence numbers match both endpoints |
| Detect replay | Anti-replay window counters in SA state | A retransmitted sequence number is dropped, not delivered |
| Diagnose IKE failure | tcpdump on UDP 500/4500 during negotiation; IKE error logs | IKEv2 exchange completes with a single INIT and AUTH round; no NOTIFY errors |

## Ship It

Create one artifact under `outputs/`:

- An IPsec SA parameter sheet (SPI, algorithms, mode, endpoints) for a two-office VPN.
- A Wireshark display-filter cheat sheet for ESP/AH dissection.
- A one-page runbook for IKE failure-mode triage.

Start with [`outputs/prompt-ipsec.md`](../outputs/prompt-ipsec.md).

## Exercises

1. A London-to-Paris VPN uses ESP tunnel mode. Draw the complete packet structure for a TCP segment sent from London to Paris, labeling which fields are encrypted, which are authenticated by the HMAC, and which are in the clear.
2. Why must a new SA be established when the 32-bit sequence number space is exhausted, rather than simply wrapping around? What attack does wrapping enable?
3. Two firewalls negotiate IKEv2 but one side selects AES-128-CBC while the other expects AES-256-CBC. What happens? Where would you see the failure in logs?
4. Compare the per-packet byte overhead of AH transport mode versus ESP tunnel mode for a 1400-byte TCP payload. Which adds more? By how many bytes?
5. A company wants to protect traffic between two hosts on the same LAN. Would you choose transport mode or tunnel mode? Why?
6. The null encryption algorithm (RFC 2410) is formally defined. When would you legitimately use it in an ESP SA, and what risk does it create if misconfigured?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SA | "a secure connection" | A simplex state record (SPI, dest IP, protocol) holding keys and algorithms; bidirectional traffic needs two |
| SPI | "the connection ID" | 32-bit value in every AH/ESP header that the receiver uses to look up SA state |
| AH | "the integrity-only one" | Authentication Header — integrity plus anti-replay, no encryption; authenticates part of the IP header |
| ESP | "the encrypting one" | Encapsulating Security Payload — integrity plus confidentiality plus anti-replay; HMAC in trailer for hardware efficiency |
| Transport mode | "host-to-host" | IPsec header inserted after IP header; smaller overhead, exposes endpoints to traffic analysis |
| Tunnel mode | "the VPN one" | Entire IP packet encapsulated in new IP packet; hides endpoints, defends against traffic analysis |
| IKE | "the key negotiator" | Internet Key Exchange; IKEv2 (RFC 4306) required — IKEv1 was deeply flawed |
| HMAC | "keyed hash" | Hashed Message Authentication Code; symmetric-key MAC much faster than SHA-1 plus RSA |

## Further Reading

- RFC 4301 — Security Architecture for the Internet Protocol (updated IPsec framework)
- RFC 4302 — IP Authentication Header (AH)
- RFC 4303 — IP Encapsulating Security Payload (ESP)
- RFC 4306 — IKEv2 (Internet Key Exchange version 2)
- RFC 2410 — The NULL Encryption Algorithm and Its Use With IPsec
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 section 8.6.1
