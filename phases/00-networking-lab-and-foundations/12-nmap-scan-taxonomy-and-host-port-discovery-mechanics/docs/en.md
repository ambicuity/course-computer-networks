# nmap Scan Taxonomy and Host/Port Discovery Mechanics

> nmap is not a port list — it is a decision tree over the TCP/IP stack's reactions to crafted packets. Every scan type is a choice of TCP control bits in the 16-bit flags word at offset 10–15 of the RFC 793 header: `-sS` SYN sets only SYN (0x02) and infers `open` from a SYN|ACK, `closed` from a RST|ACK, `filtered` from silence or an ICMP error; `-sF`/`-sN`/`-sX` send FIN, zero, or FIN|PSH|URG and exploit RFC 793's rule that a port with no listening socket MUST RST while an open socket ignores the segment, collapsing open and firewalled into the ambiguous `open|filtered`. `-sA` sends a bare ACK to map firewalls, never application state. `-sU` probes UDP (RFC 768) where the only closed signal is an ICMP type 3 code 3 port-unreachable and silence is again ambiguous. Host discovery (`-sn`) layers ICMP echo (RFC 792), ARP (IEEE 802.3) on the local segment, and TCP SYN/ACK to 443/80 to separate alive from dead before a single port is scanned, and the timing templates T0–T5 trade per-probe delay against stealth and accuracy. This lesson builds a runnable scanner model that forges a 20-byte TCP header with a correct RFC 1071 one's-complement checksum over the pseudo-header and shows, for the same target, how seven flag menus produce seven different state vocabularies.

**Type:** Build
**Languages:** Python, nmap, shell
**Prerequisites:** TCP three-way handshake and the RFC 793 state machine, IPv4/UDP header layout, ICMP types, ARP on a LAN
**Time:** ~80 minutes

## Learning Objectives

- For each nmap scan type (`-sS`, `-sT`, `-sF`, `-sN`, `-sX`, `-sA`, `-sU`), name the exact TCP/UDP flags sent and the RFC 793/768 response that maps to each reported state.
- Explain why FIN, NULL, and Xmas scans report `open|filtered` instead of `open`, and why Windows hosts break this inference.
- Build a minimal 20-byte TCP header with a correct RFC 1071 one's-complement checksum over the IPv4 pseudo-header, and verify the checksum field is non-zero.
- Distinguish host discovery (`-sn`, `-PE`, `-PS`, `-PR`) from port scanning, and order them so a dead host never wastes a 65535-port scan.
- Pick a timing template T0–T5 from a link's RTT and IDS tolerance, and compute the serial air time of a full-range scan.
- Read an nmap output table and state, for each port, which probe would disambiguate `open|filtered` into `open` or `filtered`.

## The Problem

A pen-tester is handed a `/24` at `203.0.113.0/24` with 254 live candidates and a 30-minute window. She runs `nmap 203.0.113.0/24` and gets back 254 lines of `Host is up` but only three `open` ports across the whole range — every other port reads `filtered`. The client asks "are those servers really only running three services, or did your scan lie?" She cannot answer without knowing *which* probe produced `filtered`, *why* a SYN scan reports `open|filtered` differently than a FIN scan, and whether a stateless firewall in front of the hosts is dropping SYN but letting FIN through. The raw nmap output is evidence; the taxonomy of probes and the RFC reactions they rely on are the theory that turns evidence into a verdict.

The deeper problem: nmap reports port *states*, not ports. A port is a 16-bit number in the TCP/UDP header; a state is an inference the scanner draws from a packet the kernel did or did not send back. Two scans of the same host can disagree because they asked different questions. To use nmap defensibly — and to write a scanner of your own — you have to know which question each flag combination asks and which RFC clause supplies the answer.

## The Concept

### The TCP header flags word and nmap's menu

RFC 793 fixes a 20-byte TCP header. The flags live in a 16-bit word at byte offset 12 (the data offset occupies the high 4 bits, then 6 reserved bits, then 6 control bits). The six control bits are, low to high: `FIN` (0x01), `SYN` (0x02), `RST` (0x04), `PSH` (0x08), `ACK` (0x10), `URG` (0x20). nmap's entire TCP scan taxonomy is a menu over these bits plus the choice of UDP (no flags, RFC 768).

| Scan | Flags set | What it asks the kernel |
|---|---|---|
| `-sS` SYN | SYN | "Would you complete a handshake?" |
| `-sT` connect() | SYN (via socket API) | Same, but the OS finishes the 3-way handshake |
| `-sN` NULL | (none) | "Do you RST a segment with no control bits?" |
| `-sF` FIN | FIN | "Do you RST a bare FIN?" |
| `-sX` Xmas | FIN\|PSH\|URG | "Do you RST a lit-up tree?" |
| `-sA` ACK | ACK | "Do you RST an out-of-state ACK?" |
| `-sU` UDP | — (UDP) | "Do you reply on a UDP socket?" |

The crucial insight: NULL, FIN, and Xmas all ask the *same* question with different costumes. RFC 793 §3.4 says a segment that does not match an existing connection and carries neither SYN nor RST "must be dropped" if there is a listener, but a port with no listener sends RST. So an open port is silent, a closed port RSTs, and a firewalled port is silent — which makes silence ambiguous.

### SYN scan and the half-open advantage

`-sS` is nmap's default when run as root. The scanner sends a bare SYN. Three outcomes, each grounded in RFC 793:

| Target reply | Flags | Inferred state |
|---|---|---|
| SYN\|ACK | SYN+ACK | **open** — a listener accepted the half-open connection |
| RST\|ACK (or RST) | RST | **closed** — no listener, kernel reset per §3.4 |
| No reply, or ICMP type 3 | — | **filtered** — a firewall dropped the SYN or sent `net-unreachable`/`host-unreachable`/`admin-prohibited` |

The "half-open" label comes from the fact that on seeing SYN\|ACK the scanner immediately sends RST instead of the final ACK of the three-way handshake. The connection is never established, so no application `accept()` ever fires and most server logs never record it. That is why SYN scan is stealthier than `-sT`, where `connect()` completes the handshake and the daemon sees a real (then instantly closed) connection. The trade-off is that `-sS` requires raw sockets and root; `-sT` works unprivileged.

### FIN, NULL, and Xmas: the open|filtered trap

These three scans send a segment that RFC 793 does not associate with connection opening. The inference table is identical for all three:

| Target reply | Inferred state |
|---|---|
| RST | **closed** |
| No reply | **open\|filtered** |

`open|filtered` is nmap's honest "I cannot tell." An open port drops the segment (no matching SYN to pair it with); a stateful firewall may also drop it. They are indistinguishable from the scanner's seat. The scan is cheap and quiet, so it is useful *after* a SYN scan has already found open ports — to confirm a port is unfiltered, or to find closed ports whose firewall would drop a SYN.

The famous caveat: Microsoft Windows (and some embedded stacks) RST on *all* non-SYN segments regardless of whether a listener exists, because their TCP does not implement the RFC 793 drop-on-no-listener rule strictly. Against such a host, FIN/NULL/Xmas report every port as `closed`, and the scan is worse than useless. The inference relies on RFC conformance that is not universal.

### ACK scan: mapping the firewall, not the port

`-sA` sends a bare ACK to a port with no established connection. RFC 793 says the correct response is RST — for *both* open and closed ports, because there is no connection block to ACK. So an RST tells the scanner nothing about application state; it only proves the segment reached a TCP stack that is willing to reset it. The state vocabulary collapses to two values:

| Target reply | Inferred state |
|---|---|
| RST | **unfiltered** |
| No reply | **filtered** |

ACK scan is the right tool when you already know the open ports (from a SYN scan) and want to know *which* ports a stateless firewall is dropping. A stateful firewall that tracks connection state will drop an ACK with no matching SYN, so `-sA` reports it `filtered` — which is the signature that distinguishes stateful from stateless filtering. See `assets/nmap-scan-taxonomy-and-host-port-discovery-mechanics.svg` for the full probe/response/state matrix.

### UDP scan: silence as the default

UDP (RFC 768) has no handshake and no flags; the 8-byte header is source port, dest port, length, checksum. A UDP scan sends an empty (or payloaded) datagram and waits. The inference is the weakest in nmap's toolbox:

| Target reply | Inferred state |
|---|---|
| Application payload | **open** |
| ICMP type 3 code 3 (port unreachable) | **closed** |
| ICMP type 3 code 1/2/9/10/13 | **filtered** |
| No reply | **open\|filtered** |

The problem is that most UDP services do not respond to empty datagrams — DNS needs a query, SNMP needs a community string. So a truly open DNS port that receives a zero-length payload stays silent and is reported `open|filtered` by default. nmap's `-sV` (service detection) and `--version-intensity` send protocol-specific probes (a DNS `A?` query for 53, an SNMPv2 get-request for 161) to convert `open|filtered` into `open`. Additionally, RFC 1812 §4.3.2.3 limits ICMP error rate to one per 500 ms per source, so on a host with many closed UDP ports nmap can under-report `closed` because the rate-limited ICMP never arrives — this is why UDP scans are slow and nmap retransmits.

### Host discovery: finding the alive set first

A full TCP scan of 65535 ports against a dead host is pure waste. nmap runs a **host discovery** phase (`-sn`, formerly `-sP`) first to build the alive list. On an Ethernet LAN the probe stack is layered:

1. **ARP request** (`-PR`, IEEE 802.3 + ARP) — definitive on the local subnet; an ARP reply means the NIC is up regardless of the IP stack.
2. **ICMP echo** (`-PE`, RFC 792 type 8 → type 0) — the classic ping; often blocked by edge firewalls.
3. **TCP SYN to 443** (`-PS443`) and **TCP ACK to 80** (`-PA80`) — when ICMP is blocked, an RST or SYN|ACK proves the host is reachable.
4. **ICMP timestamp** (`-PP`) and **address-mask** (`-PM`) — older RFC 792 variants for hosts that answer timestamp but block echo.

`-sn` skips the port scan after discovery; `nmap -sn 203.0.113.0/24` returns only the alive list. On a single host with no `-sn`, the discovery probes run first, and if all of them fail nmap reports `Host seems down` and stops — unless `--reason` or `-Pn` forces a full scan anyway. Ordering matters: the cheapest, most definitive probe (ARP) runs first; expensive full-range scans run only against confirmed-live hosts. `code/main.py` models this separation with `host_discovery()` returning a verdict before `run_scan()` ever touches a port.

### The TCP checksum, forged packets, and why root matters

A raw SYN scan must emit a valid IP/TCP packet or the target will drop it before the kernel's TCP layer ever sees it. The TCP checksum (RFC 1071, RFC 793) covers a 12-byte **pseudo-header** (source IPv4, dest IPv4, zero byte, protocol = 6, TCP segment length) concatenated with the TCP header and payload. The checksum is the one's complement of the one's-complement sum of all 16-bit words, padded with a zero byte if the segment is odd-length. Because it covers the pseudo-header, a sender cannot precompute it — it depends on the source and destination addresses, which change per target.

`code/main.py` implements `tcp_checksum()` and `build_tcp_segment()`: it packs a 20-byte header (sport, dport, seq, ack, data-offset+flags, window=8192, checksum placeholder, urgent=0), computes the checksum over the pseudo-header, and writes it into bytes 16–17. The demo forges a SYN to `:22` and prints the hex — that is the exact bytes a raw socket would send. This is why `-sS` needs root: only raw sockets (`SOCK_RAW`, `IPPROTO_TCP`) let a process set its own source port, sequence number, and flags, and therefore emit a SYN without the kernel's three-way handshake completing behind it.

### Timing templates: the T0–T5 dial

nmap bundles dozens of timing knobs into six templates. The dominant effect is per-probe delay and retry behavior:

| Template | Per-probe delay | Stealth / IDS | Use when |
|---|---|---|---|
| T0 paranoid | ~5 s serial | near-invisible | slow IDS evasion, fragile links |
| T1 sneaky | ~1.5 s | low signature | cautious scanning |
| T2 polite | ~0.4 s | polite to load | shared bandwidth |
| T3 default | ~0.1 s | balanced | general use |
| T4 aggressive | ~0.01 s, parallel | noisy | fast reliable LAN |
| T5 insane | ~0, no retries | loudest, least accurate | trusted, very fast LAN only |

The serial air time of a 65535-port scan is roughly `ports × delay`. At T3 that is ~6553 s (~1.8 h) serial; nmap parallizes across hosts and ports, so real wall time is far lower, but the dial shows why T5 on a lossy WAN produces false `filtered` (it skips the retransmit that would have caught a dropped SYN). The model in `code/main.py` prints the per-template serial air time for a 7-port scan: T0 ≈ 35 s, T4 ≈ 0.07 s — a 500× spread from one flag.

## Build It

1. Read `code/main.py`. It models a target host as a port table plus per-probe firewall verdicts, and the kernel as RFC 793 response functions `respond_syn`, `respond_stealth`, `respond_ack`.
2. Run `python3 code/main.py`. Confirm the seven scan tables print different state vocabularies for the *same* port set — note how port 3306 (`open` but `fw_tcp_syn=drop`) reports `open` nowhere except the UDP table, where it is `open`.
3. Inspect the forged SYN segment line: a 20-byte hex string with a non-zero checksum at bytes 16–17. Decode it by hand: `d431` = sport 54321, `0016` = dport 22, then seq, ack, `5002` = data-offset 5 + flags 0x02 (SYN).
4. Edit the `_sample_host()` topology: set port 8080 to `fw_tcp_ack="drop"` and rerun `-sA` — watch 8080 flip from `unfiltered` to `filtered`, the signature of a stateful firewall.
5. Change the timing template passed to `run_scan` (edit `main()`) and compare the serial air-time line across T0…T5.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a port is truly open | SYN scan reports `open`; connect scan agrees; service probe (`-sV`) returns a banner | Three independent probes agree on `open` and a version string |
| Disambiguate `open\|filtered` | Re-scan with `-sS`; if SYN gets SYN\|ACK it is `open`, if silent it is `filtered` | The port resolves to a single state, not a compound |
| Detect a stateful firewall | `-sA` reports `filtered` where `-sS` also reports `filtered`, but LAN ARP shows the host up | ACK dropped, RST absent — stateful, not just absent |
| Find closed ports behind a SYN-dropping firewall | `-sF`/`-sN` report `closed` where `-sS` reported `filtered` | FIN gets RST where SYN was silently dropped |
| Pick a timing template | RTT ~10 ms, trusted LAN, IDS absent → T4; lossy WAN, IDS present → T1 | Full-range scan finishes in the window with no false `filtered` from missed retransmits |
| Verify host liveness cheaply | `-sn` + ARP on LAN returns alive list in <1 s, no port probes sent | Dead hosts never trigger a 65535-port scan |

## Ship It

Produce one artifact under `outputs/prompt-nmap-scan-taxonomy.md`:

- An annotated scan report for a target you define (the `code/main.py` sample host or your own), showing the seven probe tables side by side, the forged SYN segment with its decoded header fields, and a per-port verdict that resolves every `open|filtered` into `open` or `filtered` with the probe that did it.
- A firewall map: for each port, the SYN/FIN/ACK/UDP result and the conclusion "stateful filter", "stateless filter", "no filter", or "host drops ICMP".
- A timing justification: the template you would pick for a 254-host `/24` over a 10 ms LAN with a 30-minute window, with the arithmetic.

Start from the printed output of `code/main.py` and annotate it with the failure mode you exercised (the `fw_tcp_syn=drop` port is the canonical one).

## Exercises

1. Port 3306 in the sample host is `open` but `fw_tcp_syn="drop"`. Predict the output of `-sS`, `-sF`, `-sA`, and `-sU` for that port *before* running, then run `code/main.py` and reconcile any mismatch. Which scan, if any, reveals that the port is actually open?
2. A Windows host reports every port as `closed` under `-sF`. Explain the RFC 793 non-conformance that causes this, state which scan you would run instead, and justify why your replacement does not depend on the drop-on-no-listener rule.
3. Forge a RST segment against port 80 of the sample host: modify `build_tcp_segment` to send `TCPFlag.RST` with `ack=1`, compute the checksum, and print the hex. Explain why a scanner would send a RST immediately after receiving SYN|ACK in a `-sS` scan.
4. A `-sU` scan of a host with 1000 closed UDP ports reports only ~60 as `closed` and the rest as `open|filtered`. Name the RFC 1812 rate-limit that causes this and describe how nmap's retransmit and `--min-rtt-timeout` interact with it.
5. Design a host-discovery sequence for a target on a different continent behind an edge firewall that blocks ICMP echo but permits 443. List the probes in order, the RFC each relies on, and the response that would mark the host `up`.
6. Compute the serial air time of a full 65535-port `-sS` scan at T2 (0.4 s/probe) and at T4 (0.01 s/probe). Then argue, using nmap's parallelism across ports, why the real wall time is not the serial number — and give one scenario where the serial number *is* the right estimate (hint: a single port, a strict IDS).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SYN scan (`-sS`) | "stealth scan" | A half-open TCP probe: send SYN, infer state from SYN\|ACK / RST / silence, send RST instead of completing the handshake |
| open\|filtered | "maybe open" | nmap's honest compound state: silence is ambiguous between an open port that drops the probe and a firewall that drops it — FIN/NULL/Xmas/UDP produce it |
| Half-open | "incomplete handshake" | The connection never reaches ESTABLISHED; the scanner sends RST on SYN\|ACK so no `accept()` fires and most daemons never log it |
| ACK scan (`-sA`) | "firewall scan" | Sends bare ACK; RST means `unfiltered`, silence means `filtered` — it maps the firewall, never the application state |
| Pseudo-header | "the TCP checksum input" | A 12-byte synthetic prefix (src IP, dst IP, zero, proto=6, length) that the RFC 1071 checksum covers so a forged segment is bound to its addresses |
| Host discovery (`-sn`) | "ping sweep" | Pre-scan phase that builds the alive list via ARP/ICMP/TCP-SYN probes so dead hosts never receive a port scan |
| Timing template T0–T5 | "speed setting" | A bundle of per-probe delay, retry, and parallelism knobs; T0 is slow/serial/stealthy, T5 is fast/noisy/inaccurate |
| Filtered | "firewall blocked it" | No TCP reply and (for SYN) either silence or an ICMP type 3 code 1/2/3/9/10/13 — the scanner cannot reach the port to ask its state |
| Unfiltered | "reachable but unknown" | ACK-scan-only state: an RST proved the segment reached a TCP stack, but tells nothing about whether a listener exists |
| ICMP port unreachable | "UDP closed signal" | ICMP type 3 code 3 (RFC 792), the only definitive `closed` verdict in a UDP scan; rate-limited per RFC 1812 §4.3.2.3 |

## Further Reading

- **RFC 793** — Transmission Control Protocol, §3.4 (the state machine and the RST/drop rules every scan relies on).
- **RFC 768** — User Datagram Protocol (the 8-byte header and the no-handshake model behind `-sU`).
- **RFC 792** — Internet Control Message Protocol (echo, type 3 destination unreachable codes used for `filtered`).
- **RFC 1071** — Computing the Internet Checksum (the one's-complement sum over the pseudo-header).
- **RFC 1812** — Requirements for IP Version 4 Routers, §4.3.2.3 (ICMP error rate limiting that distorts UDP scans).
- **RFC 8446** — TLS 1.3 (relevant to service detection on 443 after a scan finds it open).
- **IEEE 802.3** — Ethernet frame and ARP on the local segment (host discovery `-PR`).
- Gordon "Fyodor" Lyon, *Nmap Network Scanning*, the official reference (`-sS`, `-sU`, timing, OS detection).
- Stevens, Fenner & Rudoff, *UNIX Network Programming, Vol. 1*, raw sockets and `SOCK_RAW` mechanics.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 5 (TCP state machine) and Chapter 6 (UDP).
