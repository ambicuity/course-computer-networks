# VRF/Network Namespace Blackhole and Asymmetric Routing

> A multi-tenant SaaS company runs each customer in its own Linux network namespace (a lightweight VRF). A customer's pod is on `vrf-cust-a`, with a veth pair to the host's `br-cust-a` bridge, and the host's `eth0` carries the customer's traffic to the public IP. A user reports: "Connections from the public internet to my service work for the first 60 seconds, then stall for 5 minutes, then resume. `tcpdump` on the host shows the SYN, the SYN-ACK, the first data packet, then nothing — the conntrack table is full and the reply packets are dropped." The root cause is **asymmetric routing with conntrack**: the customer's incoming traffic arrives on `eth0` (source IP `198.51.100.42`), the conntrack entry is created, the packet is DNAT'd to the customer's pod, the pod replies, but the reply goes out a *different* interface — the bridge `br-cust-a` (because the pod's default route points that way), then back through the host's routing table. The host's conntrack sees the reply packet on a different interface than the original, marks it INVALID, and drops it. The fix is to either (a) use a VRF (in Linux: `ip vrf` or network namespace) so the customer has its own routing table and the reply goes out the same interface, or (b) disable conntrack's interface match with `iptables -t raw -A PREROUTING -j NOTRACK` for the affected flow, or (c) configure the host's routing table so the reply to `198.51.100.42` is forced out `eth0` (a `policy routing` rule with `ip rule`).

**Type:** Lab
**Languages:** Python, shell, iproute2
**Prerequisites:** Phase 07 routing tables and longest-prefix match, Phase 16 VRF and network namespaces, iproute2 `ip netns`, `ip vrf`, `ip rule`
**Time:** ~100 minutes

## Learning Objectives

- Diagnose a connection that is established but stalls after the first data exchange, with conntrack marking the reply as INVALID because the reply's egress interface differs from the ingress interface.
- Distinguish three failure modes: (a) VRF / namespace mismatch (the reply leaves a different routing table), (b) conntrack interface-mismatch drop, (c) policy routing rule missing.
- Use `ip netns exec <ns> ss -ant` and `conntrack -L` to read the conntrack state and identify INVALID entries.
- Use `ip rule` and `ip route show table all` to read the policy routing table, and identify which routing table a given source IP is using.
- Construct a `tc` filter or `nft` rule to bypass conntrack for a specific flow: `iptables -t raw -A PREROUTING -s 198.51.100.42 -j NOTRACK` (or `nft add rule ip raw prerouting ip saddr 198.51.100.42 notrack`).
- Build a Python simulator that walks the conntrack state machine (NEW → ESTABLISHED → INVALID) and prints the verdict for a synthetic asymmetric flow.

## The Problem

The on-call SRE for a multi-tenant SaaS company gets a ticket: "Customer X's service is intermittently unreachable from the public internet. It works for 60 seconds, then stalls, then works again, then stalls." The customer's pod runs in a Linux network namespace, the host's `eth0` carries the public-facing traffic, and a bridge `br-cust-a` connects the namespace to the host.

The customer's pod has a default route via `192.168.100.1` (the bridge's host-side IP). The host has a default route via `203.0.113.1` (the upstream gateway) on `eth0`. The host's conntrack table is shared across all flows (no namespace isolation at the conntrack level). When the public client sends a SYN, it arrives on `eth0`, the conntrack creates a NEW entry, the DNAT rule (e.g., `iptables -t nat -A PREROUTING -d 198.51.100.42 -j DNAT --to-destination 192.168.100.42`) rewrites the destination, the packet is delivered to the pod, the pod replies, the reply leaves via `br-cust-a` and `eth0` (because the pod's default route points that way).

But the host's conntrack, when it sees the reply on the `br-cust-a` interface, marks the entry INVALID because the original packet arrived on `eth0`. The reply is dropped. The client retransmits the SYN, the conntrack updates, the entry is NEW again, the connection works for a few seconds, and then stalls again.

The diagnostic is `conntrack -L | grep INVALID`. The output shows the customer's source IP entries with `[INVALID]`. The fix is to put the customer in a VRF, or to bypass conntrack, or to add a policy routing rule that forces the reply out the same interface.

## The Concept

### Linux network namespaces as VRF

A network namespace is an isolated kernel networking stack: its own interfaces, routing table, ARP cache, and iptables rules. The `ip netns add <name>` command creates a new namespace. The `ip netns exec <name> <cmd>` command runs `<cmd>` inside the namespace. A veth pair connects the namespace to the host; one end is in the namespace, the other is in the host's default namespace.

A VRF (Virtual Routing and Forwarding) is a similar concept in network hardware, and Linux supports it via `ip vrf` (kernel 4.4+). A VRF is a lightweight namespace that shares most of the kernel's network stack but has its own routing table. The `ip vrf exec <vrf> <cmd>` runs `<cmd>` with the VRF's routing table.

The conntrack table is *shared* across namespaces by default. This is the source of the bug: a flow that crosses a namespace boundary can have its reply dropped because the conntrack sees the reply on a different interface.

### Conntrack states and the INVALID transition

Linux's conntrack (the `nf_conntrack` kernel module) tracks the state of every flow. The states are:

- **NEW**: a packet matching no existing entry
- **ESTABLISHED**: a packet that is part of a flow that has seen traffic in both directions
- **RELATED**: a packet related to an existing flow (e.g., an ICMP error that matches a TCP flow)
- **INVALID**: a packet that does not match the expected direction or interface of an existing flow

The INVALID transition is triggered by the conntrack's `nf_conntrack_in` hook. The default behavior is to drop INVALID packets. The conntrack checks the reply's interface against the original's interface (a "reverse-path filter" of sorts), and if they differ, the reply is INVALID.

The conntrack state machine does *not* check the routing table — it checks the kernel's view of where the packet was received and where the reply is being sent. If the reply is leaving a different interface than the one the original arrived on, conntrack marks it INVALID.

### Why this happens in practice

The classic case is a multi-tenant host: the host has multiple bridges (one per customer), each bridge is in its own namespace (or VRF), and the host's `eth0` is the public-facing interface. A customer pod's reply is sent via the customer's bridge, and the host's routing table sends the reply out `eth0`. The conntrack, however, remembers the *original* interface as `eth0`, so the reply's interface (also `eth0` from the host's perspective, but the bridge is the namespace's interface) does not match.

The fix is to either:

1. Put each customer in its own VRF, with its own routing table. The reply from the customer's pod is then routed via the customer's VRF, and the conntrack entry's interface is consistent.
2. Bypass conntrack for the flow: `iptables -t raw -A PREROUTING -s <source> -j NOTRACK`. The packets are then routed without stateful inspection; the connection works but is not protected by conntrack's anti-spoofing.
3. Add a policy routing rule that forces the reply to leave `eth0` regardless of the namespace: `ip rule add from 192.168.100.42 lookup 100` and `ip route add default via 203.0.113.1 dev eth0 table 100`.

### `ip rule` and policy routing

`ip rule` lists the policy routing rules. The default table is `main` (table 254). Additional tables can be created and assigned to specific source IPs, interfaces, or TOS. The kernel walks the rules in order of priority and uses the first matching table.

The classic setup for a multi-tenant host:

```
ip rule add from 192.168.100.0/24 lookup 100 prio 100
ip route add default via 203.0.113.1 dev eth0 table 100
```

The `from 192.168.100.0/24` rule sends traffic from the customer's pod to table 100, which has a default route via `eth0`. The reply is then routed via `eth0`, and the conntrack entry's interface is consistent.

### `conntrack` command and INVALID detection

`conntrack -L` lists the conntrack table. The output includes the state of each entry:

```
tcp  6  120 ESTABLISHED src=198.51.100.42 dst=203.0.113.10 sport=54321 dport=443 ...
```

To filter for INVALID entries: `conntrack -L | grep INVALID`. The `-E` flag shows the events in real time; the `-S` flag shows statistics.

### How the simulator models this

`code/main.py` walks the conntrack state machine for a configurable scenario (`--scenario asymmetric`, `--scenario vrf`, `--scenario notrack`, `--scenario policy_routing`). The simulator prints the per-packet interface, the conntrack state, and the verdict that matches a production `conntrack -L` output.

## Build It

1. **Set up the topology.** Two namespaces (`ns-cust-a`, `ns-cust-b`) connected by veth pairs to a host bridge. The host's `eth0` is the public-facing interface.
2. **Reproduce the failure.** Send a SYN from outside, capture the conntrack state, and watch the reply go INVALID.
3. **Apply the fix.** Add a policy routing rule, or put the customer in a VRF. Re-test.
4. **Run the simulator.** `python3 code/main.py --scenario asymmetric` should print the matching state machine.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read conntrack state | `conntrack -L` | All entries are NEW/ESTABLISHED; no INVALID |
| Find INVALID entries | `conntrack -L \| grep INVALID` | Empty; if non-empty, the fix is below |
| Read policy routing | `ip rule show; ip route show table all` | `from 192.168.100.0/24 lookup 100` is present |
| Read VRF | `ip vrf show` | `vrf-cust-a` is present with the right table ID |
| Confirm NOTRACK | `iptables -t raw -L -n -v` | The NOTRACK rule is in PREROUTING |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **multi-tenant conntrack runbook** with the diagnostic commands, the three fixes (VRF, NOTRACK, policy routing), and the trade-offs.
- A **before/after capture** of the same flow, showing INVALID entries in conntrack before the fix and clean ESTABLISHED entries after.

Start from `outputs/prompt-vrf-namespace-blackhole-asymmetric-routing.md`.

## Exercises

1. A conntrack entry is in state `INVALID`. The packet is TCP, source `198.51.100.42`, destination `203.0.113.10`. What is the most likely reason, and which interface did the reply leave?
2. The host's `ip rule` has `from 192.168.100.0/24 lookup 100 prio 100`. The customer's pod sends a packet to `8.8.8.8`. Which routing table is consulted, and why?
3. `iptables -t raw -A PREROUTING -s 198.51.100.42 -j NOTRACK` is added. What is the security trade-off?
4. A namespace `ns-cust-a` has a veth pair to the host. The host's `eth0` is the public interface. The customer's reply leaves via the veth (the namespace's default route). On the host, which interface does conntrack see the reply on?
5. The conntrack table is full (the default limit is 262,144 entries on modern kernels). A new SYN arrives. What does the kernel do? Cite the relevant sysctl.
6. The host has `net.netfilter.nf_conntrack_tcp_timeout_established = 7200` (2 hours). A flow is idle for 2 hours. What does conntrack do, and what is the consequence for a long-lived HTTP/2 connection?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Network namespace | "VRF for free" | An isolated kernel networking stack; `ip netns add` / `ip netns exec` |
| VRF | "Virtual routing table" | `ip vrf`; a lightweight namespace with its own routing table (kernel 4.4+) |
| Conntrack | "Stateful firewall" | The Linux `nf_conntrack` module that tracks flows and marks INVALID mismatches |
| INVALID state | "Conntrack drop" | A reply that does not match the original packet's interface or direction |
| NOTRACK | "Bypass conntrack" | `iptables -t raw -j NOTRACK`; disables stateful inspection for a flow |
| `ip rule` | "Policy routing" | The kernel's policy routing rules; select routing table by source, interface, TOS, etc. |
| `ip vrf exec` | "Run in a VRF" | Run a command with the VRF's routing table |
| Veth pair | "Virtual cable" | Two linked interfaces; one in the namespace, one in the host |

## Further Reading

- Linux `man ip-netns(8)`, `man ip-vrf(8)`, `man ip-rule(8)`, `man ip-route(8)`
- `iptables(8)`, `iptables-extensions(8)` (the `raw` table, the `NOTRACK` target)
- `conntrack(8)`, `man nf_conntrack` (the Linux conntrack module)
- Linux kernel source — `net/netfilter/nf_conntrack_core.c` (the state machine)
- RFC 3021 — Using 31-Bit Prefixes on IPv4 Point-to-Point Links (a small bonus for /31 mask lab)
- IETF `vpn` working group — VRF and namespace semantics
- `tc(8)` for additional context on Linux network stack
