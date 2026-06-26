# IMAP4 vs POP3 Final Delivery

> SMTP is push-based (the sender connects to the receiver); final delivery from the mailbox to the user agent is pull-based (the user agent connects to the mailbox server). Two protocols dominate this final hop. **POP3** (Post Office Protocol version 3, RFC 1939) is the simpler model: connect, authenticate, list messages, optionally retrieve them, optionally delete them on the server. Most POP3 deployments download each message to the client and remove it from the server, which makes multi-device use painful and offline backups important. **IMAP4rev1** (Internet Message Access Protocol version 4 revision 1, RFC 3501, with extensions in RFC 2177 IDLE, RFC 2088 LITERAL+ / RFC 5530, RFC 4314 ACL, RFC 4978 COMPRESS, RFC 6851 MOVE, RFC 7888 / 7162 OBJECTID) is the richer model: messages stay on the server, the client sees folder state, flag state (\Seen, \Answered, \Flagged, \Deleted, \Draft, \Recent), and can synchronize partially-fetched parts over a long-lived connection. Modern IMAP also exposes server-side search (RFC 5465 METADATA / RFC 6203 SEARCH) and SORT (RFC 5256) so a thin client does not need to download every message to find one. Both protocols ride on TCP (POP3 port 110, IMAP port 143), and both have implicit-TLS variants (POP3S port 995, IMAPS port 993) and a `STARTTLS` upgrade.

**Type:** Lab
**Languages:** Python, shell, openssl
**Prerequisites:** Phase 12 lessons on SMTP, MX records, and RFC 5322
**Time:** ~90 minutes

## Learning Objectives

- Connect to a POP3 and an IMAP server by hand, authenticate, and read messages.
- Distinguish the POP3 model (download-and-delete default, stateless) from the IMAP model (stateful, server-resident, multi-folder, multi-client safe).
- Use IMAP flags (`\Seen`, `\Answered`, `\Flagged`, `\Deleted`, `\Draft`, `\Recent`) and the `\Deleted` + `EXPUNGE` semantics.
- Use IMAP IDLE (RFC 2177) for server-push notifications and `SEARCH` for server-side filtering.
- Compare implicit-TLS (POP3S 995, IMAPS 993) and STARTTLS (RFC 3207 analogue for IMAP, RFC 7817) and recognize their security implications.
- Reason about when POP3 is the right choice and when IMAP is, based on access patterns and offline behavior.

## The Problem

You want to read mail from multiple devices: laptop, phone, webmail, work desktop. POP3's default behavior — download and delete from the server — leaves each device with a different view; read messages on the phone, they vanish from the laptop's POP3 run. IMAP keeps everything on the server and synchronizes state across clients. But IMAP also keeps everything on the server: a multi-gigabyte mailbox needs server-side quota management, and the user cannot back up mail by simply copying the local mail folder. Each protocol makes different tradeoffs.

The trap is treating POP3 as obsolete. POP3 is still the right choice for some scenarios (an isolated kiosk, a single-user backup destination, an offline archival pull). And IMAP has its own pitfalls: many implementations do not expunge cleanly, the server can be a single point of failure, and the client must understand flags to behave correctly.

## The Concept

### POP3 lifecycle (RFC 1939)

```
S: +OK POP3 server ready <1896.697170952@dbc.mtview.ca.us>
C: USER alice
S: +OK User accepted
C: PASS hunter2
S: +OK Pass accepted
C: STAT
S: +OK 3 12345
C: LIST
S: +OK 2 messages:
S: 1 1234
S: 2 11111
S: .
C: RETR 1
S: +OK 1234 octets
S: <message body octets>
S: .
C: DELE 1
S: +OK message 1 deleted
C: QUIT
S: +OK POP3 server signing off
```

POP3 has three states: AUTHORIZATION (after connect), TRANSACTION (after successful USER/PASS), UPDATE (after QUIT). In UPDATE the server processes any pending DELE commands and closes the connection. POP3 supports optional TOP and UIDL commands; UIDL assigns each message a unique ID so a client can resume a session across reconnects.

### IMAP4rev1 lifecycle (RFC 3501)

```
S: * OK [CAPABILITY IMAP4rev1 STARTTLS LOGINDISABLED] server ready
C: a001 STARTTLS
S: a001 OK begin TLS negotiation now
... TLS handshake ...
C: a002 CAPABILITY
S: * CAPABILITY IMAP4rev1 IDLE MOVE OBJECTID ...
S: a002 OK CAPABILITY completed
C: a003 LOGIN alice hunter2
S: a003 OK LOGIN completed
C: a004 SELECT INBOX
S: * 5 EXISTS
S: * 0 RECENT
S: * FLAGS (\Answered \Flagged \Deleted \Seen \Draft)
S: * OK [PERMANENTFLAGS (\Deleted \Seen \*)] limited
S: a004 OK [READ-WRITE] SELECT completed
C: a005 IDLE
S: + idling
... (server pushes * 6 EXISTS when a new message arrives) ...
C: DONE
S: a005 OK IDLE terminated
C: a006 LOGOUT
S: * BYE
S: a006 OK LOGOUT completed
```

Every IMAP client command is prefixed with a tag (here `a001`); server responses reference the same tag. Responses to commands without explicit data start with `*`, then the data, then the tagged `OK`/`NO`/`BAD`. The state machine is larger than POP3: AUTHENTICATED, SELECTED, LOGOUT are the three primary states.

### The IMAP flag model

IMAP messages carry a set of flags (RFC 3501 §2.3.2):

| Flag | Meaning |
|---|---|
| `\Seen` | The message has been read |
| `\Answered` | The user has replied |
| `\Flagged` | Marked for follow-up (star) |
| `\Deleted` | Marked for deletion; actually removed at `EXPUNGE` |
| `\Draft` | Not yet sent |
| `\Recent` | Newly arrived in this session (cleared on next SELECT) |

The `\Deleted` flag does **not** delete; it only marks. The server only removes messages on `EXPUNGE` (or implicit `EXPUNGE` on some servers with the `OBJECTID` extension, RFC 8474). Closing a mailbox with `CLOSE` does an implicit `EXPUNGE`; closing with `UNSELECT` (RFC 3691) does not.

### IDLE: server-push notifications

`IDLE` (RFC 2177) lets the client send a command that puts the server in a state where unsolicited updates flow to the client without further commands. When the server receives a new message, it sends `* 6 EXISTS` without the client doing anything. The client sends `DONE` to exit IDLE and resume normal command mode. IDLE is how push mail on phones works without constant polling.

### The implicit-A-record vs UID vs MSN gotchas

POP3 numbers messages by their position in the mailbox (MSN — message sequence number), starting at 1. They can shift as messages are expunged. UIDL assigns each message a stable unique identifier. IMAP has the same distinction with `MSN` (the `* n EXISTS` count) and UID (set per mailbox via `UIDVALIDITY`, increased whenever UIDs need to be reassigned).

### TLS: implicit vs STARTTLS

Both POP3 and IMAP have two TLS modes:

| Mode | POP3 | IMAP | Behavior |
|---|---|---|---|
| Implicit TLS | 995 | 993 | TLS handshake immediately on connect (RFC 8314) |
| STARTTLS | 110 + STARTTLS command | 143 + STARTTLS command | TLS upgrade after AUTH command (RFC 7817 for IMAP) |

RFC 8314 (2021) recommends implicit TLS for both POP3 and IMAP going forward and deprecates the use of the plain ports plus STARTTLS in favor of the implicit-TLS ports.

### The choice matrix

| Need | POP3 | IMAP |
|---|---|---|
| Single device, offline-capable | Excellent | Workable |
| Multiple devices, shared state | Painful | Ideal |
| Server-side search | No | Yes |
| Folder hierarchy | Not standard | Yes |
| Server-side quota management | Limited | Yes |
| Backup by local copy | Natural | Optional |
| Push notifications | No (must poll) | IDLE, MOVE, OBJECTID |
| Client complexity | Low | High |

### The hybrid model

Many users today see neither protocol directly: they use a webmail client that talks IMAP internally and exposes a JS UI, or they use a mobile app that uses IMAP IDLE for push and a local cache for offline reading. POP3 survives mostly in niche roles: archival pull, ISP-only mailboxes, simple kiosks.

## Build It

1. Run `code/main.py` to simulate a POP3 STAT/RETR/DELE/QUIT session and an IMAP LOGIN/SELECT/IDLE/LOGOUT session.
2. Connect to a real mailbox with `openssl s_client -connect imap.example.com:993` and read the `* OK` banner; issue `a001 CAPABILITY` and read the extension list.
3. With `openssl s_client -connect pop.example.com:995`, run `USER`, `PASS`, `STAT`, `LIST`, `QUIT` by hand.
4. Send yourself a test message and watch the IMAP `* n EXISTS` count rise in another terminal running IDLE.
5. Use `python3 -c "import imaplib; ..."` or a similar client to FETCH a message by UID, set the `\Seen` flag, and EXPUNGE.
6. With STARTTLS: `openssl s_client -starttls imap -connect imap.example.com:143` then EHLO-style commands.

```python
# Excerpt from code/main.py
def pop3_session(msgs: list[tuple[int, bytes]]) -> list[str]:
    log = []
    log.append(f"S: +OK POP3 ready ({len(msgs)} messages)")
    for uid, body in msgs:
        log.append(f"C: RETR {uid}    -> {len(body)} octets")
        log.append(f"C: DELE {uid}    -> marked for deletion")
    log.append("C: QUIT          -> UPDATE state; physical delete happens here")
    return log
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| POP3 dialog | `pop3_session(msgs)` | `poplib` (Python) | RFC 1939 |
| IMAP dialog | `imap_session(...)` | `imaplib` (Python) | RFC 3501 |
| Flag set | `apply_flag(uid, flag)` | `STORE` | RFC 3501 §6.4.6 |
| IDLE | `idle_session(...)` | Dovecot, Cyrus | RFC 2177 |
| UID/UIDVALIDITY | `mailbox_state(...)` | Dovecot, Courier | RFC 3501 §2.3.1 |
| TLS upgrade | STARTTLS | `openssl s_client -starttls imap` | RFC 7817 |
| Implicit TLS | connect to 993 / 995 | RFC 8314 | RFC 8314 |

## Ship It

Produce one reusable artifact under `outputs/`:

- A side-by-side reference of POP3 and IMAP commands with equivalent tasks (login, list, retrieve, delete) for fast lookup.
- A minimal Python client (using only the stdlib `imaplib` and `poplib`) that authenticates, lists messages, and downloads one.
- A TLS decision table for "implicit vs STARTTLS" with the modern (RFC 8314) recommendation.

Start from [`outputs/prompt-imap4-vs-pop3-final-delivery.md`](../outputs/prompt-imap4-vs-pop3-final-delivery.md).

## Exercises

1. Connect to a real IMAP server with `openssl s_client -connect imap.example.com:993`. Send `a001 CAPABILITY` and list every extension.
2. Use `python3 imaplib` to log in, SELECT INBOX, FETCH the most recent message by UID, and print its envelope.
3. Set the `\Seen` flag on a message and verify by FETCHing its flags.
4. With IDLE running, send yourself a message and observe the unsolicited `* n EXISTS` notification.
5. Compare POP3 STAT and IMAP STATUS: which gives you more information about the mailbox without listing messages?
6. Capture a `tcpdump -w imap.pcap tcp port 993` while fetching a message and observe that the body bytes are inside the TLS record layer (not visible in plaintext).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| POP3 | "the download protocol" | RFC 1939: simple retrieve-and-delete on TCP/110 (or 995 for TLS) |
| IMAP4rev1 | "the sync protocol" | RFC 3501: stateful, server-resident, multi-folder on TCP/143 (or 993 for TLS) |
| \Seen | "read flag" | IMAP flag set when the user has read the message |
| \Deleted | "delete flag" | IMAP flag that marks for deletion; server removes on EXPUNGE |
| IDLE | "push notifications" | RFC 2177: server pushes updates to the client without further commands |
| UIDVALIDITY | "the UID epoch" | IMAP per-mailbox counter; changes when UIDs are reassigned |
| STARTTLS | "upgrade to TLS" | RFC 7817 (IMAP) / RFC 3207 analogue: upgrade the connection after AUTH |
| Implicit TLS | "connect to 993" | RFC 8314: TLS from the very first byte; recommended over STARTTLS today |
| UID | "stable id" | IMAP per-mailbox unique message identifier (paired with UIDVALIDITY) |
| EXPUNGE | "actually delete" | The command that physically removes \Deleted-flagged messages |

## Further Reading

- RFC 1939 — Post Office Protocol Version 3 (POP3)
- RFC 3501 — Internet Message Access Protocol Version 4rev1 (IMAP4rev1)
- RFC 2177 — IMAP4 IDLE command
- RFC 4314 — IMAP4 Access Control List (ACL) Extension
- RFC 5256 — IMAP4 SORT and THREAD Extensions
- RFC 5465 — IMAP4 METADATA Extension
- RFC 6203 — IMAP4 Extension for Fuzzy Search
- RFC 6851 — IMAP MOVE Extension
- RFC 7162 — IMAP4 Extensions for Quick Mailbox Resynchronization (CONDSTORE, QRESYNC)
- RFC 7817 — IMAP4 StartTLS Extension (RFC 7817)
- RFC 8314 — Cleartext Considered Obsolete: Use TLS (deprecates STARTTLS)
- RFC 8474 — IMAP OBJECTID Extension
- Python `imaplib` and `poplib` — reference clients
- `openssl s_client -starttls imap` and `-starttls pop3` — manual TLS upgrade
