# TLS Handshake Lab to Firewall Policy Review Lab

> The TLS 1.2 / 1.3 handshake and the firewall policy that allows or blocks it are two sides of the same coin: the firewall's job is to allow the bytes the handshake needs (ClientHello, ServerHello, certificate, Finished, NewSessionTicket) and to deny the bytes the handshake forbids (downgrade attacks, weak ciphers, expired certificates, unauthorized renegotiations). A misconfigured firewall that blocks the certificate path fails the handshake with a TLS alert 40 (handshake_failure); a misconfigured TLS server that offers only weak ciphers fails the handshake with a TLS alert 47 (illegal_parameter); a misconfigured TLS client that requires a certificate the server does not have fails with a TLS alert 116 (certificate_required). This capstone ships a stdlib-only Python lab (`code/main.py`) that walks through a complete TLS 1.2 handshake with RSA key exchange, a TLS 1.3 handshake with X25519 / ECDHE, a downgrade-detection check that compares the negotiated cipher against a policy, and a firewall policy review that walks through 12 real-world firewall rules and identifies which ones are unsafe. The deliverable is a "TLS handshake + firewall policy" runbook that pairs each handshake step with the firewall rule that allows or blocks it.

**Type:** Build
**Languages:** Python (stdlib only), openssl s_client, Wireshark, iptables / nftables
**Prerequisites:** Phase 14 (crypto foundations), Phase 15 (keys, signatures, auth), Phase 16 lessons 01-09
**Time:** ~90 minutes

## Learning Objectives

- Trace a TLS 1.2 handshake (ClientHello, ServerHello, Certificate, ServerKeyExchange, ServerHelloDone, ClientKeyExchange, ChangeCipherSpec, Finished) and identify the role of each message.
- Trace a TLS 1.3 handshake (ClientHello + key_share, ServerHello + key_share + Finished, encrypted extensions, certificate, certificate verify, NewSessionTicket) and explain the 1-RTT vs 0-RTT trade-off.
- Identify the TLS alert codes (40, 42, 43, 44, 45, 46, 47, 48, 116) and the failure mode each one signals.
- Inspect a TLS server configuration with `openssl s_client` and identify weak ciphers, expired certificates, missing intermediate certs, and protocol-version downgrades.
- Review a firewall policy for the 12 most common TLS-related rules and identify which are unsafe (e.g., "allow all outbound 443" without SNI inspection, "block all inbound 443" that breaks legitimate traffic, "allow STARTTLS" that misses command-injection attempts).
- Pair each TLS handshake step with the firewall rule that allows it, and identify the failure mode if the rule is too restrictive or too permissive.

## The Problem

You are the network engineering lead at NetCove Inc. A customer reports that their web app — served at app.netcove.com over HTTPS — fails to load in Safari but works fine in Chrome. The on-call engineer has already spent an hour: the DNS resolves, the TCP handshake completes (they can `telnet app.netcove.com 443` and get a connection), but the TLS handshake fails. The Safari console shows "TLS handshake failed: alert 40." The Chrome console shows no errors. You have 30 minutes to figure out the difference and ship a fix.

The deeper problem is that a TLS handshake failure can have a dozen root causes, and the alert code is just the symptom. Alert 40 (handshake_failure) means the server cannot negotiate an acceptable set of parameters — but "cannot negotiate" can mean: the server's certificate is expired, the server's certificate chain is missing an intermediate, the server only offers ciphers the client has disabled, the server requires a client certificate the client does not have, or the server has been configured to reject the client's TLS version. Without a structured walkthrough, the on-call engineer is left guessing.

The firewall is the other half of the picture. Even a perfect TLS configuration fails if the firewall blocks the certificate path or the OCSP stapling response. And a permissive firewall that allows all outbound 443 with no SNI inspection is a data-exfiltration path. The firewall and the TLS configuration must be reviewed together.

## The Concept

Source: `chapters/chapter-08-network-security.md` (SSL/TLS) and RFC 5246 (TLS 1.2), RFC 8446 (TLS 1.3). The companion diagram is `assets/tls-handshake-lab-to-firewall-policy-review-lab.svg`.

### The TLS 1.2 handshake (two round trips)

A TLS 1.2 handshake takes two round trips from the client's perspective:

| # | Message | Direction | Purpose |
|---|---------|-----------|---------|
| 1 | ClientHello | C → S | Client offers: protocol version, random nonce, session ID, cipher suites, compression methods, extensions (SNI, ALPN, supported_groups, signature_algorithms) |
| 2 | ServerHello | S → C | Server picks: protocol version, random nonce, session ID, cipher suite, compression method, extensions |
| 3 | Certificate | S → C | Server's certificate chain (leaf + intermediates) |
| 4 | ServerKeyExchange | S → C | (only for DHE/ECDHE) server's DH parameters and signature |
| 5 | ServerHelloDone | S → C | Server signals end of hello messages |
| 6 | ClientKeyExchange | C → S | Client's DH public value (or encrypted pre-master secret for RSA) |
| 7 | ChangeCipherSpec | C → S | Client switches to negotiated cipher |
| 8 | Finished | C → S | MAC over the entire handshake (proves both sides derived the same keys) |
| 9 | ChangeCipherSpec | S → C | Server switches |
| 10 | Finished | S → C | Server's MAC |
| 11 | Application Data | C ↔ S | Encrypted application traffic |

The two round trips are the visible performance cost of TLS 1.2: the client cannot send any application data until the second round trip completes. TLS 1.3 reduces this to one round trip (the client sends its key share in the ClientHello, the server sends its key share and Finished in the ServerHello, and the client can send application data after the second flight).

### The TLS 1.3 handshake (one round trip, with 0-RTT option)

A TLS 1.3 handshake takes one round trip from the client's perspective:

| # | Message | Direction | Purpose |
|---|---------|-----------|---------|
| 1 | ClientHello + key_share | C → S | Client offers: protocol version (TLS 1.3 only), random nonce, cipher suites, key share (X25519 / secp256r1), extensions (SNI, ALPN, supported_versions) |
| 2 | ServerHello + key_share + Finished | S → C | Server picks: cipher suite, key share, Finished (MAC over the handshake) |
| 3 | EncryptedExtensions | S → C | Encrypted extensions (SNI echo, ALPN) |
| 4 | Certificate | S → C | Server's certificate chain (encrypted) |
| 5 | CertificateVerify | S → C | Server's signature over the handshake (encrypted) |
| 6 | NewSessionTicket | S → C | (optional) ticket for resumption |
| 7 | Application Data | C → S | Client can send data after Finished |
| 8 | Application Data | S → C | Server can send data after Finished |

The client's Finished is sent with its first flight of application data (combined in the same record). 0-RTT mode skips even the client's round trip: the client sends application data in the first flight using a PSK derived from a previous session. 0-RTT is faster but vulnerable to replay attacks; the application must be idempotent or the 0-RTT data must be limited to read-only operations.

### The TLS alert codes

A TLS handshake can fail with one of several alert codes:

| Code | Name | Meaning |
|------|------|---------|
| 0 | close_notify | Graceful shutdown |
| 10 | unexpected_message | Inappropriate message received |
| 20 | bad_record_mac | MAC verification failed |
| 22 | record_overflow | Record too long |
| 40 | handshake_failure | Sender cannot negotiate acceptable parameters |
| 42 | bad_certificate | Certificate corrupted or signature invalid |
| 43 | unsupported_certificate | Certificate type not supported |
| 44 | certificate_revoked | Certificate has been revoked |
| 45 | certificate_expired | Certificate has expired |
| 46 | certificate_unknown | Certificate issue not specified (e.g., untrusted issuer) |
| 47 | illegal_parameter | Field out of range or inconsistent with other fields |
| 48 | unknown_ca | CA chain not trusted |
| 49 | access_denied | Sender refused the negotiation |
| 50 | decode_error | Message could not be decoded |
| 51 | decrypt_error | Handshake crypto operation failed |
| 116 | certificate_required | Server requires a client certificate |

In the Safari-vs-Chrome scenario, the Safari console showed alert 40 (handshake_failure). The most common cause is that the server offers only ciphers that Safari has disabled (e.g., RC4, 3DES, or any cipher using SHA-1 in the PRF). The fix is to update the server's cipher list to include AES-GCM and ChaCha20-Poly1305 with modern groups.

### The openssl s_client diagnostic

`openssl s_client -connect host:443 -servername host` is the first-line diagnostic. The output shows:

- The negotiated protocol version (`Protocol : TLSv1.3`)
- The negotiated cipher (`Cipher : TLS_AES_256_GCM_SHA384`)
- The server's certificate chain
- The session ticket (if any)
- The OCSP stapling response (if any)
- The server's random nonce
- The extensions (SNI, ALPN, etc.)

`openssl s_client` with `-tls1_2` or `-tls1_3` forces a specific version; with `-cipher` you can test a specific cipher. The combination of these flags lets the engineer reproduce the Safari failure in a CLI and see exactly which parameter the server is rejecting.

### The 12 firewall rules for TLS traffic

A firewall policy for TLS traffic typically has 12 rules, of which several are commonly misconfigured:

| # | Rule | Purpose | Common failure |
|---|------|---------|----------------|
| 1 | Allow inbound TCP 443 from any | Web traffic to the company's HTTPS servers | If too permissive, allows attackers to scan for open web servers |
| 2 | Allow outbound TCP 443 from any | Browsers, API clients, CDNs | If missing SNI inspection, allows data exfiltration via TLS |
| 3 | Allow inbound TCP 80 from any | HTTP redirect to HTTPS | If missing redirect, allows unencrypted traffic |
| 4 | Allow outbound TCP 80 from any | Legacy clients, cert transparency logs | Often unnecessary in 2026 |
| 5 | Allow inbound UDP 443 from any | HTTP/3 (QUIC) | If blocked, HTTP/3 falls back to TCP, performance regression |
| 6 | Allow outbound UDP 443 from any | HTTP/3 clients | If blocked, browsers fall back to HTTP/2 over TCP |
| 7 | Allow outbound TCP 25 from mail servers | SMTP (sometimes STARTTLS) | If STARTTLS is allowed without inspection, command injection is possible |
| 8 | Allow inbound TCP 993 from any | IMAPS (mail) | Often forgotten, mail clients cannot connect |
| 9 | Allow inbound TCP 995 from any | POP3S (mail) | Legacy, often unnecessary |
| 10 | Allow outbound TCP 587 from any | SMTP submission (mail clients) | If missing, mail clients cannot send |
| 11 | Allow outbound TCP 853 from any | DNS over TLS (DoT) | If blocked, the resolver cannot use DoT |
| 12 | Allow outbound TCP 443 to specific domains only | Egress filtering | If the allowlist is too narrow, browsers cannot load arbitrary sites |

The lab's `code/main.py` walks through each of these 12 rules and identifies whether the rule is too restrictive, too permissive, or correctly configured.

## Build It

1. Read `code/main.py` and understand the data model: `TLSHandshake12` and `TLSHandshake13` (the two handshake simulators), `TLSAlert` (the alert codes and their meanings), `FirewallPolicy` (the 12 rules and their review).
2. Run `python3 main.py` and walk through the demo: a TLS 1.2 handshake, a TLS 1.3 handshake, an alert-code lookup, a `openssl s_client` command, and a 12-rule firewall review.
3. Use `openssl s_client -connect app.netcove.com:443 -servername app.netcove.com` against a real server and compare the output to the simulator's expectations.
4. Modify the `TLSHandshake12` to use ECDHE instead of RSA key exchange. Confirm the message list shrinks by one (no ServerKeyExchange is needed in TLS 1.2 ECDHE_RSA — it is folded into the ServerKeyExchange).
5. Add a downgrade-detection check: if a TLS 1.3-capable server negotiates TLS 1.2, the lab should warn. Implement the check using the `supported_versions` extension.
6. Add a 13th firewall rule for HTTP/3 (QUIC) and update the review to flag the common failure mode (UDP 443 blocked by accident).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Diagnose a TLS handshake failure | `openssl s_client` output + alert code | Alert code maps to a known cause (e.g., 40 = weak cipher) |
| Identify weak ciphers | `openssl ciphers -v 'DEFAULT:!AES'` | List of ciphers excluding AES; all should be disabled in 2026 |
| Verify the certificate chain | `openssl s_client -showcerts` | Full chain: leaf + intermediates + root |
| Check OCSP stapling | `openssl s_client -status` | "OCSP Response Status: successful" |
| Review the firewall policy | The 12-rule review table | Each rule marked safe / too permissive / too restrictive |
| Test the egress allowlist | `curl https://blocked.example.com` from a workstation | Returns 403 or connection refused; allows the legitimate sites |

## Ship It

Produce one artifact under `outputs/`:

- A "TLS Handshake + Firewall Policy" runbook suitable for the on-call binder, with: the two handshake diagrams, the alert-code table, the `openssl s_client` reference card, the 12-rule firewall review, and a worked example of the Safari-vs-Chrome failure.
- A 1-page "TLS Quick Reference" card for the team room wall, with: the 13 alert codes (40, 42, 43, 44, 45, 46, 47, 48, 116), the openssl s_client flags, and the safe cipher list.

Start from [`outputs/prompt-tls-handshake-lab-to-firewall-policy-review-lab.md`](../outputs/prompt-tls-handshake-lab-to-firewall-policy-review-lab.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Capture a real TLS handshake with Wireshark (`tcp.port == 443 && tls.handshake`) and walk through the messages. Compare to the simulator's output.
2. Use `openssl s_client -cipher 'DEFAULT:!AES'` to verify that a real server rejects all non-AES ciphers. If it accepts RC4 or 3DES, the server is misconfigured.
3. Implement a "TLS 1.3 downgrade detector" that warns when a server that advertises TLS 1.3 in ClientHello receives a ServerHello at TLS 1.2. (This is the same detection that browsers do to enforce the "version fallback" signal.)
4. Add a "client certificate" check: `openssl s_client -cert client.pem -key client.key`. The server should request a client certificate (via CertificateRequest) and the client should present it.
5. Walk through a real firewall policy file (iptables-save or nftables list) and identify the 12 rules from this lesson. Note any rules that are missing or over-broad.
6. Build a CI gate that refuses to deploy a config change if the resulting TLS configuration includes any cipher from a deny-list (RC4, 3DES, MD5, SHA-1 PRF, EXPORT, NULL).

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| TLS 1.2 | "the 2-RTT handshake" | TLS protocol version with a 2-round-trip handshake; defined in RFC 5246; now deprecated by IETF (use 1.3) |
| TLS 1.3 | "the 1-RTT handshake" | TLS protocol version with a 1-round-trip handshake; defined in RFC 8446; encrypts the certificate |
| 0-RTT | "zero round-trip resumption" | TLS 1.3 mode that sends application data in the first flight using a PSK; vulnerable to replay |
| Alert 40 | "handshake_failure" | TLS alert code 40: sender cannot negotiate acceptable parameters |
| Alert 47 | "illegal_parameter" | TLS alert code 47: a field was out of range or inconsistent |
| Alert 116 | "certificate_required" | TLS alert code 116: server requires a client certificate (mTLS) |
| Cipher suite | "the algorithm list" | The negotiated combination of key exchange (ECDHE), authentication (RSA/ECDSA), cipher (AES-GCM), and MAC (SHA-384) |
| SNI | "Server Name Indication" | TLS extension that allows multiple HTTPS sites on one IP; the client sends the hostname in ClientHello |
| ALPN | "Application-Layer Protocol Negotiation" | TLS extension that negotiates the application protocol (h2, http/1.1) during the handshake |
| OCSP stapling | "the certificate status" | TLS extension where the server includes the certificate's revocation status in the handshake |
| Forward secrecy | "PFS" | Property of a cipher suite where compromise of the long-term key does not compromise past sessions (requires ECDHE) |
| mTLS | "mutual TLS" | TLS mode where the client also presents a certificate; the server validates it via CertificateRequest / CertificateVerify |

## Further Reading

- Rescorla, E. (2018). *TLS 1.3 — One Round Trip, Many New Features*, IETF TLS WG — the TLS 1.3 design rationale.
- RFC 5246 — *The Transport Layer Security (TLS) Protocol Version 1.2* — the canonical TLS 1.2 reference.
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3* — the canonical TLS 1.3 reference.
- RFC 6066 — *TLS Extensions* — SNI, OCSP stapling, max_fragment_length, and others.
- RFC 7301 — *ALPN* — application-layer protocol negotiation during the TLS handshake.
- OpenSSL Cookbook, Chapter 3 — `s_client` and `s_server` for TLS testing and debugging.
- Wireshark User's Guide, Chapter 7 — TLS decryption and the (pre)-master-secret log file.
- Mozilla SSL Configuration Generator — the modern reference for safe cipher lists and protocol versions.
- Qualys SSL Labs SSL Test — the public scanner that grades a server's TLS configuration; useful as a CI check.
