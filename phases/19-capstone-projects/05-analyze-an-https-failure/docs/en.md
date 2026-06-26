# Analyze an HTTPS Failure

> Given five broken HTTPS scenarios and their traces, identify the failure mode at the TLS layer for each, map the alert code to its root cause, and produce a diagnostic runbook you can reuse in production.

**Type:** Capstone
**Languages:** Python, openssl, curl, Wireshark
**Prerequisites:** Phase 14–15 cryptography and TLS lessons, Phase 16 web security
**Time:** ~180 minutes

---

## Learning Objectives

1. Trace each stage of the TLS 1.3 handshake and identify where a given failure interrupts it.
2. Validate a certificate chain from leaf to intermediate to root using `openssl verify` and `openssl s_client`.
3. Explain how SNI and ALPN extensions affect handshake routing and protocol selection, and diagnose failures caused by their absence or mismatch.
4. Read TLS alert codes from packet captures and map each numeric value to the underlying error condition.
5. Diagnose OCSP stapling failures and distinguish them from certificate revocation proper.
6. Recognize mutual TLS (mTLS) failures and identify which side of the handshake is rejecting the connection.

---

## The Problem

The following five scenarios were reported in the same week by users hitting different services. Each produces a different user-visible error. Your job is to work through them in order, collect evidence from packet captures and command-line tools, and identify the exact TLS failure mode in each case.

**Scenario 1 — Browser shows `NET::ERR_CERT_AUTHORITY_INVALID`**
A developer has deployed an internal API behind nginx. External browsers accept the site, but a staging machine inside the corporate network receives `NET::ERR_CERT_AUTHORITY_INVALID` on every request. The certificate was issued by an internal CA. No changes were made to the server.

**Scenario 2 — curl returns `SSL connect error: certificate has expired`**
An automated pipeline that calls a payment provider starts failing overnight. The error appears immediately on the TLS handshake, before any HTTP data is exchanged. The server certificate was valid the previous day. The pipeline machine and the payment server are in different timezones.

**Scenario 3 — Connection resets after ClientHello**
A load balancer receives a TLS connection and sends a TCP RST after the client finishes its ClientHello. No TLS alert is sent — the connection simply dies. The service has been running for months. The only recent change was a firewall rule update.

**Scenario 4 — 400 Bad Request: No required SSL certificate was sent**
A microservice calls an internal API endpoint and receives an HTTP 400 response with the body `No required SSL certificate was sent`. The service uses HTTPS but does not send a client certificate. The endpoint was working without client certificates last sprint.

**Scenario 5 — Slow HTTPS with occasional handshake timeouts**
A high-traffic service begins showing p99 HTTPS connection latency of 8–12 seconds, with ~3% of connections timing out during the handshake. The server certificate was recently renewed and includes a full OCSP staple URL. Client machines are behind a strict egress firewall.

---

## The Concept

### TLS 1.3 Handshake

TLS 1.3 (RFC 8446) collapses the two-round-trip handshake of TLS 1.2 into a single round trip under normal conditions, and adds 0-RTT resumption for repeat connections. The core exchange looks like this:

```
Client                                          Server
  |                                               |
  |------- ClientHello (supported ciphers,  ----->|
  |         key_share, SNI, ALPN)                 |
  |                                               |
  |<------ ServerHello (chosen cipher,     -------|
  |         key_share, session_id)                |
  |<------ {EncryptedExtensions}           -------|
  |<------ {Certificate}                   -------|
  |<------ {CertificateVerify}             -------|
  |<------ {Finished}                      -------|
  |                                               |
  |------- {Finished}                      ------>|
  |                                               |
  |===== Application Data (encrypted) ===========|
```

After the server sends its `Finished`, the connection is established. The client may optionally send a client certificate before its own `Finished` in mTLS scenarios. Items in `{}` are encrypted with the handshake traffic keys derived from the key exchange.

### Certificate Chain Validation

When a client receives the server's `Certificate` message, it must build and validate a chain from the leaf certificate up to a trusted root. The typical chain is:

```
Leaf cert (server's cert)
    |  signed by
    v
Intermediate CA cert
    |  signed by
    v
Root CA cert  <-- must be in the client's trust store
```

Validation fails if any link in the chain is broken: the leaf's signature cannot be verified against the intermediate, the intermediate is not trusted, the root is not in the trust store, or any certificate in the chain has expired or been revoked.

### SNI and ALPN

**Server Name Indication (SNI)** is a TLS extension (RFC 6066) that carries the hostname the client intends to reach. It is sent in plaintext in the ClientHello before any encryption is negotiated. Virtual hosting — one IP serving multiple TLS certificates — depends entirely on SNI. If a client does not send SNI, or sends the wrong hostname, the server may serve the wrong certificate or refuse the connection outright.

**Application-Layer Protocol Negotiation (ALPN)** is a TLS extension (RFC 7301) that lets the client advertise which application protocols it supports (e.g., `h2` for HTTP/2, `http/1.1`). The server selects one and includes it in the `EncryptedExtensions` message. If the server requires a specific protocol and the client does not offer it, the server sends a `no_application_protocol` alert (120).

### TLS Alert Codes

TLS alerts are two-byte records: a level (warning=1 or fatal=2) and a description. Fatal alerts close the connection immediately. Key codes:

| Code | Name | Meaning |
|------|------|---------|
| 20 | bad_record_mac | Decryption failed, MAC mismatch |
| 42 | bad_certificate | Certificate is malformed or untrusted |
| 44 | certificate_revoked | Certificate has been revoked |
| 45 | certificate_expired | Certificate validity period has passed |
| 46 | certificate_unknown | Unspecified certificate problem |
| 48 | unknown_ca | CA is not recognized or trusted |
| 70 | protocol_version | Client offered only old protocol versions |
| 71 | insufficient_security | No acceptable cipher suite |
| 80 | internal_error | Server-side error unrelated to the certificate |
| 112 | unrecognized_name | SNI hostname not recognized |
| 116 | certificate_required | mTLS: client certificate required but not sent |
| 120 | no_application_protocol | No shared ALPN protocol |

### OCSP Stapling

Online Certificate Status Protocol (OCSP, RFC 6960) lets clients check whether a certificate has been revoked. In the naive model, the client contacts the OCSP responder directly during every handshake — this adds latency and leaks browsing behavior to the CA. OCSP stapling (RFC 6961) solves both problems: the server periodically fetches a signed OCSP response from the CA and "staples" it to the `Certificate` message. The client verifies the stapled response without making an outbound network call.

If the server cannot reach the OCSP responder to refresh the staple (e.g., blocked by an egress firewall), the staple expires, and some clients configured with `must-staple` will refuse the connection.

### Mutual TLS

In standard TLS, only the server presents a certificate. In mutual TLS (mTLS), the server sends a `CertificateRequest` message after its own `Certificate`, and the client must respond with its own certificate chain. The server validates the client certificate against its trusted client CA list. Failure produces a `certificate_required` alert (116) or, after a bad client cert, a `bad_certificate` alert (42).

---

## Build It

Work through each step with the corresponding scenario. You will need `openssl`, `curl`, `tcpdump` or Wireshark, and a terminal.

**Step 1 — Capture the baseline handshake**

For each scenario, start a packet capture before making the failing request:

```bash
sudo tcpdump -i any -w /tmp/tls_scenario_N.pcap 'tcp port 443'
```

In Wireshark, use the display filter `tls` to isolate handshake records, and `tls.alert_message` to jump straight to any alert frames.

**Step 2 — Scenario 1: Missing root CA in trust store**

Reproduce the error and capture it. Then inspect the certificate chain the server presents:

```bash
openssl s_client -connect internal-api.corp:443 -showcerts 2>/dev/null | \
  openssl x509 -noout -text | grep -A2 "Issuer\|Subject\|Not After"
```

The `-showcerts` flag dumps every certificate in the chain. Save the intermediate and root PEM blocks, then test validation explicitly:

```bash
# Test with only the system trust store (will fail)
openssl verify -CAfile /etc/ssl/certs/ca-certificates.crt leaf.pem

# Test with the internal CA bundle (should succeed)
openssl verify -CAfile /path/to/internal-ca.pem -untrusted intermediate.pem leaf.pem
```

The fix is distributing `internal-ca.pem` to the staging machine's trust store (`/etc/ssl/certs/` on Linux, System Keychain on macOS) or passing `-CAfile` to curl: `curl --cacert internal-ca.pem https://internal-api.corp/`.

**Step 3 — Scenario 2: Clock skew causing certificate_expired**

Check the certificate's `Not Before` / `Not After` window:

```bash
openssl s_client -connect payment.example.com:443 </dev/null 2>/dev/null | \
  openssl x509 -noout -dates
```

Then check the pipeline machine's clock:

```bash
date -u
timedatectl status   # Linux systemd
```

If the machine's UTC clock is ahead of the certificate's `Not After` timestamp, the handshake will produce TLS alert 45 (`certificate_expired`). In Wireshark, filter `tls.handshake.certificate` and look for the Certificate message followed immediately by an alert record with description `2d` (hex for 45). Fix by syncing the system clock: `sudo systemctl restart systemd-timesyncd` or `sudo ntpdate pool.ntp.org`.

**Step 4 — Scenario 3: Connection reset after ClientHello — firewall blocking**

A RST without a TLS alert means the TCP connection was forcibly closed before TLS negotiation completed. This is almost always a network-layer block, not a TLS failure.

In Wireshark, filter `tcp.flags.reset == 1` and examine the frame immediately after the ClientHello. The RST originates from an intermediate device, not the server.

Confirm with `openssl s_client` from multiple vantage points:

```bash
# From affected network
openssl s_client -connect target.example.com:443 -debug 2>&1 | head -40

# Check if a specific cipher list triggers the block (some DPI devices block
# connections that advertise post-quantum key exchange groups)
openssl s_client -connect target.example.com:443 \
  -cipher 'ECDHE-RSA-AES256-GCM-SHA384' \
  -no_tls1_3
```

If the connection succeeds from outside the firewall but not from inside, the firewall rule is blocking based on packet content (e.g., blocking certain TLS extensions or key exchange groups).

**Step 5 — Scenario 4: mTLS — missing client certificate**

The server sent a `CertificateRequest` during the handshake. The client ignored it and sent an empty `Certificate` message, or no certificate at all. The server then sent alert 116 (`certificate_required`) and closed the connection — but because the server is an HTTP layer above TLS here, it gracefully returned a 400 instead.

Confirm with `openssl s_client`:

```bash
# Without client cert — will trigger the 400
openssl s_client -connect internal-api.corp:8443 -servername internal-api.corp

# With client cert
openssl s_client -connect internal-api.corp:8443 \
  -cert client.pem \
  -key client-key.pem \
  -CAfile server-ca.pem \
  -servername internal-api.corp
```

In curl:

```bash
curl -v --cert client.pem --key client-key.pem \
  --cacert server-ca.pem \
  https://internal-api.corp:8443/endpoint
```

In Wireshark, filter `tls.handshake.type == 13` to find `CertificateRequest` frames and confirm the server is issuing the request.

**Step 6 — Scenario 5: OCSP staple expiry causing handshake timeouts**

Check whether the server is presenting a valid staple:

```bash
openssl s_client -connect slow-service.example.com:443 \
  -status \
  -servername slow-service.example.com \
  </dev/null 2>&1 | grep -A 10 "OCSP response"
```

If the output shows `OCSP Response Status: unauthorized` or `no response sent`, the server's staple is stale or absent. Clients configured with OCSP `must-staple` (X.509 extension OID 1.3.6.1.5.5.7.1.24) will refuse to complete the handshake and sit waiting until a timeout.

Check whether the server can reach its OCSP responder:

```bash
# Extract the OCSP URL from the certificate
openssl x509 -in server.pem -noout -ocsp_uri

# Test connectivity to the OCSP responder
curl -v http://ocsp.example-ca.com
```

If the OCSP responder URL is unreachable from the server (blocked egress firewall), the fix is either opening the firewall rule for the OCSP URL or disabling `must-staple` in the certificate request for this environment.

**Step 7 — Read alert codes in Wireshark**

For any scenario that produces a TLS alert (not a raw RST), use the Wireshark filter:

```
tls.alert_message.desc
```

The description field maps directly to the alert code table above. Right-click a TLS record and choose "Follow > TLS Stream" to see the full handshake context around the alert.

**Step 8 — Verify repairs**

After applying each fix, rerun the original `openssl s_client` command and confirm the handshake completes:

```bash
openssl s_client -connect target.example.com:443 \
  -CAfile fixed-ca.pem \
  -servername target.example.com \
  </dev/null 2>&1 | grep -E "Verify return code|Protocol|Cipher"
```

A successful handshake shows `Verify return code: 0 (ok)`.

---

## Use It

| Failure | TLS Alert / Error | Diagnostic Command | Root Cause |
|---------|------------------|--------------------|------------|
| `NET::ERR_CERT_AUTHORITY_INVALID` | Alert 48 `unknown_ca` | `openssl verify -CAfile ca.pem leaf.pem` | Internal CA root not in client trust store |
| `certificate has expired` | Alert 45 `certificate_expired` | `openssl x509 -noout -dates` + `date -u` | Clock skew on client or genuine cert expiry |
| Connection reset after ClientHello | No TLS alert — TCP RST | Wireshark `tcp.flags.reset==1` after ClientHello | Firewall DPI blocking TLS extension or key group |
| `400 No required SSL certificate` | Alert 116 `certificate_required` | `openssl s_client -cert c.pem -key k.pem` | mTLS endpoint; client did not send certificate |
| Handshake timeout / p99 spike | No alert — timeout | `openssl s_client -status` + egress ping to OCSP URL | OCSP staple expired; must-staple clients block |

---

## Ship It

Produce a TLS diagnostic runbook at `outputs/tls-runbook.md`. The runbook must cover all five failure classes and include an openssl command reference. Structure it as follows:

**Section 1 — Quick triage tree**
A decision tree: does the connection reach the server at all (TCP SYN-ACK)? If no, the problem is network-layer. If yes, does a TLS alert appear? If yes, map alert code to failure class. If no alert but connection drops, suspect firewall DPI.

**Section 2 — Per-failure procedure**

For each of the five failure classes, document:
- User-visible symptom
- Wireshark filter to locate evidence
- `openssl s_client` command to reproduce in isolation
- Fix and verification command

**Section 3 — openssl s_client reference**

```bash
# Full chain inspection
openssl s_client -connect HOST:443 -showcerts -CAfile ca.pem -servername HOST

# OCSP staple check
openssl s_client -connect HOST:443 -status -servername HOST

# mTLS client certificate
openssl s_client -connect HOST:443 -cert client.pem -key client-key.pem -CAfile server-ca.pem

# Force TLS 1.2 (test older clients)
openssl s_client -connect HOST:443 -tls1_2

# Show cipher negotiated
openssl s_client -connect HOST:443 </dev/null 2>/dev/null | grep "Cipher is"

# Verify certificate chain offline
openssl verify -CAfile root.pem -untrusted intermediate.pem leaf.pem
```

**Section 4 — Wireshark filter reference**

```
tls                            # All TLS records
tls.handshake                  # Handshake messages only
tls.handshake.type == 1        # ClientHello
tls.handshake.type == 2        # ServerHello
tls.handshake.type == 11       # Certificate
tls.handshake.type == 13       # CertificateRequest (mTLS)
tls.alert_message              # All TLS alerts
tls.alert_message.desc == 45   # certificate_expired
tls.alert_message.desc == 48   # unknown_ca
tls.alert_message.desc == 116  # certificate_required
tcp.flags.reset == 1           # TCP RST (firewall drops)
```

---

## Exercises

1. **Certificate pinning**: Modify a Python `requests` call to pin the server's leaf certificate SHA-256 fingerprint using `ssl.SSLContext`. Observe what happens when the pinned certificate is rotated. Write the fingerprint-rotation procedure that avoids downtime.

2. **HSTS preloading**: Set up a local nginx with `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`. Use `curl -v` to capture the header, then delete the header and observe that Chrome still refuses the HTTP connection for the preload period. Explain why the removal has no immediate effect.

3. **OCSP must-staple**: Use `openssl req` and a local CA (via `step-ca` or a self-signed chain) to issue a certificate with the `must-staple` extension (`tlsfeature = status_request`). Configure nginx to serve it. Then stop the OCSP responder and observe client behavior with both a must-staple-aware client and a non-aware client.

4. **Certificate Transparency logs**: Fetch the SCT (Signed Certificate Timestamp) from a live certificate using `openssl s_client -ct`. Decode the SCT manually to identify the log ID, timestamp, and signature. Cross-reference the log ID against the list at `https://www.certificate-transparency.org/known-logs`.

5. **mTLS client certificate validation**: Build a minimal Python server with `ssl.SSLContext` that requires a client certificate (`CERT_REQUIRED`). Issue two client certificates: one signed by your local CA (should succeed) and one self-signed (should fail with alert 42). Capture both handshakes and annotate the difference.

6. **Cipher suite downgrade**: Use `openssl s_client -cipher 'AES128-SHA'` against a server configured to require TLS 1.3 only. Observe and record the specific TLS alert code returned. Explain why some servers prefer to send alert 70 (`protocol_version`) and others send alert 71 (`insufficient_security`) in this scenario.

---

## Key Terms

| Term | Definition | Where it appears |
|------|-----------|-----------------|
| ClientHello | First TLS handshake message; contains protocol versions, cipher suites, key shares, SNI, and ALPN | Wireshark `tls.handshake.type == 1` |
| SNI | Server Name Indication; plaintext hostname extension in ClientHello enabling virtual hosting | RFC 6066; Wireshark `tls.handshake.extensions_server_name` |
| ALPN | Application-Layer Protocol Negotiation; advertises supported app protocols (h2, http/1.1) in ClientHello | RFC 7301; alert 120 on mismatch |
| Certificate chain | Ordered sequence: leaf → intermediate → root; client validates from root down | `openssl verify`, `openssl s_client -showcerts` |
| TLS alert | Two-byte record (level + description) signaling a fatal or warning condition | RFC 8446 §6; Wireshark `tls.alert_message` |
| OCSP | Online Certificate Status Protocol; revocation checking mechanism | RFC 6960; `openssl s_client -status` |
| OCSP stapling | Server fetches and caches signed OCSP response, includes it in TLS handshake | RFC 6961; reduces client latency and privacy leakage |
| must-staple | X.509 extension requiring the server to always provide an OCSP staple | OID 1.3.6.1.5.5.7.1.24; causes timeout if staple absent |
| mTLS | Mutual TLS; both client and server present certificates; server sends CertificateRequest | Alert 116 on missing client cert |
| certificate_expired (45) | TLS alert: certificate NotAfter in the past relative to the verifying clock | Alert code 45; common with clock skew |
| unknown_ca (48) | TLS alert: issuing CA not in trust store | Alert code 48; common with internal CAs |
| DPI | Deep Packet Inspection; firewall technique that inspects TLS extensions and may drop connections | Manifests as TCP RST without TLS alert |

---

## Further Reading

- **RFC 8446** — The Transport Layer Security (TLS) Protocol Version 1.3. The authoritative specification for TLS 1.3 handshake state machine, alert codes, and extension definitions. https://www.rfc-editor.org/rfc/rfc8446

- **RFC 6960** — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol — OCSP. Defines OCSP request/response format and stapling semantics. https://www.rfc-editor.org/rfc/rfc6960

- **RFC 6066** — Transport Layer Security (TLS) Extensions: Extension Definitions. Covers SNI (section 3) and other ClientHello extensions. https://www.rfc-editor.org/rfc/rfc6066

- **Let's Encrypt Documentation — Chain of Trust**. Practical explanation of intermediate CA certificates, cross-signatures, and what happens when an intermediate expires. https://letsencrypt.org/certificates/

- **Wireshark TLS Wiki** — Decrypting TLS traffic with pre-master secret log files, TLS display filters, and handshake dissection guide. https://wiki.wireshark.org/TLS
