# Twisted Pair Categories and Duplex Modes

> Twisted pair is two insulated copper wires (~1 mm thick) twisted into a helix so adjacent twists radiate out of phase and external noise hits both wires equally, leaving the differential voltage signal intact. Categories are graded by frequency, twists-per-meter, and crosstalk limits: Cat 3 (~16 MHz, 10BASE-T), Cat 5/5e (100 MHz, 100BASE-TX and 1000BASE-T), Cat 6 (250 MHz, 10GBASE-T to 55 m), Cat 6A (500 MHz, 10GBASE-T to 100 m), and Cat 7/7A (600/1000 MHz, individually shielded pairs — S/FTP). 100BASE-TX uses two pairs (one per direction); 1000BASE-T uses all four pairs bidirectionally at once, so each receiver must cancel its own transmit signal via echo cancellation (hybrid transformers, DSP). Duplex mode is a link property, not a cable property: simplex (one-way), half-duplex (either direction, one at a time, e.g. CSMA/CD 10BASE5), full-duplex (both directions simultaneously, mandatory for 1000BASE-T which has no half-duplex standard). Auto-negotiation (IEEE 802.3 clause 28) exchanges 16-bit FLP bursts to pick the highest common speed and duplex; a mismatch silently degrades to half-duplex and produces late collisions and CRC errors on the full-duplex side. TIA/EIA-568 defines the RJ-45 T568A/B pinout; PoE (IEEE 802.3af/at/bt) rides the same pairs using the center taps of the magnetics.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Guided transmission media; baseband digital signaling; Nyquist/Shannon capacity
**Time:** ~80 minutes

## Learning Objectives

- Map each TIA category (3, 5, 5e, 6, 6A, 7, 7A, 8) to its rated bandwidth, typical Ethernet PHY, and shielding type (UTP vs. STP/FTP/S/FTP).
- Explain why twisting reduces both electromagnetic radiation and differential-mode crosstalk, and quantify the trade-off against attenuation and NEXT.
- Distinguish simplex, half-duplex, and full-duplex at the link, MAC, and PHY layers, and state which Ethernet PHYs support which duplex modes.
- Describe how 1000BASE-T achieves full-duplex on all four pairs simultaneously using hybrid echo cancellation and Trellis-coded PAM-5.
- Reproduce the IEEE 802.3 clause 28 auto-negotiation priority resolution table and diagnose a duplex mismatch from its symptoms.
- Decode the RJ-45 T568A/B pinout and pair assignments, including which pairs carry data for 10/100 vs. 1000 Mbps and which pairs are available for PoE.

## The Problem

A data-center tech runs a new Cat 6 patch cable from a top-of-rack switch to a 10GBASE-T server NIC. Link comes up at 10 Gbps full-duplex and passes `ping`, but under `iperf3` load the server sees 40% throughput, `ifconfig` shows tens of thousands of input CRC errors per minute, and the switch log fills with `late collision` and `FLP burst` messages. Swapping the cable for another from the same batch fixes it. The cable had been crushed by a rack door, raising near-end crosstalk (NEXT) past the Cat 6 limit so the 1000BASE-T echo canceller could not separate the local transmit signal from the remote signal. The symptom looks like a duplex mismatch but is really a physical-layer failure exposed only at load — exactly the kind of failure that twisted-pair category ratings, NEXT/PSNEXT limits, and duplex mode rules exist to prevent.

## The Concept

### Why Twisting Works: Differential Signaling and Cancellation

A single wire is an antenna. Two parallel wires form a loop antenna that both radiates and picks up noise. Twisting the pair into a helix makes each half-twist a small loop whose current flows in the opposite sense to its neighbor, so far-field radiation from successive twists cancels. From the outside, induced noise (EMI from motors, fluorescent ballasts, adjacent pairs) couples into both wires nearly equally — this is **common-mode noise**. The receiver measures only the **differential voltage** between the two wires, so common-mode noise subtracts out. The key metric is how symmetric the coupling is, which worsens with pair-to-pair imbalance and with too few twists per meter.

The differential receiver has high **common-mode rejection ratio (CMRR)**, typically 40–60 dB in Ethernet PHYs. The trade-off: more twists per meter means better crosstalk rejection but slightly higher attenuation (longer copper path) and higher capacitance, which rolls off high frequencies. Cat 5 made the twists denser than Cat 3; Cat 6 and above also vary twist pitch per pair so that no two pairs in a sheath have the same lay length, defeating structured crosstalk.

### Category Ratings: Bandwidth, Twists, and Shielding

| Category | Bandwidth | Max Ethernet PHY | Shielding | Twists | Typical use |
|----------|-----------|------------------|-----------|--------|-------------|
| Cat 3 | 16 MHz | 10BASE-T | UTP | ~2–3/m | Legacy voice, 10 Mbps |
| Cat 5 | 100 MHz | 100BASE-TX, 1000BASE-T | UTP | denser | Obsoleted by 5e |
| Cat 5e | 100 MHz | 1000BASE-T (100 m) | UTP | denser | Office LAN default |
| Cat 6 | 250 MHz | 10GBASE-T (≤55 m) | UTP | dense, mixed pitch | Modern LAN |
| Cat 6A | 500 MHz | 10GBASE-T (100 m) | UTP/FTP | dense | Data center, 10G |
| Cat 7 | 600 MHz | 10GBASE-T | S/FTP | per-pair shield + braid | Short runs, Europe |
| Cat 7A | 1000 MHz | 10GBASE-T and beyond | S/FTP | per-pair shield | Av, high-noise |
| Cat 8.1/8.2 | 2000 MHz | 25GBASE-T/40GBASE-T (≤30 m) | U/FTP, S/FTP | tight | Switch-to-switch in rack |

"Bandwidth" here is the frequency at which insertion loss equals the worst-case crosstalk plus a 3 dB margin — the **ACR (Attenuation-to-Crosstalk Ratio)** limit. The category guarantees the channel, not the speed: 1000BASE-T works over Cat 5 because it stays within 100 MHz, but 10GBASE-T needs the 500 MHz of Cat 6A to keep alien crosstalk (AXT) under control at 100 m. Shielding types use the `XX/YTP` convention: first letter the overall shield (`U` unshielded, `S` braided, `F` foil), second the per-pair shield, then `TP`. Cat 6A `U/FTP` shields pairs but not the bundle; `S/FTP` (Cat 7) shields both, which is why Cat 7 mandates the individual-pair shield — otherwise PSANEXT at 600 MHz is unmanageable.

### Pair Usage: 10/100 vs. 1000 Mbps

RJ-45 T568A/B assigns four pairs to eight pins. The center pair (pins 4–5) is blue; pins 1–2 and 3–6 are the two data pairs; pins 7–8 is the brown pair.

| Pins | Pair color | 10/100BASE-T | 1000BASE-T | PoE (mode A/B) |
|------|-----------|--------------|------------|----------------|
| 1–2 | Orange/White | TX+ / TX− | BI_DA+ / BI_DA− | Mode A data |
| 3–6 | Green/White | RX+ / RX− | BI_DB+ / BI_DB− | Mode A data |
| 4–5 | Blue/White | — (unused) | BI_DC+ / BI_DC− | Mode B spare |
| 7–8 | Brown/White | — (unused) | BI_DD+ / BI_DD− | Mode B spare |

100BASE-TX uses only two pairs and is strictly full-duplex per direction on its own pair — one pair TX, one RX. 1000BASE-T uses **all four pairs simultaneously in both directions** (bidirectional, `BI_D`), which is only physically possible because each pair carries a 125 Mbaud 4-level PAM-5 signal (2 bits/symbol + 1 redundant level for Trellis coding) and the receiver subtracts its own transmitted waveform (echo cancellation) before decoding the remote symbol. That is why 1000BASE-T magnetics include a hybrid transformer and the PHY runs a long adaptive equalizer + echo canceller — failure of that canceller is exactly the crush-damage failure in the problem.

### Duplex Modes at Three Layers

Duplex is often confused because it lives at three places:

1. **Link directionality** (physics): can energy flow one way (simplex), one-way-at-a-time (half), or both ways at once (full)? A fiber strand carrying a beacon is simplex; a walkie-talkie channel is half-duplex; a phone call is full-duplex.
2. **MAC access rule**: CSMA/CD (half-duplex shared bus) vs. point-to-point no-contention (full-duplex switched). 10BASE5/10BASE2 and hubs force half-duplex CSMA/CD: a station listens, transmits, detects a collision within the slot time (512 bits for 10/100 Mbps, 4096 bits for 1000 Mbps half-duplex), jams for 32 bits, and backs off using truncated binary exponential backoff (k = min(2^n − 1, 1024) for attempt n ≤ 10, then up to 16 attempts before the frame is dropped).
3. **PHY framing**: a PHY advertises which duplex it supports. 10BASE-T supports both; 100BASE-TX supports both in the standard but switches almost universally run it full-duplex; 1000BASE-T has **no half-duplex mode** in 802.3 — it is full-duplex only, because the four-pair bidirectional scheme already implies simultaneous TX/RX.

### Auto-Negotiation: Clause 28 Priority Resolution

Two link partners exchange 16-bit **Fast Link Pulses (FLP)** bursts. The 16-bit Link Code Word packs a 5-bit Selector Field (00001 = 802.3), an 8-bit Technology Ability Field (bit positions for 10BASE-T, 10BASE-T full, 100BASE-TX, 100BASE-TX full, 100BASE-T4), and a Remote Fault bit. For 1000BASE-T a Next Page exchange adds a 1000BASE-T ability word. Both sides advertise their capabilities and independently apply the **priority resolution table** — highest mutually supported mode wins:

| Priority | Technology |
|----------|-----------|
| 1 | 1000BASE-T full-duplex |
| 2 | 1000BASE-T half-duplex |
| 3 | 100BASE-TX full-duplex |
| 4 | 100BASE-T4 |
| 5 | 100BASE-TX half-duplex |
| 6 | 10BASE-T full-duplex |
| 7 | 10BASE-T half-duplex |

The trap: if one side is set to a **forced** mode (auto-neg off) and the other to auto-neg, the auto-neg side falls back to its default (usually 10BASE-T half-duplex per clause 28 parallel detection). The forced side stays at, say, 100/full. Result: the forced side transmits whenever it wants (full-duplex assumption), the auto side runs CSMA/CD (half), and every simultaneous transmission is a **late collision** — a collision detected after the 512-bit slot time, which the MAC counts as an error rather than a normal collision. Throughput collapses, CRC errors climb, and the link stays "up" the whole time. The fix is to leave auto-neg on at both ends or force the identical speed and duplex at both ends.

### Worked Example: 10GBASE-T Reach vs. Category

10GBASE-T runs 800 Mbaud over four pairs with DSQ128 encoding (two PAM-16 symbols quadratured). The Shannon limit and the channel's ACR determine reach. For Cat 6 (250 MHz), alien crosstalk from neighboring bundled cables dominates above ~55 m, so 802.3 limits 10GBASE-T to 37–55 m unless alien-crosstalk-tested Cat 6 is installed. Cat 6A raises the frequency to 500 MHz and mandates PSANEXT margins, giving the full 100 m. The same 10GBASE-T PHY therefore behaves differently by cable category — not a protocol change, purely a physical-layer guarantee. `code/main.py` models this by computing the per-category ACR-limited reach and the duplex/PHY matrix; the SVG (`assets/twisted-pair-categories-and-duplex-modes.svg`) shows the four-pair bidirectional 1000BASE-T layout and the auto-negotiation resolution flow.

## Build It

1. Open `code/main.py`. It models the category table, the per-PHY pair usage, and the clause 28 priority resolution.
2. Run `python3 main.py` — the demo prints the full category table with ACR-limited 10GBASE-T reach, the duplex support matrix per PHY, and resolves a sample auto-negotiation where one side advertises `{1000T-full, 100TX-full, 10T-full}` and the other `{100TX-full, 100TX-half, 10T-half}`.
3. Inspect `resolve_auto_neg(local, remote)` — it intersects capability bitmaps, then walks the priority table to pick the winner. Change the inputs to force a mismatch (one side forced to 100/full, the other parallel-detected to 10/half) and observe the `DUPLEX_MISMATCH` warning.
4. Trace `ten_gb_reach(cat)`: it returns the max 10GBASE-T distance using the category's ACR ceiling. Edit the `ALIEN_XT_MARGIN` constant to see reach collapse on Cat 6.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Identify cable category from a label | Printed `Cat 6A U/FTP` on sheath + verified bandwidth | Sheath marks category AND shielding type; matches a TIA class |
| Diagnose duplex mismatch | `ethtool` shows `full` on switch port, `half` on host, late-collision counter rising | Both ends report same speed AND duplex; late-coll = 0 |
| Verify 10G reach feasibility | Length from TDR < `ten_gb_reach(cat)` for the installed category | Cat 6 ≤ 55 m or upgrade to Cat 6A for 100 m |
| Confirm 1000BASE-T uses 4 pairs | Wire-map tester shows continuity on all 4 pairs, both directions | All 8 pins pair-correct; no split pair on 3–6 |
| Reason about PoE mode | PSE advertises Mode A (pins 1–2, 3–6) vs Mode B (4–5, 7–8) | Mode chosen matches PD signature; no double-class |

## Ship It

Produce the artifact `outputs/prompt-twisted-pair-categories-and-duplex-modes.md`: a one-page runbook giving the cable-category → PHY → reach decision matrix, the auto-negotiation priority table, and a duplex-mismatch triage procedure (which counters to read on Cisco IOS and Linux `ethtool -S`). Include the output of `python3 main.py` as the worked example section.

## Exercises

1. A 100 m Cat 5e link must carry 10GBASE-T. Using the category table and the ACR argument in `code/main.py`, explain why it fails and state the minimum cable upgrade and whether re-termination alone could help.
2. Two switches are both forced to `speed 100 / duplex full` but one port is on a hub in between. Predict which counters (late collisions, FCS errors, alignment errors) rise on each side and why. Confirm your prediction by editing `resolve_auto_neg` to model forced-vs-parallel-detection.
3. 1000BASE-T has no half-duplex mode. Justify this from the four-pair bidirectional scheme: what physical impossibility does half-duplex CSMA/CD run into when all four pairs are already transmitting and receiving at once?
4. A bundle of 48 Cat 6A cables runs 90 m through a cable tray next to a 480 V three-phase feeder. Name the three crosstalk/interference mechanisms (NEXT, PSNEXT, alien crosstalk/AXT) that matter and which shielding choice (`U/FTP` vs `S/FTP`) defends against each.
5. Given the clause 28 priority table, side A advertises `{100BASE-TX-full, 100BASE-TX-half, 10BASE-T-half}` and side B advertises `{1000BASE-T-full, 100BASE-TX-full}`. Determine the negotiated mode and the duplex, and explain what `resolve_auto_neg` returns and why.
6. PoE++ (802.3bt Type 4, 90 W) is delivered over a 100 m Cat 6A run to a 60 W PD. Compute the per-pair current and the worst-case voltage drop assuming 0.188 Ω/m per conductor (24 AWG), and decide whether all four pairs must be used. Show your arithmetic.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| UTP | "unshielded cable" | Unshielded Twisted Pair — no foil/braid, only insulation; Cat 3–6 default |
| STP / S/FTP | "shielded cable" | Shielded Twisted Pair; S/FTP = overall braid + per-pair foil, mandatory Cat 7+ |
| NEXT | "crosstalk" | Near-End Crosstalk: signal leaking from a local TX pair into a local RX pair at the same connector |
| PSNEXT | "PowerSum crosstalk" | Power-Sum NEXT: combined NEXT from all three other pairs into one — governs four-pair PHYs |
| ACR | "headroom" | Attenuation-to-Crosstalk Ratio: signal margin = insertion loss − crosstalk; defines category bandwidth |
| Echo cancellation | "hybrid" | DSP that subtracts a PHY's own transmitted waveform from the received sum so 1000BASE-T can run 4-pair full-duplex |
| FLP | "auto-neg pulse" | Fast Link Pulse — 17 ms burst of 16-bit Link Code Word exchanged on clause 28 link-up |
| Slot time | "collision window" | 512 bits (10/100) or 4096 bits (1000 half) within which a valid collision must be detected |
| Late collision | "bad collision" | Collision after slot time; indicates duplex mismatch or over-length segment, counted as an error not retried normally |
| Hybrid transformer | "the magjack part" | 2-wire to 4-wire coupler in Ethernet magnetics that lets TX and RX share one pair |

## Further Reading

- IEEE Std 802.3-2022, clauses 14 (10BASE-T), 28 (Auto-Negotiation), 40 (1000BASE-T), 55 (10GBASE-T) — the canonical PHY and duplex definitions.
- ANSI/TIA-568.2-D — Balanced Twisted-Pair Telecommunications Cabling and Components Standard; defines categories 3–8.1 and the T568A/B pinout.
- ISO/IEC 11801-1 — Generic cabling for customer premises; defines Classes A–I (Cat 7/7A as Class F/Fa, shielding letter codes `X/YTP`).
- IEEE 802.3bt-2018 — DTE Power via MDI over 4 pairs (Type 3/4, up to 90 W).
- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §2.2.2 — the source textbook section on twisted pairs and duplex terminology.
- "1000BASE-T: Auto-Negotiation and Full-Duplex Operation," IEEE 802.3ab Task Force tutorial — echo-cancellation and PAM-5 detail.
