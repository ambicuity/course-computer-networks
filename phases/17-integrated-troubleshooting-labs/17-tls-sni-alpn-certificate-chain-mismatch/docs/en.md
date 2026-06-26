# TLS SNI/ALPN and Certificate Chain Validation Mismatch

> A web service runs on a single IP address, `203.0.113.10`, and serves three hostnames: `app.example.com`, `api.example.com`, and `legacy.example.com`. The server is configured with a default certificate for `app.example.com`, and the other two are SNI-based certificates. A `curl --resolve api.example.com:443:203.0.113.10 https://api.example.com` call works. A `curl https://203.0.113.10` call returns the `app.example.com` certificate. A `curl -H 'Host: api.example.com' http://203.0.113.10` returns the right HTTP content. The mismatch surfaces when a Java client uses the legacy `httpsConnectionImpl` default and skips the SNI extension entirely (Java 8u60 and earlier had this problem): the client opens a TLS session to `203.0.113.10` with no SNI, the server falls back to the default certificate (`app.example.com`), the client validates the chain (which is fine — it is a real cert for `app.example.com` signed by a public CA), and the hostname check fails with `javax.net.ssl.SSLPeerUnverifiedException: Hostname 203.0.113.10 not verified`. The fix is `jsse.enableSNIExtension=true` and a stack update. A second variant of the same problem: the server's certificate chain is missing the intermediate CA, the chain is incomplete, and the client fails to validate the chain even though the leaf is correct. This lab walks both failure modes with `openssl s_client` and the precise diagnostic command for each.

**Type:** Lab
**Languages:** Python, openssl, Wireshark
**Prerequisites:** Phase 14 TLS 1.3 handshake, the SNI extension (RFC 6066), the ALPN extension (RFC 7301)
**Time:** ~95 minutes

## Learning Objectives

- Diagnose a TLS handshake that fails with `SSLPeerUnverifiedException` (Java) or `SSL_ERROR_BAD_CERT_ALERT` (OpenSSL) by reading the `s_client` output: the `subject` of the returned leaf, the `issuer` chain, and the SNI the client sent.
- Distinguish three failure modes: (a) hostname mismatch (wrong leaf returned), (b) incomplete chain (missing intermediate), (c) protocol mismatch (ALPN advertised but server returns 1-RTT only).
- Construct a synthetic ClientHello in Python (stdlib `struct`, `socket`) that places an SNI extension in the `Extensions` block, and read the server's chosen ALPN back from the ServerHello.
- Run `openssl s_client -connect host:443 -servername <name>` with and without `-servername` and explain why the latter is the diagnostic for the missing-SNI case.
- Inspect a Wireshark capture of a TLS 1.3 handshake: the ClientHello, the SNI extension (type `0x0000`), the ALPN extension (type `0x0010`), and the server's `Certificate` record.
- Build a Python diagnostic that, given a synthetic ClientHello and the server's `Certificate` record, classifies the failure as hostname-mismatch, chain-incomplete, or ALPN-refused, and prints the corrective action.

## The Problem

The on-call ticket reads: "Our Java backend integration is failing in production with `SSLPeerUnverifiedException`, but `curl` from the same machine works fine." The integration tests have been green for two months. The production deploy changed the client to a newer JVM — but not the underlying JSSE defaults. The integration was never actually using SNI before, because the old code path was a separate `HttpURLConnection` implementation that sent SNI by default. The new code path is `HttpsClient` (or `Apache HttpClient`) on Java 17, and a different code branch handles the `HostnameVerifier` default.

The production server is shared, IP `203.0.113.10`, three hostnames. The Java client opens the socket, sends a ClientHello with no SNI, the server's SNI-based selection cannot match, and the server returns the default certificate for `app.example.com`. The Java client then does its hostname check on the leaf: the leaf is for `app.example.com`, the URL the client is connecting to is `https://api.example.com/`, the names do not match, the client throws.

The diagnostic move is to repeat the same connection with `openssl s_client` and to compare the SNI the client sends with the SNI the server selects. The command is:

```
openssl s_client -connect 203.0.113.10:443 -servername api.example.com
```

With `-servername api.example.com`, `s_client` puts the SNI in the ClientHello; the server picks the `api.example.com` certificate; the chain validates. Without `-servername` (i.e. `openssl s_client -connect 203.0.113.10:443`), the SNI is empty; the server returns the default certificate; the chain has a different subject. The two outputs side by side are the proof.

A second failure mode, often co-occurring: the leaf certificate is correct for `api.example.com`, but the intermediate CA is missing from the chain. The server did not include it in the `Certificate` record, and the client cannot validate the chain. The diagnostic is the line "No client certificate CA names sent" followed by an empty chain block, or `Verify return code: 21 (unable to verify the first certificate)`. The fix is server-side: configure the web server to send the full chain, not just the leaf.

## The Concept

### The SNI extension (RFC 6066 §3)

TLS 1.0 did not have a way to tell the server "this handshake is for hostname X" before the server chose a certificate. The fix was the **Server Name Indication** extension, type `0x0000` in the `Extensions` block of the ClientHello. The extension carries the hostname as a `HostName` (length-prefixed byte string). The server reads it, looks up the right certificate, and proceeds.

A TLS handshake without SNI is allowed — the server then uses its *default* certificate. On a shared-IP server with multiple virtual hosts, the default certificate is whichever one the operator configured as the fallback. If the client does not send SNI, the server picks the default, and if the default does not match the hostname the client is verifying, the connection fails.

The Java 8u60 fix story is the canonical example of why this matters: before 8u60, the JSSE did not send SNI by default for `HttpsURLConnection` on shared-IP servers, and the failure was silent (or a hostname-mismatch exception). The `-Djsse.enableSNIExtension=true` flag (now the default in Java 17) forces SNI on.

### The ALPN extension (RFC 7301)

`ALPN` is a separate TLS extension, type `0x0010`, that lets the client and server negotiate the *application-layer* protocol. Common ALPN identifiers: `h2` (HTTP/2), `http/1.1`, `h3` (HTTP/3 over QUIC). The client advertises a list, the server picks one. The `ALPN` extension appears in the ClientHello and in the ServerHello, and the negotiated value is in the `Application-Layer Protocol Negotiation` field of the encrypted handshake (TLS 1.3) or in the clear (TLS 1.2).

A failure mode here is the client advertising `h2` but the server only supports `http/1.1`. The server picks `http/1.1`, the client tries to interpret the response as HTTP/2, the connection breaks. The diagnostic is to read the ServerHello's ALPN field and compare it to the client's offer list.

### The certificate chain structure

A TLS server's `Certificate` record contains a list of ASN.1 certificates, in order: leaf first, then intermediates, then optionally the root. The client walks the chain from the leaf upward, looking for a certificate signed by a trusted root. A "complete" chain is one that the client can walk all the way to a root in its trust store. An "incomplete" chain is one where the server did not include enough intermediates — the client does not have the bridge from the leaf to a trusted root.

The diagnostic command is `openssl s_client -connect host:443 -showcerts`. The output shows the chain the server sent. If the chain is two entries (leaf, intermediate) and the client needs three (leaf, intermediate, root), the chain is incomplete.

### Hostname validation: SAN, not CN

Since RFC 6125 (and the deprecation in CA/B Forum BRs), the only valid hostname source is the `subjectAltName` (SAN) extension. The `CN` (Common Name) in the `subject` is *no longer trusted* by modern clients for hostname validation. The diagnostic is to extract the SAN list and check that the requested hostname is in it. `openssl x509 -in leaf.pem -text -noout | grep -A1 "Subject Alternative Name"` is the canonical one-liner.

### How the simulator models this

`code/main.py` reads a synthetic ClientHello (built offline) and a synthetic `Certificate` record (built by the user pasting the leaf and chain, or by selecting a scenario), and produces a verdict. The three scenarios are `hostname_mismatch` (server returned the wrong leaf), `chain_incomplete` (intermediate is missing), and `alpn_refused` (ALPN offer did not match). The simulator prints the verdict, the responsible layer, and the corrective action.

## Build It

1. **Capture a real handshake.** `tcpdump -i any -w tls.pcap port 443` while running `curl -v https://api.example.com`. Stop the capture.
2. **Run openssl s_client.** Repeat the same `curl` against `s_client -servername` to compare. Note the leaf `subject` in each output.
3. **Inspect SNI/ALPN.** Open `tls.pcap` in Wireshark. Filter on `tls.handshake.extensions.server_name` and `tls.handshake.extensions.alpn`. Confirm the SNI matches the hostname you sent.
4. **Run the simulator.** `python3 code/main.py --mode hostname_mismatch` should produce the matching verdict.
5. **Ship the runbook.** A one-page runbook with the three `openssl s_client` flags and the three failure verdicts.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Detect missing SNI | `s_client` output without `-servername` | Default cert returned; subject may not match the requested hostname |
| Detect wrong leaf | `s_client` shows `subject` differing from the requested hostname | Hostname validation fails; `Verify return code: 62` |
| Detect incomplete chain | `s_client` shows fewer certs than needed; `Verify return code: 21` | Server is not sending the full chain |
| Confirm ALPN | `s_client` shows `ALPN protocol: h2` | ALPN negotiation succeeded |
| Detect ALPN refusal | `s_client` shows no `ALPN protocol:` line; client only sees `http/1.1` | Server does not support the offered ALPN |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **TLS chain validation triage runbook** with the three failure modes and the one diagnostic command for each.
- A **before/after** `s_client` capture showing the same server, the same client, with and without `-servername`, to make the SNI effect visible.

Start from `outputs/prompt-tls-sni-alpn-certificate-chain-mismatch.md`.

## Exercises

1. `openssl s_client -connect example.com:443 -servername example.com` returns `subject=CN = api.example.com`. The user requested `example.com`. Which TLS extension is the server reading, and what is the failure mode?
2. The chain has only one entry: the leaf. The client's trust store has the intermediate but not the root. Will validation succeed? Why or why not?
3. A client advertises `ALPN: h2, http/1.1` and the server returns no ALPN extension. The client then sends an HTTP/1.1 request. What did the negotiation produce, and is this an error?
4. A Java client gets `SSLPeerUnverifiedException: Hostname '203.0.113.10' not verified`. The leaf is for `app.example.com`. List, in order, the two most likely causes and the one command for each.
5. The server's certificate is signed by `ISRG Root X1` (Let's Encrypt). The client trust store is missing that root. The chain is otherwise complete. What is the failure mode and the fix?
6. A Wireshark capture of a TLS 1.3 handshake shows the `Certificate` record, but the SNI extension is missing from the ClientHello. Will the server pick the right certificate? What is the consequence for hostname validation?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SNI | "Hostname in TLS" | Server Name Indication extension (RFC 6066 §3), `0x0000` in ClientHello; tells the server which virtual host the client wants |
| ALPN | "Next-protocol" | Application-Layer Protocol Negotiation (RFC 7301), `0x0010` in ClientHello/ServerHello; selects h2, http/1.1, etc. |
| SAN | "The hostname list" | Subject Alternative Name extension; the only valid source for hostname validation since RFC 6125 |
| Incomplete chain | "Missing intermediate" | The server's `Certificate` record did not include enough intermediates for the client to walk to a root |
| Hostname mismatch | "Wrong cert" | Leaf certificate's SAN list does not contain the requested hostname |
| TLS 1.3 `Certificate` record | "Encrypted cert" | In TLS 1.3 the certificate is encrypted under the handshake traffic secret; use `s_client` to see it |
| `-servername` flag | "SNI in s_client" | The `openssl s_client` flag that puts the SNI extension in the ClientHello |
| `Verify return code` | "Chain verdict" | `s_client`'s verdict; 0 = OK, 21 = unable to verify first cert, 62 = hostname mismatch |

## Further Reading

- RFC 6066 §3 — Server Name Indication
- RFC 7301 — ALPN (Application-Layer Protocol Negotiation)
- RFC 8446 — TLS 1.3 (the `Certificate` record, the encrypted handshake)
- RFC 6125 — Representation and Verification of Domain-Based Application Service Identity (SAN-based hostname validation)
- CA/B Forum Baseline Requirements — deprecation of CN-based hostname validation
- `openssl s_client(1)` and `openssl x509(1)` man pages
- Wireshark — `tls.handshake.extensions.server_name` and `tls.handshake.extensions.alpn` display filters
