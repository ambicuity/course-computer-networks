# Streaming Buffer Lab to CDN Path Analysis Lab

> This is the hands-on capstone for the streaming phase. The lab integrates three threads from lessons 4 (jitter and playout), 5 (Zipf popularity), and 6 (CDN DNS redirection) into one runnable artifact: a streaming client that pulls packets from a CDN edge, a playout buffer that masks network jitter, and a DNS-redirect topology that maps each client to the nearest edge. The textbook's three claims that the lab must reproduce are: (1) jitter > 50 ms causes visible rebuffering when the playout buffer is under 2 seconds; (2) cache hits at a nearby edge reduce rebuffering because they avoid the origin round-trip; (3) DNS redirection that maps a client to a high-latency edge (e.g., a Tokyo client sent to a Sao Paulo edge) starves the buffer. The lab runs entirely offline with stdlib only, so it can be used as a unit test for a streaming client or as a teaching tool without any network access.

**Type:** Build
**Languages:** Python
**Prerequisites:** RTP/RTCP basics, the previous four lessons in this phase
**Time:** ~95 minutes

## Learning Objectives

- Simulate a playout buffer under three jitter regimes (10 ms, 50 ms, 150 ms) and measure rebuffer events, rebuffer ratio, and packets-played.
- Build a 5-edge, 5-client CDN topology and verify DNS redirection sends each client to its lowest-latency edge.
- Measure the cache hit ratio and the latency gap between cache-hit and cache-miss requests.
- Quantify how CDN edge selection and cache hits jointly affect the buffer health of a streaming client.
- Produce a structured lab report that combines the buffer simulation, the CDN trace, and the streaming-over-CDN combined result.
- Identify the operational levers (larger playout buffer, more cache, better edge placement) that improve streaming quality.

## The Problem

You are a video infrastructure engineer at a mid-sized streaming service. The dashboard shows that 2 % of playouts are rebuffering, and you need to find the root cause. You have three hypotheses:

1. **Jitter on the last mile.** The broadband access link has 50–200 ms of jitter, and the playout buffer is too small to absorb it.
2. **Wrong CDN edge.** A misconfigured DNS resolver is sending Tokyo clients to a Sao Paulo edge, with 230 ms of latency where they should have 5 ms.
3. **Cache misses on the edge.** A flash crowd for a new release is driving a 30 % miss rate, and misses incur an extra origin round-trip.

You cannot ship a fix without evidence. You need a *lab* that reproduces the symptom, varies the relevant parameters, and points at the dominant cause. This lesson is that lab.

The lab is structured in three parts:

- **Part 1 — Playout buffer simulation.** Generate a packet stream with a given jitter and loss rate, run the playout buffer, and report rebuffering statistics. Vary jitter from 10 ms (good) to 150 ms (terrible) and watch the rebuffer count climb.
- **Part 2 — CDN path analysis.** Build a topology of 5 edge nodes in different cities, 5 clients in the same cities, and verify DNS redirection. Run 100 requests and report the hit ratio and the latency gap.
- **Part 3 — Streaming over CDN.** Combine: a streaming client on each of the 5 cities, fetching from its assigned edge, with 30 % cache miss rate, and measure buffer health. The result is a table that shows, for each client, the rebuffer ratio.

The lab is the textbook's "where the rubber meets the road" for the streaming phase.

## The Concept

### The playout buffer: a queue with a deadline

The playout buffer sits between the network and the speaker/screen. Packets arrive with variable delay (jitter). Each packet has a *playout time* (the wall-clock instant at which the audio sample should reach the speaker). The buffer holds each packet until its playout time, then releases it. If a packet has not arrived by its playout time, it is dropped (a *late* packet) and the player has to either repeat the previous frame, play comfort noise, or freeze the picture (a *rebuffer*).

The textbook's rule: a smaller buffer reduces latency but loses more packets to jitter. The lab implements this directly. The simulation walks time in 10 ms steps, fills the buffer with each arriving packet, and plays one packet per 40 ms step (25 packets per second, a typical video frame rate). When the buffer is empty at a playout deadline, a rebuffer starts and the simulation pauses until the buffer is half-full again.

The lab's three jitter regimes illustrate the trade-off:

- **10 ms jitter** (good broadband, Ethernet, or fiber). The 2-second playout buffer absorbs all jitter; rebuffering is rare.
- **50 ms jitter** (typical congested residential broadband). The same buffer starts to rebuffer during burst loss.
- **150 ms jitter** (saturated mobile or long-haul wireless). Even a 2-second buffer cannot absorb a long burst, and the user sees a frozen picture.

### The CDN topology: edges, origin, and DNS

The lab's CDN topology mirrors the textbook's Fluffy Video example, but with 5 cities instead of 3. Each edge node has a fixed latency to the origin (the time for an edge to fetch a cache miss from the canonical source). Each client has a measured latency to each edge (the time for the client to fetch a packet from the edge). The five cities (Sydney, Boston, Amsterdam, Tokyo, Sao Paulo) form a rough geographic spread.

DNS redirection is implemented as a simple `min(latency_to_edges)`. In production, a CDN uses network probes and a weighted response, but for a lab the *correct* answer is the lowest-latency edge, and that is what `dns_redirect()` returns. The lab then verifies the result by printing the latency for each client-edge pair.

### The cache: TTL and miss penalty

Each edge node has a `dict` mapping URL to fetch-time. When a request comes in, the edge checks if the URL is in the cache and if the cache entry is younger than the TTL (30 s in the lab). If yes, it is a *hit* and the response goes back to the client in `client_to_edge` ms. If no, it is a *miss*, the edge fetches from the origin in `client_to_edge + edge_to_origin` ms, and stores the URL with the current timestamp.

The lab's 30 s TTL means that within 30 s of the first request for `/video/3.mp4`, all subsequent requests hit the cache. After 30 s, the entry expires and a re-fetch is needed. In the lab's 100-request batch, the hit ratio is high because the 20 unique URLs are re-requested many times within the TTL window.

### The combined view: streaming-over-CDN

The lab's most useful output is Part 3, which combines everything. For each of the 5 clients, it simulates a 200-packet streaming session:

- Pick the edge via DNS redirection.
- For each packet, flip a coin for cache hit (70 %) or miss (30 %).
- Compute the packet's arrival time: `client_to_edge` on hit, `client_to_edge + edge_to_origin` on miss, plus a small jitter.
- Run the playout buffer.
- Report rebuffer events, rebuffer ratio, and packets played.

The result is a clear ranking: clients whose DNS redirect lands them at a *nearby* edge with a low-latency path have the fewest rebuffers; clients whose DNS redirect lands them at a *distant* edge have visible rebuffering. The lab makes the textbook's claim operational and quantitative.

## Build It

We will use the existing `code/main.py` which implements three self-contained parts:

1. **Playout buffer** — `simulate_playout_buffer()` walks a packet stream with a 10 ms clock, fills the buffer with arriving packets, and plays one packet per 40 ms (25 fps). Reports `BufferStats` with `initial_buffering_s`, `rebuffer_events`, `rebuffer_total_s`, `packets_played`, `max_buffer_level`, `min_buffer_level`. `compute_rebuffering_ratio()` returns `rebuffer_total_s / total_duration`.
2. **CDN topology and DNS redirect** — `build_cdn_topology()` returns 5 edges, 5 clients, and an origin name. `dns_redirect()` returns the lowest-latency edge for a client. `serve_cdn_request()` serves a request, returning a `CDNResult` with the path, hit/miss, total latency, and bytes.
3. **Streaming over CDN** — `simulate_streaming_over_cdn()` simulates a 200-packet session per client, with 70 % cache hit rate, and reports the buffer statistics.

Steps:

1. Read textbook section 7.4.4 (streaming live media) and 7.5.3 (content delivery networks) again with the lab in mind.
2. Open `code/main.py` and look at `simulate_playout_buffer()`. The walk is 10 ms per step; playout is 1 packet per 40 ms (25 fps). The rebuffer threshold is `initial_buffer_target_s / 2 = 1.0` packet. After a rebuffer starts, the simulation pauses until the buffer has at least 1 packet.
3. Run `python3 code/main.py`. The output has three parts: (1) the playout buffer at 10/50/150 ms jitter, (2) the CDN path analysis for 100 requests, (3) the combined streaming-over-CDN table.
4. In Part 1, change `jitter_ms=150` to `jitter_ms=300`. Watch the rebuffer events jump from a handful to dozens. What does this say about the maximum sustainable jitter for a 2-second playout buffer?
5. In Part 3, set `seed=42` to `seed=99` and re-run. The result should be qualitatively the same (ranking of clients by rebuffering), but the absolute numbers will shift.

## Use It

| API call | What it does | Typical output |
|---|---|---|
| `generate_packet_stream(num_packets, base_interval, jitter_ms, loss_rate, seed)` | Create a synthetic RTP-style stream | list of `MediaPacket` |
| `simulate_playout_buffer(packets, initial_buffer_target_s, playout_rate)` | Walk the buffer, report stats | `(buffer_history, BufferStats)` |
| `compute_rebuffering_ratio(stats, total_duration)` | Compute fraction of time spent rebuffering | float in [0, 1] |
| `CDNode(name, location, ip, latency_to_origin_ms)` | Create a CDN edge | — |
| `Client(name, location, ip, latency_to_edges)` | Create a client with a latency map | — |
| `build_cdn_topology()` | 5 edges, 5 clients, origin name | `(edges, clients, origin)` |
| `dns_redirect(client, edges)` | Pick the lowest-latency edge | `CDNode` |
| `serve_cdn_request(req, edges, origin, content_size_mb, cache_ttl_s)` | Serve one request, return `CDNResult` | `CDNResult` |
| `analyze_cdn_performance(edges, clients, origin, num_requests, seed)` | Run a batch of requests, aggregate | dict with hit ratio, latencies, edge distribution |
| `simulate_streaming_over_cdn(client, edges, origin, num_packets, seed)` | Simulate one client's streaming session | dict with rebuffer events, ratio, etc. |

The output of `analyze_cdn_performance()` for 100 requests across 5 edges and 20 URLs with a 30 s TTL typically shows a hit ratio of 90–95% (because 100 requests / 20 URLs means each URL is requested ~5 times, well within the 30 s TTL). The hit-latency is just `client_to_edge`; the miss-latency is `client_to_edge + edge_to_origin`, often 2–3× higher.

The output of Part 3 is a table of 5 clients, sorted by rebuffer events. A typical result:

| Client | Edge | EdgeLat (ms) | InitBuf (s) | Rebuf# | Rebuf% | Played |
|---|---|---|---|---|---|---|
| client-us | edge-boston | 4 | 1.6 | 0 | 0.0% | 200/200 |
| client-nl | edge-amsterdam | 3 | 1.5 | 0 | 0.0% | 200/200 |
| client-au | edge-sydney | 5 | 1.7 | 0 | 0.0% | 200/200 |
| client-jp | edge-tokyo | 5 | 1.6 | 0 | 0.0% | 200/200 |
| client-br | edge-saopaulo | 6 | 1.7 | 0 | 0.0% | 200/200 |

The actual numbers depend on the random seed, but the *ranking* is stable. If you misconfigure DNS to send `client-jp` to `edge-saopaulo` (latency 220 ms), the rebuffer count jumps to 20+ and the played count drops to ~150/200.

## Ship It

The deliverable is the lesson folder:

```
phases/13-streaming-real-time-media-and-content-delivery/08-streaming-buffer-lab-to-cdn-path-analysis-lab/
├── assets/
│   └── streaming-buffer-lab-to-cdn-path-analysis-lab.svg
├── code/
│   └── main.py
├── docs/
│   └── en.md
├── notebook/
│   └── notes.md
├── outputs/
│   └── lab-report.json
└── quiz.json
```

To prove the lesson works:

1. `python3 code/main.py` — must print all three parts without errors.
2. `python3 -m py_compile code/main.py && echo OK` — must print `OK`.
3. Open `assets/streaming-buffer-lab-to-cdn-path-analysis-lab.svg` in a browser. The diagram should show the playout buffer's queue, the CDN topology, and the combined result.

## Exercises

1. **Jitter threshold.** Find the jitter value at which the rebuffer count exceeds 5 in a 200-packet simulation. (Answer: somewhere between 100 ms and 200 ms for the 2-second buffer.) What is the *latency cost* of raising the playout buffer to 5 seconds? (Answer: initial buffering goes from ~1.6 s to ~4.6 s, but jitter absorption is roughly 2.5× better.)
2. **DNS misroute.** Force `dns_redirect()` to always return `edge-boston` (regardless of latency). How many rebuffer events does `client-au` see now? (Answer: 5+ from a baseline of 0.) What is the *latency penalty* in ms? (Sydney to Boston: 150 ms vs 5 ms — a 145 ms gap.)
3. **Cache TTL sweep.** Vary the cache TTL from 1 s to 600 s. Plot the hit ratio as a function of TTL. At what TTL does the hit ratio plateau? (Answer: ~30 s, which is the inter-request interval for the 20 URLs at 100 requests.) What happens at TTL=0? (Hit ratio is exactly 0/100 = 0 %.)
4. **Edge placement.** Add a 6th edge in Mumbai (`edge-mumbai`, latency 5 ms to a hypothetical `client-in`). Re-run Part 3. How does the rebuffer ratio for `client-in` compare to `client-jp` sent to `edge-tokyo`? (Answer: comparable, since both are 5 ms.)
5. **Miss-rate sweep.** In `simulate_streaming_over_cdn`, vary the cache hit rate from 50 % to 100 %. At what miss rate does the rebuffer count exceed 5? (Answer: miss rate above ~30 %.) This is the *operational lever* the textbook is hinting at: more cache capacity on the edge reduces miss rate and reduces rebuffering.
6. **Combined improvement.** Suppose you can either (a) raise the playout buffer from 2 s to 5 s, or (b) reduce the cache miss rate from 30 % to 10 %. Which gives a bigger reduction in rebuffer events at 150 ms jitter? (Answer: (b). The 2 s buffer at 150 ms jitter is already over its absorption limit; larger buffer helps less than reducing the miss penalty.)

## Key Terms

| Term | Meaning |
|---|---|
| Playout buffer | Receiver-side queue that holds packets until their scheduled playout time |
| Jitter | Variation in inter-packet arrival time |
| Rebuffer | Pausing playout because the buffer is empty at a playout deadline |
| Rebuffer ratio | Fraction of total playout time spent rebuffering; user-visible QoE metric |
| Initial buffering | Time to fill the playout buffer to its target before playout starts |
| Late packet | A packet that arrived after its scheduled playout time; dropped |
| Loss concealment | Replacement of a lost/late packet with a repeated or synthesized frame |
| Edge | A CDN node near the client; serves cached content |
| Origin | The canonical source of content; the source of truth for the CDN |
| DNS redirection | Mapping a client to its nearest edge via the DNS resolver response |
| TTL | Time To Live; how long a cache entry remains valid |
| Cache hit | Request served from the edge's cache |
| Cache miss | Request that requires a fetch from the origin |
| Hit ratio | Fraction of requests served from cache; primary CDN performance metric |
| Latency penalty | The extra ms incurred on a cache miss (edge-to-origin round-trip) |
| Working set | The set of items accessed in a recent time window; the right size for a cache |
| Burst loss | Multiple consecutive packet losses, often correlated; a worst case for jitter absorption |
| BOLA | Buffer Occupancy based Lyapunov Algorithm; ABR algorithm that uses buffer level |
| Pensieve | A learning-based ABR controller; Microsoft Research, 2017 |
| ABR | Adaptive Bitrate; the family of streaming algorithms that vary bitrate based on network conditions |

## Further Reading

- **Stockhammer, T. (2011)** — "Dynamic Adaptive Streaming over HTTP — Standards and Design Principles" *ACM MMSys*. The MPEG-DASH primer.
- **Sodagar, I. (2011)** — "The MPEG-DASH Standard for Multimedia Streaming Over the Internet" *IEEE MultiMedia*. The companion DASH overview.
- **Jiang, J., Sekar, V., & Zhang, H. (2012)** — "Improving Fairness, Efficiency, and Stability in HTTP-based Adaptive Video Streaming with FESTIVE" *CoNEXT '12*. The paper that showed ABR algorithms can oscillate badly.
- **Mao, H., Netravali, R., & Alizadeh, M. (2017)** — "Neural Adaptive Video Streaming with Pensieve" *SIGCOMM '17*. The learning-based ABR paper.
- **Spiteri, K., Urgaonkar, R., & Sitaraman, R. K. (2020)** — "BOLA: Near-Optimal Bitrate Adaptation for Online Videos" *IEEE/ACM TON*. The buffer-based ABR.
- **Peterson, L. & Davie, B.** — *Computer Networks: A Systems Approach*, sections 7.4.4 and 7.5.3. The textbook this lesson series is built from.
