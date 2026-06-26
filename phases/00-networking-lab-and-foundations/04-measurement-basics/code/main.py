#!/usr/bin/env python3
"""Latency / loss / jitter summarizer for network RTT samples.

Reads round-trip-time samples (the kind ``ping`` prints) and emits the same
distribution summary every real measurement tool produces: sample count,
min/avg/max, standard deviation, jitter, packet-loss rate, and a full
percentile ladder (p50/p90/p95/p99/p99.9).

The whole point of the lesson: the *mean* is blind to the *tail*. This script
prints both side by side so the gap is undeniable.

stdlib only. No network calls. Feed it a file of ``ping`` output, a file of
bare numbers, or run with no arguments for an embedded demonstration::

    python3 main.py                 # built-in skewed demo set
    python3 main.py ping-raw.txt    # parse real `ping -c N` output
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass

# `ping` prints e.g. "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.3 ms"
_TIME_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)
# Summary line: "100 packets transmitted, 98 received, 2% packet loss"
_LOSS_RE = re.compile(
    r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received", re.IGNORECASE
)

JITTER_ALPHA = 16  # RFC 3550 smoothing divisor for the running jitter estimate


@dataclass(frozen=True)
class Summary:
    """Immutable distribution summary for a set of RTT samples (milliseconds)."""

    n: int
    sent: int
    received: int
    minimum: float
    maximum: float
    mean: float
    stdev: float
    jitter: float
    percentiles: dict[float, float]

    @property
    def loss_rate(self) -> float:
        """Fraction of transmitted packets that never returned (0.0-1.0)."""
        if self.sent == 0:
            return 0.0
        return (self.sent - self.received) / self.sent


def parse_samples(text: str) -> tuple[list[float], int, int]:
    """Extract RTT samples plus (sent, received) counts from ping-like text.

    Falls back to parsing bare floating-point numbers (one per line) when no
    ``time=`` tokens are present. Returns (samples_ms, sent, received).
    """
    samples = [float(m) for m in _TIME_RE.findall(text)]

    if not samples:
        # Bare-number mode: one RTT per non-empty, non-comment line.
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                samples.append(float(stripped))
            except ValueError:
                continue

    loss_match = _LOSS_RE.search(text)
    if loss_match:
        sent = int(loss_match.group(1))
        received = int(loss_match.group(2))
    else:
        # No explicit loss line: assume every sample we have is a reply.
        sent = received = len(samples)
    return samples, sent, received


def percentile(sorted_samples: list[float], pct: float) -> float:
    """Percentile via linear interpolation (NIST / numpy "linear" method).

    ``pct`` is in [0, 100]. Requires a pre-sorted ascending list.
    """
    if not sorted_samples:
        raise ValueError("percentile of empty sample set")
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    rank = (pct / 100.0) * (len(sorted_samples) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_samples[low]
    frac = rank - low
    return sorted_samples[low] * (1 - frac) + sorted_samples[high] * frac


def jitter(samples: list[float]) -> float:
    """Mean absolute successive difference - a faithful jitter proxy.

    This is the simple cousin of the RFC 3550 interarrival jitter EMA
    (J += (|D| - J) / 16); for a static sample list the mean of |D| is the
    clearest single number to report.
    """
    if len(samples) < 2:
        return 0.0
    diffs = [abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))]
    return sum(diffs) / len(diffs)


def stdev(samples: list[float], mean: float) -> float:
    """Population standard deviation of the samples."""
    if len(samples) < 2:
        return 0.0
    variance = sum((x - mean) ** 2 for x in samples) / len(samples)
    return math.sqrt(variance)


def summarize(samples: list[float], sent: int, received: int) -> Summary:
    """Compute the full distribution summary from raw RTT samples."""
    if not samples:
        raise ValueError("no RTT samples to summarize")
    ordered = sorted(samples)
    mean = sum(samples) / len(samples)
    wanted = [50.0, 90.0, 95.0, 99.0, 99.9]
    pcts = {p: percentile(ordered, p) for p in wanted}
    return Summary(
        n=len(samples),
        sent=sent,
        received=received,
        minimum=ordered[0],
        maximum=ordered[-1],
        mean=mean,
        stdev=stdev(samples, mean),
        jitter=jitter(samples),  # order-sensitive: use original sequence
        percentiles=pcts,
    )


def bandwidth_delay_product(bits_per_sec: float, rtt_ms: float) -> float:
    """Bytes in flight needed to fill a pipe: BDP = bandwidth x RTT."""
    return bits_per_sec * (rtt_ms / 1000.0) / 8.0


def render(summary: Summary) -> str:
    """Format the summary as a human-readable report block."""
    lines: list[str] = []
    lines.append("=" * 52)
    lines.append("  RTT MEASUREMENT SUMMARY")
    lines.append("=" * 52)
    lines.append(f"  samples (n)   : {summary.n}")
    lines.append(f"  sent/received : {summary.sent}/{summary.received}")
    lines.append(f"  packet loss   : {summary.loss_rate * 100:.2f}%")
    lines.append("-" * 52)
    lines.append(f"  min  : {summary.minimum:8.2f} ms")
    lines.append(f"  mean : {summary.mean:8.2f} ms   <- the average that lies")
    lines.append(f"  max  : {summary.maximum:8.2f} ms")
    lines.append(f"  stdev: {summary.stdev:8.2f} ms")
    lines.append(f"  jitter: {summary.jitter:7.2f} ms   (mean abs successive diff)")
    lines.append("-" * 52)
    for pct, value in summary.percentiles.items():
        label = f"p{pct:g}"
        lines.append(f"  {label:6s}: {value:8.2f} ms")
    lines.append("-" * 52)
    tail_ratio = summary.percentiles[99.0] / summary.percentiles[50.0]
    lines.append(f"  p99/p50 ratio : {tail_ratio:.1f}x")
    if tail_ratio >= 3.0:
        lines.append("  -> heavy tail: suspect queueing / bufferbloat, not capacity")
    else:
        lines.append("  -> tail is contained relative to the median")
    lines.append("=" * 52)
    return "\n".join(lines)


# A deliberately right-skewed demo set: a tight ~40 ms floor with a few
# queueing-induced spikes into the hundreds of ms (the tail users feel).
_DEMO = (
    "PING demo (100 samples)\n"
    + "\n".join(
        f"64 bytes from 10.0.0.1: icmp_seq={i} ttl=57 time={rtt} ms"
        for i, rtt in enumerate(
            [39.1, 40.2, 41.0, 38.9, 42.3, 40.8, 39.7, 41.5, 40.1, 43.2] * 9
            + [712.4, 488.0, 39.5, 41.1, 805.7, 40.0, 612.3, 40.9, 41.4, 39.8],
            start=1,
        )
    )
    + "\n102 packets transmitted, 100 received, 1.96% packet loss\n"
)


def main() -> None:
    """Run a realistic demonstration of the RTT summarizer."""
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            text = handle.read()
        source = sys.argv[1]
    else:
        text = _DEMO
        source = "built-in skewed demo set"

    samples, sent, received = parse_samples(text)
    if not samples:
        print(f"No RTT samples found in {source}", file=sys.stderr)
        sys.exit(1)

    print(f"source: {source}\n")
    summary = summarize(samples, sent, received)
    print(render(summary))

    # Worked BDP example tied to the lesson: 1 Gbit/s link at the measured p50.
    link_bps = 1_000_000_000
    p50 = summary.percentiles[50.0]
    bdp = bandwidth_delay_product(link_bps, p50)
    print(
        f"\nBDP @ 1 Gbit/s x p50({p50:.1f} ms) = "
        f"{bdp / 1_000_000:.2f} MB must be in flight to fill the pipe."
    )
    window_64k = 65536
    capped = window_64k / (p50 / 1000.0)
    print(
        f"A 64 KB TCP window on this RTT caps a flow at "
        f"{capped / 1_000_000:.2f} MB/s regardless of link speed."
    )


if __name__ == "__main__":
    main()
