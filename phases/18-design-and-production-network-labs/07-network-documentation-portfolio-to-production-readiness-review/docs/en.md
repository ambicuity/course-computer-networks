# Network Documentation Portfolio and Production Readiness Review

> A network documentation portfolio is the single source of truth that lets an on-call engineer, an auditor, and a new hire answer the question "what does this network look like right now, and how do we know it's safe to operate?" in under five minutes. A production-readiness review (PRR) is the structured exercise that walks through that portfolio and scores the network on redundancy, monitoring, backups, security, capacity, documentation, and procedures. This capstone ships a stdlib-only Python scorecard (`code/main.py`) that enumerates the 18 production-readiness checks, scores each 0-10 with PASS / WARN / FAIL, prints a remediation plan, and shows a 90-day trend. The deliverable is a JSON summary that the engineering lead can paste into the quarterly board deck alongside the rest of the network's reliability metrics.

**Type:** Project
**Languages:** Python (stdlib only), Markdown, draw.io / Visio
**Prerequisites:** Phase 17 (integrated troubleshooting), Phase 18 lessons 01-06 (campus, home, cloud, monitoring, address plan, IR kit)
**Time:** ~150 minutes

## Learning Objectives

- Identify the ten canonical directories in a network operations portfolio and the artifacts that belong in each.
- Score a network on the 18 production-readiness checks and explain what each check proves (and what it does not).
- Distinguish PASS, WARN, and FAIL statuses and assign remediation priority based on severity and ease of fix.
- Track readiness over time and present a 90-day trend that demonstrates improvement.
- Build a machine-readable JSON summary of the scorecard so it can be ingested by a dashboard or a CI/CD gate.
- Identify the checks that gate a "production" sign-off versus the checks that are nice-to-have for an "internal" sign-off.

## The Problem

You are the network engineering lead at NetCove Inc. The CEO has just told the board that the company's network is "production-ready," and the board has asked for evidence. The CTO has tasked you with producing a written scorecard in two weeks. The catch: the network has grown organically over six years, and no one person knows the whole thing. The on-call rotation has 14 people across three time zones, and they each have their own tribal knowledge. Some of the documentation lives in Confluence, some lives in a Google Drive folder owned by an engineer who left last quarter, and some lives in the heads of the two most senior SREs.

The deeper problem is that "production-ready" is a moving target. A network that was production-ready in 2020 may not be production-ready in 2024 because the threat landscape, the customer load, and the compliance requirements all changed. The scorecard must be reproducible — a different engineer should be able to re-run it next quarter and get the same (or better) numbers. That reproducibility requires that the artifacts the scorecard points to are version-controlled, that the evidence is timestamped, and that the scoring rubric is documented.

## The Concept

Source: this lesson is a synthesis of every prior Phase 18 lesson and the integrated troubleshooting discipline of Phase 17. The companion diagram is `assets/network-documentation-portfolio-to-production-readiness-review.svg`.

### The ten canonical portfolio directories

A network operations portfolio lives in a version-controlled monorepo (git is the de-facto choice). The top-level layout has ten canonical directories:

| Directory | Contents | Cadence |
|-----------|----------|---------|
| `inventory/`  | Hardware inventory (model, serial, location, EoL/EoSL date) | Updated on receipt / disposal |
| `topology/`   | L2 and L3 topology diagrams (draw.io / Visio source + exported PNG) | Updated on topology change |
| `ipam/`       | IP address management (subnet allocations, reservations, free-space) | Updated on assignment |
| `vlans/`      | VLAN database (ID, name, subnet, gateway, port assignments) | Updated on VLAN change |
| `configs/`    | Device configurations (backed up nightly to git) | Nightly |
| `runbooks/`   | Operational runbooks (outage, DDoS, breach, BPG flap, etc.) | Updated on incident |
| `policies/`   | Security policies (ACLs, firewall rules, QoS, BGP routing policy) | Updated on policy change |
| `procedures/` | Change management, incident response, onboarding | Updated on process change |
| `monitoring/` | Dashboard URLs, alert definitions, escalation paths, on-call schedule | Updated on schedule change |
| `vendor/`     | Support contracts, SLAs, contact information, escalation matrix | Updated on contract change |

The portfolio lives in git so every change is reviewable. The pull-request review is the natural place to enforce "no change to the network without a corresponding change to the documentation."

### The 18 production-readiness checks

The scorecard has 18 checks grouped into seven categories:

| Category | Checks | Maximum score |
|----------|--------|---------------|
| Redundancy | Core, Internet, Power (3) | 30 |
| Monitoring | Metrics, Alerts, Logs (3) | 30 |
| Backups | Config, Device image (2) | 20 |
| Security | Access control, Port security, Audit logs (3) | 30 |
| Capacity | Bandwidth, Growth (2) | 20 |
| Documentation | Topology, IPAM, Runbooks (3) | 30 |
| Procedures | Change mgmt, Incident response (2) | 20 |
| **Total** | **18** | **180** |

Each check is scored 0-10 with a status:

- **PASS (9-10)**: the evidence is current, automated, and tested. Example: "Nightly config backup to git, verified weekly by a smoke test that diffs against the live device."
- **WARN (5-8)**: the evidence exists but is not current, automated, or tested. Example: "Config backup to git but the last successful run is 6 days old; the cron is broken."
- **FAIL (0-4)**: the evidence does not exist or is not enforced. Example: "No runbook exists for the most common incident class."

A 90% overall score (162/180) is the typical "production-ready" bar. A 70% score (126/180) is "internal-only" and a 50% score (90/180) is "pilot, do not onboard paying customers."

### Remediation priority

Remediation priority is severity-first, then effort-first within a severity:

- **Priority 1 (FAIL)**: fix within 1 week. A FAIL on a production network is a board-level risk; the fix may be small (write a runbook, enable a cron) but the consequences of not fixing are large.
- **Priority 2 (WARN)**: fix within 1 month. A WARN means the system works today but will not survive the next failure. The fix is in flight but not yet completed.
- **Priority 3 (PASS)**: monitor. A PASS today is not a PASS forever; re-score quarterly.

The scorecard's remediation plan is the deliverable that the engineering lead sends to the CTO. It must have dates, owners, and acceptance criteria for each item.

### 90-day trend and machine-readable output

The scorecard is a snapshot; the trend is the story. A network that scored 62% in January and 82% in June tells a different story than one that scored 82% in January and 82% in June — even though the second number is the same. The trend line makes the improvement (or the stagnation) visible at a glance.

The scorecard also produces a JSON summary so the numbers can be ingested by the company dashboard (Grafana, Datadog, internal status page). The JSON has the date, the score, the grade, the list of FAIL items, and the list of WARN items — enough to feed a chart, an alert, or a CI/CD gate that refuses to deploy a network change when the score drops below 80%.

### What the scorecard does not do

The scorecard is a starting point, not a substitute for judgment. It does not catch configuration errors, it does not catch subtle security vulnerabilities, and it does not catch "the documentation is current but the network is wrong" (a frequent failure mode where the doc reflects the desired state rather than the actual state). The scorecard is most useful when paired with a quarterly chaos exercise (cut a link, kill a device, simulate a routing loop) and a quarterly security review (run a port scan, attempt a privilege escalation). The scorecard is the door; the chaos exercise and the security review are the windows.

## Build It

1. Read `code/main.py` and understand the data model: `Scorecard` (list of checks + date), `READINESS_CHECKS` (the 18 checks), `PORTFOLIO_DIRS` (the 10 canonical directories), `TREND` (90-day history).
2. Run `python3 main.py` and confirm the output walks through all five parts: portfolio layout, scorecard, remediation plan, trend, JSON summary.
3. Modify the scorecard by changing one PASS to a FAIL and one WARN to a PASS. Re-run and confirm the grade changes appropriately.
4. Add a new check to the `READINESS_CHECKS` list — for example, "Disaster Recovery - Off-site backups" with score 0 and status FAIL. Re-run and confirm the totals and grade reflect the new check.
5. Replace the `TREND` list with your own network's 90-day history (or a synthetic 90-day trajectory that ends at the current score). Re-run and confirm the ASCII bar chart updates.
6. Pipe the JSON summary to a file: `python3 main.py > output.txt` and check that the JSON block is syntactically valid (the block is inside the captured output).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Establish a baseline | First scorecard run with all checks at current state | Total score and grade; list of FAIL items is short and actionable |
| Track readiness | Quarterly scorecard runs, logged in `monitoring/scorecard-history/` | Trend line shows monotone improvement; no FAIL item ages more than one quarter |
| Drive a remediation plan | Scorecard's Priority 1 list sent to the CTO with owners and dates | All FAIL items are closed within 1 week; WARN items within 1 month |
| Feed a CI/CD gate | JSON summary ingested by the network change pipeline | Pipeline refuses to deploy a network change when the score drops below 80% |
| Onboard a new engineer | Portfolio repo plus scorecard in week 1 | New engineer answers 80% of "what is the network?" questions in week 1 using the portfolio |
| Pass an external audit | Portfolio + scorecard + 90-day trend in the audit binder | Auditor signs off because the artifacts are version-controlled, current, and reproducible |

## Ship It

Produce one artifact under `outputs/`:

- A self-contained network operations portfolio in git with the ten canonical directories populated, the 18-check scorecard, a `scorecard-history/` directory holding the last 12 quarterly runs, a `remediation-plan.md` with the current Priority 1 and Priority 2 items, and a `summary.json` snapshot suitable for the company dashboard.
- A 2-page "Network production-readiness report" PDF suitable for the board, with the scorecard, the trend, the remediation plan, and a one-paragraph executive summary.

Start from [`outputs/prompt-network-documentation-portfolio-to-production-readiness-review.md`](../outputs/prompt-network-documentation-portfolio-to-production-readiness-review.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Add a "Disaster Recovery - Off-site backups" check to the scorecard and update the totals. Decide whether the check belongs in a new category or in Backups, and justify the decision.
2. Implement a `Scorecard.from_json(path)` constructor that reads a JSON file written by the current `main()` and rebuilds a `Scorecard` object. Round-trip the JSON and confirm the score and grade are preserved.
3. Write a `Scorecard.diff(other)` method that returns the set of checks whose score changed by more than 2 points. Use it to compare this quarter's scorecard to last quarter's.
4. Build a Grafana dashboard that ingests the JSON summary and shows: current score, 90-day trend, count of FAIL items, count of WARN items, and a green/yellow/red status indicator.
5. Implement a CI gate in your network's change pipeline: refuse to merge a pull request that touches a config file if the scorecard's most recent run has a FAIL on "Backups - Config" or "Procedures - Change mgmt".
6. Run a quarterly chaos exercise (cut a link, kill a device) and update the scorecard to add a new check "Resilience - Chaos-tested" that grades the team's response. Discuss the trade-off between making chaos a checkbox and making it a culture.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Portfolio | "the docs repo" | A version-controlled monorepo of all network operations artifacts: inventory, topology, configs, runbooks, policies, procedures, monitoring, vendor |
| Scorecard | "the readiness report" | A structured exercise that scores the network on a fixed rubric (here: 18 checks across 7 categories) and produces a PASS/WARN/FAIL grade |
| Production-ready | "safe to onboard customers" | A network that scores 90% or higher on the scorecard, has zero FAIL items, and is re-scored quarterly |
| EoL / EoSL | "end of life / support" | Vendor-announced dates after which a device no longer receives security patches; must be tracked in `inventory/` |
| IPAM | "IP address management" | The discipline of tracking which subnets are assigned, which are free, and which are reserved; the source of truth for IP planning |
| Runbook | "the playbook" | A step-by-step procedure for handling a specific incident class; must be tested, not just written |
| Change management | "the approval process" | A documented process (PR + review + change window + rollback plan) for any network change; gated by `procedures/change-mgmt.md` |
| IR process | "incident response" | The cross-functional process for handling security or operational incidents; documented in `procedures/incident-response.md` |
| Chaos exercise | "breaking things on purpose" | A scheduled exercise where a real failure is injected (link cut, device killed) to test the runbooks and the on-call team's response |
| CI gate | "the merge blocker" | A check in the network change pipeline that refuses to merge a change if a precondition (here: scorecard above threshold) is not met |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 1 §1.5 — network design and reference models (the conceptual basis for "what is the network?").
- NIST SP 800-53 Rev. 5 — *Security and Privacy Controls for Information Systems and Organizations* — the canonical controls catalog that maps to the scorecard's Security category.
- AWS Well-Architected Framework — *Operational Excellence Pillar* — the cloud analog of the scorecard, with five design principles and a review process.
- Google SRE Book, Chapter 6 — *Monitoring Distributed Systems* — the four golden signals (latency, traffic, errors, saturation) that map to the Monitoring category.
- Limoncelli, T. (2017). *The Practice of Cloud System Administration*, Addison-Wesley — operational excellence for network and system administrators.
- Bourke, T. (2021). *Network Reliability and Resiliency*, O'Reilly — quantitative methods for measuring and improving network reliability.
- Allspaw, J. (2009). *Web Operations: Keeping the Data On Time*, O'Reilly — the on-call rotation, runbook discipline, and incident review that underpin the scorecard's Procedures category.
