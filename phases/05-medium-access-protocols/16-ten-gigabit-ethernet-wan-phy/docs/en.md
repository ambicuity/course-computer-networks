# 10-Gigabit Ethernet: WAN PHY, 64B/66B coding, and fiber variants

> 10 Gigabit Ethernet finally abandoned half-duplex collision detection entirely. At this speed, a shared collision domain is not useful, so the standards split into full-duplex-only PHYs: 10GBASE-SR for short multimode fiber, 10GBASE-LR for longer single-mode fiber, 10GBASE-ER for extended reach, 10GBASE-T for twisted pair, and the interoperable WAN PHY variant that matches SONET/SDH framing expectations. The big coding change is 64B/66B: every 64 bytes of payload gets 2 bits of synchronization overhead, replacing the heavy 8B/10B penalty and making the line efficient enough for large data flows. This lesson ties the PHY choices to real operational questions: which cable reaches what distance, why 10GBASE-T needs far more DSP than 1000Base-T, and why 10 Gigabit Ethernet is about serialization and optics, not collisions.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Gigabit Ethernet carrier extension, 8B/10B, full duplex switching, optical media basics
**Time:** ~75 minutes

## Learning Objectives

- Compare the major 10 Gigabit Ethernet PHY families by medium, reach, and use case.
- Explain why 64B/66B coding replaced 8B/10B and how its overhead is only about 3.125%.
- Distinguish LAN PHY and WAN PHY behavior, especially the WAN PHY's interoperability intent with SONET/SDH environments.
- Explain why 10GBASE-T depends on sophisticated digital signal processing, echo cancellation, and multiple-pair full-duplex transmission.
- Diagnose common 10 GbE problems from cable reach, optics type, autonegotiation, and FCS/CRC symptoms.

## The Problem

A server team upgrades a storage network from 1 GbE to 10 GbE expecting a simple cable swap. Half the links come up, half do not. One campus run exceeds the copper reach and flaps. One optical transceiver pair is multimode on one end and single-mode on the other. Another port works but consumes so much CPU on the NIC that the storage benchmark barely improves over 1 GbE. Operators see only "link down" or "throughput not as expected." The real answer is that 10 GbE is no longer one thing; it is a family of PHYs with different optics, distances, and DSP requirements.

## The Concept

### The 10 GbE family

10 Gigabit Ethernet keeps the Ethernet MAC but swaps the physical layer to suit the medium.

| PHY | Medium | Typical reach | Notes |
|---|---|---|---|
| 10GBASE-SR | Multimode fiber | ~26–400 m depending on fiber grade | Short-reach optics, data center and campus use |
| 10GBASE-LR | Single-mode fiber | ~10 km | Long-reach fiber for campus or metro uplinks |
| 10GBASE-ER | Single-mode fiber | ~40 km | Extended reach, more powerful optics |
| 10GBASE-LX4 | Fiber | ~300 m MMF / ~10 km SMF | Legacy wavelength-division approach |
| 10GBASE-T | Twisted pair Cat6a/Cat7 | 100 m | Copper PHY with heavy DSP and echo cancellation |
| 10GBASE-W | WAN PHY | SONET/SDH handoff compatibility | Bridges Ethernet frames into WAN transport expectations |

The MAC frame is the same; only the PHY changes. That is why switch uplinks and server NICs can move between fiber and copper as long as the installed medium and optics match the negotiated PHY.

### 64B/66B coding

10 GbE's signature coding scheme is 64B/66B. Instead of converting every 8 bits to 10 bits like 8B/10B, it groups 64 data bits into a 66-bit block:

```
64 data bits + 2 sync bits = 66-bit block
overhead = 2 / 64 = 3.125%
```

The two sync bits distinguish data blocks from control blocks. The encoding is far more efficient than 8B/10B, and the low overhead is one reason 10 GbE became economical for high-volume traffic.

The sync bits also help the receiver maintain block alignment. If the receiver loses lock, it can search for the expected sync pattern and recover framing without needing a separate low-overhead control channel.

### Why 10GBASE-T is harder than 1000Base-T

10GBASE-T still uses copper, but the signaling problem is much harder than Gigabit Ethernet's. At 10 Gbps over four pairs, the PHY must cope with:

- much tighter timing margins,
- more severe crosstalk,
- more aggressive echo cancellation,
- PAM-16 or similar multilevel coding depending on implementation,
- and stronger forward error correction.

The result is a PHY that behaves like a tiny signal-processing appliance. This is why 10GBASE-T ports run hotter and often have higher latency than short-reach fiber ports. The trade-off buys you the convenience of existing copper plant.

### WAN PHY versus LAN PHY

The WAN PHY exists so Ethernet can interoperate more naturally with WAN transport systems. The intent is not to make Ethernet "slow"; it is to make the framing and clocking friendly to SONET/SDH handoff expectations. In practical terms, WAN PHY is the niche choice when the carrier or transport system constrains the handoff, while LAN PHY is the mainstream choice for campus and data center links.

### Operational failures

The most common 10 GbE issues are ordinary physical-layer mismatches disguised as application problems:

| Symptom | Likely cause | Evidence |
|---|---|---|
| Link never comes up | Wrong optic, wrong wavelength, unsupported PHY | Transceiver type mismatch, port logs |
| Link flaps under load | Distance too long, dirty fiber, bad connector | Error counters, optical power alarms |
| Throughput is unexpectedly low | CPU/DSP cost, MTU mismatch, congestion elsewhere | NIC stats, system load, packet drops |
| FCS or CRC errors | Signal corruption, bad cabling, optics problem | Interface counters on both ends |
| High latency on copper | 10GBASE-T DSP and negotiation overhead | Hardware/driver behavior |

## Build It

1. Read `code/main.py` and identify any functions that model coding overhead, media reach, or PHY choice.
2. Compare 8B/10B and 64B/66B efficiency numerically for a 10 Gbps link.
3. Create a small table of media types and maximum practical reach for SR, LR, ER, T, and WAN PHY.
4. Simulate a link selection decision from advertised PHY capabilities and cable type.
5. Add a diagnostic branch that emits likely fault categories when an optic or cable choice is invalid.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute coding overhead | 64B/66B arithmetic | Overhead is 3.125%, much lower than 8B/10B |
| Match medium to PHY | Reach table | Multimode, single-mode, or copper choice matches installed plant |
| Explain WAN PHY | Short written summary | WAN PHY is about transport compatibility, not higher speed |
| Diagnose bad link | Error/counter interpretation | Wrong optic or cable yields link failure or recurring errors |
| Compare copper vs fiber | Latency and heat notes | 10GBASE-T costs more DSP; fiber is simpler on the NIC |

## Ship It

Produce one artifact under `outputs/`:

- A 10 GbE selection guide that maps use case to PHY choice, maximum distance, and operational trade-off.
- A coding-efficiency worksheet comparing 8B/10B, 64B/66B, and frame-level payload efficiency.
- A troubleshooting runbook for "10 GbE link is down or slow".

Start from `outputs/prompt-ten-gigabit-ethernet-wan-phy.md` if present, or create `outputs/10gbe-phy-selection-guide.md`.

## Exercises

1. Compute the overhead percentage of 64B/66B and compare it with 8B/10B.
2. Why does 10GBASE-T need more signal processing than 1000Base-T even though both use copper and multiple pairs?
3. A data center link needs 300 m reach with low latency. Which 10 GbE PHY is the most plausible choice and why?
4. Explain why 10 GbE does not use CSMA/CD, even if old textbooks still mention Ethernet collision rules.
5. A switch reports a 10 GbE port as up but the peer sees no light. List the first three checks you would make.
6. Compare LAN PHY and WAN PHY in one paragraph for a networking teammate.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| 10GBASE-SR | "Short-reach fiber" | 10 GbE over multimode fiber for short indoor distances |
| 10GBASE-LR | "Long-reach fiber" | 10 GbE over single-mode fiber for about 10 km |
| 10GBASE-ER | "Extended-reach fiber" | 10 GbE over single-mode fiber for longer campus or metro spans |
| 10GBASE-T | "10 gig over copper" | 10 GbE over twisted pair with heavy DSP and 100 m reach |
| 64B/66B | "New encoding" | 64 data bits plus 2 sync bits; only 3.125% overhead |
| WAN PHY | "Carrier handoff mode" | 10 GbE variant shaped for SONET/SDH interoperability |
| Optical budget | "How far light can go" | Power and attenuation margin that determines real fiber reach |
| DSP echo cancellation | "Copper magic" | Digital subtraction of self-interference on full-duplex copper pairs |

## Further Reading

- IEEE 802.3ae (2002) — 10 Gigabit Ethernet physical layer specifications for fiber and CX4.
- IEEE 802.3an (2006) — 10GBASE-T over twisted pair, with PAM-16 and LDPC coding.
- IEEE 802.3 clause 49 — 64B/66B coding, lane distribution, and block alignment.
- Charles Spurgeon, *Ethernet: The Definitive Guide* (O'Reilly) — 10 GbE optics and troubleshooting.
- Seifert, *The All-New Switch Book* (Wiley) — chapter on high-speed Ethernet switch fabric design.

## Selected Numbers Worth Memorizing

| Quantity | Value |
|---|---|
| 10GBASE-T symbol rate | 800 Mbaud over each of 4 pairs |
| 10GBASE-T levels per symbol | 16 (PAM-16) |
| 10GBASE-CX4 lanes × rate | 4 × 3.125 Gbaud |
| 64B/66B overhead | 2 bits per 64 bits = 3.125% |
| 8B/10B overhead | 2 bits per 8 bits = 25% |
| Effective baud for 10G with 64B/66B | 10.3125 Gbaud (≈ 10G × 66/64) |
| Effective baud for 10G with 8B/10B | 12.5 Gbaud (≈ 10G × 10/8) |
| 10GBASE-SR reach (OM3 / OM4) | 300 m / 400 m |
| 10GBASE-LR reach | 10 km |
| 10GBASE-ER reach | 40 km |
| 10GBASE-T reach | 100 m on Cat6a (55 m on Cat5e possible) |
| 10GBASE-CX4 reach | 15 m on twinax |
