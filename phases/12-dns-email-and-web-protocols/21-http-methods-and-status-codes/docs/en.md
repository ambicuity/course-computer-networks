# HTTP Request Methods and Status Code Groups

> HTTP (HyperText Transfer Protocol, RFC 1945 for HTTP/1.0 and RFC 7230/7231 for HTTP/1.1, with the modern update in RFC 9110) is a request-response protocol that rides on TCP (default port 80 for cleartext, 443 for HTTPS). Each request is one ASCII line: a method, a request target, and the protocol version — `GET /index.html HTTP/1.1`. The server replies with a status line `HTTP/1.1 200 OK`, a header block, and a body. The eight standard methods (`GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE`) are the verbs the Web exposes to scripts, but `GET` carries the bulk of real traffic. Status codes are three-digit numbers whose first digit identifies the class: `1xx` informational, `2xx` success, `3xx` redirection, `4xx` client error, `5xx` server error. Each code is a single canonical number; the textual reason phrase (`OK`, `Not Found`, `Internal Server Error`) is human-readable decoration that clients should not parse.

**Type:** Lab
**Languages:** Python, shell, curl
**Prerequisites:** Phase 11 (TCP), Phase 9 (IP), and the prior Phase 12 lessons on DNS
**Time:** ~75 minutes

## Learning Objectives

- Read an HTTP request line and response status line and identify method, target, version, code, and reason phrase.
- Distinguish the eight standard methods (`GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE`) and predict what each is for.
- Map every 1xx/2xx/3xx/4xx/5xx code to its canonical meaning and use case.
- Use `curl -v` and `telnet` to observe a real request and response, including headers.
- Recognize that method names are case-sensitive (`GET` is valid; `get` is not) and that the response reason phrase is purely informational.
- Build a tiny HTTP server in stdlib Python and exercise the verbs end-to-end.

## The Problem

You see `HTTP/1.1 504 Gateway Timeout` in a log and want to know which side is responsible. You see `307 Temporary Redirect` and want to know whether to follow it automatically. You see `405 Method Not Allowed` and want to know which methods *are* allowed. The codes, methods, and version strings are the protocol; without them, you cannot debug, build, or integrate with HTTP.

The trap is treating HTTP like a black box. The request line is three fields; the response status line is three fields; the verb set is small and well-defined; the status classes are five. Once you can read these, the rest of the protocol is headers and bodies.

## The Concept

### The request line

```
GET /index.html HTTP/1.1
```

| Field | Value |
|---|---|
| Method | `GET` (uppercase required) |
| Request Target | `/index.html` (path, absolute form, authority form, or asterisk form) |
| HTTP Version | `HTTP/1.1` (or `HTTP/2` for HTTP/2 over TLS) |

Methods are case-sensitive (RFC 7230 §3.1.1). `GET` is valid; `get` is not. The asterisk form `OPTIONS *` is used for server-level queries. The authority form `CONNECT example.com:443` is used for tunneling (proxies).

### The status line

```
HTTP/1.1 200 OK
```

| Field | Value |
|---|---|
| HTTP Version | `HTTP/1.1` |
| Status Code | Three-digit integer |
| Reason Phrase | Human-readable text (informational only) |

The reason phrase is **optional** in HTTP/1.1 and required to be ignored by clients (RFC 7230 §3.1.2). Servers should still send one for human readers. A response of `HTTP/1.1 200 \r\n` is valid; `HTTP/1.1 OK\r\n` is not.

### The eight standard methods

| Method | RFC | Use |
|---|---|---|
| `GET` | 7231 §4.3.1 | Retrieve a representation of the resource. Idempotent and safe. |
| `HEAD` | 7231 §4.3.2 | Like GET but only return headers (no body). Used for cache validation and metadata. |
| `POST` | 7231 §4.3.3 | Submit data to be processed. Used for forms, uploads, RPC, webhooks. |
| `PUT` | 7231 §4.3.4 | Replace the resource at the request target with the request body. |
| `DELETE` | 7231 §4.3.5 | Remove the resource at the request target. |
| `CONNECT` | 7231 §4.3.6 | Establish a tunnel through a proxy (e.g., for HTTPS). |
| `OPTIONS` | 7231 §4.3.7 | Query the methods and options applicable to a resource. |
| `TRACE` | 7231 §4.3.8 | Echo the received request back to the sender (diagnostic). |

RFC 5789 adds `PATCH` for partial updates. RFC 4918 (WebDAV) adds many more (`PROPFIND`, `MKCOL`, `COPY`, `MOVE`, `LOCK`, `UNLOCK`). RFC 8144 adds `COPY`/`PATCH` etc. for GIS servers. Modern APIs use POST for almost everything that is not GET, often with an `X-HTTP-Method-Override` header for tunnelling.

### The five status code classes

| Class | Range | Meaning |
|---|---|---|
| 1xx | 100–199 | Informational. The request is being processed; client should keep going. |
| 2xx | 200–299 | Success. The request was understood, accepted, and completed. |
| 3xx | 300–399 | Redirection. The client must take additional action (often follow a `Location:` header). |
| 4xx | 400–499 | Client error. The request was malformed or cannot be fulfilled. |
| 5xx | 500–599 | Server error. The request was valid but the server failed. |

### The status codes that matter in practice

| Code | Name | When |
|---|---|---|
| 100 | Continue | Server acknowledges request headers, ready for body (RFC 7231 §6.2.1, RFC 9110 §15.2.1) |
| 101 | Switching Protocols | Upgrade header succeeded (e.g., WebSocket) |
| 200 | OK | Standard success |
| 201 | Created | Resource created (typically POST or PUT) |
| 204 | No Content | Success but no body (e.g., DELETE) |
| 206 | Partial Content | Range request fulfilled (RFC 7233) |
| 301 | Moved Permanently | The resource has a new canonical URL; clients should update bookmarks |
| 302 | Found | Temporary redirect; the next request should still go to the original URL |
| 303 | See Other | Redirect after POST: the response should be retrieved via GET |
| 304 | Not Modified | Conditional GET validated the cached copy |
| 307 | Temporary Redirect | Like 302, but the method must not change (RFC 7231 §6.4.7) |
| 308 | Permanent Redirect | Like 301, but the method must not change (RFC 7538) |
| 400 | Bad Request | Generic malformed request |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Server refuses; do not retry with the same credentials |
| 404 | Not Found | Resource does not exist |
| 405 | Method Not Allowed | The resource does not support this method; `Allow:` header lists supported ones |
| 406 | Not Acceptable | Server cannot produce a representation matching the `Accept:` headers |
| 409 | Conflict | Request conflicts with current resource state |
| 410 | Gone | Resource was here but is permanently removed |
| 418 | I'm a Teapot | RFC 2324 (April Fools' RFC; some servers keep it as an Easter egg) |
| 422 | Unprocessable Entity | WebDAV; request is well-formed but semantically invalid |
| 429 | Too Many Requests | Rate limited (RFC 6585) |
| 500 | Internal Server Error | Generic server failure |
| 501 | Not Implemented | Server does not support the method or feature |
| 502 | Bad Gateway | A proxy got an invalid response from upstream |
| 503 | Service Unavailable | Temporary overload or maintenance; `Retry-After:` header may indicate when |
| 504 | Gateway Timeout | A proxy did not get a timely response from upstream |

### Method safety and idempotency

| Property | Methods |
|---|---|
| Safe (no side effects) | `GET`, `HEAD`, `OPTIONS`, `TRACE` |
| Idempotent (same result on retry) | `GET`, `HEAD`, `PUT`, `DELETE`, `OPTIONS`, `TRACE` |
| Neither | `POST`, `PATCH`, `CONNECT` |

Idempotency matters for retries: a `PUT` that times out can be safely retried because the second request replaces the resource with the same body. A `POST` that times out may have already created a new resource; retrying creates a duplicate.

### The version string matters

HTTP/1.0 (RFC 1945) closes the connection after every request unless `Connection: keep-alive` is set explicitly. HTTP/1.1 (RFC 7230) defaults to persistent connections. HTTP/2 (RFC 7540) requires TLS, multiplexes many streams over one TCP connection, and uses a binary framing layer; the request line is still ASCII but headers are HPACK-compressed pseudo-headers (`:method`, `:path`, `:scheme`, `:authority`). HTTP/3 (RFC 9114) replaces TCP with QUIC.

### The `Allow:` header

A 405 response should include `Allow:` listing the methods the resource *does* support. Clients use this to recover: `Allow: GET, HEAD` on a POST attempt tells the client "try GET".

## Build It

1. Run `code/main.py` to simulate request/response pairs and classify the codes.
2. `curl -v https://example.com/` and read the request line, the response line, and every header.
3. Open a TCP connection with `telnet example.com 80`, type `GET / HTTP/1.0\r\nHost: example.com\r\n\r\n`, and read the raw response.
4. Build a tiny HTTP server with Python's `http.server` and add handlers for `GET`, `POST`, `DELETE` on `/items/<id>`.
5. Force a 404 and a 405 from your server and inspect the `Allow:` header on the 405.
6. Capture a `tcpdump -w http.pcap tcp port 80` while issuing `curl -v http://example.com/` and follow the TCP stream in Wireshark.

```python
# Excerpt from code/main.py
def parse_request_line(line: str) -> tuple[str, str, str]:
    parts = line.rstrip("\r\n").split(" ", 2)
    return parts[0], parts[1], parts[2]
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Request parser | `parse_request_line` | `http.server` | RFC 7230 §3.1 |
| Status classifier | `classify_status(code)` | curl, urllib | RFC 7231 §6 |
| Method safety | `is_safe(method)` | `werkzeug`, `flask` | RFC 7231 §4.2.1 |
| Idempotency | `is_idempotent(method)` | `requests` | RFC 7231 §4.2.2 |
| HTTP/1.1 keepalive | `keepalive_default()` | `http.client` | RFC 7230 §6 |
| Range/206 | `parse_range(header)` | `http.server` | RFC 7233 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A curl cheatsheet showing `GET`, `HEAD`, `-X POST -d`, `-X PUT --upload-file`, `-X DELETE`, `-X OPTIONS`, `-i`, `-v`, `--http2`.
- A reference table of every commonly seen status code with one-line meaning.
- A 30-line Python `http.server` subclass that handles a few methods and returns proper 200/201/204/404/405/500.

Start from [`outputs/prompt-http-methods-and-status-codes.md`](../outputs/prompt-http-methods-and-status-codes.md).

## Exercises

1. Issue `curl -v https://example.com/` and identify the request line, response line, and the `Server:` header.
2. Use `curl -X OPTIONS -i https://example.com/` to query the supported methods.
3. Send `HEAD https://example.com/` with `curl -I` and confirm the response has no body.
4. Force a 405 by `POST`-ing to a path that only allows `GET`. Inspect the `Allow:` header.
5. Capture a real HTTP request and decode the version, method, and status code from Wireshark.
6. Write a 30-line Python server that returns 200 for `GET /`, 405 with `Allow:` for any other method, and 404 for unknown paths.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Method | "the HTTP verb" | `GET`, `POST`, `PUT`, `DELETE`, `HEAD`, `OPTIONS`, `CONNECT`, `TRACE` (case-sensitive) |
| Status code | "the response number" | Three-digit response code; first digit is the class (1xx..5xx) |
| Reason phrase | "the text after the code" | Human-readable decoration like "OK"; clients must ignore it |
| Safe method | "no side effects" | `GET`, `HEAD`, `OPTIONS`, `TRACE` — RFC 7231 §4.2.1 |
| Idempotent | "retry safe" | Multiple identical requests have the same effect; `PUT`/`DELETE` qualify |
| `Allow:` | "the supported methods" | Header on 405 listing the methods the resource accepts |
| HTTP/1.1 | "the modern version" | RFC 7230: defaults to persistent connections |
| HTTP/2 | "binary, multiplexed" | RFC 7540: HPACK-compressed, multiplexed, TLS required |
| HTTP/3 | "over QUIC" | RFC 9114: same semantics as HTTP/2, on UDP/QUIC |
| `Location:` | "where to go next" | Header on 3xx responses pointing at the new URL |

## Further Reading

- RFC 1945 — Hypertext Transfer Protocol — HTTP/1.0
- RFC 7230 — HTTP/1.1: Message Syntax and Routing
- RFC 7231 — HTTP/1.1: Semantics and Content
- RFC 7232 — HTTP/1.1: Conditional Requests (If-Modified-Since, If-None-Match, 304)
- RFC 7233 — HTTP/1.1: Range Requests (206, Accept-Ranges, Range)
- RFC 7538 — The Hypertext Transfer Protocol Status Code 308
- RFC 5789 — PATCH Method for HTTP
- RFC 6585 — Additional HTTP Status Codes (429)
- RFC 7540 — HTTP/2
- RFC 9110 — HTTP Semantics (modern consolidated spec)
- RFC 9114 — HTTP/3
- `curl` man page — `-v`, `-i`, `-I`, `-X`, `-L`, `--http2`
- Python `http.server` documentation
