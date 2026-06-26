# Static Channel Allocation

> Static channel allocation carves a single shared link of capacity **C** bps into **N** fixed private subchannels using **FDM** (Frequency Division Multiplexing) or **TDM** (Time Division Multiplexing). Each user owns one slice forever, so there is zero contention — but the moment traffic becomes bursty (computer traffic routinely has peak-to-mean ratios near **1000:1**), the scheme collapses. An M/M/1 queueing analysis shows the mean frame delay rises from **T = 1/(μC − λ)** for one big shared channel to exactly **N·T** when you split it into N equal pieces. Concretely, a 100 Mbps channel with 10,000-bit frames arriving at 5000 frames/sec delays a frame **200 µs**; replace it with ten static 10 Mbps subchannels and that jumps to **2 ms** — 10× worse — while idle subchannels waste their bandwidth because no one else may borrow it. This lesson builds an M/M/1 simulator that reproduces equation (4-1), proving why FDM/TDM are a poor fit for LAN traffic and motivating the dynamic protocols (ALOHA, CSMA) that follow.

**Type:** Build
**Languages:** Python, models
**Prerequisites:** Phase 02 multiplexing (FDM/TDM/Sec. 2.5), basic probability, Phase 05 intro
**Time:** ~75 minutes

## Learning Objectives

- Derive and explain the M/M/1 delay formula **T = 1/(μC − λ)** and identify each term (C, λ, 1/µ, µC) in operational units.
- Show analytically and by simulation why splitting one channel into N static subchannels multiplies mean delay by exactly **N** (equation 4-1).
- Quantify spectrum/timeslot waste when fewer than N users are active and explain why an idle FDM band cannot be reclaimed.
- Distinguish FDM, TDM, and physical channel splitting as three forms of the *same* static-allocation failure under bursty load.
- Decide from a workload's user count, burstiness, and stability whether static allocation is appropriate or whether a dynamic MAC protocol is required.

## The Problem

You operate a 100 Mbps backbone segment shared by 10 departments. To "guarantee fairness," an engineer statically partitions it: every department gets a dedicated 10 Mbps slice via FDM-style channelization. On paper this looks clean — no collisions, no contention, predictable isolation.

In production it behaves terribly. The finance department's nightly batch saturates its 10 Mbps slice and runs for hours, while nine other 10 Mbps slices sit **99% idle** the entire night. Finance cannot borrow the idle capacity because the partition is rigid: their frames queue behind each other on a tenth of the link even though 90 Mbps is available right next door. Interactive users on other slices, meanwhile, see latency that is *worse* than before the "fix."

The symptom an engineer files is "the upgrade made latency worse and the link looks empty in the graphs." The root cause is structural: static allocation trades statistical multiplexing gain for guaranteed isolation, and for bursty data traffic that trade is a loss. This lesson makes the loss exact and measurable.

## The Concept

Static channel allocation predates packet switching. It comes from the telephone world, where a trunk carrying many simultaneous calls is chopped into fixed channels. It works beautifully there — and fails for data — and the math tells you precisely why.

### FDM, TDM, and physical splitting: one idea, three skins

Given a channel of capacity **C** and **N** users, static allocation assigns each user a permanent 1/N share:

| Scheme | What is divided | Each user gets | Real-world example |
|---|---|---|---|
| **FDM** | Frequency spectrum | A private frequency band of C/N bandwidth | FM radio stations, analog TV channels, FDD cellular |
| **TDM** | Time | Every Nth time slot, fixed and reserved | T1/E1 trunk channels, classic circuit switching |
| **Physical split** | The wire itself | One of N separate slower links | Ten 10 Mbps cables replacing one 100 Mbps cable |

All three share the fatal property: **a slice a user does not use lies fallow.** An empty FDM band radiates nothing useful; an unused TDM slot transmits idle bits; an empty physical link carries nothing. None of that capacity can be lent to a neighbor who is overloaded. See `assets/static-channel-allocation.svg` for the spectrum-vs-time view of FDM and TDM side by side.

### Why static allocation is a poor fit for data

Static allocation is *simple and efficient* under exactly one condition the textbook is explicit about: **a small, constant number of users, each with a steady or heavy load.** FM radio fits — the station count is fixed and each station broadcasts essentially continuously.

Computer traffic violates every clause. The number of active stations varies second to second. The load is **bursty**, with peak-to-mean ratios "often 1000:1." A station blasts a file transfer for 50 ms, then sits silent for seconds. Under these conditions:

- If **fewer than N** users want to transmit, a large chunk of the channel is wasted — and it cannot be reclaimed.
- If **more than N** users want to transmit, the surplus users are denied service entirely *even though* allocated-but-idle users are wasting their guaranteed share.

### The M/M/1 delay model

To make "poor performance" precise, model the shared channel as an **M/M/1 queue** (Poisson arrivals, exponential service times, one server):

- **C** = channel capacity in bps.
- **λ** = mean frame arrival rate, frames/sec.
- **1/µ** = mean frame length in bits, so **µ** has units of 1/bits.
- **µC** = service rate of the channel in frames/sec (capacity divided by mean frame size).

The standard M/M/1 result for mean time in system (queueing delay + transmission delay) is:

```
        1
T  =  -------
      µC − λ
```

The denominator **µC − λ** is the spare service rate. As λ approaches µC, the channel saturates and **T → ∞**. `code/main.py` implements this exact formula.

### Worked example — the 200 µs baseline

Plug in the textbook's numbers:

- C = 100 Mbps = 100,000,000 bps
- 1/µ = 10,000 bits  →  µ = 1/10,000 = 0.0001 per bit
- λ = 5000 frames/sec
- µC = 0.0001 × 100,000,000 = **10,000 frames/sec**

```
T = 1 / (10,000 − 5000) = 1 / 5000 = 200 µs
```

A naïve calculation — "how long to send a 10,000-bit frame at 100 Mbps?" — gives 10,000 / 100,000,000 = **100 µs**. That is wrong for a shared channel: it ignores the time a frame waits behind others. The queueing delay *doubles* the answer at this load. Contention is real even on a fast link.

### Splitting the channel: the N× penalty (equation 4-1)

Now statically divide the one channel into **N** independent subchannels, each of capacity **C/N**. By symmetry, each subchannel receives a fraction λ/N of the arrivals. Recompute T for one subchannel:

```
            1                    1                  N
T_N = ----------------- = --------------- = ---------- = N · T
      µ(C/N) − (λ/N)      (µC − λ)/N         µC − λ
```

**The mean delay of the statically divided channel is exactly N times worse** than feeding all frames into one big shared queue. Same total capacity, same total load, N× the delay — purely from forbidding sharing.

| Configuration | Per-channel capacity | Per-channel λ | Mean delay T |
|---|---|---|---|
| One shared channel | 100 Mbps | 5000 f/s | 200 µs |
| Split into N=2 | 50 Mbps | 2500 f/s | 400 µs |
| Split into N=10 (ten 10 Mbps links) | 10 Mbps | 500 f/s | **2 ms** |
| Split into N=20 | 5 Mbps | 250 f/s | 4 ms |

This is the same intuition as a bank lobby: one queue feeding all the ATM machines beats a separate queue per machine. A single shared server pool absorbs bursts; partitioned pools cannot.

### When static allocation is actually correct

It is not always wrong. Use static allocation when **all** of these hold: the user set is fixed and known in advance; each user has a near-constant, heavy load; isolation/guaranteed-rate matters more than average latency; and there is no carrier-sense or collision-detect capability to build a dynamic scheme on. Voice trunks, broadcast radio/TV, and rigid SLA-backed circuits qualify. General-purpose LAN/data traffic does not — which is why the next lessons turn to dynamic protocols.

## Build It

`code/main.py` turns the equations above into a runnable model.

1. Read the module docstring and the `mm1_delay(capacity_bps, arrival_rate, mean_frame_bits)` function — it is a direct transcription of `T = 1/(µC − λ)`.
2. Run `python3 main.py`. It prints the 200 µs baseline, then the N-way split table reproducing the 2 ms result for N=10.
3. Inspect `split_channel_delay(...)` and confirm it returns `N * baseline` — the analytic equation (4-1) and the recomputed-from-scratch value should match to floating-point precision.
4. Look at the `utilization_waste(...)` function: it reports how much capacity is stranded when only `active_users` of `N` allocated slices are busy.
5. Change `mean_frame_bits` or `arrival_rate` and watch the channel approach saturation (T → ∞ as λ → µC). Note the stability check that refuses λ ≥ µC.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute baseline delay | `mm1_delay()` output for C, λ, 1/µ | Returns 200 µs for the textbook inputs; matches hand calculation |
| Prove the N× penalty | Split table from `split_channel_delay()` | N=10 row shows exactly 2 ms = 10 × 200 µs |
| Quantify idle waste | `utilization_waste()` with active_users < N | Reports stranded Mbps that no busy user may borrow |
| Detect saturation | Run with λ near µC | Function raises/flags instability instead of returning a bogus negative delay |
| Justify a design choice | Workload description → recommendation | Static rejected for bursty/variable users; accepted for fixed heavy-load circuits |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **delay-vs-N chart** (CSV or plotted) showing mean delay climbing linearly with the number of static partitions.
- A **one-page decision runbook**: "Should this link be statically partitioned?" with the four-condition checklist from *When static allocation is actually correct*.
- A **capacity-waste calculator** wrapping `utilization_waste()` for capacity-planning reviews.

Start from `outputs/prompt-static-channel-allocation.md` and the `main.py` output captured to a file.

## Exercises

1. A campus has **8** research groups sharing one 1 Gbps link, each generating Poisson traffic of 12,000 frames/sec with 8000-bit frames. Compute the shared-channel mean delay, then the delay if the link is statically split 8 ways. State the multiplier and explain it without re-deriving the formula.
2. Your FM-style allocation has N=16 fixed bands but, on average, only 3 transmitters are ever active at once. Compute the fraction of spectrum wasted and explain why a 17th transmitter is rejected despite this waste.
3. Show that splitting via **TDM** (each user gets every Nth slot) gives the same N× delay penalty as FDM. Identify the one operational difference between an idle FDM band and an idle TDM slot.
4. A voice-trunk vendor argues static TDM channels are the right design for their product. List the workload properties that make them *correct* here, and the single property that, if it changed, would break the argument.
5. Using `mm1_delay()`, find the maximum arrival rate λ a 50 Mbps subchannel (10,000-bit frames) can sustain before mean delay exceeds 1 ms. Verify against µC.
6. Explain why the bank-lobby single-queue analogy is mathematically the *same* statement as equation (4-1), mapping ATMs↔subchannels and customers↔frames.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| FDM | "Splitting by frequency" | Permanently assigning each of N users a private C/N-wide frequency band; unused bands cannot be reclaimed |
| TDM | "Time slots" | Assigning each user every Nth fixed time slot; an unused slot transmits idle bits and is wasted |
| Static allocation | "Reserving bandwidth for fairness" | Rigid 1/N partition that eliminates contention but forbids statistical multiplexing, multiplying delay by N |
| M/M/1 queue | "Some math" | Poisson arrivals + exponential service + one server; the model giving T = 1/(µC − λ) |
| µC | "The bandwidth" | Service rate in *frames/sec* = capacity ÷ mean frame size, not raw bits/sec |
| Burstiness (1000:1) | "Spiky traffic" | Peak-to-mean ratio of data traffic that makes any fixed reservation mostly idle |
| Statistical multiplexing | "Sharing" | Letting any user temporarily use idle capacity; the gain static allocation throws away |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., **Section 4.1.1** (Static Channel Allocation) and **4.1.2** (assumptions for dynamic allocation).
- Tanenbaum, **Section 2.5** — FDM, TDM, and OFDM multiplexing fundamentals referenced by this section.
- Kleinrock, *Queueing Systems, Volume 1: Theory* (1975) — the M/M/1 derivation behind T = 1/(µC − λ).
- Leland, Taqqu, Willinger & Wilson, "On the Self-Similar Nature of Ethernet Traffic," *IEEE/ACM ToN*, 1994 — empirical evidence that LAN traffic is bursty, not Poisson.
- Paxson & Floyd, "Wide-Area Traffic: The Failure of Poisson Modeling," *IEEE/ACM ToN*, 1995.
- **ITU-T G.704 / ANSI T1.107** — the TDM frame structure of T1/E1 carrier systems, a real static-TDM deployment.
