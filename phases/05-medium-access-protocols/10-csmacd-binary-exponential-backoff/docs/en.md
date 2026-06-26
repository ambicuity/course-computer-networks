# CSMA/CD with Binary Exponential Backoff on Shared Ethernet

> Classic Ethernet (IEEE 802.3, 10BASE5/10BASE2/10BASE-T) uses 1-persistent CSMA/CD — Carrier Sense Multiple Access with Collision Detection — as its MAC sublayer protocol. When two stations transmit simultaneously their signals overlap and corrupt; both detect this within 2τ (the worst-case end-to-end propagation round-trip, ≈51.2 µsec on a 2500 m 10 Mbps segment), abort with a 32-bit jam signal, and independently choose a random backoff. The backoff interval after the i-th consecutive collision is drawn uniformly from [0, 2^i − 1] slot times (each slot = 512 bit times = 51.2 µsec), capped at 1023 after the 10th collision, and the frame is abandoned after 16 consecutive collisions. This exponential doubling of the contention window is the binary exponential backoff (BEB) algorithm — it keeps delay low under light load (small window) while preventing livelock under heavy load (large window spreads retransmissions). The minimum Ethernet frame size of 64 bytes is not arbitrary: a station must still be transmitting when a far-end collision echo returns, so the frame must occupy the wire for at least 2τ, which at 10 Mbps equals 512 bits. The IEEE 802.3 CRC-32 over the frame body is the sole error-detection mechanism; neither CSMA/CD nor classic Ethernet provides acknowledgements or retransmission at the MAC layer.

**Type:** Learn
**Languages:** Python, simulation
**Prerequisites:** CSMA variants (1-persistent, non-persistent, p-persistent), ALOHA throughput analysis, Manchester encoding, CRC-32 basics
**Time:** ~75 minutes

## Learning Objectives

- Derive why the minimum Ethernet frame size is 64 bytes from the 2τ propagation constraint.
- Trace the BEB algorithm for a sequence of collisions, stating the exact contention window [0, 2^i − 1] at each step and the cap/abort thresholds (10 collisions → 1023 cap, 16 → abort).
- Identify the IEEE 802.3 Ethernet frame fields (Preamble 8B, DA 6B, SA 6B, Type/Length 2B, Data 46–1500B, FCS 4B) and explain the Type vs. Length disambiguation rule (≤ 0x0600 = Length, > 0x0600 = Type).
- Calculate channel efficiency using η = 1 / (1 + 2BLe/cF) and identify the BL product as the key degradation factor.
- Explain why CSMA/CD is absent in modern full-duplex switched Ethernet and what replaced the contention mechanism.
- Run `code/main.py` to observe collision histograms and mean backoff rounds as station count increases from 2 to 32.

## The Problem

You are debugging packet loss on a legacy 10BASE2 (thinnet coax) segment shared by 12 workstations running a backup job. Captures show frames with corrupted CRCs, but only during the nightly window. There are no physical-layer errors on idle days. The NIC counters show `rx_over_errors` and a steadily climbing `collision` counter that peaks at values like 7–9 consecutive collisions per frame, well below the abort threshold of 16, yet throughput collapses to under 20% of wire rate.

Understanding what drives collision probability, why backoff grows exponentially rather than linearly, and what the hard limits are (cap at 1023, give-up at 16) is necessary to determine whether the segment is simply overloaded or whether a station is misbehaving — a faulty NIC that never backs off would look very similar in a capture until you isolate the MAC source address.

## The Concept

### Carrier Sense and the 1-Persistent Rule

Stations running 1-persistent CSMA listen before transmitting. If the channel is idle, they transmit immediately (probability = 1, hence "1-persistent"). If the channel is busy, they wait until it becomes idle, then transmit immediately. This greediness is why collisions happen: two stations waiting for the same busy period both fire the instant the channel clears.

Non-persistent CSMA avoids this by waiting a random time before re-sensing, reducing collisions at the cost of higher idle time. P-persistent CSMA (used in IEEE 802.11) transmits with probability p each idle slot, deferring with probability 1−p. Classic 10 Mbps Ethernet chose 1-persistent because its collision-detection mechanism makes collisions cheap to recover from, unlike wireless where detection is impossible.

### Collision Detection and the 2τ Window

CSMA alone does not eliminate collisions; it only reduces them. Detection is an analog process: a transmitting NIC continuously compares what it is putting on the wire with what it reads back. A voltage anomaly (signal levels outside the single-sender envelope) indicates a collision.

The critical constraint: a station can only declare the channel collision-free once its signal has propagated to the farthest point and back with no interference. This takes at most 2τ, the round-trip propagation delay. For the longest allowed 10BASE5 path (2500 m, up to 4 repeaters), this works out to roughly 5 µsec one-way → 51.2 µsec round-trip at 10 Mbps (the standard sets slot time = 512 bit times = 51.2 µsec).

**Why 64 bytes is the minimum frame size:**

```
Minimum frame bits = slot time in bits = 512 bits = 64 bytes
```

If a frame finishes transmitting before its last bit has traveled 2τ round-trip, the station would stop monitoring the wire and never detect a late collision echo. The pad field (0–46 bytes) ensures frames shorter than 64 bytes are padded to exactly 64 bytes of data + header + FCS.

### The Jam Signal

When collision is detected, the transmitting station does not simply stop. It continues sending 32 bits of a deliberately invalid pattern (the jam signal). This ensures the collision is long enough to be detected by all stations still transmitting, not just the two that collided. After the jam, both stations stop.

The jam is not a valid frame; its CRC will fail. Receivers that see a partial frame before the jam discard it as a runt or collision fragment.

### Binary Exponential Backoff Algorithm

After a collision, time is divided into slots of 51.2 µsec each. The algorithm for station i after k consecutive collisions:

| Collision count k | Contention window | Draw from |
|---|---|---|
| 1 | 2 | {0, 1} |
| 2 | 4 | {0, 1, 2, 3} |
| 3 | 8 | {0, …, 7} |
| 4 | 16 | {0, …, 15} |
| … | … | … |
| 10 | 1024 | {0, …, 1023} |
| 11–15 | 1024 (capped) | {0, …, 1023} |
| 16 | — | **Abort, report to upper layer** |

The general rule: after the i-th collision (i ≤ 10), pick r uniformly from [0, 2^i − 1], wait r × 51.2 µsec, then retransmit. After 10 collisions the window freezes at 1023 rather than continuing to double, preventing the mean wait from becoming unboundedly large. After 16 total failures the controller signals an error to the operating system; TCP will retransmit at a higher layer.

**Worked numeric example:**

Two stations A and B both have frames ready. Channel goes idle:
- Both transmit immediately (1-persistent). Collision after ~2 µsec.
- Jam sent, both stop.
- k=1: A draws 1, B draws 0. B waits 0 slots → retransmits immediately. A waits 1 slot (51.2 µsec). B wins.
- If both drew 0 again: k=2, window [0,3]. A draws 2, B draws 0. B wins immediately, A waits 102.4 µsec.

Probability of re-collision at k=1: 2/4 = 50% (both pick same value from {0,1}).
Probability of re-collision at k=2: 4/16 = 25%.
Probability of re-collision at k=3: 8/64 ≈ 12.5%.

See `assets/10-csmacd-binary-exponential-backoff.svg` for a timing diagram of this scenario.

### Ethernet Frame Format (IEEE 802.3)

```
 Bytes:  8      6      6      2         46-1500   0-46    4
┌────────┬──────┬──────┬──────┬─────────┬─────────┬──────┐
│Preamble│ DA   │  SA  │Type/ │  Data   │   Pad   │ FCS  │
│ + SFD  │      │      │Length│         │         │(CRC32│
└────────┴──────┴──────┴──────┴─────────┴─────────┴──────┘
```

- **Preamble** (8 bytes): 7 bytes of `10101010` + 1 Start Frame Delimiter byte `10101011`. The alternating pattern produces a 10 MHz square wave in Manchester encoding for receiver clock synchronization. The two trailing `1` bits of the SFD signal "data starts next."
- **Destination Address** (6 bytes): 48-bit MAC. Bit 0 of the first byte = 0 → unicast, 1 → multicast. All-ones = broadcast (FF:FF:FF:FF:FF:FF).
- **Source Address** (6 bytes): 48-bit MAC. First 3 bytes = OUI (Organizationally Unique Identifier), assigned by IEEE. Last 3 bytes = NIC-specific, programmed at manufacture.
- **Type / Length** (2 bytes): Values > 0x0600 (1536) are EtherType codes (DIX Ethernet; e.g., 0x0800 = IPv4, 0x0806 = ARP, 0x86DD = IPv6). Values ≤ 0x0600 are IEEE 802.3 Length fields. This disambiguation was standardized in 1997; prior to that, DIX and 802.3 were incompatible on this field.
- **Data** (46–1500 bytes): Payload. Minimum 46 bytes ensures total frame ≥ 64 bytes.
- **Pad** (0–46 bytes): Zero-fill when data < 46 bytes to reach the 64-byte minimum.
- **FCS** (4 bytes): CRC-32 computed over DA + SA + Type/Length + Data + Pad using the polynomial x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10 + x^8 + x^7 + x^5 + x^4 + x^2 + x + 1 (0x04C11DB7). This is the same polynomial used in PPP, ADSL, USB, and many other standards.

The Preamble is not included in the FCS calculation and is stripped by the receiver before passing the frame upward.

### CSMA/CD State Machine

A transmitting station cycles through three states (from the IEEE 802.3 model):

```
  IDLE ──sense idle──► TRANSMIT ──collision──► CONTENTION
    ▲                      │                      │
    └──── success ◄────────┘                      │
    ◄──── backoff expired ◄───────────────────────┘
```

1. **IDLE**: Channel quiet. Station waits for a frame to send.
2. **TRANSMIT**: Sending bits. Simultaneously reading back signal. If read-back matches transmitted: continue. If mismatch: collision.
3. **CONTENTION**: Emit jam (32 bits). Increment collision counter. If counter = 16: abort. Otherwise compute backoff r, wait r × 51.2 µsec. Re-enter TRANSMIT.

The `code/main.py` simulation models this state machine for N concurrent stations and collects per-station collision histograms.

### Channel Efficiency Analysis

Under constant heavy load with k stations always ready to send, Metcalfe and Boggs (1976) derived:

```
Channel efficiency η = P / (P + 2τ/A)
```

where P = frame transmission time, τ = one-way propagation delay, and A = probability that exactly one station acquires the channel in a slot = kp(1−p)^(k−1), maximized at p = 1/k giving A → 1/e as k → ∞.

Substituting P = F/B (F = frame size in bits, B = bandwidth):

```
η = 1 / (1 + 2BLe / cF)
```

where L = cable length (m), c = propagation speed (~2×10^8 m/s in coax), e ≈ 2.718.

**Numerical examples at 10 Mbps, L = 2500 m:**

| Frame size | 2BLe/cF | η |
|---|---|---|
| 64 bytes (512 bits) | 2×10^7×2500×2.718 / (2×10^8×512) ≈ 1.66 | ~38% |
| 512 bytes (4096 bits) | ~0.21 | ~83% |
| 1024 bytes (8192 bits) | ~0.10 | ~91% |
| 1500 bytes (12000 bits) | ~0.07 | ~93% |

The BL product is the fundamental efficiency enemy. Doubling bandwidth (100 Mbps) or doubling cable length halves efficiency for the same frame size. This is why Gigabit Ethernet over shared coax is impractical — the minimum frame size would need to be 512 bytes to maintain useful efficiency, and Fast/Gigabit Ethernet moved to full-duplex switched architectures instead.

### CSMA/CD in Modern Ethernet — Why It Disappeared

Modern Ethernet (Fast Ethernet 100BASE-TX, Gigabit 1000BASE-T, 10G, and beyond) uses point-to-point full-duplex links between each NIC and a switch port. In full-duplex mode:

- Each link is a separate collision domain with exactly two endpoints.
- Simultaneous TX and RX occur on separate wire pairs; no electrical collision is possible.
- The CSMA/CD algorithm is bypassed entirely; flow control uses PAUSE frames (IEEE 802.3x).

The IEEE 802.3 standard removed the CSMA/CD requirement from Gigabit and higher speed standards. Switches maintain a forwarding table (MAC address → port mapping) and perform store-and-forward or cut-through switching with no shared medium.

Half-duplex Gigabit Ethernet (1000BASE-T shared hub) was technically specified and required a minimum frame size of 512 bytes to maintain 2τ coverage, but it was never commercially significant. The market went directly to full-duplex switches.

### Interframe Gap (IFG)

Between consecutive frames, stations must observe a minimum Interframe Gap of 96 bit times (9.6 µsec at 10 Mbps). This pause:
- Allows receiver logic to reset between frames.
- Gives lower-priority stations a window to inject frames (fairness).
- Is not enforced by a collision mechanism — it relies on NIC compliance.

## Build It

The simulation in `code/main.py` implements the CSMA/CD BEB algorithm for a configurable number of stations on a shared medium:

1. Run `python3 code/main.py` — no dependencies needed.
2. The simulation models N stations each with one frame to transmit. They contend on a slotted medium (slot = 51.2 µsec) using 1-persistent sensing and BEB.
3. Output includes: total slot count consumed, per-station collision count, and transmission success round.
4. A second scenario sweeps N from 2 to 32 and prints mean collision rounds and mean slots-to-success to show how BEB scales.
5. To model a misbehaving NIC (no backoff), set `fair=False` for one station and observe how it starves others.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Run 2-station simulation | Output shows 0–2 collision rounds typically | Both stations succeed within 3 rounds for N=2 with high probability |
| Run 16-station simulation | Collision histogram shows BEB distribution | Mean collision rounds ~3–5; no station exceeds 10 before success |
| Identify abort condition | Trigger by setting max_collisions=16 in one run | Station hits 16 consecutive collisions, prints "frame dropped" |
| Measure efficiency vs N | Plot or read slots-per-frame from sweep output | Efficiency degrades gracefully; not catastrophic collapse until N > 20 |
| Compare fair vs unfair NIC | Set one station to always pick r=0 | Unfair station dominates; others show starvation pattern in histogram |

## Ship It

Running `python3 code/main.py` writes a summary to stdout. Save it with:

```
python3 code/main.py > outputs/simulation-results.txt
```

The `outputs/` directory already exists. The output file captures the collision histogram, mean backoff rounds per station count, and the abort scenario trace, suitable for submission or lab report inclusion.

## Exercises

1. **Minimum frame size derivation**: A new 100 Mbps Ethernet (Fast Ethernet, 100BASE-TX) uses the same 2500 m maximum segment length but reduces slot time to 512 bit times at 100 Mbps. Calculate the slot time in µsec. Now explain why 100BASE-TX was standardized with a *maximum* cable length of 100 m per segment rather than 2500 m.

2. **Backoff window probability**: Three stations A, B, C all collide simultaneously on the first attempt (k=1). Window = {0,1}. List all 8 equally-likely outcomes (each station picks 0 or 1). In how many outcomes is exactly one station's draw unique (no ties)? What is the probability of resolving the collision in the next slot?

3. **BEB cap analysis**: At k=10 the window is frozen at [0, 1023]. Suppose 50 stations all collide at once. Estimate the probability that the collision is resolved in the next round (exactly one station picks each unique slot). Compare to what the probability would be if the window continued doubling to [0, 2^10 − 1 = 1023] vs [0, 2^50 − 1]. Why does capping at 1023 make sense despite 50 stations?

4. **Jam signal necessity**: Station A detects a collision after transmitting 200 bits. It stops immediately without sending a jam. Station B is 2499 m away and has only received 190 bits of A's frame. Describe what B observes. Does B detect a collision? What does B do with the 190-bit fragment?

5. **Efficiency calculation**: You have a 10 Mbps 10BASE5 segment, L=2500 m, c=2×10^8 m/s. A backup application sends 1500-byte frames in bursts. Using η = 1/(1 + 2BLe/cF), compute efficiency. Now model the same workload on a 100 Mbps switched network (full-duplex, no CSMA/CD). What is the theoretical efficiency? What changed architecturally?

6. **Misbehaving NIC forensics**: Your packet capture shows one MAC address (AA:BB:CC:DD:EE:FF) always retransmitting exactly 0 slots after a collision (it never backs off). Other stations show increasing collision counts. Describe: (a) what the collision counter on other NICs will show over time, (b) how you would confirm this is the culprit from a capture, and (c) what the fix is.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| CSMA/CD | "listen before transmit" | Carrier Sense Multiple Access with Collision Detection: sense channel, transmit if idle, abort and backoff if collision detected during transmission |
| 1-persistent | "greedy CSMA" | Transmit with probability 1 as soon as channel goes idle; maximizes throughput at low load but increases collision rate compared to p-persistent |
| Slot time | "51.2 microseconds" | 512 bit times at 10 Mbps = worst-case 2τ round-trip propagation; the unit of BEB backoff; also the minimum time to detect a collision anywhere on the segment |
| Binary exponential backoff | "BEB" or "exponential backoff" | After k-th collision, draw random integer from [0, 2^k − 1] and wait that many slot times; window doubles each round to spread retransmissions |
| Jam signal | "collision jam" | 32 bits of deliberate invalid pattern sent after collision detection to ensure all colliding stations see the event; not a valid frame fragment |
| Contention window | "backoff window" | [0, 2^k − 1] for k ≤ 10; frozen at [0, 1023] for k > 10; controls range of random backoff draw |
| Interframe Gap (IFG) | "idle time between frames" | Mandatory 96-bit-time (9.6 µsec at 10 Mbps) gap between back-to-back frames; gives other stations a chance to transmit |
| Runt frame | "short frame" | Frame shorter than 64 bytes; result of a collision fragment or improperly padded transmission; discarded by receiver |
| Preamble + SFD | "sync bytes" | 7 bytes 0xAA + 1 byte 0xAB; produces 10 MHz square wave in Manchester encoding for clock recovery; SFD last two bits 11 signal start of data |
| CRC-32 / FCS | "checksum" | 32-bit Frame Check Sequence computed over DA+SA+Type/Length+Data+Pad using polynomial 0x04C11DB7; detects but does not correct errors; frame dropped on failure |
| OUI | "vendor prefix" | Organizationally Unique Identifier: first 3 bytes of a 48-bit MAC address, assigned by IEEE to manufacturers; identifies the NIC vendor |
| BL product | "bandwidth-distance product" | B × L in the efficiency formula; increasing either degrades CSMA/CD efficiency; the fundamental reason CSMA/CD is impractical at high speeds or long distances |
| Full-duplex | "no CSMA/CD needed" | Simultaneous TX and RX on separate wire pairs; point-to-point switch links; collisions impossible; CSMA/CD bypassed entirely |

## Further Reading

- **IEEE 802.3-2022** — The definitive Ethernet standard; Clause 4 covers CSMA/CD MAC algorithm; Clause 3 defines the frame format. Available at ieee.org.
- **Metcalfe, R.M. and Boggs, D.R. (1976).** "Ethernet: Distributed Packet Switching for Local Computer Networks." *Communications of the ACM*, 19(7):395–404. Original paper deriving the efficiency formula and justifying BEB.
- **Tanenbaum, A.S. and Wetherall, D. (2011).** *Computer Networks*, 5th ed. Section 4.3 (Classic Ethernet MAC Sublayer Protocol, pp. 279–290) covers CSMA/CD, BEB, the frame format, and efficiency analysis — the primary source for this lesson.
- **RFC 894** — "A Standard for the Transmission of IP Datagrams over Ethernet Networks." Specifies use of EtherType 0x0800 for IPv4 over DIX Ethernet.
- **RFC 1042** — "A Standard for the Transmission of IP Datagrams over IEEE 802 Networks." Covers the LLC/SNAP encapsulation needed when using IEEE 802.3 Length framing.
- **IEEE 802.3x-1997** — Full-duplex and PAUSE frame specification; the amendment that effectively ended CSMA/CD as a production requirement for switched Ethernet.
- **Spurgeon, C.E. (2000).** *Ethernet: The Definitive Guide.* O'Reilly. Chapter 5 covers classic CSMA/CD operation with practical troubleshooting guidance.
