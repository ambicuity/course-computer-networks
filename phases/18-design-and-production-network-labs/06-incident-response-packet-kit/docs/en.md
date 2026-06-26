# Incident Response Packet Kit

> An incident response packet kit is the curated set of pcaps, hashes, syslog entries, timeline artifacts, and chain-of-custody documentation that an on-call network engineer hands off to the security incident response team when a network event escalates from "operational problem" to "security event." A well-built kit lets the IR team reconstruct the timeline in hours instead of days, gives legal counsel admissible evidence, and gives the post-mortem author the data needed to write a defensible root-cause analysis. This lesson ships a stdlib-only Python runbook (`code/main.py`) that enumerates the six canonical incident classes, the capture filters and tcpdump commands for each, the evidence preservation procedure (rotation, hashing, off-box transfer), a chain-of-custody log with SHA-256 verification, an analysis checklist, and a timeline correlator that joins pcap events with syslog so the responder has a single coherent view of the incident from first alarm to remediation.

**Type:** Project
**Languages:** Python (stdlib only), tcpdump, tshark, Wireshark, sha256sum
**Prerequisites:** Phase 0 (Wireshark, tcpdump), Phase 12 (DNS, HTTP, TLS), Phase 17 (integrated troubleshooting labs)
**Time:** ~150 minutes

## Learning Objectives

- Identify the six canonical network incident classes and the specific capture filter that maximizes signal-to-noise for each.
- Build a tcpdump / tshark command with rotation (`-G`, `-W`, `-C`) that bounds the capture size and prevents disk exhaustion during long-running incidents.
- Implement evidence preservation: copy to write-once storage, compute SHA-256, log the chain of custody, and verify the hash on every access.
- Construct a chain-of-custody log with at least the case ID, capturer, start/end timestamps, file name, size, SHA-256, and access history.
- Correlate pcap events with syslog entries on a unified timeline (UTC) so the responder sees application, network, and security signals side by side.
- Distinguish between operational incidents (outage, latency) and security incidents (breach, exfiltration) and produce a kit appropriate to each.

## The Problem

Your company, NetCove Inc., just had a PagerDuty fire at 14:30 UTC: edge firewall logs show 1.2 Gbps outbound from internal host 10.0.0.42 to a destination in 198.51.100.0/24, an address range your security team flags as known-malicious. The IDS signature TROJAN-EXFIL-HTTP fires 67 times in 90 seconds. The on-call network engineer — call them J. Smith — starts a tcpdump on the edge firewall mirror port, but does not know: how long to capture, where to store the file, what the SHA-256 is, who is allowed to touch the file, or how to coordinate with the IR team that just got paged. The capture runs for 15 minutes, the pcap is 4.7 GB, and J. accidentally writes it to the local /tmp on the firewall — which is wiped by the nightly logrotate at 03:00. By the time the IR team arrives, the evidence is gone.

This is the failure mode the incident response packet kit is designed to prevent. The kit is a pre-built bundle of capture commands, evidence procedures, custody log templates, and analysis checklists that the on-call engineer can deploy in seconds, not minutes. The kit's value is not in any one piece but in the discipline that every incident looks the same way: same capture filter template, same preservation procedure, same custody log fields, same timeline format. That uniformity is what makes the post-mortem tractable and the evidence admissible.

## The Concept

Source: `chapters/chapter-08-network-security.md` (defense in depth, IDS, evidence handling) and Phase 17 (integrated troubleshooting labs). The companion diagram is `assets/incident-response-packet-kit.svg`.

### The six canonical network incident classes

A network incident response kit must cover at least these six classes, each with a tailored capture filter:

| Class | Capture filter (tcpdump syntax) | Duration | Capture interface |
|-------|--------------------------------|----------|-------------------|
| Network outage | `host <affected_ip> and (port 80 or port 443 or port 22)` | 5 min | all |
| DDoS attack | `(dst port 80 or dst port 443) and tcp[tcpflags] & tcp-syn != 0` | 10 min | uplink |
| Security breach | `host <suspect_ip> and (port 22 or port 3389 or port 4444)` | 30 min | dmz |
| Latency issue | `host <affected_ip> and tcp` | 10 min | affected |
| DNS issue | `port 53` | 5 min | all |
| Rogue DHCP | `(port 67 or port 68) and ether src not <legit_dhcp_mac>` | 5 min | user-vlan |

Each filter is designed to maximize the signal-to-noise ratio for that class. A DDoS capture restricted to SYNs catches the L7 flood without recording every legitimate ACK. A breach capture restricted to management ports catches the lateral movement without recording the entire internal subnet. A rogue-DHCP capture restricted to port 67/68 with a MAC exclusion catches the rogue server's offers without recording the entire user VLAN.

### Evidence preservation: rotation, hashing, transfer

A pcap is a file. Files can be lost. The preservation procedure is a discipline that makes the loss recoverable:

1. **Rotate captures** to bound the file size. The flags `-G 300 -W 12` tell tcpdump to rotate every 300 seconds, keeping 12 files (1 hour total). A capture that runs for 4 hours produces 16 files of roughly 200 MB each instead of one 8 GB file that cannot be opened in Wireshark. The ring-buffer form `-C 200 -W 24` rotates at 200 MB, keeping 24 files.
2. **Write to a non-ephemeral location.** `/tmp` on most Linux distributions is mounted on tmpfs (RAM-backed) and cleared on reboot. Use `/var/lib/evidence/<case-id>/` or, better, an NFS-mounted evidence vault.
3. **Compute SHA-256 immediately after capture ends.** A SHA-256 of a 4 GB file takes a few seconds on modern hardware. The hash is the chain-of-custody anchor: if the file is later modified, the hash changes, and the modification is detectable.
4. **Copy to write-once storage.** `chmod 444 capture.pcap` makes the file read-only for everyone, including root. For higher assurance, copy to a WORM (write-once-read-many) filesystem or to a cloud object lock bucket.
5. **Record every access in the custody log.** Every person who reads the file, when they read it, and why. A simple text log in `/var/lib/evidence/<case-id>/CUSTODY.log` is sufficient; a database-backed log is nicer but not required.

### Chain of custody: the legal anchor

A chain-of-custody log is the legal anchor for any evidence that may end up in court. The minimum fields are:

- **Case ID** — a unique identifier (e.g., `CASE-2024-001`).
- **Incident description** — one sentence, e.g., "Suspected data exfiltration from 10.0.0.42".
- **Capturer** — full name and role of the person who started the capture.
- **Start time, end time** — ISO 8601 timestamps in UTC.
- **File name** — the path to the pcap on evidence storage.
- **File size** — bytes or megabytes.
- **SHA-256** — the hash computed at the moment of capture.
- **Storage path** — the canonical location of the file.
- **Access log** — every subsequent read by every person.

A custody log without SHA-256 is not legally defensible. A custody log without an access log is incomplete. The verification step (`custody.verify(observed_sha)`) is the mechanism by which the IR team proves at trial that the file they analyzed is the same file that was captured.

### Timeline correlation: pcap + syslog

The hardest part of incident reconstruction is correlating evidence from different sources. A pcap has timestamps from the network adapter; syslog has timestamps from the application; the firewall log has timestamps from the firewall. To unify, the responder must:

1. Force all timestamps to UTC. Local time zones, daylight saving, and clock drift are the three classic correlation bugs.
2. Pick a reference clock and normalize all sources to that clock (NTP, GPS, or simply "the firewall's clock").
3. Sort all events by timestamp and group by incident ID.
4. Look for the first and last event in each incident ID — these are the "blast radius" boundaries.

The kit's `timeline()` function does steps 1, 2, 3 in code; the responder does step 4 by inspection.

### Analysis checklist: the responder's morning routine

The analysis checklist is the responder's "first 30 minutes" routine. It is short on purpose — long checklists get skipped in the heat of an incident. The minimum items are: verify the SHA-256, load the pcap in Wireshark, check for anomalous protocols, extract HTTP objects, check DNS queries, analyze TLS SNI, look for data staging, document findings with timestamps, and generate a report.

## Build It

1. Read `code/main.py` and understand the data model: `CustodyLog` (case fields + access events), `CustodyEvent` (one row of the access log), `timeline()` (sorts events from different sources into a single UTC-ordered view).
2. Run `python3 main.py` and confirm the kit prints all six capture filters, the seven tcpdump commands, the preservation steps, the custody log, the analysis checklist, and a demo timeline.
3. Modify the `CAPTURE_FILTERS` list to add a seventh class: "VPN tunnel flapping" with a filter for ESP (protocol 50) and ISAKMP (UDP 500) packets on the WAN interface. Re-run and confirm the new row appears.
4. Add a `CustodyEvent` for yourself as the latest reader of the file, then verify the custody log still passes `custody.verify(custody.sha256)`.
5. Replace the demo timeline with a real timeline from your own company's last incident (sanitize any sensitive data first), then run the kit and confirm the events sort correctly.
6. Add a `verify_against_disk()` method that reads the file at `custody.storage_path` and returns `True` iff the on-disk SHA-256 matches `custody.sha256`. Use it to detect tampering.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Capture during an outage | pcap file with the outage filter, sized ≤ 200 MB per file | File opens cleanly in Wireshark; rotation timestamps are contiguous |
| Capture during a DDoS | pcap file with the SYN-only filter, rotated hourly | SYN rate in pcap matches firewall counter; post-mitigation SYNs drop to baseline |
| Capture during a breach | pcap file with the management-port filter, hashed and locked | SHA-256 matches; file is read-only; access log shows every reader |
| Correlate pcap with syslog | Timeline with merged pcap and syslog events | All events UTC, sorted by timestamp, gap-free |
| Generate a report | PDF or Markdown with timeline, IOCs, root cause | Report cites pcap timestamps and packet numbers as evidence |
| Hand off to legal | Custody log with all access events | Every access is logged; SHA-256 verifies on every read |

## Ship It

Produce one artifact under `outputs/`:

- A self-contained "Incident Response Packet Kit" bundle with: `chain-of-custody.pdf`, `capture.pcap`, `capture.pcap.sha256`, `syslog-correlated-timeline.md`, `executive-summary.md`, and `iocs.txt` (indicators of compromise).
- A runbook titled *"On-call engineer's first 15 minutes"* that walks through: (1) classify the incident, (2) start the right capture, (3) preserve the evidence, (4) page IR if security-class, (5) document in the timeline.
- A 1-page cheat sheet for the team room wall: the six filter templates, the seven tcpdump commands, and the chain-of-custody fields.

Start from [`outputs/prompt-incident-response-packet-kit.md`](../outputs/prompt-incident-response-packet-kit.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Add a "TLS interception suspected" incident class with a filter for TLS 1.2 renegotiations and a 15-minute capture on the egress proxy. Document the filter's design rationale.
2. Implement `verify_against_disk()` and add a `tamper_test` that modifies a single byte of the pcap and asserts the SHA-256 mismatch is detected. Confirm the test fails as expected.
3. Build a multi-source timeline: parse a 100-line syslog, a 50-line pcap timestamp list, and a 20-line firewall log; merge them on UTC timestamp and print the result. Use the real log formats from your environment.
4. Add a "preserved until" date to the custody log (e.g., 7 years for SEC-regulated industries) and a check that refuses to delete a file before that date.
5. Implement WORM enforcement in the kit: after capture, copy the pcap to an S3 object-lock bucket with a 7-year retention and a "compliance" mode that prevents deletion even by root.
6. Walk through a tabletop exercise: pick a class, run the kit end-to-end on a synthetic scenario, and write a post-mortem that cites the pcap, the custody log, and the timeline.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Capture filter | "the tcpdump expression" | A BPF (Berkeley Packet Filter) expression that selects which packets to record; tuned to maximize signal-to-noise per incident class |
| Ring buffer | "-W 24 -C 200" | A rotation scheme that keeps the last N files of M bytes; the oldest file is overwritten when a new one is created |
| Chain of custody | "who touched the file" | The legal record of every person who accessed the evidence, when they accessed it, and why |
| SHA-256 | "the file hash" | A 256-bit cryptographic hash of the file's bytes; detecting tampering requires only re-hashing and comparing |
| WORM storage | "write once, read many" | A storage tier (e.g., S3 object lock, NetApp SnapLock) that prevents modification after write |
| UTC normalization | "convert to UTC" | All timestamps in the timeline are forced to UTC; the source's local time zone and clock drift are eliminated |
| IOC | "indicator of compromise" | An observable (IP, domain, hash, file path) that signals malicious activity; collected during analysis and shared via threat-intel platforms |
| IDS signature | "the alert" | A pattern match in the IDS engine (Suricata, Snort) that fires when a rule's conditions hold; one signal among many, not proof |
| Post-mortem | "the writeup" | A retrospective document covering timeline, root cause, contributing factors, customer impact, and remediation; cites the packet kit as evidence |
| IR team | "incident response" | A cross-functional team (security, ops, legal, comms) that takes over when an incident crosses a severity threshold |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 8 §8.6 — security monitoring and intrusion detection.
- RFC 3227 — *Guidelines for Evidence Collection and Archiving* — the foundational RFC for network forensics.
- National Institute of Standards and Technology (NIST) SP 800-86 — *Guide to Integrating Forensic Techniques into Incident Response*.
- Wireshark User's Guide, Chapter 4 — capture filters and display filters, file-format reference.
- Suricata User Guide, Chapter 6 — IDS signatures, alert output, EVE JSON for downstream correlation.
- Bejtlich, R. (2013). *The Practice of Network Security Monitoring*, No Starch Press — operational network forensics.
- Ligh, M., Case, A., Levy, J., and Walters, A. (2014). *The Art of Memory Forensics*, Wiley — memory and disk evidence handling.
- Casey, E. (2011). *Digital Evidence and Computer Crime*, 3rd ed., Academic Press — legal foundations of digital evidence.
