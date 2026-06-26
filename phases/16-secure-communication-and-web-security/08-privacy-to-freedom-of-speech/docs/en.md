# Privacy to Freedom of Speech

> Privacy on a network is not a single mechanism — it is a stack of mechanisms that hide different things at different layers: PGP and SSL hide the *content* of messages; anonymous remailers and Tor hide *who* sent them; steganography hides *that* anything was sent at all. Three historical episodes define the policy backdrop: the **Clipper Chip** (April 1993), a government-proposed escrowed symmetric cipher with key recovery that collapsed under public pressure; the **cypherpunk remailer chain** (Mazières & Kaashoek 1998) that showed three public-key wraps plus traffic-analysis countermeasures are enough to make subpoena attacks economically infeasible; and the **eternity service** (Anderson 1996) which proposed replicated peer-to-peer storage across many legal jurisdictions to make censorship infeasible without physically confiscating every shard. Steganography over a 1024x768 RGB image gives a 294,912-byte covert channel (1024*768*3 low-order bits) — enough to hide 274 KB of compressed Shakespeare plus an IDEA-encrypted payload. code/main.py implements a three-hop cypherpunk remailer chain with layered X.25519-style wraps, an LSB embedder on a synthetic RGB buffer, and an anonymity-set calculator for a Tor-style path.

**Type:** Learn
**Languages:** Python (stdlib remailer + LSB steganography), Tor Browser, gpg/openssl
**Prerequisites:** Phase 16 lessons 1-7 (IPsec, firewalls, wireless, PGP/SMIME, threats, secure naming, mobile code); X.509 + PKI fundamentals (lesson 18)
**Time:** ~80 minutes

## Learning Objectives

- Trace a message through a **three-hop cypherpunk remailer chain** and explain why each hop only knows its predecessor and successor (no end-to-end correlation possible from a single seized node).
- Distinguish a **Type-1 remailer** (stores pseudonym-to-real-address mapping and can be subpoenaed, as in the 1990s Scientology case) from a **Type-2 cypherpunk remailer** (no accounts, no logs, public-key-encrypted outer envelope, inner message and next-hop header).
- Compute the **anonymity set size** for a Tor-style 3-relay path against a global passive adversary and explain why padding, reordering, and random delays at each hop raise the cost of traffic analysis.
- Embed and extract a payload in a synthetic RGB image using **LSB steganography** on the three low-order bits per pixel (one each from R, G, B), reproducing the bandwidth of Tanenbaum's three-zebras Shakespeare example (294,912 bytes per 1024x768 image).
- Articulate why the **Clipper Chip** failed as a policy proposal (the "if you have nothing to hide" framing collapsed under technical critique of key escrow and the Clipper 1994 interception-capable Mykotronx chip's MYK-78 escrow mechanism) and how that failure shaped the modern stance that strong crypto is a legitimate export.
- Map real cases: the **1990s anonymous remailer subpoena** that exposed the poster of alleged Scientology trade secrets, and the **November 2000 French Yahoo! Nazi memorabilia ruling** (Tribunal de grande instance de Paris), to the policy and technology choices that would have prevented each.

## The Problem

A human-rights worker in country X needs to publish evidence of state-level corruption to a news outlet in country Y. The evidence is a 14 MB document set. They have a domestic ISP that logs all traffic for 90 days under a national security directive. They have no control over the certificate authority store on their laptop; the government operates several root CAs. They are willing to use commercial VPN and Tor, but their adversary has a passive collector at every cross-border peering link.

Two designs could work. The first is **onion routing**: each relay strips one layer of encryption and forwards to the next, so a single adversary that controls one of three relays cannot de-anonymize the sender. The second is **steganographic publication**: the document is compressed, encrypted, and embedded in innocuous images on a publicly hosted photo gallery, so even traffic analysis cannot prove anything was communicated. Both designs come from the same intellectual family: assume your adversary is at every wire, and design so they cannot tell what happened.

The lesson's job is to teach the design vocabulary — onion, mix, anonymity set, covert channel, eternity shard — and let you exercise each in code.

## The Concept

### The right-to-privacy backdrop

Privacy is one of the older social claims in U.S. constitutional law. The **Fourth Amendment** (1791) constrains government search and seizure: "The right of the people to be secure in their persons, houses, papers, and effects, against unreasonable searches and seizures, shall not be violated, and no Warrants shall issue, but upon probable cause." That clause and the warrant clauses together limit the conditions under which state power can read private documents.

Two changes since 1990 inverted the practical calculus. First, **telephone companies and ISPs readily comply with warrants and pen-register orders**; CALEA (Communications Assistance for Law Enforcement Act, 1994) compels carriers to maintain lawful-intercept capabilities. Second, **strong cryptography became free and ubiquitous**: PGP (1991), SSL (Netscape 1994, RFC 6101 then RFC 8446 for TLS 1.3), OpenSSH (1999). With a well-managed 4096-bit RSA or 256-bit Ed25519 key and a current OpenSSL release, no adversary without your private key can read your traffic, warrant or no warrant.

States that depend on wiretaps for criminal investigation pushed back. France banned cryptography before 1999 unless the government held an escrow key; the U.S. proposed the **Clipper Chip** (April 1993) — a hardware symmetric cipher (the MYK-78 Skipjack-class algorithm) with a key escrow split between two federal agencies under a "lawful access" framework. Critics (Diffie, Schneier, Denning, et al., *Cryptologia* 1993-1995) showed the escrow protocol could not stop a malicious insider from re-escrowing an escrow key, that the MYK-78 cipher itself was a 16-round Feistel with 80-bit keys (weaker than contemporary 3DES), and that any hardware backdoor would eventually leak. The U.S. government dropped the proposal in 1996. The episode established the modern presumption: civilian-grade cryptography is a legitimate tool, and governments requesting key escrow must bear a heavy burden of proof.

### Anonymous remailers: Type 1 vs Type 2

A **remailer** is a service that strips identifying headers before forwarding an email or post. **Type 1 (pseudo-anonymous) remailers** maintain a mapping between user accounts and pseudonyms, like `anon-1234`. They are easy to subpoena: the operator can be compelled to turn over the mapping table. The 1990s Scientology case — critics posted alleged trade secrets to `alt.religion.scientology` via a Type-1 remailer; the religious group sued the operator; the operator was compelled to surrender the mapping; the posters were identified — is the canonical demonstration that this design is *not* anonymous against legal process.

**Type 2 (cypherpunk) remailers** are designed to be subpoena-resistant. They keep no accounts. They keep no logs. To send a message `M` through remailers R1, R2, R3 toward recipient `bob@destination.example`, the sender constructs a chain of nested envelopes:

```
header: To: remailer1@example.org
body:   [ encrypted_to_R2 ( header: To: remailer2@example.org
                                 body:   [ encrypted_to_R3 ( header: To: remailer3@example.org
                                                              body:   [ header: To: bob@destination.example
                                                                       body:   M ] ) ] ) ]
```

Each remailer decrypts one layer with its private key, sees only the address of the next remailer, and forwards. After remailer 3 strips the last layer, the inner RFC 822 envelope shows only `bob@destination.example` as the destination. No single remailer knows both the sender and the recipient; subpoenaing one only gets you one hop.

**Countermeasures against traffic analysis** add delay and reorder at each hop. The Mazières & Kaashoek "Mixmaster" remailer (USENIX 1998, also known as the cypherpunk mix) added:

- Constant-size messages: every outgoing message is padded to a fixed length.
- Random delays: a message waits in the mix's pool for a random interval before being forwarded.
- Reordering: messages are sent out in a different order than they arrived.
- Reply blocks: a sender can publish an encrypted reply block so a recipient can reply without knowing the sender's address.

Together these raise the cost of traffic correlation: an adversary watching both the ingress and egress of a single mix cannot easily pair incoming and outgoing messages.

### Onion routing and Tor

**Onion routing** (Goldschlag, Reed, Syverson, *IEEE JSAC* 1999) generalizes the cypherpunk idea to TCP streams. Each router (called a relay) maintains long-term TLS keys with other relays; the sender picks a path of three relays and constructs three layers of encryption, one for each. As a packet travels the path, each relay decrypts its layer to learn only the next hop. This became **Tor** (Dingledine, Mathewson, Syverson, USENIX 2004, *Tor: The Second-Generation Onion Router*); the current protocol is **Tor** with onion services using onion addresses like `3g2upl4pq6kufc4m.onion` (16-character base32 v3 onion service identifiers).

Anonymity in Tor is best understood as an **anonymity set**: the set of plausible senders a single packet could have come from. On a 3-relay path where the guard relay sees traffic from N users, the entry anonymity set is N; the middle relay sees aggregate traffic from the entire Tor network; the exit relay sees the destination request but cannot link it to a specific sender. The **anonymity set size** at any hop is the number of users whose traffic is *indistinguishable* from yours on the wire at that hop.

A global passive adversary that can monitor every Tor relay at once can perform end-to-end correlation, matching packets by timing and volume. This is the well-known "guard discovery + traffic confirmation" attack. Defenses are layered: constant-rate padding (proposed in Tor's design but never fully deployed for performance), `netflow`-resistant transports like **obfs4** (pluggable transport, RFC 7688 IETF context) and **meek** (domain-fronting), and **anonymity set hygiene** (use the network as a crowd, not a specialty channel).

### The eternity service

The **eternity service** (Ross Anderson, *IEEE ESORICS* 1996) tackles censorship rather than surveillance. The user uploads a document, pays a fee proportional to retention time and size, and the document is sharded across dozens or hundreds of servers spread across many legal jurisdictions. Each server gets a fraction of the fee and an incentive to keep its copy. If a court in jurisdiction X orders a takedown, the attacker would need to find and confiscate every shard in every other jurisdiction; with k=10 random replicas chosen from a pool of N and N large enough, the cost becomes prohibitive. **Freenet** (Clarke et al., 2002), **PASIS** (Wylie et al., 2000), and **Publius** (Waldman, Mazières, and others, USENIX 2000) all instantiate variants of this idea with different tradeoffs:

| System | Storage model | Anonymity layer | Update model |
|---|---|---|---|
| Eternity service (1996) | replicated shards | none for publisher | append-only |
| Freenet | distributed hash table with popularity caching | both publisher and reader | mutable via signed updates |
| PASIS | threshold-based secret sharing across replicas | optional | append-only |
| Publius | write-once replicated shards + Shamir sharing | minimal | write-once |

The 2000s saw a parallel defense proposal called **publius.com** (Waldman, Rubin, Cranor, USENIX 2000) which combined replicated Web hosting with anonymity for the publisher.

### Steganography: hiding that anything was said

When the threat model is "the mere fact that you communicated is incriminating," encryption alone is insufficient — ciphertext over the wire is itself a signal. **Steganography** (Greek *steganos* = covered + *graphein* = write) hides the existence of a message inside an innocuous cover medium. The original story is Herodotus: a message tattooed on a slave's scalp, hidden under regrown hair, walked across enemy lines.

Modern image steganography exploits the fact that 24-bit RGB pixels tolerate a few low-order bits of noise without visible artifacts. For a 1024x768 image, each pixel exposes 3 bits (the LSB of each of R, G, B), so the covert channel is `1024 * 768 * 3 = 2,359,296 bits = 294,912 bytes`. Tanenbaum's classic example embeds the compressed text of five Shakespeare plays (*Hamlet*, *King Lear*, *Macbeth*, *The Merchant of Venice*, *Julius Caesar* — total uncompressed ~734 KB; compressed with gzip to ~274 KB) into the zebras-and-tree photograph using IDEA encryption of the compressed payload before LSB embedding. The cover image is visually identical to a 24-bit image but carries a hidden message readable only by anyone who has the extraction key.

A real deployment requires care. Naive LSB embedding is detected by **statistical steganalysis** — tools like *StegDetect* and *SPAM* (Steganalysis with Penalized linear regression And Mixture distribution) flag images whose LSB plane has a non-natural distribution. Modern steg (e.g., *HUGO*, *WOW*) minimizes distortion using syndrome-trellis codes; detection is harder but not impossible. For journalism-grade steganography, distribute fresh scans, never re-encode, and pair the covert channel with plausible cover metadata.

**Watermarking** is the dual: an owner hides ownership evidence *into* the image so that theft can be proven in court by revealing the watermark. Watermarks must survive JPEG recompression, cropping, and rotation; steg does not need to.

### Freedom-of-speech and censorship resistance

Three landmark legal/technical confrontations shape the modern internet:

1. **Loudoun County breast-cancer filter (1998)** — a public library Web filter blocked a patron's search for breast cancer information because the filter flagged the word "breast." The patron sued. Meanwhile, in Livermore, California, a *different* parent sued a library for *not* installing a filter after her 12-year-old son viewed pornography there. The two cases together illustrate the impossible choice facing any institution that filters the Web.

2. **Yahoo! Nazi memorabilia ruling (November 2000)** — a French court (Tribunal de grande instance de Paris) ordered Yahoo!, a California corporation, to block French users from viewing auctions of Nazi memorabilia on Yahoo.com because such sales violate French law. Yahoo! appealed to a U.S. court, which sided with Yahoo! on jurisdictional grounds, but the question of whose law applies on a transnational network remains unsettled.

3. **John Gilmore, 1993**: "The Net interprets censorship as damage and routes around it." This is the engineering motto of the eternity service family. The Tor pluggable transports (*obfs4*, *meek*, *Snowflake*, *WebTunnel*) are the current operational implementation: traffic that looks like a censored user trying to reach a bridge relay is made indistinguishable from random bytes or a TLS connection to a popular CDN.

The U.K. Export Control Order 2008 extended export-control law to intangible transmissions including email and Web sites, an order later repealed in 2014 after sustained criticism. The pattern repeats in many jurisdictions: each new layer of technical capability draws a new layer of legal control, and the practical result is set by which side deploys faster.

## Build It

`code/main.py` ships three demonstrations:

1. **Three-hop cypherpunk remailer** — given three static "public keys" and a recipient, build the nested envelope structure, then *peel* one layer at a time on each remailer node. The peeler at each hop shows only the next-hop address, never both ends.
2. **LSB steganography** — embed and extract a payload in a synthetic RGB image buffer (default 32x32 to keep memory reasonable; design supports the 1024x768 ratio used in the Shakespeare example).
3. **Anonymity set calculator** — given a Tor-style path and a network population, compute the anonymity set at the guard, middle, and exit positions.

Run `python3 code/main.py` to see all three.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Read an anonymous-remailer trace | Outer/inner envelope structure | Each hop sees exactly two addresses (its predecessor and its successor) |
| Decide between Tor and a VPN | Threat model and adversary model | Tor: anonymity set and traffic analysis; VPN: shifts trust to the VPN operator |
| Estimate bandwidth of an LSB channel | Image dimensions x 3 bits | 1024x768 RGB => 294,912 bytes; 3840x2160 => 3.1 MB per cover |
| Evaluate a censorship-resistance system | Replica count and jurisdictional spread | k-of-N with N >> k; replicas in jurisdictions with independent legal process |
| Diagnose a steg-detection false positive | LSB plane chi-square vs expected | The cover image's LSB plane must look naturally noisy (camera sensor noise) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **remailer envelope diagram** showing three nested layers with the (predecessor, successor) view each hop has.
- An **LSB capacity cheat sheet** for common resolutions: 640x480, 1024x768, 1920x1080, 3840x2160, 7680x4320.
- A **policy-and-technology chronology** of privacy/censorship incidents from the 1993 Clipper announcement through the 2000 Yahoo! ruling and the 2020s Tor pluggable-transport work.
- The **remailer + LSB simulator** (`code/main.py`) wired to your team's threat-model template.

Start from `outputs/prompt-privacy-to-freedom-of-speech.md`.

## Exercises

1. A 1280x720 RGB image is offered as a steganography cover. Compute the maximum LSB-channel payload in bytes and the corresponding channel bit-rate assuming a 30 fps display rate.
2. Trace a message through a 3-hop cypherpunk remailer chain. After subpoena of remailer 2 only, can the adversary recover either (a) the original sender address or (b) the final recipient address? Cite the specific field each remailer decrypts at its step.
3. The Clipper Chip's escrow split the 80-bit session key into two 40-bit halves sent to two federal agencies, requiring a court order to retrieve. Explain why this design is structurally weak against a malicious insider at one of the escrow agencies and against an attacker who recovers the per-device *unit key* (which the agency uses to decrypt the escrow halves on demand).
4. The Eternity Service proposal stored each document on k=10 randomly chosen servers out of N. Compute the probability that an attacker confiscating servers in 3 specific jurisdictions still recovers at least one copy, assuming N=500 servers spread uniformly across 50 jurisdictions and at least 5 servers per jurisdiction.
5. Tor's anonymity set at the guard relay is the number of users whose traffic the guard sees. If 2,000,000 users are active and 4,000 guard relays exist, compute the average guard anonymity set assuming uniform user-to-guard assignment, and explain why the real number is lower due to guard pinning (Tor clients pick 1 guard and reuse it for months).
6. A content owner claims watermarking proves the image on a piracy site is theirs. The defendant argues the watermark detector runs at 70% confidence. What additional evidence (per Benham et al. and the Kerckhoffs principle) should the court require before admitting the watermark as proof?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Clipper Chip | "the government's crypto backdoor" | A 1993 proposal for escrowed symmetric hardware cipher (MYK-78 / Skipjack-class) with split-key escrow at two federal agencies; abandoned 1996 after technical and policy critique |
| Anonymous remailer | "an email anonymizer" | Server that strips identifying headers before forwarding; Type 1 stores pseudonym maps (subpoena-vulnerable); Type 2 (cypherpunk) keeps no logs and uses nested public-key encryption |
| Cypherpunk mix | "remailer with delays" | Mazières & Kaashoek 1998 design with constant-size messages, random delays, and reorder to resist traffic correlation |
| Onion routing | "Tor" | Layered encryption path through 3 relays; each relay decrypts one layer to learn only the next hop; original 1999 paper, deployed as Tor in 2003 |
| Tor | "the onion network" | Implementation of onion routing by Dingledine, Mathewson, Syverson (2004); uses TLS between relays, 3-hop paths by default, v3 onion services with 56-char addresses |
| Anonymity set | "how many users look like me" | The number of plausible senders whose traffic is indistinguishable from yours at a given network position; bigger is better |
| Eternity service | "uncensorable publication" | Anderson 1996 design: replicate documents across many servers in many jurisdictions to make takedown require confiscating every shard |
| Freenet | "distributed censorship-resistant storage" | Clarke et al. 2002: distributed hash table with popularity caching; provides anonymity for both publisher and reader |
| Steganography | "hidden writing" | Embedding a payload in a cover medium (image, audio, HTML) so the existence of the message is hidden, not just its content |
| LSB | "least significant bit" | The low-order bit of a byte or color channel; standard target for image steganography because changes are visually imperceptible |
| Watermarking | "ownership proof in the image" | Steganographic channel designed to survive JPEG/crop and prove the owner's identity when revealed |
| Pluggable transport | "Tor bridges that look like video" | obfs4, meek, Snowflake, WebTunnel: transforms Tor traffic to look like random bytes or TLS-to-CDN so a censor cannot recognize it |
| CALEA | "wiretap law" | 1994 U.S. statute requiring carriers to maintain lawful-intercept capabilities; the legal backbone for ISP cooperation with warrants |

## Further Reading

- **RFC 7688** — *Using Pre-Shared Keys with the OpenPGP* (IETF context for pluggable transport design).
- **RFC 8446** — *The Transport Layer Security (TLS) Protocol Version 1.3* (background on Tor's TLS-underlying transport).
- **RFC 6973** — *Privacy Considerations for Internet Protocols* (IETF, 2013).
- **Clipper Chip critique**: Matt Blaze, *Protocol Failure in the Escrowed Encryption Standard*, 2nd ACM CCS, 1994.
- **Anderson, R. (1996)**, "The Eternity Service," *Proc. ESORICS* (Springer LNCS 1146). Foundational paper.
- **Mazières, D. & Kaashoek, M. F. (1998)**, "The Design, Implementation and Operation of an Email Pseudonym Server," *5th ACM CCS*.
- **Dingledine, R., Mathewson, N., Syverson, P. (2004)**, "Tor: The Second-Generation Onion Router," *13th USENIX Security Symposium*.
- **Clarke, I., et al. (2002)**, "Freenet: A Distributed Anonymous Information Storage and Retrieval System," *Designing Privacy Enhancing Technologies*, Springer LNCS 2009.
- **Waldman, M., Rubin, A. D., Cranor, L. F. (2000)**, "Publius: A Robust, Tamper-Evident, Censorship-Resistant Web Publishing System," *9th USENIX Security Symposium*.
- **Electronic Frontier Foundation** — `www.eff.org` — current privacy litigation, surveillance cases, and Crypto Wars history.
- **Garfinkel, S. with Spafford, G. (2002)**, *Web Security, Privacy & Commerce*, 2nd ed., O'Reilly — Chapter 9 on privacy and anonymity.
- **Schneier, B. (1996)**, *Applied Cryptography*, 2nd ed., Wiley — Chapter 1 contains the famous "Key Escrow" and "Clipper Chip" history.
- **John Gilmore quote (1993)** — "The Net interprets censorship as damage and routes around it," attributed in *TIME Magazine* and EFF archives.
- **Herodotus, *Histories***, Book 5 — the slave's tattooed scalp, the earliest steganography story.
