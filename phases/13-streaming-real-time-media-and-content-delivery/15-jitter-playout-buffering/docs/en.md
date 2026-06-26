# Jitter and Playout Buffering

> Packets arrive at irregular intervals. The playout buffer absorbs the wobble so audio plays smoothly. Too small and you get gaps; too large and you get latency.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Phase 13 lessons 01-14 (RTP/RTCP, Real-time Conferencing)
**Time:** ~75 minutes

## Learning Objectives

- Define jitter and distinguish it from absolute delay
- Explain how a playout buffer converts jittered arrivals into smooth playback
- Compute optimal playout delay from jitter statistics
- Implement adaptive playout delay that tracks network conditions
- Analyze the tradeoff between latency and packet loss (late packets)

## The Problem

In a perfect network, every packet arrives exactly 20ms after the previous one. Real networks add variable delay: packet 1 takes 15ms, packet 2 takes 45ms, packet 3 takes 10ms. If the receiver plays each packet immediately on arrival, the audio speeds up and slows down, producing choppy, robotic speech. The solution is a playout buffer: delay the first packet by a fixed amount (say 60ms), then play subsequent packets on a smooth schedule. Packets that arrive before their scheduled playout time wait in the buffer. Packets that arrive after their playout time are too late and must be discarded (packet loss).

## The Concept

### Jitter vs delay

- **Delay**: the time a packet takes from sender to receiver. Constant delay is fine; variable delay is the problem.
- **Jitter**: the variation in delay. It is the deviation from the expected interarrival time. A playout buffer does not reduce delay; it absorbs jitter.

### Fixed playout delay

```text
sender schedules:  t=0   t=20  t=40  t=60  t=80  (ms)
network delay:     25    55    15    80    30    (ms, variable)
arrival times:     25    75    55    140   110   (ms)

with playout_delay=60ms:
  playout times:   60    80    100   120   140   (ms)
  buffer wait:     35    5     45    -20(LATE!) 30
```

Packet 4 arrives at 140ms but its playout was at 120ms. It is 20ms late and must be discarded. Increasing playout_delay to 100ms would save packet 4 but add 40ms more latency to all packets.

### Adaptive playout delay

Instead of a fixed delay, the receiver tracks the network's jitter and adjusts the playout delay dynamically:

```text
estimated_delay = average_delay + 4 * jitter_deviation
playout_delay = max(min_delay, estimated_delay)
```

When jitter is low, the delay shrinks (lower latency). When jitter spikes, the delay grows (fewer late packets). The adjustment happens during silent periods (talkspurt boundaries) to avoid audible glitches.

### The tradeoff

```text
playout_delay ↑  =>  latency ↑  but  late_loss ↓
playout_delay ↓  =>  latency ↓  but  late_loss ↑
```

The optimal delay is where the marginal latency cost equals the marginal quality gain. For voice, 50-150ms is typical. For interactive video, 100-300ms. For one-way streaming, 1-5 seconds is acceptable.

## Build It

The script below simulates a playout buffer processing jittered RTP packets. It demonstrates:

1. Generating packets with variable network delay
2. Fixed playout delay: showing late packets and buffer occupancy
3. Adaptive playout delay: tracking jitter and adjusting
4. Comparing late-loss rates at different delay settings
5. Buffer occupancy visualization

```python
# Core idea (see code/main.py for full implementation)
for pkt in arrivals:
    playout_time = base_playout + pkt.seq * frame_duration
    if arrival > playout_time:
        late_loss += 1  # too late to play
    else:
        buffer.append(pkt)  # wait for playout
```

## Use It

```bash
python3 code/main.py
```

Expected output: a trace showing each packet's arrival time, scheduled playout time, buffer wait, and whether it was played or lost. A sweep of playout delays shows the latency-vs-loss tradeoff. The adaptive mode shows the delay tracking the jitter.

## Ship It

- Use the sweep results to pick an optimal playout delay for a target loss rate (e.g., < 1% late loss).
- Extend the adaptive algorithm with talkspurt detection (adjust only during silence).
- Export the buffer occupancy over time to visualize how the buffer fills and drains.

## Exercises

1. Increase jitter standard deviation from 15ms to 40ms and find the new optimal playout delay.
2. Add a burst-loss model (packets 10-15 all delayed by 200ms) and show how adaptive delay responds.
3. Implement a "freeze" policy: if buffer drops below 1 frame, pause playback for 100ms to rebuild.
4. Compute the Mean Opinion Score (MOS) from the late-loss rate and compare with the latency-adjusted MOS.
5. Compare fixed vs adaptive playout over 1000 packets and report average latency and total loss for each.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Jitter | "Network wobble" | The variation in packet interarrival time, not the absolute delay |
| Playout buffer | "A queue" | A delay buffer that holds packets until their scheduled playback time, absorbing jitter |
| Playout delay | "Buffer size" | The fixed or adaptive delay added before the first packet plays, trading latency for smoothness |
| Late loss | "Dropped packet" | A packet that arrives after its scheduled playout time and must be discarded |
| Talkspurt | "A speech burst" | A continuous period of speech between silences, the natural point to adjust playout delay |
| Adaptive playout | "Smart buffering" | Dynamically adjusting the playout delay based on measured jitter statistics |
| Buffer occupancy | "How full" | The number of packets waiting in the buffer at any given time |

## Further Reading

- [RFC 3550 Appendix A.8](https://www.rfc-editor.org/rfc/rfc3550) - jitter buffer algorithm
- [Playout Delay Algorithms for Voice over IP](https://ieeexplore.ieee.org/document/969566) - academic survey
- [Jitter Buffer (Wikipedia)](https://en.wikipedia.org/wiki/Jitter_buffer) - overview
