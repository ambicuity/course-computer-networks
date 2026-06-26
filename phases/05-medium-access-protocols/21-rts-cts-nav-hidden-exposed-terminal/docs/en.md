# RTS/CTS, the NAV, and the Hidden/Exposed Terminal Problems

> In 802.11, physical carrier sense alone fails because two stations that cannot hear each other can simultaneously destroy each other's frames at a shared receiver — the RTS/CTS handshake and the **NAV (Network Allocation Vector)** are the MAC-layer instruments that coordinate channel access across these acoustic shadows, at the cost of a 34-byte handshake overhead that only pays off for large frames.

**Type:** Learn
**Languages:** Python, simulation
**Prerequisites:** CSMA/CA basics (Lesson 20), 802.11 architecture overview, half-duplex radio fundamentals
**Time:** ~75 minutes

## Learning Objectives

- Explain the hidden terminal problem and construct a 3-node diagram showing why CSMA/CA alone cannot prevent the resulting collisions.
- Explain the exposed terminal problem and show why it causes unnecessary channel waste rather than data corruption.
- Trace the exact 4-frame RTS/CTS/DATA/ACK exchange, identifying which stations set the NAV from which frame.
- Calculate the NAV value placed in an RTS or CTS given exact SIFS, frame sizes, and data rate.
- Identify why 802.11 RTS/CTS does not cure exposed terminals while MACA (the research precursor) does.
- Configure an RTS threshold and justify its value given a traffic mix of small and large frames.

## The Problem

A university lecture hall has a wireless network with an AP (B) at the front. Station A (left side) and station C (right side) are both within range of B but cannot hear each other. A begins streaming a large file to B. C, unaware that B is busy, senses an idle channel and begins its own large upload to B. Both frames collide at B. Neither A nor C detects the collision because neither can hear the other. Both time out waiting for an ACK, then retransmit with exponential backoff — but because the root cause (mutual inaudibility) persists, they will collide again and again. CSMA/CA is powerless: no amount of listening before transmitting helps when the interference source is acoustically invisible.

A second scenario causes the opposite failure. B wants to send to C. It senses the channel and hears A transmitting to a distant out-of-range station D. B falsely concludes the channel is busy and defers. But A's signal cannot reach D via B — B's transmission to C would not have interfered at D at all. The deferral wastes capacity without preventing any collision. This is the exposed terminal problem.

Both problems share a root cause: physical carrier sense is a local measurement that does not reflect the global state of ongoing transmissions. The solution is to embed channel-reservation information in every frame header and have every station that overhears any frame — addressed to it or not — honour a countdown timer. That timer is the NAV.

## The Concept

### Topology for Both Problems

```
Hidden terminal scenario:
  A --------> B <-------- C
  |           |           |
  range       range       range
  of A        of B        of C
  
  A and C cannot hear each other.
  Both can hear B (the AP).

Exposed terminal scenario:
  D <-- A <--------> B <--------> C
        |    range        range
        A transmitting to D;
        B hears A and wrongly defers from sending to C.
```

### The Hidden Terminal Problem in Detail

At time t=0, A senses the channel idle (it cannot hear C) and begins transmitting frame F1 to B. At time t=5 µs, C also senses the channel idle (it cannot hear A) and begins transmitting frame F2 to B. F1 and F2 collide at B's antenna. B receives garbled energy and sends no ACK. A and C both run their ACK timeout, then retransmit with doubled backoff windows. Because the backoff windows are sampled from overlapping ranges, they will collide again with significant probability.

The problem is structural: CSMA/CA's "listen before talk" step requires that the interfering station be audible. When it is not, the protocol has no mechanism to detect contention before it becomes a collision.

### The Exposed Terminal Problem in Detail

B wants to send to C. B performs carrier sense and detects A's ongoing transmission to D. B defers. However, B is out of range of D, so B transmitting to C would not corrupt D's reception of A's frame. The deferral is unnecessary. In a busy mesh network, exposed terminal waste can account for a significant fraction of lost throughput.

Note: exposed terminal causes **underutilization**, not data corruption. It is less operationally severe than hidden terminal.

### Virtual Carrier Sense and the NAV

802.11 defines channel sensing as the logical OR of **physical carrier sense** (energy on the medium) and **virtual carrier sense** (the NAV timer). The NAV is a per-station countdown initialized from the **Duration/ID** field present in every 802.11 frame header.

```
Duration/ID field: 2 bytes, positions 3–4 of every 802.11 MAC header.

Value semantics:
  Bits 15:14 = 00 → Duration value in µs (0–32767 µs)
  Bits 15:14 = 10 → Association ID (used in PS-Poll frames)
```

A station that receives any frame — data, control, or management — reads the Duration field and sets its NAV to the maximum of its current NAV value and the Duration value. The NAV decrements in real time. The station will not initiate a transmission while NAV > 0, even if the channel is physically silent.

Duration values carried by each frame type:

```
RTS Duration  = SIFS + t(CTS) + SIFS + t(DATA) + SIFS + t(ACK)
CTS Duration  = SIFS + t(DATA) + SIFS + t(ACK)
DATA Duration = SIFS + t(ACK)
ACK Duration  = 0
```

### The RTS/CTS Handshake

The optional RTS/CTS mechanism extends NAV-based reservation to stations that cannot directly hear the data transmitter.

```
Timeline (→ = transmission, gap labels show interframe spacing):

  A: |---RTS(20B)→|  SIFS  |  SIFS  |---DATA(n B)-------->|  SIFS
  B:              | ←CTS(14B)|                             |←ACK(14B)|
  
  C (hears A's RTS, cannot hear B):
     sets NAV_rts = SIFS+CTS+SIFS+DATA+SIFS+ACK
     |<------- C defers for NAV_rts µs ------->|
  
  D (hears B's CTS, cannot hear A):
     sets NAV_cts = SIFS+DATA+SIFS+ACK
              |<-- D defers for NAV_cts µs -->|
```

Step-by-step exchange:

1. A waits DIFS + random backoff slots, then transmits an **RTS** frame (20 bytes). Duration field = SIFS + t(CTS) + SIFS + t(DATA) + SIFS + t(ACK).
2. B, on clean receipt of RTS, waits exactly SIFS then replies with a **CTS** frame (14 bytes). Duration field = SIFS + t(DATA) + SIFS + t(ACK).
3. A, on receipt of CTS, waits SIFS then transmits the **DATA** frame.
4. B, on correct receipt of DATA, waits SIFS then sends an **ACK** (14 bytes). Duration = 0.

Any station hearing the RTS sets its NAV from the RTS Duration. Any station hearing the CTS (but not the RTS) sets its NAV from the CTS Duration. The result: both C (heard RTS only) and D (heard CTS only) defer for the duration of the full exchange without needing to hear every frame.

### RTS and CTS Frame Sizes

| Frame | Size (bytes) | Fields |
|-------|-------------|--------|
| RTS | 20 | Frame Control(2) + Duration(2) + RA(6) + TA(6) + FCS(4) |
| CTS | 14 | Frame Control(2) + Duration(2) + RA(6) + FCS(4) |
| ACK | 14 | Frame Control(2) + Duration(2) + RA(6) + FCS(4) |

Both RTS and CTS are transmitted at the **BSS basic rate** (typically 1 Mbps for 802.11b, 6 Mbps for 802.11a/g/n) so that all stations at the edge of coverage can receive them reliably.

### NAV Calculation Example

Given: SIFS = 16 µs, basic rate = 6 Mbps, data rate = 54 Mbps, DATA = 1000 bytes.

```
t(CTS)  = (14 × 8) / 6 Mbps  = 18.7 µs
t(DATA) = (1000 × 8) / 54 Mbps = 148.1 µs
t(ACK)  = (14 × 8) / 6 Mbps  = 18.7 µs

NAV in RTS = 16 + 18.7 + 16 + 148.1 + 16 + 18.7 = 233.5 µs
NAV in CTS = 16 + 148.1 + 16 + 18.7             = 198.8 µs
```

### Why RTS/CTS Has Limited Practical Value

RTS/CTS is disabled by default on virtually all 802.11 implementations. The reasons:

1. **Small frames:** RTS(20B) + CTS(14B) = 34 bytes of overhead plus three SIFS gaps. For a 100-byte data frame this overhead exceeds the frame itself. The **RTS threshold** (default ~2347 bytes, effectively off) is the minimum frame size that triggers RTS/CTS.
2. **AP is universally audible:** The AP, by definition, is within range of every station in the BSS. Sending RTS before downlink frames adds overhead with no collision-reduction benefit.
3. **Exposed terminals not fixed in 802.11:** When any station hears an RTS, it sets its NAV and defers — including stations that are exposed terminals that could safely transmit. The original MACA protocol (Karn 1990) only silenced CTS hearers; 802.11 silences both RTS and CTS hearers, trading exposed-terminal efficiency for implementation simplicity.
4. **CSMA/CA already partially mitigates hidden terminals:** Exponential backoff naturally separates stations that fail repeatedly, reducing repeated hidden-terminal collisions even without RTS/CTS.

### MACA vs 802.11 RTS/CTS

| Behavior | MACA (1990) | 802.11 RTS/CTS |
|----------|------------|----------------|
| Hears RTS | Does NOT defer | Defers (sets NAV) |
| Hears CTS | Defers | Defers (sets NAV) |
| Exposed terminal helped? | Yes | No |
| Hidden terminal helped? | Yes | Yes |
| Standard? | Research only | IEEE 802.11 optional |

## Build It

`code/main.py` simulates a 4-node wireless network and measures collision rates with and without RTS/CTS for varying frame sizes and backoff windows.

```python
# code/main.py — hidden terminal collision simulator
import random

SIFS   = 16   # µs
DIFS   = 34   # µs
SLOT   =  9   # µs (802.11g)
BASIC  =  6   # Mbps — basic rate for RTS/CTS frames

def tx_time_us(bytes_, mbps):
    return (bytes_ * 8) / mbps

def nav_rts(data_bytes, data_mbps):
    cts  = tx_time_us(14, BASIC)
    data = tx_time_us(data_bytes, data_mbps)
    ack  = tx_time_us(14, BASIC)
    return SIFS + cts + SIFS + data + SIFS + ack

def nav_cts(data_bytes, data_mbps):
    data = tx_time_us(data_bytes, data_mbps)
    ack  = tx_time_us(14, BASIC)
    return SIFS + data + SIFS + ack

# can_hear[rx][tx] = True if rx can receive tx
can_hear = {
    'A': {'A', 'B'},
    'B': {'A', 'B', 'C', 'D'},
    'C': {'B', 'C'},
    'D': {'B', 'C', 'D'},
}

def simulate(trials=2000, use_rts=False, rts_threshold=500, data_mbps=54.0):
    collisions = successes = 0
    for _ in range(trials):
        data_bytes = random.randint(64, 1500)
        bo_a = random.randint(0, 15) * SLOT
        bo_c = random.randint(0, 15) * SLOT
        dt   = tx_time_us(data_bytes, data_mbps)

        if use_rts and data_bytes >= rts_threshold:
            # Whichever wins backoff sends RTS first.
            # If C cannot hear A's RTS, it does NOT set NAV from RTS.
            a_wins = bo_a <= bo_c
            c_hears_rts = 'A' in can_hear['C']   # False in our topology
            if a_wins:
                if not c_hears_rts:
                    # C never knew about the exchange → still may collide
                    # but RTS/CTS at B: B will not send CTS if channel busy.
                    # C hears CTS from B (B is in C's can_hear set).
                    c_hears_cts = 'B' in can_hear['C']   # True
                    if c_hears_cts:
                        successes += 1   # C deferred on CTS NAV
                    else:
                        collisions += 1
                else:
                    successes += 1
            else:
                a_hears_cts = 'B' in can_hear['A']
                if a_hears_cts:
                    successes += 1
                else:
                    collisions += 1
        else:
            # No RTS/CTS: hidden terminals collide if their transmit windows overlap
            overlap = abs(bo_a - bo_c) < (dt / 1000.0)
            if overlap:
                collisions += 1
            else:
                successes += 1

    total = collisions + successes
    return successes, collisions, collisions / total * 100

print(f"{'Mode':<30} {'Successes':>10} {'Collisions':>12} {'Collision%':>12}")
print("-" * 68)
for use_rts, thresh in [(False, 9999), (True, 256), (True, 512)]:
    label = "No RTS/CTS" if not use_rts else f"RTS/CTS (threshold={thresh}B)"
    s, c, pct = simulate(use_rts=use_rts, rts_threshold=thresh)
    print(f"{label:<30} {s:>10} {c:>12} {pct:>11.1f}%")

print("\n--- NAV value examples ---")
for data_b in [100, 500, 1000, 1500]:
    print(f"  DATA={data_b:4d}B → NAV(RTS)={nav_rts(data_b,54):.1f} µs, "
          f"NAV(CTS)={nav_cts(data_b,54):.1f} µs")
```

Run:
```
python3 code/main.py
```

## Use It

| Scenario | Recommended RTS threshold | Rationale |
|----------|--------------------------|-----------|
| Dense lecture hall, large video uploads | 500–800 bytes | Hidden-terminal risk high; large frames justify handshake overhead |
| IoT sensors, 50–150 byte payloads | Disabled (2347) | Overhead exceeds benefit for every frame |
| Mesh backhaul link, mostly bulk | 256 bytes | Long-distance links; hidden nodes likely; large frames common |
| VoIP-only network | Disabled | 160-byte VoIP packets; RTS adds 25% overhead with minimal gain |

To inspect NAV in Wireshark: filter `wlan.fc.type_subtype == 11` for RTS, `wlan.fc.type_subtype == 12` for CTS. The Duration field (bytes 3–4, little-endian) is the NAV seed in microseconds.

## Ship It

```bash
#!/bin/bash
# scripts/nav-audit.sh
# Parse a monitor-mode pcap and report every RTS/CTS pair with NAV values.
# Usage: ./nav-audit.sh capture.pcap
PCAP="${1:?Usage: nav-audit.sh <pcap>}"
echo "=== RTS frames ==="
tshark -r "$PCAP" -Y "wlan.fc.type_subtype == 11" \
  -T fields -e frame.number -e wlan.ta -e wlan.ra -e wlan.duration \
  -E header=y -E separator='\t'
echo ""
echo "=== CTS frames ==="
tshark -r "$PCAP" -Y "wlan.fc.type_subtype == 12" \
  -T fields -e frame.number -e wlan.ra -e wlan.duration \
  -E header=y -E separator='\t'
echo ""
echo "=== RTS/CTS ratio (RTS count / total data frames) ==="
RTS=$(tshark -r "$PCAP" -Y "wlan.fc.type_subtype == 11" -T fields \
  -e frame.number | wc -l)
DATA=$(tshark -r "$PCAP" -Y "wlan.fc.type_subtype == 32" -T fields \
  -e frame.number | wc -l)
echo "RTS=$RTS  DATA=$DATA  ratio=$(echo "scale=3; $RTS / ($DATA+1)" | bc)"
```

## Exercises

1. **NAV arithmetic:** 802.11g, SIFS = 16 µs, basic rate = 6 Mbps, data rate = 54 Mbps. A sends RTS for a 1460-byte data frame. CTS = 14 bytes, ACK = 14 bytes. Compute the exact Duration value A places in the RTS. Show all five terms.

2. **Trace analysis:** Open a Wireshark capture containing an RTS/CTS exchange. Identify the sender (A), receiver (B), a bystander C that heard only the RTS, and a bystander D that heard only the CTS. What NAV value does each set? In what order do their NAV timers expire?

3. **Threshold design:** An 802.11ac AP serves 60 devices: 75% send 80-byte MQTT keep-alives at 1 Hz, 25% send 5-KB JPEG snapshots at 0.5 Hz. Compute the per-frame RTS/CTS overhead ratio for both traffic classes at 54 Mbps basic rate. Recommend an RTS threshold and justify it quantitatively.

4. **MACA vs 802.11:** Draw the 4-node topology (A sends to B; C hears A but not B; D hears B but not A). Under MACA, which stations defer and why? Under 802.11 RTS/CTS, which stations defer and why? Which rule helps exposed terminals, and which does not?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Hidden terminal | "two stations can't hear each other" | Two stations that cannot detect each other's transmissions but share a common receiver; they cause undetectable collisions at that receiver |
| Exposed terminal | "station defers unnecessarily" | A station that senses a busy channel but whose own transmission would not actually interfere at its intended receiver |
| NAV | "virtual carrier sense timer" | Network Allocation Vector; a per-station countdown in µs initialized from the Duration field of overheard frames; station defers while NAV > 0 |
| Duration/ID field | "the NAV field" | 2-byte field (bytes 3–4) in every 802.11 MAC header; carries remaining exchange time in µs so bystanders can set their NAV |
| RTS | "request handshake" | Request To Send; 20-byte control frame sent before a large data frame to reserve the channel via NAV at all nearby stations |
| CTS | "permission handshake" | Clear To Send; 14-byte control frame replying to RTS; causes stations that only heard CTS (not RTS) to also defer via their NAV |
| RTS threshold | "the size cutoff" | Minimum frame size (bytes) above which RTS/CTS is triggered; default ~2347 (off); smaller values enable RTS/CTS for more frames |
| MACA | "the academic original" | Multiple Access with Collision Avoidance (Karn 1990); precursor to 802.11 RTS/CTS; only CTS hearers defer, curing exposed terminals too |
| Physical carrier sense | "listen before talk" | Measuring energy or a valid preamble on the RF channel; fails for hidden terminals because the interferer is out of range |
| Virtual carrier sense | "NAV-based silence" | Deferring based on Duration fields in overheard frames; works even when the interfering station is physically inaudible |

## Further Reading

- **IEEE 802.11-2020**, Section 10.3.2 (NAV update rules) and Section 10.23 (RTS/CTS procedure) — normative definitions of Duration/ID, NAV semantics, and the 4-frame handshake.
- Karn, P., "MACA — A New Channel Access Method for Packet Radio," *ARRL/CRRL Amateur Radio 9th Computer Networking Conference*, 1990 — the original paper proposing RTS/CTS-style handshaking; the direct inspiration for 802.11.
- Tobagi, F. & Kleinrock, L., "Packet Switching in Radio Channels: Part II — The Hidden Terminal Problem," *IEEE Transactions on Communications*, Vol. 23, No. 12, 1975 — formal analysis proving hidden terminals are a structural MAC-layer problem.
- Tanenbaum, A.S. & Wetherall, D.J., *Computer Networks*, 5th ed., Section 4.4.3 — textbook treatment of hidden/exposed terminals and the 802.11 NAV mechanism.
- Heusse, M. et al., "Performance Anomaly of 802.11b," *IEEE INFOCOM 2003* — demonstrates how a single slow or hidden station can collapse throughput for the entire BSS.
