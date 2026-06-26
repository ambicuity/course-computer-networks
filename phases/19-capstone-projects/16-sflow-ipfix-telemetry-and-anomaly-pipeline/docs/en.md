# sFlow IPFIX Telemetry and Anomaly Pipeline

> Build a network telemetry pipeline that collects sFlow/IPFIX flow records, aggregates them into time-series metrics, and detects traffic anomalies using statistical baselines and threshold alerts.

**Type:** Capstone
**Languages:** Python, shell, packet traces
**Prerequisites:** Phase 18 monitoring lessons; understanding of flow records, time-series data, and basic statistics
**Time:** ~150 minutes

## Learning Objectives

- Model sFlow and IPFIX flow record collection from network devices
- Aggregate flow records into time-series metrics (bytes/s, packets/s, flows/s per interface and per conversation)
- Implement statistical baseline computation: moving average and standard deviation for normal-traffic profiling
- Detect anomalies: sudden traffic spikes, flow count surges, unusual protocol distributions, and DDoS patterns
- Implement threshold-based alerting with severity levels (INFO, WARNING, CRITICAL)
- Produce a telemetry dashboard showing real-time metrics and anomaly alerts

## The Problem

Network telemetry is the lifeblood of operations. Without flow records, you cannot detect DDoS attacks, find bandwidth hogs, diagnose congestion, or capacity-plan. sFlow and IPFIX are the two dominant flow export protocols: sFlow samples 1-in-N packets (statistical), IPFIX exports every flow's summary (deterministic). Both produce massive volumes of flow records that must be collected, aggregated, and analyzed.

The challenge is turning raw flow records into actionable alerts. A single flow record says "10.0.0.5 sent 1.5 MB to 8.8.8.8 on port 53 at 14:32." That is useless by itself. But when you aggregate 10,000 flow records per minute into time-series metrics (bytes/s per interface, flows/s per conversation, protocol distribution), you can detect that interface traffic jumped 300% above baseline, or that DNS flows from a single source increased 1000x (a DNS amplification attack).

This capstone asks you to build a complete telemetry pipeline: generate synthetic sFlow/IPFIX records, collect and aggregate them, compute statistical baselines, detect anomalies, and produce alerts. You must demonstrate detection of four anomaly types: traffic spike, flow count surge, protocol distribution shift, and DDoS pattern.

## The Approach

The pipeline follows seven stages:

**Stage 1: Flow Record Generation.** Generate synthetic sFlow records using a 1-in-1000 sampling ratio: for every 1000 packets on the wire, one packet header is exported with its 5-tuple (src_ip, dst_ip, src_port, dst_port, proto) plus scaled byte and packet counts. Generate IPFIX records deterministically: every flow start and flow end triggers an export, giving exact byte and packet totals for each completed conversation without sampling loss.

**Stage 2: Collection and Normalization.** A collector process receives both sFlow datagrams and IPFIX messages and normalizes them into a common `FlowRecord` schema with fields: `src_ip`, `dst_ip`, `src_port`, `dst_port`, `proto`, `bytes`, `packets`, `start_time`, `end_time`, and `interface`. Normalizing at collection time means all downstream stages work on one data structure regardless of whether the source was sFlow or IPFIX.

**Stage 3: Time-Series Aggregation.** Bucket incoming `FlowRecord` objects into 60-second windows keyed by `(interface, window_start)`. For each bucket compute bytes/s, packets/s, and flows/s per interface, and build a top-N conversations list ranked by total bytes. These aggregated windows are the inputs to baseline computation and anomaly detection.

**Stage 4: Baseline Computation.** For each metric (bytes/s, packets/s, flows/s per interface), maintain a 7-day rolling window of 60-second samples aligned to the same hour of day and day of week — so Monday 14:00 baselines are compared only to prior Monday 14:00 windows, not to Sunday night traffic. Store each baseline as a `(mean, stddev)` pair keyed by `(interface, metric, hour_of_day, day_of_week)`.

**Stage 5: Anomaly Detection.** For each new 60-second window, compute the z-score for every metric: `z = (value - mean) / stddev`. Emit a WARNING alert when `|z| > 3` and a CRITICAL alert when `|z| > 5`. In addition, run a rate-of-change detector that flags any metric that increases more than 10x within a single 60-second window as a sudden spike regardless of the z-score — this catches zero-to-flood transitions that statistical baselines cannot see until several windows of history exist.

**Stage 6: DDoS Pattern Detection.** Apply three pattern detectors on each 60-second window. Volumetric: flag when bytes/s spikes above the WARNING threshold and more than 60% of destination bytes concentrate on a single `dst_ip`. Reflection: flag when traffic arrives from source ports 53 (DNS), 123 (NTP), or 19 (chargen) with an amplification factor (response bytes / request bytes) above 10. SYN flood: flag when the SYN packet count exceeds 10,000/s and the ACK-to-SYN ratio drops below 0.1 for the same destination. Each matched pattern emits a `DDoSAlert` with the pattern name, evidence, and affected interface.

**Stage 7: Dashboard Output.** Emit Prometheus-compatible metric lines (`# HELP`, `# TYPE`, and value lines) for bytes/s, packets/s, flows/s, z-scores, and DDoS pattern counters. Produce structured alert objects with fields: `severity`, `description`, `affected_interface`, `z_score`, `timestamp`. Output a top-10 talkers table per 60-second window showing src_ip, dst_ip, proto, bytes, and percentage of total interface traffic.

## Build It

1. **Define dataclasses.** Create the four core types:
   ```python
   @dataclass
   class FlowRecord:
       src_ip: str; dst_ip: str; src_port: int; dst_port: int
       proto: str; bytes: int; packets: int
       start_time: float; end_time: float; interface: str

   @dataclass
   class TimeSeriesMetric:
       interface: str; window_start: float
       bytes_per_sec: float; packets_per_sec: float; flows_per_sec: float
       top_talkers: list[tuple[str, str, int]]  # (src_ip, dst_ip, bytes)

   @dataclass
   class Anomaly:
       interface: str; metric: str; value: float
       mean: float; stddev: float; z_score: float
       severity: str; timestamp: float

   @dataclass
   class DDoSAlert:
       pattern: str; interface: str; evidence: dict
       severity: str; timestamp: float
   ```

2. **Generate sFlow records.** Simulate 5 routers each exporting at 1-in-1000 sampling ratio. At 10,000 flows/minute per router, the collector receives ~50 exported records/minute per router after sampling. Scale each sampled record's byte and packet counts by 1000 to reconstruct estimated wire volume.

3. **Generate IPFIX records.** For the same 5 routers, export one IPFIX record per completed flow (no sampling). At normal load this yields approximately 10,000 IPFIX records/minute per router. Inject anomaly events at t=35min (traffic spike), t=40min (flow count surge to 50,000 flows/min), t=45min (DNS share rises from 5% to 60%), and t=50min (single source sends 80% of total bytes).

4. **Normalize to FlowRecord.** Write an sFlow parser that extracts the 5-tuple and scales byte/packet counts by the sampling ratio. Write an IPFIX parser that reads the template-defined fields and maps them to `FlowRecord` fields. Feed both parsers into a shared queue.

5. **Aggregate into 60-second windows.** Group `FlowRecord` objects by `(interface, floor(start_time / 60))`. Sum bytes and packets, count flows, and build the top-10 talkers list. Emit a `TimeSeriesMetric` for each completed window.

6. **Compute baselines.** For each `(interface, metric, hour_of_day, day_of_week)` key, maintain a circular buffer of the last 7 days of same-slot values (168 samples for hourly slots, 10,080 for per-minute slots). Compute mean and stddev over the buffer. Require at least 30 samples before emitting z-scores to avoid false alarms during cold start.

7. **Detect anomalies.** For each new `TimeSeriesMetric`, compute z-scores for bytes_per_sec, packets_per_sec, and flows_per_sec. Apply thresholds: `|z| > 3` → WARNING, `|z| > 5` → CRITICAL. Apply rate-of-change check: if the current value exceeds 10x the previous window's value, emit a CRITICAL spike alert. Apply the three DDoS detectors (volumetric, reflection, SYN flood) and emit `DDoSAlert` objects on match.

8. **Output metrics and alerts.** Print Prometheus metric lines every 60 seconds. Print the top-10 talkers table. Print any `Anomaly` or `DDoSAlert` objects with severity, z_score, and a one-line description. Run the simulation for 60 minutes (3600 time steps of 1 second each, or 60 aggregated windows) and write all outputs to the `outputs/` directory.

## Use It

| Task | Metric | What Good Looks Like |
|---|---|---|
| Baseline accuracy | Mean absolute error between computed baseline and true synthetic mean | Error < 5% after 30 warm-up windows |
| Anomaly detection latency | Time from anomaly injection to first alert | Alert fires within one 60-second window of injection |
| False positive rate | Alerts fired during normal traffic (first 30 minutes) | Zero false positives at `|z| > 3` threshold |
| DDoS detection sensitivity | Fraction of injected DDoS events detected | All 3 patterns (volumetric, reflection, SYN flood) detected within one window |
| Top-talkers output | Rows in talkers table per window | Exactly 10 rows, sorted descending by bytes, with correct percentage |
| Prometheus output | Valid metric lines parseable by promtool | `promtool check metrics` exits 0 with no warnings |
| Alert JSON schema | Required fields present in every alert object | `severity`, `description`, `affected_interface`, `z_score`, `timestamp` all present |

## Ship It

- `code/collector.py` — sFlow and IPFIX record parser and normalization layer; accepts raw datagrams and emits `FlowRecord` objects
- `code/aggregator.py` — 60-second window aggregation and top-talkers computation; emits `TimeSeriesMetric` objects
- `code/anomaly_engine.py` — baseline computation, z-score anomaly detection, rate-of-change detector, and DDoS pattern matchers
- `code/prometheus_exporter.py` — Prometheus metric line formatter and HTTP `/metrics` endpoint stub
- `outputs/sample-alerts.json` — sample alert objects showing all four anomaly types with correct field schema
- `outputs/grafana-dashboard.json` — Grafana dashboard definition with panels for bytes/s, packets/s, flows/s, z-scores, and active alerts

## Exercises

1. **IPFIX variable-length Information Elements.** The IPFIX protocol supports variable-length fields (IE type 65535) where the length is encoded inline rather than in the template. Implement a parser that handles variable-length IEs correctly. What breaks in a fixed-length-only parser when it encounters a variable-length field mid-record?

2. **sFlow agent configuration on a real switch.** Configure sFlow on a physical or virtual switch (e.g., Open vSwitch with `ovs-vsctl set Bridge br0 sflow=@sf -- --id=@sf create sflow agent=eth0 target="collector:6343" sampling=1000 polling=30`). Capture the actual UDP datagrams with Wireshark and verify that your parser handles real sFlow v5 counter samples and flow samples correctly.

3. **ML-based anomaly detection.** Replace the z-score detector with an isolation forest (`sklearn.ensemble.IsolationForest`). Train it on the first 30 minutes of synthetic traffic, then score each subsequent window. Compare precision and recall against the z-score approach. Which method produces fewer false positives at the same recall level, and why?

4. **Flow stitching across export intervals.** A long-lived TCP session may span multiple IPFIX export intervals, producing partial flow records that must be stitched into a single logical flow. Implement a stitcher that matches records by 5-tuple and merges byte/packet counts across intervals. What timeout do you use to declare a flow complete when no FIN or RST is observed?

5. **Encrypted traffic classification.** With TLS 1.3, payload inspection is not possible. Implement a traffic classifier that uses flow metadata only: inter-packet arrival times, packet size distribution, flow duration, and byte-to-packet ratio. Use a simple decision tree to distinguish video streaming from bulk file transfer from interactive SSH. Evaluate on a labeled synthetic dataset.

6. **AS-path enrichment from BGP.** Enrich each `FlowRecord` with the originating AS number by doing a longest-prefix match against a BGP RIB snapshot (use a public RIB dump from routeviews.org). Add `src_asn` and `dst_asn` fields to the schema. Aggregate traffic by AS pair and identify the top-5 AS pairs by volume.

7. **GDPR compliance for IP flow data.** IP addresses are personal data under GDPR. Implement a pseudonymization scheme: replace each IP address with a consistent HMAC-SHA256 hash using a per-session key, so that traffic patterns are preserved for analysis but individual addresses cannot be recovered without the key. Verify that the top-talkers table and anomaly detection still function correctly on pseudonymized records.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| sFlow | Sampled flows | A statistical sampling protocol: exports 1-in-N packet headers, not every flow; scales counts by N to estimate wire volume |
| IPFIX | IP Flow Information Export | RFC 7011 successor to NetFlow v9; deterministic, template-based, exports a summary record for every completed flow |
| NetFlow | Cisco's original flow protocol | Cisco-proprietary predecessor to IPFIX; v5 is fixed-format, v9 introduced templates; largely superseded by IPFIX |
| Flow record | A traffic summary | A record containing src/dst IP, ports, protocol, bytes, packets, and timestamps for one conversation or one sampled packet |
| Sampling ratio | 1-in-N | The fraction of packets exported by sFlow; 1-in-1000 means one packet header per 1000 packets seen on the interface |
| Z-score | Standard deviations from mean | (value - mean) / stddev; measures how many standard deviations a current metric is from its historical baseline |
| Baseline | Normal traffic profile | The rolling mean and standard deviation of a metric computed over a sliding window of historical samples |
| Anomaly | Deviation from baseline | A metric value that exceeds the baseline by more than N standard deviations, indicating unusual traffic behavior |
| DDoS | Distributed Denial of Service | A volumetric attack where many sources flood a target; detected via byte/s spike combined with high destination concentration |
| Amplification factor | Bandwidth multiplier | The ratio of attack response bytes to attacker request bytes; DNS amplification can reach 50x, NTP monlist 556x |
| SYN flood | TCP handshake exhaustion | A flood of TCP SYN packets without completing handshakes, exhausting server connection tables; detected via low ACK/SYN ratio |
| Time-series aggregation | Bucketing flow records | Grouping raw flow records into fixed-width time windows and computing per-window statistics (bytes/s, flows/s, top talkers) |

## Further Reading

- RFC 3954 — Cisco Systems NetFlow Services Export Version 9: the template-based format that IPFIX standardized; useful for understanding the evolution from fixed v5 to flexible v9 templates
- RFC 7011 — Specification of the IP Flow Information Export (IPFIX) Protocol for the Exchange of Flow Information: the authoritative IETF standard; covers templates, options records, variable-length IEs, and transport
- RFC 3176 — InMon Corporation's sFlow: A Method for Monitoring Traffic in Switched and Routed Networks: defines sFlow v4/v5 datagram format, counter samples, flow samples, and the agent/collector model
- "Network Management: Accounting and Performance Strategies" by William Stallings — covers flow-based accounting, SNMP MIB design, and capacity planning from collected telemetry
- Elastic Stack (ELK) for network telemetry — Logstash sFlow/IPFIX input plugins, Elasticsearch time-series indices, and Kibana dashboards for flow visualization: https://www.elastic.co/guide/en/logstash/current/plugins-inputs-sflow.html
