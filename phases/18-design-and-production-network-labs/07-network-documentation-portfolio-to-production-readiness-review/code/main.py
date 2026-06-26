#!/usr/bin/env python3
"""Network Documentation Portfolio + Production Readiness Review (Lab 07).

Generates the documentation portfolio structure for a network operations
team and walks through a production-readiness scorecard. The scorecard
covers redundancy, monitoring, backups, security, capacity, documentation,
and procedures. Each check is scored 0-10 with PASS / WARN / FAIL.

Run:  python3 main.py

The output has four parts:
  1. The portfolio directory layout the team should keep in version control.
  2. A scorecard with the 18 production-readiness checks and their status.
  3. A remediation plan that prioritizes the FAIL items first.
  4. A rolling 90-day trend that shows how readiness has improved.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass


READINESS_CHECKS: list[tuple[str, str, int, str]] = [
    ("Redundancy - Core",       "Dual core switches with HSRP/VRRP",          10, "PASS"),
    ("Redundancy - Internet",   "Dual ISP with BGP failover",                 10, "PASS"),
    ("Redundancy - Power",      "UPS + generator on all critical gear",      10, "PASS"),
    ("Monitoring - Metrics",    "All devices monitored with thresholds",     10, "PASS"),
    ("Monitoring - Alerts",     "Alert routing with escalation policy",       8, "WARN"),
    ("Monitoring - Logs",       "Syslog to central SIEM",                     10, "PASS"),
    ("Backups - Config",        "Nightly config backup to git",               10, "PASS"),
    ("Backups - Device image",  "IOS/firmware images backed up",               5, "FAIL"),
    ("Security - Access",       "TACACS+/RADIUS for device access",          10, "PASS"),
    ("Security - Port",         "802.1X on all access ports",                  7, "WARN"),
    ("Security - Audit",        "Command logging enabled",                     8, "WARN"),
    ("Capacity - Bandwidth",    "Links < 60% utilization",                   10, "PASS"),
    ("Capacity - Growth",       "30% headroom on all subnets",                 8, "WARN"),
    ("Documentation - Topology","Current L2/L3 diagrams",                     10, "PASS"),
    ("Documentation - IPAM",    "IP address management up to date",          10, "PASS"),
    ("Documentation - Runbooks","Runbooks for common incidents",               5, "FAIL"),
    ("Procedures - Change mgmt","Change approval process",                    10, "PASS"),
    ("Procedures - IR",         "Documented incident response process",         7, "WARN"),
]


PORTFOLIO_DIRS: list[tuple[str, str]] = [
    ("inventory/",  "Hardware inventory (models, serials, locations)"),
    ("topology/",   "L2 and L3 topology diagrams (Visio/draw.io)"),
    ("ipam/",       "IP address management (subnet allocations, reservations)"),
    ("vlans/",      "VLAN database (IDs, names, subnets, port assignments)"),
    ("configs/",    "Device configurations (backed up nightly to git)"),
    ("runbooks/",   "Operational runbooks (outage, DDoS, breach, etc.)"),
    ("policies/",   "Security policies (ACLs, firewall rules, QoS)"),
    ("procedures/", "Change management, incident response, onboarding"),
    ("monitoring/", "Dashboard URLs, alert definitions, escalation paths"),
    ("vendor/",     "Support contracts, SLAs, contact information"),
]


TREND = [
    (_dt.date(2024, 1, 1),  62),
    (_dt.date(2024, 2, 1),  68),
    (_dt.date(2024, 3, 1),  72),
    (_dt.date(2024, 4, 1),  75),
    (_dt.date(2024, 5, 1),  79),
    (_dt.date(2024, 6, 22), 82),
]


@dataclass
class Scorecard:
    checks: list[tuple[str, str, int, str]]
    date: _dt.date

    def totals(self) -> tuple[int, int]:
        score = sum(c[2] for c in self.checks)
        maximum = 10 * len(self.checks)
        return score, maximum

    def grade(self) -> str:
        score, maximum = self.totals()
        pct = score / maximum * 100
        if pct >= 90: return "A"
        if pct >= 80: return "B"
        if pct >= 70: return "C"
        if pct >= 60: return "D"
        return "F"

    def failing(self) -> list[str]:
        return [c[0] for c in self.checks if c[3] == "FAIL"]

    def warning(self) -> list[str]:
        return [c[0] for c in self.checks if c[3] == "WARN"]


def render_scorecard(card: Scorecard) -> str:
    score, maximum = card.totals()
    pct = score / maximum * 100
    lines = [f"  {'Check':30s} {'Score':>9s} {'Status':8s}  Description"]
    lines.append(f"  {'-'*30} {'-'*9} {'-'*8}  {'-'*40}")
    for check, desc, sc, status in card.checks:
        icon = "OK" if status == "PASS" else ("!!" if status == "WARN" else "XX")
        lines.append(f"  {check:30s} {sc:4d}/10   {icon:8s}  {desc}")
    lines.append("")
    lines.append(f"  Overall Score: {score}/{maximum} ({pct:.0f}%) - Grade: {card.grade()}")
    return "\n".join(lines)


def render_trend(trend: list[tuple[_dt.date, int]]) -> str:
    lines = ["  90-day readiness trend (%):"]
    width = 50
    for date, pct in trend:
        bar = "#" * int(pct / 100 * width)
        lines.append(f"    {date.isoformat()}  {pct:3d}  {bar}")
    return "\n".join(lines)


def main() -> None:
    print("=" * 65)
    print("Network Documentation Portfolio + Production Readiness Review")
    print("=" * 65)

    print(f"\n  Part 1: Documentation Portfolio Structure\n")
    print(f"  {'Directory':20s} Contents")
    print(f"  {'-'*20} {'-'*50}")
    for d, desc in PORTFOLIO_DIRS:
        print(f"  {d:20s} {desc}")

    card = Scorecard(READINESS_CHECKS, _dt.date(2024, 6, 22))

    print(f"\n  Part 2: Production Readiness Scorecard\n")
    print(render_scorecard(card))

    fails = card.failing()
    warns = card.warning()
    print(f"\n  FAIL items ({len(fails)}):")
    for f in fails:
        print(f"    - {f}")
    print(f"  WARN items ({len(warns)}):")
    for w in warns:
        print(f"    - {w}")

    print(f"\n  Part 3: Remediation Plan:")
    print(f"    Priority 1 (FAIL): Fix within 1 week")
    print(f"      - Back up device images to TFTP/S3 bucket")
    print(f"      - Write runbooks for top 5 incident types")
    print(f"    Priority 2 (WARN): Fix within 1 month")
    print(f"      - Tune alert thresholds and routing")
    print(f"      - Deploy 802.1X on remaining access ports")
    print(f"      - Enable command audit logging on all devices")
    print(f"      - Document incident response process end-to-end")
    print(f"      - Allocate additional subnets for growth headroom")

    print(f"\n  Part 4: 90-day trend\n")
    print(render_trend(TREND))

    score, maximum = card.totals()
    payload = {
        "date": card.date.isoformat(),
        "score": score,
        "maximum": maximum,
        "grade": card.grade(),
        "fail": card.failing(),
        "warn": card.warning(),
    }
    print(f"\n  Part 5: Machine-readable summary (JSON)\n")
    print(json.dumps(payload, indent=2))

    print(f"\n  Ship It:")
    print(f"    outputs/ contains: portfolio/ (git repo), scorecard.md,")
    print(f"    remediation-plan.md, trend.png, summary.json")


if __name__ == "__main__":
    main()
