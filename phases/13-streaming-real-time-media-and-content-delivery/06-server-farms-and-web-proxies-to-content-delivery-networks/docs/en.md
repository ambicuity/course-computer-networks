# Server Farms and Web Proxies to Content Delivery Networks

> The Web's scaling story has three chapters. **Server farms** (textbook section 7.5.2) replace one overloaded box with a cluster behind a load-balancing front-end, using round-robin DNS, packet-level L4 hashing, or HTTP-cookie L7 hashing to keep all packets of one TCP connection on the same backend. **Web proxies** (also 7.5.2) share a browser cache across an organization — every user behind a corporate proxy benefits when a coworker has already fetched the same image. **Content Delivery Networks** (7.5.3) turn the proxy model inside out: the *provider* places copies of the content at dozens of edge locations and uses **DNS redirection** to send each client to the nearest one. Akamai pioneered this in 1998 and remains the industry leader; Cloudflare, Fastly, and AWS CloudFront are the modern competitors. The textbook's "Fluffy Video" worked example shows how a content owner rewrites its HTML to point to `www.cdn.com/fluffyvideo/koalas.mpg` so the *small* HTML stays on the origin and the *large* video bytes come from the edge. The three mechanisms solve different problems at different scales, and the right combination depends on the workload. This lesson builds a server-farm load simulator, an LRU edge cache, a DNS-redirection geo-router, and a cache-size sweep that demonstrates the diminishing returns of edge capacity.

**Type:** Build
**Languages:** Python
**Prerequisites:** HTTP, DNS resolution, basic probability, the previous lesson on content and Internet traffic
**Time:** ~95 minutes

## Learning Objectives

- Explain why a single server cannot serve a popular site and what a server-farm front-end does to a TCP connection's packet stream.
- Compare round-robin DNS, L4 packet-hash, and L7 HTTP-cookie load-balancing policies and identify the middlebox-design pitfall each one avoids or creates.
- Compute the hit ratio of an LRU proxy cache against a Zipf-distributed workload and find the cache size at which diminishing returns set in.
- Trace a CDN DNS-redirection request from client resolver to authoritative CDN nameserver and back, identifying which answer is returned for which client location.
- Select the nearest CDN edge to a client using haversine great-circle distance and explain why network distance is *not* the same as geographic distance.
- Describe the Fluffy Video split-content pattern and explain why most entry pages stay on the origin while large bytes move to the edge.

## The Problem

It is November 7, 2000, and you are the lead engineer for the Florida Secretary of State's election-results Web site. Yesterday the site served 5,000 visitors per day. Today the U.S. presidential election results are being reported, and your site is *the* canonical source for returns. You are getting 5 million requests per hour. Your single Sun server has 2 GB of RAM and a 100 Mbps Ethernet connection. It has been down for six hours.

Three engineers argue in the war room:

- Engineer A: "Buy a bigger server. A 32-way SMP with 32 GB of RAM will handle this."
- Engineer B: "Even if you bought it today, you cannot provision it in 18 hours, and the election results come in tonight. A single machine has a single point of failure. If it crashes, you are off the air for *hours*."
- Engineer C: "We do not have the budget for a CDN. But we can build a server farm in front of our existing machine: a small L4 switch that load-balances TCP connections across 4–8 commodity boxes, each running a copy of the Web site, all behind a single virtual IP. We can deploy this in 4 hours."

Engineer C is right. The textbook's Figure 7-65 shows exactly this: a server farm with a front-end that "balances load across servers." The solution is a 1U Linux box running LVS (Linux Virtual Server) or a hardware load balancer from F5 or Citrix, with 8 backend Web servers behind it. The front end has one virtual IP, the back ends all serve the same content, and the front end decides which packet goes to which back end.

The same day, in 1998, Akamai's founders faced the same problem at internet scale: the early Web was "the World Wide Wait" because popular pages were served from one origin, and the round-trip time plus TCP slow-start plus a single congested uplink combined to make every page slow. Akamai's answer was the CDN: instead of one origin, hundreds of edges; instead of a single IP, DNS that returns the IP of the *nearest* edge.

This lesson is the textbook's chapter on how to build both.

## The Concept

### Server farms: one logical site, many physical boxes

A server farm is a cluster of computers that act as a single Web server. The textbook's Figure 7-65 shows the architecture: an Internet-access link, a front-end (sometimes called a "director" or "load balancer"), and a pool of backend servers, all sharing a back-end database (if the site is dynamic).

The challenge is that the *set* of computers must look like a *single* logical Web site. The textbook lists three possible solutions, all in active use:

**1. DNS-based spreading.** When a DNS request is made for `www.example.com`, the authoritative DNS server returns a *rotating* list of IP addresses. Each client tries the first IP; if it is busy, the client falls back to the next. The DNS server rotates the order between requests, so successive clients get different orderings. This is simple but coarse: it does not balance within a single client's session, and it ignores the actual load on the backends.

**2. Front-end broadcast.** The front end receives all incoming requests and broadcasts them to all backends. Each backend examines the source IP address and replies only if the last 4 bits match its configured selector (so 16 backends each handle 1/16 of the address space). Wasteful on the inbound link, but trivial to implement.

**3. Front-end packet inspection (the "middlebox" approach).** The front end inspects the IP, TCP, and HTTP headers, hashes them to a backend, and forwards. The mapping is the *load-balancing policy*. Policies include:
  - **Round-robin** — cycle through backends in order, remembering which TCP connection belongs to which backend.
  - **Least-connections** — pick the backend with the fewest active TCP connections.
  - **Source-IP hash** — `hash(client_ip) mod N_backends`. Stable, but does not handle NAT (many clients behind one IP).
  - **Cookie-based** — parse the `Cookie:` header, route subsequent requests from the same user to the same backend (so session state is consistent).

The textbook warns that the third approach "violates the most basic principle of layered protocols: each layer must use its own header for control purposes and may not inspect and use information from the payload." The device is called a **middlebox** (like a NAT box or a firewall), and it works — but it is fragile in the face of protocol evolution (HTTP/3 over QUIC, for example, breaks naïve packet-hash approaches).

### The back-end database problem

If the site is purely static, every backend has the same content on local disk and no shared state is needed. The textbook draws the back-end database as a "dashed line" for this reason. But for a site with login, sessions, shopping carts, or any other dynamic state, all backends must see the *same* database — either a single back-end DB (a single point of failure) or a replicated DB (operational complexity).

The textbook's hint: the front end can use **HTTP cookies** to send subsequent requests from the same user to the *same* backend, where that backend can cache the user's session in memory. This is a form of "session affinity" and is the most common middlebox trick in production today.

### Web proxies: shared cache for a community of users

A **Web proxy** is an agent that fetches Web requests on behalf of its users. It is placed between the browsers and the Web servers, and it caches responses in a shared cache. The textbook's Figure 7-66 shows the topology: every browser in the organization is configured to send requests to the proxy; the proxy checks its cache, returns a hit, or fetches from the origin server and caches the result.

The textbook identifies three benefits of a shared proxy cache:

1. **Performance** — repeated requests for the same page are served from memory, often sub-millisecond.
2. **Bandwidth savings** — for organizations and ISPs charged per-byte, the cache reduces transit cost.
3. **Policy / privacy** — the administrator can filter sites, and the proxy can shield the user's IP from the server.

The textbook's empirical finding (Wolman et al., 1999): shared caching is most beneficial up to about 100 users. Beyond that, the long tail of unique pages dilutes the cache and the marginal benefit of additional users becomes small. For ISP-scale caching (millions of users), only the very top of the popularity distribution benefits.

### CDNs: turn the proxy model inside out

A **CDN (Content Delivery Network)** is a network of edge servers distributed across the Internet, owned by a third party, that serves content on behalf of *content owners*. The textbook's Figure 7-67 shows the architecture: a tree, with the origin server at the root and CDN nodes (edges) at the leaves; the origin pushes content to the edges; clients fetch from the nearest edge.

The CDN is the *inverse* of a proxy cache: instead of clients going to a *shared* cache, the *content provider* pushes the content to *distributed* caches and steers clients to the nearest one. The proxy-cache model is client-pulled; the CDN model is provider-pushed.

The textbook lists three virtues of the CDN tree:

1. **Scalability** — the origin serves only the edges, not the clients. The edges serve the clients. Each level in the tree can be expanded independently.
2. **Performance** — the client connects to a *nearby* edge, with short RTT, fast TCP slow-start, and a path that is less likely to cross congestion.
3. **Network efficiency** — with well-placed edges, the bytes for a popular page traverse each link only once (between the edge and the client). Without CDN, the same bytes would be sent *N* times from the origin.

### DNS redirection: the magic step

The textbook's key insight: a CDN uses **DNS redirection** to steer clients to edges. When a client asks its resolver for `www.cdn.com`, the resolver asks the CDN's authoritative nameserver, which inspects the *client's* IP (typically the resolver's IP) and returns the IP of the *nearest* edge.

Concretely, a client in Sydney asks for `www.cdn.com`, and the CDN nameserver returns `203.0.113.10` (the Sydney edge IP). A client in Amsterdam makes the same request and gets `198.51.100.25` (the Amsterdam edge IP). This is legal under DNS semantics — nameservers may return different answers for the same name, and the textbook notes that name servers "may return changing lists of IP addresses."

The textbook identifies two factors that determine which edge is "nearest":

1. **Network distance** — short, high-capacity path. CDN operators build IP-to-location maps by measuring latency from probes deployed in many networks. The nearest edge is not always the geographically closest one.
2. **Edge load** — if an edge is overloaded, mapping some clients to a *slightly* further edge that is less loaded gives better overall response time.

Modern CDNs (Akamai, Cloudflare, Fastly) combine the two with weighted round-robin at the per-edge level: the resolver returns *multiple* IPs with weights, and clients try them in order.

### The "Fluffy Video" pattern

The textbook's worked example shows the split-content pattern. The content owner rewrites its HTML so that the small HTML stays on its own server, but links to large assets go through the CDN:

```html
<!-- before -->
<a href="koalas.mpg">Koalas Today</a>

<!-- after CDN rewrite -->
<a href="http://www.cdn.com/fluffyvideo/koalas.mpg">Koalas Today</a>
```

The user types `www.fluffyvideo.com`, the HTML is fetched from Fluffy's origin (fast, small, no cache benefit), the browser parses the HTML and resolves `www.cdn.com` (CDN returns nearest edge), and the video is fetched from the edge. The user sees a single coherent site, but the bytes are split: 5 KB of HTML from the origin, 50 MB of video from the edge.

### Flash crowds and the case for using a CDN

The textbook cites the Florida Secretary of State's 2000 election-results site as a cautionary tale. A site that was a backwater on November 6 was a top-100 site on November 7, and crashed under the load. A CDN would have absorbed the surge because CDNs have *tens of thousands* of servers and a single site's flash crowd is a rounding error.

The textbook also notes that DNS replies at the *second* level of redirection are given with short TTLs (10–60 seconds) so that the client re-resolves frequently. This lets the CDN shift a client from one edge to another when an edge fails or becomes overloaded.

### Mirroring vs DNS redirection

Before DNS redirection, content providers used **mirroring** — they would host the same content on multiple Web servers in different regions and let users manually pick a mirror. Debian's `ftp.debian.org` mirrors are the classic example. Mirroring works but puts the burden on the user; DNS redirection puts the burden on the network.

## Build It

We will use the existing `code/main.py` which implements five self-contained functions:

1. **Load balancing simulation** — `simulate_load_balancer()` runs a workload of 120 requests across 3 servers with variable duration, comparing round-robin and least-connections. `print_load_balance_table()` shows the max/mean/std of active connections and requests.
2. **Proxy / edge cache** — `ProxyCache` is an LRU cache with `request()` and `hit_ratio()`. `generate_zipf_workload()` produces a Zipf-distributed workload of 1,000 requests against 50 content keys.
3. **Cache size sweep** — `cache_size_sweep()` runs the same workload against caches of capacity 5, 10, 20, 30, 40, 50 to show diminishing returns.
4. **CDN edge selection** — `haversine_km()` computes great-circle distance; `select_edge_server()` picks the closest edge from a list.
5. **Comparison table** — `print_load_balance_table()` and `print_cache_table()` render results.

Steps:

1. Read textbook sections 7.5.2 ("Server Farms and Web Proxies") and 7.5.3 ("Content Delivery Networks"). The Fluffy Video example is in 7.5.3.
2. Open `code/main.py` and look at `LoadBalancer.round_robin()` (a simple index increment) versus `LoadBalancer.least_connections()` (a `min()` over a list of backends).
3. Run `python3 code/main.py`. The output has 5 sections: load balancing, proxy cache, CDN edge selection, cache size sweep, and summary.
4. In `cache_size_sweep()`, change `sizes = [5, 10, 20, 30, 40, 50]` to `[1, 2, 3, 5, 10, 20, 30, 50]`. Watch the hit ratio climb from 0% to a plateau around 60–70%.
5. Add a new client (e.g., `ClientLocation("Client-BuenosAires", -34.6037, -58.3816)`) to the `clients` list in `main()`. Run and check which edge it gets routed to.

## Use It

| API call | What it does | Typical output |
|---|---|---|
| `Server(name, weight)` | Create a backend server record | — |
| `LoadBalancer(servers).round_robin()` | Pick the next server cyclically | Server object |
| `LoadBalancer(servers).least_connections()` | Pick the least-loaded server | Server object |
| `simulate_load_balancer(balancer, requests, "least_connections")` | Run a workload, return stats | dict with `max_active`, `mean_active`, `stdev_active`, etc. |
| `ProxyCache(capacity=10)` | Create an LRU cache of given capacity | — |
| `cache.request(key)` | Record a request, return True if hit | bool |
| `cache.hit_ratio()` | Get the current hit ratio | float in [0, 1] |
| `generate_zipf_workload(keys, total_requests, alpha=1.2)` | Generate a popularity-skewed workload | list of keys |
| `cache_size_sweep(keys, workload, sizes)` | Sweep cache capacities, return hit ratios | list of (capacity, hits, misses, ratio) |
| `haversine_km(lat1, lon1, lat2, lon2)` | Great-circle distance in km | float |
| `select_edge_server(client, edges)` | Find nearest CDN edge to client | (EdgeLocation, distance_km) |
| `EdgeLocation(name, lat, lon, load=0)` | Create a CDN edge | — |

The output of `cache_size_sweep()` for a 50-key Zipf workload shows hit ratios climbing from ~30% at capacity 5 to ~60% at capacity 50. The textbook's "Pareto 80/20" prediction would say the top 10 keys (20% of items) get 80% of requests, so a cache of size 10 should hit 80% — but the LRU cache's *steady-state* hit ratio is below the *theoretical* Zipf hit ratio because of churn.

## Ship It

The deliverable is the lesson folder:

```
phases/13-streaming-real-time-media-and-content-delivery/06-server-farms-and-web-proxies-to-content-delivery-networks/
├── assets/
│   └── server-farms-and-web-proxies-to-content-delivery-networks.svg
├── code/
│   └── main.py
├── docs/
│   └── en.md
├── notebook/
│   └── notes.md
├── outputs/
│   └── trace.json
└── quiz.json
```

To prove the lesson works:

1. `python3 code/main.py` — must print all 5 sections without errors.
2. `python3 -m py_compile code/main.py && echo OK` — must print `OK`.
3. Open `assets/server-farms-and-web-proxies-to-content-delivery-networks.svg` in a browser.

## Exercises

1. **Round-robin vs least-connections at scale.** Increase the number of requests in `simulate_load_balancer` from 120 to 12,000 and the request duration variance from 1–8 s to 0.1–80 s. Does round-robin still keep active connections balanced? Why? (Answer: no — when durations are skewed, round-robin assigns equal *counts* of requests but the *load* (in-flight work) is unequal. Least-connections adapts in real time.)
2. **Cache working-set size.** Run `cache_size_sweep` on the 50-key workload with capacities 1, 2, 3, ..., 50. At what capacity does the hit ratio cross 50%? (Answer: somewhere between 8 and 12.) What does that tell you about the *working-set size* of the workload?
3. **Haversine vs network distance.** Compute the haversine distance from Boston to NYC and from Boston to Chicago. Then look up the *network* round-trip time from a Boston server to a NYC edge vs a Chicago edge. Which is closer in haversine? Which is closer in network latency? (Haversine: NYC 306 km, Chicago 1,513 km. Network: NYC ~12 ms RTT, Chicago ~25 ms RTT. NYC wins both. But for a client in rural Vermont, the *geographically* nearest edge (Boston) might not be the *network* nearest — a Montreal edge could have lower latency.)
4. **Akamai's business model.** The textbook says CDN nodes are placed *inside ISP networks* so the ISP pays nothing but gets reduced upstream bandwidth and improved customer experience. What is the analogous arrangement for a modern CDN like Cloudflare? (Answer: Cloudflare offers a *free* tier in exchange for placing an edge in the ISP's data center. The ISP gets reduced DDoS risk and lower transit cost. Cloudflare gets the ability to serve content (and inspect it for the paying tier's WAF/CDN services).)
5. **Split-content pattern.** You own a recipe site. The HTML for a recipe page is 30 KB; each photo is 500 KB; each video is 5 MB. Your site gets 10 million recipe-page views per day, with 3 photos and 1 video per page on average. Compute the daily bandwidth for the HTML (origin) and the media (CDN). (HTML: 10e6 * 30 KB = 300 GB/day. Media: 10e6 * (3 * 500 KB + 5 MB) = 65 TB/day. The CDN handles 99.5% of the bytes.)
6. **DNS TTL and edge failover.** A CDN edge in Sydney fails. The CDN's authoritative nameserver needs to redirect clients to Melbourne (the next-nearest edge). How does it do this, and what is the latency? (Answer: it changes the DNS response for `www.cdn.com` to return the Melbourne edge IP. The latency is the DNS TTL of the *upstream* resolver's cached entry — typically 30–300 s, so up to 5 minutes for the shift to complete. Modern CDNs use *active* probing and short TTLs (10–60 s) to detect failures faster.)

## Key Terms

| Term | Meaning |
|---|---|
| Server farm | A cluster of computers that act as a single Web server |
| Front-end | The load-balancing device in front of a server farm (also: director, L4 switch) |
| Middlebox | A device that violates strict layering by inspecting payload headers (NAT, firewall, load balancer) |
| Round-robin | Cycle through backends in a fixed order |
| Least-connections | Pick the backend with the fewest active connections |
| Source-IP hash | Hash the client's IP to a backend; stable but NAT-hostile |
| Cookie-based affinity | Parse the HTTP Cookie header to route the same user to the same backend |
| Web proxy | An agent that fetches Web requests on behalf of its users; caches responses |
| Shared cache | A cache used by multiple users (e.g., a corporate proxy) |
| CDN | Content Delivery Network; a network of edges that serves content on behalf of owners |
| Origin server | The canonical source of content; the CDN pushes from here to edges |
| Edge server | A CDN node near the client; serves the cached copy |
| DNS redirection | The CDN's nameserver returns the IP of the nearest edge based on the client's IP |
| Flash crowd | A sudden surge of traffic to a previously low-traffic site |
| Mirroring | Hosting the same content on multiple servers; users manually pick a mirror |
| Split-content | The pattern of putting HTML on the origin and large assets on the CDN |
| Working set | The set of items accessed in a recent time window; the right size for a cache |
| LRU | Least Recently Used; the standard cache eviction policy |
| Pareto / 80-20 | The empirical finding that 20% of items account for 80% of accesses |
| Wolman et al. (1999) | The paper that measured the diminishing returns of shared caching |
| Dilley et al. (2002) | The Akamai engineering paper on CDN architecture |

## Further Reading

- **Dilley, J., Maggs, B., Parikh, J., Prokop, H., Sitaraman, R., & Weihl, B. (2002)** — "Globally Distributed Content Delivery" *IEEE Internet Computing*. The Akamai engineering paper that explains the two-level DNS redirection in detail.
- **Wolman, A., Voelker, G., Sharma, N., Cardwell, N., Brown, M., Landray, T., Pinnel, D., Karlin, A., & Levy, H. (1999)** — "Organization-Based Analysis of Web-Object Sharing and Caching" *USENIX Symposium on Internet Technologies and Systems*. The paper that measured the diminishing returns of shared proxy caching beyond ~100 users.
- **Krishnamurthy, B., Wills, C., & Zhang, Y. (2001)** — "On the Use and Performance of Content Distribution Networks" *IMC '01*. Empirical study of CDN effectiveness.
- **RFC 1034 / RFC 1035** — Domain Names: Concepts and Facilities / Implementation and Specification. The DNS standard.
- **Linux Virtual Server (LVS)** — `http://www.linuxvirtualserver.org/`. The open-source L4 load balancer referenced in the textbook.
- **Cloudflare Learning Center** — "What is a CDN?" A modern, practitioner-oriented take on the textbook's content.
- **Peterson, L. & Davie, B.** — *Computer Networks: A Systems Approach*, sections 7.5.2 and 7.5.3. The textbook this lesson series is built from.
