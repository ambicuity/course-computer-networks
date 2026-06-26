# ARP Resolution, Gratuitous ARP, and Cache Dynamics

> The **Address Resolution Protocol** (RFC 826) bridges IPv4 to Ethernet: before a host can put a packet on the wire it must know the destination's 48-bit **MAC** address, which IP never carries. ARP resolves this with a broadcast **REQUEST** (`op=1`, `htype=1 Ethernet`, `ptype=0x0800 IPv4`, `hlen=6`, `plen=4`) carrying `sender hardware address`, `sender protocol address`, and a `target protocol address` (TPA) asking "who has this IP?" — the owner replies with a unicast **REPLY** (`op=2`) giving its MAC, and *every* host that overhears the exchange updates its **ARP cache** under the RFC 826 rule "always learn the sender." A **gratuitous ARP** (RFC 5227) reuses that learning rule: a host announces itself with `sender protocol address == target protocol address`, forcing peers to refresh the binding without being asked — this is how a host survives a NIC swap, claims a takeover address, and detects IP duplicates. Caches do not live forever: Linux runs a neighbour-state machine **REACHABLE → STALE → (gc)** driven by `base_reachable_time` (~30s) and `gc_stale_time` (~60s); the classic failure modes are **stale-cache black holes** after a silent MAC change, **ARP poisoning** (a forged REPLY pinning a victim's IP to an attacker's MAC), and **unbounded broadcast storms** on large flat L2. This lesson builds a runnable RFC 826 resolver plus gratuitous-ARP and proxy-ARP models so you can read the exact cache state these mechanisms leave behind.

**Type:** Lab
**Languages:** Python, ip, arp, tcpdump
**Prerequisites:** Ethernet framing (Phase 00), IPv4 addressing and subnet masks, the difference between L2 and L3
**Time:** ~80 minutes

## Learning Objectives

- Decode a 28-byte ARP payload plus its 14-byte Ethernet header field by field, naming every RFC 826 field and its size.
- Trace an ARP REQUEST broadcast and the unicast REPLY that resolves a target IP to a MAC, including which caches get updated and why.
- Explain why `sender protocol address == target protocol address` makes an ARP packet gratuitous, and list the four operational uses of gratuitous ARP.
- Distinguish gratuitous ARP from proxy ARP and from ARP poisoning, and predict the cache state each leaves on the victim.
- Describe the Linux neighbour-state lifecycle (REACHABLE → STALE → garbage-collected) and compute when an entry transitions given `base_reachable_time` and `gc_stale_time`.
- Read `ip neigh`, `arp -n`, and a `tcpdump -e -n arp` capture and map each printed field back to the RFC 826 packet layout.

## The Problem

A switch port is moved during maintenance: a server at `10.0.0.9` is replugged into a different NIC and re-IPs with a brand-new MAC. Its peers on `10.0.0.0/24` are not told. For the next sixty seconds the rest of the VLAN happily send their TCP segments to the *old* MAC still sitting in their ARP caches. Connections stall, retransmissions pile up, and the NOC gets paged for a "network outage" that is really a stale L2 binding. Meanwhile the on-call engineer's `tcpdump` shows no traffic to the server at all — because the frames are being handed to a MAC that no longer exists on the segment, and the switch is flooding them to a dead port.

This is the core operational lesson of ARP: **IP tells you *who*, Ethernet tells you *where*, and nothing automatically reconciles them when *where* changes.** Resolution, gratuitous announcement, and cache expiry are the three mechanisms the stack uses to keep that mapping live. Get any of them wrong and you get silent black holes that look exactly like a routing failure.

## The Concept

### The ARP packet, field by field (RFC 826)

ARP is carried directly inside an Ethernet frame, identified by **EtherType `0x0806`** (IPv4 is `0x0800`). There is no IP header. The 28-byte payload is fixed-layout:

| Offset | Field | Size | Meaning |
|---|---|---|---|
| 0 | `htype` (Hardware type) | 2 | `1` = Ethernet |
| 2 | `ptype` (Protocol type) | 2 | `0x0800` = IPv4 |
| 4 | `hlen` | 1 | `6` = length of a MAC in bytes |
| 5 | `plen` | 1 | `4` = length of an IPv4 address in bytes |
| 6 | `op` | 2 | `1` REQUEST, `2` REPLY, `3`/`4` RARP |
| 8 | `sha` (sender hardware address) | 6 | sender's MAC |
| 14 | `spa` (sender protocol address) | 4 | sender's IPv4 |
| 18 | `tha` (target hardware address) | 6 | `00:00:00:00:00:00` in a REQUEST; the requester's MAC in a REPLY |
| 24 | `tpa` (target protocol address) | 4 | the IP being looked up |

The Ethernet header wrapping it is the ordinary 14 bytes: destination MAC (6), source MAC (6), EtherType (2). A REQUEST is broadcast (`ff:ff:ff:ff:ff:ff`); a REPLY is unicast back to the requester's MAC. `code/main.py` builds exactly these bytes with `struct.pack` and round-trips them through `ArpPacket.from_bytes` so you can see the wire format. The full layout is drawn in `assets/arp-resolution-gratuitous-arp-and-cache-dynamics.svg`.

### Resolution: the four-step exchange

Given a host A (`10.0.0.7`, MAC `..07`) wanting to send to B (`10.0.0.9`, unknown MAC):

1. **Cache check.** A looks up `10.0.0.9` in its ARP cache. If a **REACHABLE** entry exists, A uses it immediately — no packets on the wire. If the entry is **STALE**, A still uses it but schedules a refresh probe.
2. **Miss → broadcast REQUEST.** A builds `op=1, sha=A, spa=10.0.0.7, tha=0, tpa=10.0.0.9` and broadcasts it on the segment. The IP packet that triggered the lookup is queued (Linux holds up to a few packets per pending neighbour in the ARP **hold queue**).
3. **Every host learns the sender.** Per RFC 826, each receiver — even the one who is *not* the target — inserts `10.0.0.7 → ..07` into its own cache. This is why ARP is "free learning": a single broadcast populates caches in both directions.
4. **Owner replies; A installs the binding.** B sees `tpa == my IP`, builds `op=2, sha=B, spa=10.0.0.9, tha=A, tpa=10.0.0.7`, and unicasts it. A installs `10.0.0.9 → B's MAC`, marks it REACHABLE, and releases the queued IP packet. B already learned A in step 3, so the reverse path needs no further traffic.

Worked numeric example: if A has `base_reachable_time = 30s` and B answers in 1 ms, the new entry enters REACHABLE and stays there until 30 s of silence elapse, then drops to STALE. If A then sends nothing for another 60 s (`gc_stale_time`), the entry is garbage-collected and the next packet triggers a fresh broadcast.

### Gratuitous ARP (RFC 5227)

A **gratuitous ARP** is an ARP packet where `spa == tpa` — the sender is announcing its own binding rather than asking for someone else's. It can be sent as a broadcast REQUEST (the common form) or a unicast REPLY. Because the receiver applies the same "always learn the sender" rule, every peer silently updates its cache without ever sending a reply. Four real uses:

| Use | Mechanism | What it prevents |
|---|---|---|
| **NIC / MAC swap** | New NIC broadcasts `spa=tpa=my IP, sha=new MAC` | Stale-cache black hole for ~60 s after replug |
| **Address takeover** (HA failover, VRRP) | New master broadcasts the virtual IP with its MAC | Peers keep sending to the dead old master |
| **Duplicate-IP detection** | Booting host broadcasts its own IP; if a REPLY comes back, the IP is in use | Two hosts claiming one IP |
| **Switch port/MAC-table refresh** | Some switches age CAM entries faster when they see a source MAC announce | Frames flooding the wrong port after a move |

`code/main.py` demonstrates use #1 directly: B has cached A's old MAC; A swaps its NIC and sends one gratuitous REQUEST; B's cache flips to the new MAC with no query on the wire. The same line of code (`cache.insert(sender_pa, sender_ha)`) that handles a normal REPLY also handles the gratuitous update — that is the elegance of RFC 826's learning rule.

### Proxy ARP

A router running **proxy ARP** answers ARP REQUESTs for IP addresses that are *not* on the local segment but that the router knows how to reach. The router replies with **its own MAC**, not the real destination's MAC, so the original sender sends the frame to the router, which then forwards it at L3. This lets two IP subnets share one broadcast domain (or appear to) without hosts running a default gateway entry. It is how Mobile IP's home agent intercepts packets for a roaming host, and how some VPN concentrators present a remote network as local. The cost is hidden asymmetry: the cache entry points at the router's MAC forever, and if the router moves the whole segment loses connectivity. `code/main.py` models this: router R holds a proxy table mapping `10.0.0.50` to an off-LAN real MAC, but answers A's REQUEST with R's own MAC, which is what A caches.

### The ARP cache and its lifecycle

Operating systems do not hold ARP bindings forever. Linux exposes this as the **neighbour state machine** (`ip neigh` / `/proc/net/neigh`):

| State | Meaning | Typical trigger to leave |
|---|---|---|
| **INCOMPLETE** | REQUEST sent, awaiting REPLY | REPLY arrives → REACHABLE; timeout → failed |
| **REACHABLE** | Recently confirmed (within `base_reachable_time`, default ~30 s) | Timer expiry → STALE |
| **STALE** | Binding is old but still used; traffic triggers a refresh probe | Outgoing traffic → DELAY → PROBE → REACHABLE; `gc_stale_time` expiry → removed |
| **DELAY / PROBE** | Mid-refresh, unicasting a probe | Reply → REACHABLE; failure → FAILED |
| **FAILED** | No answer | Removed or retried |

The two numbers that dominate behaviour are `base_reachable_time` (~30 s, REACHABLE→STALE) and `gc_stale_time` (~60 s, after which a STALE entry with no traffic can be garbage-collected). Windows uses a simpler scheme: dynamic entries expire after roughly 2–10 minutes of inactivity depending on edition; static entries (`arp -s`) never expire. macOS follows a similar reachable/stale pattern via `ndp`/`arp -a`. Because REACHABLE→STALE is a *time* transition and STALE→REACHABLE is *traffic* triggered, a chatty peer keeps its entry fresh for free while a quiet one is periodically re-probed — which is exactly why a silent MAC swap on a quiet host is the worst-case failure.

### Failure modes: stale caches, poisoning, and storms

| Failure | Cause | Symptom | Mitigation |
|---|---|---|---|
| **Stale-cache black hole** | Host changes MAC without gratuitous ARP | Peers send to dead MAC for up to `gc_stable_time` | Gratuitous ARP on link-up; `arping -U` after replug |
| **ARP poisoning / spoofing** | Attacker injects forged REPLY pinning victim IP → attacker MAC | Traffic hijacked or sniffed; MITM | Dynamic ARP Inspection (DAI) on switches; static ARP on critical hosts |
| **Unsolicited-reply abuse** | Some stacks accept REPLY with no outstanding REQUEST | Forged unicast REPLY poisons cache silently | DAI; RFC 5227-style validation |
| **Broadcast storm on flat L2** | Every miss floods the whole VLAN; large subnets amplify it | High CPU, ARP loss, retransmissions | Smaller subnets; L3 segmentation; broadcast-rate limiting |
| **Proxy-ARP sprawl** | Router answers for everything; caches point at router forever | Asymmetric paths; hard to debug | Disable proxy ARP unless explicitly needed |

The common thread: ARP has **no authentication**. Any host on the segment can speak for any IP. Securing L2 (DAI, 802.1X, port security) is the only real defence; the protocol itself trusts everyone.

### Reading the tools: `ip neigh`, `arp -n`, `tcpdump`

```text
$ ip neigh show
10.0.0.9 dev eth0 lladdr aa:bb:cc:00:00:09 REACHABLE
10.0.0.1 dev eth0 lladdr aa:bb:cc:00:00:01 STALE

$ tcpdump -e -n arp
ethertype ARP, ARP, Request who-has 10.0.0.9 tell 10.0.0.7, length 28
ethertype ARP, ARP, Reply 10.0.0.9 is-at aa:bb:cc:00:00:09, length 28
```

`ip neigh` prints the cache with the live state word; `arp -n` (older) prints the same bindings without state. `tcpdump -e` adds the Ethernet header so you see the broadcast destination and EtherType `0x0806`. The `length 28` is the ARP payload — add 14 for the Ethernet header to get the on-wire frame size of 42 bytes (padded to 60 on legacy Ethernet). Run `code/main.py` and compare its printed frame decode against a real `tcpdump -e -n arp` on your own machine: the field layout is identical.

## Build It

1. Read `code/main.py`. It models RFC 826 with `ArpPacket` (struct-packed 28-byte payload in a 14-byte Ethernet frame), `ArpCache` (the REACHABLE→STALE→GC lifecycle), and `Host.resolve()` driving a broadcast REQUEST through a small LAN.
2. Run it: `python3 code/main.py`. Confirm Scenario 1 prints the broadcast REQUEST, B's unicast REPLY, A's updated cache, and the 42-byte reply frame in hex.
3. Watch Scenario 2 (gratuitous ARP): B's cache holds A's old MAC, A swaps its NIC, one gratuitous REQUEST silently flips B's binding. Note `is_gratuitous()` returns True because `spa == tpa`.
4. In Scenario 3 (proxy ARP) confirm that A caches the *router's* MAC for `10.0.0.50`, never the off-LAN host's real MAC.
5. In Scenario 4 shorten `reachable_s` and `gc_s` in the `ArpCache` constructor and watch the entry age REACHABLE → STALE → removed across the printed ticks.
6. On a real Linux box run `ip neigh show` before and after `ping`ing a neighbour; note the state flips INCOMPLETE → REACHABLE → (later) STALE. Compare the timing to the values in `/proc/sys/net/ipv4/neigh/eth0/`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a resolution | `tcpdump -e -n arp` shows REQUEST then REPLY; cache gains a REACHABLE entry | One broadcast, one unicast reply, both caches updated, no retransmissions |
| Verify gratuitous ARP worked | After a NIC swap, peers' caches show the new MAC with no REQUEST on the wire | One broadcast `spa==tpa`; victim cache flips silently; no 60-s outage |
| Detect a stale-cache black hole | `ip neigh` shows STALE pointing at a MAC no longer on the segment; `tcpdump` shows frames to a dead MAC | Flushing the entry (`ip neigh del …`) and re-resolving recovers connectivity |
| Spot ARP poisoning | Unexpected REPLY pinning a gateway IP to a non-gateway MAC; DAI log drops | Static ARP for the gateway or DAI stops the binding; traffic returns to real MAC |
| Justify cache timeouts | `base_reachable_time` vs `gc_stale_time` vs observed churn | Quiet subnets tolerate long STALE; mobile subnets use shorter values + gratuitous ARP |
| Read a frame decode | 14 B Ether + 28 B ARP = 42 B; EtherType 0x0806; op 1 or 2 | Fields map exactly to the RFC 826 table above |

## Ship It

Produce one artifact under `outputs/prompt-arp-resolution-gratuitous-arp-and-cache-dynamics.md`:

- An annotated ARP trace for a NIC-swap incident: the stale-cache symptom, the single gratuitous ARP that fixes it, and the before/after `ip neigh` output. Start from the printed output of `code/main.py` (Scenarios 1 and 2) and annotate each line with the RFC 826 field and the cache-state transition it triggers. Add a one-paragraph runbook: "when a replugged host is unreachable for ~60 s, run `arping -U <ip>` and check `ip neigh`."

## Exercises

1. Host A (`10.0.0.7`, MAC `..07`) resolves B (`10.0.0.9`). Write out the exact 28-byte ARP payload of A's REQUEST and B's REPLY, including `op`, `sha`, `spa`, `tha`, `tpa` for each. Which other hosts on the segment update their caches, and with what binding?
2. A server on `10.0.0.9` swaps its NIC from MAC `..09` to `..99` during maintenance and does *not* send gratuitous ARP. Describe exactly what its peers experience over the next 60 seconds and which `ip neigh` state transitions occur. Then describe the one packet that would have prevented it.
3. An attacker on the same VLAN sends a forged unicast ARP REPLY claiming the default gateway `10.0.0.1` is at the attacker's MAC. Explain why this works (cite the RFC 826 learning rule), what symptom the victims see, and two switch features that stop it.
4. Two hosts on `10.0.0.0/24` are configured with the same IP `10.0.0.50`. Describe how a boot-time gratuitous ARP exchange reveals the duplicate, and what each host should do when it sees a REPLY to its own announcement.
5. A router R runs proxy ARP for subnet `10.0.0.0/24` even though that subnet is actually behind a different router. Trace what A's ARP cache contains for `10.0.0.50` after resolution, and explain why disabling proxy ARP is usually the right default.
6. Given `base_reachable_time = 30 s` and `gc_stale_time = 60 s`, compute the wall-clock time after which a freshly resolved entry that receives *no further traffic* is (a) marked STALE, (b) garbage-collected. Now suppose the peer sends one packet at t = 25 s — what happens to the state, and when?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ARP | "MAC lookup" | Address Resolution Protocol (RFC 826): maps an IPv4 address to a 48-bit Ethernet MAC on the same L2 segment |
| Gratuitous ARP | "a pointless ARP" | An ARP packet with `spa == tpa` that forces peers to learn/refresh a binding without being asked (RFC 5227) |
| Proxy ARP | "router fakes it" | A router answering ARP for IPs not on the local segment, replying with its own MAC so traffic is routed at L3 |
| ARP cache | "the MAC table" | Per-host `(IP → MAC, state, timestamp)` table; not the switch's CAM table, which is a separate L2 forwarding table |
| REACHABLE / STALE | "fresh / old" | Linux neighbour states: REACHABLE = confirmed within `base_reachable_time`; STALE = older but usable, pending refresh |
| `base_reachable_time` | "cache timeout" | Time a confirmed entry stays REACHABLE before dropping to STALE (~30 s default) |
| `gc_stale_time` | "GC timer" | Time a STALE entry with no traffic survives before being garbage-collected (~60 s default) |
| ARP poisoning | "ARP spoofing" | Injecting a forged REPLY to pin a victim IP to an attacker's MAC; works because ARP has no authentication |
| Hold queue | "pending packets" | Packets buffered while a neighbour is INCOMPLETE, released once the REPLY arrives; bounded to avoid memory exhaustion |
| EtherType 0x0806 | "the ARP type" | The EtherType value that tells an Ethernet receiver the payload is an ARP packet (vs 0x0800 for IPv4) |

## Further Reading

- **RFC 826** — An Ethernet Address Resolution Protocol (Plummer, 1982); the base specification, field layout, and the "always learn the sender" rule.
- **RFC 5227** — IPv4 Address Conflict Detection; defines gratuitous ARP semantics and the probe/announce state machine.
- **RFC 1027** — Using ARP to Implement Transparent Subnet Gateways; the original proxy-ARP rationale.
- **RFC 903** — A Reverse Address Resolution Protocol (RARP), `op=3/4`; the historical precursor to DHCP for diskless boot.
- **IEEE 802.3** — Ethernet frame format and the 14-byte header ARP rides on (EtherType registry).
- **Linux documentation** — `ip neigh`, `/proc/sys/net/ipv4/neigh/*`, and the neighbour state machine in the kernel docs.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5, Section 5.2.5 (ARP and RARP).
- Kurose & Ross, *Computer Networking*, 8th ed., Section 6.4 (link-layer addressing and ARP).
