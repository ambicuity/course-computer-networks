# Frame Anatomy Lab

> Every byte on a wired LAN arrives wrapped in an IEEE 802.3 Ethernet frame: a 7-byte preamble, a 1-byte Start Frame Delimiter (SFD, 0xAB), 6-byte destination and 6-byte source MAC addresses, a 2-byte EtherType/Length field, a 46–1500 byte payload, and a 4-byte CRC-32 Frame Check Sequence (FCS) computed with the polynomial 0x04C11DB7. The minimum frame is 64 bytes for a reason — it ties directly to the 51.2 µs slot time of classic 10 Mbps CSMA/CD and the 2,500 m collision domain. This lab teaches you to read a frame the way Wireshark reads it: identify the EtherType (0x0800 IPv4, 0x0806 ARP, 0x86DD IPv6, 0x8100 802.1Q VLAN tag), distinguish a Length value (≤ 1500) from an EtherType (≥ 1536/0x0600), recompute the FCS to catch bit errors, and recognize undersized "runt" and oversized "jumbo" frames. You will build a stdlib-only Python frame parser and CRC-32 calculator (`code/main.py`) that decodes real hex captures, verifies the checksum bit-for-bit, and flags malformed frames. By the end you can take a Wireshark "Copy as Hex Stream" and explain every field, the way an on-call engineer triages a flapping link.

**Type:** Build
**Languages:** Wireshark, Python
**Prerequisites:** Phase 03 lessons on MAC addressing, CSMA/CD, and the data-link layer; basic hex/binary literacy
**Time:** ~90 minutes

## Learning Objectives

- Decode an IEEE 802.3 / Ethernet II frame field-by-field from a raw hex stream, naming each field's byte offset and size.
- Distinguish an EtherType (≥ 0x0600) from an 802.3 Length value (≤ 0x05DC) using the 1536 threshold, and map the common EtherTypes (0x0800, 0x0806, 0x86DD, 0x8100).
- Compute and verify a CRC-32 Frame Check Sequence using the IEEE 802.3 polynomial 0x04C11DB7 and explain why the FCS lives in the trailer, not the header.
- Explain why the minimum payload is 46 bytes (64-byte minimum frame) by linking it to slot time and the collision-domain diameter.
- Identify runt frames (< 64 bytes), giant/jumbo frames (> 1518 bytes), and FCS errors from interface counters and a packet capture.

## The Problem

A user reports that a file copy between two hosts on the same switch is "randomly slow." Ping looks fine. The application team blames the network; the network team blames the application. You SSH into the access switch and run `show interfaces` on the user's port. The link is up at 1 Gbps full-duplex, but you see a counter climbing: `CRC` errors, a few hundred and rising, plus a handful of `runts`.

That counter is the whole story, but only if you can read it. CRC errors mean frames are arriving whose 4-byte FCS no longer matches the data — bits got flipped in transit (a marginal cable, EMI, a failing transceiver, or a duplex mismatch). Runts mean frames shorter than the 64-byte minimum, the classic signature of a half-duplex/full-duplex mismatch producing late collisions. To diagnose this you must understand exactly what a frame is made of, where the FCS sits, and how it is computed — otherwise the counters are just noise. This lab makes the frame concrete: you will parse one by hand and in code, recompute its checksum, and learn the failure modes those counters point to.

## The Concept

### The Ethernet II / 802.3 frame layout

A frame as it appears on the wire, with byte offsets measured from the start of the destination MAC (the preamble and SFD are stripped by the NIC before the frame reaches the capture, so Wireshark's offset 0 is the destination address):

| Offset | Size (bytes) | Field | Notes |
|--------|--------------|-------|-------|
| — | 7 | Preamble | `10101010` × 7, clock sync; not captured |
| — | 1 | SFD | `10101011` (0xAB); marks frame start |
| 0 | 6 | Destination MAC | Unicast, multicast (LSB of first byte = 1), or broadcast `FF:FF:FF:FF:FF:FF` |
| 6 | 6 | Source MAC | Always a unicast address |
| 12 | 2 | EtherType / Length | ≥ 0x0600 → EtherType; ≤ 0x05DC → 802.3 length |
| 14 | 46–1500 | Payload | Padded to 46 if shorter; carries IP, ARP, etc. |
| last 4 | 4 | FCS (CRC-32) | Covers dest MAC through payload; **not** the preamble |

Total frame size ranges from **64 bytes** (minimum, 18 bytes of header/trailer + 46-byte minimum payload) to **1518 bytes** (1500-byte MTU + 18). A 4-byte 802.1Q VLAN tag, when present, sits between the source MAC and the EtherType, pushing the maximum to 1522. The `assets/frame-anatomy-lab.svg` diagram shows this layout to scale so the FCS-in-trailer relationship is visually obvious.

### EtherType vs. Length: the 1536 rule

The same 2-byte field at offset 12 means two different things, disambiguated by a single threshold: **0x0600 = 1536**.

- Value **≤ 1500 (0x05DC)** → it is a **Length** field (original IEEE 802.3). The payload that follows is an 802.2 LLC/SNAP header.
- Value **≥ 1536 (0x0600)** → it is an **EtherType** (Ethernet II / DIX). The value names the upper-layer protocol.

The gap between 1500 and 1536 is intentionally reserved so the two interpretations can never collide. The EtherTypes you will see constantly:

| EtherType | Protocol |
|-----------|----------|
| 0x0800 | IPv4 |
| 0x0806 | ARP |
| 0x86DD | IPv6 |
| 0x8100 | 802.1Q VLAN-tagged frame |
| 0x8847 | MPLS unicast |
| 0x88CC | LLDP |

`code/main.py` implements exactly this branch: it reads the field, compares against 1536, and either prints a known protocol name or labels the frame as 802.3-with-length.

### The Frame Check Sequence: CRC-32

The 4-byte FCS is a cyclic redundancy check over every byte from the destination MAC through the end of the payload (not the preamble or SFD). IEEE 802.3 specifies the CRC-32 polynomial:

```
x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10
     + x^8 + x^7 + x^5 + x^4 + x^2 + x + 1   →  0x04C11DB7
```

The standard algorithm: initialize the register to all-ones (0xFFFFFFFF), process bits LSB-first with the reflected polynomial 0xEDB88320, then XOR the final value with 0xFFFFFFFF. This is the identical CRC-32 used by zlib, PNG, and gzip — which is why `code/main.py` can cross-check its hand-rolled bit-by-bit implementation against Python's `zlib.crc32` and get the same answer.

Flip a single bit anywhere in the covered region and the recomputed CRC will not match the stored FCS — that mismatch is exactly what increments the switch's `CRC` counter. CRC-32 reliably detects all single-bit errors, all double-bit errors, any odd number of bit errors, and any burst error up to 32 bits long.

### Why 64 bytes is the minimum

The 46-byte minimum payload is not arbitrary. In classic 10 Mbps half-duplex Ethernet, CSMA/CD requires that a transmitting station still be sending when the first bit of a collision propagates back to it — otherwise it would never notice the collision. The **slot time** is 512 bit-times = 51.2 µs at 10 Mbps. That slot time bounds the maximum collision-domain diameter (round-trip ≈ 2 × the one-way propagation delay, historically ~2,500 m with repeaters). 512 bits = 64 bytes, so a frame must be at least 64 bytes for collision detection to work. Subtract the 18 bytes of header and FCS and you get the 46-byte payload floor; shorter payloads are zero-padded.

Frames shorter than 64 bytes are **runts**. On a modern full-duplex switched port there are no collisions, but runts still appear — typically from a **late collision** caused by a duplex mismatch (one side half-duplex, one side full), or from a failing NIC truncating frames.

### Sizing edge cases: runts and jumbos

| Condition | Size | Likely cause |
|-----------|------|--------------|
| Runt | < 64 bytes | Late collision, duplex mismatch, truncating NIC |
| Normal | 64–1518 bytes | Healthy frame, standard 1500 MTU |
| Baby giant | 1519–1522 bytes | 802.1Q VLAN tag or small MTU bump |
| Jumbo | up to 9018 bytes | Intentional jumbo-frame MTU (9000) on storage/cluster links |
| Giant (error) | > configured max | MTU mismatch; dropped and counted as `giants` |

Jumbo frames raise the payload to ~9000 bytes to cut per-frame overhead on iSCSI, NFS, and east-west datacenter traffic — but **every device in the path must agree on the MTU**, or the oversized frame is dropped as a giant. `code/main.py` classifies each parsed frame into these buckets so you can spot the anomaly immediately.

### From counters to capture

The diagnostic chain is: interface counter → hypothesis → packet capture → confirmation.

```
show interfaces  →  CRC errors + runts rising
        |
        v
hypothesis: duplex mismatch on this access port
        |
        v
span/mirror the port, capture in Wireshark
        |
        v
filter: eth.fcs.status == "Bad"  and frame.len < 64
        |
        v
confirm: late collisions during high-traffic windows  →  hard-set duplex
```

Wireshark exposes the frame fields directly: `eth.dst`, `eth.src`, `eth.type`, `eth.fcs`, `frame.len`. Because the NIC often offloads FCS validation, you may need to disable checksum offload in Wireshark's Ethernet preferences to see real FCS values rather than the driver's recomputed ones.

## Build It

1. Read `code/main.py` and run it: `python3 main.py`. It ships with three embedded hex frames — an ARP request, an IPv4 packet, and a deliberately corrupted frame.
2. Trace the `parse_frame()` function: note how it slices offset 0–5 (dest), 6–11 (src), 12–13 (EtherType), the middle (payload), and the last 4 bytes (FCS).
3. Follow `crc32_bitwise()` and confirm it matches `zlib.crc32` on the same bytes — this proves the bit-by-bit implementation is correct.
4. Look at `classify_size()` to see the runt/normal/jumbo logic tied to the 64- and 1518-byte boundaries.
5. Capture your own frame: open Wireshark, capture on your active interface, pick any packet, right-click → Copy → "...as a Hex Stream," and paste it into the `CUSTOM_FRAME` constant. Re-run and read your own traffic.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Identify the upper-layer protocol | EtherType bytes at offset 12–13 | You read 0x0800 → IPv4, 0x0806 → ARP without a lookup table |
| Verify frame integrity | Recomputed CRC-32 vs. stored FCS | Your computed value matches the trailer for good frames, mismatches for corrupted ones |
| Distinguish 802.3 from Ethernet II | The offset-12 field vs. the 1536 threshold | You correctly call a value of 0x05DC a Length and 0x0800 an EtherType |
| Triage a sizing anomaly | `frame.len` and the size buckets | You label < 64 as a runt and explain late-collision/duplex causes |
| Map a counter to a field | `show interfaces` CRC/runt counts | You point to the exact byte (FCS) or size rule the counter measures |

## Ship It

Produce one artifact under `outputs/`:

- A frame-decode cheat sheet mapping every byte offset to its field and the common EtherTypes.
- A one-page runbook: "CRC errors / runts on an access port" with the duplex-mismatch decision tree.

Start with [`outputs/prompt-frame-anatomy-lab.md`](../outputs/prompt-frame-anatomy-lab.md) and feed it a real capture.

## Exercises

1. You capture a frame whose offset-12 field is `0x05DC`. Is this an EtherType or a Length? What header do you expect immediately after it, and why can this value never be confused with an EtherType?
2. Take the ARP frame in `code/main.py`, flip the last bit of the source MAC by editing the hex, and re-run. Show that the stored FCS no longer matches and explain which switch counter this would increment in production.
3. A 1522-byte frame arrives on a port configured for a 1500 MTU with no VLAN support. Classify it and predict the interface counter that increments. Now the same frame on an 802.1Q trunk — is it still an error?
4. Compute by hand (or with `crc32_bitwise`) the CRC-32 of the 4-byte payload `DE AD BE EF`. Confirm it equals `zlib.crc32(bytes.fromhex("DEADBEEF"))`.
5. Explain, using slot time and the 51.2 µs figure, why a 10 Mbps Ethernet segment limited to 64-byte minimum frames could not span 10 km even with perfect cabling.
6. Your switch shows rising `runts` but zero `CRC` errors on a full-duplex link. Why does this combination point to a duplex mismatch rather than a bad cable?

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| FCS | "the checksum" | A 4-byte CRC-32 (poly 0x04C11DB7) in the frame **trailer** covering dest-MAC through payload |
| EtherType | "the protocol number" | Offset-12 field ≥ 0x0600; values < 0x0600 are 802.3 Length instead |
| Preamble | "the header start" | 7 bytes of `10101010` for clock sync, stripped by the NIC, never in the capture |
| Runt | "a small packet" | A frame < 64 bytes, usually a late-collision/duplex-mismatch symptom |
| Jumbo frame | "a big packet" | Payload up to ~9000 bytes; requires end-to-end MTU agreement or it's dropped as a giant |
| Slot time | "the Ethernet timing thing" | 512 bit-times (51.2 µs at 10 Mbps); the reason the minimum frame is 64 bytes |
| MTU | "the size limit" | Max **payload** (1500 standard); the frame on the wire is up to 18 bytes larger |
| CRC error | "a corrupt packet" | Stored FCS ≠ recomputed CRC-32; bits flipped after the FCS was written |

## Further Reading

- IEEE 802.3-2022, Clause 3 — MAC Frame and Packet Specification (frame format, FCS, minimum/maximum sizes).
- IEEE 802.1Q-2022 — VLAN tagging (the 4-byte 0x8100 tag and the 1522-byte baby-giant case).
- RFC 894 — *A Standard for the Transmission of IP Datagrams over Ethernet Networks* (EtherType 0x0800).
- RFC 826 — *An Ethernet Address Resolution Protocol* (ARP, EtherType 0x0806).
- RFC 1042 — *Transmission of IP and ARP over IEEE 802 Networks* (the 802.3 LLC/SNAP encapsulation alternative).
- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 4 (the data-link layer, Ethernet, and CSMA/CD).
- Wireshark User's Guide — Ethernet dissector and the `eth.*` / `frame.len` display filters.
