#!/usr/bin/env python3
"""RFC 5322 header parser, Received-trace renderer, and Bcc-stripping demo.

Splits an RFC 5322 message into its unfolded headers and body, parses the
principal header fields, builds a Received-chain summary, and shows how
Bcc stripping works on a multi-recipient copy.

Run with `python3 main.py`.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Address:
    display_name: str
    local: str
    domain: str

    @property
    def full(self) -> str:
        if self.display_name:
            return f"{self.display_name} <{self.local}@{self.domain}>"
        return f"{self.local}@{self.domain}"


def unfold(text: str) -> List[Tuple[str, str]]:
    """RFC 5322 §3.2.2: unfold continuation lines (CRLF + WSP)."""
    lines: List[str] = []
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += " " + line.lstrip()
        else:
            lines.append(line)
    return [tuple(p.split(":", 1)) for p in lines if ":" in p]


def parse_headers(text: str) -> Dict[str, str]:
    return {k.strip(): v.strip() for k, v in unfold(text)}


ADDR_RE = re.compile(r"^(?:(?P<name>.*?)\s*<)?(?P<local>[^@<\s]+)@(?P<domain>[^>]+)>?$")


def parse_address(field: str) -> Optional[Address]:
    field = field.strip()
    m = ADDR_RE.match(field)
    if not m:
        return None
    name = m.group("name") or ""
    return Address(display_name=name.strip(), local=m.group("local"), domain=m.group("domain").rstrip(">"))


def split_envelope_headers_body(message: bytes) -> Tuple[str, Dict[str, str], str]:
    head, _, body = message.partition(b"\r\n\r\n")
    headers = parse_headers(head.decode("ascii", errors="replace"))
    return ("<envelope: see SMTP MAIL FROM / RCPT TO>", headers, body)


def received_trace(headers: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for key, value in headers.items():
        if key.lower() == "received":
            for line in value.splitlines() or [value]:
                out.append(line.strip())
    return out


def new_message_id(domain: str = "example.com") -> str:
    local = uuid.uuid4().hex + "." + hex(int(time.time()))[2:]
    return f"<{local}@{domain}>"


def strip_bcc(headers: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() != "bcc"}


SAMPLE = (
    b"From: Alice Example <alice@example.org>\r\n"
    b"To: Bob Example <bob@example.com>\r\n"
    b"Cc: Carol <carol@example.com>\r\n"
    b"Bcc: Dave <dave@example.com>\r\n"
    b"Date: Thu, 25 Jun 2026 14:32:11 -0700\r\n"
    b"Subject: Lunch?\r\n"
    b"Message-Id: " + new_message_id().encode() + b"\r\n"
    b"Received: from sender.example.org (sender.example.org [203.0.113.10])\r\n"
    b" by mx.example.com (Postfix) with ESMTPS id D3F8A2C0124\r\n"
    b" for <bob@example.com>; Thu, 25 Jun 2026 14:32:11 -0700 (PDT)\r\n"
    b"Received: from client.example.org (client.example.org [198.51.100.7])\r\n"
    b" by sender.example.org (Postfix) with ESMTPSA id 91B0E1A0023\r\n"
    b" for <bob@example.com>; Thu, 25 Jun 2026 14:32:05 -0700 (PDT)\r\n"
    b"\r\n"
    b"Hi Bob, are you free for lunch?\r\n"
)


def main() -> None:
    print("=" * 64)
    print("RFC 5322 HEADERS AND ENVELOPE  --  RFC 5321 / RFC 5322")
    print("=" * 64)

    envelope, headers, body = split_envelope_headers_body(SAMPLE)
    print(f"\nEnvelope: {envelope}")
    print("Headers (parsed):")
    for k in ("From", "To", "Cc", "Bcc", "Date", "Subject", "Message-Id"):
        if k in headers:
            print(f"  {k}: {headers[k]}")
        elif k.lower() in headers:
            print(f"  {k}: {headers[k.lower()]}")

    print("\nAddress parse:")
    for header in ("From", "To", "Cc", "Bcc"):
        if header in headers:
            addr = parse_address(headers[header])
            print(f"  {header:5s} -> {addr}")

    print("\nReceived trace (most recent first, as it appears):")
    for line in received_trace(headers):
        print(f"  {line}")

    print("\nAfter Bcc strip (what the other recipients see):")
    clean = strip_bcc(headers)
    print(f"  remaining headers: {sorted(clean)}")
    print(f"  Bcc present? {'Bcc' in clean}")

    print("\nGenerated Message-Id for a new outgoing message:")
    print(f"  Message-Id: {new_message_id()}")


if __name__ == "__main__":
    main()
