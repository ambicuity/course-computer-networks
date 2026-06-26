# Lab: Ethernet channel efficiency under varying load and the bandwidth-distance product

> Measure why classic shared Ethernet is fast when the cable is short and the frames are large, but wastes time when the propagation delay becomes visible. Ethernet's CSMA/CD rule only works because a sender can detect a collision before it has finished sending the minimum 64-byte frame. That requirement creates the famous slot time: 512 bit-times on 10/100 Mbps Ethernet, or 51.2 µs at 10 Mbps and 5.12 µs at 100 Mbps. This lab turns that timing rule into numbers: frame transmission time, one-way propagation delay, round-trip collision detection, channel efficiency, and the bandwidth-distance product. The goal is not to memorize Ethernet speeds; it is to explain why shared half-duplex Ethernet had a maximum diameter, why minimum frame size mattered, and why switched full-duplex Ethernet made CSMA/CD disappear from modern links.

**Type:** Lab
**Languages:** Python, simulation
**Prerequisites:** CSMA/CD, binary exponential backoff, Ethernet frame format, propagation delay
**Time:** ~75 minutes

## Learning Objectives

- Compute Ethernet frame transmission time from frame size and line rate, including the 64-byte minimum frame and the 1518-byte non-tagged maximum frame.
- Explain the slot-time rule: a transmitter must still be sending when a worst-case collision reflection returns.
- Use the bandwidth-distance product to decide how many bits can be in flight on a shared medium.
- Measure channel efficiency under rising offered load and identify when collisions dominate useful throughput.
- Explain why Fast Ethernet shortened collision domains and why Gigabit Ethernet used carrier extension only for half-duplex compatibility.

## The Problem

A lab still has an old half-duplex Ethernet segment connecting industrial controllers through a repeater. During normal telemetry, it works. During a firmware rollout, every controller starts transferring images at once, and throughput falls far below the advertised 10 Mbps. The switch replacement budget is approved, but you need to write the incident note: was the link slow because Ethernet is inefficient, because the cable was too long, or because the shared collision domain was overloaded?

The answer lives in timing. A station cannot know a frame collided until the collision signal can propagate from the farthest point in the network and back. If the frame is too short, the sender may finish, assume success, and only later discover that the receiver saw garbage. Ethernet prevents that by defining a minimum frame length and a slot time. This lab makes you calculate those limits and then simulate the collision cost under load.

## The Concept

### Transmission time versus propagation time

Two clocks matter on every link:

```
transmission_time = frame_bits / line_rate_bps
propagation_time = cable_length_m / signal_speed_mps
```

Transmission time is how long it takes to push the bits onto the wire. Propagation time is how long the first bit takes to travel across the medium. On copper or fiber, signal speed is roughly 2 × 10^8 m/s, about two-thirds the speed of light. For a 64-byte Ethernet frame at 10 Mbps:

```
64 bytes × 8 = 512 bits
512 bits / 10,000,000 bps = 51.2 µs
```

That 51.2 µs is the 10 Mbps Ethernet slot time. It is long enough for a worst-case collision to be detected in a properly sized shared segment.

### The collision-detection rule

CSMA/CD is not merely listen-before-talk. It is listen-while-talking. A station transmits, monitors the medium, and aborts if it detects energy inconsistent with its own signal. The network must be engineered so the worst-case collision returns before the sender finishes the minimum frame:

```
minimum_frame_time >= 2 × maximum_one_way_propagation_time + repeater_delay_budget
```

This is why early Ethernet standards specified both a minimum frame size and maximum network diameter. If you stretch the cable too far or add too many repeaters, late collisions appear: collisions detected after the first slot time. Late collisions are not normal congestion; they are evidence of a duplex mismatch, bad cabling, or an oversized collision domain.

### Bandwidth-distance product

The bandwidth-distance product tells you how many bits are physically in flight:

```
bits_in_flight = line_rate_bps × propagation_time_seconds
```

A 500 m copper segment with signal speed 2 × 10^8 m/s has one-way propagation delay of 2.5 µs. At 10 Mbps, that is only 25 bits in flight one way. At 1 Gbps, the same cable would hold 2500 bits in flight. Higher speed makes the same distance look longer in bit-times, which is why keeping half-duplex collision detection at gigabit speeds required awkward compatibility mechanisms.

### Efficiency under load

An ideal full-duplex point-to-point link has no collisions: one sender, one receiver, independent transmit and receive paths. A shared half-duplex Ethernet segment has a contention process. At low load, most frames succeed on the first try. At high load, many stations defer, collide, jam, and back off. Binary exponential backoff prevents permanent collapse, but every collision wastes:

- the partial frame time before detection,
- the jam signal,
- the interframe gap,
- the random backoff slots,
- and the retransmission attempt.

The useful efficiency is therefore:

```
efficiency = delivered_payload_bits / elapsed_channel_bit_capacity
```

The simulator for this lab should show the shape: nearly linear throughput at light load, a bend as collisions rise, and a plateau or decline when the segment is saturated.

## Build It

1. Open `code/main.py` and identify the parameters for line rate, cable length, frame size, offered load, and station count.
2. Run the script with the default 10 Mbps shared segment and record: frame transmission time, one-way propagation delay, round-trip propagation delay, slot time, collision count, and delivered throughput.
3. Change frame size from 64 bytes to 1518 bytes. Re-run and explain why larger frames usually improve efficiency even though they occupy the medium longer.
4. Change the line rate from 10 Mbps to 100 Mbps while keeping distance constant. Re-run and watch how propagation delay consumes more bit-times.
5. Increase offered load until collision retries dominate. Record the point where useful throughput stops rising.
6. Optional extension: add a `late_collision` counter that fires when collision detection occurs after the minimum frame transmission time.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute slot timing | Printed minimum-frame time and propagation round trip | 64-byte frame at 10 Mbps is 51.2 µs; collision must return within that window |
| Compare frame sizes | Throughput for 64-byte and 1518-byte frames | Larger frames waste less overhead per payload bit under the same collision rate |
| Stress offered load | Collision and retry counts as load increases | Throughput bends or plateaus as contention rises |
| Test distance sensitivity | Same load at short and long cable lengths | Longer propagation delay increases the collision window |
| Explain modernization | Short written note in `outputs/` | Switched full-duplex removes the shared collision domain, so CSMA/CD is disabled |

## Ship It

Produce one artifact under `outputs/`:

- A timing worksheet showing frame transmission time, propagation delay, round-trip delay, slot time, and bits in flight for at least three scenarios.
- A throughput table comparing light, medium, and saturated offered load.
- A short incident note explaining whether a real symptom is congestion, late collisions, a duplex mismatch, or normal shared-medium contention.

Start from `outputs/prompt-ethernet-performance-analysis-lab.md` if present, or create `outputs/ethernet-performance-analysis.md` with your measurements.

## Exercises

1. Calculate the transmission time of a 64-byte frame and a 1518-byte frame at 10 Mbps, 100 Mbps, and 1 Gbps. Which values are larger than a 5 µs round-trip propagation delay?
2. A 10 Mbps half-duplex segment reports late collisions. Give three likely causes and explain why normal congestion is not enough to create a late collision.
3. For a 300 m cable with signal speed 2 × 10^8 m/s, compute one-way propagation delay and bits in flight at 10 Mbps and 100 Mbps.
4. Run the simulator with 2, 10, and 50 stations at the same aggregate offered load. Does the number of contenders change collision behavior? Explain using backoff synchronization.
5. Explain why full-duplex Ethernet links do not use CSMA/CD even though they still use Ethernet frames.
6. If a small-packet workload performs worse than a large-file transfer on a shared segment, separate the effects of per-frame overhead, collision probability, and payload efficiency.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Slot time | "Ethernet timing window" | The 512 bit-time interval used by classic Ethernet so collisions are detected before a minimum frame finishes |
| Minimum frame size | "64 bytes" | The smallest Ethernet frame that keeps the sender transmitting long enough for worst-case collision detection |
| Propagation delay | "Cable delay" | Time for a signal edge to travel across the medium, independent of frame size |
| Transmission time | "Serialization delay" | Time required to put all frame bits onto the link at the configured line rate |
| Bandwidth-distance product | "Bits in the pipe" | The amount of data physically in flight, equal to bandwidth multiplied by propagation delay |
| Late collision | "Collision after the window" | A collision detected after the first slot time, usually indicating an invalid collision domain or duplex mismatch |
| Collision domain | "Shared segment" | The set of stations whose transmissions can collide with each other on a half-duplex medium |
| Full duplex | "Send and receive at once" | Separate transmit and receive paths; no shared contention, no CSMA/CD |

## Further Reading

- IEEE 802.3, clause 4 — MAC method, frame timing, slot time, jam, and backoff.
- IEEE 802.3, clause 13 and 14 — classic 10 Mbps media and repeater timing constraints.
- A. Tanenbaum & D. Wetherall, *Computer Networks*, 5th ed., Chapter 4 — Ethernet performance and CSMA/CD.
- Charles Spurgeon, *Ethernet: The Definitive Guide* — collision domains, late collisions, and practical Ethernet design.
