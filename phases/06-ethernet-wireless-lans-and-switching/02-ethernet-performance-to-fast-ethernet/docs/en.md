# Ethernet Performance to Fast Ethernet

> Classic shared (CSMA/CD) Ethernet pays for arbitration with a contention interval. Following Metcalfe & Boggs (1976), if `k` stations each transmit in a slot with probability `p`, the chance one succeeds is `A = kp(1-p)^(k-1)`, maximized at `p = 1/k` where `A → 1/e ≈ 0.368` as `k → ∞`. The mean number of contention slots is `1/A` (at most `e ≈ 2.72`), each slot lasting one round-trip `2τ`, so channel efficiency is `1 / (1 + 2BLe/cF)` — it collapses as the bandwidth-distance product `BL` rises or frame size `F` shrinks. At 10 Mbps with a 51.2 µs (512-bit) slot time, 64-byte frames are badly inefficient while 1024-byte frames reach ~85%. Two evolutions fixed this: **switched Ethernet** (one collision domain per port, full duplex, no CSMA/CD, simultaneous frames over a multi-Gbps backplane) and **Fast Ethernet / IEEE 802.3u (June 1995)**, which kept the 64-byte minimum and frame format but cut the bit time from 100 ns to 10 ns — shrinking the maximum collision diameter 10× to ~250 m. Watch for the classic failure: an **autonegotiation duplex mismatch** that produces late collisions and FCS errors on one side only.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 06 · 01 (Ethernet framing, CSMA/CD, binary exponential backoff); Manchester / 4B5B line coding from Phase 02
**Time:** ~75 minutes

## Learning Objectives

- Compute classic Ethernet channel efficiency from `A = kp(1-p)^(k-1)` and `efficiency = 1/(1 + 2BLe/cF)`, and explain why small frames and long cables kill it.
- Explain why the contention slot equals one round-trip `2τ` and why that ties minimum frame size (64 bytes) to maximum cable length (2500 m at 10 Mbps).
- Contrast a hub (one collision domain, logically the old shared cable) with a switch (one collision domain per port, full duplex, no CSMA/CD).
- State what 802.3u changed and held constant: bit time 100 ns → 10 ns, slot diameter 2500 m → 250 m, frame format unchanged.
- Distinguish 100Base-T4, 100Base-TX, and 100Base-FX by cabling, pairs, encoding, and reach.
- Identify a duplex mismatch from late collisions, FCS/CRC errors, and runts in counters or a trace.

## The Problem

A user reports that a backup over the office LAN "crawls" — about 3 Mbit/s on a link marked 100 Mbps full duplex. Ping looks fine at idle, but throughput collapses under load. You pull interface counters and see, on the *switch* side, a steady climb of `late collisions`, `FCS errors`, and `runts`; the *host* side shows `carrier sense errors` instead. Nothing is broken at layer 3.

This is the signature of a **duplex mismatch**: one end autonegotiated to half duplex, the other was hard-set to full. Understanding it requires the whole arc of this lesson — why CSMA/CD needs a round-trip slot, why a *late* collision (after the 64-byte slot time) is pathological rather than normal, and how Fast Ethernet's tighter timing budget makes the symptom sharper. The same physics that bounds efficiency in classic Ethernet is what turns a config typo into a 30× slowdown.

## The Concept

Source: [`chapters/chapter-04-the-medium-access-control-sublayer.md`](../../../../chapters/chapter-04-the-medium-access-control-sublayer.md), sections 4.3.3–4.3.5.

### Why there is a contention interval at all

Classic Ethernet is a single shared medium. A station that wants to send must win the channel against everyone else, and the only way to detect a clash is **collision detection during transmission** (CSMA/CD). A collision can only be guaranteed-detected if every sender is still transmitting when the worst-case echo returns — one full round-trip propagation, `2τ`. That round-trip is the *slot time*. For 10 Mbps, `2τ = 51.2 µs = 512 bit times = 64 bytes`; the standard bounds the span to ~2500 m once repeater and transceiver delays eat into that round-trip budget. This is exactly why the **minimum Ethernet frame is 64 bytes**: a frame shorter than the slot time could finish before its own collision came back, and the sender would wrongly believe it succeeded.

### Modeling efficiency: the Metcalfe-Boggs result

Under heavy constant load with `k` stations always ready, assume each transmits in a contention slot with probability `p`. The probability that *exactly one* succeeds is:

```
A = k · p · (1 - p)^(k-1)              (4-5)
```

`A` is maximized at `p = 1/k`, and as `k → ∞`, `A → 1/e ≈ 0.368`. Because each contention is a geometric sequence of slots, the **mean number of slots per contention is `1/A`** — at most `e ≈ 2.718`. Each slot costs `2τ`, so the mean contention interval `w = 2τ/A ≤ 2τe ≈ 5.4τ`.

If a frame takes `P` seconds to send, efficiency is the useful time over total time:

```
efficiency = P / (P + 2τ/A)            (4-6)
```

Rewriting with frame length `F`, bandwidth `B`, cable length `L`, signal speed `c`, and `P = F/B`, for the optimal `e`-slot case:

```
efficiency = 1 / (1 + 2·B·L·e / (c·F))  (4-7)
```

The denominator term `2BLe/cF` is the **bandwidth-distance penalty**. Efficiency falls when you raise bandwidth `B` or length `L`, or shrink frame `F`. `code/main.py` evaluates 4-7 directly.

### Worked numbers: where 64-byte frames hurt

At 10 Mbps, `2τ = 51.2 µs`, `c ≈ 2 × 10^8 m/s` in copper, evaluating Eq. (4-7) at the full collision diameter (the numbers `code/main.py` prints):

| Frame `F` | Transmit time `P` | Efficiency (Eq. 4-7) |
|-----------|-------------------|----------------------|
| 64 bytes  | 51.2 µs           | ~27% (frame ≈ one slot) |
| 256 bytes | 204.8 µs          | ~60% |
| 512 bytes | 409.6 µs          | ~75% |
| 1024 bytes| 819.2 µs          | ~85% |

The textbook figure (Fig. 4-16) plots the same shape. The lesson: 85% with 1024-byte frames is far better than slotted ALOHA's 37% ceiling — but only because the frame dwarfs the slot. Halve the frame or double the cable and the picture degrades. The SVG ([`assets/ethernet-performance-to-fast-ethernet.svg`](../assets/ethernet-performance-to-fast-ethernet.svg)) shows the slot-vs-frame timeline and the efficiency curve side by side.

### Switched Ethernet: deleting the collision domain

Hubs replaced the long coax with a star of twisted pairs to a central box, but a **hub is logically still one cable** — it electrically joins all ports, so every station shares one collision domain and CSMA/CD still arbitrates. Adding stations just slices the fixed capacity thinner.

A **switch** looks identical from outside (RJ-45 ports, 4–48 of them) but is fundamentally different inside:

| Property | Hub | Switch |
|----------|-----|--------|
| Collision domains | 1 (shared) | 1 *per port* |
| Forwarding | Repeats to all ports | Forwards only to the destination port (by MAC) |
| Simultaneity | One frame at a time | Many frames at once over backplane |
| CSMA/CD on full-duplex link | Required | Not needed (collisions impossible) |
| Capacity scaling | Splits fixed pool | Aggregates, often 10× throughput |
| Promiscuous-mode snooping | Sees all traffic | Sees only its own port |

On a **full-duplex** switch port, station and port each have a dedicated pair to transmit on, so they can send simultaneously — collisions become structurally impossible and CSMA/CD is disabled. (On a *half-duplex* port, CSMA/CD still runs.) Because two inputs can target the same output, switches must **buffer** and queue frames. The switch must also learn which MAC lives on which port — the backward-learning process covered later in Phase 06.

### Fast Ethernet (802.3u, June 1995): same frame, 10× the clock

When 10 Mbps tightened, IEEE re-opened 802.3 in 1992. The winning proposal: **keep everything, just go faster.** 802.3u is an *addendum* to 802.3, not a new standard, to stress backward compatibility. The core change is one number — **bit time from 100 ns to 10 ns**. Frame format, 64-byte minimum, addressing, and CSMA/CD rules are untouched.

The catch is the slot-time invariant. Efficiency Eq. (4-7) and collision detection both depend on the frame still covering the round trip. Hold the 64-byte minimum and raise speed 10×, and the **maximum collision diameter must shrink 10×: 2500 m → ~250 m**. A hub with 100 m drops already fits, so the easy choice was to cut distance rather than enlarge frames. All Fast Ethernet uses hubs/switches on twisted pair or fiber — no vampire taps, no BNC.

### The three Fast Ethernet physical layers

| Name | Cable | Pairs | Encoding / signaling | Max segment | Duplex |
|------|-------|-------|----------------------|-------------|--------|
| 100Base-T4 | Cat 3 UTP | 4 (3 active each way) | Ternary, 8B6T, 25 MHz | 100 m | Half only |
| 100Base-TX | Cat 5 UTP | 2 | 4B/5B at 125 MHz | 100 m | **Full** |
| 100Base-FX | Multimode fiber | 2 strands | 4B/5B, NRZI | 2000 m | **Full** |

100Base-T4 let buildings reuse existing telephone-grade Cat 3 (giving up one phone pair). It needed 4 pairs because Cat 3 cannot carry 100 Mbps cleanly on one. But once buildings rewired with Cat 5, **100Base-TX won** the market: only two pairs, 4B/5B encoding (4 data bits → 5 line bits gives enough transitions for clock recovery), full duplex 100/100. 100Base-FX over fiber reaches 2 km — too long for half-duplex CSMA/CD, so a 2 km FX link *must* run full duplex on a switch.

### Autonegotiation and the duplex-mismatch failure

802.3u added **autonegotiation**: two link partners exchange Fast Link Pulse bursts to agree on the best common speed (10/100) and duplex (half/full). It usually works. It famously breaks when **one end autonegotiates and the other is hard-coded to full duplex** (Shalunov & Carlson, 2005). The autonegotiating end, hearing no negotiation, falls back to **half duplex** per spec. Now:

- The hard-set **full-duplex** end transmits whenever it has data, ignoring carrier sense.
- The **half-duplex** end senses that transmission as a collision *after* it has already started sending — a **late collision** (a collision detected after the 64-byte slot time, which should never happen on a correctly configured LAN).

Result: the half-duplex side logs `late collisions` and emits `runts`; both sides log `FCS / CRC errors` from truncated frames; throughput collapses under bidirectional load while idle pings pass. The fix is to make both ends match — preferably autonegotiate on both. `code/main.py` includes a small duplex-mismatch detector that classifies counter snapshots.

## Build It

1. Open `code/main.py`. The `channel_efficiency()` function implements Eq. (4-7); call it across frame sizes to reproduce the ~27%/60%/75%/85% table above.
2. Use `slot_time_us()` to confirm that 64 bytes = 512 bits = the 51.2 µs slot at 10 Mbps, then call `max_collision_diameter_m(100)` and watch the diameter shrink 10× when you raise `bandwidth_mbps` from 10 to 100.
3. Build profiles with `hub_profile(8)` and `switch_profile(8, full_duplex=True)` and print `.describe()` to see the collision-domain contrast for an N-port box.
4. Feed `classify_duplex(...)` a switch-side and host-side counter snapshot (late collisions, FCS errors, runts vs carrier-sense errors) and confirm it flags a mismatch.
5. Run `python3 code/main.py` end to end and read the printed report.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Justify the 64-byte minimum | Slot time = `2τ` = 512 bits at 10 Mbps | You can state that a sub-slot frame breaks collision detection |
| Predict efficiency | Eq. (4-7) output vs frame size | Your numbers track Fig. 4-16 (85% at 1024 B) |
| Tell hub from switch | Port-to-collision-domain mapping; full-duplex flag | You explain why CSMA/CD is *off* on a full-duplex switch port |
| Verify a Fast Ethernet PHY | Cable type, pair count, encoding, reach | You match 100Base-TX ↔ Cat 5 / 4B5B / 2 pairs / full duplex |
| Diagnose slow "100 Mbps full" link | `show interface` counters: late collisions, FCS, runts | You name duplex mismatch and which side is half duplex |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **duplex-mismatch runbook**: the counter signatures per side, the `show interface` fields to read, and the remediation (match both ends, prefer autoneg).
- Or an **efficiency calculator note** wrapping `code/main.py` for quick "is my frame size sane for this BL product?" checks.

Start from [`outputs/prompt-ethernet-performance-to-fast-ethernet.md`](../outputs/prompt-ethernet-performance-to-fast-ethernet.md).

## Exercises

1. A 10 Mbps shared segment runs at the full 2500 m diameter with 128-byte frames. Use Eq. (4-7) (`c = 2×10^8 m/s`, `e` slots) to estimate efficiency. Then shorten the cable to 250 m and recompute — by how much does efficiency improve, and why?
2. You move that same workload to a 100 Mbps **half-duplex** hub but keep the 250 m diameter and 128-byte frames. The slot time is now 5.12 µs. Does efficiency rise, fall, or stay roughly equal? Explain in terms of the `2BLe/cF` term.
3. A switch port shows `0` collisions of any kind under heavy load while a hub port on the same switch shows binary-backoff collisions. Which port is full duplex, and why does the difference exist?
4. Given an interface snapshot — switch side: `late collisions=412, FCS errors=1190, runts=380`; host side: `carrier sense errors=905` — which end is half duplex and which is hard-set full? What single change fixes it?
5. Explain why a 2 km 100Base-FX link cannot legally run as a half-duplex CSMA/CD segment. Tie your answer to the 250 m collision diameter.
6. A vendor ships "jumbo" 9000-byte frames on a 1 Gbps link. Using Eq. (4-7) intuition, argue why larger frames help efficiency — and one reason the standard still caps the *minimum* at 64 bytes rather than raising it.

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Slot time (`2τ`) | "the wait before sending" | One worst-case round-trip; the unit of contention and the floor on min frame size (512 bits at 10 Mbps) |
| Channel efficiency | "how fast the wire is" | Useful frame time over total time, `1/(1+2BLe/cF)`; falls with the bandwidth-distance product |
| Collision domain | "the network segment" | The set of stations that can collide; one shared (hub) vs one per port (switch) |
| Hub | "a switch without ports labeled" | An electrical repeater — logically the old shared cable, single collision domain |
| Switch | "a smart hub" | Per-port collision domain, MAC-based forwarding, full-duplex, no CSMA/CD |
| Fast Ethernet / 802.3u | "100 meg Ethernet" | 1995 addendum: bit time 100→10 ns, frame format unchanged, diameter cut 10× to ~250 m |
| 100Base-TX | "the copper one" | Cat 5, 2 pairs, 4B/5B at 125 MHz, full duplex 100/100 |
| Autonegotiation | "plug and play speed" | FLP exchange agreeing speed+duplex; falls back to *half* if the partner is silent |
| Late collision | "a normal collision" | A collision after the slot time — never legal; the fingerprint of duplex mismatch |
| Duplex mismatch | "a slow link" | One end half, one end full; produces late collisions + FCS errors + runts |

## Further Reading

- **IEEE 802.3** (base CSMA/CD Ethernet) and **IEEE 802.3u-1995** (Fast Ethernet / 100Base-T addendum).
- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., Ch. 4 §4.3.3–4.3.5 (Ethernet Performance, Switched Ethernet, Fast Ethernet).
- Metcalfe, R. & Boggs, D. (1976), "Ethernet: Distributed Packet Switching for Local Computer Networks," *CACM* 19(7) — the original efficiency analysis.
- Boggs, Mogul & Kent (1988), "Measured Capacity of an Ethernet" — empirical evidence Ethernet works well at real load.
- Shalunov, S. & Carlson, R. (2005), "Detecting Duplex Mismatch on Ethernet" — the canonical mismatch reference.
- Wireshark display filters for evidence: `eth.fcs_bad == 1`, `eth.len < 64` (runts); plus `show interface` counter fields `late-collisions`, `runts`, `CRC`.
