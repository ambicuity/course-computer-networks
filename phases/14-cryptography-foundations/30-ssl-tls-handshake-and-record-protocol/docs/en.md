# SSL/TLS handshake, premaster secret, and the record protocol

> Every time a browser shows the padlock, a TLS handshake just finished — typically 1-2 round trips of asymmetric cryptography to authenticate the server and to deliver a fresh 46-byte **premaster secret** to it, then a symmetric-cipher switch where every byte of the application stream is fragmented into 16 KB records, each one carrying a per-record nonce and a MAC (TLS 1.2) or AEAD tag (TLS 1.3). This lesson walks through the SSL 3.0/TLS 1.2 handshake that the chapter describes — ClientHello, ServerHello, Certificate, ServerHelloDone, ClientKeyExchange, ChangeCipherSpec, Finished — and then the **Record Protocol** that turns the resulting stream into ciphertext on the wire. You will see why a fresh premaster secret matters, how the master secret is derived from it via the PRF (TLS 1.2, RFC 5246), and why TLS 1.3 (RFC 8446) reduces the entire handshake to **one** round trip and then to **zero** round trips on a resumption. `code/main.py` is a stdlib-only TLS 1.2 simulator: it generates the four-byte TLS record header, walks the seven handshake messages, derives the master secret with the TLS 1.2 PRF, splits the key block into client_write_MAC_key / server_write_MAC_key / client_write_key / server_write_key / client_write_IV / server_write_IV, and demonstrates the record protocol's MAC-then-encrypt path.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Symmetric vs. asymmetric crypto, the AES-and-HMAC lesson, familiarity with the OSI transport/application layering
**Time:** ~75 minutes

## Learning Objectives

- Identify the seven messages of the TLS 1.2 handshake and what each one contributes to the connection.
- Explain how the 46-byte (TLS 1.2) or 32-byte (TLS 1.3) **premaster secret** is generated, encrypted to the server's public key, and turned into a master secret via the TLS PRF.
- Derive the 6-key key block from the master secret and walk through how the Record Protocol uses one of those keys per direction.
- Use `code/main.py` to simulate a TLS 1.2 handshake, build a Record-layer frame, and inspect the MAC-then-encrypt path.
- Distinguish TLS 1.2 (RFC 5246) from TLS 1.3 (RFC 8446) by handshake shape, key derivation, and the AEAD-only cipher suite restriction.
- Recognize downgrade attacks (POODLE, Bleichenbacher) and the role of the Finished message's verify-data in preventing them.

## The Problem

A user wants to log in to `bank.example.com`. Without TLS, the password would cross the Internet in cleartext, visible to every router in between. The user's browser needs three things before it can send a single byte of credentials: (1) proof that the server it's talking to actually owns the bank.example.com DNS name (and not some attacker who replied first), (2) a fresh shared secret that no one else can derive, and (3) a way to know that the bytes it sends and receives haven't been modified in transit.

The first requirement is **authentication** of the server — solved by the X.509 certificate chain and a digital signature on the handshake transcript. The second is **key exchange** — solved by the premaster secret, a 46-byte (TLS 1.2) or 32-byte (TLS 1.3) random blob the client generates and encrypts to the server's public key (RSA key transport) or that both sides contribute to via Diffie-Hellman (DHE / ECDHE). The third is **integrity** — solved by a MAC (TLS 1.2) or an AEAD tag (TLS 1.3) computed over each record, with a per-record nonce to prevent replay.

The trap most beginners fall into is conflating "the handshake" with "the encryption". The TLS handshake is a multi-message key-agreement protocol; the actual encryption happens in the **Record Protocol** that comes after. The handshake produces six keys (client/server × MAC/encryption/IV), the Record Protocol picks one pair per direction, and every application byte travels inside a record framed by a five-byte header. Forgetting the Record Protocol is why so many people "implement TLS" and end up with HTTPS that the browser still rejects.

## The Concept

### Where TLS sits in the stack

TLS — formally RFC 5246 (TLS 1.2) and RFC 8446 (TLS 1.3) — is a session-layer protocol that sits between the application (HTTP, IMAP, LDAP, …) and TCP. The four sub-protocols:

| Sub-protocol | RFC | Purpose |
|---|---|---|
| Handshake | RFC 5246 §7.4 / RFC 8446 §4 | Negotiate cipher suite, authenticate peers, derive keys |
| ChangeCipherSpec | RFC 5246 §7.1 | One-byte signal: "the next record I send uses the new cipher" |
| Alert | RFC 5246 §7.2 | Error and closure notifications (`close_notify`, `bad_record_mac`, …) |
| Application Data | RFC 5246 §7.3 | The encrypted stream (HTTP, IMAP, etc.) |

The first byte of every TLS record names the sub-protocol: `22` (Handshake), `20` (ChangeCipherSpec), `21` (Alert), `23` (Application Data). Wireshark's "decrypt TLS" feature reads the record header to dispatch.

### The seven TLS 1.2 handshake messages

The chapter describes the SSL 3.0 model; TLS 1.2 (RFC 5246) refines it but keeps the message order. The seven messages, in order, are:

| # | Message | Direction | Carries | State change |
|---|---|---|---|---|
| 1 | `ClientHello` | C → S | TLS version, 32-byte client random `R_A`, session ID, cipher suite list, compression methods, extensions | None — just offers |
| 2 | `ServerHello` | S → C | TLS version, 32-byte server random `R_B`, session ID, **chosen** cipher suite, compression, extensions | None — just chooses |
| 3 | `Certificate` | S → C | Server's X.509 chain, anchored to a root the client trusts | Server identity established |
| 4 | `ServerHelloDone` | S → C | (empty body) | Server says "that's my offer, your turn" |
| 5 | `ClientKeyExchange` | C → S | For RSA: 46-byte premaster secret `P` encrypted with the server's public key. For (EC)DHE: the client's DH public value. | Premaster secret in flight (RSA) or both DH halves exchanged (DHE) |
| 6 | `ChangeCipherSpec` | C → S, then S → C | One byte `0x01` | "I am now encrypting with the negotiated suite" |
| 7 | `Finished` | C → S, then S → C | 12-byte `verify_data` (TLS 1.2): PRF(master_secret, "client finished", hash(handshake_messages)) for the client, and analogously for the server | First encrypted record; proof of key possession |

`verify_data` is the most important message in the entire handshake. It is a MAC over **all** the previous handshake messages, computed with a key that depends on the master secret. If even one bit of the handshake was tampered with, the verify_data check fails and the connection is torn down with a `decrypt_error` alert. This is the property that defeats active downgrade attacks: an attacker who can rewrite a `ServerHello` to demote the cipher suite to SSL 3.0 also has to rewrite all the subsequent Finished messages, and they cannot, because they do not have the master secret.

### How the premaster secret becomes a master secret

The 46-byte premaster secret `P` is generated by the client: in TLS 1.2 RSA key transport, it is `version || 46_random_bytes` (the first two bytes are the negotiated version, the remaining 46 are random). For DHE/ECDHE, there is no `P` per se — the DH exchange itself produces the shared secret. Either way, the 48-byte **master secret** is:

```
master_secret = PRF(premaster_secret, "master secret",
                    client_random || server_random)[0..48]
```

`PRF(secret, label, seed)` in TLS 1.2 is built from HMAC-SHA-256 (or HMAC-MD5 + HMAC-SHA-1 concatenated, for legacy). The label is an ASCII string with no trailing NUL.

### The key block: six keys from one master secret

The PRF is then used a second time to produce the **key block**:

```
key_block = PRF(master_secret, "key expansion",
                server_random || client_random)
```

The key block is split left-to-right into the six per-direction keys, in the order the negotiated cipher suite requires. For `TLS_RSA_WITH_AES_128_CBC_SHA` (TLS 1.2, RSA key transport, AES-128-CBC + HMAC-SHA-1):

| Slice | Size | Name | Direction |
|---|---|---|---|
| `key_block[0:20]` | 20 B | `client_write_MAC_key` | Client → Server MAC |
| `key_block[20:40]` | 20 B | `server_write_MAC_key` | Server → Client MAC |
| `key_block[40:56]` | 16 B | `client_write_key` | Client → Server AES-128 |
| `key_block[56:72]` | 16 B | `server_write_key` | Server → Client AES-128 |
| `key_block[72:88]` | 16 B | `client_write_IV` | Client → Server CBC IV |
| `key_block[88:104]` | 16 B | `server_write_IV` | Server → Client CBC IV |

Other cipher suites have different slice sizes (AES-256 needs 32 B for the key, SHA-256 needs 32 B for the MAC), but the order is always the same. TLS 1.3 (RFC 8446) replaces this with `HKDF-Expand-Label` and a separate traffic secret per direction; the six-key model is a TLS 1.2 idiom.

### The Record Protocol, byte for byte

Every TLS record has the same five-byte header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Content      |    Version     |        Length (16)          |
|  type (8)     | major (8) | minor |                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Fragment (0 to 2^14 bytes, 16 KB)                   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Meaning |
|---|---|---|
| Content type | 8 bits | `20` ChangeCipherSpec, `21` Alert, `22` Handshake, `23` Application Data |
| Version | 16 bits | `0x0301` (TLS 1.0), `0x0302` (TLS 1.1), `0x0303` (TLS 1.2), `0x0304` (TLS 1.3 — but only in the *record layer*; the handshake layer still uses 0x0303 for compatibility) |
| Length | 16 bits | Length of the fragment that follows, **excluding** the 5-byte header |
| Fragment | 0–16384 B | The payload (compressed, MACed, encrypted — see cipher suite) |

The maximum fragment is 16 KB. The Application Data stream is just `opaque_content[TLSCompressed][TLSCiphertext]`; the MAC and the encryption are applied to the compressed fragment, not to the original Application Data.

### MAC-then-encrypt vs. encrypt-then-MAC vs. AEAD

TLS 1.0 and 1.1 use the **MAC-then-encrypt** construction, which has been the source of several well-known attacks (BEAST, Lucky 13). The construction in TLS 1.2 with a CBC cipher suite is:

```
seq_num = 64-bit record sequence counter (starts at 0, increments per record)
mac     = HMAC(mac_key, seq_num || type || version || compress(plaintext))
padding = PKCS#7 padding to AES block (16 B)
cipher  = AES-CBC-enc(enc_key, IV, mac || pad || plaintext)  # for some suites; varies
```

TLS 1.3 (RFC 8446) requires an **AEAD** cipher suite — AES-GCM, ChaCha20-Poly1305, AES-CCM — and uses encrypt-then-MAC semantics (well, the AEAD does both at once, so the order is "AEAD-encrypt"). This eliminates the entire class of padding-oracle attacks that plagued CBC-mode TLS 1.2.

### What TLS 1.3 changes

RFC 8446 (TLS 1.3, finalized August 2018) is a major revision. The differences from TLS 1.2 that matter operationally:

| Property | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Handshake round trips | 2 (full handshake), 1 (resumption) | 1 (full handshake), 0 (resumption with PSK + 0-RTT data) |
| Cipher suites | ~37 named suites including RC4, 3DES, CBC, AES-GCM, ChaCha20 | 5 suites, all AEAD: TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256, TLS_AES_128_CCM_SHA256, TLS_AES_128_CCM_8_SHA256 |
| Key derivation | Ad-hoc `key_block` slice | `HKDF-Extract` + `HKDF-Expand-Label` traffic secrets per direction |
| Static RSA key transport | Allowed | **Removed** (only DHE/ECDHE) |
| ChangeCipherSpec | Yes | Removed (replaced by implicit switch in the encrypted handshake) |
| Renegotiation | Indeterminate | Limited and explicit |
| Downgrade protection | None in protocol | `tls13_downgrade` sentinel in ServerHello.random last 8 bytes |

The static-RSA removal is the most consequential security change: it closes the Bleichenbacher / ROBOT family of attacks that exploit the RSA padding-oracle when the server decrypts the premaster secret. TLS 1.3 also has built-in downgrade detection: if a TLS 1.3-capable client negotiates TLS 1.2, the last 8 bytes of `ServerHello.random` are set to a sentinel value the client can verify post-handshake.

### Worked example: key block for one session

Inputs:
- `R_A` (client random): `0xa1a1…` (32 bytes)
- `R_B` (server random): `0xb2b2…` (32 bytes)
- Premaster secret `P`: 46 random bytes (TLS 1.2 RSA)
- Negotiated suite: `TLS_RSA_WITH_AES_128_CBC_SHA`

Step 1:
```
master_secret = PRF(P, "master secret", R_A || R_B)
             = 48 bytes
```

Step 2:
```
key_block = PRF(master_secret, "key expansion", R_B || R_A)
          = 104 bytes for AES-128-CBC + HMAC-SHA-1
```

Step 3 (slice the block):
```
client_write_MAC_key  = key_block[0:20]
server_write_MAC_key  = key_block[20:40]
client_write_key      = key_block[40:56]
server_write_key      = key_block[56:72]
client_write_IV       = key_block[72:88]
server_write_IV       = key_block[88:104]
```

This is exactly what `code/main.py` computes, and you can compare the printed values to a known-good `keylog.txt` line that an instrumented browser emits: `CLIENT_RANDOM <R_A_hex> <master_secret_hex>`. (Browsers do not normally log the key block itself, only the master secret and client random — Wireshark reconstructs the rest.)

### Failure modes you can recognize

| Symptom | Likely cause | What you see |
|---|---|---|
| Handshake hangs after `ServerHello` | Client does not trust the server's certificate chain (self-signed, expired, wrong CN/SAN) | Browser shows `NET::ERR_CERT_AUTHORITY_INVALID` or `SSL_ERROR_UNTRUSTED_CERT` |
| `bad_record_mac` alert after `Finished` | MTU problem or middlebox modification of records (the "TLS middlebox" failure mode) | Connection drops after 1-3 KB of traffic; `bad_record_mac` in the alert |
| POODLE-style downgrade to SSL 3.0 | Attacker forces the client to negotiate SSL 3.0; CBC padding oracle is exploitable | `decrypt_error` alerts and re-handshakes; fixed by disabling SSL 3.0 |
| Bleichenbacher / ROBOT attack | Server uses PKCS#1 v1.5 RSA decryption with a padding oracle | Latency differences on the server's response to malformed premaster secrets |
| "Handshake failed" with no alert | Version negotiation failed (no common version) | Server supports only TLS 1.0; client requires TLS 1.2+ |
| 0-RTT replay | TLS 1.3 resumption data is replayed by a network attacker | Some servers accept it twice; only safe for *idempotent* GETs |

## Build It

1. Run `code/main.py` and confirm:
   - The premaster secret is 48 bytes (2-byte version + 46 random bytes, the TLS 1.2 RSA key-transport shape).
   - The master secret is 48 bytes, derived from `PRF(P, "master secret", R_A || R_B)`.
   - The key block is 104 bytes (the slice sizes for AES-128-CBC + HMAC-SHA-1).
2. The simulator walks the seven handshake messages. For each, it prints:
   - the TLS record header (5 bytes: type, version, length),
   - the handshake message header (4 bytes: type, 3-byte length),
   - the body fields (client random, server random, chosen cipher suite, encrypted premaster, verify_data, …).
3. The MAC-then-encrypt path is exercised on a synthetic HTTP request: the simulator computes `MAC = HMAC-SHA-1(mac_key, seq || type || version || compressed)`, pads the result to 16 bytes, encrypts with an illustrative AES-CBC (XOR-keystream) stand-in, and prints the 5-byte record header followed by the ciphertext.
4. Run the TLS 1.3 mode (set `tls13 = True`): the simulator collapses the handshake to 2 round trips, derives the traffic secret via `HKDF-Expand-Label(master_secret, "c hs traffic", ClientHello…ServerHello)`, and produces a single AEAD-encrypted record (the Finished).
5. Run a downgrade attack simulation: set `force_version = 0x0300` (SSL 3.0). The simulator still produces a successful "handshake" with the verify_data check passing, demonstrating why TLS 1.3 added the `tls13_downgrade` sentinel.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the record header | Print first 5 bytes of any record | `22 03 03 00 XX` for a 1.2 Handshake record; `23 03 03 00 XX` for Application Data |
| Derive the master secret | Compare `main.py` output to a `keylog.txt` entry | The 48-byte master secret hex matches `CLIENT_RANDOM <R_A_hex> <ms_hex>` |
| Split the key block | Compare the simulator's six keys to a Wireshark TLS debug log | Each of the 6 slices matches the values in the Security Association record |
| Inspect the Finished | `verify_data` from `main.py` | 12-byte hex matches Wireshark's "Verify Data" field for the same `R_A`, `R_B`, and master secret |
| Detect a downgrade | Re-run with `force_version=0x0300` | Simulator produces a "successful" handshake that a real TLS 1.3 client would reject via the `tls13_downgrade` sentinel |
| Compare to TLS 1.3 | Set `tls13=True` | The handshake collapses to 2 round trips, no `Certificate` is sent in cleartext, AEAD tag replaces the explicit MAC |

## Ship It

Produce one reusable artifact under `outputs/`:

- A Wireshark capture of a real TLS 1.2 handshake (`tls12.pcapng`) with the seven handshake messages annotated, the master secret overlaid on the capture (from `keylog.txt`), and the six key-block slices printed next to the Security Association.
- A reference key-derivation worksheet (`key-derivation.md`) with the PRF inputs and outputs for one session, so a reader can hand-verify a handshake from a packet capture.
- A downgrade-detection cheat sheet mapping the failure modes in the table above to the corresponding alert message and the browser UI string (`NET::ERR_CERT_DATE_INVALID`, `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`, etc.).

Start from `outputs/prompt-ssl-tls-handshake-and-record-protocol.md`.

## Exercises

1. Compute the on-wire size of one 1.5 KB HTTP request sent over TLS 1.2 with AES-128-CBC + HMAC-SHA-1. Show the contributions: 5-byte record header, MAC (20 B), padding (up to 16 B), ciphertext. Why is the record's "Length" field limited to 2^14 = 16384 bytes?
2. Trace the verify_data computation. Which messages are covered by it? What is the consequence of an attacker re-ordering the ClientHello and ServerHello before the Finished is computed?
3. The premaster secret in TLS 1.2 RSA key transport is 46 bytes of random data prefixed with the 2-byte client-hello version. Why include the version bytes, and what attack is prevented by their presence?
4. The key block is the same length for the client and server (they share the master secret), but each direction uses a different slice. Walk through what happens if the client and server mistakenly use the same MAC key for both directions.
5. TLS 1.3 removes static RSA. What class of attacks is closed by this removal? Why does the (EC)DHE-only requirement in TLS 1.3 also give you Perfect Forward Secrecy by default?
6. In TLS 1.3, the `server_hello` is encrypted under a traffic secret derived from `(EC)DHE`. Sketch how 0-RTT data works and explain the replay trade-off (the 0-RTT key is bound to the client random, but the server has no nonce to reject duplicates).
7. Why does the TLS Record Protocol use a per-record 64-bit sequence number, and what would go wrong if it were omitted from the MAC input?
8. In Wireshark, set `(Pre)-Master-Secret log filename` to a `keylog.txt` produced by a browser. Which fields in the dissected handshake are decrypted as a result, and which remain encrypted?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| TLS | "the S in HTTPS" | RFC 5246 (1.2) / RFC 8446 (1.3) — Transport Layer Security |
| SSL | "the old name" | Netscape's Secure Sockets Layer; SSL 2.0 and 3.0 are deprecated; TLS 1.0 is "SSL 3.1" |
| Handshake | "the part that sets up the keys" | The sub-protocol that negotiates the cipher suite, authenticates peers, and derives the master secret |
| Record | "the encrypted envelope" | A 5-byte header + up to 16 KB of (compressed, MACed, encrypted) payload |
| Premaster secret | "what the client sends to the server" | A 46-byte (TLS 1.2) or 32-byte (TLS 1.3) random blob, RSA-encrypted to the server's public key in TLS 1.2 key transport |
| Master secret | "what the keys are derived from" | 48-byte secret; `PRF(P, "master secret", R_A || R_B)` |
| Key block | "the six per-direction keys" | Output of `PRF(master_secret, "key expansion", R_B || R_A)`, sliced into the six keys |
| PRF | "the pseudo-random function" | TLS 1.2's HMAC-based PRF, used for both master-secret derivation and key expansion |
| verify_data | "the proof of key possession" | The 12-byte (TLS 1.2) or 32-byte (TLS 1.3) MAC over the handshake transcript |
| AEAD | "encryption + authentication in one" | Authenticated Encryption with Associated Data: AES-GCM, ChaCha20-Poly1305, AES-CCM |
| 0-RTT | "the zero-round-trip data" | TLS 1.3 resumption data sent in the first flight; safe only for idempotent requests |
| HKDF | "the TLS 1.3 KDF" | HMAC-based Key Derivation Function (RFC 5869) used to derive traffic secrets |
| Bleichenbacher | "the 1998 RSA padding attack" | Exploits PKCS#1 v1.5 RSA decryption to recover the premaster secret; closed in TLS 1.3 |
| POODLE | "the SSL 3.0 downgrade attack" | Forces SSL 3.0 negotiation to exploit CBC padding; fixed by disabling SSL 3.0 |
| BEAST | "the 2011 CBC attack" | Exploits TLS 1.0 CBC IV predictability; fixed in TLS 1.1 with explicit per-record IVs |
| Perfect Forward Secrecy | "past sessions stay secret" | Property of (EC)DHE: compromising long-term keys does not retroactively decrypt recorded sessions |

## Further Reading

- RFC 5246 — The Transport Layer Security (TLS) Protocol Version 1.2
- RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3
- RFC 4347 — Datagram Transport Layer Security (DTLS) — the UDP analog
- RFC 4346 — TLS 1.1 (obsolete, superseded by RFC 5246)
- RFC 6101 — The Secure Sockets Layer (SSL) Protocol Version 3.0 (historical)
- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF) — used in TLS 1.3
- RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm
- Bleichenbacher (1998) — "Chosen Ciphertext Attacks Against Protocols Based on the RSA Encryption Standard PKCS #1"
- Möller, Duong, Kotowicz (2014) — "This POODLE Bites: Exploiting the SSL 3.0 Fallback"
- Rizzo, Duong (2011) — "Here Come The XOR Ninjas" — BEAST
- Rescorla (2018) — *SSL and TLS: Designing and Building Secure Systems*, Addison-Wesley
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — SSL/TLS section
