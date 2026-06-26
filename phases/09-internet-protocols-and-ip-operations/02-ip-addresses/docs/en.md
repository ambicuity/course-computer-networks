# IP Addresses

> An IPv4 address is a 32-bit hierarchical identifier split into a variable-length **network prefix** and a **host suffix**, written in **dotted decimal** (e.g. `128.208.2.151`). The original 1981 **classful** scheme carved the space into five fixed blocks: **Class A** `0.0.0.0/8`–`127.255.255.255` (8-bit net, 24-bit host), **Class B** `128.0.0.0/16`–`191.255.255.255` (16/16), **Class C** `192.0.0.0/24`–`223.255.255.255` (24/8), **Class D** `224.0.0.0/4` multicast, and **Class E** `240.0.0.0/4` reserved. The **subnet mask** (e.g. `255.255.255.0`) is a binary AND-mask that isolates the network portion; **CIDR** notation (RFC 1519) appends the prefix length as `/n`, so `192.168.1.0/24` means a 24-bit prefix with 254 usable hosts. **RFC 1918** reserves three private ranges for internal use — `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — and **NAT** (RFC 3022) translates between these and one public address using transport-layer **ports**. Special-use addresses include `127.0.0.0/8` loopback, `169.254.0.0/16` link-local, `0.0.0.0` "this host", and `255.255.255.255` limited broadcast. This lesson dissects the structure, works through subnetting and VLSM arithmetic by hand, and builds an IP toolkit you can use in real address planning.

**Type:** Build
**Languages:** IP tools, Wireshark
**Prerequisites:** The IP Version 4 Protocol (Phase 9 L01), dotted decimal notation, binary arithmetic
**Time:** ~90 minutes

## Learning Objectives

- Decode a 32-bit IPv4 address into network and host portions using a subnet mask, and express the same prefix in both dotted-decimal-mask and `/n` CIDR notation.
- Recite the Class A–E ranges and explain why classful addressing wasted addresses (the "three bears problem"), and how CIDR replaced it with variable-length prefixes and longest-prefix-match routing.
- Work a subnetting problem by hand: given a `/24` block and a requirement list, compute subnet boundaries, masks, broadcast addresses, and usable host counts using VLSM.
- Identify the three RFC 1918 private ranges, explain how NAT maps internal addresses to a public IP via port numbers, and state why private addresses must never appear on the public Internet.
- Classify special-use addresses (`127/8`, `169.254/16`, `0.0.0.0`, `255.255.255.255`) by their operational meaning and the failure modes they expose.
- Relate IP addressing to ARP: explain how a host resolves a next-hop IP to a MAC address on the local subnet before the packet can leave.

## The Problem

A small company is assigned `192.168.1.0/24` — 256 addresses, 254 usable — and needs to wire up four subnets: a 60-host engineering floor, a 30-host sales floor, a 14-host server rack, and a 2-host point-to-point WAN link. A junior engineer assigns `/25` (126 hosts) to engineering, `/25` to sales, `/27` (30) to servers, and `/30` (2) to the WAN — and runs out of addresses after the second subnet. The block is too small for that layout.

The fix is **VLSM**: subnet the block into a `/26` (62) for engineering, a `/27` (30) for sales, a `/28` (14) for servers, and a `/30` (2) for the WAN, packing them back-to-back on power-of-two boundaries so the total fits inside the original `/24`. The arithmetic is not hard, but it is exact: every boundary must align on `2^(32-prefix)` and every subnet must reserve the all-zeros network address and all-ones broadcast address. Get one bit wrong and two subnets silently overlap, or a router forwards traffic to the wrong floor. This lesson teaches the bit-level mechanics so you can do the division on a whiteboard and verify it with `code/main.py`.

## The Concept

An IP address names a **network interface**, not a host. A host on one network has one IP address; a router with N interfaces has N IP addresses. The address is hierarchical: the top bits identify the network (the **prefix**), the bottom bits identify the host on that network. Routers forward only on the prefix, which is why the global routing table holds ~300,000 prefixes instead of a billion per-host entries. The SVG shows the class table and a VLSM carving of a `/24`; `code/main.py` parses CIDR, computes network/broadcast, checks membership, and divides blocks.

### Dotted decimal and the 32-bit address

Every IPv4 address is 4 bytes. The 32-bit hex value `80D00297` is written `128.208.2.151` — each byte in decimal, 0–255, separated by dots. The prefix is written as `lowest_address/length`, e.g. `128.208.0.0/24` means "the block from `128.208.0.0` to `128.208.0.255`, network portion is 24 bits." The block size must be a power of two and the base address must be aligned to that size.

### Classful addressing (historical, pre-1993)

The original 1981 scheme split the 32-bit space into five classes by the leading bits:

| Class | Leading bits | Prefix length | First octet range | Hosts per network | Use |
|---|---|---|---|---|---|
| A | `0` | /8 | 0–127 | 2^24 − 2 = 16,777,214 | very large orgs |
| B | `10` | /16 | 128–191 | 2^16 − 2 = 65,534 | medium orgs |
| C | `110` | /24 | 192–223 | 2^8 − 2 = 254 | small LANs |
| D | `1110` | n/a | 224–239 | multicast group | multicast |
| E | `1111` | n/a | 240–255 | reserved | experimental |

The villain was Class B: 65,534 hosts was "just right" for most orgs, so everyone asked for one, and the 16,384 Class B blocks were exhausted quickly — even though studies showed over half of Class B holders had fewer than 50 hosts. This "three bears problem" is what drove the move to CIDR.

### CIDR and prefix length (RFC 1519)

**Classless Inter-Domain Routing** dropped the fixed class boundaries. A prefix can be any length from `/0` to `/32`, and the mask is written as `address/prefixlen`. The mask is a string of `prefixlen` ones followed by `32 − prefixlen` zeros. Routers use **longest-prefix-match**: if a destination matches both a `/20` and a `/24`, the `/24` wins because it is more specific. This enables **route aggregation** — a distant router can advertise `194.24.0.0/19` instead of three separate `/20`, `/21`, `/22` blocks — and keeps the global table near 200,000 entries instead of millions.

| Prefix | Subnet mask | Usable hosts | Block size |
|---|---|---|---|
| /24 | 255.255.255.0 | 254 | 256 |
| /25 | 255.255.255.128 | 126 | 128 |
| /26 | 255.255.255.192 | 62 | 64 |
| /27 | 255.255.255.224 | 30 | 32 |
| /28 | 255.255.255.240 | 14 | 16 |
| /29 | 255.255.255.248 | 6 | 8 |
| /30 | 255.255.255.252 | 2 | 4 |
| /32 | 255.255.255.255 | 1 (host route) | 1 |

### Subnet mask in binary

The subnet mask is a 32-bit value with `n` leading 1s and `32−n` trailing 0s. AND the mask with the IP address to extract the network portion:

```
  IP    128.208.2.151  = 10000000 11010000 00000010 10010111
  mask  255.255.255.0  = 11111111 11111111 11111111 00000000
  AND   128.208.2.0    = 10000000 11010000 00000010 00000000  (network)
  broadcast = network | ~mask = 128.208.2.255
```

The **network address** (host bits all 0) and **broadcast address** (host bits all 1) are reserved; usable hosts = `2^(32−n) − 2` for `/n` where `n ≤ 30`.

### Subnetting worked example: VLSM on `/24`

Carve `192.168.1.0/24` into four subnets, largest first, each aligned to its block size:

| Subnet | Need | Prefix | Network | Broadcast | Usable range | Mask |
|---|---|---|---|---|---|---|
| Engineering | 60 | /26 | 192.168.1.0 | 192.168.1.63 | .1–.62 | 255.255.255.192 |
| Sales | 30 | /27 | 192.168.1.64 | 192.168.1.95 | .65–.94 | 255.255.255.224 |
| Servers | 14 | /28 | 192.168.1.96 | 192.168.1.111 | .97–.110 | 255.255.255.240 |
| WAN link | 2 | /30 | 192.168.1.112 | 192.168.1.115 | .113–.114 | 255.255.255.252 |
| (free) | — | /28 | 192.168.1.128 | 192.168.1.143 | — | — |

Each block starts on a multiple of its size (64, 32, 16, 4), and the next block starts immediately after the previous broadcast. The total consumes `.0–.115` and leaves `.116–.255` for future growth.

### Private addresses and NAT (RFC 1918 / RFC 3022)

Three ranges are reserved for private use and must not appear on the public Internet:

| Range | CIDR | Hosts | Typical use |
|---|---|---|---|
| 10.0.0.0 – 10.255.255.255 | 10.0.0.0/8 | 16,777,214 | large enterprises |
| 172.16.0.0 – 172.31.255.255 | 172.16.0.0/12 | 1,048,574 | mid-size |
| 192.168.0.0 – 192.168.255.255 | 192.168.0.0/16 | 65,534 | home/SMB |

**NAT** sits at the customer/ISP boundary. Internal hosts use `10.x.y.z`; on egress the NAT box rewrites the source IP to the single public IP and the source port to a unique NAT-assigned port. The NAT keeps a translation table mapping `(public IP, NAT port) ↔ (internal IP, internal port)`. When the reply returns, the NAT looks up the port and restores the internal destination. This multiplexes thousands of internal hosts behind one public address — a quick fix for IPv4 exhaustion that IPv6 will eventually make unnecessary.

```
  10.0.0.1:5544  ──NAT──▶  198.60.42.12:3344  ──▶  Internet
      ▲                         │
      │   reply to :3344         │
      └─────────────────────────┘  table: 3344 → 10.0.0.1:5544
```

### Special-use addresses

| Address | Mask | Meaning | Failure mode |
|---|---|---|---|
| `0.0.0.0` | /32 | "this host on this network" — used during boot before DHCP | misconfigured DHCP client |
| `127.0.0.0` | /8 | loopback — packets never hit the wire | `localhost` works but external fails |
| `169.254.0.0` | /16 | link-local (APIPA) — self-assigned when DHCP fails | duplicate `169.254` = DHCP outage |
| `255.255.255.255` | /32 | limited broadcast — all hosts on local LAN | broadcast storm if flooded |
| `net.255.255` | — | directed broadcast — all hosts on a distant net | disabled by admins (security hazard) |

### ARP and address resolution

An IP address names a logical interface; an Ethernet frame needs a MAC address. When a host wants to send to a next-hop IP on the same subnet, it broadcasts an **ARP Request** ("who has `192.168.1.5`? tell `192.168.1.1`"). The owner replies with its MAC, the sender caches the mapping in its ARP table, and the packet is encapsulated in an Ethernet frame to that MAC. ARP is link-local only — routers do not forward ARP across subnets. A stale or poisoned ARP cache is a common cause of "IP works at the gateway but host is unreachable" symptoms. In Wireshark, filter `arp.dst.hw_mac == 00:00:00:00:00:00` to see requests.

Reference code: [`code/main.py`](../code/main.py) — IP toolkit. Diagram: [`assets/ip-addresses.svg`](../assets/ip-addresses.svg).

## Build It

`code/main.py` is a stdlib-only IP toolkit with five operations tied to the concept.

1. **Parse CIDR** — `parse_cidr("192.168.1.0/24")` returns network, broadcast, mask, host range, usable count.
2. **Compute network/broadcast** — AND the IP with the mask (network), OR with inverted mask (broadcast).
3. **Check membership** — `in_subnet("192.168.1.55", "192.168.1.0/26")` returns True/False by AND-masking both.
4. **Classify** — identify class (A–E) from the first octet, flag private (RFC 1918) and special-use addresses.
5. **Subnet divider** — `divide("192.168.1.0/24", [60, 30, 14, 2])` returns the VLSM layout, or reports it does not fit.

Run `python3 code/main.py`, then change the requirements to watch boundaries shift.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Find the network of an IP | `ip route get`, mask AND | `192.168.1.55 & 255.255.255.192` = `192.168.1.0` (/26) |
| Size a subnet | Host count → prefix length | 60 hosts → need `/26` (62 usable) |
| Verify a VLSM plan | No overlap, aligned boundaries | All subnets packed, broadcast < next network |
| Spot a private address | First octet + range check | `10.x`, `172.16–31.x`, `192.168.x` → RFC 1918 |
| Diagnose connectivity | `arp -n`, Wireshark ARP | Gateway MAC in ARP table; no `169.254` self-assignment |
| Trace NAT | `conntrack -L` / Wireshark | Public port maps to internal `10.x` address |

Wireshark filters: `ip.addr == 192.168.1.0/24`, `ip.src == 10.0.0.0/8`, `arp`, `ip.dst == 255.255.255.255`.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **VLSM worksheet template** for dividing any `/n` block into a requirement list, with alignment and overlap checks.
- An **address-class cheat sheet** with the Class A–E table, RFC 1918 ranges, and special-use addresses.
- A **NAT troubleshooting runbook**: how to read the translation table, spot port exhaustion, and detect a private address leaking to the public Internet.
- The **IP toolkit script** (`code/main.py`) wired to your own subnet plan.

Start from [`outputs/prompt-ip-addresses.md`](../outputs/prompt-ip-addresses.md).

## Exercises

1. Convert `172.16.45.200` to binary, apply the `/12` mask, and write the network and broadcast addresses in dotted decimal. How many usable hosts does this private block have?
2. You are given `10.0.0.0/22`. Subnet it into one block for 200 hosts, one for 100 hosts, one for 50 hosts, and a `/30` for a WAN link. Give every network address, broadcast, and mask. Does it fit?
3. A host has IP `192.168.1.130/26`. A colleague says the gateway should be `192.168.1.1`. Explain why that is wrong and give the correct gateway range.
4. A packet arrives at a router destined for `192.168.1.130`. The routing table has `192.168.1.0/24` via eth0 and `192.168.1.128/25` via eth1. Which interface wins and why? What is the rule called?
5. A laptop shows `169.254.10.20`. What happened, what protocol assigned this, and which two things should you check first?
6. NAT translates `10.0.0.5:4444` to `203.0.113.7:5001`. When the reply comes back to `203.0.113.7:5001`, how does the NAT box know to send it to `10.0.0.5`? What breaks if two internal hosts pick the same source port?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Prefix | "the network part" | The top L bits of the address; written `/L`; all hosts in one subnet share the prefix |
| Subnet mask | "the thing after the IP" | 32-bit AND-mask with L leading 1s; isolates the network portion from the host portion |
| CIDR | "slash notation" | Classless addressing with arbitrary `/n` prefix lengths and longest-prefix-match routing (RFC 1519) |
| VLSM | "variable masks" | Using different prefix lengths within one block so subnets match their host counts exactly |
| Private address | "internal IP" | RFC 1918 range (10/8, 172.16/12, 192.168/16) not routable on the public Internet |
| NAT | "the thing that makes home Wi-Fi work" | Port-multiplexed translation of many private IPs behind one public IP (RFC 3022) |
| Network address | "the all-zeros one" | Host bits all 0; identifies the subnet itself, not assignable to a host |
| Broadcast address | "the all-ones one" | Host bits all 1; reaches every host on the subnet; reserved, not assignable |
| ARP | "MAC lookup" | Link-local broadcast that resolves a next-hop IP to a MAC address; cached in an ARP table |
| Longest prefix match | "most specific route" | When multiple prefixes match a destination, the one with the most bits wins |

## Further Reading

- **RFC 1918** — Rekhter et al. (1996): "Address Allocation for Private Internets" — the three private ranges.
- **RFC 1519** — Fuller, Li, Yu, Varadhan (1993): "Classless Inter-Domain Routing (CIDR)" — prefix aggregation and longest-match. Superseded by RFC 4632 (2006).
- **RFC 3022** — Srisuresh & Egevang (2001): "Traditional IP Network Address Translator" — port-based NAT.
- **RFC 3927** — Cheshire et al. (2005): "Dynamic Configuration of IPv4 Link-Local Addresses" — the `169.254/16` APIPA range.
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §5.6.2 "IP Addresses" — the source chapter.
- `ipcalc` CLI and Python `ipaddress` module for checking arithmetic.