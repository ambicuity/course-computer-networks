# Subnetting and Address Notation Primer to Course Portfolio Setup

> An IPv4 address is a 32-bit unsigned integer (RFC 791, written as four dotted-decimal octets), split by a *prefix length* into a network part and a host part. CIDR notation (RFC 4632) replaced the old Class A/B/C scheme in 1993: `192.168.10.0/24` means the high 24 bits are network, the low 8 are host. A `/24` yields 2^(32-24)=256 addresses, of which 254 are usable because the all-zeros host is the *network address* and the all-ones host is the *directed broadcast* (RFC 919). The subnet mask `255.255.255.0` is just the prefix as a bitmask; the *wildcard mask* `0.0.0.255` is its bitwise complement, used by ACLs and OSPF. To test whether two addresses share a subnet you AND each with the mask and compare. This lesson builds a stdlib-only Python subnet calculator, teaches VLSM (Variable Length Subnet Masking) for right-sizing networks, covers the RFC 1918 private ranges and RFC 6598 CGN space, and ships a reusable lab artifact for your course portfolio.

**Type:** Build
**Languages:** Python, shell, Markdown, Git
**Prerequisites:** Binary and hexadecimal arithmetic; earlier Phase 00 lessons on the IP layer and the lab environment
**Time:** ~90 minutes

## Learning Objectives

- Convert an IPv4 address between dotted-decimal and its 32-bit integer form, and explain why `/24` equals mask `255.255.255.0` and wildcard `0.0.0.255`.
- Given an address and prefix, compute the network address, broadcast address, usable host range, and host count without a calculator, using bitwise AND/OR/NOT.
- Apply VLSM to carve one block (e.g. `10.20.0.0/22`) into right-sized subnets for hosts counts like 100, 50, 25, and 2, choosing prefixes that minimize waste.
- Classify any address as RFC 1918 private, RFC 6598 shared CGN, RFC 3927 link-local, loopback, or globally routable, and predict whether two hosts are on the same subnet.
- Produce a portfolio artifact (`outputs/`) — a subnet plan plus a verifiable calculator script you reuse in later routing and ACL lessons.

## The Problem

You are handed a single allocation, `10.20.0.0/22`, and four departments that need addresses: Engineering wants 200 hosts, Sales 100, Ops 50, and a point-to-point WAN link needs exactly 2. A junior engineer naively splits the `/22` into four equal `/24`s. That "works" but it cannot fit Engineering's 200 hosts into the natural growth headroom, wastes 252 addresses on the WAN link that needs 2, and silently overlaps with a `10.20.2.0/24` route already advertised by another team.

Worse, a week later a host at `10.20.1.130` cannot reach `10.20.1.200`. Ping fails. The application team blames DNS. The real cause: someone configured those hosts with a `/26` mask instead of `/25`, so the two addresses land in *different* subnets (`10.20.1.128/26` ends at `.191`) and traffic gets sent to a default gateway that has no route back. The symptom is "the app is down"; the evidence lives in the address-and-mask arithmetic. This lesson makes that arithmetic mechanical and verifiable.

## The Concept

### IPv4 as a 32-bit integer

An IPv4 address is not four numbers — it is one 32-bit unsigned integer that we *print* as four 8-bit octets for human eyes. `192.168.10.1` is:

```
11000000 . 10101000 . 00001010 . 00000001
   192        168         10          1
= 192*2^24 + 168*2^16 + 10*2^8 + 1 = 3232238081
```

Every subnetting operation is integer math on that value. `code/main.py` does exactly this: `ip_to_int` packs the four octets with shifts, and `int_to_ip` unpacks them. Once you think in the integer, network and broadcast addresses are just "clear the low bits" and "set the low bits."

### Prefix, mask, and wildcard are three views of one thing

The prefix length *p* says "the high *p* bits are the network." The mask is *p* ones followed by (32-*p*) zeros. The wildcard is the bitwise complement. They are interchangeable:

| Prefix | Mask | Wildcard | Host bits | Total addrs | Usable hosts |
|--------|------|----------|-----------|-------------|--------------|
| /30 | 255.255.255.252 | 0.0.0.3 | 2 | 4 | 2 |
| /29 | 255.255.255.248 | 0.0.0.7 | 3 | 8 | 6 |
| /28 | 255.255.255.240 | 0.0.0.15 | 4 | 16 | 14 |
| /27 | 255.255.255.224 | 0.0.0.31 | 5 | 32 | 30 |
| /26 | 255.255.255.192 | 0.0.0.63 | 6 | 64 | 62 |
| /25 | 255.255.255.128 | 0.0.0.127 | 7 | 128 | 126 |
| /24 | 255.255.255.0 | 0.0.0.255 | 8 | 256 | 254 |
| /23 | 255.255.254.0 | 0.0.1.255 | 9 | 512 | 510 |
| /22 | 255.255.252.0 | 0.0.3.255 | 10 | 1024 | 1022 |

Total addresses = 2^(32-p). Usable hosts = 2^(32-p) − 2, because the all-zeros host is reserved as the network/subnet identifier and the all-ones host is the directed broadcast (RFC 919, RFC 922). The one exception: a `/31` (RFC 3021) intentionally has *no* network/broadcast reservation so both addresses are usable on point-to-point links, and a `/32` is a single host route.

### Computing network, broadcast, and host range

Given address `A` and mask `M` (as integers):

- **Network address** = `A AND M` — forces all host bits to 0.
- **Broadcast address** = `A OR (NOT M)` — forces all host bits to 1; `NOT M` is the wildcard.
- **First usable host** = network + 1 (for prefixes shorter than /31).
- **Last usable host** = broadcast − 1.

Worked example for `10.20.1.130/25` (mask `255.255.255.128`, wildcard `0.0.0.127`):

```
A         = 00001010.00010100.00000001.10000010   (10.20.1.130)
M         = 11111111.11111111.11111111.10000000   (/25)
A AND M   = 00001010.00010100.00000001.10000000 = 10.20.1.128   network
NOT M     = 00000000.00000000.00000000.01111111   wildcard
A OR ~M   = 00001010.00010100.00000001.11111111 = 10.20.1.255   broadcast
usable    = 10.20.1.129 ... 10.20.1.254   (126 hosts)
```

Now the bug from "The Problem" is obvious: under `/25`, `.130` and `.200` are both in `10.20.1.128/25` and can talk directly. Under the wrong `/26` mask, `.130` is in `10.20.1.128/26` (`.128`–`.191`) but `.200` is in `10.20.1.192/26` (`.192`–`.255`) — different subnets, no direct path. `code/main.py`'s `same_subnet()` reproduces this in one line: compare `A1 AND M` with `A2 AND M`.

### Same-subnet test (the forwarding decision)

When a host wants to send to a destination, the IP stack performs exactly this test to decide *deliver locally via ARP* vs *hand to the default gateway*:

```
if (src_ip AND mask) == (dst_ip AND mask):
    resolve dst MAC via ARP, send directly (Layer 2)
else:
    send to default gateway's MAC (Layer 3 forwarding)
```

The SVG (`assets/subnetting-and-address-notation-primer-to-course-portfolio-setup.svg`) lays out the 32 bits with the prefix boundary, the AND operation, and the resulting network/broadcast split so you can trace this decision visually.

### VLSM: right-sizing with variable prefixes

Classful and fixed-length subnetting force every subnet to the same size. VLSM lets each subnet take just enough host bits for its requirement. The rule: **allocate largest first**, and for each requirement pick the smallest prefix whose usable-host count covers it.

Carving `10.20.0.0/22` (1024 addresses) for 200 / 100 / 50 / 2 hosts:

| Dept | Need | Smallest fit | Prefix | Block | Range | Usable |
|------|------|--------------|--------|-------|-------|--------|
| Engineering | 200 | 2^8−2=254 | /24 | 10.20.0.0/24 | .0.1–.0.254 | 254 |
| Sales | 100 | 2^7−2=126 | /25 | 10.20.1.0/25 | .1.1–.1.126 | 126 |
| Ops | 50 | 2^6−2=62 | /26 | 10.20.1.128/26 | .1.129–.1.190 | 62 |
| WAN link | 2 | 2^2−2=2 | /30 | 10.20.1.192/30 | .1.193–.1.194 | 2 |

Everything fits inside the first half of the `/22` with `10.20.1.196`–`10.20.3.255` left free for growth — versus the naive four-`/24` split that would have run out of room. `code/main.py`'s `vlsm_plan()` implements this greedy allocator and prints the table.

### Special and reserved ranges

Not every address is routable on the public Internet. The calculator classifies these:

| Range | RFC | Purpose |
|-------|-----|---------|
| 10.0.0.0/8 | 1918 | Private (large orgs) |
| 172.16.0.0/12 | 1918 | Private (172.16–172.31) |
| 192.168.0.0/16 | 1918 | Private (home/SMB) |
| 100.64.0.0/10 | 6598 | Carrier-grade NAT shared space |
| 169.254.0.0/16 | 3927 | Link-local (APIPA) when DHCP fails |
| 127.0.0.0/8 | 1122 | Loopback |
| 224.0.0.0/4 | 5771 | Multicast |
| 0.0.0.0/8 | 1122 | "This network" / unspecified |

A classic failure mode: a host shows `169.254.x.x` — that is not a routing problem, it is APIPA self-assignment because the DHCP DISCOVER got no OFFER. The address itself is the evidence.

## Build It

1. Open `code/main.py` and read the module docstring. Note the four core helpers: `ip_to_int`, `int_to_ip`, `prefix_to_mask`, and `mask_to_wildcard`.
2. Run it: `python3 code/main.py`. It prints a full breakdown of `10.20.1.130/25`, a `/30` WAN link, a same-subnet test for the bug scenario, a VLSM plan, and address classifications.
3. Verify the network/broadcast math by hand for one row using the worked example above. The script's output must match your bitwise arithmetic.
4. Change the demo input in `main()` to your own allocation (e.g. `172.16.8.0/22`) and a host-requirement list, then re-run to generate your plan.
5. Capture the output into `outputs/` as your portfolio subnet plan.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decode an address+prefix | `network`, `broadcast`, usable range, host count | All four match a hand-computed AND/OR; off-by-one on broadcast is caught |
| Decide local vs gateway delivery | `same_subnet(a, b, mask)` result | You can state which subnet each host is in and why traffic does/doesn't route |
| Plan a network with VLSM | Greedy allocation table with no overlaps | Largest-first ordering; no block overlaps; leftover space documented |
| Classify an address | RFC label (1918 / 6598 / 3927 / loopback / global) | A `169.254.x.x` host is diagnosed as DHCP failure, not a route problem |

## Ship It

Produce one artifact under `outputs/`:

- A subnet plan for a realistic allocation (the VLSM table for your chosen block), saved as Markdown.
- The captured `python3 code/main.py` run that proves the numbers.

Start from [`outputs/prompt-subnetting-and-address-notation-primer-to-course-portfolio-setup.md`](../outputs/prompt-subnetting-and-address-notation-primer-to-course-portfolio-setup.md). This calculator and plan are reused directly in the later routing-table and ACL lessons, where the wildcard masks and network/broadcast boundaries you compute here become route entries and access-list lines.

## Exercises

1. A host is configured as `192.168.50.77/27`. Compute its network address, broadcast, usable range, and host count by hand, then confirm with `code/main.py`. Which other addresses can it reach directly?
2. Two servers `10.0.5.65` and `10.0.5.130` are both set to mask `255.255.255.192` (`/26`). Can they communicate directly? Show the `AND` for each and state the subnet boundary that separates or joins them.
3. Carve `198.51.100.0/24` into subnets for departments needing 60, 28, 12, and 2 hosts using VLSM. List each block, prefix, usable range, and the address space left over.
4. You inherit a network where users intermittently lose connectivity and `ipconfig` shows `169.254.18.4`. Name the mechanism (RFC and protocol), explain why no manual subnetting fixes it, and state the single packet exchange you would capture to confirm the root cause.
5. Explain why a `/31` link (RFC 3021) gives 2 usable hosts while a `/30` also gives 2 usable hosts. What does the `/31` save, and on what kind of interface is it used?
6. Given `10.20.1.192/30`, which exact two addresses are usable, what is the broadcast, and why would assigning `10.20.1.195` to a router interface fail?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Prefix length (/n) | "the slash number" | Count of leading network bits; defines mask = n ones then 32−n zeros |
| Subnet mask | "the 255s" | The prefix as a 32-bit bitmask; ANDed with an address to extract the network |
| Wildcard mask | "backwards mask" | Bitwise complement of the mask; used by ACLs and OSPF to match host bits |
| Network address | "the first one" | All host bits = 0; identifies the subnet, not assignable to a host |
| Broadcast address | "the last one" | All host bits = 1; directed broadcast (RFC 919), not assignable to a host |
| CIDR | "classless IP" | RFC 4632 prefix notation replacing Class A/B/C; enables route aggregation |
| VLSM | "subnetting subnets" | Variable-length masks so each subnet is sized to its host requirement |
| RFC 1918 | "private IPs" | 10/8, 172.16/12, 192.168/16 — non-routable on the public Internet |
| APIPA / link-local | "the 169 address" | RFC 3927 self-assignment when DHCP returns no OFFER; a failure signal |

## Further Reading

- RFC 791 — Internet Protocol (IPv4 header and 32-bit addressing).
- RFC 4632 — Classless Inter-Domain Routing (CIDR) address assignment and aggregation.
- RFC 1878 — Variable Length Subnet Table for IPv4 (the prefix/mask reference table).
- RFC 1918 — Address Allocation for Private Internets.
- RFC 6598 — IANA-Reserved IPv4 Prefix for Shared Address Space (100.64.0.0/10).
- RFC 3927 — Dynamic Configuration of IPv4 Link-Local Addresses (169.254.0.0/16).
- RFC 3021 — Using 31-Bit Prefixes on IPv4 Point-to-Point Links.
- RFC 919 / RFC 922 — Broadcasting Internet Datagrams (network and broadcast reservations).
- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 5 — Network Layer, CIDR and subnetting.
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, Chapter 4 — Addressing and CIDR.
