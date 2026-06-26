# PGP message construction and key rings

> Pretty Good Privacy (PGP) is the canonical end-user public-key cryptosystem, formalized in RFC 4880 (OpenPGP) and described in Tanenbaum section 8.6. A PGP message bundles five cryptographic operations in a single byte stream: a per-message symmetric session key K_S (IDEA, 3DES, CAST, AES), an asymmetric encryption of K_S under the recipient's public key (RSA or ElGamal), a public-key signature over the plaintext (RSA, DSA, or ECDSA), a hash chain (MD5, SHA-1, SHA-256) for integrity, and an ASCII-armor wrapper so the result survives 7-bit email gateways. The companion code uses stdlib only: it computes a SHA-256 message digest, generates a deterministic 128-bit session key, encrypts the session key with textbook RSA (modular exponentiation) under the recipient's (e,n), builds a key ring that stores public-key / user-id / trust tuples, and shows the five operations that the PGP "Encrypt and Sign" command performs in sequence. The lesson closes with the OpenPGP web-of-trust argument: identity, trust, and validity are three separate attributes the key ring must keep distinct.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 15 lessons 21 (RSA), 19 (X.509 PKI), Tanenbaum 8.6
**Time:** ~70 minutes

## Learning Objectives

- Decompose a PGP "Encrypt and Sign" message into its five component operations and identify the byte-level boundary between each in an OpenPGP packet stream.
- Generate a per-message symmetric session key K_S, encrypt a plaintext with a stream-mode cipher under K_S, and "wrap" K_S under the recipient's RSA public key (n, e).
- Compute a SHA-256 digest of the plaintext and "sign" it with the sender's RSA private key (d, n), then verify by recovering the digest with the sender's public key.
- Distinguish between a public-key ring (correspondence <user-id, public-key, trust>) and a private-key ring (correspondence <user-id, private-key, passphrase-protect flag>) and explain why PGP keeps them in separate files.
- Apply the OpenPGP web-of-trust trust model: assign an "ownertrust" of unknown / never / marginally / fully / ultimately to a key introducer and explain how PGP computes validity from signatures and ownertrust.

## The Problem

Alice, a journalist, must email a confidential source story to Bob, an editor, over a public network she does not control. Her threat model has four separate adversaries: a passive eavesdropper who wants to read the story (needs confidentiality), an active attacker who wants to modify the story in transit (needs integrity), an impersonator who wants to post a fake story under her byline (needs authentication), and a denier who claims later that Bob forged the message (needs nonrepudiation). A bare TLS connection protects her only as long as the connection lasts; if the email is stored on an IMAP server, forwarded to a third reporter, or printed and mailed by hand, the protection evaporates. PGP solves this by attaching cryptographic protection to the *message*, not the *connection*: the file travels to the printer with its protection intact.

The challenge is that no single cryptographic primitive does all four jobs at once. RSA is too slow to encrypt megabytes of plaintext. AES gives confidentiality but Bob, who also has the AES key, can forge anything. A hash alone gives integrity but no signature. PGP therefore chains primitives: a fast symmetric cipher for confidentiality, RSA for key wrapping, RSA signature for authentication and nonrepudiation, SHA-256 for integrity. The lesson implements this chain in roughly 200 lines of stdlib Python so every step is auditable.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.6 (Pretty Good Privacy). The companion diagram is `assets/pgp-message-construction-and-key-rings.svg`.

### The five-operation chain

A PGP "Encrypt and Sign" message is constructed in this order:

| # | Operation | Algorithm choices | What it produces |
|---|-----------|------------------|------------------|
| 1 | Hash the plaintext | MD5 / SHA-1 / SHA-256 | digest D of length 128 / 160 / 256 bits |
| 2 | Sign the digest | RSA / DSA / ECDSA | signature S = K_SA_priv(D); in RSA, S = D^d mod n |
| 3 | Pick a session key K_S | OS CSPRNG | 128-bit (IDEA, CAST) or 256-bit (AES) secret |
| 4 | Encrypt the plaintext | IDEA / 3DES / CAST / AES / Twofish | ciphertext C = E_K_S(P) |
| 5 | Encrypt K_S for the recipient | RSA or ElGamal | wrapped session key K_S' = K_S^e_B mod n_B |

The wire format packs S, K_S', and C into a single byte stream. RFC 4880 specifies packet tags; the conceptual structure is `(S, K_S', C, optional IV, optional compression header)`.

### Why a per-message session key

Asymmetric ciphers like RSA are 100-1000x slower than symmetric ciphers like AES at the same security level. Encrypting a 4 MB photo with RSA-2048 would take seconds, and would expand the file to 4 MB of 2048-bit blocks. A 128-bit AES key, by contrast, encrypts at gigabits per second. PGP therefore picks a fresh symmetric K_S per message, encrypts the data with K_S in a streaming mode (CFB in the original spec, AES-OCB in modern OpenPGP), and uses RSA only to wrap the 128-bit K_S. The recipient unwraps K_S, then decrypts C with K_S. The cost is one RSA exponentiation (cheap) plus one bulk AES pass (fast).

### Key rings: public, private, and trust

PGP stores keys in two on-disk structures called *rings*:

- **Public-key ring** — a flat table with columns `timestamp`, `key-ID`, `public-key`, `user-ID`, `ownertrust`, `signature(s)`, `signature-trust(s)`. Every user maintains one. Entries are shared freely.
- **Private-key ring** — a flat table with the same shape but `private-key` instead of `public-key`, plus a passphrase-protection flag. Never shared.

The two rings are kept separate so a key-ring export operation can publish only the public side. PGP also stores the *user-ID* separately from the *key*, because a user may rotate keys and want to keep the same email address attached to multiple key generations.

### Web of trust vs hierarchical trust

X.509 (covered in lesson 18) trusts certificates through a top-down hierarchy: a root CA signs an intermediate, the intermediate signs a leaf, and trust flows downward. PGP inverts the model. There is no root. Instead, each user assigns an *ownertrust* to the keys they hold for other users: *unknown*, *never*, *marginally*, *fully*, or *ultimately*. A key's *validity* — is this person really who they say they are — is computed as the sum of the ownertrust values of all introducers who have signed that key, weighted by signature trust. If two marginally-trusted introducers both signed a key, validity crosses the threshold (the typical margin is two marginally-trusted or one fully-trusted introducer). This is the *web of trust*: trust flows along the edges of a graph the users collectively build by signing each other's keys at key-signing parties.

### ASCII armor and the wire format

PGP messages travel as binary packets on the wire but are typically *armored* to base64 when sent as email or pasted into chat. The armor header is `-----BEGIN PGP MESSAGE-----`, the body is base64 of the packet stream, and the checksum at the tail is a CRC-24 of the body. The armor layer is the reason a PGP-encrypted message survives being copy-pasted through 7-bit-clean MTAs (RFC 4880 §6). A binary version (raw packets) is used when the channel is known to be 8-bit clean, such as a file upload.

## Build It

`code/main.py` builds a minimal PGP-style message pipeline. Work through it in this order:

1. Run `python3 main.py` and read the imports. Only stdlib: `hashlib`, `hmac`, `os`, `struct`, `base64`. No third-party crypto. The "RSA" we use is textbook RSA on a small 1024-bit modulus — fast for the demo, never use it in production.
2. Read `KeyRing.__init__`. It keeps two dicts: `_public`, keyed by user ID, and `_private`, also keyed by user ID. Each value is a `PublicRingEntry` or `PrivateRingEntry` dataclass holding the key material plus trust metadata.
3. Read `make_session_key()`. It pulls 16 bytes from `os.urandom` for AES-128 — the per-message K_S that protects the bulk payload.
4. Read `pgp_encrypt_and_sign`. The order matches Tanenbaum Fig. 8-25: hash, sign, encrypt-plaintext, wrap-key. The function returns a dict with `signature`, `wrapped_key`, `iv`, and `ciphertext`, exactly the four component types PGP would put on the wire.
5. Read `pgp_verify_and_decrypt`. The order is inverted: unwrap-key, decrypt-plaintext, recover-signature, verify. If the recovered SHA-256 does not match the hash of the decrypted plaintext, the message is rejected.
6. Read `assign_ownertrust` and `compute_validity`. These implement the web-of-trust arithmetic: each introducer's ownertrust contributes weight; the threshold is "two marginal or one full" (configurable in the demo).
7. Read `armor`. The output of step 4 is binary; `armor` wraps it in the `-----BEGIN PGP MESSAGE-----` envelope so it survives copy-paste through 7-bit-clean channels.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Verify confidentiality | Decrypting the wrapped key requires the recipient's RSA private key | An attacker with only the public key cannot recover K_S |
| Verify integrity | SHA-256 of decrypted plaintext matches recovered digest | Tampering with the ciphertext changes the stream output and breaks the hash match |
| Verify signature | Recovered digest matches the recomputed SHA-256 of plaintext | A forger without the sender's private key cannot produce a valid signature |
| Verify nonrepudiation | Bob can present (S, K_S', C) in court and the judge verifies with Alice's public key | The judge accepts that only Alice's key could have produced S |
| Test key ring | Lookup of a known user ID returns the public key from the public ring | A missing user ID raises `KeyError` |
| Test web of trust | Assigning ownertrust "full" to an introducer lifts a key's validity above the threshold | Key validity flips from "unknown" to "marginal" or "full" |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"How Alice emails Bob a story that survives the network"* that names the five operations in order, names the byte offsets where each appears in the packet stream, and identifies which operations defend which threats.
- Or a key-signing party report: Alice meets three friends, exchanges fingerprints, signs each other's public keys, and the report lists each introducer with ownertrust and the resulting validity.

Start from [`outputs/prompt-pgp-message-construction-and-key-rings.md`](../outputs/prompt-pgp-message-construction-and-key-rings.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. PGP picks a fresh K_S per message rather than reusing a long-term key. Show concretely why reusing K_S across messages lets an attacker recover plaintext from two ciphertexts under the same key and IV (the two-time pad).
2. The PGP signature is computed over the plaintext hash, not over the ciphertext. Give one attack this prevents (chosen-ciphertext forgery against the signature) and one property it requires (the encryption must be semantically secure).
3. Modify `code/main.py` to add compression: compress the plaintext with zlib before hashing and signing, and verify that decryption + decompression recovers the original bytes. Why does PGP *not* compress after signing?
4. The web-of-trust model says two marginally-trusted introducers equal one fully-trusted introducer. What goes wrong if an attacker can register many Sybil identities and sign the same key?
5. PGP packets are self-describing (each starts with a tag and length). Describe how a PGP implementation distinguishes a signature packet from a key-wrap packet in the byte stream, and what happens if a length field is corrupted.
6. Tanenbaum notes PGP was originally free but commercial pressures pushed it into commercial products like PGP Inc. and now Symantec. What does this episode illustrate about the political economy of open cryptographic standards?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|--------------------|
| PGP | "Pretty Good Privacy" | OpenPGP (RFC 4880) end-to-end email encryption format; chains RSA, AES, and SHA-256 in one packet stream |
| Session key K_S | "the per-message secret" | Symmetric key freshly generated for each message; encrypted under recipient's RSA public key |
| Public-key ring | "the table of contacts" | File holding (timestamp, key-ID, public-key, user-ID, trust) for every correspondent |
| Private-key ring | "your own keys" | File holding private-key material, normally passphrase-protected; never shared |
| Web of trust | "trust the people you trust" | Decentralized alternative to CA hierarchies; validity = sum of ownertrust values weighted by signatures |
| ASCII armor | "the -----BEGIN envelope" | Base64 wrapper around binary OpenPGP packets so messages survive 7-bit email |
| Signature trust | "do I trust the introducer" | The weight a key signature carries toward the validity of the signed key |
| Ownertrust | "how much I trust the introducer" | Per-key flag: unknown / never / marginal / full / ultimate |

## Further Reading

- Callas, J., Donnerhacke, L., Finney, H., Shaw, D., and Thayer, R. (2007). *OpenPGP Message Format*. RFC 4880.
- Zimmermann, P. (1995). *The Official PGP User's Guide*. MIT Press.
- Garfinkel, S. (1995). *PGP: Pretty Good Privacy*. O'Reilly Media.
- Tanenbaum, A. S., and Wetherall, D. J. (2011). *Computer Networks*, 5th ed., Chapter 8 §8.6 — Pretty Good Privacy.
- Atkins, D., Stallings, W., and Zimmermann, P. (1996). "PGP Message Exchange Formats." RFC 1991 (obsoleted by RFC 4880 but still informative).
- Finney, H., Shaw, D., and Thayer, R. (2003). *OpenPGP Key Management*. draft-ietf-openpgp-keymgmt (work-in-progress).