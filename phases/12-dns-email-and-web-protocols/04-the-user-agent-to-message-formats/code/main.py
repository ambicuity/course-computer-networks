#!/usr/bin/env python3
"""RFC 5322 message format and MIME multipart parser.

Stdlib only, no network calls. Demonstrates three things:

1. Parsing RFC 5322 (formerly RFC 822) email headers: the
   name: value format with header folding (continuation lines),
   and the principal transport headers (To, Cc, Bcc, From, Sender,
   Received, Return-Path, Date, Reply-To, Message-Id, Subject)
   from Figs. 7-10 and 7-11.
2. MIME multipart parsing: detecting Content-Type, Content-Transfer-
   Encoding, MIME-Version, boundary extraction, splitting multipart/
   alternative and multipart/mixed bodies into parts (section 7.2.3
   and Fig. 7-14).
3. Base64 and quoted-printable decoding of part bodies, showing how
   binary content is carried over the 7-bit-ASCII SMTP transport.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import base64
import quopri


@dataclass
class MIMEPart:
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "text/plain").split(";")[0].strip().lower()

    @property
    def charset(self) -> str:
        ct = self.headers.get("content-type", "")
        for part in ct.split(";"):
            part = part.strip().lower()
            if part.startswith("charset="):
                return part.split("=", 1)[1].strip('"')
        return "us-ascii"

    @property
    def transfer_encoding(self) -> str:
        return self.headers.get("content-transfer-encoding", "7bit").strip().lower()

    def decoded_body(self) -> str:
        if self.transfer_encoding == "base64":
            raw = self.body.replace("\n", "").replace("\r", "")
            try:
                return base64.b64decode(raw).decode(self.charset, errors="replace")
            except Exception:
                return f"[base64 decode failed, {len(raw)} chars]"
        if self.transfer_encoding == "quoted-printable":
            try:
                return quopri.decodestring(self.body.encode()).decode(self.charset, errors="replace")
            except Exception:
                return f"[qp decode failed]"
        return self.body


def parse_headers(raw: str) -> tuple[dict[str, list[str]], str]:
    """Parse RFC 5322 headers, returning (header_map, body).

    Handles folded continuation lines (leading whitespace).
    Returns headers as a dict of name -> list of values (to allow
    multiple Received: lines).
    """
    headers: dict[str, list[str]] = {}
    lines = raw.splitlines()
    i = 0
    current_name: Optional[str] = None
    current_val: str = ""

    while i < len(lines):
        line = lines[i]
        if line == "":
            break
        if line[0] in (" ", "\t") and current_name is not None:
            current_val += " " + line.strip()
        else:
            if current_name is not None:
                headers.setdefault(current_name.lower(), []).append(current_val)
            if ":" in line:
                current_name, _, current_val = line.partition(":")
                current_name = current_name.strip()
                current_val = current_val.strip()
            else:
                current_name = None
                current_val = line
        i += 1

    if current_name is not None:
        headers.setdefault(current_name.lower(), []).append(current_val)

    body = "\n".join(lines[i + 1:])
    return headers, body


def extract_boundary(content_type: str) -> Optional[str]:
    """Extract the boundary parameter from a multipart Content-Type."""
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            return part.split("=", 1)[1].strip('"')
    return None


def parse_multipart(body: str, boundary: str) -> list[MIMEPart]:
    """Split a multipart body on the given boundary string."""
    parts: list[MIMEPart] = []
    delim = f"--{boundary}"
    segments = body.split(delim)
    for seg in segments[1:]:
        if seg.strip() == "--" or seg.strip().startswith("--"):
            break
        if seg.startswith("\n"):
            seg = seg[1:]
        if seg.endswith("\n"):
            seg = seg[:-1]
        hdrs, part_body = parse_headers(seg)
        norm: dict[str, str] = {}
        for k, v in hdrs.items():
            norm[k] = v[0] if len(v) == 1 else "; ".join(v)
        parts.append(MIMEPart(headers=norm, body=part_body))
    return parts


@dataclass
class EmailMessage:
    headers: dict[str, list[str]]
    body: str
    mime_parts: list[MIMEPart] = field(default_factory=list)

    @classmethod
    def parse(cls, raw: str) -> "EmailMessage":
        headers, body = parse_headers(raw)
        msg = cls(headers=headers, body=body)
        ct = msg.first("content-type", "text/plain")
        if "multipart" in ct.lower():
            boundary = extract_boundary(ct)
            if boundary:
                msg.mime_parts = parse_multipart(body, boundary)
        return msg

    def first(self, name: str, default: str = "") -> str:
        vals = self.headers.get(name.lower(), [])
        return vals[0] if vals else default

    def all(self, name: str) -> list[str]:
        return self.headers.get(name.lower(), [])

    @property
    def is_mime(self) -> bool:
        return "mime-version" in self.headers

    @property
    def subject(self) -> str:
        return self.first("subject", "(no subject)")

    @property
    def from_addr(self) -> str:
        return self.first("from", "")

    @property
    def to_addrs(self) -> list[str]:
        return [a.strip() for a in self.first("to", "").split(",") if a.strip()]

    @property
    def date(self) -> str:
        return self.first("date", "")

    @property
    def message_id(self) -> str:
        return self.first("message-id", "")

    @property
    def received_path(self) -> list[str]:
        return self.all("received")

    @property
    def return_path(self) -> str:
        return self.first("return-path", "")

    @property
    def reply_to(self) -> str:
        return self.first("reply-to", "")

    @property
    def in_reply_to(self) -> str:
        return self.first("in-reply-to", "")

    @property
    def keywords(self) -> list[str]:
        kw = self.first("keywords", "")
        return [k.strip() for k in kw.split(",") if k.strip()]

    def x_headers(self) -> dict[str, list[str]]:
        return {k: v for k, v in self.headers.items() if k.startswith("x-")}


SAMPLE_RFC5322 = """\
From: alice@cs.washington.edu
To: bob@ee.uwa.edu.au, carol@ee.uwa.edu.au
Cc: dan@ee.uwa.edu.au
Subject: Earth orbits sun integral number of times
Date: Fri, 18 Nov 2011 09:41:01 -0800
Message-Id: <0704760941.AA00747@cs.washington.edu>
Received: from mail.cs.washington.edu by mailhost.cs.washington.edu
    with SMTP id AA00747; Fri, 18 Nov 2011 09:41:01 -0800
Received: from mailhost.cs.washington.edu by ee.uwa.edu.au
    with SMTP; Fri, 18 Nov 2011 09:42:00 -0800
Return-Path: <alice@cs.washington.edu>
Reply-To: alice@cs.washington.edu
In-Reply-To: <previous-message@example.com>
Keywords: birthday, celebration
X-Priority: 1
X-Mailer: SimMail 1.0

This is the body of the message.  It is for the human recipient.
"""


SAMPLE_MIME = """\
From: alice@cs.washington.edu
To: bob@ee.uwa.edu.au
MIME-Version: 1.0
Message-Id: <0704760941.AA00747@cs.washington.edu>
Content-Type: multipart/alternative; boundary="qwertyuiopasdfghjklzxcvbnm"
Subject: Earth orbits sun integral number of times

This is the preamble. The user agent ignores it. Have a nice day.
--qwertyuiopasdfghjklzxcvbnm
Content-Type: text/plain

Happy birthday to you
Happy birthday to you
Happy birthday dear Bob
Happy birthday to you
--qwertyuiopasdfghjklzxcvbnm
Content-Type: text/html

<p>Happy birthday to you<br>
Happy birthday to you<br>
Happy birthday dear <b>Bob</b><br>
Happy birthday to you</p>
--qwertyuiopasdfghjklzxcvbnm
Content-Type: audio/basic
Content-Transfer-Encoding: base64

UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=
--qwertyuiopasdfghjklzxcvbnm--
"""


SAMPLE_QP = """\
From: test@example.com
To: user@example.com
MIME-Version: 1.0
Content-Type: text/plain; charset="iso-8859-1"
Content-Transfer-Encoding: quoted-printable
Subject: Caf=E9 meeting

Let's meet at the caf=E9 for a r=E9sum=E9 review.
"""


def print_message_summary(msg: EmailMessage, label: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"{label}")
    print(f"{'=' * 70}")
    print(f"  From:        {msg.from_addr}")
    print(f"  To:          {', '.join(msg.to_addrs)}")
    print(f"  Subject:     {msg.subject}")
    print(f"  Date:        {msg.date}")
    print(f"  Message-Id:  {msg.message_id}")
    print(f"  Reply-To:    {msg.reply_to or '(none)'}")
    print(f"  In-Reply-To: {msg.in_reply_to or '(none)'}")
    print(f"  Return-Path: {msg.return_path or '(none)'}")
    print(f"  Keywords:    {msg.keywords or '(none)'}")
    print(f"  Is MIME:     {msg.is_mime}")
    print(f"  Received headers ({len(msg.received_path)} hops):")
    for i, rcv in enumerate(msg.received_path, 1):
        print(f"    [{i}] {rcv}")
    x_hdrs = msg.x_headers()
    if x_hdrs:
        print(f"  X- headers:")
        for k, v in x_hdrs.items():
            print(f"    {k}: {'; '.join(v)}")
    if msg.mime_parts:
        ct = msg.first("content-type")
        print(f"  Content-Type: {ct}")
        print(f"  MIME parts ({len(msg.mime_parts)}):")
        for i, part in enumerate(msg.mime_parts, 1):
            print(f"    [{i}] type={part.content_type}  encoding={part.transfer_encoding}  "
                  f"body_len={len(part.body)}")
            decoded = part.decoded_body()
            preview = decoded[:120].replace("\n", " | ")
            print(f"        decoded preview: {preview}{'...' if len(decoded) > 120 else ''}")
    else:
        print(f"  Body ({len(msg.body)} chars):")
        for line in msg.body.splitlines()[:6]:
            print(f"    | {line}")


def main() -> None:
    print("=" * 70)
    print("RFC 5322 Header Parsing (section 7.2.3, Figs. 7-10 & 7-11)")
    print("=" * 70)
    print("Header fields related to message transport:")
    transport_headers = [
        ("To", "Email address(es) of primary recipient(s)"),
        ("Cc", "Email address(es) of secondary recipient(s)"),
        ("Bcc", "Email address(es) for blind carbon copies"),
        ("From", "Person or people who created the message"),
        ("Sender", "Email address of the actual sender"),
        ("Received", "Line added by each transfer agent along the route"),
        ("Return-Path", "Can be used to identify a path back to the sender"),
    ]
    for h, desc in transport_headers:
        print(f"  {h:<14} - {desc}")
    print("\nUser-agent headers:")
    ua_headers = [
        ("Date", "The date and time the message was sent"),
        ("Reply-To", "Email address to which replies should be sent"),
        ("Message-Id", "Unique number for referencing this message later"),
        ("In-Reply-To", "Message-Id of the message to which this is a reply"),
        ("References", "Other relevant Message-Ids"),
        ("Keywords", "User-chosen keywords"),
        ("Subject", "Short summary of the message"),
    ]
    for h, desc in ua_headers:
        print(f"  {h:<14} - {desc}")

    msg1 = EmailMessage.parse(SAMPLE_RFC5322)
    print_message_summary(msg1, "Simple RFC 5322 message (plain text)")

    msg2 = EmailMessage.parse(SAMPLE_MIME)
    print_message_summary(msg2, "MIME multipart/alternative message")

    msg3 = EmailMessage.parse(SAMPLE_QP)
    print_message_summary(msg3, "Quoted-printable encoded message")
    print(f"  Decoded body:")
    for part in ([MIMEPart(headers={"content-transfer-encoding": msg3.first("content-transfer-encoding"),
                                     "content-type": msg3.first("content-type")},
                          body=msg3.body)] if not msg3.mime_parts else msg3.mime_parts):
        for line in part.decoded_body().splitlines():
            print(f"    | {line}")

    print(f"\n{'=' * 70}")
    print("MIME Content-Type types (Fig. 7-13)")
    print(f"{'=' * 70}")
    mime_types = [
        ("text", "plain, html, xml, css", "Text in various formats"),
        ("image", "gif, jpeg, tiff", "Pictures"),
        ("audio", "basic, mpeg, mp4", "Sounds"),
        ("video", "mpeg, mp4, quicktime", "Movies"),
        ("model", "vrml", "3D model"),
        ("application", "octet-stream, pdf, javascript, zip", "Data for applications"),
        ("message", "http, rfc822", "Encapsulated message"),
        ("multipart", "mixed, alternative, parallel, digest", "Combination of types"),
    ]
    for t, subtypes, desc in mime_types:
        print(f"  {t:<12} {subtypes:<40} {desc}")


if __name__ == "__main__":
    main()