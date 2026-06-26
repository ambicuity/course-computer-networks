# Physical-to-Application Outage Trace

> A fiber cut between a web server and its core switch does not look like "a fiber cut" in the application logs: it looks like HTTP 503, then connection timeouts, then DNS cache errors, then an angry customer tweet. Each layer of the stack rewrites the same root cause into its own dialect, and a competent engineer traces the symptom chain from the top down while collecting evidence from the bottom up. This lesson walks the full bottom-up forensic chain — from `eth0` going down, through route withdrawal, TCP resets, and HTTP 5xx responses — and uses a synthetic packet-trace generator to replay the cascade deterministically. By the end you will be able to look at a single `tcpdump -nn -i any port 80` capture and pinpoint which layer first reported the failure, and you will be able to articulate why DNS, surprisingly, still works while HTTP is dead.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 04 IP addressing, Phase 06 Ethernet & switching, Phase 08 TCP fundamentals, Phase 10 DNS basics, Phase 12 HTTP semantics
**Time:** ~120 minutes

## Learning Objectives

- Trace a single root-cause outage from the physical layer upward through data link, network, transport, and application layers, naming the specific counter, frame flag, or protocol field that first reported the failure at each layer.
- Distinguish carrier loss (Layer 1) from interface flap (Layer 2) from route withdrawal (Layer 3) from TCP RST (Layer 4) from HTTP 5xx (Layer 7), and explain why a single physical event produces five different log signatures.
- Apply a bottom-up evidence-gathering methodology: start with `ip -s link`, then ARP, then `ip route`, then `ss -s`, then application logs, in that order, so that the first decisive evidence short-circuits the search.
- Diagnose the "DNS works but HTTP fails" anti-pattern: cached DNS responses outlive the path they resolved to, so a working DNS query proves nothing about reachability.
- Construct a synthetic packet-trace generator (no live capture required) that emits a deterministic, time-ordered record of layer-specific events triggered by a simulated physical fault.
- Produce a one-page failure-mode runbook in `outputs/` that another engineer could use to triage a similar outage without your tribal knowledge.

## The Problem

A regional e-commerce company runs a single backend pod in a carrier hotel. At 14:32 local time the operations team gets paged: customers in two adjacent metropolitan areas see "This site can't be reached" when they load the homepage. The status page shows a yellow banner. The first responder opens a terminal, runs `ping 10.20.0.5` (the backend's internal VIP) and sees `Request timeout for icmp_seq 1..7`. She runs `dig www.example.com` and gets a clean A record. She runs `curl -v http://www.example.com` and sees the TCP three-way handshake hang, then fail with `Connection timed out`. The first instinct is "DNS problem?" but DNS works. The second is "firewall rule?" but nothing in the firewall was changed. The third is "the application is broken" and she pages the development team, who confirm there was no deploy.

What actually happened: at 14:31:48 a backhoe working on a road widening project severed the metro fiber ring carrying traffic between the company's edge router and the carrier hotel. The first responder sees no DNS failure, no HTTP error, and no firewall deny — she sees silence. The trace moves from the application symptom ("page won't load") down through TCP timeout, route withdrawal (the routing daemon on the edge router, running BFD with a 900 ms multiplier against a 100 ms timer, has not yet declared the neighbor dead), a sudden `link down` on the SFP+, and finally a `carrier lost` event in the transceiver's DOM (Digital Optical Monitoring) thresholds.

The challenge: each layer's telemetry is correct in isolation, and the only way to find the root cause is to walk the stack and notice that all five layers reported a problem in the same 90-second window. The `code/main.py` in this lesson reproduces that cascade synthetically so that you can rehearse the evidence-gathering pattern without waiting for a real backhoe.

## The Concept

### Why One Fault, Five Symptoms

The OSI model is not just a teaching aid — it is a layered set of failure-reporting contracts. When a fiber is cut, each layer has independent instrumentation, and each layer translates the same physical event into its own native vocabulary:

| Layer | What happens at the fiber cut | What the operator sees |
|-------|------------------------------|------------------------|
| 1 — Physical | Light signal drops below receiver threshold (~ -24 dBm for 10GBASE-LR). Transceiver DOM threshold-crossing alarm fires. | `eth0: link down`, `kernel: tg3: phy reset failed`, `IF-MIB::ifInErrors` increments |
| 2 — Data Link | The MAC detects loss of carrier, drops the interface, flushes the bridge FDB for that port. | `ip link show` reports `state DOWN`, `bridge fdb show` no longer lists the MAC |
| 3 — Network | The routing daemon (BIRD, FRR, Quagga) receives an `ifdown` netlink notification, withdraws the route, runs SPF. | `ip route` no longer shows `10.20.0.0/24 via 10.0.0.1`, BGP UPDATE sent to peers |
| 4 — Transport | Existing TCP sessions see no ACKs; retransmission timer fires, RTO doubles each round. After ~9 minutes, RST is sent. New SYNs get no response. | `ss -s` shows `ESTAB` count dropping, `ESTAB` retransmits growing, no `SYN-SENT` progress |
| 5–7 — Application | Application calls `connect()` block until the kernel's `tcp_syn_retries` ceiling (default 6) is reached (127 s on Linux). Load balancer marks backend unhealthy after its own health check threshold. | HTTP 503, "could not connect to backend", `nginx` `connect() failed (110: Connection timed out)` |

The `code/main.py` in this lesson emits a deterministic, time-stamped log of all five layers for a simulated cable cut, then prints a bottom-up diagnostic summary. Run it and observe how the wall-clock time of the first signal at each layer differs — the data link signal arrives in microseconds, the routing signal in milliseconds, the transport signal in seconds, and the application signal in tens of seconds to minutes.

### Bottom-Up Evidence Gathering

A common mistake in outage triage is to start at the application layer. The application error message is a *symptom* of the symptom — it is what the user complained about, but it is rarely where the fault lives. The disciplined approach walks up from the physical interface:

1. **Layer 1 — `ip -s link show <iface>`**: Look for `state DOWN`, `carrier`, `errors`, `dropped`, and the `LINK STATE` flags. A `NO-CARRIER` flag is the gold-standard single-bit answer: the wire is electrically or optically silent.
2. **Layer 1 — DOM / DDM**: Modern SFP+/QSFP transceivers expose `ethtool -m <iface>` with receive power, transmit power, temperature, and supply voltage. A receive power below the sensitivity threshold (typically -14 to -24 dBm depending on rate and reach) confirms a fiber problem rather than a switch-port problem.
3. **Layer 2 — `ip neighbor`, `bridge fdb`**: If the interface is up but you still cannot reach the gateway, ARP may be failing. If the gateway's MAC is missing from `ip neighbor show`, the issue is below ARP (Layer 1) or the gateway is genuinely unreachable.
4. **Layer 3 — `ip route show`, `ip route get <dst>`**: A missing route is a Layer 3 fault. `ip route get` is more useful than `ip route show` because it shows which route the kernel would *actually use* for a given destination, including any policy rules.
5. **Layer 4 — `ss -ti dst <dst>`**: `ss -ti` (the `-i` is for internal TCP info) shows the kernel's view of every TCP socket, including `retrans`, `rtt`, `cwnd`, and timer state. If retrans is climbing on all sessions to a destination, the fault is below TCP (routing, fiber, congestion).
6. **Layer 5–7 — application logs, HTTP status codes**: Only after Layers 1–4 are confirmed healthy should you conclude that the application itself is the problem.

The order matters because each lower layer's evidence is more decisive: a `NO-CARRIER` flag ends the investigation in two seconds; a missing route narrows it to a routing-protocol problem; a high TCP retrans count could be congestion *or* loss *or* misbehavior, and is much less decisive.

### The "DNS Works But HTTP Fails" Anti-Pattern

A surprising number of misdiagnoses start with the wrong assumption that DNS is the problem. The confusion comes from how DNS caches work:

- When a client resolver gets an A record for `www.example.com`, it caches the answer for the record's TTL (often 300 to 3600 seconds).
- The resolver will continue to hand out the cached answer for the entire TTL even if the IP it points to becomes unreachable.
- The TCP connection to that IP, however, will fail immediately if the path is broken.
- The user sees a browser error that uses the words "site can't be reached" which is a DNS-looking error message even though DNS is not the problem.

The rule: a successful DNS resolution is necessary but not sufficient evidence of reachability. Always pair `dig` (or `getent ahosts`) with `curl -v` or `ping` (where ICMP is allowed) before concluding that a name is reachable. The synthetic trace in `code/main.py` deliberately preserves this pattern: at T=5.0 it emits a DNS A record from cache, followed immediately by a TCP timeout, to drill the lesson in.

### Layer 3: Route Withdrawal and BFD

When an interface goes down, the Linux kernel sends a `RTM_DELROUTE` netlink message to user-space routing daemons. The daemon (FRR, BIRD, Quagga, or the kernel's own multipath logic) recalculates which routes are now invalid and signals the FIB to remove them. In a healthy OSPF or IS-IS network, the convergence time is dominated by:

- **Interface debounce timer** (typically 0–1000 ms): prevents flapping from triggering route flaps
- **BFD (Bidirectional Forwarding Detection) interval** (typically 50–900 ms × multiplier 3): detects neighbor reachability loss in tens of milliseconds
- **SPF calculation** (typically 5–100 ms on modern routers): Dijkstra over the LSDB

If the operator has disabled BFD and relies on the OSPF hello/dead-interval defaults (10 s / 40 s), the routing layer can take up to 40 seconds to detect a single-homed outage. During that window, the routing table still claims the path is valid, packets get black-holed, and the TCP retransmission timer is the only thing protecting the application from silent data loss. This is why BFD is mandatory in modern data-center fabrics and is the single most important tuning knob in any "fast convergence" deployment.

### Layer 4: TCP Retransmission and Connection Reset

Once the path is broken, TCP enters a controlled descent. The retransmission timer starts at the **SRTT** (smoothed round-trip time) and grows exponentially on each failure — RFC 6298 specifies the formula:

```
RTO = SRTT + max(G, 4 * RTTVAR)
RTO doubles on each retransmission (capped at 64 s)
```

So if the SRTT was 50 ms, the RTO sequence is 50 ms, 100 ms, 200 ms, 400 ms, 800 ms, 1.6 s, 3.2 s, 6.4 s, 12.8 s, 25.6 s, 51.2 s, 64 s, 64 s, 64 s, ... and the connection is reset after `tcp_retries2` (default 15) retransmissions, which on a 50 ms RTT network is approximately 924 seconds (15.4 minutes). The Linux default is conservative; many operations teams lower it to 5–8 to fail fast in the face of clear network failure.

`ss -ti` shows this state in real time. The `timer:(<type>,<remaining_ms>)` field is the smoking gun:

```
ESTAB  0  10.0.0.5:443  93.184.216.34:51234  timer:(on,102ms)  retrans:5/7  rtt:50/40
```

`timer:(on,102ms)` means the retransmit timer is armed with 102 ms remaining; `retrans:5/7` means 5 retransmissions have been sent out of 7 total attempts.

### Layer 7: HTTP 503, Connection Timeout, and the User

The application's view of the outage is mediated by its connect timeout, retry policy, and circuit breaker. A typical synchronous request looks like:

1. `connect()` blocks for up to `tcp_syn_retries` × RTO ≈ 127 s on Linux
2. If `connect()` succeeds but the read times out (e.g., `curl --max-time 30`), the application gets an `EAI_AGAIN` or `ETIMEDOUT`
3. The application translates this to HTTP 503 to the upstream caller, or to a generic "try again" page
4. The load balancer's health check (typically every 2–10 s) eventually marks the backend unhealthy and stops sending it traffic
5. DNS-based load balancers like AWS Route 53 health checks trigger a TTL-bounded failover

The total time from "fiber cut" to "user sees a friendly error page" is dominated by the load balancer's health-check interval and the application's connect timeout, and is typically 30–120 s. This is why the customer's tweet arrives before the on-call engineer's pager fires — the user has given up faster than the monitoring has reacted.

## Build It

The `code/main.py` in this lesson is a deterministic, stdlib-only event simulator. It does not sniff live packets (that would require root and a `tcpdump` libpcap binding); instead it emits a time-ordered stream of layer-specific events for a simulated cable cut, then walks the stack bottom-up and prints a diagnosis. To use it:

1. **Read** `code/main.py` end to end. Notice the use of `dataclass(frozen=True)` for all event records, the `@dataclass` `CableCutSimulator` class that owns a deterministic event log, and the separation between *event emission* (`simulate`) and *diagnosis* (`diagnose`).
2. **Run** it from the lesson directory: `python3 code/main.py`. You will see a tabular trace of events at T=0, 0.1, 1.0, 2.0, 3.0, and 5.0 seconds, with each event labeled by layer and tagged with the counter or state change.
3. **Modify** the `CableCutSimulator` constructor to change the failure mode: pass `failure_mode="interface_flap"` for a flapping link, `failure_mode="route_withdraw"` for a routing-protocol-level fault with the link up, or `failure_mode="dns_cache"` for a DNS TTL mismatch. Each mode emits a different event sequence.
4. **Add** a new failure mode that simulates a firewall silently dropping packets (`failure_mode="silent_drop"`). At each layer, the symptoms are identical to a cable cut from the application's point of view, but Layer 1 and Layer 2 see no problem — the diagnostic chain must reach Layer 3 or 4 to detect it.

The simulator deliberately keeps the same bottom-up diagnostic output regardless of failure mode. This is the lesson: the *method* is constant, only the *evidence* changes.

## Use It

| Symptom | Diagnostic Command | Expected Output |
|---------|-------------------|-----------------|
| Page won't load | `ip -s link show eth0` | `state DOWN` or `NO-CARRIER` |
| Page won't load, link up | `ip route get 8.8.8.8` | `RTNETLINK answers: Network is unreachable` or unexpected next hop |
| Page won't load, route present | `ss -ti dst 8.8.8.8` | `timer:(on,...)` with growing `retrans:N/N` field |
| Page won't load, TCP fine | `curl -v --max-time 5 http://...` | HTTP 5xx, response body indicates app error |
| DNS suspected | `dig +short example.com` | Returns IP, but pairing with `curl` shows timeout |
| Carrier loss confirmed | `ethtool -m eth0` (if supported) | DOM `rx_power` below `-24 dBm` for 10GBASE-LR |
| SFP health | `ethtool eth0 \| grep -E 'Speed\|Link detected'` | `Link detected: no` |
| Routing convergence | `watch -n0.1 'ip route show 10.0.0.0/8'` | Route present, then absent within seconds of fault |
| TCP retransmissions | `ss -ti dst 10.20.0.5` | `retrans:N/N` with N growing each second |
| Load balancer health | `curl -sI http://internal-vip/health` | 200 → 503 transition within health-check interval |

## Ship It

The `outputs/prompt-physical-to-application-outage-trace.md` file is your deliverable. Author a one-page runbook that another engineer could use to triage a similar outage. The runbook should contain:

1. A 5-line decision tree: "First, run `ip -s link`. If state DOWN, dispatch field tech and check DOM. If state UP, run `ip route get <dst>`. If no route, check routing daemon logs. If route present, run `ss -ti dst <dst>`. If retrans climbing, look at the path. If retrans fine, escalate to application team."
2. A table of the five layers, the one command to run for each, and the one output line that means "the fault is here."
3. A list of three common false-positive pitfalls: (a) DNS is cached so it is not a DNS failure, (b) ICMP is rate-limited or blocked so `ping` failing does not prove TCP is broken, (c) HTTP 502/503 may be a load-balancer response, not a backend response.

## Exercises

1. **Layer 1 only**: A fiber cut produces a `link down` event in 1.2 ms, but a `route withdraw` event takes 240 ms. Why the difference? What does this tell you about the ordering of evidence in a `tcpdump -i eth0 -nn -c 1000` capture taken at the moment of the cut?
2. **BFD tuning**: A network has OSPF hello=10, dead=40, and no BFD. A second network has OSPF hello=10, dead=40, and BFD interval=50, multiplier=3. The first network's edge router takes ~40 s to withdraw a single-homed route; the second takes ~150 ms. Calculate the upper bound on TCP data loss in both cases for a 50 ms RTT link carrying 10,000 in-flight bytes. (Hint: how many RTTs fit in 40 s? In 150 ms?)
3. **DNS anti-pattern**: At T=0, a name resolves to 10.20.0.5 with TTL 600. At T=200, the path to 10.20.0.5 is severed. At T=300, the user re-runs `dig example.com` and gets 10.20.0.5. At T=310, the user `curl`s the URL and gets a TCP timeout. Explain why the DNS response is still valid (it has not reached TTL), and what command the user should run to get an uncached answer (`dig +nocache example.com @8.8.8.8` or `dig example.com @1.1.1.1`).
4. **Diagnosis chain**: For each layer, name one counter or flag whose value proves the fault is at that layer (not above or below). Example: `ifInErrors` is *not* a Layer 1 counter — it is a Layer 2 MAC counter. A true Layer 1 indicator is DOM `rx_power` or `carrier` flag.
5. **Compare with adjacent layer**: A different lesson in this phase (Lesson 02 — "DNS Works but HTTP Fails") is a *subset* of this lesson. Identify the two layers that are problematic in Lesson 02 and explain how the diagnostic chain differs.
6. **Synthetic fault injection**: Modify `code/main.py` to add a `failure_mode="arp_storm"` mode where the data link layer floods ARP requests but never receives replies. Walk through how the bottom-up evidence chain changes.

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| Carrier loss | An old telephone term | The receiver detects no light/Electrical signal on the medium; transceiver reports NO-CARRIER |
| Route withdrawal | The router gives up | A routing daemon signals the FIB to remove a prefix from the active table |
| RTO | Retransmit time-out | The current retransmit timeout, computed from SRTT and RTTVAR per RFC 6298 |
| TTL | Time to live | In DNS, the cache lifetime of a record. In IP, a hop counter that decrements at each router |
| BFD | Binary File Descriptor? | Bidirectional Forwarding Detection — a fast (sub-second) liveness protocol on top of any routing protocol |
| SFP | Small Form-factor Pluggable | Hot-swappable optical/copper transceiver module with DOM telemetry |
| DOM/DDM | Document Object Model? | Digital Optical/Diagnostic Monitoring — telemetry from the SFP's internal sensors |
| NO-CARRIER | A radio term | A kernel `IFF_NO_CARRIER` flag indicating the physical layer has no signal |
| RST | Reset | A TCP control flag that forcibly terminates a connection, used in response to unexpected segments or to refuse new ones |
| 503 | A page number | HTTP "Service Unavailable" — the origin or load balancer is refusing or unable to serve |

## Further Reading

- **RFC 6298** — *Computing TCP's Retransmission Timer*. The authoritative formula for SRTT, RTTVAR, and the exponential RTO backoff.
- **RFC 5880–5884** — *Bidirectional Forwarding Detection (BFD)*. The sub-second liveness protocol used in every modern data center.
- **IEEE 802.3 Section 4** — *Transceiver and Medium Dependents*. The DOM threshold definitions for `rx_power`, `tx_power`, temperature, and voltage.
- **Linux kernel `tcp_input.c`** — Source for `tcp_retries2` and the reset behavior. Comment block at the top of the file explains the RTO cascade.
- **Wireshark display filters reference** — `tcp.analysis.retransmission`, `tcp.flags.reset`, `icmp.type==3` (destination unreachable). Filters for isolating the layer of interest.
- **SRE Workbook, Chapter 6** — *Eliminating Toil* and the *playbook* concept. The runbook you ship in `outputs/` is exactly this.
- **phases/00-networking-lab-and-foundations** — the troubleshooting methodology this lab integrates.
- **phases/06-ethernet-wireless-lans-and-switching** — physical- and data-link-layer fundamentals.
- **phases/08-tcp-and-udp** — TCP retransmission, timers, and the state machine.
- **phases/10-application-protocols** — DNS caching and HTTP semantics relevant to the user-visible symptom.
