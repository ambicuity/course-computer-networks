# Dual-Stack SLAAC and DHCPv6 Misconfig

> A campus rolls out dual-stack on VLAN 42. The router's Router Advertisement carries prefix `2001:db8:cafe::/64` with `A=1, M=0`; a separately installed ISC `dhcpd` server on the same L2 segment hands out addresses from `2001:db8:face::/64` with `M=1`. About half the hosts (macOS, Windows 10 with IPv6 enabled) honour the SLAAC address and reach the Internet; the other half (Ubuntu 22.04 with `ipv6 dhcp enabled` per NetworkManager) lease a DHCPv6 address from the rogue pool and silently lose upstream connectivity. The `M` flag is the Managed flag (RFC 4861 §4.2), the `O` flag is OtherConfig (RFC 4861 §4.2), and the `A` flag is Autonomous (RFC 4862 §5.5.1). Source-address selection (RFC 6724 §5) ranks the host's candidates by longest-match against the destination; when the destination is also in `2001:db8:cafe::/64` the SLAAC address wins, but for any global destination the unrouted DHCPv6 address sometimes wins because the local policy table prefers `2001:db8:face::/64` over `2001:db8:cafe::/64` on a host whose administrator once manually added a `prefixpolicy` rule. The fix is to align the DHCPv6 pool to the RA prefix and set `M=0` everywhere on segments where DHCPv6 is only needed for DNS (stateless DHCPv6, `A=1, O=1, M=0` per RFC 3736). This lab reproduces both the two-prefix misconfig and the more subtle "stable-privacy prefix ordering" misconfig that affects RFC 7217 hosts, and walks the diagnostic from `rdisc6` output to `ip -6 route` to the lease file.

**Type:** Lab
**Languages:** Python, shell, Wireshark, ndpmon
**Prerequisites:** Phase 9 IPv6 lesson, Phase 17 lesson 09 (NAT hairpin), RFC 4861/4862/6724/8415
**Time:** ~95 minutes

## Learning Objectives

- Decode Router Advertisement flags (`M`, `O`, `A`) and predict which of the three configuration modes (SLAAC, stateless DHCPv6, stateful DHCPv6) a host will use; cite the RFC for each flag.
- Diagnose the two-prefix misconfig by reading `rdisc6 eth0` output, the `dhcpd.leases` file, and the host's `ip -6 addr` to find the unrouted DHCPv6 prefix.
- Apply RFC 6724 source-address selection rules: same-prefix longest match, scope, label, then policy table, and predict which source a dual-prefix host uses for a given destination.
- Compute a stable-privacy address (RFC 7217) for a given interface identifier and `net_iface` secret and verify it does not leak the MAC.
- Build a Python simulator that walks the host's configuration state machine under each `(M, O, A)` combination and produces a table of host behaviour.
- Produce a dual-stack commissioning checklist that aligns the RA prefix, the DHCPv6 pool, and the upstream router's routing table, with explicit per-VLAN flag values.

## The Problem

The on-call ticket reads: "Users on VLAN 42 in Building C report that 'some websites' don't load. IPv4 always works. Traceroute to a dual-stack destination like `2606:4700:4700::1111` (Cloudflare DNS) dies after the first hop for some users, works for others, and is slow for the rest." The network team's first response is to check the router: it shows the prefix `2001:db8:cafe::/64` advertised, and `show ipv6 route` confirms the prefix is in the upstream table. They escalate to the platform team, who owns the host configuration. The platform team sees nothing wrong on the workstations: every host has at least one IPv6 address, IPv4 works, and `ping6 2001:db8:cafe::1` (the router) succeeds from every host.

The on-call engineer who finally resolves the ticket does three things in order. First, `rdisc6 eth0` from an affected host: the output shows `2001:db8:cafe::/64` with `A=1, M=0, O=0`, which is a pure SLAAC segment — no DHCPv6 involvement. Second, the engineer `tcpdump`s UDP/546 on the segment and sees `dhcp6 solicit` from the host followed by `dhcp6 advertise` from a *second* server at `2001:db8:face::53` (not the router) offering `2001:db8:face::cafe:beef`. That is the rogue DHCPv6 server that was installed for a separate IoT experiment and never decommissioned. Third, `ip -6 route show table all | grep 2001:db8:face` shows the unrouted prefix is in the host's routing table with metric 100, the same metric as the SLAAC route. RFC 6724 prefers the prefix that appears first in the policy table — and on this Ubuntu host, the `face::/64` was added to `prefixpolicy` *after* `cafe::/64` (later in the file = lower precedence) so it actually loses, but other hosts (a CentOS 7 box that was upgraded to use NetworkManager's older IPv6 ordering) have the opposite ordering and pick `face::`. Half the hosts use the unrouted prefix, the other half use the routed prefix, and a small minority that are doing only IPv4 in DNS lookup still manage to work because their AAAA queries return multiple addresses and Happy Eyeballs (RFC 6555) races IPv4.

The deeper diagnostic lesson is that the symptom is "intermittent IPv6" not "no IPv6". The hosts *believe* they have working IPv6 — they have an address, they have a route, and `ping6` to the L2 router works because the L2 router is in *both* prefixes. The unrouted prefix is reachable hop-by-hop on the L2 segment, so `traceroute6 2001:db8:cafe::1` succeeds but `traceroute6 2606:4700:4700::1111` fails: the second hop is the upstream router, which has no route for `2001:db8:face::/64` and emits ICMPv6 Destination Unreachable (`type=1, code=0`, no route to destination) that the host never sees because the response goes to the unrouted source.

The `code/main.py` simulator implements the host-side state machine and lets you reproduce both the half-broken symptom and the all-broken symptom by toggling a single flag.

## The Concept

### The RA flags drive three distinct configuration modes

The Router Advertisement is an ICMPv6 type 134 message (RFC 4861 §4.2). Three flags in the RA determine how the host forms its address and whether it consults DHCPv6:

| Flag | Name | RFC | Effect on host |
|---|---|---|---|
| `M` | Managed | 4861 §4.2 | If 1, host uses stateful DHCPv6 for address assignment (replaces SLAAC) |
| `O` | OtherConfig | 4861 §4.2 | If 1, host uses stateless DHCPv6 for non-address options (DNS, domain search list, NTP) |
| `A` | Autonomous | 4861 §4.2 / 4862 §5.5.1 | If 1, host uses SLAAC to form an address from the advertised prefix |

The three useful modes derived from these flags are:

- `M=0, O=0, A=1`: SLAAC only. Host forms an address from the prefix, gets DNS from RA's RDNSS option (RFC 8106) if present, no DHCPv6.
- `M=0, O=1, A=1`: Stateless DHCPv6 (RFC 3736). Host forms an address from SLAAC, queries DHCPv6 only for DNS and other options.
- `M=1`: Stateful DHCPv6 (RFC 8415). Host addresses come from the server; if `A=1` the host may *also* SLAAC the prefix (RFC 4861 leaves this implementation-defined), but on macOS, Windows, and current NetworkManager-managed Linux the SLAAC path is suppressed when `M=1`.

The fourth combination (`M=0, O=0, A=0`) is meaningless for the host: it must keep the link-local and cannot form a global address. Hosts that see this combination stay on link-local only, which is the right fallback but is rarely what an operator intends.

### A real RA packet decoded

The minimum RA in Wireshark's Packet Bytes pane, captured with `rdisc6 -d eth0` on Linux, looks like:

```
ff: 02 00 00 00 00 40 00 00  ICMPv6 Router Advertisement (134)
     |--type=134, code=0, checksum, hop limit=64, flags=0---|
02: 00 00 00 00 00 00 00 00  Router Lifetime = 0  (NOT a default router)
02: 38 00 00 00 00 00 00 00  Reachable Time = 14336 ms
02: 00 00 03 e8 00 00 00 00  Retrans Timer = 1000 ms
    --- options ---
02: 01 00 00 00 00 00 00 00  Source Link-Layer Address (option 1)
02: 03 20 40 00 00 00 00 00  Prefix Information (option 3)
     20 10 0d b8 0c af e0 00  prefix = 2001:db8:cafe::
     00 00 00 00 40 00 00 00  /64, A=1, L=0 (RFC 4861 §4.6.2)
```

The two bytes that matter for this lab are the flags `R|O|Reserved|M|O|Reserved|A|Reserved` in the prefix option: `0x40` here is `A=1` with `L=0` (on-link). If the byte were `0xc0` it would mean `A=1, L=1` (SLAAC + use the prefix as on-link). If the byte were `0x80` it would mean `A=0, L=1` (no SLAAC, but the prefix is on-link) — used to advertise a prefix for routing only. RFC 4861 §4.6.2 defines these bits precisely; the simulator uses the same bit field.

### Source-address selection ranks candidates deterministically

RFC 6724 §5 defines the rules the host uses to pick a source address from its table of candidates. The rules, in order, are:

1. Prefer same address (skip — usually no match).
2. Prefer appropriate scope: matching scope of destination, else narrower, else wider.
3. Avoid deprecated addresses (RFC 4862 §5.5.4 deprecated prefix lifetime).
4. Prefer home addresses (Mobile IPv6, RFC 6275).
5. Prefer outgoing interface (the source must be on the outgoing interface).
6. Prefer matching label: the source's prefix and the destination's prefix share an entry in the `prefixpolicy` table (RFC 6724 §2.1).
7. Prefer matching prefix: longest common prefix with destination.
8. Prefer temporary addresses (RFC 4941 privacy).
9. Use longest matching prefix length between source and destination (note: the *source* candidate here, not the destination).

The "two-prefix misconfig" hits rule 6. The host has two addresses, one in `cafe::/64` and one in `face::/64`. The destination is in `cafe::/64` for a *local* destination, in which case rule 7 (matching prefix) picks the SLAAC address. For a *global* destination (Cloudflare, Google, etc.), rule 7 falls through and rule 6 (matching label in prefixpolicy) is the tiebreaker. If the host's prefixpolicy lists `face::/64` *before* `cafe::/64`, the unrouted address wins, the packet goes to the local router, the local router has no route for `face::/64`, and ICMPv6 unreachables are generated that the host never reads because they are returned to the unrouted source.

### SLAAC address formation: EUI-64 vs RFC 7217 stable privacy

When `A=1`, the host forms an address by appending a 64-bit interface identifier (IID) to the prefix. Two methods:

- **EUI-64** (RFC 4291 Appendix A): take the 48-bit MAC, insert `ff:fe` in the middle, flip bit 6 of the first byte (the U/L bit). The IID reveals the MAC — privacy concern.
- **RFC 7217 stable privacy**: the IID is a cryptographic hash of `(prefix, net_iface_secret, counter)`, generated with SHA-256, then truncated to 64 bits. The IID does NOT reveal the MAC and is stable across reboots as long as the secret and prefix stay the same. Current macOS, Windows 10+, and NetworkManager 1.18+ default to RFC 7217.

The simulator implements both so you can see that an EUI-64 host's IID tracks the MAC across networks, while an RFC 7217 host's IID is uncorrelated.

### The "right" RA on a routed /64

For a segment where the operator wants pure SLAAC:

```text
R flag: 0 (not a default router advertisement — fine, RA is not "I am a router" anyway)
M flag: 0
O flag: 0
A flag: 1, L flag: 1, R flag: 0
Prefix: 2001:db8:cafe::/64, valid_lifetime=2592000 (30d), preferred_lifetime=604800 (7d)
RDNSS:  2001:db8:cafe::53, lifetime=604800   (RFC 8106)
MTU:    1500
```

If DNS is centralised and the operator wants to push it via DHCPv6, set `O=1` and add a `dhcp6 -S -c /etc/dhcpd6.conf` server. If the operator wants full stateful (e.g. for accounting), set `M=1` and disable SLAAC on the host (`sysctl net.ipv6.conf.eth0.accept_ra=0` to be sure, although RFC 4861 says the host should not SLAAC when M=1).

### How the simulator models this

`code/main.py` implements a host-side state machine. Each `Host` has a list of candidate addresses, a prefixpolicy table, and a `mode` (`slaac`, `stateless_dhcpv6`, `stateful_dhcpv6`). You choose a `(M, O, A)` triple, a DHCPv6 server (with prefix and `stateful` flag), and a list of hosts; the simulator produces each host's final address set, then runs an RFC 6724 selection for a given destination and prints which address wins and whether that prefix is routed. The `--scenario` flag picks one of three scenarios: `pure_slaac` (works), `two_prefix_misconfig` (the ticket), `rogue_dhcpv6_with_M1` (a more aggressive version of the same failure).

## Build It

1. **Set up a lab segment.** Two Linux VMs on the same bridge. VM1 runs `radvd` (or uses the in-kernel `rdisc6` + a Python RA emitter). VM2 runs `isc-dhcp-server` with a /64 from a *different* prefix. A third VM is the host under test.
2. **Capture the RA.** `tcpdump -ni eth0 -vvvv -XX 'icmp6 and ip6[40]==134'` and identify the `M`, `O`, `A` flags in the prefix option byte.
3. **Capture DHCPv6.** `tcpdump -ni eth0 -vvvv 'udp port 546 or 547'`. Note the `server identifier` option and the `IA_NA` / `IA_PD` options in the server's `advertise`.
4. **Run the simulator.** `python3 code/main.py --scenario two_prefix_misconfig` and compare the simulator's verdict to the host's actual `ip -6 route get` for a global destination.
5. **Fix the misconfig.** Align DHCPv6 pool to `2001:db8:cafe::/64`, restart `radvd` and `isc-dhcp-server`, repeat step 2 and 4.
6. **Ship the runbook.** A dual-stack commissioning checklist that explicitly aligns RA prefix, DHCPv6 pool, and upstream router routing.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read RA flags | `rdisc6 eth0`, `tcpdump icmp6` | One prefix with A=1, M=0 (or M=1 with stateful DHCPv6) |
| Read DHCPv6 lease | `dhcpd6.leases`, `dhcp6ctl` | Prefix == RA prefix; `ia-na` lifetime sensible |
| Find rogue server | `rdisc6` + `dhcp6 -n -d` | Only one source of `dhcp6 advertise`; matches authorised server IP |
| Trace selection | `ip -6 route get 2606:4700:4700::1111` | Source in routed prefix; matches what RFC 6724 predicts |
| Confirm break | `traceroute6 2606:4700:4700::1111` from a wrong-prefix host | Hop 1 replies, hop 2 times out (no upstream route for face::) |
| Validate fix | Re-run traceroute after aligning prefixes | Path reaches hop 2 (upstream) and exits to global |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page **dual-stack commissioning checklist** that maps each VLAN's `(M, O, A)` to the expected DHCPv6 server behaviour and the prefixpolicy table state.
- A monitoring probe (Python + `rdisc6` or a libnetconf validator) that asserts (a) the RA prefix matches the DHCPv6 pool prefix and (b) every DHCPv6 server on the segment has a MAC in the authorised server list.

Start from `outputs/prompt-dual-stack-slaac-dhcpv6-misconfig.md` and paste in the actual `rdisc6` and `dhcpd6.leases` excerpts from your capture.

## Exercises

1. Configure the router for stateless DHCPv6 (`A=1, O=1, M=0`) and verify hosts still get DNS via DHCPv6 while addresses come from SLAAC. Capture both the RA and the `dhcp6 information-request` exchange.
2. Inject a second RA from a misconfigured downstream router (`radvd -m logfile -l`) and observe duplicate-prefix warnings in `ndpmon` (or in `ip monitor`).
3. Show that an RFC 7217 stable-privacy address does not change when the host moves between two prefixes on the same interface, but a SLAAC address *does* change.
4. Reproduce the IPv4-works-but-IPv6-fails scenario for an AAAA-only service (e.g. `dns.google`) and explain why Happy Eyeballs (RFC 6555) does not always save you when the host's only IPv6 address is unrouted.
5. Write a monitoring rule that compares the RA prefix against the DHCPv6 lease pool every hour and raises an alert if they diverge.
6. Set `accept_ra=0` on a Linux host while `M=1` is advertised and explain why the host still uses DHCPv6 (RFC 4861 §6.3.4 vs Linux kernel behaviour — `accept_ra` controls RA acceptance, not DHCPv6 use).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SLAAC | Autoconfig | Stateless Address Autoconfiguration; host derives address from RA prefix using EUI-64 (RFC 4291 App A) or RFC 7217 stable privacy |
| DHCPv6 | IPv6 DHCP | Stateful or stateless lease of addresses and options from a server; RFC 8415 supersedes RFC 3315 |
| Router Advertisement | ICMPv6 134 | Message from router to all nodes carrying prefix, flags M/O/A, MTU, and RDNSS (RFC 4861 §4.2) |
| M flag | Managed | RA flag 1; if set, host uses stateful DHCPv6 for addresses (RFC 4861 §4.2) |
| O flag | Other | RA flag 1; if set, host uses stateless DHCPv6 for non-address options (RFC 4861 §4.2) |
| A flag | Autonomous | RA flag 1; if set, host uses SLAAC for the advertised prefix (RFC 4862 §5.5.1) |
| RDNSS | Recursive DNS | RA option (RFC 8106) carrying DNS server addresses and lifetime |
| RFC 6724 | Address selection | Algorithm ranking candidate source addresses by scope, label, prefix, and policy table |
| Stable privacy | RFC 7217 | Cryptographic IID generated from (prefix, secret, counter); hides the MAC |
| Happy Eyeballs | RFC 6555 | Algorithm that races IPv4 and IPv6 to mask one-sided failure; does not fix unrouted IPv6 |

## Further Reading

- RFC 4291 — IP Version 6 Addressing Architecture (EUI-64 IID formation)
- RFC 4861 — Neighbor Discovery for IP version 6 (IPv6) (RA flags, M/O/A)
- RFC 4862 — IPv6 Stateless Address Autoconfiguration (SLAAC, A flag)
- RFC 6724 — Default Address Selection for Internet Protocol Version 6 (IPv6) (source-address selection rules)
- RFC 7217 — A Method for Generating Semantically Opaque Interface Identifiers (stable privacy)
- RFC 8106 — IPv6 Router Advertisement Options for DNS Configuration (RDNSS)
- RFC 8415 — Dynamic Host Configuration Protocol for IPv6 (DHCPv6) (supersedes 3315)
- RFC 3736 — Stateless Dynamic Host Configuration Protocol (IPv6) Service (stateless DHCPv6 mode)
- Wireshark display filters: `icmpv6.type == 134` (RA), `dhcpv6` (DHCPv6 summary)
