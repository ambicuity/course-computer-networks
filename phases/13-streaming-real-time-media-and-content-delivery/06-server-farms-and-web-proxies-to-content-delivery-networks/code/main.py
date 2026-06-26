"""Lesson: Server Farms and Web Proxies to Content Delivery Networks.

This module simulates core building blocks of scalable content delivery:

1. Server farm load balancing (round-robin vs. least-connections).
2. A web proxy / CDN edge cache with an LRU eviction policy and hit/miss rates.
3. DNS-style CDN edge selection based on geographic (haversine) distance.
4. How cache hit ratio improves as cache size grows.
5. A comparison table summarising load-balancer behaviour and cache scaling.

All logic uses the Python standard library only; no network calls are made.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Iterable

# Reproducible simulations
random.seed(42)


@dataclass
class Server:
    """A backend server in a server farm."""

    name: str
    weight: int = 1
    active_connections: int = 0
    total_requests: int = 0


@dataclass
class Request:
    """A synthetic client request."""

    id: int
    duration: float


class LoadBalancer:
    """Simulate round-robin and least-connections load balancing."""

    def __init__(self, servers: list[Server]) -> None:
        self.servers = list(servers)
        self._rr_index = 0

    def round_robin(self) -> Server:
        """Select the next server in cyclic order."""
        server = self.servers[self._rr_index % len(self.servers)]
        self._rr_index += 1
        server.total_requests += 1
        return server

    def least_connections(self) -> Server:
        """Select the server with the fewest active connections."""
        server = min(self.servers, key=lambda s: s.active_connections)
        server.total_requests += 1
        return server

    def reset(self) -> None:
        """Clear counters for a fresh simulation."""
        self._rr_index = 0
        for server in self.servers:
            server.active_connections = 0
            server.total_requests = 0


def simulate_load_balancer(
    balancer: LoadBalancer,
    requests: list[Request],
    strategy: str,
) -> dict[str, float]:
    """Run a load-balancing simulation and return utilisation statistics.

    Args:
        balancer: Configured load balancer with backend servers.
        requests: Synthetic request workload.
        strategy: Either ``"round_robin"`` or ``"least_connections"``.

    Returns:
        A mapping of metric names to values, including max active
        connections, mean active connections, and request distribution.
    """
    balancer.reset()
    strategy_fn = balancer.round_robin if strategy == "round_robin" else balancer.least_connections

    # Assign requests and advance time to track concurrency.
    time = 0.0
    completion_heap: list[tuple[float, Server]] = []
    for request in requests:
        time += 1.0
        # Free any connections that completed before this request arrives.
        still_active: list[tuple[float, Server]] = []
        for finish_at, server in completion_heap:
            if finish_at <= time:
                server.active_connections -= 1
            else:
                still_active.append((finish_at, server))
        completion_heap = still_active

        server = strategy_fn()
        server.active_connections += 1
        completion_heap.append((time + request.duration, server))

    max_active = max(server.active_connections for server in balancer.servers)
    active_counts = [server.active_connections for server in balancer.servers]
    requests_per_server = [server.total_requests for server in balancer.servers]

    return {
        "strategy": strategy,
        "max_active": float(max_active),
        "mean_active": statistics.mean(active_counts),
        "stdev_active": statistics.stdev(active_counts) if len(active_counts) > 1 else 0.0,
        "min_requests": min(requests_per_server),
        "max_requests": max(requests_per_server),
        "request_stdev": statistics.stdev(requests_per_server)
        if len(requests_per_server) > 1
        else 0.0,
    }


class ProxyCache:
    """LRU web proxy / edge cache simulator.

    The cache stores content objects identified by string keys.  When the
    cache is full, the least-recently-accessed entry is evicted.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("Cache capacity must be at least 1")
        self.capacity = capacity
        self._store: OrderedDict[str, int] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def request(self, key: str, size: int = 1) -> bool:
        """Record a request for ``key`` and return True if it was a hit."""
        if key in self._store:
            self.hits += 1
            self._store.move_to_end(key)
            return True

        self.misses += 1
        if len(self._store) >= self.capacity:
            self._store.popitem(last=False)
        self._store[key] = size
        return False

    def hit_ratio(self) -> float:
        """Return the fraction of requests that were cache hits."""
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def reset(self) -> None:
        """Clear the cache and counters."""
        self._store.clear()
        self.hits = 0
        self.misses = 0


def generate_zipf_workload(
    keys: list[str],
    total_requests: int,
    alpha: float = 1.2,
) -> list[str]:
    """Generate a popularity-skewed request stream using a Zipf-like distribution."""
    weights = [1.0 / (i + 1) ** alpha for i in range(len(keys))]
    return random.choices(keys, weights=weights, k=total_requests)


def cache_size_sweep(
    keys: list[str],
    workload: list[str],
    sizes: Iterable[int],
) -> list[tuple[int, int, int, float]]:
    """Run the same workload against caches of increasing capacity.

    Returns rows of ``(capacity, hits, misses, hit_ratio)``.
    """
    cache = ProxyCache(capacity=1)
    results: list[tuple[int, int, int, float]] = []
    for capacity in sizes:
        cache.reset()
        cache.capacity = capacity
        for key in workload:
            cache.request(key)
        results.append((capacity, cache.hits, cache.misses, cache.hit_ratio()))
    return results


@dataclass
class EdgeLocation:
    """A CDN edge server at a geographic location."""

    name: str
    latitude: float
    longitude: float
    load: float = field(default=0.0)


@dataclass
class ClientLocation:
    """A client requesting content from a CDN."""

    name: str
    latitude: float
    longitude: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two lat/lon points."""
    earth_radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


def select_edge_server(
    client: ClientLocation,
    edges: list[EdgeLocation],
) -> tuple[EdgeLocation, float]:
    """Choose the closest CDN edge server to ``client`` by haversine distance.

    This mirrors DNS-based CDN redirection where a resolver returns the
    address of the nearest edge node.
    """
    best_edge = min(
        edges,
        key=lambda edge: haversine_km(
            client.latitude, client.longitude, edge.latitude, edge.longitude
        ),
    )
    distance = haversine_km(
        client.latitude, client.longitude, best_edge.latitude, best_edge.longitude
    )
    return best_edge, distance


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def print_load_balance_table(results: list[dict[str, float]]) -> None:
    """Print a comparison table for load-balancer simulations."""
    header = (
        f"{'Strategy':<18} "
        f"{'Max Active':>12} "
        f"{'Mean Active':>12} "
        f"{'Std Active':>12} "
        f"{'Req Range':>12} "
        f"{'Req StdDev':>12}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        req_range = f"{int(r['min_requests'])}-{int(r['max_requests'])}"
        print(
            f"{r['strategy']:<18} "
            f"{r['max_active']:>12.0f} "
            f"{r['mean_active']:>12.2f} "
            f"{r['stdev_active']:>12.2f} "
            f"{req_range:>12} "
            f"{r['request_stdev']:>12.2f}"
        )


def print_cache_table(rows: list[tuple[int, int, int, float]]) -> None:
    """Print a table showing cache hit ratio vs. capacity."""
    header = f"{'Capacity':>10} {'Hits':>10} {'Misses':>10} {'Hit Ratio':>12}"
    print(header)
    print("-" * len(header))
    for capacity, hits, misses, ratio in rows:
        print(f"{capacity:>10} {hits:>10} {misses:>10} {ratio:>11.2%}")


def main() -> None:
    """Run all lesson simulations and print results."""
    # ------------------------------------------------------------------
    # 1. Load balancing simulation
    # ------------------------------------------------------------------
    print_section("1. Server Farm Load Balancing")
    servers = [
        Server(name="server-a", weight=1),
        Server(name="server-b", weight=1),
        Server(name="server-c", weight=1),
    ]
    requests = [
        Request(i, duration=random.uniform(1.0, 8.0))
        for i in range(120)
    ]

    balancer = LoadBalancer(servers)
    rr_result = simulate_load_balancer(balancer, requests, "round_robin")
    lc_result = simulate_load_balancer(balancer, requests, "least_connections")
    print_load_balance_table([rr_result, lc_result])
    print(
        "\nObservation: least-connections keeps the active-connection count "
        "more balanced when request durations vary."
    )

    # ------------------------------------------------------------------
    # 2. Proxy / edge cache simulator
    # ------------------------------------------------------------------
    print_section("2. Web Proxy Cache (LRU)")
    content_keys = [f"video_{i:03d}.mp4" for i in range(50)]
    workload = generate_zipf_workload(content_keys, total_requests=1000, alpha=1.2)
    cache = ProxyCache(capacity=10)
    for key in workload:
        cache.request(key)
    print(f"Capacity:     {cache.capacity}")
    print(f"Hits:         {cache.hits}")
    print(f"Misses:       {cache.misses}")
    print(f"Hit ratio:    {cache.hit_ratio():.2%}")
    print(f"Cached items: {len(cache._store)}")

    # ------------------------------------------------------------------
    # 3. CDN edge selection by geographic distance
    # ------------------------------------------------------------------
    print_section("3. CDN Edge Selection (DNS Redirection)")
    edges = [
        EdgeLocation("Edge-NYC", 40.7128, -74.0060),
        EdgeLocation("Edge-LON", 51.5074, -0.1278),
        EdgeLocation("Edge-SIN", 1.3521, 103.8198),
        EdgeLocation("Edge-SYD", -33.8688, 151.2093),
    ]
    clients = [
        ClientLocation("Client-Boston", 42.3601, -71.0589),
        ClientLocation("Client-Berlin", 52.5200, 13.4050),
        ClientLocation("Client-Tokyo", 35.6762, 139.6503),
        ClientLocation("Client-CapeTown", -33.9249, 18.4241),
    ]
    for client in clients:
        edge, distance = select_edge_server(client, edges)
        print(
            f"{client.name:<15} -> {edge.name:<12} "
            f"({distance:,.0f} km via haversine)"
        )

    # ------------------------------------------------------------------
    # 4. Cache hit ratio improvement as cache size grows
    # ------------------------------------------------------------------
    print_section("4. Cache Hit Ratio vs. Cache Size")
    sizes = [5, 10, 20, 30, 40, 50]
    sweep = cache_size_sweep(content_keys, workload, sizes)
    print_cache_table(sweep)
    print("\nObservation: hit ratio rises quickly, then plateaus as the cache")
    print("approaches the working-set size.")

    # ------------------------------------------------------------------
    # 5. Combined comparison table
    # ------------------------------------------------------------------
    print_section("5. Summary Comparison")
    print("Load balancing strategies:")
    print_load_balance_table([rr_result, lc_result])
    print("\nCache scaling:")
    print_cache_table(sweep)
    print(
        "\nTakeaway: server farms spread requests across backends, proxies "
        "and CDN edge caches reduce origin load and latency, and DNS-based "
        "redirection steers clients to the closest edge."
    )


if __name__ == "__main__":
    main()
