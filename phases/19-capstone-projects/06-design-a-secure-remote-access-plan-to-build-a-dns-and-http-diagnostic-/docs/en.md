# Design a Secure Remote Access Plan / Build a DNS and HTTP Diagnostic Tool

> Design a split-tunnel WireGuard remote access architecture for a 200-person company, then build a Python diagnostic tool that tests DNS resolution and HTTP reachability end-to-end through the tunnel to verify traffic flows correctly and no DNS leaks exist.

**Type:** Capstone
**Languages:** Python (stdlib + requests), shell, WireGuard
**Prerequisites:** Phase 16 VPN and security lessons, Phase 12 DNS and HTTP lessons
**Time:** ~180 minutes

---

## Learning Objectives

1. Explain the WireGuard Noise_IKpsk2 handshake and how public/private key pairs establish authenticated, encrypted tunnels without a PKI.
2. Calculate AllowedIPs CIDR ranges to implement a split-tunnel policy that routes only corporate traffic through the VPN while leaving internet-bound traffic on the local default gateway.
3. Configure DNS-over-VPN so that internal hostnames resolve through the corporate resolver and external queries never leak the tunnel's existence to public DNS servers.
4. Write a Python diagnostic tool that compares DNS answers from the internal resolver versus a public one, measures HTTP round-trip latency through each path, and flags discrepancies.
5. Verify tunnel connection state using `wg show` output, routing table entries, and `iptables -L` policy chains rather than relying on application-layer symptoms alone.
6. Apply per-group access controls using AllowedIPs and iptables to enforce that developers reach SSH targets and sales users reach only HTTPS endpoints, with traffic to all other destinations dropped at the gateway.

---

## The Problem

### Part 1 — Remote Access Architecture

A 200-person company has three employee groups: engineers who need SSH access to a fleet of internal Linux servers on `10.10.1.0/24`, a sales team that needs HTTPS access to a CRM at `10.10.2.50`, and an IT group that needs unrestricted internal access. All remote employees authenticate with a hardware MFA token before receiving a WireGuard configuration. The company's security policy requires that only traffic destined for `10.10.0.0/16` (the full internal corporate range) traverses the VPN tunnel; all other traffic—video calls, personal browsing, cloud SaaS tools—must route directly through the employee's local ISP connection. Routing everything through the VPN would saturate the corporate uplink and introduce unnecessary latency.

The DNS requirement is strict: any DNS query for `*.corp.example.com` must be answered by the internal resolver at `10.10.0.53`, and that resolver must never be reachable from outside the tunnel. Queries for public domains must not be sent through the tunnel. The architecture must prevent DNS leaks—situations where the client OS sends internal-domain queries to a public resolver before the tunnel is fully established, or after a tunnel reconnect event. Access controls are enforced at two layers: the WireGuard peer's AllowedIPs constrains which destinations a peer's packets can claim to originate for, and an iptables policy on the VPN gateway enforces group-level routing rules by matching on the peer's tunnel IP.

### Part 2 — DNS and HTTP Diagnostic Tool

Once the tunnel is running, verifying it behaves correctly requires more than checking that `ping 10.10.0.1` responds. A tunnel can pass ICMP while silently misrouting DNS, returning stale cached answers, or allowing internal hostnames to resolve through the public resolver when the tunnel is down. The diagnostic tool must actively probe three conditions: whether the internal resolver at `10.10.0.53` returns the expected answer for a given hostname, whether a public resolver like `8.8.8.8` returns a different or empty answer for the same name (confirming the name is genuinely internal), and whether the HTTP endpoint is reachable through the tunnel within an acceptable latency budget.

The tool also detects traffic leaks by querying an external IP-echo service (`https://api.ipify.org`) through the default interface and comparing the returned public IP against the expected VPN gateway egress IP. If a request that should route through the tunnel instead returns the employee's home ISP IP, the tool flags a routing misconfiguration. All results are printed as a structured report with pass/fail indicators, measured latency in milliseconds, and the specific DNS records returned by each resolver. The tool uses only Python stdlib plus `requests`; no third-party DNS libraries are required.

---

## The Concept

WireGuard uses the Noise_IKpsk2 handshake protocol, a variant of the Noise Protocol Framework that combines an ephemeral Diffie-Hellman exchange with the static public keys of both peers and an optional pre-shared key for post-quantum resistance. Each peer has a Curve25519 key pair. The initiator encrypts its static public key under the responder's known static public key, proves knowledge of its own private key through the DH operation, and both sides derive a shared session key via HKDF. The result is a mutually authenticated, forward-secret session established in a single round trip without certificates or a CA. Sessions re-key automatically every 180 seconds.

Split tunneling is implemented entirely through the `AllowedIPs` field in the peer configuration. WireGuard installs a route for each CIDR in that field pointing at the `wgN` interface. Traffic destined for any other prefix routes over the default gateway as usual. The critical constraint is that `AllowedIPs` also controls ingress: the kernel drops packets arriving from a peer whose source IP does not fall within that peer's declared AllowedIPs. This makes the field serve double duty as both a routing policy and an access control list. For a split tunnel covering the corporate range, `AllowedIPs = 10.10.0.0/16` is sufficient. Adding `0.0.0.0/0` would produce a full tunnel.

```text
Split-tunnel routing table (employee endpoint)

Destination          Gateway         Interface
10.10.0.0/16         (wg0 tunnel)    wg0          ← corp traffic: VPN
0.0.0.0/0            192.168.1.1     eth0         ← everything else: ISP

DNS resolution path:
  *.corp.example.com  →  10.10.0.53 (internal, via wg0)
  *.google.com        →  192.168.1.1 → ISP resolver (not through tunnel)

Full-tunnel would replace eth0 default with wg0:
  0.0.0.0/0           (wg0 tunnel)    wg0          ← all traffic: VPN
```

DNS leak prevention requires configuring the OS resolver to use `10.10.0.53` exclusively for `corp.example.com` queries and to forbid fallback to the system's DHCP-assigned resolver for that domain. On Linux this is done through `systemd-resolved` with per-interface DNS domains (`Domains=~corp.example.com`), which routes only matching queries to the interface-specific resolver. On macOS, `/etc/resolver/corp.example.com` achieves the same. An iptables rule on the VPN gateway blocks UDP/53 from tunnel IPs to any address except `10.10.0.53`, preventing a misconfigured client from accidentally querying a public resolver through the tunnel. Per-group access control is implemented with an iptables `mangle` table that matches each peer's tunnel-assigned IP range (engineers get `10.10.100.0/24`, sales get `10.10.101.0/24`) and enforces FORWARD chain rules that permit only the allowed destination subnets and ports.

---

## Build It

### Step 1 — WireGuard Server Configuration

Create `/etc/wireguard/wg0.conf` on the VPN gateway (`10.10.0.1`):

```ini
[Interface]
Address    = 10.10.0.1/16
ListenPort = 51820
PrivateKey = <SERVER_PRIVATE_KEY>
PostUp     = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown   = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

# Engineer peer (SSH to 10.10.1.0/24 only)
[Peer]
PublicKey  = <ENG_PEER_PUBLIC_KEY>
AllowedIPs = 10.10.100.1/32

# Sales peer (HTTPS to 10.10.2.50 only)
[Peer]
PublicKey  = <SALES_PEER_PUBLIC_KEY>
AllowedIPs = 10.10.101.1/32
```

### Step 2 — Generate Key Pairs

```bash
# On the server
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key

# For each peer (run on the peer machine)
wg genkey | tee peer_private.key | wg pubkey > peer_public.key

# Optionally generate a pre-shared key per peer pair
wg genpsk > peer_psk.key
```

### Step 3 — Client Configuration (Engineer)

```ini
[Interface]
Address    = 10.10.100.1/32
PrivateKey = <ENG_PRIVATE_KEY>
DNS        = 10.10.0.53

[Peer]
PublicKey    = <SERVER_PUBLIC_KEY>
PresharedKey = <PSK>
Endpoint     = vpn.example.com:51820
AllowedIPs   = 10.10.0.0/16
PersistentKeepalive = 25
```

The `AllowedIPs = 10.10.0.0/16` on the client side defines the split tunnel: only packets destined for the corporate /16 route through `wg0`. The `DNS = 10.10.0.53` line tells `wg-quick` to configure the OS resolver for this interface.

### Step 4 — DNS Leak Prevention (systemd-resolved)

```bash
# Verify the interface DNS config after wg-quick up wg0
resolvectl status wg0

# Expected output should show:
#   DNS Servers: 10.10.0.53
#   DNS Domain: ~corp.example.com
```

Add to `/etc/systemd/resolved.conf.d/vpn.conf`:

```ini
[Resolve]
DNS=10.10.0.53
Domains=~corp.example.com
```

### Step 5 — iptables Group Access Control

```bash
# Engineers: allow SSH (22) to server subnet only
iptables -A FORWARD -s 10.10.100.0/24 -d 10.10.1.0/24 -p tcp --dport 22 -j ACCEPT
iptables -A FORWARD -s 10.10.100.0/24 -j DROP

# Sales: allow HTTPS (443) to CRM only
iptables -A FORWARD -s 10.10.101.0/24 -d 10.10.2.50/32 -p tcp --dport 443 -j ACCEPT
iptables -A FORWARD -s 10.10.101.0/24 -j DROP

# Block DNS queries from tunnel to anything except internal resolver
iptables -A FORWARD -i wg0 -p udp --dport 53 ! -d 10.10.0.53 -j DROP
iptables -A FORWARD -i wg0 -p tcp --dport 53 ! -d 10.10.0.53 -j DROP

# Save rules
iptables-save > /etc/iptables/rules.v4
```

### Step 6 — Python Diagnostic Tool Structure

Create `vpn_diag.py` with three independent probe functions and a report printer:

```python
#!/usr/bin/env python3
"""VPN diagnostic: DNS resolution, HTTP reachability, and leak detection."""

import socket
import time
import sys
import urllib.request
import urllib.error

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

INTERNAL_DNS = "10.10.0.53"
PUBLIC_DNS   = "8.8.8.8"
EXPECTED_VPN_EGRESS = "203.0.113.10"  # replace with actual VPN gateway public IP
```

### Step 7 — DNS Probe

```python
def resolve_via(hostname: str, dns_ip: str, timeout: int = 3) -> tuple[list[str], float]:
    """Return (list_of_A_records, latency_ms) by opening a raw UDP DNS query."""
    import struct, random

    txid = random.randint(0, 65535)
    # Build minimal DNS query for A record
    qname = b"".join(len(p).to_bytes(1,"big") + p.encode() for p in hostname.split(".")) + b"\x00"
    query = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0) + qname + struct.pack(">HH", 1, 1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    t0 = time.perf_counter()
    try:
        sock.sendto(query, (dns_ip, 53))
        resp, _ = sock.recvfrom(512)
        latency = (time.perf_counter() - t0) * 1000
    except socket.timeout:
        return [], -1.0
    finally:
        sock.close()

    # Parse answer count and extract A records from response
    ancount = struct.unpack_from(">H", resp, 6)[0]
    addrs, offset = [], 12 + len(qname) + 4  # skip header + question
    for _ in range(ancount):
        offset += 2   # name (pointer or label assumed)
        rtype, _, _, rdlen = struct.unpack_from(">HHIH", resp, offset)
        offset += 10
        if rtype == 1 and rdlen == 4:   # A record
            addrs.append(socket.inet_ntoa(resp[offset:offset+4]))
        offset += rdlen
    return addrs, round(latency, 2)
```

### Step 8 — HTTP Reachability and Latency

```python
def http_probe(url: str, timeout: int = 5) -> tuple[int, float]:
    """Return (status_code, latency_ms). status -1 means connection failed."""
    t0 = time.perf_counter()
    try:
        if HAS_REQUESTS:
            r = requests.get(url, timeout=timeout, allow_redirects=True)
            return r.status_code, round((time.perf_counter() - t0) * 1000, 2)
        else:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.status, round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        return -1, round((time.perf_counter() - t0) * 1000, 2)


def egress_ip(timeout: int = 5) -> str:
    """Return the public IP that outbound traffic exits from."""
    try:
        if HAS_REQUESTS:
            return requests.get("https://api.ipify.org", timeout=timeout).text.strip()
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return r.read().decode().strip()
    except Exception:
        return "UNKNOWN"
```

### Step 9 — Report and Main Entry Point

```python
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

def run_report(hostname: str, http_url: str) -> None:
    print(f"\n=== VPN Diagnostic Report: {hostname} ===\n")

    # DNS comparison
    int_addrs, int_lat = resolve_via(hostname, INTERNAL_DNS)
    pub_addrs, pub_lat = resolve_via(hostname, PUBLIC_DNS)

    int_ok = len(int_addrs) > 0
    leak   = len(pub_addrs) > 0  # public resolver should NOT know internal names

    print(f"DNS via internal ({INTERNAL_DNS}): {int_addrs or 'NXDOMAIN'}  [{int_lat} ms]  "
          f"{'  ' + PASS if int_ok else '  ' + FAIL}")
    print(f"DNS via public   ({PUBLIC_DNS}):   {pub_addrs or 'NXDOMAIN'}  [{pub_lat} ms]  "
          f"{'  ' + FAIL + ' (DNS LEAK)' if leak else '  ' + PASS + ' (name is private)'}")

    # HTTP reachability
    status, lat = http_probe(http_url)
    http_ok = 200 <= status < 400
    print(f"HTTP {http_url}: status={status}  [{lat} ms]  {'  ' + PASS if http_ok else '  ' + FAIL}")

    # Egress leak detection
    actual_egress = egress_ip()
    egress_ok = actual_egress == EXPECTED_VPN_EGRESS
    print(f"Egress IP: {actual_egress}  (expected {EXPECTED_VPN_EGRESS})  "
          f"{'  ' + PASS if egress_ok else '  ' + FAIL + ' (traffic not exiting VPN)'}")

    # Summary
    all_pass = int_ok and not leak and http_ok and egress_ok
    print(f"\nOverall: {'  ' + PASS if all_pass else '  ' + FAIL}\n")


if __name__ == "__main__":
    host    = sys.argv[1] if len(sys.argv) > 1 else "intranet.corp.example.com"
    url     = sys.argv[2] if len(sys.argv) > 2 else "https://crm.corp.example.com"
    run_report(host, url)
```

---

## Use It

| Task | Command / Tool | What Good Looks Like |
|------|----------------|----------------------|
| Bring up the tunnel | `wg-quick up wg0` | No errors; `wg show` lists the peer with a valid handshake timestamp |
| Inspect tunnel state | `wg show wg0` | `latest handshake` within the last 3 minutes; `transfer` bytes incrementing |
| Verify routing table | `ip route show table main \| grep wg0` | `10.10.0.0/16 dev wg0` present; no `0.0.0.0/0` via wg0 (split tunnel) |
| Check DNS resolver | `resolvectl status wg0` | `DNS Servers: 10.10.0.53`, `DNS Domain: ~corp.example.com` |
| Run diagnostic tool | `python3 vpn_diag.py intranet.corp.example.com https://crm.corp.example.com` | All four probes show PASS; no DNS LEAK flag |
| Verify iptables policy | `iptables -L FORWARD -n -v` | Engineer source range shows DROP on non-port-22 hits; counter increments on blocked sales attempts |
| Test DNS leak manually | `dig @8.8.8.8 intranet.corp.example.com` | `NXDOMAIN` — public resolver must not know the name |

---

## Ship It

Deliver four artifacts under `outputs/`:

**`wg0-server.conf.template`** — Annotated WireGuard server config with placeholder keys, per-group peer blocks, and PostUp/PostDown iptables hooks. Strip all real keys before committing.

**`iptables-vpn-policy.sh`** — Idempotent shell script that flushes and re-applies the full FORWARD chain: engineer SSH rule, sales HTTPS rule, DNS lock-down rule, and default DROP. Includes `iptables-save` at the end.

**`vpn_diag.py`** — The complete diagnostic tool from Steps 6–9. Accepts `hostname` and `http_url` as positional arguments. Zero dependencies beyond `requests` (optional); falls back to `urllib` when `requests` is absent.

**`remote-access-runbook.md`** — A one-page operational runbook covering: how to provision a new peer (key generation, config distribution, MFA enrollment), how to rotate keys without downtime, how to diagnose a failing tunnel using `wg show` and the diagnostic tool, and the escalation path when the diagnostic tool reports a DNS leak or egress IP mismatch.

---

## Exercises

1. **Full tunnel mode.** Modify the client config to route all traffic through the VPN (`AllowedIPs = 0.0.0.0/0, ::/0`). Update the diagnostic tool's egress check to confirm that both IPv4 and IPv6 traffic exits through the VPN gateway. Measure the latency increase for a public HTTPS request compared to split-tunnel mode.

2. **Simulated DNS leak.** Temporarily remove the `DNS` line from the client `[Interface]` block and reconnect. Run `python3 vpn_diag.py` and verify the tool detects the leak. Restore the config and confirm the PASS result returns. Document which OS resolver was used during the leak.

3. **Certificate pinning over VPN.** Add TLS certificate pinning to `http_probe` by comparing the SHA-256 fingerprint of the server's leaf certificate against a hardcoded expected value. Use `ssl.get_server_certificate` and `hashlib`. Explain why certificate pinning is more important over a VPN than over a direct corporate LAN connection.

4. **IPv6 split tunnel.** Add an IPv6 tunnel address to the WireGuard interface (`fd00::/120`). Extend `AllowedIPs` to include the corporate IPv6 prefix. Update `resolve_via` to query AAAA records in addition to A records. Verify that IPv6 DNS queries for internal names resolve correctly while public IPv6 traffic bypasses the tunnel.

5. **Bandwidth and jitter measurement.** Extend the diagnostic tool with a `bandwidth_probe` function that sends a 1 MB HTTP GET to an internal test endpoint, records throughput in Mbit/s, and samples 10 round-trip times to compute jitter. Add these metrics to the report output.

6. **Peer revocation drill.** Remove a peer's `[Peer]` block from `wg0.conf` and reload with `wg syncconf wg0 <(wg-quick strip wg0)`. Confirm with `wg show` that the peer no longer has an active session. Verify with the diagnostic tool that the revoked peer's tunnel IP now fails HTTP reachability within 5 seconds of removal—without restarting the WireGuard process.

---

## Key Terms

| Term | Short Definition | Operational Relevance |
|------|-----------------|----------------------|
| WireGuard | Modern VPN protocol using Noise_IKpsk2 | Replaces OpenVPN/IPsec for most corporate remote-access use cases |
| AllowedIPs | Per-peer CIDR allowlist in WireGuard | Controls both routing and ingress ACL simultaneously |
| Split tunnel | VPN mode routing only selected prefixes | Preserves corporate bandwidth; internet traffic goes direct |
| Full tunnel | VPN mode routing all traffic (0.0.0.0/0) | Maximum privacy; higher latency; required for strict egress control |
| DNS leak | Internal query answered by public resolver | Exposes internal hostname existence to third parties |
| Noise_IKpsk2 | Handshake variant in WireGuard | Provides mutual auth + forward secrecy in one round trip |
| HKDF | HMAC-based key derivation function | Derives session keys from DH output in WireGuard handshake |
| Pre-shared key (PSK) | Optional symmetric key layered over DH | Adds post-quantum resistance to WireGuard sessions |
| PersistentKeepalive | UDP keepalive interval in seconds | Keeps NAT mappings alive for peers behind home routers |
| Egress IP | Public IP seen by external servers | Used to verify traffic exits through the VPN gateway, not direct |
| iptables FORWARD chain | Kernel netfilter chain for routed packets | Enforces per-group access control on the VPN gateway |

---

## Further Reading

- **WireGuard Whitepaper** — J. Donenfeld, "WireGuard: Next Generation Kernel Network Tunnel," NDSS 2017. Covers the Noise_IKpsk2 handshake, cryptographic primitives, and routing model in full detail. `https://www.wireguard.com/papers/wireguard.pdf`
- **RFC 8446 — TLS 1.3** — The IETF specification for the handshake protocol that WireGuard's Noise framework was designed to complement at the transport layer. Relevant for understanding ephemeral DH key exchange patterns.
- **WireGuard Quick Start** — Official configuration reference for `wg0.conf` fields, `wg-quick` lifecycle hooks, and `AllowedIPs` semantics. `https://www.wireguard.com/quickstart/`
- **systemd-resolved(8) man page** — Documents `Domains=~example.com` split-DNS syntax, per-interface resolver assignment, and DNSSEC validation. Essential for DNS leak prevention on Linux. `man systemd.network`
- **Netfilter/iptables HOWTO** — Covers FORWARD chain semantics, connection tracking with `-m state`, and MASQUERADE for VPN gateway NAT. `https://netfilter.org/documentation/`
