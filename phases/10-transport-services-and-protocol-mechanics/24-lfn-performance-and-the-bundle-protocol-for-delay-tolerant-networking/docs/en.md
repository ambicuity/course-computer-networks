# LFN Performance and the Bundle Protocol for Delay-Tolerant Networking

> Long Fat Networks (LFNs) are paths where the **bandwidth-delay product** dwarfs the original 64 KB TCP window. RFC 1072 and RFC 1323 catalog the problems and fixes: 32-bit sequence numbers that wrap in 34 seconds at 1 Gbps, 16-bit windows that cap flow control at 65,535 bytes, simple retransmission schemes (go-back-n) that waste an entire BD product on every loss, and stop-and-wait protocols whose latency is bounded by the speed of light. The fixes are **PAWS** (RFC 1323, timestamp-based protection against wrapped sequence numbers), **Window Scale** (RFC 1323, up to 1 GB windows), **selective repeat** semantics carried by SACK, and **jumbo frames** (up to 9 KB) or **jumbograms** (up to 64+ KB). At a different extreme, **Delay-Tolerant Networking** (RFC 4838) and the **Bundle Protocol** (RFC 5050, updated by RFC 9171) handle paths where there is **no end-to-end connection at all**: low-earth-orbit satellites passing in and out of range, submarines, buses that carry data physically, sensor networks that sleep. DTN uses **store-carry-forward** with messages called **bundles**, and the architecture is meant to tolerate very long delays (Earth-Mars RTT ~ 20 minutes). This capstone simulates both regimes: an LFN throughput calculator that proves why window scaling matters, and a small DTN router that schedules bundles across intermittent contacts.

**Type:** Capstone
**Languages:** Python, shell, simulation
**Prerequisites:** All previous lessons in this phase (17–23), bandwidth-delay product math, basic DTN concepts
**Time:** ~150 minutes

## Learning Objectives

- Compute the bandwidth-delay product for an LFN path and the minimum TCP window size required to fill the pipe.
- Explain why PAWS (RFC 1323) is required when the sequence-number wrap time falls below the MSL.
- Identify the four LFN problems (sequence wrap, small window, slow retransmit, speed-of-light) and match each to its RFC-defined fix.
- Walk a Bundle Protocol header (RFC 5050 primary block + payload block + optional security block) and identify Destination, Source, Custodian, Report, Creation timestamp, Lifetime, and Dictionary.
- Simulate a DTN router that schedules bundles across intermittent contacts with known start times and durations.
- Compare TCP's "always-connected" assumption with the Bundle Protocol's "store-carry-forward" model and explain when each is appropriate.

## The Problem

You are asked to design a transport for two extreme environments. The first is a 10 Gbps transcontinental research link with 80 ms RTT — a "long fat network" where the 1981 TCP design assumptions break. The second is a sensor network deployed on buses and ferries — a delay-tolerant network where there is no end-to-end path for hours at a time. The same design (TCP) cannot serve both; you need to know which knobs to turn for each.

The deeper problem is that TCP's **end-to-end assumption** — sender and receiver are continuously connected by some working path — is itself the limiting factor. On an LFN you keep the assumption and stretch TCP (bigger windows, scaled sequence numbers, SACK). On a DTN you abandon the assumption entirely and let intermediate nodes store, carry, and forward bundles until a contact appears.

## The Concept

### The four LFN problems (RFC 1072, RFC 1323)

**Problem 1 — sequence-number wrap.** A 32-bit sequence number wraps in `2^32 / bandwidth` seconds. On a 1 Gbps link the wrap time is 34 seconds, well under the 120 s MSL. A stale segment from the previous wrap could be accepted as belonging to the new connection. **Fix: PAWS** (Protection Against Wrapped Sequence numbers) — the timestamp option in RFC 1323 carries a 32-bit timestamp that the receiver uses to discard segments with timestamps older than the most recent one.

**Problem 2 — small window.** A 16-bit Window field caps flow control at 65,535 bytes. On a 1 Gbps / 40 ms RTT link, this caps throughput at ~13 Mbps. **Fix: Window Scale** option (RFC 1323) — both sides agree on a shift count up to 14, multiplying the effective window up to 1 GB.

**Problem 3 — go-back-n waste.** A single loss under go-back-n requires retransmitting everything sent after the loss — an entire BD product of bandwidth wasted. **Fix: selective repeat via SACK** (RFC 2018 + RFC 3517).

**Problem 4 — speed-of-light bound.** A 4,000 km fiber link has a 40 ms RTT (round-trip speed of light in fiber is ~200,000 km/s). No protocol can deliver a message faster than that — even if the link runs at 1 Tbps. **Fix: design for speed, not bandwidth optimization** (Mogul 1993). Minimize state and processing per segment.

### The bandwidth-delay product revisited

| Path | Bandwidth | RTT | BD product (bytes) | Min window |
|---|---|---|---|---|
| Geostationary satellite | 50 Mbps | 540 ms | 3,375,000 | 3,375,000 (~3.2 MB) |
| Transcontinental 1 Gbps | 1 Gbps | 40 ms | 5,000,000 | 5,000,000 (~4.8 MB) |
| Transcontinental 10 Gbps | 10 Gbps | 80 ms | 100,000,000 | 100,000,000 (~95 MB) |
| Mars-Earth link | 6 Mbps | 1,200 s (20 min) | 900,000,000 | 900 MB |

The Mars-Earth case is the canonical LFN: 1.2 Gbit/s × 20 min of round-trip latency means you cannot do interactive control — software must be uploaded and run autonomously, and Bundle-style store-and-forward is the only practical model.

### DTN architecture (RFC 4838)

The DTN architecture relaxes the end-to-end assumption. A **DTN node** is any device with persistent storage that can hold bundles until a **contact** — a working link — appears. The contact model:

- **Deterministic contacts**: known in advance (LEO satellite orbital mechanics, scheduled ferries).
- **Predicted contacts**: known statistically (bus timetables, off-peak ISP bandwidth).
- **Opportunistic contacts**: random (mobile phones coming into Wi-Fi range).

Routing depends on the contact type: deterministic contacts use Contact Graph Routing (CGR); opportunistic contacts use spray-and-wait or epidemic routing.

### The Bundle Protocol (RFC 5050, updated by RFC 9171)

The Bundle Protocol runs **above** TCP/IP (or any other convergence-layer transport) and is **application-agnostic** — anything can send a bundle. The primary block carries:

| Field | Bits | Purpose |
|---|---|---|
| Version | 8 | Protocol version (currently 7 per RFC 9171) |
| Flags | 20 | Class of service, custody-transfer request, ack request |
| Destination | variable | URI-like identifier (not an IP address) |
| Source | variable | URI-like identifier |
| Report | variable | Where status reports go |
| Custodian | variable | Current responsible node (shifts with custody transfer) |
| Creation | variable | Creation timestamp + sequence number |
| Lifetime | variable | Absolute time at which the bundle is no longer useful |
| Dictionary | variable | URI compression table |

The payload block carries the application data; optional blocks carry security parameters (Bundle Security Protocol, RFC 9172).

### Custody transfer

In the Internet, the source is usually the custodian (it retransmits on loss). In a DTN, the source may be **disconnected** for hours and cannot retransmit. Custody transfer lets a DTN node closer to the destination take over retransmission responsibility. Each custody transfer is acknowledged at the convergence-layer level.

### Convergence layers

The Bundle Protocol needs to run over *something*. Convergence layers adapt it to TCP, UDP, LTP (Licklider Transmission Protocol, designed for deep-space links with very long delays), or even raw files on a USB stick carried by hand.

### When to use TCP vs Bundle Protocol

| Scenario | Use | Why |
|---|---|---|
| Web browsing over fiber | TCP | End-to-end path exists, latency tolerable |
| Bittorrent over DSL | TCP | Same |
| 10 Gbps transcontinental RTT 80 ms | TCP + RFC 1323 + SACK + jumbo frames | LFN extensions cover the cases |
| Earth-Mars link | Bundle Protocol over LTP | 20-min RTT makes TCP ack/retransmit useless |
| Sensor network on buses | Bundle Protocol over Wi-Fi or BLE | End-to-end path only exists during stops |
| Disaster-response ad-hoc radio | Bundle Protocol over TCP/UDP | Topology changes constantly |

## Build It

```bash
cd phases/10-transport-services-and-protocol-mechanics/24-lfn-performance-and-the-bundle-protocol-for-delay-tolerant-networking
python3 code/main.py
```

The script:

1. Computes the BD product and minimum window for five sample paths (including Earth-Mars).
2. Computes the sequence-number wrap time at each bandwidth and shows whether PAWS is required.
3. Builds a tiny Bundle Protocol primary block in bytes (just enough to print the field layout).
4. Simulates a DTN router with three nodes and four intermittent contacts; tracks bundle delivery and shows the total transfer time for a 10 MB payload.
5. Compares the time to transfer 1 TB over a 10 Gbps link, the BD product, and whether jumbo frames help.

Use `lfn_throughput()`, `wrap_time()`, `bundle_header()`, and `dtn_simulator()` to plug in your own parameters.

## Use It

| What you want to verify | How `main.py` shows it | Real-world evidence |
|---|---|---|
| Minimum window for an LFN | `lfn_throughput(...)` returns `min_window` | `ss -ti` shows `rcv_wscale` and `rcv_wnd` |
| Sequence-number wrap risk | `wrap_time(...)` shows whether PAWS is required | Wireshark shows `Timestamps` option |
| Bundle header layout | `bundle_header(...)` prints fields in order | `dtnperf` capture |
| DTN delivery time | `dtn_simulator(...)` prints arrival time | `dtnd` daemon log |
| Jumbo-frame efficiency | `frame_efficiency(mtu, mss)` | `ifconfig <iface> mtu 9000` |

## Ship It

Produce a reusable artifact under `outputs/`:

- A printable comparison sheet: TCP extensions for LFNs vs Bundle Protocol for DTNs.
- A reference Bundle Protocol primary-block encoder in your language.

Start from [`outputs/prompt-lfn-performance-and-the-bundle-protocol-for-delay-tolerant-networking.md`](../outputs/prompt-lfn-performance-and-the-bundle-protocol-for-delay-tolerant-networking.md).

## Exercises

1. Compute the BD product and minimum window for a 100 Gbps link with 100 ms RTT.
2. A link runs at 10 Gbps. After how many seconds does a 32-bit sequence number wrap? Is PAWS required?
3. Build a Bundle Protocol primary block for a bundle with Destination `dtn://server/bundle`, Source `dtn://client/bundle`, Lifetime 1 hour. Print it in hex.
4. Simulate three DTN nodes A-B-C with contacts: A-B at t=0 for 60 s, B-C at t=30 for 60 s. A 10 MB bundle is created at A at t=0. When does C receive it?
5. Earth-Mars RTT is 20 minutes. If TCP acks were used, how long would a 1 MB file take to transfer one-way, ignoring processing?
6. Why does Bundle Protocol define its own identifiers instead of using IP addresses?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| LFN | "long fat network" | Path where the BD product is huge (high bandwidth × long RTT) |
| BD product | "pipe size" | `bandwidth × RTT` — bytes in flight on a path |
| PAWS | "anti-wrap" | RFC 1323 — use timestamp option to reject stale segments after a wrap |
| Window Scale | "big window" | RFC 1323 — shifts the 16-bit Window field left by up to 14 bits |
| Jumbo frame | "9 KB Ethernet" | MTU up to 9,000 bytes — reduces per-segment overhead |
| DTN | "delay-tolerant" | RFC 4838 — architecture that tolerates intermittent connectivity |
| Bundle | "DTN message" | The unit of DTN transfer; carries primary + payload + optional blocks |
| Store-carry-forward | "postman model" | DTN nodes store bundles, may physically move with them, then forward |
| Custody transfer | "pass the responsibility" | DTN handover of retransmission responsibility to a node closer to the destination |
| Contact | "working link" | A period during which two DTN nodes have a working link |
| Convergence layer | "glue" | Adapts the Bundle Protocol to a specific transport (TCP, UDP, LTP, file) |

## Further Reading

- RFC 1072 — TCP Extensions for Long-Delay Paths (the original LFN extensions)
- RFC 1323 — TCP Extensions for High Performance (PAWS, Window Scale, Timestamps)
- RFC 2018 — TCP Selective Acknowledgement Options
- RFC 3517 — A Conservative SACK-based Loss Recovery Algorithm
- RFC 4838 — Delay-Tolerant Networking Architecture
- RFC 5050 — Bundle Protocol Specification (now updated by RFC 9171)
- RFC 9171 — Bundle Protocol Version 7
- RFC 9172 — Bundle Security Protocol Specification
- RFC 5326 — Licklider Transmission Protocol Specification (for deep-space links)
- Mogul, 1993 — *The Case for Persistent-Connection HTTP* (host design for fast networks)
- Fall, 2003 — *A Delay-Tolerant Network Architecture for Challenged Internets* (the DTN paper)
- Wood et al., 2008 — *Disruption-Tolerant Networking: Satellites and the Deep Space Network* (the Disaster Monitoring Constellation)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Chapter 6, performance issues and DTN
- Laoutaris et al., 2009 — *Delay-Tolerant Bulk Data Transfers on the Internet* (the Boston-Amsterdam-Perth case)