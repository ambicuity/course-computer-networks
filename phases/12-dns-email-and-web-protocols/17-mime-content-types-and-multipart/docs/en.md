# MIME Content Types, Transfer Encodings, and Multipart

> MIME (Multipurpose Internet Mail Extensions, RFCs 2045–2049 and 4288/4289) extends RFC 5322 so that mail bodies can carry non-ASCII text, binary attachments, multiple alternatives in the same envelope, and nested messages. Five new headers do the work: `MIME-Version:`, `Content-Type:` (`type/subtype` plus parameters like `charset=` or `boundary=`), `Content-Transfer-Encoding:` (`7bit`, `8bit`, `binary`, `quoted-printable`, `base64`), `Content-Id:`, and `Content-Description:`. The body is reorganized as a tree of parts: a `multipart/mixed` wrapper with a randomly generated `boundary=` string separates the parts; each part has its own `Content-Type` and (often) its own `Content-Transfer-Encoding`. The base64 encoding lifts arbitrary binary through 7-bit SMTP clean channels, and `quoted-printable` keeps mostly-ASCII text readable while still escaping anything above 0x7F. The recipient's user agent walks the tree, decodes each part, and renders or saves it according to its `Content-Type`.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 12 lessons on RFC 5322 and prior exposure to SMTP
**Time:** ~75 minutes

## Learning Objectives

- Identify the five MIME headers (`MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, `Content-Id`, `Content-Description`) and the version tag `1.0`.
- Distinguish `Content-Type` types: `text`, `image`, `audio`, `video`, `application`, `message`, `multipart`, `font`, `model`.
- Encode and decode base64 (`A-Z a-z 0-9 + /` with `=` padding) and quoted-printable (`=XX` for non-printables, soft line breaks as `=\r\n`).
- Build a `multipart/mixed` envelope with a `boundary=` parameter, separating a plain text part from an image attachment.
- Build a `multipart/alternative` with the same content in `text/plain` and `text/html` so the user agent can pick the best one.
- Walk a multipart MIME tree, identify each part, and assemble the body for a chosen representation.

## The Problem

You want to email a PDF to a colleague. The PDF is binary and may contain any byte, including NUL, while SMTP was designed for 7-bit ASCII with line-length limits. You also want the message to carry both a plain-text summary and the PDF so the reader can choose how to read it. RFC 5322 alone cannot do either. Without MIME, mail was effectively ASCII-only and single-part. With MIME, the same wire format carries text, HTML, images, audio, encrypted blobs, and nested messages — and the receiving user agent picks how to display each part.

The trap is treating MIME as a "format for attachments". It is much more: it is a recursive envelope around an arbitrary tree of typed parts. `multipart/alternative` lets you say "here is the same content in three forms, pick the best". `multipart/related` lets you embed images in HTML. `message/rfc822` lets you forward a complete message inside a new one. Each subtype has a specific role.

## The Concept

### The five MIME headers (RFC 2045)

| Header | Mandatory? | Example | Purpose |
|---|---|---|---|
| `MIME-Version:` | Recommended | `1.0` | Identifies the message as MIME; lets receivers branch to a MIME parser |
| `Content-Type:` | Strongly recommended | `text/plain; charset=UTF-8` | Type/subtype plus parameters (boundary, charset, name) |
| `Content-Transfer-Encoding:` | Strongly recommended | `base64` | How the body bytes are encoded for the wire |
| `Content-Id:` | Optional | `<part1@example.com>` | Globally unique identifier for referencing the part (e.g., from HTML `<img src="cid:...">`) |
| `Content-Description:` | Optional | `Photo of Barbara's hamster` | Human-readable summary shown before the part is opened |

A message without `MIME-Version:` is assumed to be RFC 5322 plain ASCII. A user agent that sees `MIME-Version: 1.0` switches into MIME mode and walks the tree starting from the top-level `Content-Type`.

### `Content-Type:` — the type/subtype model

The original RFC 1521 (now RFC 2046) defined seven top-level types; RFC 4288 added `application` siblings and refined the registry. Modern IANA registry is at `iana.org/assignments/media-types`:

| Type | Examples | Meaning |
|---|---|---|
| `text` | `text/plain`, `text/html`, `text/css`, `text/csv` | Human-readable text |
| `image` | `image/jpeg`, `image/png`, `image/gif`, `image/svg+xml` | Still images |
| `audio` | `audio/basic`, `audio/mpeg`, `audio/mp4` | Audio |
| `video` | `video/mpeg`, `video/mp4`, `video/quicktime` | Video |
| `application` | `application/pdf`, `application/json`, `application/octet-stream`, `application/zip` | Data for an application to consume |
| `message` | `message/rfc822`, `message/http`, `message/external-body` | Wraps another message |
| `multipart` | `multipart/mixed`, `multipart/alternative`, `multipart/related`, `multipart/form-data` | A container of multiple parts |
| `font` | `font/woff`, `font/ttf` | Web fonts |
| `model` | `model/vrml` | 3D models |

Subtypes can carry parameters. `text/plain; charset=UTF-8` says the body is text with the UTF-8 character set. `multipart/mixed; boundary=abc123` says the parts are separated by lines of `--abc123` and the final boundary is `--abc123--`.

### `Content-Transfer-Encoding:` — five options

RFC 2045 originally defined three; RFC 2046 added binary; RFC 3032 added `8bit`; modern usage centers on three:

| Encoding | Body bytes on the wire | Use |
|---|---|---|
| `7bit` | Pure 7-bit ASCII, lines ≤ 998 chars | Default; no encoding needed |
| `8bit` | 8-bit bytes allowed, lines ≤ 998 chars | Only safe with SMTP extension `8BITMIME` (RFC 6152) |
| `binary` | Arbitrary bytes, no line limit | Only safe with SMTP extension `BINARYMIME` (RFC 3030) |
| `quoted-printable` | 7-bit ASCII with `=XX` escapes | Mostly-ASCII text with a few non-ASCII characters |
| `base64` | 6-bit groups packed into 7-bit ASCII | Arbitrary binary data |

The 7-bit / 8-bit / binary encodings are not really "encodings" — they describe what the sender is willing to assume about the transport. `quoted-printable` and `base64` are real encodings that produce 7-bit-safe output.

### Base64 encoding (RFC 4648 §4)

Base64 splits the input into 6-bit groups, maps each to one of 64 ASCII characters:

```
index:  0..25 -> 'A'..'Z'
       26..51 -> 'a'..'z'
       52..61 -> '0'..'9'
        62    -> '+'
        63    -> '/'
       pad    -> '='
```

A 24-bit (3-byte) input block produces 4 base64 characters. An input not a multiple of 3 bytes is padded with `=` to round up: 1 leftover byte → `XX==`, 2 leftover bytes → `XXX=`. Decoding is the inverse. The 7-bit safety of base64 made it the workhorse for binary attachments before `8BITMIME` and `BINARYMIME` were widely deployed.

### Quoted-printable (RFC 2045 §6.7)

Quoted-printable keeps ASCII printable bytes as-is, but escapes anything else as `=XX` (two hex digits). Lines are limited to 76 characters; longer lines are broken with a soft line break (`=\r\n`). Examples:

- `café` (UTF-8: `c a f c3 a9`) becomes `caf=c3=a9`.
- A tab at column 75 is encoded as `=09`.
- A line longer than 76 chars gets a soft break: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=\r\naaaaaaaa`.

QP is most useful for text where most bytes are ASCII (European-language emails before UTF-8 became universal). For purely binary data it is inefficient (~3x expansion) and base64 is preferred.

### Multipart envelopes and boundaries

A `multipart/*` message is a single body that contains multiple parts, each separated by a delimiter line:

```
--boundary1
Content-Type: text/plain; charset=UTF-8

This is the first part.
--boundary1
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQKJ...
--boundary1--
```

The opening delimiter is `--boundary1`. The closing delimiter is `--boundary1--` with trailing `--`. Between delimiters, each part has its own set of MIME headers and body. `Content-Disposition:` (RFC 2183, also RFC 6266 for the `filename*=` extension) tells the user agent whether to show inline or offer a download.

The `boundary=` value must be chosen so it does not appear in any part body. RFC 2046 recommends a random-looking string; tools often use 16-32 random characters. If a boundary collides with content, the part tree is malformed and the user agent may show only the first part.

### The standard multipart subtypes

| Subtype | Use |
|---|---|
| `multipart/mixed` | Independent parts (an email body and several attachments) |
| `multipart/alternative` | Same content in multiple forms; user agent picks best |
| `multipart/related` | Parts reference each other (HTML + its inline images) |
| `multipart/digest` | Each part is a `message/rfc822` (mailing-list digests) |
| `multipart/form-data` | HTML form submissions with file uploads |
| `multipart/parallel` | (Theoretical) parts meant to be viewed simultaneously |

`multipart/alternative` is the most subtle: the parts should be ordered from least to most expressive (`text/plain` first, then `text/html`, then a richer format last). A user agent that cannot handle the richest format falls back to the next one down. RFC 2046 §5.1.4 codifies this.

### The "envelope in an envelope" recursion

`message/rfc822` lets you wrap a complete RFC 5322 message inside the body of another. This is what `mail forwarding` produces: the original message, with all its headers, becomes a single part of the new message. `message/external-body` (RFC 2046 §5.2) takes it further: the body lives somewhere else (FTP, HTTP) and only a reference is in the mail.

## Build It

1. Run `code/main.py` to build a `multipart/mixed` envelope, encode a PDF stub as base64, and walk the resulting tree.
2. Encode a small binary buffer in base64 by hand and decode it back; verify the padding rule (`=`, `==`).
3. Encode a mostly-ASCII UTF-8 string with one non-ASCII character in quoted-printable and verify the `=XX` escape.
4. Build a `multipart/alternative` with `text/plain` and `text/html`; verify both parts share the same `Message-Id:` and have the same subject.
5. Use Python's `email` module to parse a real multipart message and walk it with `walk()`.

```python
# Excerpt from code/main.py
def build_multipart(parts: list[dict], boundary: str) -> bytes:
    """RFC 2046: a multipart body with one boundary and N parts."""
    out = bytearray()
    for part in parts:
        out.extend(f"--{boundary}\r\n".encode())
        out.extend(part["headers"].encode())
        out.extend(b"\r\n")
        out.extend(part["body"])
        out.extend(b"\r\n")
    out.extend(f"--{boundary}--\r\n".encode())
    return bytes(out)
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| Base64 encode | `b64_encode(data)` | `base64.b64encode` | RFC 4648 §4 |
| Quoted-printable | `qp_encode(text)` | `quopri.encodestring` | RFC 2045 §6.7 |
| Build multipart | `build_multipart(parts, boundary)` | `email.mime.multipart` | RFC 2046 §5.1 |
| Parse multipart | `parse_multipart(raw, boundary)` | `email.message.Message` | RFC 2046 |
| Generate boundary | `random_boundary()` | `email.generator._make_boundary` | RFC 2046 §5.1.1 |
| Multipart walker | `walk_parts(message)` | `email.iter_parts` | RFC 2046 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A `multipart/alternative` template (plain + HTML) for transactional mail.
- A `multipart/mixed` template that attaches a PDF stub generated in stdlib (no external libraries).
- A small walker that prints every part of a real `multipart/*` message with its headers, encoding, and decoded length.

Start from [`outputs/prompt-mime-content-types-and-multipart.md`](../outputs/prompt-mime-content-types-and-multipart.md).

## Exercises

1. Encode the bytes `b"hi?"` and `b"hi"` in base64 and observe the `==` vs `=` padding.
2. Encode the string `"café"` in UTF-8 and then in quoted-printable; explain why QP is more compact for mostly-ASCII content.
3. Build a `multipart/alternative` with `text/plain` and `text/html` parts. Verify the boundary never appears inside either body.
4. Use Python's `email` module to parse a real message with attachments; print each part's `Content-Type`, transfer encoding, and decoded length.
5. Construct a `multipart/related` with an HTML part referencing a `Content-Id:` from an image part. Verify the `cid:` URL is found in the HTML and resolves to the image.
6. Build a `message/rfc822` wrapper that contains an entire original message (with its own headers) and verify the wrapper can be re-parsed.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| MIME | "the attachment format" | RFC 2045–2049 + 4288/4289 framework for typed, encoded, multipart bodies |
| Content-Type | "what kind of file" | `type/subtype` plus optional parameters (charset, boundary, name) |
| Content-Transfer-Encoding | "the encoding" | One of `7bit`, `8bit`, `binary`, `quoted-printable`, `base64` |
| Multipart | "multiple parts in one message" | A `multipart/*` content type with a `boundary` delimiter |
| Boundary | "the delimiter" | A `boundary=` parameter; parts are separated by `--BOUNDARY` and end with `--BOUNDARY--` |
| Base64 | "the binary encoding" | RFC 4648 §4: 6 bits per character, `A-Za-z0-9+/`, `=` pad |
| Quoted-printable | "the text encoding" | RFC 2045 §6.7: `=XX` for non-ASCII, `=\r\n` for soft breaks |
| multipart/alternative | "the same content in many forms" | Subtype ordered least-to-most expressive; UA picks best |
| multipart/mixed | "body + attachments" | Subtype for independent parts (typical email body + attachments) |
| message/rfc822 | "forwarded message" | A complete RFC 5322 message wrapped as one part of another |

## Further Reading

- RFC 2045 — Format of Internet Message Bodies (MIME Part 1)
- RFC 2046 — Media Types (MIME Part 2)
- RFC 2047 — Message Header Extensions for Non-ASCII Text
- RFC 2048 — MIME Registration Procedures
- RFC 2049 — MIME Conformance Criteria
- RFC 4288 — Media Type Specifications and Registration Procedures
- RFC 4289 — MIME Part 2 revision (re-registered types)
- RFC 4648 — The Base16, Base32, and Base64 Data Encodings
- RFC 2183 — The Content-Disposition Header Field
- RFC 6266 — Use of the Content-Disposition Header Field in HTTP (filename* extension)
- IANA Media Types registry — https://www.iana.org/assignments/media-types
