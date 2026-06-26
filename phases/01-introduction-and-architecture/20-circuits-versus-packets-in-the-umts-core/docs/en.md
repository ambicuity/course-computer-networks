# Circuit Versus Packet Networking in the Mobile Core Network

> The UMTS 3G core network is the textbook case of a network caught mid-transition between two competing philosophies. On the **circuit-switched (CS) path** a voice call enters through the **Iu-CS** interface, is admitted by the **MSC / GMSC**, cross-connected by a **Media Gateway (MGW)** onto a 64 kbps PCM slot of the **PSTN**, and holds that bandwidth end-to-end for the whole call — giving hard quality of service but aborting the call if any switch or trunk on the reserved path fails. On the **packet-switched (PS) path** a data session enters through **Iu-PS**, is anchored by the **SGSN** (Serving GPRS Support Node) for mobility and charging, exits through the **GGSN** (Gateway GPRS Support Node) over the **Gi** interface to the Internet, and every IP packet is routed independently over a **GTP tunnel** (GPRS Tunneling Protocol, 3GPP TS 29.060) — fault-tolerant but prone to loss and jitter under load. The **RNC** (Radio Network Controller) sits in front of both paths and decides per-bearer which interface to use; the **HSS** (Home Subscriber Server) holds the IMSI, authentication quintet, and current Location Area so either path can find the mobile; and **soft handover** let a CDMA mobile keep two Node Bs at once while **hard handover** broke first then reconnected. This lab builds a runnable core-network simulator that admits a voice circuit with bandwidth reservation versus a packet data session with best-effort queueing, so you can watch the failure modes — call rejection on resource exhaustion, packet loss under congestion — that drove the move to an all-IP core in LTE.

**Type:** Lab
**Languages:** Python, simulation
**Prerequisites:** The Internet architecture and the circuit-vs-packet debate (Phase 1 introduction); familiarity with the idea of a bearer and a tunnel
**Time:** ~85 minutes

## Learning Objectives

- Classify each UMTS core node (MSC, GMSC, MGW, SGSN, GGSN, HSS, RNC, Node B) as serving the CS path, the PS path, or both, and name the interface that connects it (Iu-CS, Iu-PS, Gi, Gn, MAP).
- Explain the admission-control decision the MSC makes for a voice call: compare requested 64 kbps PCM slots against free trunk capacity and either reserve for the call's duration or reject with a busy signal.
- Distinguish a GTP-U tunnel (UDP/2152) carrying user-plane IP packets between SGSN and GGSN from a circuit's reserved timeslot, and state which one survives a single-node failure.
- Trace a soft handover (mobile held by two Node Bs simultaneously) versus a hard handover (break-before-make) and predict which leaves a gap in the audio.
- Reproduce the textbook's point that circuits buy quality of service by reserving bandwidth, switch buffers, and CPU up front, while packet nets choke and drop under simultaneous load — and quantify the loss.
- Identify the evidence in the simulator — accepted/rejected calls, queue depths, lost packets — that shows which core philosophy is carrying each flow.

## The Problem

An operator runs a UMTS network with a fixed-capacity CS trunk (say 8 PCM E1 slots = 8 × 64 kbps voice calls) between the MSC and the PSTN, and a single PS path whose Gn link between SGSN and GGSN can carry, in round numbers, 2 Mbps of best-effort IP traffic. At 17:55 on a Friday, subscribers in one cell start a burst: nine voice calls and a 3 Mbps downlink video session all arrive inside a few seconds. The MSC must admit or reject each voice call against the 8-slot trunk — the ninth caller gets a network busy signal even though the radio link is fine. Meanwhile the SGSN queues the data packets behind a finite output buffer; once the queue overfills the system drops packets and the video stutters.

The engineer has to answer two questions the simulator must make visible: *how many calls does the circuit core admit before it starts rejecting*, and *what packet-loss rate does the packet core produce when offered traffic exceeds the Gn link capacity*. These are precisely the trade-offs the textbook describes: circuits reserve resources up front and either give good service or a busy signal; packet nets accept everything and degrade. The UMTS core shows both designs running side by side through one RNC, which is the whole point of the lesson.

## The Concept

### The UMTS core: two cores, one radio access network

The radio access network (RAN) — the **Node B** base stations and their **RNC** controller, joined over the air interface **Uu** — is shared. Behind the RNC the core forks. Voice and circuit data cross **Iu-CS** to the **MSC** (and the gateway variant **GMSC** for calls entering or leaving the operator's network); a **Media Gateway (MGW)** converts the packetized voice of the UMTS backbone into the 64 kbps PCM timeslots of the **PSTN**. Packet data crosses **Iu-PS** to the **SGSN**, which anchors the mobile for mobility and charging, and on over the **Gn** interface to the **GGSN**, which faces the Internet across **Gi** and allocates the mobile an IP address. See `assets/circuits-versus-packets-umts-core.svg` for the fork.

| Node | camp | Path | Interfaces |
|---|---|---|---|
| Node B | RAN | shared (both) | Uu (air), Iub (to RNC) |
| RNC | RAN | shared (both) | Iub, Iu-CS, Iu-PS |
| MSC / GMSC | circuit | CS | Iu-CS, ISUP to PSTN |
| MGW | circuit | CS | Nb (bearer), PSTN PCM |
| SGSN | packet | PS | Iu-PS, Gn (to GGSN) |
| GGSN | packet | PS | Gn, Gi (to Internet) |
| HSS | both | both | MAP/Gr (to SGSN, MSC) |

### Admission control on the circuit path

When the MSC receives a call setup over Iu-CS it runs a simple reservation test: is there a free 64 kbps trunk slot to the destination for the whole duration of the call? If yes, it deducts one slot from the free pool, marks the slot busy for the call's lifetime, and emits an ISUP IAM (Initial Address Message, ITU-T Q.763) toward the GMSC. If no, the call is rejected and the caller hears a busy signal — exactly the textbook's "if insufficient resources are available, the call is rejected." The crucial property is *determinism*: once admitted, the call's quality is fixed and immune to other traffic, because the slot is reserved.

Worked example: the MSC-to-PSTN trunk carries 8 slots. Calls arrive; each holds its slot for a random duration. The 9th simultaneous call is rejected even though the radio access network and the mobile both have capacity. `code/main.py` models the trunk as a counting semaphore and prints exactly which calls are admitted and which are rejected.

### Best-effort queueing on the packet path

The PS path does not reserve. The SGSN presents packets to the Gn link, which has a fixed service rate (say 2 Mbps) and a finite queue (say 1 MB, about half a second at the link rate). When offered traffic exceeds the service rate, the queue fills; once full, arriving packets are dropped. Unlike the circuit case there is no busy signal — the sender (TCP) notices the loss via duplicate ACKs or a timeout and backs off, but the application sees jerkiness.

The textbook's contrast is exact: "if too many packets arrive at the same router at the same moment, the router will choke and probably lose packets." `code/main.py` simulates this with a discrete-time queue. At each tick a random number of packets arrive (a simple on/off bursty source), the link dequeues its capacity, and overflow is counted as loss. Run it and you get a loss-vs-offered-load curve that matches the textbook's diagnosis.

### GTP tunnels: the packet path's answer to circuits

Interestingly the packet core does build something circuit-like: a **GPRS Tunneling Protocol (GTP)** tunnel between SGSN and GGSN, identified by a 32-bit **TEID** (Tunnel Endpoint Identifier) and carried over UDP port 2152 (GTP-U, user plane; 3GPP TS 29.060, TS 29.281). The tunnel gives the mobile a stable anchor — the GGSN's IP address and the TEID — while the mobile roams between SGSNs. But it is *not* a circuit: it reserves no bandwidth and gives no latency guarantee. It is a forwarding label, not a timeslot. Compare:

| Property | CS trunk slot (MSC↔PSTN) | GTP-U tunnel (SGSN↔GGSN) |
|---|---|---|
| Reserved bandwidth | yes, 64 kbps for call duration | no |
| State on failure | call aborted if any element fails | packets rerouted, tunnel re-anchored |
| Identifier | E1 timeslot number | 32-bit TEID, UDP/2152 |
| Quality | fixed, immune to load | best-effort, lossy under congestion |
| Setup signaling | ISUP IAM/ACM/ANM | PDP context activation (3GPP TS 23.060) |

### Handover: soft versus hard, and which core cares

Mobility is the other thing that breaks in the core. As the textbook says, when a mobile crosses a cell boundary the traffic flow must be re-routed from the old Node B to the new one. CDMA systems — UMTS/WCDMA is one — allow a **soft handover**: the mobile is connected to *both* Node Bs for a short window, so there is no gap in service. A **hard handover** breaks the old link first, then makes the new one, leaving a short silence.

Crucially, the *core* path differs by what is being handed over. On the CS path the MSC must re-bridge the circuit to the new RNC; on the PS path the SGSN simply updates the GTP tunnel endpoint to the new RNC. The PS path tolerates a few dropped packets in the handover window; a CS soft handover hides the gap by combining frames at the RNC. `code/main.py` models both: a soft handover keeps an old-link and new-link buffer alive during overlap and combines them; a hard handover drops the frames in the gap.

### HSS: how either core finds the mobile

A mobile is addressed by its **IMSI** (up to 15 digits, E.212), stored on the **SIM card** along with the long-term key Ki and the authentication algorithm. The **HSS** holds, per IMSI, the current serving node (SGSN or MSC) and a Location Area identifier. When a call arrives at the GMSC, it queries the HSS over the **MAP** (Mobile Application Part, 3GPP TS 29.002) protocol to find which MSC currently serves the mobile, then routes the ISUP IAM there. The PS path does the same: the GGSN, on receiving a downlink packet for a mobile it has no PDP context for, asks the HSS which SGSN holds it and forwards via GTP. The HSS is the single source of truth that both cores agree on.

### Decision rule the RNC applies

Per-bearer, the RNC (or, in later releases, the core) decides which interface to use:

| Bearer type | Path | Admission | Why |
|---|---|---|---|
| Conversational voice | Iu-CS | reserve slot, else reject | needs deterministic delay, low rate (64 kbps, or 3–4× less compressed) |
| Streaming video | Iu-PS | best-effort GTP | bursts, tolerates some loss, high peak rate |
| Interactive web | Iu-PS | best-effort | request/response, elastic |
| Background (SMS, file) | Iu-PS | best-effort | no delay bound |

The textbook says data rates of "tens of kbps" on early GPRS grew to "multiple Mbps," while a voice call is "carried at a rate of 64 kbps, typically 3–4x less with compression." The simulator encodes exactly those rates so you can see why voice keeps a circuit and data does not.

### Worked numeric example

Offer the network 10 voice calls of average duration 120 s against an 8-slot CS trunk over a 200 s window. Expected admitted calls = 8, rejected = 2 — wasted radio capacity with a busy signal. On the PS side, offer 3 Mbps against a 2 Mbps Gn link with a 1 MB queue: as the queue saturates the loss rate climbs toward roughly (3 − 2)/3 ≈ 33%. `code/main.py` prints both numbers each run, and varying the offered load reveals the knee where the packet core starts degrading while the circuit core simply rejects.

## Build It

1. Open `code/main.py`. It defines a `CircuitTrunk` (a counting semaphore over a fixed slot count) and a `PacketQueue` with a service rate in packets per tick and a finite buffer in packets.
2. Run `python3 code/main.py`. The demo admits a burst of voice calls against the trunk and reports which were accepted and which were rejected with a busy signal; then it runs a packet-data load test and reports the loss rate at several offered loads.
3. Read the `handover` section: `soft_handover` keeps two link buffers alive during an overlap and combines frames; `hard_handover` produces a gap whose length equals the overlap you removed.
4. Change `TRUNK_SLOTS = 8` to `4` and rerun — watch rejections climb. Change `GN_RATE` to a lower number and watch the packet loss rate rise sharply.
5. Try offered load 1.0, 1.5, 2.0, 3.0 × capacity and observe the loss curve; locate the knee where best-effort breaks down.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the CS trunk admits up to its slot count | accepted/rejected log per call | exactly `TRUNK_SLOTS` admitted, the rest rejected with a busy signal — no degradation of admitted calls |
| Confirm the PS path loses packets under overload | loss count and loss rate at each offered load | loss rises above the service rate; below saturation, loss ≈ 0 |
| Compare failure modes | busy signal vs dropped packets | the circuit rejects, the packet degrades — neither is free |
| Verify a GTP tunnel is just a label | the `TEID` is carried, not bandwidth | a tunnel can exist with zero reserved bandwidth; quality still varies with load |
| Distinguish handover types | gap length in frames for soft vs hard | soft = 0 lost frames during overlap; hard = overlap-length gap |
| Validate HSS lookup | IMSI → serving SGSN/MSC binding returns current node | both cores resolve the mobile by querying HSS, not by guessing |

## Ship It

Produce one artifact under `outputs/`:

- A runbook comparing a CS voice session and a PS data session on the same RNC, annotated with which node admitted the flow, what was reserved, and what failed (or degraded) when the trunk or link saturates.
- Start from the printed output of `code/main.py` and an offered-load sweep. Write `outputs/prompt-circuits-vs-packets-umts-core.md` describing the artifact and what it proves about the circuit–packet trade-off.

## Exercises

1. The CS trunk has 8 slots. Model nine simultaneous calls whose holding times are exponential with mean 120 s. By inspection of the simulator output, estimate the probability the ninth call is blocked. Now double the holding time — what happens to blocking?
2. Offer the PS path traffic at 0.9, 1.0, 1.1, and 2.0 times the Gn link capacity. Plot the steady-state loss rate. At what offered load does it first exceed 10%? Why is the loss not zero at 0.9 even though average demand is below capacity?
3. A voice call uses a CS slot for its entire duration; a TCP file download uses the PS path for its entire duration. Suppose both must traverse a node that fails halfway through. Which flow aborts and which survives with a retransmission? Relate this to the textbook's fault-tolerance comparison.
4. Modify the simulator so the PS path reserves bandwidth for streaming video (a "PDP context with guaranteed bit rate"). Show numerically how this turns packet loss into admission rejection, and explain which philosophy you have just implemented.
5. A mobile in soft handover is held by two Node Bs for 200 ms while it moves between cells. Compute the frames lost (assume one 20 ms voice frame per tick) for soft versus a hard handover whose break-make gap is 60 ms. Why does CDMA make soft handover practical where a 1G AMPS system could not?
6. The GGSN receives a downlink packet for an IMSI it has no active PDP context for. Walk the HSS query (MAP) and GTP forwarding sequence the GGSN and SGSN perform to deliver it, naming the protocols and the tunnel endpoint that gets created.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Iu-CS / Iu-PS | "two interfaces from the RNC" | The RNC's circuit-switched and packet-switched user-plane interfaces into the core; the fork where the network chooses its philosophy |
| MSC / GMSC | "the voice switch" | Mobile Switching Center admits and switches CS calls; Gateway MSC is the entry/exit point for calls to/from other operators |
| MGW | "the gateway box" | Media Gateway translating the UMTS packet voice backbone into 64 kbps PCM timeslots on the PSTN |
| SGSN | "the data anchor" | Serving GPRS Support Node; anchors a mobile's PS mobility, charging, and routes GTP tunnels to the GGSN |
| GGSN | "the Internet gateway" | Gateway GPRS Support Node; allocates the mobile's IP address and bridges Gn tunnels to the Internet over Gi |
| GTP / TEID | "the mobile VPN" | GPRS Tunneling Protocol (3GPP TS 29.060); a 32-bit Tunnel Endpoint Identifier on UDP/2152 labels each mobile's flow — a forwarding label, not reserved bandwidth |
| HSS | "the subscriber database" | Home Subscriber Server; holds IMSI, authentication quintet, and current serving node, queried via MAP by both cores |
| Soft handover | "make-before-break" | CDMA mobile connected to two Node Bs simultaneously, frames combined at the RNC, zero gap |
| Hard handover | "break-before-make" | old link torn down before new one is up, leaving a silence equal to the gap |
| IMSI | "the phone number inside" | International Mobile Subscriber Identity (E.212, up to 15 digits) on the SIM; the identifier both cores use to find the mobile |
| PDP context | "the data session" | the PS equivalent of a call setup; establishes a GTP tunnel and a mobile IP address without reserving bandwidth |

## Further Reading

- **3GPP TS 25.410** — UTRAN Iu Interface: Overall Aspects (the Iu-CS / Iu-PS split).
- **3GPP TS 29.060** — GPRS Tunnelling Protocol (GTP) across the Gn and Gp interface (TEID, UDP/2152 for GTP-U).
- **3GPP TS 23.060** — General Packet Radio Service (GPRS); PDP context activation and SGSN/GGSN procedures.
- **3GPP TS 29.002** — Mobile Application Part (MAP) specification, used by the HSS.
- **3GPP TS 23.401** — EPS / Evolved Packet System architecture (the all-IP core that succeeded the CS/PS split).
- **ITU-T E.212** — Identification plan for land mobile stations (IMSI structure).
- **ITU-T Q.763** — ISUP signaling messages (IAM, ACM, ANM) used by the MSC/GMSC.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.5.2 (Third-Generation Mobile Phone Networks).
- Kaaranen et al., *UMTS Networks: Architecture, Mobility and Services*, 2nd ed., Wiley, 2005.