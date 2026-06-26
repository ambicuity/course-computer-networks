# Content and Internet Traffic

> Internet traffic is two things at once: it is in *seismic shift* (FTP and email dominated before 1994, the Web dominated by 2000, P2P by 2003, streamed video by the late 2000s, and by 2014 Cisco predicted 90% of all Internet traffic would be video in one form or another), and it is *highly skewed* — a small number of popular items account for the bulk of requests. The skew follows a power law: when N items are available, the fraction of all requests for the kth most popular one is approximately C / k where C = 1 / (1 + 1/2 + ... + 1/N) is the normalization constant. This is **Zipf's law** (Zipf, 1949), and it appears on a log-log plot as a straight line. Power laws also describe the topology of the Internet (Faloutsos et al., 1999) and the distribution of city populations. The two facts together — the *fast change* and the *long tail* — mean that an "average" site is not a useful concept; you must design for the popular *and* the long tail. This lesson builds a traffic-composition modeler, a Zipf-distributed request simulator, and a Pareto-fraction calculator that proves the 80/20 rule from first principles.

**Type:** Build
**Languages:** Python
**Prerequisites:** Basic probability, log-log plots, the streaming lessons in this phase
**Time:** ~80 minutes

## Learning Objectives

- Plot a Zipf distribution on both linear and log-log axes and identify it as a straight line on the log-log plot.
- Simulate N requests against M items using a Zipf popularity distribution and verify the 80/20 rule empirically.
- Trace the four-step evolution of Internet traffic composition (FTP/email → Web → P2P → video) and explain why each transition happened.
- Distinguish power-law (Zipf) decay from exponential decay, and explain why the long tail cannot be ignored.
- Compute the bandwidth fraction consumed by a traffic category given total bandwidth and category share.
- Identify the operational consequence of Zipf popularity for CDN design: caching the top 1% captures most of the value.

## The Problem

It is January 2008 and you are a network engineer at a Tier-1 ISP. Your management has asked for a five-year capacity plan. You need to answer two questions:

1. **What kind of traffic is growing?** Your intuition says "video" but your intuition is not a plan. You need a defensible decomposition of total traffic into categories (Web, P2P, video, other) over time, with the bandwidth each category consumes.
2. **Where is the traffic concentrated?** A small set of sites (YouTube, Netflix, Facebook) account for the majority of bytes. Do you provision the network for the *median* site, the *peak* site, or the *aggregate* of the long tail?

The first question is about *traffic composition*; the second is about *content popularity*. Both are answered by the textbook's two essential facts about Internet traffic: (1) it changes quickly, and (2) it is highly skewed.

Without these two facts, every capacity plan over-provisions for the long tail and under-provisions for the spikes. With them, you can build a model that says: "Video will be 65% of traffic by 2025, and the top 1% of items will account for 40% of all requests." That model tells you to provision transit bandwidth for video (large flows, asymmetric) and to deploy caches that absorb the top 1% (small storage, high hit rate).

## The Concept

### The four eras of Internet traffic

The textbook identifies four distinct eras, each with a different dominant application:

| Era | Years | Dominant traffic | Why it dominated |
|---|---|---|---|
| 1 | pre-1994 | FTP, email, telnet | Academic and research network; bulk file transfer |
| 2 | 1994–2000 | Web (HTTP) | Mosaic → Netscape → mass-market browsers |
| 3 | 2000–2007 | P2P (Napster, Kazaa, BitTorrent) | Music then movie sharing; "free" bandwidth from peers |
| 4 | 2007–present | Video (YouTube, Netflix, Twitch) | Broadband access + cheap storage + adaptive streaming |

Each era's traffic mix was driven by an *application*, not by the network. The network's role was to *accommodate* the application. The bandwidth number that operators plan against changes by an order of magnitude per era, even though the number of users grew much more slowly.

Cisco's Visual Networking Index forecast that by 2014, 90% of all Internet traffic would be video in one form or another. By 2020, this prediction had been *exceeded*: video-on-demand alone (Netflix, YouTube, Amazon Prime) was over 60% of downstream traffic in most access networks, and live streaming (Twitch, TikTok live) added another 10–15%.

### Why voice-over-IP is a "minor blip"

Voice-over-IP (the subject of the previous lesson) is always a small fraction of total Internet traffic — typically 1–2% — even though it is *critical* to the applications that use it. The reason is fundamental: a voice call is 64 kbps; a video stream is 4–25 Mbps. The two orders of magnitude gap in bandwidth means that even with hundreds of millions of VoIP users, the aggregate bandwidth is a rounding error compared to video.

But VoIP stresses the network *differently*: it is latency-sensitive, not bandwidth-sensitive. The textbook distinguishes "stressing the network in other ways" (latency, jitter, packet-loss sensitivity) from "stressing the network in volume" (bandwidth, storage, transit cost). Both are real engineering concerns, but they require different design responses.

### Zipf's law: the formal statement

For N items ranked 1 to N, the relative popularity of the kth item is

```
P(k) = C / k,    C = 1 / (1 + 1/2 + 1/3 + ... + 1/N)
```

The constant C is the harmonic-number normalization that makes the probabilities sum to 1. For large N, the harmonic sum is approximately ln(N) + γ where γ ≈ 0.5772 is the Euler-Mascheroni constant. The key consequence: the most popular item is about 7 times as popular as the 7th most popular item, regardless of N. The textbook calls this "rank-proportional popularity."

A Zipf distribution has three properties that matter for design:

1. **Heavy tail.** The decay is polynomial, not exponential. The probability of the 1000th item is only 1000× smaller than the 1st, not e^1000× smaller. This means the long tail is *significant* — the total weight of the tail is comparable to the total weight of the head.
2. **Scale-free.** The shape is the same at every scale. If you plot items 1–100, the curve looks the same as items 1–10,000. This is the "self-similar" property the textbook describes in section 7.5.1.
3. **Linear on log-log.** Plotting log P(k) vs log k gives a straight line with slope -1. This is the visual signature of a power law.

### Why the long tail matters (the Anderson argument)

The textbook quotes Chris Anderson's *The Long Tail* (2008) on the long tail of content. The argument: even if no individual unpopular item is popular, the *aggregate* of all unpopular items can be a large fraction of the total. A library that stocks the top 1% of books has 60% of the demand. A library that stocks the *bottom* 99% has the remaining 40% — and as the catalog becomes digital and the marginal cost of carrying an item approaches zero, the long tail becomes economically important.

For network operators, the consequence is that the *unpopular* sites are also worth caching, just less aggressively. A typical Web cache that holds the top 1% of items captures 50% of requests; expanding to the top 10% captures 80% of requests; expanding to the top 50% captures 95%. The marginal value of each additional percent falls off quickly, but it is never zero.

### Power law vs exponential decay

The textbook contrasts Zipf (power-law) decay with exponential decay. Exponential decay has the form e^(-t/α) and is what you see with radioactive atoms: half-life is constant, and the tail is negligible. Zipf decay has the form 1/k, and the tail is *not* negligible — the total weight of the tail (from rank N/2 to N) is comparable to the weight of the head (rank 1 to N/2).

For design: a Zipf-distributed workload needs caches and indexes that cover the long tail, not just the head. An exponentially-distributed workload (e.g., exponential inter-arrival times) can be designed for the head only, because the tail is statistically invisible.

### Self-similarity and the "packet train" model

The textbook cites Leland et al. (1994) on self-similarity in network traffic. The observation: Ethernet traffic, when measured at multiple time scales (1 ms, 10 ms, 100 ms, 1 s, 10 s), shows burstiness at *every* scale. This is in contrast to Poisson traffic, which smooths out at long time scales. The practical consequence: buffers sized for a Poisson workload under-perform for real network traffic, because real traffic has "packet trains" — bursts of dozens of back-to-back packets followed by gaps — that the Poisson model would predict as extremely unlikely.

The connection to content popularity: heavy-tailed flow duration distributions (a few very long flows, many short ones) plus heavy-tailed file size distributions (a few very large files, many small ones) compound to produce self-similar aggregate traffic. The textbook calls these the "elephants and mice" of networking.

## Build It

We will use the existing `code/main.py` which implements four self-contained functions:

1. **Traffic composition table** — `build_composition_table()` takes a list of years, total Gbps per year, and per-year category shares, and returns a list of `YearlyComposition` records. Run `main()` to see a 2010–2025 table with Web, P2P, video, and other.
2. **Bandwidth fraction** — `bandwidth_fraction(total, share_percent)` multiplies. Used in 1 to compute the per-category Gbps from the total.
3. **Zipf popularity** — `zipf_popularity(rank, exponent=1.0)` returns `1 / rank^exponent`. The textbook uses exponent = 1.0; empirically measured exponents for Web traffic cluster around 0.7–1.2.
4. **Zipf request simulation** — `simulate_zipf_requests(num_items, num_requests, exponent, seed)` draws N requests from M items with Zipf-distributed probability and returns the empirical popularity. `pareto_80_20_fraction(popularity)` returns the fraction of items needed to reach 80% of accesses.

Steps:

1. Read the textbook section 7.5.1 ("Content and Internet Traffic") and skim 7.5 (the chapter introduction on Content Delivery).
2. Open `code/main.py` and look at the `YearlyComposition` dataclass. Note the `__post_init__` validator that enforces the shares sum to 100% — this is the same kind of invariant that `data[]` does in a real network telemetry pipeline.
3. Run `python3 code/main.py`. The output should be a 4-year composition table followed by a 100-item Zipf simulation showing that ~10% of items account for ~80% of requests.
4. Edit `simulate_zipf_requests(num_items=100, num_requests=100_000, exponent=1.1, seed=42)`. Try `exponent=0.5` (flatter distribution, more long-tail) and `exponent=2.0` (steeper distribution, less long-tail). How does the 80/20 fraction change?
5. Edit `years` and `shares` in `main()` to add a 2030 forecast. The textbook says video was 90% by 2014; what does the extrapolation look like to 2030?

## Use It

| API call | What it does | Typical output |
|---|---|---|
| `YearlyComposition(year, total_gbps, categories)` | Create an immutable composition record (frozen dataclass) | — |
| `build_composition_table(years, totals, shares)` | Build a list of compositions across years | list of `YearlyComposition` |
| `bandwidth_fraction(total_gbps, share_percent)` | Compute the bandwidth of one category | float Gbps |
| `zipf_popularity(rank, exponent=1.0, base=1.0)` | Compute relative popularity of a rank | float |
| `simulate_zipf_requests(num_items, num_requests, exponent, seed)` | Draw N requests from a Zipf distribution | list of `(item, score)` pairs |
| `pareto_80_20_fraction(popularity)` | Fraction of items needed to reach 80% of accesses | float in [0, 1] |
| `print_composition_table(table)` | Print a formatted table of compositions | None (side effect) |

The output of `pareto_80_20_fraction(simulate_zipf_requests(100, 100_000, 1.1, 42))` is typically around 0.10–0.15 — about 10–15% of items account for 80% of accesses. The textbook's "80/20 rule" is an approximation; the real value depends on the exponent.

## Ship It

The deliverable is the lesson folder:

```
phases/13-streaming-real-time-media-and-content-delivery/05-content-and-internet-traffic/
├── assets/
│   └── content-and-internet-traffic.svg        # Zipf curve + composition table
├── code/
│   └── main.py                                  # composition modeler + Zipf simulator
├── docs/
│   └── en.md                                    # this file
├── notebook/
│   └── notes.md                                 # your worked examples
├── outputs/
│   └── trace.json                               # sample run output
└── quiz.json
```

To prove the lesson works:

1. `python3 code/main.py` — must print the composition table, the Zipf popularity table, and the Pareto fraction without errors.
2. `python3 -m py_compile code/main.py && echo OK` — must print `OK`.
3. Open `assets/content-and-internet-traffic.svg` in a browser. The diagram should show a log-log Zipf curve and a stacked bar of traffic composition across years.

## Exercises

1. **Log-log plot of Zipf.** Generate a Zipf distribution with N=1000 items and plot `log(P(k))` vs `log(k)`. Is the slope approximately -1? (Yes, for exponent = 1.0.) What happens to the slope for exponent = 0.5? For exponent = 1.5?
2. **80/20 vs 90/10 vs 50/50.** For a Zipf distribution with N=1000 items, compute the fraction of items needed to reach 50%, 80%, 90%, and 95% of accesses. How does the result change with the Zipf exponent? (Higher exponent → steeper curve → smaller fraction needed.)
3. **Exponential vs power law.** Generate two distributions: a Zipf with exponent=1.0 over 1000 items, and an exponential with the same mean. Compare the fraction of accesses captured by the top 1% of items. (Zipf: ~30%; exponential: ~60%.) Why is the exponential "easier" to cache?
4. **Long-tail economics.** A music streaming service has 50 million tracks. The top 1% (500,000 tracks) account for 80% of plays. Should the service cache the top 1% only, or invest in caching the long tail? (Answer: the top 1% is enough to satisfy 80% of users; the remaining 20% is spread across 49.5 million tracks. Caching the long tail is only economical if the marginal cost per track is very low — which it is for a streaming service with cold storage on disk.)
5. **Voice vs video bandwidth.** A region has 1 million subscribers. Each makes a 30-minute VoIP call per day at 64 kbps. Each watches 2 hours of streaming video per day at 5 Mbps. Compute the daily aggregate bandwidth for each. (VoIP: 1e6 * 0.5 hr * 64 kbps = 32,000 GB/day. Video: 1e6 * 2 hr * 5 Mbps = 4,500,000 GB/day. Video is 140× the VoIP bandwidth — yet operators usually plan for VoIP's latency, not video's volume.)
6. **Self-similarity and buffer sizing.** A router has a 1 Gbps link and an output buffer of 64 KB. The traffic is Poisson with mean rate 500 Mbps. What is the probability the buffer overflows in any 1-second interval? (Poisson: probability of a 64 KB burst at 1 Gbps is e^(-64e3 * 8 / 500e6) ≈ e^(-1.024) ≈ 36% per millisecond, ~0% per second — buffer is fine.) Now suppose the traffic is self-similar with Hurst parameter H = 0.8. The same buffer overflows with probability 5% per second. *Why does the same buffer size fail?* (Answer: self-similar traffic has long-range dependence; bursts cluster, so the effective peak rate over 1 s is 2–3× the mean.)

## Key Terms

| Term | Meaning |
|---|---|
| Traffic composition | Decomposition of total Internet traffic into categories (Web, P2P, video, other) |
| Zipf's law | Power-law popularity: P(k) = C / k for the kth most popular item |
| Power law | A distribution whose log-log plot is a straight line; heavy-tailed |
| Heavy tail | A distribution whose tail is not negligible; sum of the tail can be a large fraction of the total |
| Long tail | The aggregate of many low-popularity items; comparable in total to the head |
| Self-similarity | A property of traffic where the same burstiness appears at every time scale |
| Hurst parameter | H quantifies self-similarity: H = 0.5 is Poisson, H → 1 is deterministic |
| Pareto principle | The "80/20 rule": a small fraction of items accounts for a large fraction of activity |
| Power-law topology | The Internet's link-degree distribution follows a power law (Faloutsos et al., 1999) |
| Cisco VNI | Cisco Visual Networking Index; periodic forecast of global IP traffic |
| Hurst exponent | Statistical measure of long-range dependence in time series |
| Packet train | A burst of back-to-back packets; signature of self-similar traffic |
| Log-log plot | A plot with both axes in log scale; the visual signature of a power law |
| Harmonic number | H_N = 1 + 1/2 + ... + 1/N; the Zipf normalization constant for exponent = 1 |

## Further Reading

- **Zipf, G. (1949)** — *Human Behavior and the Principle of Least Effort*. The original statement of Zipf's law, applied to word frequencies.
- **Leland, W., Taqqu, M., Willinger, W., & Wilson, D. (1994)** — "On the Self-Similar Nature of Ethernet Traffic" *IEEE/ACM TON* 2(1). The paper that established self-similarity in network traffic.
- **Faloutsos, M., Faloutsos, P., & Faloutsos, C. (1999)** — "On Power-Law Relationships of the Internet Topology" *SIGCOMM CCR* 29(4). The paper that established power laws in Internet topology.
- **Breslau, L., Cao, P., Fan, L., Phillips, G., & Shenker, S. (1999)** — "Web Caching and Zipf-like Distributions" *IEEE/ACM TON* 7(1). The paper that measured Zipf popularity in Web traffic empirically.
- **Anderson, C. (2008)** — *The Long Tail: Why the Future of Business Is Selling Less of More*. The book that popularized the long-tail argument.
- **Cisco Visual Networking Index** — Cisco's annual forecast of global IP traffic, the de-facto reference for traffic-composition numbers.
- **Peterson, L. & Davie, B.** — *Computer Networks: A Systems Approach*, section 7.5.1. The textbook this lesson series is built from.
