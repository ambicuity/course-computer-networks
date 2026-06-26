# Gigabit Ethernet Carrier Extension, Frame Bursting, and 8B/10B Coding

> Gigabit Ethernet in half-duplex mode reduces the CSMA/CD collision window to just 25 meters — making hub-based LANs impractical — so IEEE 802.3z (1998) introduced **carrier extension** (hardware padding every frame to 512 bytes minimum on the wire) and **frame bursting** (concatenating multiple frames into one 65,536-byte transmission) to stretch the effective collision domain to 200 meters without touching the 64-byte minimum frame size visible to software.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Classic Ethernet physical layer (lesson 08), CSMA/CD and slot time (lesson 10), Fast Ethernet autonegotiation (lesson 14)
**Time:** ~75 minutes

## Learning Objectives

- Derive the 25-meter half-duplex distance limit for 1 Gbps from the 512-bit slot time and explain why it makes hub topologies impractical.
- Explain how carrier extension pads frames at the hardware layer without changing the software-visible 64-byte minimum frame size.
- Calculate worst-case line efficiency when carrier extension carries a 46-byte payload inside a 512-byte padded frame (9%).
- Describe frame bursting: how multiple frames concatenate with inter-frame extension fill, the 65,536-byte burst cap, and when it is more efficient than carrier extension alone.
- Identify 8B/10B encoding used by 1000Base-SX/LX/CX, compute its 25% bandwidth overhead, and explain DC balance via running disparity.
- Describe 1000Base-T signaling: four pairs, PAM-5 at 125 Msymbols/sec per pair, simultaneous bidirectional DSP echo cancellation.

## The Problem

You are upgrading a campus wiring closet from 100 Mbps to 1 Gbps using a 24-port 1000Base-T hub (not a switch). Workstations are within 80 meters of the hub — within the 100-meter Cat5 cable limit. During load testing, the network analyzer reports a collision rate 10× higher than the 100-Mbps setup, and several frames are silently corrupted.

The cause is the CSMA/CD slot time. At 1 Gbps, one bit takes 1 ns. The slot time is 512 bit times × 1 ns = 512 ns. Signal propagation through Cat5 UTP runs at roughly 0.59c (≈ 1.77 × 10^8 m/s). A round-trip through 80 meters takes 80 × 2 / (1.77 × 10^8) ≈ 905 ns — nearly double the slot time. A station transmitting a minimum 64-byte frame finishes in 512 ns and releases the medium before a collision signal from 80 meters away returns. The CSMA/CD guarantee breaks: the sender declares success on a corrupted frame.

Understanding carrier extension — what it is, who adds it, when it is stripped — is the only way to diagnose whether a hub reports false collisions because of a standards violation or because of a NIC that does not understand extension symbols.

## The Concept

### The Slot Time Constraint at 1 Gbps

Classic 10-Mbps Ethernet has a slot time of 512 bit times × 100 ns = 51.2 µs, supporting a maximum cable path of 2,500 m. At 1 Gbps:

```
Slot time = 512 bit times × 1 ns/bit = 512 ns

Propagation speed in Cat5 (velocity factor 0.59):
  v = 0.59 × 3×10^8 m/s = 1.77×10^8 m/s

Maximum one-way distance for 512 ns slot time (before repeater/NIC delays):
  d = (512 ns × 1.77×10^8 m/s) / 2 ≈ 45 m

After accounting for repeater and transceiver delays: ~25 m practical limit
```

This 25-meter limit is useless for any real building LAN. IEEE 802.3z needed to restore a useful collision domain without shrinking the minimum frame size (which would break existing software and drivers).

### Carrier Extension: Mechanism

The solution is to extend the minimum on-wire transmission to 4096 bits (512 bytes) using hardware-generated **extension symbols**, while keeping the minimum MAC frame at 64 bytes.

```
Normal 64-byte MAC frame on the wire:

  Preamble | DA  | SA  | Type | Data+Pad | FCS
  8 bytes  | 6 B | 6 B | 2 B  | 46 B     | 4 B  = 72 bytes total

With carrier extension (hardware appends fill after FCS):

  Preamble | DA  | SA  | Type | Data+Pad | FCS | Extension fill
  8 bytes  |<----  64 byte MAC frame  --->|     | 448 bytes 0x0F
           |<------------ 512 bytes on wire ----------->|
```

The extension symbol is octet **0x0F**, which is a reserved non-data control character in 8B/10B coding — it cannot be confused with frame data. The sending NIC appends it automatically after the FCS. The receiving NIC strips it before delivering the frame to the OS. Every layer above the physical sees a normal 64-byte frame.

**Slot time with carrier extension:**

```
512 bytes × 8 bits/byte × 1 ns/bit = 4096 ns

Maximum cable path for 4096 ns slot:
  d = (4096 ns × 1.77×10^8) / 2 ≈ 362 m

After repeater delays and safety margin: ~200 m
```

### Line Efficiency of Carrier Extension

When carrying a minimum-size payload (46 bytes of user data inside a 64-byte frame), carrier extension wastes 448 bytes of wire bandwidth per frame:

```
Line efficiency  = 64 / 512 = 12.5%
Payload efficiency = 46 / 512 ≈ 9%
```

A gigabit link carrying only minimum-size frames delivers only ~90 Mbps of actual user data. For larger frames the penalty decreases rapidly:

| Payload (bytes) | Frame (bytes) | Wire bytes | Efficiency |
|-----------------|---------------|------------|------------|
| 46              | 64            | 512        | 9%         |
| 100             | 118           | 512        | 20%        |
| 500             | 518           | 518        | 97%        |
| 1500            | 1518          | 1518       | 99%        |

Frames of 464 bytes or larger (payload ≥ 446 bytes) already exceed 512 bytes on the wire and need no extension.

### Frame Bursting: Mechanism

When a sender has multiple queued frames, **frame bursting** is more efficient than carrier extension. The sender transmits frames back-to-back in a single continuous transmission:

```
Burst structure:
[CE-padded frame 1][IFE fill][frame 2][IFE fill][frame 3]...[frame N][normal IFG]
 <-- 512 bytes -->  <12 B>   <normal>  <12 B>
```

Rules (IEEE 802.3z section 4.2.3):
1. First frame uses carrier extension if shorter than 512 bytes.
2. Subsequent frames use **inter-frame extension** (IFE) fill — 12 bytes of 0x0F symbols — instead of a normal interframe gap. This keeps the medium marked as busy.
3. Total burst capped at **65,536 bytes** (8192 bit times = 8192 ns at 1 Gbps).
4. After the burst, a normal IFG (96-bit time, 96 ns) is inserted before the next station can transmit.

**Burst efficiency example (20 queued 64-byte frames):**

```
Total payload: 20 × 46 = 920 bytes
Frame bytes: 20 × 64 = 1280 bytes
CE fill on frame 1: 512 − 64 = 448 bytes
IFE fill between frames: 12 × 19 = 228 bytes

Total wire bytes: 512 + 19×64 + 228 = 1956 bytes
Payload efficiency: 920 / 1956 ≈ 47%
```

Compared to 9% with individual carrier-extended frames — a 5× improvement.

### 8B/10B Encoding (1000Base-SX, LX, CX)

Fiber and short-copper Gigabit Ethernet variants use **8B/10B encoding**, borrowed from Fibre Channel (ANSI X3.230-1994):

**Mechanism:**
Each 8-bit data byte maps to one of two 10-bit codewords (chosen based on **running disparity** — a running tally of excess 1s vs 0s). The codeword pair is selected to keep the running disparity within ±1, ensuring DC balance. Every codeword is designed to have at most 6 consecutive identical bits, guaranteeing clock-recovery transitions.

```
Data byte (8 bits) → 8B/10B encoder → 10-bit codeword
  0xBC → K28.5 (comma character, used for word alignment)
  0x00 → D0.0  (data zero)
  0xFF → D31.7 (data all-ones)
```

Control characters (K-codes) are used for special purposes:
- K28.5: comma sequence for frame/word alignment
- K28.1, K28.7: idle fill between frames
- K23.7, K27.7, K29.7, K30.7: set delimiter codes

**Bandwidth overhead:**

```
8B/10B overhead = (10 − 8) / 8 = 25%

Required signaling rate to deliver 1 Gbps:
  1000 Mbps × (10/8) = 1250 Msymbols/sec = 1.25 Gbaud

Comparison:
  Manchester:    100% overhead (20 MHz for 10 Mbps)
  4B/5B (100TX): 25% overhead (125 MHz for 100 Mbps)
  8B/10B (1 GbE): 25% overhead (1.25 GHz for 1 Gbps)
  64B/66B (10 GbE): ~3.1% overhead
```

### 1000Base-T: PAM-5 over Category 5 UTP

1000Base-T (IEEE 802.3ab, 1999) uses all four twisted pairs of Cat5 and sends in both directions simultaneously on each pair:

```
Signaling:     PAM-5 (5 voltage levels: −2, −1, 0, +1, +2 V)
Symbol rate:   125 Msymbols/sec per pair
Bits/symbol:   ~2 bits (log2(5) = 2.32; exact mapping via Trellis code)
Pairs used:    4 (all pairs carry 250 Mbps bidirectionally)
Total:         4 × 250 Mbps = 1000 Mbps

Techniques required:
  - Digital echo cancellation (DSP): separates TX from RX on same pair
  - Scrambling: improves spectral properties and prevents long DC runs
  - Trellis coding (0, 2): forward error correction embedded in symbol mapping
  - Four-dimensional coding: symbols on all 4 pairs encoded jointly
```

The DSP echo cancellation is what makes 1000Base-T fundamentally different from all earlier Ethernet. There is no simple analog loopback — each NIC runs a continuous adaptive filter that models and subtracts the echo of its own transmission from the received signal. This requires analog front-end processing; 1000Base-T cannot be built from pure digital logic.

### Gigabit Ethernet PAUSE Frames

At 1 Gbps, buffer overruns become likely when a fast sender fills a slower receiver. IEEE 802.3x (1997) defines PAUSE frames:

```
PAUSE frame:
  Destination: 01:80:C2:00:00:01 (reserved multicast, never forwarded by bridges)
  EtherType:   0x8808 (MAC Control)
  Opcode:      0x0001
  Pause time:  0–65535 units
  1 unit = 512 bit times = 512 ns at 1 Gbps
  Maximum pause: 65535 × 512 ns ≈ 33.5 ms
```

PAUSE is symmetric and priority-blind — it halts all traffic from the remote end regardless of application priority. IEEE 802.1Qbb (Priority-based Flow Control, 2011) later added per-priority PAUSE to solve this.

### Jumbo Frames

A non-standard but widely deployed extension allows payloads up to 9,000 bytes (making total frame size 9,018 bytes with header and FCS). Jumbo frames are not in IEEE 802.3 and require explicit configuration on all switches and NICs on the path.

```
Standard MTU:  1500 bytes payload → 1518 bytes frame
Jumbo MTU:     9000 bytes payload → 9018 bytes frame
Efficiency gain: interrupt rate reduced 6× for same throughput
```

### Gigabit Ethernet Cable Standards

| Standard | Medium | Max Length | Encoding | Notes |
|----------|--------|-----------|----------|-------|
| 1000Base-SX | 50/62.5 µm multimode fiber | 550 m | 8B/10B | 0.85 µm, cheaper LEDs |
| 1000Base-LX | 10 µm single-mode fiber | 5000 m | 8B/10B | 1.3 µm laser; also works on 50/62.5 µm MM up to 550 m |
| 1000Base-CX | Shielded twisted pair | 25 m | 8B/10B | Equipment room only |
| 1000Base-T | 4-pair Cat5 UTP | 100 m | PAM-5 + Trellis | Most deployed; IEEE 802.3ab |

## Build It

`code/main.py` provides:

1. **`slot_time_check(speed_bps, distance_m, vf)`** — computes round-trip propagation time and compares to slot time at given line rate; prints whether CSMA/CD works.
2. **`carrier_extension_efficiency(payload_bytes)`** — returns line efficiency and payload efficiency with extension.
3. **`frame_burst_efficiency(frame_count, frame_bytes)`** — returns burst payload efficiency for N identical frames.
4. **`bandwidth_overhead_table()`** — prints Manchester/4B5B/8B10B/64B66B overhead comparison.

Run with:
```
python3 code/main.py
```

No external dependencies. Expected output: slot-time analysis table for 10/100/1000 Mbps, efficiency curves for frame sizes 46–1500 bytes, burst efficiency for queue depths 1–50 frames.

## Use It

| Task | Command | What Good Looks Like |
|------|---------|----------------------|
| Verify 25-m limit | `slot_time_check(1e9, 25, 0.59)` | Round-trip ≈ 508 ns < 512 ns slot — just within spec |
| Verify 80-m failure | `slot_time_check(1e9, 80, 0.59)` | Round-trip ≈ 905 ns > 512 ns — CSMA/CD fails |
| Quantify CE waste | `carrier_extension_efficiency(46)` | Payload efficiency ≈ 9% |
| Measure burst gain | `frame_burst_efficiency(20, 64)` | Payload efficiency rises to ~47% |
| Find PAUSE frames | `tcpdump -i eth0 ether proto 0x8808` | PAUSE frames visible during incast stress test |

## Ship It

```
python3 code/main.py > outputs/gigabit-extension-report.txt
```

Output includes: slot-time analysis table, carrier extension efficiency for all standard frame sizes, burst efficiency curve, encoding overhead comparison.

## Exercises

1. **Slot time arithmetic:** A 1-Gbps hub connects two stations 70 meters apart over Cat5 (velocity factor 0.59). The hub adds 4 bit times of delay. Compute the round-trip time in nanoseconds. Does CSMA/CD work correctly without carrier extension? What is the minimum padded frame size (in bytes) that would guarantee collision detection at this distance?

2. **Carrier extension waste:** A link carries 60% minimum-size frames (64 bytes) and 40% maximum-size frames (1518 bytes). Compute the weighted average wire efficiency with carrier extension. Then compute it for a switched link where carrier extension is never applied. What is the throughput difference at 1 Gbps?

3. **Burst structure:** A sender queues 35 frames: 25 are 64-byte frames and 10 are 800-byte frames. Describe how the first burst is structured: first frame CE padding, IFE fill between frames, total wire bytes. Does the burst stay under the 65,536-byte cap? How many bursts are needed to send all 35 frames?

4. **8B/10B vs 64B/66B:** Calculate the raw signaling rate needed to deliver 10 Gbps of user throughput using 8B/10B encoding. Then calculate it with 64B/66B encoding. Explain why 10-Gigabit Ethernet switched to 64B/66B and why Gigabit Ethernet could not use it.

5. **PAUSE frame timing:** A Wireshark trace shows PAUSE frames with pause_time = 0xFFFF (65535 units) arriving at a 1-Gbps NIC every 25 ms. What fraction of airtime is the sender being suppressed? What does this pattern imply about the receiver's buffer fill rate?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Carrier extension | "GigE padding" | Hardware-appended 0x0F fill bytes after the FCS extending total on-wire transmission to 512 bytes; transparent to software |
| Frame bursting | "burst mode" | Concatenating multiple frames in one transmission with IFE fill to keep medium busy; capped at 65,536 bytes |
| Slot time (1 Gbps) | "collision window" | 512 bit times × 1 ns = 512 ns; limits half-duplex cable to ~25 m without carrier extension |
| 8B/10B | "eight-ten coding" | Maps 8 data bits to 10-bit codewords for DC balance and clock recovery; 25% overhead; used in all fiber/STP GigE variants |
| Running disparity | "RD" | Signed running tally of excess 1s vs 0s in 8B/10B stream; kept within ±1 to maintain DC balance |
| PAM-5 | "five-level signaling" | Voltage levels −2,−1,0,+1,+2 used in 1000Base-T; ~2 bits per symbol; requires DSP echo cancellation |
| PAUSE frame | "flow control frame" | EtherType 0x8808 opcode 0x0001; halts remote transmitter for up to 33.5 ms at 1 Gbps |
| Jumbo frame | "9K MTU" | Non-standard payload up to 9000 bytes; reduces interrupt rate 6×; requires end-to-end configuration |
| Inter-frame extension | "IFE fill" | 12 bytes of 0x0F symbols inserted between frames in a burst to keep medium marked as busy |
| 1000Base-T | "GigE over copper" | IEEE 802.3ab; four-pair Cat5 UTP; 125 Msymbols/sec PAM-5 per pair; bidirectional via DSP echo cancellation |

## Further Reading

- **IEEE 802.3z-1998** — Gigabit Ethernet for fiber and STP; sections 35–39 define carrier extension, frame bursting, 8B/10B coding, and 1000Base-SX/LX/CX.
- **IEEE 802.3ab-1999** — 1000Base-T; section 40 defines PAM-5 signaling, Trellis coding, and four-pair autonegotiation.
- **IEEE 802.3x-1997** — MAC Control sublayer and PAUSE frames; EtherType 0x8808 definition.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 4.3.6 — source textbook coverage of carrier extension, frame bursting, and gigabit cabling.
- Spurgeon, C. E., *Ethernet: The Definitive Guide*, O'Reilly, 2000 — Chapter 9 covers all gigabit variants; Chapter 10 covers 1000Base-T signaling in detail.
- ANSI X3.230-1994 (Fibre Channel) — original 8B/10B encoding specification from which Gigabit Ethernet borrowed the coding scheme.
