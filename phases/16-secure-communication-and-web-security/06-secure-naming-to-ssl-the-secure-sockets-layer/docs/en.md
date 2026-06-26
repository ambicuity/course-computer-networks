# Secure Naming to SSL-the Secure Sockets Layer

> Secure naming starts with DNS: Trudy can poison Alice's ISP DNS cache by forging a reply with her own IP address (42.9.9.9) for bob.com, then intercept all of Alice's traffic to "Bob." DNSsec (RFC 2535) fixes this by signing every Resource Record Set (RRSet) with the zone's private key — clients verify the SIG record with the zone's public key, and a forged RRSet fails verification. The SSL (Secure Sockets Layer) protocol, introduced by Netscape in 1995, builds secure connections in four steps: parameter negotiation (client sends nonce R_A and preferences; server chooses algorithms and sends nonce R_B), server authentication via X.509 certificate chain (browsers come preloaded with about 100 root public keys), secret key exchange (client sends a random 384-bit premaster key encrypted with the server's public key), and data transport (fragment up to 16KB, compress, add MAC with agreed hash, encrypt with agreed symmetric cipher). TLS (Transport Layer Security, RFC 5246) is the IETF successor to SSL 3 — small but incompatible changes to key derivation, stronger cipher suites (AES), and fallback negotiation. SSL sits between the application and transport layers; HTTP over SSL is HTTPS (port 443).

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Lesson 05 (Threats); Phase 12 DNS and HTTP
**Time:** ~75 minutes

## Learning Objectives

- Explain the DNS spoofing attack: how Trudy poisons a DNS cache by racing a forged reply with the legitimate one, and why 16-bit DNS query IDs make guessing feasible.
- Describe DNSsec: RRSet signing with zone private keys, KEY and SIG record types, offline key storage, and how it defeats poisoned caches.
- Walk through the SSL connection-establishment subprotocol: the nine messages from client hello to finished.
- Explain how the 384-bit premaster key, combined with both nonces, derives the session key for encryption.
- Describe the SSL data transport subprotocol: fragment (up to 16KB), compress, MAC, encrypt, header.
- Contrast SSL 3 with TLS (RFC 5246): key derivation changes, cipher suite differences, and fallback negotiation.

## The Problem

Alice wants to visit Bob's web site. She types his URL and a page appears — but is it really Bob's? Trudy might intercept Alice's traffic, fetch Bob's page herself, modify it (slash prices, trick Alice into entering her credit card), and return the fake page. Active wiretapping works but requires tapping a line. Easier: crack DNS, replace Bob's IP address with Trudy's, and intercept from the comfort of her living room. Even with correct naming, Alice's traffic to Bob traverses dozens of routers that can read it. The engineer needs secure naming (DNSsec) and secure connections (SSL/TLS) together.

## The Concept

### DNS Spoofing

The normal flow: Alice asks DNS for Bob's IP address, gets 36.1.2.3, sends HTTP GET to Bob, and receives his page. After Trudy modifies Bob's DNS record to contain her IP (42.9.9.9), Alice's DNS lookup returns Trudy's address — all traffic goes to Trudy, who can run a man-in-the-middle attack without tapping any phone line.

Trudy's attack steps:

| Step | Trudy's action | DNS server state |
|------|----------------|------------------|
| 1 | Register trudy-the-intruder.com (IP 42.9.9.9) and set up a DNS server | — |
| 2 | Ask Alice's ISP to look up foobar.trudy-the-intruder.com (forces ISP to learn Trudy's DNS server) | Trudy's DNS server cached |
| 3 | Ask Alice's ISP for www.trudy-the-intruder.com (to learn the ISP's next DNS query sequence number) | ISP sends query with seq = n |
| 4 | Immediately ask ISP to look up bob.com | ISP queries the com TLD server with seq = n+1 |
| 5 | Forge a reply: "bob.com is 42.9.9.9" with seq = n+1 (and n+2, n+3, ... as backup) | If forged reply arrives first, it is cached |
| 6 | Real reply from TLD arrives — rejected (no outstanding query) | Poisoned cache: bob.com = 42.9.9.9 |

DNS query IDs are only 16 bits — a computer can guess all of them easily. Random IDs help, but every time one hole is plugged, another turns up.

### DNSsec — Secure DNS

DNSsec (RFC 2535) makes DNS fundamentally secure using public-key cryptography. Every DNS zone has a public/private key pair. All information sent by a DNS server is signed with the originating zone's private key, so the receiver can verify authenticity.

DNSsec offers three services: proof of data origin, public key distribution, and transaction/request authentication. Secrecy is not offered — all DNS information is considered public.

| Record type | Purpose |
|-------------|---------|
| KEY | Public key of a zone, user, host, or principal; algorithm and protocol fields |
| SIG | Signed hash of an RRSet (per algorithm in KEY record); validity times, signer name |
| CERT | Optional: stores X.509 certificates (some want DNS to become a PKI) |

The zone's private key can be kept offline: once or twice a day, the zone database is manually transported to a disconnected machine, RRSets are signed, and SIG records are returned. This reduces electronic security to physical security (a CD-ROM in a safe). Records increase tenfold in size due to signatures, but no cryptography happens on the fly at query time.

### SSL — The Secure Sockets Layer

SSL builds a secure connection between two sockets with four properties: parameter negotiation, server authentication, secret communication, and data integrity protection. It sits between the application and transport layers — HTTP over SSL is HTTPS (port 443 instead of 80).

### SSL connection-establishment subprotocol (9 messages)

| Msg | From -> To | Content |
|-----|-----------|---------|
| 1 | Client -> Server | SSL version, preferences (compression, crypto algorithms), nonce R_A |
| 2 | Server -> Client | Chosen algorithms, nonce R_B |
| 3 | Server -> Client | X.509 certificate chain (server's public key; chain back to a preloaded root) |
| 4 | Server -> Client | Server done |
| 5 | Client -> Server | E_B(premaster key) — random 384-bit premaster encrypted with server's public key |
| 6 | Client -> Server | Change cipher |
| 7 | Client -> Server | Finished |
| 8 | Server -> Client | Change cipher |
| 9 | Server -> Client | Finished |

After message 5, both sides compute the session key from the premaster key combined with both nonces in a complex way. The strongest cipher suite uses triple DES with three separate keys for encryption and SHA-1 for integrity. For ordinary e-commerce, RC4 with a 128-bit key and MD5 is used. RC4 has weak keys, so browsers should be configured for triple DES + SHA-1, or upgraded to TLS.

### SSL data-transport subprotocol

| Step | Operation |
|------|-----------|
| 1 | Fragment message into units up to 16 KB |
| 2 | Compress each unit (if enabled) |
| 3 | Concatenate secret key with compressed text, hash with agreed algorithm (usually MD5) -> MAC |
| 4 | Append MAC to compressed fragment |
| 5 | Encrypt with agreed symmetric algorithm (usually RC4 XOR) |
| 6 | Attach fragment header and transmit over TCP |

### TLS — Transport Layer Security

In 1996, Netscape turned SSL over to IETF. The result was TLS (RFC 5246), built on SSL 3 with small but incompatible changes: the session key derivation from premaster key and nonces was changed to make the key stronger. TLS 1.2 (August 2008) adds support for stronger cipher suites (notably AES). Most browsers implement both protocols with TLS falling back to SSL during negotiation — "SSL/TLS."

### SSL vs TLS

| Aspect | SSL 3 | TLS 1.2 |
|--------|-------|---------|
| Standardizer | Netscape (proprietary) | IETF (RFC 5246) |
| Key derivation | Original scheme | Changed for stronger keys |
| Cipher suites | triple DES, RC4 | Adds AES-128/256 |
| Interoperability | Cannot interoperate with TLS | Falls back to SSL 3 |
| Port | 443 (HTTPS) | 443 (HTTPS) |

### Failure modes

- **DNS cache poisoning**: forged reply races the real one; 16-bit query IDs are guessable.
- **No DNSsec deployment**: many DNS servers are still vulnerable to spoofing.
- **Weak cipher suites**: RC4 has weak keys; MD5 has collision vulnerabilities.
- **Certificate chain not verified**: if the client does not check the chain back to a preloaded root, a self-signed cert is accepted.
- **SSL/TLS interoperability**: small incompatibilities mean fallback to SSL 3, which has known weaknesses.
- **Premaster key interception**: if the server's private key is compromised, all past sessions recorded with that key are decryptable (no forward secrecy in basic SSL).

`code/main.py` simulates the DNS cache-poisoning attack and the SSL handshake; `assets/secure-naming-to-ssl-the-secure-sockets-layer.svg` diagrams both flows.

## Build It

1. Run `python3 code/main.py` to see the DNS cache-poisoning attack and the SSL handshake.
2. Examine the DNSsec verification path: a forged RRSet fails the SIG check.
3. Run the SSL handshake simulation: nine messages from client hello to finished.
4. Trigger the cipher-suite comparison: triple DES + SHA-1 vs RC4 + MD5.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify DNSsec | DNS response with RRSIG record; validation result | RRSIG validates against zone KEY; AD bit set in response |
| Detect DNS spoofing | DNS cache showing unexpected IP for a domain | Cached IP does not match the authoritative zone's signed record |
| Verify SSL handshake | Wireshark TLS capture with ClientHello, ServerHello, Certificate, KeyExchange | All nine messages present; certificate chain validates to a root CA |
| Audit cipher suite | openssl s_client output showing negotiated cipher | AES-256-GCM or triple DES; no RC4; no export-grade keys |

## Ship It

Create one artifact under `outputs/`:

- A DNSsec deployment checklist (zone signing, key offline storage, client validation).
- An SSL/TLS handshake trace annotation guide (nine messages).
- A cipher-suite hardening runbook (disable RC4, enable AES, enforce TLS 1.2+).

Start with [`outputs/prompt-secure-naming-to-ssl-the-secure-sockets-layer.md`](../outputs/prompt-secure-naming-to-ssl-the-secure-sockets-layer.md).

## Exercises

1. Walk through Trudy's DNS cache-poisoning attack step by step. Why does she need to learn the ISP's next DNS query sequence number? Why are 16-bit IDs insufficient?
2. DNSsec signs RRSets with the zone's private key. How does offline key storage work, and why does it reduce electronic security to physical security?
3. In the SSL handshake, the client sends a 384-bit premaster key encrypted with the server's public key. How is the actual session key derived? Why are both nonces needed?
4. Compare SSL 3 and TLS 1.2: what changed in key derivation, what cipher suites were added, and why can they not interoperate directly?
5. The SSL data-transport subprotocol fragments into 16KB units, compresses, MACs, and encrypts. Why is the MAC computed over the compressed data plus a secret key, not just the plaintext?
6. A browser is configured to use RC4 with 128-bit keys and MD5. Why is this considered shaky? What configuration should replace it?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DNS spoofing | "cache poisoning" | Forging a DNS reply so the ISP caches Trudy's IP for bob.com; enables MITM without wiretapping |
| DNSsec | "signed DNS" | DNS security (RFC 2535): zones sign RRSets with private keys; clients verify SIG records with public keys |
| RRSet | "record set" | Resource Record Set — all records with same name/class/type, hashed and signed as a unit |
| SSL | "the web security one" | Secure Sockets Layer — Netscape 1995; sits between app and transport; HTTPS = HTTP over SSL |
| Premaster key | "the secret seed" | Random 384-bit value sent encrypted with server's public key; session key derived from it + both nonces |
| TLS | "the IETF version" | Transport Layer Security (RFC 5246) — IETF successor to SSL 3; stronger key derivation, AES support |
| X.509 chain | "cert chain" | Sequence of certificates from server's cert back to a preloaded root CA (~100 in a browser) |

## Further Reading

- RFC 2535 — Domain Name System Security Extensions (DNSsec)
- RFC 5246 — TLS 1.2 (Transport Layer Security)
- Fluhrer, Mantin, and Shamir (2001) — Weaknesses in RC4 Key Scheduling
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 sections 8.9.2 and 8.9.3
