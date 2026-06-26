#!/usr/bin/env python3
"""RPKI Origin Validator + RFC 9234 Route-Leak Detector (Production Lab 10).

Given a list of ROAs, a BGP table dump, and an AS-rank table, this script
produces a per-prefix origin validation report (Valid / Invalid / NotFound),
a route-leak report per RFC 9234, a state-transition history, and a runbook.

Stdlib only: dataclasses, ipaddress, json.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from ipaddress import IPv4Network
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class ROA:
    prefix: str
    prefix_length: int
    max_length: int
    origin_asn: int
    not_before: datetime
    not_after: datetime

    def covers(self, route_prefix: str, route_length: int) -> bool:
        if self.prefix_length > route_length:
            return False
        if route_length > self.max_length:
            return False
        roa_net = IPv4Network(f"{self.prefix}/{self.prefix_length}")
        route_net = IPv4Network(f"{route_prefix}/{route_length}")
        return roa_net.supernet_of(route_net) or roa_net == route_net


@dataclass
class Route:
    prefix: str
    prefix_length: int
    origin_asn: int
    as_path: list[int]      # leftmost first


@dataclass
class ASRank:
    asn: int
    tier: int               # 1 = tier-1 transit, 2 = tier-2, 3 = customer
    name: str


# ---------------------------------------------------------------------------
# Origin validation (RFC 6811)
# ---------------------------------------------------------------------------

def validate_origin(route: Route, roas: list[ROA], now: datetime) -> str:
    valid_roas = [r for r in roas if r.not_before <= now <= r.not_after]
    covering = [r for r in valid_roas if r.covers(route.prefix, route.prefix_length)]
    if not covering:
        return "NotFound"
    for r in covering:
        if r.origin_asn == route.origin_asn:
            return "Valid"
    return "Invalid"


# ---------------------------------------------------------------------------
# Route-leak detection (RFC 9234)
# ---------------------------------------------------------------------------

def infer_role(prev_tier: int, curr_tier: int) -> str:
    """Infer AS relationship: provider, customer, or peer.

    Heuristic (simplified from RFC 9234 / CAIDA AS-rank):
      provider (upstream)   -> lower tier number
      customer (downstream) -> higher tier number
      peer                  -> same tier
    """
    if curr_tier < prev_tier:
        return "provider"   # curr is upstream of prev
    if curr_tier > prev_tier:
        return "customer"   # curr is downstream of prev
    return "peer"


def detect_leak(route: Route, ranks: dict[int, ASRank]) -> str | None:
    """Return the rule violated and the violating hop, or None if clean."""
    if len(route.as_path) < 2:
        return None
    tiers = [ranks.get(a, ASRank(a, 3, f"AS{a}")).tier for a in route.as_path]
    inferred = []
    for i in range(1, len(tiers)):
        inferred.append(infer_role(tiers[i - 1], tiers[i]))

    # Rule 1: only-to-customer. Provider->provider is a leak.
    for i, role in enumerate(inferred):
        if role == "provider":
            return f"Rule1 (only-to-customer) violated at hop {i+1} AS{route.as_path[i+1]}"
    # Rule 2: only-to-peer. Peer->peer is a leak.
    for i, role in enumerate(inferred):
        if role == "peer":
            return f"Rule2 (only-to-peer) violated at hop {i+1} AS{route.as_path[i+1]}"
    return None


# ---------------------------------------------------------------------------
# State transition history
# ---------------------------------------------------------------------------

def transition_summary(history: list[tuple[datetime, str]]) -> dict:
    counts: dict[str, int] = {"Valid": 0, "Invalid": 0, "NotFound": 0}
    last_state: str | None = None
    longest_valid = 0
    cur_streak = 0
    for _, state in history:
        counts[state] = counts.get(state, 0) + 1
        if state == "Valid":
            cur_streak += 1
            longest_valid = max(longest_valid, cur_streak)
        else:
            cur_streak = 0
        last_state = state
    return {
        "transitions": len(history) - 1,
        "current_state": last_state,
        "time_in_state_min": counts,
        "longest_valid_streak": longest_valid,
    }


# ---------------------------------------------------------------------------
# Runbook
# ---------------------------------------------------------------------------

RUNBOOK_TEMPLATE = """# RPKI Incident Response Runbook

## Detection
- Alert fired: prefix {prefix} transitioned {from_state} -> {to_state}
- Detection source: rpki_monitor (60s poll)
- Affected ASN: AS{origin_asn}

## Containment (within 15 min)
1. Confirm with `show ip bgp {prefix}` and `show bgp ipv4 unicast {prefix}` on all 12 BGP speakers
2. If Invalid: drop the route at ingress with `route-map DROP-INVALID` (Cisco) or `policy-options policy-statement DROP-INVALID` (Juniper)
3. If route-leak: identify the violating hop via `show ip bgp {prefix} regex _<LEAKER>_`

## Eradication (within 60 min)
1. Open ticket with offending AS NOC (lookglass, PeeringDB contact)
2. If the offending AS is a customer, suspend the BGP session with `neighbor <ip> shutdown`
3. If the offending AS is a transit provider, escalate to the provider's NOC with the RFC 7908 e-mail template

## Recovery
1. Wait for the ROA to be republished (operator) or the offending advertisement to be withdrawn (attacker)
2. Re-validate with `show bgp ipv4 unicast {prefix` rpki validation-state`
3. Document the incident in the postmortem queue

## Contacts
- NorthStar NOC: noc@northstar.example
- Upstream A NOC: noc@westlink.example
- Upstream B NOC: noc@northcoast.example
- ARIN RPKI: rpki@arin.net
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Reference time: now (operator sets to current time in real use)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # ROAs: 198.51.100.0/24 AS65020, 203.0.113.0/24 AS65020
    roas = [
        ROA("198.51.100.0", 24, 24, 65020,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2027, 1, 1, tzinfo=timezone.utc)),
        ROA("203.0.113.0", 24, 24, 65020,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2027, 1, 1, tzinfo=timezone.utc)),
    ]

    # BGP table: legitimate + attack + leaked
    routes = [
        Route("198.51.100.0", 24, 65020, [65020, 64600]),               # legit
        Route("203.0.113.0", 24, 65020, [65020, 64600]),                 # legit
        Route("198.51.100.0", 24, 65999, [65999, 64500]),               # hijack
        Route("198.51.100.128", 25, 65020, [65020, 64600]),             # legit more-spec
        Route("198.51.100.0", 24, 65020, [65020, 64500, 64600, 64900]), # provider chain (clean valley-free)
    ]

    # AS-rank (simplified): tier 1 = transit, tier 2 = content, tier 3 = customer
    ranks = {
        64500: ASRank(64500, 1, "WestLink (tier-1)"),
        64600: ASRank(64600, 1, "NorthCoast (tier-1)"),
        64900: ASRank(64900, 2, "NetFlux (tier-2 content)"),
        65020: ASRank(65020, 3, "NorthStar (customer)"),
        65999: ASRank(65999, 3, "AttackerAS (customer)"),
    }

    print("=" * 72)
    print(f"  RPKI ORIGIN VALIDATION + ROUTE-LEAK REPORT  AS65020")
    print("=" * 72)
    print(f"  ROAs loaded      : {len(roas)}")
    print(f"  BGP routes       : {len(routes)}")
    print(f"  Validation time  : {now.isoformat()}")
    print()
    print("--- Per-prefix origin validation ---")
    report = []
    for r in routes:
        state = validate_origin(r, roas, now)
        leak = detect_leak(r, ranks)
        line = f"  {r.prefix}/{r.prefix_length}  AS{r.origin_asn}  " \
               f"as_path={' '.join('AS'+str(a) for a in r.as_path):30s}  " \
               f"state={state:10s}"
        if leak:
            line += f"  LEAK: {leak}"
        print(line)
        report.append({
            "prefix": f"{r.prefix}/{r.prefix_length}",
            "origin_asn": r.origin_asn,
            "as_path": r.as_path,
            "validation_state": state,
            "leak": leak,
        })

    print()
    print("--- State transition history (synthetic, 24h) ---")
    for r in routes[:3]:
        history = [
            (now, "NotFound"),
            (now, "Valid"),
            (now, "Valid"),
            (now, "Invalid"),
        ]
        s = transition_summary(history)
        print(f"  {r.prefix}/{r.prefix_length}: {s}")

    out = {
        "validation_time": now.isoformat(),
        "n_roas": len(roas),
        "n_routes": len(routes),
        "report": report,
    }
    with open("outputs/rpki_report.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Wrote outputs/rpki_report.json")
    print("Runbook template available - see RUNBOOK_TEMPLATE in code.")


if __name__ == "__main__":
    main()
