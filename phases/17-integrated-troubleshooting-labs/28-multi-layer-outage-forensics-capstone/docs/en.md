# Multi-Layer Outage Forensics Capstone

> A regional bank reports: "All online banking is down. The web portal returns `502 Bad Gateway`. Mobile app shows `SSL handshake failed`. Branch offices can reach internal systems. The outage started at 09:42 UTC and is now in its second hour." This capstone is a synthetic outage that exercises every diagnostic discipline from the prior 13 lessons: a misconfigured DNSSEC chain broke DNS resolution of the public hostname (lesson 20), a corporate proxy intercepting TLS for the partner's CDN produced a certificate chain with the wrong issuer (lesson 17), an ICMP filter on the egress firewall caused a PMTUD black hole for the mobile app's larger packets (lesson 19), an ECN-marking CoDel queue on the WAN link halved the bank's bulk transfer throughput (lesson 24), and an SSH jump-host's WireGuard endpoint was misconfigured with the wrong `AllowedIPs` (lesson 22). The diagnostic is a 30-step playbook that walks the layers from L1 to L7 and identifies which of the five simultaneous failures is the bottleneck for each symptom. The deliverable is a runbook artifact that any on-call engineer can follow to reduce the symptom to a root cause in under 10 minutes.

**Type:** Capstone
**Languages:** Python, Wireshark, nmap, dig, openssl, ip
**Prerequisites:** All 13 prior lessons in this phase
**Time:** ~180 minutes

## Learning Objectives

- Execute a multi-layer diagnostic playbook on a synthetic outage that exhibits five simultaneous failures across L3 (DNS, routing), L4 (TCP, MTU, ECN), L5/L6 (TLS, ALPN), and L7 (proxy, application).
- For each symptom, identify the responsible layer and the root cause from a fixed set of candidate failures.
- Read a `tcpdump` capture that mixes HTTP/2, DNS, TLS, and TCP events, and tag each event with the layer it belongs to.
- Compute the BDP, the path MTU, the DNSSEC chain, the TLS chain, and the ECN state for the same flow in the same capture, and explain how they interact.
- Produce a one-page runbook that maps each user-visible symptom to a single diagnostic command, the expected output, and the corrective action.
- Build a Python simulator that walks the multi-failure state machine and prints the per-symptom verdict.

## The Problem

The bank's online portal is `bank.example.com`, served by a CDN. The mobile app talks to `api.bank.example.com`. Branch offices use a separate internal network with `intranet.bank.example.internal`. The outage reports are:

| Channel | Symptom | Layer |
|---|---|---|
| Web portal | `502 Bad Gateway` | L7 (proxy) |
| Mobile app | `SSL handshake failed` for large requests, small requests OK | L4 (MTU) / L6 (TLS) |
| Bulk file transfer | 50% of expected throughput | L4 (ECN) |
| SSH jump host | `Permission denied (publickey)` | L7 (WireGuard) |
| DNS | `SERVFAIL` from corporate resolver | L7 (DNSSEC) |

Each symptom is a different failure. The diagnostic is to walk through each symptom's evidence and reduce it to a single root cause. The synthetic outage has all five failures active simultaneously.

## The Concept

### The diagnostic discipline: layer-by-layer

The 30-step playbook walks the stack from L1 to L7, narrowing the suspect set at each step. The principle: **at each layer, check the layer below's evidence first.** A L7 problem that looks like a TLS handshake failure may actually be a L3 DNS problem that returns the wrong IP. A L4 throughput problem may be a L1 link problem. Layer-by-layer prevents symptom-level guessing.

The 30 steps are grouped by layer:

| Layer | Steps | Tools |
|---|---|---|
| L1 (physical) | `ip link show`, `ethtool <iface>` | `ip`, `ethtool` |
| L2 (link) | `ip neighbor show`, `bridge fdb show` | `ip`, `bridge` |
| L3 (network) | `ip route get`, `ip route show table all`, `ping`, `tracepath` | `ip`, `tracepath` |
| L4 (transport) | `ss -ti`, `netstat -s`, `tcpdump -i any tcp` | `ss`, `tcpdump` |
| L5/L6 (TLS) | `openssl s_client -servername`, `dig +dnssec`, `tcpdump port 443` | `openssl`, `dig`, `tcpdump` |
| L7 (application) | `curl -v`, `mitmproxy`, application logs | `curl`, `mitmdump` |

### Symptom-to-cause mapping for this capstone

The synthetic outage has five failures. Each is mapped to a symptom and a diagnostic:

1. **DNSSEC chain broken (lesson 20)**: `dig +dnssec bank.example.com` returns `SERVFAIL` from the corporate resolver. The fix is to publish the new DS in the parent.
2. **TLS interception by proxy (lesson 17)**: `openssl s_client -proxy proxy.corp.example:3128 -connect bank.example.com:443` shows `issuer=CN=Corp Internal Sub-CA`. The fix is to whitelist `bank.example.com` in the proxy.
3. **PMTUD black hole (lesson 19)**: `tracepath -m 5 api.bank.example.com` shows `pmtu 1280`. The `ping -M do -s 1472` returns nothing. The fix is to add an ICMP Type 3 Code 4 rule on the egress firewall, or clamp the MSS.
4. **ECN marking with CoDel (lesson 24)**: `tc -s qdisc show dev eth0` shows `ecn_mark 12345`. The fix is to remove the `ecn` parameter from the qdisc.
5. **WireGuard `AllowedIPs` mismatch (lesson 22)**: `wg show` on the jump host shows the peer's `AllowedIPs` is `10.0.0.5/32` but the user is on `10.0.0.6`. The fix is to expand the AllowedIPs.

### The runbook format

A runbook is a one-page artifact that maps each user-visible symptom to:

- **The one command** that diagnoses it
- **The expected output** in the good case
- **The expected output** in the bad case
- **The corrective action**

The format is a 4-column table. The on-call engineer can follow the table from top to bottom, running the commands and comparing the output. The first column is the symptom, the second is the command, the third is the verdict, the fourth is the action.

### Why five failures at once

A real outage rarely has one cause. Multiple changes shipped overnight, each breaking a different channel. The on-call engineer's job is to triage which symptom blocks which user, prioritize the fix, and run the diagnostic in parallel. The capstone simulates this by presenting five symptoms at once and asking the engineer to map each to a root cause in 10 minutes.

### How the simulator models this

`code/main.py` reads a synthetic symptom report (the five channels above) and a synthetic evidence dump (the outputs of the diagnostic commands), and prints the per-symptom verdict. The simulator does not sniff live traffic; it walks a state machine for each symptom and identifies the root cause from the evidence. The output is a 5-row table with the symptom, the layer, the root cause, and the corrective action.

## Build It

1. **Set up the synthetic outage.** Use a combination of the techniques from the prior 13 lessons: a DNSSEC chain with a stale DS, a `mitmproxy` instance intercepting TLS, a `tc` filter simulating a PMTUD black hole, a CoDel qdisc with ECN marking, and a `wg0.conf` with a narrow AllowedIPs.
2. **Capture the evidence.** Run the 30-step diagnostic playbook. Capture the outputs of the key commands (`dig`, `openssl s_client`, `tracepath`, `tc -s qdisc`, `wg show`).
3. **Map to the runbook.** Fill in the 4-column table with the symptom, the command, the verdict, and the action.
4. **Apply the fixes.** Each fix is independent; apply them in any order. Confirm the symptom is resolved.
5. **Run the simulator.** `python3 code/main.py --scenario multi_outage` should print the 5-row verdict.

## Use It

| Symptom | Command | Good output | Bad output | Action |
|---|---|---|---|---|
| Web `502` | `openssl s_client -proxy <proxy> -connect <host>:443 -servername <host>` | `issuer=CN=<public CA>` | `issuer=CN=Corp Internal Sub-CA` | Whitelist in proxy |
| Mobile `SSL handshake failed` (large) | `tracepath -m 5 <host>; ping -M do -s 1472 <host>` | `pmtu 1500`; `Reply from ...` | `pmtu 1280`; nothing | MSS clamp; allow ICMP 3/4 |
| Bulk transfer 50% throughput | `tc -s qdisc show dev eth0` | `ecn_mark 0` | `ecn_mark 12345` | Remove `ecn` from qdisc |
| SSH jump `Permission denied` | `wg show` on jump host; check `AllowedIPs` | `AllowedIPs = 10.0.0.0/24` | `AllowedIPs = 10.0.0.5/32` | Expand AllowedIPs |
| DNS `SERVFAIL` | `dig +dnssec <host>` | `status: NOERROR, ad flag` | `status: SERVFAIL` | Publish new DS in parent |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **multi-layer outage forensics runbook** with the 5-row table, the 30-step diagnostic, and the corrective actions.
- A **before/after capture** of the diagnostic commands showing each symptom's good and bad outputs.

Start from `outputs/prompt-multi-layer-outage-forensics-capstone.md`.

## Exercises

1. The symptom is `502 Bad Gateway` on the web portal. The portal is behind a corporate proxy. List, in order, the three commands to run and the expected output for each (good and bad).
2. The mobile app's `SSL handshake failed` is intermittent: small requests succeed, large requests fail. What is the layer of the failure, and what is the most likely root cause?
3. The bulk file transfer peaks at 500 Mbps on a 1 Gbps link. `tc -s qdisc` shows `ecn_mark 12000`. What is the corrective action, and what is the trade-off (loss-based recovery)?
4. The SSH jump host is on `10.0.0.6` and the peer's `AllowedIPs` is `10.0.0.5/32`. The user can reach the jump host by SSH on `10.0.0.6`. Why does the connection fail with `Permission denied (publickey)`?
5. The DNSSEC chain is broken. The child's DNSKEY has a new KSK (`67890`), the parent's DS has the old KSK (`12345`). What is the corrective action, and how long until the chain is re-established (parent TTL = 86400 s)?
6. The PMTUD black hole is fixed by adding an ICMP Type 3 Code 4 rule on the egress firewall. List two alternative fixes and their trade-offs.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Layer-by-layer diagnostic | "Bottom-up triage" | The discipline of checking L1 before L2 before L3, etc., to avoid symptom-level guessing |
| Multi-failure outage | "Death by a thousand cuts" | An outage with multiple simultaneous root causes, each breaking a different channel |
| Runbook | "On-call playbook" | A one-page artifact mapping symptoms to commands, verdicts, and actions |
| `openssl s_client` | "TLS probe" | The diagnostic command for TLS handshake, certificate chain, ALPN |
| `dig +dnssec` | "DNSSEC probe" | The diagnostic command for DNSSEC chain validation |
| `tracepath` | "MTU probe" | The diagnostic command for path MTU discovery |
| `tc -s qdisc` | "Qdisc stats" | The diagnostic command for queue discipline statistics, including ECN marks |
| `wg show` | "WireGuard state" | The diagnostic command for WireGuard peer state, including AllowedIPs and latest handshake |

## Further Reading

- All 13 prior lessons in this phase (the runbook references them by name)
- IETF `opsawg` working group — operational runbooks and outage postmortems
- USENIX SREcon proceedings — incident response and triage patterns
- Brendan Gregg, "Systems Performance" 2nd ed. — the USE method (Utilization, Saturation, Errors) for layer-by-layer diagnostics
- Rob Pike, "Notes on Programming in C" — the discipline of small, focused diagnostic commands
- The SRE Book (Google) — chapters on incident response and runbook construction
