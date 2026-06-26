# Server Farm Load Balancing

> Read the protocol, build the evidence, then ship an artifact you can reuse in real troubleshooting.

**Type:** Learn
**Languages:** Python, diagrams
**Prerequisites:** Earlier lessons in Phase 13
**Time:** ~75 minutes

## Learning Objectives

- Explain section 7.5.2 (Server Farms) in operational terms
- Identify the front-end behaviors, header inspections, and mapping policies that prove load balancing
- Connect the mechanism to at least one realistic failure mode (hot spot, broken affinity, dead server not removed)
- Produce a reusable simulator that demonstrates round-robin, IP-hash, least-connections, and cookie-affinity policies

## The Problem

No single machine can serve a popular Web site on its own. Eventually the request rate exceeds what one CPU, one NIC, and one TCP stack can absorb. The naive fix is to run several identical servers side by side, but that creates a new problem: the cluster must look like a single logical site to every client, or you have merely built several competing sites.

Server Farm Load Balancing matters because the front end that distributes requests is invisible to clients yet determines which server sees which request. When it works, the load is spread and sessions stay coherent. When it breaks, one server drowns while its siblings sit idle, or a user is bounced between servers that have no shared state and the application appears to forget who they are.

## The Concept

Source material: [`chapters/chapter-07-the-application-layer.md`](../../../../chapters/chapter-07-the-application-layer.md) section `7.5.2` (Server Farms).

A server farm is a cluster of machines that together present a single Web site. A front end, usually a link-layer switch or an IP router, accepts all incoming traffic addressed to one virtual IP and sprays requests across the pool. The front end is a middlebox: it inspects network, transport, or application headers and uses them in nonstandard ways to choose a backend server. All packets of one request must land on the same server, or TCP state is lost.

There are two broad families of distribution:

1. **DNS rotation.** The DNS server returns a rotating list of server IP addresses. Each client picks the first address, so different clients hit different servers. This method is simple and stateless, but it is coarse (one binding per resolver cache TTL) and it is the seed of the CDN technique studied in the next lesson.

2. **Front-end spraying.** The client contacts a single virtual IP. The front end maps each new connection to a backend server using a load balancing policy:
   - **Round-robin** -- servers are used one after the other in turn. Simple, but ignores real load.
   - **IP-hash** -- the last bits of the source IP address select a server (e.g., 16 servers look at 4 bits). Stateless and stable per source, but one proxy NATing a whole company funnels all its users onto one server.
   - **Least-connections** -- the front end tracks open connections per server and picks the server with the fewest. Adapts to slow servers but requires state.
   - **Cookie/session affinity** -- the front end inspects HTTP cookies (or other application hints) and pins a user to a server so cached session state on that server is reused. Fragile if a layer changes, but very useful when the backend caches per-user data.
   - **Health-aware** -- the front end runs health checks and stops sending requests to failed servers, which is what makes a farm more reliable than a single machine.

The front end must remember the mapping for each in-flight request so subsequent packets of the same TCP connection reach the same server. It must also detect server failure and drain traffic away from dead nodes. Peeking at TCP and HTTP headers violates layering in the strict sense, which is why the source calls this design useful but fragile: a change in a higher layer can break the middlebox.

### Working Model

```text
client request (one virtual IP)
        |
        v
front end: inspect IP / TCP / HTTP headers
        |
        v
load balancing policy: round-robin | IP-hash | least-conn | cookie-affinity
        |
        v
chosen server in the farm (with health check + mapping state)
        |
        v
observable evidence: per-server connection counts, request distribution, failed-server drain
```

## Build It

This lesson ships a simulator (`code/main.py`) that models a server farm with a configurable front end. It implements four policies, tracks per-server connection counts, simulates health checks and server failure, and prints the resulting distribution so you can see hot spots and affinity with your own eyes.

Run it:

```bash
python3 code/main.py
```

The simulator lets you:

1. Compare round-robin, IP-hash, least-connections, and cookie-affinity on the same request stream.
2. Inject a failed server and watch the health-aware variant drain traffic.
3. Observe how a single NATed corporate proxy collapses IP-hash to one server.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the layer | Front-end config, per-server connection counters, health-check logs | You can explain why a request imbalance is a front-end policy issue, not a client issue |
| Explain normal behavior | Policy plus a balanced distribution table | Counts roughly match the policy intent (round-robin is even; affinity pins a user) |
| Diagnose abnormal behavior | Before/after distribution, failed-server state | The hypothesis (dead server still in pool, or NAT collapsing IP-hash) predicts the skew |

## Ship It

Create one artifact under `outputs/`:

- A one-page runbook for diagnosing a server-farm hot spot
- A policy comparison table (when to use round-robin vs. least-connections vs. cookie-affinity)
- The simulator from `code/main.py` extended with one extra policy (weighted round-robin)
- A study prompt that teaches load balancing from the simulator output

Start with [`outputs/prompt-server-farm-load-balancing.md`](../outputs/prompt-server-farm-load-balancing.md).

## Exercises

1. Run the simulator with all four policies. Which policy produces the most even distribution? Which is most stable for a returning user?
2. Inject a failed server in the health-aware run. Describe the evidence you would collect first in production to confirm a server is actually down versus merely slow.
3. Configure IP-hash with 16 servers, then send all requests from one source IP (simulating a corporate NAT). Explain the resulting skew.
4. Compare this front-end mechanism with the DNS-rotation method. When does DNS rotation win, and when does it lose?
5. The source calls the front end a middlebox. Name one higher-layer change (e.g., HTTP/3 over QUIC) that would break a front end that inspects TCP headers, and explain why.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Server farm | A rack of servers | A cluster that must appear as one logical site to clients via a front end |
| Front end | A load balancer box | A middlebox that inspects headers and maps connections to backend servers |
| Load balancing policy | "The algorithm" | The rule (round-robin, IP-hash, least-connections, cookie-affinity) that chooses a server |
| Cookie affinity | Sticky sessions | Pinning a user to a server by inspecting HTTP cookies so cached session state is reused |
| Health check | A ping | An active probe that lets the front end drain traffic from failed servers |

## Further Reading

- The full source chapter linked above, section 7.5.2
- RFC 7230 (HTTP/1.1 message syntax) for the headers a front end may inspect
- HAProxy and nginx documentation for real-world policy implementations
