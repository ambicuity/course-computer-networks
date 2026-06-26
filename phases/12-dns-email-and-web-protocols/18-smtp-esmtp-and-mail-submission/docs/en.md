# SMTP, ESMTP Extensions, and Mail Submission

> SMTP (RFC 5321) is the ASCII text-based protocol that moves mail between MTAs. A client opens a TCP connection to port 25, the server announces itself with a `220` banner, the client sends `EHLO` (or `HELO` for old servers), the server replies `250` and lists its **ESMTP** extensions, then the client uses `MAIL FROM:` and one or more `RCPT TO:` to describe the envelope, then `DATA` to send the RFC 5322 message terminated by a single dot on a line. Reply codes are three digits: 2xx success, 3xx more input needed, 4xx transient failure (retry), 5xx permanent failure (bounce). The modern `EHLO`/ESMTP pair unlocks `AUTH` (RFC 4954) for client authentication, `STARTTLS` (RFC 3207) to upgrade the connection to TLS, `SIZE` (RFC 1870) to pre-declare message size, `8BITMIME` (RFC 6152) and `BINARYMIME` (RFC 3030) to ship non-ASCII bytes without 7-bit conversion, `CHUNKING` (RFC 3030) for streaming large messages, and `SMTPUTF8` (RFC 6531) for internationalized addresses. Port 587 (RFC 6409) is the **mail submission** port — what user agents use; port 25 is the **MTA-to-MTA** transfer port; port 465 is the legacy SMTPS port.

**Type:** Lab
**Languages:** Python, shell, telnet
**Prerequisites:** Phase 12 lessons on RFC 5322, MIME, and DNS MX records
**Time:** ~90 minutes

## Learning Objectives

- Read an SMTP reply code (2xx, 3xx, 4xx, 5xx) and identify which class of failure it represents.
- Drive a manual SMTP session with `telnet` or `nc` and capture every command and reply, including the ESMTP extension banner.
- Distinguish SMTP from ESMTP: `HELO` vs `EHLO`, and the resulting reply structure.
- Negotiate `STARTTLS`, `AUTH`, `SIZE`, `8BITMIME`, and `CHUNKING` in an EHLO response and predict their effect on subsequent commands.
- Use port 587 with `AUTH` for mail submission (RFC 6409) and port 25 for MTA-to-MTA relay.
- Send a multipart message by hand over SMTP and verify the byte-stuffing rule for lines beginning with a dot.

## The Problem

You want to debug why a transactional email is being rejected by your provider's MTA. The bounce message says `554 5.7.1 ... refused` but you cannot tell whether it is the envelope sender, the recipient, the size, or the lack of authentication. The only way to find out is to talk SMTP yourself — open a TCP connection to port 25, send `EHLO`, read the extension list, then walk through `MAIL FROM`, `RCPT TO`, and `DATA` exactly as your user agent does, and watch each reply as it comes back. Once you have done this once, the bounce messages stop being mysterious.

The trap is treating SMTP as something your user agent does for you. It is, but the user agent is just an ESMTP client that opens the connection, negotiates extensions, and follows the exact protocol you can drive by hand. The advantage of doing it by hand is that you see every reply code, every extension, and every negotiation step that real software hides.

## The Concept

### The transcript

A canonical SMTP exchange, taken from the textbook, with reply codes inline:

```
S: 220 mail.example.com ESMTP ready
C: EHLO client.example.org
S: 250-mail.example.com Hello client.example.org
S: 250-SIZE 10485760
S: 250-8BITMIME
S: 250-STARTTLS
S: 250-ENHANCEDSTATUSCODES
S: 250-PIPELINING
S: 250-CHUNKING
S: 250 HELP
C: STARTTLS                       (optional: upgrade to TLS)
... TLS handshake ...
C: EHLO client.example.org        (re-greet after TLS)
S: 250 ... (new EHLO list)
C: AUTH PLAIN dGVzdAB0ZXN0AHRlc3RwYXNz
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<alice@example.com>
S: 250 2.1.0 Sender OK
C: RCPT TO:<bob@example.org>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 Send message; end with <CR><LF>.<CR><LF>
C: From: alice@example.com
C: To: bob@example.org
C: Subject: Test
C:
C: Hi Bob, this is a test.
C: .
S: 250 2.0.0 OK queued as ABCDEF123
C: QUIT
S: 221 2.0.0 Bye
```

Every line sent by the server starts with a 3-digit code. Multi-line replies use a hyphen after the code (`250-...`); the final line uses a space (`250 ...`).

### Reply code classes (RFC 5321 §4.2)

| Class | Meaning | Retry? |
|---|---|---|
| 2xx | Success | n/a |
| 3xx | More input needed (e.g., `354` after `DATA`) | n/a |
| 4xx | Transient failure (greylist, queue full) | Yes, after delay |
| 5xx | Permanent failure (bad address, refused) | No, bounce the message |

The second digit narrows the meaning: `x1x` is "address status", `x2x` is "mail system", `x5x` is "mailbox" or "protocol". The third digit is specific. Examples: `250` = OK, `354` = send mail, `421` = service not available, `450` = mailbox busy, `452` = insufficient storage, `500` = unrecognized command, `550` = mailbox not found, `554` = transaction failed.

### ESMTP extensions

When a client sends `EHLO` (extended hello) instead of `HELO`, the server replies with a multi-line list of supported extensions:

```
250-mail.example.com Hello client.example.org
250-SIZE 10485760
250-8BITMIME
250-STARTTLS
250-ENHANCEDSTATUSCODES
250-PIPELINING
250-CHUNKING
250 HELP
```

The client may then use any of those extensions. Notable ones:

| Extension | RFC | Effect |
|---|---|---|
| `STARTTLS` | 3207 | Upgrade the connection to TLS; mandatory for submission |
| `AUTH` | 4954 | Authenticate the client (PLAIN, LOGIN, CRAM-MD5) |
| `SIZE` | 1870 | Pre-declare message size in `MAIL FROM`; lets server refuse early |
| `8BITMIME` | 6152 | Allow 8-bit bytes in the body |
| `BINARYMIME` | 3030 | Allow arbitrary binary in the body |
| `CHUNKING` | 3030 | Stream the message in chunks instead of `DATA ... .` |
| `ENHANCEDSTATUSCODES` | 2034 | Reply codes carry extra semantic info after a `2.0.0` style status |
| `PIPELINING` | 2197 | Send multiple commands without waiting for each reply |
| `SMTPUTF8` | 6531 | Internationalized addresses (UTF-8 mailbox local-parts) |

### The `AUTH PLAIN` mechanism

`AUTH PLAIN` is the most common submission mechanism. The client sends:

```
AUTH PLAIN <base64(\0login\0password)>
```

i.e., NUL login NUL password, base64-encoded. RFC 4954 requires `AUTH` only after `STARTTLS` (or over a port like 465 that is implicitly TLS). `AUTH LOGIN` is a legacy variant that sends the username and password in separate commands. `CRAM-MD5` is a challenge-response mechanism that avoids sending the password in cleartext but is rarely used today.

### The byte-stuffing rule for `DATA`

When sending the message body, lines that begin with a dot must be escaped (RFC 5321 §4.5.2): the sender adds an extra leading dot, and the receiver strips the first dot from any line that begins with one. So a body containing a single `.` becomes `..` on the wire. The terminator is `<CR><LF>.<CR><LF>` on a line by itself.

### Mail submission vs MTA-to-MTA (RFC 6409)

| Port | Service | Auth required? | TLS required? |
|---|---|---|---|
| 25 | SMTP (MTA-to-MTA relay) | No | STARTTLS recommended |
| 587 | Mail submission (MUA to MSA) | Yes | STARTTLS recommended |
| 465 | SMTPS (legacy implicit TLS) | Yes | Yes (implicit) |

A **Message Submission Agent** (MSA) is just an MTA running on port 587 that requires `AUTH` and refuses to relay for unauthenticated clients. It exists to stop port-25 open relays (RFC 5065) from being abused by spammers. Most modern operating systems no longer listen on port 25 at all for outbound mail; user agents are pointed at port 587 on the ISP's MSA.

### The flow for an outbound message

```
user agent  --(587+STARTTLS+AUTH)--&gt;  MSA  --(25+STARTTLS)--&gt;  next MTA  --(25+STARTTLS)--&gt;  ...  --(25+STARTTLS)--&gt;  final MTA  --(143/993 IMAP or 110/995 POP)--&gt;  user agent
```

Each hop adds a `Received:` header. SPF, DKIM, and DMARC checks happen at each receiving MTA.

### What `5.7.1` means

A bounce like `554 5.7.1 ... Sender address rejected` uses the **ENHANCEDSTATUSCODES** structure: `5` = permanent, `7` = security/policy, `1` = sender authentication. The `5.7.1` family almost always means "your envelope `MAIL FROM` failed SPF, DKIM, or DMARC, or your IP is on a blocklist". RFC 3463 defines the enhanced status codes.

## Build It

1. Run `code/main.py` to simulate an SMTP dialog and print the state machine transitions and reply codes.
2. Open a real connection with `telnet mail.isp.com 25` (or `nc -v mail.isp.com 25`); read the `220` banner.
3. Send `EHLO test.example.org` and read the multi-line extension list.
4. Issue `MAIL FROM:<you@your-domain.com>` and observe the reply.
5. Send `RCPT TO:<a-friend@example.com>` and observe the reply.
6. Send `DATA`, paste a minimal RFC 5322 message ending with a dot on a line, and observe the `250` queued reply.
7. Repeat with `STARTTLS` first: `openssl s_client -starttls smtp -connect mail.isp.com:587` then EHLO again.

```python
# Excerpt from code/main.py
def classify_reply(code: int) -> str:
    if code < 300:
        return "OK"
    if code < 400:
        return "more input"
    if code < 500:
        return "transient (retry)"
    return "permanent (bounce)"
```

## Use It

| Capability | Our implementation | Real tool | Reference |
|---|---|---|---|
| SMTP dialog | `SmtpClient.simulate(...)` | `telnet`, `nc` | RFC 5321 §4 |
| Reply parser | `parse_reply(line)` | postfix logs | RFC 5321 §4.2 |
| Enhanced codes | `parse_enhanced(line)` | pymap, smtplib | RFC 3463 |
| TLS upgrade | `STARTTLS` | openssl s_client | RFC 3207 |
| AUTH PLAIN | `auth_plain(user, pw)` | smtplib.SMTP.login | RFC 4954 |
| Byte stuffing | `dot_stuff(body)` | smtplib | RFC 5321 §4.5.2 |

## Ship It

Produce one reusable artifact under `outputs/`:

- An annotated transcript of a real SMTP session with `EHLO`, `STARTTLS`, `AUTH`, `MAIL FROM`, `RCPT TO`, `DATA`, and the final `QUIT`.
- A bounce-code decoder that turns `554 5.7.1 ...` into a human explanation ("policy / sender authentication failed").
- A reusable Python SMTP client (or `smtplib` recipe) that submits a message with STARTTLS and AUTH.

Start from [`outputs/prompt-smtp-esmtp-and-mail-submission.md`](../outputs/prompt-smtp-esmtp-and-mail-submission.md).

## Exercises

1. Telnet to a real mail server on port 25, read the banner, send `EHLO test.example.com`, and list every ESMTP extension in the reply.
2. Issue `MAIL FROM:<test@example.com>` and observe the response; try again with `MAIL FROM:<>` and note the empty envelope sender used for bounces.
3. Send a tiny `DATA` payload ending with `.` on its own line and verify the byte-stuffing rule by sending a body that starts with a dot.
4. Run `openssl s_client -starttls smtp -connect mail.isp.com:587` and confirm the EHLO reply changes after TLS.
5. Use `AUTH PLAIN` to log in (capture the base64 of `\0user\0pass` with `printf '\0user\0pass' | base64`) and observe the `235` reply.
6. Capture a `tcpdump -w smtp.pcap tcp port 587` while sending a real submission; in Wireshark, follow the TCP stream and annotate each command and reply.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| SMTP | "the mail protocol" | RFC 5321: ASCII text protocol on TCP, port 25 for MTA-to-MTA |
| ESMTP | "extended SMTP" | RFC 5321: `EHLO` greeting with extension banner |
| HELO / EHLO | "the greeting" | `HELO` for plain SMTP, `EHLO` to request extension list |
| MAIL FROM | "envelope sender" | RFC 5321: opens the mail transaction with the envelope sender |
| RCPT TO | "envelope recipient" | RFC 5321: one per recipient; precedes DATA |
| DATA | "the message" | RFC 5321: command that starts the body; terminated by `\r\n.\r\n` |
| Reply code | "the 3-digit number" | 2xx OK, 3xx more input, 4xx transient, 5xx permanent |
| STARTTLS | "upgrade to TLS" | RFC 3207: upgrade the SMTP connection to TLS on the same port |
| AUTH | "login" | RFC 4954: client authentication; PLAIN, LOGIN, CRAM-MD5 |
| Submission port | "port 587" | RFC 6409: MSA port for user agents; AUTH required |
| Enhanced status | "5.7.1" | RFC 3463: 5 = permanent, 7 = security, 1 = sender auth |
| Byte stuffing | "the dot rule" | RFC 5321 §4.5.2: escape leading dots in DATA |

## Further Reading

- RFC 5321 — Simple Mail Transfer Protocol
- RFC 3207 — SMTP Service Extension for Secure SMTP over TLS (STARTTLS)
- RFC 4954 — SMTP Service Extension for Authentication (AUTH)
- RFC 6409 — Message Submission for Mail (port 587)
- RFC 2034 — SMTP Service Extension for Returning Enhanced Error Codes
- RFC 3463 — Enhanced Mail System Status Codes
- RFC 1870 — SMTP Service Extension for Message Size Declaration (SIZE)
- RFC 6152 — SMTP Service Extension for 8-bit MIME Transport (8BITMIME)
- RFC 3030 — SMTP Service Extensions for Transmission of Large and Binary Messages (CHUNKING, BINARYMIME)
- RFC 6531 — SMTP Extension for Internationalized Email (SMTPUTF8)
- RFC 5065 — Email Submission Operations (anti-open-relay guidance)
- `smtplib` Python module — reference client implementation
- `openssl s_client -starttls smtp` — manual TLS upgrade from the command line
