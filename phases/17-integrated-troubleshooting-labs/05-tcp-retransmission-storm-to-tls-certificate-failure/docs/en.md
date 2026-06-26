# TCP Retransmission Storm to TLS Certificate Failure

> A user reports that HTTPS connections to a partner company's web service are failing — but inconsistently. Most connections succeed in under a second, but one in five hangs for 15 seconds before failing with a TLS alert. The application team swears the service is healthy (their monitoring shows 99.95% success on the server side). The network team sees no errors on the edge firewall. The security team has just renewed a certificate, and that is the obvious scapegoat — but renewing a cert should not produce 15-second delays. This lesson walks the diagnostic chain from "TCP retransmission storm" (Layer 4) up to "TLS certificate failure" (Layer 6) and explains why the two phenomena can both be present in the same capture and how to disambiguate them. The synthetic trace generator in `code/main.py` models a network with periodic micro-bursts of loss and a server that has just been reconfigured with a new intermediate CA that the client does not yet trust.

**Type:** Lab
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 08 TCP retransmission, Phase 12 TLS handshake, Phase 13 cryptography basics, Lesson 02 of this phase
**Time:** ~120 minutes

## Learning Objectives

- Distinguish a TCP retransmission storm (Layer 4: packets are dropped and retransmitted with exponential backoff) from a TLS handshake failure (Layer 6: the cryptographic handshake fails after TCP completes), and identify the evidence signature of each in `tcpdump`.
- Read a `tcpdump` capture and identify the exact packet at which the failure occurs: at the TCP SYN, at the TCP SYN-ACK, at the TCP ACK of the SYN-ACK, in the middle of the TLS handshake, or in the middle of encrypted application data.
- Apply a four-step diagnostic chain (`ss -ti` for retrans/RTO, `tcpdump -tttt` for timing, `openssl s_client` for TLS handshake, `curl -v --tls-max 1.2` for application behavior) to a "TLS connection fails" report.
- Explain why a server that returns "valid" to `openssl s_client` from a workstation can still fail in a browser, by walking through the certificate chain validation logic and the role of the trust store.
- Identify the specific TLS alerts (`bad_certificate`, `certificate_unknown`, `handshake_failure`, `certificate_expired`, `unsupported_certificate`) and what each implies about the failure cause.
- Construct a synthetic retransmission-and-TLS-handshake trace generator (no live capture) that models a network with periodic micro-bursts of loss and a server that has been reconfigured with a new intermediate CA.

## The Problem

A regional bank has a B2B API used by partner companies to fetch account balances. The bank's operations team has just rotated the TLS certificate (a routine annual task) and updated the intermediate CA bundle on the server. Within an hour, the partner integration team reports: "API calls are timing out intermittently — about 1 in 5 fails with a TLS error after 15 seconds." The bank's application monitoring shows 99.95% success. The network team sees no alerts. The security team insists the certificate is valid (and a quick `openssl s_client` from a workstation confirms this).

What is actually happening is two unrelated problems that happen to coexist:

1. **TCP retransmission storm from micro-bursts**: A misconfigured QoS policy on the bank's edge router is causing periodic micro-bursts of packet loss (5–10 packets dropped per second for 100–500 ms at a time, in cycles of 30–60 seconds). The TCP connections that happen to be in their handshake during a micro-burst see the SYN-ACK dropped, retransmit the SYN, and either succeed on the second attempt (fast) or fail after 15 seconds (when the third SYN retransmission and the application timeout align).
2. **TLS handshake failure on the new intermediate CA**: A subset of the bank's clients (those with older trust stores, or those that do TLS validation strictly) do not yet have the bank's new intermediate CA in their trust store. The TLS ServerHello completes, the server sends its certificate chain including the new intermediate, the client tries to verify the chain, fails, sends a `certificate_unknown` alert, and closes the connection.

The bank's `openssl s_client` test from a workstation does not reproduce the TLS issue because the workstation's trust store is up to date. The bank's application monitoring does not see the TLS issue because the bank's clients all have the new intermediate (the bank pushed it to them in the certificate rotation announcement, and they updated).

The partner company's clients, however, do not have the new intermediate. The bank's network's micro-bursts happen to be timed such that the partner's clients are more likely to hit a burst during the TLS handshake (because the partner is geographically far from the bank and has longer RTT, which makes the handshake take longer and overlap more with the burst cycles).

The first responder's job is to walk the diagnostic chain, identify both root causes, and report them as two separate findings rather than one confused "TLS is broken" or "network is bad" diagnosis.

## The Concept

### The TCP Retransmission Storm: Mechanism

A TCP retransmission storm is a self-reinforcing cycle of packet loss and retransmission that can degrade network throughput by orders of magnitude. The mechanism:

1. A micro-burst of loss occurs on a router (e.g., a QoS policer drops a queue's tail, a link briefly flaps, an interface momentarily overruns its buffer)
2. The TCP connections that were in flight see packet loss, retransmit the lost segments
3. The retransmissions arrive in a burst at the next bottleneck, where the bottleneck is still recovering from the original micro-burst
4. The bottleneck drops the retransmissions (tail-drop or AQM drop), triggering more retransmissions
5. The cycle continues, often for tens of seconds, before the bottleneck recovers and the connections can drain their retransmission queues

The signature in `ss -ti` is unmistakable: `retrans:N/N` with `N` growing rapidly, `cwnd` low (often stuck at 1–2 segments during slow-start recovery), `timer:(on,...)` armed with a value that doubles each retransmission.

In a `tcpdump` capture, the signature is multiple identical TCP segments (same SEQ number, same IPID for IPv4, same TCP timestamp option) sent at intervals of 1 s, 2 s, 4 s, 8 s, ... per RFC 6298's exponential backoff.

### The TLS Handshake: Anatomy

A modern TLS 1.2 handshake takes 2 RTTs to complete (TLS 1.3 reduces this to 1 RTT for new connections). For a typical client-server pair with 50 ms RTT:

```
T=0       Client → Server:  ClientHello
T=50ms    Server → Client:  ServerHello, Certificate, ServerHelloDone
T=100ms   Client → Server:  ClientKeyExchange, ChangeCipherSpec, Finished
T=150ms   Server → Client:  ChangeCipherSpec, Finished
T=200ms   Application data can now flow
```

The `Certificate` message at T=50ms contains the server's leaf certificate and the chain of intermediate CAs needed to validate it (typically 2–3 certificates). The client uses its trust store to verify the chain: it must be able to construct a path from the leaf to a trusted root CA, with every certificate in the path being currently valid (not before the `notBefore` date, not after the `notAfter` date), properly signed by the next certificate in the chain, and having the correct key usages and extended key usages.

If the chain is broken (the client does not have the intermediate CA), the handshake fails at T=100ms or T=150ms with a TLS alert:

```
TLS Alert: certificate_unknown (alert level: fatal)
```

If the leaf certificate is expired, the alert is `certificate_expired`. If the certificate is for the wrong hostname, the alert is `unrecognized_name` (in TLS 1.3) or the client reports `hostname mismatch` after the handshake.

### Why `openssl s_client` and the Browser Disagree

The most confusing aspect of TLS troubleshooting is that `openssl s_client` from a workstation often succeeds even when browsers fail. Three reasons:

1. **Different trust stores**: `openssl s_client` uses the system trust store (on Linux: `/etc/ssl/certs/ca-certificates.crt`; on macOS: the system keychain). Browsers (especially Chrome and Firefox) maintain their own trust stores that may differ from the system. A new intermediate CA that the system has but the browser does not will fail in the browser but succeed in `openssl`.
2. **Different validation strictness**: Browsers enforce additional checks that `openssl s_client` does not: SCT (Certificate Transparency) validation, OCSP stapling, CRLSets, and hostname matching against SAN (Subject Alternative Name) entries. A certificate that passes `openssl s_client` can fail a browser because it lacks an SCT.
3. **Different protocol support**: Browsers may have disabled older TLS versions or ciphers that `openssl s_client` still supports. A handshake that succeeds with TLS 1.0 in `openssl` may fail in a browser that requires TLS 1.2+.

The right test is the same tool the user is using: if the user is on Chrome, use Chrome's certificate viewer (click the padlock → "Connection is secure" → "Certificate is valid"). If the user is on Firefox, use Firefox's certificate viewer (click the padlock → "Connection secure" → "More information" → "View Certificate").

### The TLS Alert Catalog

TLS alerts are 2-byte messages: 1 byte for the alert level (`warning` or `fatal`) and 1 byte for the alert description. The most common in troubleshooting:

| Alert | Meaning | Layer implication |
|-------|---------|-------------------|
| `bad_certificate` | Certificate is corrupted or unsupported format | Server or proxy sent garbage |
| `unsupported_certificate` | Certificate type is not supported (e.g., a server sent a PGP cert) | Server misconfiguration |
| `certificate_expired` | `notAfter` date has passed | Cert rotation missed |
| `certificate_unknown` | Trust store lacks the chain | New intermediate CA not deployed |
| `handshake_failure` | Generic failure; no specific cause | Often cipher mismatch or extension rejection |
| `unrecognized_name` | Server cannot find a cert for the SNI | Wrong SNI or no SNI on multi-tenant server |
| `protocol_version` | Client/server cannot agree on TLS version | One side has disabled the version the other requires |
| `insufficient_security` | Server requires ciphers the client does not support | Cipher suite mismatch |

`certificate_unknown` is by far the most common alert in production. It almost always means a missing intermediate CA.

### The Four-Step Diagnostic Chain

| # | Command | Healthy output | Problem output | Points to |
|---|---------|----------------|----------------|-----------|
| 1 | `ss -ti dst <ip>` | `retrans:0` and `rtt:50/40` | `retrans:N/N` climbing | TCP retransmission storm |
| 2 | `tcpdump -tttt -ni <iface> 'host <ip> and tcp'` | Smooth timing intervals | 1s, 2s, 4s, 8s gaps between identical segments | RFC 6298 backoff visible |
| 3 | `openssl s_client -connect <ip>:443 -servername <name> -showcerts` | "Verify return code: 0 (ok)" | "Verify return code: 21 (unable to verify)" | Certificate chain issue |
| 4 | `curl -v --tls-max 1.2 https://<name>` | TLS handshake completes, HTTP response | TLS alert received, curl reports error | Application-layer symptom |

The order matters: the `ss -ti` step is the most decisive for distinguishing "the path is the problem" from "the handshake is the problem." If `ss -ti` shows climbing retrans, the failure is at Layer 4 and the TLS handshake never even gets a chance to run cleanly. If `ss -ti` shows healthy TCP and the failure is in `openssl s_client`, the failure is at Layer 6.

### Reading `openssl s_client` Output

The most useful parts of `openssl s_client -showcerts` output:

```
CONNECTED(00000005)
---
Certificate chain
 0 s:CN = api.example.com
   i:CN = Bank Intermediate CA G2
-----BEGIN CERTIFICATE-----
MIIDxTCCAq2gAwIBAgIRAL...
-----END CERTIFICATE-----
 1 s:CN = Bank Intermediate CA G2
   i:CN = Bank Root CA
-----BEGIN CERTIFICATE-----
MIIEkjCCA3qgAwIBAgIQCg...
-----END CERTIFICATE-----
---
Server certificate
subject=CN = api.example.com
issuer=CN = Bank Intermediate CA G2
---
No client certificate CA names sent
---
SSL handshake has read 4256 bytes and written 411 bytes
Verification: OK
---
New, TLSv1/SSLv3, Cipher is ECDHE-RSA-AES256-GCM-SHA384
```

The "Verification: OK" line is the conclusion. The "Certificate chain" block shows the chain the server sent; the client tries to verify it against its trust store. If the chain's issuer (the intermediate CA) is in the trust store, verification succeeds. If not, the client tries to construct a path; if it cannot, `Verification: unable to verify` and the alert is `certificate_unknown`.

### `Verification error: unable to get local issuer certificate` (error 20)

This specific error message means the client has the leaf certificate and the root CA in its trust store, but the intermediate CA is missing. The fix is to add the intermediate CA to the client's trust store. For a server that the operator controls, this is the right answer: include the intermediate CA in the certificate chain sent during the TLS handshake (most servers do this by default, but if the chain is being served by a CDN or proxy, the chain may be incomplete).

### `Verification error: certificate has expired` (error 10)

The certificate's `notAfter` date has passed. The fix is to renew the certificate and replace it on the server.

### `Verification error: hostname mismatch` (error 62)

The certificate is valid, but the hostname in the URL does not match any of the `Subject Alternative Name` (SAN) entries. The fix is to use the correct hostname or to issue a certificate that includes the desired hostname.

### The TCP-vs-TLS Disambiguation Heuristic

When a "TLS connection fails" report comes in, the first question is "is it TCP or TLS?" A fast heuristic:

```bash
# Does TCP complete?  (If yes, the failure is in TLS or above.)
nc -vz -w 5 <ip> 443
# Does TLS complete?
echo "" | openssl s_client -connect <ip>:443 -servername <name> 2>/dev/null | grep -E 'Verify|subject|issuer'
# Does the application respond?
curl -v --max-time 10 https://<name>/ 2>&1 | grep -E 'TLS|alert|HTTP'
```

If `nc` fails, the issue is TCP. If `nc` succeeds but `openssl s_client` fails, the issue is TLS. If `openssl s_client` succeeds but `curl` fails, the issue is application-layer (HTTP, SNI mismatch, or content negotiation).

## Build It

The `code/main.py` in this lesson is a synthetic TCP+TLS trace generator. It models a TLS 1.2 handshake (ClientHello → ServerHello + Certificate → ClientKeyExchange + Finished → server's Finished) over a TCP connection that has periodic micro-bursts of loss. It also models a server that sends a chain missing the intermediate CA. To use it:

1. **Read** `code/main.py`. Notice the `FailureMode` enum, the `TcpSegment` and `TlsMessage` dataclasses (immutable), the `SimulatedNetwork` class that injects micro-bursts of loss, and the `run_handshake` function that emits the TCP and TLS events for each scenario.
2. **Run** `python3 code/main.py --mode retrans_storm` (or `--mode missing_intermediate`, `--mode cert_expired`, `--mode sni_mismatch`, `--mode healthy`). You will see the trace of TCP segments and TLS messages, with annotations for which step the failure occurs at.
3. **Compare** the five modes side by side: `python3 code/main.py --mode all`. The output will show the diagnostic chain producing a different verdict for each case.
4. **Modify** the `SimulatedNetwork` class to add a mode where the TCP handshake succeeds but the server's response to the ClientKeyExchange is fragmented across two segments and the second segment is lost. This is a "TLS retransmission storm" — a sub-case of the TCP retransmission storm that happens to occur during the TLS handshake.

## Use It

| Symptom | Diagnostic Command | Expected Output | Culprit |
|---------|-------------------|-----------------|---------|
| `curl https://` fails after 15 s | `nc -vz -w 5 <ip> 443` | "Connection refused" / "timed out" | Service down or firewall |
| `curl https://` fails after 1–2 s | `openssl s_client -connect <ip>:443 -servername <name>` | "Verify return code: 21" | Certificate chain issue |
| `curl https://` fails after 30 s | `ss -ti dst <ip>` | `retrans:N/N` climbing | TCP retransmission storm |
| `openssl s_client` fails | `openssl s_client -connect <ip>:443 -servername <name> 2>&1 \| grep -i alert` | `TLS alert: certificate_unknown` | Missing intermediate |
| `openssl s_client` fails | `openssl s_client ... 2>&1 \| grep -i 'verify error'` | "verify error:num=20" | Missing intermediate CA |
| `openssl s_client` fails | `openssl s_client ... 2>&1 \| grep -i 'expired'` | "notAfter: date in past" | Expired cert |
| `openssl s_client` fails | `openssl s_client ... 2>&1 \| grep 'subject\|issuer'` | `subject=CN=wrong.host` | SNI / hostname mismatch |
| `ss -ti` shows healthy | `curl -v --max-time 10 https://<name>` | TLS handshake completes, HTTP 4xx/5xx | Application-layer fault |
| 1 in 5 connections fail | `for i in {1..20}; do curl -s -o /dev/null -w '%{http_code}\n' https://<name>` | Most 200, some 000 | Micro-burst loss |
| 1 in 5 from one network | same command, run from different network | All 200 from one, some 000 from another | Network path specific |

## Ship It

The `outputs/prompt-tcp-retransmission-storm-to-tls-certificate-failure.md` file is your deliverable. Author a one-page runbook for "TLS connections fail intermittently" that contains:

1. The four-step diagnostic chain with one-line decision rules.
2. A reference table of TLS alerts and their implications.
3. A list of three common false-positive pitfalls: (a) `openssl s_client` succeeds but the browser fails because the browser has a different trust store, (b) a cert "works" from inside the network but fails from outside because the server sends a different chain when the CDN terminates the connection, (c) the application returns 200 but the browser shows "insecure" because the cert is for the wrong hostname (often happens with multi-tenant SaaS).
4. An "intervention menu" with the specific commands to fix each root cause: install intermediate CA, renew cert, fix SNI, fix micro-bursts (QoS policer, AQM, link flap detection).

## Exercises

1. **RFC 6298 backoff**: A TCP connection sees its SYN-ACK dropped. The RTT is 50 ms. Trace the retransmission times for the next 5 SYN attempts. How long until the connection is reset (assuming `tcp_syn_retries=6`)?
2. **TLS handshake timing**: For a TLS 1.2 handshake with 50 ms RTT, when does the client send the first application data? For TLS 1.3, when?
3. **openssl s_client reading**: An `openssl s_client` test returns "Verify return code: 21 (unable to verify the first certificate)". What does this mean? What is the most likely fix?
4. **Trust store divergence**: A user reports "your cert is broken" but `openssl s_client` from a server you control says it's fine. What are three possible explanations?
5. **Two coexisting failures**: A network has periodic micro-bursts of loss AND a server that sends an incomplete certificate chain. A user reports "intermittent TLS failures." How do you disambiguate the two? What evidence would point to each?
6. **Compare with lesson 02**: Lesson 02's "DNS works but HTTP fails" chain is for *complete* failures. This lesson's chain is for *intermittent* failures. How does the diagnostic methodology change?

## Key Terms

| Term | What it sounds like | What it actually means |
|------|---------------------|------------------------|
| TCP retransmission storm | A catchy name | A self-reinforcing cycle of packet loss and retransmission that degrades throughput |
| Micro-burst | A small explosion | A brief (100–500 ms) period of high loss or congestion, often invisible to averaged metrics |
| TLS alert | An alarm | A 2-byte message (level + description) sent by either side to signal a handshake or session failure |
| Trust store | A list | The set of root CAs that a client considers authoritative, typically in `/etc/ssl/certs/` or the system keychain |
| Intermediate CA | A middle entity | A CA that is signed by a root CA and signs leaf certificates; must be in the trust chain for verification |
| SCT | Certificate Transparency log proof | Signed Certificate Timestamp — a proof that a certificate was submitted to a CT log, required by Chrome |
| SAN | A desert | Subject Alternative Name — the extension in a certificate that lists the hostnames it is valid for |
| CRL | A list | Certificate Revocation List — a list of certificates that have been revoked, consulted during validation |
| OCSP | A protocol | Online Certificate Status Protocol — a real-time way to check if a certificate is revoked |
| SNI | A header field | Server Name Indication — a TLS extension that carries the hostname the client is trying to reach |

## Further Reading

- **RFC 6298** — *Computing TCP's Retransmission Timer*. The RTO cascade referenced in the retransmission storm.
- **RFC 5246** — *The Transport Layer Security (TLS) Protocol Version 1.2*. The full TLS 1.2 specification, including the alert protocol.
- **RFC 8446** — *The Transport Layer Security (TLS) Protocol Version 1.3*. The TLS 1.3 specification, with the reduced 1-RTT handshake.
- **RFC 6960** — *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)*. The OCSP protocol.
- **RFC 6962** — *Certificate Transparency*. The CT log protocol that browsers use to verify certificates.
- **Mozilla's SSL Configuration Generator** — https://ssl-config.mozilla.org/. The recommended TLS configurations for various server software.
- **Qualys SSL Labs** — https://www.ssllabs.com/ssltest/. The de-facto standard for testing TLS server configurations.
- **OpenSSL's s_client documentation** — `man s_client`. The full set of options for the diagnostic tool.
- **phases/08-tcp-and-udp** — TCP retransmission and timers.
- **phases/12-application-protocols** — TLS handshake and certificate validation.
- **phases/17-integrated-troubleshooting-labs/02-dns-works-but-http-fails** — the parent lesson whose diagnostic chain this lesson extends for TLS-specific failures.
- **phases/17-integrated-troubleshooting-labs/18-tcp-spurious-retransmission-versus-loss** — the deeper TCP retransmission failure class.
