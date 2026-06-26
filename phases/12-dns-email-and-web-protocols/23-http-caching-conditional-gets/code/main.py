#!/usr/bin/env python3
"""HTTP cache freshness + conditional GET simulator (RFC 7234 / RFC 7232).

Models the cache's two strategies: serve-stale-if-fresh and revalidate-with-
If-None-Match. Walks through a sequence of client requests at increasing
times and reports what happens at each one (fresh, revalidate 304, full
200). Includes a Cache-Control directive parser.

Run with `python3 main.py`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class CachedResponse:
    body: bytes
    etag: str
    cache_control: str = "max-age=300"
    vary: str = ""
    date: int = 0

    def max_age(self) -> int:
        for d in parse_cache_control(self.cache_control):
            if d.lower().startswith("max-age="):
                try:
                    return int(d.split("=", 1)[1])
                except ValueError:
                    return 0
        return 0

    def is_fresh(self, now: int) -> bool:
        age = max(0, now - self.date)
        return age < self.max_age()


def parse_cache_control(value: str) -> List[str]:
    return [d.strip() for d in value.split(",") if d.strip()]


def compute_etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:16] + '"'


@dataclass
class Cache:
    responses: Dict[str, CachedResponse] = field(default_factory=dict)
    served_304: int = 0
    served_fresh: int = 0
    served_full: int = 0

    def get_or_revalidate(self, key: str, server_body: bytes, now: int, client_etag: Optional[str]) -> Tuple[str, bytes]:
        cached = self.responses.get(key)
        server_etag = compute_etag(server_body)
        if cached is None:
            cached = CachedResponse(body=server_body, etag=server_etag, date=now)
            self.responses[key] = cached
            self.served_full += 1
            return "200", server_body
        if cached.is_fresh(now):
            self.served_fresh += 1
            return "fresh", cached.body
        if client_etag is not None and client_etag == cached.etag:
            cached.date = now
            self.served_304 += 1
            return "304", b""
        cached.body = server_body
        cached.etag = server_etag
        cached.date = now
        self.served_full += 1
        return "200", server_body


def simulate(now_steps: List[Tuple[str, int, Optional[str]]]) -> List[str]:
    cache = Cache()
    server_body = b"hello world"
    out: List[str] = []
    for label, t, client_etag in now_steps:
        verdict, body = cache.get_or_revalidate("https://example.com/", server_body, t, client_etag)
        size = len(body) if body else 0
        out.append(f"  {label:<24} t={t:<5} -> {verdict:<6} bytes={size}")
    out.append(
        f"  totals: full 200s={cache.served_full}  "
        f"fresh no-contact={cache.served_fresh}  304 revalidations={cache.served_304}"
    )
    return out


def main() -> None:
    print("=" * 64)
    print("HTTP CACHING + CONDITIONAL GETS  --  RFC 7234 / 7232")
    print("=" * 64)

    print("\nCache-Control directives parsed:")
    for value in (
        "max-age=300",
        "no-cache, max-age=0",
        "no-store",
        "private, max-age=60",
        "public, s-maxage=600, must-revalidate",
        "max-age=86400, immutable",
    ):
        print(f"  '{value}' -> {parse_cache_control(value)}")

    print("\nETag of 'hello world' (sha256 prefix):")
    print(f"  {compute_etag(b'hello world')}")

    print("\nSimulated client over time (max-age=300):")
    steps = [
        ("first visit",          0,    None),
        ("+60s (fresh)",         60,   None),
        ("+400s (past max-age)", 400,  None),
        ("revalidate +etag",     400,  compute_etag(b"hello world")),
        ("another +400s",        800,  compute_etag(b"hello world")),
    ]
    for line in simulate(steps):
        print(line)


if __name__ == "__main__":
    main()
