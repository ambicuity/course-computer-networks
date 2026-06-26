# WEP flaws, WPA2/802.11i, and the four-way key handshake

> A coffee shop runs an 802.11 network "FreeWiFi" that the customers assume is private because they had to type a password. In 2001 the WEP protocol that "FreeWiFi" actually uses was broken in a public attack paper (Fluhrer, Mantin, Shamir) and a 2002 implementation by Adam Stubblefield recovered the keystream in one week of work, and modern tools recover a 104-bit WEP key in under a minute. WPA2 — the marketing name for IEEE 802.11i, finalized June 2004 — replaced WEP with a proper key hierarchy, per-station temporal keys, and a four-message **4-Way Handshake** that proves both peers know the password without ever sending it on the air. This lesson walks through the WEP design that failed, then the WPA2/CCMP architecture that replaced it, then the four-message EAPOL-Key exchange that derives the per-station Pairwise Transient Key (PTK) from the Pre-Shared Key (PSK) and the two nonces ANonce and SNonce, and finally the group key handshake that delivers the broadcast key GTK to a now-authenticated client. `code/main.py` is a stdlib-only 802.11i handshake simulator: it derives the PMK from the PSK, computes the PTK via the PRF-384 function, walks all four EAPOL-Key messages, prints the MIC computed over each one, and demonstrates the consequences of a wrong PSK and of a replayed first message.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Familiarity with the encryption-vs-integrity lesson, basic HMAC knowledge, the WPA-vs-WPA2 distinction, hex/byte buffers
**Time:** ~75 minutes

## Learning Objectives

- Explain why WEP's use of RC4 with a 24-bit IV and a per-packet keystream made it cryptographically broken.
- Describe the key hierarchy of 802.11i: PSK → PMK → PTK → KCK/KEK/TK, and the role of each.
- Walk the four-message 4-Way Handshake (EAPOL-Key) and what each message proves.
- Use `code/main.py` to derive a PMK and PTK, simulate all four EAPOL-Key messages, and verify the MIC.
- Show why the SNonce and ANonce must be fresh, and how a captured-then-replayed Message 1 enables a KRACK-style attack (CVE-2017-13082).
- Explain how the second two-message Group Key Handshake delivers the GTK and what the receiver checks.

## The Problem

A user trusts the coffee-shop Wi-Fi because the splash page demanded the password `hunter2`. But the password is the *only* thing standing between the user's credit-card number and a person in the parking lot. Two facts make this worse than the user's intuition suggests: (1) the 802.11 frame is broadcast on a radio channel that anyone in range can capture, and (2) the user has *no way to know* whether the AP is running WEP, WPA, or WPA2 — the visible UI is identical, and the only signal is the encryption mode advertised in the beacon.

The WEP failure mode is the most-cited case study in practical cryptography. WEP concatenated a 24-bit IV with a 40-bit or 104-bit shared key, fed the 64/128-bit result into RC4, and XORed the keystream against the plaintext. The IV was sent in the clear. Three properties of that design compounded into catastrophe:

- **The 24-bit IV space is tiny.** At typical 11 Mbps 802.11b rates, a busy AP cycles through all 2^24 ≈ 16 million IVs in about five hours. With many APs running, *collisions* on the same IV across networks become routine.
- **The same keystream encrypts every packet for that IV.** The same (IV || key) pair always produces the same RC4 keystream, so two ciphertexts under the same IV are two plaintexts XORed against each other — a textbook many-time-pad attack.
- **RC4 has known weak keys.** Fluhrer, Mantin, and Shamir (2001) showed that for IVs of a particular structure ("resolved" or "A-suffix" IVs), the first few RC4 keystream bytes leak information about the secret key. Stubblefield's 2002 implementation recovered the WEP key with ~4 million packets.

WPA2 closes all of these holes at once by (a) using AES-CCMP with a 128-bit per-station temporal key, (b) giving each station its own key so there is no multi-station keystream collision, and (c) using a 4-message handshake that proves liveness and key possession on every association. The handshake is the part most engineers mis-implement; getting it wrong enables the 2017 KRACK attacks (Key Reinstallation Attacks).

## The Concept

### The 802.11i key hierarchy

802.11i (ratified June 2004; the same year the Wi-Fi Alliance branded it "WPA2") separates the long-term shared secret from the short-term per-station keys. The hierarchy is:

| Acronym | Full name | Length | Where it lives | What it is used for |
|---|---|---|---|---|
| PSK | Pre-Shared Key | 256 bits | Both peers, derived from a passphrase via PBKDF2-SHA-1 with 4096 iterations and the SSID as salt | The password-equivalent: input to the PMK derivation |
| PMK | Pairwise Master Key | 256 bits | Both peers, derived from PSK or from the AAA server | Top-of-the-key-hierarchy; the same for every handshake until the password changes |
| PTK | Pairwise Transient Key | 384 bits (TKIP) or 512 bits (CCMP) | Both peers, derived fresh per handshake | Concatenated split into KCK + KEK + TK |
| KCK | Key Confirmation Key | 128 bits | First 16 bytes of PTK | MIC over EAPOL-Key messages during the 4-Way and Group Key handshakes |
| KEK | Key Encryption Key | 128 bits | Next 16 bytes of PTK | AES-Key-Wrap of the GTK in Message 3 of the 4-Way Handshake and in the Group Key Handshake |
| TK | Temporal Key | 128 bits (CCMP) or 256 bits (TKIP) | Last 16 (or 32) bytes of PTK | The key that actually encrypts data frames with CCMP or TKIP |
| GTK | Group Temporal Key | 128 bits (CCMP) or 256 bits (TKIP) | AP generates, distributes to clients | The shared key used for broadcast and multicast frames |

For a home WPA2-PSK deployment, the PSK is computed from the typed passphrase by PBKDF2 (4096 rounds of HMAC-SHA-1, salted with the SSID), and the PMK is *the same* as the PSK. In an enterprise deployment that uses 802.1X and a RADIUS server, the PMK is delivered per-station from the AAA server after EAP authentication completes.

### How the PMK becomes a PTK

The PTK is computed from the PMK by the **PRF-384** (or PRF-512 for CCMP) pseudo-random function. The function is built from HMAC-SHA-1 and is specified in 802.11i §8.5.1.1. In symbols:

```
PTK = PRF-384(PMK,
              "Pairwise key expansion",
              AA || SA || ANonce || SNonce)
```

where:

- `AA` is the AP's MAC address (Authenticator Address),
- `SA` is the Station's MAC address (Supplicant Address),
- `ANonce` is a 32-byte random nonce the AP generates for this handshake,
- `SNonce` is a 32-byte random nonce the STA generates for this handshake.

`PRF-384` is built as `T1 || T2 || T3`, where each `Tn` is `HMAC-SHA-1(PMK, A || label || data || n)` with `A` an 8-bit counter, and the result is truncated to 128 bits per iteration.

### The four EAPOL-Key messages

The 4-Way Handshake is carried in EAPOL-Key frames (EtherType `0x888E`). Each frame has a key information field that names the message number and the key data length. The four messages are:

| Msg | Direction | Key Data | MIC | What it proves |
|---|---|---|---|---|
| 1 | AP → STA | (none) | none | AP is alive, ANonce is fresh, STA may now compute PTK |
| 2 | STA → AP | (none) | MIC over the entire EAPOL-Key frame using KCK | STA knows the PMK (the MIC only verifies with the right PMK) and STA's SNonce is bound to this session |
| 3 | AP → STA | Encrypted GTK, key data length ≠ 0, "Install" bit set | MIC using KCK | AP is alive, has the same PTK, and delivers the GTK encrypted with KEK |
| 4 | STA → AP | (none) | MIC using KCK | STA confirms receipt and the AP-side state machine may now install TK |

Message 1 has *no* MIC because the STA does not yet have the PTK; the only thing the STA can verify is that the ANonce is well-formed. Message 4 has a MIC that the AP verifies before installing the TK on its side; if the MIC fails the AP retries rather than installing the key, which is the property KRACK attacks exploit.

### The Group Key Handshake (the "two-way handshake")

After the 4-Way completes, the AP delivers the GTK (used for broadcast and multicast) in a second, shorter handshake:

| Msg | Direction | Key Data | MIC | What it proves |
|---|---|---|---|---|
| 1 | AP → STA | Encrypted GTK | MIC using KCK | AP is alive and authorized to issue the GTK |
| 2 | STA → AP | (none) | MIC using KCK | STA confirms receipt and the AP may now broadcast using the new GTK |

Both messages are protected with the KCK derived during the 4-Way. The Group Key is rotated every time a station leaves the BSS (or at a fixed interval), so a departing client cannot decrypt subsequent broadcast traffic.

### WEP vs. WPA2 at a glance

| Property | WEP (1999) | WPA2/802.11i CCMP (2004) |
|---|---|---|
| Cipher | RC4 stream cipher | AES-128 in CTR mode with CBC-MAC |
| Key size | 40 or 104 bits + 24-bit IV | 128-bit per-station TK |
| Per-packet key | IV || shared key (reused) | Pn (packet number) packed into the CCMP nonce — unique per frame |
| Integrity | CRC-32 (linear, malleable) | CBC-MAC over the MAC header (with maskable bits zeroed) + 8-byte MIC |
| Authentication | Shared key (or open) | PSK (PBKDF2-derived PMK) or 802.1X with EAP |
| Replay defense | None | 48-bit PN; receiver drops packets with PN ≤ last accepted |
| Status | Deprecated, broken | Current standard, still in widespread use |
| Spec | IEEE 802.11 (1999) §8 | IEEE 802.11i-2004, then 802.11-2007/2012/2016 |

The line of failure in WEP, summarized: stream cipher + tiny IV space + linear integrity = two-time-pad and bit-flipping in one design. WPA2's response is also a single sentence: an AEAD cipher (AES-CCM) with a per-station, per-packet-unique nonce and a key-derivation function that proves mutual liveness before any data frame is sent.

### Worked example: PTK derivation for a single session

Inputs:
- Passphrase: `"correct horse battery staple"`, SSID `"FreeWiFi"`
- PMK (PBKDF2-SHA-1, 4096 iterations): `0x73d8…(256 bits)`
- AA = `aa:bb:cc:dd:ee:01`, SA = `11:22:33:44:55:02`
- ANonce = `0x0102…(32 bytes)`, SNonce = `0x0304…(32 bytes)`

Step 1: concatenate AA || SA || ANonce || SNonce (76 bytes total).

Step 2: `T1 = HMAC-SHA-1(PMK, 0x01 || "Pairwise key expansion" || data || 0x00)[0:20]`
`T2 = HMAC-SHA-1(PMK, 0x02 || "Pairwise key expansion" || data || 0x00)[0:20]`
`T3 = HMAC-SHA-1(PMK, 0x03 || "Pairwise key expansion" || data || 0x00)[0:20]`

Step 3: PTK-CCMP = `T1 || T2 || T3` (60 bytes; 16 bytes of `T3` are truncated).

Step 4: split: `KCK = PTK[0:16]`, `KEK = PTK[16:32]`, `TK = PTK[32:48]`.

This is exactly what `code/main.py` computes — you can run the lesson's example values and compare the printed KCK/KEK/TK against a known-good Wireshark capture (the EAPOL-Key Message 2 frame, decrypted with the same PSK, exposes the KCK in the MIC field).

### Failure modes you can recognize

| Symptom | Likely cause | What you see |
|---|---|---|
| 4-Way Handshake never completes (timeout) | Mismatched PSK between AP and STA, or the AP doesn't see the STA's EAPOL-Key Message 2 | AP logs `4-Way Handshake timeout` after ~5 seconds; STA keeps trying to associate |
| STA connects but every data frame is dropped | TK installed on one side only (out-of-order handshake, KRACK-style replay) | AP shows the STA as "associated", but `wlan.fc.type_subtype == 0x28` data frames are dropped; logs show `TK installed` then `TK reinstalled` |
| Group-addressed frames lost (e.g., ARP) | GTK handshake failed or GTK not rotated on STA departure | Unicast works, broadcast fails; the client may not have the current GTK |
| 4-Way Handshake completes, then 30 seconds later re-associates | PMKSA caching expired (default 12 hours for WPA2-PSK) | Logs show `PMKSA expired` and a fresh 4-Way Handshake at 30 s intervals |
| 4-Way Handshake takes ~3 s instead of <100 ms | AP is doing PBKDF2 from a very long passphrase (or from a fast-roaming inter-AP handoff) | CPU spike on the AP during association; usually benign |

## Build It

1. Run `code/main.py` and read the printout. Confirm:
   - The PMK is 32 bytes (PBKDF2-SHA-1 output).
   - The PTK is 48 bytes for CCMP.
   - The KCK is the first 16 bytes of the PTK, the KEK the next 16, and the TK the last 16.
2. The simulator walks the four EAPOL-Key messages. For each one it prints:
   - the EAPOL-Key frame structure (descriptor type, key information, key data length),
   - the MIC it computes (which is the value that would appear in the frame's MIC field),
   - the action the receiver takes (`ACCEPT`, `DROP_REPLAY`, `DROP_BAD_MIC`).
3. Run a "wrong PSK" simulation by changing the PSK input to the STA side. The MIC computed for Message 2 will not match the AP's expected MIC; the AP drops the frame and restarts the handshake.
4. Run a "replay Message 1" simulation: cache Message 1, then later replay it. Because the AP installs the TK on receipt of Message 4, a replayed Message 1 followed by a fresh Message 2/3/4 forces the TK to be reinstalled, which is the exact primitive used by the 2017 KRACK attacks.
5. Run the Group Key Handshake by setting `group_key=True`. The AP encrypts the GTK with the KEK and wraps it in a fresh EAPOL-Key Message 1; the STA responds with Message 2 carrying the MIC.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Derive the PMK from a passphrase | `pbkdf2_hmac("sha1", passphrase, ssid, 4096, 32)` | 32-byte hex string that matches the value shown by `wpa_supplicant -K` |
| Compute the PTK from a captured 4-Way | `main.py` with the captured ANonce, SNonce, AA, SA, PMK | KCK/KEK/TK split matches the values in the EAPOL-Key MIC and key data fields |
| Verify the MIC of Message 2 | `HMAC-SHA-1(KCK, EAPOL_frame_bytes[81:])` | First 16 bytes of the digest match the MIC field of the captured Message 2 |
| Detect a replayed Message 1 | Run the handshake, save Message 1, replay it after the original 4-Way | Second 4-Way completes but the AP's TK gets reinstalled — the same primitive as CVE-2017-13082 |
| Show the MIC failure on wrong PSK | Set a different PSK on the STA side | MIC mismatch in Message 2; AP drops the frame |

## Ship It

Produce one reusable artifact under `outputs/`:

- A Wireshark capture of a successful 4-Way Handshake (`4way.pcapng`) with the four EAPOL-Key frames annotated, the PMK derived from the passphrase overlaid on the capture, and the MIC verification shown for each.
- A reference PTK-computation worksheet (`ptk-worksheet.md`) with the input concatenation and PRF-384 step-by-step, so a reader can hand-verify a handshake from a packet capture.
- A one-page runbook of the failure modes above with the corresponding `wpa_supplicant` debug log lines (`WPA: 4-Way Handshake timeout`, `WPA: Message 2 of 4 not received`, etc.).

Start from `outputs/prompt-wep-wpa2-and-the-80211i-handshake.md`.

## Exercises

1. Compute the security margin in WEP: how long does it take for a busy 11 Mbps AP to exhaust the 24-bit IV space? How many packets can a passive attacker capture in that window? What is the worst-case keystream reuse rate?
2. In 802.11i, the PMK is the same for every handshake until the password changes, and only ANonce/SNonce change. What is the role of including both nonces in the PRF? What happens if you re-use the same SNonce with a fresh ANonce?
3. Trace the MIC computation in Message 2. Which bytes of the EAPOL-Key frame are covered by the MIC? Why is the MIC field itself zeroed in the input to the HMAC?
4. Why is the "Install" bit in Message 3 important? What is the consequence of the AP setting it before the STA has confirmed receipt of Message 3 (i.e., before Message 4 arrives)?
5. KRACK (CVE-2017-13082) exploits the fact that the AP installs the TK on receipt of Message 3, not Message 4. Walk through how a replayed Message 3 with a fresh Message 4 forces a TK reinstall and what an attacker gains from it (hint: the per-frame packet number gets reset).
6. Compute the PTK for the inputs in the worked example above. Verify the first 16 bytes match the KCK in a real `wpa_supplicant` debug log.
7. The Group Key Handshake protects the GTK with the KEK using AES-Key-Wrap (RFC 3394). What is the wrapped-key length overhead, and where in the EAPOL-Key frame is the wrapped GTK carried?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WEP | "the original Wi-Fi encryption" | RC4 + 24-bit IV; broken since 2001; never use |
| WPA | "the early fix" | Interim 802.11i subset; TKIP cipher; also broken since 2012 |
| WPA2 | "the current Wi-Fi encryption" | 802.11i-2004; AES-CCM with 4-Way Handshake |
| 802.11i | "the IEEE name for WPA2" | The standard ratified June 2004; "WPA2" is the Wi-Fi Alliance branding |
| PSK | "the Wi-Fi password" | 256-bit key derived from a passphrase by PBKDF2-SHA-1 with the SSID as salt |
| PMK | "the master key" | 256-bit top of the 802.11i key hierarchy; equals the PSK in home deployments |
| PTK | "the per-session key" | 384/512-bit transient key derived from PMK + ANonce + SNonce + MACs |
| KCK | "what proves possession" | First 16 bytes of PTK; used to compute the EAPOL-Key MIC |
| KEK | "what protects the GTK" | Second 16 bytes of PTK; wraps the GTK via AES-Key-Wrap |
| TK | "what encrypts data" | Last 16 bytes of PTK; the AES-CCM key for data frames |
| 4-Way Handshake | "the dance after the password" | Four EAPOL-Key messages that prove mutual key possession and deliver the TK |
| ANonce / SNonce | "freshness" | 32-byte random numbers the AP and STA each generate per handshake; protect against replay |
| KRACK | "the 2017 attack" | Key Reinstallation Attack: abuses TK reinstall on replayed Message 3 |
| CCMP | "the cipher" | Counter Mode with CBC-MAC Protocol — AES-128 in CTR mode + CBC-MAC for integrity |
| Group Key | "the broadcast key" | GTK, distributed via the Group Key Handshake; rotated on STA departure |

## Further Reading

- IEEE 802.11i-2004 — Medium Access Control (MAC) Security Enhancements (the standard that became WPA2)
- IEEE 802.11-2016 — the consolidation that incorporated 802.11i (current)
- RFC 4493 — The AES-CMAC Algorithm (used to compute the MIC on EAPOL-Key frames)
- RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm (used to wrap the GTK)
- Fluhrer, Mantin, Shamir (2001) — "Weaknesses in the Key Scheduling Algorithm of RC4" — the original WEP break
- Vanhoef (2017) — "Key Reinstallation Attacks: Forcing Nonce Reuse on WPA2" — the KRACK paper
- Stubbefield, Ioannidis, Rubin (2002) — "Using the Fluhrer, Mantin, and Shamir Attack to Break WEP"
- `wpa_supplicant` debug log reference — `WPA:` messages, available with `-d` flag
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed. — 802.11 security section
