# HTTP/2 Coalescing and Stream Deadlock

> The browser opens one TLS connection, reuses it for three origins via connection coalescing, and a server stream-window stall freezes all three sites at once.

**Type:** Lab
**Languages:** Python (stdlib), HTTP/2 frame concepts, curl
**Prerequisites:** Phase 12 HTTP lesson, Phase 17 lesson 13
**Time:** ~90 minutes

## Learning Objectives

- Explain HTTP/2 connection coalescing and when it triggers across origins
- Read the stream and connection window flow-control counters and identify a deadlock
- Distinguish a coalescing-induced stall from a TLS cert mismatch and from DNS failure
- Propose mitigations: disable coalescing, tune WINDOW_UPDATE, or split origins

## The Problem

HTTP/2 multiplexes many streams over one TLS connection. When a client resolves `a.example`, `b.example`, and `c.example` to the same IP and the TLS certificate covers all three (Subject Alternative Names), the browser uses connection coalescing: it opens one TLS+HTTP/2 connection and sends requests for all three origins over it as separate stream IDs.

When it works this saves a handshake. When it fails, one blocked stream stalls every other coalesced origin because they share the same TCP connection and the same HTTP/2 connection-level flow-control window. A server that stops sending WINDOW_UPDATE (or a middlebox that trims SETTINGS_MAX_CONCURRENT_STREAMS) freezes `a`, `b`, and `c` simultaneously, even though each site is healthy on its own.

**Concrete 8-step failure scenario** — browser loads `a.example/index.html` which embeds a font from `b.example` and a beacon from `c.example`; all three resolve to `203.0.113.42`:

1. **DNS + TLS handshake.** Browser opens TCP to `203.0.113.42`, negotiates TLS 1.3 with ALPN `h2`. Server certificate SAN lists all three hostnames. Server sends SETTINGS: `SETTINGS_MAX_CONCURRENT_STREAMS=100`, `SETTINGS_INITIAL_WINDOW_SIZE=65535`. Both connection and stream windows start at 65535 bytes.
2. **Coalescing decision.** Browser needs `b.example`. Same IP? Yes. Valid SAN? Yes. ALPN `h2`? Yes. Browser reuses the existing connection; no second handshake. The `:authority` pseudo-header carries `b.example` on the existing socket.
3. **Stream assignment.** Browser opens stream 1 (`GET a.example/index.html`), stream 3 (`GET b.example/font.woff2`), stream 5 (`GET c.example/beacon.js`). Client-initiated streams use odd IDs. Each inherits `stream_window=65535`.
4. **Stream 1 drains the connection window.** Server sends HEADERS then DATA on stream 1. After 65535 bytes of DATA the connection-level window reaches zero. Server pauses and waits for a connection-level WINDOW_UPDATE.
5. **Client stalls processing stream 1.** The browser is parsing HTML and executing render-blocking scripts. The application layer has not consumed stream 1's data from the receive buffer, so the client does not issue WINDOW_UPDATE on stream 1 or on the connection.
6. **Streams 3 and 5 block.** Server has font and beacon bytes ready but `conn_window=0`. Both streams show HEADERS delivered but zero DATA sent. Browser network panel shows both as `pending`; TTFB climbs.
7. **Deadlock established.** Stream 1 waits for the client to free connection credit. Streams 3 and 5 wait for connection credit. The client cannot paint (needs the font from stream 3) and therefore never frees stream 1's buffer. `chrome://net-export` logs `HTTP2_SESSION_SEND_DATA_BLOCKED` and `HTTP2_STREAM_FLOW_CONTROL_BLOCKED`.
8. **Timeout.** After ~30 seconds Chrome emits `ERR_HTTP2_PROTOCOL_ERROR` and tears down the connection. All three origins fail together. `curl` to each origin succeeds individually because curl opens its own fresh connection with a clean window.

Symptoms: `curl` to each origin succeeds independently, but a browser load of a page that embeds resources from all three stalls mid-load; the network tab shows all three pending on one connection; `chrome://net-export` shows `SOCKET_POOL_STALL_MAX_SOCKETS` and `HTTP2_STREAM_DEADLOCK`.

## The Concept

HTTP/2 (RFC 7540, 9113) defines:

- **Stream**: a bidirectional frame flow with a numeric ID (client odd, server even).
- **Connection-level flow control**: a window (default 65535 bytes) shared by all streams. Each DATA frame consumes credit; WINDOW_UPDATE replenishes.
- **Stream-level flow control**: per-stream window.
- **SETTINGS_MAX_CONCURRENT_STREAMS**: cap on simultaneously active streams.

**Key frame types**

| Type | Hex | Purpose |
|---|---|---|
| HEADERS | `0x1` | Opens a stream; carries HPACK-compressed HTTP fields |
| DATA | `0x0` | Carries body bytes; decrements both connection and stream windows |
| SETTINGS | `0x4` | Exchanges connection parameters; receiver must ACK (flags=`0x1`) |
| WINDOW_UPDATE | `0x8` | Increments flow-control window; stream ID 0 = connection-level |
| RST_STREAM | `0x3` | Abruptly terminates one stream; carries 32-bit error code |
| GOAWAY | `0x7` | Gracefully drains connection; carries last-processed stream ID |

**Connection vs. stream window arithmetic**

Both windows start at `SETTINGS_INITIAL_WINDOW_SIZE` (default 65535). The sender must respect:

```
bytes_allowed = min(conn_window, stream_window)
```

A WINDOW_UPDATE targeting stream ID 0 increments the connection window; targeting stream ID N increments only that stream's window. Zero-increment WINDOW_UPDATE is a protocol error (PROTOCOL_ERROR).

**Coalescing decision algorithm (RFC 9113 § 9.1)**

A client MAY coalesce a new origin onto an existing connection if all three hold:

1. The new origin resolves to the same IP as the existing connection (compared byte-for-byte, not re-resolved later).
2. The existing connection's TLS certificate is valid for the new origin (hostname matches SAN or CN; chain is trusted; not expired).
3. The existing connection negotiated `h2` via ALPN.

Clients are not required to coalesce. Chromium, Firefox (`network.http.http2.coalesce-hostnames=true`), and Safari all coalesce by default. The server cannot opt out via configuration alone.

**How middleboxes corrupt SETTINGS**

A TLS-terminating proxy can rewrite SETTINGS parameters before forwarding. Common harmful rewrites:

- `SETTINGS_MAX_CONCURRENT_STREAMS` lowered to 1: serializes all streams; combined with coalescing, each coalesced origin queues behind the previous.
- `SETTINGS_INITIAL_WINDOW_SIZE` lowered to 4096: every new stream exhausts its window after one small DATA frame.
- WINDOW_UPDATE frames batched or dropped: introduces artificial credit starvation.

Diagnostic signature: SETTINGS values visible in `nghttp -v` or Wireshark differ from the origin server's configured values. Bypass the middlebox via `--resolve` to compare.

Deadlock arises when:

- A server sends DATA exhausting the connection window then waits for WINDOW_UPDATE, but the client is blocked on another stream and never issues the update.
- A middlebox caps `MAX_CONCURRENT_STREAMS` to 1 so the second origin's request queues indefinitely.
- The server's response on stream 1 depends on a callback to origin 2 over the same connection → circular wait.

## Build It

Work through `code/main.py` — a frame-level HTTP/2 simulator — using this 8-step procedure:

1. **Setup.** `--mode setup --origins a.example,b.example,c.example --ip 203.0.113.42`. Confirm: `conn_window=65535`, 3 origin slots.
2. **Exchange SETTINGS.** `--mode settings --max-concurrent 100 --initial-window 65535`. Server frame hex: `00 00 0c 04 00 00 00 00 00 | 00 03 00 00 00 64 | 00 04 00 00 ff ff`. Client ACKs with SETTINGS flags=`0x1`.
3. **Open streams.** `--mode open-streams --stream-ids 1,3,5 --authorities a.example,b.example,c.example`. All three report `OPEN`, `stream_window=65535`.
4. **Drain connection window.** `--mode send-data --stream 1 --bytes 65535`. After completion: `conn_window=0`, `stream1_window=0`. Streams 3 and 5 have stream credit but cannot send.
5. **Observe deadlock.** `--mode status` shows streams 3 and 5 as `BLOCKED(conn_window=0)`, `DEADLOCK=True`.
6. **Issue connection WINDOW_UPDATE.** `--mode window-update --stream 0 --increment 65535`. Frame hex: `00 00 04 08 00 00 00 00 00 | 00 00 ff ff`. `conn_window` rises to 65535.
7. **Confirm stall clears.** `--mode status` shows streams 3 and 5 `UNBLOCKED`, `DEADLOCK=False`.
8. **Simulate middlebox rewrite.** `--mode middlebox --max-concurrent 1`. Open streams 1 and 3; observe stream 3 immediately enters `REFUSED_STREAM`. Restore with `--max-concurrent 100`.

```text
Browser --TLS(h2, SAN=a,b,c)--> Server:443
  stream 1 (a.example) consumes full conn window
  stream 3 (b.example) waits -> DEADLOCK
  stream 5 (c.example) waits -> DEADLOCK
  WINDOW_UPDATE(stream=0, increment=65535) -> stall clears
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm coalescing | `chrome://net-export`, `nghttp -v` | One connection, multiple `:authority` headers |
| Inspect windows | `h2stat`, server debug logs | Connection window > 0; WINDOW_UPDATEs flowing |
| Reproduce stall | Hold stream 1 open, no WINDOW_UPDATE | Streams 3/5 stuck in `pending` |
| Validate fix | Tune window, split origins, disable coalescing | Streams progress independently |
| Detect middlebox rewrite | Compare `curl -v https://hostname/` vs `curl -v --resolve hostname:443:IP https://hostname/` | SETTINGS values match origin server config |
| Measure window saturation | Wireshark `tcp.analysis.window_full` filter | No `window_full` events during normal load |
| Isolate stream vs. connection block | Check per-stream `stream_window` alongside `conn_window` | `conn_window=0` with healthy stream windows = coalescing deadlock |

## Ship It

Produce an HTTP/2 coalescing runbook under `outputs/` covering these six steps:

**1 — Per-origin independence test.**
```sh
for origin in a.example b.example c.example; do
  curl --http2 -sv "https://$origin/" 2>&1 | grep -E "< HTTP|ALPN"
done
```
If all return 200 independently, the origin servers are healthy and the fault is coalescing-specific.

**2 — Confirm coalescing is occurring.**
Run `nghttp -v https://a.example/` and scan output for `:authority` values other than `a.example`. In `chrome://net-export` JSON, search for `HTTP2_SESSION_RECV_HEADERS` entries with different authority values sharing the same `source_id`.

**3 — Tune server-side SETTINGS.**

nginx:
```nginx
http2_max_concurrent_streams 128;
http2_recv_buffer_size       256k;
```

Apache:
```apache
H2MaxSessionStreams 128
H2InitialWindowSize 1048576
```

Raise OS TCP buffers: `sysctl -w net.core.rmem_default=4194304 net.core.wmem_default=4194304`.

**4 — Disable coalescing for diagnosis.**
Chrome: `--disable-features=Http2Coalescing`. Firefox: `network.http.http2.coalesce-hostnames=false` in `about:config`. If the stall disappears, root cause is confirmed.

**5 — Middlebox audit.**
Capture with Wireshark (`SSLKEYLOGFILE` for TLS decryption). Compare `SETTINGS_MAX_CONCURRENT_STREAMS` and `SETTINGS_INITIAL_WINDOW_SIZE` in the capture against origin server config. A discrepancy confirms SETTINGS rewriting; engage the network team to bypass or reconfigure the proxy.

**6 — Split origins as permanent mitigation.**
Move `b.example` to a distinct IP (`203.0.113.43`) so the coalescing precondition (same IP) fails. Alternatively issue a separate TLS certificate for `b.example` that does not include `a.example` in its SAN list — the browser will not coalesce connections whose certificates do not mutually cover both origins.

Start with [`outputs/prompt-http2-coalescing-stream-deadlock.md`](../outputs/prompt-http2-coalescing-stream-deadlock.md).

## Exercises

1. Reproduce the deadlock by setting `INITIAL_WINDOW_SIZE=0` on the server and explain why no stream can start. What RST_STREAM error code does the client emit, and why is it a FLOW_CONTROL_ERROR rather than a PROTOCOL_ERROR?
2. Add a middlebox that silently rewrites `SETTINGS_MAX_CONCURRENT_STREAMS` to 1 and show the second origin queues forever. What is the minimum value that allows all three coalesced origins to proceed without queuing?
3. Propose a mitigation where the client opens a second connection when the first stalls for more than 1 second. Describe the threshold metric, the fallback algorithm, and how it handles the race if the original connection recovers simultaneously.
4. Contrast HTTP/2 coalescing with HTTP/3 (QUIC) connection migration: does QUIC suffer the same head-of-line blocking at the transport layer? Explain how QUIC stream isolation differs even though both protocols multiplex over one connection.
5. Evaluate the security implication of coalescing: can a malicious origin in the same SAN list read another origin's stream data by injecting HEADERS with a spoofed `:authority`? What prevents cross-origin data leakage in a well-implemented HTTP/2 stack?
6. The server sends a PUSH_PROMISE on stream 2 (even, server-initiated) promising a resource for `b.example` before the client opens stream 3. Trace the connection window accounting: does PUSH_PROMISE itself consume window credit? When does the corresponding DATA consume credit, and on which stream's window?
7. A load balancer forwards both `a.example` and `b.example` onto a single upstream HTTP/2 connection to a backend that only knows `a.example`. Describe the HTTP/2 error frame sequence that results and explain why the browser ultimately falls back to a separate connection for `b.example`.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| HTTP/2 stream | A request | Bidirectional frame flow with a numeric ID over one TCP connection |
| Connection coalescing | Reuse | Client reuses one h2 connection for multiple SAN-covered origins |
| Connection window | Flow credit | Shared byte budget for all streams on a connection; starts at 65535 |
| WINDOW_UPDATE | Credit refill | Frame restoring flow-control credit; stream ID 0 = connection-level |
| MAX_CONCURRENT_STREAMS | Stream cap | SETTINGS parameter limiting simultaneously active streams |
| SAN | Cert names | Subject Alternative Names extension listing every hostname a cert covers |
| ALPN | Proto negotiation | TLS extension (RFC 7301) that selects h2 vs. http/1.1 during handshake |
| Head-of-line blocking | Stall | One blocked stream prevents progress on all others sharing the connection window |
| HPACK | Header compression | Stateful compression for HTTP/2 headers (RFC 7541); replaced by QPACK in HTTP/3 |
| SETTINGS frame | Config exchange | Binary frame (type `0x4`) carrying key-value connection parameters; must be ACKed |
| RST_STREAM | Stream abort | Frame (type `0x3`) that terminates one stream immediately without closing the connection |
| GOAWAY | Connection close | Frame (type `0x7`) draining a connection gracefully; carries last-processed stream ID |

## Further Reading

- RFC 9113 — HTTP/2 (supersedes RFC 7540)
- RFC 9110 — HTTP Semantics (origin model and coalescing rules)
- Chromium net-export logging documentation
- RFC 7301 — TLS ALPN Extension
- RFC 7541 — HPACK: Header Compression for HTTP/2
- Ilya Grigorik, "High Performance Browser Networking" ch. 12 — HTTP/2 (O'Reilly; covers flow control and server push with worked examples)
