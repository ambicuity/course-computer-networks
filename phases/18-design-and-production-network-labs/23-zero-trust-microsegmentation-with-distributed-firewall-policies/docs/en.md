# Zero-trust microsegmentation with distributed firewall policies

> On 2024-03-04 a contractor laptop in VLAN 20 (HR Wi-Fi) pivoted laterally into the Engineering Kubernetes API server on `10.40.50.0/24`, then to PostgreSQL on `10.40.50.30:5432`, in 47 seconds flat. The firewall at the perimeter was perfect. The flat L3 inside the campus let any source talk to any destination — the exact anti-pattern that zero-trust (NIST SP 800-207) is designed to break. This lesson deploys a four-tier distributed firewall on Linux with `nftables` (the successor to iptables, RFC 9281), using **per-host policies** as the segmentation primitive instead of one shared ACL on the core router. You will build a 6-node topology (`edge`, `app`, `db`, `worker`, `mgmt`, `attacker`), write a per-tier nftables policy in a small Python DSL, push it to each namespace, then run `nmap` from `attacker` to verify that only port 443 to `app` reaches the right tier. The companion `code/main.py` is the policy compiler: it takes a YAML-shaped Python dict and emits one nftables script per host, with policy decision points (PDPs) and policy enforcement points (PEPs) clearly separated — the same shape a Calico Cilium or OpenPolicyAgent deployment uses at scale.

**Type:** Project
**Languages:** Python, shell, nftables, nmap
**Prerequisites:** Phase 09 IPv4 basics, ability to run namespaces with `ip netns`, comfort reading iptables-style rules
**Time:** ~75 minutes

## Learning Objectives

- Build a 6-node lab (`edge`, `app`, `db`, `worker`, `mgmt`, `attacker`) with Linux network namespaces and 4 tiers: `dmz`, `app`, `data`, `mgmt`.
- Author a per-tier nftables ruleset that enforces "default deny, explicit allow" with **connection tracking** (`ct state`), **rate limiting** (`limit rate`), and **logging** (`log prefix`) so that every denied packet produces a syslog line.
- Run `code/main.py` to compile a Python-policy-dict into 4 nftables scripts (`edge.nft`, `app.nft`, `db.nft`, `worker.nft`) and apply them with `nft -f`.
- Validate the segmentation with `nmap` from `attacker` to `db` — confirm only ports 22 (from `mgmt` only), 5432 (from `app` only) are reachable; everything else is dropped with a `LOG` prefix visible in `journalctl`.
- Explain the NIST SP 800-207 zero-trust tenet of "never trust, always verify" — and how per-host enforcement removes the implicit-trust zone that a shared router ACL leaves open.
- Distinguish policy decision (PDP, the Python dict) from policy enforcement (PEP, the nftables chains) — the same separation that enterprise tools (OPA, Calico, Cilium) scale.

## The Problem

The classic enterprise has a perimeter firewall and a "trusted internal network". Once an attacker breaches the perimeter (phishing, contractor laptop, supply chain), every internal host is one ARP request away from every other internal host. Lateral movement from one VLAN to another only requires routing permission, not firewall permission — because the segmentation happens at L3 only, and a router forwards everything by default.

Zero-trust removes the implicit trust of "any host on this subnet can talk to any other". Instead, every flow is allowed only if there is an explicit policy permitting `(source identity, source workload, destination workload, port, protocol)` — checked at the host closest to the destination (the PEP). The PDP decides; the PEP enforces. A successful zero-trust rollout reduces the "blast radius" of any single compromise to the workload that was actually breached.

The trap most teams fall into is treating "zero-trust" as a marketing word and shipping a single ACL on the core switch. That ACL is one configuration push away from disaster, applies to the whole VLAN, and has no per-workload context. Real zero-trust is per-host, with the policy expressed in a structured form that compiles into the native enforcement plane (nftables, eBPF, XDP, OVS).

## The Concept

### What nftables gives you over iptables

`nftables` is the Linux packet classification framework, replaced `iptables`, `ip6tables`, `arptables`, and `ebtables` with a single virtual-machine-based engine (RFC 9281, the IETF "NFTables Architecture"). Concretely:

- One rule syntax for IPv4, IPv6, ARP, bridge, and netdev (incoming packet).
- Sets and dictionaries that let you match thousands of addresses or ports in a single rule (`@mgmt_hosts`).
- Native **conntrack** integration with `ct state { new, established, related }` (the same RFC 4936 conntrack the kernel has always used).
- **Metering** for rate limits and counting (`meter ratelimit`, `counter`).
- **Maps / verdicts** that let you decouple policy from rule ordering — `iifname vmap @ingress_policy`.

### Connection tracking is the foundation of stateful filtering

The kernel's **conntrack** subsystem tracks every flow in a hash table (`nf_conntrack_max`, default 262144). Each connection transitions through states: `NEW` (SYN seen), `ESTABLISHED` (SYN/ACK seen), `RELATED` (a separate but related flow — e.g., FTP data, ICMP error), `INVALID` (does not match any tracked flow), and `UNTRACKED` (excluded by `notrack`). A stateful rule accepts `ct state { established, related }` and only re-checks new flows — which is what makes 10,000 concurrent TCP connections possible with a 100-rule ACL.

### NIST zero-trust architecture (SP 800-207)

NIST SP 800-207 codifies three pillars:

1. **Policy Engine (PE)** — decides whether a request is allowed. Inputs: subject identity, device posture, behavioral history, time of day.
2. **Policy Administrator (PA)** — issues the allow/deny verdict to the PEP.
3. **Policy Enforcement Point (PEP)** — actually drops or forwards the packet.

In our lab, the **Python dict** is the PE+PA (single file, human-readable, signed by the operator). The **nftables chains on each host** are the PEPs. When you scale to a Kubernetes cluster, the same shape holds: OPA/Cilium policy = PDP, Cilium eBPF datapath = PEP.

### The four tiers

| Tier | Subnet | Hosts | Allowed source tiers | Allowed destination tiers |
|---|---|---|---|---|
| `dmz` | `10.40.10.0/24` | `edge` | `external` (any) | `app` (443 only) |
| `app` | `10.40.20.0/24` | `app` | `dmz` | `data` (5432 only), `mgmt` (ssh) |
| `data` | `10.40.50.0/24` | `db` | `app` (5432 only), `mgmt` (ssh only) | `mgmt` (ssh only) |
| `mgmt` | `10.40.99.0/24` | `mgmt` | `app` (ssh only) | all tiers (admin only) |

Every other `(source, destination, port)` tuple is denied and logged. The default policy is `policy drop` on the input chain.

### Why per-host and not per-router

A shared router ACL has three failure modes a per-host PEP avoids:

1. **Single point of failure**: misconfigure the ACL once and the entire trust zone breaks. Per-host, only one host breaks.
2. **Asymmetric routing**: ingress and egress flow on different routers; the ACL applies only on the path the router sees.
3. **Workload blindness**: a router does not know which Kubernetes pod the packet is from. A per-host nftables chain can match on `cgroup` (the kernel `cgroup v2` id is available as `meta cgroup`).

### Logging for incident response

Every deny rule should emit a `LOG` line with a stable prefix (e.g., `nft-drop: tier=data peer=10.40.20.5 proto=6 dport=5432`). The `LOG` target writes to the kernel ring buffer; `rsyslog` (or syslog-ng, RFC 5424) then picks it up and ships to the SIEM. Without that log line, a denied packet is invisible.

## Build It

### Step 1: Build the 6-node lab

```bash
for n in edge app db worker mgmt attacker; do ip netns add $n; done

# edge <-> dmz
ip link add veth-e-d type veth peer name veth-d-e
ip link set veth-e-d netns edge
ip link set veth-d-e netns app
ip netns exec edge ip addr add 10.40.10.1/24 dev veth-e-d
ip netns exec edge ip link set veth-e-d up
ip netns exec app ip addr add 10.40.10.2/24 dev veth-d-e
ip netns exec app ip link set veth-d-e up

# app <-> data
ip link add veth-a-b type veth peer name veth-b-a
ip link set veth-a-b netns app
ip link set veth-b-a netns db
ip netns exec app ip addr add 10.40.20.1/24 dev veth-a-b
ip netns exec app ip link set veth-a-b up
ip netns exec db ip addr add 10.40.50.10/24 dev veth-b-a
ip netns exec db ip link set veth-b-a up
ip netns exec db ip route add default via 10.40.50.1   # if the app subnet is the gateway

# mgmt out-of-band
ip link add veth-m-b type veth peer name veth-b-m
ip link set veth-m-b netns mgmt
ip link set veth-b-m netns db
ip netns exec mgmt ip addr add 10.40.99.5/24 dev veth-m-b
ip netns exec mgmt ip link set veth-m-b up
ip netns exec db ip addr add 10.40.99.10/24 dev veth-b-m
ip netns exec db ip link set veth-b-m up

# attacker on the dmz side
ip link add veth-d-a type veth peer name veth-a-d
ip link set veth-d-a netns app
ip link set veth-a-d netns attacker
ip netns exec app ip addr add 10.40.10.3/24 dev veth-d-a
ip netns exec app ip link set veth-d-a up
ip netns exec attacker ip addr add 10.40.10.4/24 dev veth-a-d
ip netns exec attacker ip link set veth-a-d up

# enable forwarding and install default routes
ip netns exec app sysctl -w net.ipv4.ip_forward=1
ip netns exec db sysctl -w net.ipv4.ip_forward=1
ip netns exec attacker ip route add default via 10.40.10.3
```

### Step 2: Author the policy

Save the policy below as `policy.py` next to `main.py`:

```python
TIERS = {
    "dmz":  {"subnet": "10.40.10.0/24", "hosts": {"edge": "10.40.10.1", "app": "10.40.10.2"}},
    "app":  {"subnet": "10.40.20.0/24", "hosts": {"app": "10.40.20.1"}},
    "data": {"subnet": "10.40.50.0/24", "hosts": {"db":  "10.40.50.10"}},
    "mgmt": {"subnet": "10.40.99.0/24", "hosts": {"mgmt":"10.40.99.5",  "db":"10.40.99.10"}},
}

ALLOW = [
    ("dmz",  "app",  "10.40.10.0/24", "10.40.20.0/24", "tcp", 443),
    ("app",  "data", "10.40.20.0/24", "10.40.50.0/24", "tcp", 5432),
    ("mgmt", "data", "10.40.99.0/24", "10.40.50.0/24", "tcp", 22),
    ("mgmt", "dmz",  "10.40.99.0/24", "10.40.10.0/24", "tcp", 22),
]
```

### Step 3: Run the policy compiler

```bash
python3 code/main.py
```

Expected output (truncated):

```
=== POLICY COMPILER — generating nftables scripts ===
  [edge.nft]   tier=dmz  rules=4
  [app.nft]    tier=app  rules=6
  [db.nft]     tier=data rules=8
  [worker.nft] tier=app  rules=6
```

Each script is written to `/tmp/<host>.nft` so you can `cat` them. Apply them with:

```bash
ip netns exec edge   nft -f /tmp/edge.nft
ip netns exec app    nft -f /tmp/app.nft
ip netns exec db     nft -f /tmp/db.nft
```

### Step 4: Validate segmentation with `nmap`

From `attacker` (an untrusted host on the dmz subnet):

```bash
ip netns exec attacker nmap -Pn -p 22,443,5432,3389 10.40.20.1
ip netns exec attacker nmap -Pn -p 22,443,5432,3389 10.40.50.10
```

The first scan should show port 443 as open (edge → app allowed), all others filtered. The second scan should show **all** ports filtered (the attacker is on `10.40.10.4`, not in any tier allowed to talk to `10.40.50.0/24`).

From `mgmt` (an admin):

```bash
ip netns exec mgmt nmap -Pn -p 22 10.40.50.10
```

This should show port 22 open — `mgmt` is the only tier allowed to SSH into `data`.

### Step 5: Verify the deny log

Every denied packet from `attacker` to `db:5432` should emit a log line. Check it:

```bash
ip netns exec attacker bash -c \
  'for i in $(seq 1 10); do nc -vz 10.40.50.10 5432 2>&1; done'

ip netns exec db journalctl -k --since "1 minute ago" | grep nft-drop
```

Expected lines:

```
nft-drop: tier=data peer=10.40.10.4 proto=6 dport=5432
nft-drop: tier=data peer=10.40.10.4 proto=6 dport=5432
...
```

If the lines do not appear, check `nft list ruleset` — the most common cause is `log prefix "nft-drop"` not being flushed because the chain policy is `accept` rather than `drop`.

## Use It

| Capability | `code/main.py` (policy compiler) | nftables CLI | Calico / Cilium | OpenPolicyAgent (OPA) |
|---|---|---|---|---|
| Per-host enforcement | yes | yes | yes (eBPF) | yes (via sidecar or netpol) |
| Policy-as-data (PEP/PDP split) | yes (Python dict) | no (rule files only) | yes (CaliCtl/CiliCtl) | yes (Rego) |
| Connection tracking | yes (uses kernel) | yes | yes | n/a |
| Logging | yes (log prefix per rule) | yes | yes | sidecar-side |
| Rate limiting | yes (limit rate) | yes (limit/meter) | yes | sidecar-side |
| Sets for many sources/dests | yes (nftables sets) | yes | yes (eBPF maps) | n/a |
| Identity-aware policy | partial (cgroup metadata) | yes (matches `meta cgroup`) | yes (CiliumIdentity) | yes (with identity provider) |

## Ship It

The reusable artifact is the policy DSL: `policy.py` + `code/main.py`. Drop them into any service that needs zero-trust segmentation at the host layer. The compiler emits standard nftables scripts, so it integrates with Ansible, Salt, or any config-mgmt tool that can `nft -f`. When you migrate to Kubernetes, the same policy dict translates to `CiliumNetworkPolicy` objects with a 30-line adapter.

## Exercises

1. **Add a worker tier.** Create a `worker` namespace in the `app` tier (so it has the same policies as `app`). Compile the policy and confirm `worker.nft` is emitted.
2. **Allow HTTPS out.** Modify `ALLOW` so that `data` can reach `mgmt` on port 443 (for a metrics dashboard). Re-run the compiler and confirm the new rule is in `db.nft`.
3. **Rate limit SSH.** Add a meter that rate-limits SSH from `mgmt` to `data` to 3 connections per minute. Verify by hammering `nc -vz` from `mgmt` and watching the kernel drop log.
4. **Add IPv6.** Replace the IPv4 subnets with `fd00:40:10::/64` and the policy dict with IPv6 CIDRs. Confirm the compiler emits `ip6 saddr`/`ip6 daddr` rather than `ip saddr`/`ip daddr`.
5. **Verify with conntrack.** Add a rule that drops packets with `ct state invalid` and run `nmap -sA` (ACK scan) from `attacker`; observe that ACK-only packets are dropped without affecting the legitimate `app → db` TCP flow.
6. **Replace `nc` with `nmap`.** Re-run the validation using `nmap --top-ports 100` from `attacker` to `db` and confirm the deny logs show 100 distinct drops — evidence that the policy is uniformly applied, not just on probed ports.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Zero-trust | "We have a firewall" | NIST SP 800-207: every flow is verified at the closest PEP; no implicit trust based on network location. |
| PDP | "The policy server" | Policy Decision Point — the source of truth that decides allow/deny (the Python dict in this lab). |
| PEP | "The firewall" | Policy Enforcement Point — the host kernel where the rule is actually applied (nftables chain). |
| nftables | "iptables replacement" | The unified Linux packet classification engine (RFC 9281); one rule syntax across IPv4/IPv6/ARP/bridge/netdev. |
| conntrack | "Stateful firewall" | The Linux connection tracker (RFC 4936); binds flows to `{new, established, related, invalid}` states. |
| `ct state` | "Established connections" | A match against the conntrack state tuple — the cornerstone of stateful filtering. |
| `policy drop` | "Block by default" | Default action on an nftables chain — drop anything not explicitly accepted, log the drop. |
| log prefix | "Trace every deny" | Stable string in the kernel log; SIEM rules key on this prefix to count denies per tier/peer. |

## Further Reading

- [NIST SP 800-207](https://csrc.nist.gov/publications/detail/sp/800-207/final) — Zero Trust Architecture (the foundational 2020 document)
- [RFC 9281](https://www.rfc-editor.org/rfc/rfc9281) — The NFTables Architecture (the IETF standard)
- [`nft(8)` manpage](https://manpages.debian.org/bookworm/nftables/nft.8.en.html) — the CLI surface this lesson uses
- Rose, "eBPF, Cilium, and the Future of Network Security" (Linux Foundation, 2022) — where per-host enforcement goes next
- [Calico policy reference](https://docs.tigera.io/calico/latest/reference/resources/networkpolicy) — enterprise-grade zero-trust at cluster scale
- [OpenPolicyAgent / Rego reference](https://www.openpolicyagent.org/docs/latest/policy-language/) — the PDP half of policy-as-code
- Kindervall, "Practical Linux Firewalls" (No Starch Press, 2022) — cookbook patterns for `nftables` in production