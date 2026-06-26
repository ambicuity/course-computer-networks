# TLS detail: record layer, handshake, and cipher suite negotiation

> TLS 1.3 (RFC 8446) collapses what used to be two round-trips of TLS 1.2 into one, removes a pile of obsolete ciphers (RC4, DES, 3DES, MD5, SHA-1, static RSA, export-grade anything), and binds every byte of the handshake into a single transcript hash that both sides sign with their long-term keys. The protocol has three layers: the record layer fragments and encrypts application data with AEAD (AES-GCM or ChaCha20-Poly1305 in TLS 1.3), the handshake negotiates cipher suites and keying material, and the alert protocol signals errors and closure. A TLS 1.3 handshake fits in 1-RTT: ClientHello (with key_share for ECDHE) → ServerHello + EncryptedExtensions + Certificate + CertificateVerify + Finished. The previous "HelloRetryRequest" pattern handles a missing key_share, giving a worst case of 2-RTT. This lesson parses a real PCAP, walks the record layer, walks the handshake state machine, and demystifies why "TLS_AES_128_GCM_SHA256" means what it means.

**Type:** Project
**Languages:** Python, packet traces, Wireshark
**Prerequisites:** Phase 18 (X.509), Phase 20 (Diffie-Hellman), Phase 22 (public-key auth), Phase 14 (AES / AEAD)
**Time:** ~120 minutes

## Learning Objectives

- Parse the TLS record header: `content_type` (1 byte: handshake=22, alert=21, change_cipher_spec=20, application_data=23), `version` (2 bytes: 0x0303 for TLS 1.2/1.3 wire-compat), `length` (2 bytes), `fragment` (≤ 2^14 bytes for plaintext; 2^14 + 256 for ciphertext with padding).
- Walk the TLS 1.3 handshake state machine: ClientHello → ServerHello → EncryptedExtensions → Certificate → CertificateVerify → Finished → (client) Finished → application data.
- Decode the `supported_versions` extension, the `key_share` extension (named groups: X25519, P-256, P-384, ffdhe2048), and the `signature_algorithms` extension (RSA-PSS, ECDSA, Ed25519).
- Identify the cipher suite ID from the wire and read it as `TLS_{KEY_EXCHANGE}_{AEAD}_{HASH}` (TLS 1.2 era) or just `TLS_{AEAD}_{HASH}` (TLS 1.3).
- Use Wireshark display filters to isolate handshake, application data, and alerts, and follow the TLS stream to reassemble the HTTP request inside.
- Replay a captured ClientHello against a live server, observe the server's negotiated cipher, and verify it matches the `supported_versions` and `key_share` the client offered.

## The Problem

You are paged at 2 AM because a service is "doing TLS but the connection is slow." The first reaction is to suspect the cipher suite (AES-GCM vs ChaCha20) or the certificate chain. The second is to suspect the round-trip count (1-RTT vs 2-RTT, hello retry request, false start). The third is to suspect the application: maybe the client opened a connection before it had any data to send and TLS 1.3's 0-RTT extension actually fired and now everything is replayed and rejected. None of these guesses are useful without being able to read a TLS handshake on the wire.

TLS 1.3 (RFC 8446, finalized August 2018, deployed everywhere by 2022) is interesting because it is *almost* a complete rewrite of TLS 1.2 but only externally: the record-layer framing looks the same on the wire (still `0x16 0x03 0x03 ...`), but the state machine is dramatically simpler. There are no more `ChangeCipherSpec` messages in TLS 1.3, no more `ServerKeyExchange` for non-EC suites, no more static RSA key exchange, and no more renegotiation (sessions are tied to PSKs or external tickets). The reason this lesson matters is that every modern HTTP/2 and HTTP/3 deployment runs over TLS 1.3, and every modern service mesh (Envoy, Linkerd, Istio) inherits the same handshake and the same failure modes.

## The Concept

### The record layer (RFC 8446 §5)

Every byte on the wire after the TCP handshake is wrapped in a TLS record:

```
+----------+----------+----------+----------+
| CT (1)   | version  | length   | fragment |
|          | (2)      | (2)      | (≤ 16384)|
+----------+----------+----------+----------+
```

- `CT` (content type): 22 (handshake), 23 (application_data), 21 (alert), 20 (change_cipher_spec; legacy, mostly absent in 1.3)
- `version`: 0x0303 for TLS 1.2 and TLS 1.3 wire-compat (the record-layer version never updates; the real version is in the `supported_versions` extension)
- `length`: 16-bit big-endian; for plaintext records ≤ 2^14 (16384) bytes; for ciphertext records ≤ 2^14 + 256

In TLS 1.3, the *first* byte of the fragment is the real content type only for plaintext records (handshake). Once encryption starts, the record is opaque ciphertext with a per-record nonce; the real content type is in a single byte appended at the very end of the AEAD output (this is "TLS 1.3 record outer type" — important when writing parsers).

### The handshake state machine

TLS 1.3 collapses the 1.2 handshake into a 1-RTT exchange:

```
Client                                              Server
  ------ ClientHello (random, session_id, ciphers, key_share, sig_algs, supported_versions) --->
                                                   select cipher, key_share, derive handshake secret
  <----- ServerHello (selected cipher, server key_share) -----
  <----- EncryptedExtensions (server-only extensions, e.g., server_name) -----
  <----- Certificate (server chain) -----
  <----- CertificateVerify (signature over transcript) -----
  <----- Finished (MAC over transcript) -----
  compute handshake secret, derive keys, decrypt server flight
  ----- Certificate (optional, for mutual auth) ----->
  ----- CertificateVerify (signature) ----->
  ----- Finished (MAC over full transcript) ----->
  derive application traffic keys
  ----- application data ------>
  <----- application data ------
```

The transcript hash is taken over every handshake message *as it appears on the wire* (after the 4-byte record header, before encryption). Each side computes its own transcript and signs/MACs it. Any change to a single byte invalidates both `CertificateVerify` (server) and `Finished` (client and server).

### Cipher suite IDs

TLS 1.2 and below use 2-byte cipher suite identifiers assigned by IANA. TLS 1.3 retains these identifiers but only allows AEAD suites; the key exchange and authentication are negotiated separately:

| Cipher suite ID | Name | AEAD | Hash |
|---|---|---|---|
| 0x1301 | TLS_AES_128_GCM_SHA256 | AES-128-GCM | SHA-256 |
| 0x1302 | TLS_AES_256_GCM_SHA384 | AES-256-GCM | SHA-384 |
| 0x1303 | TLS_CHACHA20_POLY1305_SHA256 | ChaCha20-Poly1305 | SHA-256 |
| 0x1304 | TLS_AES_128_CCM_SHA256 | AES-128-CCM | SHA-256 |
| 0x1305 | TLS_AES_128_CCM_8_SHA256 | AES-128-CCM-8 | SHA-256 |

Note that the hash part in TLS 1.3 is for the HKDF (RFC 5869) used to derive the key schedule from the ECDHE shared secret; it is *not* the integrity hash of the AEAD. The AEAD's GHASH (GCM) or Poly1305 does the integrity.

### The `supported_versions` extension

TLS 1.3 hides inside the legacy `version` field of the ClientHello (set to 0x0303 like TLS 1.2) and uses a `supported_versions` extension (type 43) to advertise the actual version list: `0x0304` for TLS 1.3, `0x0303` for TLS 1.2. Servers that do not understand the extension fall back to TLS 1.2; servers that do understand reply with `0x0304` in their own ServerHello. This is the only way to negotiate TLS 1.3 vs 1.2 on the same wire format.

### Key schedule

After ECDHE produces the shared secret, TLS 1.3 derives six secrets via HKDF-Extract and HKDF-Expand (RFC 5869):

1. `early_secret = HKDF-Extract(salt=00..00, ikm=PSK)`
2. `derived_secret = HKDF-Expand-Label(early_secret, "derived", "", hash.length)`
3. `handshake_secret = HKDF-Extract(salt=derived_secret, ikm=ECDHE_shared)`
4. `client_handshake_traffic_secret = HKDF-Expand-Label(handshake_secret, "c hs traffic", ClientHello..server Finished, hash.length)`
5. `server_handshake_traffic_secret = HKDF-Expand-Label(handshake_secret, "s hs traffic", ClientHello..server Finished, hash.length)`
6. `master_secret = HKDF-Extract(salt=derived_from_handshake_secret, ikm=00..00)` (used after `Finished`)
7. `client_application_traffic_secret_0` and `server_application_traffic_secret_0` derived from `master_secret`

Each side derives its own `IV` and `key` for the AEAD from the corresponding traffic secret using `HKDF-Expand-Label`. The key schedule is the reason TLS 1.3 can do 0-RTT on resumption: the PSK fed into step 1 is bound to a previous `master_secret`, and the client's first flight can be encrypted immediately under a key derived from that PSK.

### What a Wireshark capture tells you

Open the capture and look for the first four records:

1. `ClientHello` (ContentType=22): record length ~500+ bytes, contains ~10–20 extensions.
2. `ServerHello` (ContentType=22): small (~100–200 bytes), includes `key_share` and `supported_versions`.
3. Then the server sends an `EncryptedExtensions` followed by `Certificate`, `CertificateVerify`, `Finished` — all wrapped in records that look like application data because TLS 1.3 reuses ContentType=23 for handshake after the server's `Finished`.

Wireshark display filters you will use:

- `tls.handshake.type == 1` — ClientHello
- `tls.handshake.type == 2` — ServerHello
- `tls.record.content_type == 22` — handshake records (only plaintext, before server Finished)
- `tls.record.content_type == 23` — application data (or post-handshake ciphertext in 1.3)
- `tls.alert` — alerts (fatal or warning)
- `tls.handshake.extensions.server_name` — SNI extension (what hostname the client is reaching)

## Build It

### Step 1 — Parse the record layer

```python
from main import parse_record, serialize_record

record = parse_record(bytes.fromhex("16 03 03 00 5a 01 00 00 56 ..."))
assert record["content_type"] == 22        # handshake
assert record["version"] == (3, 3)         # 0x0303 wire compat
assert record["length"] == 0x005a
```

`parse_record` returns a dict with `content_type`, `version`, `length`, and `fragment`. `serialize_record` wraps the inverse.

### Step 2 — Walk the handshake state machine

```python
from main import TLS13Client

client = TLS13Client(sni="example.com")
client_hello = client.send_client_hello()
server_hello, encrypted_flight = server_respond(client_hello)   # simulated
client.process_server_flight(server_hello, encrypted_flight)
assert client.handshake_complete
assert client.application_traffic_secret_client is not None
```

The simulator emits the bytes that a TLS 1.3 client would write and processes the server's response. It does not implement the AEAD itself (that requires a real AES-GCM primitive) but it tracks every state transition and reports the negotiated cipher suite, the key share, and the derived secrets.

### Step 3 — Decode a cipher suite ID

```python
from main import decode_cipher_suite

suite = decode_cipher_suite(0x1301)
assert suite.aead == "AES-128-GCM"
assert suite.hash == "SHA-256"
```

IANA cipher suite IDs above 0x1300 are TLS 1.3; below are TLS 1.2 or earlier.

### Step 4 — Verify a PCAP

```python
from main import parse_pcap_tls_records

records = parse_pcap_tls_records(open("capture.pcap", "rb").read())
for r in records[:5]:
    print(r["content_type"], r["version"], r["length"])
```

The parser reads a PCAP file (RFC 7422 linktype 1, Ethernet/IPv4/TCP frames stripped) and returns the TLS records. It is not a full PCAP parser — it expects a capture that is already decrypted or captures only the first plaintext flight.

### Step 5 — Replay and inspect

Use `openssl s_client -tls1_3 -connect example.com:443` and capture the handshake. Compare the cipher suite your client offered with what the server selected. If the server did not pick your first choice, look for the `supported_versions` and `key_share` extensions to see whether you offered a group it does not support.

## Use It

| Real system | TLS version | Cipher | Notes |
|---|---|---|---|
| Browsers (Chrome, Firefox, Safari) | TLS 1.3 only since 2022 | AES-128-GCM / ChaCha20-Poly1305 | Disable 1.0/1.1; default 1.3 with 1.2 fallback |
| curl / OpenSSL | TLS 1.3 by default | All 5 TLS 1.3 cipher suites | `-tls_max 1.2` for downgrade testing |
| nginx | TLS 1.3 (BoringSSL) | AES-128-GCM | `ssl_protocols TLSv1.2 TLSv1.3;` |
| HAProxy | TLS 1.3 (SSL/TLS stack) | AES-128-GCM / ChaCha20-Poly1305 | Stick-table for session resumption |
| Envoy / Istio | TLS 1.3 | AES-128-GCM | HTTP/2 + ALPN h2 |
| WireGuard | Not TLS; Noise IK pattern | ChaCha20-Poly1305 | UDP-based, custom protocol |
| QUIC (RFC 9001) | TLS 1.3 in QUIC framing | AES-128-GCM / ChaCha20-Poly1305 | Same AEAD; AEAD nonce uses packet number |
| IPsec (RFC 4303) | ESP with AES-GCM | AES-GCM | Different protocol, same AEAD |

## Ship It

The reusable artifact in `outputs/prompt-tls-detail.md` is a small `tls_inspector.py` exposing:

- `parse_record(data) -> dict` and `serialize_record(...) -> bytes`.
- `TLS13State` class that tracks `client_hello_sent`, `server_hello_received`, `encrypted_extensions`, `certificate`, `certificate_verify`, `server_finished`, `client_finished`, `application_traffic_secrets`.
- `decode_cipher_suite(id) -> CipherSuite` for the IANA registry.
- `cli.py` that reads a PCAP, prints the negotiated cipher suite, the key share group, the server certificate subject DN, and the alert history.

## Exercises

1. Capture `openssl s_client -connect example.com:443` with `tshark -i any -Y "tcp.port==443" -V`. Identify the ClientHello, ServerHello, EncryptedExtensions, and Finished records by content type and length. Where does the ServerHello end?
2. Use `openssl s_client -cipher "TLS_AES_256_GCM_SHA384"` and observe whether the server selects it. If not, what cipher does it pick, and what does the ClientHello say about why your first choice was rejected?
3. Hand-derive the `handshake_secret` for a real handshake given the client random, server random, ECDHE shared secret (X25519: `X25519(client_priv, server_pub)`), and the `HKDF-Extract(salt, ikm)` formula. Verify against Wireshark's "Handshake Secret" view.
4. Replay a captured ClientHello to a TLS 1.3 server. Does the server still accept it? Why does the server-bound `server_random` and signature in `CertificateVerify` protect against this?
5. Compare the ClientHello size between TLS 1.2 (no supported_versions extension) and TLS 1.3 (with supported_versions and key_share). How much larger? What extension grew the most?
6. Trace a full HTTP/2 connection that establishes via TLS 1.3: what is the ALPN protocol string in ClientHello? At what point does the client send the HTTP/2 connection preface? (Hint: only after `Finished`.)

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Record layer | "the framing" | 5-byte header (`type`, `version`, `length`) + fragment; TLS 1.3 reuses the 1.2 framing |
| Cipher suite | "the algorithm" | `TLS_{AEAD}_{HASH}` in 1.3; key exchange and auth are negotiated separately via extensions |
| supported_versions | "the version extension" | Extension type 43; tells the server "I can do TLS 1.3" while keeping the wire version at 0x0303 |
| key_share | "the DH group" | Extension type 51; client sends its ECDHE public value; server replies with its own |
| HKDF | "the key schedule" | RFC 5869 extract-and-expand; turns a shared secret into AEAD key + IV |
| Handshake secret | "the first derived key" | Bound to the ECDHE shared secret; used to encrypt handshake messages |
| Application traffic secret | "the data key" | Derived from master_secret; encrypts application data records |
| Finished | "the MAC at the end" | `HMAC(finished_key, transcript_hash)`; verifies the entire handshake |
| CertificateVerify | "the signature" | `sig(priv, 0x00*64 || context || transcript_hash)` per RFC 8446 §4.4.3 |
| 0-RTT | "early data" | Encrypted under a PSK bound to a previous session; replay-vulnerable |

## Further Reading

- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3 (Rescorla)
- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)
- RFC 5246 — The Transport Layer Security (TLS) Protocol Version 1.2 (legacy but still relevant for downgrade semantics)
- RFC 8448 — TLS 1.3 Example Trace (worked handshake transcripts)
- RFC 9001 — Using TLS to Secure QUIC (TLS 1.3 reused in QUIC framing)
- IANA TLS Cipher Suites registry (`iana.org/assignments/tls-parameters/tls-parameters.xhtml`)
- Cloudflare — *TLS 1.3: One Year Later* (deployment lessons from 2019)
- Rescorla, E. — *The Transport Layer Security (TLS) Protocol Version 1.3*, IETF Trust, 2018
- Wireshark TLS dissection documentation (`wiki.wireshark.org/TLS`)
