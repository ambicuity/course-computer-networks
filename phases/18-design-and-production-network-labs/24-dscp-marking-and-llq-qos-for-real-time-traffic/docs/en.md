# DSCP marking verification and LLQ QoS for real-time traffic

> Your CEO is on a Zoom call at 09:03 when finance kicks off a 200-MB Snowflake export over the same MPLS link. The call drops, the audio cuts out for 4 seconds, and the CFO's slides freeze mid-slide. Your SLA commits to 200 ms one-way delay and 30 ms jitter for voice traffic — and you are now at 410 ms p99 with 92 ms jitter. The fix is not a bigger pipe; the fix is **Low-Latency Queuing (LLQ)** with **DSCP EF (46)** marking and a strict-priority queue capped at 33% of the link bandwidth. RFC 8628 (the LLQ PHB) plus the classic Cisco/IETF recommendation: a **priority queue** with a policer, plus 4 class-based queues for everything else. This lesson builds a 3-node topology (`phone`, `router`, `gateway`), wires up Linux `tc` with `prio` + `htb` qdiscs, marks the voice flow with `iptables`/`tc` DSCP bits (RFC 2474), and validates end-to-end with `iperf3` background traffic and a `tcpdump` showing the EF-marked packets traversing the priority queue. The companion `code/main.py` is a DSCP / PHB calculator: given a class name, it returns the 6-bit DSCP value, the queue number, the bandwidth cap, and the queueing discipline — exactly the mapping a carrier switches on every packet.

**Type:** Lab
**Languages:** Python, shell, tcpdump, iperf3
**Prerequisites:** Phase 09 IPv4 basics, exposure to `tc qdisc`, comfort running `iperf3`
**Time:** ~75 minutes

## Learning Objectives

- Build a 3-node lab (`phone`, `router`, `gateway`) using Linux network namespaces and `veth` pairs; configure `ip link` with a `tc` root `prio` qdisc and an `htb` class hierarchy underneath.
- Mark voice traffic with `iptables -t mangle -A POSTROUTING -p udp --dport 5004 -j DSCP --set-dscp 46` and verify the byte on the wire with `tcpdump -i veth-r-g -vv -n` reading the IP ToS byte (RFC 791 §3.1, RFC 2474).
- Reproduce the "voice + bulk at 100 Mbps" congestion scenario, then enable LLQ with a 33% bandwidth cap (`rate 33mbit ceil 33mbit`) on the EF queue and re-measure to confirm voice recovers while bulk is capped.
- Use `code/main.py` to translate 11 canonical DSCP classes (BE, AF11–AF43, EF, CS6, CS7) into PHB parameters (queue index, bandwidth cap, precedence, drop probability).
- Explain the **3-bit IP precedence** field (RFC 791) versus the **6-bit DSCP** field (RFC 2474) and why EF (`101110₂`) is incompatible with old precedence-only routers.
- Validate end-to-end with `iperf3 -u -b 8M -l 200 -t 30` (the standard RTP packet size for G.711) plus `tcpdump` capturing the DSCP byte on the egress side.

## The Problem

A flat best-effort network carries voice, video, and bulk data with the same single FIFO queue. Bulk traffic (full-speed TCP, large HTTP downloads) starves voice traffic because TCP keeps the link saturated and voice UDP packets wait behind the bulk queue — and the human ear notices 150 ms of one-way delay. Adding bandwidth does not fix this: a 1 Gbps link with 900 Mbps of bulk is still the same one-giant-FIFO problem.

The fix is **differentiated service**: mark the voice traffic with DSCP EF (Expedited Forwarding, RFC 3246) at the sender, classify it on every router hop, and place it in a strict-priority queue (LLQ) that is policed to a fraction of the link — typically 33% so the priority queue cannot starve everything else. Bulk traffic is best-effort, video is AF41 (Assured Forwarding class 4, drop precedence 1), and management is CS6.

The trap is that DSCP marking is invisible without instrumentation. Routers re-mark or honor the existing DSCP, and the only way to confirm is `tcpdump -v` reading the IP ToS byte at every hop. Many deployments enable QoS but never verify the marking on the wire — and find out at the next incident.

## The Concept

### IP precedence (RFC 791) vs DSCP (RFC 2474)

The IPv4 ToS byte is 8 bits:

```
 0   1   2   3   4   5   6   7
+---+---+---+---+---+---+---+---+
|   Precedence  |     ToS     | 0|
+---+---+---+---+---+---+---+---+
   RFC 791         RFC 1349
```

RFC 791 defined a 3-bit precedence field (0=routine, 7=network control) and a 4-bit ToS field (delay, throughput, reliability, cost). RFC 1349 revised the ToS bits. RFC 2474 redefined the byte as a 6-bit **DSCP** with 2 unused bits (the CU — currently used for ECN, RFC 3168):

```
 0   1   2   3   4   5   6   7
+---+---+---+---+---+---+---+---+
|         DSCP          |  CU    |
+---+---+---+---+---+---+---+---+
       6 bits              2 bits
```

The 6-bit DSCP gives 64 codepoints. Standardized ones (RFC 8628 / RFC 3246 / RFC 2597):

| DSCP | Binary | Name | PHB |
|---|---|---|---|
| 0 | 000000 | BE (Best Effort) | DF |
| 10 | 001010 | AF11 | AF class 1, low drop |
| 12 | 001100 | AF12 | AF class 1, med drop |
| 14 | 001110 | AF13 | AF class 1, high drop |
| 18 | 010010 | AF21 | AF class 2, low drop |
| 26 | 011010 | AF31 | AF class 3, low drop |
| 34 | 100010 | AF41 | AF class 4, low drop (video) |
| 46 | 101110 | EF | Expedited Forwarding (voice) |
| 48 | 110000 | CS6 | Internetwork control (routing) |
| 56 | 111000 | CS7 | Network control (keepalive) |

EF (`101110₂`) is the PHB RFC 3246 codifies for "voice packets should be delivered with the lowest possible delay, jitter, and loss". Routers honor EF with a priority queue.

### LLQ is `prio` + `htb` + a policer

LLQ is **not** a separate qdisc — it is the **combination** of a `prio` (priority) qdisc and an `htb` (Hierarchical Token Bucket, RFC 3290) class with a **bandwidth ceiling**. The `prio` qdisc on Linux separates traffic into `bands 0..3` by ToS / DSCP bit; `band 0` is drained before anything else. A naive `prio` queue would starve everything else, so LLQ adds an `htb` `ceil` rate on the EF queue (RFC 8628 says: "the priority queue should be policed to a percentage of the link bandwidth, typically 33%"). This prevents EF traffic from monopolizing the link.

The Linux commands look like:

```bash
tc qdisc add dev eth0 root handle 1:0 prio bands 4
tc qdisc add dev eth0 parent 1:1 handle 10:0 htb default 30
tc class add dev eth0 parent 10:0 classid 10:1 htb rate 100mbit ceil 100mbit
tc class add dev eth0 parent 10:1 classid 10:10 htb rate 33mbit ceil 33mbit   # EF
tc class add dev eth0 parent 10:1 classid 10:20 htb rate 33mbit ceil 100mbit  # AF41
tc class add dev eth0 parent 10:1 classid 10:30 htb rate 33mbit ceil 100mbit  # BE
tc filter add dev eth0 parent 10:0 protocol ip u32 match ip tos 0xb8 0xfc \
    flowid 10:10   # EF -> priority
```

The filter `match ip tos 0xb8 0xfc` decodes as `tos value 0xb8 = 10111000₂ = DSCP 46 (EF)`, mask `0xfc = 11111100₂` (mask off the 2 CU bits). This is exactly the DSCP byte the `iptables -j DSCP` target sets.

### Why ECN rides on the same 2 bits

RFC 3168 repurposes the low 2 bits of the ToS byte as the **Explicit Congestion Notification** field: `00` = no ECN, `10`/`01` = ECN-capable transport (ECT), `11` = congestion experienced (CE). Modern TCP (CUBIC, BBR) honor ECN by reducing the congestion window instead of dropping — the same ToS byte carries both DSCP and ECN. A router marking ECN CE on EF packets is bad — voice UDP has no congestion control to honor it.

### Why iperf3 + tcpdump together

`iperf3 -u -b 8M` saturates the link with UDP at a configurable rate; `tcpdump -v` reads the ToS byte off each packet. The combination proves three things at once: (1) the marking reached the egress interface, (2) the EF queue is being drained (latency under load stays < 50 ms), (3) the bulk queue is degraded but not starved (TCP throughput drops to ~67 Mbps when EF takes 33 Mbps).

## Build It

### Step 1: Build the 3-node lab

```bash
ip netns add phone
ip netns add router
ip netns add gateway

ip link add veth-p-r type veth peer name veth-r-p
ip link set veth-p-r netns phone
ip link set veth-r-p netns router
ip netns exec phone ip addr add 10.50.0.1/24 dev veth-p-r
ip netns exec phone ip link set veth-p-r up
ip netns exec router ip addr add 10.50.0.2/24 dev veth-r-p
ip netns exec router ip link set veth-r-p up

ip link add veth-r-g type veth peer name veth-g-r
ip link set veth-r-g netns router
ip link set veth-g-r netns gateway
ip netns exec router ip addr add 10.50.1.1/24 dev veth-r-g
ip netns exec router ip link set veth-r-g up
ip netns exec gateway ip addr add 10.50.1.2/24 dev veth-g-r
ip netns exec gateway ip link set veth-g-r up

# throttle the egress side to 100 Mbps so we can saturate it
ip netns exec router ip link set veth-r-g down
ip netns exec router ip link set veth-r-g 100Mbps
ip netns exec router ip link set veth-r-g up
ip netns exec router sysctl -w net.ipv4.ip_forward=1
```

### Step 2: Configure LLQ on the egress interface

```bash
ip netns exec router bash - <<'EOF'
tc qdisc add dev veth-r-g root handle 1:0 prio bands 4
tc qdisc add dev veth-r-g parent 1:1 handle 10:0 htb default 30
tc class add dev veth-r-g parent 10:0 classid 10:1 htb rate 100mbit ceil 100mbit
tc class add dev veth-r-g parent 10:1 classid 10:10 htb rate 33mbit ceil 33mbit
tc class add dev veth-r-g parent 10:1 classid 10:20 htb rate 33mbit ceil 100mbit
tc class add dev veth-r-g parent 10:1 classid 10:30 htb rate 33mbit ceil 100mbit
tc filter add dev veth-r-g parent 10:0 protocol ip u32 \
    match ip tos 0xb8 0xfc flowid 10:10
tc filter add dev veth-r-g parent 10:0 protocol ip u32 \
    match ip tos 0x88 0xfc flowid 10:20
EOF
```

### Step 3: Mark voice traffic on the phone

```bash
ip netns exec phone iptables -t mangle -A POSTROUTING \
    -p udp --dport 5004 -j DSCP --set-dscp 46
```

### Step 4: Run `code/main.py` to verify DSCP values

```bash
python3 code/main.py
```

Expected output (truncated):

```
=== DSCP / PHB CALCULATOR ===
  class BE    dscp=0x00  tos=0x00  queue=3  ceil=100%  drop=tail
  class AF11  dscp=0x0a  tos=0x20  queue=2  ceil=100%  drop=precedence 1
  class AF41  dscp=0x22  tos=0x88  queue=2  ceil=100%  drop=precedence 1
  class EF    dscp=0x2e  tos=0xb8  queue=0  ceil=33%   drop=police 33mbit
  class CS6   dscp=0x30  tos=0xc0  queue=1  ceil=100%  drop=precedence 0
  class CS7   dscp=0x38  tos=0xe0  queue=0  ceil=100%  drop=precedence 0
```

### Step 5: Saturate with bulk and verify EF stays low-latency

```bash
# background bulk
ip netns exec phone iperf3 -c 10.50.1.2 -u -b 90M -t 30 -i 1 > /tmp/bulk.log &

# voice traffic with DSCP EF
ip netns exec phone iperf3 -c 10.50.1.2 -u -b 8M -l 200 -t 30 -p 5004 \
    > /tmp/voice.log &
sleep 5
ip netns exec router tcpdump -i veth-r-g -nn -c 30 -v 'udp port 5004' 2>/dev/null | grep tos
```

You should see `tos 0xb8` (DSCP 46 EF) on every voice packet. Voice one-way delay should stay < 50 ms because EF takes priority; bulk throughput will cap at ~67 Mbps (100 - 33 reserved for EF).

### Step 6: Disable QoS and re-measure to see the failure mode

```bash
ip netns exec router tc qdisc del dev veth-r-g root
ip netns exec phone iperf3 -c 10.50.1.2 -u -b 8M -l 200 -t 30 -p 5004 -J
```

Voice one-way delay will jump to 300+ ms — confirming that the bulk queue is starving the voice flow in a flat FIFO, and the LLQ is what protected it.

## Use It

| Capability | `code/main.py` (PHB calc) | `tc qdisc` / `tc filter` | Cisco IOS `policy-map` | Nokia SR OS QoS |
|---|---|---|---|---|
| DSCP-to-queue map | yes | manual filter | yes | yes |
| Strict priority queue | yes (LLQ on EF) | yes (`prio` band 0) | yes (`priority` class) | yes (`sap-ingress` qos) |
| Bandwidth ceiling on priority | yes (`ceil 33%`) | yes (`htb ceil`) | yes (`police cir pct`) | yes (`policer`) |
| DiffServ marking at sender | n/a (offline) | yes (`iptables -j DSCP`) | yes (`set dscp`) | yes (`qos mark`) |
| Per-flow policer | n/a | yes (`u32 match`) | yes (`police`) | yes |
| Weighted fair queuing | n/a | yes (`htb` weights) | yes (`bandwidth %`) | yes |
| Re-marking on ingress | n/a | yes (`dscp rewrite`) | yes (`set dscp`) | yes |
| ECN-aware | n/a | yes (`ecn` on RED) | partial | yes |

## Ship It

The reusable artifact is the DSCP/PHB table in `code/main.py`. Drop it into a config template generator (Ansible, Jinja, Go template) and you have a single source of truth for "what DSCP value should land in which queue". Production networks treat this table as the contract between the edge marking policy and the core queueing policy — a single mismatch (e.g., edge marks EF but core queues it as AF) silently breaks voice.

## Exercises

1. **Mark at the edge only.** Strip the marking on the phone and add it on the router's ingress (`iptables -t mangle -A PREROUTING`). Confirm DSCP still arrives at the gateway.
2. **Add CS7 for routing.** Run `ospfd` between `router` and `gateway`, mark OSPF packets as CS7 (`iptables -p ospf -j DSCP --set-dscp 48`), and verify CS7 also lands in priority queue 0.
3. **Verify AF41 vs AF42.** Mark two video streams with DSCP 34 and 36, run them at 40 Mbps each, and watch the precedence-based drop: AF42 (drop precedence higher) loses packets first under congestion.
4. **Replace `prio` with `fq_codel`.** Swap the qdisc for `fq_codel` and observe: with no QoS configuration, modern `fq_codel` achieves nearly the same voice latency as LLQ — proof that end-to-end queue management is more important than DSCP for many flows.
5. **ECN-CE for non-EF only.** Add a rule that marks ECN CE on AF41 congestion, and confirm that EF never gets CE marked (voice UDP has no ECN response).
6. **Tune the EF ceiling.** Set `ceil` to 10% and re-run; voice quality is unchanged but bulk gets more bandwidth. Find the knee point where voice degrades.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DSCP | "The priority field" | 6-bit field in the IP ToS byte (RFC 2474) — the modern replacement for the 3-bit IP precedence (RFC 791). |
| EF | "Voice priority" | Expedited Forwarding, DSCP 46 (`101110₂`), RFC 3246 — the standardized PHB for low-delay/jitter/loss traffic. |
| AFxy | "Assured Forwarding" | DSCP class (1–4) and drop precedence (1–3), RFC 2597 — class for video and business-critical traffic. |
| LLQ | "Priority queue with a cap" | Low-Latency Queuing (RFC 8628) — a strict-priority queue policed to a fixed % of link bandwidth (33% typical). |
| `tc qdisc prio` | "Multiple queues" | Linux qdisc that separates packets into bands (0..3) by ToS bits; band 0 is drained first. |
| `htb` | "Hierarchical bandwidth" | Hierarchical Token Bucket (RFC 3290) — Linux qdisc that lets you put rate/ceil caps on each class. |
| ECN | "Congestion without drops" | Explicit Congestion Notification (RFC 3168) — rides on the low 2 bits of ToS, set by routers, honored by TCP. |
| PHB | "What a router does" | Per-Hop Behavior — the forwarding treatment a DSCP class receives on each router (RFC 2474 §3). |

## Further Reading

- [RFC 2474](https://www.rfc-editor.org/rfc/rfc2474) — Definition of the Differentiated Services Field (DSCP) in IPv4/IPv6
- [RFC 2597](https://www.rfc-editor.org/rfc/rfc2597) — Assured Forwarding PHB Group (AFxy)
- [RFC 3246](https://www.rfc-editor.org/rfc/rfc3246) — An Expedited Forwarding PHB (EF)
- [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628) — A Model of Resource Consumption in a Low-Latency Queue (LLQ)
- [RFC 3168](https://www.rfc-editor.org/rfc/rfc3168) — The Addition of Explicit Congestion Notification (ECN) to IP
- [RFC 3290](https://www.rfc-editor.org/rfc/rfc3290) — An Informal Management Model for Diffserv Routers (HTB design)
- [`tc(8)` manpage / `tc-prio(8)`](https://man7.org/linux/man-pages/man8/tc.8.html) — Linux traffic control reference
- [`iptables-extensions(8)`](https://man7.org/linux/man-pages/man8/iptables-extensions.8.html) — `DSCP` and `TOS` match/target
- Clark, "Adding Service Discrimination to the Internet" (MIT, 1995) — the original Differentiated Services paper