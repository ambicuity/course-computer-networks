# Integrated Services

> Integrated Services (IntServ) is the IETF's flow-based QoS architecture: each traffic flow explicitly reserves resources along its path, routers maintain per-flow state, and a signaling protocol (RSVP) walks reservation state from receivers up the multicast tree toward senders. Two service classes were defined — **guaranteed service** (RFC 2212) gives hard delay bounds via fluid modeling, **controlled load** (RFC 2211) approximates best-effort behavior on an unloaded network. The model delivers real guarantees but does not scale: thousands of flows mean thousands of per-flow queues and reservation records in every core router, and every flow needs an advance setup exchange. That scalability wall is why the IETF built the class-based alternative (Differentiated Services) right beside it. Understanding IntServ is understanding the tradeoff between hard per-flow guarantees and per-flow operational cost.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Phase 8 lessons 01–06 (congestion control, traffic shaping, packet scheduling, admission control)
**Time:** ~90 minutes

## Learning Objectives

- Explain why per-flow reservation needs a signaling protocol separate from the data path, and why that protocol runs receiver-to-sender (upstream).
- Trace an RSVP PATH message downstream and an RSVP RESV message upstream, naming what state each installs in each router.
- Distinguish a **flowspec** (TSpec + RSpec) from the reservation itself, and read both off a reservation request.
- Tell guaranteed service from controlled load in terms of the guarantee each makes and the queueing each requires.
- Name the three scalability problems (per-flow state, advance setup, router complexity) that pushed the IETF toward Differentiated Services.
- Run the simulator, admit or reject a flow from its flowspec, and produce the evidence an operator would read to confirm a reservation succeeded.

## The Problem

A video conference between two sites is not a best-effort flow. If the network queues it behind a large file transfer, the audio stutters and the video freezes. The application does not need "as much bandwidth as possible" — it needs a bounded delay and a bounded loss rate, end to end, for the lifetime of the call.

Best-effort IP gives none of that. The network treats every packet identically, queues drop under load, and delay varies with whatever else is in the queue. The question IntServ set out to answer: can the network reserve resources per flow so that a single flow's behavior is predictable even when other flows compete?

The answer is yes — at a price. To guarantee anything per flow, routers must know the flow exists, must hold state for it, and must check that admitting it will not break existing guarantees. That requires a signaling protocol, a per-flow data structure, and an admission-control decision at every hop. IntServ is the architecture that defines those pieces; RSVP is the protocol that drives them.

## The Concept

### The IntServ model

IntServ adds three things to a best-effort router:

1. **A flow descriptor** (the flowspec): a formal statement of the traffic the sender will inject (TSpec) and the service the receiver wants (RSpec).
2. **Per-flow state** in every router on the path: the router remembers the flow, its reservation, and its queue parameters.
3. **A packet scheduler** (typically WFQ — weighted fair queueing, Phase 8 · 06) that enforces the reservation at every outgoing interface.

The flow is the unit of QoS. A flow is identified by the 5-tuple (src addr, dst addr, protocol, src port, dst port) or, for multicast, by (src addr, group addr, protocol, port). Every router on the path installs the same flow descriptor and runs the same scheduler against it. The guarantee is end-to-end only because every hop honors it.

### RSVP signaling: PATH and RESV

RSVP is the signaling protocol, not the data protocol. Data packets follow normal IP routing; RSVP installs the reservation state that the scheduler uses to treat those data packets correctly.

The protocol is **receiver-initiated**. The sender does not know who is listening or what they want. The receiver tells the network. Two messages drive the state machine:

- **PATH** — sender → receiver (downstream). The sender periodically multicasts a PATH message down the spanning tree. Each PATH carries the sender's TSpec (the traffic it will produce) and accumulates a *path state* at every hop: the previous hop address, so a later RESV knows where to go upstream. PATH does not reserve anything. It advertises.
- **RESV** — receiver → sender (upstream). A receiver that wants a reservation sends a RESV message back up the tree, following the previous-hop chain the PATH left behind. The RESV carries the flowspec the receiver wants. At each hop, the router runs **admission control**: does the outgoing interface have enough free capacity to honor this flowspec alongside existing reservations? If yes, the router installs the reservation (per-flow state + scheduler entry) and forwards RESV upstream. If no, the router sends a RESVERR back downstream and the reservation fails.

PATH and RESV are soft state. They are re-sent periodically (default 30 seconds). If messages stop arriving, the state times out and the reservation is released. This handles dynamic group membership — a receiver that leaves simply stops sending RESV — and router crashes — state rebuilds itself when messages resume.

### The flowspec: TSpec and RSpec

A flowspec has two parts:

- **TSpec** (Traffic Spec) — what the sender will inject. Token bucket parameters: peak rate `p`, bucket size `b`, sustainable rate `r`, minimum policed unit `m`, maximum datagram size `M`. The sender's traffic is policed against this; packets that violate the TSpec are out of profile and may be dropped or re-marked.
- **RSpec** (Reservation Spec) — what the receiver wants the network to provide. Service class (`guaranteed` or `controlled-load`) plus, for guaranteed service, a rate `R` and a slack term `S` describing how much extra delay the receiver can tolerate beyond the theoretical minimum.

Admission control compares the RSpec against the free capacity on the interface, taking the TSpec as the upper bound on what the flow could send. A flow is admitted only if the scheduler can guarantee the RSpec for the offered TSpec.

### Guaranteed service (RFC 2212)

Guaranteed service provides a **hard delay bound**. The end-to-end delay is bounded by a formula derived from the fluid model: the network treats the flow as a fluid with rate `R`, and the delay through each hop is bounded by the bucket size, the rate, and the per-hop latency. The receiver can compute the worst-case end-to-end delay before the flow starts and know that no packet will arrive later.

The price is WFQ (or another scheduling discipline that provides a rate guarantee) plus a per-hop latency term that the PATH message accumulates. The receiver gets a number — "your delay will not exceed 150 ms" — and can plan around it. Guaranteed service is the right choice for real-time audio and video where late is as bad as lost.

### Controlled load (RFC 2211)

Controlled load makes a softer promise: the flow will get service "approximately equivalent to best-effort on an unloaded network." There is no delay bound. There is no mathematical guarantee. The network admits the flow only if enough capacity is free that, under the offered load, the queue stays short and loss stays near zero.

Controlled load is simpler to implement — it does not require WFQ's rate guarantee, only that the router not overcommit the interface. It is the right choice for adaptive applications (audio/video with playback buffers, loss-tolerant codecs) that can tolerate variation but not sustained congestion.

### Per-flow state: the cost of the guarantee

Every IntServ router holds, per admitted flow: the flowspec, the path state (previous hop, next hop for multicast), the reservation state (admitted or not), and a scheduler entry (which queue, what weight). For a core router carrying 100,000 concurrent flows, that is 100,000 state entries — each of which must be created by a signaling exchange, refreshed every 30 seconds, and torn down on timeout.

Compare with best-effort: zero per-flow state. The router forwards a packet and forgets it. IntServ trades that forgetfulness for a guarantee.

### Scalability limitations

Three problems killed broad IntServ deployment:

1. **Per-flow state does not scale.** A backbone router carrying millions of flows cannot hold millions of reservation records in fast memory. The state grows linearly with the number of active flows.
2. **Advance setup per flow.** Every flow requires a PATH/RESV exchange before data flows. For short flows (a web request, a DNS query) the setup cost dwarfs the data transfer. IntServ only makes sense for long-lived flows.
3. **Router complexity.** Admission control, per-flow queueing, and RSVP state machines are substantial additions to the forwarding path. Every router on the path must implement all of them for the guarantee to hold end-to-end.

These are why the IETF built Differentiated Services (Phase 8 · 08): class-based, no per-flow state, no per-flow setup, no end-to-end signaling. The trade is no per-flow guarantee. IntServ remains the reference for what "hard QoS" means; DiffServ is what got deployed.

## Build It

1. Write the one-paragraph mechanism summary in your own words: PATH advertises, RESV reserves, the scheduler enforces, soft state refreshes.
2. Draw the PATH/RESV message flow for one sender and two receivers on a three-router tree. Label which state each message installs at each hop.
3. Identify the evidence that would confirm a reservation succeeded: RESV reached the sender, the scheduler queue exists for the flow, no RESVERR was generated.
4. Identify one failure mode and the smallest test that would confirm it: a router rejects admission (RESVERR), a RESV refresh is missed and state times out, a sender's TSpec is violated and packets are out of profile.
5. Run `code/main.py` — it simulates the full PATH/RESV exchange over a small network, admits or rejects flows by checking each interface's free capacity against the flowspec, and prints the per-hop state after each step. Replace the sample flows with your own and observe which get admitted.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Locate the layer | RSVP messages, per-flow state in router tables, scheduler queue entries | You can explain why a flow's behavior is a network-layer decision, not an application symptom |
| Explain normal behavior | PATH/RESV exchange trace, admitted flow, scheduler honoring the rate | Observed messages match the soft-state model; refresh interval is consistent |
| Diagnose abnormal behavior | RESVERR message, missed refresh, out-of-profile packets dropped | The failure hypothesis predicts which hop rejected and why (capacity, TSpec violation, timeout) |

## Ship It

Create one artifact under `outputs/`:

- A PATH/RESV trace annotation for the simulator's run, showing every hop's state after each message
- A one-page runbook: "Flow rejected — what to check" (admission control, TSpec conformance, refresh state, scheduler queue)
- The RSVP state diagram (PATH/RESV/RESVERR/timeout transitions)
- The simulator itself, extended with a fourth router or a second sender, with the admission decisions annotated
- A study prompt that teaches IntServ from the evidence the simulator prints

Start with `outputs/prompt-integrated-services.md`.

## Exercises

1. List the RSVP state (path state, reservation state) a router holds for one admitted flow, and state how often each is refreshed.
2. Run the simulator with the default topology. Which flows are admitted? Which are rejected? Why?
3. Increase one flow's RSpec rate until admission fails. Note the exact interface and free capacity at the failing hop — that is the evidence.
4. A receiver stops sending RESV. How many refresh periods before the router releases the reservation? What does the scheduler do in the meantime?
5. Compare guaranteed service and controlled load for a 64 kbps audio flow with a 200 ms playback buffer. Which do you pick, and what changes if the buffer is 2 seconds?
6. Describe the three scalability limitations of IntServ and, for each, the specific DiffServ design choice that addresses it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| IntServ | "the flow-based QoS thing" | An architecture where every router holds per-flow state and runs a scheduler per flow |
| RSVP | "the reservation protocol" | Receiver-initiated soft-state signaling: PATH advertises downstream, RESV reserves upstream |
| Flowspec | "the traffic description" | TSpec (offered traffic, token bucket) + RSpec (service requested, rate + slack) |
| Guaranteed service | "hard QoS" | A mathematical end-to-end delay bound, enforced by WFQ, per RFC 2212 |
| Controlled load | "soft QoS" | Service approximately equivalent to best-effort on an unloaded network, per RFC 2211 |
| Per-flow state | "what the router remembers" | The flowspec, path state, reservation state, and scheduler entry a router holds per admitted flow |
| Soft state | "state that times out" | Reservation state refreshed by periodic messages; released automatically if refreshes stop |
| Admission control | "the yes/no decision" | The per-hop check that free interface capacity can honor the flowspec alongside existing reservations |

## Further Reading

- RFC 1633 — Integrated Services in the Internet Architecture: Overview
- RFC 2205 — Resource ReSerVation Protocol (RSVP) — Version 1 Functional Spec
- RFC 2210 — The Use of RSVP with IETF Integrated Services
- RFC 2212 — Specification of Guaranteed Quality of Service
- RFC 2211 — Specification of the Controlled-Load Network Element Service
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, §5.4.5–5.4.6
- The full source chapter: `chapters/chapter-05-the-network-layer.md`