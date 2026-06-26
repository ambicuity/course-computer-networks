# Monitoring and Alerting Runbook

> A network without monitoring is a network without a story — every outage looks the same and every postmortem starts from "we don't know." The lesson builds a production monitoring + alerting stack out of the four pillars that compose every modern network observability system: **metrics** (numeric time series), **logs** (structured or unstructured events), **traces** (request-level causal chains), and **alerts** (the human-facing consequence of metric thresholds). It combines the **SNMPv3** standard (RFC 3411-3418) for legacy gear, **Streaming Telemetry** with **gNMI / OpenConfig** (Google, Arista, Cisco, Juniper) for modern gear, the **Prometheus exposition format** and **Grafana** dashboards, and the **Google SRE Workbook**'s SLO model (SLI / SLO / error budget / burn rate). The deliverable is a runnable Python toolkit that ingests a router / switch / firewall inventory, emits Prometheus alert rules, a Grafana dashboard JSON, an on-call rotation, an SLO compliance report, and a **runbook** for the ten most common network incidents (link down, BGP neighbor down, OSPF stuck-in-EXSTART, packet loss above 1%, DNS resolution above 100 ms, certificate expiry, MTU blackhole, route flap, BGP session reset, and full interface congestion). The artifact is the difference between "we noticed at 3 AM" and "we knew 30 minutes before the user did."

**Type:** Project
**Languages:** Python (stdlib: dataclasses, json, statistics, math, hashlib, datetime, itertools)
**Prerequisites:** Phase 11 (TCP, UDP, congestion), Phase 12 (DNS, HTTP), Phase 17 (Integrated Troubleshooting Labs), Phase 13 (Streaming media + CDN — for the tracing examples)
**Time:** ~180 minutes

## Learning Objectives

- Inventory a network of 50 to 5,000 devices and choose the right collection mechanism per device class (SNMPv3 vs gNMI Streaming Telemetry vs Syslog vs IPFIX / NetFlow).
- Define **SLIs** (Service Level Indicators), **SLOs** (Service Level Objectives), and **error budgets** for the three critical user journeys: packet delivery, DNS resolution, and reachability.
- Compute **multi-window multi-burn-rate alert thresholds** per the Google SRE Workbook (e.g., 2% budget in 1 hour ⇒ page; 5% budget in 6 hours ⇒ ticket).
- Generate **Prometheus alerting rules** YAML, **Grafana dashboard JSON**, and **Alertmanager routing** with deduplication, grouping, and silence windows.
- Write a **runbook** for the ten most common incidents, each with detection, triage commands, mitigation, escalation, and postmortem template.
- Build an **on-call rotation** with primary, secondary, and manager escalation, plus a "follow-the-sun" handoff template for global teams.

## The Problem

A 600-person SaaS company runs a global network across three regions (us-east, eu-west, ap-southeast), two clouds (AWS, GCP), and 14 datacenters and points-of-presence. The network team is three engineers plus a manager. The current monitoring stack is **PRTG** (legacy, SNMP-only, polling every 60 seconds, $0.30 per sensor), Grafana for dashboards, and PagerDuty for paging. Pain points: (1) PRTG is missing **30%** of the interfaces because the SNMP community strings were never reconciled after the cloud migration; (2) the alert rules fire on thresholds like "interface utilization > 80%" without distinguishing between a 1 Gbps interface at 80% (acceptable) and a 100 Gbps interface at 80% (problem); (3) every incident has the same runbook — "look at PRTG, look at Grafana, look at the device, escalate" — with no concrete commands; (4) the on-call engineer gets **paged 40 times per week** for issues that resolve themselves; (5) the postmortem template is 8 sections but the team skips 5 of them every time.

The lesson is to design a single monitoring + alerting plan that fixes all five pain points and produces a runbook that is actually usable at 3 AM.

## The Concept

A monitoring stack is the same shape as the network it watches: layers. The **collection layer** gathers data from devices, the **storage layer** persists it, the **analysis layer** computes SLIs and thresholds, the **alerting layer** pages the right person, and the **response layer** runs the runbook. Each layer has its own standards, vendors, and failure modes.

### The four telemetry types

| Type | What it is | Standards | Vendors |
|---|---|---|---|
| Metrics | Numeric time series (counter or gauge) | SNMP (RFC 3411-3418), gNMI / OpenConfig / YANG, Prometheus exposition | PRTG, LibreNMS, Telegraf, Prometheus exporters |
| Logs | Structured or unstructured events | Syslog (RFC 5424), journald, Windows Event Log | rsyslog, syslog-ng, Splunk, Loki |
| Traces | Request-level causal chains | OpenTelemetry (W3C Trace Context, formerly Zipkin), eBPF | Jaeger, Tempo, Honeycomb |
| Flows | Per-flow records (5-tuple, counters) | IPFIX (RFC 7011), NetFlow v5/v9, sFlow (RFC 3176) | nfdump, pmacct, Kentik, Vectis |

The lesson focuses on **metrics** (the bulk of network monitoring) plus a sketch of **logs** and **flows**. Tracing is less mature for networks but is increasingly used for application-layer issues (HTTP latency, DNS resolution chains).

### SNMPv3 vs Streaming Telemetry

**SNMPv3** (RFC 3411-3418) is the legacy poll-based protocol. The manager polls an agent every N seconds (typically 30-60s), the agent returns the value of one or more OIDs. SNMPv3 adds authentication (HMAC-SHA) and privacy (AES-128/192/256) on top of the SNMPv1/v2c plaintext communities. It works on every device in production today. The downsides are: (1) **polling is slow** — 60 seconds is the floor for thousands of devices; (2) **traps** (the push equivalent) are unreliable; (3) **scalar counters** lose the per-interface detail needed for modern SLOs.

**Streaming Telemetry** (gNMI / OpenConfig) is the modern push-based equivalent. The device subscribes to a YANG-modeled data tree and pushes updates as soon as the value changes, typically **sub-second**. The standards are **gNMI** (gRPC Network Management Interface, OpenConfig), **gRPC** (Google's HTTP/2 + Protobuf RPC), **YANG** (RFC 7950, the data modeling language), and **OpenConfig** (a vendor-neutral YANG model for interfaces, BGP, OSPF, IS-IS, etc.). Modern Arista, Cisco IOS-XR, Cisco NX-OS, and Juniper Junos devices all support gNMI.

The lesson's collection-layer decision matrix:

| Device class | Collection | Why |
|---|---|---|
| Legacy access switches (< 2018) | SNMPv3 polling @ 30s | No streaming support |
| Modern campus/distribution (Arista, Cisco Cat9k, Junos) | gNMI streaming @ 1s + SNMP fallback | Sub-second visibility |
| Service provider edge (Juniper MX, Cisco ASR9k, Nokia SR) | gNMI streaming @ 1s + IPFIX for flow | Carrier-grade |
| Firewalls (Palo Alto, Fortinet, Check Point) | Syslog (RFC 5424) + SNMP polling + vendor API | Vendor-specific best path |
| Servers / Kubernetes | Prometheus node-exporter + cAdvisor | Application-level |
| Cloud (AWS CloudWatch, GCP Cloud Monitoring) | Vendor-native metrics | Vendor-managed |

### Prometheus exposition and Alertmanager

**Prometheus** is the de-facto open-source metrics stack. Each device or application exposes a `/metrics` HTTP endpoint in **Prometheus exposition format** (text-based: `metric_name{label="value"} <number> <timestamp>`). Prometheus scrapes these endpoints every 15s by default, stores them in a time-series database, and evaluates **PromQL** rules against them. **Alertmanager** deduplicates, groups, and routes alerts to **PagerDuty**, **Opsgenie**, **Slack**, or email.

The lesson's planner emits Prometheus alert rules in YAML for the ten most common network incidents. Example:

```yaml
groups:
- name: network
  rules:
  - alert: InterfaceDown
    expr: up{job="network_devices", instance=~".*"} == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Device {{ $labels.instance }} unreachable"
      runbook_url: "https://wiki/runbooks/interface-down"
```

### SLIs, SLOs, and error budgets

The **Google SRE Workbook** formalized three concepts:

- **SLI** (Service Level Indicator) — a measured quantity. For the network: **packet delivery rate** (received / sent), **DNS resolution p99 latency** (ms), **reachability** (1 if probe succeeds, 0 if not).
- **SLO** (Service Level Objective) — a target on the SLI. "DNS resolution p99 < 100 ms over 30 days." "Reachability > 99.9% over 30 days."
- **Error budget** — 100% - SLO. For 99.9% reachability, the budget is 0.1%, or 43.2 minutes per 30 days.

The lesson's planner computes the budget consumption over the last 30 days and emits an SLO report.

### Multi-window multi-burn-rate alerts

A single threshold ("alert when p99 latency > 100 ms") generates too many alerts. The **Google SRE Workbook** Chapter 5 recommends **multi-window, multi-burn-rate** alerts:

- **Page** when 2% of the 30-day budget is consumed in 1 hour (fast burn ⇒ major incident).
- **Ticket** when 5% of the 30-day budget is consumed in 6 hours (slow burn ⇒ developing issue).
- **No alert** for slow burns that consume < 0.1% of budget per day (normal noise).

The lesson's planner computes the multi-window thresholds for each SLO and emits the corresponding Prometheus rules.

### Grafana dashboards

A **dashboard** is a set of **panels** rendered on a shared time axis. Each panel has a query (PromQL), a visualization type (time series, bar, table, heatmap, gauge), and a threshold. Good dashboards are **story-driven** — the top panel answers "is it broken?", the second answers "where?", the third answers "why?", and the rest provide detail.

The lesson's planner emits a Grafana dashboard JSON with panels for: (1) global reachability heatmap; (2) per-device interface utilization heatmap; (3) BGP neighbor state table; (4) DNS resolution latency histogram; (5) top-N talkers (from IPFIX); (6) error budget remaining.

### On-call and escalation

A well-designed on-call has:

- **Primary** (first responder, 7 days).
- **Secondary** (backup if primary doesn't ack in 5 minutes).
- **Manager** (escalation if both don't ack in 15 minutes).
- **Subject-matter expert** (specific incidents: BGP expert for BGP flap, routing expert for OSPF, security for DDoS).

The lesson's planner emits a PagerDuty schedule JSON with a **follow-the-sun** rotation for global teams: Americas primary, EMEA primary, APAC primary.

### Runbook structure

A runbook that gets used at 3 AM has a single-page structure:

1. **Alert** — what fired, what threshold, what SLI is affected.
2. **Blast radius** — how many users / services affected.
3. **Quick checks** — 5 commands to run in the first 60 seconds.
4. **Common causes** — top 3, ordered by probability.
5. **Mitigation** — concrete commands (no "investigate further").
6. **Escalation** — who, when, how.
7. **Postmortem template** — link to the postmortem doc with TODOs pre-filled.

The lesson's planner emits runbooks in this format for the ten most common incidents.

## Build It

The deliverable is `code/main.py`, a stdlib-only monitoring + alerting toolkit. Inputs are the device inventory, the SLI / SLO definitions, and the on-call schedule. Outputs are:

- **Prometheus alert rules** YAML for the ten most common incidents.
- **Grafana dashboard** JSON with 6 panels.
- **Alertmanager routing** with severity labels and PagerDuty / Slack destinations.
- **SLO compliance report** over the last 30 days.
- **On-call rotation** JSON for PagerDuty.
- **Runbook** Markdown for each of the ten incidents.

Run it: `python3 main.py`. The output is a deterministic monitoring plan ready to commit to the network's git repo.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| Prometheus rules | 10 incidents, multi-window burn rate, runbook URL embedded | Generated |
| Grafana dashboard | 6 panels, story-driven (top-to-bottom: what/where/why/detail) | Generated |
| Alertmanager routing | Severity groups, dedup, 5-min grouping, Slack + PagerDuty | Generated |
| SLO report | 30-day window, per-SLI budget consumption, RAG status | Generated |
| On-call rotation | Primary/secondary/manager escalation, follow-the-sun handoff | Generated |
| Runbooks | 10 incidents, each with detection / triage / mitigation / escalation | Generated |
| Collection matrix | SNMPv3 vs gNMI vs Syslog per device class | Generated |

## Ship It

The artifact is `outputs/prometheus-alerts.yaml`, `outputs/grafana-dashboard.json`, `outputs/alertmanager-routing.yaml`, `outputs/slo-report.md`, `outputs/oncall-rotation.json`, and `outputs/runbooks/`. The YAML and JSON are deployment-ready; the runbooks are pasted into the wiki.

To regenerate after a SLO or threshold change: edit the SLI definitions in `code/main.py`, re-run, diff the outputs.

## Exercises

1. **SNMPv3 vs gNMI math**: a 1,000-device network is polled by SNMPv3 every 60 seconds. Each poll retrieves 50 OIDs. Estimate the daily SNMP traffic. If the same network streams telemetry every 1 second (only on change, average 10% of OIDs), what is the daily traffic? Which scales better, and why?
2. **Burn-rate alert**: an SLO is "packet delivery > 99.9% over 30 days" (43.2-minute budget). Compute the **page threshold** (2% budget in 1 hour): how many minutes of packet loss must be observed in a 1-hour window to page? The **ticket threshold** (5% budget in 6 hours): how many minutes in 6 hours?
3. **BGP runbook**: write the runbook for "BGP neighbor down on session X." Include: detection (which alert), blast radius (which prefixes affected), quick checks (`show bgp summary`, `show ip bgp neighbors x received-routes`), common causes (interface down, ACL, MD5 mismatch, hold-time expiry), mitigation (specific commands), escalation (routing expert), and postmortem TODOs.
4. **On-call handoff**: a global team has engineers in San Francisco (PST), London (GMT), and Singapore (SGT). Design a 24×7 follow-the-sun rotation with 1-week shifts. Show the primary / secondary / manager escalation per shift, and the daily handoff time (in UTC) that minimizes pain for both shifts.
5. **SLI definition**: for an enterprise LAN, define five SLIs that are measurable from existing infrastructure (no new probes required). For each, propose the data source (SNMP OID, gNMI path, syslog pattern, IPFIX record). Estimate the storage cost at 15-second resolution over 30 days.
6. **Dashboard storyboarding**: design a Grafana dashboard for the network operations team. Top-to-bottom: (1) one panel answering "is the network broken?" (2) three panels answering "where?" (3) three panels answering "why?" (4) three panels of detail. Sketch each panel's query, visualization, and threshold.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SNMPv3 | "Old polling" | RFC 3411-3418 — authenticated and encrypted polling for legacy network gear |
| Streaming Telemetry | "Modern push" | gNMI / OpenConfig / YANG — sub-second push of YANG-modeled data from modern gear |
| Prometheus | "Metrics DB" | Open-source time-series database with PromQL query language and Alertmanager |
| SLI / SLO / Error Budget | "Reliability targets" | Service Level Indicator / Objective / the allowed downtime = 100% - SLO |
| Burn rate | "How fast are we failing" | Rate of error budget consumption; multi-window burn rate is the Google SRE recommendation |
| Runbook | "What to do" | Step-by-step playbook for a specific alert / incident |
| On-call rotation | "Who pages" | The schedule of primary / secondary / manager escalation for paging |
| IPFIX / NetFlow | "Flow records" | RFC 7011 — per-flow 5-tuple records exported from routers / switches |
| OpenConfig | "Vendor-neutral YANG" | The vendor-neutral YANG data models for interfaces, BGP, OSPF, IS-IS |
| Alertmanager | "Pager router" | Prometheus's alert deduplication, grouping, and routing to PagerDuty / Slack |
| Grafana | "Dashboard tool" | Visualization tool for Prometheus, Loki, Elasticsearch, CloudWatch, etc. |
| gNMI | "gRPC for networks" | Google + OpenConfig's gRPC-based streaming telemetry protocol |

## Further Reading

- **Google SRE Book** (free online: sre.google/sre-book) and **Google SRE Workbook** (free online: sre.google/workbook) — the SLI / SLO / error budget and multi-window burn-rate chapters.
- **RFC 3411-3418** — SNMPv3 standard.
- **RFC 5424** — Syslog protocol.
- **RFC 7011** — IPFIX.
- **RFC 7950** — YANG 1.1 data modeling language.
- **gNMI specification** (github.com/openconfig/reference) — the gNMI proto and gRPC binding.
- **Prometheus documentation** (prometheus.io/docs) — the alerting guide.
- **Grafana documentation** (grafana.com/docs) — dashboard best practices.
- *Network Monitoring and Management* (various vendors) — vendor-specific guides for Cisco, Juniper, Arista, Palo Alto.
- *Cloud Native Data Center Networking* (Dinesh G. Dutt, O'Reilly 2019) — modern telemetry-driven network operations.
- *Web Operations* (Allspaw & Robbins, O'Reilly 2010) — the cultural side of on-call.