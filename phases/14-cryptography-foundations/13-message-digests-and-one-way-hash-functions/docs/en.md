# Message digests and one-way hash functions

> A **message digest** (one-way hash function) compresses an arbitrarily long plaintext P into a fixed-length fingerprint MD(P) with four cryptographic properties: (1) easy to compute MD(P) given P; (2) given MD(P), it is effectively impossible to recover P (one-way / pre-image resistance); (3) given P, no one can find a different P' with MD(P') = MD(P) (collision resistance); (4) a one-bit change in P avalanches through every bit of MD(P). To meet property 3 the digest should be at least 128 bits, preferably more. SHA-1 (NIST FIPS 180-1, 1993) processes 512-bit blocks and produces a 160-bit hash; SHA-2 (FIPS 180-2) extends to 224, 256, 384, and 512 bits and changes the digest function to defeat known weaknesses. MD5 (Rivest, 1992) produces 128-bit digests using a sine-derived mixing table; Sotirov et al. (2008) demonstrated MD5 collisions, and the security community considers MD5 broken for digital signatures. This lesson ships a stdlib-only Python tool (`code/main.py`) that exercises SHA-1, SHA-256, SHA-512, and MD5, demonstrates the avalanche effect, runs a birthday-attack pre-image search, and computes HMAC-SHA256 as a building block.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-12, especially 08 (RSA, for context on signing speed)
**Time:** ~75 minutes

## Learning Objectives

- State and explain the four properties of a cryptographic hash function: pre-image resistance, second pre-image resistance, collision resistance, and avalanche behavior.
- Compute SHA-1, SHA-256, SHA-512, and MD5 digests of arbitrary input and demonstrate the avalanche effect empirically.
- Explain why message digests accelerate digital signature schemes: signing MD(P) is much faster than signing P, and any modification to P is detected because MD(P') != MD(P).
- Discuss why MD5 is broken for digital signatures but still appears in legacy checksums, and why SHA-1 was deprecated for new uses after SHAttered (2017).
- Implement HMAC-SHA256 as the canonical building block for IPsec AH/ESP, TLS record MACs, and JSON Web Tokens.

## The Problem

Your company distributes software updates as signed binaries. Each binary is hundreds of megabytes; signing each binary directly with RSA is so slow that release engineers complain about ten-minute build pipelines. Worse, customers in bandwidth-constrained regions cannot download the full binary plus the encrypted signature just to verify integrity. You need a way to produce a tiny fixed-size fingerprint of the binary that uniquely identifies it, sign only the fingerprint, and let customers re-compute the fingerprint themselves to verify.

The deeper version of the problem is more subtle: hash functions must satisfy four mathematical properties that are deceptively hard to get right. A naive checksum like CRC-32 detects random transmission errors but lets an attacker craft two different binaries with the same checksum — fatal for security. We need a hash where no attacker can find a second input that produces the same digest, even after spending centuries of compute.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.4.3 (Message Digests). The companion diagram is `assets/message-digests-and-one-way-hash-functions.svg`.

### The four properties of a one-way hash

Tanenbaum §8.4.3 enumerates the four required properties:

1. **Easy to compute.** Given P, computing MD(P) is fast (linear in |P|).
2. **Pre-image resistance.** Given MD(P), recovering P is "effectively impossible." For SHA-256, the best known attack tries 2^256 candidates — more work than the universe has been doing for its entire history.
3. **Collision resistance.** Given P, finding any P' != P with MD(P') = MD(P) is "effectively impossible." This is the property digital signatures rely on.
4. **Avalanche behavior.** Changing a single bit of P changes roughly half the bits of MD(P). Without this, an attacker could craft a near-collision and grind the rest by brute force.

Property 3 is why digests must be at least 128 bits: by the birthday paradox (lesson 15), collisions become likely around 2^(n/2) attempts for an n-bit digest. SHA-1 at 160 bits gives 2^80 collision resistance — still too weak after SHAttered (2017) found a real SHA-1 collision with 2^63 operations.

### Why hash-then-sign is faster than sign-directly

The dominant cost of an RSA signature is one modular exponentiation with a 2048-bit modulus — about 1 ms on a modern CPU for sign and 0.1 ms for verify. For a 1 GB binary, signing the binary directly means feeding the 1 GB through the RSA padding oracle (impractical — RSA is defined per block of modulus size), or computing 10 million RSA block signatures.

A message digest sidesteps both problems: compute MD(binary) once (one pass over 1 GB, ~5 seconds at 200 MB/s), then sign MD(binary) — one RSA operation on a 256-bit hash. Bob verifies by re-computing MD(binary) himself and checking the signature on the hash. Any modification to the binary triggers the avalanche property and produces a totally different MD, so the signed hash no longer matches.

### MD5: a cautionary tale

MD5 (Rivest, 1992) produces a 128-bit digest using a 128-bit running buffer. The mixing table is derived from the sine function — Rivest's point was to use a "known function" to avoid suspicion that the designer built in a back door. For over a decade MD5 was the de facto industry standard for file checksums and software downloads.

Then in 2004 Wang et al. demonstrated practical MD5 collisions with hand-tuned messages; in 2008 Sotirov et al. used MD5 collisions to forge a rogue CA certificate that real browsers accepted. The lesson: a "good enough" hash can be quietly broken by years of cryptanalytic progress. NIST now lists MD5 as "legacy" and forbids its use in digital signatures (NIST SP 800-131A Rev. 2, 2023).

### SHA-1 and SHA-2

SHA-1 (FIPS 180-1, 1993) processes 512-bit blocks through 80 rounds and produces a 160-bit digest. It was the standard for TLS 1.0/1.1, IPsec, and code signing for two decades. In February 2017 Google and CWI Amsterdam announced SHAttered, the first practical SHA-1 collision (two PDFs with the same SHA-1 hash, produced with ~6500 CPU-years of computation). Browsers and CA browsers deprecated SHA-1 in 2017-2018.

SHA-2 (FIPS 180-2, 2001) is a family of digests — SHA-224, SHA-256, SHA-384, SHA-512 — that share SHA-1's Merkle-Damgård structure but use a stronger compression function with more rounds and a wider internal state. SHA-256 is the modern default for TLS 1.2+, Bitcoin mining, and HMAC construction. SHA-3 (FIPS 202, 2015) is a different design (Keccak sponge construction) that NIST standardized as a hedge against a future SHA-2 break.

### HMAC: keyed hashing for message authentication

A bare hash is a fingerprint, not an authenticator — anyone can compute MD(P), so a bare hash does not prove who sent P. To prove both integrity and origin, hash under a secret key. HMAC (Hash-based Message Authentication Code, RFC 2104) is the canonical construction:

```
HMAC(K, m) = H( (K XOR opad) || H( (K XOR ipad) || m ) )
```

where ipad = 0x36 repeated to the hash block size and opad = 0x5C repeated likewise. HMAC-SHA256 is the workhorse for IPsec AH/ESP, TLS record MACs, JSON Web Tokens (RFC 7519), and countless API authentication schemes.

## Build It

`code/main.py` exercises the four standard hash algorithms and demonstrates the four properties. Work through it in this order:

1. Run `python3 main.py` and read the import block: `hashlib` provides SHA-1, SHA-256, SHA-512, MD5, and SHA-3 (Python 3.6+). No third-party deps.
2. Read `digest(text, algo)`: a thin wrapper that returns the hex-encoded digest.
3. Read `avalanche_demo`: hashes two strings that differ in one byte, shows the digests differ in roughly half their bits, and counts the Hamming distance.
4. Read `pre_image_resistance`: illustrates that the digest cannot be reversed — the only way to find a pre-image is brute force, which is 2^128 or more work for SHA-256.
5. Read `collision_resistance_attempt`: searches for a collision among a small set of candidate strings; with SHA-256 this never succeeds in reasonable time.
6. Read `md5_vs_sha256_perf`: benchmarks MD5 vs SHA-256 on a 100 MB buffer to show the speed difference (~3-5x).
7. Read `hmac_demo`: shows HMAC-SHA256 of a message under a key, and verifies that changing the key changes the MAC.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Compute a digest | `hashlib.sha256(data).hexdigest()` | Hex string of expected length (64 hex chars for SHA-256) |
| Demonstrate avalanche | Two 1-bit-different inputs | Hamming distance ~ n/2 in the digest |
| Sign-then-hash | Sign MD(P) with RSA | Signature on hash verifies against MD(P); signature on P is impractical |
| HMAC authentication | HMAC-SHA256(K, m) | Receiver verifies with same K; mismatched K yields different MAC |
| Detect modification | Re-hash tampered data | MD differs entirely (avalanche) |

## Ship It

Produce one artifact under `outputs/`:

- A cheat sheet titled *"When to use which hash"* with columns: Algorithm, Output bits, Status (NIST), Speed (MB/s), Recommended for. Fill in SHA-1, SHA-256, SHA-512, SHA-3-256, MD5, BLAKE2.
- Or a threat-model document: "What breaks if we use MD5?" covering signature forgery, rogue CA, and integrity attacks.

Start from [`outputs/prompt-message-digests-and-one-way-hash-functions.md`](../outputs/prompt-message-digests-and-one-way-hash-functions.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Compute SHA-256 of "Hello, world!" and "Hello, world?" and report the Hamming distance. Why is the answer evidence for the avalanche property?
2. Why does Tanenbaum say digests should be at least 128 bits? Reference the birthday bound from lesson 15.
3. Show that signing MD(P) is faster than signing P by timing RSA-sign on a 32-byte hash versus a 1 GB buffer (use the simulator from lesson 12).
4. The SHAttered attack found a SHA-1 collision with ~2^63 operations. Compare to the birthday bound of 2^80 and explain why SHAttered was a roughly 130000x speedup over generic collision search.
5. Implement HMAC-SHA1 from scratch using only the hashlib primitive (no hmac module) and verify it matches the stdlib's HMAC output for a fixed key and message.
6. A legacy system uses MD5 for software-update integrity. What is the minimum change you would make, and what is the residual risk during the migration window?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Message digest | "hash" | Fixed-length fingerprint of arbitrary input; satisfies the four properties below |
| Pre-image resistance | "one-way" | Given MD(P), finding P is infeasible |
| Second pre-image resistance | "can't tamper" | Given P, finding P' != P with MD(P') = MD(P) is infeasible |
| Collision resistance | "unique fingerprint" | Finding any P1 != P2 with MD(P1) = MD(P2) is infeasible |
| Avalanche | "one bit changes everything" | A 1-bit input change flips ~n/2 output bits |
| SHA-1 | "the 1990s standard" | FIPS 180-1; 160-bit output; broken 2017 (SHAttered) |
| SHA-256 | "the modern default" | FIPS 180-2; 256-bit output; 64 rounds; ~200 MB/s software |
| MD5 | "the broken hash" | Rivest 1992; 128-bit output; collisions demonstrated 2004 |
| HMAC | "keyed hash" | Hash-based Message Authentication Code (RFC 2104); H(K xor opad || H(K xor ipad || m)) |
| Birthday bound | "the collision floor" | 2^(n/2) attempts find a collision with 50% probability (lesson 15) |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 8 §8.4.3 — Message Digests.
- NIST FIPS 180-4 (2012). *Secure Hash Standard (SHS)* — SHA-1, SHA-224, SHA-256, SHA-384, SHA-512.
- NIST FIPS 202 (2015). *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*.
- Rivest, R. (1992). *The MD5 Message-Digest Algorithm*. RFC 1321.
- Krawczyk, H., Bellare, M., and Canetti, R. (1997). *HMAC: Keyed-Hashing for Message Authentication*. RFC 2104.
- Stevens, M., et al. (2017). "SHAttered." https://shattered.io/ — first practical SHA-1 collision.
- Wang, X., Yu, H. (2005). "How to Break MD5 and Other Hash Functions." *Eurocrypt 2005*. LNCS 3494, 19-35.
- Sotirov, A., et al. (2008). "MD5 considered harmful." https://www.win.tue.nl/hashclash/rogue-ca/ — rogue CA via MD5 collisions.