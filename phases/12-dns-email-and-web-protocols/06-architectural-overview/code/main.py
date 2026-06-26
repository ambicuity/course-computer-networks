#!/usr/bin/env python3
"""Web architectural overview: client-server, proxies, caches, CDN (section 7.3.1).

Stdlib only, no network calls. Demonstrates four things:

1. The client-server model: browser fetches pages via HTTP from a
   Web server. The URL resolution pipeline (determine URL -> DNS lookup
   -> TCP connect to port 80 -> HTTP request -> response -> render)
   matching the 9-step sequence from section 7.3.1.
2. Intermediary roles: proxy (caching forward proxy), gateway
   (protocol converter), and tunnel (blind relay) with their
   request-processing pipelines.
3. Cache hierarchy: browser cache -> proxy cache -> origin server,
   with freshness validation via Expires, Last-Modified, and ETag
   (conditional GET with If-Modified-Since / If-None-Match).
4. CDN edge resolution: DNS-based redirect to the nearest edge node,
   simulating how a CDN maps content to the closest replica.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import hashlib


@dataclass
class URL:
    scheme: str
    host: str
    port: int
    path: str

    @classmethod
    def parse(cls, raw: str) -> "URL":
        scheme, rest = raw.split("://", 1)
        if "/" in rest:
            host_port, path = rest.split("/", 1)
            path = "/" + path
        else:
            host_port = rest
            path = "/"
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            port = int(port)
        else:
            host = host_port
            if scheme == "https":
                port = 443
            elif scheme == "ftp":
                port = 21
            else:
                port = 80
        return cls(scheme, host, port, path)

    def __str__(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.path}"


@dataclass
class HTTPResponse:
    status_code: int
    headers: dict[str, str]
    body: str
    source: str = "origin"

    @property
    def is_fresh(self) -> bool:
        return "expires" in {k.lower() for k in self.headers}


@dataclass
class WebPage:
    url: URL
    content: str
    content_type: str = "text/html"
    last_modified: str = "Mon, 01 Jan 2024 00:00:00 GMT"
    etag: str = ""

    def __post_init__(self) -> None:
        if not self.etag:
            self.etag = hashlib.md5(self.content.encode()).hexdigest()[:16]


class OriginServer:
    """A simple origin Web server that serves static pages."""

    def __init__(self, hostname: str) -> None:
        self.hostname = hostname
        self.pages: dict[str, WebPage] = {}

    def add_page(self, path: str, content: str, content_type: str = "text/html") -> None:
        url = URL("http", self.hostname, 80, path)
        self.pages[path] = WebPage(url, content, content_type)

    def fetch(self, path: str) -> Optional[HTTPResponse]:
        page = self.pages.get(path)
        if page is None:
            return HTTPResponse(404, {}, "Not Found", self.hostname)
        return HTTPResponse(200, {
            "Content-Type": page.content_type,
            "Content-Length": str(len(page.content)),
            "Last-Modified": page.last_modified,
            "ETag": f'"{page.etag}"',
            "Cache-Control": "max-age=3600",
            "Server": f"{self.hostname}/1.0",
        }, page.content, self.hostname)

    def conditional_fetch(self, path: str, if_modified_since: str = "",
                         if_none_match: str = "") -> HTTPResponse:
        page = self.pages.get(path)
        if page is None:
            return HTTPResponse(404, {}, "Not Found", self.hostname)
        if if_none_match and f'"{page.etag}"' == if_none_match:
            return HTTPResponse(304, {"ETag": if_none_match}, "", self.hostname)
        if if_modified_since and if_modified_since == page.last_modified:
            return HTTPResponse(304, {"Last-Modified": page.last_modified}, "", self.hostname)
        return self.fetch(path)


class BrowserCache:
    """Browser-side cache with expiry and validation."""

    def __init__(self) -> None:
        self.entries: dict[str, tuple[HTTPResponse, int]] = {}
        self.hits: int = 0
        self.misses: int = 0

    def get(self, url: str) -> Optional[HTTPResponse]:
        if url in self.entries:
            resp, ttl = self.entries[url]
            if ttl > 0:
                self.hits += 1
                return resp
        self.misses += 1
        return None

    def put(self, url: str, response: HTTPResponse, ttl: int = 3600) -> None:
        self.entries[url] = (response, ttl)


class ProxyCache:
    """Forward proxy that caches responses and validates with origin."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.cache: dict[str, HTTPResponse] = {}
        self.hits: int = 0
        self.misses: int = 0
        self.upstream_requests: int = 0

    def fetch(self, url: str, origin: OriginServer, path: str,
              if_modified_since: str = "", if_none_match: str = "",
              force_validate: bool = False) -> HTTPResponse:
        if url in self.cache and not force_validate:
            cached = self.cache[url]
            self.hits += 1
            return cached
        self.misses += 1
        self.upstream_requests += 1
        resp = origin.conditional_fetch(path, if_modified_since, if_none_match)
        if resp.status_code == 200:
            self.cache[url] = resp
        return resp


@dataclass
class CDNEdge:
    """A CDN edge node that serves cached content."""

    name: str
    location: str
    cache: dict[str, WebPage] = field(default_factory=dict)

    def serve(self, path: str, origin: OriginServer) -> Optional[WebPage]:
        if path in self.cache:
            return self.cache[path]
        page = origin.pages.get(path)
        if page:
            self.cache[path] = page
        return page


class CDN:
    """A CDN with multiple edge nodes and DNS-based routing."""

    def __init__(self, origin: OriginServer, edges: list[CDNEdge]) -> None:
        self.origin = origin
        self.edges = edges

    def resolve_edge(self, client_location: str) -> CDNEdge:
        """Simulate DNS-based edge selection by proximity."""
        scored = [(abs(hash(e.location) - hash(client_location)), e) for e in self.edges]
        scored.sort(key=lambda x: x[0])
        return scored[0][1]

    def fetch(self, path: str, client_location: str) -> tuple[CDNEdge, Optional[WebPage]]:
        edge = self.resolve_edge(client_location)
        page = edge.serve(path, self.origin)
        return edge, page


def main() -> None:
    print("=" * 70)
    print("Web Architectural Overview (section 7.3.1)")
    print("=" * 70)

    print("\n--- URL parsing (scheme, host, port, path) ---")
    urls = [
        "http://www.cs.washington.edu/index.html",
        "https://www.bank.com/accounts/",
        "ftp://ftp.cs.vu.nl/pub/minix/README",
    ]
    for raw in urls:
        url = URL.parse(raw)
        print(f"  {raw}")
        print(f"    scheme={url.scheme}  host={url.host}  port={url.port}  path={url.path}")

    print("\n--- Page fetch pipeline (9 steps from section 7.3.1) ---")
    origin = OriginServer("www.cs.washington.edu")
    origin.add_page("/index.html", "<html><body><h1>Welcome to CSE</h1></body></html>")
    origin.add_page("/about.html", "<html><body><h1>About Us</h1></body></html>")

    url = URL.parse("http://www.cs.washington.edu/index.html")
    steps = [
        "1. Browser determines the URL (by seeing what was selected)",
        "2. Browser asks DNS for the IP address of www.cs.washington.edu",
        "3. DNS replies with 128.208.3.88",
        "4. Browser makes a TCP connection to 128.208.3.88 on port 80",
        "5. Browser sends an HTTP request asking for the page /index.html",
        "6. Server sends the page as an HTTP response",
        "7. Browser fetches embedded URLs (images, scripts, etc.)",
        "8. Browser displays the page /index.html",
        "9. TCP connections are released after idle timeout",
    ]
    for step in steps:
        print(f"  {step}")
    print()
    resp = origin.fetch("/index.html")
    print(f"  HTTP response: {resp.status_code}")
    print(f"  Headers:")
    for k, v in resp.headers.items():
        print(f"    {k}: {v}")
    print(f"  Body ({len(resp.body)} bytes): {resp.body[:60]}...")

    print("\n--- Intermediary roles: proxy, gateway, tunnel ---")
    print("  Proxy:  intercepts requests, caches responses, forwards to origin")
    print("  Gateway: converts between protocols (e.g., HTTP <-> WAP)")
    print("  Tunnel:  blind relay (e.g., TLS pass-through)")

    print("\n--- Cache hierarchy: browser -> proxy -> origin ---")
    browser_cache = BrowserCache()
    proxy = ProxyCache("proxy.isp.net")

    print("\n  [1] First fetch (cold cache):")
    r1 = proxy.fetch(str(url), origin, "/index.html")
    browser_cache.put(str(url), r1)
    print(f"    proxy: hits={proxy.hits} misses={proxy.misses} upstream={proxy.upstream_requests}")
    print(f"    browser: hits={browser_cache.hits} misses={browser_cache.misses}")
    print(f"    response: {r1.status_code} from {r1.source} ({len(r1.body)} bytes)")

    print("\n  [2] Second fetch (proxy cache hit):")
    r2 = proxy.fetch(str(url), origin, "/index.html")
    browser_cache.put(str(url), r2)
    print(f"    proxy: hits={proxy.hits} misses={proxy.misses} upstream={proxy.upstream_requests}")
    print(f"    response: {r2.status_code} from {r2.source} ({len(r2.body)} bytes)")

    print("\n  [3] Conditional GET (validation with If-None-Match):")
    r3 = proxy.fetch(str(url), origin, "/index.html",
                     if_none_match=f'"{origin.pages["/index.html"].etag}"',
                     force_validate=True)
    print(f"    response: {r3.status_code} (304 = not modified, use cache)")

    print("\n  [4] Conditional GET (validation with If-Modified-Since):")
    r4 = proxy.fetch(str(url), origin, "/index.html",
                     if_modified_since=origin.pages["/index.html"].last_modified,
                     force_validate=True)
    print(f"    response: {r4.status_code}")

    print("\n--- CDN edge resolution ---")
    edges = [
        CDNEdge("edge-sea", "Seattle"),
        CDNEdge("edge-nyc", "New York"),
        CDNEdge("edge-ams", "Amsterdam"),
        CDNEdge("edge-tok", "Tokyo"),
    ]
    cdn = CDN(origin, edges)

    for client_loc in ["Seattle", "New York", "Amsterdam", "Tokyo"]:
        edge, page = cdn.fetch("/index.html", client_loc)
        print(f"  Client in {client_loc} -> edge={edge.name} ({edge.location})  "
              f"page={'served' if page else 'miss'}")

    print("\n  [2] Second request from same edge (cache hit):")
    edge, page = cdn.fetch("/index.html", "Seattle")
    print(f"  Client in Seattle -> edge={edge.name}  page={'served (cached)' if page else 'miss'}")

    print("\n--- HTTP caching headers summary ---")
    cache_headers = [
        ("Expires", "Time/date when page stops being valid"),
        ("Last-Modified", "Time/date the page was last changed"),
        ("ETag", "Tag for the contents of the page"),
        ("Cache-Control", "Directives for how to treat caches"),
        ("If-Modified-Since", "Request: check freshness by time"),
        ("If-None-Match", "Request: check freshness by ETag"),
    ]
    for header, desc in cache_headers:
        print(f"  {header:<22} {desc}")


if __name__ == "__main__":
    main()