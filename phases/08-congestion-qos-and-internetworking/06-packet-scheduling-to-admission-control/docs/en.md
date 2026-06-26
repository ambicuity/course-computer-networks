# Packet Scheduling to Admission Control

> A router with three flows pointed at one 2 Mbps output link has to pick who goes next. **FIFO** queues everything in arrival order and tail-drops when full — simple, but one aggressive burst starves everyone behind it. **Priority queuing** puts voice ahead of bulk transfers, yet a sustained high-priority stream can lock out low priority indefinitely. **Round robin** cycles one packet per flow for fairness, but big packets hog more byte-time than small ones. **WFQ (Weighted Fair Queueing)** fixes that with a virtual-clock finish-time formula `Fᵢ = max(Aᵢ, Fᵢ₋₁) + Lᵢ/Wᵢ` — each flow's weight W drains at a guaranteed fraction of link capacity, giving hard bandwidth and bounded-delay guarantees when paired with token-bucket shaping. None of that matters, though, if the router already overcommitted the link. **Admission control** is the gatekeeper: before a new flow is accepted, each router along the path compares the **flowspec** (token bucket rate, bucket size, peak rate, min/max packet size) against residual bandwidth, buffer, and CPU cycles, and either reserves resources or rejects the flow — like the telephone network refusing to give a dial tone. **RSVP** (RFC 2205) is the signaling protocol that carries those flowspecs: PATH messages travel sender→receiver advertising the traffic profile, RESV messages travel receiver→sender back up the multicast tree installing per-hop reservations. The whole chain — shape, schedule, admit, signal — is what turns "best effort" into "guaranteed QoS."

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01–05 (congestion control, traffic shaping)
**Time:** ~90 minutes

## Learning Objectives

- Compute a WFQ finish time for a packet given arrival time, length, weight, and previous finish time.
- Explain why FIFO plus tail drop lets one aggressive flow starve others, and name two schedulers that fix it.
- Distinguish priority queuing from WFQ with a large weight on the high-priority queue.
- Read a five-parameter flowspec (token bucket rate, bucket size, peak rate, min pkt, max pkt) and state which router resource each parameter constrains.
- Trace a PATH/RESV exchange through three routers and identify where a reservation fails.
- Decide, given residual capacity and a new flow's flowspec, whether admission control accepts or rejects.

## The Problem

Three flows arrive at the same router output line: a 1 Mbps video stream, a 0.5 Mbps VoIP call, and a 9 Mbps FTP backup. The line is 10 Mbps. Best-effort FIFO queues them in arrival order and transmits head-of-line first. The FTP burst lands first, fills the buffer, and tail-drops the video and voice packets behind it. The video user sees stuttering; the voice user hears gaps. Nothing in the FIFO rule says "voice matters more than backup."

The question is not "how fast is the link?" — it is "who goes next, and is there room for one more flow?" Packet scheduling answers the first half. Admission control answers the second. Without both, QoS is a wish.

## The Concept

Source: [`chapters/chapter-05-the-network-layer.md`](../../../../chapters/chapter-05-the-network-layer.md) §5.4.3 (packet scheduling) and §5.4.4 (admission control).

### FIFO (First-In First-Out)

One queue per output line. Packets leave in arrival order. When the queue fills, the new arrival is dropped (tail drop). Implementation is O(1) per packet. Failure mode: one bursty flow hogs capacity and delays every other flow's packets behind it. No isolation between flows.

### Priority Queuing

Multiple queues, one per priority class. Strict priority: always drain the highest-priority non-empty queue first; within a class, FIFO. Voice goes ahead of bulk transfer. Failure mode: a sustained high-priority stream starves low priority indefinitely — low-priority packets may wait forever. Mitigation: rate-limit the high-priority class, or use WFQ instead.

### Round Robin (Fair Queueing)

One queue per flow. Cycle through queues, take one packet from each non-empty queue in turn. Each of N flows gets roughly 1/N of the link. Nagle (1987). Flaw: a flow with large packets gets more byte-time than a flow with small packets. Demers et al. (1990) fixed this with byte-by-byte round robin simulated via a virtual clock.

### WFQ (Weighted Fair Queueing)

Each flow i has a weight Wᵢ. Finish time of packet i:

```
Fᵢ = max(Aᵢ, Fᵢ₋₁) + Lᵢ / Wᵢ
```

where Aᵢ is arrival time, Lᵢ is packet length, and Fᵢ₋₁ is the previous packet's finish time in the same flow. Packets are transmitted in increasing finish-time order across all flows. A flow with weight 2 drains twice as fast as weight 1. Parekh–Gallagher (1993, 1994) proved that token-bucket-shaped sources plus WFQ at every router gives **hard** end-to-end bandwidth and bounded-delay guarantees — the burst B is delayed at most B/R at the first router and that delay smooths the burst for downstream routers. Implementation: exact WFQ needs O(log N) per packet for a sorted finish-time queue; deficit round robin (Shreedhar & Varghese 1995) approximates it in O(1) and is what most real routers run.

### Admission Control

Before a flow is accepted, every router on the path checks whether it can honor the flowspec without breaking existing guarantees. Three resources are checked: bandwidth (don't oversubscribe the output line), buffer space (reserve enough to absorb the flow's bursts), CPU cycles (some packets cost more to process — ICMP, ACLs). The decision is per-hop: if any router on the path cannot reserve, the flow is rejected or rerouted (QoS routing). The M/M/1 queueing result shows why you cannot run at 100%: at ρ = λ/µ = 0.95, mean delay is 20× the zero-load service time. Admission control keeps ρ bounded.

### The Flowspec

Five parameters (RFC 2210/2211, Integrated Services):

| Parameter | Unit | Constrains |
|---|---|---|
| Token bucket rate R | bytes/sec | Sustained bandwidth reservation |
| Token bucket size B | bytes | Buffer reservation for max burst |
| Peak rate P | bytes/sec | Line-rate ceiling, never exceeded |
| Minimum packet size | bytes | CPU-cycle budget (per-packet overhead) |
| Maximum packet size | bytes | MTU / fragmentation limit |

The sender proposes; each router along the path may only **reduce** the spec (lower rate, smaller bucket), never increase. The result that reaches the receiver is the negotiated flow.

### RSVP — PATH and RESV

RSVP (RFC 2205) carries flowspecs along a multicast spanning tree. Two message types:

- **PATH** — sender → receiver. Carries the sender's traffic template (TSpec) and the path's advertised hop characteristics. Each router records the previous hop so RESV can travel back.
- **RESV** — receiver → sender, back up the tree. Carries the reservation request (RSpec) and the flowspec. Each router on the reverse path runs admission control: if it can reserve, it installs the per-flow state and forwards RESV upstream; if not, it sends ResvErr back to the receiver and the reservation fails.

Receiver-initiated because in multicast the set of receivers is dynamic — senders cannot track joiners and leavers. PATH is sent periodically to refresh path state; RESV is sent periodically to refresh reservations. Soft state, not hard.

### Comparison

| Scheduler | Fairness | Isolation | Complexity | Delay bound |
|---|---|---|---|---|
| FIFO | None | None | O(1) | Unbounded |
| Priority | By class | Partial (high from low) | O(1) | Low-priority unbounded |
| Round robin | Per-flow, packet-biased | Good | O(1) | Bounded by N packets |
| WFQ | Per-flow, byte-fair | Hard | O(log N) exact, O(1) DRR | B/R per router |

## Build It

`code/main.py` simulates three schedulers — FIFO, strict priority, and WFQ — on the same input trace of three flows (voice, video, bulk) hitting one 10 Mbps link. For each scheduler it prints per-flow packet count, bytes transmitted, mean delay, and max delay. Run it and compare the delay columns: WFQ should give voice the lowest max delay while still letting bulk make progress; FIFO should show bulk dominating; strict priority should show low-priority starvation.

Then modify the trace: double the bulk burst size and rerun. Watch FIFO's voice max delay explode while WFQ's voice bound stays close to B/R.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the scheduler | Device config (`qos-policy`, `priority-queue`, `wfq`), `show interface` queue stats | You can name which scheduler a router is running and its weights |
| Confirm fairness | Per-flow throughput counters, per-flow queue depth | Each flow's throughput is within one packet of its WFQ share |
| Diagnose starvation | Low-priority queue depth growing, low-priority tx count near zero | Strict priority with no rate limit is the hypothesis |
| Admit or reject a flow | Flowspec vs. residual bandwidth on each hop; ResvErr trace | The reject decision is reproducible from the numbers |
| Trace RSVP | `show ip rsvp`, PATH/RESV message counts, ResvErr | You can point to the hop that failed admission |

## Ship It

Produce one artifact under `outputs/`:

- A per-scheduler delay comparison report generated from `code/main.py` with your own trace, OR
- A one-page RSVP PATH/RESV call flow for a three-router path with the flowspec at each hop and the admit/reject decision annotated, OR
- A runbook: "VoIP sounds choppy — is it the scheduler or admission control?" with the three commands to run and the decision tree.

Start from [`outputs/prompt-packet-scheduling-to-admission-control.md`](../outputs/prompt-packet-scheduling-to-admission-control.md).

## Exercises

1. Compute the WFQ finish times for the trace in `code/main.py` by hand for the first four packets and verify against the program's output.
2. In the simulator, make bulk traffic 10× larger. Which scheduler keeps voice delay bounded? Which does not? Why?
3. A router has 100 Mbps residual capacity. A new flow requests R = 30 Mbps, B = 200 KB, peak = 50 Mbps. Can it be admitted if two existing flows already hold 70 Mbps? What if one of them is FIFO and not WFQ?
4. Trace a PATH message from sender S through routers R1, R2, R3 to receiver D. Where does RESV get generated? At which hop can ResvErr originate, and what state does each router roll back?
5. Modify `main.py` to add deficit round robin as a fourth scheduler and compare its delay to exact WFQ. How close is the approximation?
6. Argue why RSVP is receiver-initiated rather than sender-initiated, using the multicast television example from §5.4.5.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| FIFO | "normal queueing" | Arrival-order queue with tail drop; no flow isolation |
| Priority queuing | "voice first" | Strict class-based ordering; low class can starve |
| Round robin | "fair" | One packet per flow per turn; biased toward large packets |
| WFQ | "weighted fair" | Byte-fair virtual-clock scheduler with hard guarantees under token-bucket shaping |
| Finish time Fᵢ | "a number" | The virtual round at which packet i completes; packets sent in F order |
| Flowspec | "the contract" | Five-parameter description of a flow negotiated hop by hop, only reducible |
| Admission control | "saying yes or no" | Per-hop check of flowspec against residual bandwidth/buffer/CPU before accepting a flow |
| RSVP PATH | "downstream" | Sender→receiver message advertising traffic template and path state |
| RSVP RESV | "upstream" | Receiver→sender reservation request carrying flowspec; installs per-hop state |
| ResvErr | "it failed" | Admission control rejected the flow at some hop; soft state rolls back |
| Deficit round robin | "fast WFQ" | O(1) approximation of WFQ used in real routers |

## Further Reading

- [RFC 2205 — RSVP Version 1 Functional Specification](https://www.rfc-editor.org/rfc/rfc2205)
- [RFC 2210 — RSVP with Integrated Services](https://www.rfc-editor.org/rfc/rfc2210)
- [RFC 2211 — Controlled-Load Network Element Service](https://www.rfc-editor.org/rfc/rfc2211)
- [RFC 2475 — Differentiated Services Architecture](https://www.rfc-editor.org/rfc/rfc2475) (the per-flow alternative)
- Tanenbaum & Wetherall, *Computer Networks* 5th ed., Chapter 5 §5.4.3–§5.4.5
- Parekh & Gallagher (1993, 1994), "A Generalized Processor Sharing Approach to Flow Control" — the WFQ delay-bound proof
- Shreedhar & Varghese (1995), "Efficient Fair Queueing using Deficit Round Robin"
