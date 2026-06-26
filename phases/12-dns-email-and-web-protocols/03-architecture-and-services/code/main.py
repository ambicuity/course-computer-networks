#!/usr/bin/env python3
"""Email architecture simulator: MUA, MTA, MDA and protocol state machines.

Stdlib only, no network calls. Demonstrates three things:

1. The three-role architecture from section 7.2.1: User Agent (MUA),
   Message Transfer Agent (MTA / mail server), and Message Delivery
   Agent (MDA / mailbox). A message flows from sender MUA through
   submission -> transfer -> final delivery -> retrieval -> receiver
   MUA, matching steps 1-3 of Fig. 7-7.
2. SMTP submission/transfer as an ASCII state machine: the HELO/
   EHLO -> MAIL FROM -> RCPT TO -> DATA -> QUIT dialog with 220,
   250, 354 response codes from Fig. 7-15.
3. POP3 and IMAP retrieval state machines for final delivery, showing
   the difference between POP3 (download-and-delete) and IMAP
   (server-side folders, FETCH, SEARCH) from section 7.2.5.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


@dataclass
class EmailMessage:
    from_addr: str
    to_addrs: list[str]
    subject: str
    body: str
    message_id: str = ""
    received_headers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = f"<{id(self):x}.sim@local>"


class Mailbox:
    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.inbox: list[EmailMessage] = []
        self.folders: dict[str, list[EmailMessage]] = {}

    def deliver(self, msg: EmailMessage) -> None:
        self.inbox.append(msg)

    def move_to_folder(self, folder: str, msg: EmailMessage) -> None:
        self.folders.setdefault(folder, []).append(msg)
        if msg in self.inbox:
            self.inbox.remove(msg)

    def status(self) -> str:
        total = len(self.inbox) + sum(len(v) for v in self.folders.values())
        return (f"{self.owner}: {len(self.inbox)} in inbox, "
                f"{sum(len(v) for v in self.folders.values())} in folders, "
                f"{total} total")


class MailServer:
    def __init__(self, domain: str) -> None:
        self.domain = domain
        self.mailboxes: dict[str, Mailbox] = {}
        self.log: list[str] = []

    def mailbox_for(self, user: str) -> Mailbox:
        return self.mailboxes.setdefault(user, Mailbox(f"{user}@{self.domain}"))

    def accepts(self, addr: str) -> bool:
        return addr.endswith(f"@{self.domain}") and addr.split("@")[0] in self.mailboxes


class SMTPState(Enum):
    CLOSED = 0
    CONNECTED = 1
    MAIL = 2
    RCPT = 3
    DATA = 4
    QUIT = 5


class SMTPServer:
    def __init__(self, server: MailServer) -> None:
        self.server = server
        self.state = SMTPState.CLOSED
        self.mail_from: Optional[str] = None
        self.rcpts: list[str] = []
        self.data_buffer: list[str] = []

    def connect(self) -> str:
        self.state = SMTPState.CONNECTED
        return f"220 {self.server.domain} SMTP service ready"

    def command(self, line: str) -> str:
        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("EHLO", "HELO"):
            self.state = SMTPState.CONNECTED
            return f"250 {self.server.domain} says hello to {arg}"

        if cmd == "MAIL" and arg.upper().startswith("FROM:"):
            self.mail_from = arg[5:].strip().strip("<>")
            self.rcpts = []
            self.state = SMTPState.MAIL
            return f"250 sender <{self.mail_from}> ok"

        if cmd == "RCPT" and arg.upper().startswith("TO:"):
            rcpt = arg[3:].strip().strip("<>")
            if self.server.accepts(rcpt):
                self.rcpts.append(rcpt)
                self.state = SMTPState.RCPT
                return f"250 recipient <{rcpt}> ok"
            return f"550 no such mailbox <{rcpt}>"

        if cmd == "DATA":
            if self.state not in (SMTPState.RCPT, SMTPState.MAIL):
                return "503 bad sequence of commands"
            self.state = SMTPState.DATA
            return '354 Send mail; end with "." on a line by itself'

        if cmd == "QUIT":
            self.state = SMTPState.QUIT
            return f"221 {self.server.domain} closing connection"

        return f"500 unrecognized command: {cmd}"

    def data_line(self, line: str) -> Optional[str]:
        if line.strip() == ".":
            return self._commit()
        self.data_buffer.append(line)
        return None

    def _commit(self) -> str:
        body = "\n".join(self.data_buffer)
        for rcpt in self.rcpts:
            user = rcpt.split("@")[0]
            msg = EmailMessage(
                from_addr=self.mail_from or "",
                to_addrs=list(self.rcpts),
                subject=self._extract_header(body, "Subject") or "(no subject)",
                body=body,
            )
            self.server.mailbox_for(user).deliver(msg)
            self.server.log.append(f"DELIVERED to {rcpt}: {msg.subject}")
        self.data_buffer = []
        self.state = SMTPState.CONNECTED
        return "250 message accepted"

    @staticmethod
    def _extract_header(body: str, name: str) -> Optional[str]:
        for line in body.splitlines():
            if line.lower().startswith(f"{name.lower()}:"):
                return line.split(":", 1)[1].strip()
        return None


def smtp_dialog(server: MailServer, from_addr: str, rcpts: list[str],
                subject: str, body: str) -> None:
    smtp = SMTPServer(server)
    print(f"  S: {smtp.connect()}")
    print(f"  C: EHLO client.example.com")
    print(f"  S: {smtp.command('EHLO client.example.com')}")
    print(f"  C: MAIL FROM: <{from_addr}>")
    print(f"  S: {smtp.command(f'MAIL FROM: <{from_addr}>')}")
    for rcpt in rcpts:
        print(f"  C: RCPT TO: <{rcpt}>")
        print(f"  S: {smtp.command(f'RCPT TO: <{rcpt}>')}")
    print(f"  C: DATA")
    print(f"  S: {smtp.command('DATA')}")
    for line in body.splitlines():
        print(f"  C: {line}")
        smtp.data_line(line)
    print(f"  C: .")
    result = smtp.data_line(".")
    print(f"  S: {result}")
    print(f"  C: QUIT")
    print(f"  S: {smtp.command('QUIT')}")


class POP3Server:
    def __init__(self, mailbox: Mailbox) -> None:
        self.mailbox = mailbox
        self.authenticated = False

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
            return f"+OK {len(self.mailbox.inbox)} {sum(len(m.body) for m in self.mailbox.inbox)}"
        if verb == "LIST":
            lines = [f"+OK {len(self.mailbox.inbox)} messages"]
            for i, m in enumerate(self.mailbox.inbox, 1):
                lines.append(f"{i} {len(m.body)}")
            return "\n".join(lines)
        if verb == "RETR" and arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(self.mailbox.inbox):
                m = self.mailbox.inbox[idx]
                return (f"+OK\nFrom: {m.from_addr}\nTo: {', '.join(m.to_addrs)}\n"
                        f"Subject: {m.subject}\n\n{m.body}\n.")
            return "-ERR no such message"
        if verb == "DELE" and arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(self.mailbox.inbox):
                self.mailbox.inbox.pop(idx)
                return "+OK message deleted"
            return "-ERR no such message"
        if verb == "QUIT":
            return "+OK POP3 server signing off"
        return "-ERR unknown command"


class IMAPServer:
    def __init__(self, mailbox: Mailbox) -> None:
        self.mailbox = mailbox
        self.authenticated = False
        self.selected_folder: Optional[str] = "INBOX"

    def command(self, cmd: str) -> str:
        parts = cmd.strip().split()
        if len(parts) < 2:
            return "* BAD missing tag"
        tag = parts[0]
        verb = parts[1].upper()
        args = parts[2:]

        if verb == "LOGIN":
            self.authenticated = True
            return f"* OK LOGIN completed\n{tag} OK LOGIN completed"
        if not self.authenticated:
            return f"{tag} NO not authenticated"
        if verb == "SELECT":
            folder = args[0].strip('"') if args else "INBOX"
            self.selected_folder = folder.upper()
            count = len(self.mailbox.inbox) if self.selected_folder == "INBOX" else 0
            return (f"* {count} EXISTS\n* {count} RECENT\n"
                    f"{tag} OK [{self.selected_folder}] SELECT completed")
        if verb == "FETCH" and args and args[0].isdigit():
            idx = int(args[0]) - 1
            if 0 <= idx < len(self.mailbox.inbox):
                m = self.mailbox.inbox[idx]
                envelope = (f"From: {m.from_addr}\nTo: {', '.join(m.to_addrs)}\n"
                             f"Subject: {m.subject}\nMessage-Id: {m.message_id}")
                return (f"* {args[0]} FETCH (ENVELOPE ({envelope})\n"
                        f"BODY[] {{{len(m.body)}}}\n{m.body})\n"
                        f"{tag} OK FETCH completed")
            return f"{tag} NO no such message"
        if verb == "SEARCH":
            criteria = " ".join(args).strip('"')
            matches: list[str] = []
            for i, m in enumerate(self.mailbox.inbox, 1):
                if criteria.lower() in m.subject.lower() or criteria.lower() in m.body.lower():
                    matches.append(str(i))
            return f"* SEARCH {' '.join(matches)}\n{tag} OK SEARCH completed"
        if verb == "STORE":
            return f"{tag} OK STORE completed (flags set)"
        if verb == "COPY" and args and args[0].isdigit():
            idx = int(args[0]) - 1
            folder = args[1].strip('"') if len(args) > 1 else "Trash"
            if 0 <= idx < len(self.mailbox.inbox):
                self.mailbox.move_to_folder(folder, self.mailbox.inbox[idx])
                return f"{tag} OK COPY completed"
            return f"{tag} NO no such message"
        if verb == "LOGOUT":
            return f"* BYE LOGOUT\n{tag} OK LOGOUT completed"
        return f"{tag} BAD unknown command"


def main() -> None:
    print("=" * 70)
    print("Email Architecture (section 7.2.1): MUA -> MTA -> MDA -> MUA")
    print("=" * 70)

    sender_server = MailServer("cs.washington.edu")
    receiver_server = MailServer("ee.uwa.edu.au")
    receiver_server.mailboxes["bob"] = Mailbox("bob@ee.uwa.edu.au")

    print("\nStep 1: Mail Submission (MUA -> MTA via SMTP port 587)")
    print("-" * 70)
    print("Sender MUA (alice) composes a message and submits to her MTA:")
    smtp_dialog(
        sender_server,
        from_addr="alice@cs.washington.edu",
        rcpts=["bob@ee.uwa.edu.au"],
        subject="Earth orbits sun integral number of times",
        body="From: alice@cs.washington.edu\nTo: bob@ee.uwa.edu.au\n"
             "Subject: Earth orbits sun integral number of times\n\n"
             "Happy birthday Bob!",
    )

    print("\nStep 2: Message Transfer (MTA -> MTA via SMTP port 25)")
    print("-" * 70)
    print("Alice's MTA looks up MX for ee.uwa.edu.au, then relays to Bob's MTA:")
    smtp_dialog(
        receiver_server,
        from_addr="alice@cs.washington.edu",
        rcpts=["bob@ee.uwa.edu.au"],
        subject="Earth orbits sun integral number of times",
        body="From: alice@cs.washington.edu\nTo: bob@ee.uwa.edu.au\n"
             "Subject: Earth orbits sun integral number of times\n\n"
             "Happy birthday Bob!",
    )

    print("\nStep 3: Final Delivery + Retrieval (MDA -> MUA via POP3/IMAP)")
    print("-" * 70)
    bob_box = receiver_server.mailboxes["bob"]
    print(f"Bob's mailbox after delivery: {bob_box.status()}")
    for m in bob_box.inbox:
        print(f"  From: {m.from_addr}  Subject: {m.subject}")

    print("\n--- POP3 retrieval (download-and-delete) ---")
    pop3 = POP3Server(bob_box)
    for cmd in ["USER bob", "PASS secret", "STAT", "LIST", "RETR 1", "DELE 1", "QUIT"]:
        print(f"  C: {cmd}")
        print(f"  S: {pop3.command(cmd)}")
    print(f"After POP3: {bob_box.status()}")

    receiver_server.mailboxes["bob"].inbox.clear()
    receiver_server.mailboxes["bob"].inbox.append(EmailMessage(
        from_addr="alice@cs.washington.edu",
        to_addrs=["bob@ee.uwa.edu.au"],
        subject="Meeting reminder",
        body="Don't forget our meeting at 3pm tomorrow.",
    ))
    receiver_server.mailboxes["bob"].inbox.append(EmailMessage(
        from_addr="carol@example.com",
        to_addrs=["bob@ee.uwa.edu.au"],
        subject="Re: Project proposal",
        body="I've reviewed the proposal and it looks great.",
    ))

    print("\n--- IMAP retrieval (server-side folders, search) ---")
    imap = IMAPServer(bob_box)
    for cmd in [
        "A1 LOGIN bob secret",
        "A2 SELECT INBOX",
        "A3 SEARCH proposal",
        "A4 FETCH 1",
        "A5 COPY 1 Trash",
        "A6 LOGOUT",
    ]:
        print(f"  C: {cmd}")
        print(f"  S: {imap.command(cmd)}")
    print(f"After IMAP: {bob_box.status()}")

    print("\n--- Failure mode: unknown recipient ---")
    smtp_fail = SMTPServer(receiver_server)
    print(f"  S: {smtp_fail.connect()}")
    print(f"  C: HELO test")
    print(f"  S: {smtp_fail.command('HELO test')}")
    print(f"  C: MAIL FROM: <spammer@bad.com>")
    print(f"  S: {smtp_fail.command('MAIL FROM: <spammer@bad.com>')}")
    print(f"  C: RCPT TO: <nobody@ee.uwa.edu.au>")
    print(f"  S: {smtp_fail.command('RCPT TO: <nobody@ee.uwa.edu.au>')}")
    print(f"  -> 550 rejection: mailbox does not exist")

    print("\n--- Server delivery log ---")
    for entry in receiver_server.log:
        print(f"  {entry}")


if __name__ == "__main__":
    main()