# Slow Start and Congestion-Window Clamping Across a High-BDP Link

> A bulk-data transfer between a data center in Frankfurt and a data center in Singapore runs at 1 Gbps and 200 ms RTT. The BDP is `1 Gbps × 200 ms = 200 Mbit = 25 MB`. The TCP `cwnd` should grow to ~25 MB before the first ACK arrives at the receiver. But the user's `scp` peaks at 250 Mbps — 25% of the link capacity. The diagnostic is `ss -ti` on the sender's socket: `cwnd:30` (about 30 MSS-sized segments ≈ 43 KB). The kernel's congestion window is not growing past 30 segments. The cause is **`tcp_notsent_lowat`** and **`tcp_sndbuf`** clamping: the default `tcp_wmem` is `4096 16384 4194304` (4 KB min, 16 KB default, 4 MB max), and the kernel's `tcp_autocorking` waits for a full buffer before sending. The 30-segment `cwnd` is bounded by the socket send buffer, which is bounded by `tcp_wmem` (max 4 MB), and `tcp_notsent_lowat` further constrains the kernel to keep most of the buffer unflushed. The fix is a combination: increase `tcp_wmem` to a value that covers the BDP (`net.ipv4.tcp_wmem='4096 87380 67108864'`, i.e., 4 KB / 87 KB / 64 MB), and tune the receiver's `tcp_rmem` similarly. The other half of the fix is the **`initial cwnd`** and **`tcp_slow_start_after_idle`**: the kernel's initial cwnd is 10 MSS (RFC 6928), and after the socket goes idle, slow start is restarted. The transfer peaks at 250 Mbps because the kernel never lets the cwnd grow past the socket buffer.

**Type:** Lab
**Languages:** Python, shell, tc, tcpdump
**Prerequisites:** Phase 11 TCP slow start and congestion avoidance, BDP calculation, Linux `tcp_wmem`/`tcp_rmem` sysctls
**Time:** ~100 minutes

## Learning Objectives

- Diagnose a bulk TCP transfer that is far slower than the link allows: read `ss -ti` for the sender's cwnd, compute the BDP from the link bandwidth and RTT, and identify the gap.
- Compute the right `cwnd_min` for the BDP: `cwnd_min = BDP_in_bytes / MSS`. For a 1 Gbps link with 200 ms RTT and 1,460-byte MSS, this is `25,000,000 / 1,460 ≈ 17,123` segments.
- Read the kernel's `tcp_wmem` and `tcp_rmem` sysctls; explain the three values (min, default, max) and how they clamp the socket send/receive buffer.
- Use `tc qdisc add dev eth0 root netem delay 200ms rate 1gbit` to simulate a high-BDP link, and `iperf3` to measure throughput.
- Apply the four fixes: (a) increase `tcp_wmem` and `tcp_rmem`, (b) disable `tcp_slow_start_after_idle`, (c) increase `tcp_init_cwnd` to a value that matches the BDP, (d) check the receiver's `tcp_rmem` and the receive window scaling.
- Build a Python simulator that walks the slow-start / congestion-avoidance state machine and the cwnd growth, and prints the verdict that matches the production `ss -ti` output.

## The Problem

The on-call SRE for a global data analytics company gets a ticket: "Bulk data transfer between FRA and SIN is hitting 250 Mbps, not the 1 Gbps the link supports. `iperf3` shows the same number. The link itself is 1 Gbps with sub-millisecond errors." The transfer is a 100 GB nightly backup that is taking 6 hours instead of 15 minutes.

The BDP is `1 Gbps × 200 ms = 200 Mbit = 25 MB`. For a TCP transfer to fill the link, the sender's `cwnd` must reach ~25 MB before the first RTT is over. With an MSS of 1,460 bytes, that is ~17,000 segments in flight. But the sender's cwnd peaks at 30 segments, which is ~43 KB. The transfer is cwnd-limited, not bandwidth-limited.

The cause is the kernel's socket send buffer. The default `tcp_wmem` is `4096 16384 4194304` (4 KB min, 16 KB default, 4 MB max). The kernel's `tcp_autocorking` keeps the socket buffer mostly full of unsent data, and the cwnd is bounded by the size of the buffer that is "in flight" (sent but not ACKed). The buffer cannot grow past 4 MB, so the cwnd is clamped.

The diagnostic is `ss -ti` for the sender's socket:

```
ESTAB  0  64512  10.0.0.5:443  10.0.0.6:54321
   skmem:(r0,rb374000,t0,tb46000,f0,w0,o0,bl0,d0)
   cwnd:30  rtt:200/50  mss:1460  rcvmss:1460  advmss:1460  cwnd:30 ssthresh:21
```

`cwnd:30` and `tb46000` (send buffer 46 KB) confirm the cwnd is buffer-limited.

The fix is multi-part:

1. **Increase `tcp_wmem`**: `sysctl -w net.ipv4.tcp_wmem='4096 87380 67108864'` (4 KB / 87 KB / 64 MB). The third value (max) must cover the BDP.
2. **Increase `tcp_rmem`**: `sysctl -w net.ipv4.tcp_rmem='4096 87380 67108864'`. The receiver's window is the upper bound on the sender's cwnd (with window scaling).
3. **Disable `tcp_slow_start_after_idle`**: `sysctl -w net.ipv4.tcp_slow_start_after_idle=0`. This prevents the cwnd from collapsing to 1 MSS after an idle period.
4. **Increase `tcp_init_cwnd`**: `ip route change default via <gw> dev eth0 initcwnd 32 initrwnd 32`. The default is 10 (RFC 6928); for a high-BDP link, 32-64 is appropriate.

After the fix, the cwnd grows to 17,000 segments and the transfer fills the 1 Gbps link.

## The Concept

### The BDP calculation

The Bandwidth-Delay Product is the amount of data that can be "in flight" on a link at any moment. It is the link's bandwidth times the round-trip time:

```
BDP = bandwidth × RTT
```

For a 1 Gbps link with 200 ms RTT:

```
BDP = 1,000,000,000 bps × 0.2 s = 200,000,000 bits = 25,000,000 bytes ≈ 25 MB
```

The TCP `cwnd` must grow to at least the BDP before the sender can fill the link. If the cwnd is smaller, the sender is idle while waiting for ACKs, and the link is under-utilized.

### The slow start / congestion avoidance state machine

TCP's slow start (RFC 5681 §3.1) starts with `cwnd = initcwnd` (default 10 MSS, RFC 6928). On each ACK, `cwnd` is increased by 1 MSS. This is exponential growth: `cwnd` doubles every RTT. Slow start continues until `cwnd` reaches `ssthresh` (slow start threshold, initially infinite), at which point the algorithm switches to congestion avoidance: `cwnd` is increased by 1 MSS every RTT (linear growth).

The trigger to exit slow start is:

- `cwnd` reaches `ssthresh` (set by the application or by previous loss)
- A packet loss is detected (sets `ssthresh = cwnd / 2` and reduces `cwnd = ssthresh`)
- An ECN feedback is received (same as loss)

The initial cwnd is configurable per-route: `ip route change default via <gw> dev eth0 initcwnd 32`. The default of 10 MSS is too small for high-BDP links.

### The socket buffer clamping

The kernel's socket buffer has three values:

- `min`: the initial buffer size, guaranteed to be available
- `default`: the default size for new sockets
- `max`: the maximum size, used when the application sets `SO_SNDBUF` / `SO_RCVBUF`

The `tcp_wmem` and `tcp_rmem` sysctls set these for TCP sockets. The default max is 4 MB, which is far smaller than the BDP of a high-BDP link. The cwnd cannot grow past the buffer's "in flight" portion (sent but not ACKed), so the buffer clamps the cwnd.

The fix is to set the max to at least the BDP. For the 1 Gbps × 200 ms example, the max should be at least 25 MB, with headroom for cwnd growth beyond the BDP: 64 MB is a good target.

### `tcp_slow_start_after_idle`

When a TCP connection goes idle (no packets sent or received for a timeout), the kernel may reset `cwnd` to `initcwnd`. This is to prevent stale cwnd values from causing congestion. For a long-lived bulk transfer, this is undesirable: a momentary pause (e.g., a write that takes 1 second) would trigger the cwnd collapse.

`sysctl -w net.ipv4.tcp_slow_start_after_idle=0` disables this. The cwnd then persists across idle periods. For a high-BDP bulk transfer, this is the right setting.

### Window scaling (RFC 7323)

The TCP receive window is 16 bits in the header, max 65,535 bytes. For a high-BDP link, that is too small. RFC 7323 introduces window scaling: a negotiated scale factor (0-14) that multiplies the receive window. With a scale of 8, the receive window can be 16 MB. With a scale of 14, it can be 1 GB.

The receiver's `tcp_rmem` max sets the receive window's max value. The window scale is negotiated in the SYN/SYN-ACK. The kernel enables window scaling by default (`net.ipv4.tcp_window_scaling=1`).

### `ss -ti` output

`ss -ti` prints the socket's internal state, including:

- `cwnd`: the current congestion window in segments
- `rtt`: smoothed RTT / RTT variance
- `mss`: the current MSS
- `ssthresh`: the slow-start threshold
- `bytes_sent`, `bytes_retrans`
- `skmem:` a memory summary showing the buffer state

A cwnd that is "stuck" at a small value (30-50 segments) for a long-RTT high-bandwidth link is the diagnostic for buffer-clamping.

### How the simulator models this

`code/main.py` walks the slow-start state machine for a configurable scenario (`--scenario bdp_clamped`, `--scenario cwnd_grown`, `--scenario init_cwnd_high`, `--scenario slow_start_after_idle`). The simulator prints the cwnd growth, the buffer state, and the verdict that matches the production `ss -ti` output.

## Build It

1. **Set up the high-BDP link.** `tc qdisc add dev eth0 root netem delay 200ms rate 1gbit`.
2. **Measure baseline.** `iperf3 -c <server> -t 60`. Capture `cwnd` from `ss -ti` every 5 seconds. Confirm the cwnd is buffer-clamped.
3. **Apply the fix.** `sysctl -w net.ipv4.tcp_wmem='4096 87380 67108864'`, `sysctl -w net.ipv4.tcp_rmem='4096 87380 67108864'`, `sysctl -w net.ipv4.tcp_slow_start_after_idle=0`. Re-test.
4. **Confirm the cwnd growth.** `ss -ti` should now show cwnd in the thousands of segments.
5. **Run the simulator.** `python3 code/main.py --scenario bdp_clamped` should print the matching state machine.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute BDP | `bandwidth × RTT` | A number in bytes; the target cwnd |
| Read tcp_wmem | `cat /proc/sys/net/ipv4/tcp_wmem` | Max is at least the BDP; 64 MB is typical |
| Read tcp_rmem | `cat /proc/sys/net/ipv4/tcp_rmem` | Max is at least the BDP |
| Read initcwnd | `ip route show \| grep initcwnd` | 10 default; 32+ for high-BDP |
| Read cwnd | `ss -ti` for the bulk flow | cwnd in the thousands for a 1 Gbps × 200 ms link |
| Confirm window scale | SYN/SYN-ACK options | Scale > 0; permits 1 MB+ receive window |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **high-BDP bulk transfer runbook** with the four sysctls, the cwnd growth calculation, and the iperf3 confirmation.
- A **before/after capture** of `ss -ti` and `iperf3` showing the cwnd growth and the throughput.

Start from `outputs/prompt-high-bdp-congestion-window-clamping.md`.

## Exercises

1. A 10 Gbps link has 100 ms RTT. Compute the BDP. With an MSS of 1,460 bytes, how many segments are in flight at the BDP? What should `tcp_wmem`'s max be?
2. `tcp_init_cwnd=10` is the default. For a 10 Gbps × 100 ms link, what is the right initcwnd? Why is `initcwnd=10` a poor choice for this link?
3. `tcp_slow_start_after_idle=1` (default) causes the cwnd to collapse to `initcwnd` after 1 RTT of idle. For a long-lived bulk transfer, why is this undesirable?
4. The receiver's `tcp_rmem` max is 4 MB. The sender's `cwnd` is 30 MB. Will the sender's cwnd grow past 4 MB? Why or why not?
5. A window scale of 8 is negotiated. The receiver's `tcp_rmem` max is 16 MB. What is the maximum effective receive window? Is 16 MB the right value for a 10 Gbps × 100 ms link?
6. `iperf3` between FRA and SIN shows 1 Gbps. The BDP is 25 MB. The cwnd peaks at 17,000 segments (= 25 MB). The throughput is 1 Gbps. Now `tcp_slow_start_after_idle` is enabled and the transfer has a 2-second gap in the middle. Compute the new throughput assuming the cwnd collapses to 10 MSS and grows back over 5 RTTs.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| BDP | "Bandwidth-delay product" | `bandwidth × RTT`; the amount of data in flight to fill the link |
| `cwnd` | "Congestion window" | The sender's limit on bytes in flight; must reach the BDP for full link utilization |
| `ssthresh` | "Slow start threshold" | The cwnd at which slow start switches to congestion avoidance |
| `initcwnd` | "Initial cwnd" | The cwnd for new connections; default 10 MSS (RFC 6928) |
| `tcp_wmem` | "Send buffer" | The three values (min, default, max) of the socket send buffer |
| `tcp_rmem` | "Receive buffer" | The three values (min, default, max) of the socket receive buffer |
| Window scaling | "RFC 7323" | A scale factor (0-14) that multiplies the 16-bit receive window; permits 1 GB windows |
| `tcp_slow_start_after_idle` | "Idle cwnd reset" | The sysctl that collapses cwnd to initcwnd after idle; disable for bulk transfer |

## Further Reading

- RFC 5681 — TCP Congestion Control (slow start, congestion avoidance, fast retransmit)
- RFC 6928 — Increasing TCP's Initial Window
- RFC 7323 — TCP Extensions for High Performance (window scaling, timestamps, PAWS)
- RFC 1323 — predecessor to RFC 7323 (window scaling)
- Linux `man tcp(7)` — `tcp_wmem`, `tcp_rmem`, `tcp_slow_start_after_idle`
- `ss(8)` — `-i` flag for internal socket state
- `ip-route(8)` — `initcwnd` and `initrwnd` per-route options
- `tc-netem(8)` — `delay` and `rate` for link simulation
