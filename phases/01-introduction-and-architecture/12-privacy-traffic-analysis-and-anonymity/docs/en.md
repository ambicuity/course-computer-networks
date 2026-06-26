# Privacy, Traffic Snooping, and Anonymous Communication

> Computer networks make communication effortless, and they make snooping effortless too. Any router on the path between two hosts can read every byte that is not protected end to end: the **FBI's Carnivore / DCS1000** box sat inside ISPs and filtered mail; a passive wiretapper at a coffee-shop Wi-Fi AP sees HTTP in the clear and can replay **cookies** to impersonate a session (the textbook's privacy leak, Berghel 2001). The defense is layered. **TLS 1.3 (RFC 8446)** encrypts the record layer with AES-GCM or ChaCha20-Poly1305 AEAD and puts only the ClientHello `SNI` extension (RFC 6066) in the clear — already enough metadata for traffic analysis. **Traffic analysis** survives encryption: an adversary reads packet **sizes, timing, count, and direction** and classifies flows with >90% accuracy on Tor (Panchenko et al.) because the on-cell / off-cell pattern of a web page leaks through the cipher. **Tor (the second-generation onion router, RFC-proposed in the Tor design paper)** wraps payloads in **symmetric onion layers**: the client negotiates a Diffie-Hellman key with each of three **relays (guard, middle, exit)** using the **Telex-style circuit construction**, then wraps each relay's cell in the next relay's key so each hop knows only its predecessor and successor — the **Perfect Forward Secrecy** comes from ephemeral Curve25519 keys (RFC 7748) rotated per circuit. **Mix networks (Chaum 1981)** defeat timing analysis by batching and re-ordering; **padding** defeats size analysis; **cover traffic / dummy messages** defeats counting. The classic failure mode is **intersection attacks**: the adversary correlates "Alice was online at time T" with "the only circuit carrying a flow to target X was active at T," narrowing suspects one observation at a time. This lesson builds a runnable Tor-circuit onion-encrypter, a traffic-analysis classifier on packet traces, and a timing-leak demo so you can see exactly what metadata your encryption does *not* hide.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Transport-layer concepts (TCP/UDP, ports), basic symmetric and public-key cryptography (AES, Diffie-Hellman), the Internet routing model from Phase 1 lessons on hosts, links, and packets
**Time:** ~85 minutes

## Learning Objectives

- Distinguish **content security** (TLS hides the bytes) from **metadata privacy** (traffic analysis still leaks who talks to whom, when, and how much) and name three metadata signals an encrypted flow still exposes.
- Trace a **Tor circuit**: name the guard, middle, and exit relays, the three layered symmetric keys, and what each relay can and cannot learn about a cell.
- Given a recorded packet trace, compute the size/timing/count/direction features a website-fingerprinting classifier would extract, and explain why encryption does not stop it.
- Explain how **mix networks**, **padding**, **cover traffic**, and **limiting circuit lifetime** each close one specific traffic-analysis channel.
- Describe an **intersection / traffic-confirmation attack** and state the one assumption it makes about the adversary's observation windows.
- Read a TLS 1.3 ClientHello and identify which fields are still visible to a passive observer (SNI, ALPN, cipher suite list) versus which are encrypted (certificates, after the EncryptedExtensions message).

## The Problem

A human-rights reporter in a country with pervasive monitoring needs to read a blocked website. She opens `https://news.example` over the hotel Wi-Fi. TLS 1.3 encrypts the page, so the local eavesdropper cannot read the article. But the eavesdropper — and every ISP on the path to `news.example` — sees the **DNS query** for `news.example`, the **TLS SNI** extension carrying `news.example` in the clear, the **destination IP**, the **packet sizes** (one 1500-byte GET response followed by a burst of 1400-byte image segments), and the **timing** (a request at 21:03:14, a 1.2 s gap, then a 240 KB burst). That is enough to log "this room visited news.example at 21:03" and to fingerprint which article. Encryption solved the content problem and left the metadata problem wide open. The reporter's real need is not confidentiality of bytes but **unlinkability** between her and the destination. That is a different problem, and it needs a different protocol stack.

## The Concept

### What a passive observer sees, even over TLS 1.3

TLS 1.3 (RFC 8446) is a major privacy improvement over TLS 1.2: the server certificate is encrypted under the handshake keys after the `EncryptedExtensions` message, and most extensions move behind the encryption boundary. But the first flight is still in the clear. A passive observer on the path (or a TLS-terminating middlebox, or an ISP running a lawful-intercept tap) sees, in the ClientHello:

| Visible field | RFC | What it leaks |
|---|---|---|
| `SNI` extension (ServerName) | RFC 6066 | The hostname the client wants (`news.example`) |
| `ALPN` extension | RFC 7301 | The application protocol (`h2`, `http/1.1`) |
| Cipher suite list | RFC 8446 §4.2.6 | Client fingerprint (JA3-style) |
| `supported_versions` | RFC 8446 §4.2.1 | TLS version |
| Key shares (X25519 / P-256) | RFC 8446 §4.2.8 | Chosen group; another fingerprint input |
| Destination IP + port | IP/TCP headers | Which server, even if SNI were stripped |
| Packet sizes and timing | — | Website fingerprint, flow classification |

ESNI/ECH (Encrypted Client Hello, RFC 9460) encrypts the `SNI` by publishing the server's public key in the DNS (HTTPS RR, RFC 9460) and wrapping the inner ClientHello inside an outer one — but the **destination IP and the visible outer SNI** still leak, and ECH deployment is partial. The lesson: you cannot make a TCP connection invisible by encrypting its payload; you have to reroute the connection through relays.

### Threat model: what does the adversary know?

A useful privacy design starts by stating the adversary. The standard taxonomy (from the Tor design paper, Dingledine et al. 2004):

| Adversary capability | Example | What they learn |
|---|---|---|
| Local eavesdropper (coffee-shop Wi-Fi) | Reads your radio frames | Source = you, destination IP, full traffic-analysis features |
| Malicious ISP / AS-level observer | Sees a large traffic slice | Correlates your flow with a flow on another AS it also sees |
| Malicious exit relay | Sees plaintext leaving Tor | Destination, content (if not HTTPS), but **not** your identity unless colluding with guard |
| Malicious guard relay | Sees your IP + timing | Your identity + traffic pattern, but **not** destination unless colluding with exit |
| Global passive adversary | Observes all links | The dream adversary: intersection attacks win eventually |
| Active adversary | Modifies, injects, drops | Tagging attacks, replay, denial of service to force fallback |

The design target of Tor is the **non-global, distributed adversary**: resist an adversary who controls *some* relays and *some* links, but not all. Under that model, three relays with one honest relay break the link between client and destination. Under a *global* passive adversary, Tor loses to intersection attacks over time — which is why circuit lifetime and rotation matter.

### Onion routing: layered symmetric encryption

The reporter's connection through Tor uses a **circuit** of three relays. The client (Alice) performs a Diffie-Hellman handshake separately with each relay to establish three symmetric keys: `K_guard`, `K_middle`, `K_exit`. Tor 0.4.x uses Curve25519 (RFC 7748) for the ntor handshake (RFC-proposed; the Tor spec `tor-spec.txt`). To send a 512-byte **cell** `C` to the destination, Alice builds the onion from the inside out:

```
onion = ENC(K_exit,    ENC(K_middle, ENC(K_guard, C)))
```

Each relay strips one layer. The guard decrypts with `K_guard` and forwards what it sees to the middle; the middle decrypts with `K_middle` and forwards to the exit; the exit decrypts with `K_exit` and sends the plaintext `C` to the destination. The crucial property: the **guard** knows Alice's IP and the middle's IP but not the destination; the **exit** knows the destination and the middle's IP but not Alice; the **middle** knows only its two neighbors. No single relay has both endpoints. See `assets/privacy-traffic-analysis-anonymity.svg` for the three-layer unwrap and the "who knows what" matrix.

The construction gives **Perfect Forward Secrecy**: the session keys are derived from ephemeral DH outputs, so recording the ciphertext today and stealing relay private keys tomorrow does not decrypt old circuits.

### What Tor does NOT hide: traffic analysis on the circuit

The onion protects *content* and *address* from individual relays, but the **cell stream itself** still flows. The guard observes a cell from Alice at time t; the exit observes a cell to the destination at time t + δ. If the adversary controls (or merely observes) both the link Alice↔guard and the link exit↔destination, they correlate the two streams by size and timing and re-link Alice to the destination. This is the **traffic-confirmation attack**, and it is the fundamental weakness of low-latency anonymity systems. The defenses:

| Defense | Closes which channel | Cost |
|---|---|---|
| **Padding** (fixed-size cells, e.g. Tor's 512-byte cells) | Size variation | Already in Tor: 1.5–5% bandwidth overhead |
| **Timing obfuscation / delaying** (introduce jitter) | Tight timing correlation | Adds latency, kills interactive feel |
| **Cover traffic / dummy cells** | Counting and on/off pattern | High bandwidth cost; little deployed |
| **Limiting circuit lifetime** (Tor rotates every ~10 min, max 3 circuits/use) | Intersection attack over long observation | Forces adversary to re-correlate each circuit |
| **Guard stability** (one guard for months, RFC-style guard design) | Pre-emption: malicious guard must be picked first | Reduces exposure surface to one chosen guard |

The textbook's point stands: every defense is a trade-off between latency, bandwidth, and anonymity. There is no free lunch.

### Mix networks vs. onion routing

Onion routing (Tor) is **low-latency**: cells flow with sub-second delay, which is why it can carry interactive web traffic — and why it is vulnerable to timing correlation. **Mix networks** (Chaum 1981; modern variants like Loopix) accept **high latency** to break timing. A mix collects a **batch** of messages, holds them until the batch is full or a timer fires, **shuffles** them, and releases them in random order. An adversary who watched N messages enter and N leave cannot tell which input matched which output. Mixnets are the right tool for **store-and-forward email**, not for web browsing. The reporter reading a news site live cannot use a mixnet; the whistleblower emailing a document once a day can and should.

A worked comparison on a 4-message batch through one mix:

| Time | Input queue | Mix action | Output |
|---|---|---|---|
| t0 | {A→X, B→Y} | hold (batch < 4) | — |
| t1 | {A→X, B→Y, C→Z, D→W} | batch full → shuffle | random order, e.g. D→W, A→X, C→Z, B→Y |

An observer sees 4 inputs and 4 outputs but cannot bind sender to recipient. The cost: every message waited until the batch filled.

### The intersection attack, by the numbers

The intersection (or traffic-confirmation) attack does not need to break crypto. It needs **observation windows** and a hypothesis about who could have spoken to whom. Suppose the adversary logs, for each time window, which users were active and which destinations were reachable through which circuit. In window 1, only Alice and Bob were online; the only circuit to target X was active. In window 2, only Alice and Carol were online; the only circuit to X was active again. Intersecting: {Alice, Bob} ∩ {Alice, Carol} = {Alice}. After two windows the adversary has eliminated Bob and Carol. Each window halves the suspect set on average; after k windows the expected suspect set is `N / 2^k`. For N = 1024 suspects, ~10 windows suffice. This is why Tor rotates circuits and why long-lived circuits to the same destination are dangerous. `code/main.py` runs this attack on a synthetic log and prints the shrinking suspect set.

### Cookies, trackers, and the privacy layer above the network

The textbook calls out a second privacy channel that has nothing to do with packet encryption: **cookies** (RFC 6265). A site sets a `Set-Cookie: id=abc123; SameSite=Lax; Secure; HttpOnly` header; the browser replays it on every subsequent request to that origin. The cookie is a **persistent cross-session identifier** that no amount of TLS, Tor, or mixnet hides from the *destination itself* — the site already knows who you are because you told it. The same applies to **browser fingerprinting** (canvas, fonts, User-Agent, JA3 on the TLS layer). The lesson: anonymity is a stack. The network layer (Tor) hides your IP from the destination; the application layer (cookies, fingerprinting, login) can still re-identify you. The reporter who logs into her personal email over Tor has gained nothing. Real anonymous communication requires both network-layer unlinkability **and** application-layer discipline (no logins, separate identities, fresh containers). `code/main.py` includes a small cookie-flow analyzer that shows how a single `id` cookie stitches together otherwise separate TLS sessions.

## Build It

1. Read `code/main.py`. It implements three things: an **onion cell encrypter/decrypter** using AES-256-CTR with three layered keys (the Tor-style circuit model), a **website-fingerprinting feature extractor** that takes a synthetic packet trace and emits the size/timing/count/direction vectors a classifier would see, and an **intersection-attack simulator** that narrows a suspect set across observation windows.
2. Run it: `python3 code/main.py`. Confirm the onion round-trip decrypts back to the original cell, that each relay only sees its one layer, and that the intersection attack collapses the suspect set over the printed windows.
3. Modify the relay key list in `build_circuit()` (add or remove a relay) and rerun. Watch the onion layer count and the per-relay "what I can see" output change.
4. Edit the packet trace in `fingerprint_features()` to add a large image burst and rerun; observe how the size histogram and direction ratio shift — the features an adversary would use.
5. Increase the number of observation windows fed to `intersection_attack()` and confirm the suspect set shrinks toward `{Alice}`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the onion round-trips | Original cell bytes equal decrypted bytes; each relay decrypts only its layer | No relay can produce the plaintext alone; layering is inside-out |
| Read a relay's view | Per-relay printout shows predecessor + successor IPs but not both endpoints | The guard sees Alice, not the destination; the exit sees the destination, not Alice |
| Run traffic analysis on a trace | Size histogram, inter-packet timing std, direction ratio, total byte count | Features are extractable *without* decrypting — encryption did not stop the leak |
| Demonstrate an intersection attack | Suspect set after window 1, 2, 3 … collapses to one user | Each window eliminates roughly half; long observation defeats low-rotation anonymity |
| Spot the cookie privacy hole | A single `id=` cookie appears across two otherwise unrelated TLS sessions | Network-layer anonymity is useless if the application layer re-identifies you |

## Ship It

Produce one artifact under `outputs/prompt-privacy-traffic-analysis-anonymity.md`:

- An annotated Tor-circuit trace showing the three onion layers, the keys at each relay, and the per-relay "what I know" matrix.
- A traffic-analysis report on a captured trace: the size/timing/count/direction features you extracted and which website they most likely fingerprint.
- A one-page threat-model card: for a chosen adversary (coffee-shop eavesdropper, ISP, malicious exit, global passive), state what they learn with and without Tor, and which defense (padding, mixnet, guard rotation, ECH) closes each leak.

Start from the printed output of `code/main.py` and annotate it with the attack you demonstrated.

## Exercises

1. A passive observer records a TLS 1.3 ClientHello to `203.0.113.44:443`. List every field still in the clear, then describe what ECH (RFC 9460) encrypts and what it still cannot hide about this connection.
2. Build a Tor circuit with guard `G`, middle `M`, exit `E` and a cell `C`. Write the exact nesting of `ENC(K_?, …)` Alice constructs, and state which key the middle relay `M` uses and what `M` learns about the destination.
3. Given the synthetic packet trace in `fingerprint_features()`, modify it so two different websites produce indistinguishable size histograms. What did you have to add, and what real-world defense does that correspond to?
4. Run the intersection attack with N = 256 suspects and count how many windows are needed on average to isolate one user. Then double the circuit rotation rate and recompute — does the attack get faster or slower, and why?
5. A whistleblower emails a document once per day through a mixnet with batch size 8. Describe the timing channel that remains and the cover-traffic defense that closes it, then argue whether the latency trade-off is acceptable for this use case versus a reporter browsing live news over Tor.
6. A user logs into their personal Gmail over Tor. Explain precisely which links in the anonymity stack have collapsed and why, naming both the network-layer and application-layer leak. What single behavior change restores anonymity?
7. Contrast onion routing (Tor) and a mixnet on four axes: latency, the timing-analysis channel, suitable applications, and resistance to a global passive adversary.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Traffic analysis | "spying on the network" | Inferring who talks to whom from packet size, timing, count, and direction — *without* decrypting content |
| Onion routing | "Tor encryption" | Layered symmetric encryption where each relay peels one layer, so no single relay knows both endpoints |
| Tor relay (guard/middle/exit) | "a Tor server" | A volunteer node; the guard is your first (long-stable) hop, the exit connects to the real destination, the middle blinds them to each other |
| Circuit | "a Tor connection" | A path through 3 relays with three session keys, rotated roughly every 10 minutes to resist intersection attacks |
| Intersection attack | "narrowing down suspects" | Correlating "who was online" with "which circuit to the target was active" across windows, halving the suspect set each time |
| Traffic-confirmation attack | "timing correlation" | Matching a flow on link A with a flow on link B by size and timing to re-link an anonymous sender to a destination |
| Mix network | "delayed email privacy" | A store-and-forward node that batches, shuffles, and re-orders messages to break the sender-recipient binding at high latency |
| Cover traffic / dummy cells | "fake packets" | Padding injected to keep the link busy so the on/off pattern and message count do not leak |
| SNI / ECH | "the website name in TLS" | Server Name Indication (RFC 6066) leaks the hostname in the ClientHello; Encrypted Client Hello (RFC 9460) encrypts it using a DNS-published key |
| Cookie | "a tracking file" | An HTTP header (RFC 6265) the destination itself sets and replays — a persistent identifier that defeats network-layer anonymity at the application layer |
| Carnivore / DCS1000 | "the FBI's email box" | A lawful-intercept packet sniffer installed inside ISPs, named in the textbook as the canonical state traffic-snooping system |

## Further Reading

- **RFC 8446** — TLS 1.3, including the encrypted handshake after `EncryptedExtensions`.
- **RFC 6066** — TLS Extensions, including the SNI extension that leaks the hostname.
- **RFC 9460** — Encrypted Client Hello (ECH) and the HTTPS DNS record that publishes the server public key.
- **RFC 7748** — Curve25519, used for Tor's ntor circuit handshake.
- **RFC 6265** — HTTP State Management (cookies), the application-layer re-identification channel.
- **RFC 7301** — ALPN, the application-protocol extension visible in the clear ClientHello.
- Dingledine, Mathewson, Syverson, "Tor: The Second-Generation Onion Router," USENIX Security 2004 — the Tor design paper and threat model.
- Chaum, "Untraceable Electronic Mail, Return Addresses, and Digital Pseudonyms," CACM 1981 — the original mix network.
- Panchenko et al., "Website Fingerprinting at Large Scale," NDSS 2016 — traffic analysis on Tor with >90% accuracy.
- Beresford & Stajano, "Location Privacy in Mobile Computing," IEEE Pervasive 2003 — the textbook's location-privacy citation.
- Blaze & Bellovin, "Plaintext Context-Dependent Attacks on IP Traffic," 2000 — cited in the textbook on Carnivore/DCS1000.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.1.4 (Social Issues: snooping, cookies, location privacy, anonymous communication).
