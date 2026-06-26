# CDN DNS Redirection and Edge Mapping

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Learn
**Languages:** Python, DNS, diagrams
**Prerequisites:** Lesson 21 (Server Farm Load Balancing), earlier lessons in Phase 13
**Time:** ~75 minutes

## Learning Objectives

- Explain section 7.5.3 (Content Delivery Networks) in operational terms
- Identify the DNS redirection flow, edge map, and load signals that prove a client was sent to a nearby node
- Connect the mechanism to at least one realistic failure mode (stale edge map, overloaded node, DNS cache pinning a far node)
- Produce a reusable simulator that maps client IPs to CDN edge nodes using network distance and load

## The Problem

A server farm in one data center can absorb many requests, but it cannot fix distance. A client in Sydney fetching a page from an origin server in Europe pays a long round-trip time, a slow TCP slow-start, and a higher chance of crossing congested transit. Caching proxies help, but they are configured by clients and cannot be controlled by the content provider, and they are not shared across organizations.

Content Delivery Networks solve this by placing copies of content at many locations (edge nodes) and directing each client to a nearby node. The hard part is not copying the content; it is deciding, for a given client, which node counts as "near." Geography is a poor proxy for network distance. The decision must also respect node load, or the nearest node becomes the slowest one.

## The Concept

Source material: [`chapters/chapter-07-the-application-layer.md`](../../../../chapters/chapter-07-the-application-layer.md) section `7.5.3` (Content Delivery Networks).

A CDN replicates content from an origin server to a set of edge nodes distributed across network regions. Clients fetch pages from the nearest edge node rather than the origin, so the round-trip time is short, TCP slow-start ramps up faster, and each network segment carries the page at most once. Three client-direction strategies are discussed:

1. **Proxy caches.** If every client were configured to use the nearest CDN node as a Web proxy, the tree would be followed automatically. This fails in practice: clients in one region belong to different organizations and use different proxies, multiple CDNs cannot all be a client's single proxy, and clients configure (or misconfigure) their own proxies.

2. **Mirroring.** The origin server replicates content to edge nodes and embeds explicit links in the pages, letting the user manually pick a nearby mirror. Static and stable, but it offloads the decision to the user and treats mirrors as separate sites.

3. **DNS redirection.** This is the mechanism that overcomes the previous two. The CDN runs the authoritative name server for its domain (e.g., `www.cdn.com`). When a client resolver asks for that name, the CDN name server inspects the IP address of the requesting resolver (the client's LDNS) and returns the IP address of the edge node nearest to that resolver. A Sydney resolver gets the Sydney node; an Amsterdam resolver gets the Amsterdam node. This is legal DNS: name servers may return different answers to different queries.

"Nearest" is defined by an edge map the CDN has previously computed, translating client IP prefixes to network locations. Two factors matter: network distance (short, high-capacity path) and current node load. If the nearest node is overloaded, the CDN may send the client to a slightly farther but lightly loaded node. The edge map is the CDN's private translation table from IP space to geography/topology.

### Working Model

```text
client browser
    |
    v  (1) resolve www.cdn.com
local DNS resolver
    |
    v  (2) query CDN authoritative name server
CDN name server: inspect resolver IP
    |
    v  (3) consult edge map: resolver IP -> network location -> nearest healthy node
    |
    v  (4) return edge node IP
client fetches page directly from that edge node
```

## Build It

This lesson ships a simulator (`code/main.py`) that models DNS redirection. It builds an edge map from client IP prefixes to network regions, assigns edge nodes with locations and load counters, and resolves each client to the nearest healthy (non-overloaded) node. It demonstrates the three failure modes: a stale edge map, an overloaded nearest node triggering a spill to a farther node, and DNS caching that pins a client to a node that has since moved or filled.

Run it:

```bash
python3 code/main.py
```

The simulator lets you:

1. Resolve a stream of clients from different regions and inspect which edge node each is sent to.
2. Overload the nearest node for one region and watch the load-aware policy spill to the next nearest.
3. Simulate a stale edge map (a prefix mapped to the wrong region) and observe a client sent to a far node.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | DNS authoritative answers, edge-map config, node load counters | You can explain why a slow fetch is a redirection issue, not a server-CPU issue |
| Explain normal behavior | Edge map plus a per-region resolution log | Clients from a region resolve to that region's node; origin is never contacted for cached pages |
| Diagnose abnormal behavior | Before/after DNS answers, node load, edge-map freshness | The hypothesis (stale map, overloaded nearest, DNS cache TTL) predicts the wrong-node assignment |

## Ship It

Create one artifact under `outputs/`:

- A one-page runbook for diagnosing "client sent to far CDN node"
- An edge-map freshness checklist (when to re-measure network distance)
- The simulator from `code/main.py` extended with a DNS-cache TTL model
- A study prompt that teaches DNS redirection from the simulator output

Start with [`outputs/prompt-cdn-dns-redirection-edge-mapping.md`](../outputs/prompt-cdn-dns-redirection-edge-mapping.md).

## Exercises

1. Run the simulator with all clients healthy. Verify that each region resolves to its local edge node and the origin is never the fetch target for cached content.
2. Overload the nearest node for one region. Describe the evidence (node load counter, DNS answer change) that proves a spill to a farther node occurred.
3. Introduce a stale edge-map entry (one prefix mapped to the wrong region). Which clients are affected, and how would you detect this from DNS logs alone?
4. Compare DNS redirection with mirroring. Under what workload does each win?
5. DNS caching means a client keeps using the answer until the TTL expires. Describe one scenario where a stale cached answer sends a client to a node that has since failed.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CDN | A faster server | A set of edge nodes that replicate origin content and redirect clients to the nearest one |
| DNS redirection | "DNS trick" | A CDN-run authoritative name server returns different IPs to different resolvers based on their source IP |
| Edge map | A list of servers | The CDN's private table translating client IP prefixes to network locations |
| Mirror | A copy of the site | A static edge node the user selects manually via embedded links |
| Spill | Fallback | Sending a client to a farther, lightly loaded node when the nearest node is overloaded |

## Further Reading

- The full source chapter linked above, section 7.5.3
- RFC 7686 (CDNI) and Akamai technical papers on DNS-based redirection
- `dig` against a CDN-backed hostname from two different network vantage points to observe different A records
