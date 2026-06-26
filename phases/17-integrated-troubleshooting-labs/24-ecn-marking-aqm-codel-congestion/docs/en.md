# ECN Marking and AQM (RED/CoDel) Congestion Interaction

> A user reports: "My long-distance SSH session freezes for 200 ms every 5 seconds, then resumes at the same speed. The `ping` is fine, the bandwidth is fine, but the latency spikes on a regular interval." A `tcpdump` shows the TCP connection's CWND is being cut every 5 seconds. The cause is **ECN marking without ECN negotiation**: the user's network egress router is running `tc qdisc add dev eth0 root codel` (CoDel AQM, RFC 8289) with ECN enabled, and the user's SSH client's TCP socket has `IPV4_TOS=0` (no ECN negotiation). The router marks the packet's ECN field to `11` (Congestion Experienced, CE), the receiver echoes `ECE` in the TCP header, and the sender halves the congestion window. The issue is the *sender* (SSH client) does not have ECN negotiated — the socket was opened without `IPV4_ECN` enabled, so the ECE flag in incoming packets is ignored. But the *router* does not know that, marks the packet, the receiver reflects the CE in the ECE flag, the *sender's* kernel still processes ECE because the kernel-level ECN is on by default. The 5-second cadence matches CoDel's `interval` parameter (default 100 ms * 8 = 800 ms in some implementations, or 5 s in the older `codel` parameters). The fix is to (a) disable ECN on the egress (`tc qdisc replace dev eth0 root codel ecn`), (b) negotiate ECN at the socket level so the sender knows the receiver understands the ECN bits, or (c) use `noecn` on the SSH socket via `sysctl net.ipv4.tcp_ecn=1` (negotiate when possible) and `net.ipv4.tcp_ecn=2` (always ECN).

**Type:** Lab
**Languages:** Python, shell, tc, netem
**Prerequisites:** Phase 11 ECN (RFC 3168), Phase 11 AQM and CoDel (RFC 8289), RED queue management (RFC 2309)
**Time:** ~100 minutes

## Learning Objectives

- Diagnose a network that exhibits periodic latency spikes caused by ECN marking that the sender does not have negotiated: read `tc -s qdisc`, find the ECN-marked packets, and trace the ECE flag through to the sender's congestion window.
- Explain the ECN bits in the IPv4 TOS / IPv6 Traffic Class field: `00` (Not-ECT, not ECN-capable), `01` (ECT(1)), `10` (ECT(0)), `11` (CE, Congestion Experienced).
- Read the TCP ECN flags: ECE (Echo Congestion Experienced), CWR (Congestion Window Reduced), and NS (Nonce Sum) in the reserved bits of the TCP header.
- Distinguish three failure modes: (a) ECN blackhole (intermediate router strips ECN, the receiver never sees the CE), (b) ECN mis-marking (a router marks CE for non-congested traffic), (c) ECN without negotiation (sender processes CE without negotiating, the CWND is cut unnecessarily).
- Use `tc qdisc add dev eth0 root codel limit 1000 target 5ms interval 100ms ecn` to configure a CoDel queue with ECN marking, and `tc -s qdisc show dev eth0` to read the mark statistics.
- Build a Python simulator that walks the ECN state machine (`ECN-enabled` → `ECN-capable` → `Congestion Experienced`) and prints the verdict that matches a production `tc -s qdisc` output.

## The Problem

The on-call SRE for a hosting company gets a ticket: "Bulk TCP throughput on a trans-Pacific link is 50% of what we expect, and the latency is spiking every 5 seconds. UDP and ICMP are fine." The link is 1 Gbps, RTT is 80 ms, the BDP is 10 MB, and the user is pushing a 200 MB file with `scp`. The user expects ~125 MB/s; they get ~60 MB/s with periodic stalls.

The cause is CoDel with ECN enabled, applied to the link. CoDel (RFC 8289) is a "controlled delay" AQM that aims to keep the queue-sojourn time below a target (default 5 ms). When the sojourn time exceeds the target for longer than the `interval` (default 100 ms), CoDel starts marking or dropping packets. The default Linux `codel` qdisc uses the older `codel_init_defaults`: `target=5ms`, `interval=100ms`. ECN marking is enabled by `ecn` parameter; without it, CoDel drops packets instead of marking them.

The user is at the receiver's side, the SSH client is on the receiver, and the server is on the sender's side. The link is from the receiver to the sender (the bulk of the `scp` traffic is server-to-client). The receiver's egress queue runs `codel` with `ecn`. CoDel marks the packet CE. The receiver's TCP stack reflects the CE in the ECE flag of the next outgoing ACK. The server's TCP stack sees the ECE flag and halves its CWND. After 5 seconds (the typical re-arming time of CoDel), the next packet is marked, the CWND is halved again, and the throughput collapses.

The diagnostic move is `tc -s qdisc show dev eth0` on the receiver's egress. The output shows:

```
qdisc codel 1: root limit 1000p target 5.0ms interval 100ms ecn
 Sent 1840000000 bytes 1500000 pkt (dropped 0, overlimits 0, ecn_mark 12000)
 ...
```

`ecn_mark 12000` confirms that 12,000 packets have been marked. The CWND halving is the consequence. The fix is `tc qdisc replace dev eth0 root codel limit 1000 target 5ms interval 100ms` (no `ecn` parameter — drop instead of mark), or `sysctl net.ipv4.tcp_ecn=2` on the receiver to always use ECN and let the sender know.

## The Concept

### ECN field and TCP flags

ECN (Explicit Congestion Notification, RFC 3168) uses the lower 2 bits of the IPv4 TOS / IPv6 Traffic Class field. The four values:

| Encoding | Name | Meaning |
|---|---|---|
| `00` | Not-ECT | The packet is not ECN-capable |
| `01` | ECT(1) | The packet is ECN-capable, transport 1 |
| `10` | ECT(0) | The packet is ECN-capable, transport 0 |
| `11` | CE | Congestion Experienced; the receiver MUST echo this in the ECE flag |

A router that experiences congestion can either drop the packet or set the ECN field to CE (if the packet is ECN-capable, i.e., ECT(0) or ECT(1)). The receiver, on seeing CE in an incoming packet, sets the ECE flag in the next outgoing ACK. The sender, on seeing ECE, halves its congestion window and sets the CWR flag in the next data packet.

The TCP ECN flags are 3 bits in the reserved area of byte 13 of the TCP header (the byte that also holds the URG, ACK, PSH, RST, SYN, FIN flags). Bits 8-6 (counting from MSB) are CWR, ECE, URG.

### CoDel and the ECN parameter

CoDel (RFC 8289) is a "no-knobs" AQM that aims to keep the queue-sojourn time below a target. The parameters:

- `target`: the acceptable sojourn time (default 5 ms)
- `interval`: the time over which the sojourn time can exceed the target before CoDel reacts (default 100 ms)
- `limit`: the queue size in packets (default 1000)
- `ecn`: if set, CoDel marks CE instead of dropping (default off)

The key idea: CoDel is "standing queue" detector. If a queue builds up, the sojourn time rises; if the rise persists, CoDel reacts. The default 5 ms target is for a 1 Gbps link with a typical 50 µs serialization time per 64-byte packet. For a 10 Gbps link, the target should be lower (1 ms).

### The ECN negotiation in TCP

The TCP ECN negotiation (RFC 3168) uses two flags in the SYN: ECE and CWR. A sender that wants to use ECN sets both flags in the SYN; a receiver that accepts sets ECE in the SYN-ACK. After the handshake, the ECN field of every data packet is ECT(0) (or ECT(1)), and ECE is used to signal CE back to the sender.

If the SYN does not negotiate ECN, the receiver does not set ECE in the SYN-ACK, and the sender does not set ECT(0) on data packets. The router cannot mark CE (because the packet is Not-ECT). This is the safe path.

A failure mode: a legacy middlebox (Cisco, Juniper, etc.) strips the ECE flag from the SYN-ACK, so the sender thinks the receiver does not support ECN. But the middlebox passes the rest of the ECN bits through. The result is an "ECN blackhole": the sender never knows the receiver understood ECN, but the receiver thinks it is ECN-capable. RFC 5562 documents this and recommends that the receiver test the ECN bits and disable ECN if the SYN-ACK does not have ECE set.

### `tcp_ecn` sysctl

Linux has three `net.ipv4.tcp_ecn` values:

- `0`: ECN disabled; never negotiate, never mark
- `1`: ECN enabled; negotiate when the peer supports it (default in modern kernels)
- `2`: ECN enabled; always use ECN (server-only, when the operator is sure the path supports it)

The right value depends on the path. For a trans-Pacific link with a known CoDel queue at the egress, `tcp_ecn=1` (negotiate) is safe. For a path with legacy middleboxes, `tcp_ecn=0` is safer.

### Reading `tc -s qdisc` output

`tc -s qdisc show dev eth0` prints per-qdisc statistics. For CoDel:

```
qdisc codel 1: root refcnt 2 limit 1000p target 5.0ms interval 100ms ecn
 Sent 1872345678 bytes 1500223 pkt (dropped 0, overlimits 0, ecn_mark 12045)
 backlog 0b 0p requeues 0
  count 12045 lastcount 1 ldelay 4ms drop_next 0us
  maxpacket 1542 ecn_mark 12045
```

The fields to read:
- `dropped`: packets dropped (CoDel drop, not ECN mark)
- `overlimits`: packets over the limit (queue size exceeded)
- `ecn_mark`: packets marked with CE
- `ldelay`: the current sojourn time
- `maxpacket`: the largest packet seen (informational)

`ecn_mark > 0` means CoDel is marking; the next step is to decide whether the sender is processing ECE.

### How the simulator models this

`code/main.py` walks the ECN state machine for a configurable scenario (`--scenario ecn_marked`, `--scenario ecn_blackhole`, `--scenario ecn_disabled`, `--scenario no_ecn_negotiated`). The simulator prints the per-packet ECN field, the TCP flags, and the verdict that matches the production `tc -s qdisc` output.

## Build It

1. **Set up a CoDel queue with ECN.** `tc qdisc add dev eth0 root codel limit 1000 target 5ms interval 100ms ecn`.
2. **Generate traffic.** `iperf3 -c <server>` for 60 seconds. Capture with `tcpdump -i eth0 -n -w ecn.pcap`.
3. **Read the qdisc stats.** `tc -s qdisc show dev eth0`. Confirm `ecn_mark` is non-zero.
4. **Read the ECE flags.** `tcpdump -r ecn.pcap -n 'tcp[tcpflags] & tcp-ece != 0'`.
5. **Apply the fix.** `tc qdisc replace dev eth0 root codel limit 1000 target 5ms interval 100ms` (no `ecn`). Re-test. The `ecn_mark` should be 0; drops will appear instead.
6. **Run the simulator.** `python3 code/main.py --scenario ecn_marked` should print the matching state machine.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read ECN marks | `tc -s qdisc` `ecn_mark` counter | Non-zero = CoDel is marking; throughput may collapse |
| Read ECE flags | `tcpdump 'tcp[tcpflags] & tcp-ece != 0'` | ACKs from receiver to sender carrying the CE echo |
| Confirm CWR | `tcpdump 'tcp[tcpflags] & tcp-cwr != 0'` | Data packets from sender acknowledging the CWND reduction |
| Read CWND | `ss -ti` for the socket | CWND halved on each ECN feedback; recovery via slow start |
| Verify the fix | Re-run iperf3 with `ecn` removed | No ECN marks; CoDel drops; the sender sees loss and reacts |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **CoDel/ECN interaction runbook** with the diagnostic commands, the `tc` qdisc to apply, and the sysctl recommendations.
- A **before/after capture** of `tc -s qdisc` and `iperf3` throughput showing the ECN marking's effect.

Start from `outputs/prompt-ecn-marking-aqm-codel-congestion.md`.

## Exercises

1. A `tc -s qdisc` output shows `ecn_mark 12045` and `dropped 0`. The bulk TCP throughput is 50% of expected. Compute the *expected* ECN feedback rate per second if the link is 1 Gbps with 1500-byte packets.
2. The TCP ECN flag byte (byte 13) has the URG/ACK/PSH/RST/SYN/FIN in the lower 6 bits, and CWR/ECE in bits 6/7. What is the byte value of a SYN with ECE and CWR set?
3. A sender has `net.ipv4.tcp_ecn=0`. A router on the path marks CE. What does the sender do? Why is this safe?
4. CoDel's `target=5ms` is appropriate for a 1 Gbps link. For a 10 Gbps link, what should the target be? For a 100 Mbps link?
5. A receiver's ECN field is `01` (ECT(1)) and the router marks it to `11` (CE). The receiver echoes ECE in the next ACK. The sender halves its CWND. The sender's next data packet has CWR=1. What does the receiver do with the CWR?
6. The Linux `tcp_ecn=2` value means "always ECN, never negotiate." Why is this safe only for servers? What is the risk?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ECN | "Explicit congestion" | RFC 3168: 2-bit field in TOS/TC; allows routers to mark congestion instead of dropping |
| CE / ECT(0) / ECT(1) / Not-ECT | "The four values" | The four states of the ECN field: 11 / 10 / 01 / 00 |
| ECE / CWR | "The TCP flags" | RFC 3168: ECE echoes CE back to the sender; CWR confirms the CWND was reduced |
| CoDel | "Controlled delay" | RFC 8289: AQM that targets a sojourn time, not a queue size |
| ECN blackhole | "Middlebox strips ECE" | RFC 5562: legacy middlebox strips the ECE flag, breaking ECN negotiation |
| `tcp_ecn` sysctl | "ECN mode" | Linux: 0 = off, 1 = negotiate, 2 = always ECN |
| `ecn_mark` | "How many CE marks" | The `tc -s qdisc` counter for CoDel's ECN marks |
| `target` / `interval` | "CoDel parameters" | The two CoDel knobs: target sojourn time and the time it can be exceeded |

## Further Reading

- RFC 3168 — The Addition of Explicit Congestion Notification (ECN) to IP
- RFC 8289 — Controlled Delay (CoDel)
- RFC 2309 — Recommendations on Queue Management and Congestion Avoidance in the Internet (RED)
- RFC 5562 — ECN Blackhole Problem in the Internet
- RFC 7560 — Problem Statement and Requirements for Increased Accuracy in Explicit Congestion Notification Feedback
- `tc-codel(8)`, `tc(8)`, `tcp(7)` man pages
- `ss(8)` — `-i` flag for TCP internal state including CWND and ECN
- `tcpdump(8)` — `tcp[tcpflags] & tcp-ece` and `tcp[tcpflags] & tcp-cwr` byte-offset filters
