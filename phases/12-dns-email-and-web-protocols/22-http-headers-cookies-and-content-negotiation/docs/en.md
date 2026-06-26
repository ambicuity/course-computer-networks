# HTTP Headers, Cookies, and Content Negotiation

> After the request and status lines, HTTP carries everything that makes the protocol useful in `Name: value` headers. RFC 7230 §3.2 codifies the header grammar; RFC 7231 §5 enumerates the canonical set. Headers control identity (`Host:`, `User-Agent:`, `Authorization:`), routing (`Referer:`, `Cookie:`), preferences (`Accept:`, `Accept-Language:`, `Accept-Encoding:`, `Accept-Charset:`), freshness (`Cache-Control:`, `Expires:`, `Last-Modified:`, `ETag:`, `If-None-Match:`, `If-Modified-Since:`), body description (`Content-Type:`, `Content-Length:`, `Content-Encoding:`, `Content-Language:`, `Content-Range:`), and connection state (`Connection:`, `Upgrade:`, `Transfer-Encoding:`). The `Set-Cookie:` response header (RFC 6265 + RFC 6265bis for SameSite) plus the `Cookie:` request header give the server persistent state in an otherwise stateless protocol. Content negotiation is the dance between the client's `Accept*` family and the server's choice: when multiple representations exist (English vs Spanish, gzip vs br, JSON vs XML), the server picks the best match or returns 406 Not Acceptable.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 12 lessons on HTTP methods and status codes, plus familiarity with `curl`
**Time:** ~75 minutes

## Learning Objectives

- Parse an HTTP header block into a `Dict[str, str]`, normalizing header names to lower case.
- Recognize and use the four `Accept*` request headers (`Accept`, `Accept-Charset`, `Accept-Encoding`, `Accept-Language`) and explain content negotiation.
- Read and set cookies with `Set-Cookie:` / `Cookie:`, including the `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Max-Age`, `Expires` attributes.
- Understand freshness headers (`Cache-Control`, `Expires`, `Last-Modified`, `ETag`) and conditional requests (`If-None-Match`, `If-Modified-Since`).
- Use `Authorization:` and `WWW-Authenticate:` for HTTP authentication (RFC 7235).
- Recognize connection-level headers (`Connection:`, `Upgrade:`, `Transfer-Encoding: chunked`).

## The Problem

You build a tiny REST API. Clients in different countries want responses in their language; clients on slow networks want responses gzip-compressed; clients in the browser want the session cookie set with `HttpOnly` and `SameSite=Lax` for CSRF defense. Without `Accept-Language` and `Accept-Encoding`, the server has no idea what to send back. Without the right cookie attributes, the session is exposed to XSS or CSRF. The HTTP headers are the protocol surface that makes all of this possible.

The trap is treating headers as decoration. They are the protocol: every meaningful HTTP feature lives in a header.

## The Concept

### Header grammar (RFC 7230 §3.2)

A header is `Name: OWS Value OWS` followed by CRLF. Field names are tokens (letters, digits, and `! # $ % & ' * + - . ^ _ ` | ~`). Field values may contain visible ASCII, spaces, and tabs, plus double-quoted strings and structured `;`/`=` lists. The same field name may appear multiple times (e.g., `Set-Cookie:` per RFC 6265; `Accept:` may carry multiple comma-separated media ranges). Header names are case-insensitive; common style is Title-Case.

### The four Accept headers (content negotiation)

| Header | RFC | Purpose |
|---|---|---|
| `Accept:` | 7231 §5.3.2 | Media types the client will accept; e.g., `text/html, application/json;q=0.9` |
| `Accept-Charset:` | 7231 §5.3.3 | Character sets; e.g., `utf-8, iso-8859-1;q=0.5` |
| `Accept-Encoding:` | 7231 §5.3.4 | Content codings; e.g., `gzip, br;q=0.9` |
| `Accept-Language:` | 7231 §5.3.5 | Natural languages; e.g., `en-US, en;q=0.9, ja;q=0.8` |

Each entry can carry a `;q=` quality value between 0 and 1 (default 1) to express preference. The server picks the best match from its representations; if nothing is acceptable, it returns 406 Not Acceptable.

### Server response counterparts

| Header | Meaning |
|---|---|
| `Content-Type:` | The actual media type the server chose |
| `Content-Length:` | Body size in octets |
| `Content-Encoding:` | The coding applied to the body (e.g., `gzip`) |
| `Content-Language:` | The natural language of the body |
| `Content-Location:` | The resource corresponding to the body (different from the request URL) |
| `Content-Range:` | Bytes covered by this response (RFC 7233) |
| `Content-Disposition:` | RFC 6266: how the UA should handle the body; `inline` or `attachment` with `filename=` |

### Cookies (RFC 6265)

`Set-Cookie: name=value; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600`

| Attribute | Purpose |
|---|---|
| `Domain=` | The cookie is sent to this domain and its subdomains |
| `Path=` | The cookie is sent for paths under this prefix |
| `Secure` | Send only over HTTPS |
| `HttpOnly` | Hide from JavaScript (defends against XSS exfiltration) |
| `SameSite=Strict / Lax / None` | Defends against CSRF: Strict = same-site only, Lax = top-level navigations only, None = always (must be Secure) |
| `Max-Age=` | Lifetime in seconds (preferred over `Expires=`) |
| `Expires=` | Absolute expiry date (HTTP date format) |

The browser then sends `Cookie: name1=value1; name2=value2` on every matching request. Cookies are domain-scoped (the cookie from `example.com` is not visible to `other.com`) and have a 4 KB size limit per cookie in most browsers.

### The two `Set-Cookie` semantics

`Set-Cookie` is the only response header that the RFC explicitly says must be sent multiple times if you want multiple cookies — one `Set-Cookie` line per cookie. Most modern parsers do join them with comma, but the cleanest server-side code emits one line per cookie.

### HTTP authentication (RFC 7235)

The `WWW-Authenticate: Basic realm="..."` response triggers the browser's auth dialog. The client retries with `Authorization: Basic dXNlcjpwYXNz` (base64 of `user:pass`). `Digest` (RFC 7616) is the challenge-response alternative; `Bearer` (RFC 6750) carries OAuth 2.0 tokens. Both `Authorization:` (request) and `WWW-Authenticate:` (response) are the contract.

### Caching headers (RFC 7234)

| Header | Direction | Purpose |
|---|---|---|
| `Cache-Control:` | both | Directives: `max-age=`, `no-cache`, `no-store`, `private`, `public`, `must-revalidate` |
| `Expires:` | response | Absolute expiry timestamp (HTTP date) |
| `Last-Modified:` | response | When the resource was last changed |
| `ETag:` | response | Opaque tag for the resource (often a hash) |
| `If-Modified-Since:` | request | Return the body only if it has changed since this date |
| `If-None-Match:` | request | Return the body only if the ETag does not match |
| `Age:` | response | How long this cached copy has existed (seconds) |
| `Vary:` | response | Headers whose values affected the response; e.g., `Vary: Accept-Encoding` |

The dance: server sends a response with `ETag: "abc123"`. Client caches. Next time, client sends `If-None-Match: "abc123"`. If the resource is unchanged, server replies `304 Not Modified` with no body, saving bytes.

### Connection management

`Connection: keep-alive` (HTTP/1.0) or its absence (HTTP/1.1 default) controls whether the TCP connection is reused. `Connection: close` forces the connection closed after the response. `Upgrade: h2, h2c, websocket` triggers a protocol switch (RFC 7230 §6.7, RFC 8441 for `Upgrade: h2c`). `Transfer-Encoding: chunked` lets the server stream a response with unknown total length.

### The Referer header

Note the misspelling: the request header is `Referer:` (sic), not `Referrer:`. RFC 7231 §5.5.2 retains the original misspelling for compatibility.

## Build It

1. Run `code/main.py` to parse a sample header block and classify each header into a category.
2. Issue `curl -v https://example.com/` and identify every header; group them by category.
3. Build a tiny server with `http.server` that sets `Set-Cookie: sid=...; HttpOnly; SameSite=Lax` on first contact and reads `Cookie:` on subsequent requests.
4. Use `Accept-Encoding: gzip` and confirm the response carries `Content-Encoding: gzip`.
5. Send `If-None-Match: "wrong"` and observe the 200 with full body; send `If-None-Match: "right"` and observe the 304 with no body.
6. Capture a `tcpdump -w hdr.pcap tcp port 80` while issuing `curl -v https://example.com/` and follow the TCP stream to see every header byte.

```python
# Excerpt from code/main.py
def parse_headers(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip().lower()] = v.strip()
    return out
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Header parser | `parse_headers(text)` | `email.parser`, `http.client` | RFC 7230 §3.2 |
| Accept negotiation | `pick_media_type(accept, available)` | `negotiate` | RFC 7231 §5.3.2 |
| Cookie jar | `CookieJar` | `http.cookiejar` | RFC 6265 |
| ETag validation | `validate_etag(client, server)` | RFC 7232 | RFC 7232 |
| Auth header | `basic_auth(user, pw)` | `requests.auth` | RFC 7617 |
| Range parsing | `parse_range(header)` | `http.server` | RFC 7233 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A header reference table that lists every commonly seen header, its direction (request/response), and a one-line purpose.
- A reusable cookie-setting helper that emits a properly-scoped `Set-Cookie:` value with HttpOnly, SameSite, and Secure.
- A 50-line Python server that demonstrates content negotiation: returns gzip when asked, English vs Spanish based on `Accept-Language`, and sets a session cookie.

Start from [`outputs/prompt-http-headers-cookies-and-content-negotiation.md`](../outputs/prompt-http-headers-cookies-and-content-negotiation.md).

## Exercises

1. Issue `curl -v https://example.com/` and list every header by direction and category.
2. Send a request with `Accept-Encoding: gzip` and verify `Content-Encoding: gzip` in the response.
3. Send a request with `Accept-Language: ja` against a server that supports English and Japanese; observe which language is returned.
4. Set a cookie with `HttpOnly; SameSite=Lax; Secure` and verify that an attempt to read `document.cookie` from the browser console returns nothing.
5. Use `ETag` validation: capture the ETag, send `If-None-Match`, and observe the 304.
6. Send `Authorization: Basic <base64 of user:pass>` and observe the `WWW-Authenticate` flow when you omit it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Header | "the request header" | `Name: value` lines after the request or status line (RFC 7230 §3.2) |
| Content negotiation | "what content to send" | The server picks the best match among the client's `Accept*` preferences |
| Accept | "the media types" | Comma-separated media ranges with optional `;q=` quality values |
| Cookie | "the session token" | RFC 6265: name/value sent in `Set-Cookie:` and returned in `Cookie:` |
| HttpOnly | "no JS access" | Cookie attribute preventing JavaScript access |
| SameSite | "CSRF defense" | Cookie attribute restricting cross-site sends |
| ETag | "the version tag" | Opaque string the server sends with a response; client echoes it back |
| Conditional GET | "the cache check" | Request that returns 304 if the cached copy is still valid |
| WWW-Authenticate | "the auth challenge" | Response header that prompts the client to provide credentials |
| Transfer-Encoding | "the framing" | `chunked` for streaming, or other codings (RFC 7230 §4) |

## Further Reading

- RFC 7230 §3.2 — HTTP/1.1 message syntax (header grammar)
- RFC 7231 §5 — HTTP/1.1 headers list
- RFC 7234 — HTTP/1.1 Caching
- RFC 7232 — HTTP/1.1 Conditional Requests (If-None-Match, If-Modified-Since, 304)
- RFC 7233 — HTTP/1.1 Range Requests (206, Accept-Ranges)
- RFC 7235 — HTTP/1.1 Authentication (WWW-Authenticate, Authorization, 401)
- RFC 6265 — HTTP State Management Mechanism (cookies)
- RFC 6265bis — Cookies draft with SameSite (precursor to RFC 6265bis final form)
- RFC 7616 — HTTP Digest Access Authentication
- RFC 7617 — The 'Basic' HTTP Authentication Scheme
- RFC 6750 — OAuth 2.0 Authorization: Bearer Token Usage
- RFC 8441 — Bootstrapping WebSockets over HTTP/2 (`Upgrade: websocket`)
- IANA HTTP Field Name Registry — https://www.iana.org/assignments/http-fields
