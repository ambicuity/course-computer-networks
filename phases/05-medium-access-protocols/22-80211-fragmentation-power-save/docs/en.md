# 802.11 fragmentation bursts, ACKs, and power-save via beacon TIMs

> Wi-Fi fragments a long MSDU into smaller MPDUs so a noisy RF link does not waste a 1500-byte frame on a single bad bit, and the AP beacon's Traffic Indication Map (TIM) tells sleeping stations when to wake up. Each fragment is an independent 802.11 frame that shares the same Sequence Control number while its 4-bit Fragment Number increments from 0 to N-1; every fragment is acknowledged by the receiver after a SIFS interval, and the burst is held together by the Duration/NAV field which all other stations set to "channel busy" for the remaining time. A station that misses the SIFS window (any other station trying to seize the medium) is locked out: the only way back in is to wait for DIFS plus a fresh backoff. The Fragment Burst then goes DATA1, SIFS, ACK, SIFS, DATA2, SIFS, ACK... until the More Fragments bit in the Frame Control field goes to zero. Power saving rides on the same periodic beacon: the AP queues frames for clients that have set the Power Management bit, marks each queued Association ID in the TIM bitmap, and a sleeping client only wakes to receive its own bit. The legacy PS-Poll handshake pulls one buffered frame per poll, while 802.11e U-APSD (also called WMM Power Save) inverts the pattern: the client sends a trigger frame and the AP delivers a burst of queued downlink data in the same TXOP. Beacon interval is typically 100 TU (1 TU = 1024 us, so 100 TUs = 102.4 ms), and the DTIM (Delivery TIM) counter, embedded in every Nth beacon, tells clients when to wake for buffered broadcast or multicast traffic.

**Type:** Learn
**Languages:** Python
**Prerequisites:** CSMA/CA and DCF (Chapter 4 sections 4.4.1-4.4.2), 802.11 interframe spacing SIFS/DIFS, basic MAC frame format, ALOHA-style contention
**Time:** ~75 minutes

## Learning Objectives

- Decompose a long MSDU into MPDU fragments, assign a shared 12-bit Sequence Number and an incrementing 4-bit Fragment Number, and explain the role of the More Fragments and Retry bits in the Frame Control field.
- Diagram a fragment burst as DATA - SIFS - ACK - SIFS - DATA - SIFS - ACK and compute the Duration/NAV value that holds competing stations off the medium between the SIFS-separated exchanges.
- Build a 802.11 beacon frame carrying the timestamp, beacon interval, capability, SSID, supported rates, and a Traffic Indication Map (TIM) element with a partial virtual bitmap keyed by Association ID (AID).
- Trace the legacy PS-Poll power-save handshake and the 802.11e U-APSD trigger/delivery exchange, and explain how the DTIM interval decides when broadcast/multicast buffered traffic is released.
- Justify the choice of fragmentation threshold (typically 500-800 bytes) and the listen interval (typically 1-10 beacon intervals) from the perspectives of bit error rate, frame retransmission cost, and battery life.
- Read a printed beacon, locate the TIM IE, and predict which stations should send a PS-Poll in response.

## The Problem

You are designing the Wi-Fi firmware for a battery-powered doorbell camera and you have two contradictory signals from the field.

First, the link is dirty. The camera sits on the back of a steel door in a townhouse; multipath from the siding plus a kitchen microwave running on the same 2.4 GHz ISM band produces a per-bit error rate around p = 10^-4 on a typical frame. A 1500-byte MSDU is 12,000 bits, so the probability that the *whole* frame is received correctly is (1 - 10^-4)^12000, which works out to roughly 30%. Seven out of ten frames are silently corrupted, and CSMA/CA's exponential backoff punishes each one with a doubled retransmission window. Throughput collapses.

Second, the battery only lasts eight hours on standby. Wi-Fi is the dominant drain. The radio consumes roughly 200 mW while awake and under 1 mW while dozing, so the radio should be asleep roughly 99.5% of the time. But the AP keeps trying to push firmware updates and video previews at the camera, and the camera must wake often enough not to miss them.

The textbook response to the first problem is shorter frames: if the MSDU is split into three 500-byte fragments, the probability of any single fragment being received correctly is (1 - 10^-4)^4000 ≈ 67%, so the *whole* MSDU now succeeds with probability around 0.67^3 ≈ 30% per attempt before retransmission, but the cost of a single bad fragment is now one third of the MSDU's airtime. To keep the burst from being hijacked by a neighboring station, the fragments must be SIFS-apart and the Duration/NAV field of each one must reserve the channel for the next ACK plus the next fragment. The retry bit, the more-fragments bit, and the sequence control bits are the three flag fields in the MAC header that make this work.

The textbook response to the second problem is the beacon/TIM protocol. The AP transmits a beacon every 100 TUs (102.4 ms). The TIM element inside the beacon contains a 2007-bit partial virtual bitmap, one bit per Association ID. A camera that has set the Power Management bit only needs to wake for each beacon, read its own bit, and send a PS-Poll to retrieve buffered downlink traffic. For real-time voice, the same idea in reverse is 802.11e U-APSD: the camera transmits a trigger frame and the AP delivers all queued voice frames in the same TXOP, so the radio can return to doze state between talkspurt bursts.

This lesson dissects the fragment burst, builds a beacon/TIM generator, simulates a U-APSD exchange, and ties the two problems to the two halves of the 802.11 MAC sublayer.

## The Concept

The 802.11 MAC sublayer does two completely different jobs in the same frame format: it fragments for reliability over a noisy medium, and it schedules the radio's sleep cycles for power management. Both jobs are visible in the same Frame Control field, both reuse the same Sequence Control field, and both depend on the beacon that the AP broadcasts every 100 TU. The SVG shows a fragment burst on top and the TIM element layout on the bottom; `code/main.py` is a stdlib-only Python toolkit that splits a 1500-byte payload into three fragments, computes each Duration/NAV, builds a beacon with a TIM element for 8 stations, and simulates the PS-Poll and U-APSD handshakes.

### The fragmentation threshold

802.11 lets the AP (or, in an IBSS, any station) configure a `dot11FragmentationThreshold` between 256 and 2346 bytes. The classic value is somewhere between 500 and 800 bytes, which is short enough to recover gracefully from a few bit errors yet long enough to keep the per-fragment header overhead (about 34 bytes of MAC header plus a 4-byte FCS) under 10%. When an MSDU arrives from the LLC layer and its length exceeds the threshold, the MAC fragments it: each fragment is a full 802.11 frame with its own Frame Control, Duration, three Address fields, Sequence Control, fragment body, and Frame Check Sequence. The MSDU is reassembled at the receiver using the Sequence Number and the Fragment Number; the receiver discards any fragment with a bad FCS and waits for a retransmission, while continuing to buffer the fragments it has already received correctly.

The choice of threshold is a bit-error vs. overhead trade-off. If the threshold is too small, the per-frame header overhead dominates and throughput drops even on a clean channel. If the threshold is too large, a single bit error wastes a long transmission and CSMA/CA's exponential backoff dominates.

### The fragment burst pattern

Once the MAC has won the channel via DIFS plus a random backoff, it owns the channel for the entire fragment burst. The pattern is:

```
+-------+   SIFS   +-----+   SIFS   +-------+   SIFS   +-----+
| DATA1 |  ----->  | ACK |  ----->  | DATA2 |  ----->  | ACK | ...
+-------+          +-----+          +-------+          +-----+
   frag=0              (More=1)         frag=1
   More=1
```

The inter-frame spacing between DATA and ACK, and between ACK and the next DATA, is SIFS, not DIFS. SIFS is the *shortest* interframe space: 10 us for the 2.4 GHz OFDM physical layer, 16 us for the original 802.11 DSSS physical layer. Because SIFS is shorter than DIFS (34 us for OFDM, 50 us for DSSS), no other station that obeys CSMA/CA can seize the channel between the SIFS-separated exchanges: the only thing those stations hear is the SIFS-sized silence between DATA and ACK, and SIFS is by definition too short for a contending station to start its DIFS timer and backoff countdown.

The fragment carries the following flag bits in its Frame Control byte:

- **More Fragments** — set on every fragment except the last; tells the receiver "expect at least one more fragment with the same Sequence Number."
- **Retry** — set if this fragment is a retransmission of an earlier fragment that the receiver failed to acknowledge.
- **Order** — set if the higher layer asked for strict in-order delivery (used by some legacy 802.11 voice profiles).

The ACK frame itself carries a Duration value of 0 and a 16-bit Fragment Number copied from the fragment it acknowledges (except for the case where the More Fragments bit is 0, in which case the ACK's Duration is also 0 because the burst is over).

### Duration/NAV computation

Every 802.11 frame carries a 16-bit Duration field that other stations copy into their Network Allocation Vector. The NAV is a countdown timer; when it reaches zero, the station is allowed to contend for the channel again.

For a fragment in the middle of a burst, the Duration value is:

```
Duration = SIFS + t_ACK + SIFS + t_DATA_next
```

where t_ACK is the time to transmit a 14-byte ACK frame at the current physical rate (including preamble and PLCP header) and t_DATA_next is the time to transmit the next fragment at the current physical rate. As each ACK is sent, the receiver updates the duration so that the channel is reserved exactly long enough for the next exchange.

For the *last* fragment, the More Fragments bit is 0 and the Duration is 0; the burst is over and the channel is released.

### Frame control and sequence control bit fields

The 2-byte Frame Control field contains:

| Bit(s) | Field | Used by this lesson |
|---|---|---|
| 0-1 | Protocol Version | 0 (always) |
| 2-3 | Type | 0 (Management), 1 (Control), 2 (Data) |
| 4-7 | Subtype | Beacon=0x80, ACK=0xD0, PS-Poll=0xA4, QoS Data=0x28 |
| 8 | To DS | 0 or 1 (frame is going to the distribution system) |
| 9 | From DS | 0 or 1 (frame is coming from the distribution system) |
| 10 | More Fragments | 1 except on the last fragment of a burst |
| 11 | Retry | 1 if the frame is a retransmission |
| 12 | Power Management | 1 if the sender is going into doze state after this frame |
| 13 | More Data | 1 if the AP has additional buffered frames for the receiver |
| 14 | Protected Frame | 1 if the body is encrypted (WPA2/AES) |
| 15 | Order | 1 if strict in-order delivery is required |

The 2-byte Sequence Control field contains a 4-bit Fragment Number (low) and a 12-bit Sequence Number (high). All fragments of the same MSDU share the same Sequence Number; the Fragment Number increments 0, 1, 2... for each fragment. The Sequence Number advances by one only when a *new* MSDU is transmitted.

### Beacon frame structure

A beacon is a management frame (Type=0, Subtype=0x80) broadcast by the AP every beacon interval. The body of the beacon is a sequence of Information Elements (IEs), each of which is a 1-byte Element ID, a 1-byte Length, and a variable-length payload:

| IE | Element ID | Typical content |
|---|---|---|
| SSID | 0 | Network name |
| Supported Rates | 1 | Bit-rate set the AP can use |
| DS Parameter Set | 3 | Channel number |
| TIM | 5 | Partial virtual bitmap for power management |
| Country | 7 | Regulatory info (5 GHz) |
| HT Capabilities | 45 | 802.11n parameters |
| VHT Capabilities | 191 | 802.11ac parameters |

The fixed fields at the top of the beacon body are the 8-byte timestamp, 2-byte beacon interval (in TUs), 2-byte capability information (privacy, short preamble, QoS, etc.), and 2-byte SSID length. The TIM IE, which is the focus of power management, contains:

- 1-byte Element ID (5)
- 1-byte Length
- 1-byte DTIM Count (number of beacons until the next DTIM)
- 1-byte DTIM Period (DTIM periodicity in beacon intervals)
- 1-byte Bitmap Control (offset of the partial virtual bitmap + the traffic indicator for AID 0, the broadcast/multicast bit)
- N-byte Partial Virtual Bitmap (2007 bits maximum, packed LSB-first, one bit per AID)

The AP sets a 1 in the bitmap at bit position AID for every station that has a frame buffered in its power-save queue. The station wakes up, reads the TIM, and if its own AID bit is 1, it sends a PS-Poll to retrieve one buffered frame. The station is free to doze again immediately afterwards.

### The PS-Poll handshake

Legacy 802.11 power saving uses a one-frame-at-a-time poll. The sequence is:

1. Sleeping station wakes for the beacon and reads its AID bit. Bit=1 means there is buffered traffic.
2. Station transmits a PS-Poll frame to the AP. The PS-Poll is a control frame (Type=1, Subtype=0xA4) with the AID in the body.
3. AP sends exactly one buffered data frame (or a null data frame if the queue is empty) after SIFS.
4. Station sends an ACK after SIFS. If the More Data bit in the data frame is 1, the station polls again. Otherwise it dozes.

The PS-Poll handshake is wasteful for applications like VoIP where the station has traffic flowing in *both* directions every 20 ms or so: the radio must wake, send the PS-Poll, wait SIFS, receive one data frame, wait SIFS, send an ACK, and the cycle repeats. For every 20 ms talkspurt, the radio is awake for several milliseconds just to do housekeeping.

### U-APSD (WMM Power Save)

802.11e introduces Unscheduled Automatic Power Save Delivery (U-APSD), also called WMM Power Save. The station sends a *trigger frame* (a QoS Data frame with the EOSP bit cleared) to the AP. The AP responds with all queued downlink frames for that station inside a single TXOP, in the same exchange. The station sends a single QoS Null or QoS Data with the EOSP bit set as the final ACK-equivalent.

U-APSD fits VoIP exactly: a phone sends a voice packet upstream, the trigger wakes the AP, the AP delivers a voice packet (or several) downstream in the same TXOP, and both radios doze until the next talkspurt. The Listen Interval parameter still controls how often the station wakes for the beacon, but the bulk of the data movement happens on demand, not on the 100 TU beacon schedule.

### Doze state and Listen Interval

A station that has set the Power Management bit in an outgoing frame is in power-save mode. It may enter the doze state at any time when it has neither frames to transmit nor frames expected. The Listen Interval is the number of beacon intervals the station promises to sleep between wake-ups; an interval of 3 means the station only wakes every third beacon. The AP uses the Listen Interval to know how long it must buffer downlink frames before deciding that the station has roamed away.

The DTIM (Delivery TIM) counter inside every beacon counts down from the DTIM Period to 0. When it reaches 0, the beacon is a DTIM beacon, and the broadcast/multicast buffered traffic is released immediately after the DTIM beacon, with no PS-Poll required. Stations that care about broadcast or multicast (e.g. ARP, DHCP, mDNS) must wake for every DTIM beacon. The DTIM Period is typically 1 or 3, so a station that listens for broadcast traffic wakes every 100 ms (DTIM Period = 1) or every 307 ms (DTIM Period = 3).

## Build It

`code/main.py` is a stdlib-only Python module that mirrors the structure of the lesson.

1. **Fragmenter** — `fragment_msdu(payload, threshold, seq_num)` takes a 1500-byte payload and a threshold (default 500) and returns a list of fragment records. Each record contains the fragment body, the Fragment Number (0, 1, 2...), the More Fragments flag, and a computed Duration value assuming a 24 Mbps OFDM rate. The main function splits a 1500-byte MSDU into three fragments and prints the burst pattern.
2. **Beacon builder** — `build_beacon(timestamp, beacon_interval_tu, ssid, dtim_count, dtim_period, aids_with_buffered_traffic)` constructs a 802.11 beacon frame as a byte string: 24-byte MAC header (with a placeholder for the timestamp/interval/etc. in the body), followed by the SSID, Supported Rates, and TIM Information Elements. The TIM element's partial virtual bitmap is packed LSB-first.
3. **PS-Poll simulator** — `simulate_ps_poll(beacon, station_aid)` walks the legacy power-save exchange: read the TIM bit, send PS-Poll, receive data, send ACK, check More Data, repeat or doze.
4. **U-APSD simulator** — `simulate_uapsd(station_aid, num_downstream_frames)` walks the 802.11e trigger/delivery exchange: station sends a QoS Data trigger, AP responds with N frames, station sends a QoS Null with EOSP=1, both doze.
5. **Main** — calls the fragmenter on a 1500-byte payload, prints the burst, builds a beacon for 8 stations where stations 2, 5, and 7 have buffered traffic, prints the hex of the beacon, and runs the PS-Poll and U-APSD exchanges for station 5.

Run with `python3 code/main.py` and watch the burst timeline, the beacon bytes, and the two power-save handshakes.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Pick a fragmentation threshold | Per-bit error rate p, MSDU size | Threshold around 500-800 bytes for p in 10^-5 to 10^-4; below 200 bytes overhead dominates; above 1500 no improvement |
| Set More Fragments | Last fragment flag | 0 on the last fragment, 1 on every earlier fragment of the same burst |
| Read a TIM bitmap | Bit position = AID | Bit 3 set means AID 3 has at least one buffered frame; bit 0 is the broadcast/multicast indicator |
| Choose DTIM Period | Broadcast/multicast traffic mix | 1 if the station must catch every ARP/DHCP/mDNS, 3 if it can tolerate 300 ms of broadcast latency |
| Predict doze schedule | Listen Interval N, beacon interval B | Station wakes every N*B TU; AP buffers for at least N*B TU before assuming the station has roamed |
| Trace a fragment burst | Sequence Control field | Same Sequence Number, incrementing Fragment Number; receiver reassembles in order, drops bad fragments, requests retransmit |

Wireshark filters: `wlan.fc.type == 2 && wlan.fc.subtype == 0x08` (data frames only), `wlan.fc.more_frag == 1`, `wlan.tim.aid == 5`, `wlan.fc.type == 0 && wlan.fc.subtype == 0x80` (beacons).

## Ship It

Produce one reusable artifact under `outputs/`:

- A **fragment-burst cheat sheet**: a one-page diagram of DATA - SIFS - ACK - SIFS - DATA with the Duration/NAV value, Frame Control flags, and Sequence Control bytes annotated for each step.
- A **TIM/BITMAP decoder** that takes a beacon hex dump and prints the SSID, beacon interval, DTIM count/period, and the list of AIDs with buffered traffic.
- The **fragmenter + beacon builder** (`code/main.py`) wired to a test MSDU and a test 8-station virtual bitmap.

Start from `outputs/prompt-80211-fragmentation-power-save.md`.

## Exercises

1. A 1500-byte MSDU is sent over a 24 Mbps OFDM link with a fragmentation threshold of 500 bytes. Compute the total on-air time for the entire burst including the three SIFS intervals and the two ACK frames (use 14-byte ACK body + 20 us preamble/PLCP). Then change the threshold to 300 and recompute. Which choice wins at p = 10^-4 if the cost of a retransmission is the full airtime?
2. The AP has 8 associated stations. Stations with AIDs 1, 4, 5, and 7 each have one buffered frame; the broadcast queue has one frame. Draw the TIM element bytes (Element ID, Length, DTIM Count, DTIM Period, Bitmap Control, Partial Virtual Bitmap) when DTIM Count=2, DTIM Period=3, and the partial virtual bitmap offset is 0.
3. A station sends a PS-Poll with AID=4, receives a data frame with More Data=1, sends an ACK, and the AP has two more frames buffered. Trace the next three SIFS-spaced exchanges and decide when the station can doze.
4. A 2.4 GHz OFDM physical layer uses SIFS=10 us, DIFS=34 us, slot time=9 us, ACK rate=24 Mbps, and data rate=54 Mbps. A 500-byte fragment takes 74 us + 20 us preamble = 94 us on air. Compute the Duration value (in microseconds) the sender places in fragment 0 of a 3-fragment burst so the channel is reserved correctly through fragment 1 and its ACK.
5. A doorbell camera's standby current budget is 0.5 mA average at 3.7 V. The radio draws 200 mA when awake and 0.05 mA when dozing. The beacon interval is 100 TU (102.4 ms) and the camera wakes for 2 ms per beacon plus 5 ms per U-APSD trigger exchange (one every 100 ms). Compute the average current and the expected battery life on a 1500 mAh cell.
6. Run `code/main.py` and verify that the fragmenter assigns Fragment Numbers 0, 1, 2 to the three fragments of a 1500-byte MSDU with a 500-byte threshold, and that the beacon builder produces a TIM element whose bit 5 is set when AID 5 is passed in as having buffered traffic.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| MSDU | "the data we want to send" | MAC Service Data Unit — the full payload that LLC hands to the MAC; what gets fragmented |
| MPDU | "a fragment" | MAC Protocol Data Unit — one fragment after splitting; one 802.11 frame with its own header and FCS |
| Fragmentation threshold | "how small to cut" | `dot11FragmentationThreshold`, typically 500-800 bytes; MSDUs longer than this are split into MPDUs |
| More Fragments | "any more coming?" | Frame Control bit, 1 except on the last fragment of a burst |
| Retry | "resend" | Frame Control bit, 1 on a retransmission of a fragment the receiver did not ACK |
| Sequence Number | "frame ID" | 12-bit field shared by all fragments of one MSDU; advances by one per new MSDU |
| Fragment Number | "piece ID" | 4-bit field that increments 0, 1, 2... for each fragment of the same MSDU |
| Duration / NAV | "channel busy time" | 16-bit microsecond countdown that other stations copy into their Network Allocation Vector |
| SIFS | "short wait" | Short InterFrame Spacing — 10 us (OFDM 2.4 GHz), used inside a fragment burst or ACK exchange |
| DIFS | "regular wait" | DCF InterFrame Spacing — 34 us (OFDM 2.4 GHz), what a station waits before contending |
| Beacon | "the AP's heartbeat" | Management frame broadcast every beacon interval (typically 100 TU = 102.4 ms) |
| TIM | "who has mail?" | Traffic Indication Map Information Element; partial virtual bitmap of AIDs with buffered traffic |
| DTIM | "broadcast wake-up" | Delivery TIM; every Nth beacon releases buffered broadcast/multicast traffic without a poll |
| AID | "the slot number" | Association ID, 1-2007, identifies a station within its BSS; bit position in the TIM bitmap |
| PS-Poll | "give me my frame" | Control frame a sleeping station sends to retrieve one buffered downlink frame |
| U-APSD | "deliver on demand" | 802.11e Unscheduled Automatic Power Save Delivery; trigger frame pulls a burst of downlink frames in one TXOP |
| Listen Interval | "how often I wake" | Number of beacon intervals between wake-ups; AP must buffer for at least this long |
| Doze | "radio asleep" | Low-power state with the radio off; station consumes under 1 mW |
| TU | "802.11 time unit" | Time Unit = 1024 microseconds; 100 TU = 102.4 ms = the typical beacon interval |

## Further Reading

- **IEEE 802.11-2007** (and current IEEE 802.11-2020) — the authoritative standard; §7.1.3 fragmentation, §7.1.3.1.3 Retry, §7.1.3.1.4 Power Management, §11.1.2 TIM, §11.2.1 PS-Poll.
- **IEEE 802.11e-2005** — U-APSD and HCF (Hybrid Coordination Function), now part of IEEE 802.11-2007 chapter 11.
- Matthew Gast, *802.11 Wireless Networks: The Definitive Guide* (O'Reilly) — Chapter 4 on the 802.11 MAC and Chapter 13 on power saving.
- Matthew Gast, *802.11n, 802.11ac, and 802.11ax* (O'Reilly) — modern frame format and HT/VHT Control fields.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.4 "Wireless LANs" — the source chapter.
- Perahia & Stacey, *Next Generation Wireless LANs: 802.11n and 802.11ac* (Cambridge) — the fragment burst and TIM in the modern context.
