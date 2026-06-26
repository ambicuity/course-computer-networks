# CSMA/CA, the DCF, and 802.11 interframe spaces (SIFS/DIFS/EIFS/AIFS)

> 802.11 Wi-Fi cannot detect collisions the way 802.3 Ethernet does: a radio transmitting at +20 dBm hears its own signal a million times louder than any incoming noise, so the same hardware cannot listen for a collision burst while it is sending. 802.11 therefore uses **CSMA/CA** (Carrier Sense Multiple Access with **Collision Avoidance**), a *defer* protocol: a station that wants to transmit first waits for the medium to be idle for **DIFS** (DCF InterFrame Spacing), then counts down a random backoff drawn from a slotted **contention window**, freezing the counter whenever the channel goes busy and resuming when it goes idle again. The **Distributed Coordination Function (DCF)** is the algorithm that runs that countdown with **binary exponential backoff** (window `[0, CW]` where `CW` doubles from `CWmin = 31` to `CWmax = 1023` on each failed transmission), per-PHY slot time (9 us for 802.11b DSSS, 9 us for 802.11a/g/n/ac/ax OFDM), and a hierarchy of **interframe spaces** that turn channel access into a priority queue. The shortest interval, **SIFS** = 10 us (11b) or 16 us (11a/g), is reserved for the in-flight dialog of an existing exchange (ACKs, RTS/CTS, fragmentation, block-acks) so a single conversation cannot be interrupted; **DIFS** = SIFS + 2 slots, the time any *new* contender must wait; **PIFS** = SIFS + 1 slot, the time the AP polls during the (unused) PCF; **EIFS** is a long recovery interval used only after a corrupted or unknown frame so a station that missed the original preamble does not barge in mid-frame; and **AIFS[AC]** is a per-access-category extension added by 802.11e that gives Voice, Video, Best-Effort, and Background traffic four different DIFS values. This lesson dissects the IFS hierarchy, the backoff state machine, the ACs, and builds a stdlib-only CSMA/CA simulator that runs a real DATA/SIFS/ACK/DIFS timeline and reports throughput.

**Type:** Learn
**Languages:** Python (stdlib-only CSMA/CA backoff + IFS simulator), diagrams
**Prerequisites:** Classic Ethernet CSMA/CD and binary exponential backoff (Phase 6 lesson 1), hidden-terminal problem (Phase 4), slot time and propagation delay, 802.11 frame format basics (Phase 6 lesson 5)
**Time:** ~75 minutes

## Learning Objectives

- Reproduce the 802.11 IFS hierarchy from PHY constants: derive **SIFS** from the RX-to-TX turnaround, **DIFS = SIFS + 2 * slot** as the new-frame idle wait, **PIFS = SIFS + 1 * slot** for the AP's polling, and explain why SIFS gives priority to in-flight dialog.
- Trace the DCF state machine: sense, wait DIFS, pick a backoff in `[0, CW]`, count down idle slots, freeze on busy, resume on idle, transmit when the counter hits zero, then on failure double `CW` (capped at 1023) and retry.
- Justify why a *minimum* contention window (`CWmin = 31`) exists and not just `[0, 0]`: it spreads simultaneous contenders across slots so the first slot after DIFS is not a guaranteed collision.
- Distinguish **collision avoidance** (defer, then back off) from **collision detection** (sense the wire while sending), and explain how RTS/CTS + NAV recover from the hidden-terminal case where deferral alone is not enough.
- Map 802.11e **access categories** (Voice, Video, Best-Effort, Background) to their AIFS and CW values, and predict which traffic wins a contention under mixed load.
- Compute **EIFS** as `SIFS + ACK_tx_time + DIFS` and explain when a station uses it (bad frame) versus DIFS (channel went idle after a good frame).
- Run a slotted-time 802.11 simulator with N stations, plot the contention-window growth, and report achieved throughput vs. the Bianchi 2000 saturation ceiling.

## The Problem

A network engineer is debugging a conference-room Wi-Fi deployment. Forty laptops are attached to one AP. Voice calls are breaking up; the engineer grabs a packet capture and sees a flood of retransmissions, an exponential climb of retry counts in the 802.11 MAC headers, and CW values that ping-pong between 31 and 1023. The AP logs say "channel utilization 92%." He turns the data-rate auto-tuning off, forces everyone to 54 Mbps, and the problem gets *worse*. He wonders whether RTS/CTS is missing, whether the radio is broken, or whether the AP just needs more antennas.

The real story is in the MAC rules. CSMA/CA is a defer protocol: every station that wants to transmit must first wait DIFS, then back off across a slotted window. When 40 stations all wake at once after a beacon, they draw backoff values from `[0, 31]` and 32 slots is barely enough to spread them out — so two or three stations usually pick the same slot and collide. On collision, the *whole* frame (which is long, because the rate is high) is on the floor, and the contenders double the window. The throughput collapse is the backoff tree expanding under load, not the radio and not the antennas. The voice calls break up because Voice is one of four access categories in 802.11e, and a misconfigured AIFS leaves it waiting longer than Best-Effort. The fix is to read the IFS hierarchy and the access-category parameters, not to swap the antenna.

That is why this lesson studies the interframe spaces and the DCF together: the IFS values define who can interrupt whom, the contention window controls how many contenders the medium can serve without collision, and the access categories layer quality-of-service on top of both.

## The Concept

CSMA/CA is the defer-and-backoff half of the 802.11 MAC, governed by the DCF. The SVG diagrams the IFS hierarchy and a single DATA/SIFS/ACK/DIFS exchange; `code/main.py` is a stdlib-only simulator that drives the same state machine and reports throughput.

### Why defer-and-backoff instead of sense-and-collide

Ethernet's CSMA/CD works because a station can listen to the wire *while it is transmitting* — the cable carries the 5 V Manchester signal, two stations driving the line both raise the voltage, the sum goes out of spec, and both stations notice the collision within 2τ. A radio cannot do this. The transmitted power at the antenna is on the order of 100 mW (+20 dBm); the smallest signal the receiver can decode is on the order of 100 fW to 1 pW (-100 to -90 dBm). That is a 90 to 100 dB gap, or seven to ten orders of magnitude. The station's own transmission drowns out any incoming noise burst. So Wi-Fi replaces "detect the collision" with "make the collision unlikely in the first place":

1. Sense the medium (physical carrier sense + virtual NAV from overheard frames).
2. Wait until the medium has been idle for at least DIFS.
3. Pick a backoff counter from `[0, CW]` slots.
4. Count down one slot per idle slot boundary; freeze if the medium goes busy.
5. Transmit when the counter hits zero. If no ACK arrives within `SIFS + ACK_tx_time`, double `CW` and retry.

A "collision" in 802.11 is therefore not detected but *inferred* — the absence of an ACK is the only signal the sender has that something went wrong. This is why every unicast DATA frame must be ACKed, and why the retry counter (the `Retry` bit and the 802.11e `dot11ShortRetryLimit`) is a fundamental state variable, not a nice-to-have.

### The slot time, per PHY

The slot is the basic unit of backoff countdown. It is not 51.2 us like Ethernet; the 802.11 spec sizes it to (a) the RX-to-TX turnaround time, (b) the time to detect a busy medium at the antenna, (c) the time for a signal to propagate across the cell, and (d) the busytone-processor delay. Numbers from the 802.11-2007 and 802.11-2016 specs:

| PHY | Slot time | Notes |
|---|---|---|
| 802.11b (DSSS, 2.4 GHz) | **20 us** | Long preamble, 1/2 Mbps fallback |
| 802.11b with short preamble (optional) | 20 us | Slot unchanged |
| 802.11a (OFDM, 5 GHz) | **9 us** | 52 subcarriers, up to 54 Mbps |
| 802.11g (OFDM, 2.4 GHz) | **9 us** | OFDM with 2.4 GHz coexistence |
| 802.11n (HT, 2.4 / 5 GHz) | 9 us | Same OFDM timing |
| 802.11ac / ax (VHT / HE, 5 / 6 GHz) | 9 us | Same OFDM timing |

The slot is the same 9 us across all OFDM-based PHYs because the receiver's energy-detect time, the PLCP preamble, and the propagation budget are dominated by RF physics, not bit rate. (The lesson's headlined 9 us for 11a/g and the 9 us of 11n/ac/ax match this table; the 20 us of 11b is the historical DSSS slot and the simulator lets you switch between them with a flag.)

### The interframe-space hierarchy

The four named intervals are *delays* that a station must observe before it is allowed to transmit. They are stacked so that an in-flight exchange always wins over a brand-new contender:

| Interval | Formula | Value (11b) | Value (11a/g) | Used by |
|---|---|---|---|---|
| **SIFS** | RX-to-TX turnaround | **10 us** | **16 us** | ACK, CTS, next fragment, CF-Poll response, any reply in an existing dialog |
| **PIFS** | SIFS + 1 * slot | 30 us | 25 us | AP polling (PCF, not used in practice) |
| **DIFS** | SIFS + 2 * slot | **50 us** | **34 us** | Any *new* contention under DCF |
| **EIFS** | SIFS + ACK_tx + DIFS | **94 us** | **94 us** | Recovery after a corrupted or unknown frame |

The order SIFS < PIFS < DIFS < EIFS is the priority order. The station that has the right to send *first* is whichever one has the shortest wait. SIFS is reserved for the in-flight dialog of an exchange that has *already acquired the channel*; if you are the recipient of a DATA frame, you may send the ACK after only SIFS and the contender waiting for DIFS has not yet finished its wait, so the ACK wins. A new contender must wait the full DIFS, and a station that received a bad frame must wait the longest, EIFS, so it does not trample on a dialog it cannot decode.

### Backoff and the contention window

After DIFS expires, every station that wants to transmit picks an integer backoff `b` uniformly from `[0, CW]` and arms a countdown timer. `CW` starts at **`CWmin = 31`** and doubles on each retransmission up to **`CWmax = 1023`**:

| Retry `k` | Window `CW` | Draw from `[0, CW]` |
|---|---|---|
| 0 (first try) | 31 | 32 slots |
| 1 | 63 | 64 slots |
| 2 | 127 | 128 slots |
| 3 | 255 | 256 slots |
| 4 | 511 | 512 slots |
| 5+ | 1023 | 1024 slots (frozen) |
| 7 (dot11ShortRetryLimit) | — | give up, drop frame |

The countdown advances at the *slot boundary* — that is, only when the medium has been continuously idle for a full slot. If the medium goes busy, the counter freezes. When the medium goes idle again, the station waits DIFS, then resumes the countdown from where it left off. This is what makes DCF fair: a station that has been waiting the longest has the smallest remaining count and the highest probability of transmitting first.

`CWmin = 31` is the minimum that keeps the first slot after DIFS from being a guaranteed collision. If `CWmin = 0`, every contender transmits the instant DIFS expires, and 40 stations on the same AP collide every time. With 32 slots, the probability of a unique choice is high, and 64, 128, ... slots give the backoff tree room to spread.

The exponential growth is *binary exponential backoff* with the same shape as Ethernet's, but a different unit. Ethernet's slots are 51.2 us; 802.11's slots are 9 us. Ethernet's `CWmax = 1023`; 802.11's is the same. Ethernet abandons the frame at 16 retries; 802.11 has separate `dot11ShortRetryLimit = 7` and `dot11LongRetryLimit = 4` for short and long frames.

### Fragmentation, block-ack, and the burst

A single 1500-byte MSDU at 54 Mbps takes about 250 us to send. During that quarter-millisecond no other station can grab the channel, so a frame collision costs a quarter-millisecond of airtime. The standard lets the sender split a long MSDU into shorter **MPDUs (fragments)**, each with its own FCS, and acknowledge them as a burst:

```
A → B : FRAG 0
SIFS
B → A : ACK
SIFS
A → B : FRAG 1
SIFS
B → A : ACK
SIFS
A → B : FRAG 2 (last)
SIFS
B → A : ACK
SIFS
B → A : BLOCK-ACK
```

The whole burst runs on the SIFS cadence, so no other station ever gets a chance to count down. A station that hears the *first* fragment updates its NAV to cover the *entire* burst — that's what the NAV duration field is for. The 802.11n **aggregate MPDU (A-MPDU)** and 802.11ac **VHT single MPDU** push the same idea further: a 64-MPDU burst at 9 us SIFS dominates the throughput.

The state machine for the sender during a burst is: after the last backoff, transmit FRAG 0, start ACK timer, wait SIFS, receive ACK, transmit FRAG 1, ... until the last fragment is ACKed, then optionally send a `CF-END` to release the channel.

### Hidden terminals, RTS/CTS, and the NAV

Defer-and-backoff works perfectly when every station can hear every other station. It does not work when two stations can hear the AP but not each other — the classic *hidden terminal* problem. Station A and station C are both in range of B (the AP) but not of each other. A senses the medium, hears nothing, picks backoff = 2, and starts sending. C senses the medium, hears nothing, picks backoff = 5, and starts sending 3 slots later. At B, the two DATA frames overlap. Both fail.

The 802.11 fix is the optional **RTS/CTS handshake**, which uses the *virtual* carrier sense (the NAV, Network Allocation Vector) to extend the deferral beyond the physical sensing range:

1. A sends a short **RTS** (Request To Send) to B. The RTS carries a duration field that says "the medium will be busy for `RTS + SIFS + CTS + SIFS + DATA + SIFS + ACK` us."
2. B replies after SIFS with a **CTS** (Clear To Send) that re-states the same duration.
3. A sends DATA after SIFS. C, hidden from A but in range of B, hears the CTS and sets its NAV to the duration — it will not transmit for the whole exchange.

RTS/CTS costs a round-trip of small frames but eliminates the hidden-terminal data collision, which is the costly part. The trade-off is: RTS/CTS is *off* by default because for short frames and small cells the RTS/CTS overhead exceeds the win. It is enabled per-queue, usually at the AP, when the cell is large or has many hidden nodes.

The NAV is a per-station timer. Every overheard frame carries a duration field (in 802.11) or an "expected duration" (in 802.11e QoS) that tells the listener how long the channel will be busy; the listener sets its NAV to that value and treats the medium as busy until the timer expires, regardless of what the physical carrier sense says.

### Quality of service: 802.11e and the access categories

The DCF treats all traffic the same. A 200-byte VoIP packet and a 1500-byte video frame both wait DIFS, both pick a backoff from `[0, 31]`, and the 1500-byte frame can finish its transmission before the VoIP packet has finished its backoff. The VoIP packet's jitter and delay climb with the load.

802.11e (2005) split traffic into four **access categories (ACs)** with different AIFS and CW parameters, all sharing the same physical channel:

| AC | Traffic | AIFSN | CWmin | CWmax | TXOP (802.11n) |
|---|---|---|---|---|---|
| AC_VO | Voice (VoIP) | 2 | 3 | 7 | 1.504 ms |
| AC_VI | Video | 2 | 7 | 15 | 3.008 ms |
| AC_BE | Best-Effort (data) | 3 | 15 | 1023 | 0 |
| AC_BK | Background (e-mail, sync) | 7 | 15 | 1023 | 0 |

AIFSN is the count of slots *after* SIFS the station must wait: `AIFS = SIFS + AIFSN * slot`. With `slot = 9 us`, AIFSN = 2 gives Voice an idle wait of 16 + 18 = 34 us, which is the same as DIFS for non-QoS — but Voice starts counting down with `CWmin = 3` (4 slots), Best-Effort with `CWmin = 15` (16 slots), and Background with `AIFSN = 7` (63 slots of idle wait) and `CWmin = 15`. Under mixed load, Voice almost always wins.

A second part of 802.11e is the **TXOP (transmission opportunity)**: a station that wins the contention gets the channel for a bounded duration, not just for one frame. With Voice and Video getting 1.5 ms and 3.0 ms TXOPs, a 54 Mbps voice station can cram in a dozen voice frames in one burst, and the channel does not have to go through DIFS/backoff for each one. The 6 Mbps / 54 Mbps rate anomaly is mitigated at the same time.

The reference MAC service primitives in 802.11e are **HCF (Hybrid Coordination Function)** with HCCA (controlled) and EDCA (enhanced distributed). EDCA is the one deployed; HCCA requires AP scheduling that no consumer AP actually runs.

### EIFS: the bad-frame recovery interval

A station that receives a frame whose FCS is bad (CRC fails) or whose duration / type field it cannot parse does not know how long the in-flight exchange will take. If it jumps in after DIFS, it could trample on a frame the original sender is still transmitting. The standard says: after a bad frame, the receiver waits **EIFS = SIFS + ACK_tx + DIFS** before contending.

The `ACK_tx` part is included because the original sender, having not received an ACK, will retransmit — and the new contender must wait for that retransmission plus a full DIFS, so it cannot collide with it. Practically: EIFS on 11a/g is `16 + 44 + 34 = 94 us` (SIFS + ACK transmission time at the OFDM basic rate + DIFS). EIFS is the longest wait, used only as a defensive fallback. A station that has transmitted at least one frame successfully in the last `EIFS` window, or that has heard the channel busy since, can use DIFS instead — the standard is conservative but does not penalize a station that has had recent context.

## Build It

`code/main.py` is a stdlib-only Python module that runs the DCF state machine in slotted time and logs the timeline. It is the executable companion to the concept above.

1. **Constants** — `SIFS_B`, `SLOT_B`, `CWMIN_B`, `CWMAX_B` for 802.11b (10, 20, 31, 1023 us) and `SIFS_AG`, `SLOT_AG`, `CWMIN_AG`, `CWMAX_AG` for 802.11a/g/n (16, 9, 31, 1023 us), plus `AIFS_AC` for the four 802.11e access categories.
2. **`Station` dataclass** — fields for `id`, `ac`, `cw`, `backoff`, `retry`, `done`, and the per-station state `IDLE / WAIT_DIFS / COUNTING / TX / WAIT_ACK`. Frozen=True is not used because the state mutates as time advances; methods return new stations.
3. **`Simulator`** — `tick(us)` advances time in 1 us steps, runs the state machine for every station, freezes backoff when the channel is busy, and emits a `Timeline` log of every transition.
4. **`channel_acquire(sim, now)`** — after DIFS / AIFS expires, pick the station with the lowest remaining backoff (or the highest-priority AC if tied) and have it transmit DATA.
5. **`transmit_data_ack(sim, sender, now)`** — transmit DATA, wait SIFS, transmit ACK, freeze other stations via the busy signal, log the whole exchange, and return the next event time.
6. **`run(stations, duration_us, seed)`** — runs the simulator for a wall-clock duration in microseconds, draws random backoffs, reports total DATA frames, total ACKs, total airtime on successful exchanges, and a per-AC contention count.
7. **CLI** — runs with `N=20` stations across all four ACs, `duration=10 ms`, prints the timeline and the throughput, then runs a saturation sweep `N in [5, 10, 20, 50, 100]` and prints throughput vs. the Bianchi 2000 ceiling.

Run `python3 code/main.py`. You should see a 30-line timeline like:

```
t=   0 us  | ch idle
t=  34 us  | AC_VO #0 backs off 2 slots (CW=3)
t=  52 us  | AC_VO #0 transmits DATA (slot boundary, backoff=0)
t= 302 us  | AC_VO #0 receives ACK (after SIFS)
t= 336 us  | AC_BE #3 backs off 4 slots (CW=15)
...
```

…then a `Throughput` line: `achieved 5.2 Mbps / Bianchi ceiling 5.8 Mbps (89%)`.

Tune the parameters: change `CWMIN_B` to 0 and watch throughput collapse (the first slot after DIFS becomes a 40-way collision); change `AIFS_VO` to 7 and watch Voice's jitter climb; double `SLOT_AG` to 18 us and watch the backoff tree spread further per wait but the throughput drop by half.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Pick the right IFS | Channel state, frame type | SIFS for ACK / CTS / next fragment, DIFS for a new contender, EIFS for the bad-frame recovery |
| Compute DIFS per PHY | `SIFS + 2 * slot` | 50 us on 11b, 34 us on 11a/g |
| Trace the backoff | Slot-by-slot timeline | Counter freezes on busy, resumes on idle, transmits at 0 |
| Choose `CW` growth | Retry count `k` | Doubles from 31 to 1023, frozen at 1023, gives up at 7 (short) or 4 (long) |
| Map AC to AIFS | 802.11e table | AC_VO uses AIFSN=2, AC_BK uses AIFSN=7 |
| Diagnose voice jitter | Capture under load | Voice is on AC_VO with CWmin=3; check AP's QoS config if Voice is queued behind Best-Effort |
| Spot an EIFS | Bad FCS in capture | Receiver backed off 94 us (11a/g), not 34 us — visible as a long idle gap in the timeline |
| Reason about RTS/CTS | Hidden terminal topology | Enable RTS/CTS at the AP when one cell has nodes that cannot hear each other |

Wireshark filter for the AC: `wlan.fc.type_subtype == 0x18` for QoS Data, then `wlan.qos.priority` to see the AC.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **DCF / IFS cheat sheet** mapping every named interval (SIFS, PIFS, DIFS, EIFS, AIFS[AC]) to its formula and value per PHY (11b, 11a/g, 11n, 11ac, 11ax).
- A **backoff state machine diagram** showing IDLE → WAIT_DIFS → COUNTING → TX → WAIT_ACK → IDLE, with the freeze-on-busy branch.
- A **throughput-vs-load curve** generated by `code/main.py`'s saturation sweep, plotted against the Bianchi 2000 `1 - (1 - τ)^n` ceiling.
- A **CSMA/CA runbook** with the AIFSN/CWmin/CWmax per AC, the retry limits, and a troubleshooting matrix (jitter, retransmits, hidden terminals, rate anomaly).

Start from `outputs/prompt-csmaca-dcf-interframe-spaces.md`.

## Exercises

1. A 2.4 GHz DSSS network is using 802.11b. A station completes a backoff of 11 slots from `CW = 31` and transmits a 1500-byte DATA at 11 Mbps. Write out the timeline (in microseconds) from the backoff's first slot to the end of the ACK, naming every IFS and the SIFS / DIFS values.
2. A misconfigured AP assigns AIFSN = 7 to its Voice queue and AIFSN = 2 to its Best-Effort queue. With 30 active stations, predict which AC wins the channel and what happens to VoIP's one-way delay. Now swap the values — does the situation change?
3. Two hidden stations A and C both want to send to B. With RTS/CTS *off*, the first DATA from each collides at B and both fail. With RTS/CTS *on*, A's RTS is heard by B and C (B is in range of both), B's CTS is heard by both, and the exchange completes. Re-draw the timeline. At what point does C stop contending, and which frame carries the information that tells it to stop?
4. A capture shows a station that has just received a frame with a bad FCS. It waits 94 us before contending on 802.11a/g, even though the channel is otherwise idle. Which IFS is it using, what is the formula, and is the station behaving correctly? Now the station transmits a successful DATA of its own 200 us later. Which IFS does it use for the *next* contention, and why?
5. A 40-station cell with default 11g parameters (slot = 9 us, CWmin = 31, SIFS = 16 us) has just finished a beacon. All 40 stations have a frame to send. What is the probability that all 40 pick *different* backoff values from `[0, 31]`? Roughly how many collisions do you expect on the *first* contention, and how does this inform the choice of `CWmin`?
6. Run `code/main.py` with `PHY = 11b` and `PHY = 11ag` for `N = 5, 20, 50, 100` stations. Report the achieved throughput and the Bianchi ceiling for each, and explain the trend. Then re-run with `AIFS_VO` set to 2 and 7, and quantify the change in Voice's share of the airtime.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CSMA/CA | "defer instead of detect" | 802.11's defer-and-backoff MAC; collision is inferred from a missing ACK, not sensed on the wire |
| DCF | "the regular Wi-Fi MAC" | Distributed Coordination Function: CSMA/CA + binary exponential backoff + slotted time + IFS hierarchy |
| IFS | "the wait between frames" | Interframe Space: SIFS / PIFS / DIFS / EIFS / AIFS[AC], each defining a different priority |
| SIFS | "the short wait" | Short InterFrame Spacing: 10 us (11b) / 16 us (11a/g); reserved for in-flight ACK, CTS, fragment, CF-Poll response |
| PIFS | "AP polling wait" | SIFS + 1 * slot; used by the (optional, not deployed) PCF |
| DIFS | "the new-contender wait" | DCF InterFrame Spacing = SIFS + 2 * slot; what a station must observe before picking a new backoff |
| EIFS | "the bad-frame wait" | Extended IFS = SIFS + ACK_tx + DIFS; used only after a corrupted or unknown frame to avoid stomping on an existing dialog |
| AIFS | "the QoS wait" | Arbitration IFS = SIFS + AIFSN * slot, where AIFSN is per AC (2 for Voice, 7 for Background) |
| Slot time | "the backoff unit" | 9 us for all OFDM PHYs (11a/g/n/ac/ax), 20 us for 11b DSSS |
| CWmin / CWmax | "the window" | 31 / 1023 in the spec; CW doubles per retry, frozen at 1023, gives up at 7 (short) or 4 (long) |
| Backoff | "the random wait" | A counter drawn from `[0, CW]` slots, decremented on every idle slot boundary, frozen on busy, resumed on idle |
| AC (access category) | "the QoS class" | Voice, Video, Best-Effort, Background; per-AC AIFSN, CWmin, CWmax, TXOP |
| TXOP | "the airtime grant" | Transmission Opportunity: 802.11e grants a station the channel for a bounded duration, not just one frame |
| NAV | "the virtual busy timer" | Network Allocation Vector: per-station timer set by the duration field of overheard frames; medium treated as busy regardless of physical sense |
| RTS / CTS | "the handshake" | Request / Clear to Send: optional frames that use the NAV to solve the hidden-terminal problem |
| Block-ack | "the burst ACK" | A single ACK at the end of a fragmentation burst, replacing per-fragment ACKs |

## Further Reading

- **IEEE Std 802.11-2007** (and current IEEE Std 802.11-2020) — section 9.3.2 "DCF" and section 9.2.10 "IFS" for the authoritative IFS definitions and the slot-time table per PHY.
- Matthew S. Gast, *802.11 Wireless Networks: The Definitive Guide* (O'Reilly), chapter 4 "Frames and Channels" and chapter 8 "802.11e QoS" — clear treatment of IFS and EDCA parameters.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.4.3 "The 802.11 MAC Sublayer Protocol" — the source chapter for this lesson.
- Giuseppe Bianchi, "Performance Analysis of the IEEE 802.11 Distributed Coordination Function," *IEEE JSAC* 18(3), March 2000 — the throughput ceiling `S = P_s P_tr E[P] / (1 + T_c^* + σ / slot)` and the saturation analysis.
- Xiao, Y. (2005), "IEEE 802.11e QoS analysis via cross-layer analytical modeling for wireless LANs," *IEEE WCNC* — the AIFS and CW per AC.
- Romit Roy Choudhury, *Introduction to Wireless Networks* (NCSU), lecture notes on CSMA/CA, RTS/CTS, and the hidden-terminal problem.
- Cisco, "Voice over Wireless LAN 4.1 Design Guide" — practical AIFSN / CWmin / TXOP settings for VoIP.
