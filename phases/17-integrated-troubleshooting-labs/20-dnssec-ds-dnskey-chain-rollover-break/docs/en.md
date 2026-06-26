# DNSSEC DS/DNSKEY Chain Validation and Key Rollover Break

> A registered `.example.com` zone is DNSSEC-signed. The parent zone (`.com`) holds a DS (Delegation Signer) record that points to a DNSKEY in the child zone. The chain of trust runs from the root's trust anchor (a `DNSKEY` with algorithm 13 (ECDSA P-256) and a `KSK` key tag, published by the root zone operators) to the TLD's signed `DS` for `.com`, to the TLD's `DNSKEY` set, to the registrar's `DS` for `example.com`, to the child's `DNSKEY` set, to the child's signed records (A, AAAA, MX, etc.). When the child rolls its Key Signing Key (KSK), the parent must publish a new `DS` record. The window between "child signs with the new KSK" and "parent publishes the new DS" is the rollover gap, and if the gap is too short, resolvers that cached the old DS will fail to validate the new DNSKEY RRset, and the zone goes "bogus" — the resolver returns `SERVFAIL` for every query. The `dig +dnssec +multi` output is the diagnostic: the `RRSIG` records carry inception and expiration times, the `DNSKEY` set has the new key tag, and the `DS` record in the parent still points to the old key tag. The chain is broken at exactly the DS↔DNSKEY step. The fix is to honor the RFC 7583 "DS rollover cadence": publish the new DS in the parent *before* the child signs with the new KSK, leave the old DS in place during the transition, then retire the old DS only after the child's new key has propagated. The same machinery catches algorithm rollovers (algorithm 8 (RSASHA256) to algorithm 13 (ECDSA P-256)), where the parent holds a DS for both algorithms during the transition.

**Type:** Project
**Languages:** Python, dig, ldns
**Prerequisites:** Phase 12 DNS message format (RFC 1035), DNSSEC chain of trust (RFC 4033, RFC 4034, RFC 4035), RFC 5014 (DS rollover), RFC 7583 (DNSSEC key timing)
**Time:** ~120 minutes

## Learning Objectives

- Diagnose a DNSSEC chain that is broken at the DS↔DNSKEY step during a KSK rollover: read `dig +dnssec` output, find the new DNSKEY, find the old DS in the parent, and confirm the parent has not yet published the new DS.
- Explain the three DNSSEC resource record types: `DNSKEY` (the public key), `DS` (a hash of the DNSKEY, in the parent), and `RRSIG` (a signature over an RRset), and the role of each in the chain of trust.
- Read a `DS` record: key tag, algorithm, digest type, and digest, and verify that the digest matches the child's `DNSKEY` according to RFC 6605 (SHA-1) or RFC 6605 / RFC 8152 (SHA-256).
- Compute the parent-to-child validation flow: `DS(parent) → DNSKEY(child)` is verified by hashing the child's DNSKEY and comparing to the parent's DS digest. The DNSKEY's RRSIG (signed by the parent's ZSK) is what authenticates the DNSKEY.
- Distinguish a KSK rollover (key tag changes) from a ZSK rollover (only the signing key changes, the DNSKEY RRset still has the same public key) from an algorithm rollover (algorithm field changes).
- Build a Python parser for a `dig +dnssec +multi` output that prints the chain, the rollover status, and the corrective action.

## The Problem

The on-call SRE for a SaaS company that runs `api.example.com` gets a ticket: "Our DNS is broken. Every lookup returns SERVFAIL." The zone was DNSSEC-signed 18 months ago. The KSK was due for rollover. The operator rolled the KSK on the authoritative nameserver — generated a new KSK, signed the DNSKEY RRset with the new key, and updated the zone. The registrar was supposed to update the DS in the parent zone (`.com`) to point to the new KSK. The operator did the right thing in *their* zone but did not coordinate with the registrar. The resolver, validating the chain, finds the new DNSKEY but no matching DS in the parent. The chain is broken. The zone is "bogus" per RFC 4033. SERVFAIL.

The diagnostic move is `dig +dnssec +multi @127.0.0.1 api.example.com A` (against a validating resolver like `unbound` or `bind9` in validator mode). The output shows:

```
;; ->>HEADER<<- opcode: QUERY, status: SERVFAIL
;; flags: qr rd ra; SERVFAIL
```

The same query without validation: `dig @authoritative-ns api.example.com A +noedns` returns the A record correctly. The authoritative server is fine. The problem is in the chain. The deeper diagnostic is `dig +dnssec DNSKEY example.com @authoritative-ns` and `dig +dnssec DS example.com @gtld-servers`. The DNSKEY set has two keys (the old and the new), both with their RRSIGs, the new one being used to sign the DNSKEY RRset. The DS in the parent still has only the old key's digest. The chain is broken at exactly the DS↔DNSKEY step.

The fix is to publish the new DS in the parent zone *now* (and keep the old DS alongside it during the rollover), wait for the parent's TTL to expire (usually 24 hours), and only then retire the old DS. RFC 7583 §3.1 specifies a "pre-publish" model: the new DS is published in the parent *before* the child signs with the new KSK, so the chain is never broken.

## The Concept

### The chain of trust

DNSSEC builds a chain of trust from a configured trust anchor (a known good DNSKEY, usually at the root zone) down to the queried name. The chain has four record types and three trust steps:

| Step | What the validator does | Records involved |
|---|---|---|
| 1. Trust anchor | Start from a configured DNSKEY at a higher zone (root, or a manually configured TLD anchor) | Trust anchor (root) |
| 2. Parent → child | Hash the child's DNSKEY; compare to the parent's DS | `DS` (parent) + `DNSKEY` (child) + `RRSIG` over `DS` (parent's ZSK) + `RRSIG` over `DNSKEY` (child's KSK or ZSK) |
| 3. Authenticate the answer | Verify the answer's RRSIG against the child's DNSKEY | `RRSIG` (signed by child's ZSK) + `ZSK` from `DNSKEY` |

A break at any of these three steps causes the answer to be marked bogus. RFC 4033 §5 defines the four possible validation outcomes: **Secure** (chain is intact), **Insecure** (no DNSSEC at this branch), **Bogus** (chain is broken), and **Indeterminate** (no data to validate).

### The DS record format (RFC 4034 §5)

A `DS` resource record has four fields after the standard DNS header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Key Tag             |  Algorithm    | Digest Type   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|            Digest (variable, 20 or 32 bytes)                  |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- **Key Tag**: 16-bit identifier of the DNSKEY (RFC 4034 §5.1.1, computed by summing certain bytes of the DNSKEY)
- **Algorithm**: 8-bit DNSSEC algorithm number (8 = RSASHA256, 13 = ECDSA P-256, 15 = ED25519, 16 = ED448)
- **Digest Type**: 8-bit (1 = SHA-1, 2 = SHA-256, 4 = SHA-384)
- **Digest**: variable length, the hash of the child's DNSKEY

To validate, the resolver hashes the child's DNSKEY with the digest type and compares to the digest. A mismatch means the DS is for a different DNSKEY.

### The KSK vs ZSK split

A DNSSEC-signed zone typically has two keys:

- **KSK (Key Signing Key)**: signs the DNSKEY RRset; the parent's DS points to it. The KSK is the *trust anchor from the parent*.
- **ZSK (Zone Signing Key)**: signs all other RRsets (A, AAAA, MX, ...). The ZSK is rotated more frequently (RFC 6781 §4 suggests rolling it every 1-3 months).

When the KSK is rolled, the parent's DS must be updated. When the ZSK is rolled, the DNSKEY RRset is updated (a new DNSKEY appears, the old one is retired), but the parent's DS for the KSK is unchanged. The validator's job is to find the ZSK in the DNSKEY set, use it to verify the answer's RRSIG, and trust the ZSK because the KSK (in the same RRset) is trusted via the parent's DS.

### Algorithm rollovers

Algorithm rollovers (e.g. RSASHA256 → ECDSA P-256) require both keys to be in the DNSKEY RRset during the transition, and the parent must hold DS records for *both* the old and the new algorithm. The standard RFC 6781 §4.1.2 "Algorithm Roll-Over" procedure is:

1. Publish the new algorithm's DNSKEY in the child
2. Sign the zone with both old and new algorithms (double-signing)
3. Publish a DS in the parent for the new algorithm's DNSKEY
4. Wait for the parent's DS TTL to expire
5. Remove the old algorithm's DS from the parent
6. Remove the old algorithm's DNSKEY and signatures from the child

A break at step 3 is the most common: the child publishes the new DNSKEY, the resolver fetches the new DNSKEY, but the parent has no DS for it, and validation fails.

### How `dig +dnssec` presents the chain

`dig +dnssec +multi` prints the answer section with all RRSIGs included. The relevant RR types are:

- `DNSKEY`: the public key. Two flags in the DNSKEY RDATA: bit 7 (SEP) = 1 if the key is a KSK, bit 15 (ZONE) = 1 if the key is for the zone.
- `DS`: in the parent, points to a DNSKEY in the child.
- `RRSIG`: signature over an RRset, carries the signer key tag, algorithm, inception, and expiration.

The diagnostic workflow:

1. `dig +dnssec DNSKEY example.com` → get the DNSKEY RRset, identify the KSK.
2. `dig +dnssec DS example.com @gtld-servers` → get the DS RRset from the parent.
3. Compare key tags. If the parent's DS has key tag X and the child's DNSKEY RRset has a KSK with key tag Y, the chain is broken at the parent→child step.

### How the simulator models this

`code/main.py` reads a synthetic `dig +dnssec` output and prints the chain. The user picks a scenario (`--scenario ksk_rollover`, `--scenario algorithm_rollover`, `--scenario intact`), and the simulator prints the chain, the broken step, and the corrective action.

## Build It

1. **Run a validating resolver locally.** `unbound -d -c /etc/unbound/unbound.conf` (with `trust-anchor` configured for `.`). Test that `dig +dnssec www.example.com A` returns NOERROR with the `ad` flag.
2. **Reproduce the failure.** Sign a test zone with a single KSK, roll the KSK in the child but skip the parent DS update, restart `unbound`, query the zone. Watch for SERVFAIL.
3. **Run the diagnostic.** `dig +dnssec DS test.example @parent`, `dig +dnssec DNSKEY test.example @child`. Compare key tags.
4. **Apply the fix.** Add the new DS to the parent, wait for the parent's TTL, restart `unbound`, re-query. The chain re-establishes.
5. **Run the simulator.** `python3 code/main.py --scenario ksk_rollover` should print the matching chain breakdown.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm SERVFAIL bogus | `dig +dnssec` returns `status: SERVFAIL` | Resolver marked the chain bogus |
| Find the broken step | Compare parent's DS key tag to child's DNSKEY KSK key tag | Mismatch = parent has not yet published the new DS |
| Confirm the new DS is published | `dig +dnssec DS child @parent` shows the new key tag | The new DS is in the parent; the chain re-establishes |
| Confirm DS digest | Recompute the digest and compare to the parent's DS | Digest matches the child's DNSKEY |
| Verify algorithm rollover | DNSKEY RRset has both old and new algorithm keys | Resolver trusts both; the chain works during transition |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **DNSSEC rollover runbook** specifying the parent DS update, the TTL wait, the child's DNSKEY rotation, and the order of operations.
- A **chain-of-trust diagram** for the specific zone, showing the trust anchor, the parent's DS, the child's KSK, the child's ZSK, and the queried record's RRSIG.

Start from `outputs/prompt-dnssec-ds-dnskey-chain-rollover-break.md`.

## Exercises

1. The child's DNSKEY RRset has two KSKs (key tags 12345 and 67890). The parent's DS has key tag 12345 only. Is the chain intact? What should the operator do?
2. The parent publishes a new DS for the new KSK at `t=0`, with TTL 86400. The resolver cached the old DS at `t=-3600`. When will the resolver see the new DS? When is the chain fully re-established?
3. The child signs the zone with both RSASHA256 (algorithm 8) and ECDSA P-256 (algorithm 13) during an algorithm rollover. The parent has DS for both. Will a resolver that supports only algorithm 8 still validate? Why or why not?
4. A `dig +dnssec DS child @parent` returns `status: NXDOMAIN` for the child. The child exists. What is the most likely cause, and what is the corrective action?
5. The DS digest type is 1 (SHA-1). The child rolls to algorithm 15 (ED25519) and the parent updates the DS. The DS digest type is still 1. Will validation succeed on a resolver that only supports digest type 2 (SHA-256)? Why or why not?
6. The DNSKEY RRset's RRSIG has expired (expiration < now). The records are still signed. What does the resolver do? Cite the relevant RFC.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DNSSEC | "Signed DNS" | The set of extensions (RFC 4033, RFC 4034, RFC 4035) that add authentication to DNS |
| Chain of trust | "DNSSEC chain" | The sequence DS → DNSKEY → RRSIG that proves an answer is authentic |
| KSK | "Key Signing Key" | Signs the DNSKEY RRset; parent's DS points to it |
| ZSK | "Zone Signing Key" | Signs all other RRsets; rotated more frequently than the KSK |
| DS | "Delegation Signer" | A record in the parent zone containing a hash of a child's DNSKEY |
| DNSKEY | "Public key" | A public key in the child's zone, flagged as KSK (SEP=1) or ZSK |
| RRSIG | "Signature" | A signature over an RRset, signed by a ZSK (or by the KSK for the DNSKEY RRset) |
| Bogus | "Chain broken" | The validator could not authenticate the answer; SERVFAIL is the result |

## Further Reading

- RFC 4033 — DNS Security Introduction and Requirements
- RFC 4034 — Resource Records for the DNS Security Extensions (DNSKEY, DS, RRSIG formats)
- RFC 4035 — Protocol Modifications for the DNS Security Extensions
- RFC 5014 — The Source Address of DNS RFC 5014 (and general DNSSEC operational notes)
- RFC 6605 — ECDSA for DNSSEC
- RFC 6781 — DNSSEC Operational Practices, Version 2 (rollover procedures)
- RFC 7583 — DNSSEC Key Timing Considerations
- `dig(1)`, `ldns-verify-zone(1)`, `unbound(8)`, `named(8)` man pages
