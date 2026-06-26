# ARP Spoofing and Duplicate IP Conflict

> Two laptops on the same subnet behave as if they have swapped souls: each sends packets to the right IP, but the wrong MAC answers on the other side. The default gateway itself is hijacked. The user's view: half the Web loads from the genuine server and half loads from a man-in-the-middle. The administrator's view: `arp -a` shows the same IP mapped to two different MAC addresses within a second, then the second MAC "wins." This lesson dissects gratuitous ARP, the ARP cache, the L2 hunt that follows a deliberate duplicate, and the synthetic trace generator that lets you rehearse the detection logic against a deterministic event log. By the end you can tell an ARP storm from a DHCP race from a malicious L2 actor, and you can name the exact `tcpdump` filter that catches each one.

**Type:** Lab
**Languages:** Python (stdlib only), tcpdump, arping, arpwatch
**Prerequisites:** Phase 04 IPv4, Phase 05 ARP, Phase 06 Ethernet switching, Phase 12 HTTP semantics
**Time:** ~110 minutes

## Learning Objectives

- Explain ARP request/reply semantics, the cache, and gratuitous ARP, and describe why gratuitous ARP is the single vector that breaks L2-to-L3 binding.
- Recognize a duplicate IP conflict in the kernel log (`kernel: arp: <IP> moved from <MAC1> to <MAC2>`) and distinguish it from a switch loop or DHCP race.
- Detect an ARP spoofing attack from `arpwatch` syslog signatures: `flip flop`, `changed ethernet address`, and `reaper repair`.
- Apply Layer-2 mitigations: `arp_filter`, `rp_filter`, dynamic ARP inspection (DAI), and port security.
- Build a synthetic ARP trace generator that emits gratuitous, request, reply, and conflict events in a deterministic time order, and a parser that flags anomalies.
- Construct a runbook in `outputs/` that names the exact command and expected output for each ARP-related symptom.

## The Problem

A mid-sized SaaS company has two office VLANs behind the same router. Yesterday at 11:14, the on-call engineer received a ticket: "GitHub is loading but the diffs are from a different repository." Investigation reveals that the laptop's `arp -an` shows the default gateway `10.0.0.1` mapped to `aa:bb:cc:00:11:22` — but the *real* gateway is at `aa:bb:cc:dd:ee:ff`. The attacker is sending unsolicited ARP replies (gratuitous ARP) that bind the gateway IP to the attacker's MAC, allowing them to intercept and forward all traffic. Half the connections work because the attacker has a forwarding path; half do not because they fail to forward them.

Simultaneously, in a different part of the office, a static IP address on a server (`10.0.0.50`) is duplicated by a developer laptop. Every few seconds, the kernel emits `arp: 10.0.0.50 moved from aa:bb:cc:11:22:33 to aa:bb:cc:44:55:66`. SSH connections to `10.0.0.50` reach whichever machine answered most recently, then fail when the other answers. The `code/main.py` in this lesson replays both failure modes — the spoof and the duplicate — in a single deterministic event log.

## The Concept

### The ARP protocol in 60 seconds

ARP (Address Resolution Protocol, RFC 826) translates an IPv4 address to the MAC address of the next hop on the local L2 segment. The protocol is two message types:

- **ARP request** (op=1): "Who has IP `10.0.0.5`? Tell `10.0.0.7`." Sent to the broadcast MAC `ff:ff:ff:ff:ff:ff`.
- **ARP reply** (op=2): "`10.0.0.5` is at `aa:bb:cc:11:22:33`." Sent as a unicast to the requester.

A normal interaction: host A wants to reach `10.0.0.5`. A broadcasts "who has 10.0.0.5?" The owner of 10.0.0.5 unicast-replies with its MAC. A caches the binding for 15–60 seconds (kernel tunable `gc_stale_time`) and transmits.

**Gratuitous ARP** is a special case where a host broadcasts an ARP reply for its *own* IP. Two reasons to do this:
1. Announce a new IP-MAC binding (e.g., after a NIC comes up, or after IP reassignment) so the rest of the segment can update their caches without waiting for the next request.
2. Announce an IP that just moved to a new host (e.g., a failover, or a malicious takeover).

Gratuitous ARP is also the *only* mechanism that allows an attacker to poison a victim's ARP cache without first receiving a request — the attacker simply broadcasts the victim's IP bound to the attacker's MAC, and the victim's kernel, upon seeing a reply from the IP it cares about, updates its cache.

### The kernel's view of an ARP conflict

When a host receives an ARP packet claiming that some IP `X` is at MAC `M`, the kernel compares it to its current cache entry for `X`:

- If the cache has `X -> M_old` and the packet says `X -> M_new` where `M_new != M_old`, the kernel updates the cache and emits:

  ```
  kernel: [ARP] 10.0.0.50 moved from aa:bb:cc:11:22:33 to aa:bb:cc:44:55:66
  ```

- If the cache has `X -> M` and the packet also says `X -> M` (i.e., the local host's own IP is being claimed by another MAC), the kernel logs a conflict and (depending on `arp_ignore`) drops the packet:

  ```
  kernel: arp: 10.0.0.50 conflict: both aa:bb:cc:11:22:33 and aa:bb:cc:44:55:66 in use
  ```

The `arp_ignore` and `arp_announce` sysctls (and their IPv6 equivalents `ipv6.conf.*.accept_ra` and the ndisc layer) tune how the kernel responds to such events.

### The four ARP failure modes

A network engineer is rarely asked "what is ARP?" — they are asked "is this an ARP problem?" The four modes are:

| Mode | Trigger | Signature | Mitigation |
|------|---------|-----------|------------|
| **Duplicate IP** | Two hosts configured with the same static IP | Kernel `moved` log, intermittent connectivity to the IP, `arp -an` shows two MACs that flip every few seconds | Find the duplicate, change one host, or use DHCP reservations |
| **ARP spoofing / poisoning** | Attacker sends gratuitous ARP for the gateway | `arpwatch: flip flop` (rapid alternation) or `changed ethernet address` (single shift) | DAI on the switch, port security, static ARP for critical hosts |
| **ARP storm** | Bridging loop, NIC failure, or a chatty device broadcasting at L2 | `ifInErrors` skyrockets, switch CPU maxed, intermittent loss for everyone on the VLAN | STP, broken-loop detection, isolate the offender |
| **Stale cache after failover** | A NIC comes up with a new MAC for an IP that was on a failed host | After a short period, traffic resumes to the right place; no log entries from the new host | Gratuitous ARP from the new owner (which most clusters do), or wait for the cache to expire |

The detective skill is recognizing which one is happening. The synthetic trace in `code/main.py` exercises the first two; the runbook exercise covers the third and fourth.

### Detection: `arpwatch` and the `flip flop` signature

`arpwatch` (a Lawrence Berkeley National Laboratory tool, in most Linux distros as `arpwatch` package) keeps a database of IP-to-MAC bindings seen on the local segment. When a binding changes, it logs to syslog with a fixed vocabulary:

- `new station` — a new IP-MAC pair has been seen.
- `changed ethernet address` — an existing IP has been seen at a new MAC exactly once.
- `flip flop` — an IP has toggled between two MACs more than once. This is the canonical signature of a duplicate IP or an active ARP attack.
- `reaper repair` — an old binding has been re-observed after a long absence.

A single `changed ethernet address` is a graceful failover. A `flip flop` is an active problem. The `code/main.py` simulator emits the syslog strings so you can practice reading them.

### Mitigation in depth

The defensive layers, ordered by closeness to the host:

1. **Kernel sysctls** — `net.ipv4.conf.<iface>.arp_ignore` and `arp_announce` control when a host replies to ARP requests and how it announces. They do not stop a determined attacker, but they prevent the host from contributing to the noise.
2. **Reverse-path filtering (`rp_filter`)** — When mode=1, the kernel drops a packet whose source IP is reachable on a different interface than the one it arrived on. This catches asymmetric routing but is not a complete ARP defense.
3. **Static ARP entries** — `arp -s <IP> <MAC>` pins an entry in the cache. Useful for gateways, impractical for large networks.
4. **Dynamic ARP Inspection (DAI)** — A switch feature. The switch intercepts ARP packets and validates each IP-MAC binding against a trusted database (typically built from DHCP snooping). Spoofed ARPs are dropped at the wire. The DAI trust boundary must be on the DHCP-trusted port.
5. **Port security with MAC binding** — A switch feature. The port is configured to allow only a specific MAC, and an alert or shutdown is triggered on violation.
6. **802.1X** — The strongest, but heaviest. Identity-based port authentication.

### What you should not do

It is tempting to "fix" ARP with encrypted overlays (VPN, IPsec, WireGuard) — and indeed, WireGuard or HTTPS defeats the *content* theft of an ARP spoof. But the attacker still has the L2 position and can still drop, delay, or reset traffic. The L2 attack must be stopped at L2.

## Build It

The `code/main.py` in this lesson is a synthetic ARP trace generator and a rules-based anomaly detector. It is stdlib only; it does not sniff live traffic. Run it and study the output:

1. **Read** `code/main.py` end to end. Notice the `ARPPacket` dataclass (frozen, with `op` as a `Literal[1, 2]`), the `L2Segment` class that owns a participant list and a time-ordered event log, and the `ARPDetector` class that scans the log for `flip flop`, `changed ethernet address`, and conflict signatures.
2. **Run** it: `python3 code/main.py`. You will see a 10-second synthetic trace in which (a) two clients each have a static IP, (b) client B's IP is duplicated, and (c) a separate attacker emits gratuitous ARP for the gateway. The detector prints which signatures fired.
3. **Modify** the script to add a third scenario: an ARP storm from a misbehaving NIC. Generate 5000 ARP packets per second from one source, and watch how `ifInErrors` (a synthetic counter) climbs.
4. **Add** a `static-arp` scenario where the gateway has a static ARP entry. The attacker's gratuitous ARP should fail to update the static entry, demonstrating why static ARP is a defense for critical hosts.

The script is deterministic: the random seed is fixed, so the trace is reproducible. This is the property that makes it useful for rehearsals and for automated tests.

## Use It

| Symptom | Diagnostic Command | Expected Output |
|---------|-------------------|-----------------|
| Intermittent connectivity to a host | `arp -an` | Two MACs listed for the same IP, alternating each time you re-run |
| Kernel reports a move | `journalctl -k -g arp` | `arp: <IP> moved from <MAC1> to <MAC2>` |
| Watch for changes | `sudo arpwatch -i eth0 -f /var/lib/arpwatch/arp.dat` | `flip flop` in syslog when an IP toggles |
| Sniff gratuitous ARP | `tcpdump -i eth0 -nn -e 'arp' | grep 'is-at'` | Lines like `who-has 10.0.0.1 tell 10.0.0.7` and `reply 10.0.0.1 is-at aa:bb:cc:00:11:22` |
| Find the sender of spoofed ARP | `tcpdump -i eth0 -nn -e 'arp src host <attacker-mac>'` | All ARP packets from the attacker's MAC, regardless of claimed source IP |
| Per-host bindings | `ip neigh show` | Same as `arp -an` but with explicit `lladdr`, `dev`, `state` |
| Inspect interface stats | `ip -s link show eth0` | `RX errors` climbs under ARP storm |
| Detect DAI violation | `show ip arp inspection statistics` (on managed switch) | Counter for dropped ARP packets |
| Pin a critical gateway | `sudo arp -s 10.0.0.1 aa:bb:cc:dd:ee:ff` | Static entry persists across `arp -d` until manually removed |
| Block suspicious IP at L3 | `sudo iptables -I INPUT -s 10.0.0.50 -j DROP` | New connections from the duplicate IP fail |

## Ship It

The `outputs/prompt-arp-spoofing-duplicate-ip-conflict.md` file is your deliverable. It must contain:

1. A 6-line decision tree: "If you see the kernel `moved` log, run `arpwatch` for 30 seconds. If `flip flop` fires, two hosts are claiming the IP. Use `tcpdump -i eth0 -nn -e 'arp'` to find the second MAC, then walk to the switch and disable the port. If `changed ethernet address` fires once and stops, it is a graceful failover. If the gateway's MAC is wrong, suspect ARP spoofing and apply DAI."
2. A table of the four ARP failure modes (duplicate IP, spoof, storm, stale cache) with the one signature that uniquely identifies each.
3. A list of three sysctl values that change on a host that wants to refuse gratuitous ARP and explain why each is not a complete defense.

## Exercises

1. **Gratuitous ARP semantics**: Why does a host send gratuitous ARP when its NIC comes up? What is the *op* field set to (1 or 2)? What is the destination MAC? What happens if the destination is unicast instead of broadcast?
2. **Flip-flop timing**: An attacker sends gratuitous ARP for the gateway every 10 seconds. A legitimate client sends a normal ARP request for the gateway every 60 seconds (cache miss). Assuming the client kernel does not have an entry, who wins, and when does the legitimate MAC "reappear" in the cache? (Hint: the kernel updates on *any* matching reply, but cache entries have a TTL.)
3. **DAI trust boundary**: A switch runs DHCP snooping. The DHCP server is on port 1 (trusted). A client on port 2 sends an ARP reply claiming to be the gateway. Will DAI drop the reply? Why? Now consider a host that has a static IP outside of DHCP — does DAI cover it?
4. **Static ARP limits**: A network operator pins the gateway's IP-MAC with `arp -s`. An attacker sends gratuitous ARP. Why does the static entry survive? What about `arp -d`? When does the static entry actually disappear?
5. **IPv6 counterpart**: How does an attacker poison the IPv6 neighbor cache, and what is the equivalent of `arpwatch` for IPv6? (`ndisc`/`ndpmon`/`ndppd`/`ip -6 neigh show`).
6. **Synthetic trace analysis**: The `code/main.py` emits a `flip flop` between `aa:bb:cc:11:22:33` and `aa:bb:cc:44:55:66` for IP `10.0.0.50`. If you see this signature in production, what is your first three actions before touching the switch?

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| Gratuitous ARP | Free ARP | An ARP reply broadcast by a host about its own IP, used to update caches or to poison them |
| ARP spoofing | ARP spoof | A L2 attack where an attacker sends gratuitous ARP claiming another host's IP, redirecting traffic |
| `flip flop` | A switch term | `arpwatch` signature: an IP-MAC binding that has toggled more than once within a short window |
| DAI | Dynamic ARP Inspection | Switch feature that drops ARP packets whose IP-MAC binding is not in a trusted database |
| DHCP snooping | A security term | Switch feature that builds a database of DHCP bindings, used as input to DAI |
| `arp_ignore` | Ignore ARP | A sysctl: bitmask controlling when a host replies to ARP requests whose target IP is not on the receiving interface |
| `arp_announce` | Announce ARP | A sysctl: bitmask controlling the source IP used in ARP announcements |
| `rp_filter` | Reverse path filter | A sysctl: drops packets whose source IP is not reachable on the receiving interface |
| Gratuitous | Free / unnecessary | A broadcast message sent without an explicit request |
| `REACHABLE` / `STALE` | Reachability states | The neighbor cache states (NUD) a host uses before sending unicast probes |

## Further Reading

- **RFC 826** — *An Ethernet Address Resolution Protocol*. The original ARP specification; gratuitous ARP is not described here but is in RFC 5227 and IEEE 802.1D.
- **RFC 5227** — *IPv4 Address Conflict Detection*. The protocol a host uses to detect that its own IP is in conflict with another host.
- **RFC 826 / RFC 903 / RFC 1027** — Related ARP and RARP history.
- **arping(8)** — Linux man page. Shows how to send an ARP request for a specific IP and observe the responding MAC, useful for finding duplicates.
- **arpwatch(8)** — Lawrence Berkeley National Laboratory. Reference for the `flip flop`, `changed ethernet address`, and `reaper repair` signatures.
- **Linux man page `arp(7)`** — The complete list of `arp_ignore` and `arp_announce` bit values and their meanings.
- **IEEE 802.1X-2010** — Port-based Network Access Control. The strongest L2 host-authentication mechanism.
- **phases/02-physical-layer-and-datalink** — A refresher on broadcast domains, FDB tables, and ARP's relationship to them.
- **phases/04-network-layer-and-ip** — The IP addressing primitives that ARP translates.
- **phases/12-application-protocols** — Why an HTTPS service still leaks metadata (SNI, certificate) even when an attacker can see the L2 frames.
