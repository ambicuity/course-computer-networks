#!/usr/bin/env python3
"""Remote-Triggered Black Hole (RTBH) Controller (Production Lab 11).

Accepts trigger requests for destination / source blackhole filtering,
validates them against an allowlist and deny-list, generates BGP updates
with the upstream's blackhole community, and writes a hash-chained audit
log that detects tampering.

Stdlib only: dataclasses, ipaddress, json, hashlib, hmac, datetime.

Run: python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Iterable


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class UpstreamRTBH:
    name: str
    peer_ip: str
    dest_community: str      # community to set for destination blackhole
    src_community: str       # community to set for source blackhole
    session_state: str       # up / down


@dataclass
class TriggerRequest:
    requester: str
    secret: bytes
    target_ip: str
    action: str               # dest-blackhole | src-blackhole
    target: str
    notes: str


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    timestamp: datetime
    requester: str
    target: str
    action: str
    decision: str             # allow / deny
    reason: str
    prev_hash: str
    record_hash: str = ""

    def compute_hash(self) -> str:
        body = (
            f"{self.timestamp.isoformat()}|{self.requester}|{self.target}|"
            f"{self.action}|{self.decision}|{self.reason}|{self.prev_hash}"
        )
        return hashlib.sha256(body.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------

def sign_request(body: bytes, secret: bytes) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify_request(req: TriggerRequest, body: bytes, signature: str) -> bool:
    expected = sign_request(body, req.secret)
    return hmac.compare_digest(expected, signature)


def evaluate(req: TriggerRequest, allowlist: set[str], denylist: set[str],
             upstreams: list[UpstreamRTBH]) -> tuple[str, str]:
    if req.requester not in allowlist:
        return "deny", "requester not in allowlist"
    if req.target in denylist:
        return "deny", f"target {req.target} is in deny-list (critical infrastructure)"
    if req.action not in ("dest-blackhole", "src-blackhole"):
        return "deny", f"unknown action {req.action}"
    if not upstreams:
        return "deny", "no upstream RTBH receivers configured"
    return "allow", "validated"


# ---------------------------------------------------------------------------
# BGP update generation
# ---------------------------------------------------------------------------

def make_bgp_update(req: TriggerRequest, upstream: UpstreamRTBH) -> dict:
    if req.action == "dest-blackhole":
        comm = upstream.dest_community
        prefix = f"{req.target}/32"
    else:
        comm = upstream.src_community
        prefix = f"{req.target}/24"
    return {
        "announce": prefix,
        "next_hop": upstream.peer_ip,
        "community": comm,
        "withdraw": False,
        "expiry": (datetime.now(timezone.utc) +
                   timedelta(hours=4 if req.action == "dest-blackhole" else 0.5)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def asdict_decision(rec: AuditRecord) -> dict:
    return {
        "timestamp": rec.timestamp.isoformat(),
        "requester": rec.requester,
        "target": rec.target,
        "action": rec.action,
        "decision": rec.decision,
        "reason": rec.reason,
        "prev_hash": rec.prev_hash,
        "record_hash": rec.record_hash,
    }


def verify_chain(log: list[dict]) -> bool:
    prev = "0" * 64
    for r in log:
        if r["prev_hash"] != prev:
            return False
        body = (
            f"{r['timestamp']}|{r['requester']}|{r['target']}|"
            f"{r['action']}|{r['decision']}|{r['reason']}|{r['prev_hash']}"
        )
        h = hashlib.sha256(body.encode()).hexdigest()
        if h != r["record_hash"]:
            return False
        prev = h
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    upstreams = [
        UpstreamRTBH("WestLink", "198.51.100.1", "64500:666", "64500:777", "up"),
        UpstreamRTBH("NorthCoast", "203.0.113.1", "64600:666", "64600:777", "up"),
    ]
    allowlist = {"noc-on-call", "detection-system", "soc-analyst"}
    denylist = {"203.0.113.10", "198.51.100.1", "10.0.0.0/8"}

    secret = b"shared-secret-do-not-commit"

    # Synthetic test requests
    requests = [
        ("noc-on-call",      "198.51.100.42", "dest-blackhole"),
        ("soc-analyst",      "203.0.113.99",  "dest-blackhole"),
        ("soc-analyst",      "203.0.113.10",  "dest-blackhole"),
        ("random-user",      "198.51.100.42", "dest-blackhole"),
        ("detection-system", "192.0.2.5",     "src-blackhole"),
    ]

    print("=" * 72)
    print("  RTBH CONTROLLER  -  TRIGGER REPORT")
    print("=" * 72)

    prev_hash = "0" * 64
    log: list[dict] = []
    for requester, target, action in requests:
        req = TriggerRequest(requester, secret, target, action, target, "")
        decision, reason = evaluate(req, allowlist, denylist, upstreams)
        rec = AuditRecord(
            timestamp=datetime.now(timezone.utc),
            requester=requester,
            target=target,
            action=action,
            decision=decision,
            reason=reason,
            prev_hash=prev_hash,
        )
        rec.record_hash = rec.compute_hash()
        prev_hash = rec.record_hash
        log.append(asdict_decision(rec))
        bgp = "  BGP: " + json.dumps(make_bgp_update(req, upstreams[0])) if decision == "allow" else ""
        print(f"  {decision.upper():4s}  {requester:18s} -> {target:18s}  {action:18s}  {reason}{bgp}")

    # Tamper detection
    print()
    print("--- Tamper detection ---")
    log_copy = [dict(r) for r in log]
    log_copy[0]["timestamp"] = "1999-01-01T00:00:00+00:00"
    print(f"  Tampered chain valid? {verify_chain(log_copy)}  (expected: False)")
    print(f"  Original chain valid? {verify_chain(log)}  (expected: True)")

    with open("outputs/rtbh_log.json", "w") as f:
        json.dump(log, f, indent=2, default=str)
    print()
    print("Wrote outputs/rtbh_log.json")


if __name__ == "__main__":
    main()
