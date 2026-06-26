# Capstone: end-to-end secure channel across IPsec, TLS, and Kerberos

> A real production network stacks at least four security layers, each addressing a different threat model: IPsec (RFC 4303) encrypts and authenticates every IP packet between two security gateways, defending against on-path attackers on the underlay; IKEv2 (RFC 7296) negotiates the IPsec Security Associations and authenticates the gateways with either pre-shared keys or certificates; Kerberos (RFC 4120) authenticates the user at login and mints a service ticket that the workload accepts without re-asking for credentials; TLS 1.3 (RFC 8446) inside the tunnel provides end-to-end mutual authentication between the workload and the service it talks to, with a separate X.509 trust anchor and forward-secret ECDHE. Each layer fixes a flaw in the layer below it: TLS without IPsec leaks the destination's IP to the underlay carrier; Kerberos without TLS lets any workload that can reach the service pretend to be that service. This capstone walks one packet end-to-end through all four, shows the trust anchors at each layer, and demonstrates a failure injection that is detected at the right layer.

**Type:** Capstone
**Languages:** Python, shell, OpenSSL, packet traces
**Prerequisites:** All Phase 16 lessons (18–24), Phase 13 (HTTP semantics), Phase 09 (IP operations)
**Time:** ~180 minutes

## Learning Objectives

- Stack four security layers (IPsec ESP → IKEv2 → Kerberos AP-REQ → TLS 1.3 ClientHello) on a single end-to-end request and identify what each layer protects against.
- Configure a minimal IPsec transform: ESP with AES-128-GCM, Security Parameter Index (SPI) `0xC0FFEE`, Security Association Database (SAD) entry keyed by `(src, dst, spi)`.
- Run an IKEv2 `IKE_SA_INIT` / `IKE_AUTH` exchange with PSK authentication and confirm the IKE SA keys flow into the IPsec SA.
- Authenticate a user via Kerberos, receive a service ticket for the target workload, and embed the AP-REQ inside the TLS 1.3 handshake as `Authorization: Negotiate` (SPNEGO, RFC 4559).
- Open a TLS 1.3 connection with client certificate authentication over the IPsec-protected transport; verify the chosen cipher and the post-quantum-safe key share.
- Inject failures at each layer (wrong SPI, expired Kerberos ticket, untrusted certificate, mismatched cipher suite) and confirm the right layer reports the failure with a precise error code.

## The Problem

You join a security team at a mid-sized SaaS company. Their incident report says: "Customer reports 5xx on the /api/v3/billing endpoint. We see TCP retransmits and connection resets. We don't know if it's the load balancer, the IPsec tunnel to the regional gateway, the user's Kerberos ticket expiring, or the TLS handshake failing."

The senior engineer on call walks you through their mental model: every packet that arrives at a service mesh workload has passed through (at minimum) four security perimeters, each with its own authentication, its own session keys, and its own failure mode. Knowing which perimeter failed is the difference between a 10-minute fix and a 4-hour war-room. The mental model is exactly the structure of this capstone:

1. **IPsec ESP** (RFC 4303) — the underlay carrier (AWS Direct Connect, MPLS, inter-DC) encrypts packets between two known gateways. Without this, an attacker on the carrier network can read or rewrite everything. Failure: ESP sequence number replay, SPI mismatch, expired SA.
2. **IKEv2** (RFC 7296) — negotiates the IPsec SAs and authenticates the gateways. Without this, you cannot set up IPsec in the first place. Failure: PSK mismatch, certificate verification, DPD timeout.
3. **Kerberos** (RFC 4120) — the user's identity is bound to a service ticket for the target workload. Without this, any workload that can route to the service can call it. Failure: clock skew, TGS unreachable, ticket expired.
4. **TLS 1.3** (RFC 8446) — the workload and the service mutually authenticate at the application layer. Without this, a compromised gateway could proxy through. Failure: certificate verification, cipher mismatch, SNI mismatch.

You do not have to memorize all four RFCs to debug a problem — you have to know *which layer* owns *which failure mode*, and how to read the error from each layer in its own protocol vocabulary.

## The Concept

### The packet's journey

```
[User] --TLS 1.3--> [Service Proxy] --Kerberos AP-REQ--> [Backend] 
                  (IPsec ESP encrypted underlay)
                  (IKEv2-negotiated SA)
```

A single user request inside the user's browser produces:

1. **TLS 1.3 ClientHello** wrapping an HTTP GET with `Authorization: Negotiate <base64-AP-REQ>` (RFC 4559 SPNEGO). The TLS layer carries a client certificate (mutual auth).
2. The TLS record is wrapped in a **TCP segment** to the service proxy.
3. The TCP segment is wrapped in an **IP packet** to the service proxy's IP.
4. That IP packet is wrapped in an **ESP packet** (`protocol=50`, SPI=`0xC0FFEE`) to the regional security gateway.
5. The ESP packet is wrapped in another **IP packet** to the gateway (this is IPsec tunnel mode; ESP can also run in transport mode without the outer IP header).
6. The outer IP packet traverses the carrier (MPLS, leased line, transit provider).
7. At the gateway, ESP is decrypted, the inner IP packet emerges, and is routed to the service proxy.
8. The service proxy terminates TLS, reads the AP-REQ, validates the Kerberos ticket, and either accepts or rejects the request.

### The trust anchors at each layer

| Layer | Trust anchor | Failure to anchor | Real error |
|---|---|---|---|
| IPsec (ESP) | SPI in the SAD; gateway IP | SPI mismatch | Kernel drops silently; ESP ICMP "bad SPI" |
| IKEv2 | PSK or gateway certificate | PSK mismatch | `IKE_AUTH_FAILED` notification (RFC 7296 §3.10.1) |
| Kerberos | KDC long-term key (`krbtgt`) | Clock skew, expired ticket | `KRB_AP_ERR_SKEW`, `KRB_AP_ERR_TKT_EXPIRED` |
| TLS 1.3 | CA bundle pinning or TOFU | Unknown CA, name mismatch | `tlsv13 alert "unknown ca"` (RFC 8446 §6.2) |

Notice the discipline: each layer fails closed, with an error message that identifies the layer. A debug session that produces an IKE error is a network-layer problem; an SPNEGO error is an authentication problem; a TLS alert is a transport-layer problem. The art is to read the error code first, not the stack trace.

### IPsec ESP and the Security Association Database (SAD)

Every IPsec-protected packet carries a 32-bit Security Parameter Index (SPI) in the ESP header. The receiving kernel looks up `(src_ip, dst_ip, spi)` in the SAD and finds:

- The encryption algorithm (AES-128-GCM in our stack)
- The encryption key
- The anti-replay sequence number window
- The lifetime (bytes and seconds)

A packet with an SPI not in the SAD is dropped silently. A packet with a sequence number outside the anti-replay window is dropped silently. ESP-encrypted payload looks like random bytes to anyone without the SAD entry.

### IKEv2

IKEv2 negotiates the IPsec SAs in two round trips:

- `IKE_SA_INIT`: each side generates a Diffie-Hellman key pair (RFC 3526 group 14 or X25519), exchanges public values, derives the `SKEYSEED`, and produces encryption keys for the rest of IKEv2.
- `IKE_AUTH`: each side authenticates (PSK or certificate), exchanges identities (IDi, IDr), and proposes IPsec SAs (`SAi2`, `SAr2`).

Once `IKE_AUTH` completes, both sides install the IPsec SA in the kernel (`ip xfrm state add ...`) and traffic flows through ESP automatically.

### Kerberos AP-REQ over SPNEGO (RFC 4559)

The service ticket (lesson 21) is wrapped in an SPNEGO `NegTokenInit` or `NegTokenTarg` structure and sent in the HTTP `Authorization: Negotiate` header. The service proxy decodes the SPNEGO token, extracts the Kerberos AP-REQ, validates the ticket against the KDC, and either accepts (returns `WWW-Authenticate: Negotiate <token>` for mutual auth) or rejects (`401 Unauthorized` with `WWW-Authenticate: Negotiate` and a `KRB_AP_ERR_*` error code in the response data).

### TLS 1.3 with mutual auth

The TLS 1.3 ClientHello includes a `certificate` extension carrying the client certificate chain. The server replies with its own certificate chain in the encrypted `Certificate` message. Both sides send `CertificateVerify` signatures over the handshake transcript. If the server's CA is trusted and the client's certificate matches the server's expected issuer, the handshake completes; otherwise the server sends an alert (`bad_certificate`, `unsupported_certificate`, `certificate_revoked`, `unknown_ca`) and closes the connection.

## Build It

### Step 1 — Set up the IPsec transform table

```python
from main import ESPTransform, install_sa, ESP_HEADER

sa = ESPTransform(
    spi=0xC0FFEE,
    src="10.0.0.1", dst="10.0.0.2",
    encryption_key=secrets.token_bytes(16),
    anti_replay_window=64,
)
install_sa(sa)
```

The simulator's `install_sa` adds the entry to an in-memory SAD. A real kernel would call `setkey` or `ip xfrm`.

### Step 2 — Run an IKEv2 PSK exchange

```python
from main import IKEv2PSK

client = IKEv2PSK(identity="gateway-a.example.com", psk=b"shared secret")
server = IKEv2PSK(identity="gateway-b.example.com", psk=b"shared secret")
ike_sa = client.exchange(server.init_payload())
```

The simulator generates the two Diffie-Hellman halves, derives the IKE SA keys (`SK_e`, `SK_a`, `SK_d`), and returns the negotiated IPsec transform.

### Step 3 — Issue a Kerberos service ticket

```python
from main import issue_kerberos_ticket

ticket = issue_kerberos_ticket(realm, user="alice", service="http/backend.internal@EXAMPLE.COM")
ap_req = ticket.to_ap_req()
spnego_token = wrap_spnego(ap_req)
```

The `wrap_spnego` function produces a base64-encoded `NegTokenInit` suitable for the `Authorization: Negotiate` header.

### Step 4 — Open the TLS 1.3 connection

```python
from main import TLS13Mutual

mutual = TLS13Mutual(
    client_cert=alice_cert_der,
    client_priv=alice_priv_rsa,
    server_name="backend.internal",
)
client_hello = mutual.client_hello(ap_req_token=spnego_token)
server_finished = mutual.parse_server_flight(server_response)
mutual.verify_application_traffic_secrets()
```

The simulator returns the negotiated cipher suite, the key share group, and the derived application traffic secrets. It does not perform AEAD encryption but tracks every state transition.

### Step 5 — Inject failures and observe the right layer

```python
from main import (
    inject_wrong_spi, inject_expired_ticket, inject_unknown_ca, inject_cipher_mismatch,
)

inject_wrong_spi(sa)        # IPsec layer: ESP ICMP "bad SPI"; tunnel drops
inject_expired_ticket(ticket) # Kerberos: KRB_AP_ERR_TKT_EXPIRED; 401 Negotiate
inject_unknown_ca(client_cert) # TLS: alert "unknown ca"; handshake aborts
inject_cipher_mismatch()    # TLS: ServerHello picks a different suite; client adapts
```

## Use It

| Layer | Real-world debugging tool | Output you read |
|---|---|---|
| IPsec | `setkey -D`, `ip xfrm state`, `tcpdump -n esp` | SPI list, replay counters, lifetime remaining |
| IKEv2 | `strongSwan`/`charon` logs, `ike-scan`, `wireshark` ISAKMP dissector | `IKE_AUTH_FAILED` notification, PSK mismatch, certificate chain validation |
| Kerberos | `kinit`, `klist`, `kdestroy`, `krb5kdc.log`, Wireshark KRB5 dissector | `KRB_AP_ERR_SKEW`, `KRB_AP_ERR_TKT_EXPIRED`, `KDC_ERR_PREAUTH_FAILED` |
| TLS 1.3 | `openssl s_client -msg -debug`, `curl -v`, Wireshark TLS dissector | `Alert (Level: Fatal, Description: bad_certificate)` |

The discipline: when you read an error, locate which layer it came from, then look only at that layer's debugging tool. Looking at the TLS dissector when the IPsec tunnel is down is wasted time.

## Ship It

The reusable artifact in `outputs/prompt-secure-channel-capstone.md` is a runnable Python package `secure_channel_sim/` with:

- `ipsec.py` — `ESPTransform`, `install_sa`, `esp_encapsulate(plaintext_ip, sa)`, `esp_decapsulate(esp_packet, sad)`.
- `ikev2.py` — `IKEv2PSK.exchange()` and `derive_ipsec_sa()`.
- `kerberos.py` — `issue_kerberos_ticket()` and `wrap_spnego()`.
- `tls13.py` — `TLS13Mutual` state machine and `client_hello(ap_req_token=...)`.
- `cli.py` — runs all four layers end-to-end and prints each layer's negotiation transcript.

## Exercises

1. Drop the ESP header and capture with `tcpdump -i any -n esp`. Why is the payload unreadable? How does the gateway know which SAD entry to use? (Hint: the SPI in the ESP header is keyed by `(src, dst, spi)`.)
2. Run `strongSwan` between two Linux namespaces and observe the IKEv2 exchange with `tcpdump -i any -n udp port 500 -w ike.pcap`. Decode it with Wireshark: how many round trips? Which messages are encrypted?
3. `kinit alice@EXAMPLE.COM`, then `kvno http/backend.internal@EXAMPLE.COM`. Capture the TGS-REQ with `tcpdump -i any -n udp port 88 -w kdc.pcap`. Which message contains the service ticket?
4. Use `curl --negotiate -u : -v https://backend.internal/api/v3/billing` against a server with `mod_auth_gssapi` enabled. Read the verbose log and identify the SPNEGO token, the Kerberos AP-REQ, and the TLS 1.3 `CertificateVerify` signature.
5. Inject a wrong SPI and observe ESP behavior. Then inject an expired Kerberos ticket and observe the SPNEGO failure. The two errors look nothing alike — which one is which in the system logs?
6. Use `openssl s_client -tls1_3 -ciphersuites TLS_AES_256_GCM_SHA384 -connect example.com:443`. The server selects a different cipher. Which extension in your ClientHello told the server that you would accept this?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ESP | "the IPsec protocol" | Encapsulating Security Payload (RFC 4303): encrypts and authenticates IP packets |
| SPI | "the SA identifier" | 32-bit Security Parameter Index; the lookup key in the SAD |
| SAD | "the SA table" | Security Association Database; per-gateway config of IPsec SAs |
| IKEv2 | "the key exchange" | RFC 7296; negotiates IPsec SAs and authenticates gateways |
| PSK | "the pre-shared key" | Shared secret for IKEv2 authentication when no PKI is available |
| SPNEGO | "Negotiate" | RFC 4559; wraps Kerberos AP-REQ for HTTP `Authorization: Negotiate` |
| AP-REQ | "the service ticket message" | RFC 4120 §3.3; the Kerberos message that proves a client holds a valid service ticket |
| Trust anchor | "the root cert" | A certificate the verifier has decided to trust out-of-band |
| Cross-layer failure | "where is the problem?" | Identify the layer by the error vocabulary, not the stack trace |
| Forward secrecy | "FS / PFS" | Compromising long-term key does not recover past sessions; ECDHE provides this |

## Further Reading

- RFC 4303 — IP Encapsulating Security Payload (ESP)
- RFC 4302 — IP Authentication Header (AH)
- RFC 7296 — Internet Key Exchange Protocol Version 2 (IKEv2)
- RFC 4120 — The Kerberos Network Authentication Service (V5)
- RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication
- RFC 8446 — The Transport Layer Security Protocol Version 1.3
- RFC 4556 — Public Key Cryptography for Initial Authentication in Kerberos (PKINIT)
- IETF `ipsecme` working group documents (deployment guides)
- StrongSwan documentation (the reference IKEv2 implementation)
- MIT Kerberos Consortium documentation (`web.mit.edu/kerberos`)
- Cloudflare — *A Detailed Look at RFC 8446 (a.k.a. TLS 1.3)* (best practical walkthrough)
- Tanenbaum, A. S., & Wetherall, D. J. — *Computer Networks*, 5th ed., Ch. 8.6 (IPsec, firewalls, cross-layer)
