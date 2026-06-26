# Collision-Free MAC Protocols: Bit-Map, Token Passing, and Binary Countdown

> When the bandwidth-delay product of a shared channel is large (long cable, short frames) or the traffic is real-time (voice, industrial control), CSMA contention wastes capacity and produces variable delay. Three deterministic protocols sidestep collisions entirely. The **basic bit-map protocol** uses an N-slot reservation period in which station *j* asserts a 1 in slot *j* to advertise a queued frame, then transmits in numerical order; overhead is N bits per cycle, so efficiency is `d/(d+N)` at low load and `d/(d+1)` at high load. **Token passing** (IEEE 802.4 token bus, IEEE 802.5 token ring, FDDI, IEEE 802.17 RPR) carries the same right-to-send as a circulating 3-byte token over a logical or physical ring, equalising wait across all stations. **Binary countdown** (Datakit, 1987) lets contending stations broadcast their addresses bit-by-bit into a wired-OR channel; any station that sees a 1 in a bit position where it had a 0 drops out, so the highest address wins with `log2 N` bits of overhead instead of N, and zero overhead when the address is the frame's first field. The lesson compares efficiency formulae, simulates each protocol, and quantifies the bias that bit-map and countdown give to high-numbered stations.

**Type:** Learn
**Languages:** Python (stdlib simulators), diagrams
**Prerequisites:** ALOHA, slotted ALOHA, CSMA, CSMA/CD, propagation delay, bandwidth-delay product
**Time:** ~75 minutes

## Learning Objectives

- Sketch the N-slot reservation period of the basic bit-map protocol and derive the per-cycle overhead N bits and the mean wait of N slots.
- Trace token circulation on a logical ring (802.5) and a logical bus (802.4) and explain why mean wait on token ring is independent of station number.
- Simulate binary countdown for four competing stations and show how a station drops out the instant it loses a high-order bit.
- Compute the efficiency formulas `d/(d+N)` (bitmap), `d/(d+1)` (bitmap saturated), and `d/(d+log2 N)` (countdown) and apply them to N=8, N=128, and N=2048.
- Identify why a collision-free protocol still loses to CSMA at very low load, and pick the right protocol given a load profile.

## The Problem

A small aerospace vendor is replacing the 10BASE2 segment that links eight test stands on a vibration floor. The frames are short (32 bytes), the cable is 800 m of shared coax, and the test data is time-sensitive: each result must land at the recorder within 5 ms or the next excitation cycle slips. The current network has a 3% collision rate at modest load and the worst-case jitter occasionally blows the 5 ms budget.

CSMA/CD is wrong for this job. With 800 m of cable at 10 Mbps the bandwidth-delay product is 800 m x 20 ns/m x 10 Mbps = 160 bit-times, small, but the propagation component of the slot time pushes 32-byte frames perilously close to the 64-byte minimum and the worst-case backoff after 10 collisions is 1023 slots, which is 52 ms by itself, more than ten times the latency budget. The vendor needs a deterministic, bounded-wait channel. The protocol options come from a single family: collision-free multiple access.

## The Concept

All three protocols assume exactly N stations, each with a unique address 0..N-1, propagation delay negligible relative to a bit, and a slotted timeline like Fig. 4-5. The question each one answers is the same: **which station gets the channel next, and how much does that cost in bits?** They differ in the answer and the fairness profile.

### The Basic Bit-Map Protocol (Reservation)

Every contention cycle is exactly N bit-slots. In slot j, station j transmits a 1 if it has a frame, otherwise 0. Every station sees the same N-bit pattern. After the bitmap completes, stations transmit in numerical order. Collisions are impossible because everyone agrees on the order.

```
+---+---+---+---+---+---+---+---+--------+--------+
| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | frame1 | frame3 |
+---+---+---+---+---+---+---+---+--------+--------+
 \_____________ 8-bit reservation period _________/
                  (each bit a station's claim)
```

The wait is uneven. Low-numbered stations pay 1.5N slots on average (current scan + full next scan), high-numbered stations pay 0.5N. Mean across all stations is N slots. Efficiency at low load is `d/(d+N)`, at high load (all stations saturated) is `d/(d+1)` because the N-bit reservation amortises over N frames. The protocol is the cleanest way to schedule periodic traffic when N is small.

### Token Passing

Token passing replaces the bitmap with a circulating **token**, a short control frame that grants the right to send. The token moves in a predefined order; the holder either transmits one frame or passes the token. Two physical realisations exist.

| Standard | Topology | Token semantics | Use case |
|---|---|---|---|
| IEEE 802.4 | Logical bus, stations polled in order | Token passed via broadcast | Factory floor (Token Bus) |
| IEEE 802.5 | Physical ring, 4 Mbps | Token grabbed on receive, sent on transmit | Office LAN (Token Ring, 1980s) |
| FDDI | Dual counter-rotating fibre rings, 100 Mbps | Token holds timed TTRT | Campus backbone (1990s) |
| IEEE 802.17 | Two counter-rotating rings, 10 Gbps | Resilient Packet Ring, spatial reuse | Metro Ethernet (2000s) |

Token ring's mean wait is N/2 for every station. No high/low bias. The trade-off is token loss: a crashed station can swallow the token, and recovery requires a designated monitor (ring) or log-in protocol (bus). Modern deterministic Ethernet (IEEE 802.1Qbv time-sensitive networking) borrows the bounded-wait idea without the token.

### Binary Countdown

Binary countdown fixes the bitmap's "1 bit per station" cost when N is large. Each station wanting the channel broadcasts its address as a bit string, starting with the high-order bit. The medium is wired-OR: if any station puts a 1 on the wire, every station sees 1. A station that has 0 in a position where the wire is 1 drops out of the bidding. The last station standing wins, and by construction it has the highest address.

The four-station trace from the chapter:

| Bit time | 0010 | 0100 | 1001 | 1010 | Result | Dropouts |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 1 | 1 | 0010, 0100 give up |
| 1 | - | - | 0 | 0 | 0 | both still in |
| 2 | - | - | 0 | 1 | 1 | 1001 gives up |
| 3 | - | - | - | 0 | 0 | 1010 wins |

Overhead is `log2 N` bits per arbitration, so efficiency is `d/(d + log2 N)`. If the protocol is layered so the winner's address is the first field of the frame, those `log2 N` bits *are* the destination address and the efficiency is 100%. The price is a fixed bias: high addresses win ties, every cycle.

### Why "collision-free" is not always faster

At very low load the bitmap burns a full N-slot scan to find a single ready station. A CSMA sender would have grabbed the channel in a fraction of a slot. Bit-map and token therefore have a U-shaped delay curve: terrible at low load, excellent at high load. The crossover depends on frame length d, propagation tau, and N. Pick collision-free when traffic is periodic, real-time, or heavily loaded; pick CSMA when traffic is bursty and load is light.

### Putting the three side by side

| Protocol | Overhead per cycle | Mean wait at low load | Mean wait at high load | Fairness | Scales to large N? |
|---|---|---|---|---|---|
| Bit-map | N bits | 1.5N (low) to 0.5N (high) | (N-1)d + N | High-numbered biased | No. 1 bit per station |
| Token ring | 1 token (~3 B) | N/2 frames + token latency | N/2 frames | Equal | Yes, with monitor |
| Token bus | 1 token (~3 B) | N/2 frames + token latency | N/2 frames | Equal | Yes, log-in needed |
| Binary countdown | log2 N bits | log2 N | log2 N | High-address biased | Yes, 1 bit per address bit |
| Countdown (address in frame) | 0 | 0 | 0 | High-address biased | Yes |

The SVG traces one cycle of each protocol on the same N=8 station line-up so the differences show visually.

## Build It

`code/main.py` ships three simulators (stdlib only):

1. **Bit-map simulator**: generates per-station traffic, runs N-slot reservation periods, reports frames sent, contention slots, and the unfairness between station 0 and station N-1.
2. **Token ring simulator**: circulates a token over a ring, services one frame per visit, reports worst-case wait (the textbook N x frame time + token latency).
3. **Binary countdown simulator**: accepts a list of contending station addresses, runs the wired-OR arbitration bit-by-bit, and prints the dropouts and the winner.

Run `python3 code/main.py` and watch the unfairness between low- and high-numbered stations in both bit-map and countdown; rerun the token ring with the same workload to see the per-station wait flatten.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Choose a MAC for periodic control traffic | Frame rate, deadline, N | You compute d, the wait, and pick bit-map or token ring over CSMA |
| Estimate bit-map efficiency | d, N | You quote `d/(d+N)` at low load, `d/(d+1)` at saturation |
| Predict token ring worst case | Frame time, N, token walk time | You compute `(N-1) x frame_time + N x token_walk` |
| Spot the bias | Address ordering vs wait | Low-numbered stations wait longer in bit-map; high-address stations win countdown ties |
| Tweak countdown for fairness | Address remap | You pair high-traffic stations with low addresses or hash to spread contention |

Wireshark filter: `wlan.fc.type == 1 && wlan.fc.subtype == 11` shows RTS frames (the modern collision-avoidance descendant of these ideas).

## Ship It

Produce one reusable artifact under `outputs/`:

- A **collision-free MAC comparison sheet** with overhead, wait, fairness, and a per-N efficiency table for bit-map and countdown.
- A **simulator log** (paste of `python3 code/main.py` output) showing the unfairness, then the token ring's equalisation.
- A **selection flowchart** mapping workload to protocol: periodic/large-N -> countdown; periodic/small-N -> bit-map; critical equal-wait -> token ring.

Start from `outputs/prompt-collision-free-mac-protocols.md`.

## Exercises

1. With N=8 stations, a 1000-bit frame, and 10 us slot time, compute the low-load efficiency of the bit-map protocol and the worst-case wait for station 0.
2. A 16-station token ring carries 512-byte frames at 16 Mbps. The token is 3 bytes and the walk time between stations is 1 us. Compute the mean wait and the throughput at 50% load.
3. Run the binary countdown simulator with stations {0010, 0100, 1001, 1010, 1111}. Which station wins? Now add station 0001 and re-run. Who wins now and why?
4. The chapter claims bit-map efficiency at saturation is `d/(d+1)`. For N=64, d=1000, plot this against countdown's `d/(d+6)`. At what value of d does the crossover happen, and which protocol is better above it?
5. A factory floor has 32 PLCs producing 64-byte frames every 10 ms. Token bus and bit-map are both candidate MACs. Which is better and why? Include a numerical wait calculation.
6. Why is the "address-in-frame" variant of binary countdown said to have 100% efficiency, and what property of the channel makes that claim hold?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Reservation protocol | "stations book a slot in advance" | Bit-map or token-style scheme where right-to-send is decided before data is sent, so collisions cannot occur |
| Bit-map | "an N-bit claim" | A contention period of exactly N slots, where station j asserts 1 in slot j if it has a frame; followed by ordered transmission |
| Token | "the permission bit" | A short control frame circulated in a predefined order; possession grants the right to transmit one frame |
| Token ring | "IBM's LAN" | Physical ring where stations forward the token by retransmitting it; the basis of IEEE 802.5 and FDDI |
| Token bus | "factory LAN" | Logical ring on a bus, with stations sorted by address; IEEE 802.4 |
| Binary countdown | "wired-OR arbitration" | Each contender broadcasts its address bit-by-bit; any station seeing a 1 where it had a 0 drops out; highest address wins |
| Wired-OR | "OR on the wire" | Physical or logical property where 1 dominates 0, letting stations read a shared channel as the OR of all transmitters |
| Bandwidth-delay product | "tau-time bits" | The number of bits "in flight" on the medium; high values make CSMA's contention window large |
| Contention slot | "one decision interval" | The unit of time in slotted protocols, equal to the time needed to detect a busy/idle state on the channel |
| Fairness bias | "addresses matter" | Bit-map and binary countdown give an advantage to high-numbered stations; token passing is unbiased by construction |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.2.3 "Collision-Free Protocols"** — the source chapter for the bit-map, token ring, token bus, and binary countdown analyses.
- **Capetanakis, J. (1979), "Tree Algorithms for Packet Broadcast Channels," *IEEE Trans. Inf. Theory* 25(5)** — the adaptive tree walk covered in the next lesson.
- **Fraser, A. (1987), "Datakit: A Modular Network for Synchronous and Asynchronous Traffic," *Proc. ICC*** — the canonical reference for binary countdown as deployed.
- **IEEE 802.4** (Token Bus, withdrawn) and **IEEE 802.5** (Token Ring, withdrawn) — original standard text for the two token styles.
- **IEEE 802.17** (Resilient Packet Ring) — the last token-ring-style standard, designed for metro Ethernet.
- **IEEE 802.1Qbv** (Time-Sensitive Networking, 2015) — modern deterministic Ethernet that achieves token-like bounds without a circulating token.
