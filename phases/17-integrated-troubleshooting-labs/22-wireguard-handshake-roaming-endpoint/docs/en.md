# WireGuard Handshake Failure and Roaming Endpoint

> A mobile engineer connects a laptop to a corporate WireGuard endpoint at `vpn.corp.example:51820`. The laptop's public key is `Abc123...`, the server's public key is `Xyz789...`, and the allowed-IPs list is `0.0.0.0/0` (full tunnel). The handshake completes (the laptop shows `latest handshake: 5 seconds ago`), the laptop can ping `10.0.0.1` (the corporate gateway), and the user can `ssh corp-internal`. The user closes the lid, opens it 30 minutes later in a coffee shop, the laptop attaches to a different Wi-Fi, and the laptop's source IP changes from `203.0.113.42:43210` to `198.51.100.91:55001`. The connection appears to keep working — `wg show` says `latest handshake: 30 minutes ago` and `transfer: 1.2 MB received` — but `ssh corp-internal` hangs and `tcpdump` shows no packets on the new source. The cause: WireGuard *roams* when it sees a valid handshake response on a new source IP, but the `latest handshake: 30 minutes ago` is the *old* handshake; the kernel has not initiated a new handshake because the keepalive timer has not fired, and the `0.0.0.0/0` allowed-IPs have not triggered a new session. The first packet the user sends from the new IP carries the *old* session's `receiver_index` and is rejected by the server because the server's `latest_handshake` for that index has expired (default 2 minutes of silence = handshake considered stale). The fix is the `persistentkeepalive` option in the peer section: `wg set wg0 peer <pubkey> persistentkeepalive 25` sends a keepalive every 25 seconds and forces a fresh handshake, so the kernel updates the endpoint. Without it, the kernel uses the cached endpoint until the next handshake timer (default 2 minutes of silent rekey) expires.

**Type:** Lab
**Languages:** Python, shell, wireguard-tools
**Prerequisites:** Phase 14 Noise protocol framework, Phase 16 IPsec / WireGuard comparison, the WireGuard whitepaper
**Time:** ~100 minutes

## Learning Objectives

- Diagnose a WireGuard tunnel that *appears* to be working (`wg show` reports a recent handshake) but does not actually carry packets after a NAT rebind: read `wg show` output, identify the cached endpoint, and explain the role of `persistentkeepalive`.
- Explain the WireGuard handshake (Noise IKpsk2, RFC 8446-inspired but custom): the initiator sends a 148-byte first message, the responder replies with a 92-byte second message, and both sides derive a symmetric key. The handshake is bound to a `sender_index` and `receiver_index`; the kernel keeps a map of `receiver_index -> session state`.
- Distinguish three failure modes: (a) handshake failure (the `latest handshake` is `never` or hours old), (b) roaming failure (the endpoint is cached and a NAT rebind is not detected), (c) allowed-IPs mismatch (a packet for an IP not in the peer's `AllowedIPs` is dropped silently).
- Use `wg show` and `wg showconf` to read the current peer state: `endpoint`, `latest handshake`, `transfer`, `persistent keepalive`.
- Use `tcpdump -i any -n udp port 51820` to capture the WireGuard handshake and the encrypted transport packets; interpret the 16-byte header (4 type, 4 receiver, 4 sender, 8 nonce) and the encrypted payload.
- Build a Python simulator that walks the WireGuard handshake state machine and the roam-detection logic, and prints the verdict that matches the production `wg show` output.

## The Problem

The on-call SRE gets a ticket from a field engineer: "WireGuard says it's connected, but I can't reach anything. `wg show` looks fine, but the moment I send a packet, the tunnel drops the first few and then re-establishes." The user is on a mobile laptop that moves between Wi-Fi networks, and the corporate WireGuard endpoint is at `vpn.corp.example:51820`.

The root cause is the cached endpoint. WireGuard's `wg` kernel module keeps a `peer.endpoint` for each peer, the IP:port it last successfully used. When the user moves, the kernel does not proactively probe the new IP — it waits for a packet to be sent, at which point the kernel sends a UDP datagram from the *new* source to the *cached* endpoint. If a NAT on the path is stateful and the old flow is gone, the datagram arrives at the server from a new source, the server's conntrack creates a new entry, the datagram reaches the WireGuard handler, and the handler checks the `receiver_index`. If the index matches a session in the server's map, the datagram is accepted as part of the existing session. If not, the datagram is dropped (or the server tries to initiate a new handshake from the new endpoint).

The subtlety: the *client's* `receiver_index` is the server's *sender_index*. When the client roams, the client's `sender_index` does not change (it is the index the *client* uses), but the server's view of the client's source IP is stale. The server's `latest_handshake` for that session is still based on the old endpoint. The fix is `persistentkeepalive 25`: every 25 seconds, the client sends an empty transport packet that triggers the server to update its view of the client's source IP. The keepalive is what enables roaming.

Without `persistentkeepalive`, the kernel uses the cached endpoint until either (a) a rekey timer fires (default every 2 minutes), (b) a new packet needs to be sent and the handshake is re-attempted, or (c) the `latest_handshake` for the index has expired (default 2 minutes of silence = the index is considered stale and a new handshake is forced).

## The Concept

### The WireGuard handshake (Noise IKpsk2)

WireGuard uses the Noise protocol framework with a custom pattern: Noise_IKpsk2 (Initiator Knows, Pre-Shared Key, 2 messages). The handshake has exactly two messages:

- **Message 1 (148 bytes)**: the initiator sends its static public key (encrypted under the responder's static public key, using ECIES), a `sender_index` (a random 4-byte nonce that identifies this session), an ephemeral public key, an encrypted timestamp, and a MAC. The responder uses this to derive a symmetric chain key.
- **Message 2 (92 bytes)**: the responder sends its static public key (encrypted), a `sender_index`, an ephemeral public key, an encrypted empty payload, and a MAC. The initiator verifies the responder knows the pre-shared key (if configured) and derives the same transport keys.

The handshake is bound to the pre-shared key (optional) and the static keypairs. The `sender_index` and `receiver_index` are the session identifiers; they appear in every transport packet header and let the peer look up the session state for decryption.

### The transport packet format

Every post-handshake WireGuard packet is a UDP datagram with the following structure:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Type = 4     |    Reserved   |       Receiver Index          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sender Index                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Encrypted Nonce                          |
|                       (8 bytes)                                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Encrypted Payload ...                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Type**: 4 for transport, 1 for handshake initiation, 2 for handshake response, 3 for cookie reply, 4 for transport data.
- **Receiver Index**: 4-byte index the receiver uses to look up the session.
- **Sender Index**: 4-byte index the sender assigned to this session.
- **Encrypted Nonce**: 8-byte nonce, encrypted with the same key as the payload.
- **Encrypted Payload**: the actual IP packet, encrypted with ChaCha20-Poly1305.

The receiver reads the `Receiver Index`, looks up the session, decrypts the nonce, validates the Poly1305 tag, and decrypts the payload. If the index is unknown, the packet is dropped.

### Roaming and the role of `persistentkeepalive`

WireGuard's roam detection is *reactive*: the kernel uses the cached endpoint until it sees a reason to update it. The reasons are:

- A new packet is sent and the handshake timer has expired (default 2 minutes of silence) — the kernel initiates a new handshake.
- A `persistentkeepalive` packet is sent (the user-configured interval) — this empty transport packet is delivered to the server from the *current* source, updating the server's `latest_handshake` and the kernel's view of the source.
- A rekey event (default every 2 minutes) — a new handshake is initiated and the source is updated.

The practical recommendation is `persistentkeepalive 25` for any client that moves between networks. Server-side peers behind a NAT should also have a keepalive to keep the NAT binding open.

### Allowed-IPs and routing

WireGuard's `AllowedIPs` in the peer section serves two roles:

1. **Cryptographic routing**: only packets whose destination IP is in the peer's `AllowedIPs` list are sent through that peer's tunnel.
2. **Source filtering**: only packets with a source IP in the `AllowedIPs` list are accepted from the peer.

A common misconfiguration: the server's `AllowedIPs` for a peer is `10.0.0.5/32` (only that IP), but the client is sending packets for `10.0.0.0/24`. The server drops them silently. The fix is to add the missing subnets to the peer's `AllowedIPs`.

### How `wg show` reports state

`wg show wg0` prints the interface state. The relevant fields per peer:

- `endpoint`: the last-known source IP:port of the peer, or `(none)` if never seen.
- `latest handshake`: how long ago the last handshake completed; `never` if the handshake has not yet happened.
- `transfer`: `X bytes received, Y bytes sent`.
- `persistent keepalive`: `every 25 seconds` if configured, `off` if not.

A peer with `latest handshake: 2 minutes ago` and `transfer: 0 bytes received` is *not* an active session — the handshake timed out and the kernel is waiting for the next rekey.

### How the simulator models this

`code/main.py` walks the WireGuard handshake state machine and the roam-detection logic for a configurable scenario (`--scenario handshake_fail`, `--scenario roam_works`, `--scenario roam_breaks`, `--scenario allowed_ips_mismatch`). The simulator prints the events, the `wg show` output, and the verdict that matches a production diagnosis.

## Build It

1. **Set up a WireGuard endpoint.** A Linux VM with `wg-quick up wg0` and a `wg0.conf` with a peer whose `AllowedIPs` includes the client's tunnel IP.
2. **Connect a client.** `wg-quick up wg0` on the client with the server's public key. Confirm `wg show` reports a recent handshake.
3. **Simulate a roam.** Use `ip addr` to change the client's source IP, or move the client to a different network namespace. Send a packet. Observe the staleness.
4. **Apply the fix.** `wg set wg0 peer <pubkey> persistentkeepalive 25`. Re-test. Confirm the roam is now seamless.
5. **Run the simulator.** `python3 code/main.py --scenario roam_breaks` should print the matching state machine.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm handshake is fresh | `wg show` `latest handshake: 5 seconds ago` | Handshake completed within the rekey window |
| Confirm endpoint is correct | `wg show` `endpoint: 198.51.100.91:55001` | Endpoint matches the client's current source |
| Confirm keepalive is on | `wg show` `persistent keepalive: every 25 seconds` | Keepalive configured; roaming is reliable |
| Confirm AllowedIPs | `wg showconf` `AllowedIPs = 10.0.0.0/24` | AllowedIPs covers the IPs the peer is sending |
| Confirm transport | `tcpdump -i wlan0 -n udp port 51820` | Encrypted transport packets, type=4, no decryptable payload |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **WireGuard roam failure runbook** with the four `wg` commands and the `persistentkeepalive` fix.
- A **before/after capture** of the same `wg show` output before and after enabling the keepalive, showing the stale `latest handshake` recovering.

Start from `outputs/prompt-wireguard-handshake-roaming-endpoint.md`.

## Exercises

1. A peer's `latest handshake: 5 minutes ago` and `transfer: 0 bytes received`. The user reports the tunnel "feels up." Is the tunnel healthy? Cite the relevant kernel state.
2. A peer's `AllowedIPs = 10.0.0.5/32` and the client is sending to `10.0.0.6`. What happens on the server, and what is the symptom for the user?
3. Compute the on-the-wire size of a WireGuard transport packet carrying a 1,400-byte inner IP packet. Include the 16-byte header, the 16-byte Poly1305 tag, and the UDP overhead.
4. The Noise pattern is `IKpsk2`. What do the letters `I`, `K`, `psk`, and `2` mean? Cite the Noise protocol framework.
5. A server has 100 peers, none of which have `persistentkeepalive` set. The server's UDP socket is behind a stateful NAT with a 60-second idle timeout. After 60 seconds of silence from a peer, the NAT binding expires. What is the consequence when the peer next sends a packet?
6. `tcpdump -i wlan0 -nn -X 'udp port 51820'` shows a packet with the first byte `0x04`. What kind of WireGuard packet is it, and what is the next step in the kernel?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WireGuard | "Modern VPN" | A kernel-mode VPN that uses the Noise protocol framework (Noise_IKpsk2), UDP transport, ChaCha20-Poly1305 |
| Noise IKpsk2 | "Handshake pattern" | A 2-message Noise pattern with pre-shared key: I = initiator knows responder's static, K = static keys mixed, psk = pre-shared key, 2 = two messages |
| Roaming | "Moving networks" | A WireGuard client's ability to change source IP without dropping the tunnel, enabled by `persistentkeepalive` |
| `persistentkeepalive` | "Keep the tunnel alive" | The wg config option that forces a transport packet every N seconds, refreshing the endpoint in the peer |
| `AllowedIPs` | "Cryptographic routing" | Both the IPs a peer is allowed to send (source filter) and the IPs routed through the peer (crypto routing) |
| `latest handshake` | "When was the last rekey" | The wg show field showing how long ago the Noise handshake completed; > 2 min = rekey needed |
| Receiver / sender index | "Session id" | 4-byte random nonces in every WireGuard packet header that let the peer look up the session state |
| Cookie reply | "Anti-amplification" | WireGuard type 3: the responder sends a cookie to a flooding source to rate-limit handshakes |

## Further Reading

- WireGuard whitepaper (Donenfeld, 2017) — design rationale, Noise pattern, kernel implementation
- The Noise protocol framework ( Perrin, 2018) — the IK, IKpsk, IKpsk2 patterns
- `wg(8)`, `wg-quick(8)`, `wg-show(8)` man pages
- `tcpdump(8)` — UDP port 51820 capture
- WireGuard protocol specification — https://www.wireguard.com/protocol/
- IPsec / WireGuard comparison notes — performance, key management, NAT traversal
