# The Internet to Wireless LANs 802.11

> The Internet is a network of networks with no central owner; the last hop for most laptops and phones is an IEEE 802.11 (Wi-Fi) wireless LAN, and that final link behaves nothing like Ethernet. Because radios are half-duplex and cannot reliably hear a collision while transmitting, 802.11 abandons CSMA/CD and uses **CSMA/CA** — Carrier Sense Multiple Access with *Collision Avoidance* — built on the Distributed Coordination Function (DCF). DCF arbitrates with carrier sensing, an interframe spacing hierarchy (SIFS 10 µs, DIFS 28/34 µs in 2.4/5 GHz), a randomized backoff counter drawn from a contention window that doubles on every failure (CW 15 → 31 → … → 1023), and mandatory link-layer ACKs after every unicast data frame. The classic failure is the **hidden terminal** — two stations that can both reach the AP but not each other, so they collide repeatedly at the AP with no way to sense it — solved by an optional RTS/CTS handshake that publishes a Network Allocation Vector (NAV) duration so neighbors defer. This lesson shows the 802.11 MAC frame fields, the DCF state machine, and a runnable backoff/hidden-terminal simulator so you can predict throughput collapse before it bites you in a packet capture.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 lessons 01–07 (layering, links, broadcast vs. point-to-point, framing)
**Time:** ~75 minutes

## Learning Objectives

- Explain why 802.11 uses CSMA/CA with positive ACKs instead of Ethernet's CSMA/CD, in terms of radio half-duplex and the capture problem.
- Lay out the 802.11 MAC data frame fields (Frame Control, Duration/ID, the three/four address fields, Sequence Control, FCS) and explain why there are up to four addresses.
- Trace the DCF timing hierarchy (SIFS → PIFS → DIFS → backoff slots) and compute a station's backoff in microseconds.
- Describe the hidden-terminal and exposed-terminal problems and how RTS/CTS plus the NAV (virtual carrier sense) mitigate the first.
- Compute the binary exponential backoff contention-window growth (CW_min=15 to CW_max=1023) after N consecutive collisions.
- Read a Wi-Fi capture and identify retries (Retry bit), backoff stalls, and NAV-driven deferral as distinct failure signatures.

## The Problem

A user files a ticket: "Video call freezes for 2–3 seconds every minute in the east conference room, but my laptop says full signal bars and 866 Mbps link rate." Bandwidth tests there show 40 Mbps; wired clients on the same switch are fine; the cloud dashboard shows healthy servers. The application team blames the WAN.

The signal is strong, so the obvious "weak Wi-Fi" story is wrong. The fault lives in the 802.11 MAC layer: another laptop and an IoT sensor on the same AP cannot hear each other (concrete walls between them), so they keep colliding *at the AP*. Each collision triggers a retransmission, doubles a contention window, and burns airtime. "Full bars" measures received signal strength — it says nothing about contention, retries, or channel utilization. Fixing this means reasoning about carrier sense, backoff, ACK timeouts, and the hidden-terminal problem, not throughput numbers on a marketing sheet.

## The Concept

### Why the Internet's last hop is special

The Internet is "a vast collection of different networks" glued by common protocols — nobody planned it, nobody controls it. IP makes all those heterogeneous links look uniform to the layers above, but the physical reality differs wildly hop to hop. The first hop for most devices today is 802.11: a *shared broadcast medium* over the air. A wired switched Ethernet link (IEEE 802.3) gives each host a dedicated full-duplex wire to a switch port — microseconds of delay, almost no errors, 1–10 Gbps. Wi-Fi shares one half-duplex radio channel among every associated station and the AP, with frame error rates orders of magnitude higher. The MAC layer is where that contention gets arbitrated.

### CSMA/CA: why not CSMA/CD?

Ethernet's classic algorithm is **CSMA/CD** — listen, transmit if idle, and *detect collisions* by sensing your own signal getting corrupted on the wire, then abort and back off. Radios cannot do the "CD" part: a transmitting station's own outgoing signal is roughly a million times stronger than a distant station's incoming signal at its own antenna, so it is deaf to collisions while sending (half-duplex capture). 802.11 therefore uses **collision *avoidance*** plus explicit acknowledgement:

1. **Carrier sense** — both *physical* (is the radio energy above threshold?) and *virtual* (is the NAV timer non-zero?). The medium must be idle.
2. **Random backoff before transmit**, not just after a collision — every station that has been waiting picks a random slot count, so two stations that were both deferring rarely fire on the same slot.
3. **Positive ACK** — the receiver returns an ACK frame a SIFS later. No ACK means the sender assumes loss and retransmits. Loss is the *only* collision signal Wi-Fi has.

### The DCF timing hierarchy

DCF (Distributed Coordination Function) is the baseline contention-based access. It uses **interframe spaces (IFS)** — fixed gaps that create priority. Shorter wait = higher priority.

| IFS | 802.11 (2.4 GHz HR/DSSS) | 802.11a/g/n (OFDM) | Used by |
|---|---|---|---|
| SIFS | 10 µs | 16 µs | ACK, CTS, the second frame of a burst — highest priority |
| SlotTime | 20 µs | 9 µs | unit of backoff counting |
| PIFS = SIFS + 1 slot | 30 µs | 25 µs | PCF / contention-free polling |
| DIFS = SIFS + 2 slots | 50 µs | 34 µs | normal DCF data access |

A station with data waits until the medium is idle for one **DIFS**, then counts down a backoff counter, one **SlotTime** per idle slot. If the medium goes busy mid-countdown, it *freezes* the counter and resumes after the next DIFS — it does not restart. ACKs go out after only a **SIFS**, so an in-progress exchange always wins against a new contender. See `assets/the-internet-to-wireless-lans-802-11.svg` for the SIFS/DIFS/backoff timeline.

### Binary exponential backoff and the contention window

The backoff counter is a uniform random integer in `[0, CW]` slots, where CW is the **contention window**. CW starts at `CW_min = 15` and doubles on each failed transmission (no ACK), capping at `CW_max = 1023`:

```
attempt 1: CW = 15    backoff ∈ [0,15]   slots
attempt 2: CW = 31    backoff ∈ [0,31]
attempt 3: CW = 63
attempt 4: CW = 127
...
attempt 7+: CW = 1023 (capped)
```

After a successful ACK, CW resets to `CW_min`. With OFDM 9 µs slots, a third-attempt frame can wait up to `63 × 9 = 567 µs` just in backoff before it even starts — pure airtime burned by contention, which is exactly what the conference-room ticket was feeling. `code/main.py` runs this exact backoff math and a multi-station contention simulation.

### The 802.11 MAC data frame

A unicast data frame (simplified, lengths in bytes):

```
+----+----+----------+----------+----------+----------+----------+ ... +-----+
| FC | Dur| Address1 | Address2 | Address3 |  SeqCtl  | Address4 | data| FCS |
+----+----+----------+----------+----------+----------+----------+ ... +-----+
  2    2       6          6          6          2          6      0-2312  4
```

- **Frame Control (FC, 2 B)** — Protocol Version, Type (mgmt/control/data), Subtype, and crucial flag bits: **ToDS / FromDS** (which way the frame is going relative to the distribution system), **Retry** (set on any retransmission — your single most useful diagnostic bit), More Fragments, Power Mgmt, Protected (encrypted).
- **Duration/ID (2 B)** — microseconds this exchange will occupy the medium; every neighbor copies it into its **NAV** and defers. This is *virtual* carrier sense.
- **Address1** is always the immediate receiver (RA), **Address2** the immediate transmitter (TA), **Address3** usually the "other end" (the BSSID or the ultimate source/dest). **Address4** appears *only* when both ToDS and FromDS are set — i.e., a wireless-distribution-system (WDS) bridge/mesh link between two APs — which is why 802.11 needs up to four addresses while Ethernet needs two.
- **Sequence Control (2 B)** — 4-bit fragment number + 12-bit sequence number, so a receiver can drop duplicates after an ACK is lost and the sender retries.
- **FCS (4 B)** — CRC-32 over the frame; a single bad bit fails the check and the frame is silently dropped (no ACK), triggering the retry path.

### Hidden terminals, exposed terminals, and RTS/CTS

The defining wireless pathology: **carrier sense is local to the listener, not the receiver.** Stations A and C both associate to AP B but are out of radio range of *each other*. A senses the channel idle (cannot hear C), C senses idle (cannot hear A), both transmit, both frames collide *at B*. Neither sender sensed a problem — they are **hidden terminals**, and throughput collapses as CW keeps doubling under repeated loss.

The fix is the optional **RTS/CTS** handshake:

1. A sends a short **RTS** (Request To Send) to B carrying a Duration value.
2. B replies with a **CTS** (Clear To Send) after a SIFS, echoing the Duration.
3. *Everyone in range of B* — including the hidden C — hears the CTS, sets its NAV for that Duration, and stays silent.
4. A sends data; B ACKs.

RTS/CTS converts the hidden node into a node that defers virtually. It costs two extra short frames, so 802.11 only uses it above the **RTS threshold** (commonly 2347 bytes = effectively off, or tuned down to ~500 in dense/hidden environments). The mirror problem, the **exposed terminal**, is where a station needlessly defers because it hears a transmitter whose receiver is elsewhere — RTS/CTS does *not* fully solve this, and it is a real source of wasted airtime.

### Infrastructure vs. ad-hoc, and association

Most Wi-Fi runs in **infrastructure mode (BSS)**: an **AP** (Access Point / wireless router / base station) relays every frame, even between two wireless clients in the same room — they each transmit to the AP, which retransmits, doubling airtime cost. A device joins by **scanning** (passive: listen for Beacon frames every ~102.4 ms; or active: probe request/response), **authenticating**, then **associating** for an Association ID. **IBSS / ad-hoc** mode lets stations talk peer-to-peer with no AP. The Beacon advertises the BSSID, supported rates, and capabilities; losing beacons is how a client decides to roam.

## Build It

1. Read `code/main.py` end to end — it has three pieces: a `parse_frame_control` bit decoder, a `backoff_window` exponential-backoff calculator, and a `simulate_dcf` discrete-event contention/hidden-terminal simulator.
2. Run `python3 code/main.py`. Confirm the Frame Control decode prints Type/Subtype, ToDS/FromDS, and the Retry bit.
3. Read the CW table it prints and verify by hand that attempt 3 gives CW=63.
4. Run the DCF simulation with all stations mutually audible, then flip `hidden=True` and watch collisions and average backoff climb — this reproduces the conference-room symptom.
5. Sketch the SIFS/DIFS/backoff timeline yourself and compare against `assets/the-internet-to-wireless-lans-802-11.svg`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | 802.11 MAC frame in a capture (radiotap + Type/Subtype), not the IP header | You explain "full bars, low throughput" as MAC contention, not signal or WAN |
| Confirm normal access | DIFS gap, single backoff, data, SIFS, ACK in the timeline | One clean data/ACK exchange per attempt; Retry bit clear |
| Diagnose hidden terminals | High **Retry**-bit rate, rising channel utilization, no RTS/CTS frames | Collisions at the AP, CW growth; enabling RTS/CTS or relocating the node restores throughput |
| Read backoff stalls | NAV/Duration values pinning neighbors silent; frozen backoff during busy medium | Deferral matches advertised Duration; airtime accounted for |

## Ship It

Create one artifact under `outputs/`:

- A one-page **hidden-terminal runbook**: the Retry-bit + channel-utilization checklist, the RTS-threshold tuning decision, and the "signal strength ≠ throughput" explanation for the helpdesk.
- Or the annotated 802.11 frame field reference (FC flags, four-address rules, NAV semantics).
- Or extend `code/main.py` into a Wireshark-display-filter cheat sheet generator (`wlan.fc.retry == 1`, `wlan.fc.type_subtype == 0x1b` for RTS, etc.).

Start with [`outputs/prompt-the-internet-to-wireless-lans-802-11.md`](../outputs/prompt-the-internet-to-wireless-lans-802-11.md).

## Exercises

1. A station's first two transmissions of a 1500-byte frame get no ACK. Compute the worst-case backoff time (in µs) before the *third* attempt starts, assuming OFDM 9 µs slots and CW doubling from CW_min=15. Show the CW value used.
2. Two associated stations A and C are hidden from each other. Explain, frame by frame, why enabling RTS/CTS with a threshold of 400 bytes fixes their collisions but RTS/CTS at the default 2347-byte threshold does nothing for their 300-byte VoIP packets.
3. In a capture you see a data frame where both ToDS and FromDS bits are set and there are four address fields. What kind of link is this, and what do Address3 and Address4 mean here?
4. The exposed-terminal problem: draw four stations A–B–C–D in a line (each hears only neighbors) and show a case where B needlessly defers to A even though B's intended receiver C is free. Explain why RTS/CTS does not recover this lost airtime.
5. Two wireless clients in the same room, both associated to one AP, transfer a file to each other. Explain why this uses *twice* the airtime of a wired switch path, and identify which address fields carry the AP's BSSID on each leg.
6. A client reports it "dropped Wi-Fi" though it never moved. Beacons from its AP stopped arriving for 800 ms. Walk through scanning → authentication → association and explain what evidence distinguishes a roam from a deauth attack.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CSMA/CA | "Wi-Fi's version of Ethernet" | Collision *avoidance* with pre-transmit random backoff and mandatory ACKs, because radios can't detect collisions while sending |
| DCF | "the Wi-Fi MAC" | Distributed Coordination Function: the contention-based access method using IFS + backoff + ACK |
| SIFS / DIFS | "Wi-Fi timing gaps" | Interframe spaces that create priority — SIFS (10/16 µs) for ACKs, DIFS for new data access |
| Contention window (CW) | "the backoff number" | Range [0,CW] of slots, doubling 15→1023 on each failed ACK (binary exponential backoff) |
| NAV | "virtual carrier sense" | A countdown timer set from a frame's Duration field; neighbors defer without sensing energy |
| Hidden terminal | "weak signal collision" | Two stations that reach the AP but not each other and collide *at the receiver* with no local collision signal |
| RTS/CTS | "Wi-Fi handshake" | Short Request/Clear-To-Send frames that publish a Duration so hidden nodes set their NAV and defer |
| Retry bit | "a resend flag" | FC flag set on every retransmission — the primary capture signature of contention/loss |
| BSSID / AP | "the router's MAC" | The MAC identity of the basic service set; the AP relays every frame, even client-to-client |

## Further Reading

- **IEEE 802.11-2020** — the consolidated Wireless LAN MAC and PHY standard (DCF, frame formats, NAV, RTS/CTS).
- **IEEE 802.3** — Ethernet, for the CSMA/CD contrast.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — §1.5 (example networks) and Chapter 4 (the MAC sublayer; 802.11 in depth).
- Gast, M., *802.11 Wireless Networks: The Definitive Guide* (O'Reilly) — frame-by-frame field reference.
- **RFC 793 / RFC 9293** (TCP) — why MAC-layer retries matter to the transport above: link retransmission hides loss from TCP but inflates RTT.
- Wireshark Wi-Fi display-filter reference: `wlan.fc.retry`, `wlan.fc.type_subtype`, `wlan.duration` for the evidence above.
