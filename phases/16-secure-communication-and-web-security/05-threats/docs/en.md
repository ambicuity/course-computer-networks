# Threats

> Web security threats span defacement, denial-of-service, data theft, stock manipulation, and man-in-the-middle attacks. Defacement: crackers replace home pages of Yahoo!, the U.S. Army, CIA, NASA, and the New York Times with funny text — repaired in hours but embarrassing. DoS (Denial of Service): a cracker floods a site with legitimate-shaped traffic until it cannot respond; a TCP SYN flood exhausts connection table slots by sending SYN packets with false source addresses and never completing the handshake. DDoS (Distributed Denial of Service): the intruder breaks into hundreds of machines and commands them all to attack simultaneously — more firepower, lower detection. Data theft: a 19-year-old Russian named Maxim stole 300,000 credit card numbers from an e-commerce site and posted them to the Internet after blackmail failed. Stock manipulation: a California student emailed a false press release about Emulex posting a large loss and the CEO resigning — the stock dropped 60%, and he made a quarter million selling short. Web security divides into three parts: secure naming (DNS), secure connections (SSL/TLS), and mobile code safety.

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Phase 14 cryptography; Phase 12 DNS and HTTP
**Time:** ~75 minutes

## Learning Objectives

- Classify web security threats into five categories: defacement, DoS/DDoS, data theft, stock/financial manipulation, and man-in-the-middle attacks.
- Explain the TCP SYN flood DoS mechanism: how false source addresses prevent tracing and how connection table exhaustion blocks legitimate connections.
- Distinguish DoS from DDoS: what makes DDoS harder to trace and harder to defend.
- Describe the Emulex stock-manipulation attack and why a fake press release on a corporate home page would have a similar effect.
- Map the three parts of web security: secure naming (DNS), secure connections (SSL/TLS), and mobile code safety.
- Identify the observable evidence for each threat type: packet captures, log entries, connection-table state, and traffic-volume anomalies.

## The Problem

One reads about web site security problems almost weekly. The situation is grim: home pages of major organizations have been attacked and replaced; sites have been brought down by denial-of-service attacks; credit card numbers have been stolen; stock prices have been manipulated by false announcements. The engineer must recognize each threat pattern, know what evidence to collect, and understand which defensive layer (naming, connection, or mobile code) applies.

## The Concept

### Defacement

The home pages of numerous organizations have been attacked and replaced by new home pages of the crackers' choosing. Sites cracked include Yahoo!, the U.S. Army, the CIA, NASA, and the New York Times. In most cases the crackers put up funny text and the sites were repaired within a few hours. The damage is reputational rather than technical, but it demonstrates that the site's defenses were breached.

### Denial of Service (DoS)

Numerous sites have been brought down by denial-of-service attacks, in which the cracker floods the site with traffic, rendering it unable to respond to legitimate queries. A classic DoS pattern is the TCP SYN flood:

| Step | Attacker action | Server response | Table state |
|------|-----------------|-----------------|--------------|
| 1 | Send SYN with false source IP | Allocate connection table slot, send SYN+ACK | Slot occupied |
| 2 | Never respond | SYN+ACK goes to forged address; slot times out (seconds) | Slot still occupied |
| 3 | Repeat thousands of times | All table slots fill | No legitimate connection gets through |

The false source addresses prevent tracing the intruder. If the attacked machine can quickly recognize a bogus request, it still takes time to process and discard — enough requests per second exhaust the CPU. These attacks are so common they do not make the news, but they cost attacked sites thousands of dollars in lost business.

### Distributed Denial of Service (DDoS)

An even worse variant: the intruder has already broken into hundreds of computers worldwide and commands all of them to attack the same target simultaneously. This approach increases firepower (hundreds of sources) and reduces detection chances (packets come from machines belonging to unsuspecting users). DDoS is difficult to defend against because the sources are distributed and numerous.

| Aspect | DoS | DDoS |
|--------|-----|------|
| Sources | Single attacker | Hundreds of compromised machines |
| Firepower | Limited by one machine | Scaled by botnet size |
| Detection | Easier (one source IP pattern) | Harder (many sources) |
| Tracing | Possible from attack origin | Requires coordinating across jurisdictions |
| Defense | Filter the source | Rate limiting, anycast, upstream filtering |

### Data theft

In one case, a 19-year-old Russian cracker named Maxim broke into an e-commerce web site and stole 300,000 credit card numbers. He approached the site owners and demanded $100,000 — if they did not pay, he would post all the credit card numbers to the Internet. They did not give in; he posted them, inflicting great damage on many innocent victims.

In 1999, a Swedish cracker broke into Microsoft's Hotmail web site and created a mirror site that allowed anyone to type in a Hotmail username and read all the person's current and archived email.

### Stock manipulation

A 23-year-old California student emailed a press release to a news agency falsely stating that the Emulex Corporation was going to post a large quarterly loss and that the CEO was resigning. Within hours, the company's stock dropped by 60%, causing stockholders to lose over $2 billion. The perpetrator made a quarter million by selling the stock short. While this was not a web site break-in, putting such an announcement on the home page of any big corporation would have a similar effect — the web site is a trusted information source.

### Man-in-the-middle attacks

Trudy intercepts Alice's outgoing packets and examines them. When she captures an HTTP GET request headed to Bob's web site, she fetches the page herself, modifies it (e.g., slashes prices to trick Alice into sending her credit card number to "Bob"), and returns the fake page. The active wiretapping disadvantage: Trudy must tap either Alice's or Bob's line, which is work. Easier alternatives exist — DNS spoofing (covered in Lesson 06).

### The three parts of web security

| Part | Question | Lesson |
|------|----------|--------|
| Secure naming | Is the resource named correctly? Is Bob's IP really Bob's? | 06 (DNS, DNSsec) |
| Secure connections | Can we establish an authenticated, encrypted channel? | 06 (SSL/TLS) |
| Mobile code safety | What happens when a site sends executable code? | 07 (Java, ActiveX, JavaScript) |

### Failure modes

- **Table-slot exhaustion**: SYN flood fills all connection slots; legitimate connections blocked.
- **DDoS amplification**: botnets scale attack volume beyond single-source defenses.
- **Reputational damage**: defacement erodes trust even when data is not stolen.
- **Financial manipulation**: false announcements move stock prices; web sites are trusted sources.
- **Untraceable sources**: false IP addresses prevent identifying the attacker.
- **Credential theft**: stolen credit card numbers or email access cause cascading damage.

`code/main.py` simulates a SYN-flood DoS attack and a DDoS attack from multiple sources, showing connection-table exhaustion and detection difficulty; `assets/threats.svg` diagrams the threat taxonomy and SYN-flood mechanism.

## Build It

1. Run `python3 code/main.py` to see a SYN flood exhaust a connection table and a DDoS from multiple sources.
2. Observe the connection-table slot count drop to zero under SYN flood; note that legitimate connections are blocked.
3. Compare the single-source DoS trace to the multi-source DDoS trace — which is harder to attribute?
4. Run the stock-manipulation simulation: a false announcement drops a synthetic stock price.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Detect DoS | Connection table state showing all slots occupied, SYN without matching ACK | Table full; SYN packets with forged source IPs; no ESTABLISHED connections |
| Detect DDoS | Traffic volume from hundreds of source IPs to one destination | Many sources, one target; no single-source pattern to filter |
| Detect defacement | Web page content hash mismatch; log of page modification | Page content changed; modification timestamp correlates with attack window |
| Detect data theft | Database query logs showing bulk export; anomalous outbound traffic | Large data egress to unknown destination; query count anomaly |

## Ship It

Create one artifact under `outputs/`:

- A threat-classification runbook (defacement, DoS, DDoS, theft, manipulation, MITM).
- A SYN-flood detection checklist (connection table state, source IP analysis).
- A DDoS incident response playbook (rate limiting, upstream filtering, anycast).

Start with [`outputs/prompt-threats.md`](../outputs/prompt-threats.md).

## Exercises

1. A SYN flood sends 5,000 SYN packets per second with forged source IPs. If the server has 8,192 connection slots and each times out after 75 seconds, how long until all slots are occupied? How many legitimate connections can be established during the attack?
2. A DDoS attack uses 500 compromised machines. Each sends 100 SYN packets per second. The target has 10,000 connection slots with a 60-second timeout. How long until exhaustion? Why is this harder to filter than a single-source DoS?
3. The Emulex stock manipulation used a press release to a news agency. How would the attack differ if the false announcement were posted on the company's own home page? What defenses apply to each vector?
4. Classify each threat into one of the three web security parts: DNS spoofing, SSL strip, malicious Java applet, SYN flood, home page defacement, credit card database theft.
5. A man-in-the-middle attack requires tapping Alice's or Bob's line. Why is this considered harder than DNS spoofing? What does DNS spoofing not require?
6. Why do DoS attacks with false source addresses prevent tracing? What protocol-level change would make source addresses verifiable?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DoS | "flood attack" | Denial of Service: legitimate-shaped traffic in great numbers; SYN flood exhausts connection table slots |
| DDoS | "botnet flood" | Distributed DoS: hundreds of compromised machines attack simultaneously; harder to trace and filter |
| SYN flood | "half-open attack" | Send SYN with forged source, never complete handshake; table slot occupied until timeout |
| Defacement | "page replaced" | Cracker replaces home page content; reputational damage, usually repaired in hours |
| Man-in-the-middle | "active wiretap" | Intercept and modify traffic in transit; requires tapping a line — harder than DNS spoofing |
| Botnet | "zombie army" | Compromised machines commanded to attack a target simultaneously; the basis of DDoS |

## Further Reading

- Anderson, R. (2008) — Security Engineering: A Guide to Building Dependable Distributed Systems
- Schneier, B. (2004) — Secrets and Lies: Digital Security in a Networked World
- Stuttard, D. and Pinto, M. (2007) — The Web Application Hacker's Handbook
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 section 8.9.1
