#!/usr/bin/env python3
"""SMTP / ESMTP dialog simulator (RFC 5321).

Models the client side of a mail submission: greeting, EHLO extension banner,
AUTH PLAIN, MAIL FROM, RCPT TO, DATA, and the byte-stuffing rule. No network
calls; runs anywhere with `python3 main.py`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


PORT_MTA = 25
PORT_SUBMISSION = 587
PORT_SMTPS_LEGACY = 465


@dataclass
class SmtpReply:
    code: int
    text: str
    enhanced: Optional[str] = None

    def classify(self) -> str:
        if self.code < 300:
            return "OK"
        if self.code < 400:
            return "more input"
        if self.code < 500:
            return "transient (retry)"
        return "permanent (bounce)"


def parse_enhanced(text: str) -> Tuple[int, Optional[str], str]:
    parts = text.split(" ", 2)
    code = int(parts[0])
    if len(parts) >= 2 and "." in parts[1]:
        return code, parts[1], parts[2] if len(parts) > 2 else ""
    return code, None, parts[1] if len(parts) > 1 else ""


EHLO_BANNER = [
    (250, "mail.example.com Hello client.example.org"),
    (250, "SIZE 10485760"),
    (250, "8BITMIME"),
    (250, "STARTTLS"),
    (250, "ENHANCEDSTATUSCODES"),
    (250, "PIPELINING"),
    (250, "CHUNKING"),
    (250, "HELP"),
]


def extensions(banner: List[Tuple[int, str]]) -> List[str]:
    return [line.split(" ", 1)[1] for code, line in banner if code == 250]


def auth_plain(user: str, password: str) -> bytes:
    payload = f"\0{user}\0{password}".encode("utf-8")
    return base64.b64encode(payload)


def dot_stuff(body: bytes) -> bytes:
    """RFC 5321 §4.5.2: prepend an extra '.' to any line beginning with '.'."""
    out = bytearray()
    for line in body.splitlines(keepends=True):
        if line.startswith(b"."):
            out.append(b".")
        out.extend(line)
    return bytes(out)


def parse_reply(line: str) -> SmtpReply:
    code_str, _, rest = line.partition(" ")
    code = int(code_str)
    enhanced = None
    text = rest
    if "." in rest.split(" ", 1)[0]:
        enhanced, _, text = rest.partition(" ")
    return SmtpReply(code=code, text=text, enhanced=enhanced)


@dataclass
class SmtpDialog:
    banner: List[Tuple[int, str]] = field(default_factory=lambda: list(EHLO_BANNER))
    replies: List[SmtpReply] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)

    def greet(self) -> None:
        self.extensions = extensions(self.banner)
        self.replies.append(SmtpReply(code=250, text="EHLO accepted"))

    def do_auth(self, user: str, password: str) -> SmtpReply:
        encoded = auth_plain(user, password)
        self.replies.append(SmtpReply(code=235, text="2.7.0 Authentication successful"))
        return self.replies[-1]

    def do_mail_from(self, sender: str) -> SmtpReply:
        if not sender or "@" in sender:
            self.replies.append(SmtpReply(code=250, text=f"2.1.0 {sender} OK"))
        else:
            self.replies.append(SmtpReply(code=501, text="5.1.7 Bad sender address syntax"))
        return self.replies[-1]

    def do_rcpt_to(self, recipient: str) -> SmtpReply:
        self.replies.append(SmtpReply(code=250, text=f"2.1.5 {recipient} OK"))
        return self.replies[-1]

    def do_data(self, body: bytes) -> SmtpReply:
        self.replies.append(SmtpReply(code=354, text="Send message; end with <CR><LF>.<CR><LF>"))
        stuffed = dot_stuff(body)
        self.replies.append(SmtpReply(code=250, text=f"2.0.0 OK queued as {len(stuffed)}"))
        return self.replies[-1]


def main() -> None:
    print("=" * 64)
    print("SMTP / ESMTP  --  RFC 5321 / 3207 / 4954 / 6409")
    print("=" * 64)

    print("\nServer EHLO banner extensions:")
    for code, line in EHLO_BANNER:
        print(f"  {code}- {line}")
    print(f"  -> parsed extensions: {extensions(EHLO_BANNER)}")

    print("\nEnhanced status code decomposition:")
    for reply in [
        "250 2.1.0 Sender OK",
        "550 5.1.1 The email account that you tried to reach does not exist",
        "554 5.7.1 Sender address rejected: SPF check failed",
        "421 4.7.0 Try again later",
    ]:
        code, enhanced, text = parse_enhanced(reply)
        print(f"  '{reply}' -> code={code}  enhanced={enhanced}  text='{text}'")

    print("\nReply classifier:")
    for code in (250, 354, 421, 450, 550, 554):
        r = SmtpReply(code=code, text="")
        print(f"  {code:>3}  -> {r.classify()}")

    dialog = SmtpDialog()
    dialog.greet()
    dialog.do_auth("alice", "s3cret")
    dialog.do_mail_from("alice@example.com")
    dialog.do_rcpt_to("bob@example.org")
    body = b"Hi Bob,\r\n.\r\nSee attached.\r\n"
    dialog.do_data(body)

    print("\nSimulated client transcript:")
    print(f"  C: EHLO client.example.org")
    print(f"  S: 250-mail.example.com ... {len(dialog.extensions)} extensions")
    print(f"  C: AUTH PLAIN {auth_plain('alice', 's3cret').decode()}")
    print(f"  S: 235 2.7.0 Authentication successful")
    print(f"  C: MAIL FROM:<alice@example.com>")
    print(f"  S: 250 2.1.0 Sender OK")
    print(f"  C: RCPT TO:<bob@example.org>")
    print(f"  S: 250 2.1.5 Recipient OK")
    print(f"  C: DATA")
    print(f"  S: 354 Send message; end with . on its own line")
    print(f"  C: <body bytes {len(body)}>")
    print(f"  S: 250 2.0.0 OK queued as ABCDEF")

    print("\nByte-stuffing demo (body starts with '.'):")
    print(f"  raw body    : {body!r}")
    print(f"  dot-stuffed : {dot_stuff(body)!r}")


if __name__ == "__main__":
    main()
