# 802.11 services: association, handoff, and WPA2/802.11i security

> The 802.11 standard groups its required behavior into nine services: five **distribution services** that traverse the Distribution System (DS) — Association, Reassociation, Disassociation, Distribution, and Integration — and four **station services** that stay on a single STA — Authentication, Deauthentication, Privacy, and MSDU delivery. A station joins a BSS by scanning channels (active Probe Request / passive Beacon), authenticating, associating (and receiving an AID), and then running a four-message EAPOL key handshake. That handshake derives a Pairwise Transient Key (PTK) for unicast CCMP frames and installs a Group Transient Key (GTK) for broadcast. Roaming uses Reassociation plus a fresh EAPOL exchange; 802.11r Fast BSS Transition, 802.11k Radio Resource Measurement, and 802.11v BSS Transition Management cut handoff latency. WPA2 is mandatory AES-128-CCM with a 48-bit Packet Number (PN) replay counter. WPA3/SAE replaces the four-message PSK handshake with a Dragonfly key exchange that is forward-secret and resists offline dictionary attacks.

**Type:** Learn
**Languages:** Python (stdlib-only handshake simulator), Wireshark
**Prerequisites:** 802.11 MAC framing, DCF/CSMA/CA, the four-frame RTS/CTS-DATA-ACK exchange, AES-CCM basics
**Time:** ~85 minutes

## Learning Objectives

- Name the nine 802.11 services and classify each as a **station service** or a **distribution service** with the DS as the boundary.
- Trace the full association sequence — Probe → Authentication → Association → EAPOL 1/2/3/4 → data — and identify which step installs the keys and which step installs the AID.
- Decode the four-message EAPOL key handshake: ANonce in msg1, SNonce + MIC in msg2, GTK wrapped in msg3, ACK in msg4, and replay counter rules.
- Compute (or simulate) the 4-way handshake: derive the PTK from PMK + ANonce + SNonce + MAC<sub>A</sub> + MAC<sub>S</sub>, and explain why the GTK is delivered inside msg3 and not its own exchange.
- Differentiate **open**, **WPA2-Personal (PSK)**, and **WPA2-Enterprise (802.1X/EAP/RADIUS)** modes by who holds the master secret and when it is generated.
- Explain what changes at handoff: reassociation, AID reassignment, full EAPOL rekey, and the latency-saving roles of 802.11k (RRM), 802.11r (FT), and 802.11v (BSS Transition Management).
- Articulate why WPA3/SAE — a Dragonfly password-authenticated key exchange — defeats the offline dictionary attack that PSK is exposed to.

## The Problem

A user walks between APs on a campus VoIP call. The WLAN engineer swears authentication is fine. The user swears the call drops. Who is right?

Both — and the answer sits at the seam between two of the nine 802.11 services. The first call, near the elevator, was carried on **AP-1's** BSS. As the user walked toward the stairwell, signal-attenuation cross the cell-edge threshold, and the station's roaming algorithm decided to switch. With classic 802.11 (pre-11r) the switch is a *full* reassociation: a Reassociation Request, an AID from the new AP, a new 4-way EAPOL handshake, fresh PTK + GTK. On a wide-coverage 5 GHz cell, that latency is on the order of hundreds of milliseconds — long enough to drop a 20 ms G.711 packet, long enough for a VoIP jitter buffer to underrun, long enough for the call to die. Authentication worked the entire time; what failed was **reassociation latency** for a moving peer.

The deeper security problem is the same 4-way handshake, just stared at from a different angle. With **WPA2-Personal**, the PMK is `PBKDF2(password, SSID, 4096, 256)` — derived from a passphrase that an attacker can passively observe by capturing the 4-way handshake off the air. Once captured, the attacker runs an **offline dictionary attack**: for every guess, run PBKDF2, replay the handshake messages, and check whether the computed MIC matches. A weak 8-character password cracks in minutes. That is why **WPA3/SAE** (Simultaneous Authentication of Equals) replaces the PSK 4-way handshake with a Dragonfly exchange: the password is never sent through a key-derivation function that the attacker can replay, and each session derives a fresh PMK with **forward secrecy** — compromising the password later cannot decrypt earlier traffic.

## The Concept

The 802.11 MAC sits on top of the radio and below the LLC. Around it the standard defines **nine services** that any conformant BSS must offer; around the *WPA2* part of the standard sits the cryptographic state machine that protects user traffic once a station is admitted. Both pieces need to be in your head before you can read a packet capture.

### The nine services and the DS boundary

The IEEE 802.11 standard splits its services into two groups, separated by the Distribution System (DS) — the wired Ethernet (typically) that connects APs in an ESS.

| Service | Group | Direction | Purpose |
|---|---|---|---|
| Distribution | Distribution | DS-bound | Decide how to route frames entering the AP: send out over the air (intra-BSS) or forward across the DS (inter-BSS). |
| Integration | Distribution | DS-bound | Translate between 802.11 frames and whatever wireline format the DS uses (e.g. Ethernet). |
| Association | Distribution | DS-bound | Bind a station to a *specific* AP. The AP returns an AID (Association ID, 1–2007) used for buffering and TIM. |
| Reassociation | Distribution | DS-bound | Move a station's binding from one AP to another. Like a cellular handover; carries the old AP's identity so the DS can forward buffered frames. |
| Disassociation | Distribution | DS-bound | Tear down the binding. Either side may initiate; polite shutdown. |
| Authentication | Station | Local to STA | Verify the station's identity. With WPA2-Personal, this proves knowledge of the PSK. |
| Deauthentication | Station | Local to STA | Tear down the authentication relationship (forces re-auth). |
| Privacy | Station | Local to STA | Encrypt/decrypt MSDUs — with WPA2, this is **AES-128-CCM**. |
| MSDU delivery | Station | Local to STA | Best-effort delivery of MAC service data units (not guaranteed reliable). |

Plus two regulatory helpers that the textbook splits off as "spectrum management" services: **Transmit Power Control (TPC)** and **Dynamic Frequency Selection (DFS)**, plus a **Higher-Layer Timer Synchronization** service that piggybacks timing on Beacon frames. They are usually drawn as a separate cluster because they have no security connotation.

A useful mnemonic: **all five *A/D* services (Association, Reassociation, Disassociation, Authentication, Deauthentication) and Distribution/Integration cross the DS** in the standard's canonical diagram; Privacy, MSDU delivery, TPC, DFS, and timer sync do not.

### Active vs passive scanning

Before a station can associate, it must find an AP. There are two methods:

- **Passive scanning** — the STA dwells on each channel for at least **ProbeDelay** (typically 100 µs) listening for **Beacon frames** broadcast every **100 TU** (102.4 ms). The STA learns SSID, BSSID, supported rates, capability bits, and the TIM.
- **Active scanning** — the STA transmits a **Probe Request** (SSID may be wildcard `0x00..0x00` or specific) on each channel, then waits **MinChannelTime**. If the channel is busy it waits **MaxChannelTime** and collects **Probe Response** frames from any AP that matches.

The textbook's "active" example: the user walks into a coffee shop, the laptop sends a directed Probe Request for `CoffeeShop-Free-WiFi`, two APs respond with Probe Responses advertising their BSSIDs and security suites, and the laptop's driver picks the strongest.

### The full association sequence

Once an AP is selected, the canonical join dance is:

```
STA                                    AP
 |    --- Probe Request (active) -->   |  (optional)
 |    <-- Probe Response ------------- |
 |                                     |
 |    --- Authentication (Open) -->    |  Algorithm=0, Transaction=1
 |    <-- Authentication (Success) --  |  Algorithm=0, Transaction=2
 |                                     |
 |    --- Association Request -->      |  SSID, rates, capability, HT/VHT caps
 |    <-- Association Response ------- |  AID, capability, status code 0
 |                                     |
 |    --- EAPOL-Key msg 1 (ANonce) --> |  S->P: A sends ANonce to S
 |    <-- EAPOL-Key msg 2 (SNonce) -- |  S->P: S sends SNonce + MIC
 |    --- EAPOL-Key msg 3 (GTK) ----> |  A->S: Sends ANonce again + GTK + MIC
 |    <-- EAPOL-Key msg 4 (ACK) ----- |  S->P: Confirms install
 |                                     |
 |    --- Data (CCMP-encrypted) ----> |
 |    <-- ARP / IPv4 / IPv6 --------- |
```

The **Open** Authentication step is misleadingly named: it is not "no security" — it is a state machine that *always succeeds* in legacy 802.11 because the standard needs an authentication state separate from cryptographic authentication. The actual key establishment happens later in the EAPOL 4-way handshake. WPA2-Personal moves the four-message exchange inside Association; WPA2-Enterprise (802.1X) runs EAPOL/EAP between Association and the 4-way, and the PMK is delivered to the AP by a RADIUS server.

### The EAPOL 4-way handshake, message by message

Each message is an EAPOL-Key frame (EAPOL protocol 0x888E) carrying an **ANonce** or **SNonce** (32-byte nonces), a **MIC** computed over the message, a **Key MIC** field, and a **Key Data** field that wraps optional group key material.

| Msg | Direction | Carries | Receiver action |
|---|---|---|---|
| 1 | AP → STA | **ANonce** | STA now has PMK (from PSK or RADIUS) + ANonce + SNonce (generated now) + MAC<sub>A</sub> + MAC<sub>S</sub>, so it can derive the PTK and compute the MIC for msg 2. |
| 2 | STA → AP | **SNonce**, **MIC** | AP reconstructs the PTK, verifies the MIC. If wrong, drops the frame — **this is what an offline dictionary attack must reproduce**. |
| 3 | AP → STA | ANonce (re-sent for safety), **GTK** wrapped with KEK portion of PTK, MIC | STA installs the PTK, decrypts GTK, installs it, then schedules msg 4. |
| 4 | STA → AP | MIC (ACK) | AP installs the PTK, starts encrypting downlink data. |

The PTK is a 384-bit blob made by:

```
PTK = PRF-384(PMK, "Pairwise key expansion",
              Min(AA,SA) || Max(AA,SA) ||
              Min(ANonce,SNonce) || Max(ANonce,SNonce))
    = KCK (128) || KEK (128) || TK (128)
```

The first 128 bits (**KCK**, Key Confirmation Key) is what computes the MIC on msg 2 and msg 3. The next 128 (**KEK**, Key Encryption Key) wraps the GTK in msg 3. The last 128 (**TK**, Temporal Key) feeds AES-CCM. The GTK is delivered *inside* msg 3 (not in its own exchange) because every CCMP broadcast/multicast frame needs a key, and a separate handshake would double the cost.

### Reassociation, AIDs, and what changes at handoff

Reassociation is *not* a new association. The frame is **Reassociation Request** (frame type 0, subtype 2) and carries the **Current AP Address** so the new AP can ask the old AP to forward any buffered frames and update the DS forwarding tables. The new AP replies with a **Reassociation Response** containing a new **AID** (a 14-bit value, 1–2007, used to address the station in the TIM bitmap and to filter ACK/Block-Ack exchanges). A full EAPOL rekey follows, because the new AP does not trust that the old PTK stays out of reach of attackers on the new BSS.

This is the latency budget that drops the VoIP call:

| Step | Typical time |
|---|---|
| 802.11k neighbor report request/response | 5–20 ms |
| Reassociation Request/Response | 5–20 ms |
| EAPOL 4-way handshake (4 round-trips at 1–10 ms) | 10–50 ms |
| Group key handshake (sometimes) | 5–20 ms |
| **Total** | **25–110 ms** |

Three amendments shave those numbers:

- **802.11k (Radio Resource Measurement)** — the STA asks the current AP for a **neighbor report** of nearby BSSIDs, channels, and capabilities *before* it needs to roam. No more 200 ms of channel scans.
- **802.11r (Fast BSS Transition, FT)** — pre-establishes a **PMK-R0** between the station and the home AAA, derives a **PMK-R1** for each candidate AP, and computes the PTK locally at handoff from cached key material. The 4-way handshake can be reduced to a 2-message **FT 4-way** (or skipped entirely in FT-over-DS), cutting handoff to single-digit ms.
- **802.11v (BSS Transition Management)** — the network tells the STA *which* AP to move to (load balancing, power save), via **BSS Transition Request** frames.

### Open, WPA2-Personal, and WPA2-Enterprise

| Mode | Master secret (PMK) | Authenticator | EAPOL 4-way? | Where the PSK is hashed |
|---|---|---|---|---|
| **Open** | none | none | no | n/a |
| **WPA2-Personal (PSK)** | PSK = PBKDF2-SHA1(password, SSID, 4096, 256) | AP (PSK in AP config) | yes | at the AP and the STA at boot |
| **WPA2-Enterprise (802.1X)** | PMK delivered by RADIUS after EAP-TLS / EAP-TTLS / PEAP | RADIUS server | yes, after EAP completes | never on the STA — only EAP methods touch it |

A useful diagnostic: in a packet capture, **RSN information element** in Beacon/Probe Response tells you what the AP supports; an **EAPOL-Key** frame with non-zero MIC field is the start of the 4-way.

### WPA3/SAE replaces PSK with Dragonfly

WPA2-Personal's offline dictionary exposure is structural, not a bug. The fix in **WPA3-Personal** is **Simultaneous Authentication of Equals (SAE)** — a **Dragonfly** key exchange (RFC 7664) that is **password-authenticated** but **zero-knowledge** to a passive observer.

```
STA                                     AP
 |   --- SAE Commit (scalar, element)  --> |
 |   <-- SAE Commit (scalar, element)  --- |
 |   --- SAE Confirm (token) --------->  |
 |   <-- SAE Confirm (token) ----------  |
 |                                       |
 |   --- EAPOL-Key msg 1 (ANonce) ---> |  (4-way now uses PMK from SAE)
 |   <-- EAPOL-Key msg 2 (SNonce) ---  |
 |   --- EAPOL-Key msg 3 (GTK) ------> |
 |   <-- EAPOL-Key msg 4 (ACK) ------  |
```

The crucial property: a passive attacker who records the SAE Commit/Confirm cannot try a dictionary offline. Dragonfly maps the password to a point on a finite-cycle group (a *hunting-and-pecking* walk), and the resulting shared secret is mixed through a one-way KDF. Compromising the password later does not retroactively decrypt the session: each session uses a fresh ephemeral scalar exchange (**forward secrecy**). Active attackers on the air still face **online** rate limiting at the AP.

## Build It

`code/main.py` is a stdlib-only Python simulator. It has no network calls and no pip dependencies. It models the four pieces that decide whether a join works:

1. **SSID/BSSID validator** — checks the SSID length, character set (0–32 octets, any 8-bit value), and that the BSSID is a valid 48-bit unicast MAC.
2. **AP and STA dataclasses** with the cryptographic state they need: PMK, ANonce, SNonce, AID, replay counter (PN).
3. **EAPOL 4-way handshake message generator** — builds msg 1 (ANonce), msg 2 (SNonce + MIC), msg 3 (ANonce + GTK-wrapped), and msg 4 (ACK), with the PN counter ticking on every CCMP-protected frame.
4. **`__main__` runner** — performs the full association sequence and prints PTK, GTK, and PN, so you can see each step.

Run it with:

```bash
python3 code/main.py
```

You will see the AP and STA negotiate the PMK (placeholder PBKDF2), derive the PTK via a PRF-384, exchange nonces, install the GTK, and emit one encrypted-data "frame" with its incremented PN. The code is a teaching simulator — its MICs are SHA-256 truncations, not AES-CMAC; for a real 802.11i stack you would use the cryptography library's CMAC and AES-CCM primitives.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Identify a STA service vs distribution service | Whether the operation touches the DS | Privacy, MSDU delivery, Authentication, Deauthentication are *station*; Association/Reassociation/Disassociation are *distribution* |
| Recognize the 4-way handshake in a capture | Frame type 0x888E (EAPOL), Key Info flags | You can label msg 1 (Install=0, Ack=1, MIC=0), msg 2 (Install=0, Ack=0, MIC=1), msg 3 (Install=1, Ack=1, MIC=1, Encrypted Key Data=1), msg 4 (Install=0, Ack=0, MIC=1) |
| Compute the PTK | PRF-384 over PMK, MAC<sub>A</sub>, MAC<sub>S</sub>, ANonce, SNonce | 384 bits = KCK ‖ KEK ‖ TK, in that order |
| Spot a roaming handoff in a capture | Reassociation Request with Current AP Address | You can follow the AID change and the immediately following EAPOL-Key exchange |
| Diagnose a slow roam | 802.11k Neighbor Reports absent; no 802.11r FT AKMs in RSN IE | Sticky client, full 4-way, no PMK caching — predict 50–200 ms latency |
| Distinguish WPA2-Personal from WPA3 | AKM suite in RSN IE | `00-0F-AC:2` = PSK, `00-0F-AC:8` = SAE |
| Verify replay protection | PN increments strictly across all CCMP frames of a session | A repeated PN triggers a receiver-side drop; a backward PN triggers immediate disassociation |

Wireshark filter cheat sheet:

```text
eapol                              # all EAPOL frames
wlan.fc.type_subtype == 0x0b       # Authentication
wlan.fc.type_subtype == 0x00       # Association Request
wlan.fc.type_subtype == 0x02       # Reassociation Request
wlan.fc.type_subtype == 0x08       # Beacon
wlan.fc.type_subtype == 0x04       # Probe Request
wlan.fc.type_subtype == 0x05       # Probe Response
eapol.keydes.key_info.install == 1 # msg 3 — installs PTK
```

## Ship It

Produce one reusable artifact under `outputs/`:

- An **802.11 services reference card** mapping each of the nine services to its scope (station vs distribution) and its standard reference.
- A **4-way handshake field decoder** with the Key Info bit layout: Install, Key Ack, Key MIC, Secure, Error, Request, Encrypted Key Data, SMK.
- The **roam-latency decision tree**: 802.11k + 802.11r + 802.11v enabled → <20 ms; PSK-only → 50–200 ms; WPA3/SAE adds an extra SAE Commit/Confirm of ~20 ms but eliminates offline dictionary exposure.
- A **WPA2 ↔ WPA3 cheat sheet** with AKM suite selectors, the difference between PSK and SAE PMK derivation, and the forward-secrecy claim.

Start from `outputs/prompt-80211-services-association-wpa2.md`.

## Exercises

1. **Services sort.** A network architect lists Integration, Privacy, MSDU delivery, Distribution, and DFS. Which are station services and which are distribution services? Which one is a "spectrum management" service and not part of the canonical nine?
2. **Scan trace interpretation.** A laptop using active scanning sends a Probe Request with SSID length 0 and a broadcast BSSID. What response can it get back, and what happens if the SSID is set to a specific value that no AP in the area uses?
3. **4-way MIC check.** A WPA2-Personal capture shows msg 1 with `Key Ack=1, Key MIC=0, Install=0`, msg 2 with `Key Ack=0, Key MIC=1, Install=0`, msg 3 with `Key Ack=1, Key MIC=1, Install=1, Encrypted Key Data=1`, and msg 4 with `Key Ack=0, Key MIC=1, Install=0`. For each, identify the role (1–4) and which side computes the MIC.
4. **PTK derivation.** Given PMK = `0x00…00` (32 bytes of zeros), MAC<sub>A</sub> = `AA:AA:AA:AA:AA:AA`, MAC<sub>S</sub> = `BB:BB:BB:BB:BB:BB`, ANonce = `0x01..01`, SNonce = `0x02..02`, sketch the PRF-384 inputs in canonical order (Min/Max of MACs and nonces) and name the three sub-keys it produces.
5. **Roaming budget.** A hospital VoIP system complains of dropped calls at the elevator bank. You have 802.11k enabled but not 802.11r. Describe the sequence the phone runs from "AP-1 RSSI < threshold" to "data flowing through AP-2," estimate the total latency, and recommend whether to enable 802.11r.
6. **WPA3 conversion.** You are asked to upgrade a guest Wi-Fi from WPA2-Personal to WPA3-Personal. The users type an 8-character alphanumeric password into a captive portal. What is the offline-dictionary exposure under WPA2, and why does SAE eliminate it? Note one operational change for your helpdesk (the SAE Commit/Confirm is *peer-to-peer* — both sides derive the PMK independently — so the AP must be reconfigured with the new AKM).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| BSS / BSSID | "the cell" / "the AP's MAC" | Basic Service Set (one AP + its STAs); the BSSID is the AP's MAC (or a random value for IBSS) |
| ESS | "the campus Wi-Fi" | Extended Service Set — multiple BSSs on the same SSID, joined by a DS |
| DS | "the wired backbone" | Distribution System — typically Ethernet, carries frames between APs |
| AID | "the slot number" | 14-bit Association ID assigned by the AP, used in TIM and Block Ack signaling |
| Probe / Beacon | "the discovery frames" | Probe Request/Response = active scan; Beacon = passive scan, broadcast by the AP every 100 TU |
| EAPOL | "the key frames" | 802.1X Encapsulation over LAN, ethertype 0x888E — carries the 4-way handshake |
| PMK | "the master secret" | Pairwise Master Key, 256 bits, lifetime of the credential (PSK or RADIUS-delivered) |
| PTK | "the session key" | Pairwise Transient Key, 384 bits = KCK (16) ‖ KEK (16) ‖ TK (16), derived from PMK + nonces + MACs |
| GTK | "the broadcast key" | Group Transient Key, 128-bit AES key installed by the AP, rotated on membership change |
| KCK / KEK / TK | "the three slices" | Key Confirmation / Key Encryption / Temporal — PTK decomposed by purpose |
| CCMP | "the encryption" | Counter Mode CBC-MAC Protocol, AES-128-CCM, the encryption + integrity algorithm in WPA2 |
| PN | "the frame counter" | 48-bit Packet Number in CCMP, strictly monotonic per session; replay protection |
| 802.11k / 11r / 11v | "the roaming amendments" | RRM neighbor reports / Fast BSS Transition / BSS Transition Management |
| SAE / Dragonfly | "the WPA3 handshake" | Password-Authenticated Key Exchange that resists offline dictionary attacks with forward secrecy |

## Further Reading

- **IEEE Std 802.11-2007** (and IEEE Std 802.11-2020), §4 — the canonical nine services and the full MAC architecture.
- **IEEE Std 802.11i-2004** — *Amendment 6: Medium Access Control Security Enhancements*; the original WPA2 spec.
- **IEEE Std 802.11r-2008** — *Amendment 2: Fast BSS Transition*; PMK-R0/R1, FT 4-way.
- **IEEE Std 802.11k-2008** — *Radio Resource Measurement*; neighbor reports, link measurement.
- **IEEE Std 802.11v-2011** — *BSS Transition Management*; network-directed roaming.
- **RFC 4493** — *The AES-CMAC Algorithm* — used for the EAPOL MIC in the 4-way handshake.
- **RFC 7664** — *Dragonfly Key Exchange* — the cryptographic core of WPA3/SAE.
- Stallings, *Cryptography and Network Security* (8th ed.), Ch. 17 — AES-CCM and the 802.11i design.
- Edney & Arbaugh, *Real 802.11 Security* (Addison-Wesley) — deep practical coverage of WPA2 enterprise deployments.
