# RFC 5322 Header Fields and the Envelope

> Internet mail has two parallel pieces of state: the **envelope** (carried by SMTP, RFC 5321, used by MTAs to route the message) and the **headers + body** (RFC 5322, displayed by user agents). The envelope tells the receiving MTA where to deliver: `MAIL FROM:<alice@cs.washington.edu>` and one or more `RCPT TO:<bob@ee.uwa.edu.au>`. The headers tell the recipient's mail reader what to display: `From: alice@cs.washington.edu`, `To: bob@ee.uwa.edu.au`, `Subject: ...`, plus optional Date, Message-Id, In-Reply-To, References, Reply-To, and the Received trace. The two are *not* the same — `MAIL FROM` is the bounce address (often empty or a VERP-style alias), `From:` is the visible sender, and they only happen to share a value when the user agent copies them. Every MTA hop adds a `Received:` header that records its identity, the protocol used (`with ESMTPS id ...`), the timestamp, and the envelope sender. The trace is your forensic record for "where did this message actually come from".

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 12 lessons on DNS and prior exposure to SMTP (covered in this phase)
**Time:** ~75 minutes

## Learning Objectives

- Distinguish the SMTP **envelope** (RFC 5321) from the RFC 5322 **header** and explain why they are independent.
- Parse the principal RFC 5322 header fields (`From`, `To`, `Cc`, `Bcc`, `Date`, `Subject`, `Message-Id`, `In-Reply-To`, `References`, `Reply-To`, `Sender`).
- Read a chain of `Received:` headers to trace a message's path, including TLS/ESMTPS marks and timestamps.
- Identify the special header semantics: `Bcc:` is stripped from delivered copies, `Reply-To:` overrides reply routing, `Sender:` disambiguates when `From:` is a group.
- Construct a minimal RFC 5322 message with the mandatory From/Date headers and a correctly formatted `Message-Id:`.
- Recognize folded header lines (continuation lines that start with whitespace) and the obsolete `X-` private header convention.

## The Problem

You receive a message claiming to be from `ceo@example.com`, asking you to wire money. You look at the `Received:` trace and see the message originated from `203.0.113.42`, a server that has no plausible relationship to `example.com`. You realize that the `From:` header is just text — anyone can put any string there. The MTAs use the envelope to route the message; the headers are merely the contents. To diagnose spoofing, you need to read the envelope, the `Received:` trace, and the difference between the two.

The trap is treating `From:` as a security signal. It is not. The closest thing to authenticated sender is the **envelope** `MAIL FROM` (which SPF and DKIM operate on) and the `From:` only after DMARC alignment. A message with `From: ceo@example.com` is, from the MTA's perspective, just text.

## The Concept

### Envelope vs header vs body

| Layer | Defined by | What carries it | What uses it |
|---|---|---|---|
| Envelope | RFC 5321 §4.1 | SMTP `MAIL FROM` and `RCPT TO` commands | MTAs for routing and bounce handling |
| Header | RFC 5322 §3.6 | Lines `Name: value` followed by a blank line | User agents for display and threading |
| Body | RFC 5322 §3.5 | Everything after the blank line | The human reader |

The envelope is created by the sending MTA when it accepts the message from the user agent. The header and body are written by the user agent and pass through the MTAs unmodified (modulo Received: additions and Bcc: stripping). The two are connected only by convention: the user agent is supposed to copy the visible `From:` from the envelope's `MAIL FROM`, but it does not have to.

### The principal header fields (RFC 5322 §3.6)

| Header | Required | Meaning |
|---|---|---|
| `From:` | Yes | The author(s) of the message. Free-form `name <addr>` form. |
| `Date:` | Yes | The sending date-time in RFC 5322 format (e.g., `Thu, 25 Jun 2026 14:32:11 -0700`). |
| `To:` | No | Primary recipient address(es). |
| `Cc:` | No | Carbon-copy recipients (delivery equivalent to `To:`). |
| `Bcc:` | No | Blind carbon copy; stripped from header on delivery to other recipients. |
| `Subject:` | No | One-line summary shown in the mailbox listing. |
| `Message-Id:` | Strongly recommended | Globally unique identifier of the form `<local@domain>`. |
| `In-Reply-To:` | No (but recommended for replies) | `Message-Id:` of the message this is replying to. |
| `References:` | No (but recommended for replies) | List of `Message-Id:`s in the thread, newest last. |
| `Reply-To:` | No | Address to which replies should be sent (defaults to `From:`). |
| `Sender:` | No (required when `From:` has multiple authors) | Actual sender, if different from `From:` authors. |
| `Received:` | Added by each MTA | Trace record: identifying name, with-protocol id, timestamp, envelope sender. |
| `Return-Path:` | Added by final MTA | Final envelope sender after bounces are routed. |
| `MIME-Version:` | No (required for MIME bodies) | `1.0` per RFC 2046. |

`From:` is the only mandatory header besides `Date:`. RFC 5322 §3.6 says a message without `From:` is technically invalid. Some MTAs accept it anyway; some reject.

### The `Message-Id:` format

A `Message-Id:` looks like `<local-part@domain>`. The angle brackets are part of the syntax. The local part should be unique on the generating host; the domain should be a fully-qualified domain name that the generator can use for a reverse lookup. Modern generators use a random or UUID-based local part:

```
Message-Id: <CAA7h9M-Q1bG-yB2F-20260625143211-Z@example.com>
```

The angle brackets are mandatory in the field body, but many parsers tolerate their absence in poorly-written mail. Reply threading (RFC 5322 §3.6.4, RFC 5536) relies on `Message-Id:`, `In-Reply-To:`, and `References:` to assemble threads.

### Folded header lines

A header line can be folded onto continuation lines that begin with whitespace (a space or tab). Example:

```
Subject: This is a really long subject line that
        wraps onto a continuation
```

Unfolding (RFC 5322 §3.2.2) is the first step of parsing. Tools that fold and unfold incorrectly mangle addresses containing commas; this is one of the historical sources of mail bugs. RFC 5322 also allows CRLF as the line terminator (and requires it on the wire); LF-only is tolerated but discouraged.

### The `Received:` trace

Every MTA that handles a message appends a `Received:` header at the top (most recent first). The format is intentionally loose, but RFC 5321 §4.4 and RFC 5322 §3.6.7 give a canonical shape:

```
Received: from sender.example.org (sender.example.org [203.0.113.10])
        by mail.example.com (Postfix) with ESMTPS id D3F8A2C0124
        for <alice@example.com>;
        Thu, 25 Jun 2026 14:32:11 -0700 (PDT)
```

Each hop adds one such header. The topmost is the most recent hop (the receiving MTA); the bottommost is the first hop. Reading them in order tells you the actual path the message traveled — including any relaying, anti-spam scanning, or TLS upgrade that occurred.

### Envelope: the real sender

The SMTP envelope is constructed at submission time. RFC 5321 §4.1.1.2 (the MAIL command) and §4.1.1.3 (RCPT) carry the values. A typical dialog:

```
S: 220 mail.example.com ESMTP ready
C: EHLO client.example.org
S: 250-mail.example.com ... 250-SIZE 10485760 ... 250-ENHANCEDSTATUSCODES
C: MAIL FROM:<alice@cs.washington.edu>     <- envelope sender
S: 250 2.1.0 OK
C: RCPT TO:<bob@ee.uwa.edu.au>              <- first envelope recipient
S: 250 2.1.5 OK
C: RCPT TO:<carol@ee.uwa.edu.au>            <- second envelope recipient
S: 250 2.1.5 OK
C: DATA
S: 354 End data with <CR><LF>.<CR><LF>
C: From: alice@cs.washington.edu            <- header (NOT the envelope)
C: To: bob@ee.uwa.edu.au
C: Subject: Lunch?
C:
C: Hi Bob, are you free for lunch?
C: .
S: 250 2.0.0 OK
```

Note: the user agent put a `From:` in the data section, but the envelope `MAIL FROM` was already fixed at the SMTP level. The receiving MTA delivers based on envelope `RCPT TO`, not on header `To:`.

### Bcc: stripping

`Bcc:` is the only header that gets *removed* from the message on its way to other recipients. When the sending MTA expands a single message to multiple envelope recipients, it builds one wire-format copy per recipient. Each copy's headers include the visible `To:` and `Cc:` but never `Bcc:`. RFC 5322 §3.6.3 codifies this. The original copy stored in the sender's Sent folder may retain `Bcc:`; the copies the other recipients see do not.

### Reply-To and the difference between author and sender

`From:` lists who wrote the message. `Sender:` lists who actually sent it (e.g., an assistant sending on behalf of an executive). When `From:` has multiple addresses, `Sender:` becomes mandatory. `Reply-To:` overrides where replies go — useful when the author wants replies routed to a different mailbox (a support address, an autoresponder, or a private account). User agents honor `Reply-To:` by default; some allow the user to disable the override.

### Private headers and the `X-` convention

RFC 5322 §3.6.8 explicitly allows user agents to invent headers for private use. The convention since RFC 822 is to prefix them with `X-`, which the IANA will not allocate, so there are no collisions with official headers. Examples: `X-Mailer: Thunderbird 115.6`, `X-Spam-Status: No, score=...`, `X-Priority: 1 (Highest)`. Modern conventions have moved past `X-` for new headers (e.g., RFC 8058 one-click unsubscribe uses `List-Unsubscribe-Post` without the `X-`), but `X-` headers are still ubiquitous.

## Build It

1. Run `code/main.py` to parse a sample RFC 5322 message, separate envelope from headers from body, and print the `Received:` trace.
2. Author a minimal RFC 5322 message with `From:`, `Date:`, `Message-Id:`, `To:`, and `Subject:`.
3. Add `Bcc:` to a message and watch how a real MTA (or your parser) strips it from copies delivered to other recipients.
4. Send a message through a multi-hop relay and read the `Received:` chain top-to-bottom to reconstruct the path.
5. Capture an SMTP dialog with `tcpdump -w smtp.pcap tcp port 25` and identify each `MAIL FROM:` and `RCPT TO:` on the wire.

```python
# Excerpt from code/main.py
def split_envelope_headers_body(message: bytes) -> tuple[str, dict[str, str], str]:
    """Separate envelope (out of scope) from RFC 5322 header+body."""
    head, _, body = message.partition(b"\r\n\r\n")
    headers = parse_headers(head.decode("ascii"))
    return "<envelope from MAIL FROM>", headers, body
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Header parser | `parse_headers(text)` | Python `email.parser` | RFC 5322 §3.2 |
| Address parsing | `parse_address(field)` | `email.utils.parseaddr` | RFC 5322 §3.4 |
| Received trace | `trace_received(headers)` | `pypff`, `mail-parser` | RFC 5321 §4.4 |
| Message-Id generator | `new_message_id(domain)` | `email.utils.make_msgid` | RFC 5322 §3.6.4 |
| Bcc stripping | `strip_bcc(message)` | real MTAs | RFC 5322 §3.6.3 |
| Date parsing | `parse_date(field)` | `email.utils.parsedate_to_datetime` | RFC 5322 §3.3 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A small envelope-vs-headers inspector that takes a `.eml` file and prints the envelope equivalents (`MAIL FROM`, `RCPT TO`), the visible headers, and the body in separate panels.
- A `Received:` trace renderer that turns the chain into a one-line-per-hop summary with TLS marker, server name, and timestamp.
- A reference RFC 5322 message with all the canonical headers filled in and annotated.

Start from [`outputs/prompt-rfc5322-header-fields-and-envelope.md`](../outputs/prompt-rfc5322-header-fields-and-envelope.md).

## Exercises

1. Author a minimal RFC 5322 message with `From:`, `Date:`, `To:`, `Subject:`, `Message-Id:`, and a one-line body. Validate with `python3 -m email.parser`.
2. Capture an SMTP session with `tcpdump` and identify every `MAIL FROM:` and `RCPT TO:`. Compare to the `From:` and `To:` headers in the DATA section.
3. Forward a message with `Bcc:` to a friend and confirm that `Bcc:` does not appear in the copy the friend receives.
4. Reconstruct the path of a real inbound message by reading its `Received:` chain in reverse order.
5. Identify every `X-` header in a recent message. Some are diagnostic (`X-Spam-Status`); some are vendor-specific.
6. Generate a `Message-Id:` using `email.utils.make_msgid` and verify it follows the `<local@domain>` syntax.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Envelope | "the SMTP envelope" | RFC 5321 `MAIL FROM` and `RCPT TO`; what MTAs use to route |
| Header | "the message header" | RFC 5322 `Name: value` lines; what user agents display |
| Body | "the body" | Everything after the blank line in the RFC 5322 message |
| MAIL FROM | "the bounce address" | SMTP envelope sender; basis for bounces and SPF |
| RCPT TO | "the recipient" | SMTP envelope recipient; basis for delivery |
| From: | "who sent this" | Visible author; often different from envelope sender |
| Sender: | "the actual sender" | Header for who physically sent the message |
| Reply-To: | "where replies go" | Header that overrides reply routing |
| Bcc: | "blind copy" | Header stripped from copies delivered to other recipients |
| Received: | "the trace line" | Per-MTA record: name, protocol id, timestamp |
| Message-Id: | "the unique id" | `<local@domain>` identifier; basis for threading |
| Folded header | "a wrapped line" | Continuation of a header on a line starting with whitespace |

## Further Reading

- RFC 5321 — Simple Mail Transfer Protocol (envelope and transport)
- RFC 5322 — Internet Message Format (headers and body)
- RFC 2045–2049 — MIME (extensions for non-ASCII and multipart bodies)
- RFC 5322 §3.6.4 — `Message-Id:`, `In-Reply-To:`, `References:` for threading
- RFC 5321 §4.4 — `Received:` line syntax
- RFC 8058 — One-Click List Unsubscribe Post Header
- Python `email` module — reference parser for RFC 5322 messages
- `tcpdump` filter reference — capturing SMTP dialogs on port 25 / 587 / 465
