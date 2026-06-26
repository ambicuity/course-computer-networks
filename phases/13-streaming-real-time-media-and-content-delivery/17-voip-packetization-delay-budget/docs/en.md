# VoIP Packetization and Delay Budget

> Voice over IP packs digitized speech into RTP packets at fixed intervals. Every millisecond of packetization, network, and playout delay eats into the budget that keeps a call feeling live.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 13 lessons 01-16 (RTP/RTCP, Jitter Buffering, FEC and Interleaving)
**Time:** ~75 minutes

## Learning Objectives

- Decompose end-to-end mouth-to-ear delay into its component parts
- Explain how the packetization interval trades off latency against header overhead
- Compute the delay budget for a G.711 voice call and identify which component dominates
- Describe how codec frame size, look-ahead, and jitter buffer depth contribute to total delay
- Recognize the ITU-T G.114 one-way delay thresholds and their perceptual consequences
- Implement a delay-budget calculator that accounts for each stage

## The Problem

A phone call feels interactive only if the round-trip delay stays below roughly 250 ms (one-way under 150 ms). On the circuit-switched PSTN that was easy: the path was short and mostly digital. On IP networks, delay accumulates at every stage: the codec waits to fill a frame, the packetizer waits to fill a payload, the network queues the packet, the jitter buffer holds it before playout, and the decoder may need look-ahead. If the sum exceeds the budget, users start talking over each other and the call becomes half-duplex. The engineer must measure each component, add them up, and decide which knob to turn when the budget overflows.

## The Concept

### The delay budget

End-to-end one-way delay in VoIP is the sum of several distinct stages, each with a physical cause and a tuning knob:

```text
mouth -> microphone -> codec -> packetizer -> network -> jitter buffer -> decoder -> ear
 |        capture     encode    pack          transmit     playout      decode    render
 |        delay       delay     delay         delay        delay        delay     delay
```

The total one-way delay is:

```
D_total = D_capture + D_encode + D_packetization
        + D_network + D_jitter_buffer + D_decode + D_render
```

### Component definitions

- **Capture delay**: time from sound hitting the microphone to the codec receiving samples. Typically 1-5 ms on modern hardware; can be tens of ms on cheap sound cards.
- **Codec encode delay**: time the codec spends compressing a frame. For G.711 (PCM) this is negligible; for G.729 (CS-ACELP) it is ~5 ms of processing plus 10 ms of frame time; for wideband Opus it can include look-ahead.
- **Packetization delay**: the time the sender waits to accumulate enough codec frames to fill one RTP payload. G.711 at 20 ms produces 160 bytes per packet; at 40 ms it produces 320 bytes. Larger payloads mean fewer packets (lower header overhead) but more delay.
- **Network delay**: propagation + serialization + queuing. A coast-to-coast fiber path is ~30-40 ms; a satellite hop is ~250 ms. Queuing delay varies with congestion.
- **Jitter buffer delay**: the playout buffer depth, typically 20-60 ms, set to absorb jitter (see the Jitter Buffering lesson).
- **Decode delay**: time to decompress and render a frame. Usually small (1-5 ms) but can be larger for complex codecs.
- **Look-ahead delay**: some codecs (G.729, Opus, AAC-LD) need to inspect the next frame before emitting the current one, adding one frame time of delay.

### The packetization tradeoff

```text
packetization_interval = T  (ms per packet)
  samples per packet   = sample_rate * T / 1000
  payload bytes        = samples * bytes_per_sample
  packets per second   = 1000 / T

  IP/UDP/RTP header    = 40 bytes (or 2 with header compression)
  overhead_fraction   = 40 / (payload + 40)
```

At T=20 ms with G.711 (8 kHz, 1 byte/sample): payload = 160 bytes, overhead = 40/200 = 20%. At T=60 ms: payload = 480 bytes, overhead = 40/520 = 7.7%. So larger T cuts overhead but adds T ms to the delay budget directly. The classic VoIP choice is 20 ms for low latency or 30-40 ms to save bandwidth on slow links.

### ITU-T G.114 delay classes

| One-way delay | Rating | User perception |
|---|---|---|
| 0-150 ms | Good | Acceptable for nearly all users; unnoticeable |
| 150-300 ms | Acceptable | Noticeable on highly interactive calls; acceptable for intercontinental |
| 300-700 ms | Poor | Talk-over, echo, difficulty interrupting |
| >700 ms | Unusable | Walkie-talkie behavior |

These are one-way, mouth-to-ear. Round-trip is roughly double. Satellite links land in the "Poor" band because of the 250 ms up-down hop.

### Echo and its interaction with delay

Echo arises when speech from the near end leaks back from the far end (acoustic echo from the speaker, or electrical echo from a hybrid at the PSTN boundary). Short delay echo sounds like sidetone and is tolerable. Long delay echo is extremely annoying because the talker hears their own voice delayed. The longer the one-way delay, the more aggressive the echo canceller must be. This is why echo cancellation is mandatory above ~25 ms one-way delay.

### A worked example

G.711 over a 40 ms packetization, 30 ms network, 40 ms jitter buffer:

```
D_capture        =   1 ms
D_encode         =   0 ms  (G.711 is PCM, trivial)
D_packetization  =  40 ms  (40 ms interval)
D_network        =  30 ms
D_jitter_buffer  =  40 ms
D_decode         =   1 ms
D_render         =   1 ms
                 -------
D_total          = 113 ms  (Good, under 150 ms)
```

Now add a G.729 codec (10 ms frame + 5 ms look-ahead) and a 200 ms congested path:

```
D_capture        =   1 ms
D_encode         =   5 ms  (G.729 processing)
D_lookahead      =   5 ms
D_packetization  =  20 ms  (two 10 ms frames per packet)
D_network        = 200 ms  (congested queue)
D_jitter_buffer  =  60 ms  (wider to absorb the jitter)
D_decode         =   2 ms
D_render         =   1 ms
                 -------
D_total          = 294 ms  (Acceptable, near the 300 ms boundary)
```

The network delay dominates. No codec change can fix that; the only lever is routing or QoS.

## Build It

The script below implements a delay-budget calculator. It:

1. Models each delay component as a named stage with a tunable value.
2. Sums the components and classifies the result per G.114.
3. Sweeps the packetization interval and shows the overhead-vs-delay tradeoff.
4. Compares three codec profiles (G.711, G.729, Opus) on the same path.
5. Identifies which component dominates so the engineer knows where to optimize.

```python
# Core idea (see code/main.py)
budget = DelayBudget(stages={...})
total = budget.total()
classification = classify_g114(total)
dominant = budget.dominant_component()
```

## Use It

```bash
python3 code/main.py
```

Expected output: a component-by-component breakdown of one-way delay for three codec profiles, a packetization sweep showing overhead versus delay, and a G.114 classification for each scenario.

## Ship It

- Use the calculator to build a delay budget for a real call path you measured (ping + jitter from an RTCP trace).
- Identify the dominant component and propose one concrete optimization (QoS, codec swap, smaller packetization).
- Export the sweep table as CSV and include it in a design review artifact.
- Write a one-page runbook: "If the call sounds half-duplex, check these components in this order."

## Exercises

1. Add a satellite hop (250 ms) to the network delay and recompute the budget. Which G.114 class does it fall into?
2. Change packetization from 20 ms to 60 ms for G.711 on a 1 Mbps link. Compute the bandwidth savings and the added delay.
3. Swap G.729 for Opus with 20 ms frames and 5 ms look-ahead. Compare total delay and expected quality.
4. Add an echo path: model a 30 ms electrical echo at the far end and determine whether echo cancellation is mandatory.
5. Find the maximum network delay that keeps a G.711 call at 20 ms packetization within the "Good" (150 ms) class, assuming a 40 ms jitter buffer.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Delay budget | "Latency headroom" | The sum of every delay stage from mouth to ear that must stay under a target to keep a call interactive |
| Packetization interval | "Frame time" | The number of milliseconds of audio packed into one RTP payload; trades latency for header efficiency |
| Look-ahead | "Codec buffering" | Samples from the next frame that a codec must inspect before emitting the current frame, adding one frame of delay |
| G.114 | "A spec" | ITU-T recommendation defining one-way delay classes and their perceptual acceptability |
| Jitter buffer delay | "Playout delay" | The depth of the playout buffer, set to absorb jitter, and a line item in the delay budget |
| Echo canceller | "Echo trimmer" | Signal processing that removes leaked near-end speech from the far-end path; mandatory as delay grows |
| Serialization delay | "Line time" | The time to clock a packet onto a link: packet_bits / link_rate; matters on slow links |
| Mouth-to-ear delay | "End-to-end delay" | The total one-way delay from the talker's mouth to the listener's ear, the quantity G.114 bounds |

## Further Reading

- [ITU-T G.114](https://www.itu.int/rec/T-REC-G.114) - one-way transmission time recommendations
- [RFC 3550](https://www.rfc-editor.org/rfc/rfc3550) - RTP, which carries the packetized voice
- [G.711 and G.729 codec summaries](https://www.itu.int/rec/T-REC-G.711) - codec frame sizes and look-ahead
- [Voice Quality and Delay](https://www.cisco.com/c/en/us/td/docs/ios/solutions_docs/voip_qos.html) - operational perspective on the delay budget