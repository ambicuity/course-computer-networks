# Carrier Sense Multiple Access Protocols to Collision-free Protocols

> Slotted ALOHA tops out at 1/e ≈ 0.368 channel utilization because stations transmit blind. Carrier-sense protocols do far better by listening before they talk. **1-persistent CSMA** sends with probability 1 the instant the channel goes idle — which guarantees a collision when two stations queue up behind a third's transmission. **Nonpersistent CSMA** backs off a random interval instead of pouncing, trading delay for fewer collisions. **p-persistent CSMA** (the slotted variant, refined by IEEE 802.11's DCF) transmits with probability p per slot. **CSMA/CD** — the classic Ethernet (IEEE 802.3) mechanism — adds analog collision detection so a sender aborts a garbled frame within one contention slot of 2τ instead of wasting the whole frame time; the worst-case detection window is twice the round-trip propagation delay, which is why 10 Mbps Ethernet fixes a 51.2 µs slot and a 64-byte minimum frame. When even contention-period collisions are intolerable, **collision-free protocols** eliminate them entirely: the basic **bit-map** reservation protocol gives each of N stations one contention slot, **token passing** (IEEE 802.5 Token Ring, FDDI, IEEE 802.17 RPR) circulates a permission token, and **binary countdown** (used in Datakit) bids station addresses bitwise via wired-OR to reach 100% efficiency. This lesson builds a discrete-event simulator that reproduces all of these and prints the utilization curve.

**Type:** Build
**Languages:** Python (stdlib), models
**Prerequisites:** Phase 5 lessons on ALOHA and slotted ALOHA; bandwidth-delay product; binary numbers
**Time:** ~90 minutes

## Learning Objectives

- Distinguish 1-persistent, nonpersistent, and p-persistent CSMA by their channel-busy and channel-idle decision rules, and predict which collides more under heavy load.
- Compute the CSMA/CD contention slot time 2τ from cable length and propagation speed, and explain the 64-byte / 51.2 µs minimum-frame rule for 10 Mbps Ethernet.
- Trace a binary-countdown bidding round given four station addresses and predict the winner using the wired-OR arbitration rule.
- Compare the efficiency of bit-map, token passing, and binary countdown, including why binary countdown reaches d/(d + log₂N) and can hit 100%.
- Run `code/main.py` to reproduce the utilization-versus-load ordering of pure ALOHA, slotted ALOHA, and the CSMA family.

## The Problem

You inherit a legacy industrial bus running 10 Mbps half-duplex Ethernet between PLCs on a factory floor. Throughput collapses to under 40% of line rate at peak, and a packet capture shows a storm of runt frames (under 64 bytes) and late collisions. A junior engineer wants to "just raise the bit rate" — but doubling the clock without changing the cable plant makes it worse, not better.

The symptom is collisions, but the *cause* is timing physics. A CSMA/CD station can only abort cleanly if it hears the collision before it finishes sending. If a frame is shorter than the round-trip propagation time across the longest cable run, the sender finishes transmitting and walks away *before* the collision echo arrives — a late collision the MAC layer can no longer retransmit automatically. To debug this you need to reason quantitatively about carrier sense, slot time 2τ, and why some networks abandon contention entirely for a collision-free scheme.

## The Concept

Stations that listen for a carrier (an ongoing transmission) and adapt are running **carrier sense protocols**, analyzed in detail by Kleinrock and Tobagi (1975). They beat ALOHA because no station starts transmitting on top of a frame it can already hear.

### 1-persistent vs nonpersistent vs p-persistent CSMA

All three sense the channel first. They differ only in what they do when it is *busy* and how greedily they grab it once it goes *idle*.

| Protocol | Channel idle | Channel busy | Collision recovery | Trade-off |
|---|---|---|---|---|
| 1-persistent | Transmit with probability 1 | Keep sensing; transmit the instant it goes idle | Wait random time, retry | Lowest delay, most collisions — N queued stations all fire at once |
| Nonpersistent | Transmit immediately | Wait a random time, *then* re-sense (do not camp on the channel) | Wait random time, retry | Higher delay, better utilization at high load |
| p-persistent (slotted) | Transmit with prob p; with prob 1−p defer to next slot | Wait until next slot, then run the idle rule | Treat as collision (random backoff) | Tunable; small p reduces collisions but adds delay |

The subtle killer in 1-persistent CSMA is **propagation delay**, not just simultaneous sends. Just after station A starts, station B becomes ready and senses an idle channel because A's signal has not yet reached B. B transmits and they collide. The probability of this scales with the **bandwidth-delay product** — how much of a frame fits "on the wire" at once. In short LAN segments only a sliver of a frame fits on the cable, so the collision window is small; on long or fast links the window grows and performance degrades. IEEE 802.11's DCF is a refinement of p-persistent CSMA (with collision *avoidance*, since wireless cannot reliably detect collisions).

The SVG in `assets/carrier-sense-multiple-access-protocols-to-collision-free-protocols.svg` shows these decision branches as a state machine, plus a CSMA/CD timing diagram and a binary-countdown bidding grid.

### CSMA/CD and the 2τ contention slot

Persistent/nonpersistent CSMA still collide when two idle-sensing stations start together. **CSMA/CD** (CSMA with Collision Detection — IEEE 802.3 classic Ethernet) adds the rule: *while transmitting, keep listening; if the signal read back differs from the signal sent, a collision is happening — abort immediately.* Aborting a garbled frame rather than finishing it saves bandwidth.

Collision detection is an **analog** process. The receiver must hear a returned signal that is not tiny relative to what it transmits — feasible on copper, but hard on wireless where the received signal can be a million times weaker than the transmitted one, which is the whole reason 802.11 uses avoidance (CA) instead of detection (CD).

The critical number is the **contention slot time 2τ**, where τ is the one-way propagation delay between the two most distant stations:

- Station A starts at t=0. Its signal reaches the far station B at t=τ.
- B may start transmitting just before t=τ, the instant before A's signal arrives.
- B's collision signal takes another τ to get back to A.
- So A is not *guaranteed* to detect a collision until **2τ** after it began.

A sender must therefore still be transmitting at t=2τ to be sure of hearing a collision. That forces a **minimum frame time ≥ 2τ**.

**Worked example — 10 Mbps Ethernet.** The standard fixes the worst-case round trip at 2τ = 51.2 µs (covering 2500 m of cable plus four repeaters). At 10 Mbps:

```
min frame bits = 51.2 µs × 10 Mbit/s = 512 bits = 64 bytes
```

That is exactly the 64-byte minimum Ethernet frame (and 46-byte minimum payload after the 18-byte header/FCS overhead). Frames shorter than 64 bytes are **runts**. Now the factory-floor bug is explained: bump the clock to 100 Mbps without shrinking the cable, and the slot time still needs 51.2 µs of *propagation*, so the minimum frame must grow tenfold — or the diameter must shrink. Fast Ethernet shrank the diameter; Gigabit added carrier extension. Sending a 64-byte frame faster than the medium's 2τ produces exactly the **late collisions** in the capture.

After capture, CSMA/CD alternates **contention** periods (the risky 2τ slots) and **transmission** periods, with **idle** periods when nothing is queued — the three-state model.

### The bit-map reservation protocol (collision-free)

Collisions still happen during CSMA/CD's contention period. For traffic that cannot tolerate that variance (real-time, voice over IP) we want zero collisions ever. The **basic bit-map protocol** is a reservation scheme:

- Each cycle begins with **N contention slots**, one per station, numbered 0…N−1.
- Station j that has a frame asserts a 1 bit in slot j; otherwise it stays silent (0).
- After all N slots, every station has heard the full reservation bitmap and knows the transmit order. Stations then send their frames back-to-back, no collisions.

Overhead is **1 bit per station per cycle**. At low load that 1 bit is prorated over few frames (poor efficiency); at high load it is amortized over N frames, so efficiency approaches d/(d + 1) for d-unit frames. This is the inverse trade-off to contention: collision-free protocols have higher delay at low load but better efficiency at high load.

### Token passing

Instead of a global bitmap, **token passing** circulates a small control message — the **token** — in a fixed station order. Holding the token is permission to send exactly one frame; then you pass it on. No token, no transmission, so no collisions.

| Standard | Name | Rate / medium | Fate |
|---|---|---|---|
| IEEE 802.5 | Token Ring | 4 / 16 Mbps STP | Beaten by switched Ethernet |
| ANSI/ISO | FDDI | 100 Mbps fiber dual ring | Beaten by switched Ethernet |
| IEEE 802.17 | RPR (Resilient Packet Ring) | Metro ISP rings, 2000s | Niche |

A physical ring is not required — **token bus** (IEEE 802.4) passes the token over a shared bus in a logical sequence. In a token ring each station forwards the token only to its neighbor, so a token need not propagate to all N stations before the next step; performance is similar to bit-map but contention slots and data frames are intermingled.

### Binary countdown

Bit-map and token passing both cost overhead proportional to N (1 bit or 1 token hop per station), so they scale badly to thousands of stations. **Binary countdown** (used in Datakit, Fraser 1987) fixes this with **wired-OR** bidding on binary station addresses, assuming negligible transmission delay so all stations see asserted bits instantaneously.

Arbitration rule: every contender broadcasts its address most-significant-bit first. The channel **BOOLEAN-ORs** simultaneous bits. *As soon as a station sees a high-order bit that is 0 in its own address overwritten by a 1, it drops out.* The highest address wins.

**Worked example** — stations 0010, 0100, 1001, 1010 all bid:

| Bit time | 0 | 1 | 2 | 3 | Action |
|---|---|---|---|---|---|
| 0010 | 0 | — | — | — | sees OR=1, gives up |
| 0100 | 0 | — | — | — | sees OR=1, gives up |
| 1001 | 1 | 0 | 0 | — | survives to bit 2; loses bit-3 tie |
| 1010 | 1 | 0 | 1 | 0 | **winner** |
| Wired-OR result | 1 | 0 | 1 | 0 | = address 1010 |

At bit 0 the OR is 1, so 0010 and 0100 (which transmitted 0) quit. At bit 2, 1010 asserts 1 while 1001 has 0, so 1001 quits. Winner: 1010, the highest address.

Efficiency is **d/(d + log₂N)** — only log₂N arbitration bits instead of N. If the frame format puts the sender's address first, those log₂N bits double as the address field and are not wasted, giving **100% efficiency**. The cost: higher-numbered stations always win, an implicit fixed priority.

### Putting it together: contention vs collision-free

Contention (CSMA, ALOHA) wins at **low load** (low delay, rare collisions). Collision-free protocols win at **high load** (fixed overhead, no wasted collision time). Limited-contention protocols (next lesson) combine both. `code/main.py` simulates this crossover and reproduces the Tanenbaum Figure 4-4 ordering.

## Build It

1. Read `code/main.py`. It is a stdlib-only discrete-event simulator with one function per protocol.
2. Run it: `python3 code/main.py`. It prints utilization for pure/slotted ALOHA and the CSMA family across offered loads G, plus a binary-countdown trace and a CSMA/CD slot-time calculation.
3. Verify the ordering: at high G, nonpersistent CSMA should beat 1-persistent CSMA, and both should beat slotted ALOHA's 1/e ceiling.
4. Change `tau_slots` (the normalized propagation delay a) and re-run. Larger a (bigger bandwidth-delay product) should worsen every CSMA result — confirming the propagation-delay argument.
5. Feed your own station-address set into `binary_countdown` and confirm the highest address always wins.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify which CSMA variant a NIC runs | Driver/MAC spec, "persistent" vs backoff-on-busy behavior | You can state the idle-rule and busy-rule and predict collision behavior under load |
| Size a CSMA/CD network | 2τ slot time, cable length, bit rate, min frame size | min frame bits = 2τ × rate; you flag runts and late collisions correctly |
| Choose contention vs collision-free | Offered load curve, delay budget (e.g. VoIP jitter) | You pick collision-free for high-load/real-time, contention for bursty/low-load |
| Trace a binary-countdown round | Station addresses, wired-OR per bit time | Your predicted winner matches the highest address; dropouts match the rule |

## Ship It

Produce one artifact under `outputs/`:

- A CSMA/CD slot-time + minimum-frame calculator (cable length & rate in, runt threshold out).
- A one-page runbook mapping symptoms (runts, late collisions, high deferral) to causes.
- A protocol decision diagram: contention vs collision-free by load and delay budget.
- A binary-countdown bidding tracer for arbitrary address sets.

Start from the prompt in `outputs/prompt-carrier-sense-multiple-access-protocols-to-collision-free-protocols.md`.

## Exercises

1. A 100 Mbps half-duplex segment spans 200 m at 2×10⁸ m/s propagation. Compute τ, the 2τ slot time, and the minimum frame size in bytes. Is a 64-byte frame safe?
2. Stations 0001, 0110, 0111, 1000 contend under binary countdown. Trace the wired-OR per bit time and name the winner. Which stations are starved if 1000 always has traffic?
3. Under heavy load (G=5), rank pure ALOHA, slotted ALOHA, 1-persistent CSMA, and nonpersistent CSMA by utilization. Explain why nonpersistent overtakes 1-persistent.
4. A VoIP deployment over a shared bus shows acceptable mean latency but unacceptable jitter under load. Argue for switching from CSMA/CD to a token-passing or bit-map scheme, and state the delay cost at low load.
5. Explain why IEEE 802.11 cannot use CSMA/CD and must fall back to collision *avoidance*. Tie your answer to the analog detection requirement and the received-signal-strength problem.
6. Your bit-map protocol serves 1000 stations. Compute its per-cycle overhead in bits and compare to binary countdown's per-cycle arbitration overhead. At what station count does binary countdown clearly win?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| 1-persistent CSMA | "send when idle" | Transmit with probability 1 the instant the channel frees — N queued stations collide together |
| Nonpersistent CSMA | "the polite one" | On busy, back off a random time *before* re-sensing instead of camping; more delay, less collision |
| p-persistent CSMA | "send with probability p" | Slotted: transmit with prob p per idle slot, defer with 1−p; basis of 802.11 DCF |
| Contention slot (2τ) | "the collision window" | Twice the one-way propagation delay; the time a sender must keep transmitting to guarantee collision detection |
| Minimum frame | "the 64-byte rule" | Frame must last ≥ 2τ so the sender is still on-air when a collision returns; shorter = runt |
| Late collision | "a weird collision" | Collision detected after the slot time, when the sender has already finished — usually a too-long cable or too-short frame |
| Bit-map protocol | "reservation" | N contention slots, one bit per station, announce intent then send collision-free; 1 bit/station overhead |
| Token passing | "ring with a token" | Circulating permission message; only the holder may send (802.5, FDDI, 802.17 RPR) |
| Binary countdown | "address bidding" | Wired-OR of station addresses MSB-first; highest address wins; d/(d+log₂N) efficiency, up to 100% |
| Wired-OR | "the bits combine" | Channel BOOLEAN-ORs simultaneously asserted bits so a 1 always overrides a 0 |

## Further Reading

- IEEE 802.3 — Ethernet / CSMA-CD MAC and slot-time definition
- IEEE 802.11 — Wireless LAN; DCF as p-persistent CSMA with collision avoidance
- IEEE 802.5 — Token Ring; IEEE 802.4 — Token Bus; IEEE 802.17 — Resilient Packet Ring
- Kleinrock & Tobagi (1975), "Packet Switching in Radio Channels: Part I — Carrier Sense Multiple-Access Modes"
- Fraser, A. G. (1987), "Towards a Universal Data Transport System" (Datakit / binary countdown)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4, sections 4.2.2–4.2.3
