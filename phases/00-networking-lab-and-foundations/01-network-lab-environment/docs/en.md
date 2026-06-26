# Network Lab Environment

> Before you can diagnose a network, you need a reproducible network to break. This lesson builds a three-node virtual lab — `h1 — router — h2` — using Linux network namespaces and `veth` pairs, so every packet crosses a real Layer-2 link, a real IP forwarding decision, and a real ARP exchange. You will assign addresses out of RFC 1918 space (`10.0.0.0/24` and `10.0.1.0/24`), enable IPv4 forwarding via `net.ipv4.ip_forward`, install host routes, and verify reachability with ICMP Echo (RFC 792, type 8 / type 0). You then capture traffic with `tcpdump`/Wireshark and confirm the Ethernet II frame (14-byte header, EtherType `0x0800` for IPv4, `0x0806` for ARP), the 20-byte IPv4 header (RFC 791), and the ICMP request/reply pair. The companion `code/main.py` is an offline subnet and reachability planner that computes network/broadcast addresses, host ranges, and whether two endpoints share a subnet or require the router — the same arithmetic the kernel's longest-prefix-match does on every forwarded packet. The lab is the foundation every later phase reuses: TCP handshakes, DNS resolution, NAT, and routing all run on top of it.

**Type:** Build
**Languages:** Python, shell, Wireshark
**Prerequisites:** Basic Linux shell, the OSI/TCP-IP layering lesson in Phase 00
**Time:** ~90 minutes

## Learning Objectives

- Build a 3-node lab (`h1`, `router`, `h2`) with Linux network namespaces and `veth` pairs so each link is a real broadcast domain.
- Assign RFC 1918 addresses across two `/24` subnets and explain why `h1` and `h2` cannot talk without enabling `net.ipv4.ip_forward` and installing routes.
- Predict, then verify, the Ethernet/IPv4/ICMP field values seen in a `ping` capture (EtherType `0x0800`, IP protocol `1`, ICMP type `8`→`0`).
- Use `code/main.py` to decide whether two hosts are same-subnet (direct ARP delivery) or off-subnet (delivery via the default gateway).
- Read an ARP exchange (RFC 826) in Wireshark and connect the resolved MAC to the destination of the next IP packet.
- Tear the lab down cleanly so namespaces and interfaces do not leak between runs.

## The Problem

You are handed a ticket: "`h2` can't reach `h1`, but both can ping their own gateway." On real hardware you cannot single-step the path — packets vanish into switches and NICs you do not control. You need a lab where you own every interface, can inject and capture every frame, and can flip exactly one variable (a missing route, a disabled forwarding flag, a wrong netmask) to see the symptom appear and disappear.

The trap most beginners fall into is testing against `8.8.8.8` or a home router, where NAT, DHCP, Wi-Fi retransmissions, and ISP routing all add noise. When the ping fails you cannot tell whether it is a Layer-2 problem (ARP), a Layer-3 problem (routing), or a policy problem (firewall). A controlled lab removes that ambiguity: there is exactly one router, two subnets, and no NAT — so a failure maps to exactly one layer.

## The Concept

### Why namespaces instead of VMs

A Linux **network namespace** is an isolated copy of the kernel's networking stack: its own interfaces, routing table, ARP cache, and iptables rules. It costs microseconds to create and a few kilobytes of memory, versus gigabytes and seconds for a VM. A **`veth` pair** is a virtual Ethernet cable: two interfaces where a frame written to one end emerges at the other. Put one end in namespace `h1` and the other in `router`, and you have a real point-to-point link with real MAC addresses.

The topology (see `assets/network-lab-environment.svg`):

```
[ h1 ]                 [ router ]                 [ h2 ]
10.0.0.2/24  --veth-->  10.0.0.1/24
                        10.0.1.1/24  --veth-->  10.0.1.2/24
   subnet A: 10.0.0.0/24        subnet B: 10.0.1.0/24
```

`h1` and `h2` are on **different** subnets on purpose. Same-subnet delivery is trivial (ARP + send). Cross-subnet delivery forces the interesting machinery: a default route, a forwarding kernel, and two ARP exchanges.

### Address plan and the subnet math

All addresses come from RFC 1918 private space. For a `/24`, the mask is `255.255.255.0`; the low byte selects the host. `code/main.py` computes the same values the kernel derives:

| Field | Subnet A | Subnet B |
|---|---|---|
| Network address | `10.0.0.0` | `10.0.1.0` |
| Usable host range | `10.0.0.1`–`10.0.0.254` | `10.0.1.1`–`10.0.1.254` |
| Broadcast | `10.0.0.255` | `10.0.1.255` |
| Router interface | `10.0.0.1` | `10.0.1.1` |
| Host | `10.0.0.2` (h1) | `10.0.1.2` (h2) |

The **same-subnet test** is pure bitwise AND: two addresses are on the same subnet iff `(ip_a & mask) == (ip_b & mask)`. `h1 & /24 = 10.0.0.0`; `h2 & /24 = 10.0.1.0`. They differ, so `h1` must send to its **default gateway** `10.0.0.1`, not directly to `h2`.

### The forwarding decision (longest-prefix match)

When `h1` pings `10.0.1.2`, its kernel walks the routing table looking for the most specific prefix that contains the destination:

```
10.0.0.0/24 dev veth-h1            # directly connected — covers 10.0.0.x
default via 10.0.0.1 dev veth-h1   # everything else → router
```

`10.0.1.2` does not match the `/24` connected route, so the `default` (`/0`) route wins, and the packet is handed to `10.0.0.1`. The router receives it, looks up `10.0.1.2` in *its* table, finds the directly-connected `10.0.1.0/24`, and forwards it out the other interface — but only if `net.ipv4.ip_forward = 1`. With forwarding off, the router silently drops the packet (or replies ICMP, depending on config), and the ping times out. This single sysctl is the most common "everything is configured but nothing works" cause in the lab.

### What ARP actually does (RFC 826)

IP routing chooses *which* next-hop IP. ARP answers *which MAC* corresponds to that next-hop on the local link. Before `h1` sends its first packet to `10.0.0.1`, it broadcasts an ARP request (EtherType `0x0806`):

```
Who has 10.0.0.1? Tell 10.0.0.2
```

destined to the broadcast MAC `ff:ff:ff:ff:ff:ff`. The router replies unicast with its MAC, `h1` caches it, and the ICMP packet finally goes out in an Ethernet frame addressed to the router's MAC — even though its IP destination is `h2`. This MAC/IP split is the most-missed point for beginners: **the Layer-2 destination is the next hop, the Layer-3 destination is the final host.**

### The frames you will capture

A successful `ping` from `h1` to `h2` produces this nesting on the wire:

| Layer | Header | Key fields |
|---|---|---|
| Ethernet II (14 B) | dst MAC, src MAC, EtherType | EtherType `0x0800` (IPv4) |
| IPv4 (20 B, RFC 791) | version/IHL, TTL, protocol, src/dst IP | protocol `1` (ICMP), TTL decremented by router |
| ICMP (RFC 792) | type, code, checksum, id, seq | type `8` (request) → type `0` (reply) |

The **TTL** is your forwarding proof: a packet that crossed the router arrives with TTL one lower than it left (e.g. `64 → 63`). If you ever see the original TTL on the far side, the packet did **not** pass an IP-forwarding hop.

### Capture and display filters

`tcpdump -i veth-h1 -n icmp or arp` shows exactly the two protocols this lab exercises. In Wireshark, the equivalent display filters are `icmp`, `arp`, and `ip.addr == 10.0.1.2`. Filter on `eth.type == 0x0806` to isolate the ARP handshake that precedes the very first ICMP packet.

### Failure modes you can reproduce on demand

| Symptom | Single broken variable | Evidence |
|---|---|---|
| `h1`→`h2` times out, gateway reachable | `ip_forward = 0` on router | ICMP request seen on router's inbound veth, never on outbound |
| `h1`→`h2` "Destination Host Unreachable" | no default route on `h1` | `ping` errors instantly; no packet leaves `h1` |
| Reply never returns | no return route on `h2` for `10.0.0.0/24` | request reaches `h2`, reply has nowhere to go |
| Wrong netmask (`/16` not `/24`) | `h1` thinks `h2` is local | ARP request for `10.0.1.2` on subnet A — no answer |

## Build It

1. Run `code/main.py` first (offline) to confirm the address plan: it prints each subnet's network/broadcast/range and the same-subnet verdict for `h1`↔`h2`.
2. Create the namespaces and links (run as root):
   ```bash
   sudo ip netns add h1; sudo ip netns add router; sudo ip netns add h2
   sudo ip link add veth-h1 type veth peer name veth-r1
   sudo ip link add veth-h2 type veth peer name veth-r2
   sudo ip link set veth-h1 netns h1;  sudo ip link set veth-r1 netns router
   sudo ip link set veth-h2 netns h2;  sudo ip link set veth-r2 netns router
   ```
3. Address and bring up the interfaces (one example shown; mirror for the rest):
   ```bash
   sudo ip netns exec h1 ip addr add 10.0.0.2/24 dev veth-h1
   sudo ip netns exec h1 ip link set veth-h1 up
   sudo ip netns exec router ip addr add 10.0.0.1/24 dev veth-r1
   sudo ip netns exec router ip addr add 10.0.1.1/24 dev veth-r2
   ```
4. Enable forwarding **inside the router namespace**: `sudo ip netns exec router sysctl -w net.ipv4.ip_forward=1`.
5. Install default routes on `h1` (`via 10.0.0.1`) and `h2` (`via 10.0.1.1`).
6. Verify with `sudo ip netns exec h1 ping -c3 10.0.1.2` while capturing: `sudo ip netns exec router tcpdump -i veth-r1 -n icmp or arp`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm address plan | `main.py` output | Network/broadcast/range match the table; `h1`↔`h2` reported as off-subnet |
| Prove the link is up | ARP request/reply in capture | `Who has 10.0.0.1` answered by router MAC before first ICMP |
| Prove forwarding works | ICMP on both router veths; TTL drop | Request enters `veth-r1`, exits `veth-r2`, TTL `64→63` |
| Localize a failure | Before/after capture per interface | The last interface that saw the packet pins the broken layer |

## Ship It

Produce one reusable artifact under `outputs/`:

- A teardown script (`ip netns del h1 router h2`) plus a one-command bring-up so the lab is reproducible.
- An annotated Wireshark capture (`.pcapng`) of one full `ping` with the ARP handshake, exported with your field notes.
- A failure-mode runbook mapping each symptom in the table above to the interface where the packet disappears.

Start from [`outputs/prompt-network-lab-environment.md`](../outputs/prompt-network-lab-environment.md).

## Exercises

1. Disable forwarding on the router (`ip_forward=0`), ping `h1`→`h2`, and capture on **both** router veths. Which interface sees the request, which does not, and what does that prove about where the drop happens?
2. Give `h1` a `/16` mask instead of `/24` but leave everything else correct. Predict whether `h1` ARPs for the gateway or for `h2` directly, then confirm in the capture with `eth.type == 0x0806`.
3. Remove `h2`'s return route to `10.0.0.0/24`. The request still reaches `h2`. Explain, using TTL and ICMP types, why `h1` still sees a timeout.
4. Run `main.py` for `10.0.0.2/30` and `10.0.0.6/30`: are they the same subnet? How many usable hosts does a `/30` give, and why is `/30` the classic point-to-point link size?
5. Capture the first packet of a `ping` and the second. Why does only the first trigger ARP? When would the ARP cache entry expire and force a new exchange?
6. Add a third subnet and a route so `h1` reaches a new host `h3` two hops away. Predict the TTL `h3` observes and verify it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Network namespace | "a container's network" | An isolated kernel networking stack: own interfaces, routes, ARP cache, firewall |
| `veth` pair | "virtual cable" | Two linked interfaces; a frame in one end exits the other, with real MACs |
| Default gateway | "the router IP" | The next hop chosen by the `/0` route when no more-specific prefix matches |
| `ip_forward` | "router mode" | The `net.ipv4.ip_forward` sysctl; if `0`, the kernel won't forward between interfaces |
| ARP | "finds the IP" | RFC 826: maps a next-hop **IP** to a **MAC** on the local link, not end-to-end |
| Longest-prefix match | "routing" | Picks the most specific matching route; `/24` beats `/0` for an in-subnet dest |
| TTL | "time to live" | A hop counter (RFC 791); decremented by 1 per router; reaching 0 drops the packet |
| Same-subnet test | "are they local?" | `(ip_a & mask) == (ip_b & mask)`; if equal, deliver via ARP, else via gateway |

## Further Reading

- RFC 791 — Internet Protocol (IPv4 header, TTL, fragmentation)
- RFC 792 — Internet Control Message Protocol (Echo request/reply, type/code)
- RFC 826 — An Ethernet Address Resolution Protocol (ARP)
- RFC 1918 — Address Allocation for Private Internets (`10/8`, `172.16/12`, `192.168/16`)
- IEEE 802.3 — Ethernet framing and the Ethernet II / 802.3 layout
- `ip-netns(8)`, `ip-route(8)`, `veth(4)` Linux man pages
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — Ch. 4 (the MAC sublayer) and Ch. 5 (the network layer)
- Wireshark User's Guide — capture and display filter reference
