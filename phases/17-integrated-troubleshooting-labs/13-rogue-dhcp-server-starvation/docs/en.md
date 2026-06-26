# Rogue DHCP Server and DHCP Starvation

> A rogue box under a desk hands out bad gateways; meanwhile an attacker exhausts the legitimate pool with forged DHCP requests.

**Type:** Lab
**Languages:** Python (stdlib), DHCP concepts, switch port-security
**Prerequisites:** Phase 6 switching, Phase 17 lesson 12
**Time:** ~90 minutes

## Learning Objectives

- Distinguish a rogue DHCP server from a DHCP starvation attack by reading DORA message evidence
- Identify the pool-exhaustion signature: all leases consumed by chaddr values that never ARP
- Build a detector that flags a server offering a gateway outside the authorised subnet
- Produce a DHCP snooping and port-security hardening runbook

## The Problem

DHCP is broadcast-based and unauthenticated on a flat L2 segment. Any host may respond to a DHCPDISCOVER. Two failure classes exploit this:

1. **Rogue DHCP server**: an unauthorised device replies to DISCOVERs with an OFFER containing a malicious `siaddr` (next-server), `yiaddr` (client IP), `option 3` (router/gateway), or `option 6` (DNS). Clients that accept the rogue OFFER send their default traffic through the attacker.
2. **DHCP starvation**: an attacker floods DISCOVERs with random `chaddr` (client hardware address) values to consume every lease in the legitimate pool. Once exhausted, legitimate clients cannot obtain addresses. Often a precursor to a rogue server attack: starve the real pool so clients grab the rogue OFFER.

Symptoms appear as clients receiving wrong gateways, DNS redirection, or "No IP address" errors while the DHCP server shows 100% utilisation with leases to unknown MACs.

## The Concept

### DHCP DORA — Timing and Mechanics

The four-message exchange has timing constraints that matter for both attacks and defenses:

```
t=0ms   Client --DHCPDISCOVER (broadcast)--> all hosts on segment
           src MAC: aa:bb:cc:11:22:33  dst MAC: ff:ff:ff:ff:ff:ff
           chaddr: aa:bb:cc:11:22:33   ciaddr: 0.0.0.0
           xid: 0x3903F326  (transaction ID, random 32-bit)

t=~5ms  Legit server  --DHCPOFFER (broadcast/unicast)--> client
           yiaddr: 10.0.1.50  option 3: 10.0.1.1  option 51: 86400s
           server identifier (opt 54): 10.0.1.254

t=~5ms  Rogue server  --DHCPOFFER (broadcast)--> client   ← arrives at same time
           yiaddr: 10.0.1.50  option 3: 192.168.99.1  option 54: 10.0.1.10

t=~8ms  Client selects one OFFER (typically first received) and broadcasts:
        Client --DHCPREQUEST (broadcast)--> all servers
           option 54 (server identifier): 10.0.1.10  ← selected the rogue

t=~12ms Rogue --DHCPACK--> client
           yiaddr: 10.0.1.50  option 3: 192.168.99.1  (attacker gateway)

t=~12ms Legit server sees DHCPREQUEST with opt 54 != its own address; silently withdraws offer
```

The client selects the first valid OFFER whose xid matches its outstanding DISCOVER. Because both servers race on the same broadcast domain, the rogue wins whenever propagation delay or server processing latency puts the rogue OFFER ahead. A rogue on the same switch often wins purely due to lower CPU load — it has nothing else to do except forge replies.

RFC 2131 gives clients a `secs` field they increment during retries; clients SHOULD wait at least a few seconds before retrying on no OFFER, but nothing prevents them from accepting the first OFFER immediately.

### chaddr Spoofing and Starvation Mechanics

The `chaddr` field (client hardware address, 16 bytes in the fixed header) is the MAC address the server uses as the lease key. The DHCP server allocates one lease per unique `chaddr`. Critically:

- The server has no way to verify that `chaddr` matches the frame's actual source MAC.
- An attacker can set `chaddr` to any 6-byte value while keeping the Ethernet frame's source MAC constant, or vary both simultaneously.
- Most DHCP server implementations (ISC dhcpd, Windows DHCP, Cisco IOS) key the lease table on `chaddr`, not on Ethernet source MAC.

A starvation tool like `yersinia` or `dhcpstarv` generates DISCOVERs in a loop:

```
for i in range(pool_size + 1):
    chaddr = random_mac()          # e.g. 02:xx:xx:xx:xx:xx (locally administered)
    send DHCPDISCOVER with chaddr=chaddr, xid=random()
    # server creates a new pending/offered lease for each unique chaddr
```

With a /24 subnet offering 253 usable addresses, 253 forged DISCOVERs (each with distinct chaddr) fills the offered-but-not-ACK'd lease table. The server holds these offers for the offer-timeout (typically 30–120 s on ISC dhcpd). Continuous flooding keeps the table full indefinitely. The attacker does not need to complete the DORA exchange — OFFERs alone reserve the address temporarily.

**Detection signature**: the lease table contains hundreds of entries whose `chaddr` values share no OUI prefix (all locally-administered, random), and none of those MACs ever appear in the switch's CAM table or ARP cache.

### DHCP Snooping — Implementation Details

DHCP Snooping is a Layer 2 switch feature that acts as a firewall for DHCP messages. The switch classifies every port as either **trusted** or **untrusted**:

- **Trusted ports**: connected to legitimate DHCP servers or to uplinks toward a DHCP server. OFFERs and ACKs arriving on trusted ports are forwarded normally.
- **Untrusted ports**: connected to end hosts (access ports). DHCP messages arriving on untrusted ports are inspected; OFFER and ACK messages are **dropped unconditionally** because an end host should never be a DHCP server.

When a DHCPREQUEST arrives on an untrusted port and is forwarded toward the trusted server, and when the server's DHCPACK returns on the trusted port, the switch extracts:

```
{client MAC (chaddr), assigned IP (yiaddr), VLAN, ingress port, lease time}
```

and writes this tuple into the **DHCP Snooping Binding Table** (also called the snooping database). This binding table is the single source of truth used by downstream features.

How the switch drops rogue OFFERs in detail:

1. Frame arrives on access port ge-0/0/5 (untrusted), Ethernet type 0x0800, UDP dst port 68 (DHCP client port).
2. Switch detects this is a DHCPOFFER (option 53 = 0x02) sourced from untrusted port.
3. Switch drops the frame and optionally increments the `DHCP snooping violation` counter on that port.
4. If `ip dhcp snooping limit rate` is configured, the port is err-disabled after exceeding the threshold.

Rate limiting protects the switch CPU from starvation floods:

```
! Cisco IOS — limit DHCP traffic on untrusted ports to 15 pps
interface GigabitEthernet0/1
 ip dhcp snooping limit rate 15
```

### DAI Correlation with the Snooping Binding Table

Dynamic ARP Inspection (DAI) consumes the snooping binding table to validate ARP packets on untrusted ports. When a host ARPs for a gateway, the switch checks:

- Does the ARP sender IP match the IP in the binding entry for this port/MAC?
- Does the ARP sender MAC match the chaddr in the binding entry?

If either check fails, the ARP is dropped. This prevents ARP poisoning by a host that obtained an address through a rogue server (since the rogue-assigned IP will not appear in the snooping binding table, the host's gratuitous ARP will be dropped and other hosts cannot be poisoned toward the rogue gateway).

DAI and DHCP Snooping together close the attack surface: Snooping prevents address assignment from rogue servers; DAI prevents ARP table corruption even if Snooping was momentarily bypassed.

## Build It

Follow these eight steps to reproduce both attacks and then validate each defense in the simulator.

**Addressing plan used throughout:**

| Role | IP | MAC |
|---|---|---|
| Legitimate DHCP server | 10.0.1.254/24 | aa:aa:aa:00:00:01 |
| Rogue DHCP server | 10.0.1.10/24 | de:ad:be:ef:00:01 |
| Attacker (starvation) | 10.0.1.7/24 | ca:fe:ba:be:00:01 |
| Client A | assigned | aa:bb:cc:11:22:33 |
| Client B | assigned | aa:bb:cc:44:55:66 |
| Legitimate gateway | 10.0.1.1 | — |
| Rogue gateway | 192.168.99.1 | — |
| Pool range | 10.0.1.50–10.0.1.200 | — |

**Steps:**

1. Read `code/main.py` and locate the three actors: `LegitServer` (pool 10.0.1.50–200, gateway 10.0.1.1, DNS 8.8.8.8, lease 86400 s), `RogueServer` (same pool range, gateway 192.168.99.1, DNS 192.168.99.53, lease 300 s — short lease encourages rapid renewal through the rogue), and `StarvationBot` (generates DISCOVERs with randomised `chaddr`, xid randomised per packet, rate configurable).

2. Run the baseline scenario with `SNOOPING=False` and `PORT_SECURITY=False`. Send DHCPDISCOVER from Client A (`aa:bb:cc:11:22:33`). Observe both OFFERs arrive: the legitimate OFFER with `option 3 = 10.0.1.1` and the rogue OFFER with `option 3 = 192.168.99.1`. Note which arrives first and which the client accepts.

3. Inspect the installed route on Client A after lease completion. If the rogue OFFER was accepted, the default gateway will be `192.168.99.1`. Verify DNS is also pointing to the rogue resolver (`192.168.99.53` via option 6).

4. Enable `SNOOPING=True`. Rerun step 2. Confirm that the rogue OFFER (arriving on the simulated untrusted port) is logged as `[SNOOPING DROP] OFFER from de:ad:be:ef:00:01 on untrusted port` and never reaches the client. Client A now reliably installs gateway `10.0.1.1`.

5. With snooping still enabled and `PORT_SECURITY=False`, run the starvation bot at 50 packets/s for 10 seconds (500 DISCOVERs, each with a distinct random `chaddr`). Observe the legitimate server's lease table grow from 0 toward 151 (the pool size). After exhaustion, send DHCPDISCOVER from Client B (`aa:bb:cc:44:55:66`). The server responds with DHCPNAK or no OFFER — pool exhausted.

6. Confirm the starvation signature: query the lease table and filter for entries where `arp_confirmed = False`. All 151 rogue leases have `arp_confirmed = False` because no real host ever ARPed for those addresses. Client B's legitimate request would have `arp_confirmed = True` within 2 s of assignment.

7. Enable `PORT_SECURITY=True` with `max_mac_per_port = 2` and `dhcp_rate_limit_pps = 15`. Rerun the starvation bot at 50 pps. Observe the port err-disable trigger fire after 15 packets in the first second. The starvation bot's port is shut and subsequent DISCOVERs from that port are silently discarded. The legitimate pool remains available.

8. Verify end state: run DHCPDISCOVER from Client B. It receives a valid lease (10.0.1.50–200) with gateway 10.0.1.1 within 15 ms. Snooping writes the binding `{aa:bb:cc:44:55:66, 10.0.1.50, VLAN10, port ge-0/0/3, 86400s}` to the binding table. DAI is now armed with this entry.

```text
Client --DISCOVER--> [legit server, rogue server, starvation bot]
         |              |               |
        OFFER          OFFER (bad gw)   DISCOVER xN to drain pool
         |              |
        Request to selected server -> Ack
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Find rogue | OFFER source MAC not in trusted server list | Rogue OFFER dropped by snooping |
| Detect starvation | Lease table full, ARP misses | Unknown chaddr leases >> threshold |
| Validate fix | Snooping + port-security on | Rogue OFFERs dropped; pool stays available |
| Confirm client | `ip route`, `resolvectl` | Gateway = legitimate router; DNS = corp |
| Starvation timing | Leases/second rate in server log | > 5 leases/s on a quiet subnet is anomalous |
| Binding table audit | `show ip dhcp snooping binding` | No entries with locally-administered OUI (02:xx / 06:xx / 0a:xx / 0e:xx prefix) |
| Port-security trigger | `show interface gi0/1 \| inc err-disable` | Starvation port enters err-disabled; client ports unaffected |

## Ship It

Produce a DHCP hardening runbook under `outputs/`. The runbook must include the following sections and, where applicable, the exact configuration stanzas shown below.

**1. Enable DHCP Snooping globally and per VLAN**

```
! Cisco IOS — enable snooping on the user VLAN
ip dhcp snooping
ip dhcp snooping vlan 10
no ip dhcp snooping information option   ! disable option 82 insertion if not needed
```

**2. Trust only the uplink port toward the real DHCP server**

```
interface GigabitEthernet0/24          ! uplink to core / DHCP server
 ip dhcp snooping trust
!
interface range GigabitEthernet0/1 - 23  ! all access ports — untrusted by default
 ip dhcp snooping limit rate 15          ! drop DHCP traffic above 15 pps per port
```

**3. Port-security: restrict MAC count on access ports**

```
interface range GigabitEthernet0/1 - 23
 switchport mode access
 switchport access vlan 10
 switchport port-security
 switchport port-security maximum 2          ! one PC + one IP phone
 switchport port-security violation restrict  ! count violations, do not shut port
 switchport port-security aging time 5        ! age sticky MACs after 5 min idle
```

**4. Dynamic ARP Inspection on the user VLAN**

```
ip arp inspection vlan 10
!
interface GigabitEthernet0/24
 ip arp inspection trust                     ! uplink is trusted; access ports are not
```

**5. Daily lease-table audit (cron job or EEM applet)**

Schedule the following EEM applet to run at 02:00 daily. It exports the snooping binding table and flags entries with locally-administered MACs (bit 1 of the first octet is set):

```
event manager applet DHCP-AUDIT
 event timer cron cron-entry "0 2 * * *"
 action 1.0 cli command "enable"
 action 2.0 cli command "show ip dhcp snooping binding"
 action 3.0 syslog msg "DHCP-AUDIT: binding table snapshot complete"
```

For off-box analysis, forward syslog to a SIEM and alert on:

- Any OFFER logged as dropped on an untrusted port (snooping violation).
- Lease count for a given VLAN crossing 80% of pool size within a 5-minute window.
- More than 10 distinct chaddr values seen from a single switchport within 60 seconds.

**6. Verify the deployed configuration**

```
show ip dhcp snooping
show ip dhcp snooping binding
show ip dhcp snooping statistics
show ip arp inspection vlan 10
show port-security interface GigabitEthernet0/1
```

Expected output for `show ip dhcp snooping`:

```
Switch DHCP snooping is enabled
DHCP snooping is configured on following VLANs: 10
DHCP snooping is operational on following VLANs: 10
Insertion of option 82 is disabled
Option 82 on untrusted port is not allowed
Verification of hwaddr field is enabled
Interface           Trusted    Allow option    Rate limit (pps)
-----------         -------    ------------    ----------------
GigabitEthernet0/24 yes        yes             unlimited
GigabitEthernet0/1  no         no              15
```

Start with [`outputs/prompt-rogue-dhcp-server-starvation.md`](../outputs/prompt-rogue-dhcp-server-starvation.md).

## Exercises

1. Modify the rogue OFFER to set a malicious DNS server (`option 6 = 192.168.99.53`) and show that clients now resolve attacker-controlled names. Capture DNS queries with `tcpdump -i any port 53` and confirm the resolver address.

2. Add a DHCP Snooping relay that forwards only OFFERs from the trusted port and verify the rogue is dropped. Instrument the relay to log each drop with the offending source MAC and the VLAN on which it arrived.

3. Reproduce starvation with 2000 forged DISCOVERs at 200 pps and measure the time to pool exhaustion for pool sizes of 50, 100, and 254 addresses. Plot exhaustion time versus pool size and explain why the relationship is not perfectly linear (hint: offer-timeout jitter).

4. Propose a detection rule that alerts when lease utilisation crosses 90% within 5 minutes on a subnet with fewer than 100 hosts. Specify the data source (SNMP OID, syslog pattern, or API call), the threshold logic, and the recommended automated response (rate-limit, VLAN quarantine, or alert-only).

5. Evaluate the impact of DHCPv4 RFC 7844 anonymity profiles on starvation detection. RFC 7844 clients randomise their `chaddr` field on each DISCOVER. Explain why a detector that relies on `chaddr` stability to distinguish legitimate clients from starvation bots may produce false positives in RFC 7844 environments and propose an alternative detection heuristic.

6. Implement a DHCP Snooping binding-table exporter in Python that reads the binding table from a Cisco IOS device via NETCONF (`ietf-dhcp` or vendor YANG model), filters for locally-administered MACs (first octet bitmask `& 0x02 == 0x02`), and writes a JSON report. Run it against the simulator's synthetic binding table from step 6 of Build It and confirm it flags all 151 starvation leases.

7. A junior engineer suggests setting every port to `trusted` to avoid snooping-related issues. Write a one-paragraph risk assessment explaining exactly what attack surface this re-opens, referencing which DORA message types would be unfiltered, and what the operational consequence is for users on that VLAN.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DORA | DHCP exchange | Discover, Offer, Request, Ack — the four-message lease acquisition sequence |
| Rogue DHCP | Unauthorised server | Any device answering DISCOVERs with crafted options such as a malicious gateway or DNS |
| Starvation | Pool drain | Flooding DISCOVERs with forged chaddr to exhaust all available leases |
| chaddr | Client hardware | The MAC in the DHCP fixed header; forgeable independently of the Ethernet frame's source MAC |
| siaddr | Next server | IP of the next bootstrap server (e.g., TFTP); abused to redirect PXE clients to attacker-controlled firmware |
| yiaddr | Your IP | The IP address being offered or confirmed to the client |
| ciaddr | Client IP | IP address the client already holds; set to 0.0.0.0 in initial DISCOVERs, populated during RENEWALs |
| xid | Transaction ID | Random 32-bit value in every DHCP message; client uses it to match replies to its outstanding request |
| DHCP Snooping | L2 protection | Switch feature that classifies ports as trusted or untrusted and drops OFFER/ACK on untrusted ports |
| Snooping binding table | Lease database | Per-port record of {MAC, IP, VLAN, port, lease time} built from observed ACKs; consumed by DAI and IP Source Guard |
| DAI | ARP protection | Dynamic ARP Inspection; validates ARP sender IP/MAC against the snooping binding table and drops mismatches |
| IP Source Guard | IP spoofing protection | Switch feature that drops IP packets whose source IP does not match the snooping binding entry for that port |

## Further Reading

- RFC 2131 — Dynamic Host Configuration Protocol (full DORA specification, fields, and option handling)
- RFC 7844 — Anonymity Profiles for DHCP Clients (chaddr randomisation and implications for lease tracking)
- Cisco IOS DHCP Snooping and Dynamic ARP Inspection configuration guide (Catalyst 9000 / IOS-XE)
- Cisco IOS IP Source Guard configuration guide (extends snooping binding table to L3 enforcement)
- `yersinia` tool documentation — DHCP starvation and rogue server attack modes with packet-level detail
- IEEE 802.1X and MACSec as complementary controls — port authentication before DHCP is permitted
- "DHCP Starvation and Rogue DHCP Server Attacks" — SANS Reading Room paper (practical pcap analysis methodology)
