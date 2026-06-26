from __future__ import annotations

"""Content and Internet Traffic.

Demonstrates Internet traffic composition modelling, bandwidth fraction
calculation, content popularity using a Zipf distribution, and the Pareto
principle (80/20 rule) for content access. Only the Python standard library is
used.
"""

import math
import random
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TrafficCategory:
    """A single category of Internet traffic in a given year."""

    name: str
    share_percent: float
    bandwidth_gbps: float


@dataclass(frozen=True)
class YearlyComposition:
    """Traffic composition for one year."""

    year: int
    total_gbps: float
    categories: tuple[TrafficCategory, ...]

    def __post_init__(self) -> None:
        total_share = sum(cat.share_percent for cat in self.categories)
        if not math.isclose(total_share, 100.0, abs_tol=0.1):
            raise ValueError(f"category shares must sum to ~100%, got {total_share}")
        total_bw = sum(cat.bandwidth_gbps for cat in self.categories)
        if not math.isclose(total_bw, self.total_gbps, rel_tol=1e-9):
            raise ValueError("category bandwidths must sum to the total bandwidth")


def build_composition_table(
    years: Iterable[int],
    total_gbps_per_year: Iterable[float],
    shares_per_year: Iterable[dict[str, float]],
) -> list[YearlyComposition]:
    """Build a traffic composition table across years.

    Args:
        years: Years to model.
        total_gbps_per_year: Total traffic bandwidth for each year.
        shares_per_year: Mapping from category name to share percentage for
            each year.

    Returns:
        A list of yearly compositions ordered by the input years.
    """
    table: list[YearlyComposition] = []
    for year, total, shares in zip(
        years, total_gbps_per_year, shares_per_year, strict=True
    ):
        categories = tuple(
            TrafficCategory(
                name=name,
                share_percent=share,
                bandwidth_gbps=bandwidth_fraction(total, share),
            )
            for name, share in shares.items()
        )
        table.append(YearlyComposition(year=year, total_gbps=total, categories=categories))
    return table


def bandwidth_fraction(total_gbps: float, share_percent: float) -> float:
    """Return the bandwidth consumed by a category given its share."""
    if total_gbps < 0:
        raise ValueError("total bandwidth must be non-negative")
    if not 0.0 <= share_percent <= 100.0:
        raise ValueError("share percent must be between 0 and 100")
    return total_gbps * (share_percent / 100.0)


def zipf_popularity(rank: int, exponent: float = 1.0, base: float = 1.0) -> float:
    """Return relative popularity of content ranked ``rank`` using Zipf's law.

    Args:
        rank: 1-based popularity rank.
        exponent: Zipf exponent, often near 1.0 for natural text / content.
        base: Scaling constant.

    Returns:
        Relative popularity score. Higher-ranked items receive larger scores.
    """
    if rank < 1:
        raise ValueError("rank must be at least 1")
    if exponent <= 0:
        raise ValueError("exponent must be positive")
    return base / (rank ** exponent)


def simulate_zipf_requests(
    num_items: int,
    num_requests: int,
    exponent: float = 1.0,
    seed: int | None = None,
) -> list[tuple[int, float]]:
    """Simulate requests to ``num_items`` items following a Zipf distribution.

    Args:
        num_items: Number of distinct content items.
        num_requests: Number of requests to draw.
        exponent: Zipf exponent controlling concentration of popularity.
        seed: Optional random seed for reproducibility.

    Returns:
        A list of ``(item_index, popularity)`` pairs for each item, sorted by
        descending popularity.
    """
    if num_items < 1:
        raise ValueError("num_items must be positive")
    if num_requests < 0:
        raise ValueError("num_requests must be non-negative")
    rng = random.Random(seed)
    weights = [zipf_popularity(i, exponent=exponent) for i in range(1, num_items + 1)]
    population = list(range(num_items))
    counts = [0] * num_items
    for _ in range(num_requests):
        chosen = rng.choices(population, weights=weights, k=1)[0]
        counts[chosen] += 1
    popularity = [
        (item, count / num_requests) if num_requests else (item, 0.0)
        for item, count in enumerate(counts)
    ]
    popularity.sort(key=lambda pair: pair[1], reverse=True)
    return popularity


def pareto_80_20_fraction(popularity: list[tuple[int, float]]) -> float:
    """Return the fraction of items needed to reach ~80% of total access.

    Args:
        popularity: List of ``(item_index, popularity)`` pairs sorted by
            descending popularity.

    Returns:
        Fraction of the total items that account for roughly 80% of accesses.
    """
    total = sum(score for _, score in popularity)
    if total == 0.0:
        return 0.0
    cumulative = 0.0
    items_needed = 0
    for _, score in popularity:
        cumulative += score
        items_needed += 1
        if cumulative >= 0.80 * total:
            break
    return items_needed / len(popularity)


def print_composition_table(table: list[YearlyComposition]) -> None:
    """Print a formatted table of traffic composition across years."""
    if not table:
        print("No traffic composition data to display.")
        return

    header = ["Year", "Total (Gbps)"]
    for cat in table[0].categories:
        header.append(f"{cat.name} %")
        header.append(f"{cat.name} Gbps")
    print(" | ".join(header))
    print("-" * (len(" | ".join(header)) + 8))
    for comp in table:
        row = [str(comp.year), f"{comp.total_gbps:.1f}"]
        for cat in comp.categories:
            row.append(f"{cat.share_percent:.1f}")
            row.append(f"{cat.bandwidth_gbps:.2f}")
        print(" | ".join(row))


def main() -> None:
    """Run the content and Internet traffic demonstration."""
    # 1. Model traffic composition over time (Web vs P2P vs Video vs Other).
    years = [2010, 2015, 2020, 2025]
    totals = [250.0, 500.0, 1000.0, 2000.0]
    shares = [
        {"Web": 40.0, "P2P": 35.0, "Video": 15.0, "Other": 10.0},
        {"Web": 35.0, "P2P": 25.0, "Video": 30.0, "Other": 10.0},
        {"Web": 25.0, "P2P": 15.0, "Video": 50.0, "Other": 10.0},
        {"Web": 20.0, "P2P": 10.0, "Video": 65.0, "Other": 5.0},
    ]
    table = build_composition_table(years, totals, shares)

    # 5. Print a traffic composition table across years.
    print("Internet Traffic Composition Over Time")
    print("=" * 70)
    print_composition_table(table)
    print()

    # 2. Calculate bandwidth fractions given total traffic and share percentages.
    total = 1000.0
    video_share = 53.0
    print(f"For {total:.0f} Gbps total traffic, video at {video_share}% = "
          f"{bandwidth_fraction(total, video_share):.2f} Gbps")
    print()

    # 3. Simulate content popularity using a Zipf distribution.
    # 4. Show the Pareto principle (80/20 rule) for content access.
    num_items = 100
    num_requests = 100_000
    exponent = 1.1
    popularity = simulate_zipf_requests(
        num_items=num_items,
        num_requests=num_requests,
        exponent=exponent,
        seed=42,
    )

    print("Content Popularity (Zipf distribution)")
    print("=" * 70)
    print(f"Top 10 items out of {num_items} account for:")
    top_10_share = sum(score for _, score in popularity[:10])
    print(f"  {top_10_share * 100:.1f}% of all requests")
    print()

    fraction = pareto_80_20_fraction(popularity)
    print("Pareto Principle Check (80/20 rule)")
    print("=" * 70)
    print(f"Items needed for 80% of traffic: {fraction * 100:.1f}%")
    print()

    print("Top 5 content items by request share:")
    for rank, (item, score) in enumerate(popularity[:5], start=1):
        print(f"  {rank}. item-{item}: {score * 100:.2f}%")


if __name__ == "__main__":
    main()
