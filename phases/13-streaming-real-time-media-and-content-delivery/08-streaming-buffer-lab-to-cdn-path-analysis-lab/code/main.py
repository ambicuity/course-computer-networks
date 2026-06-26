#!/usr/bin/env python3
"""Streaming Buffer Lab + CDN Path Analysis Lab.

Stdlib only, no network calls. Demonstrates three things:

1. Playout buffer simulation: model a media streaming client that buffers
   packets before playout to mask network jitter. Tracks buffer level,
   rebuffering events, and playout continuity. Reproduces the textbook
   distinction between absolute delay (only affects start time) and jitter
   (variation in delay that must be masked by the buffer).

2. CDN path analysis: simulate DNS-based CDN edge selection (the textbook's
   "DNS redirection" method from Sec 7.5.3), cache hit/miss ratios, and
   the path from client -> edge -> origin. Models the distribution tree
   (origin -> edge nodes -> clients) with per-hop latency.

3. Combined: show how CDN edge selection and cache hits affect streaming
   buffer health - a cache hit at a nearby edge fills the buffer faster,
   reducing rebuffering; a cache miss that fetches from the origin across
   a high-latency path starves the buffer.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaPacket:
    seq: int
    arrival_time: float
    playout_time: float
    size_bytes: int


@dataclass
class BufferStats:
    initial_buffering_s: float = 0.0
    rebuffer_events: int = 0
    rebuffer_total_s: float = 0.0
    packets_played: int = 0
    packets_dropped_late: int = 0
    max_buffer_level: float = 0.0
    min_buffer_level: float = 1e9


def generate_packet_stream(
    num_packets: int,
    base_interval: float,
    jitter_ms: float,
    loss_rate: float,
    seed: int = 42,
) -> list[MediaPacket]:
    rng = random.Random(seed)
    packets: list[MediaPacket] = []
    t = 0.0
    for seq in range(num_packets):
        t += base_interval
        if rng.random() < loss_rate:
            continue
        jitter = rng.uniform(-jitter_ms / 1000, jitter_ms / 1000)
        arrival = t + jitter
        playout = seq * base_interval
        packets.append(MediaPacket(
            seq=seq,
            arrival_time=arrival,
            playout_time=playout,
            size_bytes=1400,
        ))
    return packets


def simulate_playout_buffer(
    packets: list[MediaPacket],
    initial_buffer_target_s: float,
    playout_rate: float,
) -> tuple[list[float], BufferStats]:
    stats = BufferStats()
    buffer_level = 0.0
    buffer_history: list[float] = []
    played = 0
    idx = 0
    clock = 0.0
    playout_started = False
    playout_clock = 0.0
    rebuffering = False
    rebuffer_start = 0.0

    while played < len(packets) or buffer_level > 0:
        while idx < len(packets) and packets[idx].arrival_time <= clock:
            buffer_level += 1.0
            stats.max_buffer_level = max(stats.max_buffer_level, buffer_level)
            idx += 1

        if not playout_started and buffer_level >= initial_buffer_target_s:
            playout_started = True
            stats.initial_buffering_s = clock
            playout_clock = clock

        if playout_started and not rebuffering:
            if clock >= playout_clock + 1.0 / playout_rate:
                if buffer_level >= 1.0:
                    buffer_level -= 1.0
                    played += 1
                    stats.packets_played += 1
                    playout_clock = clock
                else:
                    rebuffering = True
                    rebuffer_start = clock
                    stats.rebuffer_events += 1

        if rebuffering and buffer_level >= initial_buffer_target_s / 2:
            rebuffering = False
            stats.rebuffer_total_s += clock - rebuffer_start
            playout_clock = clock

        stats.min_buffer_level = min(stats.min_buffer_level, buffer_level)
        buffer_history.append(buffer_level)
        clock += 0.01

    if stats.min_buffer_level == 1e9:
        stats.min_buffer_level = 0.0
    return buffer_history, stats


def compute_rebuffering_ratio(stats: BufferStats, total_duration: float) -> float:
    if total_duration <= 0:
        return 0.0
    return stats.rebuffer_total_s / total_duration


@dataclass
class CDNode:
    name: str
    location: str
    ip: str
    latency_to_origin_ms: float
    cache: dict[str, float] = field(default_factory=dict)


@dataclass
class Client:
    name: str
    location: str
    ip: str
    latency_to_edges: dict[str, float] = field(default_factory=dict)


@dataclass
class CDNRequest:
    client: Client
    url: str
    timestamp: float


@dataclass
class CDNResult:
    edge_node: str
    cache_hit: bool
    path: list[str]
    total_latency_ms: float
    bytes_transferred: int


def build_cdn_topology() -> tuple[list[CDNode], list[Client], str]:
    origin = "origin-server.example.com"
    edges = [
        CDNode("edge-sydney", "Sydney, AU", "203.0.113.10", 180.0),
        CDNode("edge-boston", "Boston, US", "203.0.113.20", 15.0),
        CDNode("edge-amsterdam", "Amsterdam, NL", "203.0.113.30", 8.0),
        CDNode("edge-tokyo", "Tokyo, JP", "203.0.113.40", 120.0),
        CDNode("edge-saopaulo", "Sao Paulo, BR", "203.0.113.50", 110.0),
    ]
    clients = [
        Client("client-au", "Sydney, AU", "198.51.100.1", {
            "edge-sydney": 5, "edge-tokyo": 60, "edge-boston": 150,
            "edge-amsterdam": 250, "edge-saopaulo": 200,
        }),
        Client("client-us", "Boston, US", "198.51.100.2", {
            "edge-boston": 4, "edge-amsterdam": 70, "edge-sydney": 160,
            "edge-tokyo": 140, "edge-saopaulo": 100,
        }),
        Client("client-nl", "Amsterdam, NL", "198.51.100.3", {
            "edge-amsterdam": 3, "edge-boston": 72, "edge-sydney": 240,
            "edge-tokyo": 200, "edge-saopaulo": 180,
        }),
        Client("client-jp", "Tokyo, JP", "198.51.100.4", {
            "edge-tokyo": 5, "edge-sydney": 55, "edge-boston": 145,
            "edge-amsterdam": 210, "edge-saopaulo": 220,
        }),
        Client("client-br", "Sao Paulo, BR", "198.51.100.5", {
            "edge-saopaulo": 6, "edge-boston": 105, "edge-amsterdam": 175,
            "edge-sydney": 195, "edge-tokyo": 230,
        }),
    ]
    return edges, clients, origin


def dns_redirect(client: Client, edges: list[CDNode]) -> CDNode:
    best_edge: Optional[CDNode] = None
    best_latency = 1e9
    for edge in edges:
        latency = client.latency_to_edges.get(edge.name, 1e9)
        if latency < best_latency:
            best_latency = latency
            best_edge = edge
    assert best_edge is not None
    return best_edge


def serve_cdn_request(
    request: CDNRequest,
    edges: list[CDNode],
    origin: str,
    content_size_mb: float,
    cache_ttl_s: float,
) -> CDNResult:
    edge = dns_redirect(request.client, edges)
    client_to_edge = request.client.latency_to_edges[edge.name]
    url = request.url

    cached_time = edge.cache.get(url)
    cache_hit = cached_time is not None and (request.timestamp - cached_time) < cache_ttl_s

    path = [request.client.name, edge.name]
    if cache_hit:
        total_latency = client_to_edge
    else:
        path.append(origin)
        edge_to_origin = edge.latency_to_origin_ms
        total_latency = client_to_edge + edge_to_origin
        edge.cache[url] = request.timestamp

    return CDNResult(
        edge_node=edge.name,
        cache_hit=cache_hit,
        path=path,
        total_latency_ms=total_latency,
        bytes_transferred=int(content_size_mb * 1_000_000),
    )


def analyze_cdn_performance(
    edges: list[CDNode],
    clients: list[Client],
    origin: str,
    num_requests: int,
    seed: int = 42,
) -> dict[str, object]:
    rng = random.Random(seed)
    urls = [f"/video/{i}.mp4" for i in range(20)]
    results: list[CDNResult] = []
    for i in range(num_requests):
        client = rng.choice(clients)
        url = rng.choice(urls)
        req = CDNRequest(client=client, url=url, timestamp=float(i))
        result = serve_cdn_request(req, edges, origin, content_size_mb=5.0, cache_ttl_s=30.0)
        results.append(result)

    hits = sum(1 for r in results if r.cache_hit)
    misses = num_requests - hits
    avg_latency = sum(r.total_latency_ms for r in results) / num_requests
    hit_latency = sum(r.total_latency_ms for r in results if r.cache_hit) / max(hits, 1)
    miss_latency = sum(r.total_latency_ms for r in results if not r.cache_hit) / max(misses, 1)

    edge_counts: dict[str, int] = {}
    for r in results:
        edge_counts[r.edge_node] = edge_counts.get(r.edge_node, 0) + 1

    return {
        "total_requests": num_requests,
        "cache_hits": hits,
        "cache_misses": misses,
        "hit_ratio": hits / num_requests,
        "avg_latency_ms": avg_latency,
        "hit_latency_ms": hit_latency,
        "miss_latency_ms": miss_latency,
        "edge_distribution": edge_counts,
        "results": results,
    }


def simulate_streaming_over_cdn(
    client: Client,
    edges: list[CDNode],
    origin: str,
    num_packets: int,
    seed: int = 42,
) -> dict[str, object]:
    edge = dns_redirect(client, edges)
    client_to_edge = client.latency_to_edges[edge.name] / 1000.0
    rng = random.Random(seed)

    packets: list[MediaPacket] = []
    t = 0.0
    for seq in range(num_packets):
        is_cache_hit = rng.random() > 0.3
        if is_cache_hit:
            fetch_latency = client_to_edge
        else:
            fetch_latency = client_to_edge + edge.latency_to_origin_ms / 1000.0
        jitter = rng.uniform(-0.02, 0.02)
        arrival = t + fetch_latency + jitter
        playout = seq * 0.04
        packets.append(MediaPacket(
            seq=seq, arrival_time=arrival, playout_time=playout, size_bytes=1400,
        ))
        t += 0.04

    buffer_history, stats = simulate_playout_buffer(
        packets, initial_buffer_target_s=2.0, playout_rate=25.0,
    )
    total_duration = max(p.playout_time for p in packets)
    rebuffer_ratio = compute_rebuffering_ratio(stats, total_duration)

    return {
        "client": client.name,
        "edge": edge.name,
        "edge_latency_ms": client_to_edge * 1000,
        "cache_hit_rate": 0.7,
        "initial_buffering_s": stats.initial_buffering_s,
        "rebuffer_events": stats.rebuffer_events,
        "rebuffer_ratio": rebuffer_ratio,
        "packets_played": stats.packets_played,
        "packets_dropped_late": stats.packets_dropped_late,
        "max_buffer_level": stats.max_buffer_level,
        "min_buffer_level": stats.min_buffer_level,
    }


def main() -> None:
    print("=" * 70)
    print("Part 1: Playout Buffer Simulation")
    print("=" * 70)

    for jitter_label, jitter_ms in [("low (10ms)", 10), ("medium (50ms)", 50), ("high (150ms)", 150)]:
        packets = generate_packet_stream(
            num_packets=200, base_interval=0.04, jitter_ms=jitter_ms, loss_rate=0.02,
        )
        _, stats = simulate_playout_buffer(
            packets, initial_buffer_target_s=2.0, playout_rate=25.0,
        )
        total_dur = max(p.playout_time for p in packets)
        reb_ratio = compute_rebuffering_ratio(stats, total_dur)
        print(f"\n  Jitter: {jitter_label}")
        print(f"    Initial buffering:     {stats.initial_buffering_s:.2f}s")
        print(f"    Rebuffer events:       {stats.rebuffer_events}")
        print(f"    Rebuffering ratio:     {reb_ratio:.1%}")
        print(f"    Packets played:        {stats.packets_played}/{len(packets)}")
        print(f"    Max buffer level:      {stats.max_buffer_level:.1f} packets")
        print(f"    Min buffer level:      {stats.min_buffer_level:.1f} packets")

    print()
    print("=" * 70)
    print("Part 2: CDN Path Analysis - DNS Redirection")
    print("=" * 70)

    edges, clients, origin = build_cdn_topology()
    print(f"\n  Origin server: {origin}")
    print(f"  Edge nodes: {len(edges)}")
    for e in edges:
        print(f"    {e.name:20s} {e.location:18s} origin_latency={e.latency_to_origin_ms:.0f}ms")
    print(f"\n  Clients: {len(clients)}")

    print("\n  DNS Redirection (nearest edge per client):")
    for c in clients:
        edge = dns_redirect(c, edges)
        latency = c.latency_to_edges[edge.name]
        print(f"    {c.name:12s} ({c.location:14s}) -> {edge.name:20s}  {latency}ms")

    print()
    print("  Single request trace (client-nl fetches /video/3.mp4):")
    nl_client = next(c for c in clients if c.name == "client-nl")
    req = CDNRequest(client=nl_client, url="/video/3.mp4", timestamp=0.0)
    result = serve_cdn_request(req, edges, origin, content_size_mb=5.0, cache_ttl_s=30.0)
    print(f"    Path:   {' -> '.join(result.path)}")
    print(f"    Cache:  {'HIT' if result.cache_hit else 'MISS'}")
    print(f"    Latency: {result.total_latency_ms:.0f}ms")
    print(f"    Bytes:  {result.bytes_transferred:,}")

    req2 = CDNRequest(client=nl_client, url="/video/3.mp4", timestamp=1.0)
    result2 = serve_cdn_request(req2, edges, origin, content_size_mb=5.0, cache_ttl_s=30.0)
    print(f"\n    Second request (same URL, within TTL):")
    print(f"    Path:   {' -> '.join(result2.path)}")
    print(f"    Cache:  {'HIT' if result2.cache_hit else 'MISS'}")
    print(f"    Latency: {result2.total_latency_ms:.0f}ms")

    print()
    print("  Batch CDN performance (100 requests):")
    perf = analyze_cdn_performance(edges, clients, origin, num_requests=100)
    print(f"    Cache hit ratio:    {perf['hit_ratio']:.1%}  ({perf['cache_hits']} hits / {perf['cache_misses']} misses)")
    print(f"    Avg latency:        {perf['avg_latency_ms']:.0f}ms")
    print(f"    Hit latency:        {perf['hit_latency_ms']:.0f}ms")
    print(f"    Miss latency:       {perf['miss_latency_ms']:.0f}ms")
    print(f"    Edge distribution:")
    for edge_name, count in sorted(perf["edge_distribution"].items()):
        print(f"      {edge_name:20s}: {count} requests")

    print()
    print("=" * 70)
    print("Part 3: Streaming Quality vs CDN Edge Selection")
    print("=" * 70)
    print("\n  Simulating 200-packet streaming session per client:")
    print(f"  {'Client':14s} {'Edge':20s} {'EdgeLat':>8s} {'InitBuf':>8s} {'Rebuf#':>7s} {'Rebuf%':>7s} {'Played':>8s}")
    print(f"  {'-'*14} {'-'*20} {'-'*8} {'-'*8} {'-'*7} {'-'*7} {'-'*8}")

    for c in clients:
        result = simulate_streaming_over_cdn(c, edges, origin, num_packets=200, seed=42)
        print(
            f"  {result['client']:14s} {result['edge']:20s} "
            f"{result['edge_latency_ms']:7.0f}ms {result['initial_buffering_s']:7.2f}s "
            f"{result['rebuffer_events']:7d} {result['rebuffer_ratio']:6.1%} "
            f"{result['packets_played']:7d}/{200}"
        )

    print()
    print("  Key insight: clients routed to a nearby edge (low latency) experience")
    print("  fewer rebuffer events and a healthier buffer level. Cache misses that")
    print("  must fetch from the origin add latency that starves the playout buffer.")
    print("  This is why CDNs use DNS redirection to map clients to the nearest edge")


if __name__ == "__main__":
    main()
