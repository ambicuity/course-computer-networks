# Mobile Users to Personal Area Networks

> Mobility and wireless are two independent axes, not one: a notebook plugged into a hotel jack is *mobile but wired*; a desktop on home Wi-Fi is *wireless but fixed*. The smallest wireless scale is the **Personal Area Network (PAN)**, ~1 m around one person, dominated by **Bluetooth** (standardized as **IEEE 802.15.1**). Bluetooth uses the **master/slave piconet**: one master clocks up to **7 active slaves** (3-bit Active Member Address, **AM_ADDR 1–7**; address `000` is reserved for broadcast), plus up to 255 parked slaves addressed by an 8-bit **PM_ADDR**. It hops across **79 1-MHz channels** in the 2.4 GHz ISM band at **1600 hops/s** (one hop per **625 µs** slot) using **Adaptive Frequency Hopping (AFH)** to dodge Wi-Fi interference. Failure modes are concrete: collisions with 802.11 on 2.4 GHz, the 8th device that cannot join an active piconet, and a slave that drifts out of the master's clock and must re-page. This lesson makes those numbers observable and gives you a piconet/address simulator you can run.

**Type:** Learn
**Languages:** Diagrams, standards
**Prerequisites:** Phase 1 · Lesson 01 (network uses and goals); basic binary/addressing
**Time:** ~70 minutes

## Learning Objectives

- Separate the two orthogonal axes — *wireless vs wired* and *mobile vs fixed* — and place real devices in the correct quadrant of the 2×2.
- Explain why the PAN sits at the ~1 m / square-meter scale in the distance-based network taxonomy and what technology fills it (Bluetooth, RFID, NFC).
- Describe the Bluetooth **piconet** master/slave model: the 3-bit AM_ADDR space, the 7-active-slave limit, parked members, and the role of the master clock.
- Compute which Bluetooth time slot a device may transmit in, given the 625 µs slot and 1600 hops/s frequency-hopping schedule.
- Identify the observable evidence (active-member count, AM_ADDR assignment, hop sequence, AFH channel map) that proves normal PAN behavior, and name at least one failure mode it would reveal.

## The Problem

A user complains: "My Bluetooth mouse stutters and my wireless headset cuts out — but *only* when I'm streaming video on Wi-Fi." Another asks why a sixth gamepad refuses to pair with a console that already has five controllers and a headset connected. A third reports that a fitness tracker "loses connection" every time they walk to the far end of the office.

These look like three unrelated bugs. They are all PAN-layer behaviors with concrete, countable causes: **2.4 GHz spectrum contention** between Bluetooth and 802.11, the **hard 7-active-slave limit** of a single piconet, and **range/clock-synchronization loss** that forces a re-page. An engineer who knows the piconet mechanism reduces each vague symptom to a specific field, counter, or timer — instead of "rebooting and hoping."

## The Concept

PANs are the smallest scale in the distance-based classification of networks. Where a LAN spans a building (~100 m) and a WAN spans a country (~1000 km), a PAN spans the **square meter around a single person** (~1 m). The point of a PAN is not bandwidth — it is *getting rid of cables* between a device and its peripherals (mouse, keyboard, headset, watch, medical remote).

### Two axes: wireless ≠ mobile

The most common conceptual error is treating "wireless" and "mobile" as the same thing. They are independent. Map every device onto this 2×2:

| | **Fixed (does not move)** | **Mobile (moves while in use)** |
|---|---|---|
| **Wired** | Desktop PC in an office | Notebook plugged into a hotel-room jack |
| **Wireless** | Desktop on home Wi-Fi in an un-cabled building | Handheld scanner doing store inventory; phone on cellular |

The lesson: a hotel notebook on an Ethernet cable has **mobility without wireless**, and a desktop on home Wi-Fi has **wireless without mobility**. Knowing the quadrant tells you whether the failure can possibly involve radio (interference, range, hopping) at all. The 2×2 is rendered in [`assets/mobile-users-to-personal-area-networks.svg`](../assets/mobile-users-to-personal-area-networks.svg).

### The PAN scale in the taxonomy

| Interprocessor distance | Processors located in | Example |
|---|---|---|
| **1 m** | **Square meter** | **Personal area network** |
| 10 m | Room | Local area network |
| 100 m | Building | Local area network |
| 1 km | Campus | Local area network |
| 10 km | City | Metropolitan area network |
| 100–1000 km | Country / continent | Wide area network |
| 10,000 km | Planet | The Internet |

PAN technologies are chosen for *short range and low power*, not throughput. The two dominant ones: **Bluetooth** (active, battery-powered, IEEE 802.15.1) and **RFID/NFC** (RFID tags are *passive* — no battery — readable over up to a few meters; NFC works at a few centimeters and lets a phone act like an RFID smartcard for payment).

### The Bluetooth piconet: master/slave

In its simplest form Bluetooth uses the **master-slave paradigm**. One device — normally the more capable one, e.g. the PC or the phone — is the **master**. The peripherals (mouse, keyboard, headset) are **slaves**. The master alone decides:

- which addresses slaves use,
- when each slave may transmit,
- how long it may transmit,
- which frequencies (the hop schedule) it uses.

A master plus its slaves is a **piconet**. The addressing is the load-bearing detail:

| Field | Width | Range | Meaning |
|---|---|---|---|
| **AM_ADDR** (Active Member Address) | 3 bits | `001`–`111` (1–7) | Identifies an active slave inside the piconet |
| `000` | 3 bits | reserved | **Broadcast** to all slaves (so it is *not* a usable unit address) |
| **PM_ADDR** (Parked Member Address) | 8 bits | 1–255 | Identifies a parked (low-power, not actively scheduled) slave |

Because the active address is 3 bits and one code is reserved for broadcast, a piconet has **at most 7 active slaves**. This is exactly why the "8th device won't join" symptom is structural, not a bug — see the worked example below and `code/main.py`, which models AM_ADDR allocation and rejects the 8th joiner.

### Frequency hopping and time slots

Bluetooth lives in the **2.4 GHz ISM band**, shared (license-free) with Wi-Fi, microwave ovens, and cordless phones. To survive that crowd it uses **Frequency-Hopping Spread Spectrum (FHSS)**: it divides the band into **79 channels of 1 MHz each** and hops pseudo-randomly across them at **1600 hops per second**. One hop occupies one **time slot of 625 µs** (because 1 / 1600 s = 625 µs).

The master's clock defines slot numbering. The rule is simple and testable:

- The **master transmits in even-numbered slots**; **slaves transmit in odd-numbered slots** (a slave only speaks after the master has addressed it). This is Time-Division Duplex (TDD).
- Worked timing example: a packet that begins at slot *k* and occupies a single slot ends 625 µs later at slot *k*+1, on a *different* of the 79 frequencies. A multi-slot packet (1, 3, or 5 slots) stays on the frequency of its starting slot for its whole duration, then the hop sequence resumes as if the skipped slots had been used.

Modern Bluetooth adds **Adaptive Frequency Hopping (AFH)**: the master measures which channels are jammed (e.g. by an overlapping Wi-Fi channel) and removes them from the hop set, keeping ≥ 20 channels. AFH is *the* defense against the "stutters only while Wi-Fi is busy" complaint.

### Worked example: the 8th controller

A games console (master) already has connected: 2 controllers, 1 headset, 1 keyboard, and a media remote — **5 active slaves**, holding AM_ADDRs `001`–`101`. A friend brings 2 more controllers.

1. Controller #6 pages in → master assigns AM_ADDR `110` (6). OK.
2. Controller #7 pages in → master assigns AM_ADDR `111` (7). OK — the address space is now full (`001`–`111`).
3. Controller #8 pages in → **no free AM_ADDR**. The master must either *park* an existing slave (move it to an 8-bit PM_ADDR, freeing its AM_ADDR) or **reject** the join. Result the user sees: "won't connect."

This is the difference between a capacity limit you can *predict from the field width* and a flaky radio. `code/main.py` prints exactly this rejection.

### Range, clock loss, and re-paging

A slave stays in sync by tracking the master's clock and hop sequence. Walk too far (Bluetooth class 2 radios target ~10 m) and received signal drops below sensitivity; the slave misses slots, loses clock lock, and the link supervision timer expires (commonly **~20 s** / `supervisionTimeout`). The slave then drops to standby and must be **paged** again to rejoin — the "loses connection when I walk away" symptom. The evidence is the supervision-timeout expiry and the subsequent page/inquiry exchange, not a hardware fault.

## Build It

1. Read `code/main.py`. It models a `Piconet` with a master and an AM_ADDR allocator (3-bit, broadcast reserved), a parking path to PM_ADDR, and an FHSS slot/frequency scheduler.
2. Run it: `python3 code/main.py`. Watch it admit 7 slaves, **reject the 8th**, then park one and admit the previously-rejected device.
3. Read the slot scheduler output: it prints, for slots 0–9, which side transmits (master/slave, even/odd) and the pseudo-random channel index in 0–78.
4. Change `NUM_JOINERS` to 9 and re-run. Confirm the structural 7-active limit, not a random failure.
5. Map each printed line back to a field in the tables above (AM_ADDR, PM_ADDR, slot parity, channel).

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify a device | The wireless/mobile 2×2 quadrant | You can say whether radio (interference/range) can possibly be involved before touching a tool |
| Confirm a healthy piconet | Active-member count ≤ 7, assigned AM_ADDRs, master clock locked | Observed active members and addresses match the 3-bit limit |
| Diagnose "won't join" | Count of active slaves; whether a park was attempted | You attribute it to AM_ADDR exhaustion, not "bad pairing" |
| Diagnose "stutters with Wi-Fi" | AFH channel map; overlapping 2.4 GHz Wi-Fi channel | Jammed 1-MHz channels are dropped from the hop set; interference, not the device, is the cause |
| Diagnose "drops when I walk away" | Link-supervision-timeout expiry, then page/inquiry | Range/clock loss explains it; re-page restores the link |

## Ship It

Produce one artifact under `outputs/`:

- A **piconet capacity + interference runbook** (the 7-active limit, AFH channel-map check, supervision-timeout symptom) — start from [`outputs/prompt-mobile-users-to-personal-area-networks.md`](../outputs/prompt-mobile-users-to-personal-area-networks.md).
- Or extend `code/main.py` into a CLI that takes a device list and prints the admit/park/reject decision plus the slot schedule.

## Exercises

1. A car infotainment unit (master) is connected to a phone (audio), a key fob, and a tyre-pressure sensor. The user pairs a second phone, a smartwatch, a dashcam, a backup-camera link, and a passenger's earbuds. At which device does pairing fail, and what AM_ADDR was the last to be assigned? Show the allocation.
2. Wi-Fi on channel 6 (2.437 GHz, ~22 MHz wide) is saturating the band. List roughly how many of Bluetooth's 79 1-MHz channels overlap that Wi-Fi channel, and explain what AFH does to them and why the link survives.
3. A single-slot master packet starts at slot 4 on channel 17. In which slot does the *slave's* reply begin, what is its slot parity, and could it reuse channel 17? Justify using the 625 µs / hopping rules.
4. Place these in the wireless/mobile 2×2 and justify each: (a) a smart-TV on Ethernet, (b) a warehouse barcode scanner, (c) a phone on 4G in a car, (d) a desktop on home Wi-Fi in an un-cabled flat.
5. A pacemaker talks to a handheld programmer over a PAN. Argue why a *parked* member with an 8-bit PM_ADDR (255 codes) is the right model for a device that is connected but rarely scheduled, versus burning one of the 7 active AM_ADDR slots.
6. Re-run `code/main.py` with 7 joiners, then manually park member 3 and admit a new device. What AM_ADDR does the new device receive, and what PM_ADDR does the parked one move to?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| PAN | "Bluetooth stuff" | The ~1 m / square-meter network scale meant for one person and their peripherals |
| Piconet | "a Bluetooth pairing" | One master + up to 7 active slaves sharing the master's clock and hop sequence |
| Master / slave | "the main device" | The master assigns addresses, slots, and the hop schedule; slaves only speak when addressed |
| AM_ADDR | "the device address" | A **3-bit** active-member address (1–7); `000` is reserved for broadcast → 7-active limit |
| PM_ADDR | "parked device" | An **8-bit** address for a low-power parked member, freeing an active slot |
| FHSS | "frequency hopping" | 79 × 1-MHz channels, 1600 hops/s, one hop per 625 µs slot in the 2.4 GHz ISM band |
| AFH | "interference avoidance" | The master drops jammed channels from the hop set (keeping ≥ 20) to coexist with Wi-Fi |
| Mobile vs wireless | "same thing" | Two independent axes; a wired notebook can be mobile and a wireless desktop can be fixed |
| RFID / NFC | "tap to pay" | Passive (no-battery) PAN tags; RFID up to a few meters, NFC a few centimeters |

## Further Reading

- **IEEE 802.15.1-2005** — Wireless PAN MAC and PHY based on Bluetooth (the standardized piconet).
- **Bluetooth Core Specification** v5.x — piconet, AM_ADDR/PM_ADDR, FHSS, AFH, link supervision timeout (Bluetooth SIG).
- **IEEE 802.11** (Wi-Fi) — the 2.4 GHz neighbor that drives AFH and PAN interference behavior.
- **IEEE 802.15.4 / Zigbee** — a contrasting low-rate PAN/sensor technology.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Ch. 1 §1.1.3 (Mobile Users), §1.2.1 (Personal Area Networks); Bluetooth detail in Ch. 4.
- **ISO/IEC 18000** and **ISO/IEC 14443 / 18092 (NFC)** — RFID/NFC air interfaces for passive PAN tags.
