#!/usr/bin/env python3
"""RFC metadata model and authoritative-spec resolver.

This module turns the Internet standards process (Section 1.6.3) into something
executable. Every RFC is an immutable, numbered document carrying status
metadata: a maturity *category*, the RFCs it *obsoletes* (fully replaces), the
RFCs it *updates* (partially amends), and the RFC that *obsoletes it* (if it is
now dead). Quoting a superseded spec is a daily operational failure; this tool
resolves any starting RFC number to the document that actually governs the wire
format today, by following the Obsoleted-By chain to its end.

No network calls, no third-party dependencies: the registry is a small,
hand-curated snapshot of real RFC relationships used purely for teaching.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Maturity categories an RFC header can declare (RFC 2026, RFC 6410).
STANDARDS_TRACK = "Standards Track"
INFORMATIONAL = "Informational"
EXPERIMENTAL = "Experimental"
BCP = "Best Current Practice"
HISTORIC = "Historic"


@dataclass(frozen=True)
class Rfc:
    """An immutable RFC record (frozen mirrors real-world immutability)."""

    number: int
    title: str
    year: int
    category: str
    obsoletes: tuple[int, ...] = field(default_factory=tuple)
    updates: tuple[int, ...] = field(default_factory=tuple)
    obsoleted_by: Optional[int] = None

    def is_dead(self) -> bool:
        """True if a later RFC has fully replaced this one."""
        return self.obsoleted_by is not None


# A small registry of real RFC relationships. Each protocol family shows a
# chain: an old document obsoleted by a newer one, sometimes through several
# hops, exactly as an engineer must trace it.
REGISTRY: dict[int, Rfc] = {
    # --- TCP: RFC 793 (1981) folded into RFC 9293 (2022) ---
    793: Rfc(793, "Transmission Control Protocol", 1981, HISTORIC,
             obsoleted_by=9293),
    2018: Rfc(2018, "TCP Selective Acknowledgment Options", 1996,
              STANDARDS_TRACK, updates=(793,)),
    9293: Rfc(9293, "Transmission Control Protocol", 2022, STANDARDS_TRACK,
              obsoletes=(793, 879, 6093, 6528)),
    # --- HTTP/1.1: 2616 -> 723x split -> 9110/9112 ---
    2616: Rfc(2616, "Hypertext Transfer Protocol -- HTTP/1.1", 1999,
              STANDARDS_TRACK, obsoleted_by=7230),
    7230: Rfc(7230, "HTTP/1.1: Message Syntax and Routing", 2014,
              STANDARDS_TRACK, obsoletes=(2616,), obsoleted_by=9112),
    9110: Rfc(9110, "HTTP Semantics", 2022, STANDARDS_TRACK),
    9112: Rfc(9112, "HTTP/1.1", 2022, STANDARDS_TRACK, obsoletes=(7230,)),
    # --- TLS: 5246 (1.2) obsoleted by 8446 (1.3) ---
    5246: Rfc(5246, "TLS Protocol Version 1.2", 2008, STANDARDS_TRACK,
              obsoleted_by=8446),
    8446: Rfc(8446, "The Transport Layer Security (TLS) Protocol Version 1.3",
              2018, STANDARDS_TRACK, obsoletes=(5246,)),
    # --- IP / DNS (live, no successor) ---
    791: Rfc(791, "Internet Protocol", 1981, STANDARDS_TRACK),
    1035: Rfc(1035, "Domain Names - Implementation and Specification", 1987,
              STANDARDS_TRACK),
    # --- Process documents ---
    2026: Rfc(2026, "The Internet Standards Process -- Revision 3", 1996, BCP),
    6410: Rfc(6410, "Reducing the Standards Track to Two Maturity Levels",
              2011, BCP, updates=(2026,)),
    1796: Rfc(1796, "Not All RFCs are Standards", 1995, INFORMATIONAL),
}


def classify_status(rfc: Rfc) -> str:
    """Return a human-readable status line for one RFC."""
    state = "HISTORIC (superseded)" if rfc.is_dead() else "LIVE"
    return f"RFC {rfc.number} [{rfc.category}] -> {state}"


def resolve_authoritative(number: int) -> tuple[Rfc, list[int]]:
    """Follow the Obsoleted-By chain to the document that governs today.

    Returns the live RFC plus the list of RFC numbers visited (the trail).
    Raises KeyError if a number in the chain is missing from the registry.
    Raises ValueError if the chain contains a cycle.
    """
    trail: list[int] = []
    seen: set[int] = set()
    current = number
    while True:
        if current in seen:
            raise ValueError(f"Cycle detected in obsolete chain at RFC {current}")
        seen.add(current)
        trail.append(current)
        rfc = REGISTRY[current]
        if rfc.obsoleted_by is None:
            return rfc, trail
        current = rfc.obsoleted_by


def find_updaters(number: int) -> list[Rfc]:
    """Return every registry RFC that *updates* (amends) the given RFC."""
    return sorted(
        (r for r in REGISTRY.values() if number in r.updates),
        key=lambda r: r.number,
    )


def print_resolution(label: str, start: int) -> None:
    """Print a full resolution report for one protocol lookup."""
    print(f"\n=== {label}: starting from RFC {start} ===")
    start_rfc = REGISTRY[start]
    live, trail = resolve_authoritative(start)
    if start_rfc.is_dead():
        print(f"  WARNING: RFC {start} ({start_rfc.title}) is DEAD.")
        chain = " -> ".join(f"RFC {n}" for n in trail)
        print(f"  Obsolete chain: {chain}")
    print(f"  Authoritative today: RFC {live.number} "
          f"({live.title}, {live.year}) [{live.category}]")
    if live.obsoletes:
        replaced = ", ".join(str(n) for n in live.obsoletes)
        print(f"  It obsoletes: {replaced}")
    updaters = find_updaters(live.number)
    if updaters:
        amend = ", ".join(f"RFC {r.number}" for r in updaters)
        print(f"  Amended by (Updates): {amend}")


def main() -> None:
    """Demonstrate the resolver on real protocol chains from Section 1.6.3."""
    print("Internet Standards Resolver -- 'rough consensus and running code'")
    print("=" * 64)

    # 1. Resolve the spec engineers most often misquote.
    print_resolution("TLS (security scanner trap)", 5246)
    print_resolution("HTTP/1.1 (request-line grammar)", 2616)
    print_resolution("TCP (capture vs RFC 793)", 793)
    print_resolution("IP (already current)", 791)

    # 2. Show the SACK 'Updates' relationship: a surgical patch, not a replace.
    print("\n=== Updates vs Obsoletes ===")
    sack = REGISTRY[2018]
    print(f"  RFC {sack.number} ({sack.title})")
    print(f"    updates RFC {sack.updates[0]} (adds a TCP option) "
          f"-- it does NOT replace TCP wholesale.")

    # 3. Status census across the registry.
    print("\n=== Status census ===")
    for num in sorted(REGISTRY):
        print("  " + classify_status(REGISTRY[num]))

    live_count = sum(1 for r in REGISTRY.values() if not r.is_dead())
    print(f"\n  {live_count}/{len(REGISTRY)} registry RFCs are still live.")
    print("  Lesson: never quote an RFC without checking its Obsoleted-By field.")


if __name__ == "__main__":
    main()
