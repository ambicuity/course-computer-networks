# mDNS/Zeroconf Name Conflict and Link-Local Multicast

> Two laptops arrive at the same conference Wi-Fi. Both have the hostname `laptop.local` set by their users. Both connect to the same `10.0.0.0/24` link-local network. Both run `avahi-daemon` (Linux's mDNS responder) and announce themselves via multicast on `224.0.0.251:5353` (IPv4) or `ff02::fb:5353` (IPv6). Within milliseconds, both detect each other's mDNS response and start the **probe** cycle: each sends three mDNS queries for `laptop.local` 250 ms apart, separated by 250 ms of silence, and waits to see if anyone else answers. Both answer each other's probe — the canonical "name conflict" condition (RFC 6762 §9). When a host sees its own proposed name answered during the probe phase, it MUST pick a new name (RFC 6762 §9.2: "If a host receives a response to a probe ... it MUST NOT use the name"). On Linux, the default is to append `-2`, `-3`, etc., so the conflict becomes `laptop-2.local` and `laptop-3.local`. The user sees their hostname has silently changed, and a long-standing SSH key trust line (`known_hosts` had `laptop.local,10.0.0.42`) now fails. The diagnostic: `avahi-browse -art` to see all announced names, `avahi-resolve -n laptop.local` to see the resolved IP, and `tcpdump -i wlan0 -n port 5353` to see the probes. The fix is either (a) set a unique hostname on each laptop, (b) keep the duplicate and live with the `-2` suffix, or (c) split the link so the two hosts are on different subnets (mDNS is link-local, so it does not cross a router unless explicitly relayed).

**Type:** Lab
**Languages:** Python, avahi, dig
**Prerequisites:** Phase 12 DNS message format, multicast addressing (RFC 5771), the mDNS RFC 6762
**Time:** ~95 minutes

## Learning Objectives

- Diagnose an mDNS name conflict by capturing the probe cycle and identifying the duplicate answers: `avahi-browse -art` shows two hosts claiming the same name, the probe/announce cycle explains why, and `tcpdump port 5353` shows the wire-level exchange.
- Read the mDNS message format (RFC 6762 §18): the DNS header is standard, but the response bit is overloaded (mDNS responses do not have a separate query section), and TTLs are typically 75 seconds for hostnames, 4500 for SRV, 120 for A/AAAA.
- Explain the link-local scope: mDNS uses multicast group `224.0.0.251` (IPv4) and `ff02::fb` (IPv6), TTL 255, and packets are not forwarded by routers. To cross subnets, you need a relay (e.g. Avahi's `enable-reflector=1` or an `mdns-repeater` daemon).
- Distinguish three failure modes: (a) name conflict (two hosts claim the same name), (b) cache pollution (a stale answer persists for the 75/4500-second TTL), (c) link-local scope (a query on a different subnet returns nothing).
- Construct a Python mDNS probe generator (stdlib `socket` with `IP_MULTICAST_TTL=255`) that sends a probe and reads the answers, simulating the conflict detection logic.
- Recommend the right fix: rename one host, accept the `-2` suffix, or split the link / enable a relay.

## The Problem

The on-call SRE for a corporate laptop fleet gets a ticket: "My SSH to `laptop.local` stopped working after I came back from the offsite. My `~/.ssh/known_hosts` has `laptop.local,10.0.0.42 ecdsa-sha2-...` and now I'm getting `REMOTE HOST IDENTIFICATION HAS CHANGED`." The user is at the office on the corporate Wi-Fi. The corporate DHCP assigned 10.0.0.42, and the corporate mDNS responder is `avahi-daemon` on the laptop itself. The user used the office network last week without trouble.

The cause is that another laptop, also named `laptop.local`, joined the office Wi-Fi while the user was at the offsite. That laptop's mDNS responder announced itself. The user's own `avahi-daemon` saw the announcement, started the probe cycle, and detected the conflict. Per RFC 6762 §9.2, the user's daemon chose a new name: `laptop-2.local`. The user's `laptop.local` is no longer theirs; it belongs to the other laptop. The other laptop has the IP `10.0.0.43`. The user's SSH key trust line points to `laptop.local,10.0.0.42`, but the new `laptop.local` is `10.0.0.43`, and `ssh` correctly complains that the host key for `laptop.local` does not match the saved one.

The diagnostic is `avahi-browse -art`. The output shows two services on `laptop.local`: one on 10.0.0.42 (the user's, now actually `laptop-2.local`) and one on 10.0.0.43 (the imposter). The fix is either (a) rename one of the two laptops so the names are unique, or (b) ssh directly to the IP (`ssh user@10.0.0.42`) and accept the new hostname.

A second failure mode, more subtle: a printer joins the network, announces itself as `printer.local`, and an old cache entry from a previous printer at the same name sticks around for the TTL (75 seconds for a host A record, 4500 for an SRV). The new printer is unreachable until the cache expires. The fix is to clear the mDNS cache: `avahi-daemon --kill && avahi-daemon` or send a `cache-flush` query (RFC 6762 §10.2).

## The Concept

### mDNS address and scope

mDNS uses the multicast group `224.0.0.251` for IPv4 and `ff02::fb` for IPv6, port 5353. The IP TTL / multicast hop limit is 255 to ensure the packet does not leak across an L3 boundary. The link-local scope is intentional: mDNS is for "this network segment," not for the internet. A router that forwards an mDNS packet to another segment breaks the model — the cache on the other segment will be wrong when a host moves.

A relay (e.g., Avahi's reflector mode, or a dedicated `mdns-repeater` daemon) intentionally forwards mDNS across segments for specific use cases (e.g., AirPlay across VLANs, Chromecast discovery across subnets). The relay rewrites the source address so the receivers can tell the packet came from a different segment. The trade-off is the multicast TTL cap and the cache lifetime become meaningless.

### The mDNS message format

mDNS uses the standard DNS message format (RFC 1035) on UDP port 5353, with two notable RFC 6762 extensions:

- **Response bit overloaded**: in unicast DNS, a response has the QR bit set; in mDNS, a single packet can contain both a query and a response (a probe includes its own question, an answer can be unsolicited).
- **Known-Answer suppression**: a host that is about to send a query and already has an answer can include the answer in the query's "known-answer" section; peers that see their own answer in the known-answer section will not re-announce. This is how mDNS keeps multicast traffic low.

The TTLs are deliberately short: 75 seconds for a hostname A/AAAA, 4500 for an SRV, 120 for a service. The short TTLs force hosts to re-probe periodically, which is how conflicts surface promptly.

### The probe/announce cycle

The full mDNS state machine for a host claiming a name (RFC 6762 §8):

```
   Probing        |      Announcing       |      Established
   (3 queries,    |   (3-9 unsolicited     |   (record persists,
    250 ms apart) |    responses)         |    re-announced at
                  |                        |    TTL/2 intervals)
```

During the **probing** phase, the host sends three queries for its own proposed name. If any peer answers, the host has lost the race and must pick a new name (RFC 6762 §9). The **announcement** phase emits 3-9 unsolicited responses, 1 second apart, so any peer's cache is populated. The **established** phase persists the record, with re-announcements at TTL/2 to keep the cache warm.

### The conflict-resolution rules (RFC 6762 §9)

When a host detects a conflict (its own proposed name is in an answer), it must:

1. If the conflicting answer comes from a host whose IP is in the same link-local subnet as itself, the host MAY defend its name by sending a *defending* response, but only if it has good reason to believe the conflicting answer is stale (RFC 6762 §9.3 — the "unique" record tie-break).
2. Otherwise, the host MUST pick a new name.

The Linux `avahi-daemon` defaults to the safer behavior: it always picks a new name. To enable the more aggressive defense, set `enable-conflict-resolution=1` and the daemon will only defend if the IP matches the right record.

### The cache-flush query

RFC 6762 §10.2 defines a special "cache flush" mechanism: a host can include a `cache-flush` bit in an mDNS response to tell peers "the cache entries I am about to send you should replace any existing entries, not just be merged." This is how the OS X / iOS Bonjour stack flushes stale entries when a service moves. `avahi-browse -r` triggers a cache flush when re-resolving a name.

### How `tcpdump` exposes mDNS

`tcpdump -i wlan0 -n port 5353` shows the mDNS traffic. The packets are standard DNS format, so `dig -p 5353 @224.0.0.251 laptop.local` works to send a query. To filter, use `tcpdump -i wlan0 -n 'udp port 5353 and udp[8:2] & 0x8000 == 0'` to select queries only, or `udp[8:2] & 0x8000 != 0` to select responses.

### How the simulator models this

`code/main.py` simulates the mDNS probe/announce state machine for a configurable number of hosts. The user picks a scenario (`--scenario conflict`, `--scenario stale_cache`, `--scenario relay`, `--scenario clean`), and the simulator emits the probe cycles, the conflict detection, and the verdict.

## Build It

1. **Run two avahi daemons in two namespaces.** `ip netns add h1 && ip netns add h2`, run `avahi-daemon` in each with a `host-name=laptop.local` in `/etc/avahi/avahi-daemon.conf`.
2. **Capture the probe cycle.** `tcpdump -i any -n port 5353` while both daemons start. Confirm the three probes 250 ms apart and the conflict.
3. **Run `avahi-browse -art`.** Confirm two services on `laptop.local` and the renamed `laptop-2.local`.
4. **Run the simulator.** `python3 code/main.py --scenario conflict` should print the same probe/announce state machine.
5. **Ship the runbook.** A one-page runbook listing the four diagnostic commands and the three fixes.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| List mDNS services | `avahi-browse -art` | All services with their IPs and ports |
| Resolve a name | `avahi-resolve -n laptop.local` | Returns `laptop.local  10.0.0.42` |
| See probes | `tcpdump -i wlan0 -n port 5353` | Three queries 250 ms apart, conflict answers, then renames |
| Force a cache flush | Send an mDNS query with the cache-flush bit | Stale entries replaced |
| Confirm link-local scope | `dig -p 5353 @224.0.0.251 laptop.local` from another subnet | No reply (packet is not forwarded) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **mDNS conflict triage runbook** with the diagnostic commands and the three fixes.
- A **before/after capture** of the probe cycle showing the conflict and the rename.

Start from `outputs/prompt-mdns-zeroconf-name-conflict-link-local.md`.

## Exercises

1. Two hosts claim the same name. Host A's IP is `10.0.0.42` and host B's IP is `10.0.0.43`. Both are on the same link. Per RFC 6762 §9.3, can host A defend its name with a tie-break? Why or why not?
2. The mDNS TTL for an SRV record is 4500 seconds. A printer at `printer.local` is unplugged and replaced with a new printer at the same name. How long until the old cache entry expires, and what is the corrective action?
3. `avahi-daemon` is configured with `enable-reflector=1`. A query from subnet A to a service on subnet B succeeds. What is the security trade-off?
4. An mDNS query has the QR bit set (it's a response) but also includes a question. What is the meaning, and which RFC section defines it?
5. `tcpdump -i wlan0 -n 'udp port 5353 and udp[8:2] & 0x7800 == 0x4000'` filters which mDNS packets? Decode the flags.
6. A user is on a guest Wi-Fi that is on subnet A. They want to print to a printer on the corporate subnet B. mDNS does not work. List the two enabling steps (a relay, or mDNS gateway) and the security implication of each.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| mDNS | "Bonjour / Avahi" | Multicast DNS (RFC 6762); DNS over UDP 5353 to multicast group 224.0.0.251 / ff02::fb |
| Probe | "Is the name taken?" | Three mDNS queries 250 ms apart; if any peer answers, the proposed name is taken |
| Announce | "I have this name" | 3-9 unsolicited responses, 1 s apart, so peers' caches are populated |
| Cache flush | "Forget old entries" | RFC 6762 §10.2: a bit in an mDNS response telling peers to replace, not merge, cache entries |
| `.local` | "Zeroconf domain" | The reserved TLD for link-local mDNS (RFC 6762 §3) |
| Link-local scope | "Stays on the link" | mDNS is not routed; a router that forwards the packet breaks the model |
| Avahi reflector | "mDNS relay" | A daemon (Avahi's `enable-reflector=1`) that forwards mDNS across segments |
| TTL 75 / 4500 / 120 | "mDNS TTLs" | The standard mDNS TTLs in seconds: A/AAAA 75, SRV 4500, PTR/TXT 120 (RFC 6762 §10) |

## Further Reading

- RFC 6762 — Multicast DNS (mDNS message format, probe/announce cycle, conflict resolution)
- RFC 6763 — DNS-Based Service Discovery (the PTR/SRV/TXT records used in mDNS service announcements)
- RFC 5771 — IANA Guidelines for IPv4 Multicast Address Assignments (224.0.0.0/24 scope)
- `avahi-daemon(8)`, `avahi-browse(1)`, `avahi-resolve(1)` man pages
- `tcpdump(8)` — UDP port 5353 capture, byte-offset filter syntax
- `dig(1)` — `-p` flag for non-standard port (used to query mDNS multicast)
- IETF `dnssd` working group — ongoing extensions to service discovery
