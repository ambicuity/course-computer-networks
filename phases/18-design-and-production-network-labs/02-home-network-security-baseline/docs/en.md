# Home Network Security Baseline

> A "home network" today is a small enterprise: 15 to 50 IP endpoints (laptops, phones, TVs, smart speakers, doorbells, thermostats, baby monitors, NAS, consoles) sharing a single uplink with no professional operator on call. The lesson turns that risk into a measurable baseline by combining the **NIST SP 800-53 control families** (access control, configuration management, identification & authentication, system & information integrity, supply chain risk) with the **CIS Critical Security Controls v8** (the consumer-friendly "IG1" profile) and the **NIST IR 8425** IoT cybersecurity baseline. The deliverable is a runnable Python auditor that ingests a configuration snapshot (admin password length, firmware version, encryption mode, port forwards, UPnP, DNS, remote management, log retention), scores each control against pass/warn/fail, computes a 0-100 security posture score, and emits a prioritized 30-day hardening plan with concrete commands and an estimated cost. The same tool scales from a single-AP apartment to a 4,000 sq ft smart home with VLANs, a Pi-hole DNS sinkhole, and a managed switch.

**Type:** Project
**Languages:** Python (stdlib: dataclasses, json, hmac, hashlib, secrets, ipaddress, statistics)
**Prerequisites:** Phase 14 (Cryptography Foundations), Phase 15 (Keys, Signatures, and Authentication), Phase 16 (Secure Communication and Web Security)
**Time:** ~150 minutes

## Learning Objectives

- Translate the **CIS Controls v8 IG1** (15 controls) into specific, testable assertions about a home router and its attached devices.
- Score an arbitrary home network against the NIST **Cybersecurity Framework 2.0** functions (Identify, Protect, Detect, Respond, Recover) on a 0-100 scale.
- Generate a prioritized 30-day hardening plan with concrete CLI commands for OpenWrt, pfSense, Ubiquiti UniFi, and consumer-grade routers (Netgear Orbi, Eero, AsusWRT-Merlin).
- Audit firmware currency against the vendor's **CVE feed**, the **CISA KEV catalog**, and the IoT vendor's update cadence (NIST IR 8425 §4).
- Distinguish three VLAN topologies (flat / IoT-isolated / full segmentation) and pick the correct one for the home's device mix.
- Produce a verifiable configuration snapshot that can be diff-reviewed and committed to a private git repo as a "network as code" artifact.

## The Problem

The household has a Netgear Orbi mesh with three nodes, an ASUS RT-AX86U router at the edge, a Synology NAS with 4 TB of family photos and one security camera archive, a Ring doorbell, eight Amazon Echo devices, four Philips Hue bridges, a Roku, three Apple TVs, a Schlage Encode smart lock, eight iPhones, four laptops, two gaming consoles, and a Roomba. The router still has the default admin password, the mesh nodes run firmware that is six months old, UPnP is enabled (which means any device on the LAN can ask the router to open an inbound port), the IoT devices share the same VLAN as the laptops, and the Wi-Fi password is on a sticky note by the fridge.

Last quarter a neighbor's Ring account was hijacked because of a credential-stuffing attack on a third-party provider; the same Ring password was reused on the family NAS admin login. Three weeks ago a smart bulb on the network started sending outbound traffic to a known cryptomining pool; the family only noticed because the ISP sent a courtesy notice. The homeowner is not a network engineer, but is technically literate enough to follow a checklist and execute shell commands. The lesson is to give them a defensible baseline in two evenings.

## The Concept

A home security baseline is the same exercise as a corporate baseline — a measurable posture against a published control set — scaled down to a single operator and a household-sized asset inventory. The hard part is choosing controls that actually move the needle without paralyzing the user.

### The CIS Controls v8 IG1 profile

The **Center for Internet Security** publishes the **CIS Critical Security Controls** in tiers. **IG1** (Implementation Group 1) is the entry-level set designed for organizations with limited cybersecurity expertise and a small IT footprint — exactly the home use case. The IG1 controls are:

1. **Inventory and Control of Enterprise Assets** — know every device on the network.
2. **Inventory and Control of Software Assets** — know every firmware and OS version.
3. **Data Protection** — encrypt data at rest and in motion; backups.
4. **Secure Configuration of Enterprise Assets and Software** — change defaults, harden OS, disable unused services.
5. **Account Management** — unique accounts per user, no shared credentials, MFA where possible.
6. **Access Control Management** — least privilege, separate admin from user accounts.
7. **Continuous Vulnerability Management** — scan for CVEs monthly, patch within 30 days.
8. **Audit Log Management** — retain logs ≥ 90 days, alert on admin actions.
9. **Email and Web Browser Protections** — DNS filtering, HTTPS-only, ad-blockers.
10. **Malware Defenses** — EDR / antivirus on endpoints.
11. **Data Recovery** — tested backups with offline copies.
12. **Network Infrastructure Management** — firewalls, segmentation, no default credentials.
13. **Network Monitoring and Defense** — IDS for unusual traffic patterns.
14. **Security Awareness and Skills Training** — the operator knows the controls.
15. **Service Provider Management** — vendors meet the same baseline.

The home baseline borrows IG1 directly: every control maps to one or more specific actions the home operator can take in two evenings.

### NIST CSF 2.0 and the IoT baseline

The **NIST Cybersecurity Framework 2.0** (released February 2024) groups the same controls into six functions: **Govern**, **Identify**, **Protect**, **Detect**, **Respond**, **Recover**. The home baseline uses these as the scoring categories:

| Function | Home translation |
|---|---|
| Govern | One person owns the network. Document the asset list. |
| Identify | The auditor inventories every device, MAC, OS, firmware. |
| Protect | Encryption, segmentation, MFA, password manager. |
| Detect | Log retention, DNS filtering, anomaly alerts. |
| Respond | Documented playbook for "device compromised," "credential leak." |
| Recover | Tested backups, ISP failover, factory-reset runbook. |

The **NIST IR 8425 "Profile of the IoT Core Baseline"** (September 2024) adds IoT-specific items: device identification, device configuration, data protection, logical access to interfaces, software update, cybersecurity state awareness.

### The three VLAN topologies

A home VLAN plan is the cheapest segmentation that gives the biggest risk reduction:

1. **Flat** — single subnet (192.168.1.0/24), all devices talk to all devices. Simplest but a compromised IoT device has direct access to the NAS and the laptops. Acceptable only for very small homes with few IoT devices.
2. **IoT-isolated** — two VLANs: "trusted" (PCs, phones, NAS) and "IoT" (smart devices). Inter-VLAN rules: IoT cannot initiate connections to trusted; trusted can initiate to IoT for management. This is the **recommended default** for most homes and is achievable with a single managed switch (~$50) plus a router that supports VLANs (most consumer routers since 2020 do, including AsusWRT-Merlin, OpenWrt, pfSense, OPNsense).
3. **Full segmentation** — trusted / IoT / guest / management / cameras. Maximum protection, more complex. Justified only for high-value targets (home offices handling sensitive data, journalists, executive protection).

The lesson's tool accepts a topology level and computes the segmentation score accordingly.

### Password hygiene and authentication

Three controls do most of the work:

- **Default credentials** — change the router admin password and the admin password of every IoT device. A 16-character passphrase (4 random words) generated by a password manager beats a complex 8-character string.
- **Unique passwords per service** — password manager (Bitwarden, 1Password, KeePass) plus no reuse. The Ring/NAS reuse scenario in the problem section would have been prevented by a password manager that flags reuse.
- **MFA on admin accounts** — TOTP (RFC 6238) for any service that supports it (Apple ID, Google, Microsoft, GitHub, password manager). SMS-based MFA is acceptable fallback but is vulnerable to SIM swap (NIST SP 800-63B §5.1.3).

The auditor checks: admin password length ≥ 16, password entropy ≥ 60 bits, MFA enabled on admin accounts, no duplicate passwords across critical services.

### Firmware currency and CVE tracking

Outdated firmware is the single biggest IoT risk. The auditor checks each device's firmware version against:

1. The vendor's latest release (from the vendor's RSS feed or release-notes page).
2. **CVE** matches for the device's model and version, looked up against the **NIST NVD** (nvd.nist.gov) or the local **CVE database**.
3. The **CISA Known Exploited Vulnerabilities** catalog (cisa.gov/known-exploited-vulnerabilities-catalog) for actively exploited CVEs.
4. The **NIST IR 8425 §4.3** recommendation: critical patches applied within **14 days**, others within **30 days**.

A device is scored: **fresh** (latest version, no known CVEs), **behind** (1-90 days old, no known CVEs), **stale** (> 90 days or known CVEs), **critical** (CISA KEV match or actively exploited).

### DNS filtering as the cheapest big win

Pointing the LAN at **1.1.1.3** (Cloudflare's malware-filtered DNS) or **9.9.9.9** (Quad9) or running **Pi-hole** locally blocks 30-50% of malicious domains at the cost of one DNS server change. **DNS over HTTPS (DoH)** (RFC 8484) or **DNS over TLS (DoT)** (RFC 7858) protects the DNS channel from on-path observers. The lesson's auditor checks: DNS server addresses are filtered (not 8.8.8.8 or ISP defaults), DoH/DoT enabled on the resolver, ad-blocker on the LAN.

### Wireless encryption and authentication

**WPA3-SAE** (RFC 8110, finalized in Wi-Fi 4 / 802.11ax generation) is the modern default. WPA2-AES/CCMP is acceptable fallback. The legacy **WPA2-TKIP** and **WEP** are broken (the WEP attack recovers the key in under 60 seconds using **aircrack-ng** with the **PTW attack** from 2007). The auditor checks: encryption mode, password strength, **WPS disabled** (WPS PIN is brute-forceable in under 4 hours), **PMF (Protected Management Frames)** enabled per **IEEE 802.11w-2009**, **802.11w** mandatory in WPA3.

### Logging and detection

Most consumer routers have minimal logging. The auditor checks: syslog enabled, logs sent to a remote collector (a Raspberry Pi running syslog-ng is sufficient), retention ≥ 30 days, alert on admin login from new IP, alert on port forward creation, alert on firmware change. **Detecting** an intrusion is impossible without logs; **responding** to an intrusion is impossible without detection.

## Build It

The deliverable is `code/main.py`, a stdlib-only home network auditor that ingests a configuration snapshot (admin password length, firmware versions, encryption mode, port forwards, UPnP, DNS, remote management, log retention, MFA status), scores each control against pass/warn/fail, and emits a prioritized 30-day hardening plan.

Run it: `python3 main.py`. The output includes:

- A **per-device audit table** with firmware status, encryption mode, password strength, CVE match.
- A **per-control score** mapped to CIS v8 IG1 and NIST CSF 2.0.
- An **overall posture score** 0-100 with a letter grade (A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F < 60).
- A **prioritized 30-day hardening plan** ordered by risk reduction per hour of effort.
- A **configuration snapshot** (the input) in JSON form, suitable for committing to git and tracking drift over time.

## Use It

| Deliverable | Acceptance Criteria | Status |
|---|---|---|
| Per-device audit | 15 IG1 controls checked per device | Generated |
| Per-control score | CIS v8 IG1 + NIST CSF 2.0 mapping | Generated |
| Overall posture score | 0-100 scale, letter grade A-F | Generated |
| 30-day hardening plan | Items ordered by risk reduction per hour | Generated |
| Firmware freshness | Compared to vendor latest, CVE/NVD cross-reference | Generated |
| Configuration snapshot | JSON in/out, diff-friendly, git-trackable | Generated |
| CLI cheat sheet | Concrete commands for OpenWrt, pfSense, UniFi | Generated |

## Ship It

The artifact is `outputs/snapshot.json` (input) plus `outputs/audit-report.md` (the auditor's report) plus `outputs/hardening-plan.md` (the 30-day plan). The snapshot is the design-of-record for the home network, suitable for revisiting annually. The hardening plan is the immediate action list.

To re-audit after a change: edit `snapshot.json`, re-run the auditor, diff the two reports. Drift is visible immediately.

## Exercises

1. **CIS v8 mapping**: take the 15 IG1 controls and rewrite each as a single testable assertion for a Netgear Orbi router. For example: "admin password length ≥ 16, password != 'password', username != 'admin'." Which assertions are easy to check from the Web UI, which require SSH or API access, which require an out-of-band check (e.g., Wi-Fi password length on a sticker)?
2. **Password entropy**: a passphrase is "correct horse battery staple" (4 words from a 2,000-word list). Compute the entropy. A WPA2-PSK password has 8 characters from a 95-character set. Which is stronger, and by how many bits?
3. **Firmware audit**: pick three IoT devices in your home. Look up the latest firmware on the vendor site. How old is the installed version? Are there any CVEs in NVD for the installed version? Are any in the CISA KEV catalog?
4. **DNS filtering**: switch the LAN's primary DNS to **9.9.9.9** (Quad9) for one week. How many blocked queries does your resolver see? Compare against a week with the ISP default. Estimate the malware click-rate reduction.
5. **IoT VLAN**: design a two-VLAN plan (trusted / IoT) for a home with 30 devices, using a managed switch (TP-Link TL-SG108E or Netgear GS308E) and an OpenWrt router. Show the IP plan, the inter-VLAN firewall rules, the DHCP ranges, and the static reservations for known IoT devices.
6. **Backup verification**: the home has a Synology NAS with 4 TB of family photos. Write a backup strategy that satisfies NIST CSF 2.0 **Recover** (PR.RC-1, PR.IP-4): at least one local copy, at least one off-site copy (e.g., Backblaze B2), at least one offline / immutable copy (e.g., an external drive rotated monthly). What is the monthly cost? How do you verify a backup is restorable?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| IG1 | "CIS basic" | The Implementation Group 1 of the CIS Critical Security Controls v8 — 15 controls designed for small organizations / home users |
| CSF 2.0 | "NIST framework" | The NIST Cybersecurity Framework 2.0 — Govern, Identify, Protect, Detect, Respond, Recover; the 2024 revision added Govern |
| NIST IR 8425 | "IoT baseline" | NIST's 2024 IoT cybersecurity baseline; device ID, configuration, data protection, software update, state awareness |
| WPA3-SAE | "Wi-Fi 4" | Wi-Fi Protected Access 3 with Simultaneous Authentication of Equals (RFC 8110); replaces WPA2-PSK's vulnerable 4-way handshake |
| PMF (802.11w) | "Protected mgmt" | Protected Management Frames; prevents deauthentication attacks |
| WPS PIN | "Wi-Fi pairing" | Wi-Fi Protected Setup PIN; brute-forceable in < 4 hours; must be disabled |
| DNS filtering | "Ad blocker" | Resolving DNS through a filtered resolver (1.1.1.3, 9.9.9.9, Pi-hole) blocks 30-50% of malicious domains |
| DoH / DoT | "Encrypted DNS" | DNS over HTTPS (RFC 8484) and DNS over TLS (RFC 7858); encrypts the DNS channel |
| CISA KEV | "Active exploits" | The CISA Known Exploited Vulnerabilities catalog; CVEs that are being actively exploited in the wild |
| Password entropy | "Password strength" | log2(charset_size^length); 60 bits is a 2024-minimum for user accounts, 128 bits for admin |
| Default credentials | "admin/admin" | Every IoT vendor ships the same admin/admin or admin/password; the first thing an attacker tries |
| Segmentation | "VLANs" | Network segmentation into VLANs so a compromised IoT device cannot reach trusted endpoints |

## Further Reading

- **CIS Critical Security Controls v8** — the IG1 profile is the home baseline.
- **NIST CSF 2.0** (February 2024) — the six-function framework.
- **NIST IR 8425** (September 2024) — Profile of the IoT Core Baseline.
- **NIST SP 800-63B** — Digital Identity Guidelines: Authentication and Lifecycle Management (password rules, MFA).
- **RFC 8484** (DoH) and **RFC 7858** (DoT) — DNS privacy.
- **RFC 8110** — WPA3-SAE; **IEEE 802.11w-2009** — Protected Management Frames.
- *The Tangled Web* (Michal Zalewski, No Starch Press 2011) — browser / web attack surface (for the DNS filtering / HTTPS-only arguments).
- *Practical IoT Hacking* (Chantzis et al., No Starch Press 2021) — IoT attack methodology and defense.
- **EFF Surveillance Self-Defense** (ssd.eff.org) — the consumer-friendly version of the same controls.