# ALOHA and CSMA Simulator Lab to Wireless Hidden Terminal Lab

> Build a discrete-event simulator that reproduces the classic medium-access throughput curves and the wireless failure mode that breaks carrier sensing. Pure ALOHA peaks at **S = 1/(2e) ≈ 0.184** at offered load G = 0.5; slotted ALOHA doubles that to **1/e ≈ 0.368** at G = 1.0. 1-persistent CSMA collapses under load because everyone transmits the instant the channel goes idle; non-persistent and p-persistent CSMA spread that backoff out. The hidden-terminal problem — two stations that can both reach an access point but cannot hear each other — defeats carrier sensing entirely and is why IEEE 802.11 added RTS/CTS (the 20-byte RTS and 14-byte CTS frames carrying a Duration/ID field that sets every overhearing station's Network Allocation Vector). This lab implements pure/slotted ALOHA, 1-persistent and non-persistent CSMA, and a hidden-terminal topology in `code/main.py`, then has you measure S-versus-G curves and the RTS/CTS recovery. The vulnerable window for pure ALOHA is 2 frame-times; for slotted ALOHA and CSMA it shrinks toward the propagation delay a = τ_prop / τ_frame.

**Type:** Build
**Languages:** Python (stdlib discrete-event simulator), Wireshark (802.11 capture), diagrams
**Prerequisites:** Phase 5 lessons on framing, collision domains, and the channel-allocation problem; basic probability (Poisson arrivals)
**Time:** ~110 minutes

## Learning Objectives

- Derive and reproduce the throughput equations S = G·e^(−2G) (pure ALOHA) and S = G·e^(−G) (slotted ALOHA) and confirm the **0.184 / 0.368** peaks from your own simulation runs.
- Explain why 1-persistent CSMA degrades faster than non-persistent CSMA under high offered load, using the synchronized-retry mechanism.
- Reproduce the hidden-terminal failure: two senders whose carrier sense reports "idle" yet collide at the receiver, and quantify the throughput loss.
- Show how the RTS/CTS handshake and the 802.11 Network Allocation Vector (NAV) restore throughput by replacing physical carrier sense with virtual carrier sense.
- Compute the channel-utilization parameter a = τ_prop / τ_frame and explain why CSMA only beats ALOHA when a is small.

## The Problem

You are debugging a warehouse Wi-Fi deployment. Two handheld scanners on opposite ends of a 60-metre aisle both associate cleanly with the same access point, both show full signal, and each works perfectly in isolation. But when forklift operators scan simultaneously during the morning rush, the AP logs a flood of retransmissions and goodput drops by half. Spectrum analysis shows no interference and no hidden rogue AP.

The scanners cannot hear each other. The AP sits between them; each scanner's carrier sense sees the channel as idle because the other scanner is out of radio range, so both transmit, and their frames collide *at the AP*. This is the hidden-terminal problem, and it is invisible to the carrier-sense logic that wired CSMA/CD relies on. To fix it you need to understand what carrier sensing actually guarantees, where it breaks, and what virtual carrier sensing (RTS/CTS + NAV) adds. This lab builds the simulator that makes all of that measurable.

## The Concept

### From ALOHA to slotted ALOHA

Pure ALOHA (Abramson, University of Hawaii, 1970) is the simplest rule: transmit whenever you have a frame, listen for an acknowledgement, and if none arrives, wait a random backoff and retry. A frame sent at time t is destroyed if any other frame starts in the interval (t − τ_frame, t + τ_frame) — a **vulnerable window of two frame-times**. With Poisson offered load G (frames per frame-time), the probability of zero collisions is e^(−2G), giving:

```
S_pure    = G · e^(−2G)      peak S = 1/(2e) ≈ 0.184 at G = 0.5
S_slotted = G · e^(−G)       peak S = 1/e   ≈ 0.368 at G = 1.0
```

Slotted ALOHA forces every transmission to begin at a slot boundary. A frame can now only collide with frames generated in the *same* slot, halving the vulnerable window to one frame-time and doubling peak throughput. `code/main.py` runs both and prints the measured S at a sweep of G values; your numbers should land within a few percent of these analytic peaks.

### Carrier Sense Multiple Access (CSMA)

CSMA improves on ALOHA by *listening before talking*. The catch is the propagation delay: a station that began transmitting τ_prop seconds ago is not yet "heard" by a distant station, so collisions still happen during that window. The key parameter is:

```
a = τ_prop / τ_frame
```

When a is small (short cable, long frames), carrier sense is almost perfect. When a is large (satellite link, tiny frames), CSMA degenerates toward ALOHA. The persistence strategy decides what a station does when it senses the channel busy:

| Variant | When channel is idle | When channel is busy | Failure under load |
|---|---|---|---|
| 1-persistent | Transmit immediately | Keep sensing, transmit the instant it goes idle | Many waiters pounce together → guaranteed collision |
| Non-persistent | Transmit immediately | Back off a random time, then re-sense | Wastes idle time but avoids synchronized pounce |
| p-persistent (slotted) | Transmit with probability p | Wait one slot, repeat | Tunable; p balances delay vs collision |

The 1-persistent collapse is the headline result: under high load, several stations queue behind a busy channel and all transmit at the same instant it clears, so they collide deterministically. Non-persistent randomizes the retry and stays useful at higher G.

### CSMA/CD versus CSMA/CA

On wired Ethernet (IEEE 802.3) a station can *detect* a collision while transmitting because it hears its own signal garbled, abort early, and run **binary exponential backoff**: after the n-th collision it waits a random number of slot-times in the range [0, 2^n − 1], capped at n = 10 (range 0–1023) and giving up after 16 attempts. That truncated backoff is why a busy Ethernet segment degrades gracefully rather than melting down.

Wireless cannot do collision *detection* — a radio cannot transmit and listen on the same channel at the same time, and the hidden terminal means the sender may not even hear the colliding frame. So 802.11 uses collision *avoidance* (CSMA/CA): sense idle for a DIFS interval, pick a random backoff in the contention window, count down only while the medium stays idle, and transmit when the counter hits zero. The receiver replies with an ACK after a SIFS gap. There is no mid-frame abort.

### The hidden-terminal problem

Carrier sense answers one question: "is the medium busy *near me*?" The hidden terminal exposes the gap between that and the real question, "will my frame collide *at the receiver*?" In the topology drawn in `assets/aloha-and-csma-simulator-lab-to-wireless-hidden-terminal-lab.svg`, stations A and C are both in range of access point B but out of range of each other:

```
   A  ---- B ---- C
   (A and C cannot hear each other; both reach B)
```

A senses idle, transmits to B. C also senses idle (it cannot hear A), transmits to B. The two frames overlap at B and are both lost. Every retry repeats the race. There is also a symmetric *exposed-terminal* problem where carrier sense is too conservative and suppresses a transmission that would actually have succeeded. The simulator in `code/main.py` models A and C as mutually invisible so their carrier sense always reports idle, reproducing the collision-at-receiver failure and the throughput cliff it causes.

### RTS/CTS and the Network Allocation Vector

802.11's fix is *virtual* carrier sensing. Before a data frame, the sender may transmit a short **Request To Send (RTS)** frame; the receiver answers with **Clear To Send (CTS)**. Because the CTS comes from the AP, every station that can hear the AP — including the hidden terminal C — overhears it and stays silent. The control frames are tiny relative to a data frame:

| Frame | Size | Key field |
|---|---|---|
| RTS | 20 bytes | Duration/ID (16 bits), RA, TA |
| CTS | 14 bytes | Duration/ID (16 bits), RA |
| ACK | 14 bytes | Duration/ID, RA |

The **Duration/ID** field carries the number of microseconds the upcoming exchange will occupy. Every station that overhears RTS or CTS loads that value into its **Network Allocation Vector (NAV)** — a countdown timer — and treats the medium as busy until the NAV expires, even if its physical carrier sense says idle. That is how a station defers to a transmission it cannot directly hear. RTS/CTS is governed by the **dot11RTSThreshold**: frames shorter than the threshold skip the handshake (the overhead is not worth it for small frames). `code/main.py` adds an RTS/CTS mode so you can measure throughput recovery on the same hidden-terminal topology.

### Worked numeric example

Suppose a 1 Mbps channel, 1500-byte data frames (τ_frame = 12,000 bits / 1 Mbps = 12 ms) and τ_prop = 1 µs across a small room. Then a = 1 µs / 12 ms ≈ 0.00008, essentially zero, so carrier sense is near-perfect on a *shared-hearing* topology. But add a hidden terminal and carrier sense buys you nothing — the collision probability returns to the ALOHA regime regardless of how small a is. RTS plus CTS cost roughly 0.27 ms of overhead to protect a 12 ms data frame: about 2% to eliminate the hidden-terminal collision. That overhead-versus-protection trade is exactly what the RTS threshold tunes.

## Build It

1. Read `code/main.py` and locate the four entry points: `simulate_aloha(slotted=...)`, `simulate_csma(persistent=...)`, `simulate_hidden_terminal(use_rts_cts=...)`, and `main()`.
2. Run `python3 main.py`. Confirm the printed pure-ALOHA peak is near 0.184 and slotted near 0.368.
3. Sweep offered load G yourself: edit the `G_VALUES` list and re-run, then plot S versus G on paper or in a spreadsheet. Verify the curves cross where slotted overtakes pure.
4. Run the CSMA comparison and confirm 1-persistent throughput falls below non-persistent at high load.
5. Run the hidden-terminal scenario both with and without RTS/CTS and record the goodput difference.
6. Optional Wireshark step: capture on a monitor-mode 802.11 interface, apply the display filter `wlan.fc.type_subtype == 0x1b` (RTS) and `0x1c` (CTS), and read the Duration field that drives the NAV.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Reproduce ALOHA peaks | Printed S at each G from `simulate_aloha` | Pure peak ≈ 0.184 at G≈0.5; slotted ≈ 0.368 at G≈1.0 |
| Show 1-persistent collapse | S-vs-G for both CSMA persistence modes | 1-persistent throughput drops below non-persistent as G rises |
| Trigger hidden terminal | Collision count with A and C mutually invisible | Goodput far below the shared-hearing CSMA baseline |
| Recover with RTS/CTS | Goodput with `use_rts_cts=True` | Collisions at the AP drop to near zero; goodput recovers |
| Read the NAV in a trace | Wireshark RTS/CTS Duration/ID field | You can state how long neighbours will defer |

## Ship It

Produce one artifact under `outputs/`:

- A throughput-curve sheet plotting your measured S-versus-G against the analytic 0.184 / 0.368 peaks.
- A one-page hidden-terminal runbook: symptom, carrier-sense gap, RTS/CTS + NAV fix, and the RTS-threshold trade-off.
- An annotated 802.11 RTS/CTS/ACK capture showing the Duration field setting neighbours' NAV.

Start from [`outputs/prompt-aloha-and-csma-simulator-lab-to-wireless-hidden-terminal-lab.md`](../outputs/prompt-aloha-and-csma-simulator-lab-to-wireless-hidden-terminal-lab.md).

## Exercises

1. Run `simulate_aloha` for G = 0.1, 0.3, 0.5, 1.0, 2.0 in both modes. At which G does slotted ALOHA's throughput first exceed pure ALOHA's peak, and why does pure ALOHA's curve turn over earlier?
2. Set the propagation parameter so a = 0.1, then a = 0.5. Show that as a grows, non-persistent CSMA's advantage over slotted ALOHA shrinks. Explain using the vulnerable window.
3. In the hidden-terminal scenario, make A and C *able* to hear each other (shared hearing) and re-run. Quantify how much carrier sense alone recovers, then add RTS/CTS on top. Which fix mattered more, and on which topology?
4. The 802.11 RTS threshold defaults around 2347 bytes (effectively off). Compute the RTS/CTS overhead as a fraction of frame time for a 100-byte frame versus a 1500-byte frame and justify why short frames skip the handshake.
5. Implement truncated binary exponential backoff in the CSMA path: range [0, 2^n − 1] capped at n = 10, give up at 16 attempts. Show it lowers the collision rate at high load compared with a fixed backoff.
6. Explain why CSMA/CD (collision detection) is impossible on the wireless hidden-terminal topology even though it works fine on wired Ethernet, citing both the half-duplex radio and the out-of-range sender.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Pure ALOHA | "Just transmit and hope" | Random-access with a 2-frame-time vulnerable window; peaks at S = 1/(2e) ≈ 0.184 |
| Slotted ALOHA | "ALOHA but synced" | Transmissions start on slot boundaries; vulnerable window halved; peaks at 1/e ≈ 0.368 |
| 1-persistent CSMA | "Send as soon as it's free" | Stations pounce together when the channel clears, causing synchronized collisions under load |
| Non-persistent CSMA | "Back off then re-check" | Randomized retry that avoids the pounce, staying useful at higher offered load |
| Parameter a | "Propagation ratio" | τ_prop / τ_frame; carrier sense is effective only when a is small |
| Hidden terminal | "Bad signal" | Two senders out of range of each other but in range of the receiver, colliding at the receiver despite "idle" carrier sense |
| RTS/CTS | "Wi-Fi handshake" | 20-byte / 14-byte control frames that establish virtual carrier sense before data |
| NAV | "A 802.11 timer" | Network Allocation Vector: a countdown loaded from the Duration/ID field that makes a station defer to transmissions it cannot hear |
| Binary exponential backoff | "Random wait" | Retry delay drawn from [0, 2^n − 1] slots, capped at n=10, giving up after 16 tries (802.3) |

## Further Reading

- IEEE 802.11-2020, clause 10 (MAC) — RTS/CTS, NAV, DIFS/SIFS, and the Duration/ID field.
- IEEE 802.3 — CSMA/CD and the truncated binary exponential backoff algorithm.
- N. Abramson, "The ALOHA System — Another Alternative for Computer Communications," AFIPS 1970 — the original random-access analysis.
- L. Kleinrock and F. Tobagi, "Packet Switching in Radio Channels: Part I — CSMA," IEEE Transactions on Communications, 1975 — the persistence-strategy throughput analysis.
- A. Tanenbaum & D. Wetherall, *Computer Networks*, 5th ed., Chapter 4 (The Medium Access Control Sublayer) — ALOHA, CSMA, and the hidden/exposed terminal problems.
- J. Kurose & K. Ross, *Computer Networking: A Top-Down Approach*, Chapter 6 (The Link Layer) — multiple-access protocols and 802.11.
- Wireshark 802.11 display-filter reference: `wlan.fc.type_subtype`, `wlan.duration` for reading RTS/CTS and NAV in captures.
