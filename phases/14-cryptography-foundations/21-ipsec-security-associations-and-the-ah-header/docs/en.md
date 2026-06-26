# IPsec Security Associations and the AH Header

> IPsec (RFC 4301-4303) provides integrity, authentication, and confidentiality at the IP layer via two protocols: Authentication Header (AH, RFC 4302) gives integrity and authentication without encryption; Encapsulating Security Payload (ESP, RFC 4303) adds encryption and is more widely deployed. A Security Association (SA) is a one-way logical channel identified by SPI + destination IP + protocol (AH or ESP). We build an AH packet constructor that emits a valid AH header with HMAC-SHA256-128 integrity covering the IP pseudo-header and the AH payload, then verify it on the receiver side.

**Type:** implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** HMAC, IPv4 header, IPsec concepts
**Time:** ~60 minutes

## Learning Objectives

- Define a Security Association (SA) as the tuple (SPI, destination IP, protocol) plus keys and algorithms.
- Construct an AH packet per RFC 4302: Next Header (8), Payload Length (8), Reserved (16), SPI (32), Sequence Number (32), ICV (variable).
- Compute the Integrity Check Value (ICV) over the IP pseudo-header (with mutable fields zeroed) + AH + payload.
- Verify a received packet: recompute ICV over the right region, constant-time compare.
- Distinguish transport mode (AH between IP and transport header) from tunnel mode (AH wraps a new IP header around the original packet).

## The Problem

IPsec is the canonical example of network-layer cryptography and the foundation of every corporate VPN. Yet most engineers have only ever seen IPsec through a configuration UI. Without a working AH implementation, you cannot tell why AH is rarely used alone (it doesn't encrypt) or why ESP is preferred (it does both). The pedagogical goal: build one packet, end-to-end, with the integrity check computed in the same way RFC 4302 specifies.

## The Concept

### The IPsec Architecture (RFC 4301)

| Component | Purpose |
|-----------|---------|
| Security Association (SA) | One-way logical channel; identified by SPI + dest IP + protocol. |
| Security Association Database (SAD) | Active SAs on the host. |
| Security Policy Database (SPD) | Rules that determine which traffic gets protected. |
| AH (RFC 4302) | Authentication Header: integrity + authentication, no encryption. |
| ESP (RFC 4303) | Encapsulating Security Payload: integrity + authentication + encryption. |
| IKEv2 (RFC 7296) | Key management; sets up SAs dynamically. |

### AH Header Layout (RFC 4302 §2.2)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Next Header   |  Payload Len  |          Reserved             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Security Parameters Index (SPI)              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Sequence Number Field                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Integrity Check Value-ICV (variable)         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Payload (variable)                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Bits | Meaning |
|-------|------|---------|
| Next Header | 8 | Type of payload that follows AH (e.g., 6 = TCP, 4 = IP-in-IP). |
| Payload Length | 8 | Length of AH in 32-bit words minus 2 (RFC 4302 §2.2). |
| Reserved | 16 | Zero. |
| SPI | 32 | Identifies the SA. |
| Sequence Number | 32 | Monotonic counter; replay protection. |
| ICV | variable | HMAC truncated to the algorithm's output (e.g., 96 bits for HMAC-SHA-256-128). |

### Modes

| Mode | Placement |
|------|-----------|
| Transport | AH inserted between original IP header and transport header (TCP/UDP). |
| Tunnel | New outer IP header + AH + original IP packet. Used by site-to-site VPNs. |

### ICV Computation

```
ICV = HMAC[algorithm](SA_key, IP_pseudo_header_mutable_zeroed || AH || payload)
```

For IPv4 the pseudo-header fields are:
- Total Length (mutable, set to 0 for ICV computation)
- Flags, Fragment Offset, Header Checksum (mutable, set to 0)
- All other IP header fields are immutable and included.

AH itself includes the mutable fields as 0 in the SPI/SN/etc., but Next Header, Payload Length, SPI, Sequence Number are included as-is.

### Anti-Replay Sequence Number

Each packet increments the SA's sequence number. Receivers maintain a sliding window (typically 32-128 packets) and reject packets whose sequence number is below the window's left edge. Sequence numbers are NOT allowed to wrap; the SA must be rekeyed before 2^32 packets.

### Transport Mode vs. Tunnel Mode Picture

```
Transport mode:
[IP hdr][AH][TCP][data]                ICV covers: IP pseudo + AH + TCP + data

Tunnel mode:
[NEW IP hdr][AH][IP hdr][TCP][data]    ICV covers: NEW IP pseudo + AH + old IP + TCP + data
```

### Algorithms in Common Use

| Algorithm | ICV size | Notes |
|-----------|----------|-------|
| HMAC-SHA-256-128 (RFC 4868) | 128 bits | Common, recommended. |
| HMAC-SHA-384-192 | 192 bits | Higher security. |
| HMAC-SHA-512-256 | 256 bits | Maximum. |
| AES-GMAC (RFC 4543) | 128 bits | AES-NI acceleration. |
| HMAC-MD5-96 (legacy) | 96 bits | Deprecated; MD5 is broken for collision resistance, though HMAC-MD5 remains secure. |

AH alone does not encrypt, so it is rarely used today — most deployments use ESP with NULL encryption (integrity-only) instead. AH survives because it authenticates parts of the outer IP header that ESP does not.

## Build It

`main.py` ships:

- `SecurityAssociation` dataclass with SPI, src, dst, algorithm, key, seq.
- `build_ah_packet(sa, payload, next_header, mode)` returning bytes.
- `verify_ah_packet(sa, packet)` returning (ok, reason).
- A demo that constructs, sends, tampers, and re-verifies.

```python
from main import SecurityAssociation, build_ah_packet, verify_ah_packet

sa = SecurityAssociation(spi=0xC0FFEE, src="10.0.0.1", dst="10.0.0.2",
                          algorithm="hmac-sha256-128", key=b"k"*32, seq=1)
pkt = build_ah_packet(sa, b"hello", next_header=6, mode="transport")
ok, reason = verify_ah_packet(sa, pkt)
print(ok, reason)
```

## Use It

| Routine | Purpose |
|---------|---------|
| `SecurityAssociation(...)` | SA record |
| `build_ah_packet(sa, payload, next_header, mode)` | emit an AH-protected packet |
| `verify_ah_packet(sa, packet)` | recompute and compare ICV |
| `ah_header_size(icv_bytes)` | AH header length in bytes |
| `increment_seq(sa)` | advance the replay counter |
| `ip_pseudo_header_bytes(ip_header, length)` | build the pseudo-header for ICV |

## Ship It

Real IPsec lives in the kernel. Linux's `xfrm` subsystem provides both AH and ESP via Netlink (`ip xfrm state`); strongSwan and Libreswan implement IKEv2 above. Python wrappers exist (`pyroute2`, `scapy`) for testing. This lesson's code models the wire format, not the kernel state machine.

## Exercises

1. Build a transport-mode AH packet carrying a TCP SYN, then verify it on the receiver. Tamper with one byte of the payload and confirm the ICV check fails.
2. Build a tunnel-mode AH packet carrying an inner IPv4 packet. Verify the inner packet survives.
3. Add anti-replay: maintain a sliding window of 32 sequence numbers and reject packets older than 32.
4. Implement both `hmac-sha256-128` (16-byte ICV) and `hmac-sha512-256` (32-byte ICV). Confirm the AH header length encodes correctly.
5. Compare AH and ESP: build an ESP-NULL packet (integrity-only) and discuss why it is preferred over AH in production.
6. Show that AH authenticates the outer IP header by zeroing the mutable fields (Total Length, Flags, Fragment Offset, Header Checksum) before computing the ICV.

## Key Terms

| Term | Definition |
|------|------------|
| Security Association (SA) | One-way logical channel: (SPI, dest IP, protocol) + keys + algorithms. |
| SPI | Security Parameters Index, a 32-bit SA identifier. |
| AH | Authentication Header (RFC 4302); integrity and authentication. |
| ICV | Integrity Check Value; truncated HMAC over the packet. |
| Anti-replay window | Sliding window of accepted sequence numbers. |
| Transport mode | AH between original IP and transport header. |
| Tunnel mode | New outer IP + AH + original packet. |
| SAD / SPD | Security Association / Security Policy databases (RFC 4301). |

## Further Reading

- RFC 4301, Security Architecture for the Internet Protocol.
- RFC 4302, IP Authentication Header.
- RFC 4303, IP Encapsulating Security Payload (ESP).
- RFC 4868, Using HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512 with IPsec.
- RFC 7296, Internet Key Exchange Protocol Version 2 (IKEv2).
- NIST SP 800-77 Rev. 1, Guide to IPsec VPNs.
- Niels Ferguson, Bruce Schneier — Practical Cryptography, Chapter 12 (IPsec).