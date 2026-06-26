# PCM T1/E1 Carriers and Signaling Bits

> Voice leaves your handset as analog, but the telephone core is digital. A **codec** in the end office samples each 4 kHz channel **8000 times per second** (125 µs/frame, the Nyquist rate) and quantizes every sample to **8 bits**, producing the universal DS0 rate of **64 kbps** specified in ITU-T **G.711**. Twenty-four of those DS0s, plus a 193rd framing bit, pack into the North American/Japanese **T1 (DS1)** frame — 193 bits every 125 µs = **1.544 Mbps**, of which **8 kbps** is the framing/signaling channel. Outside that region the ITU **E1** carrier carries **32** 8-bit time slots per 125 µs frame = **2.048 Mbps**, with time slot 0 reserved for framing and (typically) slot 16 for **common-channel signaling**, leaving 30 usable voice channels. Signaling rides either **channel-associated** — T1's infamous **robbed-bit signaling** steals the LSB of each channel every 6th frame, which is fine for voice but corrupts data down to 56 kbps per slot — or **common-channel** (out-of-band, the CCS model that SS7/CAS use). Higher carriers are built by bit-interleaving: four T1 → **T2** (6.312 Mbps, not the naive 6.176), seven T2 → **T3** (44.736 Mbps), six T3 → **T4** (274.176 Mbps); the ITU/CEPT hierarchy instead stacks four-for-one into E2/E3/E4. This lesson builds a runnable T1/E1 frame packer, a robbed-bit-signaling scheduler, and an extended-superframe (ESF) CRC-6 checker so you can see exactly where the bits go.

**Type:** Build
**Languages:** Python
**Prerequisites:** PCM and the Nyquist sampling rate (Phase 2 lesson on digitizing voice), TDM vs FDM multiplexing basics, bit/byte/rate arithmetic
**Time:** ~80 minutes

## Learning Objectives

- Compute the DS0 rate (8 bits × 8000 samples/s = 64 kbps) from the Nyquist theorem and explain why every telephone time interval is a multiple of 125 µs.
- Lay out a 193-bit T1 frame bit-by-bit: 24 channels × 8 bits + 1 framing bit, and derive the 1.544 Mbps gross rate with 8 kbps of overhead.
- Contrast A-law (Europe) and µ-law (North America/Japan) companding and explain why a logarithmic quantization step makes quantization error proportional to signal amplitude.
- Distinguish channel-associated signaling (robbed-bit signaling, the 6th-frame LSB) from common-channel signaling (E1 time slot 16, clear-channel T1) and predict the 56-vs-64 kbps per-slot impact on data.
- Trace the T1 extended superframe (ESF): 24 frames, the 001011… framing pattern at frames 4/8/12/16/20/24, the 6-bit CRC-6, and the 12 FPS maintenance bits.
- Walk the DS1/T-carrier and CEPT/E-carrier hierarchies up to T4/E4, accounting for the framing overhead that makes each aggregate rate exceed the naive multiple.

## The Problem

A business leases a T1 to carry 24 simultaneous voice calls between two PBXs, then tries to repurpose it for data and finds each channel delivers only **56 kbps**, not the 64 kbps the datasheet promises. Meanwhile a European counterpart leasing an E1 gets 30 usable 64 kbps channels, not 32. The engineer must explain where the missing bits went, justify why the two regions' trunks are not interchangeable, and produce a frame map that shows the signaling bits exactly where a bit-error-rate tester expects them. This is the daily reality of the digital telephone trunk: every rate is a precise accounting of payload bits plus stolen signaling and framing bits over the 125 µs cadence the codec dictates.

## The Concept

### PCM and the 64 kbps DS0 building block

A **codec** (coder-decoder) in the end office band-limits each voice channel to ~3.4 kHz inside a 4 kHz slot, then samples at **8000 samples/s** — the Nyquist rate for a 4 kHz channel (2 × 4000). Each sample is quantized to **8 bits**, so one digitized voice channel runs at:

```
8 bits/sample × 8000 samples/s = 64 000 bps = 64 kbps
```

This **64 kbps DS0** (Digital Signal level 0) is the atom of the entire digital telephone hierarchy — T1, E1, SONET, SDH, and ISDN B-channels are all built from it. Because frames are emitted every 125 µs, virtually every telephone-system time interval (frame, superframe, multiframe) is a multiple of 125 µs. `code/main.py` opens by reproducing this arithmetic.

### Companding: A-law and µ-law (ITU-T G.711)

Uniform quantization wastes bits: quiet speech rarely exercises the high amplitudes, so error there dominates perceived noise. **Companding** (compress + expand) applies a logarithmic quantization curve so the step size is fine near zero and coarse near the peaks, making quantization noise roughly **proportional to signal amplitude** rather than absolute. ITU-T **G.711** defines two incompatible curves:

| Feature | µ-law (North America, Japan) | A-law (Europe, rest of world) |
|---|---|---|
| Standard | G.711 µ-law | G.711 A-law |
| Zero-input code | 0xFF (idle/comfort noise) | 0x54 alternating 0x55/0x54 |
| Dynamic range | ~8 bits over ~78 dB | ~8 bits over ~78 dB, slightly flatter |
| Conversion | µ→A via piecewise tables | A→µ via piecewise tables |

Both encode 13–14 bit linear samples into 8 bits. International gateways convert between them, which is why a transcontinental call can show a faint quantization "edge." The `code/main.py` `mu_to_linear` / `a_to_linear` decoders let you read the actual amplitude curve.

### The T1 (DS1) frame: 193 bits every 125 µs

The T1 carrier multiplexes **24** DS0 channels into one stream. Each channel contributes **8 bits** per frame; the multiplexer adds **1 framing bit** so the receiver can find the frame boundary. The arithmetic:

```
24 channels × 8 bits = 192 payload bits
+ 1 framing bit (F bit)
= 193 bits / 125 µs
× 8000 frames/s = 1 544 000 bps = 1.544 Mbps
```

The 1 framing bit × 8000 = **8 kbps** of overhead; the remaining 1.536 Mbps is the 24 × 64 kbps payload. Frame layout (one 125 µs frame):

| Bit positions | Contents |
|---|---|
| Bit 1 (F bit) | Framing / signaling bit |
| Bits 2–9 | Channel 1 sample (8 bits) |
| Bits 10–17 | Channel 2 sample |
| … | … |
| Bits 186–193 | Channel 24 sample |

The receiver locates frame by watching the F-bit stream for a known pattern. In the original **D4 (superframe, SF)** format, 12 frames form a superframe and the F bits carry the alternating `101010…` pattern; the receiver scans for it and, on loss, walks bit-by-bit until it relocks. See the frame layout in `assets/pcm-t1-e1-carriers-and-signaling-bits.svg`.

### Robbed-bit signaling and the ESF superframe

T1 carries per-channel telephone signaling (off-hook, dial pulses, ring) **channel-associated**: it steals the **least significant bit** of each channel's byte in **every 6th frame**. This is **robbed-bit signaling (RBS)**. Across the 12-frame D4 superframe, frames 6 and 12 are "signaling frames"; the stolen bits form two signaling subchannels (A and B bits). The argument is that flipping one LSB of an 8-bit µ-law sample is inaudible on voice — but for data it is fatal: each robbed slot carries only **7 reliable bits per 6 frames**, so a "64 kbps" channel nets **56 kbps** for clean data. That is the historical 56 kbps modem ceiling.

The newer **Extended Superframe (ESF)** spreads 24 frames and uses the 193rd bit more cleverly — 24 F-bits per ESF are divided into three roles:

| ESF F-bit role | Frames | Bits | Use |
|---|---|---|---|
| Framing pattern `001011…` | 4, 8, 12, 16, 20, 24 | 6 | Synchronization check pattern |
| CRC-6 error check | 2, 6, 10, 14, 18, 22 | 6 | Detects frame slips / bit errors |
| Facility Data Link (FDL) | 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23 | 12 | OAM: performance reports, loopback commands |

The receiver continuously verifies the `001011` pattern *and* the CRC-6; a mismatch triggers a resync scan. `code/main.py` builds an ESF, injects a single-bit error, and shows the CRC-6 catching it.

### Clear-channel T1 and common-channel signaling

For leased data lines, robbed-bit signaling is unacceptable. Modern T1 provisions **clear-channel (B8ZS)** mode: no bits are robbed, all 8 bits per slot are usable (back to 64 kbps × 24), and signaling moves **out-of-band** via a **common-channel signaling (CCS)** facility — historically one whole DS0 is sacrificed as the signaling channel, or signaling is carried by SS7 on a separate link. B8ZS also replaces long zero runs with intentional bipolar violations (the `000VB0VB` code) so the line keeps its ones density for clock recovery without stealing payload bits.

### The E1 carrier: 32 slots, 2.048 Mbps

Outside North America/Japan the ITU **E1** carrier packs **32** 8-bit time slots into the 125 µs frame:

```
32 slots × 8 bits = 256 bits / 125 µs
× 8000 frames/s = 2 048 000 bps = 2.048 Mbps
```

| Time slot | Use |
|---|---|
| 0 | Framing: the frame-alignment signal `x0011011` in odd frames, plus CRC-4 bits and a remote alarm bit in even frames |
| 16 | Signaling channel — carries the **CAS multiframe** (A/B/C/D bits for up to 30 channels) or **CCS** when common-channel signaling is used |
| 1–15, 17–31 | 30 payload voice/data channels at 64 kbps each = 1.920 Mbps payload |

So E1 yields **30 usable 64 kbps channels** (1.920 Mbps) versus T1's **24** (1.536 Mbps). E1 puts signaling in a dedicated slot instead of stealing payload bits, so an E1 channel is *always* clear-channel — no 56 kbps surprise. 16 frames form the **CAS multiframe** so each of the 30 channels gets 4 signaling bits (A, B, C, D) per multiframe. `code/main.py` builds the E1 frame, marks slot 0 and slot 16, and demonstrates the CAS multiframe signaling nibble rotation.

### Higher-order multiplexing: the T and E hierarchies

Slower carriers are multiplexed into faster ones by **bit-interleaving** (T2 and above, not byte-interleaving like T1's internal channels). Each level adds framing and recovery overhead, so the aggregate rate exceeds the naive multiple:

| Level | Composition | Aggregate rate | Payload capacity |
|---|---|---|---|
| DS0 / E0 | 1 PCM voice channel | 64 kbps | 1 channel |
| T1 (DS1) | 24 DS0 + F bit | 1.544 Mbps | 24 × 64 kbps |
| T2 (DS2) | 4 T1 + overhead | 6.312 Mbps | 96 × 64 kbps |
| T3 (DS3) | 7 T2 + overhead | 44.736 Mbps | 672 × 64 kbps |
| T4 (DS4) | 6 T3 + overhead | 274.176 Mbps | 4032 × 64 kbps |
| E1 | 32 DS0 | 2.048 Mbps | 30 × 64 kbps |
| E2 | 4 E1 + overhead | 8.848 Mbps | 120 × 64 kbps |
| E3 | 4 E2 + overhead | 34.368 Mbps | 480 × 64 kbps |
| E4 | 4 E3 + overhead | 139.264 Mbps | 1920 × 64 kbps |

Note 4 × 1.544 = 6.176, but T2 is 6.312 — the **136 kbps** gap is framing/control for recovery when a carrier slips. The U.S. hierarchy multiplies by 4, 7, 6; the ITU/CEPT hierarchy multiplies by 4 at every level. T1 and T3 are customer-facing; T2 and T4 live inside the carrier and are rarely seen. `code/main.py` validates every aggregate against these published rates.

### SONET/SDH: the container that eats T1s whole

Above the plesiochronous hierarchy sits **SONET** (North America, ANSI) / **SDH** (ITU-T G.707/G.708/G.709), a fully synchronous optical TDM with a master clock at 1 part in 10⁹. The basic **STS-1** frame is 810 bytes (90 columns × 9 rows) emitted every 125 µs:

```
810 bytes × 8 bits × 8000/s = 51.84 Mbps
```

The first 3 columns (transport overhead: section + line overhead) are management; the remaining 87 columns carry the **Synchronous Payload Envelope (SPE)**, which can hold T1s/E1s swallowed whole, voice samples, or packets, and can float within the frame via a pointer. STS-N is N byte-interleaved STS-1s. SONET unifies the U.S./European/Japanese 64 kbps worlds into one container hierarchy — the payoff for the standardization effort that began at Bellcore in 1985.

## Build It

1. Open `code/main.py` and run `python3 code/main.py`. The first block prints the DS0 derivation and confirms 1.544 / 2.048 Mbps from the 125 µs cadence.
2. Read `build_t1_frame(samples, frame_index, signaling_mode)`: it packs 24 8-bit samples plus the F bit, and when `signaling_mode="rbs"` it zeroes the LSB of every channel on every 6th frame to model robbed-bit signaling. Confirm the 6th-frame LSB is the stolen bit.
3. Run the ESF demo: `build_esf_frame(payload_blocks)` assembles 24 frames, computes the **CRC-6** over the 192 payload bits using the standard x⁶+x+1 polynomial, and places it in the F-bit positions of frames 2/6/10/14/18/22. `inject_bit_error` flips one payload bit; re-run the CRC and watch it flag a non-zero syndrome.
4. Read `build_e1_frame(slots, cas_nibbles)`: it lays out 32 slots, fills slot 0 with the frame-alignment signal and slot 16 with the CAS multiframe nibbles for the 30 channels. Confirm slots 1–15 and 17–31 are the payload.
5. Run `t_hierarchy()` and `e_hierarchy()`: they print each level's naive multiple and published rate so you can see exactly where the framing overhead hides.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify a DS0 | 8 bits × 8000/s = 64 000 bps, 125 µs frame | The cadence is exactly 125 µs; all higher rates are integer multiples of 64 kbps |
| Confirm T1 framing | 193-bit frame, F-bit at position 1, 8 kbps overhead | Gross 1.544 Mbps, payload 1.536 Mbps, overhead exactly 8 kbps |
| Spot robbed-bit signaling | LSB stolen on frames 6 & 12 of the D4 superframe | Voice tolerates it; data channels net 56 kbps, the modem ceiling |
| Validate an ESF | `001011` pattern at frames 4/8/12/16/20/24, CRC-6 over payload | A single flipped payload bit produces a non-zero CRC-6 syndrome |
| Read an E1 | Slot 0 = frame alignment, slot 16 = CAS, 30 payload slots | 2.048 Mbps gross, 1.920 Mbps payload, no per-channel bit theft |
| Audit the hierarchy | T2 = 6.312 not 6.176; E3 = 34.368 not 34.304 wait-check | Each aggregate exceeds the naive multiple by the framing/recovery overhead |

## Ship It

Produce one artifact under `outputs/` — a frame-mapping report for both a T1 (ESF) and an E1 trunk:

- The bit-by-bit T1 frame map with the F-bit role per ESF frame, the CRC-6 value, and a marked robbed-bit slot.
- The E1 slot map with slot 0 alignment, slot 16 CAS multiframe, and the 30 payload channels.
- A one-page rate card: DS0 → T4 / E4 with naive-multiple vs published-rate columns and the overhead explained.

Start from the printed output of `code/main.py` and annotate where a bit-error-rate tester would probe each signaling bit.

## Exercises

1. A T1 line carrying only data shows 56 kbps per channel instead of 64 kbps. Identify the mechanism, name the frames where bits are stolen in the D4 superframe, and state the two configuration changes (B8ZS + common-channel signaling) that restore clear 64 kbps channels.
2. Build a 24-frame ESF in `code/main.py`, compute the CRC-6, then flip bit 100 of the combined payload. Report the new syndrome and explain why the receiver treats a non-zero syndrome as a frame-slip/loss-of-sync indicator.
3. An E1 is provisioned with common-channel signaling instead of CAS. Which slot changes role, how many 64 kbps payload channels remain, and what is the new usable payload rate? Compare with a clear-channel T1.
4. Four T1 streams naive-multiplex to 6.176 Mbps, yet T2 is 6.312 Mbps. Compute the overhead in kbps, explain what it buys (framing + recovery from carrier slips), and give the equivalent overhead for E2 (4 × 2.048 vs 8.848).
5. Convert the µ-law byte `0x87` to linear PCM using the decoder in `code/main.py`, then encode that linear value back with A-law and report the difference in quantization steps. Why does an international gateway incur this loss twice?
6. An STS-1 SONET frame is 90 columns × 9 rows = 810 bytes every 125 µs. Compute the gross rate, identify the transport-overhead columns, and derive the SPE payload rate (87 × 9 × 8 × 8000). Show that the SPE is the container that can carry an entire T1 intact.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DS0 | "a voice channel" | One 8-bit PCM sample every 125 µs = 64 kbps; the atom of every digital telephone hierarchy |
| T1 / DS1 | "a T1 line" | 24 DS0s + 1 framing bit per 125 µs frame = 193 bits = 1.544 Mbps; DS1 is the format, T1 the carrier |
| F bit | "the extra bit" | The 193rd bit of a T1 frame; carries the framing pattern, CRC-6, and FDL in ESF mode |
| Robbed-bit signaling | "stolen bits" | Channel-associated signaling that takes the LSB of each channel's byte every 6th frame; inaudible on voice, fatal to data (56 kbps ceiling) |
| Extended Superframe | "ESF" | 24-frame T1 structure: 6 F-bits carry `001011`, 6 carry CRC-6, 12 carry the FDL OAM channel |
| Clear channel | "no bit stealing" | B8ZS line code + common-channel signaling so all 8 bits/slot are payload — full 64 kbps per channel |
| E1 | "the European T1" | 32 8-bit slots per 125 µs = 2.048 Mbps; slot 0 frames, slot 16 signals, 30 payload channels |
| CAS multiframe | "the signaling cycle" | 16 E1 frames giving each of 30 channels 4 signaling bits (A/B/C/D) in slot 16 |
| Common-channel signaling | "SS7 style" | Signaling carried in a dedicated channel/link separate from payload, not stolen from each voice slot |
| Bit-interleaving | "how T2 is built" | Higher carriers mix constituent streams one bit at a time (not byte at a time like T1's internal channels) |
| Companding | "log quantization" | A-law/µ-law logarithmic quantization (G.711) making quantization noise proportional to signal amplitude |

## Further Reading

- **ITU-T G.711** — Pulse Code Modulation (PCM) of voice frequencies; defines A-law and µ-law companding.
- **ITU-T G.703 / G.704** — Physical/electrical and frame structure of E1 (2.048 Mbps) and higher plesiochronous hierarchies.
- **ANSI T1.403 / T1.408** — DS1 ESF format, CRC-6, and Facility Data Link definitions.
- **ITU-T G.707 / G.708 / G.709** — SONET/SDH synchronous digital hierarchy (STS-1 = 51.84 Mbps).
- **Bellamy**, *Digital Telephony*, 3rd ed., Wiley — the canonical reference for DS1/DS2/DS3 framing and B8ZS.
- **Goralski**, *SONET: A Guide to Synchronous Optical Networks*, McGraw-Hill, 2002.
- **Tanenbaum & Wetherall**, *Computer Networks*, 5th ed., Chapter 2, Section 2.6.4 (Trunks and Multiplexing).
