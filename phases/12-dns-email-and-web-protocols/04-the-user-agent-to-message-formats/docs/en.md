# The User Agent and Message Formats

> A **user agent (UA)** is the program humans use to read and send mail — composing, replying, filing, searching, filtering, and rendering messages. The underlying message format is **RFC 5322** (the latest revision of RFC 822), which defines a primitive **envelope**, a header block of `Field: value` lines, an empty line, and a free-form body. Standard transport headers (`From:`, `To:`, `Cc:`, `Bcc:`, `Subject:`, `Date:`, `Message-Id:`, `In-Reply-To:`, `References:`, `Reply-To:`, `Received:`, `Return-Path:`) are case-insensitive ASCII text. To carry non-ASCII data — images, audio, multilingual text, binaries — **MIME** (RFCs 2045–2049, 4288/4289) adds five new headers (`MIME-Version`, `Content-Description`, `Content-Id`, `Content-Transfer-Encoding`, `Content-Type`) and a structured body tree. Seven top-level MIME types (`text`, `image`, `audio`, `video`, `model`, `application`, `message`) plus `multipart` cover every kind of attachment. Encoding schemes include 7bit, 8bit, binary, **quoted-printable** (sparse non-ASCII), and **base64** (dense binary), with lines capped at 998 octets per RFC 5322.

**Type:** Build
**Languages:** Python (RFC 5322 + MIME parser), email headers
**Prerequisites:** Phase 12 Lesson 03 (mail architecture)
**Time:** ~110 minutes

## Learning Objectives

- Enumerate the responsibilities of a UA (composition, display, filing, search, filtering) and map each to a real product.
- Decode an RFC 5322 message into its envelope, header block, and body, identifying every standard header.
- Apply the four core transport headers (`From:`, `To:`, `Cc:`, `Subject:`) and the four extended headers (`Date:`, `Message-Id:`, `In-Reply-To:`, `References:`) to construct a valid message.
- Explain why MIME was needed and walk through a `multipart/alternative` envelope showing how a UA chooses between HTML and plain text.
- Encode a small binary blob using base64 and quoted-printable, and state when each is appropriate.

## The Problem

A user clicks **Reply All** in Thunderbird. The reply must contain the original message threaded under it, preserve all attachments, add a `In-Reply-To:` referencing the original `Message-Id:`, set a sensible `Subject:`, and arrive at the recipient's UA rendered correctly regardless of whether the recipient uses Outlook, Gmail, or Apple Mail. Underneath, the message is a stream of ASCII bytes with a header block and a body that may contain nested multiparts, base64 attachments, and quoted-printable accented characters. You need to understand both the user-facing UA behaviour and the on-the-wire message format that makes it all work.

## The Concept

### What a user agent actually does

A UA — also called an **email reader** or **mail client** — provides five capabilities:

1. **Composition** — drafting new messages and replies, with assistance from address books, signature blocks, spell-check, and digital signing.
2. **Display** — rendering incoming messages, reformatting them to fit the screen, decoding quoted-printable and base64, extracting attachments, threading replies.
3. **Filing** — sorting messages into folders by sender, topic, or rule, then later searching by full-text content.
4. **Filtering** — running rules on incoming mail (e.g., "if From contains amazon, move to Shopping folder") and pre-sorting obvious spam.
5. **Disposition** — letting the user delete, reply, forward, archive, or mark a message read or unread.

UA interfaces fall into two camps:

- **Graphical** (Outlook, Thunderbird, Apple Mail, mobile mail apps) — menu/icon driven, mouse or touch input.
- **Text-based** (mutt, Pine, Elm) — single-character keyboard commands, still common in technical environments.

Functionally both styles do the same things. The text-based UAs are simpler to script and run over slow links; graphical UAs embed HTML rendering, contact photos, and conversation threading.

### RFC 5322 — the canonical message format

The textbook flags RFC 822 (1982) and its successor RFC 5322 (2008) as the format every Internet mail message uses:

```text
[envelope: SMTP-only, MAIL FROM and RCPT TO commands]
From: Alice <alice@cs.example.edu>
To: Bob <bob@ee.example.org>
Cc: Carol <carol@ee.example.org>
Subject: Lunch on Tuesday
Date: Tue, 24 Jun 2026 12:34:56 -0700
Message-Id: <20240624123456.7@cs.example.edu>
In-Reply-To: <20240620120000.3@ee.example.org>
References: <20240620120000.3@ee.example.org>
Received: from sender.example.org (sender.example.org [203.0.113.10])
        by mail.cs.example.edu (Postfix) with ESMTPS id A1B2C3
        for <bob@ee.example.org>; Tue, 24 Jun 2026 12:35:01 -0700 (PDT)

Body starts after this blank line.
Dear Bob,
  ...
```

Strict rules:

- Each header line is ASCII text in the form `Field: value`.
- Field names are case-insensitive (`Subject:` == `subject:`).
- Lines end with CRLF (`\r\n`) on the wire; UAs render LF as equivalent.
- Lines must not exceed **998 octets**, and ideally stay under 78.
- Headers may span multiple lines by starting the continuation with whitespace.
- The body is everything after the first blank line; the UA ignores most of it.
- Custom headers prefixed with `X-` are explicitly reserved for private use and will never be standardised.

### The two addressing systems

An RFC 5322 message carries **two parallel sets of addresses**: envelope (SMTP) and header (RFC 5322).

| Field | Used by | Visible to recipient? | Determines routing? |
|-------|---------|----------------------|---------------------|
| `MAIL FROM:` (envelope) | Sending MTA | No | Yes (return path on bounce) |
| `RCPT TO:` (envelope) | Sending MTA | No | Yes (final destination) |
| `From:` header | UA | Yes | No |
| `To:` header | UA | Yes | No (informational only) |
| `Cc:` header | UA | Yes | No |
| `Bcc:` header | Sending MTA | No (stripped before delivery) | Yes (extra RCPT TO) |

A mailing list can rewrite `MAIL FROM` to a bounce address while keeping a friendly `From:` header pointing at the original poster. This is why bounces go to `list-bounces@example.com` even though the recipient sees `From: "Interesting List" <list@example.com>`.

### Standard headers

RFC 5322 defines **transport-relevant** headers (Fig. 7-10) and **user-facing** headers (Fig. 7-11). Here is the canonical set with RFC 5322 reference:

| Header | Section | Example |
|--------|---------|---------|
| `From:` | 3.6.2 | `Alice Example <alice@example.edu>` |
| `To:` | 3.6.3 | `bob@example.org, carol@example.org` |
| `Cc:` | 3.6.3 | `team@example.org` |
| `Bcc:` | 3.6.3 | `audit@example.org` |
| `Subject:` | 3.6.5 | `Lunch on Tuesday` |
| `Date:` | 3.6.1 | `Tue, 24 Jun 2026 12:34:56 -0700` |
| `Message-Id:` | 3.6.4 | `<20240624123456.7@example.edu>` |
| `In-Reply-To:` | 3.6.4 | `<20240620120000.3@example.org>` |
| `References:` | 3.6.4 | `<20240620120000.3@example.org>` |
| `Reply-To:` | 3.6.2 | `replies@example.edu` |
| `Sender:` | 3.6.2 | `assistant@example.edu` (when different from From:) |
| `Received:` | 3.6.7 | (added by each MTA, top-down) |
| `Return-Path:` | 3.6.7 | `alice@example.edu` (added by final MTA) |
| `Keywords:` | 3.6.5 | `project-x, urgent` |
| `X-` private | — | `X-Spam-Score: 0.3` |

The `Received:` headers form a **reverse-traceable route**: the topmost is added by the final MTA just before delivery, and reading top-down shows the path the message took from sender to recipient. Time deltas between successive `Received:` headers tell you where the message was delayed.

### MIME — Multipurpose Internet Mail Extensions

RFC 822 was designed for English ASCII. The 1990s demand for binary attachments and non-Latin alphabets forced RFCs 2045–2049, which the textbook summarises as **MIME**. MIME keeps the RFC 822 envelope and adds structure to the body plus five new headers:

```
MIME-Version: 1.0
Content-Description: Photo of Barbara's hamster
Content-Id: <hamster42@example.com>
Content-Transfer-Encoding: base64
Content-Type: image/jpeg; name="hamster.jpg"
```

`Content-Type:` is the load-bearing field. It uses the `type/subtype` syntax and includes optional parameters.

### The seven content types

The original RFC 1521 defined seven top-level types:

| Type | Purpose | Example subtypes |
|------|---------|------------------|
| `text` | Human-readable text | `plain`, `html` (RFC 2854), `xml` (RFC 3023), `css`, `csv` |
| `image` | Still pictures | `gif`, `jpeg`, `png`, `tiff`, `svg+xml` |
| `audio` | Sound | `basic`, `mpeg`, `mp4` (RFC 3003) |
| `video` | Moving pictures | `mpeg`, `mp4`, `quicktime`, `webm` |
| `model` | 3D model data | `vrml`, `x3d+xml` |
| `application` | Other binary data | `octet-stream`, `pdf`, `json`, `zip`, `javascript` |
| `message` | Encapsulated messages | `rfc822`, `partial`, `external-body` |
| `multipart` | Composite body | `mixed`, `alternative`, `parallel`, `digest` |

`application/octet-stream` is the universal fallback when nothing more specific applies — the UA prompts the user to save the file.

### Multipart bodies

The `multipart` type lets a single RFC 5322 message carry several parts, each with its own Content-Type. Parts are delimited by a boundary string declared in the parent header:

```
Content-Type: multipart/mixed; boundary="qwertyuiop"

--qwertyuiop
Content-Type: text/plain

This is the message body.
--qwertyuiop
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
--qwertyuiop--
```

Four important subtypes:

- **`multipart/mixed`** — parts have no relationship to each other (text + attachments).
- **`multipart/alternative`** — same content in multiple forms (text + HTML + PDF); UA picks the best.
- **`multipart/parallel`** — parts must be rendered simultaneously (audio + video for a movie).
- **`multipart/digest`** — each part is a complete email message (mailing-list archive).

`multipart/alternative` should order parts from **simplest to most complex** so that pre-MIME UAs see at least the plain-text version.

### Content-Transfer-Encoding

SMTP was originally 7-bit ASCII with 1000-character lines. MIME defines five encodings to keep binary data within those constraints:

| Encoding | Use case | Line endings | Notes |
|----------|----------|--------------|-------|
| `7bit` | Pure ASCII | Preserved | Default; no encoding |
| `8bit` | 8-bit clean text (UTF-8) | Preserved | Requires SMTP 8BITMIME extension |
| `binary` | Arbitrary binary | Arbitrary | No constraints; rarely used |
| `quoted-printable` | Mostly ASCII with few non-ASCII chars | Preserved | `=XX` hex escapes for byte > 127 |
| `base64` | Arbitrary binary | Folded at 76 | 4 ASCII chars per 3 bytes; ends with `=` or `==` padding |

Quoted-printable keeps the message readable if a human inspects it; base64 is denser but opaque. Modern MTAs negotiate 8BITMIME (RFC 6152) and BINARYMIME (RFC 3030) so encodings are less often needed, but you still see them in archives.

### Threading and conversation view

Three headers (`References:`, `In-Reply-To:`, `Subject:`) let UAs reconstruct conversations:

- `Message-Id:` is the unique identifier of one message.
- `In-Reply-To:` references the immediate parent's `Message-Id:`.
- `References:` lists all ancestor `Message-Id:` values, oldest first.
- `Subject:` matching with `Re:` prefix is the legacy fallback for messages without proper threading headers.

When the UA renders a conversation view, it groups all messages with the same `References:` chain (or matching normalized `Subject:`) and shows them as a single thread.

## Build It

1. Run `python3 code/main.py` to parse a sample RFC 5322 message and a MIME multipart envelope, then enumerate every header and part.
2. Add a new MIME part (e.g., `text/html` alternative) to the sample message and confirm the parser recognises it.
3. Encode a small file with `base64 -w0` and `python3 -c "import quopri; print(quopri.encodestring(open('x.txt','rb').read()).decode())"` to compare.
4. Inspect `assets/email-message-format.svg` for the envelope/header/body structure.

## Use It

| Task | Tool | What Good Looks Like |
|------|------|----------------------|
| View raw headers | UA menu "View Source" or `mail -H` | All standard headers present, ordered |
| Decode a base64 attachment | `base64 -d` or UA "Save attachment" | Original bytes restored |
| Thread a conversation | UA "View > Threads" or `mail -t` | Messages grouped by References: |
| Test a quoted-printable body | `python3 -c "import quopri; print(quopri.decodestring(s.encode()).decode())"` | Special chars render correctly |
| Parse a MIME tree | `python3 email.parser.BytesParser` | Walkable tree of parts with Content-Type |

## Ship It

Build a Python UA in `outputs/`: read an `.mbox` file, list subjects, group by `References:`, count attachments, and detect MIME type distribution. Start with [`outputs/prompt-user-agent-message-formats.md`](../outputs/prompt-user-agent-message-formats.md).

## Exercises

1. A user sends mail with `From: alice@cs.example.edu` and `Reply-To: assistant@cs.example.edu`. Where does the recipient's reply go, and why might the sender prefer this?
2. The recipient sees the body of a message containing `=C3=A9` (UTF-8 é in quoted-printable). What header should be present so the UA decodes it as é, not as two bytes of Latin-1?
3. A message has `Content-Type: multipart/alternative; boundary="x"` with two parts: `text/plain` and `text/html`. The HTML part is malformed. Which will the UA display?
4. The `Received:` header chain shows four hops with delays of 2s, 30s, 1s, 1s. Which MTA is the bottleneck?
5. A message has `Message-Id: <>` (empty). Why is this invalid per RFC 5322?
6. Why is `Bcc:` removed from the headers delivered to the primary recipient but `To:` is not?

## Key Terms

| Term | Plain English | Technical meaning |
|------|---------------|-------------------|
| UA | "mail program" | User Agent; what humans use |
| MUA | "mail client" | Mail User Agent; synonym for UA |
| RFC 5322 | "the message format" | Current Internet Message Format (revises RFC 822) |
| RFC 822 | "the original message format" | 1982 format, now obsolete but still cited |
| MIME | "the attachment system" | RFCs 2045-2049; non-ASCII body |
| Multipart | "parts in parts" | Composite body with multiple parts |
| Base64 | "binary disguised as text" | 6-bit groups mapped to A-Z a-z 0-9 + / |
| Quoted-printable | "mostly text, escapes for special" | `=XX` hex for bytes > 127 |
| Thread | "reply chain" | Messages sharing References: / Subject: |
| Body | "the human text" | Everything after the header blank line |
| Received | "trace line" | Header added by each MTA, top-down |

## Further Reading

- RFC 5322 — Internet Message Format (current revision of RFC 822)
- RFC 2045 — MIME Part One: Format of Internet Message Bodies
- RFC 2046 — MIME Part Two: Media Types
- RFC 2047 — MIME Part Three: Message Header Extensions for Non-ASCII Text
- RFC 2049 — MIME Part Five: Conformance Criteria and Examples
- RFC 4288 — Media Type Specifications and Registration Procedures
- RFC 4289 — MIME Type Registrations
- RFC 2854 — text/html
- RFC 3023 — text/xml
- RFC 6152 — 8BITMIME SMTP Extension
- Crocker, *Internet Mail Architecture and Standards*, 2008
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 7, Sections 7.2.2 to 7.2.3
