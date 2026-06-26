#!/usr/bin/env python3
"""MX-record ranker, glue resolver, and MTA fallback simulator (RFC 5321 §5.1).

Loads a sample MX record set with A/AAAA glue, sorts by preference, and
simulates an MTA trying targets in order. Demonstrates the implicit-A-record
fallback when no MX exists and the Null MX (RFC 7505) for non-mail domains.

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MxRecord:
    preference: int
    target: str

    def __str__(self) -> str:
        return f"{self.preference:>5} {self.target}"


@dataclass
class GlueTable:
    a: Dict[str, str] = field(default_factory=dict)
    aaaa: Dict[str, str] = field(default_factory=dict)

    def resolve(self, host: str) -> Tuple[Optional[str], Optional[str]]:
        return self.a.get(host), self.aaaa.get(host)


def rank_mx(records: List[MxRecord]) -> List[MxRecord]:
    return sorted(records, key=lambda r: (r.preference, r.target))


def is_null_mx(records: List[MxRecord]) -> bool:
    return any(r.preference == 0 and r.target == "." for r in records)


def select_mx_target(
    records: List[MxRecord],
    glue: GlueTable,
    implicit_a: Optional[str],
    reachable: Optional[Dict[str, bool]] = None,
) -> Tuple[Optional[str], str]:
    """Simulate MTA selection: try MX targets in preference order."""
    if is_null_mx(records):
        return None, "null MX (RFC 7505) -- domain does not accept mail"
    if not records:
        if implicit_a is not None:
            return implicit_a, "implicit A fallback (RFC 5321 §5.1)"
        return None, "no MX and no A -- no delivery target"
    ranked = rank_mx(records)
    for rec in ranked:
        if reachable is not None and reachable.get(rec.target, True):
            return rec.target, f"preferring {rec.target} (preference {rec.preference})"
        if reachable is None:
            return rec.target, f"preferring {rec.target} (preference {rec.preference})"
    return None, f"all MX unreachable; queue and retry"


SAMPLE_MX = [
    MxRecord(20, "mail2.example.com."),
    MxRecord(10, "mail1.example.com."),
    MxRecord(30, "backup.example.net."),
]

SAMPLE_GLUE = GlueTable(
    a={
        "mail1.example.com.": "192.0.2.10",
        "mail2.example.com.": "192.0.2.20",
        "backup.example.net.": "198.51.100.5",
    },
    aaaa={
        "mail1.example.com.": "2001:db8::10",
    },
)


def main() -> None:
    print("=" * 64)
    print("MX RECORDS + MTA RELAYING  --  RFC 974 / RFC 1035 / RFC 5321 §5.1 / RFC 7505")
    print("=" * 64)

    print("\nSample MX record set (unsorted):")
    for r in SAMPLE_MX:
        print(f"  {r}")

    print("\nRanked by preference (ascending = higher priority):")
    for r in rank_mx(SAMPLE_MX):
        a, aaaa = SAMPLE_GLUE.resolve(r.target)
        glue = f"A={a} AAAA={aaaa}" if a else "<no glue>"
        print(f"  {r}  -> {glue}")

    print("\nMTA selection scenarios:")
    cases = [
        (SAMPLE_MX, SAMPLE_GLUE, None, None, "all reachable, no info"),
        (SAMPLE_MX, SAMPLE_GLUE, None, {"mail1.example.com.": False, "mail2.example.com.": False}, "primary and secondary down"),
        ([], SAMPLE_GLUE, "192.0.2.50", None, "no MX records"),
        ([MxRecord(0, ".")], GlueTable(), None, None, "null MX"),
    ]
    for mx, glue, implicit_a, reachable, label in cases:
        target, reason = select_mx_target(mx, glue, implicit_a, reachable)
        print(f"  {label}: target={target}  reason={reason}")


if __name__ == "__main__":
    main()
