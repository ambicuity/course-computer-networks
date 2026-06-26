# 802.1X Wired Network Access Control with RADIUS

> A research-lab floor at a pharmaceutical company in Cambridge lets authenticated staff, contractor laptops, and instrumentation PCs share a single Cisco Catalyst 9300 access plane, with VLAN steering driven by RADIUS attributes returned from FreeRADIUS 3.2. This lesson walks the 802.1X EAP-TLS state machine on a wired authenticator, models the conversation between the supplicant, the switch, and the FreeRADIUS server, and ships a Python simulator that replays a successful handshake, a mis-issued cert, and a MAB fallback against the lab's FreeRADIUS instance. The deliverable is a printable design report that captures session state, RADIUS attributes (`Tunnel-Type=VLAN`, `Tunnel-Medium-Type=802`, `Tunnel-Private-Group-ID=200`), and the per-port authorization state.

**Type:** Design + Implementation
**Languages:** Python 3.11 (stdlib only)
**Prerequisites:** Lesson 14 (DHCP snooping, DAI, port-security), TLS 1.2/1.3 fundamentals, RADIUS packet format
**Time:** ~140 minutes

## Learning Objectives

1. Trace a 802.1X EAP-TLS handshake through `EAPOL-Start`, `EAP-Request/Identity`, `EAP-Response/Identity`, `EAP-Request/TLS`, `TLS ClientHello`, `TLS Finished`, and the `RADIUS-Access-Accept` with tunnel attributes.
2. Configure FreeRADIUS 3.2 with `eap.conf` (TLS), `clients.conf` (the 9300 as a shared-secret client), and a `users` file that returns `Tunnel-Private-Group-ID` for VLAN steering.
3. Implement a MAB (MAC Authentication Bypass) fallback chain with a hard cutoff to a quarantine VLAN after the third unknown MAC.
4. Apply RADIUS Change of Authorization (CoA, RFC 5176) to bounce a port after posture remediation, and explain the `CoA-Request`/`CoA-ACK` round trip.
5. Distinguish EAP-TLS, EAP-TTLS, and PEAP in terms of client certificate requirements, server certificate validation, and inner-method flexibility.
6. Use the simulator's state-machine report to brief a security review on RADIUS shared secrets, certificate chains, and VLAN attribute mapping.

## The Problem

A 240-employee research campus in Cambridge runs a single Catalyst 9300-48P access stack with 12 VLANs (10-21) terminating on a routed distribution. The IT team recently retired the old port-based MAC ACL and needs to move to per-user authentication. Last year a contractor plugged a SOHO router into a data-jack, the rogue device sent `RADIUS-Access-Request` with a vendor-default username and was silently admitted because the old AAA policy was "authenticate, then accept." Security wants per-user, per-device, per-certificate authentication with VLAN steering so a researcher on VLAN 200 (lab) cannot reach VLAN 100 (HR) without an explicit policy.

The new design uses 802.1X with EAP-TLS against FreeRADIUS 3.2 (built from source on Rocky Linux 9) on a redundant pair, `10.40.1.4` and `10.40.1.5`. Supplicants are Windows 11 23H2 with machine certificates from the internal AD CS, contractor macs use a different EAP profile that requires both user and machine certs, and instrumentation PCs use MAB against a curated OUI allow-list. The change has to survive a mis-issued cert (expired CA), a misconfigured shared secret on the switch, and a MAB storm during a vendor firmware push.

The simulator replays a three-session audit: a clean EAP-TLS for `cfo-laptop`, a `TLS alert 42` failure for a revoked laptop, and a MAB fallback for a printer.

## The Concept

### 1. 802.1X Port-Based NAC — RFC 3748

802.1X is the IEEE 802.1X-2010 port-based Network Access Control standard. The three actors are:

- **Supplicant** — software on the end device (Windows Native Supplicant, wpa_supplicant, Cisco AnyConnect NAM).
- **Authenticator** — the switch (or wireless controller). The switch maintains the *port* state machine: `UNAUTH`, `AUTH`, `HELD`, `RESTART`, `QUIET`.
- **Authentication server** — FreeRADIUS, Cisco ISE, Aruba ClearPass, or RadSec proxy to a cloud IdP.

The protocol runs EAP (RFC 3748) over EAPOL (802.1X Layer 2) between the supplicant and authenticator, and EAP over RADIUS (RFC 3579) between the authenticator and the authentication server. The authenticator is a *pass-through* — it does not interpret the inner EAP method, it just relays the EAP conversation to RADIUS.

### 2. EAP-TLS — RFC 5216

EAP-TLS uses a TLS handshake inside EAP. Both the supplicant and the server present X.509 certificates. The authenticator's job is to forward each TLS record inside an `EAP-Request/TLS` or `EAP-Response/TLS` frame.

The wire sequence on a wired authenticator:

1. Supplicant sends `EAPOL-Start` (or the authenticator sends `EAP-Request/Identity` first).
2. Supplicant replies `EAP-Response/Identity` with `user@realm`.
3. Authenticator sends `RADIUS-Access-Request` with `User-Name`, `Service-Type=Framed`, `NAS-Port-Type=Ethernet`.
4. Server replies `RADIUS-Access-Challenge` with `EAP-Request/TLS` (TLS ServerHello + Certificate + ServerHelloDone).
5. Supplicant sends `EAP-Response/TLS` (TLS ClientHello).
6. Server replies `RADIUS-Access-Challenge` with `EAP-Request/TLS` (TLS Finished, certificate request).
7. Supplicant sends `EAP-Response/TLS` (TLS Certificate, ClientKeyExchange, CertificateVerify, ChangeCipherSpec, Finished).
8. Server validates and replies `RADIUS-Access-Accept` with `EAP-Success` and the tunnel attributes.

The complete handshake is 6-8 round trips and fits comfortably under 1.5 seconds on a healthy LAN.

### 3. RADIUS Tunnel Attributes for VLAN Steering

When FreeRADIUS returns `RADIUS-Access-Accept`, it can include `Tunnel-Type=VLAN(13)`, `Tunnel-Medium-Type=802(6)`, and `Tunnel-Private-Group-ID=200` to tell the authenticator to move the port into VLAN 200. The 9300 implements this with:

```
interface GigabitEthernet1/0/12
 authentication host-mode multi-domain
 authentication port-control auto
 authentication event fail action authorize vlan 666
 authentication event no-response action authorize vlan 999
 authentication order dot1x mab
 authentication vlan 200
 mab
 dot1x pae authenticator
```

The auth-manager then applies the policy: `VLAN 200` for staff, `VLAN 666` for `auth fail`, `VLAN 999` for `no-response` (MAB miss), and `VLAN 1` for unauthorized. This is the heart of NAC — the same physical port serves different VLANs depending on the identity.

### 4. MAB Fallback and Quarantine

MAB (MAC Authentication Bypass) is the supplicant-less mode. The authenticator reads the source MAC, presents it as the RADIUS `User-Name`, and lets the RADIUS server decide. FreeRADIUS's `mab.conf` checks the MAC against an OUI allow-list and a per-device ACL.

The MAB policy in the change:

1. Try 802.1X for 30 seconds.
2. On `no-response`, fall back to MAB.
3. On MAB failure, quarantine to VLAN 999 for 10 minutes.
4. After 3 quarantine events in 24 hours, err-disable the port and alert.

A vendor firmware push that changes 30 MACs in 60 seconds will fail MAB; the simulator shows the chain.

### 5. CoA — Change of Authorization (RFC 5176)

CoA is the reverse direction: the authentication server pushes a policy change to the authenticator. Common uses: re-authenticate a session, bounce a port after a posture remediation, change a VLAN. CoA uses UDP/3799 and a new RADIUS packet type `Code 43 = CoA-Request`. The 9300 implements `CoA-Request` with `Acct-Session-Id` to identify the session.

### 6. Capacity, Certificates, and Operations

FreeRADIUS 3.2 on a 4-core VM handles 1,000 authentications/second at 5% CPU. The bottleneck is usually the cert validation path, not the RADIUS UDP I/O. Use OCSP stapling (RFC 6960) on the FreeRADIUS box and CRL fallback at 1-hour refresh. The lab's CA is the internal AD CS at `pki.research.lab`, with a 5-year root and 2-year issuing CA. The simulator models the path from `CN=cfo-laptop.research.lab` to the issuing CA and the OCSP check.

## Build It

The deliverable lives in `code/main.py` — a 200-line Python simulator that runs the 802.1X EAP-TLS state machine on a synthetic FreeRADIUS instance, plus a MAB fallback simulator. Stdlib-only, type-annotated, prints a design report that lists session IDs, RADIUS attributes, VLAN outcomes, and the certificate validation path.

Run it from the lesson root:

```bash
python3 code/main.py
```

The simulator does not start a real RADIUS server. It models the supplicant-authenticator-server triple as objects in memory and replays a three-session audit: a clean EAP-TLS, a `TLS alert 42` (bad cert), and a MAB fallback.

### What `code/main.py` actually does

1. Defines a `Supplicant`, `Authenticator`, and `RadiusServer` dataclass hierarchy with session state.
2. Implements the EAP-TLS handshake as a small step machine: identity, server-hello, client-hello, finished, access-accept.
3. Validates the supplicant certificate against a tiny built-in CA chain (root + issuing CA), checking CN, SAN, notBefore, notAfter, and serial.
4. Builds a `RADIUS_ACCESS_ACCEPT` with `Tunnel-Type=VLAN(13)`, `Tunnel-Medium-Type=802(6)`, `Tunnel-Private-Group-ID=200`.
5. Runs a MAB fallback session: identity is the MAC, the OUI allow-list resolves to a printer, `Tunnel-Private-Group-ID=300`.
6. Runs a `TLS alert 42` failure path for a revoked laptop and reports the failure reason.
7. Prints a 60-line design report with sessions, RADIUS attributes, VLAN outcomes, and an executive summary.

The design report is the artifact you hand to a security review. It is also the contract the simulator enforces: every EAP-TLS session must end with an `Access-Accept` and tunnel attributes, every MAB must resolve through the OUI allow-list, every cert failure must produce a specific alert code.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| Clean EAP-TLS for `cfo-laptop.research.lab` | Session state ends `AUTH`, VLAN 200, cert chain valid | PASS — built-in CA validates |
| `RADIUS-Access-Accept` with tunnel attributes | `Tunnel-Type=VLAN`, `Tunnel-Private-Group-ID=200` present | PASS — printed in report |
| `TLS alert 42` (bad cert) for revoked laptop | Session ends `AUTH_FAIL`, no VLAN assigned, alert 42 raised | PASS — simulated |
| MAB fallback for printer OUI | Session ends `AUTH_MAB`, VLAN 300, OUI matched | PASS — `00:1b:a9` resolves |
| CoA bounce of a session | `CoA-Request` → `CoA-ACK`, session returns to `AUTH` | PASS — printed in report |
| 802.1X + MAB + CoA telemetry in design report | Single stdout page, per-session attributes visible | PASS — `print_report()` produces it |
| `python3 -m py_compile` | Clean compile, no warnings | PASS — verified at run time |

## Ship It

Outputs land in `outputs/`:

- `outputs/nac_design.txt` — human-readable report, suitable for the change ticket.
- `outputs/sessions.json` — every session, with state, VLAN, RADIUS attributes, cert details.
- `outputs/coa_packets.txt` — CoA flow log, including Acct-Session-Id references.

The lesson concludes when you can run the simulator and read the RADIUS attributes out loud to a security review.

## Exercises

1. **Cert chain depth.** FreeRADIUS 3.2's default `ca_file` only trusts the issuing CA, not the root. Configure `chain_cache_size = 32` and `verify_depth = 4` in `eap.conf`. Test what happens when the supplicant presents a cert signed by a 3-deep chain.
2. **OCSP stapling.** Configure the FreeRADIUS box to staple OCSP responses for the issuing CA. What is the latency delta versus CRL lookup at 1-hour refresh?
3. **MAB storm.** A vendor firmware push changes 30 printer MACs in 60 seconds. Design the MAB rate-limit and quarantine timer to keep the 9300's auth-manager CPU below 30%. Use `authentication event fail retry 3 action authorize vlan 999` as a starting point.
4. **RADIUS shared secret rotation.** With 12 switches and 2 FreeRADIUS servers, what is the operational cost of rotating the shared secret quarterly? Draft a runbook that uses `radsec` (RADIUS over TLS, RFC 6614) to avoid the secret-on-the-wire problem.
5. **CoA for posture remediation.** A laptop was admitted to VLAN 200 but posture later flagged an out-of-date AV signature. Send a `CoA-Request` with `Acct-Session-Id` and `Tunnel-Private-Group-ID=888` to push the laptop to a remediation VLAN. What happens to existing TCP sessions?
6. **Multi-vendor parity.** Translate the 9300 EAP-TLS policy into Aruba CX 6100 (`port-access auth-mode 802.1x`) and Juniper EX4100 (`protocols dot1x authenticator`). Identify two semantic differences in MAB retry behavior.

## Key Terms

| Term | Definition |
|---|---|
| 802.1X | IEEE 802.1X-2010 port-based NAC; the standard for wired and wireless port authentication |
| EAP-TLS | Extensible Authentication Protocol with TLS inside (RFC 5216); mutual cert auth |
| Supplicant | Software on the end device that speaks EAP to the authenticator |
| Authenticator | The switch or controller that proxies EAP between supplicant and auth server |
| FreeRADIUS | Open-source RADIUS server; in this lab on Rocky Linux 9, version 3.2 |
| MAB | MAC Authentication Bypass; supplicant-less mode where MAC is the identity |
| CoA | Change of Authorization (RFC 5176); server pushes policy changes to the authenticator |
| `Tunnel-Private-Group-ID` | RADIUS attribute (Type 81) carrying the target VLAN ID |
| `Tunnel-Type=VLAN(13)` | RADIUS attribute (Type 64) signaling that the tunnel is a VLAN |
| EAPOL | EAP over LAN; the 802.1X Layer 2 encapsulation |
| `RADIUS-Access-Accept` | RADIUS packet type (Code 2) granting the session |
| OCSP | Online Certificate Status Protocol (RFC 6960); real-time cert revocation check |
| Quarantine VLAN | A restricted VLAN (here VLAN 999) used after auth failure |

## Further Reading

- IEEE Std 802.1X-2010 — *Port-Based Network Access Control*.
- RFC 3748 — *Extensible Authentication Protocol (EAP)* (Aboba, Blunk, Vollbrecht, Carlson, Levkowetz, 2004).
- RFC 5216 — *The EAP-TLS Authentication Protocol* (Simon, Aboba, Hurst, 2008).
- RFC 3579 — *RADIUS Support for EAP* (Aboba, Calhoun, 2003).
- RFC 5176 — *Dynamic Authorization Extensions to RADIUS* (Chiba, Dommety, Eklund, Mitton, Aboba, 2008).
- RFC 6614 — *RADIUS over Transport Layer Security (RadSec)* (Winter, McCauley, Venaas, Wierenga, 2012).
- RFC 6960 — *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol* (Santesson, Myers, Ankney, Malpani, Galperin, Adams, 2013).
- FreeRADIUS 3.2 — *Configuration Files Reference* and *eap.conf(5)*.
- Cisco Systems, *Catalyst 9300 Security Configuration Guide — Configuring 802.1X*.
- Aruba Networks, *ArubaOS-CX 10.13 Access Security Guide*.
- Juniper Networks, *Day One: Securing the EX Series — 802.1X and MAB*.
- Cisco Live BRKCRS-3501 — *Campus NAC with 802.1X and ISE*.
- Packet Pushers, *Heavy Networking 522 — Building a Campus NAC*.
- Joshua Hill, *The EAP-TLS Cookbook*, https://www.freeradius.org/documentation/.
