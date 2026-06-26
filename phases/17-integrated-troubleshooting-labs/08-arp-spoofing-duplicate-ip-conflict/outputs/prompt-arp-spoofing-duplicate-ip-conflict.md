# ARP Spoofing and Duplicate-IP Conflict — Runbook

## Triage decision tree (top to bottom)

1. `journalctl -k --since '5 min ago' -g 'arp'` — look for `moved` or `conflict` lines.
2. If `moved` appears: run `arpwatch` for 60 seconds on the affected VLAN and watch syslog.
3. If `flip flop` fires: two hosts are claiming the same IP. Use `tcpdump -i <iface> -nn -e 'arp'` to find the second MAC, then isolate its switch port.
4. If `changed ethernet address` fires once and stops: graceful failover (HA pair, VRRP master change). No action.
5. If the gateway's MAC is wrong from a workstation: suspect ARP spoofing. Enable DAI, pin critical hosts with `arp -s`, capture evidence.
6. After mitigation: `ip neigh flush all` on victims, verify with `arp -an`, then escalate to incident response.

## Four ARP failure modes (one signature each)

| Mode | Unique signature |
|------|------------------|
| Duplicate IP | `arpwatch: flip flop` (rapid alternation, two MACs) |
| ARP spoofing | `arpwatch: changed ethernet address` for the gateway IP, repeated |
| ARP storm | `ifInErrors` and `RX dropped` climb on the switch port; switch CPU maxed |
| Stale cache after failover | `changed ethernet address` fires once, no further flaps |

## Three sysctls that reduce host-side noise (not full defenses)

- `net.ipv4.conf.<iface>.arp_ignore = 1` — reply only when the target IP is on the receiving interface. Prevents the host from "covering" for an IP it doesn't own.
- `net.ipv4.conf.<iface>.arp_announce = 2` — always use the best local address in ARP replies, never the source IP of an unrelated packet. Limits gratuitous-ARP amplification.
- `net.ipv4.conf.all.rp_filter = 1` — drop packets whose source IP is not reachable on the receiving interface. Defeats some spoofed sources.

None of these defeat a determined L2 attacker. Use DAI on the switch for that.
