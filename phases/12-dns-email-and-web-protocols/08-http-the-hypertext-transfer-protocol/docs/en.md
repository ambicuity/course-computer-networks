# HTTP — the HyperText Transfer Protocol

> **HTTP** (RFC 2616 / RFC 7230-7235) is a simple **request-response** protocol running over **TCP port 80**. Each request is one or more lines of ASCII text (the **request line** plus **headers**); each response is a **status line** (`HTTP/1.1 200 OK`), headers, a blank line, and the body. The principal methods are **GET** (read), **HEAD** (header only), **POST** (append/process data — used by forms and SOAP), **PUT** (write), **DELETE**, **TRACE** (debug), **CONNECT** (proxy tunnel), and **OPTIONS**. Status codes are three digits grouped `1xx` info, `2xx` success, `3xx` redirection, `4xx` client error, `5xx` server error — common examples 200, 204, 301, 304, 403, 404, 500, 503. Headers like `User-Agent`, `Accept`, `Accept-Language`, `Host`, `If-Modified-Since`, `If-None-Match`, `Authorization`, `Referer`, `Cookie`, `Set-Cookie`, `Content-Type`, `Content-Length`, `Location`, `ETag`, `Cache-Control`, `Last-Modified`, `Expires` carry all the metadata. HTTP 1.1 introduced **persistent connections** (re-use one TCP for many requests) and **pipelining** (send next request before previous response). Caching combines **Expires** validation with **conditional GET** (If-Modified-Since / If-None-Match returning 304 Not Modified).

**Type:** Build
**Languages:** HTTP, telnet, curl, Python (RFC 7230 request builder)
**Prerequisites:** Phase 6 (TCP), Phase 12 Lesson 06 (Web architecture)
**Time:** ~130 minutes

## Learning Objectives

- Construct an HTTP/1.1 GET request with the required `Host` header and parse the status line, headers, and body from the response.
- List the eight standard methods (GET, HEAD, POST, PUT, DELETE, TRACE, CONNECT, OPTIONS) and state which are safe or idempotent.
- Map common status codes (200, 204, 301, 304, 403, 404, 500, 503) to their meaning and decide the correct client reaction.
- Decide between sequential, parallel, persistent, and pipelined connections for a given workload.
- Use `If-Modified-Since` and `If-None-Match` to implement conditional GETs and reduce server load.

## The Problem

Browsers fetch a page, then 40 subresources, then a JSON payload, then a video manifest — all from the same server. Each one is a tiny request and a possibly-large response, sequenced over a single TCP connection if the server uses HTTP/1.1 keep-alive. The protocol has to be: simple enough to debug with `telnet`, efficient enough to amortise TCP setup across many requests, flexible enough to carry HTML, CSS, JavaScript, images, video, JSON, XML, and arbitrary binary, and reliable enough that caches can answer in milliseconds. HTTP/1.1 (RFC 7230-7235) is the answer that has held up since 1997.

## The Concept

### The request-response shape

HTTP is asymmetric. A **client** opens a TCP connection to port 80 and sends a request. A **server** listens, parses the request, and returns a response. After HTTP/1.0 each connection carried one request; HTTP/1.1 introduced **persistent connections** (default keep-alive) and **pipelining** (next request sent before previous response arrives).

An HTTP request:

```text
GET /index.html HTTP/1.1\r\n
Host: www.cs.washington.edu\r\n
User-Agent: Mozilla/5.0\r\n
Accept: text/html,application/xhtml+xml\r\n
Accept-Language: en-US,en;q=0.9\r\n
If-Modified-Since: Sat, 01 Jan 2025 12:00:00 GMT\r\n
\r\n
```

An HTTP response:

```text
HTTP/1.1 200 OK\r\n
Date: Tue, 24 Jun 2026 12:00:00 GMT\r\n
Server: Apache/2.4.57 (Ubuntu)\r\n
Content-Type: text/html; charset=utf-8\r\n
Content-Length: 1234\r\n
Last-Modified: Mon, 23 Jun 2026 09:15:00 GMT\r\n
ETag: "a1b2c3d4"\r\n
Cache-Control: max-age=3600\r\n
\r\n
<!DOCTYPE html>
<html>...
```

Header lines end with CRLF (`\r\n`). The body starts after the first blank line. For `HEAD` requests or `304 Not Modified`, the body is empty. For `Content-Length` absent, the body ends at connection close (HTTP/1.0 behaviour) or via `Transfer-Encoding: chunked` (HTTP/1.1+).

### The eight standard methods

| Method | RFC | Safe? | Idempotent? | Body? | Purpose |
|--------|-----|-------|-------------|-------|---------|
| `GET` | 7231 | yes | yes | no | Read a resource (most common) |
| `HEAD` | 7231 | yes | yes | no (response only) | Read just the headers |
| `POST` | 7231 | no | no | yes | Append data or trigger processing (forms, SOAP) |
| `PUT` | 7231 | no | yes | yes | Write/replace a resource at the URL |
| `DELETE` | 7231 | no | yes | optional | Remove a resource |
| `TRACE` | 7231 | yes | yes | no | Echo the request back for debugging |
| `CONNECT` | 7231 | no | no | no | Tunnel through a proxy (HTTPS) |
| `OPTIONS` | 7231 | yes | yes | optional | List the methods allowed on a URL |

**Safe** = no side effects on the server. **Idempotent** = repeated calls have the same effect as one. `GET`, `HEAD`, `OPTIONS`, `TRACE` are safe; `GET`, `HEAD`, `PUT`, `DELETE`, `OPTIONS`, `TRACE` are idempotent.

### Status codes

Three digits; first digit carries the class:

| Class | Range | Meaning | Common examples |
|-------|-------|---------|------------------|
| 1xx | 100-199 | Informational, continue | 100 Continue |
| 2xx | 200-299 | Success | 200 OK, 204 No Content, 206 Partial Content |
| 3xx | 300-399 | Redirection | 301 Moved Permanently, 302 Found, 304 Not Modified |
| 4xx | 400-499 | Client error | 400 Bad Request, 403 Forbidden, 404 Not Found, 418 I'm a teapot |
| 5xx | 500-599 | Server error | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable |

`304 Not Modified` is the workhorse of caching: the server says "your copy is still fresh; use it." The body is empty.

### Headers — the metadata backbone

HTTP's power is in headers. They are ASCII text lines of the form `Name: value`. Major categories:

**Request headers (sent by client):**

| Header | Function |
|--------|----------|
| `Host` | DNS name of the server (mandatory in HTTP/1.1) |
| `User-Agent` | Browser identification |
| `Accept` | MIME types the client can handle |
| `Accept-Charset` | Acceptable character sets |
| `Accept-Encoding` | Compression methods (`gzip`, `br`) |
| `Accept-Language` | Preferred natural languages |
| `If-Modified-Since` | Caching: only return if newer |
| `If-None-Match` | Caching: only return if ETag differs |
| `Authorization` | Credentials for protected resources |
| `Referer` | URL of the previous page (sic, the misspelling) |
| `Cookie` | Cookies attached to this request |
| `Range` | Request a byte range (resumable downloads) |

**Response headers (sent by server):**

| Header | Function |
|--------|----------|
| `Server` | Server software identification |
| `Content-Type` | MIME type of the body |
| `Content-Length` | Body size in bytes |
| `Content-Encoding` | Encoding applied to body (e.g., `gzip`) |
| `Content-Language` | Natural language of the body |
| `Last-Modified` | When the resource last changed |
| `Expires` | When the cache copy becomes stale |
| `ETag` | Tag identifying the body content |
| `Cache-Control` | Caching directives |
| `Location` | Redirect target or resource location |
| `Set-Cookie` | Cookie to store client-side |
| `Accept-Ranges` | Whether byte ranges are supported |

**Bidirectional headers:**

| Header | Direction | Function |
|--------|-----------|----------|
| `Date` | both | Date/time the message was sent |
| `Connection` | both | Connection options (`keep-alive`, `close`) |
| `Cache-Control` | both | Caching directives |
| `Upgrade` | both | Protocol upgrade (`h2`, `h2c`, `websocket`) |

### Connections — sequential, parallel, persistent, pipelined

The textbook's Figure 7-36 contrasts three patterns:

```text
(a) Sequential, one connection per request:
   [CONNECT][REQ1][RESP1][CLOSE][CONNECT][REQ2][RESP2][CLOSE][CONNECT][REQ3][RESP3][CLOSE]
   Cost: 3x TCP setup + 3x slow-start ramp-up

(b) Persistent (keep-alive), sequential:
   [CONNECT][REQ1][RESP1][REQ2][RESP2][REQ3][RESP3][CLOSE]
   Cost: 1x setup, 1x ramp-up. Server idle between REQ and RESP.

(c) Persistent + pipelined:
   [CONNECT][REQ1][REQ2][REQ3][RESP1][RESP2][RESP3][CLOSE]
   Cost: same as (b), but server never idle; responses come back in order.
```

HTTP/1.1 defaults to (b) with optional pipelining. Browsers also open **up to 6 parallel TCP connections per origin** (configurable) to hide TCP setup latency for image-heavy pages. The cost is congestion: six independent TCP flows compete for bandwidth. HTTP/2 (RFC 7540, 2015) replaced this with **multiplexing** — many streams over one TCP connection.

Persistent connections typically close after 60 seconds of idleness or when the server hits its open-connection limit.

### Caching — two strategies

The textbook's Figure 7-40 shows the two caching strategies combined:

1. **Freshness check (step 2)**: the cache compares the stored resource's `Expires` (or `Cache-Control: max-age`) against the current time. If still fresh, return immediately.
2. **Conditional GET (step 3)**: if expired or no Expires given, send the cached `Last-Modified` as `If-Modified-Since` (or the cached `ETag` as `If-None-Match`). The server replies:
   - `304 Not Modified` if cache is still good (empty body)
   - `200 OK` with new body if not

This means most cache hits cost only a tiny request and a tiny 304 response — much cheaper than downloading the full body.

### Cookies over HTTP

Cookies are set by `Set-Cookie:` in responses and returned by `Cookie:` in subsequent requests:

```http
HTTP/1.1 200 OK
Set-Cookie: session=abc123; Path=/; HttpOnly; Secure; SameSite=Strict

GET /account HTTP/1.1
Host: example.com
Cookie: session=abc123
```

The `Set-Cookie` attributes control scope (`Domain`, `Path`), lifetime (`Expires`, `Max-Age`), and security (`Secure`, `HttpOnly`, `SameSite`).

### Method choice for common patterns

| Use case | Method | Why |
|----------|--------|-----|
| View a page | `GET` | Safe, idempotent, cacheable |
| Search query | `GET` with `?q=...` | URL-encoded, can be cached |
| Form submission that creates an account | `POST` | Has side effects, body |
| Form submission that is idempotent (e.g., search) | `GET` | Safe, bookmarkable |
| Upload a file | `POST` (multipart/form-data) or `PUT` | Body needed |
| Update a row in place | `PUT` | Idempotent |
| Delete a row | `DELETE` | Idempotent |
| WebSocket handshake | `GET` + `Upgrade: websocket` | Special upgrade flow |

### Talking HTTP by hand

`telnet` (or `nc`) makes HTTP trivially debuggable:

```bash
$ telnet www.ietf.org 80
Trying 4.31.198.44...
Connected to www.ietf.org.
Escape character is '^]'.
GET /rfc.html HTTP/1.1
Host: www.ietf.org

HTTP/1.1 200 OK
Date: ...
Server: ...
Content-Type: text/html; charset=utf-8
...
```

The blank line after `Host:` is mandatory — it terminates the headers and tells the server to send the response.

## Build It

1. Run `python3 code/main.py` to construct and parse an HTTP request/response, demonstrating the headers and status line.
2. Use `curl -v https://example.com` to see the actual request and response bytes.
3. Use `curl -I https://example.com` (HEAD) to confirm the response body is empty.
4. Try `curl -H 'If-Modified-Since: Sat, 01 Jan 2000 00:00:00 GMT' -I https://example.com` and observe the `200 OK` response.
5. Inspect `assets/http-protocol-flow.svg` for the connection-state and caching diagrams.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| Capture a request | `curl -v` | Verbose request and response shown |
| Replay a request | `curl --trace-ascii - URL` | ASCII trace of bytes on the wire |
| Inspect headers only | `curl -I URL` | Status line + headers, no body |
| Conditional GET | `curl -z 2025-01-01 -I URL` | 200 OK if newer, 304 Not Modified otherwise |
| Measure pipelining | `curl --http1.1 -v` then check `Connection: keep-alive` | Header present |

## Ship It

Under `outputs/`, build an HTTP client that opens a TCP connection to port 80, sends an HTTP/1.1 GET, parses the status line, headers, and body. Demonstrate with `example.com` or a local server. Start with [`outputs/prompt-http-protocol.md`](../outputs/prompt-http-protocol.md).

## Exercises

1. The server returns `304 Not Modified`. List the headers that must (or must not) be in the response.
2. A client opens 6 parallel TCP connections to the same server. What HTTP-level problem does HTTP/2 solve that HTTP/1.1 with pipelining does not?
3. The client sends `If-None-Match: "abc"` and the server's current ETag is `"abc"`. What is the response?
4. Why is `Content-Length` required for persistent connections but not for one-shot HTTP/1.0 connections?
5. The server responds with `Content-Encoding: gzip`. What header must the client send to indicate it can decode it?
6. A request includes `Range: bytes=100-199`. What status code does the server return for a successful partial response?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| HTTP | "the Web protocol" | RFC 7230-7235 request-response over TCP :80 |
| Method | "the verb" | GET, POST, PUT, DELETE, ... |
| Status code | "the answer" | 1xx-5xx three-digit reply |
| Header | "metadata line" | `Name: value` ASCII line |
| Persistent connection | "keep-alive" | One TCP for many requests |
| Pipelining | "send next before previous arrives" | Reduces server idle time |
| Conditional GET | "am I still fresh?" | If-Modified-Since / If-None-Match |
| ETag | "fingerprint" | Opaque tag identifying a body version |
| Cache | "nearby copy" | Browser, proxy, or CDN edge |
| Range request | "send me part" | `Range: bytes=0-1023` |
| Host header | "which virtual host" | Mandatory in HTTP/1.1 |
| Cookie | "stateful memory" | RFC 6265 named string set by server |

## Further Reading

- RFC 7230 — HTTP/1.1: Message Syntax and Routing
- RFC 7231 — HTTP/1.1: Semantics and Content
- RFC 7232 — HTTP/1.1: Conditional Requests
- RFC 7233 — HTTP/1.1: Range Requests
- RFC 7234 — HTTP/1.1: Caching
- RFC 7235 — HTTP/1.1: Authentication
- RFC 6265 — HTTP State Management Mechanism (Cookies)
- RFC 7540 — HTTP/2
- RFC 9110 — HTTP Semantics (2022, replaces 7230-7235)
- Fielding, *Architectural Styles and the Design of Network-based Software Architectures*, 2000
- Gourley, *HTTP: The Definitive Guide*, O'Reilly 2002
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Section 7.3.4
