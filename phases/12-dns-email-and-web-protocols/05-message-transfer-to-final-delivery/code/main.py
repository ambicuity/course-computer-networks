#!/usr/bin/env python3
"""SMTP protocol simulator and POP3/IMAP final delivery (section 7.2.4-7.2.5).

Stdlib only, no network calls. Demonstrates four things:

1. The full SMTP command flow from Fig. 7-15: HELO/EHLO, MAIL FROM,
   RCPT TO, DATA, QUIT with response codes 220, 250, 354, 550, 221.
2. ESMTP extension negotiation (EHLO -> service list) and the AUTH,
   SIZE, STARTTLS, BINARYMIME extensions from Fig. 7-16.
3. Mail submission (port 587 + AUTH) vs. message transfer (port 25)
   distinction from section 7.2.4.
4. Final delivery via POP3 (download-and-delete, RFC 1939) and IMAP
   (server-side folders, RFC 3501) from section 7.2.5.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


SMTP_EXTENSIONS: dict[str, str] = {
    "AUTH": "Client authentication",
    "BINARYMIME": "Server accepts binary messages",
    "CHUNKING": "Server accepts large messages in chunks",
    "SIZE": "Check message size before trying to send",
    "STARTTLS": "Switch to secure transport (TLS)",
    "UTF8SMTP": "Internationalized addresses",
}


class SMTPState(Enum):
    CLOSED = 0
    GREETING = 1
    READY = 2
    MAIL = 3
    RCPT = 4
    DATA = 5
    QUIT = 6


@dataclass
class SMTPResponse:
    code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code} {self.message}"


@dataclass
class EmailMessage:
    from_addr: str
    to_addrs: list[str]
    data: str
    size: int = 0

    def __post_init__(self) -> None:
        self.size = len(self.data)


class SMTPServerSim:
    """Simulates an SMTP/ESMTP server with state tracking."""

    def __init__(self, hostname: str, port: int = 25,
                 extensions: Optional[list[str]] = None,
                 max_size: int = 10485760,
                 valid_recipients: Optional[set[str]] = None) -> None:
        self.hostname = hostname
        self.port = port
        self.extensions = extensions or ["AUTH", "SIZE", "STARTTLS"]
        self.max_size = max_size
        self.valid_recipients = valid_recipients or set()
        self.state = SMTPState.CLOSED
        self.mail_from: Optional[str] = None
        self.rcpts: list[str] = []
        self.data_buffer: list[str] = []
        self.authenticated = False
        self.delivered: list[EmailMessage] = []
        self.log: list[str] = []

    def connect(self) -> SMTPResponse:
        self.state = SMTPState.GREETING
        return SMTPResponse(220, f"{self.hostname} SMTP service ready")

    def _command(self, line: str) -> SMTPResponse:
        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "EHLO":
            self.state = SMTPState.READY
            ext_list = "\n".join(f"250-{e}" for e in self.extensions[:-1])
            if self.extensions:
                ext_list += f"\n250 {self.extensions[-1]}"
            msg_parts = [f"{self.hostname} greets you"]
            for e in self.extensions:
                if e == "SIZE":
                    msg_parts.append(f"SIZE {self.max_size}")
                else:
                    msg_parts.append(e)
            return SMTPResponse(250, "\n".join(msg_parts))

        if cmd == "HELO":
            self.state = SMTPState.READY
            return SMTPResponse(250, f"{self.hostname} says hello to {arg}")

        if cmd == "AUTH":
            if "AUTH" in self.extensions:
                self.authenticated = True
                return SMTPResponse(235, "authentication successful")
            return SMTPResponse(502, "command not implemented")

        if cmd == "STARTTLS":
            return SMTPResponse(220, "Ready to start TLS")

        if cmd == "MAIL" and arg.upper().startswith("FROM:"):
            if self.state != SMTPState.READY:
                return SMTPResponse(503, "bad sequence of commands")
            raw = arg[5:].strip()
            addr = raw.split()[0].strip("<>") if raw else ""
            if "SIZE=" in arg.upper():
                size_str = arg.upper().split("SIZE=")[1].split()[0]
                if int(size_str) > self.max_size:
                    return SMTPResponse(552, f"message exceeds size limit {self.max_size}")
            self.mail_from = addr
            self.rcpts = []
            self.state = SMTPState.MAIL
            return SMTPResponse(250, f"sender <{addr}> ok")

        if cmd == "RCPT" and arg.upper().startswith("TO:"):
            if self.state not in (SMTPState.MAIL, SMTPState.RCPT):
                return SMTPResponse(503, "bad sequence of commands")
            rcpt = arg[3:].strip().strip("<>")
            if self.valid_recipients and rcpt not in self.valid_recipients:
                return SMTPResponse(550, f"no such mailbox <{rcpt}>")
            self.rcpts.append(rcpt)
            self.state = SMTPState.RCPT
            return SMTPResponse(250, f"recipient <{rcpt}> ok")

        if cmd == "DATA":
            if self.state != SMTPState.RCPT:
                return SMTPResponse(503, "bad sequence of commands")
            self.state = SMTPState.DATA
            return SMTPResponse(354, 'Send mail; end with "." on a line by itself')

        if cmd == "QUIT":
            self.state = SMTPState.QUIT
            return SMTPResponse(221, f"{self.hostname} closing connection")

        if cmd == "RSET":
            self.mail_from = None
            self.rcpts = []
            self.state = SMTPState.READY
            return SMTPResponse(250, "OK")

        if cmd == "NOOP":
            return SMTPResponse(250, "OK")

        if cmd == "VRFY":
            return SMTPResponse(252, f"Cannot VRFY user, but will accept message")

        return SMTPResponse(500, f"unrecognized command: {cmd}")

    def data_line(self, line: str) -> Optional[SMTPResponse]:
        if self.state != SMTPState.DATA:
            return SMTPResponse(503, "not in DATA mode")
        if line.strip() == ".":
            return self._commit()
        self.data_buffer.append(line)
        return None

    def _commit(self) -> SMTPResponse:
        data = "\n".join(self.data_buffer)
        msg = EmailMessage(from_addr=self.mail_from or "", to_addrs=list(self.rcpts), data=data)
        self.delivered.append(msg)
        self.log.append(f"DELIVERED from={msg.from_addr} to={msg.to_addrs} size={msg.size}")
        self.data_buffer = []
        self.state = SMTPState.READY
        return SMTPResponse(250, "message accepted")


def run_smtp_session(server: SMTPServerSim, commands: list[tuple[str, str]]) -> list[SMTPResponse]:
    """Run a scripted SMTP session. commands = [(direction, text), ...]"""
    responses: list[SMTPResponse] = []
    print(f"  S: {server.connect()}")
    for direction, text in commands:
        if direction == "C":
            print(f"  C: {text}")
            if server.state == SMTPState.DATA and text.strip() != ".":
                resp = server.data_line(text)
            elif text.strip() == "." and server.state == SMTPState.DATA:
                resp = server.data_line(".")
            else:
                resp = server._command(text)
            if resp:
                responses.append(resp)
                print(f"  S: {resp}")
        elif direction == "C-DATA":
            print(f"  C: {text}")
            server.data_line(text)
    return responses


class POP3ServerSim:
    """POP3 final delivery simulator (RFC 1939)."""

    def __init__(self, messages: list[EmailMessage]) -> None:
        self.messages = list(messages)
        self.authenticated = False
        self.deleted: set[int] = set()

    def command(self, cmd: str) -> str:
        parts = cmd.strip().split(maxsplit=1)
        verb = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if verb == "USER":
            return "+OK user accepted"
        if verb == "PASS":
            self.authenticated = True
            return "+OK password accepted"
        if not self.authenticated:
            return "-ERR not authenticated"
        if verb == "STAT":
            n = len(self.messages) - len(self.deleted)
            total = sum(m.size for i, m in enumerate(self.messages) if i not in self.deleted)
            return f"+OK {n} {total}"
        if verb == "LIST":
            lines = [f"+OK {len(self.messages) - len(self.deleted)} messages"]
            for i, m in enumerate(self.messages, 1):
                if i - 1 not in self.deleted:
                    lines.append(f"{i} {m.size}")
            return "\n".join(lines)
        if verb == "RETR" and arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(self.messages) and idx not in self.deleted:
                m = self.messages[idx]
                return f"+OK {m.size} octets\n{m.data}\n."
            return "-ERR no such message"
        if verb == "DELE" and arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(self.messages):
                self.deleted.add(idx)
                return "+OK message deleted"
            return "-ERR no such message"
        if verb == "QUIT":
            for idx in sorted(self.deleted, reverse=True):
                if idx < len(self.messages):
                    self.messages.pop(idx)
            self.deleted.clear()
            return "+OK POP3 server signing off"
        return "-ERR unknown command"


class IMAPServerSim:
    """IMAP4rev1 final delivery simulator (RFC 3501)."""

    def __init__(self, messages: list[EmailMessage]) -> None:
        self.messages = list(messages)
        self.flags: dict[int, set[str]] = {i: set() for i in range(len(self.messages))}
        self.folders: dict[str, list[int]] = {"INBOX": list(range(len(self.messages)))}
        self.authenticated = False
        self.selected: Optional[str] = None

    def command(self, cmd: str) -> str:
        parts = cmd.strip().split()
        if len(parts) < 2:
            return "* BAD missing tag"
        tag = parts[0]
        verb = parts[1].upper()
        args = parts[2:]

        if verb == "LOGIN":
            self.authenticated = True
            return f"{tag} OK LOGIN completed"
        if not self.authenticated:
            return f"{tag} NO not authenticated"
        if verb == "SELECT":
            folder = args[0].strip('"') if args else "INBOX"
            if folder not in self.folders:
                self.folders[folder] = []
            self.selected = folder
            count = len(self.folders[folder])
            return (f"* {count} EXISTS\n* {count} RECENT\n"
                    f"{tag} OK [{folder}] SELECT completed")
        if verb == "FETCH" and args and args[0].isdigit():
            seq = int(args[0])
            if self.selected and 1 <= seq <= len(self.folders[self.selected]):
                idx = self.folders[self.selected][seq - 1]
                m = self.messages[idx]
                flags = " ".join(self.flags.get(idx, set()))
                return (f"* {seq} FETCH (FLAGS ({flags}) "
                        f"RFC822.SIZE {m.size} BODY[] {{{len(m.data)}}}\n{m.data})\n"
                        f"{tag} OK FETCH completed")
            return f"{tag} NO no such message"
        if verb == "STORE" and args and args[0].isdigit():
            seq = int(args[0])
            if self.selected and 1 <= seq <= len(self.folders[self.selected]):
                idx = self.folders[self.selected][seq - 1]
                self.flags.setdefault(idx, set()).add("\\Seen")
                return f"* {seq} FETCH (FLAGS (\\Seen))\n{tag} OK STORE completed"
            return f"{tag} NO no such message"
        if verb == "SEARCH":
            criteria = " ".join(args).strip('"')
            matches: list[str] = []
            if self.selected:
                for seq, idx in enumerate(self.folders[self.selected], 1):
                    m = self.messages[idx]
                    if criteria.upper() == "UNSEEN" and "\\Seen" not in self.flags.get(idx, set()):
                        matches.append(str(seq))
                    elif criteria.lower() in m.data.lower():
                        matches.append(str(seq))
            return f"* SEARCH {' '.join(matches)}\n{tag} OK SEARCH completed"
        if verb == "EXPUNGE":
            if self.selected:
                to_remove = [i for i, idx in enumerate(self.folders[self.selected])
                             if "\\Deleted" in self.flags.get(idx, set())]
                for seq in sorted(to_remove, reverse=True):
                    del self.folders[self.selected][seq]
                    return_str = f"* {seq + 1} EXPUNGE\n"
                return f"{return_str}{tag} OK EXPUNGE completed"
            return f"{tag} OK EXPUNGE completed"
        if verb == "LOGOUT":
            return f"* BYE LOGOUT\n{tag} OK LOGOUT completed"
        return f"{tag} BAD unknown command"


def main() -> None:
    print("=" * 70)
    print("SMTP Protocol Simulator (section 7.2.4, Fig. 7-15)")
    print("=" * 70)

    print("\n--- Basic SMTP transfer (HELO) ---")
    server1 = SMTPServerSim("ee.uwa.edu.au", valid_recipients={"bob@ee.uwa.edu.au"})
    run_smtp_session(server1, [
        ("C", "HELO abcd.com"),
        ("C", "MAIL FROM: <alice@cs.washington.edu>"),
        ("C", "RCPT TO: <bob@ee.uwa.edu.au>"),
        ("C", "DATA"),
        ("C-DATA", "From: alice@cs.washington.edu"),
        ("C-DATA", "To: bob@ee.uwa.edu.au"),
        ("C-DATA", "Subject: Earth orbits sun integral number of times"),
        ("C-DATA", ""),
        ("C-DATA", "Happy birthday Bob!"),
        ("C", "."),
        ("C", "QUIT"),
    ])

    print("\n--- ESMTP with extensions (EHLO) ---")
    server2 = SMTPServerSim("mail.example.com", port=587,
                             extensions=["AUTH", "SIZE", "STARTTLS", "BINARYMIME"],
                             valid_recipients={"bob@example.com", "carol@example.com"})
    run_smtp_session(server2, [
        ("C", "EHLO client.example.com"),
        ("C", "AUTH LOGIN"),
        ("C", "MAIL FROM: <alice@example.com> SIZE=500"),
        ("C", "RCPT TO: <bob@example.com>"),
        ("C", "RCPT TO: <carol@example.com>"),
        ("C", "DATA"),
        ("C-DATA", "From: alice@example.com"),
        ("C-DATA", "To: bob@example.com, carol@example.com"),
        ("C-DATA", "Subject: Testing ESMTP"),
        ("C-DATA", ""),
        ("C-DATA", "This is a test message."),
        ("C", "."),
        ("C", "QUIT"),
    ])

    print("\n--- SMTP response codes used ---")
    codes = [
        (220, "Service ready"),
        (221, "Service closing connection"),
        (235, "Authentication successful"),
        (250, "Requested action OK"),
        (354, "Start mail input; end with <CRLF>.<CRLF>"),
        (552, "Message exceeds size limit"),
        (550, "No such mailbox"),
        (503, "Bad sequence of commands"),
        (500, "Unrecognized command"),
    ]
    for code, desc in codes:
        print(f"  {code} - {desc}")

    print("\n--- ESMTP extensions (Fig. 7-16) ---")
    for keyword, desc in SMTP_EXTENSIONS.items():
        print(f"  {keyword:<12} {desc}")

    print("\n--- Failure modes ---")
    print("  1. Unknown recipient:")
    server3 = SMTPServerSim("test.com", valid_recipients={"good@test.com"})
    server3.connect()
    server3._command("HELO client")
    print(f"     MAIL FROM: {server3._command('MAIL FROM: <spam@bad.com>')}")
    print(f"     RCPT TO:   {server3._command('RCPT TO: <bad@test.com>')}")
    print("  2. Message too large:")
    server4 = SMTPServerSim("test.com", max_size=100, valid_recipients={"ok@test.com"})
    server4.connect()
    server4._command("EHLO client")
    print(f"     {server4._command('MAIL FROM: <big@test.com> SIZE=200')}")
    print("  3. Bad sequence (DATA before RCPT):")
    server5 = SMTPServerSim("test.com", valid_recipients={"ok@test.com"})
    server5.connect()
    server5._command("HELO client")
    print(f"     {server5._command('DATA')}")

    print(f"\n{'=' * 70}")
    print("Final Delivery (section 7.2.5)")
    print(f"{'=' * 70}")

    test_messages = [
        EmailMessage("alice@cs.washington.edu", ["bob@ee.uwa.edu.au"],
                     "From: alice@cs.washington.edu\nTo: bob@ee.uwa.edu.au\n"
                     "Subject: Birthday greeting\n\nHappy birthday Bob!", 0),
        EmailMessage("carol@example.com", ["bob@ee.uwa.edu.au"],
                     "From: carol@example.com\nTo: bob@ee.uwa.edu.au\n"
                     "Subject: Project update\n\nThe project is on track.", 0),
    ]

    print("\n--- POP3 final delivery (RFC 1939) ---")
    pop3 = POP3ServerSim(list(test_messages))
    for cmd in ["USER bob", "PASS secret", "STAT", "LIST", "RETR 1", "DELE 1", "STAT", "QUIT"]:
        print(f"  C: {cmd}")
        resp = pop3.command(cmd)
        for line in resp.split("\n"):
            print(f"  S: {line}")

    print("\n--- IMAP final delivery (RFC 3501) ---")
    imap = IMAPServerSim(list(test_messages))
    for cmd in [
        "A1 LOGIN bob secret",
        "A2 SELECT INBOX",
        "A3 SEARCH birthday",
        "A4 FETCH 1",
        "A5 STORE 1 +FLAGS \\Seen",
        "A6 SEARCH UNSEEN",
        "A7 LOGOUT",
    ]:
        print(f"  C: {cmd}")
        resp = imap.command(cmd)
        for line in resp.split("\n"):
            print(f"  S: {line}")

    print("\n--- POP3 vs IMAP comparison ---")
    print("  POP3:  download-and-delete, messages stored on client, simple")
    print("  IMAP:  server-side folders, FETCH parts, SEARCH, STORE flags")
    print("  SMTP:  push-based, cannot do final delivery (MUA may be offline)")

    print(f"\n--- Server delivery log ---")
    for entry in server1.log + server2.log:
        print(f"  {entry}")


if __name__ == "__main__":
    main()