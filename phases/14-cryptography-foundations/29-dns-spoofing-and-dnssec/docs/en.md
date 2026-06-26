# DNS spoofing, cache poisoning, and the DNSSEC chain of trust

> The Domain Name System maps names like www.example.com to IP addresses, but every DNS response is unauthenticated by default. A resolver that asks 8.8.8.8 for the A record of evil.com has no way to verify that the answer came from the authoritative server, and a man-in-the-middle on the path between the resolver and the authoritative server can inject a forged A record with the resolver's source port and transaction ID both guessed correctly. The classic Kaminsky attack (2008) exploited this: by sending many randomized queries and listening for the matching forged response, an attacker could poison a resolver's cache for a target domain in seconds. DNSSEC (RFC 4033, 4034, 4035, 5155) closes the gap by signing every RRset with the zone's private key (typically ECDSA P-256 or RSA-2048) and chaining the public keys through a parent zone's DS record. The root zone is signed by the trusted KSK held by VeriSign and ICANN, and resolvers configured with a trust anchor can validate every signed response from root to TLD to SLD. The lesson ships a stdlib-only simulator that demonstrates cache poisoning, walks the DNSSEC chain-of-trust validation, and shows the difference between validated and bogus answers.

**Type:** Learn
**Languages:** Python (stdlib only), dig
**Prerequisites:** Phase 14 lessons 01-09, Chapter 8.6
**Time:** ~75 minutes

## Learning Objectives

- Trace a DNS query from a stub resolver through a recursive resolver to the authoritative server, and identify the four pieces of metadata a resolver must match: transaction ID, source port, question section, and answer section.
- Construct a Kaminsky-style cache poisoning attack where the attacker races the authoritative server's response and wins by guessing the transaction ID space.
- Implement a DNSSEC validation chain: verify an RRset's RRSIG with the zone's DNSKEY, verify the DNSKEY against the parent's DS record, and walk the chain up to a configured trust anchor.
- Identify the cost of DNSSEC: increased query latency (DS queries), larger responses (signatures are 512+ bytes), and operational complexity (key rollovers with RFC 5011 timers).
- Use a real dig command to inspect a signed zone (e.g., dig +dnssec www.cloudflare.com) and read the RRSIG and DS records.

## The Problem

DNS was designed in 1983 when the internet was small and trusted. The protocol has no authentication: a UDP packet with the right transaction ID and source port is accepted as the answer. Cache poisoning exploits this: an attacker who can guess or race these two 16-bit values can inject a fake A record into a resolver's cache, and every subsequent query for that name (until TTL expires) returns the attacker's IP. The Kaminsky attack (2008) made cache poisoning trivially automatable: instead of guessing the ID for a single name, the attacker randomizes the queried name and forces the resolver to re-query, giving the attacker many shots at the ID/port space.

DNSSEC solves this by signing every RRset. Each zone has a Key Signing Key (KSK) and a Zone Signing Key (ZSK); the KSK signs the DNSKEY RRset, and the ZSK signs all other RRsets. The parent's DS (Delegation Signer) record contains a hash of the child's KSK, chaining trust from the root down. With DNSSEC validation enabled, a resolver refuses to accept unsigned or invalidly-signed responses, and cache poisoning requires breaking ECDSA or RSA — which is the actual security goal.

## The Concept

Source: chapters/chapter-08-network-security.md, section 8.6 (DNS security). The companion diagram is assets/dns-spoofing-and-dnssec.svg.

### The DNS resolution path

| Step | From | To | Wire | What |
|------|------|----|------|------|
| 1 | Stub resolver | Recursive resolver | A? www.example.com | Stub asks its configured resolver |
| 2 | Recursive | Root server | Referral query for .com | Resolver walks the delegation chain |
| 3 | Root | Recursive | NS referral to .com TLD | Root returns the .com nameservers |
| 4 | Recursive | .com TLD | Referral for example.com | TLD returns the example.com nameservers |
| 5 | Recursive | example.com auth | A query | Authoritative returns the A record |
| 6 | Recursive | Stub | A record + TTL | Stub uses the answer |

The recursive resolver caches the answer for the TTL (typically 300-86400 seconds). During that window, every stub that asks the resolver gets the cached answer.

### Cache poisoning mechanics

The attacker's goal: inject a fake A record for www.evil.com into the resolver's cache. The attacker needs to match four fields in the response:
- Transaction ID (16 bits, 65536 candidates)
- Source port (16 bits, 65536 candidates)
- Question section (must match the query)
- Answer section (the forged A record)

Naive attack: guess the ID. 1/65536 chance per guess; with 1000 guesses per second, ~65 seconds to succeed. The Kaminsky trick: query for a random subdomain (12345.evil.com), forcing a fresh delegation, and race the response. The attacker can fire thousands of guesses in parallel because the resolver re-queries every time.

### Defenses before DNSSEC

Three partial defenses exist:
- Source port randomisation (per RFC 5452): adds 16 bits of entropy to the guess.
- 0x20 encoding (upper/lower case in the name): adds ~5 bits per label.
- Cookie-based identification (RFC 7873): adds 32+ bits but requires server support.

Kaminsky's attack reduces the effective entropy from 32+5+5 bits to 16 bits (the ID alone), because the question section is randomized by the attacker. Without DNSSEC, the only complete defense is a much larger ID space — which DNSSEC effectively provides by requiring a signature that is computationally infeasible to forge.

### DNSSEC chain of trust

DNSSEC signs every RRset and chains keys through parent zones:

| Layer | What is signed | By what key | Verified by |
|---|---|---|---|
| Leaf RRset (e.g., A record) | A, AAAA, MX, etc. | ZSK of the zone | DNSKEY of the zone (RRSIG) |
| DNSKEY RRset | DNSKEY records themselves | KSK of the zone | DS record in parent zone |
| DS record | Delegation Signer hash | ZSK of parent | DNSKEY of parent (RRSIG) |
| Root DNSKEY | Root DNSKEY | Root KSK | Trust anchor (configured out-of-band) |

Validation is recursive: a validating resolver starts at the trust anchor (the root KSK), verifies the root's DNSKEY via the trust anchor, then verifies TLD DNSKEYs via DS records in the root, and so on down to the leaf. Each step uses a digital signature (RSA, ECDSA, or Ed25519) that is computationally infeasible to forge.

### DNSSEC record types

- DNSKEY: a zone's public key (ZSK or KSK).
- RRSIG: a signature over an RRset, with algorithm, inception, and expiration.
- DS: Delegation Signer; a SHA-256 hash of the child zone's KSK.
- NSEC / NSEC3: authenticated denial of existence; proves a name does not exist.

### Operational realities

DNSSEC has costs:
- Every signed RRset carries an RRSIG; DNSSEC responses are ~2-4x larger than unsigned.
- Key rollovers (KSK and ZSK) require careful timing (pre-publish, double-sign, RFC 5011 timers).
- Some middleboxes and firewalls mishandle large DNS responses, causing validation failures.
- DNSSEC does not provide confidentiality — use DoT (RFC 7858) or DoH (RFC 8484) for that.

## Build It

code/main.py implements a simplified DNS resolver with cache poisoning demo and DNSSEC validation. Work through it in this order:

1. Run python3 main.py and read the import block. The simulator uses hmac for response authentication and dataclasses for state.
2. Read Resolver: holds a cache, an authoritative-server interface, and a DNSSEC trust anchor.
3. Read scenario_poisoning: Trudy races the authoritative server's response with a forged A record. The naive resolver accepts the first matching response.
4. Read scenario_dnssec_validates: every RRset has an RRSIG; the resolver verifies the signature before caching. Trudy's forged response has no valid signature and is rejected.
5. Read scenario_chain_of_trust: walk the chain root -> TLD -> SLD -> leaf and verify each signature.
6. Run the main() scenarios: poisoning (succeeds against naive), DNSSEC validation (blocks poisoning), chain-of-trust walk.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Issue a query | resolver.query(name, qtype) returns a ResourceRecord | Answer has matching ID, port, question section |
| Detect poisoning | First matching response is from a non-authoritative source | Resolver drops the answer and re-queries (or with DNSSEC, rejects the signature) |
| Validate RRSIG | verify_rrsig(rrset, sig, dnskey) returns True iff HMAC/RSA verifies | Bogus sigs are dropped |
| Walk chain | validate_chain(name) returns True iff root -> TLD -> SLD -> leaf all verify | Bogus intermediate keys cause validation failure |
| Use a real dig | dig +dnssec www.example.com @1.1.1.1 | Output includes RRSIG record with algorithm, inception, expiration |

## Ship It

Produce one artifact under outputs/:

- A one-page runbook titled "Cache poisoning and the DNSSEC chain" that shows a Kaminsky-style attack and the DNSSEC defense.
- Or a dig output collection: dig +dnssec for a known-signed domain (e.g., www.cloudflare.com, internetsociety.org) showing RRSIG, DNSKEY, and DS records.

Start from outputs/prompt-dns-spoofing-and-dnssec.md and back every claim with a transcript from code/main.py or a real dig command.

## Exercises

1. Trace a Kaminsky attack for "Trudy wants to poison resolver R for www.evil.com." Identify which field Trudy must guess and which she controls.
2. Modify code/main.py to add source-port randomisation and 0x20 encoding. Show that the naive resolver now requires more guesses to be poisoned.
3. Implement RRSIG verification: for each RRset, compute HMAC-SHA256(rrset_canonicalization, ZSK) and compare with the RRSIG. Verify that a forged RRset without a matching signature is rejected.
4. Walk the chain root -> com -> example -> www for a real DNSSEC-signed domain. Capture the RRSIG, DNSKEY, and DS records with dig +dnssec +trace.
5. Compare the size of a DNSSEC-signed response to an unsigned response for the same query. By what factor does the response grow? What implication does this have for DNS-over-UDP packet size (512-byte limit vs. EDNS0's 4096)?
6. Active DNSSEC deployment in 2026 covers about 35% of TLD zones and ~30% of ccTLD zones. Identify three operational reasons an enterprise might delay DNSSEC deployment despite the security benefit.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Cache poisoning | "fake DNS response" | An attacker injects a forged DNS answer into a resolver's cache |
| Kaminsky attack | "race the response" | 2008 attack that made cache poisoning trivially automatable |
| Transaction ID | "the 16-bit guess" | 16-bit field in the DNS header; the primary guess target |
| DNSSEC | "DNS with signatures" | RFC 4033-4035; signs every RRset and chains trust from the root |
| RRSIG | "the signature record" | A signature over an RRset, signed by a ZSK or KSK |
| DNSKEY | "the zone's public key" | A ZSK or KSK published in the zone |
| DS | "the chain link" | Delegation Signer; SHA-256 hash of the child zone's KSK, stored in the parent |
| Trust anchor | "the root key" | The root KSK, configured out-of-band in the resolver |
| ZSK / KSK | zone / key signing key | Two-tier key structure; KSK signs DNSKEY, ZSK signs everything else |
| NSEC / NSEC3 | "authenticated denial" | Records that prove a name does not exist (signed) |
| DoT / DoH | DNS-over-TLS / HTTPS | RFC 7858, 8484; encrypt DNS for confidentiality |

## Further Reading

- RFC 4033 — DNS Security Introduction and Requirements.
- RFC 4034 — Resource Records for the DNS Security Extensions.
- RFC 4035 — Protocol Modifications for the DNS Security Extensions.
- RFC 5155 — DNS Security (DNSSEC) Hashed Authenticated Denial of Existence.
- RFC 5011 — Automated Updates of DNSSEC Trust Anchors.
- RFC 7858 — DNS over TLS.
- RFC 8484 — DNS over HTTPS.
- Kaminsky, D. (2008). "It's the End of the Cache as We Know It." Black Hat USA presentation.
- Tanenbaum & Wetherall, Computer Networks, Chapter 8 Section 8.6.
- Huston, G., and Michaelson, G. (2019). "Measuring DNSSEC Performance." APNIC.