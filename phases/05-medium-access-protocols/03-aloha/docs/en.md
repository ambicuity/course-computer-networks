# ALOHA

> ALOHA is the first random-access MAC protocol: stations transmit whenever they have a frame, accept that collisions will happen, detect them, and retransmit after a random backoff. Norman Abramson built it at the University of Hawaii (~1971) over short-range UHF radio, with terminals sharing one upstream frequency to a hub in Honolulu that rebroadcast every frame so senders could confirm delivery. Pure ALOHA has a **vulnerable period of two frame times** and tops out at **S = G·e^(-2G)**, a maximum throughput of **1/(2e) ≈ 0.184** at offered load G = 0.5. Roberts (1972) added slot synchronization to create **slotted ALOHA**, halving the vulnerable period to one frame time: **S = G·e^(-G)**, peaking at **1/e ≈ 0.368** at G = 1. The fixed-size frame and random-backoff design are the direct ancestors of Ethernet's CSMA/CD, DOCSIS cable-modem upstream contention, and slotted-ALOHA RFID tag arbitration (ISO 18000-6C). The classic failure mode is congestion collapse: as offered load G rises past the peak, collisions grow exponentially, retransmissions inflate G further, and throughput crashes toward zero.

**Type:** Build
**Languages:** Python, models
**Prerequisites:** Phase 5 lessons 01–02 (channel allocation, the multiple-access problem); basic probability (Poisson)
**Time:** ~90 minutes

## Learning Objectives

- Derive and explain why pure ALOHA's vulnerable period is **2 frame times** and slotted ALOHA's is **1**, and connect that to the throughput formulas S = G·e^(-2G) and S = G·e^(-G).
- Compute peak throughput and the operating point for both variants (G = 0.5 → 18.4%; G = 1 → 36.8%) and predict the slot occupancy split (37% empty / 37% success / 26% collision at G = 1).
- Simulate a contention channel in `code/main.py` and show measured success rates converging on the analytic curve across a sweep of offered loads.
- Identify congestion collapse from a throughput-vs-load trace and explain why a random (not fixed) retransmission delay is mandatory.
- Map ALOHA's mechanics onto a modern descendant (DOCSIS upstream, RFID tag inventory, or Ethernet backoff) and name what each system added.

## The Problem

You are bringing up the upstream path of a cable network segment. Many cable modems share one RF upstream channel back to the CMTS (the head-end). There is no wire-by-wire isolation: when two modems request bandwidth in the same contention region, their bursts collide and both are lost. At light load everything works; at a busy hour, customers report that pages "hang then load," speed tests stall, and the CMTS shows a climbing count of collided ranging/request slots while *goodput falls*.

That last detail — load goes up, useful throughput goes *down* — is the signature of an uncontrolled contention channel. It is not a wiring fault, not a routing problem, and not an application bug. It is the ALOHA throughput curve in the wild. To reason about it you need the model Abramson published 50 years earlier: how often a random-access transmission survives, where the peak is, and why pushing past the peak makes things worse, not better.

## The Concept

### The setup: one shared channel, uncoordinated senders

ALOHA assumes an (effectively infinite) population of stations that each occasionally produce a fixed-length frame. There is no coordination before transmitting and — in pure ALOHA — no listening to the channel first. A station sends, then learns whether it succeeded. In Abramson's original system the central hub **rebroadcast every received frame** on a separate downstream frequency; a sender heard its own frame come back to confirm success. If the echo was garbled or absent, the frame collided and must be resent. Wired LANs later learned the result faster by listening *while* transmitting (collision detection), but the ALOHA confirmation loop is the conceptual root.

Frames are deliberately **fixed length**. Variable-length frames lower throughput because they widen the window in which a collision can occur; a uniform frame time is the cleanest analysis and the best performer.

### The vulnerable period (the heart of it)

Let the **frame time** be the time to transmit one fixed-length frame (frame bits ÷ bit rate). Consider a "shaded" test frame that starts at time t₀ and runs to t₀ + 1 frame time.

- Any other frame that *started* between **t₀ − 1** and **t₀** is still on the air when ours begins → its tail collides with our head.
- Any other frame that starts between **t₀** and **t₀ + 1** → its head collides with our tail.

So our frame is destroyed if *any* other transmission begins anywhere in a window **2 frame times wide**. That is the vulnerable period. The `assets/aloha.svg` diagram draws this window explicitly: the test frame plus the two-frame-time shaded danger zone around it, and how slotting collapses it to one.

Note the brutal fact: a collision destroys the frame *completely*. The checksum (e.g., a CRC-32) cannot and should not distinguish a one-bit overlap from total overlap — a bad FCS is a bad FCS, and the whole frame is retransmitted. "Bad is bad."

### Throughput of pure ALOHA

Model the combined stream of new frames *plus* retransmissions as Poisson with mean **G** frames per frame time. New frames alone have mean N; at low load G ≈ N, at high load G > N because collisions breed retransmissions.

The probability that *k* frames are generated in a window of mean λ is the Poisson term `λ^k · e^(−λ) / k!`. Our frame succeeds only if **zero** other frames appear in the 2-frame-time vulnerable window, where the mean is 2G:

```
P(success) = e^(−2G)
S = G · P(success) = G · e^(−2G)
```

Differentiate: the maximum is at **G = 0.5**, giving **S = 1/(2e) ≈ 0.184**. Even with perfect luck you use only ~18% of the channel.

### Throughput of slotted ALOHA

Roberts' insight (1972): force every frame to begin only at the start of a fixed time **slot**, one frame time wide. A reference station emits a "pip" at each slot boundary so everyone agrees on slot edges. Now a frame can only collide with another frame *in the same slot* — the "started just before us" half of the window disappears. The vulnerable period drops from 2 to **1** frame time:

```
P(success) = e^(−G)
S = G · e^(−G)
```

Maximum at **G = 1**, giving **S = 1/e ≈ 0.368** — exactly double pure ALOHA. At that operating point the slot outcomes split as:

| Slot outcome | Probability at G = 1 | Formula |
|---|---|---|
| Empty (no sender) | 0.368 | e^(−G) |
| Success (exactly one) | 0.368 | G·e^(−G) |
| Collision (two or more) | 0.264 | 1 − e^(−G) − G·e^(−G) |

So even the *best* slotted ALOHA operating point wastes ~63% of slots (37% idle + 26% collided).

### Retransmissions explode with load

The probability a frame needs exactly *k* attempts (k−1 collisions, then success) is `e^(−G)·(1 − e^(−G))^(k−1)`. The expected number of transmissions per successfully delivered frame works out to **E = e^G**. Because E grows *exponentially* in G, a small rise in offered load drastically multiplies retransmissions. This is the math behind congestion collapse: push G past the peak and each new attempt makes the channel worse for everyone.

This is also why the backoff delay **must be random**. If two stations collided and both waited a *fixed* interval, they would retransmit in lockstep and collide forever. A random wait decorrelates them. `code/main.py` models exactly this: collided stations reschedule to a random future slot/time.

### Why a uniform frame size, and why "listen first" is missing

Pure ALOHA does not sense the channel before sending, so a frame's fate is sealed before its first bit even goes out. The whole CSMA family (Phase 5, next lesson) fixes exactly this by listening for a carrier first, which is why LANs beat 1/e. ALOHA is the *baseline* every later MAC is measured against.

### Comparison table

| Property | Pure ALOHA | Slotted ALOHA |
|---|---|---|
| Time | Continuous | Discrete slots (1 frame each) |
| Send when ready? | Yes, immediately | Only at next slot boundary |
| Vulnerable period | 2 frame times | 1 frame time |
| Throughput formula | S = G·e^(−2G) | S = G·e^(−G) |
| Peak throughput | 1/(2e) ≈ 18.4% | 1/e ≈ 36.8% |
| Peak at offered load | G = 0.5 | G = 1.0 |
| Needs synchronization | No | Yes (slot clock) |
| Year / author | ~1971, Abramson | 1972, Roberts |

## Build It

1. Write the one-paragraph mechanism summary in your own words: shared channel, transmit-on-demand, collision, random retransmission, confirmation echo.
2. Sketch the vulnerable period for one test frame (use `assets/aloha.svg` as a reference) and mark which neighbors collide with the head vs. the tail.
3. Run `python3 code/main.py`. It (a) prints the analytic peak for both variants, (b) runs an event-driven Monte-Carlo channel across a sweep of offered loads G, and (c) prints measured throughput beside the theoretical S = G·e^(−G) and S = G·e^(−2G).
4. Confirm the simulated peaks land near 0.184 (pure, G≈0.5) and 0.368 (slotted, G≈1.0). Identify the load where measured throughput starts *falling* — that is your congestion-collapse onset.
5. Modify the backoff to a *fixed* delay and observe lockstep re-collisions; restore randomness and watch throughput recover. Record the before/after as your artifact evidence.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | Collision counters, fixed-size frames, random backoff timers, slot clock | You can explain this is MAC-sublayer contention, not routing or application loss |
| Explain normal behavior | Throughput sweep matching S = G·e^(−G) / G·e^(−2G) | Simulated points track the analytic curve within Monte-Carlo noise |
| Predict the peak | Operating point G and utilization | You state 18.4% @ G=0.5 (pure) and 36.8% @ G=1 (slotted) without looking it up |
| Diagnose congestion collapse | Throughput-vs-load trace turning downward past the peak | Rising load → falling goodput; E = e^G explains the retransmission blowup |
| Justify random backoff | Lockstep collision trace under fixed delay | You show fixed delay deadlocks two senders; randomness breaks the tie |

## Ship It

Create one artifact under `outputs/`:

- A throughput-vs-load plot (or printed table) annotated with both peaks and the collapse region.
- A one-page runbook: "Is my shared channel in ALOHA congestion collapse?" with the symptoms and the fix (admission control / reduce G / move to CSMA).
- A protocol/timing diagram of the vulnerable period for pure vs. slotted.
- The simulator output saved as evidence (`code/main.py` redirected to a file).

Start with [`outputs/prompt-aloha.md`](../outputs/prompt-aloha.md).

## Exercises

1. A slotted-ALOHA channel runs at offered load G = 1.5. Compute throughput S, the fraction of empty slots, and the fraction of collided slots. Is this above or below the peak? Which way should you move G?
2. Your pure-ALOHA link carries N = 0.3 new frames/frame-time of *useful* traffic but you measure G = 0.9 on the air. Explain the gap and estimate the average transmissions per delivered frame using E = e^G.
3. Run `code/main.py`, sweep G from 0.1 to 3.0, and report the G where measured slotted throughput first drops below 0.30. Compare to the analytic crossing of S = G·e^(−G) = 0.30.
4. RFID inventory: a reader must read 200 tags using slotted ALOHA with one frame per slot. Roughly how many slots will it take if the reader sizes the frame so G ≈ 1? Why is "one tag per slot at G = 1" only 37% efficient, and what does ISO 18000-6C add to do better?
5. Change `code/main.py` so collided stations use a *fixed* 1-slot backoff. Describe the trace and explain, using the lockstep argument, why throughput collapses.
6. Argue from the formulas why slotted ALOHA needs a slot clock but pure ALOHA does not — and what new failure mode (clock skew) slotting introduces.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Pure ALOHA | "Send whenever, hope it works" | Continuous-time random access; vulnerable period 2 frame times; peak 1/(2e) ≈ 0.184 at G = 0.5 |
| Slotted ALOHA | "ALOHA but with slots" | Frames start only at slot boundaries; vulnerable period 1 frame time; peak 1/e ≈ 0.368 at G = 1 |
| Frame time | "How long a packet is" | Frame length ÷ bit rate — the time unit the whole analysis is denominated in |
| Offered load G | "The traffic" | Mean Poisson rate of *all* attempts (new + retransmissions) per frame time; G ≥ N |
| Throughput S | "The speed" | Fraction of frame times carrying a *successful* frame: S = G·P(success) |
| Vulnerable period | "The danger window" | Interval in which any other transmission's start destroys our frame (2T pure, 1T slotted) |
| Congestion collapse | "It got slow" | Past the peak, rising G multiplies collisions (E = e^G), and goodput falls toward zero |
| Random backoff | "Wait and retry" | Mandatory *randomized* retransmission delay; fixed delay causes perpetual lockstep collisions |
| Contention system | "Shared medium" | Multiple users on one channel where simultaneous use causes conflicts |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., §4.2.1 (ALOHA) — the source for this lesson.
- N. Abramson, "THE ALOHA SYSTEM," *AFIPS FJCC*, vol. 37, 1970.
- L. G. Roberts, "ALOHA packet system with and without slots and capture," *Computer Communication Review*, vol. 5, no. 2, 1975 (slotted ALOHA).
- M. Schwartz and N. Abramson, "The Alohanet — surfing for wireless data," *IEEE Communications Magazine*, 2009.
- **IEEE 802.3** (Ethernet / CSMA-CD) — the wired descendant that adds carrier sense and collision detection.
- **DOCSIS 3.1/4.0** (CableLabs) — uses contention-based slotted-ALOHA-style request/ranging on the upstream.
- **ISO/IEC 18000-6C (EPC Gen2)** — dynamic framed slotted ALOHA for RFID tag inventory.
