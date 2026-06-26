# HTTP Caching and Conditional GETs

> HTTP caching (RFC 7234) lets a client reuse a previous response without contacting the origin server at all, or contact it just to ask "is this still fresh?". The first strategy is **freshness** — the response carries `Cache-Control: max-age=N` (or `Expires:`) and the client computes `Age` against the response's `Date:`. If `Age < max-age`, the cached copy is served directly. The second strategy is **validation** — the client has a stored `ETag:` and `Last-Modified:` from the original response and on the next request sends `If-None-Match:` and `If-Modified-Since:`. If the origin server's current representation matches, it replies `304 Not Modified` with no body; the client reuses its cached body. Together these two strategies eliminate most redundant bytes on the Web. The `Vary:` header tells caches which request headers (typically `Accept-Encoding`, `Accept-Language`) influenced the response so a Spanish response is not served to a French client. `Cache-Control: no-store` forbids storage entirely (use it for personalized or sensitive data); `Cache-Control: no-cache` allows storage but forces revalidation; `private` and `public` decide whether shared caches may store the response.

**Type:** Build
**Languages:** Python, shell
**Prerequisites:** Phase 12 lessons on HTTP methods, headers, and a real `curl`
**Time:** ~90 minutes

## Learning Objectives

- Compute whether a cached response is fresh by comparing `Age` against `Cache-Control: max-age`.
- Send a conditional GET with `If-None-Match` and `If-Modified-Since` and read the resulting `304 Not Modified`.
- Distinguish `Cache-Control: no-store` from `no-cache` and explain when each is appropriate.
- Read a `Vary:` header and predict which request header values must match for a cache hit.
- Author a server response that issues a strong ETag, an `Expires:` timestamp, and the right `Vary` for an Accept-Encoding-driven response.
- Reason about the long tail of cacheable vs uncacheable resources and why the long tail dominates cache hit rates.

## The Problem

You are paying for bandwidth and you notice the same images are downloaded on every page load. The browser *could* cache them, but the server returns `Cache-Control: no-cache` or no caching headers at all, so the browser always revalidates. Or worse: the server returns a `Last-Modified:` but no `ETag:`, so the browser sends `If-Modified-Since` and gets a 200 anyway because the server's clock is slightly off. Or: the server returns `Vary: User-Agent` and the cache stores one copy per user agent, exploding cache storage.

The trap is treating cache headers as automatic. They are not. They are an explicit contract between origin and client, and getting them wrong loses either bandwidth (over-cache misses) or correctness (stale bytes).

## The Concept

### Freshness: `Cache-Control: max-age` and `Expires`

`Cache-Control: max-age=N` says: this response is fresh for `N` seconds from the `Date:` header's time. The cache computes `Age = now - Date`; if `Age < max-age`, the cached body is served without contacting the origin. `Expires: Thu, 25 Jun 2026 15:00:00 GMT` is the legacy absolute equivalent. RFC 7234 prefers `Cache-Control` because relative times survive clock skew.

The `s-maxage=N` directive is the same idea but for **shared** caches (CDNs, proxies). It overrides `max-age` for shared caches only.

### Validation: `ETag` and `If-None-Match`

`ETag: "v1"` (or `"5e9c1a3a-1f0"`) is an opaque tag the server attaches to a response, derived from the resource content. On the next request, the client sends `If-None-Match: "v1"`. If the resource still has that tag, the server replies `304 Not Modified` with no body — the client keeps its cached body. ETag is also useful for byte-level range requests (RFC 7233): a client doing a resume download can revalidate the partially-downloaded file.

ETag values are **strong** if they identify the exact byte sequence, **weak** if they identify semantic equivalence (prefixed with `W/`, e.g., `W/"v1"`). Weak ETags are useful when the server wants to consider gzip vs non-gzip as semantically equivalent.

### Validation: `Last-Modified` and `If-Modified-Since`

`Last-Modified: Thu, 25 Jun 2026 13:00:00 GMT` says when the resource was last changed. The client echoes it as `If-Modified-Since` on the next request. The server compares: if the resource's `Last-Modified` is unchanged, it returns `304`. If-Modified-Since has second-level resolution (HTTP date format), so sub-second edits are invisible to it.

### The freshness+validation dance

A cache can combine both: when the cached copy is past `max-age`, it can either refetch the whole thing or **revalidate**. Revalidation is a conditional request with both `If-None-Match` and `If-Modified-Since`. If the server returns 304, the cache keeps the body and resets its freshness timer for another `max-age` interval. This is sometimes called "stale-while-revalidate".

### `Cache-Control` directives (RFC 7234 §5.2)

| Directive | Meaning |
|---|---|
| `max-age=N` | Fresh for N seconds |
| `s-maxage=N` | Same as max-age but for shared caches only |
| `no-store` | Do not store at all (sensitive data) |
| `no-cache` | Store, but always revalidate before serving |
| `private` | Only the end-user's cache may store (not shared) |
| `public` | Any cache may store, even if response would normally be private |
| `must-revalidate` | Once stale, do not serve stale — must revalidate or 504 |
| `immutable` | The body will not change during freshness lifetime (RFC 8246) |
| `stale-while-revalidate=N` | Serve stale for up to N seconds while revalidating in background |
| `stale-if-error=N` | Serve stale for up to N seconds if revalidation fails (RFC 5861) |

### `Vary` and cache key composition

`Vary: Accept-Encoding` tells the cache: "the response differs depending on `Accept-Encoding`; do not serve a gzip response to a client that sent no `Accept-Encoding`". The cache key is `method + URL + Vary headers' values`. Over-broad `Vary` (e.g., `Vary: User-Agent`) fragments the cache into many small buckets; under-broad `Vary` causes correctness bugs. Common practice: `Vary: Accept-Encoding` for compressed responses, `Vary: Accept-Language` for localized content.

### Heuristic freshness

When a response has no `Cache-Control` or `Expires`, caches may apply heuristic freshness: typically `0.1 * (Date - Last-Modified)` capped at 24 hours. Heuristics are a fallback, not a contract — origin servers should always set explicit freshness when they want it.

### The long tail

Cache hit rates depend on Zipfian access distributions: a few popular items get most of the traffic, a long tail of unique items gets the rest. Even a large cache only captures the head; the long tail goes to the origin on every request. The lesson: caching helps most for your top 100 resources, less for the rest.

### Private vs shared caches

| Cache | Scope | Examples |
|---|---|---|
| Private | One user | Browser, mobile app |
| Shared | Many users | CDN, corporate proxy |

A shared cache must respect `Cache-Control: private` (do not store) and `Authorization:` headers (do not store unless explicitly allowed). A private cache can store anything except `no-store`.

### Negative caching

A 404 or 410 response can be cached briefly to dampen typos and bots. `Cache-Control: max-age=60` on error responses is common. A 500 or 503 is generally not cached because the cause is often transient.

## Build It

1. Run `code/main.py` to model freshness and validation against a sample resource and a series of cached responses.
2. Issue `curl -I https://example.com/` and identify `Cache-Control`, `Expires`, `Last-Modified`, `ETag`, `Vary`.
3. Send a request, capture the `ETag`, then send `curl -H 'If-None-Match: "<etag>"' -i https://example.com/` and observe the 304.
4. Issue `curl -H 'Cache-Control: no-cache' -i https://example.com/` and observe the response still carries its own caching headers (the request `Cache-Control: no-cache` only forces revalidation).
5. Capture a `tcpdump -w cache.pcap tcp port 80` while a browser loads a page with images; in Wireshark, count how many responses carry `200` with body and how many carry `304 Not Modified`.
6. Add a `Vary: Accept-Encoding` and serve different bodies for gzip vs identity; confirm the cache key differs.

```python
# Excerpt from code/main.py
def is_fresh(response_age: int, max_age: int) -> bool:
    return response_age < max_age
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Freshness check | `is_fresh(age, max_age)` | `requests-cache` | RFC 7234 §4.2 |
| ETag compare | `etag_matches(client, server)` | `curl --etag-compare` | RFC 7232 §2.3 |
| 304 parser | `parse_status(line)` | curl, urllib | RFC 7232 §4.1 |
| Vary key | `cache_key(method, url, vary, request)` | Varnish, Squid | RFC 7234 §4.1 |
| Cache-Control parse | `parse_cache_control(value)` | `werkzeug.http` | RFC 7234 §5.2 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `Cache-Control` decision matrix mapping resource type (static asset, HTML, JSON API, private data) to the right directive.
- A `curl` cookbook of conditional GET patterns (`-I`, `-H 'If-None-Match: ...'`, `-H 'If-Modified-Since: ...'`, `--compressed`).
- A small Python ETag generator (hash of the response body) and matching validator.

Start from [`outputs/prompt-http-caching-conditional-gets.md`](../outputs/prompt-http-caching-conditional-gets.md).

## Exercises

1. Issue `curl -I https://example.com/` and identify every freshness and validation header.
2. Capture an ETag with `curl -I`, then send `curl -H 'If-None-Match: "<etag>"' -i https://example.com/` and confirm 304 + empty body.
3. Send `If-Modified-Since: <Last-Modified value>` and observe whether the server honors it.
4. Build a tiny Python server that returns `ETag: "<sha256 of body>"` and `Cache-Control: max-age=300`. Reload twice and observe the second call returns 304.
5. Add `Vary: Accept-Encoding` and serve two different bodies for gzip vs identity. Confirm both responses are cached independently.
6. Force `Cache-Control: no-store` and confirm the browser does not write the response to disk cache.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Cache-Control | "the freshness header" | RFC 7234 §5.2: `max-age`, `no-store`, `no-cache`, `private`, `public`, etc. |
| max-age | "how long it's fresh" | Number of seconds a response can be reused without revalidation |
| Expires | "the absolute expiry" | RFC 7234 §5.3: legacy absolute expiry timestamp |
| ETag | "the version tag" | RFC 7232: opaque server-assigned string identifying the representation |
| If-None-Match | "the revalidation" | Client echoes its cached ETag; server replies 304 if unchanged |
| If-Modified-Since | "the date check" | Client echoes its cached Last-Modified; server replies 304 if unchanged |
| Vary | "the cache key" | RFC 7234 §4.1: response varies based on these request header values |
| 304 Not Modified | "the empty success" | RFC 7232 §4.1: validation succeeded; reuse cached body |
| Heuristic freshness | "the fallback" | Cached when origin sends no explicit freshness; 10% of age by convention |
| immutable | "it never changes" | RFC 8246: skip revalidation during the freshness window |

## Further Reading

- RFC 7234 — HTTP/1.1 Caching (Cache-Control, freshness, validation)
- RFC 7232 — HTTP/1.1 Conditional Requests (If-None-Match, If-Modified-Since, 304)
- RFC 8246 — HTTP Immutable Responses
- RFC 5861 — HTTP Cache-Control Extensions for Stale Content
- RFC 7233 — HTTP/1.1 Range Requests (uses ETags for byte ranges)
- RFC 9111 — HTTP Caching (modern consolidated spec)
- IANA HTTP Cache Directive Registry — https://www.iana.org/assignments/http-cache-directives
- `curl` reference: `-I`, `-H`, `--etag-compare`, `--compressed`, `-H 'Cache-Control: no-cache'`
- Wireshark display filter: `http.response.code == 304`
- Breslau et al. (1999) — Web caching and the long tail
