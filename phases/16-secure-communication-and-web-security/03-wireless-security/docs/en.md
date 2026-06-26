# Wireless Security

> Wireless networks leak like a sieve: 802.11 radio signals pass over the firewall in both directions, and an attacker in the parking lot can record everything a base station blurts out. The first-generation 802.11 security protocol, WEP (Wired Equivalent Privacy), was broken in one week by Adam Stubblefield at AT&T using the Fluhrer attack — weak keying made stream-cipher output repeat, and the 32-bit CRC integrity check was not cryptographically strong. WEP was replaced by 802.11i (trade name WPA2), which uses a four-packet handshake exchanging nonces between client and access point to derive a session key from a master key. CCMP (Counter mode with Cipher block chaining Message authentication code Protocol) provides confidentiality via AES-128 in counter mode and integrity via CBC-MAC. Bluetooth 2.1 uses frequency hopping, passkeys (four to six digits — only 10^4 to 10^6 choices), the E0 stream cipher, and SAFER+ for integrity; it authenticates devices, not users, so device theft grants access to accounts. TKIP was an interim fix for WEP on old hardware but is now also broken.

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Lessons 01 and 02; Phase 14 cryptography fundamentals
**Time:** ~75 minutes

## Learning Objectives

- Explain why wireless security is harder than wired: radio passes over firewalls, and base stations ship with security disabled by default.
- Describe the WEP failure: weak keying causing stream-cipher keystream reuse, 32-bit CRC integrity check (not cryptographically strong), and the Fluhrer attack that broke it in one week.
- Walk through the 802.11i (WPA2) four-packet handshake: how nonces, MAC addresses, and a master key derive a session key.
- Contrast CCMP (AES-128 counter mode + CBC-MAC) with TKIP (the interim fix, now also broken).
- Identify the two WPA2 deployment scenarios: corporate (802.1X + EAP authentication server) and home (single shared password, all clients derive each other's keys).
- Describe Bluetooth security: frequency hopping, passkey weakness, E0 stream cipher, SAFER+ integrity, device-not-user authentication, and the device-theft risk.

## The Problem

A company deploys a logically secure VPN-and-firewall architecture, but some machines are wireless. 802.11 radio range is a few hundred meters — an attacker drives into the parking lot in the morning, leaves a notebook computer in the car recording everything it hears, and leaves for the day. By late afternoon the hard disk is full of valuable goodies. The root cause: wireless base stations ship with security disabled to be "user friendly." Plugged in out of the box, they begin operating immediately with no security at all, blurting secrets to everyone within radio range. If the base station is plugged into the Ethernet, all Ethernet traffic suddenly appears in the parking lot too. Wireless is a snooper's dream: free data without doing any work.

## The Concept

### The parking-lot attack

802.11 range is a few hundred meters. An attacker with an 802.11-enabled notebook in the company parking lot can record everything the base station transmits. If the base station is connected to the Ethernet, the attacker sees all wired traffic too — the firewall is irrelevant because radio bypasses it. This is why wireless security is more important than wired security, not less.

### WEP — Wired Equivalent Privacy (broken)

WEP was the first-generation 802.11 security protocol, designed by a networking standards committee (a completely different process from how NIST selected AES). The results were devastating:

| Flaw | Detail |
|------|--------|
| Weak keying | Stream cipher (RC4) keystream was reused due to poor key management |
| Integrity check | 32-bit CRC — efficient for detecting transmission errors but not cryptographically strong against attackers |
| Key reuse | Reused keystream allows XOR of two ciphertexts to cancel the keystream, revealing the XOR of two plaintexts |

Adam Stubblefield, an intern at AT&T, coded and tested the Fluhrer et al. (2001) attack in one week — most of the time was spent convincing management to buy him a WiFi card. Software to crack WEP passwords within a minute is freely available. WEP use is very strongly discouraged: it prevents casual access but provides no real security.

### 802.11i (WPA2) — the real fix

802.11i (trade name WPA2) is a data-link-level security protocol replacing WEP. It was standardized in June 2004 after the 802.11i group was assembled in a hurry when WEP was clearly broken. Two deployment scenarios:

| Scenario | Authentication | Key distribution |
|----------|---------------|-----------------|
| Corporate | 802.1X + EAP (RFC 3748) with an authentication server holding username/password database | Each client gets a unique encryption key unknown to other clients |
| Home | Single shared password | Different keys derived per client, but all clients share the password and can derive each other's keys |

The home scenario is less secure: with a shared password, any client can derive any other client's session key.

### The four-packet handshake

The session key is computed with a four-packet handshake that happens right after the client associates with the wireless network:

| Step | Direction | Content |
|------|-----------|---------|
| 1 | AP -> Client | AP's nonce (random number used once — a "nonce") |
| 2 | Client -> AP | Client's nonce + MIC (Message Integrity Check) |
| 3 | AP -> Client | AP distributes group key K_G + MIC |
| 4 | Client -> AP | Acknowledgment + MIC |

Both sides compute the session key K_S from the nonces, both MAC addresses, and the master key. The nonces can be sent in the clear because the keys cannot be derived from them without the master key. The MIC (Message Integrity Check) is a message authentication code — the term MIC is used instead of HMAC in networking protocols to avoid confusion with MAC (Medium Access Control) addresses.

### CCMP vs TKIP

| Protocol | Encryption | Integrity | Status |
|----------|-----------|-----------|--------|
| TKIP (Temporary Key Integrity Protocol) | Improved RC4 | Michael MIC | Interim fix for old hardware; now broken |
| CCMP (Counter mode with CBC MAC Protocol) | AES-128 in counter mode | CBC-MAC (last 128-bit block) | Recommended; real security |

CCMP uses AES with a 128-bit key and block size. Confidentiality: messages encrypted with AES in counter mode (mixes a counter into encryption to prevent the same message encrypting to the same bits). Integrity: the message including header fields is encrypted with cipher block chaining mode; the last 128-bit block is kept as the MIC. Both the encrypted message and the MIC are sent. For broadcast/multicast, the group key K_G is used instead of the session key.

### Bluetooth security

Bluetooth has a considerably shorter range than 802.11, so parking-lot attacks are harder, but security is still an issue — imagine a wireless keyboard without security: Trudy in the adjacent office reads everything Alice types.

| Aspect | Bluetooth 2.1 |
|--------|--------------|
| Physical layer | Frequency hopping provides a tiny bit of security, but the hopping sequence is told to any device joining the piconet |
| Passkey | Before 2.1: four decimal digits (10^4 choices, often "1234"). 2.1+: six digits (10^6) — less predictable but still far from secure |
| Encryption | E0 stream cipher (similar to RC4/A5/1; may have fatal weaknesses) |
| Integrity | SAFER+ (submitted to AES bake-off, eliminated first round for being slow) |
| Authentication | Devices, not users — theft of a Bluetooth device grants access to the user's accounts |
| Session key | Random 128-bit; some bits may be public to comply with government export restrictions |

Bluetooth authenticates only devices, not users, so theft of a device may give the thief access to financial and other accounts. Upper-layer security (PIN codes for transactions) provides some defense even if link-level security is breached.

### Failure modes

- **Default-open base stations**: out-of-the-box, no security — the most common real-world failure.
- **WEP still deployed**: old hardware or misconfiguration leaves WEP active; cracked in under a minute.
- **Shared-password leakage**: in the home scenario, any client can derive any other's session key.
- **Group key staleness**: the group key K_G must be updated as clients leave and join; a stale group key lets departed clients still read broadcast traffic.
- **Bluetooth device theft**: device authentication, not user authentication — the thief gets access.
- **TKIP still enabled**: TKIP was an interim fix and is now broken; must be disabled in favor of CCMP.

`code/main.py` simulates the WPA2 four-packet handshake and the CCMP encryption/decryption flow; `assets/wireless-security.svg` diagrams the handshake and the WEP-to-CCMP evolution.

## Build It

1. Run `python3 code/main.py` to see the four-packet handshake complete and a session key derived.
2. Examine the WEP crack simulation: how weak keying leads to keystream reuse.
3. Run the CCMP flow: AES counter-mode encryption plus CBC-MAC integrity check.
4. Trigger the shared-password scenario: one client derives another's key.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm WPA2 is enabled | Router config page showing WPA2/CCMP, not WEP or WPA | Encryption is AES-CCMP; TKIP disabled |
| Verify handshake | Wireshark 802.11 capture with EAPOL frames 1-4 | All four messages complete; MICs verified |
| Detect WEP | Wireshark capture showing WEP-encrypted data frames | WEP is a red flag — upgrade immediately |
| Audit Bluetooth | Device pairing list; passkey length | Passkeys are 6+ digits; no "1234" defaults |

## Ship It

Create one artifact under `outputs/`:

- A wireless security audit checklist (WPA2/CCMP, no WEP, strong passkeys, group key rotation).
- A four-packet handshake trace annotation guide.
- A one-page runbook for upgrading WEP to WPA2-CCMP.

Start with [`outputs/prompt-wireless-security.md`](../outputs/prompt-wireless-security.md).

## Exercises

1. A company has an 802.11 network with WEP enabled. An attacker parks in the lot with a directional antenna. How long until they have the key? What must the company do?
2. Walk through the four-packet handshake: what does the AP send first, what does the client compute, and why can the nonces be sent in the clear?
3. In the home WPA2 scenario, three clients share a password. Client A wants to read Client B's traffic. What can Client A derive, and why is the corporate scenario safer?
4. CCMP uses AES-128 in counter mode for confidentiality and CBC-MAC for integrity. Why does counter mode prevent the same message from encrypting to the same ciphertext each time?
5. A Bluetooth headset ships with passkey "0000". Describe two attacks this enables and how Bluetooth 2.1 simple secure pairing mitigates them.
6. The group key K_G is distributed in message 3 of the handshake. Why must it be updated when a client leaves the network? What happens if it is not?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WEP | "the old one" | Wired Equivalent Privacy — broken in a week; weak RC4 keying, CRC integrity; do not use |
| WPA2 / 802.11i | "the good one" | WiFi Protected Access 2 — real security if configured properly; four-packet handshake + CCMP |
| CCMP | "AES mode" | Counter mode with CBC MAC Protocol — AES-128 counter-mode encryption + CBC-MAC integrity |
| TKIP | "the interim fix" | Temporary Key Integrity Protocol — improved RC4 for old hardware; now also broken |
| Nonce | "number used once" | Random number used once in a security protocol; sent in the clear because keys cannot be derived from it without the master key |
| MIC | "integrity check" | Message Integrity Check — a message authentication code; term avoids confusion with MAC addresses |
| EAP | "auth framework" | Extensible Authentication Protocol (RFC 3748) — framework for client-to-authentication-server dialogue |
| Passkey | "the pairing code" | Bluetooth shared secret; 4 digits (10^4) before 2.1, 6 digits (10^6) after — still far from secure |

## Further Reading

- IEEE 802.11i-2004 — Amendment 6: Medium Access Control Security Enhancements
- RFC 3748 — Extensible Authentication Protocol (EAP)
- Fluhrer, Mantin, and Shamir (2001) — Weaknesses in the Key Scheduling Algorithm of RC4
- Stubblefield, Ioannidis, and Rubin (2002) — Using the Fluhrer, Mantin, and Shamir Attack to Break WEP
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 section 8.6.4
