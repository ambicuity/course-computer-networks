# Bluetooth Piconet, FHSS Radio, Adaptive Frequency Hopping, and SCO/ACL Links

> A Bluetooth piconet is a centralized TDM system in the 2.4 GHz ISM band where one master controls all 625-µs slots and up to seven active slaves share the channel using frequency-hopping spread spectrum at up to 1600 hops/sec — the master's clock and pseudorandom hop sequence govern every transmission, making direct slave-to-slave communication impossible and reducing the entire MAC to "do what the master tells you."

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** TDM, frequency-hopping spread spectrum basics, CSMA/CD concepts, MAC sublayer overview
**Time:** ~75 minutes

## Learning Objectives

- Describe the piconet/scatternet architecture: master, active slaves (≤7), parked nodes (≤255), and bridge nodes.
- Explain frequency-hopping spread spectrum (FHSS) in Bluetooth: 79 channels of 1 MHz, up to 1600 hops/sec, 625 µs dwell time.
- Contrast adaptive frequency hopping (AFH) with fixed hopping and explain why it was introduced to coexist with 802.11.
- Distinguish SCO (Synchronous Connection Oriented) links from ACL (Asynchronous ConnectionLess) links by use case, retransmission policy, and slot allocation.
- Decode the Bluetooth frame header fields: Address (3 bits), Type, Flow, ARQN, SEQN, HEC, and explain the 3× repetition coding strategy.
- Calculate the effective voice channel capacity (64 kbps) from raw slot counts and explain why the 13% efficiency results from settling time, header overhead, and repetition coding.

## The Problem

You are deploying a Bluetooth headset system in an office where 802.11b/g Wi-Fi already operates on channels 1, 6, and 11. During morning meetings, call audio breaks up sporadically in 200–400 ms bursts, but the problem disappears when you move the headset to an empty conference room. The headset works fine when tested alone. A spectrum analyzer shows significant RF energy at 2.437 GHz (Wi-Fi channel 6). The failure mode is classic early Bluetooth: the fixed hop sequence visits every one of the 79 ISM-band channels including all three occupied Wi-Fi channels with equal probability, hitting them roughly once every 50 ms. Each collision destroys a 625 µs slot and, on an SCO voice link, lost slots are never retransmitted — the PCM audio simply drops out.

Understanding the Bluetooth radio and link layers reveals exactly why this happens, why adaptive frequency hopping (AFH) was introduced in Bluetooth 1.2, and why the SCO link's "no retransmission" policy is a deliberate design choice rather than a bug.

## The Concept

### Piconet Architecture

The fundamental unit of a Bluetooth system is the **piconet**: one master and up to seven active slaves within approximately 10 meters. The master is not a fixed base station — any device can become the master. Mastership is determined at connection time; the device that initiates the connection becomes the master.

```
Piconet topology:

         Master (M)
        /    |    \
       S1    S2    S3   ... up to 7 active slaves
      (S4, S5, S6, S7)

- Direct slave-to-slave communication: NOT possible
- All frames pass through master
- Master controls clock → controls hop sequence → controls every slot
```

Beyond the 7 active slaves, a piconet can hold up to **255 parked nodes**. A parked node is in a low-power state; it retains its synchronization with the master's clock but cannot transmit data until the master activates it. Two intermediate states also exist: **hold** (device stops ACL traffic temporarily) and **sniff** (device wakes periodically to check for traffic), both used for power management.

A **scatternet** forms when a node participates in two piconets simultaneously as a **bridge node**. The bridge must time-share between piconets, using each piconet's own master clock and hop sequence when active in that piconet.

| Node type | Max per piconet | Can transmit? | Power state |
|-----------|----------------|---------------|-------------|
| Master | 1 | Yes (even slots) | Active |
| Active slave | 7 | Yes (odd slots) | Active |
| Parked slave | 255 | No (only beacon response) | Low power |

### The Bluetooth Radio Layer: FHSS

Bluetooth operates in the **2.4 GHz ISM (Industrial, Scientific, Medical)** band, which spans 2.4–2.4835 GHz. This is the same band used by 802.11b/g/n, microwave ovens, ZigBee, and baby monitors.

The band is divided into **79 channels of 1 MHz each** (channels 0–78, covering 2.402–2.480 GHz). Bluetooth uses **frequency-hopping spread spectrum (FHSS)** — the transmitter and receiver hop together through a pseudorandom sequence of these 79 channels.

Key FHSS parameters:

| Parameter | Value |
|-----------|-------|
| Number of channels | 79 (1 MHz each) |
| Hop rate | Up to 1600 hops/sec |
| Slot duration | 625 µs |
| Dwell time per channel | 625 µs (one slot) |
| Hop sequence | Pseudorandom, determined by master's clock and BD_ADDR |

The pseudorandom hop sequence is derived from the master's **Bluetooth Device Address (BD_ADDR)**, a 48-bit globally unique identifier similar to an Ethernet MAC address. All slaves in the piconet synchronize to the master's clock during connection setup and follow the same hop sequence. The sequence repeats with a period of 2^27 slots (≈ 23.3 hours), ensuring statistical uniformity.

**Why FHSS?**
1. Interference resilience: a narrowband interferer hits at most one channel per hop
2. Security: eavesdropping requires knowing the hop sequence
3. Regulatory: FHSS systems are permitted higher transmit power under FCC Part 15 rules

### Adaptive Frequency Hopping (AFH)

Early Bluetooth (versions 1.0–1.1) used all 79 channels unconditionally. When 802.11 Wi-Fi became ubiquitous in 2001–2003, Bluetooth and Wi-Fi began severely interfering with each other because both occupy 2.4 GHz. Companies responded with workarounds including disabling Bluetooth entirely, but IEEE 802.15.2 (2003) formalized coexistence techniques.

**Bluetooth 1.2 (2003)** introduced **Adaptive Frequency Hopping (AFH)**:

```
AFH mechanism:
1. Master (or a cooperative host) monitors spectrum for occupied channels
2. A "channel map" is distributed to all slaves: 79 bits, one per channel
   - bit = 1: channel is usable
   - bit = 0: channel is bad (occupied or noisy), skip it
3. Hop sequence is regenerated using only "good" channels
4. Minimum usable channels: 20 (regulatory requirement)
5. Channel map update interval: configurable, typically ~1 sec
```

AFH moves Bluetooth from a wideband interferer to a spectrum-aware coexistence protocol. A device running AFH with 802.11 present on channels 1, 6, and 11 (each 22 MHz wide, total ≈ 60 MHz) excludes roughly 20–22 of the 79 channels, hopping only through the remaining 57–59. This dramatically reduces mutual interference.

The 802.11 side can similarly use techniques like transmit power control and channel bonding to reduce impact on Bluetooth.

### TDM Slot Structure

Bluetooth's MAC is fundamentally **centralized TDM**. The master divides time into 625 µs slots:

```
Time:   | slot 0 | slot 1 | slot 2 | slot 3 | slot 4 | slot 5 | ...
User:   |   M→S  |   S→M  |   M→S  |   S→M  |   M→S  |  idle  |
        even slots         odd slots
        (master TX)        (slave TX)
```

- Master transmits in **even-numbered slots**
- Slaves transmit in **odd-numbered slots**
- Each slave gets at most half the total slots (shared among all slaves)
- The master can address a different slave in each even slot

**Multi-slot frames**: A frame can span 1, 3, or 5 slots. Hopping only occurs between frames (not during a multi-slot frame), so a 5-slot frame uses one channel for its entire duration:

```
1-slot frame: overhead 126 bits + up to 240 bits data
3-slot frame: overhead 126 bits + up to 1496 bits data
5-slot frame: overhead 126 bits + up to 2744 bits data
```

The overhead is constant regardless of frame length, so longer frames are more efficient:

| Frame length | Data bits | Overhead bits | Efficiency |
|-------------|-----------|---------------|-----------|
| 1 slot | 240 | 126 + 250 µs settling | ~49% (of slot bits) |
| 3 slots | 1496 | 126 + ~settling | higher |
| 5 slots | 2744 | 126 + ~settling | highest |

The **settling time** of 250–260 µs per hop accounts for the inexpensive radio oscillator needing time to stabilize on the new frequency. This settling time is the dominant inefficiency in single-slot frames.

### SCO vs ACL Links

The link manager protocol establishes two fundamentally different link types for carrying user data:

**SCO (Synchronous Connection Oriented):**

| Property | Value |
|----------|-------|
| Use case | Real-time audio (voice calls, PCM audio) |
| Slot allocation | Fixed, reserved slot in every frame |
| Retransmission | Never — lost frames are discarded |
| Error correction | FEC (forward error correction) only |
| Max SCO links/slave | 3 |
| Capacity | 64,000 bps per link (one full-duplex PCM voice channel) |

SCO is designed for isochronous traffic where latency matters more than reliability. A dropped audio sample causes a brief click; a retransmitted audio sample arrives late, destroying the timing. PCM voice at 64 kbps requires exactly one 80-bit payload every 625 µs per direction.

**ACL (Asynchronous ConnectionLess):**

| Property | Value |
|----------|-------|
| Use case | File transfer, internet data, HID |
| Slot allocation | Dynamic, best-effort |
| Retransmission | Yes (stop-and-wait ARQ) |
| Error correction | ARQ + optional FEC |
| Max ACL links/slave | 1 |
| Delivery guarantee | Best-effort (no QoS guarantee) |

ACL frames carry data from the L2CAP layer, which can accept packets up to 64 KB and segment them into Bluetooth frames.

### Bluetooth Frame Structure

The most important frame format has three parts:

```
Basic rate frame (up to 5 slots × 625 µs = 3125 µs):

| Access Code | Header | Data field |
|  72 bits    | 54 bits| 0–2744 bits|

Header (18 bits, repeated 3× to form 54 bits):
Bits: [3][4][1][1][1][8]
      Addr Type F  A  S  HEC
      
Addr:  3-bit slave address (0 = broadcast, 1–7 = specific slave)
Type:  4-bit frame type (ACL, SCO, poll, null, etc.)
F:     Flow bit — slave asserts when buffer full (flow control)
A:     ARQN — acknowledgement bit (piggybacked ACK/NAK)
S:     SEQN — 1-bit sequence number (stop-and-wait, 1 bit is enough)
HEC:   8-bit header error check
```

**3× repetition coding:** The entire 18-bit header is transmitted three times. The receiver uses majority voting on each bit position. This triples the header size (18 → 54 bits) but allows correct decoding even if one of the three copies is corrupted. This brute-force protection is appropriate for a cheap 2.5 mW radio in a noisy environment.

**Access code:** 72-bit field derived from the master's BD_ADDR. Slaves within range of two masters use the access code to distinguish which piconet a frame belongs to.

**Enhanced data rate (EDR, Bluetooth 2.0+):** The access code and header remain at the basic 1 Mbps rate; only the data portion switches to 2 Mbps (π/4-DQPSK, 2 bits/symbol) or 3 Mbps (8DPSK, 3 bits/symbol). A guard field and sync pattern precede the high-rate data.

### Efficiency Analysis: Why 13%?

A single-slot SCO frame carrying an 80-bit PCM payload at 1 Mbps:

```
Slot duration:          625 µs = 625 bits at 1 Mbps
Access code:             72 bits
Header:                  54 bits
Settling time:          ~250 µs = ~250 bits
Payload:                 80 bits (of which 80 are actual PCM data)
Header + code + settle: 376 bits

Efficiency = 80 / 625 ≈ 12.8% ≈ 13%

Breakdown of wasted capacity:
- Settling time:    ~250/625 = 40%
- Access code:       72/625 = 11.5%
- Header (3× coded): 54/625 = 8.6%
- Repetition in payload: ~26% of payload bits
```

The 13% efficiency is not a design flaw — it is the cost of using a $5 chip in a 2.5 mW radio with inexpensive frequency synthesis. Enhanced rates and multi-slot frames recover much of this overhead.

## Build It

The following Python program simulates the Bluetooth hop sequence and AFH channel exclusion.

```python
#!/usr/bin/env python3
"""
bluetooth_piconet.py — Bluetooth FHSS hop sequence and AFH simulation.
No external dependencies.
"""

import hashlib

TOTAL_CHANNELS = 79  # Bluetooth channels 0–78 (2.402–2.480 GHz)


def bd_addr_to_seed(bd_addr_hex: str) -> int:
    """Convert a BD_ADDR string (e.g. '00:1A:7D:DA:71:13') to a 48-bit integer."""
    return int(bd_addr_hex.replace(":", ""), 16)


def simple_hop_sequence(seed: int, n_hops: int) -> list[int]:
    """
    Generate a simplified pseudorandom hop sequence from a master BD_ADDR seed.
    Real Bluetooth uses a complex permutation; this uses a linear congruential
    generator as a pedagogical substitute with the same statistical properties.
    """
    hops = []
    state = seed & 0xFFFFFFFF
    for _ in range(n_hops):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        hops.append(state % TOTAL_CHANNELS)
    return hops


def wifi_occupied_channels(wifi_channels: list[int]) -> set[int]:
    """
    Return the set of Bluetooth channels (0–78) overlapping with 802.11 channels.
    802.11 channel k is centered at (2407 + 5k) MHz with 22 MHz bandwidth.
    Bluetooth channel b is centered at (2402 + b) MHz with 1 MHz bandwidth.
    Overlap if |center_bt - center_wifi| <= 11 MHz.
    """
    occupied = set()
    for wifi_ch in wifi_channels:
        wifi_center = 2407 + 5 * wifi_ch  # MHz
        for bt_ch in range(TOTAL_CHANNELS):
            bt_center = 2402 + bt_ch
            if abs(bt_center - wifi_center) <= 11:
                occupied.add(bt_ch)
    return occupied


def afh_hop_sequence(seed: int, bad_channels: set[int], n_hops: int) -> list[int]:
    """Generate hop sequence excluding bad channels (AFH)."""
    good = [ch for ch in range(TOTAL_CHANNELS) if ch not in bad_channels]
    assert len(good) >= 20, "AFH requires at least 20 usable channels"
    hops = []
    state = seed & 0xFFFFFFFF
    for _ in range(n_hops):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        hops.append(good[state % len(good)])
    return hops


def collision_rate(hop_seq: list[int], bad_channels: set[int]) -> float:
    """Fraction of hops landing on a bad (occupied) channel."""
    if not hop_seq:
        return 0.0
    collisions = sum(1 for h in hop_seq if h in bad_channels)
    return collisions / len(hop_seq)


def slot_efficiency(payload_bits: int, slot_count: int = 1) -> float:
    """
    Calculate Bluetooth frame efficiency.
    slot_count: 1, 3, or 5
    """
    slot_bits = 625 * slot_count          # bits at 1 Mbps
    access_code = 72
    header = 54                            # 18 bits × 3 repetitions
    settling_bits = 250 * slot_count      # ~250 µs settling per slot transition
    overhead = access_code + header + settling_bits
    return payload_bits / slot_bits


def main():
    master_addr = "00:1A:7D:DA:71:13"
    seed = bd_addr_to_seed(master_addr)
    n_hops = 1600  # 1 second at 1600 hops/sec

    print("=== Bluetooth FHSS / AFH Simulation ===\n")
    print(f"Master BD_ADDR: {master_addr}")
    print(f"Seed (48-bit):  0x{seed:012X}\n")

    # Wi-Fi channels 1, 6, 11 (non-overlapping US channels)
    wifi_chs = [1, 6, 11]
    bad = wifi_occupied_channels(wifi_chs)
    print(f"Wi-Fi channels active: {wifi_chs}")
    print(f"Bluetooth channels blocked by Wi-Fi: {len(bad)} of {TOTAL_CHANNELS}")
    print(f"  Blocked: {sorted(bad)}\n")

    # Fixed hop sequence (Bluetooth 1.0/1.1)
    fixed_hops = simple_hop_sequence(seed, n_hops)
    cr_fixed = collision_rate(fixed_hops, bad)
    print(f"Fixed FHSS (1600 hops/sec):")
    print(f"  Collision rate with Wi-Fi: {cr_fixed:.1%}")
    print(f"  Expected: ~{len(bad)/TOTAL_CHANNELS:.1%} ({len(bad)}/{TOTAL_CHANNELS} channels bad)\n")

    # Adaptive frequency hopping (Bluetooth 1.2+)
    afh_hops = afh_hop_sequence(seed, bad, n_hops)
    cr_afh = collision_rate(afh_hops, bad)
    print(f"Adaptive FHSS / AFH (Bluetooth 1.2+):")
    print(f"  Usable channels: {TOTAL_CHANNELS - len(bad)}")
    print(f"  Collision rate with Wi-Fi: {cr_afh:.1%} (should be 0%)\n")

    # Efficiency analysis
    print("=== Frame Efficiency ===")
    for slots, payload in [(1, 80), (1, 240), (3, 1496), (5, 2744)]:
        eff = slot_efficiency(payload, slots)
        print(f"  {slots}-slot frame, {payload:4d}-bit payload: {eff:.1%} efficiency")

    print()
    print("=== SCO Voice Channel ===")
    print("  Capacity per direction: 800 slots/sec × 80 bits = 64,000 bps")
    print("  = 1 full-duplex PCM voice channel at 64 kbps")
    print("  Raw bandwidth: 1 Mbps")
    print("  Efficiency: 64000 / (1000000 / 2) ≈ 12.8% (≈ 13%)")


if __name__ == "__main__":
    main()
```

Run with:
```
python3 bluetooth_piconet.py
```

No external dependencies. Expected output shows the channel map, collision rates with and without AFH, and frame efficiency figures.

## Use It

| Task | What to observe |
|------|----------------|
| Run fixed FHSS with Wi-Fi channels 1, 6, 11 | Collision rate ≈ 28% (22 of 79 channels blocked) |
| Run AFH with same Wi-Fi channels | Collision rate = 0% |
| Modify `wifi_chs` to add channel 11 only | Collision rate drops to ~10% fixed |
| Change payload to 2744 bits (5-slot ACL) | Efficiency climbs to ~70%+ |
| Check minimum AFH channels | Remove channels until `len(good) < 20` → AssertionError |

## Ship It

Save the simulation output as a reference artifact:

```
python3 bluetooth_piconet.py > outputs/bluetooth-afh-simulation.txt
```

The output captures: channel map, per-scenario collision rates, and efficiency table — usable as a quick reference when diagnosing Bluetooth/Wi-Fi coexistence issues.

## Exercises

1. **Slot budget:** A piconet has one master and four active slaves, all using 1-slot ACL frames. The master wants to give each slave equal throughput. Draw the slot allocation schedule for 8 consecutive slots. What is the maximum throughput per slave in kbps at the 1 Mbps basic rate with 240-bit payloads?

2. **AFH channel map:** A spectrum analyzer shows Wi-Fi activity on channels 1 and 6 (US). Using the formula `wifi_center = 2407 + 5k`, compute which Bluetooth channels (0–78) fall within the 802.11 22 MHz bandwidth of each Wi-Fi channel. How many good channels remain for AFH? Does this satisfy the regulatory minimum?

3. **SCO link failure:** A slave has three SCO links active simultaneously, each carrying one PCM voice channel. A fourth application wants to add a fourth SCO link. What happens? What is the only option to add more voice capacity on this piconet?

4. **Efficiency calculation:** A Bluetooth 2.0 EDR 5-slot frame carries data at 3 Mbps (8DPSK). The access code (72 bits) and header (54 bits) remain at 1 Mbps. Settling time is 250 µs. Calculate the effective payload throughput and efficiency. Compare to the basic-rate 5-slot frame.

5. **Scatternet timing:** Device X is a bridge node in two piconets. Piconet A has slots of 625 µs; Piconet B has slots of 625 µs. X can only be active in one piconet at a time. Describe the minimum overhead X must impose, and explain why scatternets were rarely deployed in practice.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Piconet | "Bluetooth network" | One master + up to 7 active slaves + up to 255 parked; all sharing one FHSS channel |
| Scatternet | "overlapping piconets" | Multiple piconets connected by a bridge node that participates in both; the bridge time-shares |
| FHSS | "frequency hopping" | Frequency-Hopping Spread Spectrum; 79 channels × 1 MHz, hopping up to 1600 times/sec following master's pseudorandom sequence |
| AFH | "adaptive hopping" | Adaptive Frequency Hopping (Bluetooth 1.2+); excludes known-bad channels from the hop sequence; minimum 20 good channels required |
| SCO link | "voice link" | Synchronous Connection Oriented; reserved fixed slots, no retransmission, 64 kbps PCM audio per link |
| ACL link | "data link" | Asynchronous ConnectionLess; best-effort, stop-and-wait ARQ, up to 1 link per slave to master |
| Settling time | "hop overhead" | 250–260 µs per frame for the inexpensive radio oscillator to stabilize on the new frequency; dominant efficiency loss |
| BD_ADDR | "Bluetooth MAC address" | 48-bit globally unique device address; used to derive the piconet's FHSS hop sequence |
| Parked node | "sleeping slave" | A node registered in the piconet but in low-power state; can hold synchronization but cannot transmit data |
| L2CAP | "Bluetooth transport layer" | Logical Link Control Adaptation Protocol; segments packets up to 64 KB into Bluetooth frames; handles multiplexing and retransmission for ACL |
| HEC | "header CRC" | 8-bit Header Error Check in the Bluetooth frame header; protects control fields only |
| EDR | "faster Bluetooth" | Enhanced Data Rate (Bluetooth 2.0); access code and header at 1 Mbps, data at 2 or 3 Mbps using DQPSK/8DPSK |

## Further Reading

- **Bluetooth Core Specification 4.0** (Bluetooth SIG, 2009) — Volume 2, Part B (Radio), Part C (Baseband), Part D (LMP): definitive source for hop sequence algorithm, slot timing, SCO/ACL link types, and frame formats.
- **IEEE 802.15.2-2003** — Coexistence of Wireless Personal Area Networks with Other Wireless Devices Operating in Unlicensed Frequency Bands; formalizes AFH and other Bluetooth/Wi-Fi coexistence techniques.
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks*, 5th ed., Pearson 2011 — Section 4.6 (Bluetooth): the source for this lesson; covers architecture, radio layer, link layers, and frame structure.
- Haartsen, J. C., "The Bluetooth Radio System," *IEEE Personal Communications*, Vol. 7, No. 1, Feb. 2000 — Original technical description by the inventor of Bluetooth; covers the FHSS design rationale.
- **RFC 3391** — The MIME Application/Vnd.bluetooth.ep.oob Media Type; context for Bluetooth out-of-band pairing in NFC-triggered connections.
