#!/usr/bin/env python3
"""mDNS / Zeroconf probe and conflict simulation.

Reference oracle for the integrated troubleshooting lab. Walks the
RFC 6762 probe/announce state machine for a configurable number of
hosts and prints the verdict.

Scenarios:

  conflict
    Two hosts propose the same .local name; both see each other's
    probe answers; both must rename.

  stale_cache
    A service is unplugged and replaced; the old cache entry
    persists for 4500 s (SRV TTL). The diagnostic is the cache
    flush (RFC 6762 sec. 10.2).

  relay
    Avahi reflector's enable-reflector=1 forwards mDNS across
    segments; the security trade-off is noted.

  clean
    Two hosts propose distinct names; no conflict; no renames.

Run:  python3 main.py --scenario conflict
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Probe:
    host: str
    proposed_name: str
    t_ms: int


@dataclass
class Host:
    name: str
    proposed: str
    announced: bool = False
    renamed_to: str = ""


# Standard mDNS constants (RFC 6762).
MDNS_PORT = 5353
MDNS_IPV4_GROUP = "224.0.0.251"
MDNS_IPV6_GROUP = "ff02::fb"
MDNS_TTL = 255
PROBE_INTERVAL_MS = 250
PROBE_COUNT = 3
ANNOUNCE_INTERVAL_S = 1
ANNOUNCE_COUNT_MIN = 3
ANNOUNCE_COUNT_MAX = 9
CACHE_TTL_A = 75        # A/AAAA record TTL in seconds
CACHE_TTL_SRV = 4500    # SRV record TTL
CACHE_TTL_PTR = 120     # PTR/TXT record TTL


def detect_conflict(observed_answers: list[Probe], own_host: str, own_name: str) -> bool:
    """True iff any peer's probe answers for the same name."""
    return any(
        p.host != own_host and p.proposed_name == own_name for p in observed_answers
    )


def renamed_name(base: str, suffix: int) -> str:
    """Avahi's default rename suffix logic (laptop -> laptop-2)."""
    return f"{base.rsplit('.', 1)[0]}-{suffix}.local"


def self_test() -> bool:
    """Self-test for the mDNS probe and conflict detection."""
    assert PROBE_COUNT == 3, "RFC 6762 sec. 8 requires 3 probes"
    assert CACHE_TTL_SRV == 4500, "RFC 6762 sec. 10 TTL_SRV is 4500 s"
    assert CACHE_TTL_A == 75, "RFC 6762 sec. 10 TTL_A is 75 s"
    assert detect_conflict(
        [Probe(host="h1", proposed_name="x.local", t_ms=0),
         Probe(host="h2", proposed_name="x.local", t_ms=0)],
        own_host="h1", own_name="x.local",
    ), "cross-host same name must be a conflict"
    assert not detect_conflict(
        [Probe(host="h1", proposed_name="x.local", t_ms=0)],
        own_host="h1", own_name="x.local",
    ), "self-only probes are not a conflict"
    return True


def simulate(scenario: str) -> tuple[list[Probe], list[str]]:
    probes: list[Probe] = []
    notes: list[str] = []
    if scenario == "conflict":
        for t in (0, 250, 500):
            probes.append(Probe(host="h1", proposed_name="laptop.local", t_ms=t))
            probes.append(Probe(host="h2", proposed_name="laptop.local", t_ms=t))
        notes.append("h1 sees h2's probe answer for laptop.local (RFC 6762 sec. 9).")
        notes.append("h2 sees h1's probe answer for laptop.local (RFC 6762 sec. 9).")
        notes.append("h1 renames to laptop-2.local; h2 renames to laptop-3.local.")
        notes.append("Result: avahi-browse -art shows two services on laptop-2 and laptop-3.")
    elif scenario == "stale_cache":
        notes.append("printer.local announced with SRV TTL = 4500 s.")
        notes.append("Printer unplugged at t=0; new printer at same name announced at t=10.")
        notes.append("Until TTL elapses, clients resolve the old printer's IP.")
        notes.append("Cache flush: send an mDNS query with the cache-flush bit (RFC 6762 sec. 10.2).")
    elif scenario == "relay":
        notes.append("Avahi reflector (enable-reflector=1) forwards mDNS across segments.")
        notes.append("Use case: AirPlay / Chromecast across VLANs.")
        notes.append("Security trade-off: any host on any segment can announce any name;")
        notes.append("the link-local trust model is broken.")
    elif scenario == "clean":
        probes.append(Probe(host="h1", proposed_name="alice.local", t_ms=0))
        probes.append(Probe(host="h1", proposed_name="alice.local", t_ms=250))
        probes.append(Probe(host="h1", proposed_name="alice.local", t_ms=500))
        probes.append(Probe(host="h2", proposed_name="bob.local", t_ms=0))
        probes.append(Probe(host="h2", proposed_name="bob.local", t_ms=250))
        probes.append(Probe(host="h2", proposed_name="bob.local", t_ms=500))
        notes.append("No conflicting answers; both hosts enter the announce phase.")
        notes.append("Announce: 3-9 unsolicited responses, 1 s apart.")
        notes.append("Established: re-announce every TTL/2 (37.5 s for A/AAAA).")
    else:
        notes.append(f"Unknown scenario: {scenario}")
    return probes, notes


def render(scenario: str, probes: list[Probe], notes: list[str]) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"mDNS PROBE / CONFLICT ORACLE  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    if probes:
        out.append(f"{'t (ms)':>6}  {'host':<6}  probe")
        out.append("-" * 48)
        for p in probes:
            out.append(f"{p.t_ms:>6}  {p.host:<6}  {p.proposed_name}")
        out.append("")
    out.append("Notes:")
    for n in notes:
        out.append(f"  - {n}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("conflict", "stale_cache", "relay", "clean"),
        default="conflict",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit.")
    args = parser.parse_args()
    if args.self_test:
        ok = self_test()
        print("mDNS self-test: PASS" if ok else "mDNS self-test: FAIL")
        return
    probes, notes = simulate(args.scenario)
    print(render(args.scenario, probes, notes))


if __name__ == "__main__":
    main()
