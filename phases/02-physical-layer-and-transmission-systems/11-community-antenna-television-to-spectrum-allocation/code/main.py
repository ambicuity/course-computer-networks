#!/usr/bin/env python3
"""Cable TV / HFC spectrum + DOCSIS toolkit (stdlib only).

This module models the three things that make cable Internet work over a shared
coaxial medium, as described in Tanenbaum & Wetherall Ch. 2 section 2.8:

  1. Spectrum allocation (FDM): classify a frequency into upstream / FM / TV /
     downstream-data per the North American plan.
  2. Downstream throughput: derive net Mbps from channel width, QAM order, and
     FEC overhead (QAM-64 -> ~27 Mbps net, QAM-256 -> ~39 Mbps net per 6 MHz).
  3. Upstream contention: simulate slotted ALOHA with binary exponential backoff,
     the algorithm cable modems use because they cannot carrier-sense the medium.

No network calls, no third-party packages. Run: python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# --- North American cable spectrum plan (MHz), from section 2.8.3 ----------
UPSTREAM_LOW_MHZ = 5.0
UPSTREAM_HIGH_MHZ = 42.0
TV_LOW_MHZ = 54.0
TV_HIGH_MHZ = 550.0
FM_LOW_MHZ = 88.0
FM_HIGH_MHZ = 108.0
DOWNSTREAM_DATA_LOW_MHZ = 550.0
DOWNSTREAM_DATA_HIGH_MHZ = 750.0

NA_CHANNEL_WIDTH_MHZ = 6.0  # North America; Europe uses 6-8 MHz

# QAM order -> bits carried per symbol
QAM_BITS_PER_SYMBOL = {
    "QPSK": 2,
    "QAM-16": 4,
    "QAM-64": 6,
    "QAM-128": 7,
    "QAM-256": 8,
}


@dataclass(frozen=True)
class Band:
    """A labeled region of the cable spectrum."""

    name: str
    low_mhz: float
    high_mhz: float
    direction: str  # "upstream", "downstream", or "n/a"


def classify_frequency(freq_mhz: float) -> Band:
    """Return the spectrum band a frequency falls into (NA plan).

    FM radio sits inside the TV downstream band (88-108 MHz) and is checked
    first so it is reported specifically rather than as generic TV.
    """
    if freq_mhz < 0:
        raise ValueError("frequency must be non-negative")
    if UPSTREAM_LOW_MHZ <= freq_mhz <= UPSTREAM_HIGH_MHZ:
        return Band("Upstream data", UPSTREAM_LOW_MHZ, UPSTREAM_HIGH_MHZ, "upstream")
    if FM_LOW_MHZ <= freq_mhz <= FM_HIGH_MHZ:
        return Band("FM radio", FM_LOW_MHZ, FM_HIGH_MHZ, "downstream")
    if TV_LOW_MHZ <= freq_mhz < DOWNSTREAM_DATA_LOW_MHZ:
        return Band("TV channels", TV_LOW_MHZ, TV_HIGH_MHZ, "downstream")
    if DOWNSTREAM_DATA_LOW_MHZ <= freq_mhz <= DOWNSTREAM_DATA_HIGH_MHZ:
        return Band(
            "Downstream data",
            DOWNSTREAM_DATA_LOW_MHZ,
            DOWNSTREAM_DATA_HIGH_MHZ,
            "downstream",
        )
    return Band("Unused / guard", freq_mhz, freq_mhz, "n/a")


def symbol_rate_msps(channel_width_mhz: float, rolloff: float = 0.12) -> float:
    """Approximate usable symbol rate (Msym/s) for a channel.

    A QAM channel cannot use the full bandwidth as symbol rate because of
    pulse-shaping roll-off (alpha ~= 0.12-0.15 for typical cable PHYs). The
    ITU-T J.83 Annex B downstream symbol rate is ~5.36 Msym/s on a 6 MHz
    channel, which this approximation reproduces.
    """
    return channel_width_mhz / (1.0 + rolloff)


def downstream_throughput(
    qam: str,
    channel_width_mhz: float = NA_CHANNEL_WIDTH_MHZ,
    fec_overhead: float = 0.06,
) -> dict[str, float]:
    """Raw and net downstream rate (Mbps) for a single channel.

    The MPEG-2-aligned 204-byte frame carries a 184-byte payload, with the
    rest Reed-Solomon FEC + overhead. We model that loss with fec_overhead
    plus framing so QAM-64 lands near the textbook ~27 Mbps net and QAM-256
    near ~39 Mbps net on a 6 MHz channel.
    """
    bits_per_symbol = QAM_BITS_PER_SYMBOL[qam]
    raw_mbps = symbol_rate_msps(channel_width_mhz) * bits_per_symbol
    framing_efficiency = 184.0 / 204.0  # MPEG-2 frame payload ratio
    net_mbps = raw_mbps * framing_efficiency * (1.0 - fec_overhead)
    return {"raw_mbps": raw_mbps, "net_mbps": net_mbps}


def bonded_throughput(qam: str, channels: int) -> float:
    """Net downstream Mbps when DOCSIS 3.0 bonds several channels."""
    return downstream_throughput(qam)["net_mbps"] * channels


@dataclass
class AlohaResult:
    """Outcome of one modem's upstream request attempt."""

    modem_id: int
    slot_chosen: int
    attempts: int
    succeeded: bool
    backoff_windows: list[int]


def simulate_slotted_aloha(
    num_modems: int,
    num_request_minislots: int,
    max_attempts: int = 8,
    seed: int = 42,
) -> list[AlohaResult]:
    """Simulate upstream request contention with binary exponential backoff.

    Modems pick a request minislot. If two pick the same slot in the same
    round, both collide (no ACK) and must retry. After each collision the
    contention window doubles (1, 2, 4, ... slots of random delay), exactly
    like slotted ALOHA with BEB. Modems cannot carrier-sense, so this is the
    only collision strategy available on the upstream.
    """
    rng = random.Random(seed)
    results = [
        AlohaResult(modem_id=i, slot_chosen=-1, attempts=0,
                    succeeded=False, backoff_windows=[])
        for i in range(num_modems)
    ]
    pending = list(range(num_modems))

    round_no = 0
    while pending and round_no < max_attempts:
        round_no += 1
        # Each pending modem picks a request minislot this round.
        picks: dict[int, list[int]] = {}
        for mid in pending:
            slot = rng.randrange(num_request_minislots)
            results[mid].slot_chosen = slot
            results[mid].attempts += 1
            picks.setdefault(slot, []).append(mid)

        still_pending: list[int] = []
        for slot, contenders in picks.items():
            if len(contenders) == 1:
                results[contenders[0]].succeeded = True  # clean request, ACK
            else:
                for mid in contenders:  # collision: back off, window doubles
                    window = 2 ** (results[mid].attempts - 1)
                    results[mid].backoff_windows.append(window)
                    still_pending.append(mid)
        pending = still_pending

    return results


def _section(title: str) -> None:
    print(f"\n{title}\n" + "-" * 60)


def main() -> None:
    print("=" * 60)
    print("Cable TV -> HFC -> Spectrum Allocation toolkit")
    print("=" * 60)

    _section("North American cable spectrum (FDM plan)")
    rows = [
        ("Upstream data", "5-42 MHz", "upstream", "QPSK..QAM-128 + TCM"),
        ("FM radio", "88-108 MHz", "downstream", "broadcast FM"),
        ("TV channels", "54-550 MHz", "downstream", "6 MHz, analog/digital TV"),
        ("Downstream data", "550-750+ MHz", "downstream", "QAM-64 / QAM-256"),
    ]
    print(f"{'Band':<16}{'Frequency':<14}{'Dir':<12}{'Modulation'}")
    for name, freq, direction, mod in rows:
        print(f"{name:<16}{freq:<14}{direction:<12}{mod}")

    _section("Classifying sample frequencies")
    for f in (5.0, 38.0, 100.0, 200.0, 600.0):
        band = classify_frequency(f)
        print(f"{f:>6.1f} MHz -> {band.name:<16} ({band.direction})")

    _section("Downstream throughput per 6 MHz channel")
    print(f"{'Modulation':<12}{'raw Mbps':<12}{'net Mbps'}")
    for qam in ("QAM-64", "QAM-256"):
        t = downstream_throughput(qam)
        print(f"{qam:<12}{t['raw_mbps']:<12.1f}{t['net_mbps']:.1f}")
    bonded = bonded_throughput("QAM-256", channels=4)
    print(f"\nDOCSIS 3.0: 4 bonded QAM-256 channels -> {bonded:.0f} Mbps net")

    _section("Upstream contention: slotted ALOHA + binary exponential backoff")
    results = simulate_slotted_aloha(num_modems=8, num_request_minislots=4)
    succeeded = sum(1 for r in results if r.succeeded)
    total_attempts = sum(r.attempts for r in results)
    for r in results:
        status = "ACK" if r.succeeded else "DROP"
        windows = ",".join(str(w) for w in r.backoff_windows) or "-"
        print(
            f"modem {r.modem_id}: attempts={r.attempts} {status:<5}"
            f" backoff_windows=[{windows}]"
        )
    print(
        f"\n{succeeded}/{len(results)} modems registered in "
        f"{total_attempts} total request attempts."
    )
    print(
        "Backoff windows double (1,2,4,...) after each collision because "
        "modems cannot sense the medium (no CSMA/CD)."
    )


if __name__ == "__main__":
    main()
