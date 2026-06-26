# Packet-Filter and Stateful Firewalls

> A firewall enforces a security policy on traffic crossing a network boundary. The two dominant families are stateless packet filters, which inspect each packet independently against a ruleset (source/destination IP, protocol, port), and stateful inspection firewalls, which track a connection's state in a flow table and only admit packets that match an existing flow. Modern NGFWs add application-layer inspection (TLS termination, deep packet inspection, IPS). We build a 5-tuple stateful firewall: each connection is keyed by (protocol, src_ip, src_port, dst_ip, dst_port); the firewall walks the SYN/SYN-ACK/ACK/FIN state machine, admits outbound flows, and rejects unsolicited inbound flows.

**Type:** implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** TCP state machine, IPv4 packet format, network security fundamentals
**Time:** ~75 minutes

## Learning Objectives

- Define a 5-tuple flow key as (protocol, src_ip, src_port, dst_ip, dst_port).
- Walk the TCP three-way handshake state machine (NEW → SYN_SENT → SYN_RECEIVED → ESTABLISHED) and the FIN/RST close transitions.
- Implement a stateless rule engine that evaluates (action, src, dst, proto, port) tuples in order.
- Implement a stateful rule engine that tracks flows and admits only packets matching a known or initiating connection.
- Distinguish outbound, inbound, and related/established flows; demonstrate why a stateless filter cannot safely allow inbound responses without exposing services.

## The Problem

Firewalls are deployed everywhere, but most engineers interact only with the policy editor, never with the engine. Without a working model, you cannot reason about why a particular rule worked, why an asymmetric flow broke, or why a stateful firewall sometimes rejects legitimate traffic. The pedagogical goal: build a small firewall that demonstrates both stateless and stateful modes side by side, on identical traffic, so the difference is visible.

## The Concept

### Three Generations of Firewalls

| Generation | Visibility | Typical decision |
|-----------|-----------|------------------|
| Packet filter (stateless) | L3/L4 headers only | Allow/deny by 5-tuple. |
| Stateful inspection | L3/L4 + flow table | Allow if packet matches an established flow. |
| NGFW / ALG | L7 inspection | Allow by URL, application, identity. |

### Stateless Rule Set Example

```
chain INPUT:
  1. allow tcp from any to 10.0.0.1:443
  2. allow tcp from any to 10.0.0.1:80
  3. allow icmp from 10.0.0.0/24 to any
  4. deny all
```

The ruleset is evaluated top to bottom; the first match wins. This is what `iptables`/`nftables` and Cisco ACLs implement.

### Why Stateless Filters Need to Allow Inbound Responses

Without state tracking, a stateless filter cannot tell whether an inbound SYN is a legitimate response or a new connection. To allow outbound HTTP, the rule typically opens an "established" path:

```
allow tcp from 10.0.0.0/24 to any established   # Cisco IOS-style
allow tcp from any to 10.0.0.1:80 established
```

This relies on the firewall inspecting the ACK bit. Most modern stacks have moved to stateful inspection precisely because of these workarounds.

### TCP State Machine

```
       SYN
   CLOSED ────► SYN_SENT ────► ESTABLISHED ────► FIN_WAIT_1 ────► FIN_WAIT_2
                  │                  │                                       │
                  │              RST/FIN                                  close
                  ▼                  ▼                                       ▼
               SYN_RCVD          CLOSE_WAIT ────► LAST_ACK              TIME_WAIT
                                                                              │
                                                                              ▼
                                                                           CLOSED
```

A stateful firewall tracks each flow's state and admits only packets that fit. A SYN without prior context is rejected; a SYN-ACK without a prior SYN is rejected; data packets are admitted only in ESTABLISHED.

### 5-Tuple Flow Key

```
key = (protocol, src_ip, src_port, dst_ip, dst_port)
```

Example: TCP 10.0.0.5:49231 → 93.184.216.34:443 is one flow. The reverse flow uses the same five values with src and dst swapped. Many firewalls store both directions in the same flow record.

### Flow Table Entry

| Field | Purpose |
|-------|---------|
| key | 5-tuple |
| state | NEW / SYN_SENT / SYN_RCVD / ESTABLISHED / FIN_WAIT / CLOSED |
| bytes/packets | counters for QoS, accounting |
| timeout | idle expiration (e.g., 60 s for TCP, 30 s for UDP) |

### UDP and ICMP "Pseudo-Flows"

UDP is connectionless, but firewalls still create a flow entry for the first packet and admit responses for ~30 seconds. ICMP echo (ping) follows the same pattern.

### Common Rule Patterns

| Pattern | Example |
|---------|---------|
| Allow inbound from specific source | `allow tcp from 10.0.0.0/24 to any:443` |
| Allow outbound initiated | stateful: `allow tcp from internal to any outbound` |
| Default deny | last rule: `deny all` |
| Anti-spoofing | drop packets whose source IP is from internal ranges arriving on the outside interface |

### Evasion History

| Attack | Mitigation |
|--------|-----------|
| IP fragmentation tricks (overlapping fragments) | modern firewalls reassemble before filtering |
| TCP flag abuse (Christmas tree packet) | drop packets with SYN+FIN+URG+PSH+RST |
| NAT slipstream (2020) | stateful tracking of expected packet sizes |

## Build It

`main.py` ships:

- `Packet` dataclass with proto, src_ip, src_port, dst_ip, dst_port, flags.
- `StatelessFirewall(rules)` with `accept(pkt) -> bool`.
- `StatefulFirewall(rules, idle_timeout)` with `accept(pkt)` updating a flow table.
- TCP handshake and tear-down demo.

```python
from main import StatelessFirewall, StatefulFirewall, Packet, TCP

rules = [
    ("allow", "10.0.0.5", "any", "tcp", 443),
    ("allow", "10.0.0.5", "any", "tcp", 80),
    ("deny",  "any", "any", "any", "any"),
]
sw = StatelessFirewall(rules)
sf = StatefulFirewall(rules)

syn = Packet(TCP, "203.0.113.1", 55555, "10.0.0.5", 443, flags="S")
print(sw.accept(syn))        # False (deny all)
print(sf.accept(syn))        # True (NEW outbound)
syn_ack = Packet(TCP, "10.0.0.5", 443, "203.0.113.1", 55555, flags="SA")
print(sf.accept(syn_ack))    # True (SYN_RECEIVED)
```

## Use It

| Routine | Purpose |
|---------|---------|
| `Packet(proto, src_ip, src_port, dst_ip, dst_port, flags)` | construct a packet |
| `StatelessFirewall(rules)` | order-dependent rule chain |
| `StatefulFirewall(rules, idle_timeout=60)` | flow-tracking engine |
| `firewall.flows` | current flow table (dict) |
| `firewall.expire(now)` | drop idle flows |

## Ship It

Real firewalls run on dedicated hardware (Juniper SRX, Palo Alto Networks, Fortinet, Cisco Firepower) or as Linux kernel modules (`nftables` with conntrack, FreeBSD `pf`). The conntrack table in Linux holds hundreds of thousands of flows and is the data structure that enables NAT. NGFWs add application-layer filtering (TLS termination, URL categorisation, IPS signatures).

## Exercises

1. Build a stateless ruleset that allows outbound HTTP/HTTPS/DNS but denies inbound SSH. Confirm that an unsolicited inbound SYN to port 22 is denied.
2. Convert the same ruleset to stateful mode. Show that an outbound connection is admitted, the SYN-ACK is admitted, and an unsolicited inbound SYN is denied.
3. Add a flow table inspection: print the active flows after the handshake. What is the state of each?
4. Implement idle-timeout expiry: a flow not seen for 60 seconds is dropped.
5. Add anti-spoofing: drop packets whose source IP is from 10.0.0.0/8 arriving on the outside interface.
6. Show a TCP FIN handshake: bidirectional FIN/ACK tears the flow down and removes it from the table.

## Key Terms

| Term | Definition |
|------|------------|
| Packet filter | Stateless rule engine operating on individual packets. |
| Stateful firewall | Tracks flows; admits packets matching known connections. |
| 5-tuple | (protocol, src_ip, src_port, dst_ip, dst_port). |
| Flow table | Per-firewall data structure holding active flows. |
| SYN/SYN-ACK/ACK | TCP handshake packets. |
| ESTABLISHED | TCP state once a flow is open. |
| Anti-spoofing | Dropping packets with source IPs that should not appear on a given interface. |
| conntrack | Linux kernel flow-tracking subsystem. |
| NGFW | Next-Generation Firewall: adds L7 inspection, IPS, identity. |

## Further Reading

- RFC 2979, Behavior of and Requirements for Internet Firewalls.
- Cheswick, Bellovin, Rubin — Firewalls and Internet Security (2nd ed.).
- NIST SP 800-41 Rev. 1, Guidelines on Firewalls and Firewall Policy.
- "conntrack" Linux kernel documentation — netfilter.org.
- PTES Technical Guidelines (penetration testing) — firewall evasion section.
- Palo Alto Networks "Next-Generation Firewall" whitepaper — commercial NGFW architecture.