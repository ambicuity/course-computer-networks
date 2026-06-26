# Load Shedding to Application Requirements

> When a router is drowning in packets it must drop some, and *which* packets it drops should depend on what the application can tolerate. A file transfer would rather lose a new packet than an old one (the receiver cannot use bytes 7–10 until byte 6 arrives); a live voice call would rather lose an old packet than a new one (a delayed sample is useless once the playout time has passed). Load shedding is the deliberate discard under overload; drop precedence encodes "how important is this packet" in the DSCP field; and the application requirement classes (real-time, streaming, elastic) translate the four-parameter QoS tuple — bandwidth, delay, jitter, loss — into the forwarding and drop policy each flow deserves. IntServ reserved per-flow resources and did not scale; DiffServ marks packets into a small set of per-hop behaviors (expedited forwarding, assured forwarding with 4 priority × 3 drop = 12 classes) and lets each router act locally. The lesson builds a simulator that mixes the three application classes, drives a router past overload, and compares random, priority, and RED shedding policies against the QoS contract each class needs.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01–03 (congestion approaches, admission control, traffic throttling)
**Time:** ~90 minutes

## Learning Objectives

- Decide whether an overloaded router should keep old packets or new packets, and tie that decision to the wine-vs-milk distinction and to application tolerance.
- Read the four-parameter QoS tuple (bandwidth, delay, jitter, loss) for a flow and classify the flow as real-time, streaming, or elastic.
- Explain how DSCP drop precedence (low / medium / high) lets a router shed load in tiers instead of all at once, and why Assured Forwarding defines 12 service classes (4 priority × 3 drop).
- Distinguish IntServ (per-flow reservation, RSVP, does not scale) from DiffServ (per-hop behavior, class-based, scales locally) and say when each is the right tool.
- Run a load-shedding simulator that mixes the three application classes, drives a router past capacity, and measures which policy (random, priority, RED) keeps each class inside its QoS contract.
- Produce a reusable artifact (runbook, trace annotation, or simulator config) that encodes a drop policy for a realistic failure mode.

## The Problem

A router has a finite output queue. When offered load on a link exceeds the link rate for long enough, the queue fills and packets must be discarded. The naive answer — tail drop — has two defects. First, it treats every packet as equally valuable, which is wrong: a routing update that keeps the network connected is not equally valuable to a bulk file transfer, and a stale voice sample that has already missed its playout deadline is not equally valuable to a fresh one. Second, tail drop signals congestion only after the queue is completely full, leaving the transport layer no time to slow down before the router is already dropping a burst.

The real question is not *whether* to shed load but *which* packets to shed, and that has no single answer. It depends on what the application can tolerate. A file transfer tolerates delay but not loss (retransmission is expensive and the receiver is blocked on the missing byte). A live telephone call tolerates occasional loss but not delay or jitter (a sample that arrives after its playout time is worthless). A video-on-demand stream tolerates jitter (the receiver buffers) but not sustained loss. The network layer must translate "what the application can tolerate" into "which packet to drop first," at line rate, without per-flow state exploding.

## The Concept

### Load shedding: random, priority, and RED

The textbook taxonomy names three shedding policies. **Random drop** (tail drop) discards the arriving packet whenever the queue is full; it is the simplest and worst policy — every flow gets the same loss rate regardless of need, and the transport layer gets no early warning. **Priority drop** classifies packets and discards from the least important class first; the classification can be by application (routing updates before data), by frame dependency (drop MPEG difference frames before I-frames), or by sender marking (excess packets marked low priority are dropped first). **Random Early Detection (RED)** is the proactive variant: the router keeps a running average of queue length and starts dropping a small random fraction of arrivals *before* the buffer is exhausted. Dropping early gives TCP time to react to the implicit loss signal (a missing ACK) and back off, instead of waiting until the queue is full and a whole burst must be dropped at once. RED picks victims at random so the fastest senders are statistically most likely to see a drop — exactly what you want in a datagram network where the router cannot tell which source is causing the congestion.

### Wine vs milk: old packets vs new packets

The application decides whether an old packet or a new packet is more valuable. For a file transfer, an old packet is worth more: dropping packet 6 and keeping 7–10 only forces the receiver to buffer data it cannot yet use. For real-time media, a new packet is worth more: a sample that has already missed its playout deadline is useless. The mnemonic is **wine** (old is better — keep the old packet, drop the new) for file transfer and **milk** (new is better — drop the old packet, keep the fresh one) for real-time media. A router that does not know the application cannot choose wisely; a router that *does* know, via DSCP marking or flow classification, can shed exactly the packets the application can best afford to lose.

### Drop precedence and DSCP

The Differentiated Services field (6 bits in the IPv4 ToS octet / IPv6 Traffic Class octet) carries a **DSCP** codepoint that tells each router the per-hop behavior the packet should receive. For Assured Forwarding (RFC 2597) the codepoint encodes two things at once: a **priority class** (gold / silver / bronze / a fourth class) and a **drop precedence** (low / medium / high). When congestion builds, the router runs RED within each priority class and preferentially drops the high-drop-precedence packets first, then medium, then low — so a flow that has already exceeded its token-bucket contract (and whose excess packets were marked high-drop by the policer) is shed before a flow that is still within contract. The twelve AF codepoints (four classes × three drop levels) plus the expedited forwarding codepoint give operators a small, stable vocabulary for "how important is this packet" that every router in the administrative domain can honor locally, without consulting a per-flow database.

### Application requirement classes: real-time, streaming, elastic

The source table (Fig. 5-27) lists eight applications with the stringency of their bandwidth, delay, jitter, and loss needs. Collapsing that table into operational classes gives three buckets that a drop policy can actually act on:

| Class | Examples | Bandwidth | Delay | Jitter | Loss | Shed policy |
|-------|----------|-----------|-------|--------|------|-------------|
| **Real-time** | Telephony, videoconferencing | Low–High | High (strict) | High (strict) | Low (tolerant) | Drop oldest first (milk); preferential queue |
| **Streaming** | Audio on demand, video on demand | Low–High | Low | High | Low | Drop newest excess; buffer absorbs jitter |
| **Elastic** | Email, file transfer, Web, remote login | Low–High | Low–Medium | Low–Medium | Medium (retransmit) | Drop newest first (wine); TCP backs off |

The three classes are the bridge between "what the application tolerates" and "what the router does at line rate." A real-time flow is delay-and-jitter sensitive but loss tolerant, so the router protects it with a priority queue and, when it must shed, drops the oldest samples. An elastic flow is loss sensitive but delay tolerant, so the router drops the newest packets first (wine) and lets TCP retransmit. A streaming flow sits in between: the receiver's buffer absorbs jitter, so the router can drop excess (out-of-contract) packets before in-contract ones.

### The QoS 4-tuple: bandwidth, delay, jitter, loss

Every flow can be characterized by four primary parameters:

- **Bandwidth** — bits per second the flow needs. Email and telephony need little; file sharing and video need a great deal.
- **Delay** — elapsed time source to destination. File transfer does not care; interactive applications care somewhat; real-time applications have strict bounds.
- **Jitter** — standard deviation of delay. The first four applications tolerate it; audio and video are extremely sensitive (a few milliseconds is audible).
- **Loss** — fraction of packets not delivered. The first four applications are stringent (every bit must arrive, via retransmission); audio and video tolerate some loss.

Applications can compensate for some of these but not all. Retransmission repairs loss; receiver buffering absorbs jitter; but nothing the application does can remedy too little bandwidth or too much delay. That asymmetry is why the network layer must promise bandwidth and delay, while the application layer can repair loss and jitter on its own.

### IntServ vs DiffServ: per-flow vs per-class

**Integrated Services (IntServ)** reserves resources per flow via RSVP: each router on the path admits or rejects the flow against residual capacity, then maintains per-flow state and queues to guarantee the contract. IntServ gives excellent QoS to a small number of flows but does not scale — thousands of flows mean thousands of per-flow state entries in every router, and a router crash drops every flow it tracked. Few deployments exist for this reason.

**Differentiated Services (DiffServ)** trades per-flow guarantees for scalability. A small set of service classes (expedited forwarding, assured forwarding with 12 subclasses) is defined for an administrative domain. Packets are marked with a DSCP at the edge, and every interior router applies the per-hop behavior locally — no per-flow state, no end-to-end setup. DiffServ cannot promise a flow anything end-to-end (the behavior is per-hop), but it scales to the entire Internet because each router needs only a small forwarding table keyed on the 6-bit DSCP.

The practical pattern: DiffServ for the backbone, IntServ-like admission at the edges where the number of flows is small enough to manage.

### Mapping applications to classes

The simulator in this lesson takes a flow specification (application, bandwidth need, delay bound, jitter bound, loss tolerance) and maps it to a DiffServ class plus a drop policy:

- Telephony → Expedited Forwarding (EF), priority queue, drop-oldest-first (milk).
- Videoconferencing → Assured Forwarding gold, weighted-fair queue, drop-oldest-first within the class.
- Video on demand → Assured Forwarding silver, weighted-fair queue, drop-excess (out-of-contract) first.
- File transfer / email / Web → Assured Forwarding bronze or best effort, drop-newest-first (wine) and let TCP retransmit.

That mapping is the engineering decision the lesson asks you to make: given an application's QoS 4-tuple, choose a DSCP, a queue, and a drop policy that keeps the flow inside its contract when the router is overloaded.

```text
offered load > link rate
        |
        v
queue fills -> shed load
        |
        v
which packets?  -->  application class  -->  QoS 4-tuple
        |                 (real-time /              (bw, delay,
        |                  streaming /               jitter, loss)
        |                  elastic)
        v
drop policy:  milk (oldest first)  |  wine (newest first)  |  RED within drop precedence
        |
        v
DSCP mark: EF / AF class + drop precedence  ->  per-hop behavior at each router
```

## Build It

1. Write the one-paragraph mechanism summary in your own words: what load shedding does, why *which* packet matters, and how DSCP carries the answer.
2. Draw the queue + classifier + policer + scheduler for one overloaded output link, showing where each drop policy (wine, milk, RED-with-drop-precedence) would act.
3. Identify the observable evidence that a router is shedding load: interface drop counter, per-class drop counter, queue-depth average, RED drop count, DSCP markings on captured packets.
4. Pick one failure mode (a real-time flow getting tail-dropped because no priority queue exists, or an elastic flow losing the oldest packet and stalling TCP) and state the smallest test that would confirm it.
5. Run `code/main.py` — it mixes the three application classes, drives a router past capacity, and prints per-class loss, delay, and jitter for random / priority / RED policies. Replace the sample traffic mix with your own and re-run.

## Use It

| Task | Evidence | What Good Looks Like |
|------|---------|-----------------------|
| Locate the layer | Interface drop counters, per-class queue counters, DSCP in packet captures | You can explain why the symptom is a network-layer shedding decision, not an application-layer timeout |
| Explain normal behavior | Source rules plus a clean capture with DSCP markings and zero drops | Observed per-class drop counters match the configured drop policy |
| Diagnose abnormal behavior | Before/after captures, per-class drop counts, queue-depth trend | The failure hypothesis ("telephony is being tail-dropped with the elastic traffic") predicts the evidence |
| Choose a drop policy | Per-class QoS contract vs measured loss/delay/jitter | Each class stays inside its 4-tuple; the real-time class sees lowest delay, the elastic class sees lowest loss |

## Ship It

Create one artifact under `outputs/`:

- A drop-policy runbook that maps each application class to (DSCP, queue, drop policy) and lists the evidence to collect when a class is violating its QoS contract.
- A trace annotation checklist for DSCP markings, per-class drop counters, and RED early-drop counts.
- A simulator configuration (traffic mix, link rate, queue depth, RED thresholds) that reproduces a realistic overload and the per-class outcomes.
- A one-page failure-mode runbook for "real-time flow is being tail-dropped alongside elastic traffic."

Start with `outputs/prompt-load-shedding-to-application-requirements.md`.

## Exercises

1. List the source rules that matter most for load shedding (wine vs milk, RED, drop precedence) and state each one in operational terms.
2. Capture or sketch a trace with at least three DSCPs visible; annotate which application class each codepoint belongs to.
3. Describe one realistic failure (real-time flow tail-dropped with elastic traffic) and the first three pieces of evidence you would collect.
4. Run `code/main.py` with the default mix, then double the real-time fraction. Which policy keeps the real-time class inside its delay bound? Which keeps the elastic class inside its loss bound?
5. Compare this mechanism (load shedding at the network layer) with TCP congestion control at the transport layer: who signals, who reacts, and what is the evidence at each layer?
6. Argue for or against: "DiffServ has won and IntServ is dead." Use one concrete deployment scenario where IntServ is still the right tool.

## Key Terms

| Term | What people say | What it actually means |
|------|------------------|------------------------|
| Load shedding | "dropping packets when full" | Deliberate discard under overload, with a policy that picks *which* packets based on what the application can tolerate |
| Wine vs milk | "old vs new" | Wine = keep old packets (file transfer); milk = keep new packets (real-time media) |
| Drop precedence | "how droppable" | A 2-bit field in the DSCP (low / medium / high) that tells the router which packets to shed first within an AF class |
| DSCP | "the QoS bits" | 6-bit Differentiated Services codepoint encoding per-hop behavior (EF, AF class + drop, best effort) |
| RED | "early drop" | Random Early Detection — drop a small random fraction before the queue is full so TCP backs off before a burst is lost |
| IntServ | "the per-flow one" | Integrated Services — RSVP reserves resources per flow; excellent QoS, does not scale |
| DiffServ | "the class one" | Differentiated Services — mark packets with a DSCP; each router applies a local per-hop behavior; scales |
| QoS 4-tuple | "what the app needs" | Bandwidth, delay, jitter, loss — the four parameters that characterize a flow's requirement |
| Real-time class | "voice/video live" | Delay-and-jitter strict, loss tolerant — protect with priority queue, shed oldest first |
| Elastic class | "file transfer / Web" | Loss sensitive, delay tolerant — drop newest first (wine), let TCP retransmit |

## Further Reading

- RFC 2475 — An Architecture for Differentiated Services
- RFC 2597 — Assured Forwarding PHB Group (the 4 × 3 = 12 AF classes)
- RFC 3246 — Expedited Forwarding PHB
- Floyd & Jacobson, "Random Early Detection gateways for Congestion Avoidance" (1993)
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5 §5.3.5 (Load Shedding) and §5.4.1 (Application Requirements)