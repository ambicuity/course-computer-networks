#!/usr/bin/env python3
"""ARP Spoofing and Duplicate-IP Conflict Investigation (Lab 08).

Simulates a Layer-2 segment where a gateway IP (10.0.0.1) is legitimately
owned by gw_mac but an attacker periodically emits forged ARP replies.
The watchdog reads a synthetic ARP-reply timeline and flags every cache
flip, every duplicate claim, and identifies the MITM pivot window.

Run:  python3 code/main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta


GW_IP = "10.0.0.1"
GW_MAC = "00:11:22:33:44:55"
ATTACKER_MAC = "de:ad:be:ef:00:01"
CACHE_TTL = timedelta(seconds=120)


@dataclass(frozen=True)
class ArpReply:
    t: float          # seconds since session start
    src_mac: str
    claimed_ip: str
    gratuitous: bool = False


@dataclass
class CacheEntry:
    mac: str
    bound_at: float
    flips: int = 0
    last_flip_t: float | None = None


def build_timeline() -> list[ArpReply]:
    # Normal gateway replies to victim ARP who-has requests
    events = [
        ArpReply(0.0, GW_MAC, GW_IP),
        ArpReply(30.0, GW_MAC, GW_IP),
    ]
    # Attacker emits gratuitous ARP binding the gateway IP to attacker MAC
    events.append(ArpReply(45.0, ATTACKER_MAC, GW_IP, gratuitous=True))
    # Victim re-ARPs; gateway answers, attacker counters
    events.append(ArpReply(50.0, GW_MAC, GW_IP))
    events.append(ArpReply(52.0, ATTACKER_MAC, GW_IP, gratuitous=True))
    # Idle period, then attacker refreshes before TTL expiry
    events.append(ArpReply(140.0, ATTACKER_MAC, GW_IP, gratuitous=True))
    events.append(ArpReply(220.0, GW_MAC, GW_IP))
    return sorted(events, key=lambda e: e.t)


def watch(timeline: list[ArpReply]) -> tuple[CacheEntry, list[str]]:
    cache = CacheEntry(mac=timeline[0].src_mac, bound_at=timeline[0].t)
    log: list[str] = []
    duplicates: list[tuple[float, str, str]] = []
    known_macs: set[str] = {timeline[0].src_mac}

    print("=" * 70)
    print("ARP Spoofing / Duplicate-IP Watchdog")
    print("=" * 70)
    print(f"  Gateway IP : {GW_IP}")
    print(f"  Legit MAC  : {GW_MAC}")
    print(f"  Attacker   : {ATTACKER_MAC}")
    print(f"  Cache TTL  : {int(CACHE_TTL.total_seconds())} s\n")

    for e in timeline:
        known_macs.add(e.src_mac)
        age = e.t - cache.bound_at
        marker = ""
        if e.src_mac != cache.mac:
            cache.flips += 1
            cache.last_flip_t = e.t
            log.append(
                f"[T={e.t:6.1f}] FLIP {GW_IP}: {cache.mac} -> {e.src_mac}"
                f"  (cache age {age:.1f}s, "
                f"{'gratuitous' if e.gratuitous else 'reply'})"
            )
            cache.mac = e.src_mac
            cache.bound_at = e.t
            marker = "<== CACHE FLIP"
        else:
            log.append(
                f"[T={e.t:6.1f}] REBIND {GW_IP} -> {e.src_mac}"
                f"  ({'gratuitous' if e.gratuitous else 'reply'})"
            )

        # Duplicate-IP heuristic: a second MAC claims the same IP
        # while another MAC is still within TTL
        if e.src_mac != GW_MAC and e.claimed_ip == GW_IP:
            duplicates.append((e.t, e.src_mac, "non-gateway MAC claimed gateway IP"))

    for line in log:
        print("  " + line + (("  " + marker) if line.endswith("FLIP " + GW_IP) else ""))

    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    print(f"  Distinct MACs observed claiming {GW_IP}: {sorted(known_macs)}")
    print(f"  Total cache flips: {cache.flips}")
    print(f"  Last flip at T={cache.last_flip_t}")
    if len(known_macs) > 1:
        rogue = sorted(known_macs - {GW_MAC})
        print(f"  ROGUE MAC(s) for gateway IP: {rogue}")
        print(f"  Verdict: ARP SPOOFING / DUPLICATE-IP CONFLICT")
        print(f"  Impact: traffic for {GW_IP} periodically routed through "
              f"{rogue[0]}")
        print(f"  Remediation:")
        print(f"    1. Enable Dynamic ARP Inspection on the access switch")
        print(f"    2. Isolate port serving {rogue[0]}")
        print(f"    3. Flush ARP cache on victim: ip neigh flush all")
        print(f"    4. Add static ARP entry for gateway on critical hosts")
    else:
        print("  Verdict: NO CONFLICT DETECTED")
    return cache, log


def mitm_window(timeline: list[ArpReply]) -> float:
    """Return cumulative seconds the attacker MAC held the gateway IP."""
    total = 0.0
    holder = None
    bound_at = 0.0
    for e in timeline:
        if holder == ATTACKER_MAC and e.src_mac != ATTACKER_MAC:
            total += e.t - bound_at
        if e.src_mac != holder:
            holder = e.src_mac
            bound_at = e.t
    if holder == ATTACKER_MAC:
        # held to end of trace
        total += timeline[-1].t - bound_at
    return total


def main() -> None:
    timeline = build_timeline()
    cache, _ = watch(timeline)
    window = mitm_window(timeline)
    print(f"\n  MITM exposure window (attacker held gateway IP): {window:.1f} s")
    print(f"  Flip rate: {cache.flips / (timeline[-1].t / 60.0):.2f} flips/min")


if __name__ == "__main__":
    main()