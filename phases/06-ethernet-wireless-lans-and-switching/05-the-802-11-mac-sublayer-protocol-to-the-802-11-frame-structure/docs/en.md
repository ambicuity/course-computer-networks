# The 802.11 MAC Sublayer Protocol to The 802.11 Frame Structure

> Wi-Fi radios are half-duplex: a transmitter's own signal can be a million times stronger than an incoming one, so a station cannot listen while it talks. That kills Ethernet-style collision *detection*, so 802.11 substitutes collision *avoidance*. The Distributed Coordination Function (DCF) makes every station sense the medium for a DIFS idle gap, draw a random backoff (0–15 slots on OFDM PHYs), count down only while idle, transmit at zero, and treat a missing SIFS-spaced ACK as a collision — then double the contention window and retry with binary exponential backoff. Hidden terminals are handled by *virtual* carrier sense: every frame's 2-byte Duration field seeds each neighbor's Network Allocation Vector (NAV), and optional RTS/CTS reserves the channel before a long frame. The data frame carries an 11-subfield Frame Control word (Protocol version 00, Type 10, Subtype 0000 for plain data), the To DS / From DS pair that selects which of three or four 6-byte addresses appear, a 16-bit Sequence field split into a 4-bit fragment number and 12-bit sequence number, up to 2312 bytes of LLC-prefixed payload, and a 32-bit CRC frame check sequence. This lesson makes those fields and timers observable so you can read a real capture and diagnose retries, NAV starvation, and the rate anomaly.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib frame/backoff model)
**Prerequisites:** Phase 6 lessons on CSMA/CD and Ethernet framing; MAC addressing; CRC-32 (Phase 3)
**Time:** ~75 minutes

## Learning Objectives

- Trace one DCF transmission attempt end to end: DIFS wait, slot countdown, frame, SIFS, ACK — and name the exact timer at each step.
- Compute a contention-window backoff sequence under repeated loss and explain why CW doubles from CWmin=15 up to CWmax=1023.
- Decode an 802.11 data frame's Frame Control bits and predict how the To DS / From DS pair changes Address 1/2/3 meaning.
- Explain how the 2-byte Duration field populates a neighbor's NAV and how RTS/CTS extends that reservation across a hidden terminal.
- Identify the packet evidence (Retry bit, Sequence/Fragment numbers, Duration, Subtype) that distinguishes a retransmission from a fresh frame in a capture.
- Describe two real failure modes — NAV starvation and the rate anomaly — and the field-level evidence each leaves.

## The Problem

A user reports that voice calls over Wi-Fi break up whenever someone in the same room starts a large file download, even though "the signal is full bars." Throughput on the call is a trickle; the AP is healthy; the wire upstream is idle. Bars measure RSSI, not airtime, and airtime is the thing that is actually scarce.

You take a capture in monitor mode and see thousands of frames with the **Retry** bit set, **Duration** fields of several hundred microseconds reserving the channel, and two stations transmitting at wildly different PHY rates (6 Mb/s and 54 Mb/s). To explain the symptom you have to read the 802.11 MAC: how DCF shares the channel, how the NAV silences neighbors, and how the frame header encodes retries, fragments, and the third address. The 802.11 MAC sublayer is where "good signal but bad Wi-Fi" gets explained, because the bottleneck is the *protocol's* sharing rules, not the radio's reach.

## The Concept

### Why collision detection is impossible

Ethernet's CSMA/CD relies on a station hearing a collision on the wire within the first 64 bytes. A radio cannot do this: it is essentially **half duplex**, and its own transmit signal swamps the antenna so completely (the received signal can be ~10^6 times weaker) that it cannot detect a competing transmission *while sending*. So 802.11 cannot detect collisions; it can only **avoid** them and then **infer** failures from a missing acknowledgement. Every reliable exchange therefore ends in an explicit ACK — silence means "assume collision or error, retransmit."

### CSMA/CA and the Distributed Coordination Function (DCF)

DCF is the default, fully decentralized access mode — no AP scheduling. A station with a frame to send runs this loop (see `code/main.py`, which simulates it):

1. Sense the medium. If idle for a full **DIFS** (DCF InterFrame Spacing), proceed; if busy, defer.
2. Draw a random backoff count uniformly from `[0, CW]`, where the contention window starts at **CWmin = 15** slots on an OFDM PHY.
3. Count down one slot per idle slot time. **Pause** the counter whenever the medium goes busy (another station transmitting) and resume after it returns to idle for DIFS.
4. Transmit when the counter hits **0**.
5. The receiver, after only a **SIFS** (Short InterFrame Spacing, shorter than DIFS so nothing else can grab the channel first), returns an ACK.
6. No ACK before the ACK timer expires → inferred failure. Double the window (binary exponential backoff: 15 → 31 → 63 → … capped at **CWmax = 1023**) and retry, up to the retry limit, then report failure to the upper layer.

Two differences from Ethernet are worth stating precisely. First, backoff happens **before** sending (proactively), not only after a collision, because in wireless a collision wastes the *entire* frame — there is no early abort. Second, success is confirmed by an **ACK**, not by the absence of a noise burst.

Worked example: stations B and C both become ready while A is transmitting. Both wait for the channel to go idle after A's ACK, then back off. C draws 4 slots, B draws 9. C reaches 0 first and sends; B's counter freezes at 5 while C transmits and its ACK returns, then B resumes counting 5, 4, 3, 2, 1, 0 and sends. The early random backoff is exactly what kept B and C from colliding the instant the channel cleared.

### Interframe spacing: the priority ladder

The gap a station must see idle before it may transmit *is* its priority. Shorter gap = higher priority.

| Interval | Relative length | Used by | Effect |
|---|---|---|---|
| **SIFS** | shortest | ACK, CTS, next fragment in a burst | Continues an in-progress dialog before anyone else can interrupt |
| **AIFS (high)** | between SIFS and DIFS | 802.11e high-priority (e.g. voice) | AP jumps voice ahead of normal data |
| **DIFS** | baseline | Ordinary DCF data frames | Normal contention + backoff |
| **AIFS (low)** | longer than DIFS | Background/best-effort traffic | Deliberately defers to normal traffic |
| **EIFS** | longest | A station that just received a *bad/unknown* frame | Stays quiet to avoid stepping on a dialog it can't decode |

Because an ACK waits only SIFS while a fresh frame must wait DIFS, the ACK always wins the channel — the dialog is protected end to end. The 802.11e QoS extension adds four access categories with different AIFS and backoff parameters.

### Virtual carrier sense: the Duration field and the NAV

Physical sensing alone cannot solve the **hidden terminal problem**: A and C are both in range of B but not of each other, so A senses "idle" while C is busy transmitting to B, and A collides. The fix is **virtual** sensing. Every 802.11 frame carries a 2-byte **Duration** field stating, in microseconds, how long the *remaining* exchange (including its ACK) will occupy the channel. Any station that overhears the frame loads that value into its **Network Allocation Vector (NAV)** — a countdown timer — and treats the channel as busy until the NAV reaches zero, *whether or not it hears a physical signal*. The NAV is never transmitted; it is a purely local reminder to stay quiet.

The optional **RTS/CTS** handshake extends this to hidden terminals (diagrammed in `assets/the-802-11-mac-sublayer-protocol-to-the-802-11-frame-structure.svg`):

- A sends a short **RTS** (Request To Send) with a Duration covering CTS + data + ACK.
- B replies with **CTS** (Clear To Send), Duration covering data + ACK.
- Stations in range of A (e.g. C) hear the RTS and set their NAV; stations in range of B only (e.g. D) hear the CTS and set theirs. Now both sides of the link are silenced even though they cannot hear each other.

In practice RTS/CTS is rarely used: it adds two frames of overhead, does nothing for short frames or for the AP (which everyone hears), and — unlike the older MACA scheme — does *not* fix exposed terminals, because everyone who hears RTS *or* CTS goes quiet for the whole exchange.

### Reliability tricks: rate adaptation and fragmentation

Wireless links are noisy (microwave ovens share the 2.4 GHz ISM band). Two MAC-level levers raise the odds a frame survives. **Rate adaptation**: drop to a slower, more robust modulation when loss rises, and occasionally probe a higher rate when loss is low. **Fragmentation**: split a frame into smaller pieces, each with its own checksum, numbered and ACKed by a **stop-and-wait** rule — fragment *k+1* may not be sent until fragment *k* is acknowledged. The math is stark: if bit error rate `p = 1e-4`, a full 12,144-bit Ethernet-sized frame survives with probability `(1-p)^12144 ≈ 30%`, but a 4048-bit fragment survives with probability `≈ 67%`. Fragments are sent back-to-back as a **burst**, each separated by SIFS so no outsider can wedge in.

### The 802.11 data frame, field by field

`code/main.py` parses and builds this exact layout. Field widths (in bytes unless noted):

```
 2        2        6          6          6        2       0–2312   4
+--------+--------+----------+----------+--------+--------+-------+-----+
| Frame  |Duration| Address1 | Address2 |Address3| Seq.   | Data  | FCS |
|Control |        |(receiver)|(transmit)|(dist.) |Control |(LLC..)|CRC32|
+--------+--------+----------+----------+--------+--------+-------+-----+
```

The **Frame Control** field is 16 bits split into 11 subfields:

| Subfield | Bits | Meaning |
|---|---|---|
| Protocol version | 2 | `00` (lets future versions coexist in one cell) |
| Type | 2 | `10` = data, `01` = control, `00` = management |
| Subtype | 4 | `0000` = plain data; for control: ACK/RTS/CTS |
| To DS | 1 | Frame headed *into* the distribution system (to AP) |
| From DS | 1 | Frame coming *from* the distribution system |
| More Fragments | 1 | Another fragment follows |
| Retry | 1 | This is a retransmission |
| Power Management | 1 | Sender entering power-save (AP buffers for it) |
| More Data | 1 | AP has more buffered frames for a dozing client |
| Protected Frame | 1 | Body is encrypted |
| Order | 1 | Strict ordering required by upper layer |

The **To DS / From DS** pair selects how many addresses appear and what they mean — this is the single most misread part of an 802.11 capture:

| To DS | From DS | Scenario | Addr1 | Addr2 | Addr3 | Addr4 |
|---|---|---|---|---|---|---|
| 0 | 0 | IBSS / ad-hoc, station-to-station | DA | SA | BSSID | — |
| 0 | 1 | AP → client (downlink) | DA | BSSID | SA | — |
| 1 | 0 | Client → AP (uplink) | BSSID | SA | DA | — |
| 1 | 1 | WDS / AP-to-AP bridge | RA | TA | DA | SA |

In the common infrastructure case the frame has **three** addresses because the AP is a relay: Addr1 = immediate receiver, Addr2 = immediate transmitter, Addr3 = the distant endpoint (the other client or the Internet portal). The fourth address only appears in the 4-address WDS case.

The **Duration** field (2 bytes, microseconds) feeds neighbors' NAVs as above. The **Sequence Control** field is 16 bits: the low **4 bits are the fragment number** and the high **12 bits are the sequence number**, incremented per new MSDU so duplicates (e.g. an ACK lost so the sender resent) can be detected and discarded. The **Data** field holds up to **2312 bytes**, beginning with an **LLC** header that names the upper-layer protocol (e.g. IP). The **Frame Check Sequence** is the same **32-bit CRC** used by Ethernet. Management frames share this layout with a subtype-specific body (e.g. beacon parameters); control frames are short — Frame Control, Duration, FCS, often a single address and no payload.

### Two failure modes you will actually see

**NAV starvation / hidden-terminal collisions.** If a hidden station never hears the RTS or the data frame, it never sets its NAV and transmits into the middle of someone else's exchange. Evidence: bursts of Retry=1 frames, ACKs missing, throughput collapsing despite strong RSSI.

**The rate anomaly.** Under the original one-frame-per-turn rule, a fast 54 Mb/s sender and a slow 6 Mb/s sender each get one frame per round, but the slow frame hogs ~9× the airtime, dragging *both* down toward the slow rate (alone they get 54 and 6; together they average ~5.4 Mb/s each). The 802.11e **TXOP** (transmission opportunity) fixes this by granting equal *airtime* instead of equal *frame count*, so the example becomes 27 and 3 Mb/s — the fast sender keeps most of its advantage. This is the real cause of the "voice breaks up during a download" problem in The Problem section.

## Build It

`code/main.py` is a stdlib-only model of this lesson. It does three things you can run and inspect:

1. **Builds and parses an 802.11 data frame.** `build_data_frame()` packs Frame Control bits, Duration, three addresses, Sequence Control (fragment + sequence), payload, and a real CRC-32 FCS. `parse_data_frame()` decodes the bytes back into named fields and verifies the FCS.
2. **Decodes the To DS / From DS address mapping**, printing which address is DA/SA/BSSID for each of the four cases.
3. **Simulates DCF backoff** under repeated loss: `simulate_backoff()` shows the contention window doubling 15 → 31 → 63 → … and prints the drawn slot counts so you can see binary exponential backoff in action.

Steps to work it:

1. Run `python3 code/main.py` and read the printed frame hex dump and decode.
2. Flip the Retry bit and re-run; confirm the parser reports a retransmission.
3. Change `to_ds`/`from_ds` and watch the address roles relabel.
4. Increase the loss probability in the backoff sim and watch CW climb toward 1023.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame is a retransmission | Frame Control **Retry** bit = 1; identical **Sequence** number to a prior frame | You can tell a genuine retry from a new frame with the same destination |
| Read the address layout | **To DS / From DS** pair vs. Addr1/2/3 | You correctly name DA, SA, and BSSID for uplink, downlink, and ad-hoc |
| Explain channel reservation | **Duration** field value vs. neighbor silence | The microsecond Duration matches the observed quiet period (the NAV) |
| Diagnose airtime starvation | Mixed PHY rates + Retry bursts + low goodput | You attribute the slowdown to the rate anomaly / NAV, not to weak signal |
| Verify integrity | 32-bit **FCS** recomputed over the frame | Recomputed CRC matches the captured FCS |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **Wireshark display-filter cheat sheet** for 802.11: `wlan.fc.retry == 1`, `wlan.fc.type_subtype == 0x1c` (RTS), `wlan.duration`, `wlan.fc.ds`, `wlan.seq`.
- Or a **one-page DCF/NAV runbook** mapping each symptom (retry storms, voice break-up, hidden-terminal collisions) to the field that proves it.
- Or extend `code/main.py` into a small frame-builder you can paste captured hex into.

Start from the parser in `code/main.py` and the field diagram in `assets/the-802-11-mac-sublayer-protocol-to-the-802-11-frame-structure.svg`.

## Exercises

1. A capture shows two consecutive frames with the same 12-bit Sequence number but the second has Retry=1. The first frame had a valid FCS. What most likely happened, and which field would you check on the receiver's side to confirm the ACK was lost rather than the data frame?
2. Using `simulate_backoff()`, a station collides 5 times in a row. List the contention window after each collision and give the *range* of slots it draws from on attempt 6. At which collision does CW hit CWmax=1023?
3. You capture a downlink frame (AP → laptop) with To DS=0, From DS=1. Label Addr1, Addr2, Addr3 with DA/SA/BSSID and explain why the laptop's MAC is *not* in Addr2.
4. RTS/CTS is enabled on an AP that everyone in the cell can hear directly. Argue, using the overhead and the hidden-terminal definition, why this almost certainly *reduces* throughput here.
5. Bit error rate is `p = 5e-5`. Compute the success probability of a 12,144-bit frame versus a 3,036-bit fragment. By roughly what factor does fragmentation cut expected retransmissions?
6. A VoIP phone and a file-transfer laptop share the channel; voice degrades during transfers. Explain the rate anomaly with airtime numbers, then describe how a TXOP-based access category changes the outcome and which 802.11 amendment introduced it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CSMA/CA | "Wi-Fi's CSMA" | Carrier sense + *avoidance* via pre-transmission random backoff and ACK-inferred failure, because collisions can't be detected on a half-duplex radio |
| DCF | "the Wi-Fi MAC" | Distributed Coordination Function: fully decentralized contention with DIFS sensing, backoff, and ACKs — no central scheduler |
| NAV | "a busy flag" | Network Allocation Vector: a local countdown timer seeded by every frame's Duration field; virtual carrier sense |
| Duration field | "frame length" | A 2-byte microsecond reservation for the rest of the exchange (incl. ACK), used to set neighbors' NAVs — not the frame's size |
| SIFS vs DIFS | "two timers" | The short/long idle gaps that *encode priority*: SIFS-spaced ACK always beats a DIFS-spaced fresh frame |
| To DS / From DS | "direction bits" | The pair that selects 3- vs 4-address layout and remaps which address is DA, SA, BSSID, RA, TA |
| Sequence Control | "a counter" | 16 bits = 4-bit fragment number + 12-bit sequence number, for duplicate detection across retries |
| Retry bit | "resent flag" | Frame Control bit marking a retransmission; pairs with an unchanged Sequence number |
| Rate anomaly | "slow Wi-Fi" | A slow sender drags fast senders to its rate under equal-frame scheduling; fixed by TXOP equal-airtime grants |

## Further Reading

- **IEEE 802.11-2020** — base standard; Clause 10 (MAC), 9.2 (frame formats), DCF, NAV, interframe spacing.
- **IEEE 802.11e-2005** — QoS amendment: AIFS, access categories, TXOP (now folded into the base standard).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., **Section 4.4** "Wireless LANs" (4.4.3 MAC protocol, 4.4.4 frame structure).
- **RFC 1042** — IEEE 802 LLC/SNAP encapsulation that prefixes the Data field and identifies the upper-layer protocol (e.g. IP).
- Heusse, Rousseau, Berger-Sabbatel, Duda (2003), *Performance Anomaly of 802.11b* — the rate anomaly result.
- Wireshark 802.11 display-filter reference: `wlan.fc.*`, `wlan.duration`, `wlan.seq`, `wlan.ra`/`wlan.ta`/`wlan.da`/`wlan.sa`.
