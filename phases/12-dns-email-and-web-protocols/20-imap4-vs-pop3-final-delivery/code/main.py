#!/usr/bin/env python3
"""POP3 / IMAP dialog simulators (RFC 1939 / RFC 3501 / RFC 2177 / RFC 8314).

Walks through the canonical POP3 (AUTHORIZATION -> TRANSACTION -> UPDATE) and
IMAP4rev1 (NOT_AUTHENTICATED -> AUTHENTICATED -> SELECTED -> LOGOUT) state
machines, demonstrating flag handling, IDLE, and the modern TLS port
recommendation from RFC 8314.

Run with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


POP3_PORT_PLAIN = 110
POP3_PORT_TLS = 995
IMAP_PORT_PLAIN = 143
IMAP_PORT_TLS = 993


@dataclass
class Pop3Mailbox:
    messages: List[bytes] = field(default_factory=list)
    deleted: set = field(default_factory=set)

    def stat(self) -> str:
        live = [m for i, m in enumerate(self.messages) if i not in self.deleted]
        return f"+OK {len(live)} {sum(len(m) for m in live)}"

    def retr(self, idx: int) -> str:
        if idx in self.deleted:
            return "-ERR message deleted"
        return f"+OK {len(self.messages[idx - 1])} octets\n<message body>"

    def dele(self, idx: int) -> str:
        self.deleted.add(idx - 1)
        return f"+OK message {idx} deleted"

    def update(self) -> None:
        self.messages = [m for i, m in enumerate(self.messages) if i not in self.deleted]
        self.deleted.clear()


def pop3_session(mailbox: Pop3Mailbox) -> List[str]:
    log: List[str] = []
    log.append("S: +OK POP3 server ready <1896.697170952@db.mtview.ca.us>")
    log.append("C: USER alice")
    log.append("S: +OK")
    log.append("C: PASS hunter2")
    log.append("S: +OK")
    log.append(f"C: STAT  -> S: {mailbox.stat()}")
    log.append("C: LIST  -> S: +OK 2 messages: (1 1234) (2 11111)")
    for i in range(1, len(mailbox.messages) + 1):
        log.append(f"C: RETR {i}  -> S: {mailbox.retr(i)}")
        log.append(f"C: DELE {i}  -> S: {mailbox.dele(i)}")
    log.append("C: QUIT  -> S: +OK (UPDATE state; physical removal happens here)")
    mailbox.update()
    return log


@dataclass
class ImapMailbox:
    name: str
    flags: Dict[int, set] = field(default_factory=dict)
    body: Dict[int, bytes] = field(default_factory=dict)
    exists: int = 0
    recent: int = 0
    uid_validity: int = 1


def imap_session(mailbox: ImapMailbox, new_messages: int = 0) -> List[str]:
    log: List[str] = []
    log.append("S: * OK [CAPABILITY IMAP4rev1 STARTTLS LOGINDISABLED] server ready")
    log.append("C: a001 STARTTLS")
    log.append("S: a001 OK begin TLS negotiation now")
    log.append("... TLS handshake ...")
    log.append("C: a002 CAPABILITY")
    log.append("S: * CAPABILITY IMAP4rev1 IDLE MOVE OBJECTID ... ")
    log.append("S: a002 OK CAPABILITY completed")
    log.append("C: a003 LOGIN alice hunter2")
    log.append("S: a003 OK LOGIN completed")
    log.append(f"C: a004 SELECT {mailbox.name}")
    log.append(f"S: * {mailbox.exists} EXISTS")
    log.append(f"S: * {mailbox.recent} RECENT")
    log.append("S: * FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)")
    log.append(f"S: a004 OK [READ-WRITE] SELECT completed")
    log.append("C: a005 IDLE")
    log.append("S: + idling")
    if new_messages:
        mailbox.exists += new_messages
        log.append(f"S: * {mailbox.exists} EXISTS   <-- unsolicited update (push)")
    log.append("C: DONE")
    log.append("S: a005 OK IDLE terminated")
    log.append("C: a006 LOGOUT")
    log.append("S: * BYE")
    log.append("S: a006 OK LOGOUT completed")
    return log


def main() -> None:
    print("=" * 64)
    print("IMAP4 vs POP3  --  RFC 1939 / RFC 3501 / RFC 2177 / RFC 8314")
    print("=" * 64)

    print("\nPOP3 session (RFC 1939):")
    mb = Pop3Mailbox(messages=[b"first message", b"second message"])
    for line in pop3_session(mb):
        print(f"  {line}")
    print(f"  mailbox after QUIT: {len(mb.messages)} messages left")

    print("\nIMAP4rev1 session with one IDLE notification (RFC 3501 / RFC 2177):")
    im = ImapMailbox(name="INBOX", exists=3, recent=0)
    for line in imap_session(im, new_messages=1):
        print(f"  {line}")
    print(f"  mailbox.exists now: {im.exists}")

    print("\nIMAP flags (RFC 3501 §2.3.2):")
    flags = ("\\Seen", "\\Answered", "\\Flagged", "\\Deleted", "\\Draft", "\\Recent")
    for f in flags:
        print(f"  {f}")

    print("\nPort matrix (RFC 8314):")
    print("  POP3 plain   110   -- deprecated in favor of implicit TLS")
    print("  POP3 implicit TLS  995   -- recommended (RFC 8314)")
    print("  IMAP plain   143   -- deprecated in favor of implicit TLS")
    print("  IMAP implicit TLS  993   -- recommended (RFC 8314)")
    print("  STARTTLS variants exist but are discouraged for new deployments")


if __name__ == "__main__":
    main()
