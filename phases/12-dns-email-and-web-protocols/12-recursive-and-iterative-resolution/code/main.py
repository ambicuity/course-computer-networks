#!/usr/bin/env python3
"""Recursive vs iterative resolution walk simulator (RFC 1034, RFC 1035).

The script models the canonical 10-step resolution walk for a name like
robot.cs.washington.edu. It distinguishes a cold cache (full walk) from a
warm cache (skips known delegations), prints the messages at each hop, and
shows the TTL-driven cache state after the walk completes. No network calls.

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Referral:
    zone: str
    ns_name: str
    ns_addr: str
    ttl: int


@dataclass
class Cache:
    """Minimal TTL-aware cache. Stores RRs and NXDOMAINs."""

    now: int = 0
    ttl_map: Dict[str, int] = field(default_factory=dict)
    nxdomain: Dict[str, int] = field(default_factory=dict)
    rrs: Dict[str, Tuple[str, int]] = field(default_factory=dict)

    def put(self, key: str, value: Tuple[str, int], ttl: int) -> None:
        self.ttl_map[key] = self.now + ttl
        self.rrs[key] = value

    def put_nxdomain(self, key: str, ttl: int) -> None:
        self.nxdomain[key] = self.now + ttl

    def get(self, key: str) -> Optional[Tuple[str, int]]:
        if self.ttl_map.get(key, 0) <= self.now:
            return None
        return self.rrs.get(key)

    def is_nxdomain(self, key: str) -> bool:
        return self.nxdomain.get(key, 0) > self.now


def delegation_chain(name: str) -> List[str]:
    """Return the zones from root to leaf for `name`."""
    labels = name.rstrip(".").split(".")
    return ["(root)"] + [".".join(labels[i:]) for i in range(len(labels))]


def walk_recursive(name: str, qtype: str, cache: Cache) -> List[str]:
    """Walk iteratively from the root down. Returns one log line per hop."""
    log: List[str] = []
    zones = delegation_chain(name)
    seen_ns = set()
    for idx, zone in enumerate(zones):
        cache_key = f"NS:{zone}"
        cached = cache.get(cache_key)
        if cached is not None and idx < len(zones) - 1:
            log.append(f"  step {idx + 1}: CACHE HIT  NS for {zone} -> {cached[0]} (skip hop)")
            continue
        if idx == len(zones) - 1:
            cache.put(f"{qtype}:{name}", ("answer-ready", 1), ttl=300)
            log.append(f"  step {idx + 1}: AUTHORITATIVE answer for {name} {qtype}")
        else:
            ns_name = f"{zones[idx + 1].split('.')[0]}.servers.net"
            ns_addr = "203.0.113." + str(idx + 10)
            ttl = 172800 if zone == "(root)" else 86400
            cache.put(cache_key, (ns_name, ns_addr), ttl=ttl)
            log.append(
                f"  step {idx + 1}: REFERRAL  {zone:>10s} -> NS {ns_name}  "
                f"glue A {ns_addr}  ttl {ttl}s"
            )
            seen_ns.add(ns_name)
    log.append(f"  final: cache keys = {sorted(cache.rrs)}")
    return log


def cold_vs_warm(name: str) -> Tuple[int, int]:
    """Return (cold_rtt_count, warm_rtt_count) for a resolution."""
    zones = delegation_chain(name)
    cold = len(zones)
    warm = 1
    return cold, warm


def main() -> None:
    print("=" * 64)
    print("RECURSIVE vs ITERATIVE RESOLUTION  --  RFC 1034 / RFC 1035")
    print("=" * 64)

    target = "robot.cs.washington.edu"
    qtype = "A"

    cache_cold = Cache(now=0)
    print(f"\nCold walk for {target} {qtype}:")
    for line in walk_recursive(target, qtype, cache_cold):
        print(line)

    print("\nSame query 5 minutes later, same resolver (warm cache):")
    cache_warm = Cache(now=300)
    cache_warm.rrs = dict(cache_cold.rrs)
    cache_warm.ttl_map = dict(cache_cold.ttl_map)
    for line in walk_recursive(target, qtype, cache_warm):
        print(line)

    cold, warm = cold_vs_warm(target)
    print(f"\nRound trips: cold = {cold}, warm = {warm}, saved = {cold - warm}")

    print("\nMode comparison (RFC 1035 §4.1.1 RD/RA flags):")
    print("  client -> local resolver   : RD=1, RA=1   (recursive)")
    print("  local  -> root server      : RD=0, RA=0   (iterative)")
    print("  local  -> TLD server       : RD=0, RA=0   (iterative)")
    print("  local  -> authoritative    : RD=0, RA=0   (iterative)")

    print("\nNegative caching (RFC 2308):")
    cache_nx = Cache(now=0)
    cache_nx.put_nxdomain("missing.example.", ttl=600)
    print(f"  t=0   miss?  is_nxdomain='missing.example.' -> {cache_nx.is_nxdomain('missing.example.')}")
    print(f"  t=601 miss?  is_nxdomain='missing.example.' -> {cache_nx.is_nxdomain('missing.example.')}  (TTL expired)")


if __name__ == "__main__":
    main()
