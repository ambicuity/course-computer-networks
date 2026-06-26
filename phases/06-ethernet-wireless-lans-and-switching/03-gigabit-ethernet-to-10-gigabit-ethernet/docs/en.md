# Gigabit Ethernet to 10-gigabit Ethernet

> Gigabit Ethernet (IEEE 802.3z fiber/STP, 802.3ab over Cat-5 UTP, 1999) retains the 48-bit MAC addressing, the same 64-1518 byte frame format, and unacknowledged datagram service of classic Ethernet, but runs each link point-to-point at 1000 Mbps. In full-duplex mode there is no contention, so CSMA/CD is disabled and cable length is bounded only by signal strength. In half-duplex (hub) mode CSMA/CD returns, and because a 64-byte frame transmits 100x faster the worst-case domain shrinks to ~25 m — so the standard adds **carrier extension** (hardware pads the slot to 512 bytes, dropping line efficiency to ~9% for a minimum frame) and **frame bursting** (concatenate frames up to a burst limit) to push usable diameter back to 200 m. Gigabit adds 802.3x PAUSE flow control via control frames with EtherType 0x8808 (pause quanta of 512 bit-times = 512 ns, max 65535 quanta ≈ 33.6 ms) and de-facto **jumbo frames** (~9 KB, non-standard). 10-Gigabit Ethernet (802.3ae, 2002) drops half-duplex and CSMA/CD entirely — every link is full-duplex — switching the line code from 8B/10B (25% overhead) to scrambled 64B/66B (~3% overhead), spanning 10GBASE-SR/LR/ER fiber and 10GBASE-CX4/T copper. This lesson ships a Python tool (`code/main.py`) that computes slot-time geometry, carrier-extension efficiency, line-code overhead, and PAUSE-quanta math so you can reason about these tradeoffs numerically.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 06 lessons on classic Ethernet (CSMA/CD, the 802.3 frame, slot time) and Fast Ethernet
**Time:** ~75 minutes

## Learning Objectives

- Explain why full-duplex Gigabit Ethernet abandons CSMA/CD and what *does* bound cable length once collisions are impossible.
- Compute the half-duplex slot-time problem and show numerically why carrier extension (512-byte slot) and frame bursting were required to reach 200 m.
- Compare 8B/10B (Gigabit fiber/CX4) versus 64B/66B (10 Gigabit) line coding and quantify the bandwidth overhead of each.
- Decode an 802.3x PAUSE frame: EtherType 0x8808, the reserved multicast destination, and the pause-quanta-to-time conversion (512 ns/quantum at 1 Gbps).
- Map a cabling requirement (distance, fiber/copper, budget) to the right 1000BASE-* or 10GBASE-* media type from the standard tables.

## The Problem

You are commissioning a new top-of-rack switch. Two servers with brand-new 1000BASE-T NICs are wired through a cheap **hub** (not a switch) the previous tenant left behind. Throughput collapses under load, the NIC reports a flood of `late collisions`, and a packet capture shows tiny 64-byte data frames padded out to 512 bytes on the wire. A junior engineer insists "Gigabit doesn't have collisions." Both observations are real, and reconciling them requires understanding exactly when Gigabit Ethernet keeps CSMA/CD, what carrier extension is doing to those frames, and why the answer is simply *replace the hub with a switch so the link goes full-duplex*.

The deeper version of the problem is design-time: when you spec links you must pick media (SR vs LR vs ER vs T), know the distance each reaches, and understand why a 10GBASE-T run over old Cat-5 will not certify even though the connector fits. This lesson reduces all of that to evidence you can capture and numbers you can compute.

## The Concept

Source: `chapters/chapter-04-the-medium-access-control-sublayer.md`, the subsections on Gigabit Ethernet (802.3ab/802.3z) and 10-Gigabit Ethernet (802.3ae). The companion diagram is `assets/gigabit-ethernet-to-10-gigabit-ethernet.svg`, which traces the speed/duplex/coding evolution.

### Two modes, one frame format

Gigabit Ethernet's design goal was a 10x speed jump while keeping *everything* visible to software identical: 48-bit unicast/multicast/broadcast addressing, the same minimum 64-byte and maximum 1518-byte (1522 with a VLAN tag) frame, and unacknowledged datagram service. What changed is the link topology: like Fast Ethernet, **every cable has exactly two devices on it** (point-to-point), and the link can run in one of two modes.

| Mode | Used with | CSMA/CD? | Length limit set by | Typical reality |
|---|---|---|---|---|
| **Full-duplex** | Switch (buffered ports) | No — contention impossible | Signal strength / attenuation | The normal mode; both ends send anytime |
| **Half-duplex** | Hub (electrically shared) | Yes — collisions possible | Worst-case round-trip slot time | Rare; only legacy hub gear |

In full-duplex, the line carries traffic both ways simultaneously, ports are buffered, and a sender never has to sense the channel — so CSMA/CD is switched off and the cable can be as long as the optics or copper will physically carry a clean signal.

### The half-duplex slot-time crisis

CSMA/CD only works if a sender is *still transmitting* when the worst-case collision noise propagates back to it. At classic 10 Mbps the 64-byte minimum frame and 2500 m maximum diameter are matched. Speed up the bit clock 100x and the geometry breaks: a 64-byte frame at 1 Gbps finishes in 512 ns, during which light travels only a fraction of the old distance. Naively, the collision domain would shrink to about **25 m** — useless for an office.

Two hardware tricks restore a 200 m diameter (see `code/main.py`, which computes both):

- **Carrier extension**: the transmitting hardware appends non-data extension symbols *after* a short frame so the slot occupies **512 bytes** on the wire. Software never sees it (added by the sender's PHY, stripped by the receiver's PHY). The cost: a 64-byte frame carrying 46 bytes of payload now burns 512 bytes of slot time — a line efficiency of roughly 46/512 ≈ **9%**.
- **Frame bursting**: rather than pad one tiny frame, a station may transmit a *concatenated burst* of several queued frames in a single channel acquisition (up to a burst limit). If real frames fill the burst, efficiency is excellent; bursting is preferred over carrier extension whenever the sender has frames waiting.

### Cabling and the 8B/10B line code

Signaling at ~1 Gbps means putting a bit on the medium roughly every nanosecond. The fiber and shielded-copper versions borrowed the **8B/10B** code from Fibre Channel: 8 data bits map to a 10-bit codeword chosen to be DC-balanced (equal 0s and 1s) with enough transitions for clock recovery. That costs 25% extra signaling bandwidth — far better than Manchester's 100% expansion, but still 2 wasted bits per byte.

| Name | Standard | Medium | Max segment | Line code |
|---|---|---|---|---|
| 1000BASE-SX | 802.3z | Multimode fiber, 0.85 µm | 550 m | 8B/10B |
| 1000BASE-LX | 802.3z | Single-mode (10 µm) or multimode | 5000 m | 8B/10B |
| 1000BASE-CX | 802.3z | 2-pair shielded twisted pair | 25 m | 8B/10B |
| 1000BASE-T | 802.3ab | 4-pair Cat-5 UTP | 100 m | PAM-5, 125 Msym/s |

1000BASE-T is the popular one because it reuses installed Cat-5. It is far more involved: **all four pairs** carry signal in *both directions at once* (DSP echo cancellation separates them), each wire using five voltage levels (PAM-5) at **125 Msymbols/s** — 4 pairs × 250 Mbps = 1 Gbps.

### PAUSE flow control (802.3x)

At 1 Gbps a receiver that stalls for just 1 ms can have ~1953 frames pile up; a Gigabit host feeding a classic-Ethernet host overruns buffers easily. The fix is **802.3x PAUSE**: an end sends a MAC control frame telling the peer to stop transmitting for a stated interval.

```
Destination: 01:80:C2:00:00:01   (reserved multicast, link-local)
Source:      <sender MAC>
EtherType:   0x8808              (MAC Control)
Opcode:      0x0001             (PAUSE)
Quanta:      0x0000..0xFFFF     (pause time in 512-bit-time units)
+ padding to the 64-byte minimum, then FCS
```

One pause *quantum* = 512 bit-times. At Gigabit speed that is **512 ns**, so the maximum 65535 quanta ≈ **33.6 ms** of pause. `code/main.py` converts quanta to wall-clock time at any link speed.

### Jumbo frames

Vendors added **jumbo frames** (typically up to ~9 KB / 9000-byte MTU) because a 1500-byte payload is tiny at Gigabit rates — bigger frames mean fewer per-frame interrupts and less segmentation/reassembly work. Jumbo frames are **not** part of the 802.3 standard (they break compatibility with 1518-byte-only gear), but most switches and NICs support them. The catch: every device in the path must agree on the same MTU, or oversize frames are silently dropped or fragmented — a classic real-world misconfiguration.

### 10-Gigabit Ethernet: full-duplex only, 64B/66B

10-Gigabit Ethernet (802.3ae, fiber 2002, twinax 2004, twisted pair 2006) is a clean break: **all versions are full-duplex only** and **CSMA/CD is removed from the design entirely**. Without a collision protocol, distance is bounded purely by the physics of the medium, which is why 10GBASE-ER reaches 40 km — far beyond anything CSMA/CD ever allowed. Interfaces still autonegotiate and fall back to the highest common speed.

The line code changes too: instead of 8B/10B's 25% overhead, 10 GbE **scrambles** the data then applies **64B/66B** — 64 data bits wrapped with a 2-bit sync header = only ~3% overhead, while scrambling provides the transitions for clock recovery.

| Name | Medium | Max segment | Notes |
|---|---|---|---|
| 10GBASE-SR | Multimode fiber, 0.85 µm | up to 300 m | Short reach, in-building |
| 10GBASE-LR | Single-mode fiber, 1.3 µm | 10 km | Long reach |
| 10GBASE-ER | Single-mode fiber, 1.5 µm | 40 km | Extended, metro/WAN |
| 10GBASE-CX4 | 4 pairs twinax | 15 m | 8B/10B, 3.125 Gsym/s/pair, early to market |
| 10GBASE-T | 4 pairs Cat-6a UTP | 100 m | PAM-16, 800 Msym/s, LDPC FEC |

10GBASE-T is the hard one: each of the four pairs carries **2500 Mbps in both directions**, using **800 Msymbols/s** with **16 voltage levels (PAM-16)**, the data scrambled and protected by an **LDPC (Low-Density Parity-Check)** error-correcting code. It calls for **Category 6a** wiring; shorter runs may use lower categories, but old Cat-5 will not certify at full length — the exact trap from The Problem.

## Build It

`code/main.py` ties the math to the concepts. Work through it in this order:

1. Run `python3 main.py` and read the slot-time section: it computes the ~25 m naive half-duplex limit and the 512-byte carrier-extension slot that restores 200 m.
2. Read the efficiency function: confirm a 64-byte frame extended to 512 bytes yields ≈9% line efficiency, and that frame bursting recovers it.
3. Read the line-code comparison: verify 8B/10B costs 25% and 64B/66B costs ~3.1%, and that this overhead is *why* 10 GbE moved codes.
4. Read the PAUSE decoder: feed it a quanta value and a link speed; confirm 65535 quanta ≈ 33.6 ms at 1 Gbps.
5. Use the media-selector table function to map a (distance, medium) requirement to a standard name.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Prove a link is full-duplex | Switch/NIC duplex status; absence of `collisions` / `late collisions` counters | Duplex shows `full`, collision counters stay at zero under load |
| Spot carrier extension | Capture on a half-duplex Gigabit link: short frames padded to 512 bytes | You explain the ~9% efficiency and recommend switching to a switch |
| Decode a PAUSE frame | Wireshark filter `eth.type == 0x8808`; opcode 0x0001, quanta field | You convert quanta to ms and identify which end is congested |
| Diagnose jumbo-frame drops | Path MTU mismatch; oversize frames dropped at a 1500-MTU hop | You find the device with the smaller MTU and align the path |
| Pick 10 GbE media | Distance + fiber/copper budget vs the 10GBASE table | SR ≤300 m, LR 10 km, ER 40 km; T needs Cat-6a for 100 m |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook: *"Gigabit link is slow — is it half-duplex?"* listing the duplex check, the carrier-extension capture signature, and the hub-to-switch fix.
- Or a media-selection cheat sheet mapping distance ranges to 1000BASE-* / 10GBASE-* names with their line codes.

Start from [`outputs/prompt-gigabit-ethernet-to-10-gigabit-ethernet.md`](../outputs/prompt-gigabit-ethernet-to-10-gigabit-ethernet.md) and back every claim with a number from `code/main.py`.

## Exercises

1. A 64-byte frame on a half-duplex Gigabit hub link carries 46 bytes of payload but occupies a 512-byte slot. Compute the line efficiency, then recompute it if frame bursting packs four 512-byte real frames into one burst. Which mechanism does the standard prefer and why?
2. Your monitoring shows `eth.type == 0x8808` frames with a quanta field of `0x4000` arriving on a 1 Gbps link. How many milliseconds is the sender being asked to pause? Recompute the same quanta value for a 10 Gbps link.
3. A campus run is 600 m of multimode fiber at 10 Gbps. Which 10GBASE-* media qualifies, and which is excluded by distance? What changes if the run is 8 km of single-mode?
4. Explain to a colleague who says "Gigabit has no collisions" the exact configuration in which CSMA/CD is still active, and what the `late collisions` counter on their NIC is telling them.
5. Compute the bandwidth a 10 Gbps stream actually consumes on the wire under 8B/10B versus 64B/66B coding. By how many Gbps does switching to 64B/66B reduce the raw symbol-rate requirement?
6. A 10GBASE-T link won't certify over the building's existing Cat-5 at 100 m. Explain the physical-layer reasons (symbol rate, PAM-16, LDPC, Cat-6a requirement) and the cheapest fix.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Full-duplex | "Gigabit has no collisions" | True *only* on a buffered switch link, where CSMA/CD is disabled and distance is set by signal strength |
| Carrier extension | "padding" | Hardware-added extension symbols making a short half-duplex slot 512 bytes, restoring CSMA/CD timing at ~9% efficiency |
| Frame bursting | "sending lots of frames" | Concatenating multiple queued frames into one channel acquisition; preferred over carrier extension when frames are waiting |
| 8B/10B | "the encoding" | Fibre-Channel-borrowed DC-balanced code, 8 data bits → 10 line bits, 25% overhead; used by Gigabit fiber and 10GBASE-CX4 |
| 64B/66B | "the faster encoding" | Scrambled code, 64 data bits + 2-bit sync header, ~3% overhead; used by 10 GbE serial PHYs |
| PAUSE frame | "flow control" | 802.3x MAC control frame, EtherType 0x8808, opcode 0x0001, dest 01:80:C2:00:00:01, pause time in 512-bit-time quanta |
| Jumbo frame | "big packets" | Non-standard ~9 KB frame; reduces per-frame overhead but every hop must share the MTU or frames drop |
| 1000BASE-T | "Gigabit copper" | 802.3ab over 4-pair Cat-5, PAM-5 at 125 Msym/s, all pairs bidirectional via DSP |
| 10GBASE-T | "10-gig copper" | PAM-16 at 800 Msym/s over Cat-6a, LDPC-protected; will not certify on old Cat-5 at 100 m |

## Further Reading

- IEEE 802.3z (1998) — Gigabit Ethernet over fiber and shielded copper (1000BASE-X)
- IEEE 802.3ab (1999) — 1000BASE-T over Category 5 UTP
- IEEE 802.3ae (2002) — 10-Gigabit Ethernet
- IEEE 802.3x (1997) — full-duplex MAC control / PAUSE flow control
- IEEE 802.3 — the consolidated Ethernet standard (current revision)
- Tanenbaum & Wetherall, *Computer Networks*, Chapter 4 (The Medium Access Control Sublayer) — Ethernet section
- Spurgeon, *Ethernet: The Definitive Guide* — practical wiring and configuration detail
- Wireshark display-filter reference: `eth.type`, `eth.fcs`, and the MAC-control dissector for `0x8808`
