# DNS Works but HTTP Fails

> A user types `https://api.example.com` into a browser and gets a connection error. The first instinct of a junior engineer is "DNS is broken," so they run `dig` and see a clean A record, conclude the network is fine, and bounce the ticket to the application team. The application team runs `curl`, sees a TCP timeout, and bounces it back. This lesson is the *decision tree* that lives between those two bounces: a sequence of seven commands, each of which eliminates an entire layer of the stack, that ends with a single decisive piece of evidence pointing at the actual fault. The synthetic trace in `code/main.py` models the three most common DNS-works-but-HTTP-fails failure modes — firewall silently dropping SYN, backend service down, and broken NAT translation — and shows how the diagnostic chain diverges at each step.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 09 UDP and DNS basics, Phase 08 TCP fundamentals, Phase 12 HTTP semantics, Lesson 01 of this phase
**Time:** ~90 minutes

## Learning Objectives

- Apply a seven-command diagnostic chain (`dig`, `getent ahosts`, `ping`, `traceroute`, `curl -v`, `ss -ti`, `nc -vz`) to a "DNS works but HTTP fails" report and identify which command produces the first decisive evidence.
- Distinguish three failure classes that all look like "DNS works but HTTP fails" from the user's perspective: (a) TCP RST from a closed port (backend service down), (b) TCP timeout from a dropped SYN (firewall, NAT, or routing), (c) TCP handshake succeeds but HTTP request hangs (slow or broken backend).
- Explain why `ping` succeeding and `curl` failing is a possible and common combination, and what each tool's success or failure proves about the network path.
- Read a `curl -v` trace line by line and pinpoint at which point the failure occurs (DNS resolve, TCP connect, TLS handshake, HTTP request send, HTTP response read).
- Diagnose the "DNS cache outlives path" anti-pattern: a cached A record is correct *for the duration of its TTL* regardless of the path's health, and proves nothing about reachability.
- Construct a synthetic DNS+TCP+HTTP trace generator (no live capture) that reproduces the three common failure modes and demonstrates the divergent diagnostic chain.

## The Problem

A monitoring alert fires: "api.example.com health check failing for 5 minutes." The on-call engineer opens a terminal and runs the obvious commands:

```text
$ dig api.example.com
;; ANSWER SECTION:
api.example.com.   300   IN   A   203.0.113.42

$ curl -v https://api.example.com/health
* Trying 203.0.113.42:443...
* connect to 203.0.113.42 port 443 failed: Connection timed out
* Failed to connect to api.example.com
```

The first instinct cycle of "dig works → network is fine → must be the app" vs. "curl fails → network is broken → must be DNS or routing" produces a flip-flop that wastes hours. The actual fault could be any of:

- **Backend service crashed**: The DNS is correct, the path is correct, but port 443 has nothing listening. The kernel sends back a TCP RST. `curl` reports "Connection refused."
- **Firewall drop rule**: A new iptables rule on the edge dropped outbound traffic to 203.0.113.42:443. SYN packets are silently discarded. `curl` reports "Connection timed out."
- **NAT translation failure**: The corporate NAT box cannot allocate a translation slot for the new flow (Lesson 09 of this phase covers this). SYN packets leave the host but get dropped at the NAT. `curl` reports "Connection timed out."
- **Routing black hole**: A recently deployed route map misdirects traffic. SYN packets enter the network and are silently dropped at the misrouted hop. `curl` reports "Connection timed out."
- **TLS handshake hangs**: TCP succeeds, the TLS ClientHello goes out, but the server's certificate is broken or the SNI is misconfigured. `curl -v` will show the handshake hang.
- **HTTP request hangs**: TCP and TLS succeed, the request is sent, but the backend never responds (slow query, deadlock, GC pause). `curl` reports "Operation timed out" after `--max-time`.
- **Stale DNS cache**: A migration moved the service to a new IP, but the TTL on the old record is still 4 hours and a downstream resolver is still returning the old IP. `dig @8.8.8.8` returns the new IP, `dig` (unqualified) returns the old one.

All seven produce a "DNS works but HTTP fails" symptom. The lesson is the discipline of *which command disambiguates which case*.

## The Concept

### The Seven-Command Diagnostic Chain

The order is not arbitrary: each command is more expensive (slower, more side effects) and more specific than the previous one. The first decisive evidence short-circuits the rest.

| # | Command | What it proves | What it does not prove |
|---|---------|----------------|------------------------|
| 1 | `dig <name>` | Name → IP resolution works at the configured resolver | Anything about the IP being reachable |
| 2 | `getent ahosts <name>` | What the *local* resolver returns (no upstream cache bypass) | Anything about reachability |
| 3 | `ping -c 3 -W 2 <ip>` | ICMP path is open | TCP is allowed (ICMP is often rate-limited) |
| 4 | `traceroute -T -p 443 <ip>` | L3 path to the IP and which hop drops the traffic | Whether the destination port is open |
| 5 | `nc -vz <ip> 443` | TCP handshake completes (or "refused" / "timed out") | Anything about the application above TCP |
| 6 | `curl -v --max-time 10 <url>` | Full stack: DNS + TCP + TLS + HTTP request/response | Which of those sub-steps failed |
| 7 | `ss -ti dst <ip>` | Kernel's view of the TCP socket: retrans, RTO, state | The cause of any retransmission |

The "first decisive evidence" rule: as soon as one of these produces a definitive positive or negative result, stop and act on it. `nc -vz` returning "Connection refused" is decisive — the port is closed, no need to look at the firewall. `ping` failing with "100% packet loss" while `nc -vz` succeeds is also decisive — the firewall is dropping ICMP but passing TCP, and the issue is elsewhere.

### Failure Class 1: TCP RST (Service Down)

When SYN arrives at a host with nothing listening on the destination port, the kernel sends RST/ACK and the connection fails immediately. The user sees "Connection refused":

```text
$ nc -vz 203.0.113.42 443
Connection to 203.0.113.42 443 port [tcp/https] succeeded!
$ nc -vz 203.0.113.42 8443
Connection to 203.0.113.42 8443 port [tcp/*] failed: Connection refused
```

The decisive evidence: `nc -vz` returns in milliseconds (no timeout). This rules out firewall drops, NAT issues, and routing — the packet reached the host. The cause is purely service-level: the process is not running, is bound to a different port, or is crashed.

`curl -v` shows the RST explicitly:

```text
* Trying 203.0.113.42:8443...
* connect to 203.0.113.42 port 8443 failed: Connection refused
* Failed to connect to api.example.com port 8443
```

The fix: SSH to the host, run `ss -tlnp | grep 8443`, restart the service. This is the easiest of the three failure classes.

### Failure Class 2: TCP Timeout (Silent Drop)

When SYN is dropped silently (firewall, NAT, or routing), the kernel retransmits SYN with exponential backoff per RFC 6298: 1 s, 2 s, 4 s, 8 s, 16 s, 32 s (capped at `tcp_syn_retries`, default 6 = 127 s total). `nc -vz` will hang for 90+ seconds before failing:

```text
$ nc -vz -w 5 203.0.113.42 443
nc: connect to 203.0.113.42 port 443 (tcp) failed: Operation timed out
```

`curl -v` shows the same:

```text
* Trying 203.0.113.42:443...
* connect to 203.0.113.42 port 443 failed: Connection timed out
```

To distinguish firewall vs. NAT vs. routing, the next command is `traceroute -T -p 443` (TCP traceroute using SYN to port 443). Each hop that does not respond shows as `* * *`; the first non-responsive hop *after* the last responsive hop is the culprit. If the trace completes to the destination (you see the destination's response) but the SYN still times out, the issue is at the destination host (its own firewall or a service that is not bound).

The traceroute technique is not perfect — many networks rate-limit ICMP TTL exceeded responses, and the TCP SYN itself may be dropped, leading to ambiguous `* * *` sequences — but it is the best single command for narrowing the fault to a specific router or firewall.

### Failure Class 3: TCP Handshake Succeeds, HTTP Hangs

The TCP handshake completes, the TLS handshake completes (or HTTP is plaintext), the request is sent, but no response arrives. `curl -v` shows:

```text
* Connected to api.example.com (203.0.113.42) port 443
* TLSv1.3 (OUT), TLS handshake, ClientHello (1)
* TLSv1.3 (IN), TLS handshake, ServerHello (2)
* ... TLS handshake complete ...
> GET /health HTTP/1.1
> Host: api.example.com
> User-Agent: curl/7.81.0
> 
* Operation timed out after 30001 milliseconds with 0 bytes received
```

The decisive evidence: `curl -v` shows the TLS handshake complete and the request line sent, but no response. The TCP socket is in `ESTABLISHED` state with retransmissions climbing. The kernel thinks the connection is healthy, but the application is not responding.

`ss -ti dst 203.0.113.42` will show:

```text
ESTAB  0  10.0.0.5:51234  203.0.113.42:443  timer:(on,1234ms)  retrans:3/3  rtt:50/40
```

Three retransmissions in a row with the timer rearmed means the server is not ACKing. This rules out the network path (TCP would not have completed the handshake) and points squarely at the application: the server is overloaded, the request handler is deadlocked, the GC is paused, the database is locked, or the request was silently dropped by a WAF after inspection.

### The DNS Cache Outlives the Path

This is the most insidious case. A user has `api.example.com` cached with TTL 3600. The IP in the cache was valid 30 minutes ago, when the path worked. Now the path is broken, but the cache is still valid for 30 more minutes. The user runs `dig api.example.com` and gets the cached IP. `curl` times out. The user concludes "DNS gave me a bad IP" and contacts the DNS team, who run `dig` and see the same answer and conclude "DNS is fine." Both are partially right: the cache is fine, and the IP is the correct one, but the path to the IP is broken.

The fix is to bypass the cache and verify the path directly:

```text
$ dig +nocache api.example.com @8.8.8.8      # bypass local cache
$ dig +short api.example.com @1.1.1.1         # use a different resolver
$ curl -v --resolve api.example.com:443:203.0.113.42 https://api.example.com
```

The last command is the most powerful: it bypasses DNS entirely and tells `curl` to use a specific IP for a specific name+port. If `curl --resolve` works but `curl` without `--resolve` fails, the fault is in DNS resolution or caching. If both fail with the same timeout, the fault is in the path.

### Layer 4 Evidence: `ss -ti` Field Reference

When a connection is misbehaving, `ss -ti` is the most informative single command on Linux. The key fields:

| Field | Meaning |
|-------|---------|
| `ESTAB` / `SYN-SENT` / `TIME-WAIT` | TCP state |
| `timer:(on,102ms)` | Retransmit timer armed, 102 ms remaining |
| `retrans:5/7` | 5 retransmissions sent, 7 total attempts including originals |
| `rtt:50/40` | Smoothed RTT 50 ms, RTT variance 40 ms |
| `cwnd:10` | Congestion window 10 segments |
| `ssthresh:20` | Slow-start threshold 20 segments |
| `bytes_acked:1024` | Total bytes acknowledged by peer |
| `rcv_space:43690` | Receive buffer auto-tuned size |

A connection in `ESTAB` with `timer:(on,...)` and `retrans:N/N` climbing is a smoking gun: the kernel knows the peer is not responding. The fact that the connection is still in `ESTAB` (not `FIN-WAIT-1` or `CLOSED`) means the kernel has not yet given up — `tcp_retries2` has not been reached.

`tcp_retries2` defaults to 15 on Linux, which means the connection will not be reset for ~15–20 minutes of continuous failure. Many operations teams lower this to 5–8 in production so that application-level circuit breakers can fire faster.

### Layer 7 Evidence: HTTP Status Codes That Indicate Lower-Layer Faults

A 5xx status is not always the application's fault. Common mappings:

| Status | Often means | Layer of the actual fault |
|--------|-------------|--------------------------|
| 502 Bad Gateway | The load balancer or proxy could not reach the backend | L4 — TCP from proxy to backend failed |
| 503 Service Unavailable | The load balancer has marked the backend unhealthy | L4 — health check failed |
| 504 Gateway Timeout | The proxy sent a request to the backend but got no response in time | L4 — TCP succeeded, L7 — backend slow |
| 502 with `connect() failed (110: Connection timed out)` in nginx error log | The proxy could not even establish a TCP connection to the backend | L4 — SYN timed out |
| 502 with `Connection refused` | The backend is up but not listening on the port the proxy expects | L7 — wrong port config |
| 500 | The backend received the request and returned an error | L7 — application bug |
| 401 / 403 | Authn/authz | L7 — credentials, ACL |

The "first response byte" timing in `curl -w '%{time_starttransfer}'` is the most useful single number: it tells you how long the server took from accepting the connection to sending the first byte of the response. A first-byte time of 8 seconds for a `/health` endpoint that should respond in 50 ms is a backend problem, not a network problem.

## Build It

The `code/main.py` in this lesson models the three failure classes and walks through the seven-command diagnostic chain for each. It is stdlib-only and deterministic. To use it:

1. **Read** `code/main.py`. Notice the `FailureMode` enum, the `simulate_dns_lookup` function (which models local cache behavior), and the `DiagnosticChain` class that walks the seven commands and records the first decisive evidence.
2. **Run** `python3 code/main.py --mode refused` (or `--mode timeout`, `--mode slow_backend`, `--mode stale_cache`). You will see a step-by-step walk of each command, the output it produces, and the layer it implicates.
3. **Modify** the seven-command chain: add an eighth command `mtr -T -P 443 <ip>` (which combines ping and traceroute) and re-run. The chain should still terminate at the same command, but the evidence should be more decisive.
4. **Add** a new failure mode `connection_pool_exhausted` where the local application has run out of ephemeral ports (Lesson 26 of this phase). `curl` fails with "Address already in use" or "Cannot assign requested address." Walk through the diagnostic chain and identify which command first catches it.

The simulator deliberately keeps the diagnostic chain identical across all failure modes. The lesson is that the *method* is constant; only the *evidence* and the *culprit* change.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| `dig` works, `curl` times out | `nc -vz -w 5 <ip> 443` | `Connection timed out` | Firewall or NAT drop |
| `dig` works, `curl` fails "refused" | `nc -vz -w 5 <ip> 443` | `Connection refused` | Service down |
| `dig` works, `curl` hangs after TLS | `ss -ti dst <ip>` | `timer:(on,...)` and `retrans:N/N` climbing | Slow/dead backend |
| `dig` returns one IP, real IP differs | `dig @8.8.8.8 +short <name>` | Different A record | Stale cache or split-horizon DNS |
| `dig` works, `ping` fails | `nc -vz -w 5 <ip> 443` | Both succeed | ICMP blocked, TCP allowed — network is fine |
| `ping` works, `nc -vz` fails with timeout | `traceroute -T -p 443 <ip>` | Star `* * *` at a specific hop | Routing or firewall at that hop |
| `curl` succeeds, `curl -v` shows wrong SNI | `openssl s_client -connect <ip>:443 -servername <name>` | Returns wrong cert | SNI / virtual host misconfig |
| `curl` times out exactly at `--max-time` | `curl -w '%{time_starttransfer}'` | First-byte time ≈ --max-time | Backend not responding |

## Ship It

The `outputs/prompt-dns-works-but-http-fails.md` file is your deliverable. Author a one-page runbook that another engineer could use to triage a "DNS works but HTTP fails" report. The runbook should contain:

1. The seven-command decision tree, with a one-line "if you see X, the answer is Y" for each command.
2. A table of HTTP status codes vs. the layer they typically implicate, with a one-line diagnostic command for each.
3. A list of three common false-positive pitfalls: (a) ICMP is rate-limited or blocked so `ping` failing does not prove TCP is broken, (b) `dig` returns a cached answer that may not reflect the current path, (c) HTTP 502 from a proxy is the proxy's report about the backend, not the backend's report about itself.
4. A "first-byte time" table: < 100 ms = healthy, 100–500 ms = slow, 500 ms – 2 s = very slow, > 2 s = probably the fault.

## Exercises

1. **Seven-command chain**: For each of the three failure classes (refused, timeout, slow backend), identify which of the seven commands first produces decisive evidence. Justify the ordering.
2. **Curl -v reading**: A `curl -v` output stops at `* connect to 203.0.113.42 port 443 failed: Connection timed out`. At what layer did the failure occur? Is this a TCP-level or application-level problem?
3. **Stale cache**: A TTL of 3600 was set 30 minutes ago. The path to the IP is now broken. How long will `dig` continue to return the (now-stale) IP? What command bypasses the cache?
4. **First-byte time**: A `/health` endpoint normally returns in 80 ms. Today it returns in 9.4 s. The TCP handshake is normal. What is the most likely layer of the fault? Name two diagnostic commands that would confirm.
5. **Compare with lesson 01**: Lesson 01 (physical-to-application outage) starts at L1. Lesson 02 (DNS-works-but-HTTP-fails) starts at L7. Where do the diagnostic chains meet, and at which layer is the most decisive evidence typically found?
6. **Modify the simulator**: Add a `connection_pool_exhausted` mode where ephemeral ports are exhausted on the client. `curl` fails with "Cannot assign requested address." Walk through the diagnostic chain and identify which command catches it. (Hint: it is `ss -s` showing `TCP:` and the `allocated` field.)

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| DNS cache | Memory used for DNS | A resolver-side store of recent query answers, keyed by name/type/class, valid for the record's TTL |
| TTL | Time to live | In DNS, the cache lifetime in seconds; in IP, a hop-counter that decrements at each router |
| TCP RST | Reset | A control flag that forcibly terminates a connection, sent in response to SYN-without-listener or to refuse data on an invalid sequence |
| SYN retransmission | A retry | The first retransmission cascade the kernel uses to establish a connection; exponential backoff per RFC 6298 |
| `nc -vz` | Netcat verbose zero-IO | A one-shot TCP port probe: open a socket, do not send data, report open/closed/filtered |
| `ss -ti` | Socket stats with internal info | Linux's per-socket TCP state, including retrans, RTO, cwnd, ssthresh, and rtt |
| First-byte time | A timing metric | The wall-clock time from the request being sent to the first response byte being received, reported by `curl -w '%{time_starttransfer}'` |
| 502 Bad Gateway | A status code | The proxy or load balancer could not reach the upstream, or the upstream returned an invalid response |
| Stale cache | A dirty cache | A cached entry that is within its TTL but no longer reflects the current state of the world |
| Split-horizon DNS | A clever trick | Returning different answers for the same name depending on the client's source IP, often used to direct internal users to internal services |

## Further Reading

- **RFC 1035** — *Domain Names — Implementation and Specification*. The DNS protocol, including the structure of the A record and the TTL field.
- **RFC 6298** — *Computing TCP's Retransmission Timer*. The RTO cascade that produces the 127-second SYN timeout.
- **RFC 7230** — *HTTP/1.1: Message Syntax and Routing*. The structure of HTTP requests and responses that `curl -v` prints.
- **`man ss`** — the Linux socket-stat utility. The full set of `-i` fields and their meaning.
- **`man curl`** — the `time_starttransfer`, `time_connect`, `time_appconnect` variables available with `-w`.
- **Wireshark display filters reference** — `dns`, `tcp.flags.syn == 1`, `tcp.flags.reset == 1`, `http.response.code`. Filters for isolating the layer of interest.
- **phases/09-tcp-and-udp** — TCP fundamentals, including the three-way handshake and the retransmission timer.
- **phases/10-application-protocols** — DNS, HTTP, and TLS fundamentals relevant to the user-visible symptom.
- **phases/17-integrated-troubleshooting-labs/01-physical-to-application-outage-trace** — the parent lesson whose diagnostic chain this lesson specializes.
- **phases/17-integrated-troubleshooting-labs/09-nat-port-exhaustion-hairpin-loopback** — the NAT-exhaustion failure class mentioned in the exercises.
- **phases/17-integrated-troubleshooting-labs/26-ephemeral-port-exhaustion-time-wait-tuning** — the port-exhaustion failure class.
