# Classic Ethernet Physical Layer: Manchester Encoding, Thick/Thin Coax, and Repeaters

> Classic Ethernet (IEEE 802.3, 1983) ran at 10 Mbps over shared coaxial cable using **Manchester encoding** — a biphase line code that XORs the clock at twice the bit rate with the data stream, guaranteeing a mid-bit transition on every symbol and embedding clock recovery without a separate timing channel. A high-to-low mid-bit transition encodes a logical 1; a low-to-high encodes a 0. The bandwidth cost is exactly 2× NRZ: 10 Mbps Ethernet requires a 20 MHz analog bandwidth budget. **Thick Ethernet (10BASE5)** used RG-8/U 50 Ω coaxial cable with a maximum segment length of 500 m, up to 100 transceivers per segment spaced at least 2.5 m apart (vampire-tap MAUs attached via 15-pin AUI cables). **Thin Ethernet (10BASE2)** replaced vampire taps with BNC T-connectors on RG-58/U coax, limiting segments to 185 m and 30 stations. **Repeaters** regenerate and re-drive signals at the physical layer; they are invisible to the MAC — a chain of segments separated by repeaters looks like one wire. The hard constraints were: maximum 2.5 km between any two transceivers, maximum 4 repeaters on any path (the **5-4-3 rule**: 5 segments, 4 repeaters, 3 populated), and these limits exist to keep the round-trip propagation time within the 512-bit-time (51.2 µs) **slot time** that CSMA/CD collision detection requires.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Physical layer line codes (NRZ, NRZI), CSMA/CD basics, coaxial cable fundamentals
**Time:** ~60 minutes

## Learning Objectives

- Explain Manchester encoding as XOR(clock, data) and compute the bandwidth overhead relative to NRZ for a 10 Mbps link.
- Contrast 10BASE5 and 10BASE2 in terms of cable type, segment length, maximum stations, and connector mechanism.
- Describe what a repeater does at the physical layer and why it does not affect MAC-layer addressing.
- Apply the 5-4-3 rule to determine whether a proposed multi-segment Ethernet topology is standards-compliant.
- Calculate the minimum valid frame size (64 bytes) from the slot time and explain why short frames violate CSMA/CD.
- Identify the 8-byte preamble structure (10101010 × 7 + 10101011 SFD) and its role in clock synchronization.

## The Problem

You are tasked with auditing a building LAN installed in 1991. The topology diagram shows four thick-Ethernet segments connected by three repeaters, with a fifth segment attached via a fourth repeater. The cable run from the farthest two stations is measured at 2.6 km. Workstations occasionally report frame corruption and intermittent carrier loss, especially at low traffic. The symptoms are classic: the network violates both the 2.5 km transceiver limit and borderline the 5-4-3 rule's populated-segment constraint. Before replacing hardware, you need to understand why these physical-layer limits exist and what failure modes they produce at the MAC layer — specifically, why a 2.6 km cable produces false "no collision" readings and why a repeater count exceeding four silently degrades CSMA/CD.

## The Concept

### Manchester Encoding: Mechanism

Manchester encoding solves two problems simultaneously: clock recovery and DC balance. NRZ (Non-Return-to-Zero) maps 1 → +V and 0 → -V, which is simple but creates long runs with no transitions (e.g., a string of 16 consecutive 0s). The receiver cannot re-synchronize its sampling clock from a flat-line signal.

Manchester embeds the clock by XORing it with the data:

```
manchester_bit = data_bit XOR clock
```

The clock runs at **twice the bit rate** and transitions every half-bit period. The XOR rule produces:

| data bit | clock phase | mid-bit transition direction | encoded symbol |
|----------|-------------|------------------------------|----------------|
| 0        | low→high    | low → high (rising)          | 0              |
| 1        | high→low    | high → low (falling)         | 1              |

Every bit period contains exactly one guaranteed transition at the mid-point. The receiver's phase-locked loop (PLL) locks to these transitions and extracts both clock and data in one pass.

**DC balance:** Because every bit contains both a high half and a low half, the average signal voltage is zero over any run. This allows transformer-coupled interfaces — critical for the external transceivers (MAUs) on thick Ethernet — and eliminates baseline wander.

**Bandwidth cost:** The fastest legitimate waveform in Manchester is two transitions per bit, requiring a Nyquist bandwidth of B Hz for a B bps stream. At 10 Mbps:

```
Required analog bandwidth = 10 MHz (minimum) to 20 MHz (maximum)
NRZ would need only 5 MHz
```

This 2× overhead was acceptable in the 1980s because clock recovery hardware was expensive and unreliable. 10BASE-T (twisted pair, 1990) switched to 4B/5B encoding + MLT-3 to regain bandwidth efficiency.

The SVG (`assets/08-classic-ethernet-physical-layer.svg`) shows a complete Manchester timing diagram for the bit stream `1 0 1 1 0 0 1 0`, with the clock, NRZ reference, and the encoded output all aligned on a common time axis.

### Thick Ethernet (10BASE5)

The original Ethernet cable was **RG-8/U** coaxial cable with:

| Parameter | Value |
|-----------|-------|
| Impedance | 50 Ω |
| Diameter | ~1 cm (0.4 inch) |
| Max segment length | 500 m |
| Max transceivers/segment | 100 |
| Transceiver spacing | ≥ 2.5 m (marked on cable) |
| Connector | N-type (threaded) |
| Nickname | "Frozen yellow garden hose" |

Stations connected via **vampire taps**: a clamp with a pin that pierced the outer jacket and shield to contact the inner conductor without cutting the cable. The tap attached to a **MAU (Medium Attachment Unit)** — or transceiver — which contained the analog transmit, receive, and collision-detect circuitry.

The MAU connected to the NIC (Network Interface Card) via an **AUI (Attachment Unit Interface)** cable, defined in the DIX standard as a 15-pin D-sub connector with separate transmit, receive, and collision-detect pairs, plus power. AUI cables could be up to 50 m long, allowing the station to sit away from the thick cable (e.g., servers in a wiring closet, cable running in the ceiling).

**Termination:** Both ends of every segment required a 50 Ω terminator. Missing or incorrect termination caused reflections that corrupted all traffic on the segment — a common installation error.

### Thin Ethernet (10BASE2)

Thin Ethernet replaced vampire taps with a simpler mechanism:

| Parameter | Value |
|-----------|-------|
| Cable type | RG-58/U (50 Ω) |
| Diameter | ~5 mm |
| Max segment length | 185 m |
| Max stations/segment | 30 |
| Transceiver spacing | ≥ 0.5 m |
| Connector | BNC (bayonet) |

Each station NIC had a **BNC T-connector**: the T's spine connected to the NIC, and the two T-arms connected inline with the coax cable. The NIC contained the transceiver circuitry directly — no separate MAU or AUI cable needed.

This dramatically reduced cost and installation complexity. An RG-58 cable snaked around an office, and adding a machine meant inserting a T-connector. The tradeoff: shorter segments (185 m vs 500 m), fewer stations (30 vs 100), and thinner cable more prone to kinking and accidental disconnection. A single open T-connector brought down the entire segment.

**Collision detection:** On both variants, the NIC detected collisions by comparing transmitted and received signal levels. While transmitting, the NIC simultaneously reads back the signal. If the received signal level exceeds what the transmitter put out, at least one other station is transmitting — collision. The NIC then asserts a **jam signal**: 32 bits of a specific pattern (not random) to ensure all stations on the segment detect the collision.

### Repeaters and Signal Regeneration

A **repeater** is a Layer 1 (physical layer) device. It:
1. Receives the incoming analog signal from one coax segment
2. Detects each bit by sampling at the Manchester transition points
3. Reconstructs a clean digital signal
4. Re-drives (re-amplifies) it onto the outgoing segment

The regenerated signal has fresh amplitude and timing — it does not accumulate the noise and attenuation of the preceding segment. This is the fundamental difference from a passive amplifier, which would also amplify noise.

**What repeaters do NOT do:**
- They do not examine MAC addresses — a repeater is invisible to the data link layer
- They do not buffer frames — every bit is forwarded immediately (with a small fixed delay, typically 1–2 bit times)
- They do not filter traffic — broadcasts and collisions propagate through them

Because collisions propagate through repeaters, all segments connected through repeaters form a **single collision domain**. This is why CSMA/CD slot timing must account for the worst-case propagation through the entire multi-segment network.

### The 5-4-3 Rule and Physical Constraints

The two absolute limits in IEEE 802.3 for classic Ethernet:

| Constraint | Value | Reason |
|------------|-------|--------|
| Max transceivers apart | 2,500 m (2.5 km) | Slot time budget |
| Max repeaters on any path | 4 | Propagation delay budget |

The **5-4-3 rule** summarizes a specific common topology:
- **5** cable segments
- **4** repeaters
- **3** segments may have stations attached (populated)
- **2** segments must be inter-repeater links only (unpopulated)

The reason only 3 of 5 segments can be populated: each station adds a small amount of capacitive loading and delay (the AUI cable and transceiver). Unpopulated link segments carry no stations, reducing the delay variability.

**Why exactly 4 repeaters?** The CSMA/CD algorithm requires that if station A begins transmitting, the farthest station B can collide with A's frame before A finishes — and A must still detect that collision. The maximum round-trip propagation time must be less than the **slot time** of 512 bit times.

At 10 Mbps, 1 bit time = 100 ns, so:

```
Slot time = 512 × 100 ns = 51.2 µs
```

The IEEE 802.3 specification allocates this budget:
- End-to-end propagation (2 × 1250 m at ~0.77c through coax): ≈ 21.65 µs round trip
- 4 repeaters at ~2 bit times each: ≈ 0.8 µs
- Transceiver, AUI cable, NIC delays: ≈ several µs
- Safety margin

With 5 or more repeaters, the accumulated delay overruns 51.2 µs. Station A would complete transmitting its minimum-size frame before B's collision signal returned — A would declare a successful send on a corrupted frame.

### Frame Preamble and Clock Lock

Every Ethernet frame begins with an 8-byte **preamble** serving one critical purpose: allow the receiver's PLL to lock to the incoming bit stream before the real data starts.

```
Preamble structure (DIX Ethernet / 802.3):

Bytes 1–7:  10101010  (seven bytes of alternating 1s and 0s)
Byte 8:     10101011  (Start Frame Delimiter, SFD — IEEE 802.3 name)
            ^^^^^^^^
                  ^^-- these two 1-bits signal: "data starts next"
```

When Manchester-encoded, the `10101010` pattern produces a **10 MHz square wave** for exactly 6.4 µs (7 bytes × 8 bits × 100 ns/bit). This is a pure, predictable signal the PLL can lock to. After synchronization, the final `11` bits in the SFD signal the boundary: the destination MAC address follows immediately.

**DIX vs IEEE 802.3 preamble:** In the original DIX standard, the preamble is 8 bytes with no separate SFD concept. In IEEE 802.3, the preamble is defined as 7 bytes followed by a 1-byte SFD (10101011). The on-wire bit pattern is identical — the difference is purely definitional.

The `code/main.py` program encodes this preamble, shows the resulting Manchester waveform, and demonstrates how the transition at the SFD's trailing `11` distinguishes frame start from sync.

### Minimum Frame Size and the Collision Window

The 64-byte minimum frame length is not arbitrary. It comes directly from the slot time:

```
Minimum frame = slot time × line rate
             = 51.2 µs × 10 Mbps
             = 512 bits
             = 64 bytes
```

If a frame is shorter than 64 bytes, the transmitting station could finish transmitting before a collision signal (traveling at signal propagation speed ≈ 0.77c through coax) returns from the far end of a 2.5 km network. The sender would then release the medium having never detected the collision — a **late collision** — and the frame would be silently corrupted.

**Frame structure and minimum sizing:**

```
Preamble  | Dst MAC | Src MAC | Type/Len | Data + Pad | FCS (CRC-32)
8 bytes   | 6 bytes | 6 bytes | 2 bytes  | 46–1500 B  | 4 bytes
```

The 64-byte minimum applies from Destination MAC through FCS (6+6+2+46+4 = 64 bytes). If the data payload is fewer than 46 bytes, a **pad** field fills to the 46-byte minimum. The preamble is not counted in the 64-byte minimum — it is stripped before the frame is passed to the data link layer.

**CRC-32:** The FCS field carries a CRC-32 computed over the entire frame from Destination MAC through data (excluding preamble and FCS itself), using the standard IEEE 802.3 polynomial: `x³² + x²⁶ + x²³ + x²² + x¹⁶ + x¹² + x¹¹ + x¹⁰ + x⁸ + x⁷ + x⁵ + x⁴ + x² + x + 1`.

### Transceiver Spacing and Heartbeat

On 10BASE5, the 2.5 m transceiver spacing rule prevents **standing wave resonance**. At 10 MHz, the wavelength in RG-8/U coax (velocity factor ~0.77) is:

```
λ = (0.77 × 3×10⁸ m/s) / 10×10⁶ Hz ≈ 23.1 m
```

Transceivers placed at random spacings that happen to be multiples of λ/2 (≈ 11.55 m) would create constructive interference in reflected signals. The 2.5 m enforced spacing avoids this. No two transceivers can be at a resonant spacing relative to each other.

After each transmission, a MAU asserts **SQE (Signal Quality Error)** — also called **heartbeat** — for approximately 10 bit times to confirm to the NIC that the collision-detect circuitry is alive. Some switches and repeaters incorrectly generated SQE on their AUI ports, causing NICs to misinterpret heartbeat as a collision; the fix was a jumper to disable SQE on those ports.

## Build It

`code/main.py` contains a complete Manchester encoding/decoding simulator organized as follows:

1. **`manchester_encode(bits)`** — takes a list of 0/1 integers, returns a list of signal samples at 4 samples/bit (2 samples per half-bit), suitable for ASCII waveform display.
2. **`manchester_decode(samples, samples_per_bit)`** — samples at the mid-point of each bit, extracts the mid-bit transition direction, returns recovered bits.
3. **`encode_preamble()`** — generates the 8-byte (64-bit) Ethernet preamble + SFD and encodes it.
4. **`crc32_ethernet(data)`** — computes CRC-32 using the IEEE 802.3 polynomial via Python's `binascii.crc32`.
5. **`build_ethernet_frame(dst, src, ethertype, payload)`** — assembles a minimal Ethernet frame with correct padding and CRC.
6. **`main()`** — demonstrates all of the above: shows the preamble waveform, encodes an example payload, displays the bandwidth comparison, and validates round-trip encode/decode.

Run with:
```
python3 code/main.py
```

No dependencies beyond the Python standard library. Expected output shows the ASCII Manchester waveform for the preamble's 10101010 pattern, the SFD transition, and the CRC-32 of a test frame.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Verify Manchester round-trip | Run `python3 code/main.py` | "Decoded bits match original: True" printed, 0 bit errors |
| Inspect preamble waveform | Read the ASCII waveform output | 7 identical `10101010` symbols, then `10101011` (SFD) visible as a break in the alternating pattern |
| Compute CRC-32 of a known frame | Modify `main()` payload to known bytes, compare to Wireshark FCS | CRC matches exactly (Wireshark's "Frame Check Sequence" field) |
| Validate 5-4-3 topology | Count segments and repeaters in a hand-drawn diagram | Populated segment count ≤ 3, total repeaters ≤ 4, end-to-end cable ≤ 2500 m |
| Bandwidth comparison | Read the "Bandwidth overhead" section of main() output | Manchester reports 20 MHz, NRZ reports 10 MHz for the same 10 Mbps stream |

## Ship It

Running `python3 code/main.py` produces a summary report. Save it to `outputs/`:

```
python3 code/main.py > outputs/manchester-demo.txt
```

The output includes the preamble waveform, frame byte dump, CRC-32 value, and the encode/decode round-trip result.

## Exercises

1. **Bandwidth budget:** If thin Ethernet (10BASE2) used 4B/5B encoding instead of Manchester, what would the required analog bandwidth be? Show the calculation and explain why 10BASE-T (1990) made this switch.

2. **5-4-3 violation:** Draw a topology with five populated segments connected by four repeaters. Identify which segments would need to become inter-repeater links to comply with the 5-4-3 rule, and explain which stations must be removed or moved.

3. **Minimum frame timing:** Station A begins transmitting a 40-byte data payload on a 2.4 km (round-trip) 10BASE5 network. Will CSMA/CD correctly detect a collision from the far end? Show the slot-time arithmetic. What padding does the Ethernet NIC add?

4. **Transceiver spacing:** A technician installs three vampire taps at positions 0 m, 11.5 m, and 23 m on a thick Ethernet segment. Why might this cause intermittent signal problems? What is the IEEE-required minimum spacing?

5. **Preamble decode:** Given the Manchester-encoded hex string `AA AA AA AA AA AA AA AB` (the raw on-wire preamble), decode each byte manually and identify the exact bit position where the SFD signals frame start.

6. **Repeater vs bridge:** A network administrator proposes replacing a repeater with a bridge to allow more than 4 hops between two distant stations. Does this solve the problem? What does a bridge do differently, and what new constraint does it impose?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Manchester encoding | "biphase mark code" | Clock XORed with data; guaranteed mid-bit transition; 2× bandwidth overhead vs NRZ |
| 10BASE5 | "thick Ethernet" | 10 Mbps, BASEband, 500 m segment maximum; RG-8/U cable, vampire taps |
| 10BASE2 | "thin Ethernet" or "cheapernet" | 10 Mbps, BASEband, 185 m segment (200 rounded); RG-58/U cable, BNC T-connectors |
| MAU | "transceiver" | Medium Attachment Unit; contains analog TX/RX/collision circuitry; attaches via AUI cable |
| AUI | "the transceiver cable" | Attachment Unit Interface; 15-pin DIX connector between NIC and MAU; up to 50 m |
| Repeater | "dumb hub" | Layer 1 regenerative amplifier; extends cable length; does not filter MAC addresses |
| 5-4-3 rule | "max topology rule" | 5 segments, 4 repeaters, only 3 populated; ensures slot time is not exceeded |
| Slot time | "the 51.2 µs window" | 512 bit times at 10 Mbps; minimum time a transmitter must occupy the medium to detect all collisions |
| SFD | "end of preamble" | Start Frame Delimiter; byte 0xAB (10101011); marks the transition from clock sync to real data |
| Vampire tap | "pierce connector" | Clamp that pierces coax insulation to contact inner conductor without cutting the cable |
| SQE / Heartbeat | "false collision signal" | Signal Quality Error; a short pulse the MAU sends after TX to confirm collision-detect is alive |
| CRC-32 | "the FCS" | Frame Check Sequence; 4-byte IEEE 802.3 CRC appended to every Ethernet frame |

## Further Reading

- **IEEE 802.3-1983** — Original standard (DIX-derived); sections 7 (PLS), 8 (MAU), and 9 (AUI) define Manchester encoding, thick coax, and transceiver specs.
- **IEEE 802.3a-1985** — Amendment that added 10BASE2 (thin Ethernet / cheapernet).
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., Pearson 2011 — Section 4.3.1 (Classic Ethernet Physical Layer) and Section 2.5 (Manchester encoding); the source textbook for this course.
- Spurgeon, C. E., *Ethernet: The Definitive Guide*, O'Reilly, 2000 — Chapter 3 covers 10BASE5 and 10BASE2 installation, termination, and troubleshooting in detail; Chapter 6 covers repeater rules.
- Metcalfe, R. M. & Boggs, D. R., "Ethernet: Distributed Packet Switching for Local Computer Networks," *Communications of the ACM*, Vol. 19, No. 7, July 1976 — The original paper; describes the 2.94 Mbps Xerox PARC system.
- **RFC 894** (1984) — Standard for the Transmission of IP Datagrams over Ethernet Networks; specifies use of DIX EtherType 0x0800 for IPv4.
- **RFC 1042** (1988) — Standard for Transmission of IP Datagrams over IEEE 802 Networks; explains the LLC/SNAP encapsulation used in IEEE 802.3 (Length-field) mode.
