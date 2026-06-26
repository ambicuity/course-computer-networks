#!/usr/bin/env python3
"""Monitoring and Alerting Runbook Generator (Production Lab 04).

Builds a Prometheus alert rules YAML, a Grafana dashboard JSON, an
Alertmanager routing config, an SLO compliance report, an on-call rotation,
and a runbook for the ten most common network incidents. Stdlib only.

Run:  python3 main.py
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from itertools import cycle


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class SLI:
    name: str
    slo_target_pct: float       # e.g. 99.9
    window_days: int = 30
    current_value_pct: float = 99.85   # observed over the window


@dataclass
class Incident:
    name: str
    severity: str               # critical / warning / info
    expr: str                   # PromQL
    for_: str = "2m"
    runbook: str = ""
    top_causes: tuple[str, ...] = ()
    quick_checks: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# The 10 canonical network incidents
# ---------------------------------------------------------------------------

INCIDENTS: list[Incident] = [
    Incident(
        name="InterfaceDown",
        severity="critical",
        expr='up{job="network_devices"} == 0',
        for_="2m",
        runbook="runbooks/interface-down.md",
        top_causes=(
            "Physical link failure (cable, SFP, port)",
            "Configuration mismatch (speed/duplex, MTU)",
            "Upstream switch port administratively down",
        ),
        quick_checks=(
            "show interfaces status | include err-disabled",
            "show interfaces counters errors",
            "show log | last 5m | include UPDOWN",
        ),
    ),
    Incident(
        name="BGPSessionDown",
        severity="critical",
        expr='bgp_session_state{state="established"} == 0',
        for_="3m",
        runbook="runbooks/bgp-session-down.md",
        top_causes=(
            "Interface to peer is down (see InterfaceDown)",
            "ACL blocking TCP 179",
            "MD5 / TCP-AO mismatch",
            "BGP hold-time expiry (peer overloaded)",
        ),
        quick_checks=(
            "show bgp summary",
            "show ip bgp neighbors <ip> received-routes",
            "show ip bgp neighbors <ip> | include Last reset",
        ),
    ),
    Incident(
        name="OSPFStuckInExStart",
        severity="critical",
        expr='ospf_neighbor_state{state=~"ExStart|Exchange"} > 0',
        for_="5m",
        runbook="runbooks/ospf-exstart.md",
        top_causes=(
            "MTU mismatch on the OSPF link",
            "Area type mismatch (stub vs transit)",
            "Duplicate router-id",
        ),
        quick_checks=(
            "show ip ospf interface <intf>",
            "show ip ospf neighbor detail",
            "show running-config interface <intf> | include mtu",
        ),
    ),
    Incident(
        name="PacketLossHigh",
        severity="critical",
        expr='(rate(ifInErrors[5m]) + rate(ifOutErrors[5m])) / rate(ifInOctets[5m]) > 0.001',
        for_="5m",
        runbook="runbooks/packet-loss.md",
        top_causes=(
            "Cabling / optics (CRC errors climbing)",
            "Duplex mismatch (late collisions)",
            "Buffer congestion (output drops)",
            "Hardware fault (TCAM, ASIC)",
        ),
        quick_checks=(
            "show interfaces counters errors",
            "show interfaces counters | include drops",
            "show hardware internal errors",
        ),
    ),
    Incident(
        name="DNSSlow",
        severity="warning",
        expr='histogram_quantile(0.99, dns_resolution_duration_seconds_bucket) > 0.1',
        for_="10m",
        runbook="runbooks/dns-slow.md",
        top_causes=(
            "Resolver upstream is slow",
            "DoT/DoH handshake failing",
            "Negative caching (NXDOMAIN flood)",
        ),
        quick_checks=(
            "dig +stats example.com @<resolver>",
            "systemd-resolve --status",
            "show dns forwarding statistics",
        ),
    ),
    Incident(
        name="CertExpiringSoon",
        severity="warning",
        expr='(cert_not_after - time()) / 86400 < 14',
        for_="1h",
        runbook="runbooks/cert-expiry.md",
        top_causes=(
            "ACME client not auto-renewing",
            "Manual cert process not started",
            "Vendor CA change required",
        ),
        quick_checks=(
            "openssl s_client -connect <host>:443 -servername <host> </dev/null",
            "acme.sh list",
            "certbot certificates",
        ),
    ),
    Incident(
        name="MTUBlackhole",
        severity="warning",
        expr='increase(ip_fragment_received_total[10m]) > 100',
        for_="10m",
        runbook="runbooks/mtu-blackhole.md",
        top_causes=(
            "IPsec tunnel ingress not clamping MSS",
            "Path MTU < interface MTU (PMTUD blocked)",
            "Jumbo frames on one side, standard on the other",
        ),
        quick_checks=(
            "show ip interface <intf> | include MTU",
            "tracepath <dst> 1500",
            "iptables -t mangle -L -nv",
        ),
    ),
    Incident(
        name="RouteFlap",
        severity="warning",
        expr='changes(routes_total[1h]) > 200',
        for_="15m",
        runbook="runbooks/route-flap.md",
        top_causes=(
            "Physical link flapping",
            "BGP session reset by upstream",
            "Redistribution between protocols creating oscillation",
        ),
        quick_checks=(
            "show ip route summary",
            "show bgp dampening",
            "show log | include flapping",
        ),
    ),
    Incident(
        name="BGPSessionReset",
        severity="critical",
        expr='increase(bgp_session_reset_total[5m]) > 0',
        for_="0m",
        runbook="runbooks/bgp-reset.md",
        top_causes=(
            "Hold-time expiry (peer not sending keepalives)",
            "BGP Notification: AS path too long, attribute error",
            "Out-of-memory on peer",
        ),
        quick_checks=(
            "show ip bgp neighbors | include last reset",
            "show log | include BGP",
            "show ip bgp neighbors <ip> errors",
        ),
    ),
    Incident(
        name="InterfaceCongested",
        severity="warning",
        expr='rate(ifInOctets[5m]) * 8 / ifSpeed > 0.85',
        for_="15m",
        runbook="runbooks/interface-congested.md",
        top_causes=(
            "Bursty traffic from a single host",
            "Misplaced backup window on production link",
            "DDoS / scan",
        ),
        quick_checks=(
            "show interfaces counters | sort utilization desc",
            "show flow monitor cache | sort packets desc",
            "show netflow top talkers",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Prometheus alert rules
# ---------------------------------------------------------------------------

def emit_prometheus_rules() -> str:
    lines = ["groups:", "  - name: network-incidents", "    rules:"]
    for i in INCIDENTS:
        lines.append(f"      - alert: {i.name}")
        lines.append(f"        expr: {i.expr}")
        lines.append(f"        for: {i.for_}")
        lines.append(f"        labels:")
        lines.append(f"          severity: {i.severity}")
        lines.append(f"          team: network")
        lines.append(f"        annotations:")
        lines.append(f"          summary: \"{i.name} detected\"")
        lines.append(f"          runbook_url: \"https://wiki/{i.runbook}\"")
        lines.append(f"          top_causes: \"{'; '.join(i.top_causes)}\"")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Grafana dashboard JSON
# ---------------------------------------------------------------------------

def emit_grafana_dashboard() -> dict:
    panels = [
        {
            "id": 1,
            "title": "Is the network broken? — global reachability heatmap",
            "type": "heatmap",
            "gridPos": {"x": 0, "y": 0, "w": 24, "h": 6},
            "targets": [{
                "expr": 'avg_over_time(probe_success{job="network_global"}[1m])',
                "legendFormat": "{{region}}",
            }],
        },
        {
            "id": 2,
            "title": "Where? — per-device up/down",
            "type": "stat",
            "gridPos": {"x": 0, "y": 6, "w": 8, "h": 4},
            "targets": [{
                "expr": 'count(up{job="network_devices"} == 0) / count(up{job="network_devices"})',
            }],
        },
        {
            "id": 3,
            "title": "BGP sessions established",
            "type": "stat",
            "gridPos": {"x": 8, "y": 6, "w": 8, "h": 4},
            "targets": [{
                "expr": 'count(bgp_session_state{state="established"})',
            }],
        },
        {
            "id": 4,
            "title": "OSPF neighbors up",
            "type": "stat",
            "gridPos": {"x": 16, "y": 6, "w": 8, "h": 4},
            "targets": [{
                "expr": 'count(ospf_neighbor_state{state="full"})',
            }],
        },
        {
            "id": 5,
            "title": "Why? — interface utilization heatmap",
            "type": "heatmap",
            "gridPos": {"x": 0, "y": 10, "w": 12, "h": 8},
            "targets": [{
                "expr": 'rate(ifInOctets[5m]) * 8 / ifSpeed',
                "legendFormat": "{{instance}} {{ifName}}",
            }],
        },
        {
            "id": 6,
            "title": "DNS p99 resolution latency",
            "type": "timeseries",
            "gridPos": {"x": 12, "y": 10, "w": 12, "h": 8},
            "targets": [{
                "expr": 'histogram_quantile(0.99, dns_resolution_duration_seconds_bucket)',
                "legendFormat": "p99",
            }],
        },
        {
            "id": 7,
            "title": "Detail — top talkers (NetFlow)",
            "type": "table",
            "gridPos": {"x": 0, "y": 18, "w": 12, "h": 8},
            "targets": [{
                "expr": 'topk(10, sum by (src_ip) (rate(netflow_bytes[5m])))',
            }],
        },
        {
            "id": 8,
            "title": "Detail — error budget remaining",
            "type": "gauge",
            "gridPos": {"x": 12, "y": 18, "w": 12, "h": 8},
            "targets": [{
                "expr": 'slo_budget_remaining{slo="packet_delivery"}',
            }],
        },
    ]
    return {
        "title": "Network Operations",
        "uid": "network-ops",
        "schemaVersion": 38,
        "timezone": "browser",
        "panels": panels,
    }


# ---------------------------------------------------------------------------
# Alertmanager routing
# ---------------------------------------------------------------------------

def emit_alertmanager_routing() -> str:
    return textwrap.dedent("""\
        route:
          group_by: ['alertname', 'instance']
          group_wait: 30s
          group_interval: 5m
          repeat_interval: 4h
          receiver: 'slack-default'
          routes:
            - match:
                severity: critical
              receiver: 'pagerduty-network'
              group_wait: 10s
              repeat_interval: 1h
              continue: true
            - match:
                severity: warning
              receiver: 'slack-network'
              group_wait: 5m
              repeat_interval: 24h
        receivers:
          - name: 'pagerduty-network'
            pagerduty_configs:
              - service_key: '<PAGERDUTY_SERVICE_KEY>'
                description: '{{ .CommonAnnotations.summary }}'
          - name: 'slack-network'
            slack_configs:
              - api_url: '<SLACK_WEBHOOK>'
                channel: '#net-ops'
                title: '{{ .CommonLabels.alertname }} on {{ .CommonLabels.instance }}'
          - name: 'slack-default'
            slack_configs:
              - api_url: '<SLACK_WEBHOOK>'
                channel: '#net-info'
        """)


# ---------------------------------------------------------------------------
# SLO report
# ---------------------------------------------------------------------------

def slo_report(slis: list[SLI]) -> str:
    lines = ["# SLO Compliance Report (last 30 days)", ""]
    for s in slis:
        budget_pct = 100.0 - s.slo_target_pct
        consumed_pct = max(0.0, s.slo_target_pct - s.current_value_pct)
        burn = consumed_pct / budget_pct if budget_pct else 0
        status = "GREEN" if burn < 0.5 else "AMBER" if burn < 0.9 else "RED"
        lines.append(f"## {s.name}")
        lines.append(f"- SLO target: {s.slo_target_pct}%")
        lines.append(f"- Current:    {s.current_value_pct}%")
        lines.append(f"- Budget:     {budget_pct:.3f}%")
        lines.append(f"- Consumed:   {consumed_pct:.3f}% (burn {burn*100:.1f}%)")
        lines.append(f"- Status:     {status}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# On-call rotation (follow-the-sun)
# ---------------------------------------------------------------------------

def oncall_rotation(shifts: list[str], weeks: int = 4) -> dict:
    start = datetime(2026, 1, 5)  # Monday
    sched = []
    cycle = cycle(shifts)
    for w in range(weeks):
        primary = next(cycle)
        secondary = next(cycle)
        sched.append({
            "week": w + 1,
            "starts": (start + timedelta(weeks=w)).date().isoformat(),
            "primary": primary,
            "secondary": secondary,
            "manager": "manager-on-call",
        })
    return {"rotation": sched}


# ---------------------------------------------------------------------------
# Runbooks
# ---------------------------------------------------------------------------

def emit_runbook(incident: Incident) -> str:
    return textwrap.dedent(f"""\
        # Runbook: {incident.name}

        **Severity**: {incident.severity}
        **Alert**:    `{incident.expr}`
        **Hold for**: {incident.for_}

        ## 1. Detection
        Prometheus rule `{incident.name}` fired. Check Alertmanager for the
        first-fire timestamp and the affected instance.

        ## 2. Blast radius
        Identify the affected device(s) and the user-facing SLIs impacted.

        ## 3. Quick checks (60 seconds)
        ```
        {'\n        '.join(incident.quick_checks)}
        ```

        ## 4. Top causes (probability-ordered)
        1. {incident.top_causes[0] if len(incident.top_causes) > 0 else 'unknown'}
        2. {incident.top_causes[1] if len(incident.top_causes) > 1 else 'unknown'}
        3. {incident.top_causes[2] if len(incident.top_causes) > 2 else 'unknown'}

        ## 5. Mitigation
        Apply the smallest change that restores the SLI. Prefer rolling
        changes over hard cutovers; verify with the same `show` command
        used in step 3.

        ## 6. Escalation
        - Primary not ack in 5 min → secondary
        - Both not ack in 15 min → manager
        - Routing-protocol alert → routing SME
        - Security alert → security SME

        ## 7. Postmortem TODOs
        - [ ] Timeline (first fire → ack → mitigation → recovery)
        - [ ] Customer impact (SLI consumption, support tickets)
        - [ ] Root cause (with packet / log evidence)
        - [ ] Action items with owners and dates
        - [ ] Lessons learned
        """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("Monitoring and Alerting Runbook Generator")
    print("=" * 72)
    print(f"\n  {len(INCIDENTS)} canonical incidents defined")
    print(f"  Incidents: {', '.join(i.name for i in INCIDENTS)}")

    # Prometheus rules (first 30 lines)
    print("\n--- Prometheus alert rules (first 30 lines) ---")
    for line in emit_prometheus_rules().splitlines()[:30]:
        print(line)

    # Grafana dashboard
    dash = emit_grafana_dashboard()
    print(f"\n  Grafana dashboard: {dash['title']} ({len(dash['panels'])} panels)")

    # Alertmanager
    print("\n--- Alertmanager routing ---")
    print(emit_alertmanager_routing())

    # SLO report
    slis = [
        SLI("packet_delivery", 99.9, current_value_pct=99.85),
        SLI("dns_resolution", 99.5, current_value_pct=99.7),
        SLI("reachability", 99.95, current_value_pct=99.99),
    ]
    print("\n--- SLO compliance ---")
    print(slo_report(slis))

    # On-call rotation
    rot = oncall_rotation(["alice", "bob", "carol", "dave"], weeks=4)
    print(f"\n--- On-call rotation ({len(rot['rotation'])} weeks) ---")
    print(json.dumps(rot, indent=2))

    # First runbook
    print("\n--- Sample runbook ---")
    print(emit_runbook(INCIDENTS[0]))

    # Final: Grafana JSON to stdout
    print("\n--- Grafana dashboard JSON (truncated) ---")
    print(json.dumps(dash, indent=2)[:800] + "...")


if __name__ == "__main__":
    main()