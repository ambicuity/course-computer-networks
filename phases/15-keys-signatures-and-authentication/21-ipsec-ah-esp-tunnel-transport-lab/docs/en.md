# IPsec AH and ESP in Transport and Tunnel Mode Lab

> Every byte in an IPsec header has a job — learn the layout, and you can read a packet capture the way a mechanic reads an engine.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 14 lessons on symmetric encryption and HMAC; Phase 15 lessons on keys and signatures; basic IPv4 header structure
**Time:** ~75 minutes

## Learning Objectives

- Read the byte-level layout of the AH header (RFC 4302): Next Header, Payload Length, Reserved, SPI, Sequence Number, and ICV fields.
- Read the byte-level layout of the ESP header and trailer (RFC 4303): SPI, Sequence Number, IV, encrypted payload, Padding, Pad Length, Next Header, and ICV fields.
- Distinguish which IP header bytes AH authenticates versus leaves mutable, and explain why those mutable fields are excluded.
- Contrast transport mode and tunnel mode: which IP header survives, which is added, and what each mode exposes to an eavesdropper.
- Construct and parse synthetic AH and ESP datagrams in both modes using Python's `hmac` and `hashlib` modules.
- Explain why AH fails through NAT and ESP does not, and articulate the practical implication for VPN deployments.

## The Problem

A security engineer is asked to verify that all traffic between two corporate sites is protected by IPsec before it crosses the public Internet. She fires up Wireshark, sees packets with protocol numbers 50 and 51, and needs to interpret every field. The team uses both AH and ESP, and the tunnel terminates at two firewalls running in tunnel mode, but some host-to-host sessions between servers on the same LAN use transport mode. Without a precise mental model of the wire format, she cannot tell from a capture whether the ICV covers the outer IP header or only the payload, whether the source address is authenticated, or whether an ESP packet that passes the ICV check actually decrypted correctly.

The second problem is NAT. The company's older branch office sits behind a NAT box. AH authenticates the IP source address; a NAT device rewrites that address, which breaks the ICV check. Nobody warned the team. Knowing the exact bytes that AH covers — and which bytes ESP covers — is what lets engineers predict this failure before it happens in production.

Understanding the wire format also matters for MTU planning. Tunnel mode adds a complete 20-byte outer IP header on top of the AH or ESP header. On a 1500-byte Ethernet path, a 1400-byte inner TCP segment plus a 20-byte inner IP header plus a 24-byte ESP header plus a 16-byte IV plus 12 bytes of HMAC-SHA-1 ICV plus padding can easily exceed 1500 bytes. Engineers who cannot compute the byte overhead cannot set the correct TCP MSS clamp.

## The Concept

### AH Header Layout (RFC 4302)

AH is IP protocol number 51. It provides integrity, data-origin authentication, and anti-replay. It does not encrypt anything.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Next Header  |  Payload Len  |          RESERVED             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Security Parameters Index (SPI)               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Sequence Number                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+         Integrity Check Value (ICV, variable length)          +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Value / Purpose |
|-------|------|-----------------|
| Next Header | 8 bits | IP protocol of the payload (6 = TCP, 17 = UDP, 4 = IP-in-IP for tunnel) |
| Payload Length | 8 bits | Length of the AH header in 32-bit words, minus 2. Fixed-size HMAC-SHA-1 AH = 4 (6 words − 2) |
| Reserved | 16 bits | Must be zero; receiver ignores |
| SPI | 32 bits | Identifies the SA; receiver uses (SPI, dest IP, protocol 51) to find shared key |
| Sequence Number | 32 bits | Monotonically increasing per-packet counter; never wraps; anti-replay |
| ICV | 96 bits (HMAC-SHA-1) or 128 bits (HMAC-SHA-256) | HMAC over authenticated fields; truncated to 96 bits for SHA-1 |

**What AH authenticates:** AH computes its ICV over the entire packet — the outer IP header (with mutable fields zeroed), the AH header itself (ICV field zeroed during computation), and the payload. Fields treated as zero during computation include TTL, DSCP, Flags, and the IP checksum, because routers modify those fields in transit. The source and destination IP addresses are included and are not zeroed — this is the field NAT breaks.

**What AH does not encrypt:** Nothing. A Wireshark capture of AH traffic shows the full TCP headers and application data in the clear.

### ESP Header and Trailer Layout (RFC 4303)

ESP is IP protocol number 50. It provides confidentiality (encryption), integrity, and anti-replay.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|               Security Parameters Index (SPI)                 |   ← plaintext
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Sequence Number                           |   ← plaintext
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                  Initialization Vector (IV)                   |   ← plaintext
~                      (algorithm-specific)                     ~
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Payload Data (encrypted)                   |   ← ciphertext
~                                                               ~
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                 Padding (0–255 bytes, encrypted)              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Pad Length  |  Next Header  |                               |   ← ciphertext
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+                               +
|               Integrity Check Value (ICV)                     |   ← plaintext after trailer
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Value / Purpose |
|-------|------|-----------------|
| SPI | 32 bits | SA identifier, sent in the clear |
| Sequence Number | 32 bits | Anti-replay counter, sent in the clear |
| IV | algorithm-specific | AES-CBC: 16 bytes; AES-CTR: 8 bytes; not secret, must be unique |
| Payload Data | variable | Encrypted transport segment (transport) or encrypted inner IP packet (tunnel) |
| Padding | 0–255 bytes | Aligns payload to cipher block boundary; also obscures true payload length |
| Pad Length | 8 bits | Number of padding bytes added; must be accurate for correct decryption |
| Next Header | 8 bits | Protocol of the encrypted payload (6 = TCP, 4 = IP-in-IP) |
| ICV | 96 or 128 bits | HMAC computed over SPI + Seq + IV + ciphertext + trailer (Pad + Pad Length + Next Header) |

**Encryption boundary:** The SPI and Sequence Number are always in the clear — the receiver needs them to locate the SA and key before it can decrypt. The IV is also in the clear (it is random, not secret). Everything from the payload data through Next Header is encrypted. The ICV is appended after encryption, also in the clear, so the receiver can verify integrity before spending time decrypting.

**ICV boundary for ESP:** ESP's ICV does not cover the outer IP header. This is the key difference from AH. A NAT device rewrites the source address in the outer IP header — ESP's ICV check still passes because ESP does not authenticate that field. AH's ICV does authenticate it, so AH fails through NAT.

### Transport Mode vs. Tunnel Mode

Transport mode inserts the AH or ESP header between the original IP header and the transport-layer header (TCP, UDP). The original IP header is preserved with only the Protocol field updated (to 51 for AH, 50 for ESP). The source and destination addresses remain the original host addresses.

Tunnel mode wraps the entire original IP packet — including the original IP header — inside a new outer IP packet. The outer IP header carries the gateway-to-gateway addresses. The inner IP header, now part of the encrypted payload (for ESP) or authenticated payload (for AH), carries the original host addresses.

```
ORIGINAL PACKET:
┌────────────┬────────────┬──────────────────────┐
│  IP Header  │ TCP Header │      Payload          │
│ src=10.1.1.5│  (20 B)    │  "GET / HTTP/1.1"     │
│ dst=10.2.1.9│            │                       │
└────────────┴────────────┴──────────────────────┘

AH TRANSPORT MODE (protocol=51 in IP header):
┌────────────┬────────────┬────────────┬──────────────────────┐
│  IP Header  │  AH Header │ TCP Header │      Payload          │
│ proto=51    │ next=6     │            │   (all in clear)      │
│             │ SPI+Seq    │            │                       │
│             │ ICV covers │            │                       │
│             │ ←────────────────────────────────────────────→ │
└────────────┴────────────┴────────────┴──────────────────────┘
 ICV covers: zeroed-IP-hdr + AH-hdr(ICV=0) + TCP-hdr + payload

ESP TRANSPORT MODE (protocol=50 in IP header):
┌────────────┬────────────┬─────────────────────────────────┬──────┐
│  IP Header  │  ESP Header│  [ TCP Header + Payload ]       │ ICV  │
│ proto=50    │ SPI + Seq  │  + Padding + PadLen + NextHdr   │(12B) │
│             │ IV (16 B)  │  ← ALL ENCRYPTED →              │      │
│             │←─ ICV covers SPI+Seq+IV+ciphertext+trailer ─→│      │
└────────────┴────────────┴─────────────────────────────────┴──────┘

AH TUNNEL MODE (outer proto=51, inner proto=6):
┌──────────────┬────────────┬──────────────┬────────────┬──────────┐
│ Outer IP Hdr │  AH Header │ Inner IP Hdr │ TCP Header │ Payload  │
│ src=gw-A     │ next=4     │ src=10.1.1.5 │            │(in clear)│
│ dst=gw-B     │ SPI+Seq    │ dst=10.2.1.9 │            │          │
│ proto=51     │ ICV→       │              │            │          │
│  ←───────── ICV covers: zeroed-outer-IP + AH + inner-IP + TCP + payload ──────────→ │
└──────────────┴────────────┴──────────────┴────────────┴──────────┘

ESP TUNNEL MODE (outer proto=50, inner proto=6):
┌──────────────┬────────────┬───────────────────────────────────────────┬──────┐
│ Outer IP Hdr │  ESP Header│  [ Inner IP + TCP Header + Payload ]      │ ICV  │
│ src=gw-A     │ SPI + Seq  │  + Padding + PadLen + NextHdr             │(12B) │
│ dst=gw-B     │ IV (16 B)  │  ← ALL ENCRYPTED →                       │      │
│ proto=50     │←── ICV covers SPI+Seq+IV+ciphertext+trailer ──────────→│      │
└──────────────┴────────────┴───────────────────────────────────────────┴──────┘
```

| Aspect | Transport Mode | Tunnel Mode |
|--------|---------------|-------------|
| Original IP header | Preserved (Protocol field updated) | Encapsulated inside; new outer header added |
| Inner source/destination | Visible in outer header | Hidden inside encrypted payload (ESP) |
| AH ICV scope | Zeroed outer IP + AH + TCP + payload | Zeroed outer IP + AH + inner IP + TCP + payload |
| ESP ICV scope | SPI + Seq + IV + ciphertext | SPI + Seq + IV + ciphertext (inner IP is ciphertext) |
| MTU overhead (ESP, AES-CBC, HMAC-SHA-1) | ~36 bytes (8 ESP + 16 IV + 12 ICV) | ~56 bytes (+20 outer IP) |
| Traffic analysis exposure | Source and destination hosts visible | Only gateways visible |
| NAT compatibility (AH) | Fails — source IP authenticated | Fails — outer source IP authenticated |
| NAT compatibility (ESP) | Works with NAT-T (UDP encapsulation) | Works with NAT-T |
| Typical use | Host-to-host on same site | Site-to-site VPN, remote access VPN |

### Why AH Breaks Through NAT

AH's ICV computation includes the source IP address from the outer IP header. A NAT device rewrites this address as the packet crosses the NAT boundary. On arrival, the receiver recomputes the ICV using the now-translated source address. The two values do not match. The packet is dropped. This is not a bug — it is a deliberate design: AH is supposed to prove the packet arrived unmodified, including the source address. The fundamental incompatibility between AH and NAT is why AH is rarely used in modern deployments. ESP with NAT Traversal (RFC 3948) — which wraps ESP inside UDP port 4500 — avoids this because UDP headers are not part of the ESP ICV.

### Anti-Replay: The Sequence Number

Both AH and ESP include a 32-bit Sequence Number. It starts at 1 for the first packet in an SA and increments by 1 for every subsequent packet. The sender never reuses a value. The receiver maintains a sliding acceptance window (default 64 packets wide) and drops any packet whose sequence number falls outside the window or has already been seen. When the 32-bit space is exhausted — after 2^32 packets — the SA must be renegotiated. Wrapping is not permitted: a repeated sequence number would allow replay attacks against an authenticated or encrypted session.

### Byte Overhead Comparison

For a 1400-byte TCP payload over a 1500-byte Ethernet MTU path (HMAC-SHA-1, AES-CBC 128):

| Mode + Protocol | Added bytes | Room for payload |
|-----------------|-------------|-----------------|
| AH transport | 24 (12 fixed + 12 ICV) | 1476 |
| ESP transport (AES-CBC) | 8 ESP + 16 IV + up to 15 pad + 2 trailer + 12 ICV = ~53 | ~1447 |
| AH tunnel | 24 AH + 20 outer IP = 44 | 1456 |
| ESP tunnel (AES-CBC) | 20 outer IP + 8 ESP + 16 IV + up to 15 pad + 2 trailer + 12 ICV = ~73 | ~1427 |

Tunnel-mode ESP has the highest overhead. On a standard 1500-byte Ethernet MTU, a TCP session sending 1400-byte segments will experience fragmentation unless the MSS is clamped to ~1360 bytes (accounting for inner IP + TCP headers + ESP tunnel overhead).

## Build It

The Python program in `code/main.py` constructs and parses all four combinations — AH transport, ESP transport, AH tunnel, ESP tunnel — using only the standard library. Each combination: assembles a synthetic inner IP packet as raw bytes, wraps it with the correct header layout, computes the ICV using `hmac` and `hashlib`, prints a labeled hexdump and field breakdown, then parses the result back and asserts round-trip integrity.

### Step 1: Construct a synthetic inner IP packet

The inner packet is a minimal IPv4 header (20 bytes) followed by a TCP header (20 bytes) followed by a small payload string. All fields are realistic but synthetic — the program does not open any sockets.

```python
import struct, hashlib, hmac, os

SRC_HOST  = bytes([10, 1, 1, 5])
DST_HOST  = bytes([10, 2, 1, 9])
SRC_GW    = bytes([192, 168, 100, 1])
DST_GW    = bytes([192, 168, 200, 1])

def make_ipv4_header(src: bytes, dst: bytes, proto: int, payload_len: int) -> bytes:
    total_len = 20 + payload_len
    return struct.pack("!BBHHHBBH4s4s",
        0x45, 0, total_len, 0, 0, 64, proto, 0, src, dst)

def make_tcp_header(sport: int, dport: int) -> bytes:
    return struct.pack("!HHLLBBHHH",
        sport, dport, 1000, 0, 0x50, 0x18, 65535, 0, 0)

PAYLOAD = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
tcp_hdr = make_tcp_header(54321, 80)
inner_ip = make_ipv4_header(SRC_HOST, DST_HOST, 6, len(tcp_hdr) + len(PAYLOAD))
```

### Step 2: Build an AH header

AH's fixed header is 12 bytes: 1 byte Next Header, 1 byte Payload Length (in 32-bit words minus 2; HMAC-SHA-1 produces a 12-byte ICV, so total AH = 24 bytes = 6 words, Payload Length = 4), 2 bytes Reserved, 4 bytes SPI, 4 bytes Sequence Number. The ICV appended after is 12 bytes (HMAC-SHA-1 truncated to 96 bits per RFC 4302).

```python
AH_PROTO   = 51
ESP_PROTO  = 50
HMAC_SHA1_ICV_LEN = 12  # 96 bits, per RFC 4302

SPI_AH_TRANSPORT  = 0x0A000001
SPI_ESP_TRANSPORT = 0x0B000001
SPI_AH_TUNNEL     = 0x0C000001
SPI_ESP_TUNNEL    = 0x0D000001

MAC_KEY = b"mac-key-for-lab-demo-only!!!!!" + b"\x00" * 2  # 32 bytes

def compute_icv(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha1).digest()[:HMAC_SHA1_ICV_LEN]

def build_ah_header(next_header: int, spi: int, seq: int) -> bytes:
    payload_len = 4  # (24 bytes / 4) - 2 = 4
    return struct.pack("!BBHII", next_header, payload_len, 0, spi, seq)

def zero_mutable_ipv4(ip_hdr: bytes) -> bytes:
    h = bytearray(ip_hdr)
    h[8]  = 0   # TTL
    h[9]  = 0   # Protocol (will be set to AH)
    h[10] = 0   # checksum high
    h[11] = 0   # checksum low
    return bytes(h)
```

### Step 3: Assemble AH transport-mode packet and compute ICV

In transport mode, the ICV covers: the outer IP header (mutable fields zeroed, Protocol set to 51, ICV field treated as zero), the fixed AH header (ICV field zeroed), and the original TCP header plus payload.

```python
def build_ah_transport(inner_ip, tcp_hdr, payload, spi, seq, mac_key):
    ah_fixed = build_ah_header(next_header=6, spi=spi, seq=seq)
    ah_icv_placeholder = bytes(HMAC_SHA1_ICV_LEN)
    outer_ip = bytearray(inner_ip)
    outer_ip[9] = AH_PROTO
    zeroed_outer = zero_mutable_ipv4(bytes(outer_ip))
    icv_input = zeroed_outer + ah_fixed + ah_icv_placeholder + tcp_hdr + payload
    icv = compute_icv(mac_key, icv_input)
    packet = bytes(outer_ip) + ah_fixed + icv + tcp_hdr + payload
    return packet, icv
```

### Step 4: Assemble ESP transport-mode packet

ESP encrypts the TCP header and payload (this lab uses XOR with an HMAC-derived keystream as a stand-in for AES; the wire format is identical). The IV is 16 random bytes. Padding aligns the payload to a 16-byte block boundary. The ICV covers SPI + Seq + IV + ciphertext + trailer.

```python
def pad_to_block(data: bytes, block: int) -> tuple[bytes, int]:
    pad_needed = (block - (len(data) + 2) % block) % block
    padding = bytes(range(1, pad_needed + 1))
    return data + padding, pad_needed

def keystream(key: bytes, iv: bytes, length: int) -> bytes:
    ks = b""
    counter = 0
    while len(ks) < length:
        ks += hmac.new(key, iv + struct.pack("!Q", counter), hashlib.sha256).digest()
        counter += 1
    return ks[:length]

def build_esp_transport(inner_ip, tcp_hdr, payload, spi, seq, enc_key, mac_key):
    iv = os.urandom(16)
    plaintext = tcp_hdr + payload
    padded, pad_len = pad_to_block(plaintext, 16)
    trailer = bytes([pad_len, 6])     # pad_length, next_header=TCP
    plaintext_with_trailer = padded + trailer
    ks = keystream(enc_key, iv, len(plaintext_with_trailer))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext_with_trailer, ks))
    esp_hdr = struct.pack("!II", spi, seq)
    icv_input = esp_hdr + iv + ciphertext
    icv = compute_icv(mac_key, icv_input)
    outer_ip = bytearray(inner_ip)
    outer_ip[9] = ESP_PROTO
    packet = bytes(outer_ip) + esp_hdr + iv + ciphertext + icv
    return packet, iv, ciphertext, icv
```

### Step 5: Tunnel mode — add outer IP header

In tunnel mode, a new outer IP header is prepended. For AH tunnel, the ICV covers zeroed-outer-IP + AH + inner-IP + TCP + payload. For ESP tunnel, the entire inner IP packet (plus TCP and payload) is the plaintext that gets encrypted; the new outer IP header is not authenticated by ESP's ICV.

```python
def make_outer_ip(src_gw, dst_gw, proto, payload_len):
    total = 20 + payload_len
    return struct.pack("!BBHHHBBH4s4s",
        0x45, 0, total, 0, 0, 64, proto, 0, src_gw, dst_gw)

def build_ah_tunnel(inner_ip, tcp_hdr, payload, spi, seq, mac_key):
    inner_pkt = inner_ip + tcp_hdr + payload
    ah_fixed = build_ah_header(next_header=4, spi=spi, seq=seq)  # 4 = IP-in-IP
    ah_icv_placeholder = bytes(HMAC_SHA1_ICV_LEN)
    outer_ip_raw = make_outer_ip(SRC_GW, DST_GW, AH_PROTO,
                                  len(ah_fixed) + HMAC_SHA1_ICV_LEN + len(inner_pkt))
    zeroed_outer = zero_mutable_ipv4(outer_ip_raw)
    icv_input = zeroed_outer + ah_fixed + ah_icv_placeholder + inner_pkt
    icv = compute_icv(mac_key, icv_input)
    packet = outer_ip_raw + ah_fixed + icv + inner_pkt
    return packet, icv

def build_esp_tunnel(inner_ip, tcp_hdr, payload, spi, seq, enc_key, mac_key):
    iv = os.urandom(16)
    plaintext = inner_ip + tcp_hdr + payload
    padded, pad_len = pad_to_block(plaintext, 16)
    trailer = bytes([pad_len, 4])      # next_header=4 means IP-in-IP
    plaintext_with_trailer = padded + trailer
    ks = keystream(enc_key, iv, len(plaintext_with_trailer))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext_with_trailer, ks))
    esp_hdr = struct.pack("!II", spi, seq)
    icv_input = esp_hdr + iv + ciphertext
    icv = compute_icv(mac_key, icv_input)
    outer_ip = make_outer_ip(SRC_GW, DST_GW, ESP_PROTO,
                              len(esp_hdr) + 16 + len(ciphertext) + HMAC_SHA1_ICV_LEN)
    packet = outer_ip + esp_hdr + iv + ciphertext + icv
    return packet, iv, ciphertext, icv
```

### Step 6: Parse and verify each packet

The parse path extracts each field from its known byte offset, recomputes the ICV, and asserts it matches the received value. For ESP, it also decrypts the ciphertext and checks that the recovered plaintext starts with the original inner packet bytes.

```python
def verify_ah_transport(packet, mac_key):
    outer_ip = packet[:20]
    ah_fixed  = packet[20:32]
    received_icv = packet[32:44]
    rest = packet[44:]
    zeroed = zero_mutable_ipv4(outer_ip)
    icv_input = zeroed + ah_fixed + bytes(HMAC_SHA1_ICV_LEN) + rest
    expected = compute_icv(mac_key, icv_input)
    return expected == received_icv

def verify_esp_transport(packet, enc_key, mac_key):
    outer_ip = packet[:20]
    esp_hdr  = packet[20:28]
    iv       = packet[28:44]
    body     = packet[44:]
    ciphertext = body[:-HMAC_SHA1_ICV_LEN]
    received_icv = body[-HMAC_SHA1_ICV_LEN:]
    icv_input = esp_hdr + iv + ciphertext
    expected = compute_icv(mac_key, icv_input)
    if expected != received_icv:
        return False, b""
    ks = keystream(enc_key, iv, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, ks))
    return True, plaintext
```

## Use It

Once you have run `python3 code/main.py` and verified the four builds pass their assertions, use the following table to map each labeled output line to a field in the RFC.

| Output label | RFC field | Where it lives |
|---|---|---|
| `SPI` | Security Parameters Index | AH bytes 4–7; ESP bytes 0–3 |
| `Seq` | Sequence Number | AH bytes 8–11; ESP bytes 4–7 |
| `ICV` | Integrity Check Value | AH bytes 12–23 (HMAC-SHA-1); ESP last 12 bytes |
| `IV` | Initialization Vector | ESP bytes 8–23 (AES-CBC 16 bytes) |
| `NextHdr` | Next Header | AH byte 0; inside ESP trailer (encrypted) |
| `PadLen` | Pad Length | Inside ESP trailer (encrypted), second-to-last byte |

To extend to Wireshark: capture any IPsec-protected traffic, right-click a packet, choose "Decode As", and select the appropriate protocol (50 for ESP, 51 for AH). Wireshark will label every field in the panel below using the same field names as the RFC and as the output from `main.py`.

Use `ip xfrm state` on Linux to observe a live SA's SPI, algorithm, and byte counters. Match the SPI printed by the kernel against the SPI you see in a Wireshark capture. They must agree.

## Ship It

This lesson produces one reusable artifact in `outputs/`:

- `prompt-ipsec-ah-esp-tunnel-transport-lab.md` — an evidence-first study prompt that maps the IPsec wire format to observable packet fields, practical diagnostic checks, and failure modes.

Use the prompt when reviewing a VPN configuration, diagnosing a NAT-T failure, or preparing for a security audit that asks for proof that IPsec is correctly applied. The prompt instructs the model to stay grounded in specific observable bytes and fields — not in abstract protocol summaries.

## Exercises

1. Compute the exact byte overhead of AH transport mode versus ESP tunnel mode (HMAC-SHA-1, AES-CBC 128-bit, 16-byte IV) for a 1400-byte TCP payload with a 20-byte TCP header and 20-byte inner IP header. Which mode consumes more bytes, and by how much?

2. Modify `code/main.py` to tamper with one byte of the ciphertext in an ESP transport packet, then call the verify function. Confirm the ICV check fails. Now tamper with one byte of the outer IP header in an AH transport packet. Confirm the ICV check fails. Compare the two failure paths.

3. An engineer configures AH tunnel mode on a firewall that sits behind a corporate NAT. Describe step by step which byte the NAT device rewrites, why the ICV computed by the receiver differs from the sender's ICV, and what error the receiver logs.

4. The RFC 4302 specification says that the Payload Length field in the AH header is the length of the AH header in 32-bit words minus 2. For HMAC-SHA-1 (12-byte ICV), verify this: count the 32-bit words in the AH header and confirm the formula yields 4.

5. Implement a 32-entry sliding anti-replay window. When the lab program sends packets with sequence numbers 1, 2, 3, 64, 65, then replays 2, confirm the replay is detected. Then send sequence number 1000 and confirm that sequence numbers below 936 are now outside the window.

6. Extend `build_esp_transport` to use AEAD mode: drop the separate HMAC step and instead derive the ICV from an AES-GCM-style combined operation (simulate using HMAC over the associated data separately, then XOR-encrypt). Compare the resulting packet size to the split encrypt+ICV version.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| AH | "the one that doesn't encrypt" | IP Authentication Header (RFC 4302); provides integrity, data-origin authentication, and anti-replay; covers part of the IP header in its ICV; protocol number 51 |
| ESP | "the encrypting one" | Encapsulating Security Payload (RFC 4303); provides confidentiality, integrity, and anti-replay; ICV does not cover outer IP header; protocol number 50 |
| SPI | "the connection ID" | Security Parameters Index; a 32-bit value in every AH/ESP header; receiver uses (SPI, destination IP, protocol) to look up the shared key and algorithm |
| ICV | "the signature" | Integrity Check Value; an HMAC truncated to 96 bits (SHA-1) or 128 bits (SHA-256); proves the packet was not modified in transit |
| Transport mode | "host-to-host" | IPsec header inserted between original IP header and transport header; original IP addresses remain in outer header; smaller overhead |
| Tunnel mode | "the VPN mode" | Entire original IP packet encapsulated inside a new outer IP packet; hides inner addresses; used for site-to-site VPNs |
| NAT-T | "ESP through NAT" | NAT Traversal (RFC 3948); wraps ESP in UDP port 4500 so NAT devices can rewrite the UDP header without breaking the ESP ICV |
| Anti-replay window | "duplicate detection" | Sliding window of accepted sequence numbers; packets outside the window or already seen are silently dropped |
| Mutable field | "the TTL problem" | IPv4 fields that routers legitimately modify in transit (TTL, DSCP, checksum); AH zeros these before computing the ICV to avoid false failures |
| Next Header | "the protocol byte" | AH byte 0 or ESP trailer field; names the protocol of the protected payload (6=TCP, 17=UDP, 4=IP-in-IP) |

## Further Reading

- RFC 4302 — IP Authentication Header (AH): complete field definitions and ICV coverage rules
- RFC 4303 — IP Encapsulating Security Payload (ESP): complete field definitions, padding rules, and ICV boundary
- RFC 4301 — Security Architecture for the Internet Protocol: SA database, policy database, and processing rules
- RFC 3948 — UDP Encapsulation of IPsec ESP Packets (NAT Traversal): why and how NAT-T works
- RFC 2410 — The NULL Encryption Algorithm: when to use ESP without encryption (integrity-only, replaces AH in modern deployments)
- Tanenbaum and Wetherall, Computer Networks, 5th ed., §8.6.1: concise textbook treatment of IPsec modes with diagrams
- Ferguson and Schneier, Practical Cryptography, Chapter 12: implementation-level analysis of IPsec's design decisions and weaknesses
