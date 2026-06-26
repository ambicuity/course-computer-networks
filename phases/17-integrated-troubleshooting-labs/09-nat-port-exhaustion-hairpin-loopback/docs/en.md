# NAT Port Exhaustion and Hairpin Loopback

> A 2,000-employee campus runs a single public IPv4 through a Linux conntrack table that holds 262,144 tuples. Yesterday the SD-WAN appliance in the data center opened a long-lived HTTPS keep-alive to a SaaS vendor; this morning a slack-bot fan-out opened 18,000 short-lived HTTPS connections in 90 seconds. The NAT pool filled; new SYNs from the load-test rig began returning `connect: Cannot assign requested address` and never produced a SYN-ACK. The VPN concentrator, sitting on the same NAT, was also unreachable from a customer demo in Hong Kong. The traceroute from the customer endpoint to the public IP stopped one hop past the ISP edge with a `* * *`; the inside server kept logging valid client connections for a few minutes, then nothing. We will reproduce the exhaustion, prove the cause is the conntrack table not the upstream, and design a split-horizon DNS and address-pool pairing fix for the hairpin case where inside clients reach an inside server through its public address.

**Type:** Lab
**Languages:** Python (stdlib), conntrack, iptables, ss
**Prerequisites:** Phase 09 NAT/ICMP labs, Phase 17 lesson 08
**Time:** ~95 minutes

## Learning Objectives

- Compute the simultaneous-flow ceiling of a single public IPv4 under symmetric NAPT and explain why TIME-WAIT amplifies the cost.
- Distinguish ephemeral-port starvation from upstream packet loss and from DNS resolution failure using `ss -tan state-time-wait`, `conntrack -L`, and `dmesg`.
- Identify a hairpin (loopback) flow where both endpoints sit behind the same NAT and explain why the return tuple can collide with the outbound leg of a peer flow.
- Propose NAT tuning, address-pool expansion, and split-horizon DNS remediation from measured evidence, and quantify the impact of each on connection rate.
- Build a deterministic NAT exhaustion simulator whose allocation log matches the observed kernel `insert_failed` counter.
- Diagnose a hairpin loop from server logs that show public-IP source addresses and intermittent connect failures on inside clients.

## The Problem

A medium enterprise has a single /29 public block (eight addresses) routed to the WAN edge. Six of those addresses are in use for the VPN concentrator, the SMTP relay, the customer-facing web farm, the partner API, the monitoring probe, and the voice gateway. The remaining two are configured as the "primary outbound pool" used by 2,000 desktops, laptops, and IoT devices. The Linux conntrack table is sized at 262,144 tuples (`nf_conntrack_max=262144`) and the ephemeral port range is the default `32768-60999`, giving a per-address theoretical ceiling of 28,232 simultaneous flows.

On a Tuesday morning, the SD-WAN appliance initiated a long-lived HTTPS keep-alive to a SaaS vendor (`203.0.113.40:443`) and held it for the entire day. At 09:14, a CI/CD run kicked off 18,000 short-lived HTTPS connections to the same vendor over 90 seconds to fetch package mirrors. The first 4,200 succeeded, the next 8,000 produced SYN retransmissions, the rest were dropped locally. The conntrack table filled with `TIME_WAIT` entries that the kernel was holding for 120 seconds; the SD-WAN keep-alive continued to consume one tuple for the entire window. The upstream was not lossy; the bottleneck was the NAT itself.

Compounding the issue: a separate problem was reported by the inside helpdesk. When an inside client tried to reach the inside helpdesk portal by its public hostname (`helpdesk.example.com -> 198.51.100.55:443`), the connection succeeded roughly half the time. Traceroute from the inside client showed the first hop as the inside default gateway; the path was hairpinning through the public NAT. The portal server, which binds only to the inside address `10.10.0.55`, was sometimes receiving the rewritten packet with `src=198.51.100.10` (the public NAT IP) and sometimes with `src=10.10.0.42` (the original inside client). The server's TCP stack could not demultiplex reliably, and the connection reset intermittently.

The `code/main.py` in this lesson replays both failure modes — single-pool exhaustion and hairpin tuple collision — in a single deterministic scenario, and prints a runbook that names the conntrack knob, the ephemeral range knob, and the DNS split-horizon remediation.

## The Concept

### The 5-tuple space under NAPT

Network Address and Port Translation (NAPT, RFC 3022) maps every inside 5-tuple `(src_ip, src_port, dst_ip, dst_port, proto)` to an outside 5-tuple that substitutes a public IP and a borrowed public port. The constraint is uniqueness: the outside 5-tuple must be globally unique while the flow is alive. With one public IP and a port range of size P, the maximum simultaneous flows is bounded by P minus the cost of TIME-WAIT reservation. Linux reserves a 5-tuple for 2*MSL after the closing FIN completes; with MSL=60s the cost is 120s of reservation per flow. The effective sustained rate is approximately `P / (TIME_WAIT_seconds)` flows per second before the pool cycles.

A single destination is an additional multiplier of the constraint. A NAT that supports Endpoint-Independent Mapping (EIM, RFC 4787) can reuse one external port for any number of inside flows to the same destination; a NAT that enforces Endpoint-Dependent Mapping (EDM, symmetric NAT) must allocate a distinct external port for each inside flow to each outside endpoint. Most production Linux gateways use EDM; the result is that a burst to one destination burns the entire port pool even when many destinations are still available.

### Conntrack, insert_failed, and the pool plateau

Linux implements NAT via the `nf_conntrack` netfilter module. The module maintains a hash table sized by `nf_conntrack_max`; each tuple consumes one entry. When the table is full, the kernel cannot insert a new tuple and emits an `nf_conntrack: table full, dropping packet` message to `dmesg`. The associated counter is `nf_conntrack_insert_failed`. The same plateau appears in the user-space `conntrack -L` output: the count stops growing while `ss -tan` shows a growing queue of `SYN_SENT` sockets on the inside clients.

The plateau is not packet loss in the traditional sense. The packet was never sent. From the client kernel's view, `connect(2)` returns `EADDRNOTAVAIL` (or `Cannot assign requested address`) because the source port allocation step inside `__inet_check_established` found no free port in the configured range. The upstream has not yet seen the SYN, so any attempt to debug the issue from the destination side will show no traffic at all.

### Hairpin NAT and the demultiplexing trap

Hairpin (also called NAT loopback, NAT reflection, or NAT hairpinning) is the case where two inside hosts communicate through a public address that resolves to another inside host. The classic topology: a small business publishes its web server at `example.com:80` which resolves to `198.51.100.10` (the public IP of the NAT). An inside client at `10.0.0.42` types `http://example.com` and the DNS answer `198.51.100.10` arrives. The client sends to `198.51.100.10:80`. The NAT must (1) rewrite source `10.0.0.42:50000` to public `198.51.100.10:60000` (or similar), (2) rewrite destination `198.51.100.10:80` to the inside server `10.0.0.10:80`, (3) deliver to the inside server, (4) accept the return from the inside server, and (5) rewrite the return in reverse.

The demultiplexing trap: when the inside server receives the rewritten packet, the source address is the public IP `198.51.100.10`. The server's TCP stack treats this as a self-connection. Some servers reject the connection outright; others process it. The reply goes back to `198.51.100.10:60000` and the NAT must recognize it as a continuation of the original flow. If the NAT has multiple inside hosts with overlapping source-port ranges — for example, two inside clients both using `50000` as their source port — the NAT's reverse lookup hash collides and the reply is delivered to the wrong inside client. The other client's connection silently fails.

### Detecting the failure mode

Three signals distinguish exhaustion from hairpin from upstream loss:

| Signal | Exhaustion | Hairpin | Upstream loss |
|---|---|---|---|
| `conntrack -L \| wc -l` | equals `nf_conntrack_max` | below max | below max |
| `dmesg \| grep nf_conntrack` | "table full" messages | none | none |
| `ss -tan state-syn-sent \| wc -l` | growing | stable | stable |
| `ss -tan state-time-wait \| wc -l` | near `nf_conntrack_max` | near `nf_conntrack_max` if hot | variable |
| Server sees source as | n/a (no traffic) | public IP | real client IP |
| `mtr -rn` to upstream | path OK | path OK | loss past ISP edge |

The hairpin case is uniquely identified by the inside server logging connections whose remote address is the public NAT IP rather than a real inside address.

### Remediation taxonomy

For exhaustion, four knobs in priority order:

1. **Address pool expansion** — add more public IPs to the outbound pool. Doubles the ceiling per IP.
2. **Widen the ephemeral range** — `net.ipv4.ip_local_port_range = 1024 65535` raises the per-IP ceiling from 28,232 to 64,512.
3. **Shorten TIME-WAIT** — `net.netfilter.nf_conntrack_tcp_timeout_time_wait = 30` halves the reservation cost per flow. The cost is asymmetric: a low value improves burst tolerance but may accept duplicate packets from prior incarnations.
4. **L7 proxy in front of bursty workloads** — a local nginx or HAProxy in the egress path reuses upstream connections, collapsing N outbound flows into a few persistent pools.

For hairpin, the canonical fix is split-horizon DNS: serve the inside address (`10.0.0.10`) to inside resolvers and the public address (`198.51.100.10`) to outside resolvers. This eliminates the hairpin path entirely. The second-best fix is to disable hairpin on the NAT (`iptables -t nat -A POSTROUTING -d 198.51.100.10 -j RETURN` for the inside zone) and accept that inside clients must use the inside address. The third option is hairpin-aware server config (e.g., nginx `set_real_ip_from` and `real_ip_header`) so the server can decode the original source.

## Build It

1. Read `code/main.py`. The `NatGateway` dataclass owns a `pool` set of `(public_ip, port)` tuples and a `flows` list. The `alloc_slot()` method is the linear-scan equivalent of the kernel's port allocator.
2. Run `python3 code/main.py` from the lesson root. The driver runs four scenarios: steady load, burst to one external destination, hairpin-heavy load, and a second-public-IP retry. Each scenario prints capacity, allocations, failures, and a diagnosis line.
3. Confirm that the burst-to-one-dest scenario fails: 28,232 slots are consumed by a pool of 28,232, and the remaining ~3,800 flows are dropped with `insert_failed`.
4. Confirm that the hairpin-heavy scenario reports tuple collisions when the inside server is asked to demultiplex more than one return flow that arrived with the same public-port key.
5. Add a fifth scenario that widens the ephemeral range from `32768-60999` to `1024-65535` and observe the pool ceiling rise from 28,232 to 64,512 per public IP.
6. Add a sixth scenario that lowers `nf_conntrack_tcp_timeout_time_wait` from 120s to 30s and observe the steady-state TIME-WAIT count drop. The `code/main.py` extends to ~190 lines for these two scenarios.
7. Add a synthetic event log under `outputs/` capturing the timeline of (a) the SD-WAN keep-alive, (b) the CI/CD burst, (c) the conntrack plateau, and (d) the recovery after the ephemeral range was widened. The log is the input to the runbook.

## Use It

| Symptom | Diagnostic Command | Expected Output |
|---|---|---|
| Pool exhausted | `cat /proc/sys/net/netfilter/nf_conntrack_count /proc/sys/net/netfilter/nf_conntrack_max` | Two integers; the first >= 95% of the second |
| `insert_failed` rising | `cat /proc/sys/net/netfilter/nf_conntrack_insert_failed` | Monotonically increasing |
| Client `EADDRNOTAVAIL` | `ss -tan state-syn-sent \| wc -l` | Growing count of half-open sockets |
| TIME-WAIT dominates | `ss -tan state-time-wait \| wc -l` | Near `nf_conntrack_max` |
| Hairpin detected | `tail -n 100 /var/log/nginx/access.log \| awk '{print $1}' \| sort -u` | Mix of public and inside source IPs |
| Hairpin demux collision | `grep 'connection reset' /var/log/portal/portal.log` | Reset entries whose client IP is the public NAT |
| Upstream loss ruled out | `mtr -rn -c 100 198.51.100.40` | Loss=0.0% on all hops |
| Ephemeral range too narrow | `cat /proc/sys/net/ipv4/ip_local_port_range` | `32768 60999` is the default; widen to `1024 65535` |
| TIME-WAIT too long | `cat /proc/sys/net/netfilter/nf_conntrack_tcp_timeout_time_wait` | Default 120; reduce to 30 if aggressive |
| Split-horizon DNS | `dig +short helpdesk.example.com @10.0.0.53` vs. `@8.8.8.8` | Inside: `10.0.0.10`; outside: `198.51.100.10` |

## Ship It

Produce a NAT capacity runbook under `outputs/`:

- The pool size formula `ephemeral_range * public_ips` annotated with the TIME-WAIT multiplier.
- A monitoring probe that asserts against the plateau threshold (`conntrack_count / conntrack_max > 0.9`) and pages on insert_failed > 0.
- A hairpin remediation decision tree: DNS split-horizon -> DMZ relay -> hairpin-aware server config.
- A migration checklist for widening `ip_local_port_range` in production: needs service restart for sockets already in TIME-WAIT.
- A second-public-IP rollout plan with conntrack affinity considerations.

Start with [`outputs/prompt-nat-port-exhaustion-hairpin-loopback.md`](../outputs/prompt-nat-port-exhaustion-hairpin-loopback.md).

## Exercises

1. Compute the maximum sustained connection rate a single public IP can sustain if every flow occupies TIME-WAIT for 60 seconds. Show the formula and the numerical result.
2. Demonstrate that adding a second public IP doubles the pool only if the NAT supports address-pool pairing; many simple NATs do not, and the second IP is used for a different outside destination pool.
3. Reproduce a hairpin failure where the inside server refuses the connection because the source appears to be the public NAT IP. Show the server's reject log line.
4. Propose a monitoring alert that distinguishes ephemeral exhaustion from upstream packet loss by combining conntrack count, `insert_failed`, and `mtr` loss into a single severity score.
5. Evaluate port preservation (full-cone NAT vs. symmetric NAT) impact on the exhaustion threshold for a UDP workload with high flow rate and short hold time.
6. Design a load test that drives the NAT to the plateau in 60 seconds and produces a clean recovery curve after the ephemeral range is widened. The test must not depend on a real public IP.

## Key Terms

| Term | Meaning |
|---|---|
| NAPT | Network Address and Port Translation; rewrites the 5-tuple |
| Ephemeral port | Source port borrowed from a bounded OS-controlled range |
| Hairpin | Inside clients reach an inside service via its public address |
| Conntrack | Kernel table holding NAT 5-tuples; has a hard cap |
| TIME-WAIT | TCP tail state; 2*MSL of port reservation before the tuple can be reused |
| Symmetric NAT | EDM; one external port per outbound flow; worst-case for pool use |
| Endpoint-Independent Mapping | EIM; one external port reused for any number of flows to a given inside endpoint |
| Port exhaustion | All ephemeral ports allocated; new connects fail locally |
| Split-horizon DNS | Different answers for inside vs. outside resolvers |
| `nf_conntrack_insert_failed` | Counter that rises when conntrack cannot insert a new tuple |

## Further Reading

- RFC 3022 — Traditional NAT (and NAPT)
- RFC 4787 — NAT UDP Behaviour Requirements (hairpin terminology)
- RFC 7857 — Updates to the NAT UDP Behaviour Requirements
- Linux conntrack documentation: `nf_conntrack` sysctl knobs, `conntrack-tools` user space
- "Linux NAT and Conntrack" — Jesper Dangaard Brouer, netdev 0x14 talk
