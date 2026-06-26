# Ephemeral Port Exhaustion and TIME_WAIT Tuning

> A web service that proxies outbound HTTP requests to upstream APIs starts failing at peak load. The error is `EADDRNOTAVAIL` from the `connect(2)` syscall: the kernel cannot find an available local port. The service's source code is correct; the upstream is healthy; the network is fine. The diagnostic is `ss -s` (socket statistics): `TCP: active 8000, passive 1, ... ` and `TCP over 60000 in use`. The kernel's ephemeral port range is 28,232 to 60,999 (the Linux default: `ip_local_port_range = 32768 60999`), and almost all 60,000+ ports are in `TIME_WAIT` state. TIME_WAIT is the TCP state a socket enters after the local end has sent the final FIN and received the final ACK — it persists for `2 * MSL` (60 seconds by default, per RFC 793 / RFC 9293) to ensure any straggling packets from the peer are silently dropped. With 60,000 sockets in TIME_WAIT, the kernel has no ephemeral port to assign to a new outgoing connection. The fix is a combination of: (a) increase the ephemeral port range: `sysctl -w net.ipv4.ip_local_port_range="1024 65535"`, (b) enable `tcp_tw_reuse=1` so the kernel can recycle a TIME_WAIT socket for a new outgoing connection to the same destination, (c) reduce `tcp_fin_timeout=15` (default 60 s) to shorten the TIME_WAIT window. The wrong fix is to disable TIME_WAIT entirely (`tcp_tw_recycle=1`) — that option was removed from the Linux kernel in 4.12 because it caused NAT-rebind issues for many users.

**Type:** Lab
**Languages:** Python, shell, ss, sysctl
**Prerequisites:** Phase 11 TCP state machine, the `ip_local_port_range` sysctl, the TIME_WAIT state (RFC 793 / RFC 9293)
**Time:** ~85 minutes

## Learning Objectives

- Diagnose `EADDRNOTAVAIL` from `connect(2)` on an outbound-heavy service: read `ss -s`, find the 60,000+ TIME_WAIT sockets, and explain why the kernel cannot assign a new ephemeral port.
- Read the kernel's ephemeral port range: `cat /proc/sys/net/ipv4/ip_local_port_range`. Compute the number of available ports (`max - min + 1`).
- Distinguish three failure modes: (a) port exhaustion (all ports in TIME_WAIT), (b) SNAT exhaustion (a SNAT rule has too few ports), (c) connection-rate exhaustion (TIME_WAIT sockets accumulate faster than they expire).
- Use `ss -tan state time-wait | wc -l` to count TIME_WAIT sockets, `ss -tan '( sport = :443 )' | wc -l` to count connections to a specific destination.
- Use `sysctl -w` to apply the three fixes: `ip_local_port_range`, `tcp_tw_reuse`, `tcp_fin_timeout`. Verify with `ss -s` after the change.
- Build a Python simulator that walks the TCP state machine and the ephemeral port assignment, and prints the verdict that matches a production `ss -s` output.

## The Problem

The on-call SRE for a web service gets a ticket: "Outbound HTTP requests to `api.partner.example` are failing at peak load. The error log shows `connect: cannot assign requested address`. The partner's API is healthy. Our service is the only one with the error." The service makes 1,000 outbound HTTP requests per second to the same upstream, and the upstream's keep-alive connection pool is configured for 5,000 connections. Each connection is closed after 60 seconds of idle time. At peak, 1,000 connections per second are being closed, and each closed connection enters TIME_WAIT for 60 seconds — so there are 60,000 sockets in TIME_WAIT at any moment. With the default ephemeral port range of 28,232 to 60,999 (32,768 ports), the kernel cannot find an unused port to bind a new outgoing connection.

The diagnostic is `ss -s` (or `netstat -s`). The output:

```
TCP: active (opens 12345, passive 1, ...)
     passive (syn接受了 ...)
     inuse 60000 ...   <-- 60,000 sockets in use
     ... 
TCP TIME_WAIT 59987   <-- almost all are TIME_WAIT
```

The fix has three parts:

1. **`ip_local_port_range`**: expand the range to 1024-65535 (about 64,000 ports). `sysctl -w net.ipv4.ip_local_port_range="1024 65535"`.
2. **`tcp_tw_reuse`**: enable so the kernel can recycle a TIME_WAIT socket for a new outgoing connection to the same destination. `sysctl -w net.ipv4.tcp_tw_reuse=1`. This is safe; it does not apply to incoming connections.
3. **`tcp_fin_timeout`**: reduce the FIN-WAIT-2 timeout so TIME_WAIT clears faster. `sysctl -w net.ipv4.tcp_fin_timeout=15`. (Default is 60 s.) This is also safe for outgoing connections.

The wrong fix is `tcp_tw_recycle=1`, which was removed in Linux 4.12 because it caused TIME_WAIT to be skipped for connections that were not from the exact same source IP+port — a problem for NATed clients. Modern kernels do not have this knob at all.

## The Concept

### The ephemeral port range

The Linux kernel uses the `ip_local_port_range` sysctl to define the range of ports that can be assigned to outgoing connections. The default is 32768 to 60999, giving 28,232 ports. Each new outgoing connection consumes one port; the port is held for the entire life of the connection, plus the TIME_WAIT period after it closes.

For a service that opens many outgoing connections, the range must be large enough to cover the peak load × TIME_WAIT duration. A service that opens 1,000 connections per second with a 60-second TIME_WAIT needs at least 60,000 ephemeral ports. The default is 28,232. The service is short by 31,768 ports.

### The TIME_WAIT state (RFC 793 / RFC 9293)

TIME_WAIT is the state a socket enters after the local end has sent the final FIN and received the final ACK (i.e., after the active close completes). The socket stays in TIME_WAIT for `2 * MSL` (Maximum Segment Lifetime, 60 seconds by default on Linux = `net.ipv4.tcp_fin_timeout` for FIN-WAIT-2, but TIME_WAIT itself is `2 * MSL` = 60 s in Linux).

The purpose of TIME_WAIT is to ensure any straggling packets from the peer are silently dropped rather than being delivered to a new socket that happens to use the same 4-tuple. Without TIME_WAIT, a delayed FIN-ACK from the peer could be delivered to a new connection, causing spurious retransmissions or a phantom RST.

The cost is that the 4-tuple cannot be reused for 60 seconds. This is fine for clients (each client uses a unique source port) but problematic for services that make many outgoing connections to the same destination (where the source port is the only varying part of the 4-tuple).

### `tcp_tw_reuse` and the safe reuse policy

`tcp_tw_reuse=1` allows the kernel to assign a port that is in TIME_WAIT to a *new* outgoing connection, but only if the new connection is to the same destination IP:port and the socket is not in the LAST_ACK state. This is safe because the kernel knows the destination is the same; the straggling packets from the old connection will be ignored by the peer (which has already moved on).

`tcp_tw_reuse` is the right knob for client-side port exhaustion. It is enabled by default on many distributions but not all.

### The (removed) `tcp_tw_recycle` option

`tcp_tw_recycle=1` was a more aggressive option that allowed the kernel to skip TIME_WAIT entirely for *incoming* connections if the client had connected from the same IP:port within a recent window. It was removed in Linux 4.12 because it caused widespread breakage for NATed clients: the NAT's many internal hosts would all look like the same IP:port, and the TIME_WAIT shortcut would break their connections. Modern kernels do not have this option; the only safe knob is `tcp_tw_reuse`.

### `ss -s` and the socket statistics

`ss -s` is the modern replacement for `netstat -s`. The output is grouped by protocol. The fields to read:

- `active (opens N, ...)`: how many times the local side opened a connection
- `passive (syn接受了 N)`: how many times the local side accepted a connection
- `inuse N`: how many sockets are in use (across all states)
- `TIME_WAIT N`: how many sockets are in TIME_WAIT
- `CLOSE_WAIT N`: how many sockets are in CLOSE_WAIT (the local end has received a FIN but not yet sent a FIN back; usually a sign of an app bug)

A healthy server has a few hundred TIME_WAIT sockets. A server with 60,000 TIME_WAIT sockets has port exhaustion.

### `ss -tan state time-wait | wc -l`

The command `ss -tan state time-wait` lists all TCP sockets in TIME_WAIT. `wc -l` counts them. For a multi-tenant host, this can reach 100,000+ during a port-exhaustion event.

### The three fixes, in order of safety

1. **Increase `ip_local_port_range`**: safe, increases capacity.
2. **Enable `tcp_tw_reuse`**: safe for outgoing connections, allows TIME_WAIT recycling.
3. **Reduce `tcp_fin_timeout`**: slightly reduces the TIME_WAIT window; not as safe as the above, but useful for high-turnover services.

### How the simulator models this

`code/main.py` walks the TCP state machine and the ephemeral port assignment for a configurable scenario (`--scenario port_exhausted`, `--scenario tw_reuse`, `--scenario range_expanded`, `--scenario tw_recycle_removed`). The simulator prints the port count, the TIME_WAIT count, and the verdict that matches a production `ss -s` output.

## Build It

1. **Reproduce the failure.** Open 30,000 outgoing connections in a Python script, close them all, and try to open a new connection. Capture `EADDRNOTAVAIL`.
2. **Read the kernel state.** `ss -s`, `cat /proc/sys/net/ipv4/ip_local_port_range`, `cat /proc/sys/net/ipv4.tcp_tw_reuse`.
3. **Apply the fix.** `sysctl -w net.ipv4.ip_local_port_range="1024 65535"`, `sysctl -w net.ipv4.tcp_tw_reuse=1`.
4. **Re-test.** Open 30,000 connections again, close them, open a new one. The new connection succeeds.
5. **Run the simulator.** `python3 code/main.py --scenario port_exhausted` should print the matching state machine.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read port range | `cat /proc/sys/net/ipv4/ip_local_port_range` | `1024 65535` (or larger) |
| Count TIME_WAIT | `ss -tan state time-wait \| wc -l` | A few hundred; not 60,000+ |
| Read socket stats | `ss -s` | `inuse` is reasonable; `TIME_WAIT` is < 50% of `inuse` |
| Confirm tcp_tw_reuse | `cat /proc/sys/net/ipv4/tcp_tw_reuse` | `1` (enabled) |
| Confirm tcp_fin_timeout | `cat /proc/sys/net/ipv4/tcp_fin_timeout` | `15` or less (more aggressive) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **port-exhaustion triage runbook** with the four sysctls and the three fixes.
- A **before/after** `ss -s` capture showing the TIME_WAIT count and the `inuse` count.

Start from `outputs/prompt-ephemeral-port-exhaustion-time-wait-tuning.md`.

## Exercises

1. The default `ip_local_port_range` is `32768 60999`. Compute the number of available ports. With 1,000 outgoing connections per second and a 60-second TIME_WAIT, how many ports are needed? Is the default sufficient?
2. `tcp_tw_reuse=1` allows the kernel to recycle a TIME_WAIT socket for a new outgoing connection. What constraint does the kernel check before recycling? Why is the constraint safe?
3. The Linux kernel removed `tcp_tw_recycle=1` in 4.12. What was the bug, and why was it especially bad for NATed clients?
4. A service has 60,000 TIME_WAIT sockets but no `EADDRNOTAVAIL` errors. The next outbound connection succeeds. Why? What does this say about the port-exhaustion threshold?
5. `tcp_fin_timeout=15` reduces the FIN-WAIT-2 timeout from 60 s to 15 s. What is the consequence for the TIME_WAIT state? Is the value of TIME_WAIT itself still 60 s?
6. A service uses HTTP/1.1 keep-alive with `Connection: keep-alive, timeout=300, max=100`. After 100 requests, the connection is closed. The service runs at 5,000 requests per second. How many outgoing connections are in TIME_WAIT at any moment?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Ephemeral port | "Source port" | The local port the kernel assigns to an outgoing connection, from `ip_local_port_range` |
| `ip_local_port_range` | "The port pool" | The sysctl defining the available ephemeral port range; default `32768 60999` |
| TIME_WAIT | "2 * MSL" | The TCP state after active close; lasts `2 * MSL` (60 s on Linux) to drop straggling packets |
| `tcp_tw_reuse` | "Recycle TIME_WAIT" | The sysctl that allows TIME_WAIT sockets to be reused for new outgoing connections to the same destination |
| `tcp_tw_recycle` | "Skip TIME_WAIT" | The removed (4.12) sysctl that caused widespread breakage for NATed clients |
| `EADDRNOTAVAIL` | "No port" | The `connect(2)` error when the kernel cannot find an ephemeral port |
| `ss -s` | "Socket stats" | The `ss` command's summary; reports inuse, TIME_WAIT, CLOSE_WAIT, etc. |
| `tcp_fin_timeout` | "FIN-WAIT-2" | The sysctl for FIN-WAIT-2 timeout; reducing it also shortens TIME_WAIT |

## Further Reading

- RFC 793 / RFC 9293 — Transmission Control Protocol (TIME_WAIT state, 2 * MSL)
- Linux `man tcp(7)` — `tcp_tw_reuse`, `tcp_tw_recycle` (the latter is removed)
- Linux `man ip(7)` — `ip_local_port_range`
- Linux `man ss(8)` — socket statistics and state filters
- Linux kernel commit `5d2ed0527c` — removal of `tcp_tw_recycle` in 4.12
- `netstat(8)` — the older tool; `ss(8)` is the modern replacement
- IETF `tcpm` working group — TCP maintenance and timeouts
