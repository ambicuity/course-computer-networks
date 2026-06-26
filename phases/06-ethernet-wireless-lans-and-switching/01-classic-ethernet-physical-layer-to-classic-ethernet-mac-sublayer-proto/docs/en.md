# Classic Ethernet Physical Layer to Classic Ethernet MAC Sublayer Protocol

> Classic Ethernet (DIX 1980, IEEE 802.3-1983) put every host on one shared coaxial cable and ran 1-persistent **CSMA/CD** at 10 Mbps using **Manchester** line coding. A frame is an 8-byte **preamble** (seven `0xAA` bytes plus a `0xAB` Start-of-Frame Delimiter), 6-byte destination and 6-byte source MAC addresses, a 2-byte **Type/Length** field, 0-1500 bytes of payload, a 0-46 byte **Pad**, and a 4-byte **CRC-32** trailer (generator `0x04C11DB7`). Two numbers dominate the design: the **slot time** of 512 bit-times (51.2 us), set to the worst-case round-trip 2tau across 2500 m and four repeaters, and the resulting **64-byte minimum frame** so a sender is still transmitting when a far-end collision returns. On collision a station sends a 48-bit **jam** burst and reschedules with **binary exponential backoff**: a random delay in `[0, 2^min(k,10)-1]` slots, frozen at 1023, abandoned after 16 attempts. Ethernet has no acknowledgements: errors are caught by the CRC and dropped, and the channel saturates near `1/e` efficiency under heavy load. This lesson dissects every field, simulates backoff, and builds a frame parser you can check against Wireshark.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib frame parser + CSMA/CD backoff simulator)
**Prerequisites:** CSMA/CD and persistent/non-persistent CSMA (Phase 5), Manchester encoding, CRC error detection
**Time:** ~75 minutes

## Learning Objectives

- Lay out a classic Ethernet frame field-by-field with exact byte offsets, and decode a destination as unicast, multicast, or broadcast from its first transmitted bit.
- Explain why the 64-byte minimum frame and the 512-bit slot time are the *same* constraint derived from worst-case 2tau on a 2500 m / four-repeater segment.
- Distinguish the DIX **Type** interpretation from the 802.3 **Length** interpretation using the 0x600 (1536) threshold IEEE adopted in 1997.
- Trace binary exponential backoff through several collisions, computing `[0, 2^min(k,10)-1]` and the 16-attempt give-up point.
- Validate a frame: verify the CRC-32, confirm padding, and read the OUI to identify the NIC vendor.

## The Problem

A junior engineer is staring at a strange capture from a lab that still runs a 10BASE2 thin-coax segment for legacy gear. `ifconfig` shows thousands of `collisions` and `runts`, throughput collapses above a handful of busy hosts, and Wireshark flags some frames as "malformed, length < 64." Someone insists the cable is faulty; someone else blames a "broadcast storm." Neither is right.

The real story is in the MAC sublayer rules. Runts are the truncated remains of frames killed mid-transmission by collisions — exactly what the 64-byte floor exists to make recognizable as garbage. The throughput collapse is binary exponential backoff resolving contention, not a hardware fault. That is why you study the two layers together: the cable geometry (2tau) sets the slot time, the slot time sets the minimum frame, and the minimum frame separates a valid frame from collision debris.

## The Concept

Classic Ethernet is two tightly-coupled layers. The **physical layer** defines the shared coax, Manchester signaling, and propagation geometry. The **MAC sublayer** defines the frame and the CSMA/CD-with-backoff access rule — and its key numbers are *derived from* the physical geometry. The SVG shows the frame layout above the backoff state machine; `code/main.py` parses real frame bytes and simulates the backoff.

### The shared-cable physical layer

Xerox Ethernet (1976) ran 3 Mbps on thick coax. The DIX standard (DEC, Intel, Xerox) fixed it at 10 Mbps; with a minor change this became IEEE 802.3 in 1983.

| Variant | Media | Segment limit | Hosts/segment |
|---|---|---|---|
| Thick (10BASE5) | yellow RG-8 coax, taps every 2.5 m | 500 m | 100 |
| Thin (10BASE2) | RG-58 coax, BNC connectors | 185 m | 30 |

Bits use **Manchester encoding**: every bit cell has a mid-bit transition, so the clock is recoverable and a 10 Mbps stream looks like a 10 MHz signal in the worst case. Segments are joined by **repeaters** (physical-layer regenerators). The hard rule: no two transceivers more than **2500 m** apart, no path through more than **four repeaters** — a ceiling that bounds the round-trip propagation time, which is what makes the MAC protocol correct.

### Anatomy of the frame

The frame on the wire, in transmission order:

```
+----------+-----+------+------+--------+-----------+--------+--------+
| Preamble | SFD | Dest | Src  | Type/  |   Data    |  Pad   |  CRC   |
|  7 bytes | 1 B | 6 B  | 6 B  | Len 2B | 0-1500 B  | 0-46 B |  4 B   |
+----------+-----+------+------+--------+-----------+--------+--------+
 \__ 8-byte preamble __/  \____ 64-byte minimum (Dest..CRC) ____/
```

- **Preamble** — 7 bytes of `10101010` (`0xAA`). Manchester-encoded this is a clean 10 MHz square wave lasting 6.4 us, used by the receiver's PLL to lock onto the sender's clock.
- **Start-of-Frame Delimiter (SFD)** — one byte `10101011` (`0xAB`); the trailing `11` says "real data starts now." (DIX calls all 8 bytes preamble; 802.3 splits the last byte as SFD.)
- **Destination / Source addresses** — 6 bytes each. The first 3 bytes are the **OUI** (Organizationally Unique Identifier), an IEEE-assigned manufacturer block; the vendor programs the low 3 bytes into the NIC, giving each card a globally unique address.
- **Type / Length** — see below.
- **Data + Pad** — payload up to 1500 bytes; if data < 46 bytes the **Pad** fills to the 64-byte minimum.
- **Checksum** — 32-bit CRC, generator `0x04C11DB7` (also used by PPP and ADSL). Error *detection* only: a frame failing CRC is silently dropped.

### Address bit semantics

The first bit transmitted of the destination (low-order bit of the first byte — Ethernet sends each byte LSB-first) is the **Individual/Group (I/G) bit**:

| First transmitted bit | Meaning | Example |
|---|---|---|
| 0 | Unicast (one station) | `00:1b:44:11:3a:b7` |
| 1 | Group: multicast or broadcast | `01:00:5e:...` (IPv4 multicast) |
| all 48 bits = 1 | Broadcast | `ff:ff:ff:ff:ff:ff` |

Multicast is selective (needs group management); broadcast reaches everyone (needs none).

### Type vs Length: the 0x600 rule

DIX uses the field as a **Type** (EtherType) telling the OS which network-layer protocol owns the payload — `0x0800` = IPv4, `0x0806` = ARP, `0x86DD` = IPv6. IEEE 802.3 made it a **Length**, then bolted an LLC header inside the data (8 bytes for 2 bytes of protocol info — a layering violation). In 1997 IEEE reconciled the two with a threshold:

> value <= **0x600 (1536)** is a **Length**; value > 0x600 is a **Type**.

This works because all pre-1997 EtherTypes were already > 1500, the established maximum payload size. The parser uses this test.

### Slot time, 2tau, and the 64-byte minimum

This is the heart of the design. Collision detection takes up to **2tau** — time to reach the far end (tau) plus time for the noise to return. A station finishing *before* 2tau can miss a collision and wrongly think the frame succeeded, so every frame must take **longer than 2tau to transmit**. Worked numbers from the 802.3 spec for a 10 Mbps network (2500 m, four repeaters):

| Quantity | Value |
|---|---|
| Worst-case round trip (incl. repeaters) | ~50 us |
| Bit time at 10 Mbps | 100 ns |
| Minimum bits to span 50 us | 500 bits |
| Rounded up for safety margin | **512 bits = 64 bytes** |
| Slot time (= 512 bit-times) | **51.2 us** |

The 64-byte minimum and the 51.2 us slot time are *the same number expressed two ways*. A station detecting a collision aborts and sends a **48-bit jam** burst so every other station registers it; the truncated leftovers are the runts on the wire.

### CSMA/CD with binary exponential backoff

Classic Ethernet runs **1-persistent CSMA/CD**: sense the channel, transmit the instant it goes idle, listen for collisions while sending. After a collision, time is sliced into 51.2 us slots and a station waits a random number of slots:

| Collision number k | Wait drawn from `[0, 2^min(k,10)-1]` slots |
|---|---|
| 1 | {0, 1} |
| 2 | {0, 1, 2, 3} |
| 3 | {0 … 7} |
| 4 | {0 … 15} |
| 10 | {0 … 1023} |
| 11-15 | frozen at {0 … 1023} |
| 16 | give up — report failure to higher layers |

The window doubles each collision (hence *binary exponential*), freezes at 1023 slots after the 10th, and the frame is abandoned after 16 attempts. Doubling adapts to load: a 2-station collision resolves in a slot or two, while 100 simultaneous senders spread out instead of dog-piling forever. The SVG's lower panel diagrams the state machine: Sense, Transmit, then on collision a jam burst, backoff, and re-sense; otherwise Done.

### No acknowledgements, and efficiency under load

Ethernet sends and forgets — **no MAC-layer ACK**. On low-error wired/fiber media the CRC drops corrupt frames and higher layers (e.g. TCP) recover. Under heavy load with optimal p = 1/k, mean contention is bounded by *e*, so efficiency is `P / (P + 2tau/A)` with `A -> 1/e` as stations grow. Longer cable -> longer contention -> lower efficiency, which is why the standard caps cable length.

## Build It

`code/main.py` is a stdlib-only toolkit with two parts tied to the concept.

1. **Frame parser** — feed it a hex string (preamble optional). It slices out destination, source, Type/Length, payload, and CRC; classifies the destination via the I/G bit; resolves Type vs Length with the 0x600 rule; looks up known OUIs and EtherTypes; recomputes the CRC-32 (`0x04C11DB7`) and reports pass/fail.
2. **CSMA/CD backoff simulator** — models N stations contending, runs slotted binary exponential backoff, counts collisions, and reports slots and efficiency so you watch the `1/e` ceiling emerge.

Run `python3 code/main.py`, then change the frame and station count to watch the decode and backoff curve shift.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decode an address class | I/G bit (first transmitted bit of dest) | You correctly call `ff:ff:ff:ff:ff:ff` broadcast and `01:00:5e:...` multicast |
| Distinguish Type from Length | 2-byte field vs 0x600 threshold | `0x0800` → IPv4 (Type); `0x002E` (46) → Length |
| Spot a runt / collision fragment | Wireshark frame length < 64 bytes | You explain it as truncated collision debris, not a bad cable |
| Predict backoff behavior | Collision count per station | Window matches `[0, 2^min(k,10)−1]`, frozen at 1023, dead at 16 |
| Verify integrity | Recomputed CRC-32 vs trailer | Match: intact; mismatch: dropped, recover upstream |

Wireshark filters: `eth.dst == ff:ff:ff:ff:ff:ff`, `eth.type == 0x0800`, `frame.len < 64`.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **frame-dissection cheat sheet** mapping every byte offset to its field, plus the 0x600 rule and I/G bit decode table.
- A **CSMA/CD backoff runbook**: the `[0, 2^min(k,10)−1]` table, the 16-attempt give-up rule, and what runts/late-collisions mean.
- The **CRC-32 + parser script** (`code/main.py`) wired to your own captures.

Start from `outputs/prompt-classic-ethernet-physical-layer-to-classic-ethernet-mac-sublayer-proto.md`.

## Exercises

1. A frame's Type/Length field reads `0x05DC`. Type or Length, and what value? Change it to `0x0806` — what does the receiver do with the payload?
2. A vendor stretches a 10 Mbps cable to 5000 m with eight repeaters. Compute the new worst-case 2τ and explain which two MAC parameters break and why short frames can now succeed silently after a collision.
3. Two stations collide five times before one wins. List the randomization interval at each collision and the largest possible total backoff (slots and microseconds).
4. Wireshark shows a 48-byte frame on a classic Ethernet segment. Is it legal? If not, what mechanism should have prevented it, and what is it most likely to be?
5. Decode destination `33:33:00:00:00:01` (first transmitted bit). Unicast, multicast, or broadcast? And what does the I/G bit say for `02:00:00:00:00:01`?
6. Run `code/main.py`'s simulator with 2, 10, and 50 stations. Report contention slots and efficiency, and explain the trend via the `1/e` bound and 2τ/A.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Slot time | "the backoff unit" | 512 bit-times = 51.2 µs = worst-case round-trip 2τ across the 2500 m / four-repeater span |
| Minimum frame | "padding rule" | 64 bytes (Dest..CRC) so a sender is still transmitting when a far-end collision returns within 2τ |
| Preamble / SFD | "the AA bytes" | 7x `0xAA` for clock sync + `0xAB` SFD whose trailing `11` marks the start of real data |
| I/G bit | "is it broadcast?" | First transmitted bit of the destination: 0 = unicast, 1 = group (multicast/broadcast) |
| OUI | "the vendor part" | First 3 bytes of a MAC, an IEEE-assigned 2^24 block identifying the NIC manufacturer |
| Type vs Length | "the EtherType" | ≤ 0x600 (1536) = 802.3 Length; > 0x600 = DIX Type (e.g. 0x0800 IPv4) |
| Binary exponential backoff | "random wait" | Random delay in `[0, 2^min(k,10)−1]` slots, frozen at 1023, abandoned after 16 collisions; a 48-bit jam burst precedes it |
| CRC-32 | "the checksum" | Error-detecting trailer using generator `0x04C11DB7`; failing frames are dropped, not corrected |

## Further Reading

- **IEEE 802.3-1983** (and current 802.3-2022) — the authoritative standard: frame format, slot time, backoff.
- Metcalfe, R. & Boggs, D. (1976), "Ethernet: Distributed Packet Switching for Local Computer Networks," *CACM* 19(7) — original paper and `1/e` analysis.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.3 "Ethernet" — the source chapter.
- **RFC 894** — IP datagrams over Ethernet (DIX framing, EtherType 0x0800); **RFC 1042** — IP over IEEE 802 (802.3/LLC/SNAP).
- Charles Spurgeon, *Ethernet: The Definitive Guide* — 10BASE5/10BASE2 cabling and repeaters.
