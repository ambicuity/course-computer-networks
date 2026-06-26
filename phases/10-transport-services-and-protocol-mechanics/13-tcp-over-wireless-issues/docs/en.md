# TCP Congestion Control over Wireless Links

> TCP was built on the assumption that packet loss equals congestion. On a wireless link that assumption breaks: a bit-error rate of 10^-4 (vs. 10^-9 on fiber) plus cellular handoffs produce losses that have nothing to do with a router running out of buffer. The sender cannot tell the two apart, so every wireless drop shrinks the congestion window (cwnd) and burns throughput. The classic mid-1990s response was to hide the wireless hop from the sender: I-TCP (Bakne and Badrinath, 1995) splits the connection at the base station, Snooping TCP (Balakrishnan et al., 1995) caches and locally retransmits at the base station, and Explicit Loss Notification (ELN) tells the sender the loss was not congestion. Modern stacks layer the defenses: link-layer ARQ (802.11 retransmits inside microseconds), ECN on wired paths, edge PEPs (Performance Enhancing Proxies) splitting long-RTT satellite links, and rate-based transports such as BBR and QUIC that are robust to random non-congestion loss.

**Type:** Learn
**Languages:** Python
**Prerequisites:** AIMD congestion control, the cwnd / ssthresh state machine, the triple-duplicate-ACK and timeout paths of TCP-NewReno, basic wireless link properties (BER, handoff, stop-and-wait ARQ)
**Time:** ~80 minutes

## Learning Objectives

- Explain why TCP's "loss equals congestion" assumption breaks over wireless links and quantify the throughput loss using the Padhye et al. inverse-square-root model.
- Distinguish BER-driven frame errors, handoff-driven reordering and blackouts, and genuine congestion loss, and describe how each corrupts the cwnd state machine.
- Compare the classic mid-1990s fixes (I-TCP, Snooping TCP, M-TCP, WTCP) by where the connection is split, what semantics are preserved, and what semantics are broken.
- Describe how Explicit Loss Notification (ELN) and Explicit Bad-State Notification decouple the loss signal from the congestion signal.
- Trace the modern layered defense: 802.11 MAC retransmits, ECN, edge PEPs, L4S, and rate-based transports (BBR, QUIC).
- Implement a discrete-event simulation that drives a TCP-NewReno sender over wired and wireless paths, measures the throughput collapse, then adds a snooping agent and re-measures.

## The Problem — TCP throughput over a noisy 802.11 link collapses because loss isn't congestion

TCP's congestion control (RFC 5681) has one equation behind every variant: if a packet is lost, the path is congested, so halve `cwnd`. Right for a router-queue bottleneck on fiber. Wrong for a microwave link on an 802.11 cell. The Padhye et al. (1998) throughput formula makes the sensitivity explicit:

```
B(p) ≈ (MSS / RTT) * (1 / sqrt(2p / 3))
```

where `p` is the loss event rate. Three numbers show the gap:

| Environment       | p         | Steady-state throughput (MSS=1460, RTT=50ms) |
|-------------------|-----------|----------------------------------------------|
| Fiber backbone    | 0.000001  | ~1.21 Gbps                                   |
| Loaded 802.11     | 0.05      | ~5.6 Mbps                                    |
| Satellite + storm | 0.20      | ~0.4 Mbps                                    |

A 1% loss rate, which TCP considers "moderate", is exactly the rate at which a busy Wi-Fi cell discards frames. At 10% loss the connection has effectively stopped working.

## The Concept

### Why TCP breaks on wireless

TCP's congestion controller is a Bayesian decision maker with a hard-coded prior: P(loss = congestion | loss) = 1. That prior was calibrated for the 1980s ARPANET, where wired links dropped a packet only when a buffer overflowed. Every modern wireless technology violates that prior: thermal noise and fading corrupt bits independently of buffer occupancy; co-channel interference drops the SINR below the decoding threshold; cellular and Mobile IPv6 handoffs briefly reroute packets and can briefly black out the radio; multipath and shadowing reorder bursts of packets that crossed a path change. Each event looks identical to a router-queue drop, so the sender backs off — and when the underlying event is not congestion, the back-off is pure throughput loss.

### The BER gap and handoff disruption

A wired sender sees about one bit error in 10^9 bits, or one dropped packet per ~85,000 segments. A marginal 802.11 sender sees a bit error every 10^4 bits, or about one corrupted segment per 9 segments. Drop `p` from 10^-6 to 10^-2 and Padhye's formula delivers a ~100x throughput drop — exactly what a user feels as "Wi-Fi is slow today". BER values: fiber 10^-12 to 10^-9; copper 10^-10; indoor 802.11n 10^-7 (good SNR) to 10^-4 (marginal); outdoor microwave 10^-4 to 10^-3; cellular edge-of-cell 10^-3 to 10^-2.

A cellular handoff is a 50-300 ms event during which the mobile node may not receive anything. The effect on TCP is twofold: (1) a burst of losses arrives at the sender when the routing settles, and (2) the remaining packets are reordered. Reordering triggers spurious fast retransmits: the sender sees a hole, retransmits, then receives the original segment that was merely delayed. The spurious retransmit counts as a duplicate ACK and can knock `cwnd` down by half — even though no segment was ever lost. Mobile IPv6 adds a third wrinkle: while the binding update is in flight, the home agent tunnels packets to the mobile node, inflating the RTT and exposing the path to a burst of reordering when the binding finishes.

### Split-connection approaches (I-TCP, M-TCP, WTCP)

The most aggressive class of fix is to break TCP at the base station. The base station then runs two separate TCPs: one for the wired side (loss = congestion) and one for the wireless side (loss = radio error, locally retransmit).

Indirect TCP (I-TCP), Bakne and Badrinath (1995): the base station terminates the wired TCP and immediately starts a fresh wireless TCP to the mobile node. ACKs flow back to the fixed sender as soon as the base station has buffered the segment. The fixed sender never sees a wireless loss, so its `cwnd` keeps climbing. The price is a complete break of TCP's end-to-end semantics: ACKs no longer mean the data reached the receiver, and a base station crash loses any data it has acknowledged.

Mobile TCP (M-TCP), Brown and Singh (1996): when the wireless side detects a blackout (handoff, deep fade), the base station sends a Choke packet to the fixed sender that *freezes* the sender's `cwnd` instead of shrinking it. When the wireless side recovers, the sender is unfrozen at its previous window.

Wireless TCP (WTCP), Ratnam and Matta (1998): the base station measures the actual wireless delay and reports a rate to the fixed sender. The sender becomes rate-based rather than window-based, so it stops inferring capacity from loss.

### Snooping TCP and ELN

I-TCP preserves the sender's blind spot at the cost of end-to-end semantics. Snooping TCP preserves the semantics at the cost of state at the base station. The base station intercepts every segment in both directions and maintains a per-connection cache of unacknowledged segments. When it sees a duplicate ACK from the mobile node (the first sign of loss), it locally retransmits the cached segment over the wireless hop before forwarding the duplicate ACK back to the fixed sender. The fixed sender sees either no loss at all (the local retransmit beat the timeout) or only the loss that the snooper could not recover (which is, by definition, congestion). ACKs still come from the real receiver.

Explicit Loss Notification (ELN) is a small but crucial refinement: when the snooper locally recovers a segment, it sets a bit in the next ACK it forwards to the fixed sender. The sender then knows the loss was a recovered wireless loss, not congestion, and does **not** halve `cwnd`. Snoop + ELN is the most aggressive end-to-end-preserving design in the 1990s literature. Explicit Bad-State Notification (EBSN) is the same idea in the opposite direction.

### Timescales and modern defenses

A puzzle from the 1990s: if link-layer retransmissions and TCP retransmissions both fire on loss, how can they coexist without doubling the back-off? The answer is timescales. 802.11 stop-and-wait retransmits happen on the order of microseconds to milliseconds; TCP retransmission timers fire on the order of hundreds of milliseconds to seconds. The three-order-of-magnitude gap means the link layer fully repairs a transient frame error long before the transport layer's timer ever expires. The transport therefore sees no loss at all in the common case. When the radio fails for hundreds of milliseconds (handoff, deep fade), the link-layer ARQ gives up and the transport sees the loss — that is the boundary case where the snooping agent earns its keep.

The mid-1990s fixes were developed when the only congestion signal was loss. Modern stacks layer four defenses:

1. Link-layer ARQ. Every modern wireless MAC (802.11n, 802.11ac, 802.11ax, LTE MAC, 5G NR) retransmits at L2 with aggressive timing. The radio itself absorbs the BER, and the transport sees a much cleaner channel than the raw air interface would suggest.
2. ECN (Explicit Congestion Notification, RFC 3168). Routers mark packets instead of dropping them. The receiver echoes the CE mark back to the sender via the ACK, and the sender reacts to the mark without needing a loss event. A wireless link does not mark congestion, so a wireless loss is unambiguously not congestion.
3. Performance Enhancing Proxies (PEPs). Satellites and other long-RTT links still need split-connection tricks, but they are now application-layer or middlebox proxies at the network edge. A PEP may terminate TCP, run a local reliability protocol over the satellite, and present a clean short-RTT TCP to the application.
4. Rate-based transport (BBR, QUIC). BBR (Cardwell et al., 2017) and QUIC both estimate the bottleneck bandwidth and round-trip time explicitly, then pace at the estimated rate. They do not use loss as the primary congestion signal, so random non-congestion loss has only a small effect on throughput.

L4S (Low Latency, Low Loss, Scalable) builds on ECN with a fine-grained, two-bit marking scheme and a scalable congestion controller (TCP Prague). Combined with 5G and Wi-Fi 6E, L4S is the closest the industry has come to a transport that is genuinely wireless-aware without splitting the connection. A modern TCP segment on a wireless device passes through this stack: App -> TCP (AIMD) -> IP -> Wi-Fi MAC (ARQ) -> wired path with ECN -> Base station / PEP (Snoop, ELN) -> Receiver. If everything works, the sender sees a clean, near-zero-loss path even when the radio is at the edge of its cell. If something fails — handoff, queue overflow — only the layer that actually failed acts, because each layer's loss is visible only to the layer above it.

## Build It

The simulation in `code/main.py` models a single TCP-NewReno sender pushing a 5 MB file over either a wired path (loss probability 0.0001) or a wireless path (loss probability 0.05). The sender implements AIMD: cwnd grows by one MSS per RTT in congestion avoidance, halves on triple-duplicate-ACK, and resets to 1 on a retransmission timeout. We compare throughput under the two paths, then add a snooping agent at the wireless edge and re-measure.

Run `python3 code/main.py`. Expected output (numbers vary slightly by seed):

```
wired (p=0.0001)     : throughput =  38.14 Mbps  cwnd halvings =   0  timeouts = 0
wireless (p=0.0500)  : throughput =   3.78 Mbps  cwnd halvings =   0  timeouts = 2
wireless + snoop     : throughput =  38.14 Mbps  cwnd halvings =   0  timeouts = 0
```

The cwnd vs time picture (see `assets/tcp-over-wireless-issues.svg`) shows the difference visually: wired is a clean sawtooth, wireless is a jagged comb that barely climbs above 1-2 MSS, snooped wireless returns to the wired sawtooth.

## Use It

| Scenario                                       | What to expect (single TCP flow, MSS=1460, RTT=50ms) |
|------------------------------------------------|--------------------------------------------------------|
| Long fat fiber, p=10^-6                        | cwnd reaches the receiver window in ~0.4 s             |
| Lossy 802.11 cell edge, p=0.05, raw            | cwnd halts around 1-4 MSS, throughput drops ~10x       |
| Same cell with 802.11ac MAC retransmits        | effective p drops to 10^-3, throughput ~25 Mbps        |
| Same cell + snoop + ELN                        | sender's view of p approx 0, throughput approx wired   |
| 5G NSA + ECN + BBR on the server               | loss insensitive, throughput tracks BDP                |
| GEO satellite, 600 ms RTT, no PEP              | one loss every 30 s halves cwnd for a full RTT         |
| GEO satellite + edge PEP                       | sender sees a 50 ms RTT, behaves like a clean fiber    |

## Ship It

A production-grade fix for TCP-over-wireless is a layered deployment: (1) keep link-layer ARQ on (Wi-Fi default; LTE/5G in RLC); (2) enable ECN on wired paths (`net.ipv4.tcp_ecn=2` on Linux); (3) add edge PEPs only for genuinely long-RTT links (GEO satellite, intercontinental backhaul); (4) prefer rate-based transports (BBR, QUIC) for wireless-heavy clients; (5) if you must run CUBIC/NewReno over a raw wireless path, add a Snooping TCP agent at the base station or access point that maintains a per-connection cache, locally retransmits on duplicate ACK, and sets ELN in the ACK it forwards; (6) monitor cwnd as an SLI — a wireless client's cwnd time-series is the single best signal that the radio is unhealthy. The vocabulary that survives from the 1995 papers: "loss is not congestion; mask the wireless losses; preserve end-to-end semantics; if you must split the connection, do it at the edge, not in the application."

## Exercises

1. Throughput under BER. Use the Padhye formula to compute steady-state throughput for `p in {10^-6, 10^-5, 10^-4, 10^-3, 10^-2, 10^-1}` with MSS=1460 and RTT=50 ms. Plot throughput (log y) vs loss rate (log x). Where does the curve cross 100 Mbps? Where does it cross 1 Mbps? Compare with the simulated values from `code/main.py`.
2. Simulate I-TCP. Extend `code/main.py` with a split-connection model: the base station terminates the wired TCP after `k` segments are buffered and starts a fresh wireless TCP. Measure throughput improvement and buffer occupancy. Identify the failure mode where the base station crashes with unACKed data.
3. Snooping agent with ELN. Modify `code/main.py` so the snooping agent sets an "ELN" flag when it locally recovers a segment. The sender treats ELN-flagged losses as no-ops (no cwnd halving). Compare throughput with plain snoop, snoop + ELN, and raw wireless.
4. Reordering-induced spurious retransmits. Simulate a cellular handoff: between t=0.5 s and t=0.8 s, delay every third ACK by 100 ms. Plot cwnd and the duplicate-ACK counter. How many spurious retransmits does the sender issue? How does the picture change if the sender is running BBR-style rate-based pacing instead of loss-based AIMD?
5. ECN vs loss on a shared bottleneck. Add a second TCP flow that shares the same bottleneck queue. With ECN enabled (queue marks when full), both flows converge to the bottleneck bandwidth. Without ECN (queue drops when full), both flows oscillate with sawtooth halvings. Measure Jain's fairness index in each case.
6. M-TCP choke packets. Implement M-TCP's choke mechanism in `code/main.py`. When the wireless link simulates a 300 ms blackout, send a choke packet that freezes cwnd (no halving). When the link recovers, send an unfreeze packet. Compare with M-TCP off (halving) and M-TCP + ELN (no reaction at all).

## Key Terms

| Term                          | What it means                                                                          |
|-------------------------------|----------------------------------------------------------------------------------------|
| BER                           | Probability a single bit is corrupted. Wireless: 10^-4, fiber: 10^-9.                   |
| AIMD                          | The cwnd control law: grow by 1 MSS per RTT, halve on loss.                             |
| cwnd                          | The sender's view of the network's current capacity, in MSS units.                      |
| Triple-duplicate ACK          | Sender's signal that one segment was lost but more are flowing. Halves cwnd.             |
| Fast retransmit               | The TCP rule fired on the third duplicate ACK.                                          |
| Handoff (cellular)            | A 50-300 ms event during which the radio can drop packets and reorder those in flight.  |
| I-TCP                        | Bakne and Badrinath (1995). Two TCPs, one wired, one wireless.                          |
| Snooping TCP                  | Balakrishnan et al. (1995). Base station caches unACKed segments, retransmits locally.  |
| ELN                          | Explicit Loss Notification bit in the ACK. Sender does not halve cwnd.                   |
| M-TCP                        | Brown and Singh (1996). Choke packets hold cwnd steady during a wireless blackout.       |
| WTCP                         | Ratnam and Matta (1998). Base station reports a target rate; sender paces at that rate.  |
| PEP                          | Performance Enhancing Proxy. Standard for GEO satellite backhaul.                        |
| ECN                          | RFC 3168. Routers mark congestion; receiver echoes the CE flag.                         |
| BBR                          | Cardwell et al. (2017). Rate-based transport, robust to random non-congestion loss.      |
| QUIC                         | IETF RFC 9000. Built-in TLS 1.3, congestion control pluggable, BBR is its default.       |
| L4S                          | RFC 9332. Designed for wireless-aware networks.                                          |
| Spurious retransmit           | Caused by reordering; counts as a duplicate ACK and can halve cwnd for nothing.          |

## Further Reading

- RFC 5681 - Allman, Paxson, Blanton, "TCP Congestion Control" (AIMD, slow start, fast retransmit).
- RFC 3168 - Ramakrishnan, Floyd, Black, "ECN to IP".
- RFC 9332 - L4S Internet Service Architecture.
- RFC 9000 - QUIC transport.
- Bakne and Badrinath (1995), "I-TCP: Indirect TCP for Mobile Hosts", ICDCS '95.
- Balakrishnan et al. (1995), "Improving TCP/IP Performance over Wireless Networks", MobiCom '95.
- Brown and Singh (1996), "M-TCP: TCP for Mobile Cellular Networks", ACM SIGCOMM CCR 27(5).
- Ratnam and Matta (1998), "WTCP: An Efficient Mechanism for Improving TCP Performance over Wireless Links", ISCC '98.
- Cardwell et al. (2017), "BBR: Congestion-Based Congestion Control", ACM Queue 14(5).
- Padhye et al. (1998), "Modeling TCP Throughput", ACM SIGCOMM '98.