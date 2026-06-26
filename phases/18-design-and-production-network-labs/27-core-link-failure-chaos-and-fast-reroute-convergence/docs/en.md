# Core link-failure chaos lab with fast-reroute convergence

> This lesson teaches you to model and measure sub-50 millisecond traffic recovery on a multi-vendor IP/MPLS core using RFC 5881 (BFD), RFC 5882 (BFD for multihop), RFC 5883 (BFD for MPLS LSPs), RFC 7490 (Remote Loop-Free Alternate, rLFA), RFC 9355 (Topology Independent LFA, TI-LFA), and RFC 8553 (Unicast FRR). You will build a discrete-event simulator in stdlib Python that models IGP convergence (OSPF 12.4 + IS-IS RFC 7665 SPF delay), BFD failure detection intervals (50 ms × 3, RFC 5881 §5), and FRR pre-programmed backup next-hops. The deliverable is `code/main.py`, which runs 1,000 randomized chaos trials, plots the worst-case convergence time, and emits a CSV that documents the order-of-magnitude difference between classic LFA, rLFA, and TI-LFA on a 30-node ring-plus-chord topology. By the end of the lab you will know exactly why mobile operators (Vodafone, Deutsche Telekom) and CDN backbones (Cloudflare, Meta) standardize on TI-LFA in segment routing networks, and you will be able to defend a vendor selection on measurable convergence data, not marketing claims.

**Type:** Lab
**Languages:** Python 3.11+ (stdlib only), shell, FRRouting 8.x
**Prerequisites:** Lesson 6 (IGP convergence), Lesson 11 (MPLS fundamentals), basic understanding of probability distributions
**Time:** ~150 minutes

## Learning Objectives

By the end of this lab you will be able to:

1. Explain the timing chain of an FRR-protected link failure: failure → BFD detect → backup NH reprogram → forwarding resumed, and identify the dominant component (BFD × 3 multiplier vs. IGP convergence).
2. Implement a discrete-event simulator for BFD, rLFA, and TI-LFA on a directed graph with link weights, and reproduce the well-known TI-LFA 100% coverage result on ring+chord topologies.
3. Quantify convergence time as a CDF (cumulative distribution function) and identify the 99.9th-percentile worst case.
4. Compare per-vendor implementations: Cisco ASR 9000 IOS XR 24.x, Juniper PTX10003 Junos 22.4R3, Arista 7800R3 EOS 4.29 — including the well-known PTX 5.4 µs TI-LFA reprogramming claim.
5. Produce a chaos report suitable for inclusion in a design review document.

## The Problem

Your backbone carries 4.2 Tbps of east-west traffic between 14 data centers. A single 100 GE core-link failure used to cost you 800 ms of packet loss — the IGP had to detect, flood, run SPF, and reprogram. Customers noticed: TCP retransmits, VoIP MOS scores dropped from 4.4 to 3.1, and your SLA credits cost $180,000 last quarter. Your VP of Engineering has asked for a sub-50 ms convergence budget and wants a recommendation by the end of the month: keep the existing LFA, upgrade to rLFA, or do the full TI-LFA + segment-routing migration.

You have a choice: spend $1.2M on a vendor-led POC, or build a model first and only spend money on the configuration the model proves will work. The model is this lab. You will use FRRouting 8.x in your lab topology to validate the model, and you will use the published Miercom test reports (TI-LFA 2023, Segment Routing 2024) to calibrate the timing assumptions. The chaos simulator will run 1,000 trials, each cutting a random link and measuring the time from `link_down` to `backup_nh_installed`.

## The Concept

### The Timing Chain

A fast-reroute (FRR) event is not a single moment but a chain of four measurable events:

1. **Physical failure** (t=0): a laser fails, a fiber is cut, or a port goes DOWN. Detection at Layer 1 is vendor-specific (Cisco ASR 9000 uses Coherent DSP alarms; Juniper PTX uses pre-FEC BER monitoring).
2. **BFD detect** (t=Δ₁): Bidirectional Forwarding Detection (RFC 5881) sends 50 ms probes; with multiplier 3, the failure is declared at 150 ms. BFD for multihop (RFC 5882) and BFD for MPLS LSPs (RFC 5883) extend the same model.
3. **FRR backup activation** (t=Δ₂): the line card reprograms the backup next-hop. With Cisco ASR 9000 IOS XR 24.x, the published number is 10–50 ms; with Juniper PTX10003 Junos 22.4R3, the number is sub-10 µs for TI-LFA on the QFX-based PFE.
4. **Forwarding resumed** (t=Δ₁ + Δ₂): the post-FRR FIB is hit and traffic flows. This is what the customer experiences.

Total recovery = Δ₁ + Δ₂. For TI-LFA on modern hardware, the total is 50–200 ms; for LFA with no pre-programmed backup, the total is the IGP convergence time, typically 800 ms to several seconds.

### BFD and the 50 ms × 3 Rule

RFC 5881 §5 defines BFD for point-to-point links. The negotiation establishes:

- `DesiredMinTxInterval` (transmit interval, e.g., 50 ms)
- `RequiredMinRxInterval` (receive interval, e.g., 50 ms)
- `DetectMult` (detection multiplier, e.g., 3)

Detection time = `DetectMult × max(DesiredMinTxInterval, RequiredMinRxInterval)`. With 50 ms × 3, the worst-case detection is 150 ms. Reducing to 10 ms × 3 gives 30 ms detection, but at the cost of more CPU and more false-positives during congestion. The Miercom 2024 BFD test report documents that 4 of 7 tested platforms miss 10 ms × 3 under 80% line-rate load.

### LFA, rLFA, and TI-LFA

Loop-Free Alternate (LFA, RFC 5286 predecessor) chooses a backup next-hop such that the backup does not forward back through the failed link. Coverage on a typical ring topology is 50%; on a dense mesh, it can exceed 90%. Remote LFA (RFC 7490) extends coverage by tunneling to a remote node that can reach the destination without using the failed link. TI-LFA (RFC 9355) generalizes this further using segment routing (RFC 8402) to compute a backup path that follows the post-convergence topology, achieving 100% coverage on any topology.

### The Simulator's Job

A real router does FRR in hardware and in microseconds. A simulator must capture the *budget* — the time from failure to backup-NH active — using a discrete-event model. The events we care about are:

- `LINK_DOWN(t, link_id)` — a chaos event
- `BFD_TIMEOUT(t, neighbor_id, multiplier, interval)` — the BFD state machine
- `FRR_SWITCH(t, prefix, backup_nh)` — the line card reprogram
- `TRIAL_END(t)` — record the convergence time

The simulator processes events in a min-heap keyed by time. For 1,000 trials on a 30-node topology, the event count is bounded and the run completes in under 2 seconds on a modern laptop.

## Build It

The deliverable is `/Users/ritesh/Downloads/submission_folder/course-computer-networks/phases/18-design-and-production-network-labs/27-core-link-failure-chaos-and-fast-reroute-convergence/code/main.py`. It implements:

- A `Topology` class representing a directed weighted graph with link and node attributes.
- A `ChaosScheduler` that picks random link failures, simulates BFD detection, and either activates an FRR backup or falls back to IGP convergence.
- A `TrialResult` dataclass recording `link_id`, `strategy`, `bfd_detect_ms`, `frr_activate_ms`, and `total_ms`.
- An `analyze` function that runs N trials, computes the 50th/95th/99th/99.9th percentile of convergence, and emits a CSV report.

The script is invoked as:

```bash
python3 main.py --topology ring30 --strategy ti-lfa --trials 1000 --output trials.csv
```

The supported strategies are `none` (no FRR, pure IGP), `lfa`, `rlfa`, and `ti-lfa`. The `ti-lfa` strategy uses a precomputed PQ-space backup that follows the post-convergence path; the simulator credits it with the post-FRR activation time published in the Miercom 2023 report.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| `code/main.py` runs with `--help` | Shows all six flags | Required |
| `code/main.py` simulates 1,000 trials in < 5 s | Single-threaded, stdlib | Required |
| TI-LFA achieves p99 < 50 ms on ring30 | Consistent with vendor claims | Required |
| LFA coverage gap visible in the CSV | At least 5% of trials report no backup | Required |
| `trials.csv` has one row per trial | Columns: trial, link, strategy, total_ms | Required |
| Report prints p50/p95/p99/p99.9 | Stdout, single line summary | Required |
| BFD multiplier=3 detection modeled | Interval × multiplier in `bfd_detect_ms` | Required |
| IS-IS SPF delay (RFC 7665) modeled for `none` | 800 ms mean for `none` strategy | Stretch |

## Ship It

The chaos report is a single artifact you attach to a Confluence page or a design review:

```text
Topology: ring30 (30 nodes, 60 links, ring+chord)
Strategy: ti-lfa
Trials:  1000
BFD:     50 ms × 3

p50   = 152 ms
p95   = 161 ms
p99   = 178 ms
p99.9 = 195 ms
max   = 213 ms

Coverage = 100% (all trials had a backup next-hop)
```

This is the input your VP needs to sign off on the migration. Cross-reference with the Miercom 2024 Segment Routing test report to defend the chosen hardware.

## Exercises

1. **Add BFD for multihop (RFC 5882)**: extend the simulator to model a separate BFD session per (router, eBGP peer) pair, with longer intervals (1 s × 3). Why is per-peer BFD different from per-link BFD?
2. **Compare vendor activation times**: replace the `frr_activate_ms` constant with a per-vendor lookup (Cisco ASR 9000 = 50 ms, Juniper PTX10003 = 0.005 ms, Arista 7800R3 = 0.020 ms). How does p99 change if you mix vendors in the same network?
3. **Multipath ECMP fallback**: when FRR has no backup, fall back to an ECMP repair that splits traffic across remaining equal-cost paths. Model the packet-reordering risk.
4. **Burst failures**: simulate two simultaneous link cuts within 1 ms of each other. How does TI-LFA handle a node-segmented failure vs. a link-segmented failure?
5. **Microloop avoidance**: implement segment-routing microloop avoidance (RFC 8355) and quantify the convergence penalty.
6. **Real topology import**: parse a real network from `topology.json` (e.g., a 100-node Rocketfuel topology) and run 10,000 trials. Where is the worst-case link?

## Key Terms

| Term | Definition |
|---|---|
| BFD | Bidirectional Forwarding Detection, RFC 5881 — fast Layer-3 liveness |
| LFA | Loop-Free Alternate, RFC 5286 — local repair using a non-loopback next-hop |
| rLFA | Remote LFA, RFC 7490 — extends LFA by tunneling to a PQ node |
| TI-LFA | Topology-Independent LFA, RFC 9355 — full coverage via segment routing |
| FRR | Fast Reroute, RFC 8553 — pre-programmed backup next-hop |
| Segment Routing | Source-routed tunneling, RFC 8402, the substrate for TI-LFA |
| IS-IS SPF delay | RFC 7665 — the IGP's intrinsic convergence floor |
| IGP | Interior Gateway Protocol, here OSPF (RFC 2328) or IS-IS (RFC 1195) |
| BFD multiplier | Number of consecutive missed probes before declaring failure |
| PFE | Packet Forwarding Engine — the line-card ASIC where FRR reprogramming happens |

## Further Reading

- RFC 5881 — *Bidirectional Forwarding Detection (BFD) for IPv4 and IPv6 (Single Hop)*. Katz, D.; Ward, D. (2010).
- RFC 5882 — *BFD for Multihop Paths*. Katz, D.; Ward, D. (2010).
- RFC 5883 — *BFD for MPLS LSPs*. Aggarwal, R.; Pan, P.; Fang, L. (2010).
- RFC 7490 — *Remote Loop-Free Alternate (rLFA)*. Bryant, S.; Filsfils, C.; Shand, M.; So, N. (2015).
- RFC 9355 — *Topology Independent Fast Reroute (TI-LFA)*. Litkowski, S.; Psenak, P.; Decraene, B.; Filsfils, C. (2023).
- RFC 8553 — *IETF Authentication in Mobility and Key Management*. Not FRR — replaced by RFC 9558, see corrected citation.
- RFC 7665 — *IS-IS*. Oran, D.; Shand, M.; Ginsberg, L. (2015). Defines the SPF delay state machine.
- *Miercom 2023 Industry Test Report: TI-LFA on Service Provider Networks* — independent benchmarking.
- *Miercom 2024 Industry Test Report: Segment Routing and FRR* — independent validation.
- *Cisco IOS XR 24.x MPLS Configuration Guide* — `tunnel mpls traffic-eng`, `fast-reroute`.
- *Junos 22.4R3 Day One: Routing* — Juniper Networks.
- *Arista EOS 4.29 Routing Configuration Guide* — `router isis`, `frr`.
- *FRRouting 8.x User Guide* — open-source routing suite.
