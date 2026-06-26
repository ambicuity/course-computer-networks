# Email Architecture and Services

> The Internet mail system is built from **two cooperating subsystems**: **user agents (UAs)** — programs like Outlook, Thunderbird, Apple Mail, or Gmail — that let humans compose, read, filter, and organise mail, and **message transfer agents (MTAs)** — always-on server processes such as Postfix, Exim, and Sendmail — that relay mail hop by hop using **SMTP on TCP port 25** (RFC 5321). Three named steps move a message from sender to recipient: **mail submission** (UA pushes to its local MSA, typically port 587 with AUTH), **message transfer** (MTA to MTA across the Internet, port 25), and **final delivery** (mailbox access, typically IMAP on port 143 or POP3 on port 110). The address format `user@dns-address` ties every recipient to a DNS name, and MX records discovered in DNS tell the sender which MTA to contact. A message has both an **envelope** (SMTP-only, used by MTAs for routing) and a **header+body** (RFC 5322, read by UAs and humans). Spam is the dominant failure mode — roughly 9 out of 10 messages — and is mitigated by SPF, DKIM, DMARC, greylisting, and content scanning.

**Type:** Build
**Languages:** SMTP, IMAP, Python (architecture simulator)
**Prerequisites:** Phase 12 Lesson 02 (DNS records, MX), Phase 6 (TCP)
**Time:** ~110 minutes

## Learning Objectives

- Identify the two subsystems of email (UA, MTA) and the three logical steps (submission, transfer, delivery) and map real products onto each role.
- Trace an email from `From:` field to recipient mailbox using the SMTP envelope and DNS MX lookup.
- Distinguish between the **envelope** (SMTP RCPT TO, MAIL FROM — used by MTAs) and the **header** (RFC 5322 From, To, Subject — read by UAs).
- Explain why mail submission uses port 587 with AUTH while mail transfer uses port 25.
- Recommend an appropriate combination of UA, MTA, and mailbox protocol for a small business versus a campus.

## The Problem

A user clicks **Send** in Gmail. The message must travel from a browser in Seattle to a recipient in Tokyo, survive 36 hours of network outages, route around blacklisted IP ranges, dodge spam folders, and end up in a specific mailbox that the recipient can read from a phone on the subway. The architecture has to handle this with **two kinds of programs** that have nothing in common except they agree on a byte-stream protocol and a message format. You must understand the split, the protocol boundaries, and where each subsystem is allowed to fail.

## The Concept

### The two-subsystem model

The Tanenbaum/Wetherall textbook splits email into two clean subsystems (Figure 7-7):

| Subsystem | Also called | Examples | Lifetime |
|-----------|-------------|----------|----------|
| **User Agent (UA)** | Mail reader, MUA, mail client | Outlook, Thunderbird, Apple Mail, mutt, Gmail web UI | Runs when the user is active |
| **Message Transfer Agent (MTA)** | Mail server, mail router | Postfix, Exim, Sendmail, Microsoft Exchange transport | Always-on daemon |

The **UA** is a user-facing program. It composes messages, manages local mailbox copies, displays messages, and lets the user file, search, or delete them. It runs only when the user is interacting with mail.

The **MTA** is a system daemon. It listens on TCP port 25, accepts connections from other MTAs, relays messages toward their destination, and queues mail for local delivery. MTAs are the workhorses — they have to be available 24/7 because they queue mail on behalf of UAs that are powered off, on airplanes, or asleep.

### The three-step journey

Mail flows through three logical steps. Each has its own protocol role:

1. **Mail submission** (step 1 in Figure 7-7) — the UA hands the message to a **Mail Submission Agent (MSA)**. RFC 6409 separates this role from the MTA proper so that authenticated, validated submission can use a different port and policy from open relay. Modern submission uses **port 587** with the SMTP **AUTH** extension (RFC 4954) to require username and password.
2. **Message transfer** (step 2) — MTAs talk to other MTAs using **SMTP on port 25** (RFC 5321). This step is what gives email its store-and-forward property: an MTA on a faraway network can hold the message for hours while waiting for the next hop to come back online.
3. **Final delivery** (step 3) — the recipient UA retrieves mail from the recipient's mailbox. Two protocols dominate: **IMAP4** on port 143 (RFC 3501, server-stored mail) and **POP3** on port 110 (RFC 1939, downloaded mail).

```text
  SENDER                                              RECIPIENT
+--------+   submit (587+AUTH)    +-------+  relay (25)  +-------+  IMAP (143)  +--------+
|   UA   | ----------------------> |  MSA  | -----------> |  MTA  | <----------  |   UA   |
| (MUA)  |                         |  MTA  |              |       |              | (MUA)  |
+--------+                         +-------+              +-------+              +--------+
                                                                 ^                    ^
                                                                 |                    |
                                                          Mailbox (mbox/Maildir)     |
                                                                 stored on server     |
                                                                                     |
                                                              recipient can also use |
                                                              webmail UA (HTTPS)     |
```

### The envelope vs. the header

A common point of confusion: an email message has **two layers of addressing**.

- The **envelope** is constructed by the sending MTA from the RCPT TO command and is invisible to the recipient. MTAs use it to route the message. It is analogous to the paper envelope in postal mail.
- The **header** is part of the RFC 5322 message body and is read by UAs and humans. It contains `From:`, `To:`, `Cc:`, `Subject:`, `Date:`, `Message-Id:`, and `Received:` lines.

In normal operation the UA puts the same address into the `From:` header and the SMTP `MAIL FROM` envelope, and the same address into the `To:` header and the `RCPT TO` envelope. But they can diverge: a mailing list may set `From: list@example.com` while sending with `MAIL FROM:<bounces@example.com>`. The envelope sender is what bounces go to; the header From is what the recipient sees.

### Services layered on the architecture

The mail architecture supports a rich set of optional services:

| Service | Where it lives | What it does |
|---------|----------------|--------------|
| Filtering | UA or MTA | Moves likely spam to Junk folder |
| Mailing lists | MTA (Listmanager, Mailman, Sympa) | Expands one address to many |
| Aliases / forwarding | MTA (`.forward` or virtual alias maps) | Redirects per-recipient |
| Auto-responders | MTA sieve / procmail | Vacation replies |
| DKIM signing | MSA | Cryptographically signs outgoing mail |
| SPF check | Receiving MTA | Rejects mail from unauthorised senders |
| DMARC | Receiving MTA | Aligns SPF + DKIM with header From |
| Greylisting | Receiving MTA | Temporarily rejects first attempt from unseen sender |
| Quarantine | MTA / separate scanner | Holds suspicious mail for review |

### Choosing protocols and ports

Standard port assignments for mail:

| Port | Protocol | Purpose |
|------|----------|---------|
| 25 | SMTP (RFC 5321) | MTA-to-MTA relay |
| 587 | Submission (RFC 6409) | UA-to-MSA, AUTH required |
| 465 | SMTPS (historic; RFC 8314) | Submission over implicit TLS |
| 143 | IMAP4 (RFC 3501) | UA mailbox access |
| 993 | IMAPS | IMAP over implicit TLS |
| 110 | POP3 (RFC 1939) | UA mailbox download |
| 995 | POP3S | POP3 over implicit TLS |

A clean architecture: **port 25 for relay, port 587 for authenticated submission, port 143/993 for mailbox reads.** Most modern providers refuse port-25 submission from residential IP ranges specifically to keep botnets from laundering spam through their MTAs.

### DNS involvement

Every email delivery depends on DNS at three points:

1. **MX lookup** — the sending MTA queries `IN MX` for the recipient domain to find which hosts accept mail.
2. **A / AAAA lookup** — the returned MX names must be resolved to IP addresses before opening a TCP connection.
3. **Reverse DNS (PTR)** — many receiving MTAs refuse mail from hosts whose forward and reverse DNS do not match.

A modern mail flow looks like:

```text
[UA] -> submit -> [MSA] -> MX query -> [Authoritative DNS]
                                          |
                                          v
                            cs.vu.nl. IN MX 10 zephyr
                            zephyr    IN A   130.37.20.10
                                          |
                                          v
                            [TCP connect to 130.37.20.10:25]
                                          |
                                          v
                            SMTP HELO/MAIL FROM/RCPT TO/DATA
                                          |
                                          v
                            [Remote MTA] -> [Mailbox]
```

### Final delivery: IMAP vs. POP3

The textbook contrasts two final-delivery protocols:

| Property | POP3 (RFC 1939) | IMAP4 (RFC 3501) |
|----------|------------------|-------------------|
| Default port | 110 | 143 |
| Mail storage | Downloaded to UA, deleted from server | Stays on server |
| Multiple UAs | Awkward (state per device) | Designed for it |
| Offline access | Yes | Partial (cached) |
| Server search | No | Yes (`SEARCH` command) |
| Folder management | Minimal | Full (`CREATE`, `RENAME`, `LIST`) |
| Server-side rules | No | Yes (`APPEND`, flags) |

POP3 is simpler but assumes a single device per user. IMAP dominates modern usage because mail is stored centrally and accessible from phone, laptop, and web browser simultaneously. Microsoft Exchange uses a proprietary IMAP-like protocol on top of HTTPS, optimised for Active Directory integration.

### Webmail as an alternative UA

Gmail, Outlook.com, and Yahoo Mail are **UAs that live in the browser**. They use HTTPS to a web server that talks IMAP to the local MTA on behalf of the user. This is an architectural variant, not a new architecture: the **MTA-MTA boundary is unchanged**, only the UA implementation differs.

## Build It

1. Run `python3 code/main.py` to simulate an email flowing through UA -> MSA -> MTA -> mailbox with envelopes, headers, and an MX lookup.
2. Modify `main.py` to add a new mailing-list expansion; observe the one-to-many fan-out.
3. Use `dig MX cs.vu.nl` and `dig A zephyr.cs.vu.nl` to confirm the two DNS steps an MTA performs.
4. Inspect `assets/email-architecture.svg` for the end-to-end diagram.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| Find the mail server for a domain | `dig MX example.com` | At least one MX with a preference number |
| Submit a test message | `swaks --to user@example.com --from me@home.test` | 250 OK from MSA |
| Read mailbox state | `openssl s_client -connect imap.gmail.com:993` then `a1 LOGIN user app-password` | OK + mailbox listing |
| Check spam posture | `dig TXT example.com` | SPF, DKIM, DMARC records present |
| Trace an email | Read `Received:` headers top-down | Each hop shows server, time, delay |

## Ship It

Under `outputs/`, deliver a one-page architecture diagram for a 50-person company showing the choice of UA, MSA, MTA, and mailbox protocol, plus a written rationale. Start with [`outputs/prompt-architecture-and-services.md`](../outputs/prompt-architecture-and-services.md).

## Exercises

1. A user sends mail from `alice@cs.example.edu` to `bob@ee.example.org`. List every component that touches the message (UA, MSA, MTA, mailbox) and what each does.
2. The sending MTA receives `MAIL FROM:<>` (empty sender). What does that mean and why is it commonly used for bounce messages?
3. Why does RFC 6409 recommend port 587 for submission and forbid open submission on port 25?
4. The recipient's domain has no MX record. Most resolvers will then fall back to an A record lookup. What problem might arise if the A record points to a host that runs only a web server, not an MTA?
5. A user complains that mail they sent 20 minutes ago has not arrived. Using `Received:` headers and MX records, list the three first places you would look.
6. Why does an organisation with strict data-residency requirements often run its own MTA rather than relying on a hosted provider?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| UA | "mail program" | User Agent: composes, displays, organises mail |
| MTA | "mail server" | Message Transfer Agent: relays mail hop by hop |
| MSA | "submission server" | Mail Submission Agent, usually on port 587 |
| MUA | "mail client" | Mail User Agent, synonymous with UA |
| Envelope | "routing info" | SMTP MAIL FROM / RCPT TO; invisible to recipient |
| Header | "human-readable addresses" | RFC 5322 From: To: Subject: |
| Submission | "hand to server" | UA -> MSA, port 587 + AUTH |
| Transfer | "server to server" | MTA -> MTA, port 25 |
| Final delivery | "read your mail" | UA reads mailbox via IMAP/POP3 |
| MX record | "where mail goes" | DNS record pointing to receiving MTA |
| IMAP | "mail stays on server" | Mailbox protocol designed for multiple UAs |
| POP3 | "mail downloads" | Mailbox protocol designed for single UA |
| Bounce | "delivery failed notice" | RFC 5321 DSN with empty MAIL FROM |

## Further Reading

- RFC 5321 — Simple Mail Transfer Protocol (SMTP)
- RFC 5322 — Internet Message Format
- RFC 6409 — Message Submission for Mail
- RFC 3501 — IMAP version 4rev1
- RFC 1939 — POP3
- RFC 4954 — SMTP Service Extension for Authentication
- RFC 7208 — SPF
- RFC 6376 — DKIM
- RFC 7489 — DMARC
- Resnick, *Internet Message Format*, 2008
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Section 7.2.1
