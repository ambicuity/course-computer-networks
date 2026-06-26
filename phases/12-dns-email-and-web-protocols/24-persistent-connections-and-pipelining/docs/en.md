# HTTP Persistent Connections and Pipelining

> HTTP/1.0 (RFC 1945) opened a fresh TCP connection for every request, paid the three-way-handshake, did TCP slow-start from cwnd=1, and tore down. A page with 40 inline images meant 40 separate handshakes and 40 separate slow-start ramps — many round trips wasted before any bytes flowed. HTTP/1.1 (RFC 7230) made persistent connections the default: one TCP connection carries a series of requests and responses until either side closes. The client sends `Connection: keep-alive` only to opt into persistence on HTTP/1.0. RFC 7230 §6 also defines **pipelining**: a client may send request 2 before the response to request 1 has arrived, so the server's idle time is reduced. Pipelining was historically fragile (especially through proxies) and was effectively superseded by HTTP/2's multiplexed streams, but pipelining still works on HTTP/1.1 today for servers and clients that opt in. HTTP/2 (RFC 7540) replaces the head-of-line blocking with frame multiplexing on a single connection, eliminating the need for pipelining.

**Type:** Lab
**Languages:** Python, packet traces
**Prerequisites:** Phase 12 lessons on HTTP methods, headers, and a familiarity with `tcpdump`
**Time:** ~75 minutes

## Learning Objectives

- Trace the cost of opening a new TCP connection for every HTTP/1.0 request and identify where the latency goes.
- Enable persistent connections and observe the saved handshakes in a `tcpdump` capture.
- Pipeline requests on HTTP/1.1 and identify the head-of-line blocking problem.
- Explain why HTTP/2's multiplexed streams replace pipelining.
- Use `Connection: close` and `Content-Length` correctly in a stdlib HTTP server so persistent connections work.
- Predict the right reuse timeout for idle persistent connections (commonly 60 s) and reason about server-side connection caps.

## The Problem

You watch a browser load a page and notice in Wireshark that every image is its own TCP connection with its own three-way handshake. Then you read that HTTP/1.1 has keep-alive by default and wonder why your server is still opening fresh connections for every request. The trap is treating TCP connection cost as free. It is not: handshake (1 RTT), slow-start ramp (multiple RTTs to reach cwnd=10 or higher), TLS handshake (1-2 extra RTTs). Persistent connections amortize these over many requests.

Pipelining on top of persistence is a further optimization that *did* work but was fragile in practice. HTTP/2 dropped pipelining in favor of binary framing on a single connection.

## The Concept

### The HTTP/1.0 cost

A page with `index.html` + `style.css` + `logo.png` + `script.js` + `analytics.js` over HTTP/1.0 means five TCP handshakes, five slow-start ramps, and (if HTTPS) five TLS handshakes. Each request's first byte time (TTFB) is dominated by the ramp, not the network. On a 50 ms RTT link, a 1 KB response can take 150-300 ms — much of that is the slow-start climb, not the data transfer.

### HTTP/1.1 persistent connections

HTTP/1.1 defaults to `Connection: keep-alive` (implicit; servers and clients both expect it). One TCP connection carries many requests, each delimited by `Content-Length` or by `Transfer-Encoding: chunked`. The connection closes when either side sends `Connection: close` or the server hits its idle timeout (commonly 60 s).

Persistent connections save:

- One TCP handshake per request (1 RTT)
- One slow-start ramp per request (multiple RTTs)
- One TLS handshake per request when HTTPS (1-2 RTTs)

For 40 images on a 100 ms RTT link, persistent connections save roughly 40 × 100 ms = 4 s of latency, even before slow-start savings.

### `Content-Length` and message framing

A persistent connection needs a way to delimit where one response ends and the next begins. HTTP/1.1 supports three:

1. `Content-Length: N` — exactly N octets follow.
2. `Transfer-Encoding: chunked` — body sent as `length\r\ndata\r\n` chunks, terminated by `0\r\n\r\n`.
3. `Connection: close` — the response ends at EOF (the server closes the connection after).

Mixing up `Content-Length` and chunked encoding, or omitting both, is one of the most common HTTP/1.1 server bugs (request smuggling).

### Pipelining (RFC 7230 §6.3)

A pipelining client sends request 2 before it has read response 1. The server processes them in order. The savings come from eliminating the server's idle time: instead of "request, wait, response, request, wait, response", the wire is full of requests, then full of responses.

The catch: a slow response 1 holds up all later responses on the same connection (**head-of-line blocking**). If response 1 is a 5 MB download, responses 2-40 are stuck behind it. Most browsers eventually disabled pipelining by default because of this. HTTP/1.1 still supports it; the `Expect: 100-continue` mechanism (RFC 7231 §5.1.1) is related but specifically for the body-upload case.

### HTTP/2 multiplexing

HTTP/2 (RFC 7540) replaces the HTTP/1.1 request-response-per-stream model with binary frames over a single TCP (or QUIC) connection. Each request gets its own **stream**; multiple streams can carry frames interleaved on the wire. There is no head-of-line blocking between streams. HTTP/2 also compresses headers with HPACK and requires TLS (with h2c, cleartext, allowed but rarely used). HTTP/3 (RFC 9114) replaces TCP with QUIC to remove TCP's own head-of-line blocking.

### Why one connection per server, not one per request

A modern browser opens **6 connections per origin** in HTTP/1.1 (the historical default, still used as a fallback). With persistent connections, this gives 6 parallel streams without paying for 6 handshakes per request. With HTTP/2, one connection is enough because of multiplexing; the 6-connection cap was removed.

### `Connection` header semantics

`Connection: close` on HTTP/1.1 tells the other side the connection will close after this response. `Connection: keep-alive` on HTTP/1.0 opts in to persistence. Other values include `Connection: Upgrade` to request a protocol switch (e.g., WebSocket). The `Connection` header also lists hop-by-hop headers that should not be forwarded by proxies.

### Server-side connection caps

Servers limit open persistent connections to bound resource usage. Apache's `MaxKeepAliveRequests` (default 100) limits how many requests per connection; `KeepAliveTimeout` (default 5 s on Apache, 60 s on nginx) caps idle time. Going past these makes the server return `Connection: close` to start a fresh handshake.

### The pipeline vs multiplex decision

| Strategy | Where it works | Where it fails |
|---|---|---|
| One connection per request (HTTP/1.0) | Slow networks, very old clients | Wasteful on modern networks |
| Persistent + sequential (HTTP/1.1 default) | Most real-world workloads | Server sits idle between requests |
| Persistent + pipelining (HTTP/1.1) | Simple clients, small numbers of requests | Head-of-line blocking |
| Multiplexed (HTTP/2, HTTP/3) | Modern browsers and APIs | Requires TLS (h2) or QUIC (h3) |

## Build It

1. Run `code/main.py` to simulate HTTP/1.0, HTTP/1.1 persistent, and HTTP/1.1 pipelined requests and report the simulated RTT cost.
2. Use `tcpdump -w perconn.pcap tcp port 80` while a browser loads a page with many images; in Wireshark, count the `SYN` packets (one per HTTP/1.0 connection) versus the number of HTTP requests on the same flow.
3. Switch the server to HTTP/1.1 with `Connection: keep-alive` (the default) and reload; observe fewer `SYN`s.
4. Add `Expect: 100-continue` support and verify the 100 response is sent before the body.
5. Use `curl --http2-prior-knowledge http://localhost:8080/` to upgrade to HTTP/2 on a cleartext server (h2c).
6. Capture a multiplexed HTTP/2 capture and observe many streams on one TCP connection.

```python
# Excerpt from code/main.py
def simulate(n: int, mode: str, rtt_ms: int = 50, body_ms: int = 20) -> int:
    """Return simulated wall-clock cost in ms for n requests under mode."""
    if mode == "http10":
        return n * (2 * rtt_ms + body_ms) + n * rtt_ms  # handshake + slow-start each time
    if mode == "http11":
        return 2 * rtt_ms + n * (rtt_ms + body_ms)
    if mode == "pipelined":
        return 2 * rtt_ms + n * rtt_ms + n * body_ms
    raise ValueError(mode)
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| RTT simulator | `simulate(n, mode, rtt_ms)` | `httperf`, `wrk` | RFC 7230 §6 |
| Connection reuse | `Connection: keep-alive` | curl, urllib | RFC 7230 §6.1 |
| Pipelining client | `pipeline(requests)` | `curl --pipeline` | RFC 7230 §6.3 |
| HTTP/2 upgrade | h2c cleartext | `curl --http2-prior-knowledge` | RFC 7540 §3.2 |
| HTTP/3 over QUIC | `--http3` | curl | RFC 9114 |
| Chunked encoding | `chunked_encode(body)` | `http.server` | RFC 7230 §4.1 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A latency-budget calculator that estimates wall-clock cost under HTTP/1.0, HTTP/1.1, and HTTP/2 for a given page (N resources) and RTT.
- A `tcpdump` filter recipe that shows handshake count per origin: `tcp.flags.syn == 1 and tcp.flags.ack == 0`.
- A 50-line HTTP/1.1 server that emits proper `Content-Length` or `Transfer-Encoding: chunked` and reuses connections.

Start from [`outputs/prompt-persistent-connections-and-pipelining.md`](../outputs/prompt-persistent-connections-and-pipelining.md).

## Exercises

1. Capture a `tcpdump` while loading a 20-image page over HTTP/1.0; count the SYN packets.
2. Switch to HTTP/1.1 keep-alive and re-capture; confirm one SYN for the page load.
3. Send `Expect: 100-continue` on a `POST` with a body; observe whether the server replies 100 before the body upload.
4. Use `curl --http2-prior-knowledge` against a cleartext HTTP/2 server and confirm the protocol switch in Wireshark.
5. Use `wrk -t 4 -c 100 -d 30s http://localhost/` and compare requests/sec against HTTP/1.0 and HTTP/1.1 modes.
6. Inspect `Connection: close` on the last response of a server's persistent connection and confirm the TCP FIN follows.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| HTTP/1.0 | "no keep-alive" | RFC 1945: one TCP connection per request unless `Connection: keep-alive` |
| HTTP/1.1 keep-alive | "persistent connections" | RFC 7230 §6: one TCP connection carries many requests by default |
| Content-Length | "the body size" | RFC 7230 §3.3.2: octets in the body; needed to delimit responses on persistent connections |
| Transfer-Encoding: chunked | "streamed body" | RFC 7230 §4.1: body sent as `length\r\ndata\r\n` chunks |
| Pipelining | "send before reading" | RFC 7230 §6.3: client sends request N+1 before reading response N |
| Head-of-line blocking | "slow first response" | A slow response blocks all later pipelined responses on the same connection |
| HTTP/2 streams | "multiplexed" | RFC 7540: many concurrent streams on one connection; no head-of-line blocking |
| HTTP/3 over QUIC | "UDP-based HTTP" | RFC 9114: HTTP semantics over QUIC (UDP), removes TCP's HOL blocking |
| `Connection: close` | "end the connection" | Tells the peer this is the last response on this connection |
| `Expect: 100-continue` | "wait before body" | RFC 7231 §5.1.1: client asks if server wants the body before sending it |

## Further Reading

- RFC 1945 — HTTP/1.0 (the original, no keep-alive by default)
- RFC 7230 §6 — HTTP/1.1 connection management (keep-alive, pipelining)
- RFC 7230 §4.1 — Transfer-Encoding: chunked
- RFC 7231 §5.1.1 — Expect: 100-continue
- RFC 7540 — HTTP/2 (binary framing, multiplexed streams, HPACK)
- RFC 9110 — HTTP Semantics (modern consolidated spec)
- RFC 9114 — HTTP/3 (HTTP over QUIC)
- RFC 9209 — HTTP/2 Expectations (modernized Expect for h2)
- `httperf`, `wrk`, `vegeta` — load generators that exercise HTTP/1.0 vs HTTP/1.1 vs HTTP/2
- `curl` reference: `--keepalive-time`, `--http2`, `--http2-prior-knowledge`, `--http3`
- Wireshark display filters: `tcp.flags.syn == 1`, `http2.streamid`
