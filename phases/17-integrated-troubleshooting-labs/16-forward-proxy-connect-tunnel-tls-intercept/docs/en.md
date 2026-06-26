# Forward HTTP Proxy CONNECT Tunnel and TLS Interception Failure

> The corporate proxy is `proxy.corp.example:3128` and every browser behind it is told "use a forward proxy" by a PAC file or WPAD. The user's browser negotiates a TLS session to `https://api.partner.example/orders/42`, the server's certificate is signed by `DigiCert Global G2`, the chain validates, and the page is encrypted — except the proxy is in the middle. The browser first sends a plain-text `CONNECT api.partner.example:443 HTTP/1.1\r\nHost: api.partner.example:443\r\n\r\n` (RFC 7231 §4.3.6) to the proxy. The proxy opens a TCP connection to the real server, replies `HTTP/1.1 200 Connection Established\r\n\r\n`, and from that point on it just forwards bytes — the TLS handshake on top is between the browser and the origin, and the proxy is a TCP-level byte pump. This is "tunnel mode" interception, not "MITM mode." The trouble starts when the proxy *does* MITM: it returns its own certificate for the requested hostname, signed by the corporate CA, and presents that to the browser. The browser then fails with `ERR_CERT_AUTHORITY_INVALID` — unless the corporate CA is in the system trust store, in which case the connection succeeds but every TLS session the user opens is now readable by the proxy. This lab reproduces both the working tunnel and the MITM failure, isolates the responsible command (`openssl s_client -proxy proxy.corp.example:3128 -connect api.partner.example:443 -servername api.partner.example`), and walks the diagnostics: when the chain shows `i:Intermediate - issuer=` the corporate CA, the proxy is in MITM mode; when the chain shows `i:DigiCert` the tunnel is intact.

**Type:** Lab
**Languages:** Python, shell, mitmproxy, openssl
**Prerequisites:** Phase 12 HTTP, Phase 14 TLS handshake, the PAC/WPAD lesson
**Time:** ~95 minutes

## Learning Objectives

- Diagnose a `CONNECT` tunnel that is supposed to be a byte-pump proxy and instead is performing TLS interception: read the certificate chain returned by `openssl s_client`, identify the issuer, and classify the proxy mode.
- Distinguish a transparent tunnel from an intercepting proxy using the `subject` and `issuer` of the leaf certificate and the chain's `i:` lines.
- Construct a `CONNECT` request in `python3` (stdlib `socket`) and parse the proxy's `HTTP/1.1 200` response to confirm tunnel establishment.
- Run `mitmproxy` in explicit-proxy mode, capture the `CONNECT` line, and verify the per-connection upstream destination the proxy actually opens.
- Explain why ALPN (`h2`, `http/1.1`) is visible *after* the `CONNECT` 200, not before, and why the proxy cannot tell HTTP/2 from HTTP/1.1 until the TLS handshake completes.
- Build a Python diagnostic that, given a captured `.pcap` of a `CONNECT` exchange, prints the verdict: "tunnel intact" or "MITM detected, corporate CA in chain."

## The Problem

A user reports: "My browser shows a warning page when I open `https://api.partner.example` from the office Wi-Fi, but the same URL works fine on my phone's LTE." The corporate help-desk says: "We have an exception for that hostname; the proxy is configured to allow it." The mobile phone, off-network, goes direct and works. The corporate laptop, on the office Wi-Fi, goes through `proxy.corp.example:3128` and the browser shows `NET::ERR_CERT_AUTHORITY_INVALID`.

The browser error message is correct but confusing: the certificate it received is valid, but the *issuer* is the corporate CA `CN=Corp Internal Sub-CA, OU=IT, O=Corp`, not `DigiCert Global G2`. The chain returned by the server (which in this case is the proxy) has a leaf signed by the corporate sub-CA, an intermediate issued by the corporate root, and the corporate root is in the laptop's system trust store because IT pushed it via MDM. So the chain *does* validate — but the hostname on the certificate is `*.partner.example`, which the corporate CA is *not* authorized to sign for a `partner.example` domain that has its own public CA. The browser therefore says the certificate "is not valid for api.partner.example." The proxy is in MITM mode and the corporate CA's domain constraints are wrong.

The diagnostic move is to bypass the browser and talk to the proxy directly with `openssl s_client -proxy proxy.corp.example:3128 -connect api.partner.example:443 -servername api.partner.example`. The output shows two `Certificate chain` blocks: one would be the legitimate chain (`i:DigiCert Global G2`), the other is the proxy's generated leaf. Compare the `subject` and `issuer` fields; the issuer reveals who actually terminated the TLS.

A different symptom: the proxy returns `HTTP/1.1 502 Bad Gateway` after the `CONNECT` line. That is a tunnel-establishment failure (the proxy could not reach the upstream), not a TLS failure. The right diagnostic for that case is `curl -v -x http://proxy.corp.example:3128 https://api.partner.example`, which shows the `CONNECT` line in the trace and the proxy's response.

## The Concept

### The CONNECT request and the 200 reply

`CONNECT` is an HTTP/1.1 method (RFC 7231 §4.3.6, obsoleted by RFC 9110 §9.3.6) that asks a proxy to open a TCP tunnel to a target host and port and then become a byte pump. The request is plain text:

```
CONNECT api.partner.example:443 HTTP/1.1
Host: api.partner.example:443
User-Agent: curl/8.4.0
Proxy-Authorization: Basic <base64>

```

The proxy's success reply is also plain text:

```
HTTP/1.1 200 Connection Established
```

After that line and a blank line, the proxy switches to a TCP-level relay: whatever bytes the client sends, it forwards to the origin; whatever the origin sends, it forwards to the client. The proxy no longer parses HTTP. That is the **tunnel** invariant.

A non-200 reply — `407 Proxy Authentication Required`, `403 Forbidden`, `502 Bad Gateway`, `504 Gateway Timeout` — means the tunnel was not established. `407` means the proxy wants credentials; `502`/`504` mean the proxy could not reach the upstream. The `200` does *not* prove MITM; the proof is in the next step (the TLS handshake).

### The two proxy modes

| Mode | What the proxy does with TLS | Evidence in `s_client` output | Browser behavior |
|---|---|---|---|
| Tunnel (RFC 7231) | Forwards TLS bytes to origin | `issuer = DigiCert Global G2` (or whatever the real CA is) | Normal, no warning |
| MITM (decrypt) | Terminates TLS, opens new TLS to origin, re-encrypts | `issuer = CN=Corp Internal Sub-CA` | `ERR_CERT_AUTHORITY_INVALID` unless corp CA trusted AND name constraints cover the domain |

A "transparent" proxy is one that intercepts traffic without the browser being configured (typically by a layer-3 redirect on the gateway). A "forward" proxy is one the browser is told about. The two modes of *TLS* behavior are tunnel and MITM, and the test is the same: read the issuer of the leaf cert.

### What `openssl s_client` actually shows

Running `openssl s_client -proxy proxy.corp.example:3128 -connect api.partner.example:443 -servername api.partner.example -showcerts` prints the certificate chain, the negotiated cipher, the negotiated ALPN, and the peer signature. The diagnostic-grade output is:

```
CONNECTED(00000005)
---
Certificate chain
 0 s:CN = api.partner.example          <-- subject
   i:CN = Corp Internal Sub-CA         <-- issuer: corporate CA = MITM
 1 s:CN = Corp Internal Sub-CA
   i:CN = Corp Internal Root
---
Server certificate
subject=CN = api.partner.example
issuer=CN = Corp Internal Sub-CA
---
No client certificate CA names sent.
---
SSL handshake has read 2941 bytes and written 423 bytes
Verification: OK                <-- chain validates, but for the wrong name
```

The `Verification: OK` is misleading: it means the chain signed correctly, *not* that the certificate is valid for the hostname you asked for. To check hostname validation, add `-verify_hostname api.partner.example` and you get `Verification error: hostname mismatch`. The right tool is `curl -v` with the proxy option, because `curl` does the hostname check that browsers do.

### Why ALPN is post-CONNECT

`ALPN` (RFC 7301) is a TLS extension that lets the client and server negotiate the next protocol. The proxy cannot see ALPN before the `CONNECT` 200, because the proxy has not yet seen the TLS handshake — it has only seen the plain-text `CONNECT` line. The ALPN negotiation happens *inside* the tunnel. This is why a tunnel-mode proxy can carry HTTP/2, HTTP/1.1, or anything else: it never decodes the bytes.

A MITM proxy *can* see ALPN, because it terminates TLS. It may also rewrite the ALPN to downgrade HTTP/2 to HTTP/1.1 for inspection. That is detectable by comparing the ALPN the client sent (`ClientHello.alpn_protocols`) with the ALPN the server saw on the upstream connection.

### Capturing the CONNECT in mitmproxy

`mitmproxy` running in explicit-proxy mode (`mitmdump -s dump.py --mode regular`) sees the `CONNECT` line and prints it. The flow capture mode (`--mode flow`) replays the entire connection including the body. The diagnostic question — "is the proxy MITM-ing this hostname or just tunnelling it?" — is answered by inspecting the `tls` peer's `sni` (Server Name Indication) field on the *first* connection the proxy opens, and comparing it to the SNI on the *upstream* connection. If the SNIs differ, the proxy is in MITM mode.

### How the simulator models this

`code/main.py` parses a synthetic capture of a `CONNECT` exchange, plus a TLS handshake transcript that the user pastes in (or that the script generates in the happy path), and produces a verdict. It does not sniff live traffic. The `proxy_mode` argument lets you rehearse both "tunnel" and "mitm" outcomes. The point is to make the diagnostic mechanical: you read the cert chain, you classify the issuer, you are done.

## Build It

1. **Capture the CONNECT.** Start a `mitmproxy` instance on `:8080`, point a browser at it, and load `https://example.com`. The `mitmproxy` event log shows `CONNECT example.com:443`. Save the dump.
2. **Run openssl directly.** `openssl s_client -proxy 127.0.0.1:8080 -connect example.com:443 -servername example.com -showcerts`. Save the `Certificate chain` block.
3. **Run the simulator.** `python3 code/main.py --mode tunnel` and `python3 code/main.py --mode mitm` should produce the two verdicts.
4. **Compare.** The leaf certificate's `issuer` field is the diagnostic.
5. **Ship the runbook.** One page listing the three commands: `openssl s_client -proxy`, `curl -v -x`, `mitmdump --mode regular`. Each is paired with the verdict it produces.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm tunnel mode | Leaf cert `issuer` is the public CA | `issuer = DigiCert Global G2` (or whatever the origin's CA is) |
| Detect MITM mode | Leaf cert `issuer` is the corporate sub-CA | `issuer = CN=Corp Internal Sub-CA, O=Corp` |
| Confirm CONNECT succeeded | `HTTP/1.1 200 Connection Established` | Proxy switched to byte-pump mode |
| Diagnose 502 Bad Gateway | `HTTP/1.1 502 Bad Gateway` in proxy reply | Proxy could not reach upstream; check DNS / routing from the proxy's egress |
| Verify ALPN survived | `ALPN protocol: h2` in `s_client` output | Tunnel is intact and HTTP/2 is in use |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **proxy mode triage runbook**: a one-page decision tree mapping `s_client` output to "tunnel," "MITM," or "connect failure."
- A **certificate-chain comparison sheet** showing the same hostname's cert under tunnel mode vs. MITM mode, with the issuer field highlighted.

Start from `outputs/prompt-forward-proxy-connect-tunnel-tls-intercept.md`.

## Exercises

1. The proxy returns `HTTP/1.1 407 Proxy Authentication Required`. What is the next `curl` flag to set? What header is the proxy expected to send back in its 407?
2. `openssl s_client` shows `issuer=CN=Corp Internal Sub-CA` and `Verification: OK`. Why is the `OK` misleading, and what single flag would make `s_client` reject the cert?
3. You see `ALPN protocol: http/1.1` in the `s_client` output, but the server advertises `h2` in its `ssl_protocols`. Name two possible reasons and how you would distinguish them.
4. The proxy returns `HTTP/1.1 502 Bad Gateway` after the `CONNECT`. List the three most likely upstream-side causes, in order, and the one command for each.
5. A `mitmproxy` dump shows two TLS connections for a single `CONNECT`: the client→proxy and the proxy→origin. The first has `sni=api.partner.example`, the second has `sni=api.partner.corp.internal`. Is the proxy in tunnel mode or MITM mode? Why?
6. You capture a `CONNECT` to `internal.corp.example:8443` that is *not* a public host. The proxy's cert is `CN=internal.corp.example` signed by the corp root. The laptop trusts the corp root. The browser shows no warning. Is this MITM? Justify with the chain.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Forward proxy | "The proxy" | An intermediary the browser is explicitly configured to use; receives `CONNECT` for tunnelled traffic |
| CONNECT method | "Tunnel request" | HTTP/1.1 method that asks a proxy to open a TCP tunnel (RFC 7231 §4.3.6) |
| Tunnel mode | "Passthrough" | Proxy forwards TLS bytes; the TLS session is between client and origin |
| MITM proxy | "TLS inspection" | Proxy terminates TLS, opens a new TLS to origin, re-encrypts; requires the proxy's cert to be trusted |
| ALPN | "Next-protocol negotiation" | TLS extension that selects the application protocol (RFC 7301); only visible after `CONNECT` 200 |
| SNI | "Hostname in TLS" | Server Name Indication extension (RFC 6066); the proxy's MITM mode shows two different SNIs |
| `ERR_CERT_AUTHORITY_INVALID` | "Bad CA" | The leaf's issuer is not trusted for the requested hostname |
| `HTTP/1.1 200 Connection Established` | "Tunnel up" | Proxy's success reply; from this point, byte-pump mode |

## Further Reading

- RFC 7231 §4.3.6 (and its successor RFC 9110 §9.3.6) — `CONNECT` method definition
- RFC 6066 — TLS Extensions: SNI (`server_name`)
- RFC 7301 — ALPN (Application-Layer Protocol Negotiation)
- RFC 8446 — TLS 1.3 (handshake, certificate chain)
- `mitmproxy` docs — explicit proxy mode, `--mode regular` and `--mode flow`
- `openssl s_client(1)` — proxy, servername, showcerts, verify_hostname flags
- `curl` man page — `-x` / `--proxy` and the `HTTPS_PROXY` environment variable
