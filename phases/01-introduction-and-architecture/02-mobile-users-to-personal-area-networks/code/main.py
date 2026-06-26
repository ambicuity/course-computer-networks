#!/usr/bin/env python3
"""Bluetooth piconet + FHSS simulator for the "Mobile Users to PANs" lesson.

Models the load-bearing facts of an IEEE 802.15.1 / Bluetooth piconet:

  * The master assigns each active slave a 3-bit Active Member Address
    (AM_ADDR) in 1..7. The code 000 is reserved for broadcast, so a single
    piconet holds AT MOST 7 active slaves.
  * An over-capacity joiner is rejected unless an existing slave is "parked"
    (moved to an 8-bit PM_ADDR, 1..255), which frees its AM_ADDR.
  * Frequency-Hopping Spread Spectrum: 79 channels of 1 MHz in the 2.4 GHz
    ISM band, 1600 hops/s, one hop per 625 microsecond time slot. The master
    transmits in even slots, slaves in odd slots (time-division duplex).

Pure standard library, no network access. Run: python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- Bluetooth constants (from IEEE 802.15.1 / Bluetooth Core spec) ---------
AM_ADDR_BROADCAST = 0b000      # reserved -> not a usable unit address
AM_ADDR_MIN = 1                # 0b001
AM_ADDR_MAX = 7                # 0b111  -> 7 active slaves maximum
PM_ADDR_MIN = 1
PM_ADDR_MAX = 255              # 8-bit parked member address
NUM_RF_CHANNELS = 79           # 79 x 1 MHz channels
SLOT_MICROSECONDS = 625        # 1 / 1600 hops/s = 625 us
HOPS_PER_SECOND = 1_000_000 // SLOT_MICROSECONDS  # 1e6 us/s / 625 us = 1600
ISM_BASE_MHZ = 2402            # channel 0 center frequency (2402 MHz)

NUM_JOINERS = 9                # try to join more devices than a piconet allows


@dataclass
class Slave:
    name: str
    am_addr: Optional[int] = None   # active member address (1..7) or None if parked
    pm_addr: Optional[int] = None   # parked member address (1..255) or None if active

    @property
    def is_active(self) -> bool:
        return self.am_addr is not None


@dataclass
class Piconet:
    """A master plus its slaves, owning the AM_ADDR/PM_ADDR allocation."""

    master_name: str
    slaves: list[Slave] = field(default_factory=list)

    def _free_am_addr(self) -> Optional[int]:
        used = {s.am_addr for s in self.slaves if s.is_active}
        for addr in range(AM_ADDR_MIN, AM_ADDR_MAX + 1):
            if addr not in used:
                return addr
        return None

    def _free_pm_addr(self) -> int:
        used = {s.pm_addr for s in self.slaves if s.pm_addr is not None}
        for addr in range(PM_ADDR_MIN, PM_ADDR_MAX + 1):
            if addr not in used:
                return addr
        raise RuntimeError("PM_ADDR space exhausted (255 parked members)")

    def active_count(self) -> int:
        return sum(1 for s in self.slaves if s.is_active)

    def admit(self, name: str) -> tuple[bool, str]:
        """Try to admit a new active slave. Returns (success, human message)."""
        addr = self._free_am_addr()
        if addr is None:
            return (
                False,
                f"REJECT '{name}': all {AM_ADDR_MAX} AM_ADDR codes in use "
                f"(broadcast 000 reserved). Park a member first.",
            )
        self.slaves.append(Slave(name=name, am_addr=addr))
        return (True, f"ADMIT  '{name}': AM_ADDR = {addr:03b} ({addr})")

    def park(self, name: str) -> tuple[bool, str]:
        """Park an active slave, freeing its AM_ADDR for a new joiner."""
        for s in self.slaves:
            if s.name == name and s.is_active:
                freed = s.am_addr
                s.am_addr = None
                s.pm_addr = self._free_pm_addr()
                return (
                    True,
                    f"PARK   '{name}': AM_ADDR {freed:03b} released, "
                    f"now PM_ADDR = {s.pm_addr} (8-bit)",
                )
        return (False, f"PARK   '{name}': not an active member")


def channel_for_slot(slot: int, master_clock_seed: int) -> int:
    """Pseudo-random FHSS channel (0..78) for a slot, keyed by master clock.

    A toy stand-in for the real Bluetooth hop-selection kernel: deterministic,
    seeded by the master's clock, spread across all 79 channels.
    """
    h = (slot * 2654435761 + master_clock_seed * 40503) & 0xFFFFFFFF
    return h % NUM_RF_CHANNELS


def channel_to_mhz(channel: int) -> int:
    return ISM_BASE_MHZ + channel  # 1 MHz spacing: 2402..2480 MHz


def slot_owner(slot: int) -> str:
    """Time-division duplex: master speaks in even slots, slaves in odd."""
    return "master" if slot % 2 == 0 else "slave"


def demo_admission(piconet: Piconet, joiners: list[str]) -> None:
    print(f"Master: '{piconet.master_name}'  (piconet active limit = {AM_ADDR_MAX})")
    print("-" * 64)
    rejected: list[str] = []
    for name in joiners:
        ok, msg = piconet.admit(name)
        print(f"  {msg}")
        if not ok:
            rejected.append(name)
    print(f"\n  active members: {piconet.active_count()} / {AM_ADDR_MAX}")
    if rejected:
        print(f"  rejected (over capacity): {', '.join(rejected)}")

    # Recover one rejected device by parking an existing active slave.
    if rejected:
        victim = piconet.slaves[2].name  # park the 3rd-admitted slave
        print("\n  Recovery: park one member, then re-admit a rejected device.")
        _, pmsg = piconet.park(victim)
        print(f"  {pmsg}")
        ok, amsg = piconet.admit(rejected[0])
        print(f"  {amsg}")
        print(f"  active members now: {piconet.active_count()} / {AM_ADDR_MAX}")


def demo_hopping(master_clock_seed: int, n_slots: int = 10) -> None:
    print("\nFHSS schedule  (79 x 1 MHz, 1600 hops/s, 625 us/slot, TDD)")
    print("-" * 64)
    print(f"  {'slot':>4}  {'owner':<6}  {'channel':>7}  {'freq (MHz)':>10}  {'t (us)':>8}")
    for slot in range(n_slots):
        ch = channel_for_slot(slot, master_clock_seed)
        print(
            f"  {slot:>4}  {slot_owner(slot):<6}  {ch:>7}  "
            f"{channel_to_mhz(ch):>10}  {slot * SLOT_MICROSECONDS:>8}"
        )


def main() -> None:
    print("=" * 64)
    print("Bluetooth piconet + FHSS simulator (IEEE 802.15.1)")
    print("=" * 64)
    assert HOPS_PER_SECOND == 1600, "hop rate must be 1600/s"

    joiners = [f"dev{i}" for i in range(1, NUM_JOINERS + 1)]
    piconet = Piconet(master_name="game-console")
    demo_admission(piconet, joiners)

    demo_hopping(master_clock_seed=0x2A1A2E)

    print("\nTakeaways:")
    print(f"  * AM_ADDR is 3 bits, code 000 reserved -> {AM_ADDR_MAX}-active limit.")
    print("  * The 8th device is a STRUCTURAL reject, not a flaky radio.")
    print("  * Parking frees an AM_ADDR via an 8-bit PM_ADDR (up to 255).")
    print("  * Even slots = master, odd slots = slave; one hop every 625 us.")


if __name__ == "__main__":
    main()
