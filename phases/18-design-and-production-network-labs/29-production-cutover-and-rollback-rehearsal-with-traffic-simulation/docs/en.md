# Production cutover and rollback rehearsal with traffic simulation

> Every production network change at scale follows the same non-negotiable sequence: open a change ticket in ServiceNow (CHG record, normal priority, CAB-approved maintenance window), freeze the deploy calendar, run a tabletop runbook with the on-call rotation, rehearse the rollback against a synthetic load profile, and only then push the production cutover. This lesson codifies that workflow as a blue/green/canary exercise for a payments edge gateway: a weighted load balancer (NGINX, Envoy, or HAProxy with stick-table session pinning) shifts a configurable percentage of traffic from the current blue pool (v1) to the candidate green pool (v2) in measured steps — 1%, 5%, 25%, 50%, 100% — while a SloGate controller watches a 5-second sliding-window 5xx error budget (trip threshold 1.0%) and a /healthz check (3 consecutive failures aborts). The deliverable is a runbook-ready Python simulator at `code/main.py` that emits the cutover timeline, the per-pool error and p50/p95 latency, the wall-clock time at which the SloGate aborted or the cutover was promoted, and a JSON record suitable for a post-incident review. The visual in `assets/production-cutover-and-rollback-rehearsal-with-traffic-simulation.svg` shows the rollback arrow returning all traffic to blue when the budget is burned.

**Type:** Capstone Project
**Languages:** Python (stdlib only: dataclasses, json, random, statistics), shell, curl, iperf3
**Prerequisites:** Phase 16 (Anycast and High Availability — connection draining, BGP MED withdrawal), Phase 18 Lessons 21-28 (full IGP, BGP, EVPN, and segment-routing lab sequence)
**Time:** ~180 minutes

## Learning Objectives

- Build a deterministic change-management runbook that names the change ID, the affected service, the canary weight schedule, the error budget, the SLO window, the health-check criteria, and the abort criteria, and is auditable by a Change Advisory Board.
- Implement a weighted-traffic dispatcher in Python that emulates NGINX/Envoy canary weights and routes synthetic requests between a blue and a green backend pool with configurable per-pool error rate and latency.
- Implement a sliding-window SloGate that records every response, prunes events older than the window, and trips on a configurable error budget; require a minimum request count before enforcement to avoid premature abort during warmup.
- Implement a /healthz probe with consecutive-failure tracking so three failed checks inside the abort threshold force an immediate rollback regardless of the SloGate.
- Distinguish four cutover states — Promote (full cutover complete), Continue (hold at current weight), Escalate (jump to next weight early), Abort (roll back to 0% green, 100% blue) — and emit the exact wall-clock time each state was entered.
- Produce a JSON report and a human-readable summary that a network operations center (NOC) engineer can attach to a post-cutover review and a Sev-1 incident postmortem.

## The Problem

A fintech has a payments edge gateway fronting 2,400 transactions per second across three data centers. The current production stack runs a custom TCP load balancer on FreeBSD jails, terminating TLS at the edge and proxying cleartext to a Java backend on Cisco UCS blades. Engineering wants to swap the FreeBSD edge for an Envoy-based proxy with HTTP/3, JWT validation at the edge, and a new circuit-breaker policy. The risk profile is brutal: a 5xx burst of 2% over 30 seconds at peak is roughly $48,000 per minute in declined-card revenue, and a 30-second outage would trigger the regulator's 24-hour outage-disclosure rule.

The platform team has been burned before. Six months ago they cut over the analytics edge from NGINX 1.18 to NGINX 1.22 in a single shot at 02:00 local. The new version changed the default for `keepalive_requests` from 1,000 to 10,000, which sounded fine until the upstream's connection-pool accounting hit a misconfigured limit and every other request got a 502. They had no canary, no SloGate, and the rollback playbook was a 14-line shell script that nobody had rehearsed. The on-call engineer ran the rollback, but the script called `kubectl rollout undo` on a deployment that had already been deleted by the failed rollout, so the rollback silently no-op'd. The Sev-1 lasted 47 minutes.

The CTO has now mandated that every Tier-0 cutover follow the four-step protocol in this lesson: a written CAB-approved runbook with weight steps, a synthetic load profile that mirrors production RPS, a SloGate that auto-aborts on SLO burn, and a rehearsed rollback that is tested in staging the week before. This lesson produces the simulator that lets the network engineering team rehearse the rollout against synthetic traffic and prove, before the maintenance window, that the SloGate correctly aborts at the 1.0% threshold and that the rollback restores 100% blue within 30 seconds.

## The Concept

A production cutover is not a single switch flip — it is a sequence of measured risk transfers, each gated by an objective signal. The lesson works through the five pieces that have to be right for a cutover to be safe.

### The change-management envelope

Every real cutover lives inside a change envelope. The envelope has a start time, an end time, a freeze list (deploys that are blocked during the window), a CAB approver, a primary on-call, a secondary on-call, a rollback owner, and a communication channel (Slack channel, conference bridge, status page). For a Tier-0 cutover the envelope is in ServiceNow as a NORMAL CHG record with `risk=high` and `impact=high`, requires CAB approval, and is published 7 days in advance. The runbook is attached to the CHG as a PDF. The simulator treats the envelope as the `Runbook` dataclass:

| Field | Production mapping | Why it matters |
|---|---|---|
| `change_id` | ServiceNow CHG number | Audit trail for postmortem and SOX evidence |
| `service` | Service catalog entry | Routes the alert to the right Slack and on-call rotation |
| `steps` | Canary weight schedule | The objective ramp that a reviewer can sign off on |
| `error_budget_pct` | SLO burn threshold | The line that, when crossed, halts the change |
| `window_s` | Sliding-window length | The shortest interval on which a burn is meaningful |
| `min_requests` | Warmup guard | Prevents the gate tripping on the first 30 requests during a pool warmup |

The runbook is the contract between the engineer, the CAB, and the on-call. If a step is not in the runbook, the engineer does not execute it without paging the on-call and getting verbal approval on the bridge. The simulator enforces this by walking the runbook in order and never skipping a step.

### The canary weight schedule

A canary schedule is a list of `(weight_percent, hold_seconds, ramp_kind)` tuples. The ramp kind is `canary` (continue to the next step), `promote` (declare victory, do not advance), or `abort` (cut the change short, do not advance). The standard schedule used in this lesson is 1% / 30s, 5% / 60s, 25% / 90s, 50% / 120s, 100% / 60s, which is the schedule that the platform team agreed on after the FreeBSD/Envoy postmortem. Each step has three decisions an on-call can make at the end of its hold:

| Decision | Condition | Next action |
|---|---|---|
| Promote | Windowed 5xx < 0.5% AND p95 within 10% of blue AND no health-check failures | Jump to 100% (or stay at 100% if already there) |
| Continue | Windowed 5xx < error_budget_pct AND no health-check failures | Advance to the next step |
| Hold | Windowed 5xx between 0.5% and error_budget_pct | Stay at the current weight for another hold_s |
| Abort | Windowed 5xx > error_budget_pct OR 3 failed /healthz checks | Roll back to 0% green, 100% blue |

The simulator implements the Continue and Abort paths. The Hold and Promote paths are operator-driven in production (the on-call announces the decision on the bridge), but the simulator auto-promotes at the final step if no abort has fired and auto-aborts the instant the SloGate trips.

### The SloGate sliding window

A 5xx burst is meaningful only if it spans a minimum interval and a minimum request count. The SloGate uses a 5-second sliding window with a 1.0% error budget and a 50-request minimum. Every response that is 5xx is recorded as `(timestamp, is_error)`. On every event, the gate prunes events older than `now - window_s`, then computes the error rate as `errors / n`. The gate trips when `n >= min_requests` AND `rate > error_budget_pct`. The min_requests guard is critical — without it, the very first 5xx in an empty window would trip the gate, and a 0.5-second warmup burst on a freshly-attached green instance would abort a healthy rollout.

| Signal | Value | Reason |
|---|---|---|
| `window_s` | 5.0 | Long enough to absorb single-instance restart blips, short enough to catch a real regression |
| `error_budget_pct` | 1.0 | SLO is 99.9% monthly; the cutover must not burn more than 1% over any 5-second slice |
| `min_requests` | 50 | At 200 RPS this is 250 ms of traffic; below this, a single client error dominates |
| `failure_threshold` (health) | 3 | At 1 check/sec this is 3 seconds; short enough to catch a hard failure, long enough to ride out a probe blip |

The SloGate is the auto-rollback mechanism. The simulator emits the gate's reason string (`ok rate=0.42% n=187`, `burned rate=2.31% n=215`) at every step boundary so the postmortem shows exactly when the budget was burned.

### Health checks and the connection-drain window

A /healthz probe is a separate signal from the SloGate. The probe hits `http://<green-instance>:<port>/healthz` once per second and tracks consecutive failures. Three failures in a row force an immediate abort, regardless of the SloGate. The reason is that a hard backend failure (process crash, OOM kill, full GC pause) may produce so few 5xx responses on the LB that the SloGate window never fills to 50 requests, but the /healthz probe will still detect the failure.

When the SloGate or the health check fires, the rollback has to drain in-flight connections before pulling traffic. A connection-drain window of 30 seconds is standard. During the drain, the green pool's weight is held at the current value and the LB stops sending new connections but allows existing connections to complete. After 30 seconds the weight is set to 0 and the blue pool takes 100%. The simulator compresses this into a single wall-clock step for clarity; the real drain is an LB-native feature (NGINX `proxy_pass` with `proxy_read_timeout` and the upstream's `drain` server directive).

### Fallback mechanisms and the rollback owner

The SloGate is the primary rollback, but the runbook always names a fallback. Three fallbacks are common:

1. **iptables drain** — at the LB host, an `iptables -I INPUT -s <green-instance> -j DROP` rule that immediately stops new connections without changing the LB config. The on-call executes this from a bastion over a serial console if the LB is unresponsive.
2. **BGP MED withdrawal** — at the upstream router, a `route-map` adjustment that sets the MED on the green pool's anycast prefix to 0 (un-preferred) and the blue pool to 100 (preferred). The traffic returns to blue in BGP convergence time, typically 30-60 seconds.
3. **DNS weight zero** — at the authoritative nameserver, set the green pool's A record's weight to 0 in the SRV-style health-check response. The clients that use DNS-based load balancing fall back to blue. This is the slowest fallback (TTL-bound) and is only used when the LB itself is unreachable.

The runbook names the rollback owner explicitly. In production this is the secondary on-call. The simulator does not implement the fallbacks (they are operator-driven shell scripts) but the validation matrix in the next section names them so the runbook review can sign off on each one.

### Validation matrix (what we check before the cutover)

| Check | Tool | Pass criterion | Owner |
|---|---|---|---|
| Synthetic 200 from green on /healthz | curl | 200 OK in <100 ms for 30 consecutive probes | Edge SRE |
| Windowed 5xx from green staging | Synthetic load generator (this lesson's simulator) | <0.5% over 5 s at production RPS | Edge SRE |
| p50/p95 latency from green | Synthetic load generator | p95 within 10% of blue | Edge SRE |
| BGP session up on green | `show ip bgp summary` (Nautobot inventory) | Established state for 24 h | Network ops |
| ECMP hash on upstream | `show ip route` (Cisco IOS-XE) | Both blue and green next-hops present | Network ops |
| Connection drain | LB test harness | New conns stop, in-flight conns complete in <30 s | Edge SRE |
| Rollback script rehearsed | Shell dry-run in staging | Returns blue to 100% in <30 s, no errors | On-call |
| iptables fallback tested | `iptables -L` on bastion | Rule applies in <1 s, removes cleanly | Network ops |
| BGP MED fallback tested | `route-map` change in staging | Traffic shifts back to blue in <60 s | Network ops |

The simulator implements the first three rows. The remaining rows are operator-driven and are documented in the runbook so a reviewer can verify they were tested in staging.

## Build It

The deliverable is `code/main.py` — a single stdlib-only Python module that builds a runbook, simulates synthetic traffic at 200 RPS, and walks the canary schedule with a SloGate and a /healthz probe. The simulator emits a JSON report and a human-readable summary.

Run it: `python3 code/main.py`. The output includes:

- The change ID and service name from the runbook.
- The final green weight, the abort/promote state, the wall-clock time of the state transition.
- A per-step timeline with request count, error count, the SloGate reason string, and the health-check status.
- The /healthz probe log showing every check and the consecutive-failure counter.
- A JSON document with the full state for archival.

The simulation is deterministic when seeded (`random.Random(20250625)` in `main()`). Identical seeds produce identical abort/promote decisions, so the rehearsal is reproducible across runs.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| `main.py` — Runbook dataclass | change_id, service, steps, error_budget_pct, window_s, min_requests | Generated |
| `main.py` — Weighted dispatcher | Routes each request to blue or green based on a percent weight | Generated |
| `main.py` — SloGate | Prunes events older than window_s, trips on rate > budget with min_requests guard | Generated |
| `main.py` — /healthz probe | 3 consecutive failures aborts regardless of SloGate | Generated |
| `main.py` — Cutover timeline | Per-step: weight, hold, requests, errors, SloGate reason, health status | Generated |
| `main.py` — JSON report | Full state serializable to JSON for archival | Generated |
| Runbook validation | Run with `random.Random(20250625)` produces a deterministic, reproducible output | Generated |
| Connection-drain guidance | Runbook section names the 30s drain window and the LB-level drain feature | Generated |
| Fallback list | Runbook section names iptables, BGP MED, DNS-weight fallbacks | Generated |

## Ship It

The artifact is the JSON line printed by `python3 code/main.py` plus the human-readable summary above it. The JSON is attached to the CHG record as evidence; the summary is the executive one-pager the SRE manager uses to sign the post-cutover review. To regenerate after a parameter change (different RPS, different canary schedule, different budget), edit the constants at the bottom of `main.py` and re-run.

The visual in `assets/production-cutover-and-rollback-rehearsal-with-traffic-simulation.svg` is the slide that goes into the CAB deck. It shows the canary ramp line, the SloGate boundary, and the rollback arrow returning traffic to blue.

## Exercises

1. **Default runbook rehearsal** — Run `main.py` as written. The simulator should auto-abort at the 5% green step when the green pool's error rate burns the 1.0% budget. Identify the exact step and the SloGate reason.

2. **Tune the green error rate** — Change `green.base_error_rate` from 0.015 to 0.005 (a healthier candidate) and re-run. Verify that the cutover now promotes to 100% green without aborting. Explain why.

3. **Stress the warmup guard** — Drop `min_requests` to 5 and re-run with the original 0.015 error rate. Predict whether the gate becomes more or less sensitive, and verify with a re-run.

4. **Shorter window** — Set `window_s` to 1.0 and re-run. The gate should now trip on smaller bursts. Identify the earliest step at which the gate trips under the 1-second window.

5. **Health check path** — Force the /healthz probe to fail three times in a row by setting `green.base_error_rate` high enough that `rng.random() > green.base_error_rate * 4` returns False for three consecutive checks. Verify that the abort path runs even if the SloGate is still under budget.

6. **Lower the RPS** — Drop `rps` from 200 to 20. The simulator still works (the math is parametric) but each hold window produces fewer requests. Verify that the runbook still completes within `sum(step.hold_s)` wall-clock seconds and that the SloGate is still meaningful.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Canary | "Ship it to 1% and see" | A measured weight step in a runbook with a defined hold time, a defined pass criterion, and a defined abort criterion. |
| Blue/Green | "Two prod environments" | Two equivalent pools (current and candidate) running in parallel, with traffic weighted between them by the LB. |
| SloGate | "The SLO checker" | A sliding-window error-rate gate with a defined window, a defined budget, and a min-requests warmup guard. |
| SLO budget | "We have 0.1% error budget" | The maximum allowed error rate over the window, expressed as a percentage; crossing it is an automatic abort. |
| Connection drain | "Wait for in-flight" | An LB feature that stops new connections to a pool while letting in-flight connections complete, typically 30 seconds. |
| CHG record | "A change ticket" | The ServiceNow artifact that documents the change envelope, the CAB approval, the runbook, and the post-change review. |
| CAB | "Change Advisory Board" | The cross-functional review group (network, security, SRE, product) that approves Tier-0 changes. |
| Rollback owner | "The person who rolls back" | A named human, typically the secondary on-call, who owns the abort decision and executes the fallback script. |
| BGP MED | "Set MED to 0" | A BGP path attribute that biases upstream route selection; setting the green pool's MED to 0 makes the blue pool preferred. |
| iptables drain | "Just block it" | A host-level firewall rule that drops new connections to a pool without changing the LB config; the fastest fallback when the LB is sick. |

## Further Reading

- Envoy, "HTTP JSON Outline, Weighted Clusters" — the canonical reference for the canary weight semantics used in the simulator.
- HAProxy, "Stick Tables and Weighted Round-Robin" — the alternative LB implementation and its weight knob (`weight` server directive).
- Brendan Gregg, "Site Reliability Engineering" (O'Reilly) — the chapter on change management and the four-step cutover protocol.
- Google SRE Book, "Canary Deployments" and "Release Engineering" — the design and risk analysis behind the canary schedule.
- ServiceNow, "Change Management Implementation" — the official CHG record lifecycle and the CAB approval process.
- NIST SP 800-61 Rev. 2, "Computer Security Incident Handling Guide" — the postmortem and root-cause analysis template referenced in the post-cutover review.
- Cisco IOS-XE, "BGP MED Path Attribute" command reference — the BGP fallback mechanism.
- Linux man page, `iptables(8)` — the host-level drain fallback.
- Datadog, "SLO Burn Rate Alerts" — the production observability tool used to monitor the SloGate in real time.
- Charity Majors, "Observability for Capital One" (SREcon talk) — the case for treating every cutover as a hypothesis test.
