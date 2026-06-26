# TLS 1.3 Handshake Capture and Cipher Suite Negotiation

> TLS 1.3 (RFC 8446) drops the 2-RTT handshake of TLS 1.2 down to a single round-trip — and frequently to zero via **0-RTT early data** — by folding key exchange into the first flight. The client sends a single **ClientHello** carrying a list of **cipher suites** (named as a 16-bit IANA registry value, e.g. `0x1301` = `TLS_AES_128_GCM_SHA256`), a **key_share** extension pre-loaded with an ephemeral **X25519** public key, and a list of **supported_versions** that advertises `0x0304` (TLS 1.3). The server replies with **ServerHello**, whose `random` field is genuinely random (no more TLS 1.2 downgrade sentinel), plus its own `key_share`, and immediately derives the handshake traffic secrets via **HKDF-Extract/Expand** over the shared **X25519** secret. From that point all further handshake messages — **EncryptedExtensions**, **CertificateRequest**, **Certificate**, **CertificateVerify**, **Finished** — fly encrypted under the handshake keys, so Wireshark sees nothing readable past ServerHello without the session keys. Negotiation collapses cipher suite, named group, and signature algorithm into three independent extension negotiations; the AEAD is always AES-GCM or ChaCha20-Poly1305, never a MAC-then-encrypt CBC mode. Failure modes include a **no_common_cipher_suite** alert (rare in modern stacks), a bad `key_share` forcing a **HelloRetryRequest** that costs an extra round-trip, and replay of 0-RTT data that an attacker captures and replays at a later connection. This lab captures a real `openssl s_client` handshake, parses the ClientHello with pure stdlib Python, and walks the state machine left behind.

**Type:** Lab
**Languages:** Python, openssl, Wireshark
**Prerequisites:** TCP three-way handshake and sockets, symmetric/asymmetric crypto basics (AES, HMAC, DH), HTTP-over-TLS familiarity
**Time:** ~85 minutes

## Learning Objectives

- Parse a raw TLS 1.3 ClientHello record by hand and identify the protocol version field, random, session ID, cipher suites list, and the `key_share` / `supported_versions` / `signature_algorithms` extensions.
- Explain why TLS 1.3 reaches 1-RTT (and 0-RTT with PSK) by folding the key exchange into the first flight, and contrast this with the two-flight TLS 1.2 ClientHello/ServerHello then KeyExchange structure.
- Trace the cipher suite, named group, and signature algorithm negotiations as three independent extension matches, and predict the alert when no intersection is found (`handshake_failure` / `no_common_cipher_suite`).
- Derive the handshake traffic secret from the X25519 shared secret through HKDF-Extract (on the early secret) and HKDF-Expand-Label, naming the labels (`derived`, `c hs traffic`, `b hs traffic`).
- Use Wireshark (or a saved key log) to decrypt a TLS 1.3 session by feeding `SSLKEYLOGFILE` lines, and explain why pre-ServerHello traffic remains visible while post-ServerHello traffic does not.
- Identify a 0-RTT early-data replay by its `early_data` extension and state which request classes are safe (idempotent) versus unsafe (POST a payment) under replay.

## The Problem

An SRE is debugging a customer report: "our mobile app's first request adds 300 ms of latency over TLS 1.2 but the competitor's app feels instant." A packet capture shows two full round-trips of plaintext handshake before the first encrypted HTTP byte — ClientHello, ServerHello/Certificate/ServerHelloDone, ClientKeyExchange/CCS/Finished, CCS/Finished — plus the server's 4 KB certificate chain traversing a flaky cellular link. The team wants to move to TLS 1.3 to halve the handshake, but the capture shows a confusing mix: a ClientHello that *says* it is version `0x0303` (TLS 1.2) yet carries a `supported_versions` extension listing `0x0304`. Is this TLS 1.2 or 1.3? Why is everything after ServerHello unreadable? And can the team safely enable 0-RTT for the login API, or will an attacker replay the customer's authentication POST?

## The Concept

### The TLS record layer and the version field paradox

TLS runs over TCP and frames every handshake and application message inside a **TLSPlaintext record** (RFC 8446 §5.1):

| Field | Bytes | Purpose |
|---|---|---|
| `ContentType` | 1 | 22=Handshake, 23=ApplicationData, 21=Alert, 20=ChangeCipherSpec (legacy) |
| `legacy_record_version` | 2 | Always `0x0303` for TLS 1.3, kept for middlebox compatibility |
| `length` | 2 | 0–16384 (2^14) bytes of fragment |
| `fragment` | `length` | The payload; encrypted once keys exist |

The first paradox every capture reader hits: the record's `legacy_record_version` and the ClientHello's `legacy_version` field are both **`0x0303`** even on a TLS 1.3 connection. TLS 1.3 is not negotiated in the version byte at all — it is negotiated in the **`supported_versions`** extension, which carries the real list ending in `0x0304`. Middleboxes that only inspect the version byte still see "TLS 1.2," which is exactly the goal of the compatibility shim. See `assets/tls-13-handshake-capture-and-cipher-negotiation.svg` for the record-frame layout and the supported_versions override.

### The ClientHello, field by field

RFC 8446 §4.1.2 defines the ClientHello. Key fields inside the Handshake (ContentType 22, handshake type 1):

| Field | Bytes | Notes |
|---|---|---|
| `legacy_version` | 2 | `0x0303` — ignored, see supported_versions |
| `random` | 32 | Client random; feeds the key schedule |
| `legacy_session_id` | 1 + var | Empty or a legacy ID; echoed for middlebox compatibility |
| `cipher_suites` | 2 + var | List of 16-bit IANA values the client will accept |
| `legacy_compression_methods` | 1 + var | Always `[0]`; compression was removed in 1.3 |
| `extensions` | 2 + var | Where every real negotiation lives |

The cipher suite list for a modern client typically contains just four TLS 1.3 suites — there is no negotiation over hundreds of CBC variants any more:

| Suite value | Name | AEAD | Hash |
|---|---|---|---|
| `0x1301` | `TLS_AES_128_GCM_SHA256` | AES-128-GCM | SHA-256 |
| `0x1302` | `TLS_AES_256_GCM_SHA384` | AES-256-GCM | SHA-384 |
| `0x1303` | `TLS_CHACHA20_POLY1305_SHA256` | ChaCha20-Poly1305 | SHA-256 |
| `0x1304` | `TLS_AES_128_CCM_SHA256` | AES-128-CCM | SHA-256 |
| `0x1305` | `TLS_AES_128_CCM_8_SHA256` | AES-128-CCM with 8-byte tag | SHA-256 |

Each suite fixes the AEAD and the hash used by HKDF. The signature algorithm and the key-exchange group are **not** in the suite — they are negotiated in their own extensions, which is why TLS 1.3 cipher suites look so sparse next to TLS 1.2's `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`.

### The three independent negotiations

TLS 1.2 packed key exchange, authentication, cipher, and MAC into one suite string. TLS 1.3 splits the choice into three orthogonal extensions:

1. **`cipher_suites`** — AEAD + hash, matched first in ServerHello.
2. **`supported_groups`** (renamed from `elliptic_curves`) — the named group for key exchange: `x25519` (0x001d), `secp256r1` (0x0017), `secp384r1` (0x0018), `x448` (0x001e). The server picks one and answers in `key_share`.
3. **`signature_algorithms`** — for CertificateVerify: `ecdsa_secp256r1_sha256`, `ed25519`, `rsa_pss_pss_sha256`, `rsa_pkcs1_sha256`, etc.

The server must satisfy all three; if any has no intersection it aborts with an Alert `handshake_failure` (40) or, specifically for cipher suites, `no_common_cipher_suite` (113 if the stack uses that sub-code). Because they are independent, a server can offer AES-256-GCM with X25519 and ECDSA, or ChaCha20 with secp256r1 and RSA-PSS — any combination the intersection allows.

### The key_share extension and the first-flight optimization

In TLS 1.2 the client sent its key share (an ECDHE public value) in a separate `ClientKeyExchange` message *after* seeing the server's choice of group, costing a round-trip. TLS 1.3 inlines the guess: the client stuffs one or more candidate **KeyShareEntry** values into the `key_share` extension of the ClientHello itself. Each entry is `group (2 bytes) + length (2 bytes) + public key`. For X25519 the public key is exactly 32 bytes.

If the server's chosen group matches an entry the client offered, the server writes its own X25519 public value into the ServerHello's `key_share` and both sides can run X25519 scalar multiplication immediately — handshake keys exist before the second flight, so Certificate and Finished are already encrypted. If the client guessed wrong (sent X25519, server wants secp256r1), the server sends a **HelloRetryRequest** echoing the chosen group, the client retries the ClientHello with a matching `key_share`, and the connection pays one extra round-trip. Modern clients list X25519 first precisely to avoid HelloRetryRequest on the common path.

### The key schedule: HKDF on top of an X25519 secret

Once both sides have the X25519 shared secret `Z`, they run it through the RFC 8446 §7.1 key schedule. Each stage extracts then expands with a **label**:

```
early_secret  = HKDF-Extract(salt=0, IKM=PSK_or_0)
derived       = HKDF-Expand-Label(early_secret, "derived", "", Hash.length)
handshake_secret = HKDF-Extract(salt=derived, IKM=Z)
c_hs_secret   = HKDF-Expand-Label(handshake_secret, "c hs traffic", transcript, Hash.length)
s_hs_secret   = HKDF-Expand-Label(handshake_secret, "b hs traffic", transcript, Hash.length)
```

`HKDF-Expand-Label` prepends the fixed string `"tls13 "` to the label, which is why a Wireshark key log shows labels like `c hs traffic` and `b ap traffic` rather than raw HKDF labels. The transcript is the hash of all handshake messages seen so far; it binds the keys to the negotiation so an attacker cannot swap a ClientHello. `code/main.py` reproduces the label construction and walks a worked example with the transcript hash left as a placeholder, since the real X25519 math needs the cryptography library — instead the demo focuses on the deterministic label framing that the standard pins byte-for-byte.

### ServerHello, EncryptedExtensions, and the encrypted handshake

ServerHello (handshake type 2) echoes `legacy_version = 0x0303`, a fresh 32-byte `random`, the chosen `cipher_suite`, and the matching `key_share` plus `supported_versions = 0x0304`. The instant both endpoints compute `handshake_secret`, the server switches to encryption and sends, all under the handshake keys:

- **ChangeCipherSpec** (a legacy no-op record, ContentType 20, sent purely to keep middleboxes from breaking) — does nothing in 1.3.
- **EncryptedExtensions** — everything that is not crypto: ALPN (`h2`), SNI acknowledgement, max_early_data_size, server_name.
- **CertificateRequest** (optional, when client auth is required).
- **Certificate** — the server's end-entity cert plus chain.
- **CertificateVerify** — a signature over the transcript-so-far using the cert's private key and a negotiated `signature_algorithms` algorithm; proves possession of the private key.
- **Finished** — an HMAC over the transcript using the finished_key derived from `handshake_secret`. This is the integrity proof that the whole negotiation was untampered.

The client then sends its own **Finished**, and both sides derive `master_secret` and the application traffic keys (`c ap traffic`, `b ap traffic`). Application data flows under ContentType 23. Wireshark cannot read any of this without the keys; export them via the `SSLKEYLOGFILE` environment variable, which OpenSSL/BoringSSL and most browsers populate with `CLIENT_RANDOM <hex> <hex>` (TLS 1.2) or `SERVER_HANDSHAKE_TRAFFIC_SECRET <hex> <hex>` plus the client/server app secrets (TLS 1.3).

### 0-RTT early data and the replay problem

When the client has previously spoken to this server it has a **PSK** (pre-shared key, resumption). On resumption it can bundle the first application request as **early data** in the first flight, before the server has even replied — true 0-RTT. The server accepts the early data only if it can decrypt it with the PSK-derived `b e traffic` key and if the `early_data` extension's limits are respected.

The catch: early data is replayable. An on-path attacker can copy the ClientHello + early_data records and replay them later; the server cannot tell the replay from a genuine retransmit because the PSK is static. The rule is therefore *only idempotent requests* may use 0-RTT: a `GET /product/42` is safe, a `POST /payments/charge` is not. RFC 8446 §8 requires servers to provide anti-replay (single-use tickets, short ticket age, or per-recipient recording) before allowing early data on state-changing operations.

## Build It

1. Read `code/main.py`. It parses a hex-encoded TLS 1.3 ClientHello from `bytes`, walks the record header, the Handshake header, the legacy fields, the cipher suite list, and every extension — printing the negotiated-looking fields a Wireshark dissection would show.
2. Run it: `python3 code/main.py`. Confirm it prints the four TLS 1.3 cipher suites, the X25519 key share length (32), and the `supported_versions` list ending in `0x0304`.
3. Generate a real ClientHello with openssl and capture it:

   ```
   openssl s_client -connect cloudflare.com:443 -tls1_3 -sess_out /tmp/sess.pem
   ```
   In another shell, `sudo tcpdump -i any -w /tmp/tls.pcap port 443`, then open `/tmp/tls.pcap` in Wireshark, set `SSLKEYLOGFILE=/tmp/keys.log`, re-run, and load the key log to decrypt post-ServerHello traffic.
4. Edit the `CLIENT_HELLO_HEX` constant in `code/main.py` to a hex blob you extract from Wireshark (right-click a ClientHello record → Copy → … as Hex Stream). Re-run and confirm the parser names the same suites Wireshark does.
5. Force a HelloRetryRequest by constraining openssl to a group the client does not offer first: `openssl s_client -groups secp384r1` against a server that defaults to X25519, and observe the extra round-trip in the capture.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm TLS 1.3 was negotiated | `supported_versions` ext lists `0x0304`; ServerHello `cipher_suite` ∈ {0x1301..0x1305} | Real version byte stays `0x0303` for middleboxes; only the extension tells the truth |
| Verify key exchange group | `key_share` in ClientHello and ServerHello use the same named group (e.g. `x25519` 0x001d) | 32-byte X25519 public value; no HelloRetryRequest on the fast path |
| Decrypt post-ServerHello traffic | `SSLKEYLOGFILE` loaded; Wireshark shows decrypted Certificate/Finished | Plaintext is empty / ApplicationData before ServerHello; readable after |
| Detect 0-RTT replay risk | `early_data` extension present; first request in captured ApplicationData | State-changing POSTs must NOT be sent as early data; GETs only |
| Diagnose a negotiation failure | Alert `handshake_failure` (40) right after ServerHello or before it | Cipher suite, group, and signature extension each checked for empty intersection |

## Ship It

Produce one artifact under `outputs/prompt-tls-13-handshake-capture-and-cipher-negotiation.md`:

- An annotated ClientHello + ServerHello byte map from a real `openssl` capture, with each extension labeled and the negotiated cipher suite, named group, and signature algorithm called out.
- A captured-and-decrypted session transcript showing where encryption turns on (ServerHello) and why pre-ServerHello traffic remains plaintext.
- A short decision table for 0-RTT: which of your service's endpoints are safe under replay and which must opt out.

Start from the printed output of `code/main.py` and annotate it with the alerts or HelloRetryRequest you observed.

## Exercises

1. A ClientHello advertises `cipher_suites = [0x1302]` only, `supported_groups = [x25519]`, `signature_algorithms = [rsa_pss_pss_sha256]`. The server has only an ECDSA secp256r1 certificate and offers suite `0x1301`. Which extension fails first, and what alert does the server send?
2. Capture a TLS 1.3 handshake to a CDN and a TLS 1.2 handshake to the same host (force `-tls1_2`). Count round-trips to first application byte in each and explain the 1-RTT saving by naming the message that moved into the first flight.
3. You run `openssl s_client -groups secp384r1` against a server that prefers X25519. Describe the HelloRetryRequest: which extension the server echoes, what the client sends in its retried ClientHello, and the extra cost in packets.
4. Given the `SERVER_HANDSHAKE_TRAFFIC_SECRET` line from an `SSLKEYLOGFILE`, explain why it cannot decrypt the ClientHello or ServerHello but does decrypt the server's EncryptedExtensions, Certificate, and Finished. Name the transcript hash that gates the key derivation.
5. A mobile banking app enables 0-RTT for `POST /transfer`. An attacker captures the ClientHello + early_data and replays it 30 seconds later. Describe the precise failure and the two anti-replay controls from RFC 8446 §8 the server should have enabled.
6. Modify `code/main.py` to also parse the ServerHello and assert that the chosen `cipher_suite`, `supported_group`, and `signature_algorithms` value each appear in the corresponding ClientHello extension. Print the negotiated tuple.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Cipher suite | "the encryption" | A 16-bit IANA value that fixes only the AEAD and hash in TLS 1.3; KE group and signature live in separate extensions |
| supported_versions | "version negotiation" | The extension that actually carries 0x0304; the legacy_version byte is stuck at 0x0303 for middlebox compatibility |
| key_share | "the public key" | An extension carrying pre-loaded ephemeral public values (e.g. 32-byte X25519) so the handshake keys can derive on flight one |
| HelloRetryRequest | "a retry" | The server's response when the client's key_share group is wrong; costs one extra round-trip to fix the guess |
| HKDF-Expand-Label | "key derivation" | HKDF-Expand with the label prefixed by "tls13 "; the function that turns the X25519 secret into traffic secrets |
| Finished | "the MAC" | An HMAC over the transcript hash using the finished_key; proves no message in the negotiation was tampered |
| ChangeCipherSpec | "the switch" | A legacy no-op record in TLS 1.3, sent only so middleboxes expecting it do not break the connection |
| 0-RTT / early data | "instant connect" | Application data sent in the first flight under a PSK-derived key; replayable, so restricted to idempotent requests |
| SSLKEYLOGFILE | "the decrypt key" | An env var browsers/openssl write to; Wireshark reads its `*_TRAFFIC_SECRET` lines to derive TLS 1.3 keys |
| PSK | "session resume" | A pre-shared key from a prior connection; the basis for resumption and the early-data encryption key |

## Further Reading

- **RFC 8446** — The Transport Layer Security (TLS) Protocol Version 1.3 (Rescorla, 2018). The authoritative spec; read §4 (handshake), §7.1 (key schedule), §8 (0-RTT).
- **RFC 8447** — IANA registry updates for TLS parameters.
- **RFC 7748** — Elliptic Curves for Security, defining X25519 and X448 used in `key_share`.
- **RFC 5869** — HMAC-based Extract-and-Expand Key Derivation (HKDF), the primitive under HKDF-Expand-Label.
- **RFC 5246** — TLS 1.2, for contrast: the two-RTT handshake and the legacy version-byte semantics.
- IANA TLS Cipher Suites registry — the master list of 16-bit suite values, including the `0x13xx` TLS 1.3 block.
- Benjamin & Watson, "Protecting TLS 1.3 from 0-RTT Replay," IETF TLS WG drafts — anti-replay single-use and bucketed-window schemes.
- Bernstein, "Curve25519: new Diffie-Hellman speed records," PKC 2006 — the X25519 design rationale.
- Kurose & Ross, *Computer Networks*, 8th ed., Chapter 8, for the transport-security context this lab builds on.
