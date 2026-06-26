# Differentiated Services to How Networks Differ

> Integrated Services (IntServ) tried to give every flow its own reservation along an entire path. It failed at scale: per-flow state in every router, end-to-end RSVP signaling for each call, brittle recovery when a router crashes. Differentiated Services (DiffServ) inverts the model — mark each packet once with a 6-bit DSCP code at the edge, then let every core router treat the packet by its **per-hop behavior (PHB)** class with no per-flow state at all. Three standardized PHBs cover most deployments: **EF (Expedited Forwarding, RFC 3246)** for low-loss/low-jitter voice, **AF (Assured Forwarding, RFC 2597)** for four priority classes × three drop precedences = 12 service classes, and **BE (Best Effort)** for everything else. Edge routers classify and police; core routers forward by behavior aggregate (BA). This buys the scalability IntServ could never reach — millions of flows collapse into a handful of classes — at the cost of statistical, not deterministic, guarantees. The same heterogeneity argument that makes DiffServ necessary (Ethernet, ATM, frame relay, satellite, WAN links all behave differently) is what makes internetworking a separate, harder problem: connecting networks that disagree on packet format, addressing, QoS semantics, and congestion signals.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01–07 (congestion control, traffic shaping, packet scheduling, Integrated Services)
**Time:** ~90 minutes

## Learning Objectives

- Decode the 8-bit IPv4/IPv6 DS field into its 6-bit DSCP and 2-bit ECN components, and name where the marking happens.
- Distinguish **EF**, **AFxy**, and **BE** per-hop behaviors by RFC, drop semantics, and scheduler treatment.
- Explain why DiffServ pushes classification and policing to the **edge** while the **core** only forwards by behavior aggregate.
- Compare IntServ vs DiffServ on state, signaling, scalability, and guarantee strength.
- Reason about network heterogeneity (ATM, frame relay, WAN) and why QoS classes are defined *per hop*, not *end to end*.

## The Problem

A backbone router carrying 400,000 concurrent flows cannot keep a reservation table for each one. IntServ/RSVP demands exactly that: every router on the path maintains per-flow soft state, refreshes it periodically, and admits or rejects new flows based on available bandwidth. The signalling load alone — RSVP PATH and RESV messages refreshed every ~30 seconds per flow — collapses the control plane long before the data plane is saturated. Router crashes wipe flow state with no clean recovery. And the QoS guarantee, even when it works, is only as strong as the weakest hop, so the entire path must speak RSVP.

Operators needed a QoS model that (a) requires **no per-flow state in the core**, (b) needs **no end-to-end signaling** for each new flow, and (c) lets them sell **coarse-grained service classes** — "voice gets priority, bulk traffic gets what's left" — without renegotiating contracts on every call. That model is DiffServ.

## The Concept

Source: `chapters/chapter-05-the-network-layer.md` §5.4.6 (Differentiated Services) and §5.5 (Internetworking — how networks differ).

### DiffServ architecture: edge vs core

DiffServ splits the network into two roles inside an **administrative domain** (an ISP, a telco, a campus):

- **Edge routers** (ingress/egress) classify incoming traffic, police it against a contract (token bucket, leaky bucket), and **mark** the DSCP field. This is the only place per-flow reasoning happens.
- **Core routers** never look at flows. They read the DSCP, map it to a PHB, and queue/schedule/drop accordingly. State is O(classes), not O(flows).

The marking is carried in the IP header itself, so it survives across hops. No RSVP, no per-flow refresh, no path-wide negotiation.

### The DSCP field: 6 bits inside the DS byte

The IPv4 header's old **Type of Service** byte (and IPv6's Traffic Class byte) was redefined by RFC 2474 as the **DS field**:

```
 bit 0   1   2   3   4   5   6   7
┌───────┴────┴────┴────┴────┴────┴────┴────┐
│      DSCP (6 bits)         │ ECN (2 bits) │
└────────────────────────────┴──────────────┘
```

- **DSCP** (Differentiated Services Code Point): 6 bits → 64 code points. Only ~14 are standardized; the rest are operator-defined or experimental.
- **ECN** (Explicit Congestion Notification): 2 bits for congestion marking, orthogonal to QoS class.

The 6-bit width is the whole scalability trick: 64 buckets collapse millions of flows into a handful of behavior aggregates.

### PHB classes: EF, AF, BE

| PHB | RFC | DSCP examples | Drop policy | Scheduler | Use case |
|-----|-----|---------------|-------------|-----------|----------|
| **EF** Expedited Forwarding | 3246 | `101110` (46) | Priority, near-zero drop | Strict priority queue, rate-capped | VoIP, real-time signaling |
| **AF** Assured Forwarding | 2597 | `AF11..AF43` (10,12,14…38) | WRED by drop precedence | WFQ across 4 classes | Premium data, gold/silver/bronze |
| **BE** Best Effort | (default) | `000000` (0) | Tail drop / WRED | Lowest weight | Default Internet traffic |

**EF** is the "two-tube" model: a small, rate-limited priority pipe that sees an effectively empty network. The ingress router polices EF strictly — exceed the contracted rate and the excess is dropped or re-marked, because a single oversubscribed EF stream poisons the whole class.

**AF** defines 4 priority classes × 3 drop precedences (low/medium/high). A token-bucket policer tags in-profile packets as low drop, small-burst exceeders as medium, large-burst exceeders as high. Inside the core, WRED (Weighted Random Early Detection) drops high-precedence packets first as the queue fills, preserving low-precedence bandwidth for well-behaved traffic. Weights double between classes so gold gets 2× silver, 4× bronze, 8× best-effort.

**BE** is the residual — whatever the scheduler leaves after EF and AF claims.

### Edge classification and policing

Classification at the edge can use a 5-tuple (src/dst IP, ports, protocol), application signaling (SIP for VoIP), or a trust boundary where the host marks its own packets and the ingress router **re-marks or polices** to enforce the contract. A typical VoIP edge rule:

```
match: UDP, dst port 5060/10000-20000  (SIP/RTP)
police: 200 kbps per flow, leaky bucket
mark:   DSCP = 46 (EF)
exceed: drop  (EF does not tolerate bursts)
```

Bulk backup traffic gets a different rule — match TCP 22 or 443 to a storage server, police to 50 Mbps, mark AF11, and on exceed re-mark down to BE rather than drop.

### Core forwarding: BA classification

Once marked, a packet is forwarded by **Behavior Aggregate** classification: the core router hashes only on the 6-bit DSCP, not on addresses or ports. This is what makes DiffServ O(1) per packet in the core. The scheduler is usually a combination of:

1. **Strict priority** for EF (dequeue EF first, up to the capped rate).
2. **Weighted Fair Queueing** across AF classes and BE for the remaining bandwidth.
3. **WRED** per AF drop-precedence for early drop as queues grow.

### IntServ vs DiffServ

| Dimension | IntServ (RSVP) | DiffServ (DSCP) |
|-----------|----------------|-----------------|
| State | Per-flow, every router | Per-class, edge only |
| Signaling | End-to-end PATH/RESV per flow | None; marking is in-band |
| Guarantee | Hard, deterministic per flow | Statistical, per class |
| Scalability | ~thousands of flows | millions of flows |
| Recovery | Lose flow state on crash | Stateless core; nothing to lose |
| Deployed | Almost nowhere | Every modern backbone |

The trade is guarantee strength for scale. DiffServ gives you "voice class gets low jitter, statistically" — not "this specific call gets 64 kbps guaranteed end to end."

### How networks differ: why per-hop, not per-path

DiffServ's per-hop framing exists because real internetworks are heterogeneous. Ethernet is broadcast, ATM is connection-oriented with cell switching, frame relay uses variable frames over virtual circuits, satellite links add 250 ms one-way delay, and WAN serial links serialize slowly. No single QoS primitive works identically across all of them. ATM has its own CBR/VBR/ABR/UBR service classes; frame relay has DE bit and BECN/FECN; MPLS carries a 3-bit EXP field that maps awkwardly onto 6-bit DSCP. The DiffServ answer is to define the **behavior at each hop** (low delay, weighted share, preferential drop) and let each underlying technology implement that behavior in its own way. The internetwork — the IP layer — stitches the heterogeneous hops together and trusts that the DSCP marking is respected (or at least not maliciously rewritten) across administrative boundaries.

## Build It

`code/main.py` implements a minimal DiffServ pipeline:

1. **`DSCPMarker`** — maps a 5-tuple flow to a DSCP codepoint per a policy table.
2. **`EdgeClassifier`** — applies a leaky-bucket policer per flow; in-profile packets keep their DSCP, exceeders are dropped (EF) or re-marked down (AF).
3. **`PHBScheduler`** — three queues (EF strict priority, AF weighted, BE residual) with WRED on AF drop precedences.
4. A small simulation feeds mixed voice, gold data, and bulk traffic through the pipeline and prints dequeue order and drop counts.

Run it:

```bash
python3 code/main.py
```

Inspect: which packets dequeue first? How many AF high-drop-precedence packets get dropped as the bulk load rises? What happens to EF when you push it past its policed rate?

## Use It

| Task | Evidence | What good looks like |
|------|----------|----------------------|
| Decode a DS field | `tcpdump -vv` or Wireshark `ip.dsfield` | You can read DSCP=46 and ECN=0b01 and name the PHB |
| Verify edge marking | Capture at ingress and egress of the edge router | DSCP is set on egress; exceeders are re-marked or dropped |
| Confirm core BA forwarding | `show queue` / interface counters per class | EF queue depth near zero; AF classes share by weight; BE starves first |
| Diagnose a QoS regression | Before/after DSCP histogram + delay per class | A re-marking bug shows as EF traffic appearing in the BE queue |

Wireshark display filter for EF traffic: `ip.dsfield.dscp == 46`. For AF41: `ip.dsfield.dscp == 34`.

## Ship It

Produce one artifact under `outputs/`:

- A **DSCP marking policy table** for a small enterprise (voice, video, signaling, transactional data, bulk, scavenger) with DSCP values, policing rules, and re-marking on exceed.
- A **DiffServ failure-mode runbook**: EF queue starvation, AF gold-class oversubscription, BE total starvation, DSCP rewrite by a non-DiffServ transit AS.
- The `code/main.py` simulation with your own traffic mix and an annotated output trace.

Start from [`outputs/prompt-differentiated-services-to-how-networks-differ.md`](../outputs/prompt-differentiated-services-to-how-networks-differ.md).

## Exercises

1. Decode `0xB8`, `0x28`, `0x00`, `0x94` as DS fields — name the DSCP, ECN bits, and likely PHB for each.
2. A customer contracts for 10 Mbps EF. They send 15 Mbps. What should the ingress router do, and what happens to the 5 Mbps excess in your simulator?
3. Add a fourth AF class (platinum, weight 16) to `code/main.py`. How does WFQ share change between platinum/gold/silver/bronze/BE?
4. Trace a packet crossing two DiffServ domains with different DSCP→PHB mappings. Where can it be re-marked, and who is responsible for the mapping?
5. Why is DiffServ's guarantee *per-hop* rather than *end-to-end*? Give a concrete heterogeneity example (ATM vs Ethernet) where a single QoS primitive cannot mean the same thing on both hops.

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| DSCP | "the QoS bits" | 6-bit code point in the DS field marking the packet's behavior aggregate |
| PHB | "a service class" | Per-Hop Behavior — the forwarding treatment a router applies to a DSCP, not a network-wide guarantee |
| EF | "the voice queue" | Expedited Forwarding, RFC 3246 — strict priority, rate-capped, near-zero drop |
| AF | "gold/silver/bronze" | Assured Forwarding, RFC 2597 — 4 classes × 3 drop precedences, WFQ + WRED |
| BE | "normal traffic" | Best Effort, DSCP 0 — whatever bandwidth the scheduler leaves |
| BA classification | "core doesn't care about flows" | Behavior Aggregate classification — core routers queue by DSCP only |
| Edge policing | "rate limiting at the border" | Token/leaky bucket enforcement of the customer contract before marking |
| IntServ | "RSVP per-flow" | Integrated Services — per-flow reservations, failed at backbone scale |
| Administrative domain | "an ISP" | The set of routers under one operator's DiffServ policy and DSCP mapping |

## Further Reading

- RFC 2474 — Definition of the Differentiated Services Field (DS Field)
- RFC 2475 — An Architecture for Differentiated Services
- RFC 3246 — An Expedited Forwarding PHB
- RFC 2597 — An Assured Forwarding PHB Group
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5 §5.4.6 and §5.5
- Wireshark display filter reference: `ip.dsfield.dscp`, `ip.dsfield.ecn`