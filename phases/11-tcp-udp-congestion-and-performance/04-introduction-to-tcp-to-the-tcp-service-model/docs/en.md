# Introduction to TCP to The TCP Service Model

> Section 6.5.1 names TCP as the protocol that delivers a **reliable end-to-end byte stream over an unreliable internetwork**, formally defined in **RFC 793 (September 1981)** and amended by RFC 1122, RFC 1323, RFC 2018, RFC 2581, RFC 2873, RFC 2988, RFC 3168, and indexed by **RFC 4614**. Each TCP segment is a fixed **20-byte header plus options plus up to 65,495 bytes of payload**, the practical **MSS** (Maximum Segment Size) often being **1460 bytes** to fit in one Ethernet frame. Section 6.5.2 fixes the **service model**: connection-oriented over a **socket** = `(IP address, 16-bit port)` pair, full-duplex, point-to-point, **byte stream** (no message boundaries), with **well-known ports 0-1023** (e.g., **20/21** FTP, **22** SSH, **25** SMTP, **80** HTTP, **443** HTTPS), **registered 1024-49151**, and **ephemeral 49152-65535**. The textbook calls out two service-level artifacts that still live in the protocol but are rarely used: the **PUSH** flag (now `TCP_NODELAY` in POSIX) and **URGENT data** (now discouraged). The lesson builds a TCP service-model simulator with a `Socket` dataclass, a `Connection = (local_socket, remote_socket)` pair, and a `StreamBuffer` that shows how four 512-byte writes can be reassembled into one 2048-byte read.

**Type:** Build
**Languages:** Python, no external dependencies
**Prerequisites:** UDP (lesson 02), socket API familiarity (any language), basic byte arithmetic
**Time:** ~90 minutes

## Learning Objectives

- Identify the **RFC stack** that defines modern TCP (793, 1122, 1323, 2018, 2581, 2873, 2988, 3168, 4614) and what each adds.
- Sketch the **TCP service model**: connection-oriented, full-duplex, point-to-point, byte stream, no message boundaries.
- Implement a **Socket = (IP, port)** pair and a **Connection = (local_socket, remote_socket)** identity that matches the textbook's "no virtual circuit numbers" rule.
- Recall the **well-known port** assignments and explain why `21` is for FTP control while `20` is for FTP data.
- Demonstrate that **byte-stream semantics** preserve order but not message boundaries using a `StreamBuffer`.
- Explain the modern status of **PUSH** and **URGENT data** and why neither is the right tool for modern signaling.

## The Problem

Two teams in the same company are debugging the same symptom: a chat application's messages sometimes arrive at the receiver out of order, and the receiver code "feels wrong." Team A blames the network. Team B blames the OS. Both are partly right and partly wrong, because the symptom is *natural* to TCP: TCP is a **byte stream**, not a message stream, and the application's mental model treats it as a message stream.

Concretely: the sender calls `send("hello")`, then `send(" ")`, then `send("world")`. The receiver calls `recv(1024)` once and might get `b"hello world"` (one read, the canonical example) — or `b"hel"`, then a separate `b"lo world"` (two reads, also legal). The receiver cannot detect that the sender made three writes; that information was lost the moment the bytes were handed to TCP.

The team's confusion comes from a missing distinction between the **TCP service model** (Sec. 6.5.2) and the **wire format** (Sec. 6.5.4). The service model says: *here is a reliable ordered byte pipe between two endpoints.* The wire format says: *here are the bytes I am putting on the wire right now, with sequence numbers and an advertised window.* The application must add its own framing on top of TCP — length prefixes, delimiters, protobuf tags — if it cares about message boundaries.

This lesson is about the service model. The next lesson takes apart the wire format.

## The Concept

### The RFC stack behind TCP

Section 6.5.1 inventories the TCP standards. The "core" TCP is RFC 793 (Postel, September 1981). Everything since then is an amendment or a clarification. A working modern TCP supports:

| RFC | Year | What it adds |
|---|---|---|
| RFC 793 | 1981 | Base TCP specification. |
| RFC 1122 | 1989 | Requirements for Internet Hosts (clarifications and bug fixes). |
| RFC 1323 | 1992 | **PAWS** (Protection Against Wrapped Sequence numbers), **Window Scale**, **Timestamps** for high-bandwidth paths. |
| RFC 2018 | 1996 | **SACK** (Selective Acknowledgement) — let the receiver tell the sender exactly which bytes are missing. |
| RFC 2581 | 1999 | **Congestion control** — slow start, congestion avoidance, fast retransmit, fast recovery. |
| RFC 2873 | 2000 | Repurposing of TCP header fields (e.g., for ECN nonce). |
| RFC 2988 | 2000 | Retransmission timer algorithm (replaced by RFC 6298). |
| RFC 3168 | 2001 | **ECN** (Explicit Congestion Notification) in the TCP header. |
| RFC 4614 | 2006 | A roadmap for the TCP-related RFCs (since "the full collection is even larger"). |
| RFC 6298 | 2011 | Current retransmission-timer computation (replaces RFC 2988). |
| RFC 5681 | 2009 | Congestion-control updates (replaces RFC 2581). |

The lesson's takeaway: when you hear "TCP" you should picture the union of all of these. Any single RFC on its own describes a non-modern TCP.

### What TCP guarantees

The TCP service is **connection-oriented, full-duplex, point-to-point, byte-stream, reliable, ordered**, and congestion-controlled. Each phrase has a precise meaning:

| Property | Meaning |
|---|---|
| Connection-oriented | Two endpoints explicitly establish and tear down the connection. |
| Full-duplex | Both sides can send simultaneously; data flows in both directions. |
| Point-to-point | Exactly two endpoints per connection. No multicast, no broadcast. |
| Byte stream | The application writes bytes; the application reads bytes. No message boundaries. |
| Reliable | Lost segments are retransmitted until acknowledged. |
| Ordered | Bytes are delivered to the receiver in the order written by the sender. |
| Congestion-controlled | The sender paces itself using the AIMD mechanism from lesson 01. |

The textbook notes the only two things TCP does *not* give the application: **message boundaries** and **timing guarantees** (latency, jitter). The application must add framing on top.

### Sockets, ports, and connections

Section 6.5.2 says TCP service is obtained by both sides creating an endpoint called a **socket**. A socket number is `(IP address, 16-bit port)`. The TCP "name" for this endpoint is **TSAP** (Transport Service Access Point). A **connection** is identified by the *pair* of endpoints `(socket1, socket2)`. There are no virtual circuit numbers; the four-tuple `(src_ip, src_port, dst_ip, dst_port)` is the connection's identity, which is why a single server socket can host many simultaneous client connections (the standard HTTP/1.1 keep-alive server has thousands).

### Well-known, registered, and ephemeral ports

The textbook reproduces the IANA port assignments. The three ranges:

| Range | Allocation | Examples |
|---|---|---|
| **0 – 1023** | Well-known; bindable only by privileged processes | 20/21 FTP, 22 SSH, 25 SMTP, 53 DNS, 80 HTTP, 110 POP3, 143 IMAP, 443 HTTPS, 543 RTSP, 631 IPP |
| **1024 – 49151** | Registered; assigned by IANA on request | 3306 MySQL, 5432 PostgreSQL, 8080 HTTP-alt |
| **49152 – 65535** | Dynamic / ephemeral; client-side allocation | Any client socket; `ss -tnp` shows them as the local port |

RFC 6335 re-numbered the boundaries in 2011 to align with the original Berkeley sockets convention. The textbook's pre-2011 numbers (1024-65535 as a single range, with the lower half privileged) are still in wide circulation; the IANA-registered range above 1024 mostly preserves compatibility.

### The inetd pattern

The textbook describes the historical `inetd` (Internet daemon) pattern: a single daemon binds to many well-known ports and forks the right specialized daemon when a connection arrives. Modern systems use the same idea under different names: `systemd` socket activation, `xinetd` for legacy services, `launchd` on macOS. The point is the same: don't keep daemons idle on ports that are rarely used; activate them on demand.

### Byte-stream semantics and the four-writes problem

The textbook's Fig. 6-35 is the canonical example: four 512-byte writes may be delivered as four 512-byte reads, two 1024-byte reads, one 2048-byte read, or any other partition. The receiver cannot tell. The application must add its own framing:

- **Length-prefixed**: write a 4-byte length before the message body; the receiver reads 4 bytes, then reads `length` more.
- **Delimiter-separated**: pick a byte sequence that cannot appear in the payload (e.g., `\r\n\r\n` in HTTP/1.1) and split on it.
- **Self-describing**: use a serialization format with explicit field tags (protobuf, JSON, msgpack).
- **Record-oriented**: define your own framing at the application layer (Netstring, SSL records).

A common bug is to assume a single `send` corresponds to a single `recv`. It does not.

### PUSH: the flag nobody uses correctly

The **PUSH** flag was originally meant to tell the receiver "deliver these bytes to the application immediately, do not buffer." The textbook says *applications cannot literally set the PUSH flag*; instead, sockets expose a `TCP_NODELAY` option (POSIX) or `TCP_NODELAY = true` in Java/.NET that disables **Nagle's algorithm** and ships small writes immediately. Modern TCP stacks still set the PUSH flag on the last segment of a burst so the receiver knows to flush, but the application cannot influence it.

### URGENT data: discouraged

The **URGENT** flag and the 16-bit **Urgent Pointer** field (offset from the sequence number) were meant to ship an out-of-band signal — the textbook's example is a CTRL-C to abort a running remote computation. The receiver's TCP signals the application that urgent data is present, and the application reads the stream to find it. The textbook notes the design is "crude" and the implementation is inconsistent across stacks. RFC 6093 explicitly discourages using urgent data. Modern signaling happens out-of-band (a separate control socket, a SIGINT, a websocket sub-protocol).

## Build It

The artifact is `code/main.py`. It contains a stdlib-only TCP service-model simulator:

1. **Socket and connection**
   - `Socket` dataclass with `ip: str` and `port: int`.
   - `Connection` dataclass with `local: Socket` and `remote: Socket`.
   - Hashable so it can be a dictionary key.

2. **StreamBuffer**
   - Holds a deque of bytes from `send()` calls.
   - `write(data: bytes)` records the write but does not preserve message boundaries.
   - `read(n: int)` returns up to `n` bytes from the front.
   - Demonstrate that four 512-byte writes can be read back as one 2048-byte read.

3. **Port allocator**
   - `pick_well_known(n)` returning a registered port from the textbook's list (20, 21, 22, 25, 53, 80, 110, 143, 443, 543, 631).
   - `pick_ephemeral()` returning a port in 49152-65535.

4. **Connection table**
   - `ConnectionTable` that maps `Connection -> app_state`.
   - Show that two clients to the same server port produce two distinct connection identities.

5. **RFC stack report**
   - Print a table of every RFC listed in the textbook's stack with the year and a one-line summary.

Run with `python3 code/main.py`. No pip dependencies.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify TCP connection identity | `ss -tnp` showing `(local, remote)` four-tuple. | The four-tuple matches what the application used; the kernel indexes the socket by it. |
| Verify byte-stream semantics | Wireshark capture of four `send` calls. | The TCP segments do not necessarily align with the four writes; the receiver can `read` them however the buffer is scheduled. |
| Find the listening socket | `ss -tlnp` on the server. | The local address is `0.0.0.0:<port>` or `[::]:<port>` for both IPv4 and IPv6. |
| Confirm TCP_NODELAY | `strace -e trace=setsockopt` on the application. | A `TCP_NODELAY = 1` call shows up; small writes go out immediately. |
| Diagnose "messages stuck together" | Application log showing merged messages from a TCP stream. | Cause is almost always missing application-layer framing; fix with length-prefix or self-describing format. |

## Ship It

The `outputs/` directory should contain `tcp-service-runbook.md` with three sections:

1. **Service-model contract**: what the application can and cannot assume about a TCP stream.
2. **Framing patterns**: a comparison of length-prefix, delimiter, and self-describing framing with trade-offs.
3. **Port-allocation decision**: a list of the ports in use in your service, marked as well-known, registered, or ephemeral.

## Exercises

1. **Four-write merge**. Using `StreamBuffer`, write 512 bytes four times, then `read(2048)`. Confirm the read returns all 2048 bytes in one call.
2. **Read partitioning**. Write 2048 bytes, then `read(1024)` twice. Confirm each read returns 1024 bytes.
3. **Connection identity**. Create a server socket on port 80 and two client connections from different ephemeral ports. Confirm the `Connection` instances are different.
4. **RFC index**. Print the table of all 11 RFCs from the textbook stack. Pick one and read its abstract on `rfc-editor.org`.
5. **TCP_NODELAY trace**. If you have a POSIX shell, run `strace -e setsockopt python3 -c "import socket; s=socket.socket(); s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)"` and confirm the option was set.
6. **URGENT data sanity**. Explain in two sentences why a modern application should not use URGENT data even though the protocol still supports it.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Socket | "IP plus port." | The TCP endpoint identity: `(IP address, 16-bit port)`. |
| Connection | "A pair of sockets." | The TCP connection identity: `(local_socket, remote_socket)`. Two connections to the same server port are distinct because their remote sockets differ. |
| Well-known port | "Below 1024." | IANA-assigned port, bindable only by privileged processes (e.g., 22 SSH, 80 HTTP, 443 HTTPS). |
| Ephemeral port | "Above 49152." | The kernel's pool of client-side ports; ephemeral means "lives for one socket's lifetime." |
| Byte stream | "No message boundaries." | TCP delivers bytes in order with no record markers. The application must add framing. |
| MSS | "1460 on Ethernet." | Maximum Segment Size, the largest TCP payload that fits in the link MTU minus IP + TCP headers. |
| PUSH | "Force the bytes out." | A TCP header flag set on the last segment of a burst; not directly settable by applications. Use `TCP_NODELAY` instead. |
| URGENT data | "Out-of-band signal." | A TCP mechanism marked by the URG flag and the Urgent Pointer; now discouraged by RFC 6093. |

## Further Reading

- Tanenbaum, Feamster, Wetherall — *Computer Networks*, Sec. 6.5.1 and 6.5.2.
- RFC 793 (Postel, 1981) — base TCP.
- RFC 1122 (Braden, 1989) — Host Requirements (clarifications, error handling).
- RFC 1323 (Jacobson, Braden, Borman, 1992) — PAWS, Window Scale, Timestamps.
- RFC 2018 (Mathis, Mahdavi, Floyd, Romanow, 1996) — SACK.
- RFC 2581 (Allman, Paxson, Stevens, 1999) — congestion control.
- RFC 5681 (Allman, Paxson, Blanton, 2009) — updates RFC 2581.
- RFC 3168 (Ramakrishnan, Floyd, Black, 2001) — ECN.
- RFC 4614 (Duke, Braden, Eddy, Blanton, 2006) — TCP roadmap.
- RFC 6093 (Gellens, Jennings, Mahy, 2011) — on discouraging urgent data.
- RFC 6335 (Cotton, Eggert, Touch, Westerlund, 2011) — port-number registry.
