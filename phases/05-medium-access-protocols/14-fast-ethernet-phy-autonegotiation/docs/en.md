# Fast Ethernet PHY: 100Base-T4/TX/FX, 4B/5B coding, and auto-negotiation

> Fast Ethernet kept the Ethernet frame and MAC service model while changing the physical layer from 10 Mbps signaling to 100 Mbps links. That compatibility was the point: hosts still sent the same Ethernet frames, but the PHY could be 100Base-TX over two copper pairs, 100Base-FX over fiber, or the older 100Base-T4 over four lower-grade copper pairs. The engineering trick was encoding. 100Base-TX uses 4B/5B block coding to guarantee enough signal transitions, then MLT-3 line signaling to reduce spectral energy on Category 5 copper. Auto-negotiation lets link partners advertise capabilities with Fast Link Pulses and choose the best common mode. This lesson connects the bits on the wire to the failures operators actually see: forced speed/duplex mismatches, bad cable pairs, missing link pulses, and PHY errors that look like packet loss higher up the stack.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Ethernet frames, Manchester encoding, collision domains, switched Ethernet
**Time:** ~75 minutes

## Learning Objectives

- Compare 100Base-TX, 100Base-FX, and 100Base-T4 by medium, pair count, encoding, and operational use.
- Explain why 4B/5B coding maps 4 data bits to 5 code bits and how that supports clock recovery.
- Describe how MLT-3 signaling lowers transition frequency for 100Base-TX copper links.
- Explain Ethernet auto-negotiation using Fast Link Pulses, advertised capabilities, and priority resolution.
- Diagnose common Fast Ethernet PHY failures: cable pair faults, speed mismatch, duplex mismatch, and excessive FCS errors.

## The Problem

A warehouse access switch has three troublesome 100 Mbps links. One link never comes up after a cable move. One comes up at 100 Mbps but drops packets under load. One shows terrible throughput after an administrator forced the server NIC to 100/full while leaving the switch port on auto. The application team sees only timeouts. You need to prove which failures live at the physical layer and which are negotiation problems.

Fast Ethernet is a clean place to learn this because the MAC frame stayed stable while the PHY changed underneath. The same 1518-byte frame can ride over twisted pair or fiber, but each medium has different encoding, signaling, and negotiation behavior. When the PHY is wrong, every upper-layer symptom becomes misleading.

## The Concept

### The Fast Ethernet family

Fast Ethernet is IEEE 802.3u's 100 Mbps extension. The names encode the speed and medium:

| PHY | Medium | Pair/fiber use | Encoding/signaling | Notes |
|---|---|---|---|---|
| 100Base-TX | Category 5 UTP/STP copper | Two pairs: one transmit, one receive | 4B/5B + MLT-3 | Dominant Fast Ethernet copper PHY |
| 100Base-FX | Multimode fiber | Two fibers | 4B/5B + NRZI | Longer reach, immune to electrical noise |
| 100Base-T4 | Category 3 copper | Four pairs | 8B/6T ternary signaling | Historical bridge for older cabling |

The MAC above these PHYs still sees Ethernet frames. The PHY below is responsible for turning MAC symbols into recoverable electrical or optical transitions.

### 4B/5B coding

Raw data can contain long runs of zeroes with too few transitions for the receiver to recover the clock. 4B/5B solves this by mapping each 4-bit nibble to a 5-bit code group chosen to contain enough transitions and avoid ambiguous patterns. The cost is 25% overhead:

```
100 Mbps data × 5/4 = 125 Mbaud code-group stream
```

Some 5-bit groups are data symbols; others are control symbols such as idle, start-of-stream, and end-of-stream delimiters. This is why the line keeps sending symbols even when no Ethernet frame is being delivered: the receiver needs continuous signal for link integrity and synchronization.

### MLT-3 on copper

After 4B/5B, 100Base-TX uses MLT-3, a three-level signaling scheme cycling through -1, 0, +1, 0 only when the encoded bit is 1. A 0 bit causes no transition. This reduces the highest fundamental transition frequency compared with simple binary signaling, making 100 Mbps practical over Category 5 twisted pair.

The trade-off is that the receiver depends on cable quality and equalization. Bad pairs, excessive length, poor terminations, and electromagnetic noise show up as symbol errors, FCS errors, link flaps, or autonegotiation failures.

### Auto-negotiation

Ethernet auto-negotiation lets link partners advertise modes and choose the best common one. For 10/100 copper, devices exchange **Fast Link Pulses (FLPs)** during link setup. Each side advertises capabilities such as:

- 10Base-T half duplex
- 10Base-T full duplex
- 100Base-TX half duplex
- 100Base-TX full duplex
- flow-control capability on later links

Priority resolution chooses the highest common mode, typically preferring faster speed and full duplex. If both sides advertise 100Base-TX full duplex, the link comes up 100/full. If one side is forced and stops negotiating, the auto side may detect speed from signal but cannot reliably infer duplex, often falling back to half duplex. That is the classic duplex mismatch.

### Operational failure signatures

PHY and negotiation failures have different evidence:

| Symptom | Likely layer | What to inspect |
|---|---|---|
| Link down | Physical medium or unsupported mode | Cable pairs, optics, admin state, advertised modes |
| Link flaps | Physical medium quality | Error counters, cable test, distance, connectors |
| FCS/CRC errors | Signal corruption or duplex mismatch | Interface counters on both ends |
| Late collisions | Half-duplex timing or duplex mismatch | Duplex settings, collision counters |
| Good speed, terrible throughput | Often duplex mismatch | One side full, other half; asymmetric counters |
| Autoneg fails to best mode | Advertisement mismatch | Capability registers or switch port status |

The rule: do not debug TCP until the link counters make sense. A bad PHY can masquerade as retransmissions, slow HTTP, DNS failures, or application instability.

## Build It

1. Open `code/main.py` and locate any functions that model 4B/5B encoding, MLT-3 transitions, or negotiation priority.
2. Encode several nibbles into 5-bit code groups. Confirm the encoded stream is longer than the input by 25%.
3. Feed the code stream into an MLT-3 transition model. Count transitions for alternating ones, all zeroes, and realistic frame-like data.
4. Simulate auto-negotiation between two devices with overlapping capabilities. Record the selected speed and duplex.
5. Simulate a forced 100/full NIC connected to an auto switch. Record why speed may be detected but duplex can fall back incorrectly.
6. Optional lab step: on real hardware, compare `show interface` or OS NIC counters before and after forcing a mismatched duplex setting in an isolated lab.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Explain 4B/5B overhead | Input bits versus code bits | 4 bits become 5 bits; 100 Mbps data uses 125 Mbaud symbols |
| Show MLT-3 behavior | Transition sequence | Only encoded 1 bits advance the -1/0/+1/0 cycle |
| Compare PHYs | Medium table | 100Base-TX and FX both use 4B/5B but different media/signaling |
| Resolve negotiation | Capability intersection | Highest common advertised mode is selected |
| Diagnose mismatch | Counter pattern | Half-duplex side sees collisions; full-duplex side sees FCS/errors/drops |

## Ship It

Produce one artifact under `outputs/`:

- A 4B/5B and MLT-3 worksheet showing input nibbles, code groups, transition sequence, and overhead.
- A negotiation matrix with at least five device-pair cases and the selected speed/duplex.
- A troubleshooting runbook for "Fast Ethernet link is up but slow" that orders checks from physical media through duplex and counters.

Start from `outputs/prompt-fast-ethernet-phy-autonegotiation.md` if present, or create `outputs/fast-ethernet-phy-runbook.md`.

## Exercises

1. Why does 100Base-TX need a 125 Mbaud symbol stream to carry 100 Mbps of data? Show the arithmetic.
2. Explain why 4B/5B improves clock recovery compared with sending arbitrary raw data bits directly.
3. A 100Base-TX link is up, but one side reports FCS errors and the other reports late collisions. What is the most likely cause, and why?
4. Compare 100Base-TX and 100Base-FX for a noisy industrial environment. Which failure modes disappear with fiber, and which remain?
5. Two devices advertise these modes: A advertises 10/half, 10/full, 100/half; B advertises 10/full, 100/full. What is the best common mode?
6. Why is forcing one side to 100/full while leaving the other side on auto a bad operational practice?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| 100Base-TX | "Fast Ethernet copper" | 100 Mbps over two twisted pairs using 4B/5B coding and MLT-3 signaling |
| 100Base-FX | "Fast Ethernet fiber" | 100 Mbps over fiber using 4B/5B with optical signaling for longer/noisier environments |
| 100Base-T4 | "Old Fast Ethernet" | Historical 100 Mbps PHY over four Category 3 pairs using ternary signaling |
| 4B/5B | "Encoding overhead" | Block code mapping 4 data bits to 5 symbols to guarantee transitions and reserve control codes |
| MLT-3 | "Three-level signaling" | Copper line code that cycles through three voltage levels on 1 bits to reduce transition frequency |
| Fast Link Pulse | "Autoneg pulse" | Pulse burst used by 10/100 copper devices to advertise link capabilities |
| Auto-negotiation | "Speed detection" | Capability exchange and priority selection for speed, duplex, and related link modes |
| Duplex mismatch | "Bad autoneg" | One side full duplex and the other half duplex, causing collisions, FCS errors, and poor throughput |
| FCS error | "Bad frame checksum" | Ethernet frame failed the frame check sequence, often due to signal corruption or duplex mismatch |

## Further Reading

- IEEE 802.3u — Fast Ethernet PHYs, 100Base-TX/FX/T4, and auto-negotiation.
- IEEE 802.3, clause 28 — Auto-negotiation for twisted-pair Ethernet.
- Charles Spurgeon, *Ethernet: The Definitive Guide* — Fast Ethernet media, encoding, and duplex troubleshooting.
- A. Tanenbaum & D. Wetherall, *Computer Networks*, 5th ed., Chapter 2 and Chapter 4 — encoding, physical media, and Ethernet evolution.
