# Spam, Phishing, Botnets, and CAPTCHAs Over Networks

> Network applications inherit a social problem the wires cannot solve: cheap, anonymous, automated communication floods the channel with abuse. **Spam** exploits the ~zero marginal cost of SMTP (RFC 5321) — a single TCP connection to port 25 can deliver millions of messages — so receivers fight back with layered authentication: **SPF** (RFC 7208, a DNS TXT record listing authorized sending IPs), **DKIM** (RFC 6376, an RSA/Ed25519 signature over selected headers + body hash), and **DMARC** (RFC 7489, a policy that tells the receiver what to do when SPF/DKIM alignment fails: `none`, `quarantine`, or `reject`). **Phishing** is spam weaponized for credential theft; it survives authentication because the mail is often *legitimately signed* by a freshly-registered lookalike domain, so detection shifts to content models (Naive Bayes over bag-of-words token frequencies) and URL reputation. **Botnets** convert the spam problem into a distributed one: a **command-and-control (C&C)** server drives thousands of compromised hosts via IRC, HTTP, or peer-to-peer overlays, each sending under a single mail provider's per-IP rate limit, which is why naive IP-based throttling fails. **CAPTCHAs** (von Ahn, 2001) invert the Turing test to rate-limit *humans-impersonating-machines-impersonating-humans*: a distorted recognition task a vision model of the era could not solve but a person could. This lesson builds a runnable email-authentication pipeline (SPF + DKIM-HMAC + DMARC verdict) and a Naive Bayes spam scorer, then ties them to the botnet economics that motivate CAPTCHA gating at the network edge.

**Type:** Build
**Languages:** Python
**Prerequisites:** SMTP basics (RFC 5321/5322), DNS resource records, HMAC and public-key signatures, TCP application protocols
**Time:** ~80 minutes

## Learning Objectives

- Trace an inbound email through SPF, DKIM, and DMARC in order, naming each DNS record queried and each alignment check that must pass.
- Compute a Naive Bayes log-likelihood spam score over a bag-of-words token table, including the Laplace-smoothed handling of unseen tokens.
- Explain why IP-rate-limiting an SMTP relay breaks down against a botnet and identify the C&C topologies (centralized IRC, HTTP pull, P2P) that change the defender's job.
- Distinguish a phishing message that *passes* DKIM (lookalike domain) from one that *fails* it (spoofed bank domain), and state which DMARC policy each triggers.
- Describe a CAPTCHA as a rate-limiter grounded in an AI-hard gap, and list the failure modes that moved the field from text-distortion to image-labeling and proof-of-work.
- Read the printed verdict of `code/main.py` and justify each component (SPF result, DKIM `pass/fail`, DMARC disposition, Bayes score).

## The Problem

Your mail transfer agent (MTA) accepts `23,000` inbound SMTP connections per minute. Roughly `89%` carry junk: pump-and-dump stock spam, fake bank login pages, and bounce messages relayed by a botnet of home PCs. A naive filter that throttles any single source IP to `50` messages/minute barely dents the flood, because the botnet rotates across `40,000` residential IPs in a single ASN block, each sending a handful. Worse, some malicious mail is **cryptographically signed** — not by the bank it impersonates, but by a domain `paypa1-login.com` registered two hours ago — so a "valid signature" green light is actively misleading. Meanwhile your signup form is being hit by a credential-stuffing script at `1,200` requests/second. You need three things at once: authenticate the mail path, score the mail content, and prove the form-submitter is human. All three are network-edge defenses against the same root cause — automation is cheap and identity is forged.

## The Concept

### The economics that make spam possible

SMTP (RFC 5321) was designed in a trusting 1982 network. A sender opens a TCP connection to port 25, issues `HELO`/`EHLO`, `MAIL FROM`, a series of `RCPT TO`, `DATA`, and the receiver queues the message. The marginal cost to the sender is one TCP handshake per *batch* of recipients; the marginal cost to the receiver is bandwidth, storage, and user attention. That asymmetry — sender pays ~0, receiver pays per message — is the economic root of spam. A spammer sending `10^8` messages per run from a botnet of `10^5` nodes pays for neither the bandwidth (the compromised hosts do) nor the attention (the victims do). Every technical defense in this lesson is an attempt to re-impose cost: authentication raises the cost of forging the sending domain, content filters raise the cost of evading words, CAPTCHAs raise the cost of automating form submission.

### SPF: who is allowed to send from this domain?

**SPF** (Sender Policy Framework, RFC 7208) is published as a DNS TXT record on the sending domain. The receiver takes the IP of the SMTP client (from the TCP connection, not any header) and the `MAIL FROM` envelope domain, fetches the TXT record, and evaluates a mechanism chain.

| Mechanism | Meaning | Result on match |
|---|---|---|
| `ip4:192.0.2.0/24` | Client IP in this CIDR | `pass` |
| `ip6:2001:db8::/32` | Client IPv6 in this prefix | `pass` |
| `a` | Client IP matches the domain's A/AAAA | `pass` |
| `mx` | Client IP matches one of the domain's MX hosts | `pass` |
| `include:example.org` | Evaluate example.org's record | inherit its result |
| `~all` | Default for everything else | `softfail` |
| `-all` | Default for everything else | `fail` |
| `?all` | Default | `neutral` |

The receiver resolves the chain left to right; the first terminating mechanism wins. A record `v=spf1 ip4:198.51.100.0/24 a:mail.example.org -all` says: only those IPs may send; everything else is a hard fail. SPF is evaluated against the **envelope** (`MAIL FROM`), not the visible `From:` header — that gap is exactly what DMARC closes.

### DKIM: a signature over chosen headers and the body

**DKIM** (DomainKeys Identified Mail, RFC 6376) attaches a digital signature in a `DKIM-Signature:` header. The signing mail server selects a canonical subset of headers (`h=from:to:subject:date`), hashes the body with a body-hash algorithm (`bh=`), and signs `(headers || body-hash)` with a private key. The verifier fetches the public key from a DNS TXT record at `<selector>._domainkey.<domain>`, then verifies.

Key DKIM-Signature fields:

| Tag | Meaning |
|---|---|
| `v=` | Version (1) |
| `a=` | Signing algorithm (`rsa-sha256`, `ed25519-sha256`) |
| `d=` | Signing domain |
| `s=` | Selector (names the key record) |
| `h=` | Header fields covered, colon-separated, in order |
| `bh=` | Base64 body hash |
| `b=` | Base64 signature over the canonicalized header set + `bh` |

The crucial detail: **DKIM only proves the mail was signed by someone holding `d=`'s private key.** A phish from `paypa1-login.com` signed by `paypa1-login.com` *passes DKIM* — and because the visible `From:` domain is also `paypa1-login.com`, SPF and DKIM are both *aligned* with it, so DMARC returns `pass` too. Authentication has done exactly what it was designed to: it proved the message came from the domain it claims. It cannot prove that `paypa1-login.com` (registered two hours ago, with a digit-`1` for the letter `l`) is a domain you should trust. That gap is where content scoring and URL reputation take over — and it is exactly why `code/main.py` runs a Bayes scorer alongside the auth pipeline.

### DMARC: aligning SPF/DKIM with the visible From

**DMARC** (RFC 7489) closes the envelope-vs-header gap. The receiver fetches a TXT record at `_dmarc.<domain>` shaped `v=DMARC1; p=quarantine; adkim=s; aspf=s;`. It then runs two **alignment** checks against the visible `From:` domain:

| Check | Aligned when (`aspf=s` / `adkim=s`, strict) |
|---|---|
| SPF alignment | `MAIL FROM` domain == `From` domain **and** SPF evaluated `pass` |
| DKIM alignment | `d=` domain == `From` domain **and** DKIM verified `pass` |

If **either** alignment passes, DMARC is `pass`. If both fail, the `p=` policy fires:

| `p=` | Receiver action |
|---|---|
| `none` | Monitor only, deliver, send reports |
| `quarantine` | Deliver to spam folder / hold |
| `reject` | Reject at SMTP `DATA` with `550 5.7.1` |

DMARC also specifies `rua=` (aggregate report address) and `ruf=` (forensic) so the domain owner learns which senders are failing — the feedback loop that lets a bank move from `p=none` to `p=reject` once legitimate third-party mail is accounted for. `code/main.py` evaluates SPF, DKIM (via an HMAC-SHA256 stand-in for the RSA signature), and DMARC alignment and prints the final disposition — see the verdict table it emits.

### Naive Bayes: scoring the content itself

Authentication catches forgery, not intent. A perfectly signed pump-and-dump still needs to be scored. The classic filter (Graham, "A Plan for Spam", 2002) is a **multinomial Naive Bayes** over a token table. For a message tokenized into words `w_1..w_n`, with `P(w|spam)` and `P(w|ham)` estimated from a training corpus, the log-odds score is:

```
score = log P(spam)/P(ham) + Σ_i log [ P(w_i|spam) / P(w_i|ham) ]
```

Unseen tokens are Laplace-smoothed: `P(w|c) = (count(w,c) + 1) / (total_tokens(c) + |V|)`, where `|V|` is the vocabulary size. A message scores above a threshold (commonly `5.0` in log-odds, i.e. `e^5 ≈ 148:1` odds) is filed as spam. The model is naive — it assumes tokens are independent — but it is cheap, online-updatable, and good enough that spammers learned to mix "Bayes-poison" words (`get`, `the`, `a`) into messages, which is why modern filters combine it with URL reputation, image OCR, and sender history.

### Botnets: turning the rate limit into a distributed problem

A **botnet** is a pool of compromised machines (`zombies`/`bots`) under a **command-and-control (C&C)** server. Three topologies dominate:

| Topology | C&C channel | Defender advantage | Botmaster risk |
|---|---|---|---|
| Centralized (IRC, RFC 1459) | One IRC channel the bots join | Kill the server, kill the net | Single point of failure; server takedown (e.g. Rustock, 2011) collapses the botnet |
| Centralized HTTP pull | Bots poll a URL on a timer | Sinkhole the domain | Fast-flux DNS / domain flux rotates IPs and domains |
| Peer-to-peer (P2P, e.g. Storm, Conficker) | Bots gossip on an overlay | No head to cut off | Harder to sinkhole; poisoned peers can be injected |

The defender's SMTP rate-limit of `50/min/IP` is trivially defeated because each zombie sends `49/min`. Effective defenses move to the **aggregate** layer: ASN-level reputation, outbound port-25 blocking on residential ranges (the reason home mail servers are mostly dead), and DNSBLs (DNS blocklists, RFC 5788) like Spamhaus where a receiver queries `<reversed-ip>.zen.spamhaus.org` and treats any A response as a listing. The economic insight: takedown shifts the botmaster's cost from bandwidth (free) to rebuilding the C&C infrastructure (expensive).

### CAPTCHAs: proving a human is present

A **CAPTCHA** (Completely Automated Public Turing test to tell Computers and Humans Apart, von Ahn 2001) is a reverse Turing test the *machine* administers. The original form distorts letters and asks the user to type them; the gap relied on 2001-era OCR failing on affine distortion, overlap, and background noise that humans tolerate. As OCR (and later CNNs) closed that gap, text CAPTCHAs stopped working, and the field moved to:

| Generation | Task | AI-hard because |
|---|---|---|
| Text distortion (2001) | Type the letters | Segmentation + affine-invariant recognition |
| Image labeling (reCAPTCHA v2) | "Click all traffic lights" | Fine-grained object detection under occlusion |
| Behavioral (reCAPTCHA v3) | No challenge; score from signals | Modeling human interaction timing/entropy |
| Proof-of-work | Solve a hash-partial preimage | Memoryless cost: the machine must do real hashes |

The network role of a CAPTCHA is **rate-limiting by cost imposition**: it raises the marginal cost of an automated request from ~0 to the cost of either a solver farm (~`$1–3` per 1000 solves) or a human. Combined with email authentication and content scoring, it is the third edge of the same defense: cheap automation is the common enemy. See `assets/spam-phishing-botnets-captchas.svg` for the inbound-mail pipeline and the botnet star topology that motivates aggregate defenses.

## Build It

1. Read `code/main.py`. It implements an SPF mechanism evaluator (`spf_check`), a DKIM verifier using HMAC-SHA256 as a stand-in for an RSA/Ed25519 signature (`dkim_verify`), a DMARC alignment+policy resolver (`dmarc_verdict`), and a Laplace-smoothed Naive Bayes scorer (`bayes_score`).
2. Run it: `python3 code/main.py`. Confirm the three sample messages produce the expected verdicts: a legitimate bank mail (SPF `pass` + DKIM `pass` + aligned → DMARC `pass`, Bayes `ham`); a spoofed-bank phish (SPF `neutral` on a no-record envelope domain + forged DKIM `fail` + mis-aligned → DMARC `reject`, Bayes `spam`); and a self-signed lookalike phish from `paypa1-login.com` (SPF + DKIM both **pass and aligned for the lookalike domain**, so DMARC also passes — authentication cannot catch it, and only the Bayes content score flags it `spam`).
3. Inspect the Bayes score for the lookalike message and verify the unseen-token smoothing path by adding a word not in the training corpus.
4. Edit the `SPF_RECORDS` map to add an `include:` chain and trace how `spf_check` recurses and terminates.
5. Change the DMARC policy of the spoofed domain from `reject` to `none` and observe that the verdict softens — this is why banks ratchet policy gradually.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify SPF | Mechanism chain result (`pass`/`fail`/`softfail`) against the connecting IP | The client IP is taken from the TCP connection, not the `Received` header |
| Verify DKIM | `b=` signature check against the `<selector>._domainkey` public key | The body hash `bh=` is recomputed and matched before the signature is checked |
| Resolve DMARC | Alignment of both SPF and DKIM against the visible `From` domain, then `p=` disposition | Either alignment passing yields `pass`; both failing yields the policy action |
| Score content | Naive Bayes log-odds with Laplace smoothing for unseen tokens | Score is a real number, sign and magnitude match ham/spam expectation |
| Model a botnet flood | Per-IP rate vs aggregate ASN rate | Per-IP throttle misses the flood; ASN/SDNSBL catch it |
| Catch a self-signed lookalike | DMARC `pass` for `paypa1-login.com` even though the brand it visually impersonates is different | Auth cannot help; the Bayes/URL-reputation layer must flag it — never green-light on auth alone |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/prompt-spam-phishing-botnets-captchas.md`: an annotated run of `code/main.py` over the three sample messages, plus a one-paragraph verdict for each citing the SPF mechanism, DKIM `d=` domain, DMARC alignment result, Bayes score, and the recommended action (deliver / quarantine / reject). Include a second section: pick a real botnet (Rustock, Storm, or Conficker), name its C&C topology, and state which single defender action (takedown, sinkhole, port-25 block) most raised the botmaster's cost.

## Exercises

1. A message arrives from connecting IP `198.51.100.9` with envelope `MAIL FROM:<[email protected]>` and visible `From: [email protected]`. SPF for `bank.example` is `v=spf1 ip4:198.51.100.0/24 -all`. Walk through SPF, then DMARC alignment, and state the disposition if `bank.example`'s DMARC is `p=reject`.
2. The phish instead comes from `paypa1-login.com` (note the digit `1`), correctly DKIM-signed by that domain, with SPF and DMARC both passing for `paypa1-login.com`. Explain why authentication *cannot* catch this and which two non-authentication signals a receiver must use instead.
3. A botnet of `50,000` zombies each sends `49` messages/minute to stay under a per-IP cap of `50`. Compute the aggregate flood rate and argue which two aggregate defenses (DNSBL, ASN throttle, outbound port-25 block, URL reputation) combine to stop it.
4. Train the Naive Bayes model in `code/main.py` on a corpus where the word `free` appears `200` times in `4000` spam tokens and `5` times in `6000` ham tokens, vocabulary size `12000`. Compute the log-odds contribution of the token `free` (with Laplace smoothing) and the message score if `free` is the only informative token.
5. A CAPTCHA provider sells solves at `$2` per 1000. Your signup form receives `1.2M` automated requests/day. Compute the daily attacker cost with vs without the CAPTCHA, and state one reason a behavioral score (reCAPTCHA v3) is cheaper for you than a challenge CAPTCHA.
6. Compare a centralized-IRC botnet and a P2P botnet (e.g. Storm) from the defender's seat: name the single decisive takedown action available for the IRC net and explain why the same action does not work on the P2P net, then name what does (poisoned peers / sybil injection).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SPF | "the allowed-senders list" | A DNS TXT record (RFC 7208) the receiver evaluates against the *connecting IP* and the envelope `MAIL FROM` domain |
| DKIM | "email signing" | A signature (RFC 6376) over selected headers + body hash; verifies the `d=` domain's key signed it — proves origin, not trust |
| DMARC | "the email policy" | RFC 7489 alignment of SPF/DKIM with the visible `From` domain, plus `p=none/quarantine/reject` and `rua=` feedback reports |
| Alignment | "the domains match" | Strict (`s`) alignment requires the SPF `MAIL FROM` domain and DKIM `d=` to exactly equal the `From` domain |
| Envelope vs header | "both are From" | `MAIL FROM` is the SMTP envelope (used by SPF); `From:` is the RFC 5322 header the user sees (used by DMARC alignment) |
| Botnet | "infected PCs" | A pool of compromised hosts driven by a C&C channel (IRC / HTTP pull / P2P) that defeats per-source rate limits |
| C&C | "the command server" | The control channel; its topology (centralized vs P2P) determines whether takedown or peer-poisoning is the right move |
| DNSBL | "a blocklist" | DNS blocklist (RFC 5788): a receiver queries `<rev-ip>.<list>.` and treats an A response as a listing |
| Naive Bayes | "the spam filter" | Multinomial bag-of-words log-odds with Laplace smoothing; cheap, online, the baseline that made Bayes-poisoning a spammer tactic |
| CAPTCHA | "the squiggly letters" | A reverse Turing test (von Ahn 2001) that rate-limits automation by imposing a human-vs-machine cost gap |
| Fast-flux | "rotating IPs" | Botnet technique cycling A records for the C&C domain across many zombies to evade sinkholing |

## Further Reading

- **RFC 5321** — Simple Mail Transfer Protocol (the `HELO/MAIL FROM/RCPT TO/DATA` protocol).
- **RFC 5322** — Internet Message Format (the headers a user sees, including `From:`).
- **RFC 7208** — Sender Policy Framework (SPF) for authorizing use of a domain.
- **RFC 6376** — DomainKeys Identified Mail (DKIM) signatures.
- **RFC 7489** — Domain-based Message Authentication, Reporting, and Conformance (DMARC).
- **RFC 5788** — DNSBL/RHSBL semantics and the `ias` query scheme.
- von Ahn et al., "Telling Humans and Computers Apart Automatically" (*Communications of the ACM*, 2004) — the CAPTCHA paper.
- Paul Graham, "A Plan for Spam" (2002) — the practical Naive Bayes filter that reset the field.
- Stone-Gross et al., "Your Botnet is My Botnet" (CCS 2009) — analyzing and taking over the Torpig botnet.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.1.4 (Social Issues) and Chapter 8 (Security).
