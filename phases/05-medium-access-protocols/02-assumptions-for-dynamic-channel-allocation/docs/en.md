# Assumptions for Dynamic Channel Allocation

> Every multiple-access protocol you will study — ALOHA, slotted ALOHA, CSMA, CSMA/CD, MACA, the IEEE 802.3 and 802.11 MACs — rests on five modeling assumptions that Tanenbaum lays out before any protocol appears: **Independent Traffic** (N stations, Poisson arrivals at rate λ, a station blocks after generating a frame), **Single Channel** (one shared medium, no side channel), **Observable Collisions** (simultaneous transmissions garble each other and every station can detect it), **Continuous or Slotted Time** (a slot holds 0, 1, or >1 frames — idle, success, or collision), and **Carrier Sense or No Carrier Sense** (can a station tell the channel is busy before transmitting?). The last three are engineering switches: 802.3 wired Ethernet picks carrier-sense + collision-detection; 802.11 Wi-Fi cannot reliably sense (hidden terminals) so it infers collisions from missing ACKs. The static-allocation baseline these protocols beat is the M/M/1 result T = 1/(μC − λ): splitting one C-bps channel into N FDM subchannels makes mean delay N times worse, which is why bursty LAN traffic demands dynamic allocation. This lesson turns those five assumptions into a runnable contention simulator so you can watch S = Ge^(−2G) collapse past the load knee.

**Type:** Build
**Languages:** Python (stdlib), models
**Prerequisites:** Phase 5 · 01 (the channel allocation problem), basic probability (Poisson process), Phase 1 framing concepts
**Time:** ~75 minutes

## Learning Objectives

- State all five assumptions (Independent Traffic, Single Channel, Observable Collisions, Continuous/Slotted Time, Carrier Sense) and classify each as either *structural* (always assumed) or an *engineering switch* (set per protocol).
- Derive why static FDM/TDM division gives mean delay T_N = N·T from the M/M/1 formula, and explain why this fails for bursty traffic.
- Map each assumption to a concrete real protocol decision: 802.3 (carrier sense + collision detect), 802.11 (no reliable carrier sense, ACK-inferred collisions), classic ALOHA (no carrier sense, no slots).
- Run a Poisson contention simulator and reproduce the S = Ge^(−2G) (pure) and S = Ge^(−G) (slotted) throughput curves, identifying the load G where throughput peaks.
- Predict how relaxing one assumption (e.g., adding carrier sense) changes collision probability and channel utilization.

## The Problem

You are sizing a shared-medium access scheme — a cable-modem upstream, a Wi-Fi cell, an industrial radio bus — and someone asks "how many stations can this hold before it falls over?" You cannot answer that without a model, and you cannot pick a model without committing to assumptions. Choose wrong and your capacity plan is fiction: assume carrier sense on a channel with hidden terminals and your collision estimate is wildly optimistic; assume Poisson arrivals on traffic that is actually bursty and your queueing delay is off by an order of magnitude.

The trap is that these assumptions are usually *implicit*. A vendor datasheet quotes "54 Mbps" for 802.11g; the real sustained MAC throughput is roughly half that, because the model behind the headline number quietly assumed no contention. The five assumptions in this lesson are the contract you must make explicit before any throughput number means anything.

## The Concept

Before introducing a single protocol, the standard model fixes five assumptions. Two are structural (you cannot remove them without changing the problem), and three are switches you set per protocol.

### Assumption 1 — Independent Traffic (structural)

There are **N independent stations**. Each generates new frames as a Poisson process: the expected number of frames in an interval Δt is **λΔt**, with λ a constant arrival rate. Critically, **once a station generates a frame it blocks** — it does nothing else until that frame is successfully transmitted. This single-buffer assumption is what makes the math tractable.

The honest caveat: real network traffic is **not** Poisson. It is self-similar and bursty across many time scales (Leland et al. 1994; Paxson & Floyd 1995). Poisson models survive anyway because they are analytically tractable and give the right *qualitative* shape of performance — where throughput peaks, how delay grows near saturation — even when absolute numbers drift.

### Assumption 2 — Single Channel (structural)

One channel carries **all** communication. Every station can transmit on it and receive from it. There is no out-of-band signaling — no way to "raise your hand" and ask permission. This is the heart of the model: coordination must happen *through the same contended channel* you are trying to allocate. Stations may have different roles (priorities, a master), but capability is symmetric.

### Assumption 3 — Observable Collisions (engineering switch)

If two frames transmit simultaneously they **overlap in time and garble** — a *collision*. The assumption has two parts: collisions happen, and **every station can detect them**. A collided frame must be retransmitted; no errors other than collisions occur.

How detection actually works splits by medium:

| Medium | Collision detection method | Real protocol |
|---|---|---|
| Wired (coax/twisted pair) | Hardware senses voltage/energy while transmitting; aborts early | IEEE 802.3 CSMA/CD |
| Wireless | Cannot listen while transmitting; collision **inferred** from a missing ACK after a timeout | IEEE 802.11 CSMA/CA |
| Central hub (cable modem) | Headend reports success/failure back downstream | DOCSIS upstream |

The wired case lets a station truncate a doomed frame (a 32-bit jam signal in 802.3) to avoid wasting the channel. Wireless cannot, so it pays the full frame time on every collision — a key reason Wi-Fi adds collision *avoidance* rather than detection.

### Assumption 4 — Continuous or Slotted Time (engineering switch)

Either time is **continuous** (a frame may start at any instant) or it is **slotted** into discrete intervals where transmissions begin only at slot boundaries. A slot then holds exactly one of three outcomes:

| Slot contents | Outcome | Channel state |
|---|---|---|
| 0 frames | Idle | wasted slot |
| 1 frame | Success | useful work |
| ≥2 frames | Collision | wasted slot + retransmits |

Slotting halves the *vulnerable period* of a frame. In pure (continuous) ALOHA a frame collides if any other frame starts within **two frame-times**; slotting cuts that to **one frame-time**, which is exactly why peak throughput doubles from **18.4%** (S = Ge^(−2G), max at G = 0.5) to **36.8%** (S = Ge^(−G), max at G = 1). The cost: stations must synchronize to a common clock. See `assets/assumptions-for-dynamic-channel-allocation.svg` for the slot-outcome timing diagram.

### Assumption 5 — Carrier Sense or No Carrier Sense (engineering switch)

**With carrier sense**, a station can tell the channel is busy *before* transmitting and will defer. **Without it**, stations transmit blindly and only learn the outcome afterward.

Carrier sense is cheap on wired LANs (everyone hears everyone) and is why CSMA dramatically outperforms ALOHA. It fails on wireless when stations are out of radio range of each other — the **hidden terminal problem**: A and C both reach B but cannot hear each other, so carrier sense at A says "idle" even while C is transmitting to B. The word "carrier" here means a *signal on the channel*, unrelated to telephone "common carriers."

### The baseline these assumptions let you beat

Why bother with dynamic allocation at all? Because static division is provably worse for bursty load. For a single channel of capacity C bps with Poisson frame arrivals (rate λ) and exponential frame lengths (mean 1/μ bits), the M/M/1 mean delay is:

```
T = 1 / (μC − λ)
```

Worked example: C = 100 Mbps, mean frame = 10,000 bits (so μC = 10,000 frames/s), λ = 5000 frames/s → **T = 200 µs**. Naively "10,000 bits ÷ 100 Mbps = 100 µs" is wrong because it ignores queueing/contention.

Now split that one channel into N FDM subchannels of C/N each, with arrivals λ/N on each:

```
T_N = 1 / (μ(C/N) − λ/N) = N / (μC − λ) = N · T
```

**Mean delay gets N times worse.** Replacing one 100-Mbps channel with ten static 10-Mbps channels pushes delay from 200 µs to 2 ms. TDM has the same defect — an idle station's slot lies fallow. A bank lobby with one queue feeding many ATMs beats a separate queue per machine. This is the formal reason bursty LAN traffic needs *dynamic* allocation, and it is what `code/main.py` contrasts against contention throughput.

## Build It

`code/main.py` encodes the five assumptions as a discrete-event contention simulator. Work through it in this order:

1. Read the `Assumptions` dataclass — each of the five appears as an explicit, toggleable field (e.g., `slotted: bool`, `carrier_sense: bool`).
2. Run the **static-division** function to reproduce T = 200 µs and T_N = 2 ms for the worked example — this is the baseline.
3. Run the **pure-ALOHA** Monte Carlo simulation: generate Poisson offered load G, place frames on a continuous timeline, count a frame as successful only if nothing else starts within two frame-times.
4. Flip `slotted=True` and rerun — confirm the vulnerable period shrinks to one frame-time and peak throughput roughly doubles.
5. Compare the simulated throughput against the closed-form S = Ge^(−2G) and S = Ge^(−G) curves printed in the same table.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify the five assumptions | The `Assumptions` dataclass fields and their per-protocol values | You can say which two are structural and which three you set per protocol |
| Reproduce the static-division penalty | Printed T and T_N for the 100-Mbps example | Output shows 200 µs vs 2.0 ms (10× the N factor) |
| Reproduce the ALOHA throughput knee | Simulated S vs offered load G table | Pure peaks near S≈0.184 at G≈0.5; slotted near S≈0.368 at G≈1.0 |
| Predict a protocol's assumption set | Mapping 802.3 / 802.11 / ALOHA onto the five switches | 802.3 = sense+detect+wired; 802.11 = no reliable sense, ACK-inferred collisions |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **assumption-mapping table** that, given a real medium (cable upstream, Wi-Fi cell, LoRa bus), fills in all five assumptions and predicts which MAC family fits.
- Or the throughput plot data (CSV of G vs simulated S vs analytic S) exported from `code/main.py`, annotated with where each real protocol operates.

Start from `outputs/prompt-assumptions-for-dynamic-channel-allocation.md`.

## Exercises

1. A cable-modem upstream forces all stations to talk only to the headend, never to each other. Which of the five assumptions does this break or weaken, and what does it imply for carrier sense?
2. Using T = 1/(μC − λ), compute the mean delay for C = 1 Gbps, mean frame 12,000 bits, λ = 60,000 frames/s. Then compute T_N if you statically split it into 8 subchannels. Show both numbers.
3. Run `code/main.py` in pure mode and record the offered load G at which simulated throughput peaks. Now run slotted mode. Explain the factor-of-two change purely in terms of the vulnerable period.
4. 802.11 cannot detect collisions during transmission. Trace which assumption this violates and explain how the protocol substitutes a missing-ACK timeout for direct detection.
5. The Independent-Traffic assumption says a station blocks after generating one frame. Describe a real workload (e.g., a busy video sensor) where this is false, and predict whether the model over- or under-estimates delay.
6. Construct a hidden-terminal scenario (stations A, B, C) where carrier sense returns "idle" but a collision still occurs at the receiver. Which assumption silently fails?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Offered load G | "How busy the channel is" | New + retransmitted frames per frame-time (Poisson mean); G ≥ N because collisions add retransmits |
| Throughput S | "Speed of the link" | Fraction of frame-times carrying a successful frame: S = G·P₀, where P₀ is the no-collision probability |
| Vulnerable period | "When collisions happen" | The window in which any competing transmission destroys this frame — 2 frame-times (pure), 1 (slotted) |
| Carrier sense | "Listening before talking" | Detecting an existing signal on the channel before transmitting; useless against hidden terminals |
| Collision detection | "Knowing a crash happened" | Sensing overlap *while transmitting* (wired) vs *inferring it from a missing ACK* (wireless) |
| Slot | "A time unit" | A discrete interval holding exactly 0 (idle), 1 (success), or ≥2 (collision) frames |
| Poisson arrivals | "Random traffic" | Memoryless arrivals at constant mean rate λ — tractable but a poor fit for real bursty traffic |
| M/M/1 delay | "Queueing math" | Mean delay T = 1/(μC − λ) for one channel; static N-way division multiplies it by N |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (6th ed.), §4.1.2 "Assumptions for Dynamic Channel Allocation" and §4.2 (ALOHA, CSMA).
- N. Abramson, "The ALOHA System," *AFIPS Conf. Proc.* 37 (1970) — the origin of contention-based access.
- IEEE Std 802.3 — CSMA/CD: carrier-sense + collision-detect on wired Ethernet.
- IEEE Std 802.11 — CSMA/CA: the no-reliable-carrier-sense, ACK-inferred-collision wireless MAC; RTS/CTS for hidden terminals.
- Leland, Taqqu, Willinger & Wilson, "On the Self-Similar Nature of Ethernet Traffic," *IEEE/ACM ToN* 2(1), 1994 — why the Poisson assumption is imperfect.
- Paxson & Floyd, "Wide-Area Traffic: The Failure of Poisson Modeling," *IEEE/ACM ToN* 3(3), 1995.
