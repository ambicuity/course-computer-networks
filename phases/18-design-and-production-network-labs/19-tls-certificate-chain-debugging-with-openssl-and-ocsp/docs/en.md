# TLS Certificate Chain Debugging with openssl and OCSP Stapling

> A TLS certificate that has expired, that is signed by an untrusted CA, that has a hostname mismatch, or that has been revoked is the cause of the most visible and most preventable outage in modern web infrastructure. A user sees "Your connection is not private" or "NET::ERR_CERT_AUTHORITY_INVALID" and immediately moves to a competitor site. The certificate chain is the foundation of TLS trust: the **leaf certificate** (the server's certificate), the **intermediate certificate(s)** (the CA's signing certificates), and the **root certificate** (the trust anchor in the browser's trust store). If any link in the chain is missing, expired, or untrusted, the TLS handshake fails. **OCSP stapling** (RFC 6960 / RFC 8446) is the mechanism by which the server periodically fetches a signed proof of its certificate's validity from the CA's OCSP responder and presents it during the TLS handshake, so the client does not have to contact the OCSP responder separately. This lesson is the working playbook for debugging TLS certificate chains with `openssl s_client`, `openssl x509`, `openssl verify`, and `openssl ocsp`, for understanding the chain-building rules (RFC 8446), for configuring OCSP stapling in NGINX, HAProxy, Apache, and the cloud load balancers, for setting up the OCSP responder (or using a third-party responder), and for the operational runbook (the 30-day-before-expiry monitoring, the chain-update procedure, the revocation response). The deliverable is a Python TLS chain debugger that takes a hostname and a port, performs the TLS handshake in stdlib, and emits the openssl-style output with the certificate details, the chain, the OCSP response, and a list of issues.

**Type:** Lab
**Languages:** Python (stdlib only: ssl, socket, hashlib, datetime, base64, dataclasses), openssl, curl
**Prerequisites:** Phase 14 cryptography, Phase 18 lesson 18 (HAProxy/TLS)
**Time:** ~120 minutes

## Learning Objectives

- Explain the **TLS certificate chain** (leaf, intermediate, root), the **chain-building rules** (RFC 8446 section 4.4.2), and the failure modes (missing intermediate, untrusted root, expired leaf, hostname mismatch, revoked certificate).
- Use **openssl s_client** to perform a TLS handshake, dump the certificate, and inspect the chain, the subject, the issuer, the validity dates, the SAN, and the public key.
- Use **openssl x509** to parse a certificate file, inspect the extensions (SAN, Key Usage, Extended Key Usage, Basic Constraints, AIA, CRL distribution points), and verify the signature.
- Use **openssl verify** to verify a certificate against a CA bundle, and to debug chain-of-trust failures.
- Use **openssl ocsp** to send an OCSP request to the CA's responder and parse the response (good / revoked / unknown).
- Configure **OCSP stapling** in NGINX (`ssl_stapling on; ssl_stapling_verify on;`), HAProxy (`ssl ocsp-update`), Apache (`SSLUseStapling On`), and the cloud LBs, and verify the stapled response with `openssl s_client -status`.

## The Problem

A B2B SaaS company, "Compliance Vault," has been receiving support tickets from customers reporting that the application shows "Your connection is not private" in Chrome, "The certificate is not trusted" in Firefox, and "The certificate has expired" in Safari. The certificate was issued by Let's Encrypt, and the chain is `leaf -> R3 -> ISRG Root X1`. The Chrome trust store trusts ISRG Root X1, but Firefox (older versions) and Safari do not trust ISRG Root X1 by default — they trust `DST Root CA X3`, which expired in September 2021. The fix is to add the ISRG Root X1 to the chain and to ensure the chain is in the correct order (leaf first, then intermediate, then root or cross-signed).

The lesson's `code/main.py` performs the TLS handshake, dumps the chain, and reports the issues.

## The Concept

### The certificate chain and the chain-building rules

The **certificate chain** is the sequence of certificates that the client walks from the leaf to a trusted root. Each certificate in the chain is signed by the next one (the issuer), and the final certificate is the root, which is self-signed and is in the client's trust store. The chain is built by the server, which sends the leaf and the intermediates (in the `Certificate` message of the TLS handshake) and the client adds the root from its trust store.

The **chain-building rules** (RFC 8446 section 4.4.2) require that:

1. The chain is in order: the leaf first, then the intermediates in the order they should be used.
2. Each certificate's issuer matches the next certificate's subject.
3. The final certificate is either a trust anchor (a root in the client's trust store) or a cross-signed certificate that the client can chain to a trust anchor.
4. Each certificate's signature is valid (signed with the issuer's public key and verified with the issuer's public key).

A failure in any of these rules causes the TLS handshake to fail with a "certificate unknown" or "certificate verify failed" error.

### The openssl toolkit and the diagnostic workflow

The `openssl` toolkit has four sub-commands that are used for TLS debugging:

- `openssl s_client -connect host:port -servername host -showcerts`: performs a TLS handshake with the server, prints the certificate chain (`-showcerts`), the subject, the issuer, the validity dates, and the negotiated cipher.
- `openssl x509 -in cert.pem -text -noout`: parses a certificate file and prints the subject, the issuer, the validity dates, the SAN, the public key, and the extensions.
- `openssl verify -CAfile ca-bundle.pem -untrusted intermediate.pem cert.pem`: verifies a certificate against a CA bundle and a list of intermediate certificates.
- `openssl ocsp -issuer intermediate.pem -cert cert.pem -url http://ocsp.example.com -resp_text`: sends an OCSP request to the CA's responder and prints the response (good / revoked / unknown).

The diagnostic workflow is: (1) `s_client` to see the chain as the server sends it; (2) `x509` to inspect each certificate; (3) `verify` to check the chain-of-trust; (4) `ocsp` to check the revocation status.

### OCSP and OCSP stapling

**OCSP** (Online Certificate Status Protocol, RFC 6960) is the protocol by which a client can ask a CA "is this certificate still valid?" The CA's OCSP responder returns a signed response with one of three states: **good** (the certificate is valid), **revoked** (the certificate has been revoked), or **unknown** (the responder does not know about the certificate). The client must contact the responder separately, which adds latency and a privacy concern (the CA learns which sites the client is visiting).

**OCSP stapling** (RFC 8446 section 4.4.2.2) is the mechanism by which the server periodically fetches a signed OCSP response from the CA and presents it during the TLS handshake. The client receives the OCSP response along with the certificate, validates the response, and uses it instead of contacting the OCSP responder directly. OCSP stapling reduces latency, improves privacy, and is required by the Chrome "Certificate Transparency" policy for EV certificates.

The `must-staple` certificate extension (RFC 7633) is a stronger form: the certificate contains a TLS feature that says "the server MUST present a stapled OCSP response, or the handshake fails." This prevents a misconfigured server from silently falling back to non-stapled OCSP.

### The operational runbook: 30-day expiry monitoring and the chain update

The most common TLS outage is a certificate that expires. The operational runbook includes:

- **30-day-before-expiry monitoring**: a Prometheus exporter (e.g., `blackbox_exporter` with a `tcp` probe that inspects the certificate) that checks the certificate's `notAfter` date every hour and pages the on-call 30, 14, 7, 3, and 1 days before expiry.
- **Chain-update procedure**: a documented process for renewing the certificate, updating the chain, and deploying the new certificate. The process is automated with Let's Encrypt's `certbot` or with a commercial CA's API.
- **Revocation response**: a documented process for responding to a CA's revocation notice (e.g., a key compromise). The process includes: (1) revoke the certificate, (2) generate a new key pair, (3) request a new certificate, (4) deploy the new certificate, (5) update the OCSP responder cache.

The lesson's planner generates the monitoring configuration, the renewal script, and the revocation runbook.

## Build It

The deliverable is `code/main.py`, a deterministic TLS chain debugger. Inputs are: a hostname, a port, and (optionally) a path to a CA bundle. Outputs are: the certificate chain (subject, issuer, validity, SAN, public key, signature algorithm, key length, key usage, extended key usage, basic constraints, AIA, CRL distribution points, OCSP URI), the chain-of-trust verification, the OCSP response (good / revoked / unknown), and a list of issues (expired, not yet valid, hostname mismatch, weak signature, weak key, chain incomplete).

Run it: `python3 code/main.py`. The output is a JSON report and a human-readable printout.

## Use It

| Deliverable | Acceptance Criteria | Status |
|-------------|---------------------|--------|
| Certificate chain | One entry per certificate; subject, issuer, validity, SAN, extensions | Pass |
| Chain-of-trust verification | Each certificate signed by the next; root in trust store | Pass |
| OCSP response | good / revoked / unknown; signature verified | Pass |
| Issue list | Expired, not yet valid, hostname mismatch, weak sig, weak key | Pass |
| Operational runbook | 30-day monitoring, renewal, revocation | Pass |

## Ship It

The artifact is `outputs/tls_report.json` plus the printout. The output directory should also contain `monitoring.yml` (the Prometheus blackbox configuration) and `renewal.sh` (the renewal script).

## Exercises

1. **Use `openssl s_client` to inspect a real certificate.** Run `openssl s_client -connect example.com:443 -servername example.com -showcerts` and dump the chain. How many certificates are there? What is the issuer of each? What is the SAN?

2. **Use `openssl ocsp` to query a responder.** Run `openssl ocsp -issuer intermediate.pem -cert cert.pem -url http://ocsp.example.com -resp_text`. What is the response?

3. **Configure OCSP stapling in NGINX.** Add `ssl_stapling on; ssl_stapling_verify on; resolver 8.8.8.8;` to the server block. Verify with `openssl s_client -connect example.com:443 -status`.

4. **Compute the days-until-expiry for a certificate with `notAfter` of 2027-01-01.** The current date is 2026-06-25. How many days? What is the renewal deadline?

5. **must-staple and the silent fallback.** A server is configured to staple OCSP, but the OCSP responder is down. With `must-staple`, what happens? Without, what happens?

6. **Chain of trust for a cross-signed certificate.** A certificate is signed by an intermediate that is cross-signed by two roots (the old root and the new root). The client's trust store has only the new root. Which intermediate should the server send? What if the server sends the old intermediate?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Certificate chain | "Leaf -> intermediate -> root" | The sequence of certificates from the leaf to a trusted root, with each signed by the next |
| Leaf certificate | "The server's certificate" | The certificate that contains the server's public key and is signed by the intermediate |
| Intermediate certificate | "The CA's signing certificate" | The certificate that signs the leaf and is signed by the root |
| Root certificate | "The trust anchor" | A self-signed certificate that is in the client's trust store |
| OCSP | "Certificate revocation check" | RFC 6960 protocol for the client to ask a CA "is this certificate still valid?" |
| OCSP stapling | "The server presents the OCSP response" | RFC 8446 mechanism by which the server presents a pre-fetched OCSP response during the TLS handshake |
| must-staple | "The server MUST staple" | RFC 7633 certificate extension that requires the server to present a stapled OCSP response |
| SAN | "Subject Alternative Name" | The certificate extension that lists the hostnames / IPs the certificate is valid for |
| Hostname mismatch | "The cert is for the wrong hostname" | The TLS error that occurs when the certificate's SAN does not include the hostname the client is connecting to |
| AIA | "Authority Information Access" | The certificate extension that points to the CA's OCSP responder and CA issuer |

## Further Reading

- **RFC 5280** — *Internet X.509 Public Key Infrastructure Certificate and CRL Profile* — the X.509 specification
- **RFC 6960** — *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)* — OCSP
- **RFC 6961** — *OCSP Multi-Stapling and Certificate Selection* — multi-stapling
- **RFC 7633** — *X.509v3 Transport Layer Security (TLS) Feature Extension* — must-staple
- **RFC 8446** — *The Transport Layer Security (TLS) Protocol Version 1.3* — TLS 1.3
- **RFC 9162** — *Certificate Transparency Version 2.0* — CT
- **Mozilla SSL Configuration Generator** — the de-facto TLS configuration reference
- **Let's Encrypt documentation** — the free, automated CA
- **OpenSSL s_client documentation** — the open-source TLS toolkit
- **OWASP TLS Cheat Sheet** — modern TLS configuration
- **Chrome Root Store policy** — the Chrome trust store policy
- **Apple CT log policy** — the Apple CT requirements
- **RFC 7469** — *HTTP Public Key Pinning (HPKP)* — pinning (deprecated but instructive)
